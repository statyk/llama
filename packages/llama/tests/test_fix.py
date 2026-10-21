"""Tests for `llama fix` — the override editor with auto-applied redo.

Plan B Task 2: `fix` absorbs the old `show` edit flags under clearer names
and, by default, runs the correct redo itself (`--no-run` stages instead).
`show`'s edit flags stay in place until Task 4 removes them.
"""
import json
from pathlib import Path

import pytest

import llama.cli as cli
import llama.pipeline as pipeline
from conftest import cli_invoke
from herder import FakeProvider
from herder.limits import RateLimited
from llama.errors import LlamaError
from llama.ia_client import IAError
from llama.locks import Locked, file_lock
from llama.models import Overrides, Show, Track
from llama.stages.gather import compute_gather
from llama.workspace import ShowWorkspace, read_model, read_overrides, write_artifact

from helpers import packaged_gd73, tree_bytes
from test_catalog import build
from test_cli import _staged_ymsb_show
from test_stage_gather import IDENT, StubIA, make_candidate


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
    monkeypatch.setattr(cli, "_redo_show_locked",
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
    # `--include` is deliberately absent from this list: the UX redesign
    # renamed the old show-level `--include` (an un-exclude) to `--unexclude`,
    # and 2026-09-07 reintroduced `--include` on `fix` with its literal
    # meaning -- re-admit a file the junk filter dropped.
    for flag, value in [("--title", "1=Song")]:
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
    monkeypatch.setattr(cli, "_redo_show_locked",
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


# --- --include: re-admitting a junk-filtered file ---

def _show_with_excluded(tmp_path: Path):
    """A gathered show carrying four excluded files: two junk-filtered, one the
    operator excluded earlier (already in overrides.exclude), and one written by
    a PRE-FEATURE llama -- bare `filename`, no `reasons`, no `duration_sec`.

    The legacy row is last, so it takes `x4` and renumbers nothing above it."""
    from llama.models import Overrides, Show
    from llama.workspace import read_model, write_artifact

    ws = _gathered_show(tmp_path)
    s = read_model(ws.show, Show)
    s.excluded_files = [
        {"filename": "intro.mp3", "reasons": ["implausibly short"], "duration_sec": 37.0},
        {"filename": "spam.mp3", "reasons": ["filename convention mismatch"],
         "duration_sec": 72.0},
        {"filename": "dropped.mp3", "reasons": ["operator-excluded"], "duration_sec": 300.0},
        {"filename": "legacy.mp3"},
    ]
    write_artifact(ws.show, s)
    write_artifact(ws.overrides, Overrides(exclude=["dropped.mp3"]))
    return ws


def test_include_by_handle_writes_overrides_include(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    stages = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", "x1")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).include == ["intro.mp3"]
    assert stages == ["gather"]


def test_include_handle_is_the_one_show_tracks_printed(tmp_path, monkeypatch):
    """The handle an operator READS and the handle the resolver MEANS come from
    one producer (`_excluded_handles`). Resolve `spam.mp3`'s handle out of the
    real `show --tracks` listing and feed it straight back to `fix --include`:
    any divergence between the two call sites lands on a different file."""
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    _stub_redo(monkeypatch)
    listed = cli_invoke(cfg, "show", "gratefuldead", "--tracks")
    assert listed.exit_code == 0, listed.output
    rows = [ln.split() for ln in listed.output.splitlines()
            if "spam.mp3" in ln.split()]
    assert len(rows) == 1, listed.output
    handle = rows[0][0]
    assert handle.startswith("x"), listed.output
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", handle)
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).include == ["spam.mp3"]


def test_include_by_filename_and_comma_group(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", "x1,spam.mp3")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).include == ["intro.mp3", "spam.mp3"]


def test_include_of_an_operator_excluded_file_unexcludes_it(tmp_path, monkeypatch):
    """Owner decision: --include is the single undo. On a row whose reason is
    operator-excluded it edits overrides.exclude, NOT overrides.include -- the
    two lists must never both name a file.

    `ov.exclude == []` alone does NOT pin the routing: _edit_overrides drops
    every `add_include` name from `exclude` anyway, so that half stays true
    with the routing removed. `ov.include == []` is the assertion that bites.
    """
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", "x3")
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.exclude == []
    assert ov.include == []


def test_excluding_an_included_file_removes_it_from_include(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    _stub_redo(monkeypatch)
    cli_invoke(cfg, "fix", "gratefuldead", "--include", "x1")
    assert read_overrides(ws).include == ["intro.mp3"]
    r = cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "intro.mp3")
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.include == []
    # "dropped.mp3" is the fixture's pre-existing exclusion and is untouched:
    # the brief drafted this as `== ["intro.mp3"]`, which would have passed
    # only if --exclude REPLACED the list instead of appending to it.
    assert ov.exclude == ["dropped.mp3", "intro.mp3"]


def test_including_a_staged_exclusion_leaves_the_lists_disjoint(tmp_path, monkeypatch):
    """The reachable path into the state gather has to tiebreak: `--exclude f
    --no-run` stages the exclusion WITHOUT re-gathering, so `f` is still an
    ordinary track and carries no `operator-excluded` row. A later
    `--include f` therefore routes to `overrides.include`, and only
    _edit_overrides' own `add_include` clause keeps it out of `exclude`."""
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    _stub_redo(monkeypatch)
    cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "a.mp3", "--no-run")
    assert read_overrides(ws).exclude == ["dropped.mp3", "a.mp3"]
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", "a.mp3")
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.include == ["a.mp3"]
    assert ov.exclude == ["dropped.mp3"]


def test_same_file_in_both_flags_errors(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    stages = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead",
                   "--include", "x1", "--exclude", "intro.mp3")
    assert r.exit_code != 0
    assert "name the same file" in r.output
    assert stages == []
    # nothing written: overrides.json is byte-identical to what it was
    ov = read_overrides(ws)
    assert ov.include == []
    assert ov.exclude == ["dropped.mp3"]


def test_exclude_and_include_of_different_files_both_apply(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    stages = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead",
                   "--include", "x1", "--exclude", "a.mp3")
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.include == ["intro.mp3"]
    assert ov.exclude == ["dropped.mp3", "a.mp3"]
    assert stages == ["gather"]


def test_out_of_range_handle_errors(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", "x9")
    assert r.exit_code != 0
    # the whole message, count clause included: the count is what tells an
    # operator whether they mistyped the handle or read a stale listing.
    assert "no excluded file x9 (show has 4 excluded files)" in r.output


def test_resolve_include_tokens_needs_show_json(tmp_path):
    """The handle branch is the only one that reads show.json; a plain filename
    must resolve without it. (`fix` guards on show.json before it gets here, so
    this arm is only reachable by calling the resolver directly.)"""
    import pytest

    from llama.errors import LlamaError

    ws = _show_with_excluded(tmp_path)
    ws.show.unlink()
    assert cli._resolve_include_tokens(ws, ["intro.mp3"]) == ["intro.mp3"]
    # `x1foo.mp3` is the EARLY-RETURN site's own case: it is not a handle, so
    # the guard must not fire and no show.json is needed. Under `match` there,
    # this raises instead -- the only observable difference that site makes on
    # its own, since `fix` guards on show.json before the resolver is reached.
    assert cli._resolve_include_tokens(ws, ["x1foo.mp3"]) == ["x1foo.mp3"]
    with pytest.raises(LlamaError):
        cli._resolve_include_tokens(ws, ["x1"])


def test_include_refuses_to_combine_with_suggest_titles(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    stages = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", "x1", "--suggest-titles")
    assert r.exit_code != 0
    assert ("--suggest-titles cannot be combined with "
            "--exclude/--unexclude/--include") in r.output
    # The remedy is the half an operator copies. It must name the flag they
    # typed -- being told to re-run `--exclude ...` after typing --include
    # sends them to a command that does something else entirely.
    assert "`llama fix gratefuldead-1973-06-10 --include ...` without --no-run" in r.output
    assert stages == []


def test_include_reads_a_pre_feature_excluded_row(tmp_path, monkeypatch):
    """A `show.json` written before this feature carries excluded rows with a
    bare `filename` -- no `reasons`, no `duration_sec`. The operator-excluded
    routing must read those defensively (`e.get("reasons", [])`), not index
    them: `e["reasons"]` raises KeyError on exactly this row and takes the
    whole command down."""
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    stages = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", "x4")
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.include == ["legacy.mp3"]
    assert ov.exclude == ["dropped.mp3"]
    assert stages == ["gather"]


def test_a_filename_that_merely_starts_like_a_handle_is_a_filename(tmp_path, monkeypatch):
    """`_HANDLE` matches with fullmatch, not match, at BOTH of its call sites.

    Under `match` the ordinary filename `x1foo.mp3` is a handle, and the two
    sites go wrong differently -- so this needs two cases, one per site.
    Measured: flipping either site ALONE leaves the single-token case below
    green, because the other site's `fullmatch` still routes the token
    correctly. Only the second, mixed case reaches the lookup site on its own.
    """
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", "x1foo.mp3")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).include == ["x1foo.mp3"]

    # Mixed group: the real handle `x1` makes the early-return guard fire on
    # its own merits, so this reaches the LOOKUP site with a lookalike token.
    # There, `match` finds "x1" but the dict is keyed on the whole token, so
    # the file is rejected as an unknown handle instead of taken as a filename.
    ws2 = _show_with_excluded(tmp_path / "second")
    cfg2 = _cfg(tmp_path / "second")
    r = cli_invoke(cfg2, "fix", "gratefuldead", "--include", "x1,x1foo.mp3")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws2).include == ["intro.mp3", "x1foo.mp3"]


def test_include_is_repeatable(tmp_path, monkeypatch):
    """Two separate --include flags in one invocation, not just a comma group."""
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead",
                   "--include", "x1", "--include", "spam.mp3")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).include == ["intro.mp3", "spam.mp3"]


def test_include_echoes_the_new_include_list(tmp_path, monkeypatch):
    """The user-visible confirmation line for a re-admission. Scoped to one
    parsed line, never a whole-output match: `fix` prints a `path:`-style line
    carrying tmp_path, which embeds this test's own name."""
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", "x1")
    assert r.exit_code == 0, r.output
    assert any(
        ln == ("gratefuldead-1973-06-10: overrides.include = ['intro.mp3'] "
               "(the hold clears itself if a clean re-gather results)")
        for ln in r.output.splitlines()), r.output


def test_unexclude_routing_says_what_it_did(tmp_path, monkeypatch):
    """--include on an operator-excluded row edits overrides.EXCLUDE. Reporting
    only that is true but unanswerable for the operator, who typed --include;
    the routing itself has to be visible to the person who invoked it."""
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", "x3")
    assert r.exit_code == 0, r.output
    assert any(
        ln == ("gratefuldead-1973-06-10: dropped.mp3 was operator-excluded, not "
               "junk-filtered -- removed from overrides.exclude rather than "
               "added to overrides.include")
        for ln in r.output.splitlines()), r.output



def test_a_no_op_exclude_still_reports_the_override_list(tmp_path, monkeypatch):
    """Whole-branch review M2. The `--include` work gated the exclude echo on
    RESOLVED values so a lone `--include` would not print a spurious
    `overrides.exclude = []` line -- but that also silenced a pre-existing
    no-op: `--exclude ,` resolves to nothing, still redoes from gather, and on
    main printed the list. Gate on what the operator TYPED, not on what it
    resolved to."""
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--exclude", ",")
    assert r.exit_code == 0, r.output
    assert "overrides.exclude = " in r.output, r.output


# --- slice 7: --untitled (spec "Slice 7") ---

def _all_unresolved_show(tmp_path, n=3):
    ws = _held_show(tmp_path)
    show = read_model(ws.show, Show)
    show.tracks = [Track(index=i, set="1", title=f"t{i:02d}.mp3", filename=f"t{i:02d}.mp3",
                         title_source="unresolved") for i in range(1, n + 1)]
    show.review_flags = ["unresolved track titles"]
    write_artifact(ws.show, show)
    return ws


def test_untitled_is_refused_when_any_track_is_resolved(tmp_path):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)          # its one track is tagged
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled")
    assert r.exit_code != 0 and "applies only when every track is unresolved (1 of 1 resolved)" in r.output


@pytest.mark.parametrize("flag", [["--suggest-titles"], ["--exclude", "x1"], ["--unexclude", "a"],
                                  ["--include", "x1"], ["--set-title", "1=A"], ["--set-breaks", "1"],
                                  ["--set-encore", "2"], ["--narration", "vague"], ["--overrule"], ["--no-run"],
                                  ["--clear-set-breaks"], ["--clear-encore"], ["--clear-title", "1"],
                                  ["--set-venue", "V"], ["--set-city", "C"], ["--set-date", "1973-06-10"]])
def test_untitled_refuses_every_combination(tmp_path, monkeypatch, flag):
    cfg = _cfg(tmp_path)
    ws = _all_unresolved_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", *flag, input="y\n")
    assert r.exit_code != 0 and f"--untitled cannot be combined with {flag[0]}" in r.output
    # refused before the confirmation prompt and before anything is written
    assert "Title every track" not in r.output
    assert not ws.overrides.exists() and calls == []


def test_untitled_lists_filenames_and_declining_writes_nothing(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _all_unresolved_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", input="n\n")
    assert "   1  t01.mp3" in r.output and "   3  t03.mp3" in r.output
    assert "tracks on this tape (no resolved titles):" in r.output
    assert not ws.overrides.exists() and calls == []


def test_untitled_one_confirmation_writes_titles_narration_and_one_set_then_redoes(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _all_unresolved_show(tmp_path)
    calls = _stub_redo(monkeypatch, result=Path("/pkg"))
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", input="y\n")
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.titles == {1: "Untitled (track 1)", 2: "Untitled (track 2)", 3: "Untitled (track 3)"}
    assert ov.narration == "vague" and ov.set_breaks == []
    assert ov.encore_after is None
    assert calls == ["gather"] and "packaged: /pkg" in r.output


def test_untitled_clears_a_pre_existing_encore_so_the_tape_is_one_set(tmp_path, monkeypatch):
    """The confirmation promises "one set"; a leftover encore_after would still
    relabel the tail "encore" (final review I2)."""
    cfg = _cfg(tmp_path)
    ws = _all_unresolved_show(tmp_path, n=6)
    write_artifact(ws.overrides, Overrides(encore_after=3))
    _stub_redo(monkeypatch, result=Path("/pkg"))
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", input="y\n")
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.encore_after is None and ov.set_breaks == []
    # the real gather over the written overrides yields a single set label
    gws = ShowWorkspace(tmp_path / "gather")
    write_artifact(gws.overrides, ov)
    res = compute_gather(gws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert {t.set for t in res.show.tracks} == {"1"}


def test_untitled_is_refused_on_a_zero_track_show(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _all_unresolved_show(tmp_path, n=0)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", input="y\n")
    assert r.exit_code == 1
    assert "--untitled applies only when every track is unresolved (0 of 0 resolved)" in r.output
    assert not ws.overrides.exists() and calls == []


def test_untitled_declined_says_so_exits_zero_and_leaves_overrides_alone(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _all_unresolved_show(tmp_path)
    write_artifact(ws.overrides, Overrides(encore_after=2))
    before = ws.overrides.read_bytes()
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", input="n\n")
    assert r.exit_code == 0, r.output
    assert "declined; nothing written" in r.output
    assert ws.overrides.read_bytes() == before and calls == []


def test_untitled_confirmed_but_still_held_says_still_held_not_declined(tmp_path, monkeypatch):
    # fw1 review M-1: written-then-held is not a decline (overrides are changed).
    cfg = _cfg(tmp_path)
    ws = _all_unresolved_show(tmp_path)
    calls = _stub_redo(monkeypatch, result=None)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", input="y\n")
    assert r.exit_code == 0, r.output
    assert "still held: " in r.output and "declined" not in r.output
    assert read_overrides(ws).narration == "vague" and calls[0] == "gather"


def test_untitled_overrules_remaining_flags_then_continues_from_brief(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _all_unresolved_show(tmp_path)
    outcomes = iter([None, Path("/pkg")])
    calls = []

    def fake_redo(config, ia, ledger, e, stage, **kw):
        calls.append(stage)
        if stage == "gather":   # the re-gather raises a flag, as the spec expects
            s = read_model(e.ws.show, Show)
            s.needs_review = True
            s.review_flags = ["single-set structure for a long show (160 min)"]
            write_artifact(e.ws.show, s)
        return next(outcomes)
    monkeypatch.setattr(cli, "_redo_show_locked", fake_redo)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", input="y\n")
    assert calls == ["gather", "brief"]
    assert "remaining flags overruled" in r.output and "packaged: /pkg" in r.output
    assert read_model(ws.show, Show).needs_review is False


def test_untitled_gather_makes_no_align_structure_call(tmp_path):
    # the override path (set_breaks=[]) skips align(): run the real gather on gd73 with an align provider
    # that would fail if called
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(titles={i: f"Untitled (track {i})" for i in range(1, 7)},
                                           narration="vague", set_breaks=[]))

    class Boom:
        def complete(self, *a, **k):
            raise AssertionError("align_structure called")
    res = compute_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT, align_provider=Boom())
    assert res.needs_llm == () and {t.set for t in res.show.tracks} == {"1"}
    assert [t.title for t in res.show.tracks][0] == "Untitled (track 1)"


def test_untitled_is_refused_when_only_some_tracks_are_resolved(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _all_unresolved_show(tmp_path, n=3)
    show = read_model(ws.show, Show)
    show.tracks[1] = show.tracks[1].model_copy(update={"title_source": "tags", "title": "Dew"})
    write_artifact(ws.show, show)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", input="y\n")
    assert r.exit_code != 0 and "(1 of 3 resolved)" in r.output
    assert not ws.overrides.exists() and calls == []


# --- slice C: fix is one restoring unit ---

def _billy_shape(tmp_path, monkeypatch):
    """The billystrings-2021-12-04 sequence on a real 24-track tape: overrides already
    carrying edits, then the bad structure fix (pre-repair overrides set_breaks [10, 20],
    encore_after 20)."""
    from test_pipeline import fake_providers
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    # the dir name must be slugify(performance_id): process_show writes there
    sws = _staged_ymsb_show(tmp_path, monkeypatch, slug="yondermountainstringband-2005-12-31")
    write_artifact(sws.selection, {"identifier": "ymsb2005-12-31.flac16.wav"})
    write_artifact(sws.overrides, Overrides(narration="vague", titles={1: "Kirby Hill"}))
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    return tmp_path / "config.toml", sws


def test_a_refused_structure_fix_leaves_every_file_byte_identical(tmp_path, monkeypatch):
    cfg, sws = _billy_shape(tmp_path, monkeypatch); before = tree_bytes(sws.dir)
    r = cli_invoke(cfg, "fix", "yonder", "--set-breaks", "10,20", "--set-encore", "20")
    assert r.exit_code == 1 and isinstance(r.exception, LlamaError)
    assert "overrides.encore_after (20) must be greater than every set break [10, 20]" in str(r.exception)
    assert tree_bytes(sws.dir) == before            # provenance.json and overrides.json included
    r2 = cli_invoke(cfg, "fix", "yonder", "--clear-encore", "--no-run")   # still editable afterwards
    assert r2.exit_code == 0, r2.output


def test_no_run_stages_bad_overrides_and_the_redo_restores_and_names_the_field(tmp_path, monkeypatch):   # C3
    cfg, sws = _billy_shape(tmp_path, monkeypatch)
    assert cli_invoke(cfg, "fix", "yonder", "--set-breaks", "10,20", "--set-encore", "20", "--no-run").exit_code == 0
    assert read_overrides(sws).encore_after == 20
    before = tree_bytes(sws.dir)
    r = cli_invoke(cfg, "redo", "yonder", "--from", "gather")
    assert r.exit_code == 1 and "encore_after" in str(r.exception) and tree_bytes(sws.dir) == before


def test_a_fix_adding_one_override_keeps_the_others(tmp_path, monkeypatch):   # (pin)
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); _stub_redo(monkeypatch)
    write_artifact(ws.overrides, Overrides(exclude=["junk.mp3"], venue="Hall", titles={2: "Dew"}, narration="vague"))
    assert cli_invoke(cfg, "fix", "gratefuldead", "--set-city", "Austin, TX").exit_code == 0
    ov = read_overrides(ws)
    assert (ov.exclude, ov.venue, ov.titles, ov.narration, ov.city) == (["junk.mp3"], "Hall", {2: "Dew"}, "vague", "Austin, TX")


def _held(ws):
    s = read_model(ws.show, Show); s.needs_review = True; s.review_flags = ["research asserts wrong date: 1974-01-01"]
    write_artifact(ws.show, s)


def test_failed_accept_vague_restores_the_hold_and_the_overrides(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); _held(ws); before = tree_bytes(ws.dir)
    monkeypatch.setattr(pipeline, "run_brief", lambda *a, **k: (_ for _ in ()).throw(RateLimited("limit")))
    r = cli_invoke(cfg, "fix", "gratefuldead", "--narration", "vague")
    assert r.exit_code == 1 and isinstance(r.exception, RateLimited)
    assert tree_bytes(ws.dir) == before and read_model(ws.show, Show).needs_review is True


def test_failed_overrule_restores_every_file(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); _held(ws); before = tree_bytes(ws.dir)
    monkeypatch.setattr(pipeline, "run_package", lambda *a, **k: (_ for _ in ()).throw(IAError("archive down")))
    r = cli_invoke(cfg, "fix", "gratefuldead", "--overrule")
    assert r.exit_code == 1 and isinstance(r.exception, IAError) and "archive down" in str(r.exception)
    assert tree_bytes(ws.dir) == before


def test_a_multi_flag_fix_whose_redo_fails_leaves_nothing_of_the_first_edits(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); _held(ws); before = tree_bytes(ws.dir)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--narration", "vague", "--set-breaks", "2,4", "--set-encore", "4")
    assert r.exit_code == 1 and "encore_after" in str(r.exception)
    assert tree_bytes(ws.dir) == before            # no narration, no cleared hold, no breaks


def test_a_failed_first_edit_removes_the_overrides_file_it_created(tmp_path, monkeypatch):   # Review Focus 2
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); assert not ws.overrides.exists()
    monkeypatch.setattr(cli, "_redo_show_locked", lambda *a, **k: (_ for _ in ()).throw(LlamaError("boom")))
    r = cli_invoke(cfg, "fix", "gratefuldead", "--set-venue", "Hall")
    assert r.exit_code == 1 and "boom" in str(r.exception)
    assert not ws.overrides.exists()


def test_fix_writes_overrides_under_the_show_lock(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); seen = []; real = cli._edit_overrides
    def probe(show_ws, **kw):
        try:
            with file_lock(show_ws.lock, blocking=False): seen.append("free")
        except Locked:
            seen.append("held")
        return real(show_ws, **kw)
    monkeypatch.setattr(cli, "_edit_overrides", probe)
    assert cli_invoke(cfg, "fix", "gratefuldead", "--set-venue", "Hall", "--no-run").exit_code == 0
    assert seen == ["held"]


def test_fix_refuses_when_the_show_changed_after_the_prompt(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); calls = _stub_redo(monkeypatch)
    def other_command_meanwhile(ia, config, entry, show):
        write_artifact(entry.ws.overrides, Overrides(venue="Elsewhere")); return {1: "Dew"}
    monkeypatch.setattr(cli, "_propose_and_confirm_titles", other_command_meanwhile)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--suggest-titles")
    assert r.exit_code == 1 and "changed by another command; run it again" in str(r.exception)
    assert read_overrides(ws) == Overrides(venue="Elsewhere") and calls == []


def test_untitled_failure_after_the_overrule_restores_everything(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path); ws = _all_unresolved_show(tmp_path); before = tree_bytes(ws.dir)
    stages = []
    def fake(config, ia, ledger, e, stage, **kw):
        stages.append(stage)
        if stage == "gather":
            s = read_model(e.ws.show, Show); s.needs_review = True; s.review_flags = ["x"]; write_artifact(e.ws.show, s)
            return None
        raise LlamaError("brief failed")
    monkeypatch.setattr(cli, "_redo_show_locked", fake)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", input="y\n")
    assert r.exit_code == 1 and stages == ["gather", "brief"] and "brief failed" in str(r.exception)
    assert tree_bytes(ws.dir) == before


def test_fix_on_a_show_with_no_show_json_takes_metadata_and_filename_edits(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select"})
    write_artifact(ws.overrides, Overrides(set_breaks=[10, 20], encore_after=20))
    assert cli_invoke(cfg, "fix", "gratefuldead", "--clear-encore", "--no-run").exit_code == 0
    assert read_overrides(ws).encore_after is None
    assert cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "junk.mp3", "--no-run").exit_code == 0
    calls = _stub_redo(monkeypatch)
    assert cli_invoke(cfg, "fix", "gratefuldead", "--set-venue", "Hall").exit_code == 0 and calls == ["gather"]


@pytest.mark.parametrize("args", [["--overrule"], ["--narration", "vague"], ["--include", "junk.mp3"],
                                  ["--suggest-titles"], ["--untitled"]])
def test_fix_on_a_show_with_no_show_json_refuses_the_rest_and_names_the_remedy(tmp_path, args):
    cfg = _cfg(tmp_path); build(tmp_path, "gratefuldead-1973-06-10", stages={"select"})
    r = cli_invoke(cfg, "fix", "gratefuldead", *args)
    assert r.exit_code == 1 and "rebuild it with: llama redo gratefuldead-1973-06-10 --from gather" in r.output


def test_a_typer_exit_inside_the_unit_leaves_the_show_byte_identical(tmp_path):   # clash
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path)
    before = tree_bytes(ws.dir)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "a.mp3", "--include", "a.mp3")
    assert r.exit_code == 1 and "name the same file(s): a.mp3" in r.output
    assert tree_bytes(ws.dir) == before and not (ws.dir / ".txn").exists()


def test_a_track_number_exclude_without_show_json_refuses_and_changes_nothing(tmp_path):
    cfg = _cfg(tmp_path)
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select"})
    before = tree_bytes(ws.dir)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "3")
    assert r.exit_code == 1 and "resolving a track number needs show.json" in r.output
    assert tree_bytes(ws.dir) == before and not (ws.dir / ".txn").exists()
