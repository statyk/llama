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


def _keyed(pid, status, run):
    return LedgerEntry(performance_id=pid, artist="Grateful Dead", date="1973-06-10",
                       status=status, run=run, recorded_at="2026-11-07T00:00:00+00:00")


def _spaced(pid, status, run):
    """A row as json.dumps writes it (spaces after separators): not model_dump_json's bytes."""
    import json
    return json.dumps({"performance_id": pid, "artist": "x", "date": "d", "status": status,
                       "run": run, "recorded_at": "t0"}) + "\n"


def test_has_row_reads_the_parsed_key(tmp_path: Path):
    led = Ledger(tmp_path / "none" / "ledger.jsonl")
    assert led.has_row("a", "selected", "r1") is False
    assert not led.path.exists()
    led = Ledger(tmp_path / "ledger.jsonl")
    led.path.write_text(_spaced("a", "selected", "r2") + "\n" + _spaced("b", "rejected", "r1"))
    assert led.has_row("a", "selected", "r2") is True
    assert led.has_row("a", "selected", "r1") is False
    assert led.has_row("a", "rejected", "r2") is False
    assert led.has_row("b", "rejected", "r1") is True


def test_remove_added_removes_every_row_of_the_key_compared_parsed(tmp_path: Path):
    p = tmp_path / "ledger.jsonl"
    kept = [_spaced("a", "selected", "r1"), _spaced("a", "rejected", "r2"),
            _spaced("b", "selected", "r2"), _spaced("a", "selected", "r3")]
    p.write_text(kept[0] + _spaced("a", "selected", "r2") + kept[1] + "\n" + kept[2]
                 + _keyed("a", "selected", "r2").model_dump_json() + "\n" + kept[3])
    led = Ledger(p)
    assert led.remove_added("a", "selected", "r2") == 2        # both spellings of the key
    assert p.read_text() == kept[0] + kept[1] + "\n" + kept[2] + kept[3]   # raw, blank kept


def test_remove_added_with_nothing_to_remove_is_a_no_op(tmp_path: Path):
    missing = Ledger(tmp_path / "none" / "ledger.jsonl")
    assert missing.remove_added("a", "selected", "r1") == 0
    assert not missing.path.exists()
    led = Ledger(tmp_path / "ledger.jsonl")
    led.record(entry("a"))
    ino, raw = led.path.stat().st_ino, led.path.read_bytes()
    assert led.remove_added("a", "selected", "r2") == 0
    assert led.remove_added("b", "selected", "r1") == 0
    assert led.path.read_bytes() == raw and led.path.stat().st_ino == ino
