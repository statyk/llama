"""`llama rm`: delete a show (or a selector batch) with intentional history
handling -- wires Plan A's `catalog.remove_show` into the CLI. Plan B Task 9."""
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.errors import LlamaError
from llama.ledger import Ledger
from llama.models import LedgerEntry

from test_catalog import build

runner = CliRunner()


def _cfg(tmp_path: Path) -> str:
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path}"\n')
    return str(cfg)


# ---------------------------------------------------------------------------
# Argument-shape validation, mirroring sibling acting commands.
# ---------------------------------------------------------------------------

def test_rm_requires_a_show_or_selector(tmp_path: Path):
    cfg = _cfg(tmp_path)
    r = runner.invoke(cli.app, ["--config", cfg, "rm"])
    assert r.exit_code != 0
    assert "give a show or a selector" in r.output.lower()


def test_rm_rejects_name_and_selector_together(tmp_path: Path):
    cfg = _cfg(tmp_path)
    r = runner.invoke(cli.app, ["--config", cfg, "rm", "someshow", "--held"])
    assert r.exit_code != 0
    assert "not both" in r.output.lower()


# ---------------------------------------------------------------------------
# Single show: confirm-by-default, --yes, dispositions.
# ---------------------------------------------------------------------------

def test_rm_single_default_prompt_decline_deletes_nothing(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ws = build(tmp_path, "s", stages={"select", "gather"})
    r = runner.invoke(cli.app, ["--config", cfg, "rm", "s"], input="n\n")
    assert r.exit_code == 0, r.output
    assert "proceed" in r.output.lower()
    assert ws.dir.exists()


def test_rm_single_prompt_accept_deletes(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ws = build(tmp_path, "s", stages={"select", "gather"})
    r = runner.invoke(cli.app, ["--config", cfg, "rm", "s"], input="y\n")
    assert r.exit_code == 0, r.output
    assert not ws.dir.exists()
    assert "removed shows/s" in r.output


def test_rm_single_yes_skips_prompt_and_echoes_default_disposition(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ws = build(tmp_path, "s", stages={"select", "gather"})
    r = runner.invoke(cli.app, ["--config", cfg, "rm", "s", "--yes"])
    assert r.exit_code == 0, r.output
    assert not ws.dir.exists()
    assert "removed shows/s" in r.output
    assert "no history rows; this show can be re-offered" in r.output


def test_rm_single_forget_purges_history(tmp_path: Path):
    cfg = _cfg(tmp_path)
    pid = "GratefulDead/1973-06-10"
    ws = build(tmp_path, "s", stages={"select", "gather"}, pid=pid)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.record(LedgerEntry(performance_id=pid, artist="Grateful Dead", date="1973-06-10",
                              status="selected", run="r1",
                              recorded_at="2026-07-01T00:00:00+00:00"))
    r = runner.invoke(cli.app, ["--config", cfg, "rm", "s", "--forget", "--yes"])
    assert r.exit_code == 0, r.output
    assert not ws.dir.exists()
    assert "forgot 1 history row(s): re-eligible" in r.output
    assert Ledger(tmp_path / "ledger.jsonl").entries() == []


def test_rm_single_suppress_writes_rejected_row(tmp_path: Path):
    cfg = _cfg(tmp_path)
    pid = "GratefulDead/1973-06-10"
    ws = build(tmp_path, "s", stages={"select", "gather"}, pid=pid)
    r = runner.invoke(cli.app, ["--config", cfg, "rm", "s", "--suppress", "--yes"])
    assert r.exit_code == 0, r.output
    assert not ws.dir.exists()
    assert f"suppressed: will not be offered again (undo: llama unsuppress {pid})" in r.output
    (row,) = Ledger(tmp_path / "ledger.jsonl").entries()
    assert row.performance_id == pid and row.status == "rejected"


def test_rm_forget_and_suppress_mutually_exclusive_surfaces_from_machinery(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ws = build(tmp_path, "s", stages={"select", "gather"})
    r = runner.invoke(cli.app, ["--config", cfg, "rm", "s", "--forget", "--suppress", "--yes"])
    assert r.exit_code != 0
    assert isinstance(r.exception, LlamaError)
    assert "cannot pass both --forget and --suppress" in str(r.exception)
    assert ws.dir.exists()   # neither disposition applied; nothing deleted


# ---------------------------------------------------------------------------
# Selector batch: shared cli_select layer, held opt-in, plan/--yes.
# ---------------------------------------------------------------------------

def test_rm_batch_selector_removes_exactly_matches(tmp_path: Path):
    cfg = _cfg(tmp_path)
    sel_only = build(tmp_path, "selonly", stages={"select"})
    gathered = build(tmp_path, "gatheredshow", stages={"select", "gather"})
    r = runner.invoke(cli.app, ["--config", cfg, "rm", "--state", "selected", "--yes"])
    assert r.exit_code == 0, r.output
    assert not sel_only.dir.exists()
    assert gathered.dir.exists()


def test_rm_batch_drops_held_unless_flag(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ready = build(tmp_path, "ready", stages={"select", "gather"})
    heldshow = build(tmp_path, "heldshow", stages={"select", "gather"}, needs_review=True)

    # Without --held: a plain selector drops held shows, with a note (the
    # ACTING-command held opt-in, same as deliver/redo).
    r = runner.invoke(cli.app, ["--config", cfg, "rm", "--artist", "Grateful Dead", "--yes"])
    assert r.exit_code == 0, r.output
    assert not ready.dir.exists()
    assert heldshow.dir.exists()
    assert "held" in r.output.lower()

    # `rm --held` is the explicit junk-hold purge (spec §8.1): it targets
    # held shows (states={"held"} sugar, same narrowing already documented
    # for redo in test_redo_selector_batch_drops_held_unless_flag).
    r2 = runner.invoke(cli.app, ["--config", cfg, "rm", "--held", "--yes"])
    assert r2.exit_code == 0, r2.output
    assert not heldshow.dir.exists()


def test_rm_batch_plans_and_confirms(tmp_path: Path):
    cfg = _cfg(tmp_path)
    ready = build(tmp_path, "ready", stages={"select", "gather"})

    declined = runner.invoke(cli.app, ["--config", cfg, "rm", "--artist", "Grateful Dead"],
                             input="n\n")
    assert declined.exit_code == 0, declined.output
    assert ready.dir.exists()
    assert "ready" in declined.output

    r = runner.invoke(cli.app, ["--config", cfg, "rm", "--artist", "Grateful Dead", "--yes"])
    assert r.exit_code == 0, r.output
    assert not ready.dir.exists()


def test_rm_batch_continues_past_failure(tmp_path: Path, monkeypatch):
    import llama.catalog as catalog

    cfg = _cfg(tmp_path)
    aready = build(tmp_path, "aready", stages={"select", "gather"})
    bready = build(tmp_path, "bready", stages={"select", "gather"})

    orig = catalog.remove_show

    def fake_remove_show(entry, ledger, **kw):
        if entry.slug == "aready":
            raise LlamaError("boom")
        return orig(entry, ledger, **kw)

    monkeypatch.setattr(catalog, "remove_show", fake_remove_show)
    r = runner.invoke(cli.app, ["--config", cfg, "rm", "--state", "gathered", "--yes"])
    assert r.exit_code == 0, r.output
    assert "FAILED aready" in r.output
    assert aready.dir.exists()
    assert not bready.dir.exists()


def test_voiced_and_broadcast_ready_selectors_are_gone(tmp_path: Path):
    cfg = _cfg(tmp_path)
    for flag in ("--voiced", "--unvoiced", "--broadcast-ready"):
        r = runner.invoke(cli.app, ["--config", cfg, "rm", flag])
        assert r.exit_code != 0, flag
        assert "no such option" in r.output.lower(), (flag, r.output)
