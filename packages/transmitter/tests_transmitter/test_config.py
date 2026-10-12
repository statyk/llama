import tomllib
from pathlib import Path

import pytest

from transmitter.config import (DEFAULT_CONFIG_TOML, DEFAULT_ROOT, PRUNE_MARGIN_FLOOR_MINUTES,
                                TransmitterConfig, default_root, load_config)
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


def test_prune_margin_floor_covers_the_live_window_and_player_lag():
    # (k + grace) * d + live.m3u8 max-age + player lag = 92.16 + 5 + 120 s,
    # rounded up to whole minutes.
    assert PRUNE_MARGIN_FLOOR_MINUTES == 4.0
    assert PRUNE_MARGIN_FLOOR_MINUTES * 60 >= (6 + 3) * 10.24 + 60
    assert TransmitterConfig().publish.prune_margin_minutes >= PRUNE_MARGIN_FLOOR_MINUTES


@pytest.mark.parametrize("value", [0, 1.5, 3.99])
def test_a_prune_margin_below_the_floor_is_a_config_error(tmp_path, value):
    path = tmp_path / "config.toml"
    path.write_text(f"[publish]\nprune_margin_minutes = {value}\n")
    with pytest.raises(ConfigError, match="prune_margin_minutes"):
        load_config(path)


def test_a_prune_margin_at_the_floor_is_accepted(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[publish]\nprune_margin_minutes = 4\n")
    assert load_config(path).publish.prune_margin_minutes == 4.0


def test_the_template_states_the_prune_margin_floor():
    assert "at least 4" in DEFAULT_CONFIG_TOML


def test_alerts_defaults_and_floors(tmp_path):
    from transmitter.config import AlertsConfig

    a = AlertsConfig()
    assert (a.smtp_host, a.smtp_port, a.repeat_hours, a.dead_clock_seconds, a.guard_stale_minutes) == \
        ("smtp.gmail.com", 587, 6.0, 120.0, 45.0)
    assert a.email_to is None and a.ntfy_url is None
    path = tmp_path / "c.toml"
    for bad in ('[alerts]\ndead_clock_seconds = 30\n', '[alerts]\nguard_stale_minutes = 30\n',
                '[publish]\nguard_check_minutes = 30\n',          # 30 + 16 is above the default 45
                '[alerts]\nsmtp_password = "x"\n'):
        path.write_text(bad)
        with pytest.raises(ConfigError):
            load_config(path)
    path.write_text('[publish]\nguard_check_minutes = 5\n[alerts]\nguard_stale_minutes = 21\n')
    assert load_config(path).alerts.guard_stale_minutes == 21
