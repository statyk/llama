"""Unit tests for the shared, Typer-free selector layer (`llama.cli_select`).

These tests exercise it directly over synthetic `CatalogEntry` objects, same
pattern as `tests/test_catalog.py`.
"""
from pathlib import Path

import pytest

from llama.catalog import CatalogEntry
from llama.cli_select import (HELD_NOTE, Selector, ShowState, apply_selector,
                              build_selector, selector_active, split_held)
from llama.workspace import ShowWorkspace


def e(slug, state, *, artist="Grateful Dead") -> CatalogEntry:
    return CatalogEntry(slug=slug, ws=ShowWorkspace(Path("/x")), state=state,
                        artist=artist)


def test_show_state_has_exactly_eight_values():
    assert [s.value for s in ShowState] == [
        "held", "selected", "gathered", "researched", "vetted", "briefed",
        "packaged", "delivered",
    ]


def test_show_state_covers_derive_state_full_vocabulary(tmp_path: Path):
    """`ShowState` must cover every state string `catalog.derive_state` can
    actually return — not just a hand-copied duplicate list — so a future 10th
    derived state can't silently slip past `--state`'s validated enum."""
    from test_catalog import build

    from llama.catalog import derive_state

    stage_combos = [
        {"select"},
        {"select", "gather"},
        {"select", "gather", "research"},
        {"select", "gather", "research", "vet"},
        {"select", "gather", "research", "vet", "brief"},
        {"select", "gather", "research", "vet", "brief", "package"},
    ]
    observed = set()
    for i, stages in enumerate(stage_combos):
        ws = build(tmp_path / f"plain{i}", f"plain{i}", stages=stages)
        state, _ = derive_state(ws, delivered=set())
        observed.add(state)

    held_ws = build(tmp_path / "held", "held", stages={"select", "gather"}, needs_review=True)
    state, _ = derive_state(held_ws, delivered=set())
    observed.add(state)

    delivered_ws = build(tmp_path / "delivered", "delivered",
                         stages={"select", "gather"}, pid="X/1970-01-01")
    state, _ = derive_state(delivered_ws, delivered={"X/1970-01-01"})
    observed.add(state)

    assert observed == {s.value for s in ShowState}


def test_state_rank_covers_show_state_vocabulary():
    """`cli._STATE_RANK` is a second, hand-maintained copy of the `ShowState`
    vocabulary (used to sort `llama status`); it must stay in sync or a
    missing key KeyErrors on the plain `llama status` path."""
    from llama.cli import _STATE_RANK

    assert set(_STATE_RANK) == {s.value for s in ShowState}


def test_held_sugar_identity():
    assert build_selector(held=True) == build_selector(states=["held"])


def test_packaged_sugar_identity():
    assert build_selector(packaged=True) == build_selector(states=["packaged"])


def test_held_sugar_accepts_showstate_members():
    assert build_selector(states=[ShowState.held]) == build_selector(states=["held"])


def test_states_or_together():
    sel = build_selector(states=["held", "packaged"])
    es = [e("a", "held"), e("b", "packaged"), e("c", "delivered")]
    assert {x.slug for x in apply_selector(es, sel)} == {"a", "b"}


def test_filters_and_together():
    sel = build_selector(states=["packaged"], artist="dead")
    es = [
        e("a", "packaged", artist="Grateful Dead"),
        e("c", "packaged", artist="Phish"),            # fails artist
        e("d", "held", artist="Grateful Dead"),        # fails state
    ]
    assert {x.slug for x in apply_selector(es, sel)} == {"a"}


def test_run_filter_applies():
    sel = build_selector(run="r1")
    assert apply_selector([], sel) == []   # smoke: run dimension passes through


@pytest.mark.parametrize("kwargs,expected", [
    ({}, False),
    ({"held": True}, True),
    ({"states": ["packaged"]}, True),
    ({"artist": "dead"}, True),
    ({"run": "r1"}, True),
])
def test_selector_active_truth_table(kwargs, expected):
    assert selector_active(build_selector(**kwargs)) is expected


def test_split_held_drops_held_by_default():
    sel = build_selector()
    es = [e("a", "held"), e("b", "packaged")]
    kept, dropped = split_held(es, sel)
    assert [x.slug for x in kept] == ["b"]
    assert [x.slug for x in dropped] == ["a"]


def test_split_held_keeps_held_when_explicitly_selected():
    sel = build_selector(held=True)
    es = [e("a", "held"), e("b", "packaged")]
    kept, dropped = split_held(es, sel)
    assert {x.slug for x in kept} == {"a", "b"}
    assert dropped == []


def test_split_held_keeps_held_when_in_explicit_state_list():
    sel = build_selector(states=["held", "packaged"])
    es = [e("a", "held"), e("b", "packaged")]
    kept, dropped = split_held(es, sel)
    assert {x.slug for x in kept} == {"a", "b"}
    assert dropped == []


def test_held_note_formatting():
    assert HELD_NOTE.format(n=3) == "note: 3 held show(s) excluded (add --held to include them)"


def test_selector_is_frozen_dataclass():
    sel = build_selector(artist="dead")
    with pytest.raises(Exception):
        sel.artist = "phish"
    assert isinstance(sel, Selector)
