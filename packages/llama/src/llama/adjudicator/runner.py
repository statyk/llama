"""The per-show adjudication runner (spec "Before judging", "Adjudication record and loop
guard", "Proposals in triage"): one held show through the loop guard, the stale
pre-flight, the bundle, the one LLM call, target validation, the gate and the apply, each
failure class mapped to an outcome and to exactly what is written.

What is written, by outcome: an applied (or accepted) record inside the apply's unit; a
proposal, malformed or dry-run record after it, by `write_outside_unit`, only while the
show is still the state the verdict judged (else `CHANGED`); a `failed` record, by the
same writer and on the same condition, for a failure after the call was paid for (the
call itself failed, the apply raised, or it hit a transient: `UNJUDGED`), outside a dry
run, so the pipeline hooks do not pay again for the same unchanged show; nothing at all
for a failure before the call (no spend), a concurrent change, or a `RateLimited`
(which propagates for the caller to pause on).

Never imports `llama.cli`: the redo arrives as `Context.redo`."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Callable

from herder import HerderError, TaskFailed
from herder.limits import RateLimited
from llama.adjudicator.apply import ApplyResult, apply_verdict
from llama.adjudicator.bundle import Bundle, build_bundle
from llama.adjudicator.gate import (Facts, GateResult, evaluate, first_judgements,
                                    validate_targets)
from llama.adjudicator.record import (AdjudicationRecord, RECORD_FILE_VERSION, is_current,
                                      read_record as read_adjudication, show_digest,
                                      view_digest, write_outside_unit, write_record)
from llama.adjudicator.verdict import (PROPOSE_ONLY_OPS, Evidence, FlagJudgement, OverruleFlag,
                                       SwitchRecording, Verdict, call_adjudicator, model_label)
from llama.campaign import CampaignUnreadable, awaiting_fix, last_mark
from llama.campaign import read_record as read_campaign
from llama.catalog import CatalogEntry
from llama.config import Config
from llama.ledger import Ledger, is_delivered
from llama.models import Show
from llama.override_keys import filename_keyed_entries, filename_keyed_refusal, refusal
from llama.overrules import flag_key
from llama.show_unit import ShowChanged
from llama.stages.select_recording import lineage_table
from llama.staleness import stale_message
from llama.workspace import ShowWorkspace, read_model

log = logging.getLogger(__name__)

APPLIED = "applied"
APPLIED_HELD = "applied, still held"
PROPOSAL = "held with proposal"
MALFORMED = "malformed"
STALE = "stale: reprocess first"
CURRENT = "skipped: current"
HAS_RECORD = "skipped: has a record"
NOT_HELD = "skipped: not held"
CHANGED = "skipped: changed"
UNJUDGED = "unjudged"
FAILED = "failed"
DRY_RUN = "dry-run"
ACCEPTED = "accepted"
PROPOSAL_STALE = "proposal stale"
NO_PROPOSAL = "no proposal"

# The run report's summary order.
OUTCOME_ORDER = (APPLIED, APPLIED_HELD, PROPOSAL, MALFORMED, STALE, CURRENT, HAS_RECORD,
                 NOT_HELD, CHANGED, UNJUDGED, FAILED, DRY_RUN, ACCEPTED, PROPOSAL_STALE,
                 NO_PROPOSAL)

_KEPT_FROM_DRY_RUN = ("applied", "proposal", "accepted")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Context:
    config: Config
    ia: object
    ledger: Ledger
    provider: object                                     # a ladder, or None
    redo: Callable[[CatalogEntry, str], "Path | None"]
    sink: Path | None = None                             # the pilot's record dir
    now: Callable[[], str] = _utc_now


@dataclass
class ShowOutcome:
    slug: str
    outcome: str
    detail: str = ""
    record: AdjudicationRecord | None = None
    changes: list[str] = field(default_factory=list)
    delivered_changed: bool = False
    fixed_eligible: bool = False
    llm_failure: bool = False


def hook_enabled(config: Config, flag: bool | None) -> bool:
    return flag if flag is not None else config.adjudicate.enabled


# ---------------------------------------------------------------- helpers

def _fixed_eligible(ws: ShowWorkspace) -> bool:
    """A station-marked show whose campaign record is processed after its last mark:
    `llama deliver --fixed` takes it."""
    camp, _ = _campaign(ws)
    return last_mark(camp) is not None and not awaiting_fix(camp)


def _record_path(ctx: Context, entry: CatalogEntry) -> Path | None:
    return ctx.sink / f"{entry.slug}.json" if ctx.sink is not None else None


def _held(ws: ShowWorkspace) -> bool:
    if not ws.show.exists():
        return False
    return read_model(ws.show, Show).needs_review


def _stale(ctx: Context, entry: CatalogEntry) -> str | None:
    ws = entry.ws
    if ws.overrides.exists():
        msg = refusal(entry.slug, json.loads(ws.overrides.read_text()))
        if msg is not None:
            return msg
    return stale_message(ctx.ia, ctx.config, ws, entry.slug)


def _campaign(ws: ShowWorkspace):
    """(record, unreadable)."""
    try:
        return read_campaign(ws), False
    except CampaignUnreadable:
        return None, True


def _facts(ctx: Context, bundle: Bundle, ws: ShowWorkspace) -> Facts:
    prov = bundle.provenance
    rec, unreadable = _campaign(ws)
    lineage = (lineage_table(ctx.config.selection, prov.candidate.collection,
                             prov.candidate.date) if prov is not None else {})
    a = prov.assessment if prov is not None else None
    complaints = {a.reviewed_identifier: len(a.recording_complaints)} if a is not None else {}
    return Facts(bundle=bundle,
                 delivered=is_delivered(ctx.ledger, bundle.show.performance_id),
                 marked=unreadable or last_mark(rec) is not None,
                 lineage=lineage, complaints=complaints)


def _target(e):
    for name in ("file", "identifier", "flag", "venue", "city"):
        if hasattr(e, name):
            return getattr(e, name)
    if hasattr(e, "breaks_after"):
        return {"breaks_after": list(e.breaks_after), "encore_after": e.encore_after}
    return None


def _applicable(verdict: Verdict) -> list[tuple[int, object]]:
    return [(i, e) for i, e in enumerate(verdict.edits) if e.op not in PROPOSE_ONLY_OPS]


def _applied_list(pairs: list[tuple[int | None, object]]) -> list[dict]:
    """`pairs` are (index in the stored verdict's `edits`, edit), so `index` always points
    into `rec.verdict["edits"]`; None for an edit with no such entry."""
    return [{"index": i, "op": e.op, "target": _target(e),
             "evidence_kinds": list(dict.fromkeys(ev.kind for ev in e.evidence))}
            for i, e in pairs]


def _base(ctx: Context, verdict: Verdict, outcome: str, *, gate: GateResult | None = None,
          dry_run: bool = False, **kw) -> AdjudicationRecord:
    return AdjudicationRecord(
        version=RECORD_FILE_VERSION, at=ctx.now(), model=model_label(ctx.config),
        dry_run=dry_run, outcome=outcome, verdict=verdict.model_dump(mode="json"),
        gate=[asdict(g) for g in gate.edits] if gate is not None else [],
        vetoes=list(gate.vetoes) if gate is not None else [],
        partial_tape=verdict.partial_tape, **kw)


def _key(flag: str, show: Show):
    k = flag_key(flag, show)
    return k if k is not None else flag


def held_proposal(pre: Show, post: Show, verdict: Verdict) -> dict:
    """For an applied show still held: each remaining post flag with the verdict's
    judgement of the pre flag of the same key, and an overrule of each one judged
    spurious (the evidence of the verdict's own overrule edit for that key, else [])."""
    judged = {_key(f, pre): j for f, j in first_judgements(verdict).items()}
    overrule_ev = {}
    for e in verdict.edits:
        if isinstance(e, OverruleFlag):
            overrule_ev.setdefault(_key(e.flag, pre),
                                   [ev.model_dump(mode="json") for ev in e.evidence])
    flags, edits = [], []
    for f in post.review_flags:
        k = _key(f, post)
        j = judged.get(k)
        flags.append({"flag": f, "judgement": j.model_dump(mode="json") if j else None})
        if j is not None and j.verdict == "spurious":
            edits.append({"op": "overrule", "flag": f, "confidence": j.confidence,
                          "why": j.why, "evidence": overrule_ev.get(k, [])})
    return {"flags": flags, "edits": edits}


def _write_after(ctx: Context, entry: CatalogEntry, rec: AdjudicationRecord,
                 bundle: Bundle, outcome: str, detail: str = "") -> ShowOutcome:
    path = _record_path(ctx, entry)
    if not write_outside_unit(entry.ws, rec, expect=bundle.view, path=path):
        return ShowOutcome(entry.slug, CHANGED, "changed while being judged")
    return ShowOutcome(entry.slug, outcome, detail,
                       record=read_adjudication(entry.ws, path=path))


def _failed(entry: CatalogEntry, what: str, exc: BaseException, **kw) -> ShowOutcome:
    log.warning("%s: adjudication %s failed: %s", entry.slug, what, exc)
    return ShowOutcome(entry.slug, FAILED, f"{what}: {exc}", **kw)


def _record_failure(ctx: Context, entry: CatalogEntry, bundle: Bundle, out: ShowOutcome, *,
                    verdict: Verdict | None = None, dry_run: bool = False) -> ShowOutcome:
    """After a paid call that left no other record: a `failed` record of the judged
    state, by `write_outside_unit` (nothing when the show moved meanwhile). Never in a
    dry run. Returns `out` unchanged; a failure to write is only logged."""
    if dry_run:
        return out
    rec = AdjudicationRecord(
        version=RECORD_FILE_VERSION, at=ctx.now(), model=model_label(ctx.config),
        outcome="failed", verdict=verdict.model_dump(mode="json") if verdict else {},
        result={"error": out.detail})
    try:
        write_outside_unit(entry.ws, rec, expect=bundle.view, path=_record_path(ctx, entry))
    except Exception as exc:          # noqa: BLE001 - the outcome is already a failure
        log.warning("%s: could not write the failed adjudication record: %s", entry.slug, exc)
    return out


# ---------------------------------------------------------------- adjudicate

def adjudicate_show(ctx: Context, entry: CatalogEntry, *, dry_run: bool = False,
                    force: bool = False, retry_failed: bool = False,
                    trial_policy: Callable[[Verdict, GateResult], bool] | None = None
                    ) -> ShowOutcome:
    """`retry_failed` (the backlog command's) judges a current `failed` record again;
    the pipeline hooks leave it False, so such a show waits for its digest to move."""
    ws, slug = entry.ws, entry.slug
    path = _record_path(ctx, entry)
    # 1-2: skips, with no call (a corrupt show.json fails here, before any spend)
    try:
        held = _held(ws)
        current = held and not force and is_current(ws, path=path)
        if current and retry_failed:
            stored = read_adjudication(ws, path=path)
            current = stored is not None and stored.outcome != "failed"
    except Exception as exc:          # noqa: BLE001 - one show must not abort a backlog
        return _failed(entry, "read show", exc)
    if not held:
        return ShowOutcome(slug, NOT_HELD)
    if current:
        return ShowOutcome(slug, CURRENT)
    if not force:
        old = read_adjudication(ws, path=path)
        if dry_run and old is not None and not old.dry_run and old.outcome in _KEPT_FROM_DRY_RUN:
            return ShowOutcome(slug, HAS_RECORD,
                               f"has a {old.outcome} record (--force to replace it)")
    # 3: stale pre-flight
    try:
        msg = _stale(ctx, entry)
    except Exception as exc:          # noqa: BLE001 - one show must not abort a backlog
        return _failed(entry, "stale check", exc)
    if msg is not None:
        return ShowOutcome(slug, STALE, msg)
    # 4: bundle
    try:
        bundle = build_bundle(ws, ctx.ia, ctx.config)
    except Exception as exc:          # noqa: BLE001
        return _failed(entry, "bundle", exc)
    # 5: the one LLM call
    if ctx.provider is None:
        return ShowOutcome(slug, FAILED, "no adjudicate provider")
    try:
        verdict = call_adjudicator(ctx.provider, bundle)
    except RateLimited:
        raise
    except (TaskFailed, HerderError) as exc:
        return _record_failure(ctx, entry, bundle,
                               _failed(entry, "adjudicate call", exc, llm_failure=True),
                               dry_run=dry_run)
    except ValueError as exc:
        return _failed(entry, "adjudicate prompt", exc)
    # 6: target validation, before anything is written
    reasons = validate_targets(verdict, bundle)
    if reasons:
        rec = _base(ctx, verdict, "malformed", malformed=reasons, dry_run=dry_run)
        return _write_after(ctx, entry, rec, bundle, MALFORMED, "; ".join(reasons))
    # 7: the gate
    facts = _facts(ctx, bundle, ws)
    gate = evaluate(verdict, facts)
    # 8: dry run, or a proposal
    if dry_run:
        result = {}
        if trial_policy is not None and _applicable(verdict) and trial_policy(verdict, gate):
            try:
                res = apply_verdict(ws, verdict, expect=bundle.view, redo=partial(ctx.redo, entry),
                                    ledger=ctx.ledger,
                                    mode="auto", gate=gate, on_commit=lambda post, r: None,
                                    trial=True, at=ctx.now())
            except RateLimited:
                raise
            except ShowChanged:
                return ShowOutcome(slug, CHANGED, "changed while being judged")
            except Exception as exc:  # noqa: BLE001
                return _failed(entry, "trial apply", exc)
            result = asdict(res)
        rec = _base(ctx, verdict, "dry-run", gate=gate, dry_run=True, result=result)
        return _write_after(ctx, entry, rec, bundle, DRY_RUN)
    if not gate.auto:
        rec = _base(ctx, verdict, "proposal", gate=gate)
        return _write_after(ctx, entry, rec, bundle, PROPOSAL)
    # 9: apply
    pre = bundle.show
    committed: dict = {}

    def on_commit(post: Show, res: ApplyResult) -> None:
        rec = _base(ctx, verdict, "applied", gate=gate, digest=show_digest(ws),
                    applied=_applied_list(_applicable(verdict)), result=asdict(res),
                    held_proposal=held_proposal(pre, post, verdict) if post.needs_review
                    else None)
        write_record(ws, rec, path=path)
        committed["rec"] = rec

    try:
        res = apply_verdict(ws, verdict, expect=bundle.view, redo=partial(ctx.redo, entry),
                            ledger=ctx.ledger,
                            mode="auto", gate=gate, on_commit=on_commit, at=ctx.now())
    except RateLimited:
        raise
    except ShowChanged:
        return ShowOutcome(slug, CHANGED, "changed while being judged")
    except Exception as exc:          # noqa: BLE001 - the unit restored the files
        return _record_failure(ctx, entry, bundle, _failed(entry, "apply", exc),
                               verdict=verdict)
    if res.status == "applied":
        rec = committed["rec"]
        return ShowOutcome(slug, APPLIED_HELD if res.held else APPLIED, record=rec,
                           changes=list(res.changes),
                           delivered_changed=facts.delivered
                           and view_digest(bundle.view) != rec.digest,
                           fixed_eligible=_fixed_eligible(ws))
    if res.status in ("restored", "refused"):
        rec = _base(ctx, verdict, "proposal", gate=gate, result=asdict(res))
        detail = "; ".join(res.diff) if res.status == "restored" else (res.error or "")
        return _write_after(ctx, entry, rec, bundle, PROPOSAL, detail)
    return _record_failure(ctx, entry, bundle,                         # transient
                           ShowOutcome(slug, UNJUDGED, f"transient: {res.error}"),
                           verdict=verdict)


# ---------------------------------------------------------------- accept

def accept_verdict(rec: AdjudicationRecord) -> Verdict | None:
    """The verdict accept applies, or None when the record holds no proposal."""
    if rec.dry_run:
        return None
    if rec.outcome == "proposal":
        return Verdict.model_validate(rec.verdict)
    hp = rec.held_proposal
    if rec.outcome == "applied" and hp and hp.get("edits"):
        base = Verdict.model_validate(rec.verdict)
        # accept runs no gate, and the evidence minimum is a gate input: model_construct
        edits = [OverruleFlag.model_construct(
                     op="overrule", flag=e["flag"], confidence=e["confidence"], why=e["why"],
                     evidence=[Evidence.model_construct(**ev) for ev in e.get("evidence", [])])
                 for e in hp["edits"]]
        flags = [FlagJudgement.model_construct(**{**f["judgement"], "flag": f["flag"]})
                 for f in hp.get("flags", []) if f.get("judgement")]
        return base.model_copy(update={"edits": edits, "flags": flags})
    return None


def acceptable_state(ws: ShowWorkspace, rec: AdjudicationRecord | None) -> str:
    """Whether accept would apply `rec` now: "ok" (readable, not a dry run, current, and
    holding at least one non-propose-only edit), "stale" (a proposal the show has moved
    past) or "none". The one predicate behind triage's `[a]` and `adjudicate --accept`'s
    preview. Raises when the record's verdict cannot be read."""
    if rec is None or rec.dry_run:
        return "none"
    verdict = accept_verdict(rec)
    if verdict is None:
        return "none"                 # no proposal at all (a failed record, say): never stale
    if not is_current(ws):
        return "stale"
    if not _applicable(verdict):
        return "none"
    return "ok"


def _accept_pairs(stored: AdjudicationRecord, verdict: Verdict,
                  show: Show) -> list[tuple[int | None, object]]:
    """The applicable edits, each with its index in the STORED verdict's `edits`. For a
    proposal that is the edit's own index (propose-only edits skipped, never re-based).
    For a held_proposal overrule it is the index of the stored verdict's own `overrule`
    edit for the same flag key, or None when the verdict had none (the overrule was
    built from a spurious judgement alone)."""
    if stored.outcome == "proposal":
        return _applicable(verdict)
    original = Verdict.model_validate(stored.verdict)
    own = {}
    for i, e in enumerate(original.edits):
        if isinstance(e, OverruleFlag):
            own.setdefault(_key(e.flag, show), i)
    return [(own.get(_key(e.flag, show)), e) for e in verdict.edits]


_PLACEHOLDER_INCLUDE = re.compile(r"^(?P<file>.+): included with a placeholder title '")


def _include_hint(slug: str, line: str) -> str:
    """The way forward for an accept the placeholder-include backstop restored. apply returns
    only text diff lines (no structured kind), so the line apply's whole_show_diff builds is
    matched here; any other line yields no hint."""
    m = _PLACEHOLDER_INCLUDE.match(line)
    if m is None:
        return ""
    return (f"\nto include it anyway: llama fix {slug} --include {m['file']} "
            f'--set-title "<title you choose>"')


def accept_proposal(ctx: Context, entry: CatalogEntry, *,
                    expected_at: str | None = None) -> ShowOutcome:
    """Apply the stored proposal. `expected_at` is the `at` of the record the operator was
    shown; a record that has been rewritten since is not applied."""
    ws, slug = entry.ws, entry.slug
    path = _record_path(ctx, entry)
    # 1: a stored, non-dry-run proposal
    stored = read_adjudication(ws, path=path)
    try:
        verdict = accept_verdict(stored) if stored is not None else None
    except Exception as exc:          # noqa: BLE001 - a hand-edited or old-format record
        return ShowOutcome(slug, NO_PROPOSAL, f"stored proposal unreadable: {exc}")
    if verdict is None:
        return ShowOutcome(slug, NO_PROPOSAL)
    if expected_at is not None and stored.at != expected_at:
        return ShowOutcome(slug, NO_PROPOSAL, "proposal changed since it was shown; re-run")
    # 2: the bundle's captured view is both the digest checked and the unit's expect
    try:
        bundle = build_bundle(ws, ctx.ia, ctx.config)
    except Exception as exc:          # noqa: BLE001
        return _failed(entry, "bundle", exc)
    if view_digest(bundle.view) != stored.digest:
        return ShowOutcome(slug, PROPOSAL_STALE, "the show changed since the proposal")
    # 3: nothing applicable (never call apply with no edit: earliest_stage raises)
    pairs = _accept_pairs(stored, verdict, bundle.show)
    edits = [e for _, e in pairs]
    if not edits:
        return ShowOutcome(slug, NO_PROPOSAL, "only propose-only edits")
    verdict = verdict.model_copy(update={"edits": edits})
    # 4: targets against the fresh bundle
    reasons = validate_targets(verdict, bundle)
    if reasons:
        return ShowOutcome(slug, MALFORMED, "; ".join(reasons))
    # 5: a switch over filename-keyed entries
    switch = next((e for e in edits if isinstance(e, SwitchRecording)), None)
    if switch is not None:
        keyed = filename_keyed_entries(bundle.overrides)
        if keyed:
            return ShowOutcome(slug, FAILED, filename_keyed_refusal(slug, keyed))
    # 6: apply, no gate and no re-hold
    committed: dict = {}

    def on_commit(post: Show, res: ApplyResult) -> None:
        rec = stored.model_copy(update={
            "version": RECORD_FILE_VERSION, "at": ctx.now(), "outcome": "accepted",
            "dry_run": False, "digest": show_digest(ws), "applied": _applied_list(pairs),
            "result": asdict(res), "held_proposal": None})
        write_record(ws, rec, path=path)
        committed["rec"] = rec

    try:
        res = apply_verdict(ws, verdict, expect=bundle.view, redo=partial(ctx.redo, entry),
                            ledger=ctx.ledger,
                            mode="accept", gate=None, on_commit=on_commit, at=ctx.now())
    except RateLimited:
        raise
    except ShowChanged:
        return ShowOutcome(slug, CHANGED, "changed since the proposal was checked")
    except Exception as exc:          # noqa: BLE001 - the unit restored the files
        return _failed(entry, "accept", exc)
    if res.status == "applied":
        return ShowOutcome(slug, ACCEPTED, "still held" if res.held else "",
                           record=committed["rec"], changes=list(res.changes),
                           delivered_changed=is_delivered(ctx.ledger, bundle.show.performance_id)
                           and view_digest(bundle.view) != committed["rec"].digest,
                           fixed_eligible=_fixed_eligible(ws))
    if res.status == "restored":
        first = res.diff[0] if res.diff else "no detail"
        detail = f"accept restored: {first}"
        if switch is not None and not first.startswith("flag silenced"):
            detail += f"; to switch anyway: llama fix {slug} --recording {switch.identifier}"
        detail += "".join(_include_hint(slug, line) for line in res.diff)
        return ShowOutcome(slug, FAILED, detail)
    if res.status == "refused":
        return ShowOutcome(slug, FAILED, res.error or "refused")
    return ShowOutcome(slug, FAILED, f"transient: {res.error}; try again")
