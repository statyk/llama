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
from llama.workspace import ShowWorkspace, read_model, write_artifact

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
    # These tracks all default to matched=None ("not measured"), which now
    # trips the "- = not measured" legend line appended after every track
    # row -- slice to just the N track rows so that legend line (unrelated
    # to title_source truncation) doesn't join the per-row checks below.
    lines = _format_tracks(
        SimpleNamespace(tracks=tracks, excluded_files=[]))[1:1 + len(tracks)]
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


# --- overrides display (text mode) ---

def test_encore_after_shown_in_text_mode(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    write_artifact(ws.overrides, {"encore_after": 16})
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert r.exit_code == 0, r.output
    assert "encore_after=16" in r.output


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
        "exclude": ["junk.mp3"], "include": [], "narration": "vague", "venue": "My Hall",
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


# --- overrides.include: the excluded listing, the `+` marker, the dropped count ---

def _show_with_excluded(tmp_path: Path):
    """A gathered show whose show.json carries two junk-filtered files and one
    re-admitted track."""
    from llama.models import Show, Track

    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    s = read_model(ws.show, Show)
    s.tracks = [
        Track(index=1, set="1", title="Introduction", filename="intro.mp3",
              title_source="override", duration_sec=37.0, included=True),
        Track(index=2, set="1", title="Morning Dew", filename="a.mp3",
              title_source="tags", duration_sec=300.0),
    ]
    s.excluded_files = [
        {"filename": "spam.mp3", "reasons": ["filename convention mismatch"],
         "duration_sec": 72.0},
        {"filename": "tuning.mp3", "reasons": ["implausibly short"],
         "duration_sec": 12.0},
    ]
    write_artifact(ws.show, s)
    return ws


def test_excluded_handles_number_from_one_in_show_json_order():
    from llama.cli import _excluded_handles

    class _S:
        excluded_files = [{"filename": "a.mp3"}, {"filename": "b.mp3"}]

    assert [(h, e["filename"]) for h, e in _excluded_handles(_S())] == [
        ("x1", "a.mp3"), ("x2", "b.mp3")]


def test_tracks_listing_shows_the_excluded_section(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    r = cli_invoke(cfg, "show", "gratefuldead", "--tracks")
    assert r.exit_code == 0, r.output
    assert "excluded (2):" in r.output
    spam = next(ln for ln in r.output.splitlines() if "spam.mp3" in ln)
    tuning = next(ln for ln in r.output.splitlines() if "tuning.mp3" in ln)
    assert spam.split() == ["x1", "spam.mp3", "1:12", "filename", "convention", "mismatch"]
    assert tuning.split() == ["x2", "tuning.mp3", "0:12", "implausibly", "short"]
    # the filename column is padded to the widest name, so the durations line up
    assert spam.index("1:12") == tuning.index("0:12")
    assert "llama fix <show> --include x1" in r.output


def test_excluded_section_survives_a_show_json_written_before_duration_sec(tmp_path: Path):
    """Pre-feature show.json entries have no `duration_sec` key at all. The
    listing must render them, not raise KeyError -- `e.get`, never `e[...]`."""
    from llama.models import Show

    cfg = _cfg(tmp_path)
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    s = read_model(ws.show, Show)
    s.excluded_files = [{"filename": "old.mp3", "reasons": ["spam"]}]
    write_artifact(ws.show, s)
    r = cli_invoke(cfg, "show", "gratefuldead", "--tracks")
    assert r.exit_code == 0, r.output
    assert next(ln for ln in r.output.splitlines() if "old.mp3" in ln).split() == [
        "x1", "old.mp3", "?", "spam"]


def test_no_excluded_section_when_nothing_was_filtered(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    r = cli_invoke(cfg, "show", "gratefuldead", "--tracks")
    assert r.exit_code == 0, r.output
    # NOT `"excluded" not in r.output`: `show` prints `path:`, and pytest's
    # tmp_path embeds the test's own NAME -- so a whole-output substring check
    # here is really asserting against the directory name, and would flip
    # meaning if the test were renamed. Scope every negative to a line.
    assert "tracks:" in r.output          # the listing really rendered
    assert not any(ln.startswith("excluded (") for ln in r.output.splitlines())
    assert "--include" not in r.output


def test_tracks_listing_marks_a_re_admitted_track(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    r = cli_invoke(cfg, "show", "gratefuldead", "--tracks")
    assert r.exit_code == 0, r.output
    assert "+ = re-admitted by operator" in r.output
    intro = next(ln for ln in r.output.splitlines() if "intro.mp3" in ln)
    dew = next(ln for ln in r.output.splitlines() if "Morning Dew" in ln)
    # whole-prefix checks, not `"1.+" in intro`: the marker occupies its own
    # fixed column, so an un-marked row must carry a SPACE there. A bare
    # substring pair would pass against a mutation that marks every row only
    # by luck of the negative half's digit.
    assert intro.startswith("   1.+ set "), intro
    assert dew.startswith("   2.  set "), dew


def test_no_re_admitted_legend_when_no_track_was_re_admitted(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    r = cli_invoke(cfg, "show", "gratefuldead", "--tracks")
    assert r.exit_code == 0, r.output
    assert not any(ln.startswith("  + = ") for ln in r.output.splitlines())


def test_dropped_count_shows_without_the_tracks_flag(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert r.exit_code == 0, r.output
    assert "(2 tracks, 2 dropped)" in r.output
    assert "excluded (2):" not in r.output


def test_no_dropped_clause_when_nothing_was_dropped(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert r.exit_code == 0, r.output
    # Pinned as the WHOLE recording line, not `"dropped" not in r.output`:
    # the `path:` line carries pytest's tmp_path, which embeds this test's own
    # name -- so the whole-output form asserts against the directory name. An
    # exact line also catches the unconditional-clause mutation, which emits
    # ", 0 dropped".
    line = next(ln for ln in r.output.splitlines() if ln.startswith("recording:"))
    assert line == "recording: gd73  (1 tracks)"


def test_overrides_line_and_json_carry_include(tmp_path: Path):
    from llama.models import Overrides

    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    write_artifact(ws.overrides, Overrides(include=["intro.mp3"]))
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert r.exit_code == 0, r.output
    assert "include=['intro.mp3']" in r.output
    r = cli_invoke(cfg, "show", "gratefuldead", "--json", "--tracks")
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["overrides"]["include"] == ["intro.mp3"]
    assert [e["filename"] for e in data["excluded"]] == ["spam.mp3", "tuning.mp3"]
    assert data["tracks"][0]["included"] is True
    assert data["tracks"][1]["included"] is False


def test_json_omits_excluded_without_the_tracks_flag(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    r = cli_invoke(cfg, "show", "gratefuldead", "--json")
    assert r.exit_code == 0, r.output
    assert "excluded" not in json.loads(r.output)
