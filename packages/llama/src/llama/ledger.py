from pathlib import Path

from llama.locks import file_lock
from llama.models import LedgerEntry
from llama.workspace import atomic_write_text


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        self._lock = path.with_name(path.name + ".lock")

    def entries(self) -> list[LedgerEntry]:
        if not self.path.exists():
            return []
        return [
            LedgerEntry.model_validate_json(line)
            for line in self.path.read_text().splitlines()
            if line.strip()
        ]

    def played_ids(self) -> set[str]:
        return {e.performance_id for e in self.entries() if e.status in ("selected", "delivered")}

    def rejected_ids(self) -> set[str]:
        return {e.performance_id for e in self.entries() if e.status == "rejected"}

    def record(self, entry: LedgerEntry) -> None:
        """Append-once, serialized across processes."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(self._lock):
            for e in self.entries():            # re-read under the lock
                if (e.performance_id, e.status, e.run) == (entry.performance_id, entry.status, entry.run):
                    return
            with self.path.open("a") as f:
                f.write(entry.model_dump_json() + "\n")

    def remove(self, performance_id: str) -> int:
        with file_lock(self._lock):
            before = self.entries()
            kept = [e for e in before if e.performance_id != performance_id]
            atomic_write_text(self.path, "".join(e.model_dump_json() + "\n" for e in kept))
            return len(before) - len(kept)

    def remove_status(self, performance_id: str, status: str) -> int:
        """Remove only rows matching both performance_id and status."""
        with file_lock(self._lock):
            before = self.entries()
            kept = [e for e in before if not (e.performance_id == performance_id and e.status == status)]
            atomic_write_text(self.path, "".join(e.model_dump_json() + "\n" for e in kept))
            return len(before) - len(kept)

    def _keyed_lines(self, performance_id: str, status: str, run: str) -> tuple[list[str], list[bool]]:
        """Every raw line (newline kept) and whether it is a row of this key. Call under the lock."""
        lines = self.path.read_text().splitlines(keepends=True)
        key = (performance_id, status, run)
        hits = []
        for line in lines:
            if not line.strip():
                hits.append(False)
                continue
            e = LedgerEntry.model_validate_json(line)
            hits.append((e.performance_id, e.status, e.run) == key)
        return lines, hits

    def rows(self, performance_id: str, status: str, run: str) -> frozenset[str]:
        """The raw rows (newline stripped) of one (performance_id, status, run) key, read
        under the lock: the 'before' an undo of `remove_added` compares against."""
        if not self.path.exists():
            return frozenset()
        with file_lock(self._lock):
            if not self.path.exists():
                return frozenset()
            lines, hits = self._keyed_lines(performance_id, status, run)
            return frozenset(line.rstrip("\n") for line, hit in zip(lines, hits) if hit)

    def remove_added(self, performance_id: str, status: str, run: str, *,
                     before: frozenset[str]) -> int:
        """Remove the rows of this key that are not in `before` (from `rows`): the rows
        appended since. Every other line is kept byte-for-byte; nothing to remove writes
        nothing (a missing ledger stays missing)."""
        if not self.path.exists():
            return 0
        with file_lock(self._lock):
            if not self.path.exists():
                return 0
            lines, hits = self._keyed_lines(performance_id, status, run)
            drop = [hit and line.rstrip("\n") not in before for line, hit in zip(lines, hits)]
            if not any(drop):
                return 0
            atomic_write_text(self.path, "".join(l for l, d in zip(lines, drop) if not d))
            return sum(drop)

    def latest_dispositions(self) -> list[LedgerEntry]:
        """One entry per performance id — the latest disposition (greatest
        recorded_at; later file position breaks ties) — ascending by recorded_at."""
        latest: dict[str, LedgerEntry] = {}
        for e in self.entries():
            cur = latest.get(e.performance_id)
            if cur is None or e.recorded_at >= cur.recorded_at:
                latest[e.performance_id] = e
        return sorted(latest.values(), key=lambda e: e.recorded_at)


def is_delivered(ledger: "Ledger", performance_id: str) -> bool:
    """The ledger records the performance as delivered (one helper for `redo`,
    `fix`, triage and `reapply`)."""
    return any(e.status == "delivered" and e.performance_id == performance_id
               for e in ledger.entries())
