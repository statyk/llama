"""Tests for `llama fix` — the override editor with auto-applied redo.

Plan B Task 2: `fix` absorbs the old `show` edit flags under clearer names
and, by default, runs the correct redo itself (`--no-run` stages instead).
`show`'s edit flags stay in place until Task 4 removes them.
"""
import json
from pathlib import Path

import llama.cli as cli
from conftest import cli_invoke
from llama.workspace import read_overrides

from test_catalog import build


def _cfg(tmp_path: Path) -> Path:
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    return tmp_path / "config.toml"


def _held_show(tmp_path: Path):
    return build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"},
                needs_review=True)


def _gathered_show(tmp_path: Path):
    return build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})


def _stub_redo(monkeypatch, picked=None, result=Path("/pkg")):
    """Stub `_redo_show` so no real pipeline work happens; records the stage
    it was called with (or nothing if never called)."""
    calls = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda config, ia, ledger, e, stage, **kw: (
                            calls.append(stage), result)[1])
    return calls


# --- bare invocation / missing edit flag ---

def test_bare_fix_errors(tmp_path):
    cfg = _cfg(tmp_path)
    _gathered_show(tmp_path)
    r = cli_invoke(cfg, "fix", "gratefuldead")
    assert r.exit_code != 0
    assert ("nothing to fix: give an edit flag (see --help), or inspect with: "
            "llama show gratefuldead-1973-06-10") in r.output


# --- renamed spellings exist; old `show` spellings do not ---

def test_old_show_flags_are_not_fix_flags(tmp_path):
    cfg = _cfg(tmp_path)
    _gathered_show(tmp_path)
    for flag, value in [("--include", "x.mp3"), ("--title", "1=Song")]:
        r = cli_invoke(cfg, "fix", "gratefuldead", flag, value)
        assert r.exit_code != 0, flag
        assert "no such option" in r.output.lower(), (flag, r.output)
    for flag in ("--vague", "--full", "--clear"):
        r = cli_invoke(cfg, "fix", "gratefuldead", flag)
        assert r.exit_code != 0, flag
        assert "no such option" in r.output.lower(), (flag, r.output)


def test_renamed_flags_exist(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _gathered_show(tmp_path)
    _stub_redo(monkeypatch)
    for args in (["--unexclude", "junk.mp3"], ["--narration", "full"], ["--overrule"]):
        r = cli_invoke(cfg, "fix", "gratefuldead", *args)
        assert r.exit_code == 0, (args, r.output)


# --- each flag writes the expected overrides.json ---

def test_exclude_writes_overrides(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "junk.mp3")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).exclude == ["junk.mp3"]


def test_exclude_by_track_number(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "1")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).exclude == ["a.mp3"]


def test_unexclude_removes_from_overrides(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    _stub_redo(monkeypatch)
    cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "junk.mp3")
    r = cli_invoke(cfg, "fix", "gratefuldead", "--unexclude", "junk.mp3")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).exclude == []


def test_set_venue_city_date(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _gathered_show(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--set-venue", "My Hall",
                  "--set-city", "My City", "--set-date", "1973-06-11")
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.venue == "My Hall"
    assert ov.city == "My City"
    assert ov.date == "1973-06-11"


def test_set_title(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _gathered_show(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--set-title", "1=Bertha")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).titles == {1: "Bertha"}


def test_clear_title(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _gathered_show(tmp_path)
    _stub_redo(monkeypatch)
    cli_invoke(cfg, "fix", "gratefuldead", "--set-title", "1=Bertha")
    r = cli_invoke(cfg, "fix", "gratefuldead", "--clear-title", "1")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).titles == {}


def test_set_breaks_and_clear(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _gathered_show(tmp_path)
    _stub_redo(monkeypatch)
    cli_invoke(cfg, "fix", "gratefuldead", "--set-breaks", "9,17")
    assert read_overrides(ws).set_breaks == [9, 17]
    cli_invoke(cfg, "fix", "gratefuldead", "--clear-set-breaks")
    assert read_overrides(ws).set_breaks is None


def test_set_encore_and_clear(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _gathered_show(tmp_path)
    _stub_redo(monkeypatch)
    cli_invoke(cfg, "fix", "gratefuldead", "--set-encore", "16")
    assert read_overrides(ws).encore_after == 16
    cli_invoke(cfg, "fix", "gratefuldead", "--clear-encore")
    assert read_overrides(ws).encore_after is None


def test_set_encore_composes_with_set_breaks(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _gathered_show(tmp_path)
    _stub_redo(monkeypatch)
    cli_invoke(cfg, "fix", "gratefuldead", "--set-breaks", "7", "--set-encore", "16")
    ov = read_overrides(ws)
    assert ov.set_breaks == [7]
    assert ov.encore_after == 16


def test_set_encore_redoes_from_gather(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _gathered_show(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--set-encore", "16", "--no-run")
    assert r.exit_code == 0, r.output
    assert "--from gather" in r.output


def test_set_encore_non_numeric_errors_cleanly(tmp_path):
    cfg = _cfg(tmp_path)
    _gathered_show(tmp_path)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--set-encore", "sixteen")
    assert r.exit_code != 0
    assert "--set-encore expects" in r.output
    assert not isinstance(r.exception, ValueError)


def test_narration_vague_and_full(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--narration", "vague")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).narration == "vague"
    r = cli_invoke(cfg, "fix", "gratefuldead", "--narration", "full")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).narration == "full"


def test_overrule_clears_a_held_show(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--overrule")
    assert r.exit_code == 0, r.output
    from llama.models import Show
    from llama.workspace import read_model
    saved = read_model(ws.show, Show)
    assert saved.needs_review is False
    assert saved.review_flags == []


def test_overrule_on_non_held_show_is_a_noop_with_note(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _gathered_show(tmp_path)      # not held
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--overrule")
    assert r.exit_code == 0, r.output
    assert "not held; nothing to overrule" in r.output
    assert calls == []                # no redo triggered — nothing changed


# --- hold-clearing semantics ---

def test_narration_vague_clears_hold(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    _stub_redo(monkeypatch)
    cli_invoke(cfg, "fix", "gratefuldead", "--narration", "vague")
    from llama.models import Show
    from llama.workspace import read_model
    assert read_model(ws.show, Show).needs_review is False


def test_exclude_does_not_clear_hold(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    _stub_redo(monkeypatch)
    cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "junk.mp3")
    from llama.models import Show
    from llama.workspace import read_model
    assert read_model(ws.show, Show).needs_review is True   # NOT pre-cleared


# --- auto-run stage selection, including earliest-stage-wins combos ---

def test_exclude_fires_gather(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "junk.mp3")
    assert r.exit_code == 0, r.output
    assert calls == ["gather"]


def test_metadata_fires_gather(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _gathered_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--set-venue", "My Hall")
    assert r.exit_code == 0, r.output
    assert calls == ["gather"]


def test_narration_fires_brief(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--narration", "vague")
    assert r.exit_code == 0, r.output
    assert calls == ["brief"]


def test_overrule_fires_package(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--overrule")
    assert r.exit_code == 0, r.output
    assert calls == ["package"]


def test_combo_exclude_and_narration_fires_gather_earliest_wins(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "1", "--narration", "vague")
    assert r.exit_code == 0, r.output
    assert calls == ["gather"]


def test_apply_prints_packaged_or_still_held(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    _stub_redo(monkeypatch, result=Path("/tmp/pkg"))
    r = cli_invoke(cfg, "fix", "gratefuldead", "--narration", "vague")
    assert r.exit_code == 0, r.output
    assert "packaged: /tmp/pkg" in r.output


def test_apply_prints_still_held_when_redo_returns_none(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    monkeypatch.setattr(cli, "_redo_show",
                        lambda config, ia, ledger, e, stage, **kw: None)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--overrule")
    assert r.exit_code == 0, r.output
    assert "still held: gratefuldead-1973-06-10" in r.output


# --- --no-run stages instead of applying ---

def test_no_run_fires_nothing_and_prints_staged_hint(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "junk.mp3", "--no-run")
    assert r.exit_code == 0, r.output
    assert calls == []
    assert "staged; next: llama redo gratefuldead-1973-06-10 --from gather" in r.output


def test_no_run_with_narration(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--narration", "vague", "--no-run")
    assert r.exit_code == 0, r.output
    assert calls == []
    assert "staged; next: llama redo gratefuldead-1973-06-10 --from brief" in r.output


# --- bad input errors cleanly (ported verbatim from `show`) ---

def test_set_title_non_numeric_errors_cleanly(tmp_path):
    cfg = _cfg(tmp_path)
    _gathered_show(tmp_path)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--set-title", "abc=Song")
    assert r.exit_code != 0
    assert "--set-title expects" in r.output
    assert not isinstance(r.exception, ValueError)


def test_clear_title_non_numeric_errors_cleanly(tmp_path):
    cfg = _cfg(tmp_path)
    _gathered_show(tmp_path)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--clear-title", "abc")
    assert r.exit_code != 0
    assert "--clear-title expects" in r.output
    assert not isinstance(r.exception, ValueError)


def test_set_breaks_non_numeric_errors_cleanly(tmp_path):
    cfg = _cfg(tmp_path)
    _gathered_show(tmp_path)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--set-breaks", "a,b")
    assert r.exit_code != 0
    assert "--set-breaks expects" in r.output
    assert not isinstance(r.exception, ValueError)


def test_exclude_out_of_range_errors(tmp_path):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "99")
    assert r.exit_code != 0
    assert "track 99" in r.output or "out of range" in r.output


# --- --narration nonsense is a Typer enum error ---

def test_narration_bad_value_is_enum_error(tmp_path):
    cfg = _cfg(tmp_path)
    _gathered_show(tmp_path)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--narration", "nonsense")
    assert r.exit_code != 0
    assert "vague" in r.output and "full" in r.output
