import re
import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from herder import HerderError, provider_for, resolve_model
from llama.config import DEFAULT_CONFIG_TOML, DEFAULT_TIERS, Config, LLMTaskConfig, load_config
from llama.errors import ConfigError


def test_invalid_audio_format_raises(tmp_path: Path):
    with pytest.raises(ValidationError):
        Config(audio_format="wav")


def test_missing_file_gives_defaults(tmp_path: Path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.audio_format == "mp3"
    assert cfg.llm_for("brief").backend == "claude_cli"


def test_load_and_task_fallback(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        'root = "/tmp/llama-root"\n'
        'audio_format = "flac"\n'
        "[llm.default]\nbackend = \"claude_cli\"\nmodel = \"claude-sonnet-5\"\n"
        "[llm.brief]\nmodel = \"claude-opus-4-8\"\n"
    )
    cfg = load_config(p)
    assert cfg.root == Path("/tmp/llama-root")
    assert cfg.audio_format == "flac"
    assert cfg.llm_for("brief").model == "claude-opus-4-8"
    assert cfg.llm_for("interpret").model == "claude-sonnet-5"  # falls back to default


def test_llm_settings_adapter_carries_config_tables():
    config = Config.model_validate(
        {"llm": {"brief": {"tier": "medium"},
                 "tiers": {"openrouter": {"low": "x/y"}}}})
    s = config.llm_settings()
    assert s.tasks["brief"].tier == "medium"
    assert s.tiers == {"openrouter": {"low": "x/y"}}
    # pydantic copies dicts on validation — compare by value, not identity
    assert s.default_tiers == DEFAULT_TIERS


def test_provider_for_uses_task_config():
    cfg = Config(llm={"default": LLMTaskConfig(model="m-default"),
                      "brief": LLMTaskConfig(model="m-big")})
    assert provider_for(cfg.llm_settings(), "brief").model == "m-big"
    assert provider_for(cfg.llm_settings(), "interpret").model == "m-default"
    with pytest.raises(HerderError):
        bad = Config(llm={"default": LLMTaskConfig(backend="nope")})
        provider_for(bad.llm_settings(), "interpret")


def test_default_tiers_vocabulary():
    assert DEFAULT_TIERS == {
        "interpret": "high", "score_reviews": "medium",
        "light_research": "medium", "extract_setlist": "medium",
        "deep_research": "high", "brief": "high",
        "find_artists": "medium",
        "align_structure": "medium",
        "vet_research": "low",
    }


def test_out_of_box_defaults_are_concrete():
    # Integration: real Config -> llm_settings() -> resolve_model, exercising
    # llama's actual task-tier vocabulary end to end (was test_model_tiers.py's
    # test_out_of_box_defaults_are_concrete before DEFAULT_TIERS moved here).
    settings = Config().llm_settings()
    assert resolve_model(settings, "interpret") == ("claude_cli", "opus")
    assert resolve_model(settings, "score_reviews") == ("claude_cli", "sonnet")
    assert resolve_model(settings, "deep_research") == ("claude_cli", "opus")
    assert resolve_model(settings, "brief") == ("claude_cli", "opus")
    assert resolve_model(settings, "some_future_task") == ("claude_cli", "sonnet")  # medium fallback


import pytest
from pydantic import ValidationError

from llama.config import LLMTaskConfig


def test_tier_accepts_valid_values(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[llm.brief]\ntier = "medium"\n')
    cfg = load_config(p)
    assert cfg.llm_for("brief").tier == "medium"
    assert LLMTaskConfig().tier is None


def test_tier_rejects_invalid_value(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[llm.brief]\ntier = "turbo"\n')
    with pytest.raises(ConfigError):
        load_config(p)


def test_setlistfm_and_structure_defaults():
    cfg = Config()
    assert cfg.setlistfm.api_key is None
    assert cfg.structure.guard_min_minutes == 150
    assert cfg.structure.align_coverage_threshold == 0.8
    assert cfg.winnow.max_metadata_fetch == 40
    assert cfg.selection.tapers["GratefulDead"] == {"miller": 2.0, "seamons": 1.0}
    era = cfg.selection.lineage_eras[0]
    assert (era.collection, era.date_from, era.date_to) == ("GratefulDead", "1980-01-01", "1987-12-31")
    assert era.scores == {"matrix": 3.0, "aud": 2.0, "sbd": 1.0}


def test_setlistfm_and_structure_from_toml(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[setlistfm]\napi_key = "k123"\n\n'
        "[structure]\nguard_min_minutes = 90\n"
        "align_coverage_threshold = 0.5\n\n"
        "[winnow]\nmax_metadata_fetch = 80\n\n"
        "[selection.tapers.GratefulDead]\nmiller = 5.0\n\n"
        "[[selection.lineage_eras]]\ncollection = \"GratefulDead\"\n"
        'date_from = "1980-01-01"\ndate_to = "1984-12-31"\n'
        "scores = { matrix = 4.0, aud = 1.0, sbd = 0.5 }\n"
    )
    cfg = load_config(p)
    assert cfg.setlistfm.api_key == "k123"
    assert cfg.structure.guard_min_minutes == 90
    assert cfg.structure.align_coverage_threshold == 0.5
    assert cfg.winnow.max_metadata_fetch == 80
    assert cfg.selection.tapers["GratefulDead"] == {"miller": 5.0}  # replaces default
    assert cfg.selection.lineage_eras[0].date_to == "1984-12-31"
    assert cfg.selection.lineage_eras[0].scores["matrix"] == 4.0


# --- extra="forbid": an unknown config key must fail loudly, not vanish ----


def test_unknown_top_level_key_raises_through_load_config(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('bogus_top_level_knob = 1\n')
    with pytest.raises(ConfigError):
        load_config(p)


def test_unknown_key_in_nested_pacing_section_raises(tmp_path: Path):
    """The half a strict `Config` alone would miss: pydantic does not
    propagate `model_config` to nested models, so without `PacingConfig`
    itself inheriting the strict base, a typo'd knob here is silently
    discarded (the operator's edit vanishes with no error) instead of
    failing to load."""
    p = tmp_path / "config.toml"
    p.write_text('[pacing]\nfive_hour_ceilingg = 50\n')
    with pytest.raises(ConfigError):
        load_config(p)


def test_unknown_key_in_llm_task_section_raises(tmp_path: Path):
    """`[llm.brief] tierr = "high"` (missing the second `r`) is the likeliest
    real-world typo this whole change exists for."""
    p = tmp_path / "config.toml"
    p.write_text('[llm.brief]\ntierr = "high"\n')
    with pytest.raises(ConfigError):
        load_config(p)


def test_llm_tiers_lifted_from_llm_table(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[llm.tiers.openrouter]\nmedium = "deepseek/deepseek-chat-v3"\n'
        '[llm.tiers.claude_cli]\nhigh = "sonnet"\n'
        '[llm.brief]\ntier = "high"\n'
    )
    cfg = load_config(p)
    assert cfg.tiers == {
        "openrouter": {"medium": "deepseek/deepseek-chat-v3"},
        "claude_cli": {"high": "sonnet"},
    }
    # "tiers" is reserved: it must not appear as a task entry
    assert "tiers" not in cfg.llm
    assert cfg.llm_for("brief").tier == "high"


def test_llm_tiers_rejects_unknown_tier_key(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[llm.tiers.openrouter]\nturbo = "some/model"\n')
    with pytest.raises(ConfigError):
        load_config(p)


def test_tiers_defaults_empty():
    assert Config().tiers == {}


def test_artists_config_defaults_and_override(tmp_path):
    from llama.config import load_config

    assert load_config(tmp_path / "missing.toml").artists.min_recordings == 25
    assert load_config(tmp_path / "missing.toml").artists.min_downloads == 50000
    p = tmp_path / "config.toml"
    p.write_text("[artists]\nmin_recordings = 5\nmin_downloads = 1000\n")
    cfg = load_config(p)
    assert cfg.artists.min_recordings == 5
    assert cfg.artists.min_downloads == 1000


def test_default_config_template_matches_defaults():
    # The seeded file, untouched, must behave exactly like no config file.
    parsed = Config.model_validate(tomllib.loads(DEFAULT_CONFIG_TOML))
    default = Config()
    assert parsed.model_dump(exclude={"llm"}) == default.model_dump(exclude={"llm"})
    # [llm.default] is written out for editability; it must be exactly the
    # built-in fallback, and the only llm entry present.
    assert set(parsed.llm) == {"default"}
    assert parsed.llm_for("interpret") == default.llm_for("interpret")


_TEMPLATE_KEY = re.compile(r"^\s*#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
_TEMPLATE_SECTION = re.compile(r"^\s*#?\s*\[\[?([A-Za-z_][A-Za-z0-9_.\-]*)\]\]?\s*$")


def _template_keys(text: str) -> dict[str, set[str]]:
    """Every key the seeded template mentions, per section path.

    Commented lines count: `config init` documents the path knobs and
    [setlistfm] as commented examples, so a parsed-only view would call a
    correct template incomplete. Nested table headers count too, and for the
    same reason -- [selection.tapers.X] and [[selection.lineage_eras]] are how
    `selection`'s two fields are documented; neither appears as `key =`.
    """
    out: dict[str, set[str]] = {"": set()}
    current = ""
    for line in text.splitlines():
        m = _TEMPLATE_SECTION.match(line)
        if m:
            current = m.group(1)
            parts = current.split(".")
            # `[a.b.c]` documents key `b` of section `a`, `c` of `a.b`, ...
            for i in range(1, len(parts) + 1):
                out.setdefault(".".join(parts[:i - 1]), set()).add(parts[i - 1])
            out.setdefault(current, set())
            continue
        m = _TEMPLATE_KEY.match(line)
        if m:
            out.setdefault(current, set()).add(m.group(1))
    return out


# Free-form maps: `dict[str, LLMTaskConfig]` and `dict[str, dict[Tier, str]]`
# have no fixed key set to assert against, so there is nothing here to check.
_FREE_FORM = {"llm", "tiers"}


def test_the_template_documents_every_config_key():
    """The behaviour comparison above cannot see a key that is simply absent,
    OR one that is simply extra: an absent key silently takes its default,
    and Config sets no `model_config`, so pydantic's default `extra="ignore"`
    silently drops a phantom one too. Either way the comparison still agrees.
    The seeded file is how an operator discovers a knob exists at all -- or
    wrongly believes one does, if a stale/typo'd key sits in the template
    doing nothing. This test pins BOTH directions: every model field must be
    documented (`missing`), and everything documented must be a real model
    field (`phantom`). Measured 2026-09-06: this passes today with no
    template change; it exists to keep that true.
    """
    from pydantic import BaseModel

    sections = _template_keys(DEFAULT_CONFIG_TOML)
    missing: dict[str, list[str]] = {}
    phantom: dict[str, list[str]] = {}
    for name, field in Config.model_fields.items():
        if name in _FREE_FORM:
            continue
        ann = field.annotation
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            documented = sections.get(name, set())
            model_keys = set(ann.model_fields)
            missing_here = model_keys - documented
            phantom_here = documented - model_keys
            if missing_here:
                missing[name] = sorted(missing_here)
            if phantom_here:
                phantom[name] = sorted(phantom_here)
        elif name not in sections[""]:
            missing["<top-level>"] = missing.get("<top-level>", []) + [name]

    phantom_top = sections[""] - set(Config.model_fields)
    if phantom_top:
        phantom["<top-level>"] = sorted(phantom_top)

    assert missing == {} and phantom == {}, (
        f"missing from DEFAULT_CONFIG_TOML: {missing}; "
        f"documented in DEFAULT_CONFIG_TOML but not a Config field: {phantom}"
    )


def test_jerrybase_enabled_default_on():
    from llama.config import Config

    assert Config().jerrybase.enabled is True


def test_jerrybase_disabled_from_toml(tmp_path):
    from llama.config import load_config

    p = tmp_path / "config.toml"
    p.write_text("[jerrybase]\nenabled = false\n")
    assert load_config(p).jerrybase.enabled is False


def test_load_config_bad_toml_raises_config_error(tmp_path):
    from llama.config import load_config

    bad = tmp_path / "config.toml"
    bad.write_text('root = "unterminated\n')  # invalid TOML
    with pytest.raises(ConfigError) as exc:
        load_config(bad)
    assert str(bad) in str(exc.value)


def test_load_config_schema_violation_raises_config_error(tmp_path):
    from llama.config import load_config

    bad = tmp_path / "config.toml"
    bad.write_text('[structure]\nguard_min_minutes = "not-an-int"\n')  # wrong type
    with pytest.raises(ConfigError) as exc:
        load_config(bad)
    assert str(bad) in str(exc.value)


def test_default_config_template_states_selection_defaults():
    # The whole point: the GD tuning is explicit, so additive edits keep it.
    data = tomllib.loads(DEFAULT_CONFIG_TOML)
    assert data["selection"]["tapers"]["GratefulDead"] == {"miller": 2.0, "seamons": 1.0}
    assert data["selection"]["lineage_eras"] == [{
        "collection": "GratefulDead",
        "date_from": "1980-01-01",
        "date_to": "1987-12-31",
        "scores": {"matrix": 3.0, "aud": 2.0, "sbd": 1.0},
    }]


