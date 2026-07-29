import multiprocessing as mp
from pathlib import Path

from llama.ledger import Ledger
from llama.models import LedgerEntry

CTX = mp.get_context("fork")


def _entry(pid, run):
    return LedgerEntry(performance_id=pid, artist="A", date="1973-06-10",
                       venue="V", status="selected", run=run,
                       recorded_at="2026-07-28T00:00:00Z")


def _record(path, pid, run, start):
    start.wait(5)
    Ledger(Path(path)).record(_entry(pid, run))


def test_concurrent_record_no_loss_no_dup(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    start = CTX.Event()
    # 8 distinct rows + 4 duplicate attempts of one existing row.
    specs = [(f"p{i}", "r") for i in range(8)] + [("p0", "r")] * 4
    procs = [CTX.Process(target=_record, args=(str(path), pid, run, start))
             for pid, run in specs]
    for p in procs:
        p.start()
    start.set()
    for p in procs:
        p.join(5)
    entries = Ledger(path).entries()
    keys = {(e.performance_id, e.status, e.run) for e in entries}
    assert len(keys) == 8              # no losses
    assert len(entries) == 8           # no duplicates despite the 4 dup attempts
