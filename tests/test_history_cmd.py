"""`llama suppress`/`llama unsuppress` (reversible rejected-row dispositions,
on-disk or a raw performance id) plus the `ledger` -> `history` namespace
rename (list-only: collapsed-by-default, `--log` for the full trail).
Plan B Task 10 -- `ledger add`/`ledger remove` are deleted; their real
intents are now `suppress`/`unsuppress`/`rm --forget`."""
import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.catalog import CatalogError
from llama.ledger import Ledger
from llama.models import LedgerEntry

from test_catalog import build

runner = CliRunner()


def _cfg(tmp_path: Path) -> str:
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path}"\n')
    return str(cfg)


def _fmt(e: LedgerEntry) -> str:
    return f"{e.recorded_at[:10]}  {e.status:9s}  {e.performance_id}  ({e.run})\n"


# ---------------------------------------------------------------------------
# suppress
# ---------------------------------------------------------------------------

def test_suppress_on_disk_writes_rejected_row_from_show_metadata(tmp_path: Path):
    cfg = _cfg(tmp_path)
    pid = "GratefulDead/1973-06-10"
    build(tmp_path, "s", stages={"select", "gather"}, pid=pid)
    r = runner.invoke(cli.app, ["--config", cfg, "suppress", "s"])
    assert r.exit_code == 0, r.output
    assert f"suppressed: {pid}" in r.output
    (row,) = Ledger(tmp_path / "ledger.jsonl").entries()
    assert row.performance_id == pid
    assert row.status == "rejected"
    assert row.run == "manual"
    assert row.artist == "Grateful Dead"   # from show.json, not the raw collection id
    assert row.date == "1973-06-10"


def test_suppress_off_disk_accepts_a_raw_performance_id(tmp_path: Path):
    cfg = _cfg(tmp_path)
    pid = "GratefulDead/1980-05-16"
    r = runner.invoke(cli.app, ["--config", cfg, "suppress", pid])
    assert r.exit_code == 0, r.output
    assert f"suppressed: {pid}" in r.output
    (row,) = Ledger(tmp_path / "ledger.jsonl").entries()
    assert row.performance_id == pid
    assert row.status == "rejected"
    assert row.artist == "GratefulDead"
    assert row.date == "1980-05-16"


def test_suppress_off_disk_early_late_id_also_parses(tmp_path: Path):
    cfg = _cfg(tmp_path)
    pid = "GratefulDead/1966-07-16/e2"
    r = runner.invoke(cli.app, ["--config", cfg, "suppress", pid])
    assert r.exit_code == 0, r.output
    (row,) = Ledger(tmp_path / "ledger.jsonl").entries()
    assert row.performance_id == pid
    assert row.date == "1966-07-16"


def test_suppress_rejects_a_name_that_is_neither_a_show_nor_a_performance_id(tmp_path: Path):
    cfg = _cfg(tmp_path)
    r = runner.invoke(cli.app, ["--config", cfg, "suppress", "not-a-pid"])
    assert r.exit_code != 0
    assert isinstance(r.exception, CatalogError)
    assert Ledger(tmp_path / "ledger.jsonl").entries() == []


# ---------------------------------------------------------------------------
# unsuppress
# ---------------------------------------------------------------------------

def test_suppress_then_unsuppress_round_trip_leaves_other_statuses_intact(tmp_path: Path):
    cfg = _cfg(tmp_path)
    pid = "GratefulDead/1973-06-10"
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.record(LedgerEntry(performance_id=pid, artist="Grateful Dead", date="1973-06-10",
                              status="delivered", run="r1",
                              recorded_at="2026-07-01T00:00:00+00:00"))

    r = runner.invoke(cli.app, ["--config", cfg, "suppress", pid])
    assert r.exit_code == 0, r.output
    statuses = sorted(e.status for e in Ledger(tmp_path / "ledger.jsonl").entries())
    assert statuses == ["delivered", "rejected"]

    r2 = runner.invoke(cli.app, ["--config", cfg, "unsuppress", pid])
    assert r2.exit_code == 0, r2.output
    assert f"removed 1 rejected row(s) for {pid}" in r2.output
    rows = Ledger(tmp_path / "ledger.jsonl").entries()
    assert [e.status for e in rows] == ["delivered"]   # the other status untouched


def test_unsuppress_on_disk_show_resolves_metadata_too(tmp_path: Path):
    cfg = _cfg(tmp_path)
    pid = "GratefulDead/1973-06-10"
    build(tmp_path, "s", stages={"select", "gather"}, pid=pid)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.record(LedgerEntry(performance_id=pid, artist="Grateful Dead", date="1973-06-10",
                              status="rejected", run="manual",
                              recorded_at="2026-07-01T00:00:00+00:00"))
    r = runner.invoke(cli.app, ["--config", cfg, "unsuppress", "s"])
    assert r.exit_code == 0, r.output
    assert f"removed 1 rejected row(s) for {pid}" in r.output
    assert Ledger(tmp_path / "ledger.jsonl").entries() == []


def test_unsuppress_nothing_to_remove_is_a_clean_noop(tmp_path: Path):
    cfg = _cfg(tmp_path)
    pid = "GratefulDead/1980-05-16"
    r = runner.invoke(cli.app, ["--config", cfg, "unsuppress", pid])
    assert r.exit_code == 0, r.output
    assert f"removed 0 rejected row(s) for {pid}" in r.output


def test_unsuppress_rejects_a_name_that_is_neither_a_show_nor_a_performance_id(tmp_path: Path):
    cfg = _cfg(tmp_path)
    r = runner.invoke(cli.app, ["--config", cfg, "unsuppress", "not-a-pid"])
    assert r.exit_code != 0
    assert isinstance(r.exception, CatalogError)


# ---------------------------------------------------------------------------
# history (renamed from ledger; list-only, collapsed default + --log/--json)
# ---------------------------------------------------------------------------

def _seed_ledger(tmp_path: Path) -> Ledger:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.record(LedgerEntry(performance_id="a", artist="Grateful Dead", date="1973-06-10",
                              status="selected", run="r1",
                              recorded_at="2026-07-01T00:00:00+00:00"))
    ledger.record(LedgerEntry(performance_id="a", artist="Grateful Dead", date="1973-06-10",
                              status="delivered", run="r1",
                              recorded_at="2026-07-03T00:00:00+00:00"))
    ledger.record(LedgerEntry(performance_id="b", artist="Grateful Dead", date="1974-05-19",
                              status="rejected", run="r2",
                              recorded_at="2026-07-02T00:00:00+00:00"))
    return ledger


def test_history_list_collapses_to_one_row_per_performance(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ledger = _seed_ledger(tmp_path)
    r = runner.invoke(cli.app, ["--config", cfg, "history", "list"])
    assert r.exit_code == 0, r.output
    expected = "".join(_fmt(e) for e in ledger.latest_dispositions())
    assert r.output == expected
    assert "selected" not in r.output   # superseded row for "a" is not shown


def test_history_list_log_shows_the_full_trail(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ledger = _seed_ledger(tmp_path)
    r = runner.invoke(cli.app, ["--config", cfg, "history", "list", "--log"])
    assert r.exit_code == 0, r.output
    expected = "".join(_fmt(e) for e in ledger.entries())
    assert r.output == expected
    assert "selected" in r.output
    assert len(ledger.entries()) == 3


def test_history_list_json_collapsed(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ledger = _seed_ledger(tmp_path)
    r = runner.invoke(cli.app, ["--config", cfg, "history", "list", "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == [
        {"performance_id": e.performance_id, "status": e.status,
         "run": e.run, "recorded_at": e.recorded_at}
        for e in ledger.latest_dispositions()
    ]


def test_history_list_json_log(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ledger = _seed_ledger(tmp_path)
    r = runner.invoke(cli.app, ["--config", cfg, "history", "list", "--log", "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output) == [
        {"performance_id": e.performance_id, "status": e.status,
         "run": e.run, "recorded_at": e.recorded_at}
        for e in ledger.entries()
    ]


# ---------------------------------------------------------------------------
# `ledger` is gone entirely (add/remove/list, and the namespace itself)
# ---------------------------------------------------------------------------

def test_ledger_namespace_no_longer_exists(tmp_path: Path):
    cfg = _cfg(tmp_path)
    r = runner.invoke(cli.app, ["--config", cfg, "ledger", "list"])
    assert r.exit_code != 0
    assert "no such command" in r.output.lower()


def test_ledger_add_no_longer_exists(tmp_path: Path):
    cfg = _cfg(tmp_path)
    r = runner.invoke(cli.app, ["--config", cfg, "ledger", "add", "x",
                                "--artist", "a", "--date", "2026-01-01"])
    assert r.exit_code != 0


def test_ledger_remove_no_longer_exists(tmp_path: Path):
    cfg = _cfg(tmp_path)
    r = runner.invoke(cli.app, ["--config", cfg, "ledger", "remove", "x"])
    assert r.exit_code != 0
