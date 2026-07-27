from pathlib import Path

from llama.models import LedgerEntry


class Ledger:
    def __init__(self, path: Path):
        self.path = path

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
        """Append-once: a replayed run must not duplicate history rows."""
        for e in self.entries():
            if (e.performance_id, e.status, e.run) == (entry.performance_id, entry.status, entry.run):
                return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(entry.model_dump_json() + "\n")

    def remove(self, performance_id: str) -> int:
        before = self.entries()
        kept = [e for e in before if e.performance_id != performance_id]
        tmp = self.path.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(e.model_dump_json() + "\n" for e in kept))
        tmp.replace(self.path)
        return len(before) - len(kept)

    def remove_status(self, performance_id: str, status: str) -> int:
        """Remove only rows matching both performance_id and status."""
        before = self.entries()
        kept = [e for e in before if not (e.performance_id == performance_id and e.status == status)]
        tmp = self.path.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(e.model_dump_json() + "\n" for e in kept))
        tmp.replace(self.path)
        return len(before) - len(kept)

    def latest_dispositions(self) -> list[LedgerEntry]:
        """One entry per performance id — the latest disposition (greatest
        recorded_at; later file position breaks ties) — ascending by recorded_at."""
        latest: dict[str, LedgerEntry] = {}
        for e in self.entries():
            cur = latest.get(e.performance_id)
            if cur is None or e.recorded_at >= cur.recorded_at:
                latest[e.performance_id] = e
        return sorted(latest.values(), key=lambda e: e.recorded_at)
