"""`llama status`: shared cli_select selectors, session attention-list,
`--by-run` (absorbing the deleted `runs` command), and the `--json` object
shape `{"sessions": [...], "shows": [...]}` (or `{"sessions", "runs"}` with
`--by-run`). Plan B Task 5."""
import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.models import Criteria, Overrides
from llama.sessions import STATE_AWAITING, STATE_COMPLETE, mark_awaiting, mark_complete
from llama.workspace import RunWorkspace, write_artifact

from test_cli_commands import _seed_show

runner = CliRunner()


def _cfg(tmp_path: Path) -> str:
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    return str(tmp_path / "config.toml")


def _session(tmp_path, name, *, state=None, query="q", profile=None):
    ws = RunWorkspace(tmp_path, name)
    write_artifact(ws.criteria, Criteria(query=query, profile=profile))
    if state == STATE_AWAITING:
        mark_awaiting(ws)
    elif state == STATE_COMPLETE:
        mark_complete(ws, "done")
    return ws


# --- ported/rewritten `status` show-table tests (were in test_cli_commands.py) ---

def test_status_orders_held_first_and_filters(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "r1", delivered=True)
    _seed_show(tmp_path, "bbb-1971-01-01", "bbb/1971-01-01", "r1", held=True)
    _seed_show(tmp_path, "ccc-1972-01-01", "ccc/1972-01-01", "r2")

    result = runner.invoke(cli.app, ["--config", cfg, "status"])
    assert result.exit_code == 0, result.output
    lines = [ln for ln in result.output.splitlines() if ln.strip()]
    rows = [ln for ln in lines if not ln.startswith("      ")]  # drop flag detail lines
    assert rows[0].startswith("bbb-1971-01-01")       # held first
    assert "two sets missing" in result.output
    assert "packaged" in rows[1]                       # ccc next
    assert "delivered" in rows[-1]                     # aaa last

    held_only = runner.invoke(cli.app, ["--config", cfg, "status", "--held"])
    assert "bbb-1971-01-01" in held_only.output
    assert "ccc-1972-01-01" not in held_only.output

    # sugar ≡ enum: --held and --state held select the same rows
    held_via_state = runner.invoke(cli.app, ["--config", cfg, "status", "--state", "held"])
    assert held_via_state.output == held_only.output

    by_run = runner.invoke(cli.app, ["--config", cfg, "status", "--run", "r2"])
    assert "ccc-1972-01-01" in by_run.output
    assert "bbb-1971-01-01" not in by_run.output


def test_status_recent_delivered_keeps_most_recent_not_slug_order(tmp_path: Path):
    """The 5-show trim must keep the most recently delivered shows, not the
    alphabetically-last slugs. Seed 7 delivered shows where recency and slug
    order disagree: "a" and "b" sort first but were delivered most recently;
    "f" and "g" sort last but were delivered longest ago."""
    cfg = _cfg(tmp_path)
    letters = ["a", "b", "c", "d", "e", "f", "g"]
    for i, letter in enumerate(letters):
        hour = 7 - i
        _seed_show(tmp_path, f"{letter}-1970-01-01", f"{letter}/1970-01-01", "r1",
                  delivered=True, recorded_at=f"2026-07-17T{hour:02d}:00:00+00:00")

    result = runner.invoke(cli.app, ["--config", cfg, "status"])
    assert result.exit_code == 0, result.output

    for letter in ["a", "b", "c", "d", "e"]:
        assert f"{letter}-1970-01-01" in result.output, result.output
    for letter in ["f", "g"]:
        assert f"{letter}-1970-01-01" not in result.output, result.output


def test_status_voiced_and_unvoiced_filters(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _seed_show(tmp_path, "silent-1970-01-01", "silent/1970-01-01", "r1", packaged=True)
    voiced_ws = _seed_show(tmp_path, "voiced-1971-01-01", "voiced/1971-01-01", "r1", packaged=True)
    write_artifact(voiced_ws.package_dir / "manifest.json",
                   {"schema_version": 2, "dj_audio": {"set_intros": {}, "outro": "o"}})

    unvoiced = runner.invoke(cli.app, ["--config", cfg, "status", "--unvoiced"])
    assert unvoiced.exit_code == 0, unvoiced.output
    assert "silent-1970-01-01" in unvoiced.output
    assert "voiced-1971-01-01" not in unvoiced.output

    voiced = runner.invoke(cli.app, ["--config", cfg, "status", "--voiced"])
    assert voiced.exit_code == 0, voiced.output
    assert "voiced-1971-01-01" in voiced.output
    assert "silent-1970-01-01" not in voiced.output
    assert "[voiced]" in voiced.output


def test_status_text_row_annotation(tmp_path: Path):
    cfg = _cfg(tmp_path)
    sws = _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "r1", packaged=True)
    write_artifact(sws.overrides, Overrides(exclude=["a.mp3", "b.mp3"], narration="vague"))

    result = runner.invoke(cli.app, ["--config", cfg, "status"])
    assert result.exit_code == 0, result.output
    assert "[vague, 2x-excl]" in result.output


def test_status_state_filter(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "r1", packaged=False)
    _seed_show(tmp_path, "bbb-1971-01-01", "bbb/1971-01-01", "r1", packaged=True)

    result = runner.invoke(cli.app, ["--config", cfg, "status", "--state", "gathered"])
    assert result.exit_code == 0, result.output
    assert "aaa-1970-01-01" in result.output
    assert "bbb-1971-01-01" not in result.output


def test_status_state_filter_accepts_briefed(tmp_path: Path):
    from test_catalog import build

    cfg = _cfg(tmp_path)
    build(tmp_path, "briefed-1972-01-01", stages={"select", "gather", "research", "vet", "brief"},
          pid="briefed/1972-01-01")
    _seed_show(tmp_path, "bbb-1971-01-01", "bbb/1971-01-01", "r1", packaged=True)

    result = runner.invoke(cli.app, ["--config", cfg, "status", "--state", "briefed"])
    assert result.exit_code == 0, result.output
    assert "briefed-1972-01-01" in result.output
    assert "bbb-1971-01-01" not in result.output


def test_status_json_has_voiced_and_overrides(tmp_path: Path):
    cfg = _cfg(tmp_path)
    sws = _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "r1", packaged=False)
    write_artifact(sws.overrides, Overrides(exclude=["a.mp3"], narration="vague"))

    result = runner.invoke(cli.app, ["--config", cfg, "status", "--json"])
    assert result.exit_code == 0, result.output
    obj = json.loads(result.output)
    row = next(r for r in obj["shows"] if r["slug"] == "aaa-1970-01-01")
    assert row["voiced"] is None
    assert row["overrides"] == {"exclude": ["a.mp3"], "narration": "vague"}


# --- `--state` as a validated, repeatable `ShowState` enum ---

def test_status_state_enum_rejects_typo_listing_legal_values(tmp_path: Path):
    cfg = _cfg(tmp_path)
    result = runner.invoke(cli.app, ["--config", cfg, "status", "--state", "bogus"])
    assert result.exit_code != 0
    assert "not one of" in result.output
    for legal in ["held", "packaged", "delivered"]:
        assert legal in result.output


def test_status_state_repeatable_ors(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _seed_show(tmp_path, "held-1970-01-01", "held/1970-01-01", "r1", held=True)
    _seed_show(tmp_path, "pkg-1971-01-01", "pkg/1971-01-01", "r1", packaged=True)
    _seed_show(tmp_path, "gathered-1972-01-01", "gathered/1972-01-01", "r1", packaged=False)

    result = runner.invoke(cli.app, ["--config", cfg, "status",
                                     "--state", "held", "--state", "packaged"])
    assert result.exit_code == 0, result.output
    assert "held-1970-01-01" in result.output
    assert "pkg-1971-01-01" in result.output
    assert "gathered-1972-01-01" not in result.output


# --- session attention-list ---

def test_status_attention_header_present_with_awaiting_and_incomplete(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _session(tmp_path, "2026-07-27-a-awaiting", state=STATE_AWAITING)
    _session(tmp_path, "2026-07-27-b-crashed")   # no marker -> incomplete

    result = runner.invoke(cli.app, ["--config", cfg, "status"])
    assert result.exit_code == 0, result.output
    assert "sessions needing attention:" in result.output
    assert "2026-07-27-a-awaiting" in result.output
    assert "awaiting approval" in result.output
    assert "llama run approve 2026-07-27-a-awaiting" in result.output
    assert "2026-07-27-b-crashed" in result.output
    assert "incomplete" in result.output
    assert "llama run resume 2026-07-27-b-crashed" in result.output


def test_status_attention_header_absent_when_all_complete(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _session(tmp_path, "2026-07-27-done", state=STATE_COMPLETE)

    result = runner.invoke(cli.app, ["--config", cfg, "status"])
    assert result.exit_code == 0, result.output
    assert "sessions needing attention:" not in result.output


def test_status_attention_header_absent_when_no_sessions(tmp_path: Path):
    cfg = _cfg(tmp_path)
    result = runner.invoke(cli.app, ["--config", cfg, "status"])
    assert result.exit_code == 0, result.output
    assert "sessions needing attention:" not in result.output


# --- `--by-run` (absorbs the deleted `runs` command) ---

def test_status_by_run_rollup_matches_old_runs_content(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ws = RunWorkspace(tmp_path, "2026-07-16-countryish")
    write_artifact(ws.criteria, Criteria(query="countryish bluegrass"))
    _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "2026-07-16-countryish")
    _seed_show(tmp_path, "bbb-1971-01-01", "bbb/1971-01-01", "2026-07-16-countryish",
               held=True)

    result = runner.invoke(cli.app, ["--config", cfg, "status", "--by-run"])
    assert result.exit_code == 0, result.output
    assert "2026-07-16-countryish" in result.output
    assert "countryish bluegrass" in result.output
    assert "held 1" in result.output and "packaged 1" in result.output


def test_status_by_run_no_runs(tmp_path: Path):
    cfg = _cfg(tmp_path)
    result = runner.invoke(cli.app, ["--config", cfg, "status", "--by-run"])
    assert result.exit_code == 0, result.output
    assert "no runs" in result.output


def test_status_by_run_rejects_selector_flags(tmp_path: Path):
    cfg = _cfg(tmp_path)
    result = runner.invoke(cli.app, ["--config", cfg, "status", "--by-run", "--held"])
    assert result.exit_code != 0
    assert "--by-run" in result.output


def test_status_by_run_rejects_all(tmp_path: Path):
    cfg = _cfg(tmp_path)
    result = runner.invoke(cli.app, ["--config", cfg, "status", "--by-run", "--all"])
    assert result.exit_code != 0
    assert "--by-run" in result.output


def test_status_by_run_shows_attention_header_too(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _session(tmp_path, "2026-07-27-a-awaiting", state=STATE_AWAITING)

    result = runner.invoke(cli.app, ["--config", cfg, "status", "--by-run"])
    assert result.exit_code == 0, result.output
    assert "sessions needing attention:" in result.output


# --- `--json` object shape ---

def test_status_json_object_shape(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "r1")
    _session(tmp_path, "2026-07-27-a-awaiting", state=STATE_AWAITING)
    _session(tmp_path, "2026-07-27-b-done", state=STATE_COMPLETE)

    result = runner.invoke(cli.app, ["--config", cfg, "status", "--json"])
    assert result.exit_code == 0, result.output
    obj = json.loads(result.output)
    assert set(obj.keys()) == {"sessions", "shows"}

    assert [s["id"] for s in obj["sessions"]] == ["2026-07-27-a-awaiting"]
    session = obj["sessions"][0]
    assert set(session.keys()) == {"id", "state", "updated_at", "query", "profile"}
    assert session["state"] == STATE_AWAITING

    assert obj["shows"][0]["slug"] == "aaa-1970-01-01"
    assert obj["shows"][0]["state"] == "packaged"
    assert obj["shows"][0]["run"] == "r1"


def test_status_json_by_run_shape(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ws = RunWorkspace(tmp_path, "2026-07-16-countryish")
    write_artifact(ws.criteria, Criteria(query="countryish bluegrass"))
    _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "2026-07-16-countryish")

    result = runner.invoke(cli.app, ["--config", cfg, "status", "--by-run", "--json"])
    assert result.exit_code == 0, result.output
    obj = json.loads(result.output)
    assert set(obj.keys()) == {"sessions", "runs"}
    row = next(r for r in obj["runs"] if r["id"] == "2026-07-16-countryish")
    assert row["query"] == "countryish bluegrass"
    assert row["states"] == {"packaged": 1}


# --- `runs` command is gone ---

def test_runs_command_is_gone(tmp_path: Path):
    cfg = _cfg(tmp_path)
    result = runner.invoke(cli.app, ["--config", cfg, "runs"])
    assert result.exit_code != 0
    assert "No such command" in result.output
