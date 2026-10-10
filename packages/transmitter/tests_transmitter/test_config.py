import tomllib
from pathlib import Path

import pytest

from transmitter.config import (DEFAULT_CONFIG_TOML, DEFAULT_ROOT, TransmitterConfig,
                                default_root, load_config)
from transmitter.errors import ConfigError


def test_default_root(monkeypatch, tmp_path):
    monkeypatch.delenv("TRANSMITTER_ROOT", raising=False)
    assert default_root() == DEFAULT_ROOT == Path.home() / ".transmitter"
    monkeypatch.setenv("TRANSMITTER_ROOT", str(tmp_path))
    assert default_root() == tmp_path
    assert TransmitterConfig().root == tmp_path


def test_defaults():
    cfg = TransmitterConfig()
    assert cfg.render.lead_hours == 24.0 and cfg.render.low_water_hours == 20.0
    assert cfg.render.music_target_lufs == -16.0 and cfg.render.speech_target_lufs == -16.0
    assert cfg.render.clip_pause_seconds == 0.75 and cfg.render.show_gap_seconds == 2.0
    assert cfg.publish.prune_margin_minutes == 10.0 and cfg.publish.guard_check_minutes == 15.0
    assert cfg.publish.prune_min_segments == 60
    assert cfg.station.root is None


def test_missing_file_gives_defaults(tmp_path):
    assert load_config(tmp_path / "nope.toml") == TransmitterConfig()


@pytest.mark.parametrize("text", [
    "typo = 1\n",                       # top level
    "[render]\nlead_hour = 1\n",        # nested section: strictness must reach it
    "[publish]\nbuckett = 'x'\n",
])
def test_unknown_keys_are_errors(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text)
    with pytest.raises(ConfigError, match="invalid config"):
        load_config(path)


def test_low_water_must_be_below_lead(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[render]\nlead_hours = 10\nlow_water_hours = 10\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_bad_toml_is_a_config_error(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[render\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_template_parses_to_the_defaults():
    parsed = TransmitterConfig.model_validate(tomllib.loads(DEFAULT_CONFIG_TOML))
    assert parsed.model_dump(exclude={"root"}) == TransmitterConfig().model_dump(exclude={"root"})
