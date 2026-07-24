from pathlib import Path

from llama.models import Criteria, SetlistConstraint
from llama.profiles import Profile, load_profile, save_profile


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
