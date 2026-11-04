"""`emcee lock show|clear`: the operator's view of the station lock, and the
only way a held lock is ever removed."""

import errno
from pathlib import Path

import pytest
from typer.testing import CliRunner

import emcee.cli as cli_mod
import emcee.station_lock as sl
from emcee.cli import app
from emcee.errors import EmceeError
from emcee.station_lock import LOCK_NAME

from tests.helpers import forbid_spend, station_home

runner = CliRunner()
FOREIGN = (b"lma-station-lock 1 " + b"b" * 32 + b"\ntool: llama\ncommand: deliver gd73\n"
           b"host: mac\npid: 999\nstarted: 2026-11-04T09:00:00-08:00\n")


@pytest.fixture(autouse=True)
def _guards(monkeypatch):
    forbid_spend(monkeypatch)
    sl._held = None
    yield
    sl._held = None


def _tty(monkeypatch, value: bool) -> None:
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: value)


def test_lock_show_prints_holder(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    (station / LOCK_NAME).write_bytes(FOREIGN)

    result = runner.invoke(app, ["lock", "show"])

    assert result.exit_code == 0, result.output
    assert str(station / LOCK_NAME) in result.stdout
    assert "command: deliver gd73" in result.stdout
    assert "pid: 999" in result.stdout
    assert (station / LOCK_NAME).read_bytes() == FOREIGN


def test_lock_show_without_lock(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)

    result = runner.invoke(app, ["lock", "show"])

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == f"no station lock at {station / LOCK_NAME}"


def test_lock_show_honours_station_root(tmp_path, monkeypatch):
    station_home(tmp_path, monkeypatch)
    other = tmp_path / "other"
    other.mkdir()
    (other / LOCK_NAME).write_bytes(b"")

    result = runner.invoke(app, ["lock", "show", "--station-root", str(other)])

    assert result.exit_code == 0, result.output
    assert "(empty lock file)" in result.stdout


def test_lock_clear_with_yes_removes_it(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    (station / LOCK_NAME).write_bytes(FOREIGN)

    result = runner.invoke(app, ["lock", "clear", "--yes"])

    assert result.exit_code == 0, result.output
    assert "pid: 999" in result.stdout
    assert "station lock removed" in result.stdout
    assert not (station / LOCK_NAME).exists()


def test_lock_clear_confirmed_at_the_prompt(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    (station / LOCK_NAME).write_bytes(FOREIGN)
    _tty(monkeypatch, True)

    result = runner.invoke(app, ["lock", "clear"], input="y\n")

    assert result.exit_code == 0, result.output
    assert "Remove this lock? [y/N]" in result.output
    assert not (station / LOCK_NAME).exists()


def test_lock_clear_declined_keeps_it(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    (station / LOCK_NAME).write_bytes(FOREIGN)
    _tty(monkeypatch, True)

    result = runner.invoke(app, ["lock", "clear"], input="n\n")

    assert result.exit_code == 0, result.output
    assert "station lock kept" in result.stdout
    assert (station / LOCK_NAME).read_bytes() == FOREIGN


def test_lock_clear_without_tty_or_yes_refuses(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    (station / LOCK_NAME).write_bytes(FOREIGN)
    _tty(monkeypatch, False)

    result = runner.invoke(app, ["lock", "clear"])

    assert result.exit_code == 1
    assert "pass --yes" in result.output
    assert (station / LOCK_NAME).read_bytes() == FOREIGN


def test_lock_clear_refuses_when_the_lock_changed_after_display(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    lock = station / LOCK_NAME
    lock.write_bytes(FOREIGN)
    _tty(monkeypatch, True)
    newer = FOREIGN.replace(b"pid: 999", b"pid: 1000")

    def confirm_after_a_new_writer(*a, **k):
        lock.write_bytes(newer)
        return True

    monkeypatch.setattr(cli_mod.typer, "confirm", confirm_after_a_new_writer)
    result = runner.invoke(app, ["lock", "clear"])

    assert result.exit_code == 1
    assert "the lock changed since it was shown; run again" in result.output
    assert lock.read_bytes() == newer


def test_lock_clear_refuses_when_the_lock_vanished_after_display(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    lock = station / LOCK_NAME
    lock.write_bytes(FOREIGN)
    _tty(monkeypatch, True)

    def confirm_after_release(*a, **k):
        lock.unlink()
        return True

    monkeypatch.setattr(cli_mod.typer, "confirm", confirm_after_release)
    result = runner.invoke(app, ["lock", "clear"])

    assert result.exit_code == 1
    assert "the lock changed since it was shown; run again" in result.output


def test_lock_clear_without_lock(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)

    result = runner.invoke(app, ["lock", "clear", "--yes"])

    assert result.exit_code == 0, result.output
    assert f"no station lock at {station / LOCK_NAME}" in result.stdout


def test_lock_clear_never_holds_a_lock_itself(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    (station / LOCK_NAME).write_bytes(b"\xff\x00junk")

    def no_acquire(*a, **k):
        raise AssertionError("emcee lock clear acquired the station lock")

    monkeypatch.setattr(sl, "acquire", no_acquire)
    monkeypatch.setattr(sl, "station_lock", no_acquire)
    result = runner.invoke(app, ["lock", "clear", "--yes"])

    assert result.exit_code == 0, result.output
    assert "station lock removed" in result.stdout
    assert sorted(p.name for p in station.iterdir()) == []


def test_lock_show_unreadable_lock_is_an_error_not_a_traceback(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    lock = station / LOCK_NAME
    lock.write_bytes(FOREIGN)
    lock.chmod(0)
    try:
        result = runner.invoke(app, ["lock", "show"])
    finally:
        lock.chmod(0o644)

    assert result.exit_code == 1
    assert type(result.exception) is EmceeError
    assert str(result.exception) == (f"cannot read the station lock at {lock}: "
                                     "[Errno 13] Permission denied")


def test_lock_clear_directory_at_the_lock_path_is_an_error(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    (station / LOCK_NAME).mkdir()

    result = runner.invoke(app, ["lock", "clear", "--yes"])

    assert result.exit_code == 1
    assert type(result.exception) is EmceeError
    assert "cannot read the station lock at" in str(result.exception)
    assert (station / LOCK_NAME).is_dir()


def test_lock_clear_unlink_error_is_an_error_not_a_traceback(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    lock = station / LOCK_NAME
    lock.write_bytes(FOREIGN)

    def denied(self, *a, **k):
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(Path, "unlink", denied)
    result = runner.invoke(app, ["lock", "clear", "--yes"])
    monkeypatch.undo()

    assert result.exit_code == 1
    assert type(result.exception) is EmceeError
    assert str(result.exception) == (f"cannot remove the station lock at {lock}: "
                                     "[Errno 13] Permission denied")
    assert lock.read_bytes() == FOREIGN
