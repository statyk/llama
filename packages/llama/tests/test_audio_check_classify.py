import subprocess
import sys
from pathlib import Path

import pytest

from llama.audio_check import classify, decode, model, rule

REPO = Path(__file__).resolve().parents[3]
TONE = REPO / "packages/llama/src/llama/data/audio_check_tone.mp3"


class FakeModel:
    def __init__(self, scores=None, exc=None):
        self.scores, self.exc = scores, exc

    def frame_scores(self, wave):
        if self.exc:
            raise self.exc
        return self.scores


@pytest.fixture
def fake_model(monkeypatch, real_classify):
    import numpy as np

    scores = np.zeros((10, 521), dtype=np.float32)
    fm = FakeModel(scores)
    classify.reset_model_cache()
    monkeypatch.setattr(model, "load", lambda: fm)
    yield fm
    classify.reset_model_cache()


def test_tone_is_tracked_by_git():
    out = subprocess.run(["git", "ls-files", str(TONE)], capture_output=True, text=True, cwd=REPO).stdout
    assert out.strip().endswith("audio_check_tone.mp3")


def test_tone_mp3_decodes_to_16k():
    wave, sec = decode.to_16k_mono(TONE)
    assert 4.5 < sec < 5.5 and abs(len(wave) - 16000 * sec) < 160


def test_non_audio_is_decode_error(tmp_path):
    p = tmp_path / "x.mp3"
    p.write_text("not audio")
    with pytest.raises(decode.DecodeError):
        decode.to_16k_mono(p)


def test_wav_named_mp3_is_decode_error(tmp_path):
    import wave

    p = tmp_path / "x.mp3"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x01" * 48000)
    with pytest.raises(decode.DecodeError):
        decode.to_16k_mono(p)


def test_ogg_content_is_decode_error(tmp_path):
    p = tmp_path / "x.mp3"
    p.write_bytes(b"OggS" + b"\x00" * 200)
    with pytest.raises(decode.DecodeError):
        decode.to_16k_mono(p)


def test_truncated_mp3_is_decode_error(tmp_path):
    p = tmp_path / "cut.mp3"
    p.write_bytes(TONE.read_bytes()[:1500])
    with pytest.raises(decode.DecodeError):
        decode.to_16k_mono(p)


def test_classify_uses_decoded_length_not_metadata(monkeypatch, fake_model):
    import numpy as np

    monkeypatch.setattr(decode, "to_16k_mono", lambda p: (np.zeros(16000, np.float32), 125.0))
    seen = {}
    real = rule.measure

    def spy(scores, duration_sec):
        seen["duration_sec"] = duration_sec
        return real(scores, duration_sec)

    monkeypatch.setattr(rule, "measure", spy)
    res = classify.classify_file(TONE)
    assert seen["duration_sec"] == 125.0
    assert res.verdict == "junk" and res.run_sec == 0


def test_music_scores_give_music_verdict(monkeypatch, fake_model):
    import numpy as np

    monkeypatch.setattr(decode, "to_16k_mono", lambda p: (np.zeros(16000, np.float32), 200.0))
    fake_model.scores[:, model.CLASS_NAMES.index("Music")] = 0.9
    res = classify.classify_file(TONE)
    assert res == classify.Result("music", 200, 1.0)


def test_model_runtime_error_is_unavailable(monkeypatch, real_classify):
    classify.reset_model_cache()
    monkeypatch.setattr(model, "load", lambda: FakeModel(exc=RuntimeError("boom")))
    with pytest.raises(model.ClassifierUnavailable, match="boom") as ei:
        classify.classify_file(TONE)
    assert isinstance(ei.value.__cause__, RuntimeError)
    classify.reset_model_cache()


def test_decode_failure_stays_decode_error(monkeypatch, fake_model, tmp_path):
    p = tmp_path / "x.mp3"
    p.write_text("nope")
    with pytest.raises(decode.DecodeError):
        classify.classify_file(p)


@pytest.mark.real_model
def test_silent_file_is_junk(monkeypatch):
    import numpy as np

    classify.reset_model_cache()
    monkeypatch.setattr(decode, "to_16k_mono", lambda p: (np.zeros(16000 * 4, np.float32), 4.0))
    assert classify.classify_file(TONE).verdict == "junk"
    classify.reset_model_cache()


def test_unavailable_warns_once(monkeypatch, capsys, real_classify):
    classify.reset_model_cache()

    def boom():
        raise model.ClassifierUnavailable("no runtime")

    monkeypatch.setattr(model, "load", boom)
    for _ in range(2):
        with pytest.raises(model.ClassifierUnavailable):
            classify.classify_file(TONE)
    err = capsys.readouterr().err.strip().splitlines()
    assert err == ["llama: audio check unavailable (no runtime); junk-title drops are recorded unchecked"]
    classify.reset_model_cache()


def test_imports_are_lazy():
    code = (
        "import sys, llama.audio_check.classify, llama.audio_check.decode;"
        "bad=[m for m in ('numpy','miniaudio','onnxruntime') if m in sys.modules];"
        "print(bad); sys.exit(1 if bad else 0)"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
