"""Filename-valued positional overrides (piece 4 spec 4.1): the legacy test, the
classifier, the migration's mapping and the one resolver gather passes through.

`fixtures/overrides_v2_17_0.py` is e37f670's `Overrides`, vendored as the oracle: a
value is legacy exactly when that model reads it as a track number.
"""
import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from llama.errors import LlamaError
from llama.models import Overrides
from llama.override_keys import (POSITIONAL_KEYS, Positions, classify, filename_values,
                                 legacy_int, rekey_raw, resolve_positions)

FIXTURES = Path(__file__).parent / "fixtures"
SLUG = "gratefuldead-1973-06-10"
GD73 = ["gd73-06-10d1t01.mp3", "gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3",
        "gd73-06-10d2t01.mp3", "gd73-06-10d2t02.mp3", "gd73-06-10d3t01.mp3"]


def _v2_17_0():
    spec = importlib.util.spec_from_file_location(
        "overrides_v2_17_0", FIXTURES / "overrides_v2_17_0.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.OverridesV2170


_PROBES = ["7", " 7", "7.0", "07", "+7", "7_0", True, 7, 2.0, 2.5,
           "gd73-06-10d1t01.mp3", "Track 7", ""]


@pytest.mark.parametrize("v", _PROBES, ids=repr)
def test_legacy_agrees_with_the_v2_17_0_model(v):
    old = _v2_17_0()
    try:
        parsed = old.model_validate_json(json.dumps({"set_breaks": [v]})).set_breaks[0]
    except ValidationError:
        parsed = None
    assert legacy_int(v) == parsed
    if isinstance(v, str):
        # A titles key is judged as the JSON string it is.
        try:
            keys = list(old.model_validate_json(json.dumps({"titles": {v: "X"}})).titles)
            key = keys[0]
        except ValidationError:
            key = None
        assert legacy_int(v) == key


def test_legacy_values_spec_pins():
    """Spec 4.1's list, asserted outright so a pydantic upgrade that moves the
    oracle fails loudly here rather than silently re-agreeing."""
    for v, n in (("7", 7), (" 7", 7), ("7.0", 7), ("07", 7), ("+7", 7), ("7_0", 70),
                 (True, 1), (7, 7), (2.0, 2)):
        assert legacy_int(v) == n, v
    for v in ("gd73-06-10d1t01.mp3", "Track 7", "", 2.5, None):
        assert legacy_int(v) is None, v


@pytest.mark.parametrize("migrated", [
    {"titles": {"gd73-06-10d1t03.mp3": "X"}},
    {"set_breaks": ["gd73-06-10d1t03.mp3"]},
    {"encore_after": "gd73-06-10d1t05.mp3"},
])
def test_old_model_rejects_a_migrated_file(migrated):
    with pytest.raises(ValidationError):
        _v2_17_0().model_validate_json(json.dumps(migrated))


def test_classify():
    for none in ({}, {"set_breaks": []}, {"set_breaks": None}, {"encore_after": None},
                 {"exclude": ["a.mp3"], "narration": "vague", "titles": {}}):
        assert classify(none) == "none", none
    assert classify({"titles": {"3": "X"}}) == "legacy"
    assert classify({"set_breaks": [2, 4]}) == "legacy"
    assert classify({"encore_after": 5}) == "legacy"
    assert classify({"titles": {"3": "X"}, "set_breaks": [], "encore_after": "5"}) == "legacy"
    assert classify({"titles": {GD73[2]: "X"}}) == "filename"
    assert classify({"set_breaks": [GD73[1]], "encore_after": GD73[4]}) == "filename"
    assert classify({"titles": {"3": "X"}, "set_breaks": [GD73[1]]}) == "mixed"


def test_filename_values_lists_every_filename_valued_entry():
    data = {"titles": {"3": "X", GD73[0]: "Y"}, "set_breaks": [2, GD73[1]],
            "encore_after": GD73[4]}
    assert filename_values(data) == [("titles", GD73[0]), ("set_breaks", GD73[1]),
                                     ("encore_after", GD73[4])]


def test_rekey_raw_maps_only_positional_keys_and_keeps_the_rest():
    raw = {"zz": [1, 2], "exclude": ["gd73-06-10d2t02.mp3"], "titles": {"3": "X", "1": "Y"},
           "narration": "vague", "set_breaks": [2, 4], "encore_after": 5}
    out = rekey_raw(raw, GD73)
    assert out == {"zz": [1, 2], "exclude": ["gd73-06-10d2t02.mp3"],
                   "titles": {GD73[2]: "X", GD73[0]: "Y"}, "narration": "vague",
                   "set_breaks": [GD73[1], GD73[3]], "encore_after": GD73[4]}
    assert list(out) == list(raw)                       # key order unchanged
    assert list(out["titles"]) == [GD73[2], GD73[0]]    # titles order unchanged
    assert raw["titles"] == {"3": "X", "1": "Y"}         # a copy: the input is untouched
    empty = rekey_raw({"set_breaks": [], "narration": "full"}, GD73)
    assert empty == {"set_breaks": [], "narration": "full"}
    assert rekey_raw({}, GD73) == {}


def test_rekey_raw_refuses_a_number_outside_the_list():
    for bad in ({"titles": {"7": "X"}}, {"set_breaks": [0]}, {"encore_after": -1}):
        with pytest.raises(IndexError):
            rekey_raw(bad, GD73)
