import json
import re
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from conftest import cli_invoke
from herder import FakeProvider
from llama.cli import app
from llama.models import Candidate, Provenance, RecordingSummary, Show
from llama.stages.gather import run_gather
from llama.util import length_seconds
from llama.workspace import ShowWorkspace, read_model, read_overrides, write_artifact

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures"


class StubIA:
    """Serves one metadata dict for every identifier (single-recording
    tests). Copied from test_stage_gather.py rather than imported, per the
    orchestrator ruling for this task: it's a private test double, not a
    shared production interface, and test_stage_gather.py's own copy is not
    part of any importable helper module."""

    def __init__(self, md=None):
        self.md = md or json.loads((FIXTURES / "gd73_metadata.json").read_text())

    def metadata(self, identifier):
        return self.md


class MultiIA:
    """Serves per-identifier metadata -- for fixtures with a donor recording
    alongside the target (Task 6: the sibling-arm tests). Copied from
    test_stage_gather.py's own copy, same rationale as `StubIA` above: a
    private test double, not a shared production interface."""

    def __init__(self, mapping):
        self.mapping = mapping

    def metadata(self, identifier):
        return self.mapping[identifier]


def _ymsb_candidate():
    return Candidate(
        performance_id="YonderMountainStringBand/2005-12-31",
        collection="YonderMountainStringBand", date="2005-12-31",
        venue="Fillmore Auditorium", city="Denver, CO",
        recordings=[RecordingSummary(identifier="ymsb2005-12-31.flac16.wav")])


def test_help_shows_description():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Live Music Archive" in result.output


def test_version_flag_works():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0


def test_version_is_no_longer_a_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_config_on_callback_works(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path}"\n')
    result = runner.invoke(app, ["--config", str(cfg), "status"])
    assert result.exit_code == 0, result.output


def test_config_after_subcommand_now_fails(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path}"\n')
    result = runner.invoke(app, ["status", "--config", str(cfg)])
    assert result.exit_code != 0


def test_artists_include_junk_accepted_all_rejected(tmp_path: Path, monkeypatch):
    import llama.cli as cli

    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "load_or_build", lambda ia, cache, refresh=False: [])
    accepted = runner.invoke(app, ["--config", str(cfg), "artists", "--include-junk"])
    assert "No such option" not in accepted.output
    rejected = runner.invoke(app, ["--config", str(cfg), "artists", "--all"])
    assert rejected.exit_code != 0
    assert "No such option" in rejected.output


def test_help_orders_and_panels_commands():
    out = runner.invoke(app, ["--help"]).output
    for panel in ["Acquire", "Watch", "Fix & ship", "Sessions & config"]:
        assert panel in out


def test_pipeline_exits_zero_with_no_config_present():
    result = runner.invoke(app, ["pipeline"])
    assert result.exit_code == 0, result.output


def test_pipeline_is_in_the_watch_panel():
    out = runner.invoke(app, ["--help"]).output
    assert "pipeline" in out


def test_pipeline_prints_stage_names_and_gates():
    out = runner.invoke(app, ["pipeline"]).output
    for stage in ["interpret", "search", "winnow", "select", "gather",
                  "research", "vet", "brief", "package", "deliver"]:
        assert stage in out, stage
    assert "gate 1" in out
    assert "gate 2" in out


def test_pipeline_prints_state_names():
    out = runner.invoke(app, ["pipeline"]).output
    for state in ["held", "selected", "gathered", "researched", "vetted",
                  "briefed", "packaged", "delivered"]:
        assert state in out, state


def test_pipeline_prints_redo_hatch():
    out = runner.invoke(app, ["pipeline"]).output
    assert "fix" in out
    assert "redo --from" in out


def test_pipeline_makes_no_writes(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["pipeline"])
    assert result.exit_code == 0
    assert list(tmp_path.iterdir()) == []


def _show_with(matched_flags):
    """duration_sec=300 on every track so _fmt_dur never falls back to its own
    "?" for a missing duration -- that would collide with the unmatched-track
    marker this suite is asserting on, independent of `matched`."""
    from llama.models import Show, Track

    return Show(
        performance_id="x/1990-03-29", identifier="gd90-03-29", artist="Grateful Dead",
        date="1990-03-29",
        tracks=[Track(index=i + 1, set="1", title=f"Song {i + 1}",
                      filename=f"t{i + 1}.mp3", title_source="tags", matched=m,
                      duration_sec=300)
                for i, m in enumerate(matched_flags)])


# Fixed column of the match-marker char in a _format_tracks row: 2 leading
# spaces + 2-digit index + ". set " (6 chars) + the 6-wide `set` field + 1
# space = 17. Verified directly against _format_tracks's own output, not
# assumed -- a substring check ("?" in line) would also be satisfied by a
# "?" elsewhere on the line (duration) or a "-" inside a filename, title, or
# the literal title_source "sibling-format", so only a fixed-offset check is
# load-bearing.
_MARK_COL = 17


def test_format_tracks_flags_an_unmatched_track():
    from llama.cli import _format_tracks

    lines = _format_tracks(_show_with([True, False]))
    assert lines[1][_MARK_COL] == " ", "a matched track carries no marker"
    assert lines[2][_MARK_COL] == "?", "an unmatched track is marked"
    assert lines[1].count("?") == 0
    assert any("? = no setlist match" in ln for ln in lines), "legend must appear"


def test_format_tracks_renders_unknown_distinctly():
    from llama.cli import _format_tracks

    lines = _format_tracks(_show_with([None, None]))
    assert lines[1][_MARK_COL] == "-", "unknown must not read as unmatched"
    assert lines[1].count("?") == 0 and lines[2].count("?") == 0
    # whole-output check, not just the track rows: unknown must not trip the
    # legend either -- narrowing this to the row-only checks above is what
    # let "matched is False" -> "matched is not True" slip through unpinned.
    assert "?" not in "".join(lines)


def test_format_tracks_omits_the_legend_when_everything_matched():
    from llama.cli import _format_tracks

    lines = _format_tracks(_show_with([True, True]))
    assert not any("no setlist match" in ln for ln in lines)


def test_format_tracks_flags_unmeasured_tracks_with_a_legend():
    """Every show gathered before this branch has no `matched` key in
    show.json, so it deserializes to Track.matched=None for every track --
    the WHOLE existing library renders an all-"-" column with nothing
    explaining it unless this legend fires. Checked as exact-line
    membership (not `in` on joined text, not `any(text in ln ...)`) so a
    mutation that drops this line, or one that emits it as a substring of
    something else, cannot slip through."""
    from llama.cli import _format_tracks

    lines = _format_tracks(_show_with([None, None]))
    assert "  - = not measured" in lines


def test_format_tracks_omits_the_unmeasured_legend_when_everything_measured():
    from llama.cli import _format_tracks

    lines = _format_tracks(_show_with([True, False]))
    assert "  - = not measured" not in lines


def test_format_tracks_can_show_both_legends_at_once():
    """An unmatched track and an unmeasured track can coexist on one show
    (e.g. after a partial redo); both legends must appear together, each
    independently -- proves the two `if`s aren't wired as mutually
    exclusive (e.g. via elif)."""
    from llama.cli import _format_tracks

    lines = _format_tracks(_show_with([False, None]))
    assert "  ? = no setlist match" in lines
    assert "  - = not measured" in lines


def test_format_tracks_distinguishes_matched_unmatched_and_unknown():
    """Reviewer-caught gap: two mutations that collapse only TWO of the three
    `matched` states each still passed all other format_tracks tests --
    _MARK[True] = " " -> "-" (matched reads identically to unmeasured), and
    _MARK[True] = " " -> "" (mixed rows misalign, but that alone escaped a
    fixed-column check too: dropping the marker to a zero-width string still
    happened to land a space at column 17 on the shortened row, by
    coincidence of the surrounding padding -- only a whole-row alignment
    check catches it). A single show carrying all three states, checked both
    at the fixed marker column AND for equal row length / a shared duration
    offset, closes both mutations: it requires three DISTINCT one-character
    markers rendered at a consistent width, not merely "a marker is present
    somewhere"."""
    from llama.cli import _format_tracks

    lines = _format_tracks(_show_with([True, False, None]))
    rows = lines[1:4]
    marks = [ln[_MARK_COL] for ln in rows]
    assert marks == [" ", "?", "-"]
    assert len(set(marks)) == 3, "matched/unmatched/unknown must render as three distinct marks"
    assert len({len(ln) for ln in rows}) == 1, "every row must be the same width"
    assert len({ln.index(" 5:00") for ln in rows}) == 1, "the duration column must line up"


def _cfg(tmp_path):
    """A config.toml pointing `root` at tmp_path, the pattern test_fix.py
    uses -- `llama fix` resolves shows by slug against `config.root`, so
    without this a show staged under an arbitrary tmp_path is never found
    (verified directly: an earlier draft of these tests passed `str(sws.dir)`
    to a bare `runner.invoke` with no `--config` and every one failed with
    CatalogError("no show matches ..."), since the default root is `~/.llama`,
    not tmp_path)."""
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    return tmp_path / "config.toml"


def _staged_ymsb_show(tmp_path, monkeypatch, slug="ymsb2005-12-31"):
    """A cataloged show (provenance.json + a real gathered show.json, laid
    out at `root/shows/<slug>/` the way `llama fix` expects to find it)
    holding the real 24-track untagged ymsb tape, all titles unresolved.

    provenance.json is written explicitly (mirroring test_catalog.py's
    `build()`) because `--suggest-titles` reads `entry.provenance.candidate`
    to rebuild the canonical setlist, and `run_gather` alone -- as used
    directly in test_stage_gather.py -- never writes it; that happens one
    layer up, in pipeline.process_show, before gather ever runs.

    Also monkeypatches `cli.IAClient` to hand back a `StubIA` over the same
    metadata: `llama fix` builds its own `IAClient` from scratch inside
    `_setup()` (see `cli.py`), so a plain `StubIA` passed only to the
    `run_gather` call above is invisible to the CLI invocation below --
    without this the CLI's `ia.metadata(...)` call hits a REAL IAClient
    against `config.root/cache`, which is empty here (verified directly: an
    earlier draft crashed/produced whatever happened to be on-disk instead
    of this fixture's metadata -- test_redo_cmd.py's `FakeIA` pattern, used
    the same way here, is what fixes it)."""
    md = json.loads((FIXTURES / "ymsb2005_metadata.json").read_text())
    cand = _ymsb_candidate()
    sws = ShowWorkspace(tmp_path / "shows" / slug)
    write_artifact(sws.provenance, Provenance(
        performance_id=cand.performance_id, run="r1", dossier="great",
        candidate=cand, processed_at="2026-08-31T00:00:00+00:00"))
    show = run_gather(sws, StubIA(md), FakeProvider(), cand,
                      "ymsb2005-12-31.flac16.wav")
    assert all(t.title_source == "unresolved" for t in show.tracks)
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: StubIA(md))
    return sws


#: Tracks left `unresolved` by `_staged_anchored_ymsb_show`, and the canonical
#: item each one is COUNT-FORCED to by the tag-titled tracks bracketing it.
#: Measured against the real fixture, not asserted by construction -- see that
#: helper's docstring for why they cannot simply be chosen.
ANCHORED_GAPS = {5: "Steep Grade Sharp Curves",
                 14: "Jack London",
                 20: "Ewe With The Crooked Horn"}


def _staged_anchored_ymsb_show(tmp_path, monkeypatch, slug="ymsb2005-12-31",
                               gaps=tuple(ANCHORED_GAPS)):
    """The same real ymsb tape, but ANCHORED: every track except `gaps`
    carries a tag title lifted from the canonical setlist, so each remaining
    unresolved run is bracketed by tracks that independently place
    themselves in that setlist.

    This exists because `_staged_ymsb_show`'s tape -- wholly untagged -- is
    no longer proposable at all, and that is the point of the M3 guard, not
    an accident to work around: with no track carrying a title of its own,
    nothing pins the setlist to the tape and `propose_titles` declines (see
    `test_the_untagged_tape_is_no_longer_proposable`). Every test that needs
    a RENDERED proposal therefore needs an anchored tape.

    Track 1 carries a MERGED tag title (`Granny Woncha Smoke Some > Ride The
    Wild Turkey`) rather than a plain one, and that is load-bearing: this
    canonical parses to 25 items over 24 files, so exactly one merge has to
    absorb the extra item somewhere. Put it on track 1 and the DP agrees with
    the anchoring; leave it for the DP to place and it spends the merge later
    on the tape, slides its assignment past the gaps, and the proposal is
    declined by the contradiction half of the guard -- verified directly
    against this fixture, which is also why `ANCHORED_GAPS`' titles are
    measured rather than derived from the tagging rule.
    """
    md = json.loads((FIXTURES / "ymsb2005_metadata.json").read_text())
    cand = _ymsb_candidate()
    sws = ShowWorkspace(tmp_path / "shows" / slug)
    write_artifact(sws.provenance, Provenance(
        performance_id=cand.performance_id, run="r1", dossier="great",
        candidate=cand, processed_at="2026-08-31T00:00:00+00:00"))
    show = run_gather(sws, StubIA(md), FakeProvider(), cand,
                      "ymsb2005-12-31.flac16.wav")
    items = _ymsb_canonical_items(md, cand, show.artist)
    tagged = []
    for t in show.tracks:
        title = (f"{items[0].title} > {items[1].title}" if t.index == 1
                 else (items[t.index].title if t.index < len(items) else None))
        tagged.append(t if (t.index in gaps or title is None) else
                      t.model_copy(update={"title": title, "title_source": "tags"}))
    write_artifact(sws.show, show.model_copy(update={"tracks": tagged}))
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: StubIA(md))
    return sws


def _ymsb_canonical_items(md, cand, artist):
    """The canonical setlist `--suggest-titles` will itself rebuild for this
    fixture -- computed by calling the real `build_canonical` the same way
    the CLI path does (`provider=None`, `setlistfm=None` offline), rather
    than hardcoding a parsed setlist that could drift away from it."""
    from llama.junk import FORMAT_BY_AUDIO, filter_files
    from llama.stages.gather import build_canonical
    kept, _, _ = filter_files(md.get("files", []),
                              want_format=FORMAT_BY_AUDIO["flac"])
    return build_canonical(StubIA(md), cand, "ymsb2005-12-31.flac16.wav",
                           md.get("metadata", {}), kept, artist, [],
                           setlistfm=None, provider=None).setlist.items


def _staged_show_with_unusable_canonical(tmp_path, monkeypatch, slug="nocanon"):
    """Same tape, description replaced by prose that parses to nothing.

    `provider=None` here (not `FakeProvider()`): with the description
    unparseable, `rank_parses` finds no candidate and `build_canonical`
    falls through to its `extract_setlist` LLM rescue whenever a provider is
    given, which a bare `FakeProvider()` (no queued responses) blows up on --
    verified directly, not assumed. `llama fix --suggest-titles` itself
    always calls `build_canonical(..., provider=None)` (the whole point of
    the CLI path never firing an LLM call), so staging with `provider=None`
    reproduces exactly the canonical the CLI path will independently
    recompute, without an incidental LLM round-trip this test doesn't care
    about. Also monkeypatches `cli.IAClient` -- see `_staged_ymsb_show`."""
    md = json.loads((FIXTURES / "ymsb2005_metadata.json").read_text())
    md["metadata"]["description"] = "A great night. Recorded from the balcony."
    cand = _ymsb_candidate()
    sws = ShowWorkspace(tmp_path / "shows" / slug)
    write_artifact(sws.provenance, Provenance(
        performance_id=cand.performance_id, run="r1", dossier="great",
        candidate=cand, processed_at="2026-08-31T00:00:00+00:00"))
    run_gather(sws, StubIA(md), None, cand, "ymsb2005-12-31.flac16.wav")
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: StubIA(md))
    return sws


def test_suggest_titles_writes_every_row_into_overrides(tmp_path, monkeypatch):
    """One confirmation replaces one --set-title call per unresolved track --
    three here, in three separate runs, all in one go."""
    cfg = _cfg(tmp_path)
    sws = _staged_anchored_ymsb_show(tmp_path, monkeypatch)
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles", "--no-run")
    assert result.exit_code == 0, result.output
    ov = read_overrides(sws)
    assert ov.titles == ANCHORED_GAPS
    # M11 (review round 1): pin that adopting a proposal is a `did_meta`
    # edit, so the existing redo selector stages `gather` -- confirmed
    # (rather than re-derived) in the implementation that `parsed_titles`
    # already sat in the `did_meta` expression; this is the pin.
    assert "--from gather" in result.output


def test_suggest_titles_declines_when_show_json_is_stale_against_pending_exclude(tmp_path, monkeypatch):
    """C1 (final review, the merge blocker): staging `--exclude` with
    `--no-run` writes `overrides.json` without re-running `gather`, so
    `_propose_titles_for_show`'s freshly recomputed `kept` (`ia.metadata`
    filtered by the now-written `overrides.exclude`, 23 files) disagrees
    with `show.tracks` read from the untouched `show.json` (still the
    pre-exclusion 24). Before the C1 fix this silently built a proposal
    over the stale 24-track numbering while `overrides.titles` gets applied
    by 1-based POST-exclusion position when `gather` eventually runs --
    landing confirmed titles on the wrong tracks with no error and no flag
    (reproduced end to end in the final review: three titles landed on
    three wrong files). The guard must decline hard, not warn, and must
    leave `overrides.titles` untouched -- this command's own `--exclude`
    refusal message ("Run the exclusion first, then `--suggest-titles` as a
    separate invocation") routes an operator straight into this exact
    sequence, so the two-invocation workflow it recommends must be safe."""
    cfg = _cfg(tmp_path)
    sws = _staged_anchored_ymsb_show(tmp_path, monkeypatch)
    victim = read_model(sws.show, Show).tracks[0].filename
    stage_result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--exclude", victim, "--no-run")
    assert stage_result.exit_code == 0, stage_result.output
    assert read_overrides(sws).exclude == [victim]
    # confirm show.json really is stale -- NOT re-derived by --no-run
    assert len(read_model(sws.show, Show).tracks) == 24

    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)   # would say yes
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles", "--no-run")
    assert result.exit_code == 0, result.output
    assert "show.json is stale relative to overrides.json" in result.output
    assert "23 files kept" in result.output
    assert "24 tracks on disk" in result.output
    assert "redo ymsb2005-12-31 --from gather" in result.output
    assert read_overrides(sws).titles == {}
    # ... and no table was printed at all.
    assert "proposal (" not in result.output


def test_the_untagged_tape_is_no_longer_proposable(tmp_path, monkeypatch):
    """The M3 gate's headline regression pin, over the real 24-track untagged
    ymsb tape. This show USED to render 24 rows and adopt 22 titles, 13 of
    them wrong via a uniform off-by-one, with nothing in the table saying so.
    Not a single track carries a title of its own, so nothing anchors the
    setlist to the tape and there is no such thing as a count-forced run --
    it must decline before rendering, and say what it could not account
    for."""
    cfg = _cfg(tmp_path)
    sws = _staged_ymsb_show(tmp_path, monkeypatch)
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)   # would say yes
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles", "--no-run")
    assert result.exit_code == 0, result.output
    assert read_overrides(sws).titles == {}
    assert "cannot be pinned to tracks 1-24" in result.output
    # Requirement: the reason has to be actionable, i.e. tell an operator
    # whether to go looking for a better setlist source. Both counts and the
    # discrepancy between them, not just a verdict.
    assert "25 canonical items vs 24 song-like tracks" in result.output
    assert "1 song" in result.output
    # ... and no table was printed at all.
    assert "proposal (" not in result.output


def test_resolve_prompt_with_titles_is_derived_from_resolve_prompt():
    """N2 (task-8 review round 2, task-8n): `RESOLVE_PROMPT_WITH_TITLES`'s
    comment claims `RESOLVE_PROMPT` is the single source of truth for the
    common tail, but it used to be a hand-copied literal that could drift
    silently -- a sentinel edit to `RESOLVE_PROMPT` passed every test because
    nothing re-derived the `WITH_TITLES` variant from it. This pins the
    derivation directly: splitting `RESOLVE_PROMPT` on its `[s]kip` option
    and checking both halves survive verbatim into `RESOLVE_PROMPT_WITH_TITLES`
    is exactly what a sentinel edit to either half would break under the old
    hand-copied literal and cannot break under the derived one."""
    before, sep, after = cli.RESOLVE_PROMPT.partition("[s]kip")
    assert sep, "RESOLVE_PROMPT must still contain the [s]kip option"
    assert cli.RESOLVE_PROMPT_WITH_TITLES.startswith(before)
    assert cli.RESOLVE_PROMPT_WITH_TITLES.endswith(sep + after)
    assert "[t] suggest titles" in cli.RESOLVE_PROMPT_WITH_TITLES


def test_declining_the_proposal_writes_nothing(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    sws = _staged_ymsb_show(tmp_path, monkeypatch)
    monkeypatch.setattr("typer.confirm", lambda *a, **k: False)
    # M8 (review round 1): --no-run is required, not cosmetic. Without it,
    # this test is fast today only because the decline exits before ever
    # reaching a real redo -- if a future regression removes that early
    # exit, the test stops failing in milliseconds and instead HANGS inside
    # a real `_redo_show` (network/pipeline calls this suite never stubs).
    # A gate regression must fail fast, not time out.
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles", "--no-run")
    assert result.exit_code == 0, result.output
    assert read_overrides(sws).titles == {}


def test_an_infeasible_show_declines_without_writing(tmp_path, monkeypatch):
    """Measured, not the brief's literal string: with the description parsing
    to zero setlist items, `propose_titles` takes its `not items` branch and
    returns reason="no usable canonical setlist" (correspondence.py), not
    "no consistent correspondence - parse quality too low" (that second
    string is DP infeasibility on a NON-empty canonical -- a different
    branch, not reachable from an empty parse). Verified directly against
    the real correspondence.propose_titles/build_canonical call the CLI path
    makes, not tuned to whatever the code happened to emit."""
    cfg = _cfg(tmp_path)
    sws = _staged_show_with_unusable_canonical(tmp_path, monkeypatch)
    result = cli_invoke(cfg, "fix", "nocanon", "--suggest-titles")
    assert "no usable canonical setlist" in result.output
    assert read_overrides(sws).titles == {}


# --- review round 1 fixes -----------------------------------------------

def test_infeasible_proposal_falls_through_to_a_co_specified_edit(tmp_path, monkeypatch):
    """I1 (round 1): an infeasible proposal used to always exit 0
    immediately, silently discarding any OTHER edit flag on the same
    invocation. It must instead warn and fall through."""
    cfg = _cfg(tmp_path)
    sws = _staged_show_with_unusable_canonical(tmp_path, monkeypatch)
    result = cli_invoke(cfg, "fix", "nocanon", "--suggest-titles",
                        "--set-venue", "The Fillmore", "--no-run")
    assert result.exit_code == 0, result.output
    assert "no usable canonical setlist" in result.output
    assert "continuing with the other edit flag(s) given" in result.output
    assert read_overrides(sws).venue == "The Fillmore"


def test_nothing_to_adopt_falls_through_to_a_co_specified_edit(tmp_path, monkeypatch):
    """I1 (round 1): same guarantee when the proposal is feasible but every
    track already has a title (picks is empty)."""
    cfg = _cfg(tmp_path)
    sws = _staged_ymsb_show(tmp_path, monkeypatch)
    show = read_model(sws.show, Show)
    show = show.model_copy(update={"tracks": [
        t.model_copy(update={"title_source": "tags", "title": f"Song {t.index}"})
        for t in show.tracks]})
    write_artifact(sws.show, show)
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles",
                        "--set-venue", "The Fillmore", "--no-run")
    assert result.exit_code == 0, result.output
    assert "nothing to adopt: every track already has a title" in result.output
    assert "continuing with the other edit flag(s) given" in result.output
    assert read_overrides(sws).venue == "The Fillmore"


def test_suggest_titles_declined_falls_through_to_a_co_specified_overrule(tmp_path, monkeypatch):
    """I1 (round 1): the reviewer's worst case -- `--suggest-titles
    --overrule` on a declined proposal must NOT read as exit 0 = "hold
    cleared" when it was not. `_staged_ymsb_show`'s show is genuinely held
    (a wholly untagged tape flags "unresolved track titles"), so this
    exercises the real combination, not a synthetic stand-in."""
    cfg = _cfg(tmp_path)
    sws = _staged_anchored_ymsb_show(tmp_path, monkeypatch)
    assert read_model(sws.show, Show).needs_review is True   # confirm it's actually held
    monkeypatch.setattr("typer.confirm", lambda *a, **k: False)
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles", "--overrule", "--no-run")
    assert result.exit_code == 0, result.output
    assert "declined; nothing written" in result.output
    assert "continuing with the other edit flag(s) given" in result.output
    assert read_overrides(sws).titles == {}
    assert read_model(sws.show, Show).needs_review is False   # --overrule DID apply


def test_suggest_titles_refuses_combination_with_exclude_flags(tmp_path, monkeypatch):
    """I2 (round 1): the proposal is numbered over the CURRENT track list;
    a same-invocation --exclude/--unexclude renumbers tracks before that
    numbering would apply to the redo, so a picked index could silently
    land on the wrong track. Refuse the combination outright rather than
    guess at the post-exclusion numbering."""
    cfg = _cfg(tmp_path)
    for flag, value in [("--exclude", "1"), ("--unexclude", "1")]:
        sws = _staged_ymsb_show(tmp_path, monkeypatch, slug=f"ymsb-{flag.strip('-')}")
        result = cli_invoke(cfg, "fix", sws.dir.name, "--suggest-titles", flag, value)
        assert result.exit_code != 0, (flag, result.output)
        assert "cannot be combined with --exclude/--unexclude" in result.output, (flag, result.output)
        assert read_overrides(sws).titles == {}
        assert read_overrides(sws).exclude == []


def test_explicit_set_title_wins_over_the_proposal(tmp_path, monkeypatch):
    """M10 (round 1): an explicit --set-title on the same invocation must
    beat a generated proposal for the same track -- the same human-
    authority principle the confirmation gate itself protects."""
    cfg = _cfg(tmp_path)
    sws = _staged_anchored_ymsb_show(tmp_path, monkeypatch)
    victim = sorted(ANCHORED_GAPS)[0]
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles",
                        "--set-title", f"{victim}=Operator Chosen Title", "--no-run")
    assert result.exit_code == 0, result.output
    ov = read_overrides(sws)
    assert ov.titles[victim] == "Operator Chosen Title"
    # the rest of the proposal still lands, unchanged
    assert ov.titles == {**ANCHORED_GAPS, victim: "Operator Chosen Title"}


def test_never_clobbers_a_track_that_already_has_a_title(tmp_path, monkeypatch):
    """M4 (round 1): `picks` only includes rows still
    `title_source == "unresolved"` on the live show. Reviewer-mutation-
    verified as unpinned before this test existed: deleting that guard
    clause from `_propose_titles_for_show` left the entire pre-round-1
    `test_cli.py` suite green."""
    cfg = _cfg(tmp_path)
    sws = _staged_anchored_ymsb_show(tmp_path, monkeypatch)
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles", "--no-run")
    assert result.exit_code == 0, result.output
    # The proposal covers all 24 rows -- every anchored tape's table does,
    # since the DP is asked about the whole tape -- but the 21 rows that
    # already carry a tag title are not adopted, only the 3 unresolved ones.
    assert "Midnight Blues" in result.output   # a proposed row that is NOT adopted
    assert read_overrides(sws).titles == ANCHORED_GAPS


def test_missing_provenance_declines_cleanly(tmp_path, monkeypatch):
    """M7 (round 1): matches the two nearest analogues (`_redo_show` and
    `triage`'s own guard) instead of an unguarded AttributeError on
    `entry.provenance.candidate`."""
    cfg = _cfg(tmp_path)
    sws = _staged_ymsb_show(tmp_path, monkeypatch)
    sws.provenance.unlink()
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles")
    assert result.exit_code == 1
    assert "no provenance.json" in result.output
    assert "reprocess it via its run first" in result.output
    assert read_overrides(sws).titles == {}


# --- task-8 review round 1: A1/A2/A3 ------------------------------------

def test_suggest_titles_threads_setlistfm_client_and_jerrybase_events(tmp_path, monkeypatch):
    """A2 (task-8 review): pin the ARGUMENTS `build_canonical` receives, not
    the behavior behind them -- every test in this suite runs with
    SETLISTFM_API_KEY unset (conftest's autouse `_no_ambient_setlistfm_key`
    fixture), so a sentinel object standing in for `make_client(config)`'s
    return is the only way to catch a future regression that drops the
    setlistfm/events threading and silently reverts the proposal path back
    to an LMA-only canonical -- invisible offline, since every test already
    runs with `setlistfm=None`. Deliberately does NOT build a real
    setlist.fm stub/fixture: that would be testing behavior no other test
    in this suite exercises, a larger scope expansion than this phase
    should absorb."""
    cfg = _cfg(tmp_path)
    _staged_ymsb_show(tmp_path, monkeypatch)

    class _SentinelSetlistfmClient:
        """A bare `object()` isn't enough here: `build_canonical` calls
        `.setlist(...)` on whatever it's handed whenever it isn't None, so
        the sentinel needs that one method (returning falsy, so it's a
        no-op on the rest of the build) while still being an identity-
        distinct object this test can assert `is` against."""

        def setlist(self, *args, **kwargs):
            return None

    sentinel_client = _SentinelSetlistfmClient()
    # Empty rather than populated with fake Event objects: `events` reaches
    # real jerrybase-consuming code inside `build_canonical`
    # (`_show_metadata_norms`) that expects real `Event` attributes (venue,
    # etc.) whenever the list is non-empty -- an empty list needs none of
    # that and is exactly what a non-family artist's real `jerrybase.lookup`
    # already returns, so this doubles as the identity-check payload without
    # inventing a fake `Event`.
    sentinel_events = []
    monkeypatch.setattr("llama.setlistfm.make_client", lambda config: sentinel_client)
    monkeypatch.setattr("llama.jerrybase.lookup", lambda artist, date: sentinel_events)

    from llama.stages import gather as gather_mod
    real_build_canonical = gather_mod.build_canonical
    captured = {}

    def spy(ia, cand, identifier, meta, kept, artist, events, *, setlistfm=None, provider=None):
        captured["setlistfm"] = setlistfm
        captured["events"] = events
        captured["provider"] = provider
        return real_build_canonical(ia, cand, identifier, meta, kept, artist, events,
                                    setlistfm=setlistfm, provider=provider)

    monkeypatch.setattr(gather_mod, "build_canonical", spy)
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)

    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles", "--no-run")
    assert result.exit_code == 0, result.output
    assert captured["setlistfm"] is sentinel_client
    assert captured["events"] is sentinel_events
    # M2 (task-8 review round 1): pin the OTHER half of the "never fires an
    # LLM call" guarantee at the same argument level as setlistfm/events --
    # `provider=None` is always passed, never threaded through from the
    # real LLM provider the pipeline would otherwise use.
    assert captured["provider"] is None


def test_suggest_titles_drops_excluded_files_from_kept(tmp_path, monkeypatch):
    """A1 (task-8 review round 1, I1): the `kept` handed to `build_canonical`
    must match what `run_gather` computes -- excluded files dropped BEFORE
    the canonical build -- or `rank_parses`' `target_count` differs between
    the proposal and the redo the confirmation triggers, and since
    `overrides.titles` is applied by 1-based position (gather.py), a
    different winning parse means confirmed titles could land on the wrong
    tracks. Pins the ARGUMENT `build_canonical` receives (the same style as
    A2), not a full re-derivation of `rank_parses`' behavior.

    C1 (final review): this test used to stage `overrides.exclude` directly
    and never re-derive `show.json` -- exactly the stale state C1's guard
    now declines on (kept 23 files, `show.tracks` still 24), so after the
    C1 fix this test silently stopped reaching `build_canonical` at all and
    started passing for the wrong reason (a KeyError on `captured["kept"]`
    caught it -- see the C1 fix report). Re-running `run_gather(...,
    force=True)` after writing the exclusion mirrors what a real `llama fix
    --exclude` redo does, keeping `show.tracks` in sync with `kept` so this
    test again exercises what its docstring claims rather than the C1
    staleness guard."""
    cfg = _cfg(tmp_path)
    sws = _staged_ymsb_show(tmp_path, monkeypatch)
    md = json.loads((FIXTURES / "ymsb2005_metadata.json").read_text())
    cand = _ymsb_candidate()
    victim = read_model(sws.show, Show).tracks[0].filename
    ov = read_overrides(sws)
    write_artifact(sws.overrides, ov.model_copy(update={"exclude": [victim]}))
    run_gather(sws, StubIA(md), FakeProvider(), cand,
              "ymsb2005-12-31.flac16.wav", force=True)

    from llama.stages import gather as gather_mod
    real_build_canonical = gather_mod.build_canonical
    captured = {}

    def spy(ia, cand, identifier, meta, kept, artist, events, *, setlistfm=None, provider=None):
        captured["kept"] = list(kept)
        captured["provider"] = provider
        return real_build_canonical(ia, cand, identifier, meta, kept, artist, events,
                                    setlistfm=setlistfm, provider=provider)

    monkeypatch.setattr(gather_mod, "build_canonical", spy)
    monkeypatch.setattr("typer.confirm", lambda *a, **k: False)
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles", "--no-run")
    assert result.exit_code == 0, result.output
    names = [f["name"] for f in captured["kept"]]
    assert victim not in names
    assert len(names) == 23
    assert captured["provider"] is None


def test_format_proposal_row_trichotomy_is_distinct():
    """A3 (task-8 review): pin the margin_sec/forced/filler trichotomy
    (models.ProposalRow's docstring) directly against synthetic rows --
    the ymsb fixture this module's other tests share never produces a
    forced row (its setlist carries no segues, so `build_canonical` always
    aligns one track per canonical item with no ambiguous cost tie), so
    collapsing the `forced` label into the filler dash previously left
    `test_cli.py` green: the same forced/filler collapse a Task 5
    correspondence.py test exists to prevent, silently reintroduced one
    layer up at render time. Verified directly (see task-8-report.md): a
    manual mutation collapsing the `forced` branch to `margin = "     -"`
    fails this test."""
    from llama.models import ProposalRow

    matched = ProposalRow(index=1, duration_sec=300.0, item_span=(0, 1),
                          title="Song A", evidence="sibling-duration", margin_sec=12.5)
    forced = ProposalRow(index=2, duration_sec=180.0, item_span=(1, 2),
                         title="Song B", evidence="duration-model", forced=True)
    filler = ProposalRow(index=3, duration_sec=None, item_span=None,
                         title="", evidence="filler")

    rendered = {name: cli._format_proposal_row(r)
               for name, r in [("matched", matched), ("forced", forced), ("filler", filler)]}
    assert len(set(rendered.values())) == 3, rendered
    assert "forced" in rendered["forced"]
    assert "forced" not in rendered["matched"]
    assert "forced" not in rendered["filler"]
    assert "12" in rendered["matched"]   # the margin_sec value renders as a number
    assert "(unresolved - hand-edit)" in rendered["filler"]


# ===========================================================================
# Task 6: the sibling-transfer arm of `--suggest-titles` / triage `[t]`.
#
# Donor fixtures are synthesized directly (archive.org-shaped file dicts,
# `MultiIA` serving per-identifier metadata) rather than captured, since no
# real fixture exercises a tagged sibling of an otherwise-untagged tape.
# Every alignment below was verified against the real `siblings.propose_rows`
# / `rate_alignment` before being encoded as an assertion (not just asserted
# and hoped): see task-6-report.md for the scratch runs.
# ===========================================================================

def _ymsb_sibling_donor(md, ident="ymsb2005-12-31.aud.sibling"):
    """A tagged donor recording for the real untagged ymsb2005 tape: one
    real (placeholder) title per kept file, 1:1 by duration, except track 9
    (12:30) -- split into two donor songs summing to the same duration, the
    merged "A > B" row the untagged-fixture acceptance test pins. What
    matters to the DP is duration correspondence, not song authenticity, so
    titles are plain `Song NN` placeholders."""
    audio = sorted((f for f in md["files"] if f.get("format") == "VBR MP3"),
                   key=lambda f: f["name"])
    donor_files = []
    for i, f in enumerate(audio):
        if i == 8:                              # track 9: 12:30 -> two donor songs
            donor_files.append({"name": f"{ident}d1t{i + 1:02d}a.mp3", "format": "VBR MP3",
                                "source": "original", "length": "400",
                                "title": "Song 09a"})
            donor_files.append({"name": f"{ident}d1t{i + 1:02d}b.mp3", "format": "VBR MP3",
                                "source": "original", "length": "350",
                                "title": "Song 09b"})
        else:
            dur = length_seconds(f["length"])
            donor_files.append({"name": f"{ident}d1t{i + 1:02d}.mp3", "format": "VBR MP3",
                                "source": "original", "length": str(dur),
                                "title": f"Song {i + 1:02d}"})
    return ident, {"metadata": {"identifier": ident, "description": ""},
                   "files": donor_files}


def _bad_ymsb_donor(md, ident="ymsb2005-12-31.aud.bad-donor"):
    """A donor with the SAME durations as the real ymsb tape but titles that
    agree with nothing -- for the below-FLOOR-donor tests. Same durations
    means the DP still pairs 1:1 with high confidence; the disagreement is
    entirely in the titles, which is what `rate_alignment` actually rates."""
    sib = {"metadata": {"identifier": ident, "description": ""},
           "files": [dict(f) for f in md["files"]]}
    audio = sorted((f for f in sib["files"] if f.get("format") == "VBR MP3"),
                   key=lambda f: f["name"])
    for i, f in enumerate(audio):
        f["title"] = f"Wrong Song {i + 1}"
    return ident, sib


def test_untagged_fixture_with_tagged_donor_renders_sibling_proposal(tmp_path, monkeypatch):
    """The phase's trigger case, end to end: ymsb2005's real untagged tape,
    now paired with a tagged sibling. Zero of the target's own 24 tracks
    carry a tag, so `rate_alignment` finds zero anchors and routes to the
    "no-anchors" band -- one of the three bands the sibling arm renders from
    (invariant: rows render despite zero anchors, the opposite of what
    `cplus_filter` would do here -- see the named-mutation tests below).
    Track 9 pins the merge: the donor's single 12:30 file was split into two
    donor songs summing to the same duration, so only a real DP -- never a
    positional/count-based transfer -- can produce the "A > B" join."""
    cfg = _cfg(tmp_path)
    md = json.loads((FIXTURES / "ymsb2005_metadata.json").read_text())
    donor_ident, donor_md = _ymsb_sibling_donor(md)
    cand = _ymsb_candidate()
    cand.recordings.append(RecordingSummary(identifier=donor_ident))
    sws = ShowWorkspace(tmp_path / "shows" / "ymsb2005-12-31")
    write_artifact(sws.provenance, Provenance(
        performance_id=cand.performance_id, run="r1", dossier="great",
        candidate=cand, processed_at="2026-08-31T00:00:00+00:00"))
    ia_map = {"ymsb2005-12-31.flac16.wav": md, donor_ident: donor_md}
    run_gather(sws, MultiIA(ia_map), FakeProvider(), cand, "ymsb2005-12-31.flac16.wav")
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: MultiIA(ia_map))
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles", "--no-run")
    assert result.exit_code == 0, result.output
    assert "sibling-align" in result.output
    assert "no-anchors" in result.output
    # residual column present: every row's residual is 0s (exact duration match)
    assert re.search(r"\b0s\b", result.output)
    ov = read_overrides(sws)
    # >= 3 exact titles, including the merged "A > B" row.
    assert ov.titles[1] == "Song 01"
    assert ov.titles[9] == "Song 09a > Song 09b"
    assert ov.titles[24] == "Song 24"


def test_operator_band_sibling_titles_diverge_from_the_canonical_dp(tmp_path, monkeypatch):
    """The named-mutation-B fixture. `_staged_anchored_ymsb_show`'s canonical
    DP is FEASIBLE (its 3 interior gaps are count-forced between real
    anchors -- `test_below_floor_donor_with_usable_canonical_falls_through_to_dp`
    already pins its exact output: `ANCHORED_GAPS`). This test's donor
    agrees with 16 of 21 real anchors (0.762, FLOOR <= x < AUTO -> operator
    band -- NOT auto, so gather itself never auto-fills these tracks) but
    tags the 3 gap positions with placeholder text instead of the real
    song names, so the sibling arm's own proposal for those 3 tracks is
    GUARANTEED to differ from the canonical DP's ("Steep Grade Sharp
    Curves" etc.) -- unlike the untagged-fixture fixture above, whose
    canonical DP is structurally infeasible either way (a wholly-unresolved
    tape is one run spanning the whole tape, and `structure.gap_span` has no
    trailing-edge branch, so `_unaccounted` always declines it regardless of
    which arm runs first -- verified directly, see task-6-report.md) and so
    cannot demonstrate this mutation on title content at all."""
    cfg = _cfg(tmp_path)
    sws = _staged_anchored_ymsb_show(tmp_path, monkeypatch)
    md = json.loads((FIXTURES / "ymsb2005_metadata.json").read_text())
    audio = sorted((f for f in md["files"] if f.get("format") == "VBR MP3"),
                   key=lambda f: f["name"])
    show = read_model(sws.show, Show)
    donor_ident = "ymsb2005-12-31.aud.divergent"
    wrong_positions = {2, 6, 10, 15, 21}   # 0-based: 5 of 21 anchors disagree
    donor_files = []
    for i, f in enumerate(audio):
        pos1 = i + 1
        if pos1 in ANCHORED_GAPS:
            title = f"Placeholder {pos1}"
        elif i in wrong_positions:
            title = "Some Wrong Title"
        else:
            title = show.tracks[i].title
        donor_files.append({"name": f"{donor_ident}d1t{i + 1:02d}.mp3", "format": "VBR MP3",
                            "source": "original", "length": f["length"], "title": title})
    donor_md = {"metadata": {"identifier": donor_ident, "description": ""},
               "files": donor_files}
    cand = _ymsb_candidate()
    cand.recordings.append(RecordingSummary(identifier=donor_ident))
    write_artifact(sws.provenance, Provenance(
        performance_id=cand.performance_id, run="r1", dossier="great",
        candidate=cand, processed_at="2026-08-31T00:00:00+00:00"))
    ia_map = {"ymsb2005-12-31.flac16.wav": md, donor_ident: donor_md}
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: MultiIA(ia_map))
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles", "--no-run")
    assert result.exit_code == 0, result.output
    assert "band operator" in result.output
    ov = read_overrides(sws)
    assert ov.titles == {5: "Placeholder 5", 14: "Placeholder 14", 20: "Placeholder 20"}
    # the canonical DP's own (real) titles for the same 3 tracks, pinned by
    # test_below_floor_donor_with_usable_canonical_falls_through_to_dp --
    # content-different from what was actually written above.
    assert ANCHORED_GAPS == {5: "Steep Grade Sharp Curves", 14: "Jack London",
                             20: "Ewe With The Crooked Horn"}
    assert set(ov.titles.values()).isdisjoint(ANCHORED_GAPS.values())


def test_delmccoury_shaped_operator_band_confirms_only_unresolved_rows(tmp_path, monkeypatch):
    """13 anchors, 4 disagreeing (9/13 = 69% agreement, FLOOR <= x < AUTO):
    the operator band. Tracks 14-15 carry no tag of their own -- the sibling
    arm proposes real titles for them too, and confirmation must write ONLY
    those two into overrides.titles, never the 13 anchor tracks (even the
    4 disagreeing ones, whose OWN rows also carry an "adopt" verdict from
    the DP -- the `title_source == "unresolved"` gate is what excludes them,
    exactly as it does for the canonical DP's own picks).

    The description is DELIBERATELY split into two variants of the same
    dict: an empty one fed to the initial `run_gather` (so gather's own
    whole-tape "setlist" rung cannot positionally resolve tracks 14-15 before
    this test ever gets to exercise the sibling arm -- verified directly: a
    populated description at gather time resolves them via "setlist"
    instead, leaving nothing "unresolved" for `--suggest-titles` to act on),
    and the real chained description for the LATER `--suggest-titles`
    invocation, which needs a real canonical to render the three-way
    disagreement's "setlist:" column."""
    cfg = _cfg(tmp_path)
    nato = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf",
           "Hotel", "India", "Juliett", "Kilo", "Xray", "Mike"]
    extra = ["Beaumont Rag", "Sally Goodin"]
    donor_titles = nato + extra
    durs = [200.0 + 30.0 * i for i in range(15)]
    wrong = {3: "Dire Wolf", 7: "Casey Jones", 9: "Ripple", 11: "Loser"}
    ident = "delmccoury2001-07-01.sbd.example.flac16"
    donor_ident = "delmccoury2001-07-01.aud.sibling"

    def files(prefix, titles):
        out = []
        for i, dur in enumerate(durs):
            f = {"name": f"{prefix}d1t{i + 1:02d}.mp3", "format": "VBR MP3",
                "source": "original", "length": str(dur)}
            if titles[i] is not None:
                f["title"] = titles[i]
            out.append(f)
        return out

    target_titles = [wrong.get(i, nato[i]) if i < 13 else None for i in range(15)]
    target_files = files(ident, target_titles)
    description = " &gt; ".join(donor_titles)
    meta_common = {"identifier": ident, "venue": "Wolf Trap Filene Center",
                   "coverage": "Vienna, VA"}
    md_gather = {"metadata": dict(meta_common, description=""),
                "files": [dict(f) for f in target_files]}
    md_cli = {"metadata": dict(meta_common, description=description),
             "files": [dict(f) for f in target_files]}
    donor_md = {"metadata": {"identifier": donor_ident, "description": ""},
               "files": files(donor_ident, donor_titles)}

    cand = Candidate(performance_id="DelMcCouryBand/2001-07-01", collection="DelMcCouryBand",
                     date="2001-07-01", venue="Wolf Trap Filene Center", city="Vienna, VA",
                     recordings=[RecordingSummary(identifier=ident),
                                RecordingSummary(identifier=donor_ident)])
    sws = ShowWorkspace(tmp_path / "shows" / "delmccoury2001-07-01")
    write_artifact(sws.provenance, Provenance(
        performance_id=cand.performance_id, run="r1", dossier="great",
        candidate=cand, processed_at="2026-08-31T00:00:00+00:00"))
    run_gather(sws, MultiIA({ident: md_gather, donor_ident: donor_md}),
              FakeProvider(), cand, ident)
    monkeypatch.setattr(
        cli, "IAClient",
        lambda *a, **k: MultiIA({ident: md_cli, donor_ident: donor_md}))
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)

    result = cli_invoke(cfg, "fix", "delmccoury2001-07-01", "--suggest-titles", "--no-run")
    assert result.exit_code == 0, result.output
    assert "band operator" in result.output
    # the three-way disagreement block lists all 4 disagreeing tracks, each
    # with tape / sibling / setlist all present.
    for track, tape_title, sibling_title in (
            (4, "Dire Wolf", "Delta"), (8, "Casey Jones", "Hotel"),
            (10, "Ripple", "Juliett"), (12, "Loser", "Xray")):
        line = next(l for l in result.output.splitlines() if l.strip().startswith(f"t{track} "))
        assert f"tape: {tape_title!r}" in line
        assert f"sibling: {sibling_title!r}" in line
        assert f"setlist: {sibling_title!r}" in line   # canonical agrees with the sibling here

    ov = read_overrides(sws)
    assert ov.titles == {14: "Beaumont Rag", 15: "Sally Goodin"}


def _ymsb_canonical_items(md, cand, artist):
    """The canonical setlist `--suggest-titles` will itself rebuild for this
    fixture -- computed by calling the real `build_canonical` the same way
    the CLI path does, rather than hardcoding a parsed setlist that could
    drift away from it. Copied from the pattern `_staged_anchored_ymsb_show`
    already uses (below), since these below-FLOOR tests need the same real
    anchor titles without going through that helper's own donor-less
    staging."""
    from llama.junk import FORMAT_BY_AUDIO, filter_files
    from llama.stages.gather import build_canonical
    kept, _, _ = filter_files(md.get("files", []), want_format=FORMAT_BY_AUDIO["flac"])
    return build_canonical(StubIA(md), cand, "ymsb2005-12-31.flac16.wav",
                           md.get("metadata", {}), kept, artist, [],
                           setlistfm=None, provider=None).setlist.items


def test_below_floor_donor_with_no_usable_canonical_declines_unchanged(tmp_path, monkeypatch):
    """A donor is present and has real anchors to disagree with (21 of 24
    tracks tag-titled, all disagreeing -> agreement 0.0 < FLOOR -> declined
    band), but the canonical setlist is unparseable. The sibling arm must
    decline (band != operator/auto/no-anchors) and fall through; the
    existing "no usable canonical setlist" decline path -- unchanged --
    is what must still fire, not a crash and not a different message."""
    cfg = _cfg(tmp_path)
    md = json.loads((FIXTURES / "ymsb2005_metadata.json").read_text())
    cand = _ymsb_candidate()
    sws = ShowWorkspace(tmp_path / "shows" / "nocanon-anchored")
    write_artifact(sws.provenance, Provenance(
        performance_id=cand.performance_id, run="r1", dossier="great",
        candidate=cand, processed_at="2026-08-31T00:00:00+00:00"))
    show = run_gather(sws, StubIA(md), FakeProvider(), cand, "ymsb2005-12-31.flac16.wav")
    items = _ymsb_canonical_items(md, cand, show.artist)
    tagged = []
    for t in show.tracks:
        title = (f"{items[0].title} > {items[1].title}" if t.index == 1
                 else (items[t.index].title if t.index < len(items) else None))
        tagged.append(t if (t.index in ANCHORED_GAPS or title is None) else
                      t.model_copy(update={"title": title, "title_source": "tags"}))
    write_artifact(sws.show, show.model_copy(update={"tracks": tagged}))

    donor_ident, donor_md = _bad_ymsb_donor(md)
    cand2 = _ymsb_candidate()
    cand2.recordings.append(RecordingSummary(identifier=donor_ident))
    write_artifact(sws.provenance, Provenance(
        performance_id=cand2.performance_id, run="r1", dossier="great",
        candidate=cand2, processed_at="2026-08-31T00:00:00+00:00"))

    md_unusable = json.loads((FIXTURES / "ymsb2005_metadata.json").read_text())
    md_unusable["metadata"]["description"] = "A great night. Recorded from the balcony."
    ia_map = {"ymsb2005-12-31.flac16.wav": md_unusable, donor_ident: donor_md}
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: MultiIA(ia_map))
    result = cli_invoke(cfg, "fix", "nocanon-anchored", "--suggest-titles")
    assert "no usable canonical setlist" in result.output
    assert read_overrides(sws).titles == {}


def test_below_floor_donor_with_usable_canonical_falls_through_to_dp(tmp_path, monkeypatch):
    """Same below-FLOOR donor, but this time the canonical setlist IS usable
    (`_staged_anchored_ymsb_show`'s real fixture). The sibling arm must
    decline and fall through to the canonical DP -- pinned on the proposal's
    OWN evidence_source, not merely on the titles landing right: the header
    line the DP path echoes never says "sibling-align" (it says
    "duration-model" or "sibling-duration"), so a regression that made the
    declined donor win anyway would show up as a wrong evidence tag before
    it ever showed up as a wrong title."""
    cfg = _cfg(tmp_path)
    sws = _staged_anchored_ymsb_show(tmp_path, monkeypatch)
    md = json.loads((FIXTURES / "ymsb2005_metadata.json").read_text())
    donor_ident, donor_md = _bad_ymsb_donor(md)
    cand = _ymsb_candidate()
    cand.recordings.append(RecordingSummary(identifier=donor_ident))
    write_artifact(sws.provenance, Provenance(
        performance_id=cand.performance_id, run="r1", dossier="great",
        candidate=cand, processed_at="2026-08-31T00:00:00+00:00"))
    ia_map = {"ymsb2005-12-31.flac16.wav": md, donor_ident: donor_md}
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: MultiIA(ia_map))
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles", "--no-run")
    assert result.exit_code == 0, result.output
    assert "sibling-align" not in result.output
    assert "proposal (duration-model)" in result.output or "proposal (sibling-duration)" in result.output
    ov = read_overrides(sws)
    assert ov.titles == ANCHORED_GAPS


def test_suggest_titles_c1_staleness_guard_still_fires_before_donor_work(tmp_path, monkeypatch):
    """C1's staleness guard must refuse BEFORE the sibling arm ever loads a
    donor -- a stale `show.json` makes the track numbering untrustworthy for
    either arm, and the guard's whole point is to decline before either one
    touches it."""
    cfg = _cfg(tmp_path)
    sws = _staged_anchored_ymsb_show(tmp_path, monkeypatch)
    victim = read_model(sws.show, Show).tracks[0].filename
    stage_result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--exclude", victim, "--no-run")
    assert stage_result.exit_code == 0, stage_result.output
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)   # would say yes
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles", "--no-run")
    assert result.exit_code == 0, result.output
    assert "show.json is stale relative to overrides.json" in result.output
    assert read_overrides(sws).titles == {}
    assert "proposal (" not in result.output
