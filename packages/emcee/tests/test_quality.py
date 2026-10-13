"""The quality layer: the single re-synthesis on a quality failure
(spec section 3 "Quality layer")."""
import json

import httpx
import pytest
from herder import FakeProvider

from emcee.audio import _synthesize_dj_audio
from emcee.config import EmceeConfig, TTSConfig
from emcee.models import ScriptNotes
from emcee.package_io import Package
from emcee.presenters import Presenter
from emcee.process import process_package
from emcee.tts import speech_provider_for
from emcee.tts.mlx_audio import MlxAudioProvider
from emcee.tts.provider import SpeechBlocked, SpeechDefect, SpeechError
from emcee.tts.quality import QualitySpeech
from emcee.tts.resolve import resolve_tts

from tests.helpers import build_package
from tests.mlx_helpers import (TEST_CAL, TEST_MODEL, calibrate_test_model, plausible_seconds,
                               wav_bytes)

WAV = wav_bytes(1.0)
TEXT = "The tapes have always called the room the Rotterdam Civic Hall."


def defect(text=TEXT):
    return SpeechDefect("mlx_audio", text=text, reason="clip is 13.0s, implausibly long")


class Scripted:
    """Inner-provider double: returns or raises `outcomes` in order."""
    voice = "inner-voice"
    model = "inner-model"

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[tuple] = []
        self.preflights = 0
        self.closed = False

    def synthesize(self, text, fmt="mp3", *, previous_text=None, next_text=None):
        self.calls.append((text, fmt, previous_text, next_text))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def preflight(self):
        self.preflights += 1

    def close(self):
        self.closed = True


def layer(inner):
    return QualitySpeech(inner, backend="mlx_audio", verifier=None)


def test_a_pass_is_returned_without_retry():
    inner = Scripted(WAV)
    assert layer(inner).synthesize(TEXT, "wav") == WAV
    assert len(inner.calls) == 1


def test_one_failure_resynthesizes_once_and_the_retry_wins(capsys):
    inner = Scripted(defect(), WAV)
    assert layer(inner).synthesize(TEXT, "wav") == WAV
    assert len(inner.calls) == 2
    assert (f'mlx_audio quality check failed on "{TEXT}" '
            "(clip is 13.0s, implausibly long); re-synthesizing once"
            ) in capsys.readouterr().out


def test_the_retry_notice_shortens_a_long_sentence(capsys):
    long_text = "Here is the second set, from Pittsburgh, " * 4
    inner = Scripted(defect(), WAV)
    layer(inner).synthesize(long_text, "wav")
    out = capsys.readouterr().out
    assert f'failed on "{long_text[:77]}..." (' in out
    assert long_text not in out


def test_two_failures_raise_a_speech_defect_naming_the_text():
    inner = Scripted(defect(), defect())
    with pytest.raises(SpeechDefect) as exc:
        layer(inner).synthesize(TEXT, "wav")
    assert exc.value.reason == "clip is 13.0s, implausibly long (failed twice)"
    assert exc.value.text == TEXT
    assert exc.value.details == [f'text: "{TEXT}"']
    assert len(inner.calls) == 2


def test_content_filter_blocks_pass_straight_through():
    inner = Scripted(SpeechBlocked("voxtral", text=TEXT, categories=["sexual"]))
    with pytest.raises(SpeechBlocked):
        layer(inner).synthesize(TEXT)
    assert len(inner.calls) == 1


def test_a_transport_error_is_not_a_quality_retry():
    inner = Scripted(SpeechError("mlx-audio server not reachable at x"))
    with pytest.raises(SpeechError) as exc:
        layer(inner).synthesize(TEXT)
    assert not isinstance(exc.value, SpeechDefect)
    assert len(inner.calls) == 1


def test_format_and_context_are_forwarded():
    inner = Scripted(b"MP3")
    assert layer(inner).synthesize(TEXT, "mp3", previous_text="a", next_text="b") == b"MP3"
    assert inner.calls == [(TEXT, "mp3", "a", "b")]


def test_preflight_and_close_are_delegated_and_the_inner_identity_kept():
    inner = Scripted()
    q = layer(inner)
    q.preflight()
    q.close()
    assert inner.preflights == 1 and inner.closed
    assert (q.voice, q.model) == ("inner-voice", "inner-model")


def _assert_nothing_written_for(pkg_dir, stem):
    """A failed segment leaves no clip and no render-cache sidecar entry, so
    a later reorder of write-vs-raise in `_synthesize_dj_audio` fails here."""
    audio_dir = pkg_dir / "dj-audio"
    assert not (audio_dir / f"{stem}.mp3").exists()
    sidecar = audio_dir / "segments.json"
    if sidecar.exists():
        assert f"{stem}.mp3" not in json.loads(sidecar.read_text())


def test_a_double_failure_in_a_dj_clip_carries_its_segment(tmp_path):
    pkg_dir = build_package(tmp_path / "station", voiced=False)
    notes = ScriptNotes(set_intros={"1": TEXT, "2": "Set two."}, outro="Thanks.")
    with pytest.raises(SpeechDefect) as exc:
        _synthesize_dj_audio(pkg_dir, notes, layer(Scripted(defect(), defect())), False)
    assert exc.value.segment == "set1-intro"
    assert "in set1-intro" in str(exc.value)
    _assert_nothing_written_for(pkg_dir, "set1-intro")


def test_a_double_failure_fails_the_package_and_leaves_the_manifest(tmp_path, monkeypatch):
    notes = {"context": "Spring '73 tour",
             "set_intros": {"1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
                            "2": "China Cat Sunflower leads set two."},
             "outro": "I Know You Rider sends us off. Thanks for listening.",
             "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"]}
    monkeypatch.setattr("emcee.process.provider_for",
                        lambda settings, task: FakeProvider(completes=[json.dumps(notes)]))
    pkg = Package(build_package(tmp_path / "station", voiced=False))
    before = pkg.manifest_path.read_bytes()
    config = EmceeConfig(root=tmp_path / "home", tts=TTSConfig(chunk=False))

    with pytest.raises(SpeechDefect):
        process_package(config, pkg, layer(Scripted(defect(), defect())))

    assert pkg.manifest_path.read_bytes() == before
    _assert_nothing_written_for(pkg.dir, "set1-intro")


def test_a_runaway_then_a_good_take_through_the_real_provider(tmp_path):
    clip = tmp_path / "c.wav"
    clip.write_bytes(WAV)
    takes = iter([30.0, plausible_seconds(TEXT)])
    calls: list = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=wav_bytes(next(takes)))

    inner = MlxAudioProvider(url="http://127.0.0.1:8000", model=TEST_MODEL, clone_ref=str(clip),
                             clone_text="Hi there.", calibration=TEST_CAL,
                             transport=httpx.MockTransport(handler))
    assert layer(inner).synthesize(TEXT, "wav")
    assert len(calls) == 2


def test_the_factory_wraps_every_mlx_provider_guard_only(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    clip = tmp_path / "c.wav"
    clip.write_bytes(WAV)
    cfg = EmceeConfig.model_validate({"tts": {"mlx_audio": {"model": TEST_MODEL}}})
    phil = Presenter(id="phil", name="P", sex="male", voice_clone=str(clip),
                     voice_clone_text="Hi there.", tts="mlx_audio", character="x")
    p = speech_provider_for(cfg, resolve_tts(cfg, phil), voice=None, clone_ref=str(clip),
                            clone_text="Hi there.")
    assert isinstance(p, QualitySpeech) and isinstance(p.inner, MlxAudioProvider)
    assert p.verifier is None and p.backend == "mlx_audio"
    assert (p.voice, p.model) == (p.inner.voice, p.inner.model)


def test_hosted_providers_are_not_wrapped_when_verification_is_off(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    cfg = EmceeConfig()
    p = speech_provider_for(cfg, resolve_tts(cfg, None), voice="v", clone_ref=None,
                            clone_text=None)
    assert not isinstance(p, QualitySpeech)


def test_the_retry_notice_keeps_an_80_character_sentence_whole(capsys):
    text = "x" * 79 + "."
    layer(Scripted(defect(), WAV)).synthesize(text, "wav")
    assert f'failed on "{text}" (' in capsys.readouterr().out


def test_the_retry_notice_collapses_whitespace(capsys):
    layer(Scripted(defect(), WAV)).synthesize("Here is\n  the  set.", "wav")
    assert 'failed on "Here is the set." (' in capsys.readouterr().out
