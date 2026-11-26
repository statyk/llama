"""Promises derived from concert break rows (spec "Promises"): which named shows
a break still owes, when a promise is void, and the first show row that breaks
one. Rows are built by hand; nothing here may raise."""

import dataclasses
import itertools
from datetime import date, timedelta

from transmitter import promises
from transmitter.clock import BlockConfig, ClockConfig, OpenConfig, RotationConfig, occurrences
from transmitter.grid import iso_to_us
from transmitter.layout import CONCERT_ROLE, PlanRow
from transmitter.promises import entries_of, first_mismatch, merge_remainders, remaining

TZ = "America/New_York"
E = iso_to_us("2026-11-02T05:00:00Z")           # 00:00 local, Monday 2026-11-02
DAY = 86_400_000_000

EVE = {"name": "eve", "title": "Evening Concert", "start": "20:00"}
LATE = {"name": "late", "title": "Late Night", "start": "23:00"}
DAWN = {"name": "dawn", "start": "05:00"}


def clk(*blocks) -> ClockConfig:
    return ClockConfig(timezone=TZ, wiggle_minutes=15, open=OpenConfig(),
                       rotation=RotationConfig(), block=[BlockConfig(**b) for b in blocks])


CLOCK = clk(EVE, LATE, DAWN)


def key(clock, name, day=0) -> tuple[str, str]:
    for o in occurrences(clock, E - DAY, E + 10 * DAY):
        if o.block.name == name and o.local_date == date(2026, 11, 2) + timedelta(days=day):
            return o.key
    raise LookupError(name)


EK = key(CLOCK, "eve")
LK = key(CLOCK, "late")

_seq = itertools.count(1)


def show(slug, k=EK, *, run_start=False) -> PlanRow:
    return PlanRow(seq=next(_seq), slug=slug, dir=slug, key=f"k-{slug}", start_frame=0, frames=10,
                   run_start=run_start, kind="show", block=k[0], nominal_start=k[1], role="show")


def iid(slug="id-a", k=EK) -> PlanRow:
    return PlanRow(seq=next(_seq), slug=slug, dir="interstitials", key=f"k-{slug}", start_frame=0, frames=10,
                   kind="interstitial", block=k[0], nominal_start=k[1], role="id")


def concert(*slugs, k=EK, names=(), **kw) -> PlanRow:
    return PlanRow(seq=next(_seq), slug="concert-abc", dir="interstitials", key="k-concert", start_frame=0,
                   frames=10, kind="interstitial", block=k[0], nominal_start=k[1], role=CONCERT_ROLE,
                   named_shows=tuple(slugs),
                   names=tuple(names) if isinstance(names, list) else names, **kw)


POOL = frozenset({"p", "x", "y", "z", "w", "v"})


def rem(rows, *, pool=POOL, clock=CLOCK, run_start=False):
    return remaining(rows, pool_slugs=pool, clock=clock, run_start=run_start)


def test_entries_put_z_in_its_named_occurrence():
    assert entries_of(concert("x", "y", "z", names=[LK])) == (("x", EK), ("y", EK), ("z", LK))
    assert entries_of(concert("x", "y")) == (("x", EK), ("y", EK))
    assert entries_of(concert("x", "z", names=[LK])) == (("x", EK), ("z", LK))
    assert entries_of(concert("x")) == (("x", EK),)
    assert entries_of(show("x")) is None
    assert entries_of(iid()) is None


def test_malformed_rows_have_no_promise():
    assert entries_of(concert(1, 2)) is None
    assert entries_of(concert("x", None)) is None
    assert entries_of(concert("x", "")) is None
    assert entries_of(concert()) is None
    assert entries_of(concert("x", "y", "z", "w")) is None
    assert entries_of(concert("x", "y", "z", names=[LK, LK])) is None
    assert entries_of(concert("x", "z", names=[("late",)])) is None
    assert entries_of(concert("x", "z", names=[("late", 5)])) is None
    assert entries_of(concert("x", names=[LK])) is None          # Z needs an X before it
    bare = PlanRow(seq=1, slug="c", dir="interstitials", key="k", start_frame=0, frames=1,
                   kind="interstitial", role=CONCERT_ROLE, named_shows=("x",))
    assert entries_of(bare) is None                               # no block / nominal_start
    for r in GARBAGE_ROWS:
        entries_of(r)                                             # never raises


def test_partial_promise_is_live_and_remaining_is_the_rest():
    rows = [show("p"), iid(), concert("x", "y", "z", names=[LK]), show("x")]
    assert rem(rows) == (("y", EK), ("z", LK))
    # Nothing placed yet: the whole promise remains; interstitials between are ignored.
    assert rem(rows[:3]) == (("x", EK), ("y", EK), ("z", LK))
    assert rem(rows + [iid("id-b")]) == (("y", EK), ("z", LK))
    assert rem(rows + [show("y")]) == (("z", LK),)


def test_kept_promise_leaves_nothing():
    rows = [show("p"), concert("x", "y", "z", names=[LK]), show("x"), show("y"), iid(k=LK), show("z", LK)]
    assert rem(rows) == ()
    assert rem(rows + [show("w", LK)]) == ()
    assert rem([show("p")]) == ()
    assert rem([]) == ()


def test_void_when_a_named_slug_left_the_pool():
    rows = [show("p"), concert("x", "y", "z", names=[LK]), show("x")]
    assert rem(rows, pool=POOL - {"y"}) == ()
    assert rem(rows, pool=POOL - {"z"}) == ()
    # A placed slug no longer in the pool does not matter.
    assert rem(rows, pool=POOL - {"x"}) == (("y", EK), ("z", LK))


def test_void_when_a_row_after_it_starts_a_run():
    assert rem([concert("x", "y"), show("x", run_start=True)]) == ()
    r_run = dataclasses.replace(iid(), run_start=True)
    assert rem([concert("x", "y"), show("x"), r_run]) == ()


def test_void_when_run_start_is_requested():
    assert rem([concert("x", "y"), show("x")], run_start=True) == ()
    assert rem([concert("x", "y")], run_start=True) == ()


def test_void_when_the_clock_no_longer_yields_the_occurrence():
    rows = [show("p"), concert("x", "y", "z", names=[LK]), show("x")]
    renamed = clk(EVE, {**LATE, "name": "late-night"}, DAWN)
    assert rem(rows, clock=renamed) == ()
    moved = clk(EVE, {**LATE, "start": "23:30"}, DAWN)
    assert rem(rows, clock=moved) == ()
    # X's own occurrence gone voids it too.
    assert rem(rows, clock=clk({**EVE, "name": "evening"}, LATE, DAWN)) == ()


def test_void_when_a_different_show_was_placed():
    assert rem([concert("x", "y"), show("w")]) == ()
    assert rem([concert("x", "y"), show("x"), show("w")]) == ()
    assert rem([concert("x", "y"), show("y")]) == ()


def test_a_prefix_remainder_agrees_and_the_longer_is_kept():
    rows = [concert("x", "y", "z", names=[LK]), show("x"), concert("y", k=EK)]
    assert rem(rows) == (("y", EK), ("z", LK))
    # Equally when the newer one is the longer.
    rows2 = [concert("x", "y"), show("x"), concert("y", "z", names=[LK])]
    assert rem(rows2) == (("y", EK), ("z", LK))


def test_newer_live_promise_wins_on_disagreement():
    rows = [concert("x", "y", "z", names=[LK]), show("x"), concert("w")]
    assert rem(rows) == (("w", EK),)


def test_merge_remainders_rule():
    a, b, c = ("a", EK), ("b", EK), ("c", LK)
    assert merge_remainders((), (a, b)) == (a, b)
    assert merge_remainders((a, b), ()) == (a, b)
    assert merge_remainders((a, b, c), (a,)) == (a, b, c)
    assert merge_remainders((a,), (a, b)) == (a, b)
    assert merge_remainders((a, b), (a, c)) == (a, c)
    assert merge_remainders((a, b), (b,)) == (b,)
    assert merge_remainders((a, b), (("a", LK),)) == (("a", LK),)


def test_first_mismatch_only_once():
    r = concert("x", "y")
    assert first_mismatch([r, show("x")], show("w")) is True
    assert first_mismatch([r, show("x"), show("w")], show("v")) is False
    assert first_mismatch([r, show("x")], show("y")) is False
    assert first_mismatch([r, show("x"), show("y")], show("v")) is False   # kept, then free
    assert first_mismatch([r], show("w")) is True
    assert first_mismatch([r, show("x")], iid()) is False                  # only show rows break
    assert first_mismatch([show("p")], show("w")) is False


def test_first_mismatch_on_a_run_start_row():
    r = concert("x", "y")
    assert first_mismatch([r, show("x")], show("y", run_start=True)) is True
    assert first_mismatch([r, show("x", run_start=True)], show("y", run_start=True)) is False


GARBAGE_ROWS = [
    concert("x", "y", k=("eve", "not-a-date")),
    concert("x", "z", names=[("late", "not-a-date")]),
    concert("x", "z", names=[("late", "9999-12-31T23:59:59.000Z")]),
    concert("x", "z", names=[("late", "2026-11-02T04:00:00")]),     # no offset
    concert("x", "z", names=[["a"]]),
    concert("x", "z", names=["ab"]),
    concert("x", "z", names=[None]),
    concert("x", "z", names=None),
    concert(["x"], ("y",)),
    PlanRow(seq=1, slug="c", dir="i", key="k", start_frame=0, frames=1, kind="interstitial",
            role=CONCERT_ROLE, block=5, nominal_start=7, named_shows=("x",)),
    PlanRow(seq=1, slug="c", dir="i", key="k", start_frame=0, frames=1, kind="interstitial",
            role=CONCERT_ROLE, block=EK[0], nominal_start=EK[1], named_shows=None),
    PlanRow(seq=1, slug="c", dir="i", key="k", start_frame=0, frames=1, kind="interstitial",
            role=CONCERT_ROLE, block=EK[0], nominal_start=EK[1], named_shows="xyz"),
    PlanRow(seq=1, slug=["unhashable"], dir="i", key="k", start_frame=0, frames=1, kind="show",
            role="show", block=EK[0], nominal_start=EK[1]),
    PlanRow(seq=1, slug="x", dir="i", key="k", start_frame=0, frames=1, kind=None, role=None),
    PlanRow.from_json({"seq": 1, "slug": "c", "dir": "i", "key": "k", "start_frame": 0, "frames": 1,
                       "kind": "interstitial", "role": CONCERT_ROLE, "block": "eve",
                       "nominal_start": EK[1], "named_shows": ["x"], "future": [["a"]]}),
]


def test_never_raises_on_garbage():
    for r in GARBAGE_ROWS:
        for rows in ([r], [r, show("x")], [concert("x", "y"), r], [r, r, show("y")]):
            assert rem(rows, pool=frozenset()) == ()
            assert isinstance(rem(rows), tuple)
            assert first_mismatch(rows, show("x")) in (True, False)
            assert first_mismatch(rows, r) in (True, False)
    # Arguments of the wrong type degrade to "no promise" too.
    assert remaining([concert("x")], pool_slugs=None, clock=CLOCK, run_start=False) == ()
    assert remaining([concert("x")], pool_slugs=POOL, clock=None, run_start=False) == ()
    assert remaining(None, pool_slugs=POOL, clock=CLOCK, run_start=False) == ()
    assert first_mismatch(None, show("x")) is False
    assert first_mismatch([concert("x")], None) is False
    assert merge_remainders(None, (("a", EK),)) == (("a", EK),)


def test_module_function_is_patchable():
    assert promises.remaining is remaining


def test_long_plan_only_the_tail_counts():
    rows = [show(f"s{i}") for i in range(20_000)] + [concert("x", "y"), show("x")]
    assert rem(rows) == (("y", EK),)
    assert first_mismatch(rows, show("w")) is True
    old = [concert("x", "y", "z", names=[LK])] + [show("x"), show("y"), show("z", LK), show("w", LK)]
    assert rem(old) == ()


def test_first_mismatch_after_an_interstitial_that_starts_a_run():
    r = concert("x", "y")
    clip_run = dataclasses.replace(iid(), run_start=True)
    # The run_start clip voids the promise; the first show row after it is the broken one, whatever its slug.
    assert first_mismatch([r, show("x"), clip_run], show("w")) is True
    assert first_mismatch([r, show("x"), clip_run], show("y")) is True
    assert first_mismatch([r, clip_run], show("w")) is True
    assert first_mismatch([r, clip_run], show("x")) is True
    assert first_mismatch([r, clip_run, iid("id-b")], show("x")) is True
    # Flagged once: a show row already followed the void.
    assert first_mismatch([r, clip_run, show("x")], show("y")) is False
    assert first_mismatch([r, show("x"), clip_run, show("w")], show("v")) is False
    # A kept promise is not broken by a later run start.
    assert first_mismatch([r, show("x"), show("y"), clip_run], show("w")) is False
    # And remaining treats it as void.
    assert rem([r, clip_run]) == ()
    assert rem([r, show("x"), clip_run]) == ()


def test_a_break_that_starts_a_run_still_promises():
    assert rem([concert("x", "y", run_start=True)]) == (("x", EK), ("y", EK))
    assert rem([concert("x", "y", run_start=True), show("x")]) == (("y", EK),)


def test_placed_entries_occurrence_must_still_be_yielded():
    rows = [concert("x", "z", names=[LK]), show("x")]
    assert rem(rows) == (("z", LK),)
    assert rem(rows, clock=clk({**EVE, "name": "evening"}, LATE, DAWN)) == ()


class _Rows:
    """A Sequence that is neither list nor tuple and refuses to be iterated whole."""

    def __init__(self, rows):
        self._rows = rows

    def __len__(self):
        return len(self._rows)

    def __getitem__(self, i):
        if isinstance(i, slice):
            raise AssertionError("sliced")
        return self._rows[i]

    def __iter__(self):
        raise AssertionError("iterated whole")


def test_tail_indexes_a_sequence_from_the_end():
    import collections.abc
    collections.abc.Sequence.register(_Rows)
    rows = _Rows([show(f"s{i}") for i in range(50)] + [concert("x", "y"), show("x")])
    assert rem(rows) == (("y", EK),)
    assert first_mismatch(rows, show("w")) is True


def test_a_coding_bug_is_logged(monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("bug")
    monkeypatch.setattr(promises, "_tail", boom)
    with caplog.at_level("ERROR", logger="transmitter.promises"):
        assert rem([concert("x")]) == ()
        assert first_mismatch([concert("x")], show("w")) is False
    assert sum("failed" in r.getMessage() for r in caplog.records) == 2
