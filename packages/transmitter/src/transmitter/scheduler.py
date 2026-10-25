"""The scheduler (spec "Planning"). Pure: no IO, deterministic for given
inputs; ties break on `rules.tie_rank(seed, slug)`.

Part 1, `fill_block`: choose the shows of one block occurrence so the next
block's first show lands inside its window, in the compromise order of Goals
3: tier 0 (own profile only, landing in window), tier 1 (own shows then fill
from the open pool, landing in window), tier 2 (own shows only, a miss).
The search itself lives in `transmitter._blocksearch`."""

from collections.abc import Sequence
from dataclasses import dataclass

from transmitter import rules
from transmitter._blocksearch import (  # noqa: F401  (re-exported: tests reach these)
    FILL_PREFIXES, MAX_FILL, NEAR_EACH_SIDE, PAIR_FIRSTS, PAIR_PARTNERS, _C, _Ctx, _Pool, _Search, _Seq,
    _Step, _Tier, _choose, _dedupe, _excluded, _fill_cause, _has_fill, _sequence_violations)
from transmitter.clock import ClockConfig, Occurrence
from transmitter.errors import PlanError
from transmitter.history import Recency
from transmitter.pieces import Piece


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
