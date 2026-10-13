"""mlx_audio through the factory and the commands: the strict surfaces
(spec Stakes 1 and 2) end to end through `emcee run`, `emcee voice` and
`emcee say --presenter`."""
import json
from pathlib import Path

import pytest
from herder import FakeProvider
from typer.testing import CliRunner

import emcee.process as process_mod
from emcee.cli import _process_one, app
from emcee.config import EmceeConfig, load_config
from emcee.package_io import Package
from emcee.presenters import Presenter, save_presenter
from emcee.process import speech_for
from emcee.tts import speech_provider_for
from emcee.tts.elevenlabs import ElevenLabsProvider
from emcee.tts.mlx_audio import PREFLIGHT_TEXT, MlxAudioProvider
from emcee.tts.provider import SpeechError
from emcee.tts.resolve import resolve_tts
from emcee.tts.voxtral import VoxtralProvider

from tests.helpers import build_package
from tests.mlx_helpers import TEST_MODEL, MlxServer, calibrate_test_model, install_mlx, wav_bytes

runner = CliRunner()
PHIL_TEXT = "It's the chemistry, basically."
SAY_TEXT = "Good evening, everybody, and welcome back to the archive."

_VOXTRAL_HOUSE = '[tts]\nvoice = "house-preset"\n'
_FAKE_HOUSE = '[tts]\nbackend = "fake"\nvoice = "house-preset"\n'
_ASSIGN_DEAD = '[assign.profiles.dead]\npresenter = "phil"\n'
_ASSIGN_ROY = '[assign.profiles.bluegrass]\npresenter = "roy"\n'


def _inner(p):
    # Task 10 wraps mlx providers in the quality layer; look through it.
    return getattr(p, "inner", p)


def _notes_json() -> str:
    return json.dumps({
        "context": "Spring '73 tour",
        "set_intros": {"1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
                       "2": "China Cat Sunflower leads set two."},
        "outro": "I Know You Rider sends us off. Thanks for listening.",
        "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"],
    })


def _arm_llm(monkeypatch) -> list[str]:
    tasks: list[str] = []

    def fake(settings, task):
        tasks.append(task)
        return FakeProvider(completes=[_notes_json()])

    monkeypatch.setattr(process_mod, "provider_for", fake)
    return tasks


def _home(tmp_path, monkeypatch, tts_toml: str, assign_toml: str) -> tuple[Path, Path]:
    home, station = tmp_path / "home", tmp_path / "station"
    home.mkdir()
    station.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text(
        f'[station]\nroot = "{station}"\n\n{tts_toml}\n'
        f'[tts.mlx_audio]\nmodel = "{TEST_MODEL}"\n\n{assign_toml}\n')
    return home, station


def _phil(home: Path, **overrides) -> Presenter:
    clip = home / "phil_ex.wav"
    clip.write_bytes(wav_bytes(1.0))
    d = dict(id="phil", name="Phil", sex="male", voice_clone=str(clip),
             voice_clone_text=PHIL_TEXT, tts="mlx_audio", character="Professorial.")
    d.update(overrides)
    p = Presenter(**d)
    save_presenter(home, p)
    return p


def _roy(home: Path) -> None:
    save_presenter(home, Presenter(id="roy", name="Roy", sex="male", voice="roy-preset",
                                   character="Smooth."))


def _forbid_hosted(monkeypatch) -> list[str]:
    """Fail any construction of a hosted provider, wherever it is imported
    from: the classes' __init__ are patched, not a module's name for them."""
    constructed: list[str] = []

    def forbidden(name):
        def init(self, *args, **kwargs):
            constructed.append(name)
            raise AssertionError(f"{name} constructed for an mlx_audio voice")
        return init

    monkeypatch.setattr(VoxtralProvider, "__init__", forbidden("voxtral"))
    monkeypatch.setattr(ElevenLabsProvider, "__init__", forbidden("elevenlabs"))
    return constructed


def _cmd(command: str, pkg: Path, tmp_path: Path) -> list[str]:
    text = tmp_path / "say.txt"
    text.write_text(SAY_TEXT)
    return {"run": ["run"], "voice": ["voice", str(pkg)],
            "say": ["say", str(text), "--presenter", "phil"]}[command]


# --- the factory ------------------------------------------------------------------


def test_factory_builds_the_mlx_provider_from_the_resolution(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    clip = tmp_path / "c.wav"
    clip.write_bytes(wav_bytes(1.0))
    cfg = EmceeConfig.model_validate({"tts": {"mlx_audio": {
        "model": TEST_MODEL, "url": "http://127.0.0.1:9001/", "timeout_s": 42}}})
    phil = Presenter(id="phil", name="P", sex="male", voice_clone=str(clip),
                     voice_clone_text=PHIL_TEXT, tts="mlx_audio", character="x")
    p = _inner(speech_provider_for(cfg, resolve_tts(cfg, phil), voice=None,
                                   clone_ref=str(clip), clone_text=PHIL_TEXT))
    assert isinstance(p, MlxAudioProvider)
    assert (p.url, p.model, p._ref_text) == ("http://127.0.0.1:9001", TEST_MODEL, PHIL_TEXT)
    assert p._client.timeout.read == 42


@pytest.mark.parametrize("voice, clone, text, match", [
    ("house-preset", True, "Hi there.", r"mlx_audio is clone-only: \[tts\] voice is a preset"),
    (None, False, "Hi there.", r"mlx_audio needs a reference clip: set \[tts\] voice_clone"),
    (None, True, "   ", r"mlx_audio needs the reference clip's transcript: set \[tts\] voice_clone_text"),
])
def test_house_voice_on_mlx_rejects_preset_missing_clip_and_blank_transcript(
        tmp_path, monkeypatch, voice, clone, text, match):
    calibrate_test_model(monkeypatch)
    clip = tmp_path / "h.wav"
    clip.write_bytes(wav_bytes(1.0))
    cfg = EmceeConfig.model_validate({"tts": {"backend": "mlx_audio",
                                              "mlx_audio": {"model": TEST_MODEL}}})
    with pytest.raises(SpeechError, match=match):
        speech_provider_for(cfg, resolve_tts(cfg, None), voice=voice,
                            clone_ref=str(clip) if clone else None, clone_text=text)


def test_house_voice_on_mlx_through_speech_for_needs_its_transcript(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    clip = tmp_path / "h.wav"
    clip.write_bytes(wav_bytes(1.0))
    cfg = EmceeConfig.model_validate({"tts": {"backend": "mlx_audio", "voice_clone": str(clip),
                                              "mlx_audio": {"model": TEST_MODEL}}})
    with pytest.raises(SpeechError, match=r"\[tts\] voice_clone_text"):
        speech_for(cfg, None)


# --- strict surface 1: never silently fall back -----------------------------------


@pytest.mark.parametrize("house", ["voxtral house, mlx presenter", "mlx house"])
@pytest.mark.parametrize("command", ["run", "voice", "say"])
def test_no_fallback_when_the_mlx_server_is_down(tmp_path, monkeypatch, command, house):
    """A Voxtral key in the env and the server down -- with a presenter
    pinned to mlx_audio under a voxtral house, or with the house voice itself
    on mlx_audio (no presenter): the command fails, and no provider but the
    mlx one is constructed (so none is called)."""
    monkeypatch.setenv("MISTRAL_API_KEY", "k-env")
    calibrate_test_model(monkeypatch)
    if house == "mlx house":
        house_clip = tmp_path / "house.wav"
        house_clip.write_bytes(wav_bytes(1.0))
        home, station = _home(tmp_path, monkeypatch,
                              f'[tts]\nbackend = "mlx_audio"\nvoice_clone = "{house_clip}"\n'
                              'voice_clone_text = "Hi there."\n', "")
        pkg = build_package(station, slug="showA")  # no profile: the house voice
    else:
        home, station = _home(tmp_path, monkeypatch, _VOXTRAL_HOUSE, _ASSIGN_DEAD)
        _phil(home)
        pkg = build_package(station, slug="showA", profile="dead")
    args = _cmd(command, pkg, tmp_path)
    if house == "mlx house" and command == "say":
        args = args[:2]  # no --presenter: the house voice
    server = MlxServer(down=True)
    install_mlx(monkeypatch, server)
    constructed = _forbid_hosted(monkeypatch)
    _arm_llm(monkeypatch)

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert constructed == []
    assert server.connect_attempts == 2  # one call, retried once, then failed
    message = str(result.exception) if command == "say" else result.stderr
    assert "mlx-audio server not reachable at http://127.0.0.1:8000" in message


# --- strict surface 2: config-only failure never takes a package off air ---------


def _voiced_then_pinned(tmp_path, monkeypatch) -> Path:
    """A package voiced with phil unpinned (house fake), then phil pinned to
    mlx_audio with the server down."""
    calibrate_test_model(monkeypatch)
    home, station = _home(tmp_path, monkeypatch, _FAKE_HOUSE, _ASSIGN_DEAD)
    _phil(home, tts=None)
    _arm_llm(monkeypatch)
    pkg = build_package(station, slug="showA", profile="dead")
    first = runner.invoke(app, ["voice", str(pkg)])
    assert first.exit_code == 0, first.output
    _phil(home)
    install_mlx(monkeypatch, MlxServer(down=True))
    return pkg


def test_dead_server_leaves_a_voiced_package_untouched(tmp_path, monkeypatch):
    pkg_dir = _voiced_then_pinned(tmp_path, monkeypatch)
    before = (pkg_dir / "manifest.json").read_bytes()
    tasks = _arm_llm(monkeypatch)

    with pytest.raises(SpeechError, match="not reachable"):
        _process_one(load_config(), Package(pkg_dir), False)

    assert tasks == []  # no scriptwrite call
    assert (pkg_dir / "manifest.json").read_bytes() == before


def test_dead_server_voice_fresh_keeps_the_manifest_and_the_clip(tmp_path, monkeypatch):
    pkg_dir = _voiced_then_pinned(tmp_path, monkeypatch)
    before = (pkg_dir / "manifest.json").read_bytes()
    clip = pkg_dir / "dj-audio" / "set1-intro.mp3"
    clip_before = clip.read_bytes()
    tasks = _arm_llm(monkeypatch)

    result = runner.invoke(app, ["voice", str(pkg_dir), "--fresh", "set1-intro"])

    assert result.exit_code == 1
    assert "not reachable" in result.stderr
    assert tasks == []
    assert (pkg_dir / "manifest.json").read_bytes() == before
    assert clip.exists() and clip.read_bytes() == clip_before


def test_run_continues_other_presenters_when_mlx_is_down(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    home, station = _home(tmp_path, monkeypatch, _FAKE_HOUSE, _ASSIGN_DEAD + _ASSIGN_ROY)
    _phil(home)
    _roy(home)
    a = build_package(station, slug="a", profile="dead")
    b = build_package(station, slug="b", profile="bluegrass")
    a_before = (a / "manifest.json").read_bytes()
    install_mlx(monkeypatch, MlxServer(down=True))
    # Track which package each LLM call is made for: the mlx package must
    # fail before its first spend, so the only scriptwrite call is b's.
    current: list[str] = []
    real_process = process_mod.process_package

    def tracked_process(config, pkg, *args, **kwargs):
        current.append(pkg.dir.name)
        return real_process(config, pkg, *args, **kwargs)

    llm_calls: list[tuple[str, str]] = []

    def fake_provider_for(settings, task):
        llm_calls.append((current[-1] if current else "<none>", task))
        return FakeProvider(completes=[_notes_json()])

    monkeypatch.setattr("emcee.cli.process_package", tracked_process)
    monkeypatch.setattr(process_mod, "provider_for", fake_provider_for)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    assert "error: a: mlx-audio server not reachable" in result.stderr
    assert "voiced: b" in result.output
    assert llm_calls == [("b", "scriptwrite")]
    assert (a / "manifest.json").read_bytes() == a_before
    assert json.loads((b / "manifest.json").read_text())["dj_audio"] is not None


# --- the transcript travels on every path -----------------------------------------


@pytest.mark.parametrize("command", ["run", "voice", "say"])
def test_each_path_sends_the_presenters_transcript(tmp_path, monkeypatch, command):
    calibrate_test_model(monkeypatch)
    home, station = _home(tmp_path, monkeypatch, _FAKE_HOUSE, _ASSIGN_DEAD)
    phil = _phil(home)
    pkg = build_package(station, slug="showA", profile="dead")
    server = MlxServer()
    install_mlx(monkeypatch, server)
    _arm_llm(monkeypatch)

    result = runner.invoke(app, _cmd(command, pkg, tmp_path))

    assert result.exit_code == 0, result.output
    assert server.speech_bodies
    ref = str(Path(phil.voice_clone).resolve())
    assert all(b["ref_text"] == PHIL_TEXT and b["ref_audio"] == ref for b in server.speech_bodies)
    first = server.speech_bodies[0]
    if command == "say":  # say has no LLM spend and no manifest: no preflight
        assert first["input"] != PREFLIGHT_TEXT
    else:
        assert (first["input"], first["max_tokens"]) == (PREFLIGHT_TEXT, 200)


# --- one provider per package; distinct cache keys --------------------------------


def test_two_presenters_on_different_backends_get_their_own_provider_and_cache_keys(
        tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    home, station = _home(tmp_path, monkeypatch, _FAKE_HOUSE, _ASSIGN_DEAD + _ASSIGN_ROY)
    _phil(home)
    _roy(home)
    a = build_package(station, slug="a", profile="dead")
    b = build_package(station, slug="b", profile="bluegrass")
    install_mlx(monkeypatch, MlxServer())
    monkeypatch.setattr(process_mod, "provider_for",
                        lambda settings, task: FakeProvider(completes=[_notes_json()]))
    built = []
    real = process_mod.speech_provider_for

    def spy(config, resolution, **kw):
        p = real(config, resolution, **kw)
        built.append((resolution.presenter, resolution.backend, p))
        return p

    monkeypatch.setattr(process_mod, "speech_provider_for", spy)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    assert [(pid, backend) for pid, backend, _ in built] == [("phil", "mlx_audio"), ("roy", "fake")]
    assert built[0][2] is not built[1][2]
    keys_a = json.loads((a / "dj-audio" / "segments.json").read_text())
    keys_b = json.loads((b / "dj-audio" / "segments.json").read_text())
    assert set(keys_a.values()).isdisjoint(keys_b.values())


def test_repinning_a_presenter_changes_the_cache_key(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    home, station = _home(tmp_path, monkeypatch, _FAKE_HOUSE, _ASSIGN_DEAD)
    pkg = build_package(station, slug="showA", profile="dead")
    install_mlx(monkeypatch, MlxServer())
    _arm_llm(monkeypatch)
    sidecar = pkg / "dj-audio" / "segments.json"

    _phil(home, tts=None)
    assert runner.invoke(app, ["voice", str(pkg)]).exit_code == 0
    fake_keys = json.loads(sidecar.read_text())
    _phil(home)
    assert runner.invoke(app, ["voice", str(pkg)]).exit_code == 0
    mlx_keys = json.loads(sidecar.read_text())
    _phil(home, tts=None)
    assert runner.invoke(app, ["voice", str(pkg)]).exit_code == 0

    assert set(fake_keys.values()).isdisjoint(mlx_keys.values())
    assert json.loads(sidecar.read_text()) == fake_keys
