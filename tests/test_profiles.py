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
