"""Unit tests for the shared, Typer-free selector layer (`llama.cli_select`).

Plan A / foundations: this module isn't wired into any CLI command yet
(that's Plan B) — these tests exercise it directly over synthetic
`CatalogEntry` objects, same pattern as `tests/test_catalog.py` and
`tests/test_broadcast_ready.py::test_select_shows_broadcast_ready_filter`.
"""
from pathlib import Path

import pytest

from llama.catalog import CatalogEntry
from llama.cli_select import (HELD_NOTE, Selector, ShowState, apply_selector,
                              build_selector, selector_active, split_held)
from llama.errors import LlamaError
from llama.workspace import ShowWorkspace


def e(slug, state, *, voiced=None, artist="Grateful Dead",
      broadcast_ready=False) -> CatalogEntry:
    return CatalogEntry(slug=slug, ws=ShowWorkspace(Path("/x")), state=state,
                        voiced=voiced, artist=artist,
                        broadcast_ready=broadcast_ready)


def test_show_state_has_exactly_eight_values():
    assert [s.value for s in ShowState] == [
        "held", "selected", "gathered", "researched", "vetted",
        "scripted", "packaged", "delivered",
    ]


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
    sel = build_selector(states=["packaged"], voiced=True, artist="dead")
    es = [
        e("a", "packaged", voiced=True, artist="Grateful Dead"),
        e("b", "packaged", voiced=False, artist="Grateful Dead"),   # fails voiced
        e("c", "packaged", voiced=True, artist="Phish"),            # fails artist
        e("d", "held", voiced=True, artist="Grateful Dead"),        # fails state
    ]
    assert {x.slug for x in apply_selector(es, sel)} == {"a"}


def test_filters_and_together_with_broadcast_ready():
    sel = build_selector(states=["packaged"], broadcast_ready=True)
    es = [
        e("a", "packaged", broadcast_ready=True),
        e("b", "packaged", broadcast_ready=False),
    ]
    assert {x.slug for x in apply_selector(es, sel)} == {"a"}


def test_run_filter_applies():
    sel = build_selector(run="r1")
    assert apply_selector([], sel) == []   # smoke: run dimension passes through


@pytest.mark.parametrize("kwargs,expected", [
    ({}, False),
    ({"held": True}, True),
    ({"states": ["packaged"]}, True),
    ({"voiced": True}, True),
    ({"unvoiced": True}, True),
    ({"artist": "dead"}, True),
    ({"run": "r1"}, True),
    ({"broadcast_ready": True}, True),
])
def test_selector_active_truth_table(kwargs, expected):
    assert selector_active(build_selector(**kwargs)) is expected


def test_voiced_and_unvoiced_conflict_raises():
    with pytest.raises(LlamaError, match="give --voiced or --unvoiced, not both"):
        build_selector(voiced=True, unvoiced=True)


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
