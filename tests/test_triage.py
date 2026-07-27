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
                stages={"select", "gather", "research", "vet", "synthesize", "package"},
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

def test_vague_action_clears_hold_and_redoes_synthesize(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="v\n")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).narration == "vague"
    assert calls == ["synthesize"]
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
    assert "set breaks (e.g. 9,17)" in r.output
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
