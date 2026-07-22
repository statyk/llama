import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import llama.cli as cli
from llama.config import Config
from llama.llm.fake import FakeProvider
from llama.models import Criteria as CriteriaModel
from llama.tts.provider import SpeechError
from llama.workspace import RunWorkspace, write_artifact

runner = CliRunner()

CRITERIA = json.dumps({
    "query": "x", "collection": "GratefulDead", "artist": "Grateful Dead",
    "date_from": "1973-01-01", "date_to": "1973-12-31",
    "setlist_constraints": [], "soft_preferences": None,
    "min_avg_rating": 3.5, "min_reviews": 2, "count": 1,
})


def test_resolve_voice_matrix():
    on = Config.model_validate({"tts": {"enabled": True, "voice": "v-global"}})
    off = Config.model_validate({"tts": {"voice": "v-global"}})
    # global flag decides when nothing explicit
    assert cli._resolve_voice(on, None) == "v-global"
    assert cli._resolve_voice(off, None) is None
    # explicit opt-in / opt-out
    assert cli._resolve_voice(off, True) == "v-global"
    assert cli._resolve_voice(on, False) is None
    # explicit profile voice wins — even when globally disabled
    assert cli._resolve_voice(off, None, "v-profile") == "v-profile"
    assert cli._resolve_voice(on, None, "v-profile") == "v-profile"


def test_resolve_voice_active_without_voice_id_raises():
    with pytest.raises(SpeechError):
        cli._resolve_voice(Config.model_validate({"tts": {"enabled": True}}), None)
    with pytest.raises(SpeechError):
        cli._resolve_voice(Config(), True)


def test_replay_voice_defers_to_stamp():
    cfg = Config.model_validate({"tts": {"voice": "v-global"}})
    assert cli._replay_voice(cfg, "v-stamped", None) == "v-stamped"
    assert cli._replay_voice(cfg, "v-stamped", False) is None
    assert cli._replay_voice(cfg, "v-stamped", True) == "v-stamped"
    assert cli._replay_voice(cfg, None, True) == "v-global"  # re-voice from config
    assert cli._replay_voice(cfg, None, None) is None


def test_find_voice_stamps_criteria_and_forces_script(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n[tts]\nbackend = "fake"\nvoice = "v-abc"\n')
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[CRITERIA])})
    seen = {}
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: seen.update(k))
    result = runner.invoke(cli.app, [
        "find", "GD 1973", "--voice", "--no-script", "--run-name", "vstamp",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    saved = json.loads((tmp_path / "runs" / "vstamp" / "criteria.json").read_text())
    assert saved["voice"] == "v-abc"
    assert saved["script"] is True          # voice implies script, despite --no-script
    assert seen["voice"] == "v-abc" and seen["script"] is True


def test_find_no_voice_overrides_global_enable(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n[tts]\nbackend = "fake"\nenabled = true\nvoice = "v-abc"\n')
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[CRITERIA])})
    seen = {}
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: seen.update(k))
    result = runner.invoke(cli.app, [
        "find", "GD 1973", "--no-voice", "--run-name", "novoice",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    saved = json.loads((tmp_path / "runs" / "novoice" / "criteria.json").read_text())
    assert saved["voice"] is None
    assert seen["voice"] is None


def test_profile_add_voice(tmp_path: Path, monkeypatch):
    from llama.profiles import load_profile

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[CRITERIA])})
    result = runner.invoke(cli.app, [
        "profile", "add", "gdhour", "GD 1973", "--voice", "v-abc",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    assert load_profile(tmp_path, "gdhour").voice == "v-abc"


def test_run_voice_without_force_warns_already_packaged_wont_revoice(
        tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n[tts]\nbackend = "fake"\nvoice = "v-abc"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, CriteriaModel(query="q"))
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: None)
    result = runner.invoke(cli.app, [
        "run", str(ws.dir), "--voice", "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    assert "redo" in result.output and "--from package --voice" in result.output


def test_run_voice_with_force_does_not_warn(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n[tts]\nbackend = "fake"\nvoice = "v-abc"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, CriteriaModel(query="q"))
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: None)
    result = runner.invoke(cli.app, [
        "run", str(ws.dir), "--voice", "--force",
        "--config", str(tmp_path / "config.toml"),
    ], input="y\n")
    assert result.exit_code == 0, result.output
    # negation of the without-force assertion: the note (and its
    # "--from package --voice" fragment) must be absent when --force is set
    assert "--from package --voice" not in result.output
    assert "won't be re-voiced" not in result.output


def test_profile_run_explicit_voice_opts_in_when_globally_disabled(
        tmp_path: Path, monkeypatch):
    from llama.models import Criteria
    from llama.profiles import Profile, save_profile

    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n[tts]\nbackend = "fake"\n')  # enabled = false
    save_profile(tmp_path, Profile(name="voiced",
                                   criteria=Criteria.model_validate_json(CRITERIA),
                                   script=False, voice="v-profile"))
    seen = {}
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: seen.update(k))
    result = runner.invoke(cli.app, [
        "profile", "run", "voiced", "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    run_dir = next((tmp_path / "runs").glob("*-voiced"))  # named <today>-voiced
    saved = json.loads((run_dir / "criteria.json").read_text())
    assert saved["voice"] == "v-profile"
    assert saved["script"] is True          # voice implies script (profile had script=False)
    assert seen["voice"] == "v-profile" and seen["script"] is True
