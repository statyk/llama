"""What `llama adjudicate` prints (spec "Backlog command and pacing"): a stored proposal
as lines, the propose-only items as the commands that do them, and the run report. Pure
text over records and outcomes; nothing here reads or writes the library."""
from __future__ import annotations

from typing import Callable

from llama.adjudicator import runner
from llama.adjudicator.record import AdjudicationRecord
from llama.adjudicator.runner import ShowOutcome
from llama.adjudicator.verdict import PROPOSE_ONLY_OPS, Verdict
from llama.models import Show

def proposal_commands(slug: str, verdict: Verdict) -> list[str]:
    """The verdict's propose-only edits as the commands that carry them out."""
    out: list[str] = []
    for e in verdict.edits:
        if e.op not in PROPOSE_ONLY_OPS:
            continue
        if e.op == "set_date":
            out.append(f"llama fix {slug} --set-date {e.value}")
        elif e.op == "untitled":
            out.append(f"llama fix {slug} --untitled")
        elif e.op == "narration":
            out.append(f"llama fix {slug} --narration {e.value}")
        elif e.op == "rm":
            out.append(f"llama rm {slug}")
        elif e.op == "redo_research":
            out.append(f"llama redo {slug} --from research")
    return out


def _mmss(sec: float) -> str:
    s = int(round(sec))
    return f"{s // 60}:{s % 60:02d}"


def _durations(show: Show) -> dict[str, float]:
    """filename -> seconds, over the kept tracks and the excluded rows (where known)."""
    out = {x.get("filename"): x.get("duration_sec") for x in show.excluded_files
           if isinstance(x.get("duration_sec"), (int, float))}
    out.update({t.filename: t.duration_sec for t in show.tracks if t.duration_sec is not None})
    return out


def _target(e, durations: dict[str, float] | None = None) -> str:
    """What an edit names, as the operator must see it before accepting: a set_title with
    its title, an include/exclude with the file's length where known."""
    if getattr(e, "op", None) == "set_title":
        return f'{e.file} -> "{e.title}"'
    if getattr(e, "op", None) in ("include", "exclude"):
        d = (durations or {}).get(e.file)
        return e.file + (f" ({_mmss(d)})" if d is not None else "")
    for name in ("file", "identifier", "flag", "venue", "city"):
        if hasattr(e, name):
            return str(getattr(e, name))
    if hasattr(e, "breaks_after"):
        enc = getattr(e, "encore_after", None)
        return (f"breaks_after={list(e.breaks_after)}"
                + (f" encore_after={enc}" if enc is not None else ""))
    v = getattr(e, "value", None)
    return str(v) if v is not None else ""


def _flag_line(flag: str, j) -> str:
    if j is None:
        return f"  flag: {flag} -> not judged"
    return f"  flag: {flag} -> {j['verdict']} ({j['confidence']}): {j['why']}"


def render_proposal(rec: AdjudicationRecord, show: Show, *, slug: str) -> list[str]:
    """A stored proposal (or an applied record's remaining hold) as lines: each edit with
    what it would write (a set_title's title, an include/exclude's length from `show`
    where known), its why and its evidence. What these lines show is what triage `[a]`
    and `adjudicate --accept` apply. `slug` is the library slug the `run:` commands name
    (the caller's, never derived)."""
    hp = rec.held_proposal
    if rec.outcome == "applied" and hp:
        lines = [f"applied ({rec.model}, {rec.at}), still held:"]
        for f in hp.get("flags", []):
            lines.append(_flag_line(f["flag"], f.get("judgement")))
        for i, e in enumerate(hp.get("edits", [])):
            conf = f" ({e['confidence']})" if e.get("confidence") else ""
            lines.append(f"  edit {i}: overrule {e['flag']}{conf}")
            if e.get("why"):
                lines.append(f"    why: {e['why']}")
            lines += [f'    {ev["kind"]}: "{ev["quote"]}"' for ev in e.get("evidence", [])]
        return lines
    verdict = Verdict.model_validate(rec.verdict)
    lines = [f"proposal ({rec.model}, {rec.at}): {verdict.kind}; "
             f"correct after: {verdict.show_correct_after}"]
    for j in verdict.flags:
        lines.append(_flag_line(j.flag, j.model_dump(mode="json")))
    gates = {g["index"]: g for g in rec.gate}
    durations = _durations(show)
    for i, e in enumerate(verdict.edits):
        g = gates.get(i)
        bar = f" [{g['bar']}: {'passed' if g['passed'] else g['reason']}]" if g else ""
        lines.append(f"  edit {i}: {e.op} {_target(e, durations)}".rstrip() + bar)
        if e.why:
            lines.append(f"    why: {e.why}")
        lines += [f'    {ev.kind}: "{ev.quote}"' for ev in e.evidence]
    if verdict.kind == "hold" and verdict.decide:
        lines.append(f"  decide: {verdict.decide}")
    if rec.partial_tape or verdict.partial_tape:
        lines.append("  partial tape")
    lines += [f"  run: {c}" for c in proposal_commands(slug, verdict)]
    return lines


def _why_held(o: ShowOutcome) -> str:
    rec = o.record
    if o.outcome == runner.APPLIED_HELD:
        flags = (rec.held_proposal or {}).get("flags", []) if rec is not None else []
        return "applied, still held" + (f": {flags[0]['flag']}" if flags else "")
    if rec is not None:
        for g in rec.gate:
            if not g.get("passed"):
                return g.get("reason", "")
        if rec.vetoes:
            return rec.vetoes[0]
        diff = rec.result.get("diff") if rec.result else None
        if diff:
            return diff[0]
        if rec.result and rec.result.get("error"):
            return rec.result["error"]
    return o.detail


def render_report(outcomes: list[ShowOutcome], *, voiced: Callable[[str], bool]) -> list[str]:
    counts: dict[str, int] = {}
    for o in outcomes:
        counts[o.outcome] = counts.get(o.outcome, 0) + 1
    order = [k for k in runner.OUTCOME_ORDER if k in counts] + [k for k in counts
                                                         if k not in runner.OUTCOME_ORDER]
    lines = [f"summary: {len(outcomes)} shows: "
             + ", ".join(f"{k} {counts[k]}" for k in order)]

    for header, kinds in (("auto-applied track-list changes:", (runner.APPLIED, runner.APPLIED_HELD)),
                          ("accepted track-list changes:", (runner.ACCEPTED,))):
        changed = [o for o in outcomes if o.changes and o.outcome in kinds]
        if changed:
            lines.append(header)
            for o in changed:
                lines.append(f"  {o.slug}:")
                lines += [f"    {c}" for c in o.changes]
    held = [o for o in outcomes if o.outcome in (runner.PROPOSAL, runner.APPLIED_HELD)]
    if held:
        lines.append("held with proposal:")
        lines += [f"  {o.slug}: {_why_held(o)}" for o in held]
    stale = [o for o in outcomes if o.outcome == runner.STALE]
    if stale:
        lines.append("stale: reprocess first:")
        lines += [f"  {o.slug}: {o.detail}" for o in stale]
    fixed = [o for o in outcomes if o.delivered_changed and o.fixed_eligible]
    if fixed:
        lines.append("eligible for llama deliver --fixed:")
        lines += [f"  {o.slug}" for o in fixed]
    redeliver = [o for o in outcomes if o.delivered_changed and not o.fixed_eligible]
    if redeliver:
        lines.append("delivered shows changed (re-deliver):")
        lines += [f"  llama deliver {o.slug}" + (" --replace-voiced" if voiced(o.slug) else "")
                  for o in redeliver]
    return lines
