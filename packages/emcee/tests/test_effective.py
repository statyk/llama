"""effective_profile: move > artist rule > llama's profile (spec section 1),
and use-time move validation (spec section 3)."""

import pytest

from emcee.config import EmceeConfig
from emcee.station import (Effective, effective_profile, manifest_artist,
                           manifest_performance_id, manifest_tts, manifest_voiced_profile,
                           manifest_voiced_source, move_target_problem, profile_label,
                           target_problem)

from tests.helpers import moves_of, no_moves

PID = "TedeschiTrucksBand/2012-11-29"
TTB = "Tedeschi Trucks Band"


def _manifest(artist=TTB, profile="funk", pid=PID) -> dict:
    return {"show": {"artist": artist}, "source": {"performance_id": pid, "profile": profile}}


def _cfg(artists=None) -> EmceeConfig:
    return EmceeConfig(assign={"profiles": {"southern": {"presenter": "gregg"},
                                            "funk": {"presenter": "fred"}},
                               "artists": artists or {}})


def test_no_rule_and_no_move_is_llamas_profile():
    assert effective_profile(_cfg(), no_moves(), _manifest()) == Effective("funk", "llama", None)


def test_an_artist_rule_without_from_applies_to_any_delivered_profile():
    got = effective_profile(_cfg({TTB: "southern"}), no_moves(), _manifest())
    assert got == Effective("southern", "artist", TTB)


def test_artist_matching_is_loose_and_reports_the_config_key():
    got = effective_profile(_cfg({"tedeschi trucks band": "southern"}), no_moves(),
                            _manifest(artist="TEDESCHI TRUCKS BAND"))
    assert got == Effective("southern", "artist", "tedeschi trucks band")


def test_from_present_applies_only_from_the_listed_profiles():
    cfg = _cfg({TTB: {"profile": "southern", "from": ["funk"]}})
    assert effective_profile(cfg, no_moves(), _manifest()).source == "artist"
    other = _cfg({TTB: {"profile": "southern", "from": ["dead"]}})
    assert effective_profile(other, no_moves(), _manifest()) == Effective("funk", "llama", None)


def test_a_show_with_no_profile_under_a_rule_with_and_without_from():
    bare = _cfg({TTB: "southern"})
    assert effective_profile(bare, no_moves(), _manifest(profile=None)).profile == "southern"
    gated = _cfg({TTB: {"profile": "southern", "from": ["funk"]}})
    assert effective_profile(gated, no_moves(), _manifest(profile=None)) == \
        Effective(None, "llama", None)


def test_a_move_beats_an_artist_rule():
    got = effective_profile(_cfg({TTB: "southern"}), moves_of({PID: "bluegrass"}), _manifest())
    assert got == Effective("bluegrass", "move", None)


def test_a_move_back_to_the_delivered_profile_beats_a_rule():
    got = effective_profile(_cfg({TTB: "southern"}), moves_of({PID: "funk"}), _manifest())
    assert got == Effective("funk", "move", None)


def test_a_move_to_none():
    assert effective_profile(_cfg(), moves_of({PID: None}), _manifest(profile=None)) == \
        Effective(None, "move", None)


def test_empty_or_non_string_llama_profile_reads_as_none():
    assert effective_profile(_cfg(), no_moves(), _manifest(profile="")).profile is None
    assert effective_profile(_cfg(), no_moves(), _manifest(profile=7)).profile is None


@pytest.mark.parametrize("show", [None, {}, {"artist": 42}, {"artist": None}, "garbage"])
def test_artist_missing_or_not_a_string_falls_to_llama(show):   # Review Focus 1
    manifest = _manifest()
    if show is None:
        del manifest["show"]
    else:
        manifest["show"] = show
    assert effective_profile(_cfg({TTB: "southern"}), no_moves(), manifest) == \
        Effective("funk", "llama", None)


@pytest.mark.parametrize("source", [None, {}, {"performance_id": 9, "profile": "funk"}])
def test_a_move_needs_a_string_performance_id(source):
    manifest = _manifest()
    if source is None:
        del manifest["source"]
    else:
        manifest["source"] = source
    assert effective_profile(_cfg(), moves_of({PID: "southern"}), manifest).source == "llama"


def test_effective_profile_never_raises_on_garbage():
    for garbage in (None, [], "x", 3, {"source": "x", "show": []}):
        assert effective_profile(_cfg({TTB: "southern"}), no_moves(), garbage).source == "llama"


# --- use-time validation ----------------------------------------------------


def test_move_target_problem_cases():
    cfg = _cfg()
    assert move_target_problem(cfg, no_moves(), _manifest()) is None                  # no move
    assert move_target_problem(cfg, moves_of({PID: "southern"}), _manifest()) is None  # assigned
    assert move_target_problem(_cfg(), moves_of({PID: "dead"}), _manifest(profile="dead")) is None
    assert move_target_problem(cfg, moves_of({PID: "gone"}), _manifest()) == \
        'move target "gone" has no [assign.profiles] entry'
    assert move_target_problem(cfg, moves_of({PID: None}), _manifest()) == \
        'move target "(none)" has no [assign.profiles] entry'


def test_target_problem_allows_the_delivered_profile_even_without_an_entry():
    cfg = EmceeConfig()
    assert target_problem(cfg, "funk", "funk") is None
    assert target_problem(cfg, None, None) is None
    assert target_problem(cfg, "funk", "dead") == 'move target "funk" has no [assign.profiles] entry'


# --- accessors ----------------------------------------------------------------


def test_accessors_are_total():
    for garbage in (None, [], "x", {"dj_audio": "x"}, {"source": None}):
        assert manifest_performance_id(garbage) is None
        assert manifest_artist(garbage) is None
        assert manifest_voiced_source(garbage) is None
        assert manifest_tts(garbage) is None
    assert profile_label(None) == "(none)" and profile_label("funk") == "funk"


def test_voiced_profile_prefers_the_recorded_key_and_falls_back_to_llamas():
    legacy = {**_manifest(), "dj_audio": {"set_intros": {}, "outro": "o"}}
    assert manifest_voiced_profile(legacy) == "funk"
    recorded = {**_manifest(), "dj_audio": {"profile": "southern", "profile_source": "artist",
                                            "tts": {"backend": "fake"}}}
    assert manifest_voiced_profile(recorded) == "southern"
    assert manifest_voiced_source(recorded) == "artist"
    assert manifest_tts(recorded) == {"backend": "fake"}
    null = {**_manifest(), "dj_audio": {"profile": None}}
    assert manifest_voiced_profile(null) is None
