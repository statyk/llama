"""Tests for emcee's config layer.

Modeled on llama's packages/llama/tests/test_config.py, narrowed to emcee's
section set (station/tts/assign/llm) and the `EMCEE_ROOT`-aware root
resolution added in Task 4.
"""

import tomllib
import unicodedata
from pathlib import Path

import pytest
from pydantic import ValidationError

from herder import HerderError, provider_for, resolve_model

from emcee.config import (
    DEFAULT_CONFIG_TOML,
    DEFAULT_ROOT,
    DEFAULT_TIERS,
    HOSTED_BACKENDS,
    TASK_KEYS,
    Assignment,
    Chunking,
    EmceeConfig,
    HostedTTSConfig,
    LLMTaskConfig,
    MlxAudioConfig,
    TTSConfig,
    VerifyConfig,
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


def test_tts_chunk_defaults_on():
    assert TTSConfig().chunk is True


def test_tiers_defaults_empty():
    assert EmceeConfig().tiers == {}


def test_tts_section_from_toml(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[tts]\nbackend = "elevenlabs"\nvoice = "v-abc"\nmodel = "m"\n'
        'chunk = false\nbed = "/beds/soul.wav"\nbed_gain_db = -15.0\n'
    )
    cfg = load_config(p)
    assert cfg.tts.backend == "elevenlabs"
    assert cfg.tts.voice == "v-abc"
    assert cfg.tts.model == "m"
    assert cfg.tts.chunk is False  # not the default, so this proves the key is read
    assert cfg.tts.bed == "/beds/soul.wav"
    assert cfg.tts.bed_gain_db == -15.0


# --- extra="forbid": an unknown config key must fail loudly, not vanish ----


def test_unknown_top_level_key_raises_through_load_config(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('bogus_top_level_knob = 1\n')
    with pytest.raises(ConfigError):
        load_config(p)


def test_unknown_key_in_nested_tts_section_raises(tmp_path: Path):
    """The half a strict `EmceeConfig` alone would miss: pydantic does not
    propagate `model_config` to nested models, so without `TTSConfig` itself
    inheriting the strict base, a typo'd knob here is silently discarded
    instead of failing to load."""
    p = tmp_path / "config.toml"
    p.write_text('[tts]\nbackendd = "voxtral"\n')
    with pytest.raises(ConfigError):
        load_config(p)


def test_unknown_key_in_assign_profile_block_raises(tmp_path: Path):
    """The emcee-specific case: `[assign.profiles.<name>]` nests a free-form
    llama-profile name one level below a DECLARED shape (`presenter` +
    optional `title`) -- a typo'd `titel` next to `presenter` must fail, even
    though the profile name itself stays unconstrained."""
    p = tmp_path / "config.toml"
    p.write_text(
        '[assign.profiles.prime-dead]\npresenter = "waldo"\ntitel = "oops"\n'
    )
    with pytest.raises(ConfigError):
        load_config(p)


def test_unknown_key_in_llm_task_section_raises(tmp_path: Path):
    """emcee's copy of llama's `test_unknown_key_in_llm_task_section_raises`.
    `[llm.scriptwrite] tierr = "high"` (missing the second `r`) is the
    likeliest real-world typo the whole strictness change exists for, and it
    is the one case emcee's own suite did not cover: reverting the strict
    base on `LLMTaskConfig` in BOTH packages reddened llama and left emcee
    entirely silent. Task names under `[llm.*]` stay free-form -- it is the
    VALUES that are strict."""
    p = tmp_path / "config.toml"
    p.write_text('[llm.scriptwrite]\ntierr = "high"\n')
    with pytest.raises(ConfigError):
        load_config(p)


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
    assert DEFAULT_TIERS == {"scriptwrite": "high", "rephrase": "medium"}


def test_task_keys_vocabulary():
    assert TASK_KEYS == ["scriptwrite", "rephrase"]


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
    # The seeded file, untouched, must behave exactly like no config file.
    parsed = EmceeConfig.model_validate(tomllib.loads(DEFAULT_CONFIG_TOML))
    default = EmceeConfig()
    assert parsed.model_dump(exclude={"llm"}) == default.model_dump(exclude={"llm"})
    # [llm.scriptwrite] is written out for editability; it must be exactly
    # the built-in fallback; [llm.rephrase] is the only other entry present.
    assert set(parsed.llm) == {"scriptwrite", "rephrase"}
    for task in ("scriptwrite", "rephrase"):
        assert parsed.llm_for(task) == default.llm_for(task)


def test_default_config_template_mentions_every_section():
    for marker in ("[station]", "[llm.scriptwrite]", "[llm.rephrase]", "[llm.tiers.", "[tts]", "[assign]", "[assign.profiles.", "[assign.artists]",
                   "voice_clone_text", "[tts.voxtral]", "[tts.elevenlabs]", "[tts.mlx_audio]", "[tts.verify]", "chunk_chars", "room_tone"):
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


# --- [tts] subtables (spec section 1) -------------------------------------


def _load(tmp_path: Path, text: str):
    p = tmp_path / "config.toml"
    p.write_text(text)
    return load_config(p)


def test_hosted_backends_constant():
    assert HOSTED_BACKENDS == ("voxtral", "elevenlabs")


def test_tts_subtable_defaults():
    t = TTSConfig()
    assert t.voice_clone_text is None
    assert t.mlx_audio == MlxAudioConfig()
    assert t.mlx_audio.url == "http://127.0.0.1:8000"
    assert t.mlx_audio.timeout_s == 600
    assert t.mlx_audio.model is None and t.mlx_audio.stt_model is None
    assert t.voxtral == HostedTTSConfig() and t.elevenlabs == HostedTTSConfig()
    assert t.voxtral.api_key is None and t.voxtral.model is None
    assert t.verify == VerifyConfig() and t.verify.backends == []


def test_mlx_audio_table_with_defaults_and_values(tmp_path: Path):
    cfg = _load(tmp_path, '[tts.mlx_audio]\nmodel = "m/x"\nurl = "http://127.0.0.1:9000"\n'
                          'timeout_s = 120\nstt_model = "s/y"\n')
    assert cfg.tts.mlx_audio == MlxAudioConfig(url="http://127.0.0.1:9000", model="m/x",
                                               timeout_s=120, stt_model="s/y")


def test_mlx_audio_table_holding_only_stt_model_is_valid(tmp_path: Path):
    cfg = _load(tmp_path, '[tts.mlx_audio]\nstt_model = "s/y"\n')
    assert cfg.tts.mlx_audio.model is None and cfg.tts.mlx_audio.stt_model == "s/y"


@pytest.mark.parametrize("table", ["voxtral", "elevenlabs", "mlx_audio", "verify"])
def test_every_tts_subtable_is_strict(tmp_path: Path, table):
    with pytest.raises(ConfigError):
        _load(tmp_path, f"[tts.{table}]\nbogus_knob = 1\n")


def test_voice_clone_text_parses(tmp_path: Path):
    cfg = _load(tmp_path, '[tts]\nvoice_clone = "/r.wav"\nvoice_clone_text = "Hi there."\n')
    assert cfg.tts.voice_clone_text == "Hi there."


# The live ~/.emcee/config.toml's shape on 2026-10-12 (key redacted): a hosted
# house backend with legacy [tts] api_key, chunk and bed_gain_db.
LIVE_CONFIG = """
[station]
root = "/Volumes/media/lma-radio/delivered/"

[llm.scriptwrite]
backend = "claude_cli"

[tts]
voice_clone = "/Users/shawn/.emcee/samples/troymcclure2.wav"
api_key = "redacted"
chunk = true
bed_gain_db = -20.0

[assign]
default = "roydemure"

[assign.profiles.bluegrass]
presenter = "monroe"
title = "Bluegrass Valley"

[assign.profiles.dead]
presenter = "phil"
title = "One More from the Archive"

[assign.profiles.indie]
presenter = "kurt"
title = "Live from the Basement"
"""


def test_live_config_loads(tmp_path: Path):
    cfg = _load(tmp_path, LIVE_CONFIG)
    assert cfg.tts.backend == "voxtral" and cfg.tts.api_key == "redacted"
    assert cfg.tts.voxtral.api_key is None


def test_house_mlx_rejects_legacy_api_key_naming_the_subtables(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, '[tts]\nbackend = "mlx_audio"\napi_key = "k"\n')
    msg = str(exc.value)
    assert "[tts] api_key is not valid when [tts] backend is mlx_audio" in msg
    assert "[tts.voxtral] or [tts.elevenlabs] api_key" in msg


def test_house_mlx_rejects_legacy_model_naming_mlx_model(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, '[tts]\nbackend = "mlx_audio"\nmodel = "m"\n')
    assert ("[tts] model is not valid when [tts] backend is mlx_audio; "
            "set [tts.mlx_audio] model") in str(exc.value)


@pytest.mark.parametrize("backend", ["voxtral", "elevenlabs"])
def test_legacy_key_and_model_valid_under_a_hosted_house(tmp_path: Path, backend):
    cfg = _load(tmp_path, f'[tts]\nbackend = "{backend}"\napi_key = "k"\nmodel = "m"\n')
    assert (cfg.tts.api_key, cfg.tts.model) == ("k", "m")


@pytest.mark.parametrize("key", ["api_key", "model"])
def test_same_key_in_tts_and_house_subtable_names_both(tmp_path: Path, key):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, f'[tts]\n{key} = "a"\n\n[tts.voxtral]\n{key} = "b"\n')
    assert f"[tts] {key} and [tts.voxtral] {key} are both set" in str(exc.value)


def test_same_key_in_tts_and_a_non_house_subtable_is_fine(tmp_path: Path):
    cfg = _load(tmp_path, '[tts]\napi_key = "mistral"\n\n[tts.elevenlabs]\napi_key = "el"\n')
    assert (cfg.tts.api_key, cfg.tts.elevenlabs.api_key) == ("mistral", "el")


@pytest.mark.parametrize("name", ["fake", "kokoro", "MLX_AUDIO"])
def test_verify_rejects_unknown_backend_names(tmp_path: Path, name):
    with pytest.raises(ConfigError):
        _load(tmp_path, f'[tts.mlx_audio]\nstt_model = "s"\n\n[tts.verify]\nbackends = ["{name}"]\n')


def test_verify_nonempty_requires_stt_model(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, '[tts.verify]\nbackends = ["mlx_audio"]\n')
    assert "[tts.verify] backends needs [tts.mlx_audio] stt_model" in str(exc.value)


def test_verify_with_stt_model_is_valid(tmp_path: Path):
    cfg = _load(tmp_path, '[tts.mlx_audio]\nstt_model = "s"\n\n'
                          '[tts.verify]\nbackends = ["mlx_audio", "voxtral"]\n')
    assert cfg.tts.verify.backends == ["mlx_audio", "voxtral"]


# --- [assign.artists] (2026-10-16 profile reassignment, spec section 2) ---

from emcee.config import ArtistRule

_SOUTHERN = '[assign.profiles.southern]\npresenter = "gregg"\n\n'


def test_artist_shorthand_and_table_forms_parse_the_same(tmp_path: Path):
    short = _load(tmp_path, _SOUTHERN + '[assign.artists]\n"Tedeschi Trucks Band" = "southern"\n')
    table = _load(tmp_path, _SOUTHERN + '[assign.artists]\n'
                  '"Tedeschi Trucks Band" = { profile = "southern" }\n')
    assert short.assign.artists == table.assign.artists
    assert short.assign.artists["Tedeschi Trucks Band"] == ArtistRule(profile="southern")
    assert short.assign.artists["Tedeschi Trucks Band"].from_ is None


def test_artist_rule_from_list_parses(tmp_path: Path):
    cfg = _load(tmp_path, _SOUTHERN + '[assign.artists]\n'
                '"JJ Grey and MOFRO" = { profile = "southern", from = ["funk"] }\n')
    assert cfg.assign.artists["JJ Grey and MOFRO"].from_ == ["funk"]


def test_artists_default_empty():
    assert EmceeConfig().assign.artists == {}


def test_artist_rule_targeting_a_profile_without_an_entry_is_a_load_error(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, '[assign.artists]\n"Tedeschi Trucks Band" = "southern"\n')
    assert '"Tedeschi Trucks Band"' in str(exc.value)
    assert "[assign.profiles.southern]" in str(exc.value)


def test_two_artist_keys_normalizing_alike_is_a_load_error_naming_both(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, _SOUTHERN + '[assign.artists]\n'
              '"Karl Denson\'s Tiny Universe" = "southern"\n'
              '"Karl Densons Tiny Universe" = "southern"\n')
    assert "Karl Denson's Tiny Universe" in str(exc.value)
    assert "Karl Densons Tiny Universe" in str(exc.value)


def test_decomposed_and_precomposed_artist_keys_are_a_duplicate(tmp_path: Path):
    nfc = unicodedata.normalize("NFC", "Béla Fleck")
    nfd = unicodedata.normalize("NFD", "Béla Fleck")
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, _SOUTHERN + f'[assign.artists]\n"{nfc}" = "southern"\n'
              f'"{nfd}" = "southern"\n')
    assert "name the same artist" in str(exc.value)


def test_artist_key_normalizing_to_empty_is_a_load_error(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, _SOUTHERN + '[assign.artists]\n"!!!" = "southern"\n')
    assert "empty artist name" in str(exc.value)


def test_an_empty_profile_name_is_a_load_error(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, '[assign.profiles.""]\npresenter = "gregg"\n')
    assert "profile names must be non-empty" in str(exc.value)


def test_empty_from_list_is_a_load_error(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, _SOUTHERN + '[assign.artists]\n'
              '"Lettuce" = { profile = "southern", from = [] }\n')
    assert "can never match" in str(exc.value)


def test_unknown_key_in_an_artist_rule_is_a_load_error(tmp_path: Path):
    with pytest.raises(ConfigError):
        _load(tmp_path, _SOUTHERN + '[assign.artists]\n'
              '"Lettuce" = { profile = "southern", form = ["funk"] }\n')


# --- chunking knobs ----------------------------------------------------


def test_chunk_chars_defaults_and_bounds():
    assert TTSConfig().chunk_chars == 250 and TTSConfig().room_tone is True
    assert TTSConfig(chunk_chars=50).chunk_chars == 50
    assert TTSConfig(chunk_chars=1000).chunk_chars == 1000


@pytest.mark.parametrize("bad", [49, 1001, "250", 250.0, 250.5, True])
def test_chunk_chars_rejects_non_strict_ints_and_out_of_range(bad):
    with pytest.raises(ValidationError):
        TTSConfig(chunk_chars=bad)


def test_chunk_chars_bad_value_in_config_toml_is_a_load_error(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[tts]\nchunk_chars = "250"\n')
    with pytest.raises(ConfigError):
        load_config(p)


def test_tts_chunking_helper():
    t = TTSConfig(chunk_chars=300, room_tone=False)
    assert t.chunking(enabled=True) == Chunking(ceiling=300, room_tone=False)
    assert t.chunking(enabled=False) is None
