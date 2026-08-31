"""Whole-tape title correspondence: a proposal generator, never an adopter.

This DP is deliberately NOT wired into the pipeline. Measured on the
blind-the-tags corpus, unanchored monotone correspondence is 45-52% wrong and
margin does not discriminate, so its output requires a human. It exists to
render a proposal an operator confirms; the confirmation lands in
overrides.json. See docs/superpowers/specs/2026-08-30-title-correspondence-design.md.
"""
from llama.models import ParsedSetlist, ProposalRow, TitleProposal, Track
from llama.structure import fuzzy_norm_title

_INF = float("inf")


def _merge_legal(items, lo: int, k: int) -> bool:
    """A k-item merge is legal only if every item but the last segues on."""
    return k == 1 or all(items[i].segue for i in range(lo, lo + k - 1))


def _item_durations(tracks, items, given):
    if given is not None:
        return list(given), "sibling-duration"
    total = sum(t.duration_sec or 0.0 for t in tracks)
    mu = total / len(items) if items else 0.0
    return [mu] * len(items), "duration-model"


def _solve(tracks, items, idur, max_merge, forbid=None):
    """Min-cost monotone assignment. Returns (cost, spans) or (inf, None).
    `forbid` is an optional {track_pos: (lo, hi)} span the solution must avoid,
    used to compute per-row margins."""
    nt, ni = len(tracks), len(items)
    best = [[_INF] * (ni + 1) for _ in range(nt + 1)]
    back = [[None] * (ni + 1) for _ in range(nt + 1)]
    best[0][0] = 0.0
    for a in range(nt):
        dur = tracks[a].duration_sec or 0.0
        for b in range(ni + 1):
            if best[a][b] == _INF:
                continue
            for k in range(0, max_merge + 1):
                if b + k > ni:
                    break
                if k >= 1 and not _merge_legal(items, b, k):
                    continue
                if forbid and forbid.get(a) == (b, b + k):
                    continue
                cost = dur if k == 0 else abs(dur - sum(idur[b:b + k]))
                if best[a][b] + cost < best[a + 1][b + k]:
                    best[a + 1][b + k] = best[a][b] + cost
                    back[a + 1][b + k] = k
    if best[nt][ni] == _INF:
        return _INF, None
    spans, b = [], ni
    for a in range(nt, 0, -1):
        k = back[a][b]
        spans.append(None if k == 0 else (b - k, b))
        b -= k
    spans.reverse()
    return best[nt][ni], spans


def propose_titles(tracks: list[Track], canonical: ParsedSetlist, *,
                   item_durations: list[float] | None = None,
                   max_merge: int = 3) -> TitleProposal:
    items = canonical.items
    if not items:
        return TitleProposal(feasible=False, reason="no usable canonical setlist")
    idur, source = _item_durations(tracks, items, item_durations)
    cost, spans = _solve(tracks, items, idur, max_merge)
    if spans is None:
        return TitleProposal(
            feasible=False, evidence_source=source,
            reason="no consistent correspondence - parse quality too low")

    rows = []
    for pos, (t, span) in enumerate(zip(tracks, spans)):
        if span is None:
            rows.append(ProposalRow(index=t.index, duration_sec=t.duration_sec,
                                    item_span=None, title="", evidence="filler"))
            continue
        title = " > ".join(items[i].title.strip() for i in range(*span))
        alt, _ = _solve(tracks, items, idur, max_merge, forbid={pos: span})
        rows.append(ProposalRow(
            index=t.index, duration_sec=t.duration_sec, item_span=span,
            title=title, evidence=source,
            margin_sec=_INF if alt == _INF else alt - cost))
    return TitleProposal(rows=rows, feasible=True, evidence_source=source)
