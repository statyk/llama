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
        given = list(given)
        if len(given) != len(items):
            raise ValueError(
                f"item_durations has {len(given)} entries, expected {len(items)}")
        return given, "sibling-duration"
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


def _counts(tracks, items) -> str:
    """The whole-tape shape, in the operator's terms: is the setlist I have
    describing the same performance as the tape I have? Song-like is
    `structure.is_filler`'s complement -- the same notion `_songish_coverage`
    counts over, since tuning/crowd/encore-break tracks are never in a
    canonical setlist and must not read as missing songs."""
    from llama.structure import is_filler
    songish = sum(1 for t in tracks if not is_filler(t.title))
    d = songish - len(items)
    if d > 0:
        return (f"{len(items)} canonical items vs {songish} song-like tracks - "
                f"the setlist is {d} song{'s' if d > 1 else ''} short of this tape")
    if d < 0:
        return (f"{len(items)} canonical items vs {songish} song-like tracks - "
                f"the setlist describes {-d} song{'s' if -d > 1 else ''} "
                f"this tape does not hold")
    return f"{len(items)} canonical items vs {songish} song-like tracks - counts agree"


def _unaccounted(tracks, canonical) -> str | None:
    """A decline reason when the canonical cannot account for the tracks this
    proposal could actually adopt for, or None when it can.

    THE SAFETY ARGUMENT, and why it is a count and not a confidence. Only
    tracks still `title_source == "unresolved"` are ever adopted (see
    `cli._propose_titles_for_show`), so what has to hold is that every
    maximal run of them is COUNT-FORCED between anchors: bracketed by tracks
    whose own titles independently place them in the canonical, with exactly
    as many canonical items in between as there are files to put them on.
    Then no shift can hide in the run. This is `adopt_gap_titles`' argument
    verbatim -- deliberately, and it reuses that code (`anchor_spans` /
    `gap_span`) rather than restating it -- and it is the only evidence class
    the spec's blind test measured safe: 2.4% wrong, against 45-52% for the
    unanchored monotone correspondence this DP otherwise performs.

    What the two paths do NOT share is the veto: `adopt_gap_titles` also
    demands `_hygienic` titles because it adopts SILENTLY. Here an operator
    reads the table first, so hygiene is their call -- which is the whole
    residual value of this command over the `setlist-gap` rung, and it is
    real: `trampledbyturtles-2007-07-20` track 21 is a count-forced,
    two-side-anchored gap over the canonical item `1922`, which
    `is_real_title` rejects (no three ASCII letters) and `setlist-gap`
    therefore refuses to adopt.

    Measured on the M3 gate's six held shows: this declines
    `yondermountainstringband-2005-12-31` and `-2002-12-31` (wholly untagged
    tapes -- no anchors exist at all, so nothing pins the setlist to the
    tape, and both rendered a uniform off-by-one), declines
    `infamousstringdusters-2014-03-15` (its 3-file unresolved run is
    bracketed by 4 canonical items -- `3x5`, `Something Wind`, `Machines`
    and the set marker `~Set 02~` -- which is exactly the extra item the DP
    spent displacing rows 6-25), and passes
    `trampledbyturtles-2007-07-20`, the one adoption that was right.

    Note what this does NOT check, since it would be easy to read more into
    it: nothing here compares the DP's assignment against the anchors on
    rows that are ALREADY titled. Those rows are never adopted, so they are
    display noise rather than a hazard -- but they are visibly wrong on
    `trampledbyturtles-2007-07-20` itself (rows 1-3, 11-12), so the rendered
    table is not evidence that the DP understood the tape. The adoptable
    rows ARE checked against the anchors, in `_contradicts_forced_gaps`.

    Returns `(reason, gaps)`: the decline reason or None, and the forced
    `[lo, hi] -> item span` gaps for the caller to hold the DP to.
    """
    from llama.structure import anchor_spans, gap_span, unresolved_runs
    items = canonical.items
    anchors = anchor_spans(tracks, canonical)
    gaps: list[tuple[int, int, tuple[int, int]]] = []
    for lo, hi in unresolved_runs(tracks):
        where = f"track {lo + 1}" if lo == hi else f"tracks {lo + 1}-{hi + 1}"
        span = gap_span(anchors, lo, hi, len(tracks))
        if span is None:
            return (f"the setlist cannot be pinned to {where}: no track with a "
                    f"title of its own brackets that run, so nothing fixes where "
                    f"in the setlist it starts ({_counts(tracks, items)})"), []
        have, need = span[1] - span[0], hi - lo + 1
        if have != need:
            gap = ", ".join(it.title.strip() for it in items[span[0]:span[1]]) or "none"
            return (f"the setlist does not account for {where}: {need} file"
                    f"{'s' if need > 1 else ''} but {have} setlist item"
                    f"{'s' if have != 1 else ''} between the titled tracks that "
                    f"bracket them ({gap}) - off by {abs(have - need)} "
                    f"({_counts(tracks, items)})"), []
        gaps.append((lo, hi, span))
    return None, gaps


def _contradicts_forced_gaps(spans, gaps) -> str | None:
    """The second half of the guard, and the reason the first half is not
    enough on its own.

    `_unaccounted` proves that a run of adoptable tracks has exactly as many
    canonical items between its anchors as it has files -- which FIXES what
    those tracks' titles are, one item per file, in order. The DP does not
    know that: it never sees an anchor, and it is free to spend a merge
    somewhere else on the tape and slide its whole assignment past the gap.
    So a tape can clear the count check and still be handed a proposal that
    contradicts the very anchoring that licensed it.

    Declining on that contradiction is deliberately the response, rather
    than quietly substituting the forced titles: this command stays
    proposal-only, with the DP its single proposer, and a disagreement
    between the DP and the structure is a reason to send the operator back
    to their sources -- not to invent a second, silent adoption path with no
    human in it. Measured on the M3 gate's six shows this fires on none of
    them; on `trampledbyturtles-2007-07-20` the DP independently agrees with
    the forced gap (`1922`, track 21).
    """
    for lo, hi, span in gaps:
        want = [(span[0] + k, span[0] + k + 1) for k in range(hi - lo + 1)]
        got = list(spans[lo:hi + 1])
        if got != want:
            where = f"track {lo + 1}" if lo == hi else f"tracks {lo + 1}-{hi + 1}"
            return (f"the correspondence contradicts the setlist at {where}: the "
                    f"titled tracks bracketing that run fix its {hi - lo + 1} "
                    f"setlist item{'s' if hi > lo else ''}, but the durations "
                    f"place different ones there - the tape and the setlist "
                    f"disagree about what is on these files")
    return None


def propose_titles(tracks: list[Track], canonical: ParsedSetlist, *,
                   item_durations: list[float] | None = None,
                   max_merge: int = 3) -> TitleProposal:
    items = canonical.items
    if not items:
        return TitleProposal(feasible=False, reason="no usable canonical setlist")
    idur, source = _item_durations(tracks, items, item_durations)
    # Before the DP, not after: this is a structural question about whether
    # the canonical and the track list describe the same material, and the
    # DP's cost cannot answer it. A shift is CONSISTENT by construction, so
    # it produces a cheap, feasible, entirely wrong solution -- which is the
    # M3 gate's finding (3 of 4 rendered tables would have written wrong
    # titles, with nothing in the rendering telling them apart).
    unaccounted, gaps = _unaccounted(tracks, canonical)
    if unaccounted is not None:
        return TitleProposal(feasible=False, evidence_source=source, reason=unaccounted)
    cost, spans = _solve(tracks, items, idur, max_merge)
    if spans is None:
        return TitleProposal(
            feasible=False, evidence_source=source,
            reason="no consistent correspondence - parse quality too low")
    contradiction = _contradicts_forced_gaps(spans, gaps)
    if contradiction is not None:
        return TitleProposal(feasible=False, evidence_source=source, reason=contradiction)

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
            margin_sec=None if alt == _INF else alt - cost,
            forced=alt == _INF))
    return TitleProposal(rows=rows, feasible=True, evidence_source=source)


def sibling_item_durations(ia, candidate, identifier: str,
                           canonical: ParsedSetlist, want) -> list[float] | None:
    """Per-canonical-item durations lifted from a TAGGED sibling recording of
    the same performance.

    Requires every canonical item to match exactly one sibling track by
    normalized title. Anything less returns None rather than guessing by
    position - a partially-matched donor is exactly the 20%-wrong case the
    blind test measured.
    """
    from llama.junk import filter_files
    from llama.titles import clean_tag_titles
    from llama.util import length_seconds
    if ia is None:
        return None
    if not canonical.items:
        # `all(...)` over an empty `norms` is vacuously true, so without this
        # guard the first non-self recording would "resolve" a zero-item
        # setlist and hand back `[]` -- callers would read that as a
        # successfully-resolved empty duration list, not "no evidence".
        return None
    norms = [fuzzy_norm_title(it.title) for it in canonical.items]
    if len(set(norms)) != len(norms):
        # A repeated song in the CANONICAL setlist (a reprise, or two merged
        # tracks sharing a title) is exactly as ambiguous as a repeated title
        # on the donor side: a single donor duration cannot tell which
        # occurrence it belongs to, so guessing by position would corrupt the
        # DP's cost model for every duplicated item. Refuse rather than guess
        # -- the duration model is the intended fallback.
        return None
    for rec in candidate.recordings:
        if rec.identifier == identifier:
            continue
        try:
            kept, _, _ = filter_files(
                ia.metadata(rec.identifier).get("files", []), want_format=want)
        except Exception:
            continue
        by_norm: dict[str, float] = {}
        for f, title in zip(kept, clean_tag_titles(kept)):
            n = fuzzy_norm_title(title)
            if not n:
                continue
            if n in by_norm:          # ambiguous donor; refuse it
                by_norm[n] = -1.0
                continue
            by_norm[n] = length_seconds(f.get("length")) or 0.0
        if all(by_norm.get(n, -1.0) > 0 for n in norms):
            return [by_norm[n] for n in norms]
    return None
