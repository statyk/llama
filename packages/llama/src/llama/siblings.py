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

from dataclasses import dataclass, replace

from llama.structure import (
    gap_span,
    hygienic_title,
    loosely_same_title,
    unresolved_runs,
)
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


def _all_present(durations) -> bool:
    """Every duration is a real, positive number.

    The `isinstance` arm is NOT belt-and-braces. A missing duration reaches
    this module as `None` -- that is exactly how `models.Track.duration_sec:
    float | None` spells "the item's metadata had no length for this file" --
    and gather (Task 5) feeds these lists straight off `Track` objects. A bare
    `d > 0` raises `TypeError` on `None` instead of declining, i.e. one
    untimed file would crash the stage rather than skip the donor.
    `float("nan")` also fails this, via `> 0`.
    """
    return all(isinstance(d, (int, float)) and d > 0 for d in durations)


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
        # UNREACHABLE from any input, and kept for the same reason as the
        # `inf` penalty the row model documents: skips are always legal, so
        # some alignment always exists and `dp[n][m]` is always finite. The
        # branch states the contract rather than guarding a real case.
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
    if not (_all_present(target_durs) and _all_present(donor.durations)):
        return None, {**diag, "decline": "missing per-track durations"}

    cost, ops = align_durations(target_durs, donor.durations)
    if cost == INF:                    # unreachable; see `align_durations`
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
        elif not all(hygienic_title(t, metadata_norms) for t in titles):
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


# ===========================================================================
# The guards. Layer 1 (`rate_alignment`) rates the whole pair; layer 2
# (`cplus_filter`) gates it run by run. Both live here rather than in gather
# so they stay pure and testable; gather (Task 5) is what calls them.
# ===========================================================================

# ---------------------------------------------------------------------------
# DO NOT RETUNE -- same class as the four above, and for a sharper reason:
# every table in `docs/superpowers/2026-09-02-sibling-transfer-evidence.md`
# was taken AT these three values, under guard shape C+, with
# `structure.loosely_same_title` as the comparator. Changing any one of them
# does not adjust a number, it invalidates the sweep that chose all of them.
# ---------------------------------------------------------------------------

# Anchor agreement at or above which a pair may ship without a human. The band
# sweep's knee: 0.80 is the first cut whose admitted MARGINAL band is not
# dominated by error (the 0.65-0.80 band admits ~5 more titles per rep at a
# 26.5% marginal error rate).
AUTO = 0.80

# Below this the pair is declined outright -- not even rendered as a proposal.
# A failed guard is evidence of a BAD ALIGNMENT, not weak evidence of a good
# one: marginal error is 68-99% below 0.30 and ~40% from 0.30 to 0.50.
FLOOR = 0.50

# Anchors (COUNT OF TARGET TRACKS, not runs or donors) required before the
# ratio may license automatic adoption. The sweep's break is between 1 and 2;
# 5 forfeits the sparse strata for no measured gain. It stays at 2 rather than
# 1 as the last stop against a pair whose single agreeing anchor brackets
# nothing.
MIN_ANCHORS = 2

# A track title is an ANCHOR only if it came from evidence independent of this
# alignment. `tags` and `sibling-format` are the tape's own metadata;
# `override` is an operator's ruling, the same trust class or stronger. NOT
# `setlist`/`setlist-gap` (the canonical setlist's own text, which says
# nothing about where this tape sits) and not `sibling`/`sibling-align`
# (another alignment's output -- circular).
INDEPENDENT_TITLE_SOURCES = frozenset({"tags", "sibling-format", "override"})


@dataclass(frozen=True)
class Disagreement:
    """An anchor whose own title does not loosely match what the sibling
    proposes for it. `track` is 1-based, as everywhere the operator looks.

    This is the operator band's payload, not decoration: 31% of pairs in
    [FLOOR, AUTO) carry a disagreement where the TAPE is the wrong one, so the
    display shows all three readings (tape / sibling / canonical) and lets a
    human rule.
    """

    track: int
    tape_title: str
    proposed: str


@dataclass(frozen=True)
class GuardResult:
    """Layer 1's reading of one target/donor pair.

    `agreement is None` means the tape has no anchors at all (wholly
    untagged) -- distinct from 0.0, which means it has anchors and they all
    disagree. The first is the phase's trigger case and routes to the
    operator; the second is a wrong alignment and is declined.
    """

    agreement: float | None
    n_anchors: int
    disagreements: list[Disagreement]
    band: str          # "auto" | "operator" | "declined" | "no-anchors"


def _anchor_row(track, row: SiblingRow | None) -> bool:
    """Is this (track, row) pair an anchor: independent evidence about the
    tape, which the DP actually paired with a titled donor track?

    A row the DP left unpaired, or one whose donor track had no usable title,
    offers nothing to agree or disagree WITH -- counting it as a disagreement
    would let an untitled donor drag a correct alignment below FLOOR.
    """
    return (track.title_source in INDEPENDENT_TITLE_SOURCES
            and is_real_title(track.title.strip())
            and row is not None and row.donor_span is not None
            and bool(row.proposed))


def _anchor_agrees(track, row: SiblingRow | None) -> bool:
    """THE definition of an AGREEING anchor -- layer 1 counts them, layer 2
    brackets fill runs with them, and there is one function so the two can
    never drift.

    Composed inline in both places in an earlier cut. Nothing was logically
    duplicated then either, which is exactly the shape of the drift Task 3
    shipped: a change to what "agreement" means in the ratio would silently
    not reach the bracketing.
    """
    return _anchor_row(track, row) and loosely_same_title(track.title, row.proposed)


def rate_alignment(rows: list[SiblingRow], tracks: list) -> GuardResult:
    """Layer 1: rate the pair by anchor agreement and route it to a band.

    Agreement is the fraction of anchors whose own title `loosely_same_title`
    the row's proposal. It is the one check in this module that is NOT
    self-referential -- the exclusion penalty prices a pairing against rival
    explanations of the SAME two tapes, and control A5 showed a wholly
    unrelated tape passing it.

    THE BANDS ARE A PRECEDENCE, NOT A SET OF PREDICATES -- evaluated in this
    order: no anchors, then anchor count, then the ratio clauses. **Fewer than
    MIN_ANCHORS anchors routes to the operator whatever the ratio says**,
    including below FLOOR.

    The overlap that ordering resolves is exactly two cases: zero anchors
    (0/0, undefined -- returned before the division, never inherited from
    float semantics, since a wholly untagged tape is this phase's central
    case), and ONE DISAGREEING anchor, whose ratio is 0.0 and so satisfies
    both `< FLOOR` and `< MIN_ANCHORS`. A ratio strictly between 0 and 1 is
    arithmetically impossible at one anchor, so those two are the whole
    surface.

    Why `operator` and not `declined` for the lone disagreeing anchor, on the
    merits: FLOOR's 68-99% marginal-error basis was measured over pairs with
    >= 2 anchors and DOES NOT EXIST at 1, so declining there would apply a
    threshold whose justification is absent for that population. 24.1% of
    disagreeing anchors are the TAPE being wrong, so one disagreeing anchor is
    near-zero evidence either way; and since neither band adopts, `operator`
    costs a minute of attention while `declined` silently discards a possibly
    correct alignment for exactly the barely-tagged population this phase
    exists to serve. Generalises: a threshold is only valid over the
    population it was measured on.
    """
    by_track = {r.track: r for r in rows}
    n_anchors, agreeing = 0, 0
    disagreements: list[Disagreement] = []
    for pos, track in enumerate(tracks):
        row = by_track.get(pos + 1)
        if not _anchor_row(track, row):
            continue
        n_anchors += 1
        if _anchor_agrees(track, row):
            agreeing += 1
        else:
            disagreements.append(
                Disagreement(pos + 1, track.title.strip(), row.proposed))
    if n_anchors == 0:
        return GuardResult(None, 0, [], "no-anchors")
    agreement = agreeing / n_anchors
    if n_anchors < MIN_ANCHORS:
        band = "operator"
    elif agreement >= AUTO:
        band = "auto"
    elif agreement >= FLOOR:
        band = "operator"
    else:
        band = "declined"
    return GuardResult(agreement, n_anchors, disagreements, band)


def _run_label(lo: int, hi: int) -> str:
    return f"track {lo + 1}" if lo == hi else f"tracks {lo + 1}-{hi + 1}"


def cplus_filter(rows: list[SiblingRow], tracks: list) -> list[SiblingRow]:
    """Layer 2, guard shape C+: demote to `decline` every adopt row sitting in
    a fill run that is not bracketed by agreeing anchors and count-forced
    between them. Returns a new row list; input rows are untouched.

    **C+ GATES THE AUTOMATIC BAND, NEVER THE PROPOSAL DISPLAY** (spec
    invariant 1, quoted): "A wholly untagged tape has no anchors and therefore
    no brackets; applied to the renderer, C+ would show ymsb2005 *nothing* --
    the phase's trigger case destroyed by its own guard. The proposal renders
    every row the DP produced, with residuals and per-run annotations; C+
    decides only what ships without a human." So gather calls this; the
    `--suggest-titles` renderer must not.

    BY REUSE, NOT REINVENTION. Runs come from `structure.unresolved_runs` and
    bracketing from `structure.gap_span` -- the real functions, called, so the
    leading-edge exception and the ABSENT trailing branch are inherited rather
    than restated. A second anchor definition inside the guard whose only job
    is preventing silent adoption would be invisible when it drifted.
    (`structure.anchor_spans` itself does not apply: it binds tracks to
    canonical setlist ITEMS by title matching, whereas here the binding is the
    DP's own duration pairing. Its half-open span SHAPE is what `donor_span`
    reuses, which is what lets `gap_span` be called unconverted.)

    COUNT-FORCING HERE IS WEAKER THAN `adopt_gap_titles`', and its
    justification is measurement, not the upstream mechanism argument (spec
    invariant 2). There the item count comes from the canonical setlist, a
    source independent of the tape, so count-forcing removes all assignment
    freedom. Here the donor span's endpoints are read off the *same alignment
    under test* -- partly self-referential, exactly what the A5 ruling warns
    about. It measured better anyway; do not restate the setlist-gap safety
    argument for it.

    RUNS DECLINE INDIVIDUALLY, each with its own reason. One unbracketed run
    must not sink the pair -- gates on evidence are per-item, never per-donor,
    and a checkerboard is the sweep's DEFAULT admitted outcome (~half of
    admitted tapes decline >= 2 runs).

    Rows on tracks that are not in an unresolved run are left alone: the
    automatic rung fills only `title_source == "unresolved"` tracks, so C+ has
    nothing to say about a track nobody is proposing to change.
    """
    by_track = {r.track: r for r in rows}
    # Agreeing anchors, position -> the half-open DONOR span they occupy, the
    # same shape `anchor_spans` returns over canonical items.
    anchors: dict[int, tuple[int, int]] = {}
    for pos, track in enumerate(tracks):
        row = by_track.get(pos + 1)
        if _anchor_agrees(track, row):
            anchors[pos] = row.donor_span

    demoted: dict[int, str] = {}
    for lo, hi in unresolved_runs(tracks):
        span = gap_span(anchors, lo, hi, len(tracks))
        files = hi - lo + 1
        if span is None:
            reason = f"{_run_label(lo, hi)}: not bracketed by agreeing anchors"
        elif span[1] - span[0] != files:
            reason = (f"{_run_label(lo, hi)}: donor span holds "
                      f"{span[1] - span[0]} tracks for a {files}-file run")
        else:
            continue
        for pos in range(lo, hi + 1):
            demoted[pos + 1] = reason

    return [replace(r, verdict="decline", reason=demoted[r.track])
            if r.verdict == "adopt" and r.track in demoted else r
            for r in rows]
