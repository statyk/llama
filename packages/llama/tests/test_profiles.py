from pathlib import Path

import pytest

from llama.errors import LlamaError
from llama.models import Criteria, SetlistConstraint
from llama.profiles import Profile, ProfileError, delete_profile, list_profiles, load_profile, save_profile


def test_profile_toml_roundtrip_with_none_fields(tmp_path: Path):
    crit = Criteria(query="sunday dead hour", collection="GratefulDead",
                    date_from="1972-01-01", date_to=None,  # None must survive TOML (dropped + re-defaulted)
                    setlist_constraints=[SetlistConstraint(sequence=["Ripple"])])
    p = Profile(name="sunday-dead-hour", criteria=crit, count=2, human_gate=True, script=True)
    path = save_profile(tmp_path, p)
    assert path == tmp_path / "profiles" / "sunday-dead-hour.toml"
    loaded = load_profile(tmp_path, "sunday-dead-hour")
    assert loaded.criteria.collection == "GratefulDead"
    assert loaded.criteria.date_to is None
    assert loaded.criteria.setlist_constraints[0].sequence == ["Ripple"]
    assert loaded.human_gate is True and loaded.count == 2
    assert loaded.script is True


def test_profile_presenter_title_roundtrip_and_unset_omitted(tmp_path: Path):
    crit = Criteria(query="q")
    save_profile(tmp_path, Profile(name="hosted", criteria=crit,
                                   presenter="casey", title="Sunday Morning Dead"))
    loaded = load_profile(tmp_path, "hosted")
    assert loaded.presenter == "casey" and loaded.title == "Sunday Morning Dead"
    path = save_profile(tmp_path, Profile(name="plain", criteria=crit))
    text = path.read_text()
    assert "presenter" not in text and "title" not in text  # TOML has no null
    plain = load_profile(tmp_path, "plain")
    assert plain.presenter is None and plain.title is None


def test_profile_legacy_voice_key_is_ignored(tmp_path: Path):
    # Profile.voice shipped with the ElevenLabs DJ-voice feature and is gone;
    # a hand-edited profile that still carries it must load (key dropped).
    path = tmp_path / "profiles" / "old.toml"
    path.parent.mkdir(parents=True)
    path.write_text('name = "old"\nvoice = "v-legacy"\n[criteria]\nquery = "q"\n')
    loaded = load_profile(tmp_path, "old")
    assert not hasattr(loaded, "voice")


def test_missing_profile_raises_profile_error(tmp_path: Path):
    with pytest.raises(ProfileError) as exc:
        load_profile(tmp_path, "ghost")
    assert "ghost" in str(exc.value)
    assert isinstance(exc.value, LlamaError)     # CLI boundary prints it cleanly


def test_invalid_toml_raises_profile_error(tmp_path: Path):
    path = tmp_path / "profiles" / "bad.toml"
    path.parent.mkdir(parents=True)
    path.write_text("name = [unclosed")
    with pytest.raises(ProfileError):
        load_profile(tmp_path, "bad")


def test_failed_validation_raises_profile_error(tmp_path: Path):
    path = tmp_path / "profiles" / "half.toml"
    path.parent.mkdir(parents=True)
    path.write_text('name = "half"\n')          # no [criteria] table at all
    with pytest.raises(ProfileError):
        load_profile(tmp_path, "half")


def test_delete_profile_removes_file_and_errors_on_unknown(tmp_path: Path):
    crit = Criteria(query="q")
    path = save_profile(tmp_path, Profile(name="gone", criteria=crit))
    assert path.exists()
    removed = delete_profile(tmp_path, "gone")
    assert removed == path
    assert not path.exists()
    with pytest.raises(ProfileError):
        delete_profile(tmp_path, "gone")


def test_list_profiles_returns_name_and_profile_or_error_string(tmp_path: Path):
    save_profile(tmp_path, Profile(name="a", criteria=Criteria(query="q1")))
    save_profile(tmp_path, Profile(name="b", criteria=Criteria(query="q2")))
    bad = tmp_path / "profiles" / "bad.toml"
    bad.write_text("not valid toml [[[")
    rows = list_profiles(tmp_path)
    assert [n for n, _ in rows] == ["a", "b", "bad"]
    by_name = dict(rows)
    assert isinstance(by_name["a"], Profile) and by_name["a"].criteria.query == "q1"
    assert isinstance(by_name["bad"], str)
