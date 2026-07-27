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


def test_resolve_bed_precedence():
    from llama.config import Config, TTSConfig
    from llama.presenters import Presenter
    from llama.tts.bed import Bed

    station = Config(tts=TTSConfig(bed="/beds/house.wav", bed_gain_db=-18.0))
    none_cfg = Config(tts=TTSConfig())
    host = Presenter(id="h", name="Casey", sex="female", voice="v",
                     character="c", bed="/beds/host.wav")
    plain = Presenter(id="p", name="Sam", sex="male", voice="v", character="c")

    assert cli.resolve_bed(none_cfg, None) is None                       # nothing set
    assert cli.resolve_bed(station, None) == Bed(Path("/beds/house.wav"), -18.0)
    assert cli.resolve_bed(station, host) == Bed(Path("/beds/host.wav"), -18.0)  # presenter wins
    assert cli.resolve_bed(station, plain) == Bed(Path("/beds/house.wav"), -18.0)  # falls back to station
    assert cli.resolve_bed(none_cfg, host) == Bed(Path("/beds/host.wav"), -20.0)   # presenter-only, station default gain


def test_resolve_voice_clone_only_activated_via_flag():
    cfg = Config.model_validate({"tts": {"voice_clone": "/tmp/ref.wav"}})
    assert cli._resolve_voice(cfg, True) == "/tmp/ref.wav"


def test_resolve_voice_clone_only_activated_via_enabled():
    cfg = Config.model_validate(
        {"tts": {"enabled": True, "voice_clone": "/tmp/ref.wav"}})
    assert cli._resolve_voice(cfg, None) == "/tmp/ref.wav"


def test_resolve_voice_no_voice_overrides_clone():
    cfg = Config.model_validate({"tts": {"voice_clone": "/tmp/ref.wav"}})
    assert cli._resolve_voice(cfg, False) is None


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
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--voice", "--no-script", "--name", "vstamp"])
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
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--no-voice", "--name", "novoice"])
    assert result.exit_code == 0, result.output
    saved = json.loads((tmp_path / "runs" / "novoice" / "criteria.json").read_text())
    assert saved["voice"] is None
    assert seen["voice"] is None


def test_profile_add_presenter_and_title(tmp_path: Path, monkeypatch):
    from llama.presenters import Presenter, save_presenter
    from llama.profiles import load_profile

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    save_presenter(tmp_path, Presenter(id="casey", name="Casey", sex="male",
                                       voice="v-casey", character="Warm FM vet."))
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[CRITERIA])})
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "profile", "add", "gdhour", "GD 1973", "--presenter", "casey",
        "--title", "Sunday Morning Dead"])
    assert result.exit_code == 0, result.output
    saved = load_profile(tmp_path, "gdhour")
    assert saved.presenter == "casey" and saved.title == "Sunday Morning Dead"


def test_profile_add_unknown_presenter_fails_fast(tmp_path: Path, monkeypatch):
    from llama.presenters import PresenterError

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[CRITERIA])})
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "profile", "add", "gdhour", "GD 1973", "--presenter", "ghost"])
    assert result.exit_code != 0
    assert isinstance(result.exception, PresenterError)
    assert not (tmp_path / "profiles" / "gdhour.toml").exists()


def test_run_voice_without_force_warns_already_packaged_wont_revoice(
        tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n[tts]\nbackend = "fake"\nvoice = "v-abc"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, CriteriaModel(query="q"))
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: None)
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "run", str(ws.dir), "--voice"])
    assert result.exit_code == 0, result.output
    assert "redo" in result.output and "--from package --voice" in result.output


def test_profile_run_presenter_opts_in_when_globally_disabled(
        tmp_path: Path, monkeypatch):
    from llama.models import Criteria
    from llama.presenters import Presenter, save_presenter
    from llama.profiles import Profile, save_profile

    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n[tts]\nbackend = "fake"\n')  # enabled = false
    save_presenter(tmp_path, Presenter(id="casey", name="Casey", sex="male",
                                       voice="v-casey", character="Warm FM vet."))
    save_profile(tmp_path, Profile(name="voiced",
                                   criteria=Criteria.model_validate_json(CRITERIA),
                                   script=False, presenter="casey",
                                   title="Sunday Morning Dead"))
    seen = {}
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: seen.update(k))
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "--profile", "voiced"])
    assert result.exit_code == 0, result.output
    run_dir = next((tmp_path / "runs").glob("*-voiced"))  # named <today>-voiced
    saved = json.loads((run_dir / "criteria.json").read_text())
    assert saved["voice"] == "v-casey"          # presenter's voice, opted in
    assert saved["presenter"] == "casey" and saved["title"] == "Sunday Morning Dead"
    assert saved["script"] is True              # voice implies script (profile had script=False)
    assert seen["voice"] == "v-casey" and seen["script"] is True


def test_speech_for_resolves_clone_ownership(monkeypatch):
    from llama.presenters import Presenter

    seen = {}
    monkeypatch.setattr(cli, "speech_provider_for",
                        lambda config, voice, clone_ref=None:
                        seen.update(voice=voice, clone_ref=clone_ref))
    cfg = Config.model_validate({"tts": {"voice_clone": "/station/ref.wav"}})
    clone_host = Presenter(id="casey", name="Casey", sex="male",
                           voice_clone="/casey/ref.wav", character="c")
    cli._speech_for(cfg, "/casey/ref.wav", clone_host)
    assert seen == {"voice": "/casey/ref.wav", "clone_ref": "/casey/ref.wav"}
    preset_host = Presenter(id="dana", name="Dana", sex="female",
                            voice="v-dana", character="c")
    cli._speech_for(cfg, "v-dana", preset_host)
    # a preset presenter never inherits the station clone
    assert seen == {"voice": "v-dana", "clone_ref": None}
    cli._speech_for(cfg, "/station/ref.wav", None)
    assert seen == {"voice": "/station/ref.wav", "clone_ref": "/station/ref.wav"}
    assert cli._speech_for(cfg, None, clone_host) is None


def test_run_replay_resolves_presenter_from_criteria(tmp_path: Path, monkeypatch):
    from llama.presenters import Presenter, save_presenter

    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n[tts]\nbackend = "fake"\n')
    save_presenter(tmp_path, Presenter(id="casey", name="Casey", sex="male",
                                       voice="v-casey", character="Warm FM vet."))
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, CriteriaModel(
        query="q", voice="v-casey", presenter="casey", title="Sunday Morning Dead"))
    seen = {}
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: seen.update(k))
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"), "run", str(ws.dir)])
    assert result.exit_code == 0, result.output
    assert seen["presenter"].id == "casey" and seen["presenter"].name == "Casey"
    assert seen["title"] == "Sunday Morning Dead"
    assert seen["voice"] == "v-casey"


def test_run_replay_missing_presenter_file_fails(tmp_path: Path, monkeypatch):
    from llama.presenters import PresenterError

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, CriteriaModel(query="q", presenter="ghost"))
    called = []
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: called.append(1))
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"), "run", str(ws.dir)])
    assert result.exit_code != 0
    assert isinstance(result.exception, PresenterError)
    assert called == []                    # never silently fell back to neutral


def test_profile_run_passes_presenter_and_title_to_execute(
        tmp_path: Path, monkeypatch):
    from llama.models import Criteria
    from llama.presenters import Presenter, save_presenter
    from llama.profiles import Profile, save_profile

    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n[tts]\nbackend = "fake"\n')
    save_presenter(tmp_path, Presenter(id="casey", name="Casey", sex="male",
                                       voice="v-casey", character="Warm FM vet."))
    save_profile(tmp_path, Profile(name="hosted",
                                   criteria=Criteria.model_validate_json(CRITERIA),
                                   presenter="casey", title="Sunday Morning Dead"))
    seen = {}
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: seen.update(k))
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"), "get", "--profile", "hosted"])
    assert result.exit_code == 0, result.output
    assert seen["presenter"].id == "casey"
    assert seen["title"] == "Sunday Morning Dead"
