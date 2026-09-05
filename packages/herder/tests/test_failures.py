import json
from pathlib import Path

from herder import failures


class FakeProc:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def test_capture_writes_the_whole_envelope(tmp_path):
    failures.set_capture_dir(tmp_path)
    try:
        path = failures.capture_failure(["claude", "-p"], FakeProc(
            stdout=json.dumps({"result": "You've hit your session limit"}),
            stderr="noise", returncode=1))
    finally:
        failures.set_capture_dir(None)
    assert path is not None and path.exists()
    body = path.read_text()
    assert "exit_code: 1" in body
    assert "session limit" in body
    assert "noise" in body
    assert "claude -p" in body


def test_capture_is_a_no_op_when_no_dir_is_set():
    failures.set_capture_dir(None)
    assert failures.capture_failure(["claude"], FakeProc(returncode=1)) is None


def test_capture_never_raises_when_the_dir_is_unwritable(tmp_path):
    # A capture failure must never mask the backend failure being captured.
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("i am a file")
    failures.set_capture_dir(blocked)
    try:
        assert failures.capture_failure(["claude"], FakeProc(returncode=1)) is None
    finally:
        failures.set_capture_dir(None)


def test_capture_never_raises_when_the_write_itself_fails(tmp_path, monkeypatch):
    # test_capture_never_raises_when_the_dir_is_unwritable only blocks
    # mkdir (an OSError, already-covered arm) and never reaches write_text -
    # it passes even if the handler is narrowed to `except FileExistsError`.
    # This one fails on the write, with a non-OSError (ValueError), so it
    # only passes when the handler is broad enough to cover that arm too.
    def _boom(self, *args, **kwargs):
        raise ValueError("simulated encoding failure")

    monkeypatch.setattr(Path, "write_text", _boom)
    failures.set_capture_dir(tmp_path)
    try:
        assert failures.capture_failure(["claude"], FakeProc(returncode=1)) is None
    finally:
        failures.set_capture_dir(None)


def test_each_capture_gets_its_own_file(tmp_path):
    failures.set_capture_dir(tmp_path)
    try:
        a = failures.capture_failure(["claude"], FakeProc(returncode=1, stderr="first"))
        b = failures.capture_failure(["claude"], FakeProc(returncode=1, stderr="second"))
    finally:
        failures.set_capture_dir(None)
    assert a != b
    assert "first" in a.read_text() and "second" in b.read_text()
