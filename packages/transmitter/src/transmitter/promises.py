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
after it, or one before the latest `run_start`, can no longer be live.
"""

from collections.abc import Sequence

from transmitter.clock import ClockConfig, occurrences
from transmitter.concert import Named
from transmitter.grid import iso_to_us
from transmitter.layout import CONCERT_ROLE, PlanRow

MAX_NAMED = 3


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


def _tail(rows: Sequence[PlanRow]) -> list[PlanRow]:
    """The rows that can still hold or decide a live promise: back from the end
    until a fourth show row or the latest run_start row (kept: only rows AFTER a
    break void it)."""
    seq = rows if isinstance(rows, (list, tuple)) else list(rows)
    shows = 0
    i = len(seq)
    while i > 0:
        i -= 1
        r = seq[i]
        if _is_show(r):
            shows += 1
            if shows > MAX_NAMED:
                return list(seq[i + 1:])
        if bool(getattr(r, "run_start", False)):
            return list(seq[i:])
    return list(seq)


def _progress(entries: tuple[Named, ...], after: Sequence[PlanRow]) -> int | None:
    """How many entries the show rows in `after` placed, in order; None when the
    promise is already broken there (a mismatch, an extra show, a run_start)."""
    placed = 0
    for r in after:
        if bool(getattr(r, "run_start", False)):   # (b); `_tail` already cuts here
            return None
        if not _is_show(r):
            continue
        if placed >= len(entries) or getattr(r, "slug", None) != entries[placed][0]:
            return None
        placed += 1
    return placed


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
        tail = _tail(rows)
        cache: dict = {}
        out: tuple[Named, ...] = ()
        for i, r in enumerate(tail):
            entries = entries_of(r)
            if entries is None:
                continue
            placed = _progress(entries, tail[i + 1:])
            if placed is None or placed >= len(entries):
                continue
            rest = entries[placed:]
            if not all(slug in pool_slugs for slug, _ in rest):
                continue
            if not all(_yielded(clock, k, cache) for _, k in entries):
                continue
            out = merge_remainders(out, rest)
        return out
    except Exception:
        return ()


def first_mismatch(rows: Sequence[PlanRow], row: PlanRow) -> bool:
    """`row` (about to be appended) is a show row that breaks a promise for the
    first time: some concert row R in `rows` has entries, every show row after R
    so far matched them in order with no run_start, fewer than all are placed,
    and `row` is not the next named slug or has run_start. Rows only (pool and
    clock are not consulted); never raises."""
    try:
        if not _is_show(row):
            return False
        tail = _tail(rows)
        for i, r in enumerate(tail):
            entries = entries_of(r)
            if entries is None:
                continue
            placed = _progress(entries, tail[i + 1:])
            if placed is None or placed >= len(entries):
                continue
            if bool(getattr(row, "run_start", False)) or getattr(row, "slug", None) != entries[placed][0]:
                return True
        return False
    except Exception:
        return False
