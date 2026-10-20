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
import hashlib
import json
import shutil
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from llama.catalog import CatalogEntry
from llama.config import Config
from llama.errors import LlamaError
from llama.ledger import Ledger
from llama.locks import file_lock
from llama.models import Provenance, Show, ShowNotes
from llama.replay import (CacheOnlyIA, classify, compute_legs, input_digests, setlistfm_client,
                          shipped_diff)
from llama.stages.brief import generate_briefing, render_briefing_md
from llama.stages.package import build_package
from llama.workspace import (drop_stage_artifacts, read_json, read_model, read_overrides,
                             write_artifact)

# Spec slice 6 "Batch state": the batch also stops after this many
# consecutive LLM failures of any kind (an openrouter 429 or an unrecognised
# refusal arrives as a plain HerderError, which the pause path never sees).
STOP_AFTER_LLM_FAILURES = 3

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
    # "skipped: inputs changed" | "skipped: structure changed" |
    # "dry-run: <predicted>"
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
                 echo: Callable[[str], None],
                 allow_structure_change: bool = False) -> ReapplyOutcome:
    """Reapply one held show (spec slice 6). `ia` is the real archive.org
    client and is used ONLY by `build_package`; the replay itself reads the
    cache through `CacheOnlyIA`. `row` is the show's predicted-list row (its
    `digests` must still match), or None for a show named on the command
    line. The only LLM call is one fresh brief (`providers["brief"]`), made
    before anything is written, so a refusal there writes nothing. A show whose
    replay changes its sets/segues/breaks (`structure-changed`) is applied only
    when `allow_structure_change` (spec slice 6: it joins the apply once
    checked); otherwise nothing is written and the outcome is `skipped:
    structure changed`."""
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
        if outcome == "structure-changed" and not allow_structure_change:
            return ReapplyOutcome(slug, "skipped: structure changed", legs.brief,
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
        if (briefing is None and flags
                and (ws.briefing_json.exists() or ws.briefing_md.exists())
                and any(shipped_diff(stored, final_show).values())):
            # Held with the briefing leg not run, and the replay moved shipped
            # fields: the stored briefing was written against the OLD show, and
            # a later `fix --overrule` -> `redo --from package` would ship it
            # unchecked (package does not re-run briefing_guard). Drop the
            # brief stage's artifacts (briefing.json, briefing.md and, as a
            # redo from brief, package/manifest.json) so the eventual overrule
            # regenerates the briefing. Last step before the commit marker: a
            # crash between this drop and show.json leaves a held show with no
            # briefing, which `redo --from brief` regenerates.
            drop_stage_artifacts(ws, "brief")
            written.append("drop:brief")
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


# --- batch state (spec slice 6 "Batch state"; plan Contracts "Reapply batch state") ---

def load_list(path: Path, *, sha: str, fingerprint: str) -> dict:
    """A predicted list written by `replay compare` (plan Contracts). Refused
    whole when it was written by other code or another config (spec
    "Predicted lists are tied to what produced them"): its rows' outcomes are
    predictions of THAT code under THAT config."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise LlamaError(f"cannot read list {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        raise LlamaError(f"list {path} is not a predicted list (no rows)")
    for row in data["rows"]:
        if not (isinstance(row, dict) and isinstance(row.get("slug"), str) and row["slug"]
                and isinstance(row.get("digests"), dict)):
            raise LlamaError(f"list {path} has a malformed row: {row!r}"[:300])
    list_sha, list_fp = data.get("sha"), data.get("config_fingerprint")
    # `<sha>-dirty` names no code at all: two trees at one HEAD with different
    # uncommitted edits share it, so equality would accept predictions made by
    # code that is not the code running. Refused on either side.
    if str(list_sha).endswith("-dirty") or sha.endswith("-dirty"):
        raise LlamaError(f"list {path} was written for code {list_sha}; running code is {sha}: "
                         "an uncommitted tree has no code identity, commit first and "
                         "re-run the harness")
    if list_sha != sha or list_fp != fingerprint:
        raise LlamaError(f"list {path} was written for code {list_sha} and config {list_fp}; "
                         f"running code is {sha}, config {fingerprint}")
    return data


def batch_dir(root: Path, list_path: Path) -> Path:
    """`<root>/reapply/<sha256(list bytes)[:16]>`: outside `runs/`, so `llama run
    list` never sees it; the same list file always finds the same batch."""
    return root / "reapply" / hashlib.sha256(Path(list_path).read_bytes()).hexdigest()[:16]


def read_progress(batch: Path) -> dict[str, dict]:
    """slug -> its LAST progress row. A slug is finished when that row has
    `retryable == false`. A line that does not parse (a crash mid-append) is
    skipped: its show is then simply not finished, the safe direction."""
    path = batch / "progress.jsonl"
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("slug"), str):
            out[row["slug"]] = row
    return out


def record_progress(batch: Path, slug: str, outcome: str, retryable: bool) -> None:
    """Append one progress row under the batch's own lock."""
    path = batch / "progress.jsonl"
    line = json.dumps({"slug": slug, "outcome": outcome, "retryable": bool(retryable),
                       "at": datetime.now(timezone.utc).isoformat()})
    with file_lock(batch / "progress.lock"):
        # A previous append cut short (no trailing newline) must not swallow this row.
        lead = ""
        if path.exists() and path.stat().st_size:
            with open(path, "rb") as f:
                f.seek(-1, 2)
                lead = "" if f.read(1) == b"\n" else "\n"
        with open(path, "a") as f:
            f.write(lead + line + "\n")
