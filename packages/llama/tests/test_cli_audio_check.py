import subprocess
import sys

import pytest

from conftest import cli_invoke
from llama.audio_check import classify, decode, model
from llama.workspace import write_artifact


def _cfg(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(f'root = "{tmp_path}"\n')
    return p


def test_audio_check_cmd_prints_verdict(monkeypatch, tmp_path):
    monkeypatch.setattr(classify, "classify_file",
                        lambda path: classify.Result("music", 42, 0.5))
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    r = cli_invoke(_cfg(tmp_path), "_audio-check", str(f))
    assert r.exit_code == 0
    assert r.stdout.strip() == "verdict=music run=42 frac=0.50"


@pytest.mark.parametrize("exc", [model.ClassifierUnavailable("no model"),
                                 decode.DecodeError("bad audio")])
def test_audio_check_unchecked_exit_2(monkeypatch, tmp_path, exc):
    def boom(path):
        raise exc
    monkeypatch.setattr(classify, "classify_file", boom)
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    r = cli_invoke(_cfg(tmp_path), "_audio-check", str(f))
    assert r.exit_code == 2
    assert f"unchecked: {exc}" in r.output


def test_audio_check_cmd_unchecked_exit_2_missing_file(tmp_path):
    r = cli_invoke(_cfg(tmp_path), "_audio-check", str(tmp_path / "nope.mp3"))
    assert r.exit_code == 2
    assert "unchecked:" in r.output
    assert "Traceback" not in r.output


def test_audio_check_hidden_from_help(tmp_path):
    r = cli_invoke(_cfg(tmp_path), "--help")
    assert r.exit_code == 0
    assert "_audio-check" not in r.output


def _show(tmp_path, slug, rows):
    from llama.workspace import ShowWorkspace
    ws = ShowWorkspace(tmp_path / "shows" / slug)
    write_artifact(ws.show, {"performance_id": f"GratefulDead/{slug}", "identifier": "i",
                             "artist": "Grateful Dead", "date": "1973-06-10",
                             "excluded_files": rows})


def test_status_counts_unchecked_shows(tmp_path):
    unchecked = {"filename": "a.mp3", "reasons": ["junk title"], "check": "unchecked"}
    _show(tmp_path, "s1", [unchecked, dict(unchecked, filename="b.mp3")])  # one show, two rows
    _show(tmp_path, "s2", [unchecked])
    _show(tmp_path, "s3", [dict(unchecked, check="junk")])
    _show(tmp_path, "s4", [{"filename": "c.mp3", "reasons": ["junk title"]}])  # predates the check
    r = cli_invoke(_cfg(tmp_path), "status", "--all")
    assert r.exit_code == 0
    assert "audio check: 2 show(s) with unchecked junk-title drops" in r.output


def test_status_omits_line_when_none_unchecked(tmp_path):
    _show(tmp_path, "s3", [{"filename": "a.mp3", "reasons": [], "check": "junk"}])
    r = cli_invoke(_cfg(tmp_path), "status", "--all")
    assert "audio check" not in r.output


def test_cli_import_does_not_load_runtime():
    code = ("import sys, llama.cli; "
            "bad=[m for m in ('onnxruntime','miniaudio','numpy') if m in sys.modules]; "
            "print(bad); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
