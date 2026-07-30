"""Tests for emcee's config layer.

Modeled on llama's packages/llama/tests/test_config.py, narrowed to emcee's
section set (station/tts/assign/llm) and the `EMCEE_ROOT`-aware root
resolution added in Task 4.
"""

import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from herder import HerderError, provider_for, resolve_model

from emcee.config import (
    DEFAULT_CONFIG_TOML,
    DEFAULT_ROOT,
    DEFAULT_TIERS,
    Assignment,
    EmceeConfig,
    LLMTaskConfig,
    default_root,
    load_config,
)
from emcee.errors import ConfigError


# --- defaults ---------------------------------------------------------


def test_default_root_is_home_dot_emcee_absent_env(monkeypatch):
    monkeypatch.delenv("EMCEE_ROOT", raising=False)
    assert default_root() == DEFAULT_ROOT == Path.home() / ".emcee"


def test_default_root_honors_emcee_root_env(monkeypatch, tmp_path):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    assert default_root() == tmp_path


def test_config_root_defaults_to_emcee_root_env(monkeypatch, tmp_path):
    # The field default is dynamic: it must pick up EMCEE_ROOT even when
    # the env var is set AFTER emcee.config was imported.
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    assert EmceeConfig().root == tmp_path


def test_defaults_empty_assign_and_voxtral_backend(monkeypatch):
    monkeypatch.delenv("EMCEE_ROOT", raising=False)
    cfg = EmceeConfig()
    assert cfg.root == DEFAULT_ROOT
    assert cfg.station.root is None
    assert cfg.assign.default is None
    assert cfg.assign.profiles == {}
    assert cfg.tts.backend == "voxtral"
    assert not hasattr(cfg.tts, "enabled")  # deliberately dropped vs llama's TTSConfig


def test_missing_file_gives_defaults(tmp_path: Path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.station.root is None
    assert cfg.tts.backend == "voxtral"
    assert cfg.llm_for("scriptwrite").backend == "claude_cli"


# --- TOML round-trip per section ---------------------------------------


def test_station_root_from_toml(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[station]\nroot = "/station/inbox"\n')
    cfg = load_config(p)
    assert cfg.station.root == Path("/station/inbox")


def test_assign_default_and_profiles_from_toml(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[assign]\ndefault = "waldo"\n\n'
        '[assign.profiles.prime-dead]\npresenter = "waldo"\ntitle = "The Primal Dead Hour"\n\n'
        '[assign.profiles.no-title]\npresenter = "casey"\n'
    )
    cfg = load_config(p)
    assert cfg.assign.default == "waldo"
    assert cfg.assign.profiles["prime-dead"] == Assignment(presenter="waldo", title="The Primal Dead Hour")
    assert cfg.assign.profiles["no-title"] == Assignment(presenter="casey", title=None)


def test_llm_scriptwrite_tier_override(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[llm.scriptwrite]\ntier = "medium"\n')
    cfg = load_config(p)
    assert cfg.llm_for("scriptwrite").tier == "medium"
    assert LLMTaskConfig().tier is None


def test_llm_scriptwrite_invalid_tier_fails_at_parse_time(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[llm.scriptwrite]\ntier = "turbo"\n')
    with pytest.raises(ConfigError):
        load_config(p)


def test_llm_tiers_lifted_from_llm_table_not_a_task(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[llm.tiers.openrouter]\nmedium = "deepseek/deepseek-chat-v3"\n'
        '[llm.tiers.claude_cli]\nhigh = "sonnet"\n'
        '[llm.scriptwrite]\ntier = "high"\n'
    )
    cfg = load_config(p)
    assert cfg.tiers == {
        "openrouter": {"medium": "deepseek/deepseek-chat-v3"},
        "claude_cli": {"high": "sonnet"},
    }
    # "tiers" is reserved: it must not appear as a task entry
    assert "tiers" not in cfg.llm
    assert cfg.llm_for("scriptwrite").tier == "high"


def test_llm_tiers_rejects_unknown_tier_key(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[llm.tiers.openrouter]\nturbo = "some/model"\n')
    with pytest.raises(ConfigError):
        load_config(p)


def test_tiers_defaults_empty():
    assert EmceeConfig().tiers == {}


def test_tts_section_from_toml(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[tts]\nbackend = "elevenlabs"\nvoice = "v-abc"\nmodel = "m"\n'
        'chunk = true\nbed = "/beds/soul.wav"\nbed_gain_db = -15.0\n'
    )
    cfg = load_config(p)
    assert cfg.tts.backend == "elevenlabs"
    assert cfg.tts.voice == "v-abc"
    assert cfg.tts.model == "m"
    assert cfg.tts.chunk is True
    assert cfg.tts.bed == "/beds/soul.wav"
    assert cfg.tts.bed_gain_db == -15.0


# --- llm_for / llm_settings ---------------------------------------------


def test_llm_for_falls_back_to_default_entry():
    cfg = EmceeConfig(llm={"default": LLMTaskConfig(model="m-default"),
                          "scriptwrite": LLMTaskConfig(model="m-big")})
    assert cfg.llm_for("scriptwrite").model == "m-big"
    assert cfg.llm_for("some_other_task").model == "m-default"


def test_llm_for_returns_bare_task_config_with_no_default_entry():
    assert EmceeConfig().llm_for("unknown") == LLMTaskConfig()


def test_llm_settings_adapter_carries_default_tiers():
    config = EmceeConfig.model_validate(
        {"llm": {"scriptwrite": {"tier": "medium"},
                 "tiers": {"openrouter": {"low": "x/y"}}}})
    s = config.llm_settings()
    assert s.tasks["scriptwrite"].tier == "medium"
    assert s.tiers == {"openrouter": {"low": "x/y"}}
    # pydantic copies dicts on validation — compare by value, not identity
    assert s.default_tiers == DEFAULT_TIERS


def test_default_tiers_vocabulary():
    assert DEFAULT_TIERS == {"scriptwrite": "high"}


def test_provider_for_uses_task_config():
    cfg = EmceeConfig(llm={"default": LLMTaskConfig(model="m-default"),
                          "scriptwrite": LLMTaskConfig(model="m-big")})
    assert provider_for(cfg.llm_settings(), "scriptwrite").model == "m-big"
    assert provider_for(cfg.llm_settings(), "other_task").model == "m-default"
    with pytest.raises(HerderError):
        bad = EmceeConfig(llm={"default": LLMTaskConfig(backend="nope")})
        provider_for(bad.llm_settings(), "scriptwrite")


def test_out_of_box_defaults_are_concrete():
    settings = EmceeConfig().llm_settings()
    assert resolve_model(settings, "scriptwrite") == ("claude_cli", "opus")
    assert resolve_model(settings, "some_future_task") == ("claude_cli", "sonnet")  # medium fallback


# --- DEFAULT_CONFIG_TOML -------------------------------------------------


def test_default_config_template_matches_defaults():
    # The seeded file, untouched, must behave exactly like no config file --
    # except [assign], which the template fills with a real worked example
    # (not the (empty) built-in default) per the design spec.
    parsed = EmceeConfig.model_validate(tomllib.loads(DEFAULT_CONFIG_TOML))
    default = EmceeConfig()
    assert parsed.model_dump(exclude={"llm", "assign"}) == default.model_dump(exclude={"llm", "assign"})
    # [llm.scriptwrite] is written out for editability; it must be exactly
    # the built-in fallback, and the only llm entry present.
    assert set(parsed.llm) == {"scriptwrite"}
    assert parsed.llm_for("scriptwrite") == default.llm_for("scriptwrite")
    # the worked [assign] example from the design spec
    assert parsed.assign.default == "waldo"
    assert parsed.assign.profiles["prime-dead"] == Assignment(presenter="waldo", title="The Primal Dead Hour")


def test_default_config_template_mentions_every_section():
    for marker in ("[station]", "[llm.scriptwrite]", "[llm.tiers.", "[tts]", "[assign]", "[assign.profiles."):
        assert marker in DEFAULT_CONFIG_TOML, marker


# --- error handling --------------------------------------------------


def test_load_config_bad_toml_raises_config_error(tmp_path):
    bad = tmp_path / "config.toml"
    bad.write_text('root = "unterminated\n')  # invalid TOML
    with pytest.raises(ConfigError) as exc:
        load_config(bad)
    assert str(bad) in str(exc.value)


def test_load_config_schema_violation_raises_config_error(tmp_path):
    bad = tmp_path / "config.toml"
    bad.write_text('[tts]\nbed_gain_db = "not-a-float"\n')  # wrong type
    with pytest.raises(ConfigError) as exc:
        load_config(bad)
    assert str(bad) in str(exc.value)


def test_config_error_is_an_emcee_error():
    from emcee.errors import EmceeError

    assert issubclass(ConfigError, EmceeError)


# --- `emcee config init` -------------------------------------------------


def test_config_init_writes_template(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from emcee.cli import app

    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    runner = CliRunner()
    r = runner.invoke(app, ["config", "init"])
    assert r.exit_code == 0, r.output
    target = tmp_path / "config.toml"
    assert target.exists()
    assert target.read_text() == DEFAULT_CONFIG_TOML
    assert "wrote" in r.output


def test_config_init_refuses_existing_target(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from emcee.cli import app

    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    runner = CliRunner()
    first = runner.invoke(app, ["config", "init"])
    assert first.exit_code == 0, first.output
    second = runner.invoke(app, ["config", "init"])
    assert second.exit_code == 1
    target = tmp_path / "config.toml"
    assert f"{target} already exists - not overwriting" in second.output
    assert "delete it first if you mean to reseed" in second.output


def test_config_init_stdout_prints_without_writing(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from emcee.cli import app

    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    runner = CliRunner()
    r = runner.invoke(app, ["config", "init", "--stdout"])
    assert r.exit_code == 0, r.output
    assert r.output == DEFAULT_CONFIG_TOML
    assert not (tmp_path / "config.toml").exists()


def test_config_init_respects_explicit_config_path(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from emcee.cli import app

    monkeypatch.delenv("EMCEE_ROOT", raising=False)
    runner = CliRunner()
    target = tmp_path / "custom" / "cfg.toml"
    r = runner.invoke(app, ["config", "init", "--config", str(target)])
    assert r.exit_code == 0, r.output
    assert target.exists()
    assert target.read_text() == DEFAULT_CONFIG_TOML
