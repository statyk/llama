"""The scheduler (spec "Planning"). Pure: no IO, deterministic for given
inputs; ties break on `rules.tie_rank(seed, slug)`.

Part 1, `fill_block`: choose the shows of one block occurrence so the next
block's first show lands inside its window, in the compromise order of Goals
3: tier 0 (own profile only, landing in window), tier 1 (own shows then fill
from the open pool, landing in window), tier 2 (own shows only, a miss).

Positions are frames: shows follow `start_frame` back to back with
`boundary_frames` between them and `final_boundary_frames` after the last.

Within a tier options rank on the rule violations (`rules.RULES` order,
lexicographic), then on value, then on the tie ranks of their shows in order.
Value is the block's score surplus `sum(score - 1.0)` (1.0 is a never-aired
show) minus `0.5 * |landing - nominal| / max(early, late)`. A surplus rather
than the plan's mean: like the mean it does not favour more shows (a show
adds only what it scores above a never-aired one), and unlike the mean it
gives a continued block's "no more shows" option a value (0) without the
placed shows' scores, which history cannot reproduce (`Recency` keeps only
their latest airing: the placement itself). Tier 1 ranks on the number of
own shows first (fill is the compromise to minimise). Tier 2 ranks on the
distance outside the window first (late beats early on a tie), then
violations, then value.

Search bound (plan, "Builder calls"): singles over every candidate; a pair's
first member from the top `PAIR_FIRSTS` by score among those that can still
land the window, its partner from the candidates whose length lands it
(bisected on the pool sorted by frames), the top `PAIR_PARTNERS` by score;
more than two shows extend a greedy prefix (fewest rule breaks, then highest
score, keeping the landing at or before `hi`) and finish with the pair search.
Tier 1 fills the best `FILL_PREFIXES` own prefixes with up to `MAX_FILL` fill
shows by the same search.

A bounded search is not continuation-closed by itself (a later call with the
first show placed can find an option the first call never looked at), so
`fill_block` runs it once per added show and keeps only each run's first
show: the result is exactly what the live planner, appending one piece per
step, ends up playing."""

import bisect
import heapq
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import NamedTuple
from zoneinfo import ZoneInfo

from transmitter import rules
from transmitter.clock import ClockConfig, Occurrence
from transmitter.errors import PlanError
from transmitter.grid import FRAME_SAMPLES, SAMPLE_RATE
from transmitter.history import Recency
from transmitter.pieces import Piece

PAIR_FIRSTS = 32
PAIR_PARTNERS = 64
NEAR_EACH_SIDE = 32            # pairs just short of / just past the window (tiers 1 and 2)
FILL_PREFIXES = 5
MAX_FILL = 3
_SLICE_SORT_MAX = 4 * PAIR_PARTNERS
_US_PER_FRAME_NUM = FRAME_SAMPLES * 1_000_000      # frame_to_us(f) == f * this // SAMPLE_RATE
_CLEAN = (0, 0, 0, 0)


@dataclass(frozen=True)
class BlockPlan:
    shows: tuple[Piece, ...]          # the shows this call adds (after `placed`)
    fill_from: int | None             # index into `shows` of the first fill show
    fill_cause: str | None            # "pool-short" | "structural"
    tier: int                         # 0 own in window, 1 with fill in window, 2 miss
    landing_frame: int                # where the next block's first show would start
    bends: tuple[str, ...]            # every rule this block's choice bent (RULES order)
    degraded: bool
    show_bends: tuple[tuple[str, ...], ...] = ()
    # per added show: the bends from that show on, i.e. what `bends` is when the
    # block is continued with the shows before it placed


class _C:
    """A candidate show with everything the search reads, computed once per call."""
    __slots__ = ("piece", "slug", "frames", "artist", "year", "md", "pkg", "pref", "last", "tie", "i")

    def __init__(self, piece: Piece, ranges, rec: Recency, seed: int):
        self.piece = piece
        self.slug = piece.slug
        self.frames = piece.frames
        self.artist = piece.artist
        self.year = piece.year
        self.md = piece.month_day
        self.pkg = piece.package
        self.pref = rules.year_weight(self.year, ranges)
        self.last = rec.last_aired_us(self.pkg) if self.pkg is not None else None
        self.tie = rules.tie_rank(seed, self.slug)
        self.i = -1


class _Seq:
    """A sequence of added shows: where the next show would start, the rule
    counts so far, each show's surplus term (score - 1.0) and the per-date
    artists added."""
    __slots__ = ("shows", "next", "viol", "terms", "prev", "pkgs", "day_a", "day_ay")

    def __init__(self, shows, nxt, viol, terms, prev, pkgs, day_a, day_ay):
        self.shows = shows
        self.next = nxt
        self.viol = viol
        self.terms = terms
        self.prev = prev
        self.pkgs = pkgs
        self.day_a = day_a
        self.day_ay = day_ay


def _tie(shows) -> tuple[str, ...]:
    """Tie ranks in order: the first show's, then (for options sharing it) the next."""
    return tuple(c.tie for c in shows)


class _Tier:
    """The best option offered so far, keyed (pre, violations, -value, ties),
    with value and ties computed only when the cheaper parts tie; and, per
    rule, whether any option offered kept it."""
    __slots__ = ("pre", "viol", "value", "tie", "best", "kept")

    def __init__(self):
        self.pre = self.viol = self.value = self.tie = self.best = None
        self.kept = [False, False, False, False]

    def offer(self, ctx: "_Ctx", pre: tuple, viol: tuple, seq_shows: tuple, extra: tuple,
              terms: tuple, landing: int, fill_from: int | None) -> None:
        k = self.kept
        if not viol[0]:
            k[0] = True
        if not viol[1]:
            k[1] = True
        if not viol[2]:
            k[2] = True
        if not viol[3]:
            k[3] = True
        shows = tie = None
        if self.best is not None:
            head, best_head = (pre, viol), (self.pre, self.viol)
            if head > best_head:
                return
            value = ctx.value(terms, landing)
            if head == best_head:
                if value < self.value:
                    return
                if value == self.value:
                    shows = seq_shows + extra
                    tie = _tie(shows)
                    if tie >= self.tie:
                        return
        else:
            value = ctx.value(terms, landing)
        if shows is None:
            shows = seq_shows + extra
            tie = _tie(shows)
        self.pre, self.viol, self.value, self.tie = pre, viol, value, tie
        self.best = (shows, landing, viol, fill_from)

    def bends(self) -> tuple[str, ...]:
        viol = self.best[2]
        return tuple(r for i, r in enumerate(rules.RULES) if viol[i] and self.kept[i])


class _Ctx:
    def __init__(self, occ: Occurrence, next_occ: Occurrence, rec: Recency, clock: ClockConfig,
                 epoch_us: int, seed: int, boundary: int, final: int, dates: dict | None = None):
        self.tz = ZoneInfo(clock.timezone)
        self.epoch = epoch_us
        self.rec = rec
        self.days = rules.RecDays(rec)
        self.gap = clock.rotation.concert_gap_days
        self.otd = rules.on_this_day_weight(occ, clock)
        self.ranges = rules.year_ranges(occ)
        self.seed = seed
        self.boundary = boundary
        self.final = final
        self.nominal = next_occ.nominal_us
        self.denom = max(next_occ.nominal_us - next_occ.lo_us, next_occ.hi_us - next_occ.nominal_us, 1)
        # the window in frames: LO is the first frame at or after lo, HI the last at or before hi
        self.LO = -((-(next_occ.lo_us - epoch_us) * SAMPLE_RATE) // _US_PER_FRAME_NUM)
        self.HI = ((next_occ.hi_us - epoch_us + 1) * SAMPLE_RATE - 1) // _US_PER_FRAME_NUM
        self._dates: dict[int, tuple[date, str]] = {} if dates is None else dates

    def at_us(self, frame: int) -> int:
        return self.epoch + frame * _US_PER_FRAME_NUM // SAMPLE_RATE

    def day(self, frame: int) -> tuple[int, date, str]:
        us = self.at_us(frame)
        hit = self._dates.get(us)
        if hit is None:
            d = rules.local_date(us, self.tz)
            hit = (d, f"{d.month:02d}-{d.day:02d}")
            self._dates[us] = hit
        return us, hit[0], hit[1]

    def cand(self, piece: Piece) -> _C:
        return _C(piece, self.ranges, self.rec, self.seed)

    def score(self, c: _C, us: int, md: str) -> float:
        s = rules.recency_term(c.last, us, self.gap) + c.pref
        if c.md is not None and c.md == md:
            s += self.otd
        return s

    def viol(self, c: _C, us: int, d: date, seq: _Seq) -> tuple[int, int, int, int]:
        a = c.artist
        adj = 1 if a and a == seq.prev else 0
        gap = 1 if (self.gap > 0 and c.pkg is not None
                    and (c.pkg in seq.pkgs or rules.gap_hit(c.last, us, self.gap))) else 0
        day = era = 0
        if a:
            ra, ray = self.days.get(d)
            if a in ra or a in seq.day_a.get(d, ()):
                day = 1
            if c.year is not None and ((a, c.year) in ray or (a, c.year) in seq.day_ay.get(d, ())):
                era = 1
        return adj, gap, day, era

    def base(self, start_frame: int, prev: str | None) -> _Seq:
        return _Seq((), start_frame, _CLEAN, (), prev, frozenset(), {}, {})

    def extend(self, seq: _Seq, c: _C) -> _Seq:
        us, d, md = self.day(seq.next)
        v = self.viol(c, us, d, seq)
        day_a, day_ay = dict(seq.day_a), dict(seq.day_ay)
        if c.artist:
            day_a[d] = day_a.get(d, frozenset()) | {c.artist}
            if c.year is not None:
                day_ay[d] = day_ay.get(d, frozenset()) | {(c.artist, c.year)}
        pv = seq.viol
        return _Seq(seq.shows + (c,), seq.next + c.frames + self.boundary,
                    (pv[0] + v[0], pv[1] + v[1], pv[2] + v[2], pv[3] + v[3]),
                    seq.terms + (self.score(c, us, md) - 1.0,), c.artist,
                    seq.pkgs | {c.pkg} if c.pkg is not None else seq.pkgs, day_a, day_ay)

    def landing(self, seq: _Seq) -> int:
        return seq.next - self.boundary + self.final

    def value(self, terms: tuple[float, ...], landing: int) -> float:
        """Surplus minus the distance term. `fsum` is exact then rounded, so
        options whose terms are the same multiset (a pair and its swap) tie
        exactly, whatever the order of summing, in a first call and in its
        continuation alike."""
        return math.fsum(terms) - 0.5 * abs(self.at_us(landing) - self.nominal) / self.denom

    def distance(self, landing: int) -> tuple[int, int]:
        """(frames outside the window, 0 late / 1 early or inside)."""
        if landing > self.HI:
            return landing - self.HI, 0
        if landing < self.LO:
            return self.LO - landing, 1
        return 0, 1


class _Pool:
    """Candidates sorted by frames once, for bisecting a landing range; the
    rankings computed at each slot are shared by every run of one call."""

    def __init__(self, cands: list[_C]):
        self.cands = sorted(cands, key=lambda c: (c.frames, c.tie))
        for i, c in enumerate(self.cands):
            c.i = i
        self.frames = [c.frames for c in self.cands]
        self.rankings: dict[tuple[int, frozenset], tuple[list[int], list[float], list[int]]] = {}

    def __bool__(self) -> bool:
        return bool(self.cands)


class _Search:
    """Enumerates `base + 1..kmax` shows from one pool, skipping `excluded`,
    and offers each option to a callback:
    `offer(seq_shows, extra, viol, terms, landing)`."""

    def __init__(self, ctx: _Ctx, pool: _Pool, excluded: frozenset[str]):
        self.ctx = ctx
        self.pool = pool
        self.excluded = excluded

    def _taken(self, seq: _Seq) -> frozenset[str]:
        return self.excluded.union(c.slug for c in seq.shows)

    def ranking(self, seq: _Seq) -> tuple[list[int], list[float], list[int]]:
        """Pool indices of the available candidates by score at the next slot
        (best first), every candidate's score there, and each index's rank.
        A candidate's score depends only on the slot (history changes between
        runs only for pieces that are taken), so runs share it."""
        taken = self._taken(seq)
        key = (seq.next, taken)
        hit = self.pool.rankings.get(key)
        if hit is not None:
            return hit
        ctx = self.ctx
        us, _, md = ctx.day(seq.next)
        cands = self.pool.cands
        scores = [0.0] * len(cands)
        avail = []
        for c in cands:
            if c.slug in taken:
                continue
            scores[c.i] = ctx.score(c, us, md)
            avail.append(c.i)
        order = sorted(avail, key=lambda i: (-scores[i], cands[i].tie))
        rank = [len(cands)] * len(cands)
        for r, i in enumerate(order):
            rank[i] = r
        out = (order, scores, rank)
        self.pool.rankings[key] = out
        return out

    def singles(self, seq: _Seq, offer) -> None:
        ctx = self.ctx
        us, d, md = ctx.day(seq.next)
        taken = self._taken(seq)
        pv = seq.viol
        for c in self.pool.cands:
            if c.slug in taken:
                continue
            v = ctx.viol(c, us, d, seq)
            offer(seq.shows, (c,), (pv[0] + v[0], pv[1] + v[1], pv[2] + v[2], pv[3] + v[3]),
                  seq.terms + (ctx.score(c, us, md) - 1.0,), seq.next + c.frames + ctx.final)

    def _feasible_first(self, seq: _Seq, c: _C) -> bool:
        ctx, frames = self.ctx, self.pool.frames
        n2 = seq.next + c.frames + ctx.boundary
        i0 = bisect.bisect_left(frames, ctx.LO - n2 - ctx.final)
        i1 = bisect.bisect_right(frames, ctx.HI - n2 - ctx.final)
        if i1 - i0 > 1:
            return True
        return i1 - i0 == 1 and self.pool.cands[i0] is not c

    def firsts(self, seq: _Seq, window: bool) -> list[_C]:
        order, _, _ = self.ranking(seq)
        cands = self.pool.cands
        out = []
        for i in order:
            c = cands[i]
            if window and not self._feasible_first(seq, c):
                continue
            out.append(c)
            if len(out) == PAIR_FIRSTS:
                break
        return out

    def pairs(self, seq: _Seq, offer, window: bool) -> None:
        ctx, pool = self.ctx, self.pool
        frames = pool.frames
        order, scores, rank = self.ranking(seq)
        us1, d1, _ = ctx.day(seq.next)
        taken = self._taken(seq)
        pv = seq.viol
        gap_on = ctx.gap > 0
        for f in self.firsts(seq, window):
            n2 = seq.next + f.frames + ctx.boundary
            i0 = bisect.bisect_left(frames, ctx.LO - n2 - ctx.final)
            i1 = bisect.bisect_right(frames, ctx.HI - n2 - ctx.final)
            if window:
                partners = self._top_in_range(i0, i1, order, rank, taken, f)
            else:
                partners = self._near(i0, i1, taken, f)
            if not partners:
                continue
            v1 = ctx.viol(f, us1, d1, seq)
            t1 = seq.terms + (scores[f.i] - 1.0,)
            us2, d2, md2 = ctx.day(n2)
            # the state after f, inline: its artist, package and per-date artists
            fa, fy, fp = f.artist, f.year, f.pkg
            ra2, ray2 = ctx.days.get(d2)
            sa2 = seq.day_a.get(d2, frozenset())
            say2 = seq.day_ay.get(d2, frozenset())
            same_day = d2 == d1
            base_shows = seq.shows + (f,)
            b0, b1, b2, b3 = pv[0] + v1[0], pv[1] + v1[1], pv[2] + v1[2], pv[3] + v1[3]
            for g in partners:
                a = g.artist
                adj = 1 if a and a == fa else 0
                gp = 1 if (gap_on and g.pkg is not None
                           and (g.pkg == fp or g.pkg in seq.pkgs or rules.gap_hit(g.last, us2, ctx.gap))) else 0
                day = era = 0
                if a:
                    if a in ra2 or a in sa2 or (same_day and a == fa):
                        day = 1
                    y = g.year
                    if y is not None and ((a, y) in ray2 or (a, y) in say2 or (same_day and a == fa and y == fy)):
                        era = 1
                s = rules.recency_term(g.last, us2, ctx.gap) + g.pref
                if g.md is not None and g.md == md2:
                    s += ctx.otd
                offer(base_shows, (g,), (b0 + adj, b1 + gp, b2 + day, b3 + era), t1 + (s - 1.0,),
                      n2 + g.frames + ctx.final)

    def _top_in_range(self, i0, i1, order, rank, taken, f) -> list[_C]:
        cands = self.pool.cands
        out: list[_C] = []
        if i1 - i0 <= _SLICE_SORT_MAX:
            for i in sorted(range(i0, i1), key=rank.__getitem__):
                c = cands[i]
                if c is f or c.slug in taken:
                    continue
                out.append(c)
                if len(out) == PAIR_PARTNERS:
                    break
            return out
        for i in order:                    # `order` holds only untaken candidates
            if i0 <= i < i1:
                c = cands[i]
                if c is f:
                    continue
                out.append(c)
                if len(out) == PAIR_PARTNERS:
                    break
        return out

    def _near(self, i0, i1, taken, f) -> list[_C]:
        cands = self.pool.cands
        out: list[_C] = []
        n, i = 0, i0 - 1
        while i >= 0 and n < NEAR_EACH_SIDE:
            c = cands[i]
            if c is not f and c.slug not in taken:
                out.append(c)
                n += 1
            i -= 1
        n, i = 0, i1
        while i < len(cands) and n < NEAR_EACH_SIDE:
            c = cands[i]
            if c is not f and c.slug not in taken:
                out.append(c)
                n += 1
            i += 1
        return out

    def chain_pick(self, seq: _Seq) -> _C | None:
        """The greedy extension: among the candidates whose addition keeps the
        landing at or before hi, the fewest rule violations at this position
        (lexicographic), then the highest score. A score-only greedy walks into
        a same-artist step that every longer option then inherits."""
        ctx = self.ctx
        room = ctx.HI - seq.next - ctx.final
        order, _, _ = self.ranking(seq)
        cands = self.pool.cands
        us, d, _ = ctx.day(seq.next)
        best, best_v = None, None
        for i in order:                    # best score first: the first clean one wins
            c = cands[i]
            if c.frames > room:
                continue
            v = ctx.viol(c, us, d, seq)
            if best_v is None or v < best_v:
                best, best_v = c, v
                if v == _CLEAN:
                    break
        return best

    def run(self, base: _Seq, kmax: int | None, offer, window: bool,
            chain: list[_Seq] | None = None) -> list[_Seq]:
        """Singles, then for k = 2.. the pair search after the greedy chain of
        k - 2 shows. Returns the chain (base first); pass it back to reuse it."""
        chain = chain if chain is not None else [base]
        if kmax is not None and kmax < 1:
            return chain
        self.singles(base, offer)
        k = 2
        while kmax is None or k <= kmax:
            if len(chain) < k - 1:
                c = self.chain_pick(chain[-1])
                if c is None:
                    break
                chain.append(self.ctx.extend(chain[-1], c))
            self.pairs(chain[k - 2], offer, window)
            k += 1
        return chain


def _dedupe(pool: Sequence[Piece]) -> list[Piece]:
    seen: set[str] = set()
    out = []
    for p in pool:
        if p.slug not in seen:
            seen.add(p.slug)
            out.append(p)
    return out


def _excluded(pool: list[Piece], placed: frozenset[str], used: frozenset[str]) -> frozenset[str]:
    """No piece twice in one block; `used` is dropped only while others remain."""
    if any(p.slug not in placed and p.slug not in used for p in pool):
        return placed | used
    return placed


def _has_fill(own_slugs: frozenset[str], placed: tuple) -> bool:
    """A placed show outside the own pool: the block is already into its fill."""
    return any(p.slug not in own_slugs for p in placed)


class _Step(NamedTuple):
    shows: tuple            # of _C
    tier: int
    fill_from: int | None
    landing: int
    bends: tuple[str, ...]


def fill_block(occ: Occurrence, next_occ: Occurrence, *, start_frame: int, placed: Sequence[Piece],
               own_pool: Sequence[Piece], open_pool: Sequence[Piece], boundary_frames: int,
               final_boundary_frames: int, prev_artist: str | None, rec: Recency, clock: ClockConfig,
               epoch_us: int, seed: int, used: frozenset[str]) -> BlockPlan:
    """Choose the shows this occurrence adds.

    `placed` are its shows already in the persisted plan: a fixed prefix that
    counts toward `max_shows`, as own shows, and supplies the previous artist;
    `rec` must already include them. `start_frame` is where the first show
    this call adds would start (after `placed` and its boundary); with no show
    added the block lands at `start_frame - boundary_frames +
    final_boundary_frames`. `BlockPlan.shows` holds only the added shows.

    Continuation-closed: `fill_block(placed=P + shows[:i])` from the matching
    frame, with `rec` holding those shows at their starts, returns `shows[i:]`
    (and `show_bends[i:]`)."""
    placed = tuple(placed)
    own_all = _dedupe(own_pool)
    degraded = not occ.is_open and not own_all
    if degraded:
        own_all = _dedupe(open_pool)
    if not own_all and not placed:
        raise PlanError("no eligible packages to plan")
    profile_block = not occ.is_open and not degraded
    own_slugs = frozenset(p.slug for p in own_all)
    fill_all = [p for p in _dedupe(open_pool) if p.slug not in own_slugs] if profile_block else []

    dates: dict = {}
    ctx = _Ctx(occ, next_occ, rec, clock, epoch_us, seed, boundary_frames, final_boundary_frames, dates)
    # the block's own start: every run, and every live continuation, judges the cause from it
    block_start = start_frame - sum(p.frames + boundary_frames for p in placed)
    cause = _fill_cause(ctx, own_all, occ.max_shows, block_start) if profile_block else None
    own = _Pool([ctx.cand(p) for p in own_all])
    fill = _Pool([ctx.cand(p) for p in fill_all])
    steps: list[_Step] = []
    start = start_frame
    for _ in range(len(own_all) + len(fill_all) + 1):     # one show per run, never twice
        step = _choose(ctx, occ, own, own_all, fill, fill_all, placed, start, prev_artist, used, degraded,
                       profile_block and _has_fill(own_slugs, placed))
        steps.append(step)
        if not step.shows:
            break
        first = step.shows[0]
        us, d, _ = ctx.day(start)
        rec = rec.with_piece(first.piece, us, d)
        placed += (first.piece,)
        start += first.frames + boundary_frames
        ctx = _Ctx(occ, next_occ, rec, clock, epoch_us, seed, boundary_frames, final_boundary_frames, dates)
    else:
        raise AssertionError("fill_block did not converge")     # unreachable: shows never repeat

    shows = tuple(s.shows[0].piece for s in steps[:-1])
    fill_from = next((i for i, s in enumerate(steps[:-1]) if s.tier == 1 and s.fill_from == 0), None)
    last = steps[-1]
    if not ctx.LO <= last.landing <= ctx.HI:
        tier = 2
    else:
        tier = 1 if profile_block and _has_fill(own_slugs, placed) else 0
    show_bends: list[tuple[str, ...]] = []
    acc: set[str] = set()
    for s in reversed(steps):
        acc |= set(s.bends)
        show_bends.append(tuple(r for r in rules.RULES if r in acc))
    show_bends.reverse()
    return BlockPlan(shows=shows, fill_from=fill_from,
                     fill_cause=cause if fill_from is not None else None,
                     tier=tier, landing_frame=last.landing, bends=show_bends[0], degraded=degraded,
                     show_bends=tuple(show_bends[:-1]))


def _choose(ctx: _Ctx, occ: Occurrence, own: _Pool, own_all: list[Piece], fill: _Pool,
            fill_all: list[Piece], placed: tuple, start_frame: int, prev_artist: str | None,
            used: frozenset[str], degraded: bool, after_fill: bool) -> _Step:
    """One bounded search: the best option in the first non-empty tier."""
    placed_slugs = frozenset(p.slug for p in placed)
    max_shows = None if degraded else occ.max_shows
    kmax = None if max_shows is None else max(0, max_shows - len(placed))
    if after_fill:
        kmax = 0                      # fill goes at the end of the block: no own show after it
    base = ctx.base(start_frame, placed[-1].artist if placed else prev_artist)
    search = _Search(ctx, own, _excluded(own_all, placed_slugs, used))

    t0 = _Tier()

    def offer_window(seq_shows, extra, viol, terms, landing):
        if ctx.LO <= landing <= ctx.HI:
            t0.offer(ctx, (), viol, seq_shows, extra, terms, landing, None)

    if placed:
        offer_window((), (), _CLEAN, (), ctx.landing(base))
    chain = search.run(base, kmax, offer_window, window=True) if own else [base]
    for seq in chain[1:]:              # the greedy prefixes are options in their own right
        if len(seq.shows) >= 2:
            offer_window(seq.shows, (), seq.viol, seq.terms, ctx.landing(seq))
    if t0.best is not None:
        return _step(t0, 0)

    # nothing lands: own options just short of or just past the window feed
    # tier 1 (as prefixes) and tier 2
    t2 = _Tier()
    prefixes: list[tuple] = []

    def offer_outside(seq_shows, extra, viol, terms, landing):
        if not seq_shows and not extra and not placed:
            return
        t2.offer(ctx, ctx.distance(landing), viol, seq_shows, extra, terms, landing, None)
        if landing < ctx.LO:
            shows = seq_shows + extra
            prefixes.append(((-len(shows),) + viol + (-landing, -math.fsum(terms), _tie(shows)), shows))

    if placed:
        offer_outside((), (), _CLEAN, (), ctx.landing(base))
    if own:
        for seq in chain[1:]:
            if len(seq.shows) >= 2:
                offer_outside(seq.shows, (), seq.viol, seq.terms, ctx.landing(seq))
        search.run(base, kmax, offer_outside, window=False, chain=chain)

    t1 = _Tier()
    if fill and prefixes:
        excluded = _excluded(fill_all, placed_slugs, used)
        for _, shows in heapq.nsmallest(FILL_PREFIXES, prefixes, key=lambda kv: kv[0]):
            seq = base
            for c in shows:
                seq = ctx.extend(seq, c)
            n_own = len(shows)

            def offer_fill(seq_shows, extra, viol, terms, landing, n_own=n_own):
                if ctx.LO <= landing <= ctx.HI:
                    t1.offer(ctx, (-n_own,), viol, seq_shows, extra, terms, landing, n_own)

            _Search(ctx, fill, excluded).run(seq, MAX_FILL, offer_fill, window=True)
    if t1.best is not None:
        return _step(t1, 1)
    return _step(t2, 2)


def _step(tier: _Tier, n: int) -> _Step:
    shows, landing, _, fill_from = tier.best
    return _Step(shows, n, fill_from if n == 1 else None, landing, tier.bends())


def _fill_cause(ctx: _Ctx, own_all: list[Piece], max_shows: int, block_start: int) -> str:
    """"structural" when the max_shows longest shows of the whole own pool (placed
    own shows included), laid out from the block's start, still land before the
    window; else "pool-short" (a pool with fewer than max_shows shows is short)."""
    longest = sorted((p.frames for p in own_all), reverse=True)
    if max_shows > len(longest):
        return "pool-short"
    landing = block_start + sum(longest[:max_shows]) + (max_shows - 1) * ctx.boundary + ctx.final
    return "structural" if landing < ctx.LO else "pool-short"


def _sequence_violations(occ: Occurrence, rec: Recency, clock: ClockConfig, epoch_us: int,
                         seq: Sequence[Piece], prev_artist: str | None, start_frame: int,
                         boundary_frames: int) -> tuple[int, int, int, int]:
    """The search's own rule counts for `seq` laid out from `start_frame`
    (tests hold them equal to `rules.violations`)."""
    ctx = _Ctx(occ, occ, rec, clock, epoch_us, 0, boundary_frames, boundary_frames)
    s = ctx.base(start_frame, prev_artist)
    for p in seq:
        s = ctx.extend(s, ctx.cand(p))
    return s.viol
