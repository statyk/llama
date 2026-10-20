"""`llama reapply`: re-process a held show with exactly the replay harness's
computation, in place (held-backlog spec slice 6).

`compute_legs` + `classify` (llama.replay) decide everything; this module only
maps `classify`'s outcome and writes the result. Under the per-show lock, from
the still-held check through the last write, it writes `vetting.json`,
`notes.json`, the briefing, the package and, last, `show.json`: the commit
marker. Until `show.json` is rewritten the show is still held, so a failure
part-way leaves it on every held list and a re-run completes it.
`reviews.json`, `provenance.json`, `research.md` and the ledger are never
written.
"""
import dataclasses
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from llama.catalog import CatalogEntry
from llama.config import Config
from llama.errors import LlamaError
from llama.ledger import Ledger
from llama.locks import file_lock
from llama.models import Provenance, Show, ShowNotes
from llama.replay import CacheOnlyIA, classify, compute_legs, input_digests, setlistfm_client
from llama.stages.brief import generate_briefing, render_briefing_md
from llama.stages.package import build_package
from llama.workspace import (drop_stage_artifacts, read_json, read_model, read_overrides,
                             write_artifact)

# classify's held-show outcomes -> the dry-run prediction (`needs-llm` stops
# before the dry-run check, like the apply).
_PREDICTED = {
    "clears": "cleared",
    "needs-brief": "needs-brief",
    "structure-changed": "structure-changed",
    "still-held": "held",
    "still-held-package": "held",
}


@dataclasses.dataclass
class ReapplyOutcome:
    slug: str
    # "cleared" | "held" | "needs-llm" | "skipped: not held" |
    # "skipped: inputs changed" | "dry-run: <predicted>"
    outcome: str
    briefing: str                  # "reuse" | "fresh" | "none"
    flags: list[str]
    delivered: bool                # the ledger records the performance as delivered
    written: list[str]             # artifact names, in write order


def _delivered(ledger: Ledger, performance_id: str) -> bool:
    return any(e.status == "delivered" and e.performance_id == performance_id
               for e in ledger.entries())


def reapply_show(config: Config, ia, ledger: Ledger, entry: CatalogEntry, *,
                 providers: dict, row: dict | None, dry_run: bool,
                 echo: Callable[[str], None]) -> ReapplyOutcome:
    """Reapply one held show (spec slice 6). `ia` is the real archive.org
    client and is used ONLY by `build_package`; the replay itself reads the
    cache through `CacheOnlyIA`. `row` is the show's predicted-list row (its
    `digests` must still match), or None for a show named on the command
    line. The only LLM call is one fresh brief (`providers["brief"]`), made
    before anything is written, so a refusal there writes nothing."""
    ws, slug = entry.ws, entry.slug
    with file_lock(ws.lock):
        if not ws.show.exists():
            raise LlamaError(f"cannot reapply {slug}: missing show.json")
        stored = read_model(ws.show, Show)
        delivered = _delivered(ledger, stored.performance_id)
        if not stored.needs_review:
            return ReapplyOutcome(slug, "skipped: not held", "none", [], delivered, [])
        if row is not None and input_digests(ws) != row["digests"]:
            return ReapplyOutcome(slug, "skipped: inputs changed", "none", [], delivered, [])

        scratch = Path(tempfile.mkdtemp(prefix="llama-reapply-"))
        try:
            legs = compute_legs(ws, config=config, ia=CacheOnlyIA(config.root / "cache"),
                                slfm=setlistfm_client(config), scratch=scratch / "show")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

        outcome, _would_be = classify(legs, "held")
        if outcome == "needs-llm":
            return ReapplyOutcome(slug, "needs-llm", legs.brief, list(legs.flags), delivered, [])
        if outcome not in _PREDICTED:
            raise LlamaError(f"cannot reapply {slug}: unexpected replay outcome {outcome!r}")
        if dry_run:
            return ReapplyOutcome(slug, f"dry-run: {_PREDICTED[outcome]}", legs.brief,
                                  list(legs.flags), delivered, [])

        # In memory first: the fresh brief (the one LLM call) runs before any write.
        # legs.flags = gather + vet + carried package flags + brief_flags; the
        # replayed show's own review_flags lack the carried ones.
        flags = list(legs.flags)
        profile = read_model(ws.provenance, Provenance).profile
        final_show = legs.replayed_show.model_copy(
            update={"review_flags": list(flags), "needs_review": bool(flags)})
        briefing = None
        if legs.brief == "reuse":
            briefing = legs.briefing            # stored, 3a-normalised by compute_legs
        elif legs.brief == "fresh":
            research_md = ws.research.read_text() if ws.research.exists() else ""
            reviews = read_json(ws.reviews) if ws.reviews.exists() else []
            echo(f"{slug}: writing a fresh briefing")
            briefing, problems = generate_briefing(
                providers["brief"], final_show, research_md, reviews,
                narration=read_overrides(ws).narration,
                vetting=legs.vet.result if legs.vet is not None else None)
            flags += problems

        written: list[str] = []

        def put(path: Path, data) -> None:
            write_artifact(path, data)
            written.append(path.name)

        if legs.vet is not None:
            put(ws.vetting, legs.vet.result)
        put(ws.notes, ShowNotes(gather=list(legs.gather.notes),
                                vet=list(legs.vet.notes) if legs.vet is not None else []))
        if briefing is not None:
            # Both files from the (normalised) model, on reuse too: a stored
            # briefing.md is never copied (spec 3a: re-rendered on every reuse).
            put(ws.briefing_json, briefing)
            put(ws.briefing_md, render_briefing_md(briefing, final_show))
        if not flags:
            # As `redo --from package`: a stale manifest must never short-circuit
            # the package and let the show be marked cleared over it.
            drop_stage_artifacts(ws, "package")
            echo(f"{slug}: packaging")
            _pkg, pkg_flags = build_package(ws, ia, final_show, force=False, profile=profile)
            written.append("package")
            flags += pkg_flags
        # The commit marker, written once and last.
        put(ws.show, final_show.model_copy(
            update={"review_flags": list(flags), "needs_review": bool(flags)}))
        return ReapplyOutcome(slug, "held" if flags else "cleared", legs.brief, list(flags),
                              delivered, written)
