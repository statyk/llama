from pathlib import Path

from llama.ledger import Ledger
from llama.models import LedgerEntry


def entry(pid: str, status: str = "selected") -> LedgerEntry:
    return LedgerEntry(
        performance_id=pid, artist="Grateful Dead", date="1973-06-10",
        status=status, run="r1", recorded_at="2026-07-14T00:00:00+00:00",
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
