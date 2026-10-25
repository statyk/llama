"""The scheduler (spec "Planning"). Pure: no IO, deterministic for given
inputs; ties break on `rules.tie_rank(seed, slug)`.

Part 1, `fill_block`: choose the shows of one block occurrence so the next
block's first show lands inside its window, in the compromise order of Goals
3: tier 0 (own profile only, landing in window), tier 1 (own shows then fill
from the open pool, landing in window), tier 2 (own shows only, a miss).
The search itself lives in `transmitter._blocksearch`.

Part 2, `project`: from the persisted plan, the piece pool, the clock and the
rotation history, every block occurrence in turn (shows via `fill_block`'s
runs) with the station IDs and announcements at its boundaries, laid out
exactly; see `project`."""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from zoneinfo import ZoneInfo

from transmitter import rules
from transmitter.announce import Form, ann_id, text_for, two_block_ok
from transmitter._blocksearch import (  # noqa: F401  (re-exported: tests reach these)
    FILL_PREFIXES, MAX_FILL, NEAR_EACH_SIDE, PAIR_FIRSTS, PAIR_PARTNERS, _C, _Ctx, _Pool, _Search, _Seq,
    _Step, _Tier, _choose, _dedupe, _excluded, _fill_cause, _has_fill, _sequence_violations)
from transmitter.clock import ClockConfig, Occurrence, occurrences
from transmitter.errors import PlanError
from transmitter.grid import frame_to_us, iso_to_us
from transmitter.history import Recency
from transmitter.layout import PlanRow
from transmitter.pieces import Piece
from transmitter.station import Show


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


class _BlockRun:
    """`fill_block`'s runs, computed on demand. Run `i` (`step(i)`) is the
    bounded search with the first `i` added shows placed; its `shows[0]` is
    the `i`-th added show, and the first run whose option is empty ends the
    block (its `landing` is the block's). `fill_block` pulls every run; the
    projection pulls only the runs it reads, so re-planning a block from a
    new start costs a search per show rather than the whole remainder.

    Arguments and contract are `fill_block`'s."""

    def __init__(self, occ: Occurrence, next_occ: Occurrence, *, start_frame: int, placed: Sequence[Piece],
                 own_pool: Sequence[Piece], open_pool: Sequence[Piece], boundary_frames: int,
                 final_boundary_frames: int, prev_artist: str | None, rec: Recency, clock: ClockConfig,
                 epoch_us: int, seed: int, used: frozenset[str]):
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
        self.cause = _fill_cause(ctx, own_all, occ.max_shows, block_start) if profile_block else None
        self.degraded = degraded
        self.profile_block = profile_block
        self.own_slugs = own_slugs
        self.steps: list[_Step] = []
        self._starts: list[int] = []
        self.done = False
        self._args = (occ, next_occ, rec, clock, epoch_us, seed, boundary_frames, final_boundary_frames, dates)
        self._own_all, self._fill_all = own_all, fill_all
        self._own = _Pool([ctx.cand(p) for p in own_all])
        self._fill = _Pool([ctx.cand(p) for p in fill_all])
        self._ctx, self._rec, self._placed, self._start = ctx, rec, placed, start_frame
        self._prev_artist, self._used = prev_artist, used
        self._limit = len(own_all) + len(fill_all) + 1     # one show per run, never twice

    @property
    def placed(self) -> tuple[Piece, ...]:
        """The placed shows plus every show added by the runs pulled so far."""
        return self._placed

    @property
    def ctx(self) -> _Ctx:
        return self._ctx

    def _advance(self) -> None:
        if len(self.steps) >= self._limit:
            raise AssertionError("fill_block did not converge")     # unreachable: shows never repeat
        occ, next_occ, _, clock, epoch_us, seed, boundary, final, dates = self._args
        ctx, placed, start = self._ctx, self._placed, self._start
        step = _choose(ctx, occ, self._own, self._own_all, self._fill, self._fill_all, placed, start,
                       self._prev_artist, self._used, self.degraded,
                       self.profile_block and _has_fill(self.own_slugs, placed))
        self.steps.append(step)
        self._starts.append(start)
        if not step.shows:
            self.done = True
            return
        first = step.shows[0]
        us, d, _ = ctx.day(start)
        self._rec = self._rec.with_piece(first.piece, us, d)
        self._placed = placed + (first.piece,)
        self._start = start + first.frames + boundary
        self._ctx = _Ctx(occ, next_occ, self._rec, clock, epoch_us, seed, boundary, final, dates)

    def step(self, i: int) -> _Step | None:
        """Run `i`, or None past the block's end."""
        while len(self.steps) <= i and not self.done:
            self._advance()
        return self.steps[i] if i < len(self.steps) else None

    def start_of(self, i: int) -> int | None:
        """Where run `i`'s first show starts, for a run pulled so far or the next one."""
        if i < len(self._starts):
            return self._starts[i]
        return None if self.done or i > len(self.steps) else self._start

    def complete(self) -> list[_Step]:
        while not self.done:
            self._advance()
        return self.steps

    def is_fill(self, i: int) -> bool:
        """Whether run `i`'s show is a fill show (its option starts with fill)."""
        s = self.step(i)
        return s is not None and bool(s.shows) and s.tier == 1 and s.fill_from == 0


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
    run = _BlockRun(occ, next_occ, start_frame=start_frame, placed=placed, own_pool=own_pool,
                   open_pool=open_pool, boundary_frames=boundary_frames,
                   final_boundary_frames=final_boundary_frames, prev_artist=prev_artist, rec=rec, clock=clock,
                   epoch_us=epoch_us, seed=seed, used=used)
    steps = run.complete()
    ctx, placed = run.ctx, run.placed
    shows = tuple(s.shows[0].piece for s in steps[:-1])
    fill_from = next((i for i, s in enumerate(steps[:-1]) if s.tier == 1 and s.fill_from == 0), None)
    last = steps[-1]
    if not ctx.LO <= last.landing <= ctx.HI:
        tier = 2
    else:
        tier = 1 if run.profile_block and _has_fill(run.own_slugs, placed) else 0
    show_bends: list[tuple[str, ...]] = []
    acc: set[str] = set()
    for s in reversed(steps):
        acc |= set(s.bends)
        show_bends.append(tuple(r for r in rules.RULES if r in acc))
    show_bends.reverse()
    return BlockPlan(shows=shows, fill_from=fill_from,
                     fill_cause=run.cause if fill_from is not None else None,
                     tier=tier, landing_frame=last.landing, bends=show_bends[0], degraded=run.degraded,
                     show_bends=tuple(show_bends[:-1]))


# --- part 2: the projection -------------------------------------------------

EXCLUDE_BEND = "exclude_profiles"
_BEND_ORDER = rules.RULES + (EXCLUDE_BEND,)
_CHUNK_US = 14 * 86_400_000_000


@dataclass(frozen=True, eq=False)
class SchedulerInput:
    """What `project` reads. Never hashed (`Recency` and the clock are not).

    `rows` is the persisted plan in order; `start_frame`/`run_start` place the
    next piece. `rec` is the caller's history: aired rows plus every persisted
    row (`history.recency`); `project` adds only the pieces it projects, never
    a persisted row again. `now_us` decides which persisted show rows are not
    yet aired (their end is after it): those, with the projection's own picks,
    are `used` (no repeat while the pool has others). None counts every
    persisted show row as unaired: a preview from a plan with nothing aired."""
    rows: Sequence[PlanRow]
    start_frame: int
    run_start: bool
    pool: Sequence[Piece]
    clock: ClockConfig
    rec: Recency
    epoch_us: int
    gap_frames: int
    seed: int
    now_us: int | None


@dataclass(frozen=True)
class PlannedPiece:
    """One projected piece. A boundary interstitial carries the occurrence
    (`block`, `nominal_start`) of the show that follows it, so a `next` carries
    X and a `later` the block it plays in.

    `bends` (show pieces): each rule a block bends is written on exactly one of
    its show rows, the one whose own placement bent it (the rules its run bent
    that the run continuing after it does not), and never twice in a block, so
    a sum of `bends` over a block's rows counts each of the block's bends once.
    `exclude_profiles` is written on the block's first show drawn from the
    open pool when `[open] exclude_profiles` was bent."""
    piece: Piece
    start_frame: int
    run_start: bool
    block: str
    nominal_start: str
    role: str                                   # "show" | "id" | "next" | "later"
    miss: bool | None = None                    # set on each occurrence's first show only
    degraded: bool = False
    fill: str | None = None                     # the block plan's fill cause, on fill shows
    bends: tuple[str, ...] = ()
    names: tuple[tuple[str, str], ...] = ()     # announcements: the occurrences named, in order

    @property
    def end_frame(self) -> int:
        return self.start_frame + self.piece.frames


def to_row(pp: PlannedPiece, seq: int) -> PlanRow:
    p = pp.piece
    return PlanRow(seq=seq, slug=p.slug, dir=p.dir, key=p.key, start_frame=pp.start_frame, frames=p.frames,
                   run_start=pp.run_start, kind=p.kind, block=pp.block, nominal_start=pp.nominal_start,
                   role=pp.role, miss=pp.miss, degraded=pp.degraded, fill=pp.fill, bends=pp.bends,
                   names=pp.names, package=p.package)


class _Pools:
    """The pool split by use: shows, the open pool, station IDs, announcements."""

    def __init__(self, pool: Sequence[Piece], clock: ClockConfig, gap: int):
        shows = _dedupe([p for p in pool if p.kind == "show"])
        if not shows:
            raise PlanError("no eligible packages to plan")
        self.shows = shows
        self.by_slug = {p.slug: p for p in shows}
        excluded = set(clock.open.exclude_profiles)
        kept = [p for p in shows if p.profile not in excluded]
        self.open_bent = not kept                # the exclusion bends last, only when nothing is left
        self.open = kept or shows
        clips = sorted((p for p in pool if p.kind == "interstitial"), key=lambda p: p.slug)
        self.ids = _dedupe([p for p in clips if p.role == "id"])
        self.anns: dict[str, Piece] = {}
        for p in clips:
            if p.role == "ann" and p.ann_id:
                self.anns.setdefault(p.ann_id, p)
        # the boundary estimate: one gap with no ID pool, else gap, a typical ID, gap
        self.boundary = gap if not self.ids else 2 * gap + statistics.median_low(p.frames for p in self.ids)
        self._own: dict[str, list[Piece]] = {}

    def own(self, occ: Occurrence) -> list[Piece]:
        if occ.is_open:
            return self.open
        hit = self._own.get(occ.block.name)
        if hit is None:
            profiles = set(occ.block.profiles)
            hit = self._own[occ.block.name] = [p for p in self.shows if p.profile in profiles]
        return hit

    def degraded(self, occ: Occurrence) -> bool:
        return not occ.is_open and not self.own(occ)


class _Occs:
    """The clock's occurrences in order from the first one, expanded on demand."""

    def __init__(self, clock: ClockConfig, first: Occurrence):
        self.clock = clock
        self.seq = [first]
        self.index = {first.key: 0}

    def _grow(self) -> None:
        last = self.seq[-1]
        added = False
        for o in sorted(occurrences(self.clock, last.end_us, last.end_us + _CHUNK_US), key=lambda o: o.nominal_us):
            if o.nominal_us > self.seq[-1].nominal_us:
                self.index[o.key] = len(self.seq)
                self.seq.append(o)
                added = True
        if not added:
            raise AssertionError("the clock yields no occurrence after " + repr(last.key))

    def at(self, i: int) -> Occurrence:
        while len(self.seq) <= i:
            self._grow()
        return self.seq[i]

    def pos(self, occ: Occurrence) -> int:
        return self.index[occ.key]

    def after(self, occ: Occurrence) -> Occurrence:
        return self.at(self.pos(occ) + 1)


_STOP = object()


class _Projection:
    """The projection's state, advanced one piece at a time. Every decision is
    a function of the state alone (the pieces laid out so far, the history
    and `used` they imply, the pool and the clock), which is what a live step
    rebuilds from the persisted rows: so appending the first piece and
    projecting again reproduces the rest."""

    def __init__(self, inp: SchedulerInput):
        self.inp = inp
        self.clock = inp.clock
        self.tz = ZoneInfo(inp.clock.timezone)
        self.gap = inp.gap_frames
        self.pools = _Pools(inp.pool, inp.clock, inp.gap_frames)
        self.B = self.pools.boundary
        rows = list(inp.rows)
        self.rec = inp.rec
        self.used = {r.slug for r in rows
                     if r.kind == "show" and (inp.now_us is None or self._us(r.end_frame) > inp.now_us)}
        last_show = next((r for r in reversed(rows) if r.kind == "show"), None)
        hit = self.pools.by_slug.get(last_show.slug) if last_show is not None else None
        self.prev_artist = hit.artist if hit is not None else None
        self.start = inp.start_frame
        self.run_start = inp.run_start
        self.after_show = not inp.run_start and bool(rows) and rows[-1].kind == "show"

        occ = self._continuing(rows[-1]) if rows else None
        placed_rows = [r for r in rows if r.kind == "show" and (r.block, r.nominal_start) == occ.key] if occ else []
        if occ is None:
            occ = self._entry()
        self.occs = _Occs(self.clock, occ)
        self._enter(occ)
        self.placed = [self._row_piece(r) for r in placed_rows]
        self.placed_bends = {b for r in placed_rows for b in r.bends}
        # persisted own shows the pool no longer lists as own (a moved or vanished package)
        self.extra_own = [p for r, p in zip(placed_rows, self.placed) if r.fill is None and not r.degraded]

    # --- frames, time, pieces ---

    def _us(self, frame: int) -> int:
        return self.inp.epoch_us + frame_to_us(frame)

    def _in_window(self, occ: Occurrence, frame: int) -> bool:
        return occ.lo_us <= self._us(frame) <= occ.hi_us

    def _row_piece(self, r: PlanRow) -> Piece:
        p = self.pools.by_slug.get(r.slug)
        if p is None:
            return Piece("show", Show(r.slug, Path(r.dir), (), r.key, {}), r.dir, r.frames, True)
        return p if p.frames == r.frames and p.exact else replace(p, frames=r.frames, exact=True)

    def _add(self, piece: Piece, frame: int) -> None:
        us = self._us(frame)
        self.rec = self.rec.with_piece(piece, us, rules.local_date(us, self.tz))
        self.start = frame + piece.frames + self.gap
        self.run_start = False

    # --- occurrences ---

    def _continuing(self, last: PlanRow) -> Occurrence | None:
        """The occurrence the last row names, when the clock still yields it (at
        a run start, only when the run restarts inside it)."""
        if last.block is None or last.nominal_start is None:
            return None
        try:
            nominal = iso_to_us(last.nominal_start)
        except (TypeError, ValueError):
            return None
        for o in occurrences(self.clock, nominal, nominal + 1):
            if o.key == (last.block, last.nominal_start):
                if self.run_start and not o.nominal_us <= self._us(self.start) < o.end_us:
                    return None
                return o
        return None

    def _entry(self) -> Occurrence:
        """The occurrence in progress at the start; the next one when the start is
        already inside its window (its first show then starts on time)."""
        t = self._us(self.start)
        cur = next(o for o in occurrences(self.clock, t, t + 1) if o.nominal_us <= t < o.end_us)
        nxt = next((o for o in occurrences(self.clock, cur.end_us, cur.end_us + 1)
                    if o.nominal_us == cur.end_us), None)
        return nxt if nxt is not None and t >= nxt.lo_us else cur

    def _enter(self, occ: Occurrence) -> None:
        self.occ = occ
        self.placed: list[Piece] = []
        self.placed_bends: set[str] = set()
        self.extra_own: list[Piece] = []
        self.run: _BlockRun | None = None
        self.run_k = 0

    # --- runs ---

    def _new_run(self, occ: Occurrence, start: int, placed: Sequence[Piece], rec: Recency, used: set[str],
                 prev_artist: str | None) -> _BlockRun:
        own = self.pools.own(occ)
        if placed and self.extra_own and own and occ.key == self.occ.key:
            have = {p.slug for p in own}
            own = own + [p for p in self.extra_own if p.slug not in have]
        return _BlockRun(occ, self.occs.after(occ), start_frame=start, placed=placed, own_pool=own,
                         open_pool=self.pools.open, boundary_frames=self.B, final_boundary_frames=self.B,
                         prev_artist=prev_artist, rec=rec, clock=self.clock, epoch_us=self.inp.epoch_us,
                         seed=self.inp.seed, used=frozenset(used))

    def _run_at(self, start: int) -> tuple[_BlockRun, int]:
        """The current occurrence's run whose next show starts at `start`: the
        active one when its own layout agrees (continuation-closed), else new."""
        if self.run is None or self.run.start_of(self.run_k) != start:
            self.run = self._new_run(self.occ, start, tuple(self.placed), self.rec, self.used, self.prev_artist)
            self.run_k = 0
        return self.run, self.run_k

    # --- interstitials ---

    def _station_id(self) -> Piece | None:
        """Least recently used first (never used before any), tie on `tie_rank`."""
        def key(p: Piece):
            last = self.rec.last_used_us(p.slug)
            return (last is not None, last or 0, rules.tie_rank(self.inp.seed, p.slug))
        return min(self.pools.ids, key=key, default=None)

    def _ann(self, form: Form, x: Occurrence, y: Occurrence | None) -> Piece | None:
        return self.pools.anns.get(ann_id(text_for(form, x, y, self.clock.announce)))

    def _forms(self, x: Occurrence, two: Form, one: Form) -> list[tuple[Form, Occurrence | None]]:
        """The forms to try for X, two-block first when Y may be named at all."""
        if not x.block.title or self.pools.degraded(x):
            return []                            # untitled or degraded X: never announced
        y = self.occs.after(x)
        if two_block_ok(x, y) and y.block.title and not self.pools.degraded(y):
            return [(two, y), (one, None)]
        return [(one, None)]

    @staticmethod
    def _names(x: Occurrence, y: Occurrence | None) -> tuple[tuple[str, str], ...]:
        return (x.key,) if y is None else (x.key, y.key)

    def _try_next(self, x: Occurrence, s: int):
        """`next` before X's first show, its clip at `s`: X must start in its
        window with the clip in place; Y (two-block) where X's run lands it."""
        for form, y in self._forms(x, "next", "next_one"):
            clip = self._ann(form, x, y)
            if clip is None:
                continue                         # missing audio: the one-block clip, then an ID
            x_start = s + clip.frames + self.gap
            if not self._in_window(x, x_start):
                continue
            xrun = None
            if y is not None:
                xrun = self._new_run(x, x_start, (), self.rec, self.used, self.prev_artist)
                if not self._in_window(y, xrun.complete()[-1].landing):
                    continue                     # fails only on Y: the one-block form
            return clip, "next", self._names(x, y), xrun
        return None

    def _try_later(self, run: _BlockRun, k: int, s: int):
        """`later` at the current block's last internal boundary (clip at `s`),
        naming the occurrence after it: X's start is predicted with the clip,
        the block's last show and a boundary estimate in place."""
        x = self.occs.after(self.occ)
        last = run.step(k).shows[0].piece
        for form, y in self._forms(x, "later", "later_one"):
            clip = self._ann(form, x, y)
            if clip is None:
                continue
            l_start = s + clip.frames + self.gap
            x_start = l_start + last.frames + self.B
            if not self._in_window(x, x_start):
                continue
            if y is not None:
                us = self._us(l_start)
                rec = self.rec.with_piece(last, us, rules.local_date(us, self.tz))
                xrun = self._new_run(x, x_start, (), rec, self.used | {last.slug}, last.artist)
                if not self._in_window(y, xrun.complete()[-1].landing):
                    continue
            return clip, "later", self._names(x, y), None
        return None

    # --- steps ---

    def boundary(self, last_pos: int):
        """The interstitial after a show: an announcement, a station ID or
        nothing (None: the next piece is the show). `_STOP` past the horizon."""
        s = self.start
        id_clip = self._station_id()
        m = s + (id_clip.frames + self.gap if id_clip is not None else 0)     # the next show, after an ID
        run = k = None
        if not self.placed:
            kind, target = "into", self.occ          # a mid-block entry: this occurrence's first show
        else:
            run, k = self._run_at(m)
            if not run.step(k).shows:
                kind, target = "into", self.occs.after(self.occ)
            else:
                kind, target = ("last" if not run.step(k + 1).shows else "internal"), self.occ
        if self.occs.pos(target) > last_pos:
            return _STOP
        choice = None
        if kind == "into":
            choice = self._try_next(target, s)
        elif kind == "last":
            choice = self._try_later(run, k, s)
        clip, role, names, xrun = choice if choice is not None else (id_clip, "id", (), None)
        if target.key != self.occ.key:
            self._enter(target)
        self.after_show = False
        if clip is None:
            return None
        pp = PlannedPiece(clip, s, self.run_start, target.block.name, target.nominal_iso, role, names=names)
        self._add(clip, s)
        if xrun is not None:
            self.run, self.run_k = xrun, 0
        return pp

    def show(self, last_pos: int):
        s = self.start
        while True:
            if self.occs.pos(self.occ) > last_pos:
                return _STOP
            run, k = self._run_at(s)
            step = run.step(k)
            if step.shows:
                break
            self._enter(self.occs.after(self.occ))     # the block re-planned to end here
        occ = self.occ
        piece = step.shows[0].piece
        is_fill = run.is_fill(k)
        nxt = run.step(k + 1)
        own = set(step.bends) - set(nxt.bends if nxt is not None else ())
        if self.pools.open_bent and (occ.is_open or run.degraded or is_fill):
            own.add(EXCLUDE_BEND)
        bends = tuple(b for b in _BEND_ORDER if b in own and b not in self.placed_bends)
        pp = PlannedPiece(piece, s, self.run_start, occ.block.name, occ.nominal_iso, "show",
                          miss=None if self.placed else not self._in_window(occ, s),
                          degraded=run.degraded, fill=run.cause if is_fill else None, bends=bends)
        self.placed.append(piece)
        self.placed_bends.update(bends)
        self.run_k = k + 1
        self._add(piece, s)
        self.used.add(piece.slug)
        self.prev_artist = piece.artist
        self.after_show = True
        return pp

    def horizon(self, until_frame: int | None, ahead: int) -> int:
        if until_frame is None:
            return ahead
        t = self._us(until_frame)
        i = 0
        while self.occs.at(i).end_us <= t:
            i += 1
        return i + ahead


def project(inp: SchedulerInput, *, until_frame: int | None = None, ahead: int = 2) -> list[PlannedPiece]:
    """Every piece from the end of the persisted plan through the continuing
    occurrence and `ahead` more (with `until_frame`, through the occurrence
    in progress at `until_frame` and `ahead` more), in order, laid out
    exactly: the first at `start_frame` (`run_start` as given), each later
    one at the previous end + `gap_frames`. Pure.

    The continuing occurrence is the one the last persisted row names
    (`block`, `nominal_start`) while the clock still yields it, its persisted
    show rows placed; otherwise (phase-1 rows, a fresh run, an edited clock)
    the occurrence in progress at `start_frame`, or the next one when
    `start_frame` already lies in its window. Occurrences follow in sequence,
    never skipped; each gets at least one show.

    After a show (not at a run start) comes its boundary: before X's first
    show a `next` for X; at a block's last internal boundary a `later` for
    the occurrence after it; else, or when the announcement is not truthful
    or its audio is missing, a station ID; with no ID clip, nothing. An
    announcement needs X titled, not degraded, and X's first show starting
    in its window with the clip in place; the two-block form also needs
    `announce.two_block_ok(X, Y)` and Y titled, not degraded and landed in
    its window by X's projected run; failing only on Y it falls back to the
    one-block form, a missing clip to the one-block clip, then an ID.

    Shows come from `fill_block`'s runs: each show is the first show of a run
    from its exact start, the boundaries after it estimated as gap, typical
    ID, gap (one gap with no ID pool); a block whose next boundary differs is
    re-planned from the exact start, as a live step would."""
    p = _Projection(inp)
    last_pos = p.horizon(until_frame, ahead)
    out: list[PlannedPiece] = []
    while True:
        pp = p.boundary(last_pos) if p.after_show else None
        if pp is _STOP:
            break
        if pp is None:
            pp = p.show(last_pos)
            if pp is _STOP:
                break
        out.append(pp)
    return out
