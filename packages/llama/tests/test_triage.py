"""Tests for `llama triage` — the named interactive held-show walkthrough.

Plan B Task 3: promotes the flagless `show`'s `_interactive_resolve` loop into
its own command, adding a `[m]etadata` mini-editor and renaming `[c]lear` to
`[o]verrule`. `show`'s own walkthrough stays in place until Task 4 strips it.
"""
import json
from pathlib import Path

import pytest
import typer.testing as typer_testing

import llama.cli as cli
from conftest import cli_invoke, output_without_paths
from herder import FakeProvider
from llama.models import Provenance, RecordingSummary, Show
from llama.stages.gather import run_gather
from llama.workspace import (ShowWorkspace, read_model, read_overrides,
                             write_artifact)

from test_catalog import build
from test_cli import (ANCHORED_GAPS, FIXTURES, MultiIA, _staged_anchored_ymsb_show,
                      _staged_ymsb_show, _ymsb_candidate, _ymsb_sibling_donor)

PROMPT = "[e]xclude tracks / [m]etadata / [v]ague / [o]verrule / [s]kip / [q]uit"


@pytest.fixture
def tty(monkeypatch):
    """Make `sys.stdin.isatty()` report True through Typer's CliRunner, whose
    `invoke()` swaps in its own stdin object for the call — patching the
    original object's attribute wouldn't reach the code under test."""
    monkeypatch.setattr(typer_testing._NamedTextIOWrapper, "isatty", lambda self: True)


def _cfg(tmp_path: Path) -> Path:
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    return tmp_path / "config.toml"


def _held_show(tmp_path: Path, slug="gratefuldead-1973-06-10"):
    return build(tmp_path, slug, stages={"select", "gather"}, needs_review=True)


def _packaged_show(tmp_path: Path, slug="other-1974-01-01"):
    return build(tmp_path, slug,
                stages={"select", "gather", "research", "vet", "package"},
                pid="OtherBand/1974-01-01")


def _stub_redo(monkeypatch, result=Path("/pkg")):
    calls = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda config, ia, ledger, e, stage, **kw: (
                            calls.append(stage), result)[1])
    return calls


# --- TTY gate ---

def test_off_tty_errors_with_exact_message(tmp_path):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    r = cli_invoke(cfg, "triage")
    assert r.exit_code != 0
    assert ("triage is interactive; use 'llama status' or 'llama show' "
            "for scripted reads") in r.output


# --- default selector: held only ---

def test_default_selector_walks_held_only(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    _packaged_show(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="s\n")
    assert r.exit_code == 0, r.output
    assert "gratefuldead-1973-06-10" in r.output
    assert "other-1974-01-01" not in output_without_paths(r, tmp_path)


# --- broader selector: non-held prints and skips ---

def test_broader_selector_prints_and_skips_non_held(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path, slug="aheld-1973-06-10")
    _packaged_show(tmp_path, slug="bpackaged-1974-01-01")
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", "--state", "packaged", "--held", input="s\n")
    assert r.exit_code == 0, r.output
    assert "aheld-1973-06-10" in r.output
    assert "bpackaged-1974-01-01" in r.output
    # only the held show gets a prompt
    assert r.output.count(PROMPT) == 1


def test_state_enum_rejects_typo_listing_legal_values(tmp_path):
    cfg = _cfg(tmp_path)
    r = cli_invoke(cfg, "triage", "--state", "helx")
    assert r.exit_code != 0
    assert "not one of" in r.output
    for legal in ["held", "packaged", "delivered"]:
        assert legal in r.output


# --- URL block appears in the header ---

def test_url_line_appears_in_header(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="s\n")
    assert r.exit_code == 0, r.output
    assert "https://archive.org/details/gd73" in r.output


# --- [e]xclude ---

def test_exclude_action_writes_overrides_and_redoes_gather(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="e\n1\n")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).exclude == ["a.mp3"]
    assert calls == ["gather"]
    assert "packaged: /pkg" in r.output


def test_exclude_with_no_picks_skips_without_redo(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="e\n\n")
    assert r.exit_code == 0, r.output
    assert calls == []
    assert "nothing selected; skipping" in r.output
    assert read_overrides(ws).exclude == []


def test_exclude_picker_lists_the_dropped_files_but_not_the_re_admit_hint(
        tmp_path, tty, monkeypatch):
    """Spec section 4: the picker gains the excluded LISTING as context. True
    today only because `_pick_excludes` shares `_format_tracks` with `show
    --tracks`, so nothing but this test stops a future split from silently
    dropping it.

    It must NOT gain the re-admit hint: that names a `llama fix` command at an
    operator who is sitting at a prompt accepting play-order integers only.
    The hint lives in `_print_show_entry`'s `--tracks` block, and the
    walkthrough calls `_print_show_entry` with show_tracks=False."""
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    s = read_model(ws.show, Show)
    s.excluded_files = [{"filename": "spam.mp3", "duration_sec": 72.0,
                         "reasons": ["filename convention mismatch"]}]
    write_artifact(ws.show, s)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="e\n\n")
    assert r.exit_code == 0, r.output
    assert calls == []                       # picked nothing; no redo
    assert "excluded (1):" in r.output.splitlines()
    assert next(ln for ln in r.output.splitlines() if "spam.mp3" in ln).split() == [
        "x1", "1:12", "spam.mp3", "filename", "convention", "mismatch"]
    assert not any("--include" in ln for ln in r.output.splitlines())
    assert not any("re-admit one with" in ln for ln in r.output.splitlines())


# --- [v]ague ---

def test_vague_action_clears_hold_and_redoes_brief(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="v\n")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).narration == "vague"
    assert calls == ["brief"]
    from llama.models import Show
    from llama.workspace import read_model
    assert read_model(ws.show, Show).needs_review is False


# --- [o]verrule (renamed from [c]lear) ---

def test_overrule_action_clears_hold_and_redoes_package(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="o\n")
    assert r.exit_code == 0, r.output
    assert calls == ["package"]
    from llama.models import Show
    from llama.workspace import read_model
    assert read_model(ws.show, Show).needs_review is False


def test_c_key_no_longer_accepted(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="c\n")
    assert r.exit_code == 0, r.output
    assert "unrecognized" in r.output
    assert calls == []
    from llama.models import Show
    from llama.workspace import read_model
    assert read_model(ws.show, Show).needs_review is True   # untouched


# --- [s]kip / empty ---

def test_skip_action_advances_without_change(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="s\n")
    assert r.exit_code == 0, r.output
    assert calls == []
    from llama.models import Show
    from llama.workspace import read_model
    assert read_model(ws.show, Show).needs_review is True


def test_empty_input_behaves_like_skip(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="\n")
    assert r.exit_code == 0, r.output
    assert calls == []


# --- [q]uit ---

def test_quit_action_stops_the_walk(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path, slug="aheld-1973-06-10")
    _held_show(tmp_path, slug="zheld-1974-01-01")
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="q\n")
    assert r.exit_code == 0, r.output
    assert "aheld-1973-06-10" in r.output
    # stopped before the second show
    assert "zheld-1974-01-01" not in output_without_paths(r, tmp_path)
    assert calls == []


# --- [m]etadata mini-editor ---

def test_metadata_action_writes_overrides_and_redoes_gather(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    # m, then venue/city/date/titles/breaks in order, blank for the rest kept
    r = cli_invoke(cfg, "triage",
                  input="m\nMy Hall\nMy City\n1973-06-11\n1=Bertha\n9,17\n")
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.venue == "My Hall"
    assert ov.city == "My City"
    assert ov.date == "1973-06-11"
    assert ov.titles == {1: "Bertha"}
    assert ov.set_breaks == [9, 17]
    assert calls == ["gather"]
    assert "packaged: /pkg" in r.output


def test_metadata_empty_input_keeps_values_and_returns_to_prompt(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    # first m: set real values
    cli_invoke(cfg, "triage", input="m\nMy Hall\nMy City\n1973-06-11\n1=Bertha\n9,17\n")
    calls.clear()
    # second invocation: m with all-blank input keeps everything, loops back
    # to the prompt (no redo), then s to finally advance
    r = cli_invoke(cfg, "triage", input="m\n\n\n\n\n\ns\n")
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.venue == "My Hall"
    assert ov.city == "My City"
    assert ov.date == "1973-06-11"
    assert ov.titles == {1: "Bertha"}
    assert ov.set_breaks == [9, 17]
    assert calls == []          # nothing changed -> no redo triggered


def test_metadata_shows_current_effective_value_as_default(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="m\n\n\n\n\n\ns\n")
    assert r.exit_code == 0, r.output
    assert "venue" in r.output.lower()
    assert "title overrides (N=Title, comma-separated)" in r.output
    assert "set breaks after tracks (e.g. 9,17)" in r.output
    assert "date (YYYY-MM-DD)" in r.output


# --- name-or-selector mutual exclusivity, single-show positional ---

def test_positional_name_and_selector_together_errors(tmp_path, tty):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    r = cli_invoke(cfg, "triage", "gratefuldead", "--held")
    assert r.exit_code != 0
    assert "give a show OR selectors, not both" in r.output


def test_positional_name_targets_one_show(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path, slug="aheld-1973-06-10")
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", "aheld", input="o\n")
    assert r.exit_code == 0, r.output
    assert calls == ["package"]


def test_no_matching_shows(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    _packaged_show(tmp_path)
    r = cli_invoke(cfg, "triage")
    assert r.exit_code == 0, r.output
    assert "no matching shows" in r.output


# --- voice/broadcast-ready selectors are gone (moved to emcee) ---

def test_voiced_and_broadcast_ready_selectors_are_gone(tmp_path, tty):
    cfg = _cfg(tmp_path)
    for flag in ("--voiced", "--unvoiced", "--broadcast-ready"):
        r = cli_invoke(cfg, "triage", flag)
        assert r.exit_code != 0, flag
        assert "no such option" in r.output.lower(), (flag, r.output)


# --- [t] suggest titles (Task 8) ---
#
# Shares `_propose_and_confirm_titles`/`_propose_titles_for_show` with `fix
# --suggest-titles` (see cli.py) rather than duplicating the propose/render/
# confirm surface -- a divergence between the two would be invisible, per
# the task brief. Both fixtures are imported from test_cli.py rather than
# copied, and are the same ones `fix --suggest-titles`'s own tests use:
# `_staged_ymsb_show` is a REAL held show flagged "unresolved track titles"
# -- the one flag this resolution is gated on -- over a wholly untagged
# 24-track tape, which is now correctly UNPROPOSABLE (nothing anchors the
# setlist to it); `_staged_anchored_ymsb_show` is the same held show with
# all but three tracks tag-titled, which is what a rendered proposal needs.

def test_suggest_titles_hint_hidden_without_the_unresolved_titles_flag(tmp_path, tty, monkeypatch):
    """`_held_show`'s hold flag is "research asserts wrong date: x", not
    "unresolved track titles" -- the [t] hint must not appear, and typing
    "t" anyway must fall through to the ordinary unrecognized-choice path
    (no crash, no redo) rather than being silently accepted."""
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="t\n")
    assert r.exit_code == 0, r.output
    prompt = next(ln for ln in r.output.splitlines() if "[e]xclude tracks" in ln)
    assert "suggest titles" not in prompt.lower(), prompt
    assert "unrecognized" in r.output
    assert calls == []


def test_suggest_titles_hint_shown_with_the_unresolved_titles_flag(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    _staged_ymsb_show(tmp_path, monkeypatch)
    _stub_redo(monkeypatch)
    monkeypatch.setattr("typer.confirm", lambda *a, **k: False)
    r = cli_invoke(cfg, "triage", "ymsb2005-12-31", input="t\ns\n")
    assert r.exit_code == 0, r.output
    assert "suggest titles" in r.output.lower()


def test_suggest_titles_resolution_writes_overrides_and_redoes_gather(tmp_path, tty, monkeypatch):
    """The triage-side twin of
    test_cli.py::test_suggest_titles_writes_every_row_into_overrides --
    same helper, different surface, per the task-8 brief's DRY requirement."""
    cfg = _cfg(tmp_path)
    sws = _staged_anchored_ymsb_show(tmp_path, monkeypatch)   # 3 unresolved -> held
    calls = _stub_redo(monkeypatch)
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
    r = cli_invoke(cfg, "triage", "ymsb2005-12-31", input="t\n")
    assert r.exit_code == 0, r.output
    assert read_overrides(sws).titles == ANCHORED_GAPS
    assert calls == ["gather"]
    assert "packaged: /pkg" in r.output


def test_suggest_titles_sibling_arm_shares_the_triage_seam(tmp_path, tty, monkeypatch):
    """Task 6 (shared-seam pin): triage's `[t]` must reach the sibling arm
    with zero extra wiring, since it shares `_propose_and_confirm_titles`/
    `_propose_titles_for_show` with `fix --suggest-titles` rather than a
    duplicated propose/render/confirm surface (see the module comment
    above). Reuses `test_cli.py`'s untagged-ymsb-with-donor fixture
    (no-anchors band, the phase's trigger case) rather than a synthetic
    stand-in of its own."""
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
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", "ymsb2005-12-31", input="t\n")
    assert r.exit_code == 0, r.output
    assert "sibling-align" in r.output
    ov = read_overrides(sws)
    assert ov.titles[1] == "Song 01"
    assert ov.titles[9] == "Song 09a > Song 09b"


def test_declining_the_triage_proposal_writes_nothing_and_returns_to_the_prompt(
        tmp_path, tty, monkeypatch):
    """A decline must not advance/skip the show outright -- it returns to
    the same prompt (like [m] with no changes), so a second choice ([s] here)
    is still needed to move on."""
    cfg = _cfg(tmp_path)
    sws = _staged_anchored_ymsb_show(tmp_path, monkeypatch)
    calls = _stub_redo(monkeypatch)
    monkeypatch.setattr("typer.confirm", lambda *a, **k: False)
    r = cli_invoke(cfg, "triage", "ymsb2005-12-31", input="t\ns\n")
    assert r.exit_code == 0, r.output
    assert "declined; nothing written" in r.output
    assert read_overrides(sws).titles == {}
    assert calls == []
    # M1 (task-8 review round 1): the `[t] suggest titles` hint must still be
    # visible on the SECOND prompt (after the decline's `continue`), not just
    # the first -- pins RESOLVE_PROMPT_WITH_TITLES being selected per loop
    # iteration rather than echoed once before the `while True:` loop. Two
    # prompts are shown here (once for "t", once for "s"), so the hint must
    # appear at least twice.
    assert r.output.count("[t] suggest titles") >= 2


def test_nothing_to_adopt_returns_to_the_prompt(tmp_path, tty, monkeypatch):
    """Every track already titled -> picks is empty -> no confirmation is
    even offered, and the walkthrough returns to the prompt untouched."""
    from llama.models import Show
    from llama.workspace import read_model, write_artifact

    cfg = _cfg(tmp_path)
    sws = _staged_ymsb_show(tmp_path, monkeypatch)
    show = read_model(sws.show, Show)
    show = show.model_copy(update={"tracks": [
        t.model_copy(update={"title_source": "tags", "title": f"Song {t.index}"})
        for t in show.tracks]})
    write_artifact(sws.show, show)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", "ymsb2005-12-31", input="t\ns\n")
    assert r.exit_code == 0, r.output
    assert "nothing to adopt: every track already has a title" in r.output
    assert calls == []


# --- [i]nclude: re-admitting a junk-filtered file from the walkthrough ---

def _held_show_with_dropped(tmp_path, slug="gratefuldead-1973-06-10"):
    """A held show whose show.json carries two junk-filtered rows and one the
    operator excluded earlier (already in overrides.exclude), so the two
    routings `[i]` has to distinguish are both reachable."""
    from llama.models import Overrides

    ws = _held_show(tmp_path, slug)
    s = read_model(ws.show, Show)
    s.excluded_files = [
        {"filename": "intro.mp3", "reasons": ["implausibly short"], "duration_sec": 37.0},
        {"filename": "spam.mp3", "reasons": ["filename convention mismatch"],
         "duration_sec": 72.0},
        {"filename": "mine.mp3", "reasons": ["operator-excluded"], "duration_sec": 300.0},
    ]
    write_artifact(ws.show, s)
    write_artifact(ws.overrides, Overrides(exclude=["mine.mp3"]))
    return ws


def test_include_option_absent_when_nothing_was_dropped(tmp_path, tty, monkeypatch):
    """Offered on the same terms as `[t]`: only when it has something to act
    on. A show with no excluded_files must not advertise it."""
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="s\n")
    prompt = next(ln for ln in r.output.splitlines() if "[e]xclude tracks" in ln)
    assert "[i]nclude dropped" not in prompt, prompt


def test_include_option_offered_when_files_were_dropped(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show_with_dropped(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="s\n")
    assert "[i]nclude dropped" in r.output, r.output


def test_include_action_by_handle_writes_overrides_and_redoes_gather(
        tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show_with_dropped(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="i\nx1\n")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).include == ["intro.mp3"]
    assert calls == ["gather"]


def test_include_action_accepts_a_comma_group_of_handles_and_filenames(
        tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show_with_dropped(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="i\nx1,spam.mp3\n")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).include == ["intro.mp3", "spam.mp3"]


def test_include_on_an_operator_excluded_row_un_excludes_instead(
        tmp_path, tty, monkeypatch):
    """The routing shared with `fix --include` via `_split_include_targets`:
    a row the operator excluded themselves was never junk-filtered, so it
    leaves overrides.exclude rather than joining overrides.include. If this
    surface reimplemented the split the two would diverge."""
    cfg = _cfg(tmp_path)
    ws = _held_show_with_dropped(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="i\nx3\n")
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.exclude == []
    assert ov.include == []
    assert "was operator-excluded" in r.output


def test_include_with_no_picks_skips_without_redo(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show_with_dropped(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="i\n\n")
    assert "nothing selected; skipping" in r.output
    assert calls == []
    assert read_overrides(ws).include == []


def test_include_with_a_bad_handle_returns_to_the_prompt(tmp_path, tty, monkeypatch):
    """A typo'd handle is a typo, not a reason to abandon the show: report it
    and loop back, so the operator can retype rather than restart triage."""
    cfg = _cfg(tmp_path)
    ws = _held_show_with_dropped(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="i\nx9\ni\nx2\n")
    assert "no excluded file x9" in r.output
    assert read_overrides(ws).include == ["spam.mp3"], r.output
    assert calls == ["gather"]


def test_exclude_prompt_names_the_mode_on_an_x_handle(tmp_path, tty, monkeypatch):
    """`_parse_ranks` keeps only all-digit tokens, so an x-handle typed at the
    EXCLUDE prompt used to vanish into "nothing selected; skipping" -- a
    message that never mentions handles, on a listing that shows play-order
    numbers and xN handles together."""
    cfg = _cfg(tmp_path)
    ws = _held_show_with_dropped(tmp_path)
    calls = _stub_redo(monkeypatch)
    # The follow-on `i\nx2` is the point: the hint must return to the PROMPT,
    # not print advice and eject the operator from the show they would take it
    # on. Reaching overrides.include proves the loop continued.
    r = cli_invoke(cfg, "triage", input="e\nx1\ni\nx2\n")
    assert "x-handles name DROPPED files" in r.output
    assert "[i]nclude" in r.output
    assert "nothing selected; skipping" not in r.output, r.output
    ov = read_overrides(ws)
    assert ov.exclude == ["mine.mp3"]          # the [e] input applied nothing
    assert ov.include == ["spam.mp3"]          # ...and [i] was still reachable
    assert calls == ["gather"]


def test_exclude_prompt_applies_nothing_on_a_mixed_input(tmp_path, tty, monkeypatch):
    """`1,x2` must apply NOTHING. Half-applying it excludes track 1 and loses
    the x2 with no way to tell that happened, which is worse than refusing.

    MEASURED SCOPE: the property is protected at TWO sites -- `_pick_excludes`
    returns no picks on wrong_mode, and the caller discards them anyway by
    looping back -- so no SINGLE mutation reaches it and this test stays green
    against either one alone. It fires only when both are broken together
    (verified). That makes it a last line of defence rather than the pin for
    either site; `test_exclude_prompt_names_the_mode_on_an_x_handle` is what
    pins the caller's `continue`."""
    cfg = _cfg(tmp_path)
    ws = _held_show_with_dropped(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="e\n1,x2\ns\n")
    assert "x-handles name DROPPED files" in r.output
    assert read_overrides(ws).exclude == ["mine.mp3"]   # track 1 NOT excluded
    assert calls == []
