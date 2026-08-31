import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from conftest import cli_invoke
from herder import FakeProvider
from llama.cli import app
from llama.models import Candidate, Provenance, RecordingSummary, Show
from llama.stages.gather import run_gather
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
    """One confirmation replaces 24 --set-title calls."""
    cfg = _cfg(tmp_path)
    sws = _staged_ymsb_show(tmp_path, monkeypatch)   # helper: show.json with 24 unresolved
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles", "--no-run")
    assert result.exit_code == 0, result.output
    ov = read_overrides(sws)
    assert len(ov.titles) == 22
    assert ov.titles[1] == "Granny Woncha Smoke Some > Ride The Wild Turkey"
    assert 11 not in ov.titles and 22 not in ov.titles   # the two filler tracks
    # M11 (review round 1): pin that adopting a proposal is a `did_meta`
    # edit, so the existing redo selector stages `gather` -- confirmed
    # (rather than re-derived) in the implementation that `parsed_titles`
    # already sat in the `did_meta` expression; this is the pin.
    assert "--from gather" in result.output


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
    sws = _staged_ymsb_show(tmp_path, monkeypatch)
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
    sws = _staged_ymsb_show(tmp_path, monkeypatch)
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles",
                        "--set-title", "1=Operator Chosen Title", "--no-run")
    assert result.exit_code == 0, result.output
    ov = read_overrides(sws)
    assert ov.titles[1] == "Operator Chosen Title"
    assert len(ov.titles) == 22   # the rest of the proposal still lands


def test_never_clobbers_a_track_that_already_has_a_title(tmp_path, monkeypatch):
    """M4 (round 1): `picks` only includes rows still
    `title_source == "unresolved"` on the live show. Reviewer-mutation-
    verified as unpinned before this test existed: deleting that guard
    clause from `_propose_titles_for_show` left the entire pre-round-1
    `test_cli.py` suite green."""
    cfg = _cfg(tmp_path)
    sws = _staged_ymsb_show(tmp_path, monkeypatch)
    show = read_model(sws.show, Show)
    show = show.model_copy(update={"tracks": [
        (t.model_copy(update={"title": "Already Tagged", "title_source": "tags"})
         if t.index == 1 else t)
        for t in show.tracks]})
    write_artifact(sws.show, show)
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles", "--no-run")
    assert result.exit_code == 0, result.output
    ov = read_overrides(sws)
    assert 1 not in ov.titles
    assert len(ov.titles) == 21   # 22 minus the now-already-titled track 1


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
        return real_build_canonical(ia, cand, identifier, meta, kept, artist, events,
                                    setlistfm=setlistfm, provider=provider)

    monkeypatch.setattr(gather_mod, "build_canonical", spy)
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)

    result = cli_invoke(cfg, "fix", "ymsb2005-12-31", "--suggest-titles", "--no-run")
    assert result.exit_code == 0, result.output
    assert captured["setlistfm"] is sentinel_client
    assert captured["events"] is sentinel_events


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
