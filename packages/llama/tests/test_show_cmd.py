"""Tests for `llama show` — strictly read-only, `--json`, archive URLs.

Plan B Task 4: strips `show` down to inspection only. Editing lives in `fix`;
the interactive walkthrough lives in `triage` (both tested elsewhere). This
file owns: the archive-URL/considered block, the read-only guarantee, the
pre-`show.json` fallback, `--tracks`, `--json`, and the `fix --overrule` hint.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer.testing as typer_testing

from conftest import cli_invoke
from llama.workspace import ShowWorkspace, write_artifact

from test_catalog import build


def _cfg(tmp_path: Path) -> Path:
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    return tmp_path / "config.toml"


@pytest.fixture
def tty(monkeypatch):
    """As in test_triage.py: make stdin report a TTY through CliRunner."""
    monkeypatch.setattr(typer_testing._NamedTextIOWrapper, "isatty", lambda self: True)


# --- archive URL + considered block ---

def test_url_and_considered_block_sorted_desc_chosen_excluded(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    write_artifact(ws.selection, {
        "identifier": "gd73-mid",
        "scores": {
            "gd73-low": {"score": 0.2, "lineage": "aud", "kept_tracks": 10},
            "gd73-mid": {"score": 0.5, "lineage": "sbd", "kept_tracks": 20},
            "gd73-high": {"score": 0.9, "lineage": "matrix", "kept_tracks": 22},
        },
    })
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert r.exit_code == 0, r.output
    assert "https://archive.org/details/gd73-mid" in r.output
    assert "gd73-mid" not in r.output.split("considered:")[1]  # chosen excluded
    considered_block = r.output.split("considered:")[1]
    high_idx = considered_block.index("gd73-high")
    low_idx = considered_block.index("gd73-low")
    assert high_idx < low_idx   # score desc


def test_single_recording_yields_no_considered_block(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert r.exit_code == 0, r.output
    assert "https://archive.org/details/gd73" in r.output
    assert "considered:" not in r.output


def test_no_selection_json_omits_url_block_entirely(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"gather"})   # no "select"
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert r.exit_code == 0, r.output
    assert "archive.org" not in r.output
    assert "considered:" not in r.output


# --- read-only guarantee ---

def test_held_show_on_tty_never_prompts(tmp_path: Path, tty):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"},
          needs_review=True)
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert r.exit_code == 0, r.output
    assert "[e]xclude" not in r.output
    assert "[o]verrule" not in r.output
    assert "state: held" in r.output


# --- --tracks ---

def test_tracks_flag_lists_numbered_tracks(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    r = cli_invoke(cfg, "show", "gratefuldead", "--tracks")
    assert r.exit_code == 0, r.output
    assert "tracks:" in r.output
    assert "1." in r.output and "Morning Dew" in r.output and "a.mp3" in r.output


def test_tracks_flag_prints_every_title_source_in_full():
    """`sibling-format` is 14 characters and the column was 10, so this branch
    shipped it as `sibling-fo`. Driven through _format_tracks directly - the
    fixture show has no recovered titles, and truncation is a formatting
    property, not a pipeline one."""
    from llama.cli import _format_tracks
    from llama.models import Track
    sources = ["tags", "setlist", "sibling", "override", "unresolved", "sibling-format"]
    tracks = [Track(index=i, set="1", title="Dark Star", filename=f"t{i:02d}.mp3",
                    duration_sec=300, segue=False, title_source=s)
              for i, s in enumerate(sources, 1)]
    lines = _format_tracks(SimpleNamespace(tracks=tracks))[1:]
    for source, line in zip(sources, lines):
        assert source in line, line
    # Every row's duration column starts at the same offset, or the table
    # stopped lining up.
    assert len({line.index(" 5:00") for line in lines}) == 1


# --- stage table ---

def test_stage_table_lists_briefing_json_once_present(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10",
          stages={"select", "gather", "research", "vet", "brief"})
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert r.exit_code == 0, r.output
    line = next(ln for ln in r.output.splitlines() if "briefing.json" in ln)
    assert "missing" not in line
    assert "d old" in line


# --- --json ---

def test_json_schema_spot_checks(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"},
              needs_review=True)
    write_artifact(ws.overrides, {
        "exclude": ["junk.mp3"], "narration": "vague", "venue": "My Hall",
        "city": "Springfield", "date": "1973-06-10", "titles": {"1": "Bertha"},
        "set_breaks": [2, 4],
    })
    r = cli_invoke(cfg, "show", "gratefuldead", "--json")
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["slug"] == "gratefuldead-1973-06-10"
    assert data["state"] == "held"
    assert data["artist"] == "Grateful Dead"
    assert data["date"] == "1973-06-10"
    assert data["identifier"] == "gd73"
    assert data["archive_url"] == "https://archive.org/details/gd73"
    assert data["considered"] == []
    assert data["run"] == "r1"
    assert data["needs_review"] is True
    assert "voiced" not in data
    assert "broadcast_ready" not in data
    assert "broadcast_reasons" not in data
    assert data["overrides"] == {
        "exclude": ["junk.mp3"], "narration": "vague", "venue": "My Hall",
        "city": "Springfield", "date": "1973-06-10", "titles": {"1": "Bertha"},
        "set_breaks": [2, 4], "encore_after": None,
    }
    assert data["stages"]["show.json"] is not None      # age in days
    assert data["stages"]["research.md"] is None        # never written
    assert "tracks" not in data


def test_json_tracks_included_when_flag_given(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    r = cli_invoke(cfg, "show", "gratefuldead", "--tracks", "--json")
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["tracks"][0]["filename"] == "a.mp3"
    assert data["tracks"][0]["title"] == "Morning Dew"


def test_json_null_fields_before_show_json_exists(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select"})   # pre-gather
    r = cli_invoke(cfg, "show", "gratefuldead", "--json")
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["state"] == "selected"
    assert data["artist"] is None
    assert data["venue"] is None
    assert data["needs_review"] is None
    assert data["overrides"] is None
    assert data["identifier"] == "gd73"    # still resolvable from selection.json


# --- selectors are gone; positional name is required ---

def test_selector_flag_is_a_usage_error(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"},
          needs_review=True)
    r = cli_invoke(cfg, "show", "--held")
    assert r.exit_code != 0
    assert "no such option" in r.output.lower()


def test_missing_name_is_a_usage_error(tmp_path: Path):
    cfg = _cfg(tmp_path)
    r = cli_invoke(cfg, "show")
    assert r.exit_code != 0


def test_old_edit_flags_are_gone(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    for flag in ("--exclude", "--include", "--vague", "--full", "--clear",
                "--apply", "--set-venue", "--set-breaks"):
        r = cli_invoke(cfg, "show", "gratefuldead", flag, "x") \
            if flag not in ("--vague", "--full", "--clear", "--apply") \
            else cli_invoke(cfg, "show", "gratefuldead", flag)
        assert r.exit_code != 0, flag
        assert "no such option" in r.output.lower(), (flag, r.output)


# --- pre-show.json fallback ---

def test_pre_show_json_prints_state_instead_of_erroring(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select"})
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert r.exit_code == 0, r.output
    assert "slug: gratefuldead-1973-06-10" in r.output
    assert "state: selected" in r.output
    assert "stages:" in r.output
    assert "show.json" in r.output and "missing" in r.output
    assert "https://archive.org/details/gd73" in r.output   # URL block still shows


def test_bare_show_dir_with_no_selection_no_show_still_inspects(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "shows" / "bare-1970-01-01")
    write_artifact(sws.provenance, {
        "performance_id": "bare/1970-01-01", "run": "r1", "dossier": "x",
        "candidate": {"performance_id": "bare/1970-01-01", "collection": "bare",
                      "date": "1970-01-01",
                      "recordings": [{"identifier": "bareid"}]},
        "processed_at": "2026-07-17T00:00:00+00:00",
    })
    cfg = _cfg(tmp_path)
    r = cli_invoke(cfg, "show", "bare")
    assert r.exit_code == 0, r.output
    assert "slug: bare-1970-01-01" in r.output
    assert "archive.org" not in r.output


# --- fix --overrule hint ---

def test_overrule_hint_points_at_fix(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"},
          needs_review=True)
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert r.exit_code == 0, r.output
    assert "to overrule after inspecting: llama fix gratefuldead-1973-06-10 --overrule" \
        in r.output
    assert "--clear" not in r.output
