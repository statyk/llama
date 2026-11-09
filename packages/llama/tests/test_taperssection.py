import pytest
from pydantic import ValidationError

from llama.config import TaperssectionArtist, TaperssectionConfig
from llama.errors import LlamaError
from llama.taperssection import Allowlist, artist_key, is_synthetic, norm_creator


def _entry(name="Phish", creators=None, lineages=None, **kw):
    return TaperssectionArtist(
        name=name, creators=creators or [name], lineages=lineages or ["aud"], **kw
    )


def _al(*entries):
    return Allowlist.from_config(TaperssectionConfig(artists=list(entries)))


def _phish():
    return _al(_entry("Phish"))


def test_norm_creator_folds_case_the_punct():
    assert norm_creator("The Allman Brothers Band") == norm_creator("allman brothers band")
    assert norm_creator("Gov't Mule") == "gov t mule"


def test_key_is_prefixed_slug():
    assert artist_key("Jerry Garcia") == "ts-jerry-garcia"
    assert is_synthetic("ts-phish")
    assert not is_synthetic("GratefulDead")


def test_match_creator_is_exact_not_substring():
    al = _al(_entry("Pearl Jam"))
    e = al.entries[0]
    assert al.match_creator("pearl jam", e)
    assert al.match_creator(["x", "The Pearl Jam"], e)
    assert not al.match_creator(None, e)
    assert not al.match_creator("Vitalogy: Pearl Jam Tribute", e)
    assert not al.match_creator("Even Flow (The Ultimate Pearl Jam Tribute Band)", e)


def test_resolve_name_exact_and_camelcase():
    al = _phish()
    assert al.resolve_name("Phish") is not None
    assert al.resolve_name("Phish").name == "Phish"
    assert al.resolve_name("JazzIsPhish") is None
    assert al.resolve_name("Jazz Is Phish") is None
    assert al.resolve_name(None) is None
    al2 = _al(_entry("Jerry Garcia"))
    assert al2.resolve_name("JerryGarcia").name == "Jerry Garcia"


def test_require_unknown_prefixed_key_raises():
    with pytest.raises(LlamaError, match="ts-old-name"):
        Allowlist.empty().require("ts-old-name")


def test_for_candidate_fails_closed():
    al = _phish()
    assert Allowlist.for_candidate(None, "GratefulDead") is None
    assert Allowlist.for_candidate(al, "GratefulDead") is None
    with pytest.raises(LlamaError):
        Allowlist.for_candidate(None, "ts-phish")
    with pytest.raises(LlamaError):
        Allowlist.for_candidate(Allowlist.empty(), "ts-phish")
    with pytest.raises(LlamaError, match="ts-gone"):
        Allowlist.for_candidate(al, "ts-gone")
    assert Allowlist.for_candidate(al, "ts-phish").name == "Phish"


def test_by_key_key_bool_matching_names():
    al = _al(_entry("Phish", creators=["Phish", "Trey"]))
    e = al.entries[0]
    assert al.key(e) == "ts-phish"
    assert al.by_key("ts-phish") is e
    assert al.by_key("ts-nope") is None
    assert al and not Allowlist.empty()
    assert al.matching_names(e) == ("Phish", "Phish", "Trey")


def test_duplicate_key_rejected():
    with pytest.raises(LlamaError):
        _al(_entry("Phish"), _entry("phish", creators=["Other"]))


def test_shared_creator_rejected():
    with pytest.raises(LlamaError):
        _al(_entry("A", creators=["The Phish"]), _entry("B", creators=["phish"]))


def test_unknown_key_in_config_is_error():
    with pytest.raises(ValidationError):
        TaperssectionArtist(name="X", creators=["X"], lineages=["aud"], bogus=1)


def test_min_lengths_and_dates_validated():
    with pytest.raises(ValidationError):
        TaperssectionArtist(name="X", creators=[], lineages=["aud"])
    with pytest.raises(ValidationError):
        TaperssectionArtist(name="X", creators=["X"], lineages=[])
    with pytest.raises(ValidationError):
        _entry(active_from="1997/01/01")
    assert _entry(active_from="1997-01-01", active_until="2000-12-31")


def test_empty_fingerprint_is_none():
    assert Allowlist.empty().fingerprint() is None


def test_fingerprint_ignores_note_but_not_other_fields():
    a = _al(_entry(note=""))
    b = _al(_entry(note="changed"))
    c = _al(_entry(jerrybase="x"))
    assert a.fingerprint() == b.fingerprint()
    assert a.fingerprint() != c.fingerprint()
    assert len(a.fingerprint()) == 64


def test_template_seeds_empty_allowlist():
    import tomllib
    from llama.config import DEFAULT_CONFIG_TOML, Config

    cfg = Config.model_validate(tomllib.loads(DEFAULT_CONFIG_TOML))
    assert not Allowlist.from_config(cfg.taperssection)
