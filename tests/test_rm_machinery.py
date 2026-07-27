from datetime import datetime, timezone
from pathlib import Path

import pytest

from llama.catalog import iter_shows, remove_show
from llama.errors import LlamaError
from llama.ledger import Ledger
from llama.models import LedgerEntry
from llama.workspace import ShowWorkspace, write_artifact

from test_catalog import build


def _entry_for(tmp_path: Path, ledger: Ledger, slug: str):
    (entry,) = [e for e in iter_shows(tmp_path, ledger) if e.slug == slug]
    return entry


def test_default_disposition_no_rows(tmp_path: Path):
    build(tmp_path, "s", stages={"select", "gather"}, needs_review=True)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    entry = _entry_for(tmp_path, ledger, "s")

    lines = remove_show(entry, ledger)

    assert not entry.ws.dir.exists()
    assert ledger.entries() == []
    assert lines == ["removed shows/s", "no history rows; this show can be re-offered"]


def test_default_disposition_keeps_rows(tmp_path: Path):
    pid = "GratefulDead/1973-06-10"
    build(tmp_path, "s", stages={"select", "gather"}, pid=pid)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.record(LedgerEntry(performance_id=pid, artist="Grateful Dead", date="1973-06-10",
                              status="selected", run="r1",
                              recorded_at="2026-07-01T00:00:00+00:00"))
    ledger.record(LedgerEntry(performance_id=pid, artist="Grateful Dead", date="1973-06-10",
                              status="delivered", run="r1",
                              recorded_at="2026-07-02T00:00:00+00:00"))
    entry = _entry_for(tmp_path, ledger, "s")

    lines = remove_show(entry, ledger)

    assert not entry.ws.dir.exists()
    assert {e.status for e in ledger.entries()} == {"selected", "delivered"}
    assert lines == ["removed shows/s",
                     "history kept (delivered, selected): stays excluded from future gets"]


def test_forget_purges_only_this_pid(tmp_path: Path):
    pid = "GratefulDead/1973-06-10"
    other_pid = "Mekons/1989-12-02"
    build(tmp_path, "s", stages={"select", "gather"}, pid=pid)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.record(LedgerEntry(performance_id=pid, artist="Grateful Dead", date="1973-06-10",
                              status="selected", run="r1",
                              recorded_at="2026-07-01T00:00:00+00:00"))
    ledger.record(LedgerEntry(performance_id=pid, artist="Grateful Dead", date="1973-06-10",
                              status="delivered", run="r1",
                              recorded_at="2026-07-02T00:00:00+00:00"))
    ledger.record(LedgerEntry(performance_id=other_pid, artist="Mekons", date="1989-12-02",
                              status="selected", run="r1",
                              recorded_at="2026-07-01T00:00:00+00:00"))
    entry = _entry_for(tmp_path, ledger, "s")

    lines = remove_show(entry, ledger, forget=True)

    assert not entry.ws.dir.exists()
    remaining = ledger.entries()
    assert [e.performance_id for e in remaining] == [other_pid]
    assert lines == ["removed shows/s", "forgot 2 history row(s): re-eligible"]


def test_suppress_appends_rejected_row_from_show_json(tmp_path: Path):
    pid = "GratefulDead/1973-06-10"
    build(tmp_path, "s", stages={"select", "gather"}, pid=pid)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    entry = _entry_for(tmp_path, ledger, "s")

    lines = remove_show(entry, ledger, suppress=True)

    assert not entry.ws.dir.exists()
    (row,) = ledger.entries()
    assert row.performance_id == pid
    assert row.status == "rejected"
    assert row.run == "manual"
    assert row.artist == "Grateful Dead"
    assert row.date == "1973-06-10"
    assert lines == ["removed shows/s",
                     f"suppressed: will not be offered again (undo: llama unsuppress {pid})"]


def test_suppress_from_candidate_when_provenance_only(tmp_path: Path):
    pid = "GratefulDead/1973-06-10"
    build(tmp_path, "s", stages={"select"}, pid=pid)  # provenance only, no show.json
    ledger = Ledger(tmp_path / "ledger.jsonl")
    entry = _entry_for(tmp_path, ledger, "s")
    assert not entry.ws.show.exists()

    remove_show(entry, ledger, suppress=True)

    (row,) = ledger.entries()
    assert row.performance_id == pid
    assert row.status == "rejected"
    assert row.artist == "GratefulDead"  # candidate.collection
    assert row.date == "1973-06-10"


def test_forget_and_suppress_mutually_exclusive(tmp_path: Path):
    build(tmp_path, "s", stages={"select", "gather"})
    ledger = Ledger(tmp_path / "ledger.jsonl")
    entry = _entry_for(tmp_path, ledger, "s")

    with pytest.raises(LlamaError):
        remove_show(entry, ledger, forget=True, suppress=True)

    assert entry.ws.dir.exists()  # neither disposition applied; dir untouched


def test_pidless_dir_default_deletes_forget_raises(tmp_path: Path):
    ws = ShowWorkspace(tmp_path / "shows" / "orphan")
    write_artifact(ws.dir / "junk.txt", "not a real artifact")
    ledger = Ledger(tmp_path / "ledger.jsonl")

    from llama.catalog import CatalogEntry
    entry = CatalogEntry(slug="orphan", ws=ws, state="selected")

    lines = remove_show(entry, ledger)
    assert not ws.dir.exists()
    assert lines == ["removed shows/orphan", "no history rows; this show can be re-offered"]

    ws2 = ShowWorkspace(tmp_path / "shows" / "orphan2")
    write_artifact(ws2.dir / "junk.txt", "not a real artifact")
    entry2 = CatalogEntry(slug="orphan2", ws=ws2, state="selected")
    with pytest.raises(LlamaError, match="cannot resolve a performance id"):
        remove_show(entry2, ledger, forget=True)
    assert ws2.dir.exists()
