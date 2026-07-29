import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from llama.config import DEFAULT_CONFIG_TOML, DEFAULT_TIERS, Config, load_config
from llama.errors import ConfigError
from llama.llm import resolve_model


def test_invalid_audio_format_raises(tmp_path: Path):
    with pytest.raises(ValidationError):
        Config(audio_format="wav")


def test_missing_file_gives_defaults(tmp_path: Path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.audio_format == "mp3"
    assert cfg.llm_for("synthesize").backend == "claude_cli"


def test_load_and_task_fallback(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        'root = "/tmp/llama-root"\n'
        'audio_format = "flac"\n'
        "[llm.default]\nbackend = \"claude_cli\"\nmodel = \"claude-sonnet-5\"\n"
        "[llm.synthesize]\nmodel = \"claude-opus-4-8\"\n"
    )
    cfg = load_config(p)
    assert cfg.root == Path("/tmp/llama-root")
    assert cfg.audio_format == "flac"
    assert cfg.llm_for("synthesize").model == "claude-opus-4-8"
    assert cfg.llm_for("interpret").model == "claude-sonnet-5"  # falls back to default


def test_llm_settings_adapter_carries_config_tables():
    config = Config.model_validate(
        {"llm": {"synthesize": {"tier": "medium"},
                 "tiers": {"openrouter": {"low": "x/y"}}}})
    s = config.llm_settings()
    assert s.tasks["synthesize"].tier == "medium"
    assert s.tiers == {"openrouter": {"low": "x/y"}}
    # pydantic copies dicts on validation — compare by value, not identity
    assert s.default_tiers == DEFAULT_TIERS


def test_default_tiers_vocabulary():
    assert DEFAULT_TIERS == {
        "interpret": "medium", "score_reviews": "medium",
        "light_research": "medium", "extract_setlist": "medium",
        "deep_research": "high", "synthesize": "high",
        "find_artists": "medium",
        "align_structure": "medium",
        "vet_research": "low",
    }


def test_out_of_box_defaults_are_concrete():
    # Integration: real Config -> llm_settings() -> resolve_model, exercising
    # llama's actual task-tier vocabulary end to end (was test_model_tiers.py's
    # test_out_of_box_defaults_are_concrete before DEFAULT_TIERS moved here).
    settings = Config().llm_settings()
    assert resolve_model(settings, "interpret") == ("claude_cli", "sonnet")
    assert resolve_model(settings, "score_reviews") == ("claude_cli", "sonnet")
    assert resolve_model(settings, "deep_research") == ("claude_cli", "opus")
    assert resolve_model(settings, "synthesize") == ("claude_cli", "opus")
    assert resolve_model(settings, "some_future_task") == ("claude_cli", "sonnet")  # medium fallback


import pytest
from pydantic import ValidationError

from llama.config import LLMTaskConfig


def test_tier_accepts_valid_values(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[llm.synthesize]\ntier = "medium"\n')
    cfg = load_config(p)
    assert cfg.llm_for("synthesize").tier == "medium"
    assert LLMTaskConfig().tier is None


def test_tier_rejects_invalid_value(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[llm.synthesize]\ntier = "turbo"\n')
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


def test_llm_tiers_lifted_from_llm_table(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[llm.tiers.openrouter]\nmedium = "deepseek/deepseek-chat-v3"\n'
        '[llm.tiers.claude_cli]\nhigh = "sonnet"\n'
        '[llm.synthesize]\ntier = "high"\n'
    )
    cfg = load_config(p)
    assert cfg.tiers == {
        "openrouter": {"medium": "deepseek/deepseek-chat-v3"},
        "claude_cli": {"high": "sonnet"},
    }
    # "tiers" is reserved: it must not appear as a task entry
    assert "tiers" not in cfg.llm
    assert cfg.llm_for("synthesize").tier == "high"


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


def test_tts_defaults():
    cfg = Config()
    assert cfg.tts.enabled is False
    assert cfg.tts.backend == "voxtral"
    assert cfg.tts.voice is None
    assert cfg.tts.voice_clone is None
    assert cfg.tts.model is None
    assert cfg.tts.chunk is False


def test_tts_chunk_from_toml(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text("[tts]\nchunk = true\n")
    assert load_config(p).tts.chunk is True


def test_tts_from_toml(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[tts]\nenabled = true\nvoice = "v-abc"\n'
                 'model = "eleven_turbo_v2_5"\napi_key = "k1"\n')
    cfg = load_config(p)
    assert cfg.tts.enabled is True
    assert cfg.tts.voice == "v-abc"
    assert cfg.tts.model == "eleven_turbo_v2_5"
    assert cfg.tts.api_key == "k1"


def test_tts_bed_fields_default_and_roundtrip():
    from llama.config import TTSConfig
    d = TTSConfig()
    assert d.bed is None and d.bed_gain_db == -20.0
    c = TTSConfig(bed="/beds/gd.wav", bed_gain_db=-18.0)
    assert c.bed == "/beds/gd.wav" and c.bed_gain_db == -18.0


def test_default_config_template_documents_tts():
    # Fully commented: the seeded file must still behave exactly like no config
    # file (test_default_config_template_matches_defaults guards this), and
    # [tts] enabled defaults to false.
    assert "# [tts]" in DEFAULT_CONFIG_TOML
    assert "ELEVENLABS_API_KEY" in DEFAULT_CONFIG_TOML
    assert "# chunk" in DEFAULT_CONFIG_TOML
    assert "lameenc" in DEFAULT_CONFIG_TOML
