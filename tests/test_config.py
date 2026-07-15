from pathlib import Path

import pytest
from pydantic import ValidationError

from llama.config import Config, load_config


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
    with pytest.raises(ValidationError):
        load_config(p)


def test_setlistfm_and_structure_defaults():
    cfg = Config()
    assert cfg.setlistfm.api_key is None
    assert cfg.structure.guard_min_minutes == 150
    assert cfg.structure.align_coverage_threshold == 0.8


def test_setlistfm_and_structure_from_toml(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[setlistfm]\napi_key = "k123"\n\n'
        "[structure]\nguard_min_minutes = 90\n"
        "align_coverage_threshold = 0.5\n"
    )
    cfg = load_config(p)
    assert cfg.setlistfm.api_key == "k123"
    assert cfg.structure.guard_min_minutes == 90
    assert cfg.structure.align_coverage_threshold == 0.5


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
    with pytest.raises(ValidationError):
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
