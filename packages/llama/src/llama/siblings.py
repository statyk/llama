"""Duration-sequence alignment of a target tape against a TAGGED SIBLING
recording of the same performance, and the per-row title transfer it licenses.

This is not `correspondence.py` (tape against the canonical setlist) and not
`structure.align()` (tape against parsed setlist items). It is tape against
TAPE: two tapers' recordings of one show, aligned on nothing but per-track
durations, so that a tape whose files carry no titles can borrow the other's.

PURE by mandate. No IO, no LLM, no imports from `stages/`. Fetching sibling
metadata, `filter_files`, `clean_tag_titles` and the dedupe all stay in
`gather`; this module takes two loaded duration/title lists and returns rows
plus diagnostics.

Two properties of the cost model that callers and future editors keep
rediscovering, recorded here once:

- **Skipping a track and absorbing it into a neighbouring pairing cost the
  same.** Under an L1 timeline cost, skipping track `t` costs `dur(t)`, and
  merging `t` into the pairing beside it costs `|dur(t) + dur(neighbour) -
  dur(donor)|`, which equals `dur(t)` plus the same jitter whenever the
  neighbour is the longer side -- and is strictly CHEAPER when it is the
  shorter one. So a `no sibling track` row is produced only where absorption
  is structurally illegal (`min(a, b) == 1` bars a 2:2 op; `MAX_MERGE` bars a
  4:1 one) or where the neighbour is already spoken for. Everywhere else the
  DP reports the absorption -- which is the conservative outcome, since a
  multi-file pairing declines every row it covers rather than shipping a
  title.
- **The exclusion penalty prices a pairing, not the alignment.** It is how
  much the best GLOBAL explanation degrades when that one pairing is barred.
  It says nothing about whether the donor is the right performance at all
  (control A5: a wholly unrelated tape passes it); that question belongs to
  the anchor-agreement guard layered on top of these rows.

See `docs/superpowers/specs/2026-09-02-sibling-title-transfer-design.md`.
"""
from __future__ import annotations

from dataclasses import dataclass

from llama.setlist import MAX_TITLE_LEN, is_junk_title
from llama.structure import fuzzy_norm_title
from llama.titles import is_real_title

INF = float("inf")

# ---------------------------------------------------------------------------
# DO NOT RETUNE. These four were fixed a priori -- before any score was read --
# and were never swept. Every measurement in
# `docs/superpowers/2026-09-02-sibling-transfer-evidence.md` was taken at these
# values, so changing any one of them invalidates ALL of them, not just the
# table it appears in. Same class as the tail-guard constants
# (`structure.TAIL_GUARD_ITEMS`/`TRACKS_REMAINING`/`MAX_SKIP`), the junk
# duration floor (`junk.SHORT_FRACTION_OF_MEDIAN`) and gather's `_RECOVER_*`.
# ---------------------------------------------------------------------------

# One file of either tape may hold up to 3 of the other tape's songs.
MAX_MERGE = 3

# Dropping a track costs its own duration -- an L1 cost on the timeline, with
# no thumb on the scale either way.
SKIP_COST_MULT = 1.0

# Barring a pairing must make the best global explanation worse by at least
# this many seconds before the pairing counts as evidence. Set from the
# MECHANISM, not from results: boundary drift between two tapes of one show is
# ~4 s, and the shortest plausible song is ~90 s (`junk.MIN_PLAUSIBLE_SEC`), so
# a real pairing should be worth far more than jitter while a one-song shift
# should cost about a song.
MIN_EXCLUSION_PENALTY = 60.0

# Whole-tape validity: at least this fraction of the target's tracks must be
# paired with donor tracks at all. Below it the two tapes are not plausibly the
# same performance and no row is proposed.
MIN_MATCH_FRACTION = 0.80


@dataclass(frozen=True)
class DonorTape:
    """A tagged sibling recording, already filtered and cleaned by `gather`.

    `names`, `durations` and `titles` are parallel and must be the same
    length; `durations` are seconds (the caller guarantees none missing, and
    `propose_rows` re-checks rather than trusting it); `titles` are cleaned tag
    titles with `""` standing for "this track has no usable tag".
    """

    identifier: str
    names: list[str]
    durations: list[float]
    titles: list[str]


@dataclass(frozen=True)
class SiblingRow:
    """One target track's proposed transfer.

    SPAN CONVENTION -- pinned by test, and load-bearing for the guard in the
    next layer, which brackets fill runs by these spans:

    - `track` is the 1-BASED target track number, matching `models.Track.track`
      and everything the operator ever sees.
    - `donor_span` is a HALF-OPEN range over 0-BASED donor track indices,
      `[j0, j1)` -- deliberately the same shape `structure.anchor_spans` and
      `structure.gap_span` return over canonical items, with the donor's track
      sequence playing the canonical's role, so the guard can reuse them
      without a conversion step. `donor_span is None` means no donor track was
      paired with this target track at all.
    - A merged pairing (one target file holding donor tracks 3 and 4) has span
      `(2, 4)`, and its `proposed` is the `"A > B"` join of those donor titles.
    - A SPLIT pairing (one donor song spread over several target files) gives
      every one of those target rows the SAME `donor_span` and the same
      `residual_sec`. Spans therefore do not partition the donor whenever a
      split is present -- do not sum them.

    `penalty_sec` is the exclusion penalty: how much the best global alignment
    degrades when this pairing is barred. `inf` would mean "forced" (no rival
    explanation exists); it is structurally unreachable, because skipping both
    sides always leaves a feasible alignment.

    A declined row may still carry a `proposed` title: `weak evidence` keeps it
    so the operator path can render what the DP thought, while the rows that
    have no title to offer (no donor track, an untitled donor, a failed hygiene
    check, a split song) carry `None`.
    """

    track: int
    proposed: str | None
    donor_span: tuple[int, int] | None
    residual_sec: float
    penalty_sec: float
    verdict: str
    reason: str = ""


def _hygienic_title(title: str, metadata_norms: set[str]) -> bool:
    """A donor tag fit to become a shipped title.

    The same predicate family as `structure._hygienic`, composed from the same
    imported functions -- never a reimplementation of any of them. The
    composition is pinned equal to `structure._hygienic`'s by
    `test_hygiene_matches_structures_own_predicate_exactly`, because a second
    definition that drifts from the first is invisible.

    No `aliases` here, deliberately, for `_hygienic`'s reason: `metadata_norms`
    is built aliaslessly by gather's `_place_norms`/`_date_norms`, so threading
    aliases into only this side would break the comparison's symmetry.
    """
    t = title.strip()
    return (bool(t) and is_real_title(t) and not is_junk_title(t)
            and len(t) <= MAX_TITLE_LEN and not t.endswith(":")
            and fuzzy_norm_title(t) not in metadata_norms)


def _prefix(xs: list[float]) -> list[float]:
    out = [0.0]
    for x in xs:
        out.append(out[-1] + x)
    return out


def align_durations(target: list[float], donor: list[float],
                    forbid: tuple | None = None) -> tuple[float, list[tuple]]:
    """Monotone alignment of two duration sequences.

    Ops: `a` target tracks against `b` donor tracks with `min(a, b) == 1` and
    `max(a, b) <= MAX_MERGE`, at cost `|Σa − Σb|`; or a skip on either side at
    cost = the skipped duration. Merges, splits, filler on either side and
    different track counts are all representable.

    Returns `(cost, ops)`, each op a half-open `(i0, i1, j0, j1)`; `j0 == j1`
    is a target-side skip and `i0 == i1` a donor-side one. The ops tile both
    sequences end to end, so they can be walked as a partition.

    `forbid` bars one exact op, which is how a pairing is priced: re-solve
    without it and the cost difference is the pairing's exclusion penalty.

    Ties are broken by exploration order, not by a rule. Where a merge and a
    skip explain a track equally well (the common case -- see the module
    docstring) this reports the merge.
    """
    n, m = len(target), len(donor)
    pt, ps = _prefix(target), _prefix(donor)
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    bk: list[list[tuple | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            cur = dp[i][j]
            if cur == INF:
                continue
            if i < n:                                   # skip a target track
                op = (i, i + 1, j, j)
                cost = cur + target[i] * SKIP_COST_MULT
                if op != forbid and cost < dp[i + 1][j]:
                    dp[i + 1][j] = cost
                    bk[i + 1][j] = (i, j, op)
            if j < m:                                   # skip a donor track
                op = (i, i, j, j + 1)
                cost = cur + donor[j] * SKIP_COST_MULT
                if op != forbid and cost < dp[i][j + 1]:
                    dp[i][j + 1] = cost
                    bk[i][j + 1] = (i, j, op)
            for a in range(1, MAX_MERGE + 1):
                for b in range(1, MAX_MERGE + 1):
                    if min(a, b) != 1 or i + a > n or j + b > m:
                        continue
                    op = (i, i + a, j, j + b)
                    if op == forbid:
                        continue
                    cost = cur + abs((pt[i + a] - pt[i]) - (ps[j + b] - ps[j]))
                    if cost < dp[i + a][j + b]:
                        dp[i + a][j + b] = cost
                        bk[i + a][j + b] = (i, j, op)
    if dp[n][m] == INF:
        return INF, []
    ops: list[tuple] = []
    i, j = n, m
    while (i, j) != (0, 0):
        step = bk[i][j]
        assert step is not None
        i, j, op = step
        ops.append(op)
    return dp[n][m], list(reversed(ops))


def propose_rows(target_durs: list[float], donor: DonorTape, *,
                 metadata_norms: set[str]) -> tuple[list[SiblingRow] | None, dict]:
    """Align `target_durs` against `donor` and propose one row per target track.

    Returns `(rows, diagnostics)`, or `(None, diagnostics)` when a whole-tape
    precondition fails -- and the preconditions are exactly the STRUCTURAL
    ones. A missing duration corrupts the whole DP and too few matched tracks
    means the tapes are not the same performance; both are validity, not
    evidence.

    There is deliberately NO whole-donor tag-fraction gate. An untitled donor
    track declines its own row and nothing else: gates on evidence are
    per-item, never per-donor (the design's standing principle, and the third
    time this project has had to relearn it -- an 86%-tagged sibling refused
    wholesale hid five correct titles).

    Adoption here is per-row evidence and hygiene only. Whether a pair may ship
    WITHOUT a human is decided above this module, by anchor agreement against
    the target's own surviving tags -- the one check that is not
    self-referential.
    """
    diag: dict = {"identifier": donor.identifier}
    if not target_durs or not donor.durations:
        return None, {**diag, "decline": "empty tape"}
    if not (len(donor.durations) == len(donor.titles) == len(donor.names)):
        return None, {**diag, "decline": "donor track fields disagree in length"}
    if not all(d > 0 for d in target_durs) or not all(d > 0 for d in donor.durations):
        return None, {**diag, "decline": "missing per-track durations"}

    cost, ops = align_durations(target_durs, donor.durations)
    if cost == INF:
        return None, {**diag, "decline": "no legal alignment"}
    diag["cost"] = cost
    diag["ops"] = ops
    matched = sum(i1 - i0 for (i0, i1, j0, j1) in ops if i1 > i0 and j1 > j0)
    diag["match_fraction"] = matched / len(target_durs)
    if diag["match_fraction"] < MIN_MATCH_FRACTION:
        return None, {**diag,
                      "decline": f"only {diag['match_fraction']:.0%} of tracks matched"}

    rows: list[SiblingRow] = []
    for (i0, i1, j0, j1) in ops:
        if j1 == j0:                       # target track(s) with no donor track
            for i in range(i0, i1):
                rows.append(SiblingRow(i + 1, None, None, 0.0, 0.0,
                                       "decline", "no sibling track"))
            continue
        if i1 == i0:                       # donor track with no target track
            continue
        alt, _ = align_durations(target_durs, donor.durations,
                                 forbid=(i0, i1, j0, j1))
        penalty = (alt - cost) if alt != INF else INF
        residual = abs(sum(target_durs[i0:i1]) - sum(donor.durations[j0:j1]))
        span = (j0, j1)
        titles = [donor.titles[j] for j in range(j0, j1)]

        if i1 - i0 > 1:                    # one donor song split across files
            for i in range(i0, i1):
                rows.append(SiblingRow(i + 1, None, span, residual, penalty,
                                       "decline",
                                       "sibling song split across target files"))
            continue

        proposed = " > ".join(t.strip().rstrip(">").strip() for t in titles)
        if not all(t.strip() and is_real_title(t.strip()) for t in titles):
            rows.append(SiblingRow(i0 + 1, None, span, residual, penalty,
                                   "decline", "sibling track untitled"))
        elif not all(_hygienic_title(t, metadata_norms) for t in titles):
            rows.append(SiblingRow(i0 + 1, None, span, residual, penalty,
                                   "decline", "sibling title fails hygiene"))
        elif penalty < MIN_EXCLUSION_PENALTY:
            rows.append(SiblingRow(i0 + 1, proposed, span, residual, penalty,
                                   "decline",
                                   f"weak evidence (penalty {penalty:.0f}s)"))
        else:
            rows.append(SiblingRow(i0 + 1, proposed, span, residual, penalty,
                                   "adopt"))
    rows.sort(key=lambda r: r.track)
    return rows, diag
