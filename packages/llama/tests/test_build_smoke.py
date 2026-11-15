"""Offline tests for packaging/build.py's audio-check smoke step (audio-check plan Task 11).

The frozen llama binary runs `_audio-check` on the committed synthetic tone; the build
fails unless the command exits 0 and its STDOUT starts `verdict=`. stderr (the
`unchecked: <reason>` line, a model-load warning) is never parsed for the verdict.
"""
import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("llama_build_smoke", ROOT / "packaging" / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)


# --- the parser ---------------------------------------------------------------

@pytest.mark.parametrize("stdout, verdict", [
    ("verdict=junk run=0 frac=0.00\n", "junk"),
    ("verdict=music run=130 frac=0.84\n", "music"),
    ("verdict=junk run=0 frac=0.00", "junk"),
])
def test_parse_accepts_a_verdict_line(stdout, verdict):
    assert build.parse_audio_check_output(0, stdout) == verdict


@pytest.mark.parametrize("rc, stdout", [
    (2, ""),                                          # unchecked: reason went to stderr
    (2, "verdict=junk run=0 frac=0.00\n"),            # a verdict with a failing exit still fails
    (0, ""),                                          # nothing printed
    (0, "unchecked: model failed to load\n"),         # not a verdict line
    (0, "warning\nverdict=junk run=0 frac=0.00\n"),   # must START with verdict=
    (0, "verdict=unchecked run=0 frac=0.00\n"),       # outcome must be music or junk
    (0, "verdict= run=0 frac=0.00\n"),
])
def test_parse_rejects_anything_else(rc, stdout):
    with pytest.raises(ValueError):
        build.parse_audio_check_output(rc, stdout)


# --- the smoke step -----------------------------------------------------------

def _fake_run(calls, audio_stdout="verdict=junk run=0 frac=0.00\n", audio_rc=0,
              audio_stderr=""):
    def run(cmd, capture_output=True, text=True, **kw):
        calls.append(list(cmd))
        if cmd[1] == "_audio-check":
            return subprocess.CompletedProcess(cmd, audio_rc, audio_stdout, audio_stderr)
        if cmd[1] == "--version":
            return subprocess.CompletedProcess(cmd, 0, "9.9.9\n", "")
        return subprocess.CompletedProcess(cmd, 0, "usage\n", "")
    return run


@pytest.fixture
def fake_dist(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "DIST", tmp_path)
    for t in build.TARGETS:
        (tmp_path / build.exe_name(t)).write_text("")
    return tmp_path


def test_smoke_runs_audio_check_on_the_source_tree_tone_for_llama(fake_dist, monkeypatch):
    calls = []
    monkeypatch.setattr(build.subprocess, "run", _fake_run(calls))
    build.smoke_test("llama", "9.9.9")
    audio = [c for c in calls if c[1] == "_audio-check"]
    assert audio == [[str(fake_dist / build.exe_name("llama")), "_audio-check",
                      str(ROOT / "packages" / "llama" / "src" / "llama" / "data"
                          / "audio_check_tone.mp3")]]
    assert build.AUDIO_CHECK_TONE.is_file()


def test_smoke_skips_audio_check_for_emcee(fake_dist, monkeypatch):
    calls = []
    monkeypatch.setattr(build.subprocess, "run", _fake_run(calls))
    build.smoke_test("emcee", "9.9.9")
    assert [c[1] for c in calls] == ["--help", "--version"]


@pytest.mark.parametrize("rc, stdout, stderr", [
    (2, "", "unchecked: cannot load the audio-check model\n"),
    (0, "", "warning: the audio check could not load\n"),
])
def test_smoke_fails_the_build_when_the_check_is_unchecked(fake_dist, monkeypatch, rc, stdout,
                                                           stderr):
    calls = []
    monkeypatch.setattr(build.subprocess, "run",
                        _fake_run(calls, audio_stdout=stdout, audio_rc=rc, audio_stderr=stderr))
    with pytest.raises(SystemExit) as exc:
        build.smoke_test("llama", "9.9.9")
    assert "_audio-check" in str(exc.value)
    assert "cannot load" in str(exc.value) or "could not load" in str(exc.value)


def test_smoke_ignores_stderr_noise_when_stdout_has_the_verdict(fake_dist, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(build.subprocess, "run",
                        _fake_run(calls, audio_stderr="some warning\n"))
    build.smoke_test("llama", "9.9.9")
    assert "verdict=junk" in capsys.readouterr().out


def test_spec_bundles_the_audio_check_runtime():
    text = (ROOT / "packaging" / "llama.spec").read_text()
    assert 'collect_dynamic_libs("onnxruntime")' in text
    for mod in ("onnxruntime", "miniaudio", "_miniaudio", "_cffi_backend", "numpy"):
        assert f'"{mod}"' in text
    assert 'collect_data_files("llama.data")' in text
