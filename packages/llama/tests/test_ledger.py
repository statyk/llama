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


def test_remove_added_removes_only_new_rows_of_the_key(tmp_path: Path):
    led = Ledger(tmp_path / "ledger.jsonl")
    led.record(entry("a"))
    before = led.rows("a", "selected", "r2")
    assert before == frozenset()
    for e in (_keyed("a", "selected", "r2"), _keyed("a", "selected", "r3"),
              _keyed("b", "selected", "r2"), _keyed("a", "rejected", "r2")):
        led.record(e)
    assert led.remove_added("a", "selected", "r2", before=before) == 1
    assert [(e.performance_id, e.status, e.run) for e in led.entries()] == [
        ("a", "selected", "r1"), ("a", "selected", "r3"), ("b", "selected", "r2"),
        ("a", "rejected", "r2")]


def test_remove_added_keeps_rows_present_before_and_kept_bytes(tmp_path: Path):
    p = tmp_path / "ledger.jsonl"
    p.write_text('{"performance_id": "a", "artist": "x", "date": "d", "status": "selected", '
                 '"run": "r2", "recorded_at": "t0"}\n'
                 '{"performance_id": "z", "artist": "x", "date": "d", "status": "selected", '
                 '"run": "r9", "recorded_at": "t0"}\n')
    led = Ledger(p)
    before = led.rows("a", "selected", "r2")
    assert len(before) == 1
    raw = p.read_bytes()
    with p.open("a") as f:                    # a hand-appended duplicate key (not via record)
        f.write(_keyed("a", "selected", "r2").model_dump_json() + "\n")
    assert led.remove_added("a", "selected", "r2", before=before) == 1
    assert p.read_bytes() == raw              # kept rows byte-identical, never re-serialized


def test_remove_added_with_nothing_to_remove_is_a_no_op(tmp_path: Path):
    missing = Ledger(tmp_path / "none" / "ledger.jsonl")
    assert missing.rows("a", "selected", "r1") == frozenset()
    assert missing.remove_added("a", "selected", "r1", before=frozenset()) == 0
    assert not missing.path.exists()
    led = Ledger(tmp_path / "ledger.jsonl")
    led.record(entry("a"))
    ino, raw = led.path.stat().st_ino, led.path.read_bytes()
    assert led.remove_added("a", "selected", "r1", before=led.rows("a", "selected", "r1")) == 0
    assert led.remove_added("b", "selected", "r1", before=frozenset()) == 0
    assert led.path.read_bytes() == raw and led.path.stat().st_ino == ino
