"""Promises derived from concert break rows (spec "Promises"). Pure: no IO.

A concert break row names shows X[, Y][, Z]; its promise is that the plan then
places those shows, in order, at the following show slots. A promise is
*live* while (a) the show rows after the break, in order, are a prefix of its
entries (interstitial rows ignored), (b) no row after it has `run_start`,
(c) each unplaced slug is in the pool and (d) each named occurrence is still
yielded by the clock. At the first failure the whole promise is void.

STRICT SURFACE: nothing here raises and nothing loops. A malformed row means
no promise; any unexpected failure degrades to "no promise" (`()` / False).
Only the tail of the plan is examined: a break with more than three show rows
after it is kept or already broken; for `remaining`, one before the latest
`run_start` is void too.
"""

import logging
from collections.abc import Sequence

from transmitter.clock import ClockConfig, occurrences
from transmitter.concert import Named
from transmitter.grid import iso_to_us
from transmitter.layout import CONCERT_ROLE, PlanRow

MAX_NAMED = 3
_log = logging.getLogger(__name__)


def _key(value: object) -> tuple[str, str] | None:
    if (isinstance(value, (tuple, list)) and len(value) == 2
            and isinstance(value[0], str) and value[0] and isinstance(value[1], str) and value[1]):
        return (value[0], value[1])
    return None


def entries_of(row: PlanRow) -> tuple[Named, ...] | None:
    """A concert row's named shows with their occurrences: every slug but Z in
    (row.block, row.nominal_start); the last slug (Z) in names[0] when names is
    non-empty. None when the row is not a concert row or is malformed (a
    non-str or empty slug, no slugs, more than three, more than one names pair,
    a names pair that is not two strings, names with a single slug, missing
    block/nominal_start). Never raises."""
    try:
        if getattr(row, "role", None) != CONCERT_ROLE:
            return None
        slugs = getattr(row, "named_shows", None)
        if not isinstance(slugs, (tuple, list)) or not 1 <= len(slugs) <= MAX_NAMED:
            return None
        if not all(isinstance(s, str) and s for s in slugs):
            return None
        own = _key((getattr(row, "block", None), getattr(row, "nominal_start", None)))
        if own is None:
            return None
        names = getattr(row, "names", None)
        if not isinstance(names, (tuple, list)) or len(names) > 1:
            return None
        if not names:
            return tuple((s, own) for s in slugs)
        z = _key(names[0])
        if z is None or len(slugs) < 2:
            return None
        return tuple((s, own) for s in slugs[:-1]) + ((slugs[-1], z),)
    except Exception:
        return None


def merge_remainders(older: Sequence[Named], newer: Sequence[Named]) -> tuple[Named, ...]:
    """Combine two live promises' remainders (the plan's merge rule): when one
    is a prefix of the other they agree and the longer is kept; only when they
    differ at some position do they disagree, and then `newer` wins. Pure;
    never raises (a malformed argument counts as empty)."""
    try:
        a = tuple(older) if older else ()
    except Exception:
        a = ()
    try:
        b = tuple(newer) if newer else ()
    except Exception:
        b = ()
    try:
        n = min(len(a), len(b))
        if a[:n] == b[:n]:
            return a if len(a) > len(b) else b
        return b
    except Exception:
        return b


def _is_show(row: object) -> bool:
    return getattr(row, "kind", None) == "show"


def _tail(rows: Sequence[PlanRow], *, cut_at_run_start: bool) -> list[PlanRow]:
    """The rows that can still hold or decide a promise: back from the end until
    a fourth show row (a break that many shows back is kept or broken already)
    and, with `cut_at_run_start`, the latest run_start row (kept: only rows AFTER
    a break void it). Indexes from the end; never copies the whole plan."""
    seq = rows if isinstance(rows, Sequence) else list(rows)
    n = len(seq)
    shows = 0
    i = n
    start = 0
    while i > 0:
        i -= 1
        r = seq[i]
        if _is_show(r):
            shows += 1
            if shows > MAX_NAMED:
                start = i + 1
                break
        if cut_at_run_start and bool(getattr(r, "run_start", False)):
            start = i
            break
    return [seq[j] for j in range(start, n)]


_INTACT = "intact"     # every show after the break matched, no run_start since
_VOIDED = "voided"     # a non-show run_start row voided it; no show row has followed yet
_SETTLED = "settled"   # kept in full, or broken and already flagged on a show row


def _progress(entries: tuple[Named, ...], after: Sequence[PlanRow]) -> tuple[str, int]:
    """(state, placed) of a promise given the rows after its break."""
    placed = 0
    voided = False
    for r in after:
        show = _is_show(r)
        if voided:
            if show:
                return _SETTLED, placed            # that show row was the flagged one
            continue
        rs = bool(getattr(r, "run_start", False))
        if placed >= len(entries):
            if show or rs:
                return _SETTLED, placed
            continue
        if not show:
            if rs:
                voided = True                      # (b): flagged on the next show row
            continue
        if rs or getattr(r, "slug", None) != entries[placed][0]:
            return _SETTLED, placed                # (a)/(b) broken on this show row
        placed += 1
    return (_VOIDED if voided else _INTACT), placed


def _yielded(clock: ClockConfig, key: tuple[str, str], cache: dict) -> bool:
    if key in cache:
        return cache[key]
    try:
        us = iso_to_us(key[1])
        ok = any(o.block.name == key[0] and o.nominal_us == us for o in occurrences(clock, us, us + 1))
    except Exception:
        ok = False
    cache[key] = ok
    return ok


def remaining(rows: Sequence[PlanRow], *, pool_slugs: frozenset[str], clock: ClockConfig,
              run_start: bool) -> tuple[Named, ...]:
    """The unplaced entries of the live promises, in order; () when none.
    `run_start=True` (the next piece starts a run) voids everything. Live
    promises combine oldest first through `merge_remainders`. Never raises."""
    try:
        if run_start:
            return ()
        tail = _tail(rows, cut_at_run_start=True)
        cache: dict = {}
        out: tuple[Named, ...] = ()
        for i, r in enumerate(tail):
            entries = entries_of(r)
            if entries is None:
                continue
            state, placed = _progress(entries, tail[i + 1:])
            if state != _INTACT or placed >= len(entries):
                continue
            rest = entries[placed:]
            if not all(slug in pool_slugs for slug, _ in rest):
                continue
            if not all(_yielded(clock, k, cache) for _, k in entries):
                continue
            out = merge_remainders(out, rest)
        return out
    except Exception:
        _log.exception("promises.remaining failed; treating every promise as void")
        return ()


def first_mismatch(rows: Sequence[PlanRow], row: PlanRow) -> bool:
    """`row` (about to be appended) is a show row that breaks a promise for the
    first time: some concert row R in `rows` has entries, fewer than all are
    placed, every show row after R so far matched them in order, and either a
    non-show row after R started a run (no show row since: the promise is void
    and this is the first show row after it) or `row` is not the next named slug
    or has run_start. Rows only (pool and clock are not consulted); never raises."""
    try:
        if not _is_show(row):
            return False
        tail = _tail(rows, cut_at_run_start=False)
        for i, r in enumerate(tail):
            entries = entries_of(r)
            if entries is None:
                continue
            state, placed = _progress(entries, tail[i + 1:])
            if state == _VOIDED:
                return True
            if state != _INTACT or placed >= len(entries):
                continue
            if bool(getattr(row, "run_start", False)) or getattr(row, "slug", None) != entries[placed][0]:
                return True
        return False
    except Exception:
        _log.exception("promises.first_mismatch failed; treating the row as not breaking a promise")
        return False
