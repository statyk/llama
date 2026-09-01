"""Tests for `llama triage` — the named interactive held-show walkthrough.

Plan B Task 3: promotes the flagless `show`'s `_interactive_resolve` loop into
its own command, adding a `[m]etadata` mini-editor and renaming `[c]lear` to
`[o]verrule`. `show`'s own walkthrough stays in place until Task 4 strips it.
"""
from pathlib import Path

import pytest
import typer.testing as typer_testing

import llama.cli as cli
from conftest import cli_invoke
from llama.workspace import read_overrides

from test_catalog import build
from test_cli import _staged_ymsb_show

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
    assert "other-1974-01-01" not in r.output


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
    assert "zheld-1974-01-01" not in r.output   # stopped before the second show
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
# the task brief. `_staged_ymsb_show` (imported from test_cli.py rather than
# copied) gives a REAL held show flagged "unresolved track titles" -- the
# one flag this resolution is gated on -- with a real 24-track untagged
# tape behind it, the same fixture `fix --suggest-titles`'s own tests use.

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
    assert "suggest titles" not in r.output.lower()
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
    sws = _staged_ymsb_show(tmp_path, monkeypatch)   # 24 unresolved tracks -> held
    calls = _stub_redo(monkeypatch)
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
    r = cli_invoke(cfg, "triage", "ymsb2005-12-31", input="t\n")
    assert r.exit_code == 0, r.output
    ov = read_overrides(sws)
    assert len(ov.titles) == 22
    assert ov.titles[1] == "Granny Woncha Smoke Some > Ride The Wild Turkey"
    assert 11 not in ov.titles and 22 not in ov.titles   # the two filler tracks
    assert calls == ["gather"]
    assert "packaged: /pkg" in r.output


def test_declining_the_triage_proposal_writes_nothing_and_returns_to_the_prompt(
        tmp_path, tty, monkeypatch):
    """A decline must not advance/skip the show outright -- it returns to
    the same prompt (like [m] with no changes), so a second choice ([s] here)
    is still needed to move on."""
    cfg = _cfg(tmp_path)
    sws = _staged_ymsb_show(tmp_path, monkeypatch)
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
