from pathlib import Path

from llama.ledger import Ledger
from llama.models import LedgerEntry


def entry(pid: str, status: str = "selected", recorded_at: str = "2026-07-14T00:00:00+00:00") -> LedgerEntry:
    return LedgerEntry(
        performance_id=pid, artist="Grateful Dead", date="1973-06-10",
        status=status, run="r1", recorded_at=recorded_at,
    )


def test_record_and_read(tmp_path: Path):
    led = Ledger(tmp_path / "ledger.jsonl")
    assert led.entries() == []
    led.record(entry("GratefulDead/1973-06-10"))
    led.record(entry("GratefulDead/1974-05-19", status="rejected"))
    led.record(entry("GratefulDead/1977-05-08", status="delivered"))
    assert len(led.entries()) == 3
    assert led.played_ids() == {"GratefulDead/1973-06-10", "GratefulDead/1977-05-08"}
    assert led.rejected_ids() == {"GratefulDead/1974-05-19"}


def test_remove(tmp_path: Path):
    led = Ledger(tmp_path / "ledger.jsonl")
    led.record(entry("a"))
    led.record(entry("b"))
    led.record(entry("a", status="delivered"))
    assert led.remove("a") == 2
    assert [e.performance_id for e in led.entries()] == ["b"]


def test_record_is_idempotent_per_performance_status_run(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    e = LedgerEntry(performance_id="GratefulDead/1973-06-10", artist="Grateful Dead",
                    date="1973-06-10", status="selected", run="r1",
                    recorded_at="2026-07-17T00:00:00+00:00")
    ledger.record(e)
    ledger.record(e.model_copy(update={"recorded_at": "2026-07-18T00:00:00+00:00"}))
    assert len(ledger.entries()) == 1
    # different status for the same performance still records
    ledger.record(e.model_copy(update={"status": "delivered"}))
    assert len(ledger.entries()) == 2


def test_remove_status_only_touches_that_status(tmp_path: Path):
    led = Ledger(tmp_path / "l.jsonl")
    led.record(entry("a", status="selected"))
    led.record(entry("a", status="rejected"))
    led.record(entry("b", status="rejected"))
    assert led.remove_status("a", "rejected") == 1
    assert [(e.performance_id, e.status) for e in led.entries()] == [
        ("a", "selected"), ("b", "rejected")]
    assert led.remove_status("a", "rejected") == 0   # idempotent


def test_latest_dispositions_one_row_per_pid(tmp_path: Path):
    led = Ledger(tmp_path / "l.jsonl")
    led.record(entry("a", status="selected", recorded_at="2026-07-01T00:00:00+00:00"))
    led.record(entry("a", status="delivered", recorded_at="2026-07-03T00:00:00+00:00"))
    led.record(entry("b", status="rejected", recorded_at="2026-07-02T00:00:00+00:00"))
    latest = led.latest_dispositions()
    assert [(e.performance_id, e.status) for e in latest] == [
        ("b", "rejected"), ("a", "delivered")]   # ascending recorded_at
