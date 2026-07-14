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
