"""The station lock (`emcee.station_lock`): the on-disk contract shared with
llama's twin, refusal on any existing lock, token-checked release, signal
handling and the non-reentrancy guard."""

import errno
import os
import re
import signal
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path

import pytest

import emcee.station_lock as sl
from emcee.errors import EmceeError
from emcee.station_lock import (
    LOCK_NAME, MAGIC, StationLocked, StationLockReentry, acquire, holder_text, read_lock,
    release, station_lock, token_of,
)

FOREIGN = (b"lma-station-lock 1 " + b"a" * 32 + b"\ntool: llama\ncommand: deliver x\n"
           b"host: elsewhere\npid: 4242\nstarted: 2026-11-04T09:00:00-08:00\n")


@pytest.fixture(autouse=True)
def _reset_held():
    sl._held = None
    yield
    sl._held = None


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_acquire_writes_magic_token_and_holder(tmp_path):
    with station_lock(tmp_path, command="voice gd73-06-10") as held:
        raw = (tmp_path / LOCK_NAME).read_bytes()
        assert raw.endswith(b"\n")
        lines = raw.decode("utf-8").splitlines()
        assert re.fullmatch(r"lma-station-lock 1 [0-9a-f]{32}", lines[0])
        assert lines[0] == f"{MAGIC} {held.token}"
        assert token_of(raw) == held.token
        fields = dict(line.split(": ", 1) for line in lines[1:])
        assert list(fields) == ["tool", "command", "host", "pid", "started"]
        assert fields["tool"] == "emcee"
        assert fields["command"] == "voice gd73-06-10"
        assert fields["host"]
        assert fields["pid"] == str(os.getpid())
        started = datetime.fromisoformat(fields["started"])
        assert started.utcoffset() is not None


def test_lock_path_is_the_delivered_folder(tmp_path):
    with station_lock(tmp_path, command="run") as held:
        assert held.path == tmp_path / ".lma-station.lock"
        assert held.path.is_file()
    assert not held.path.exists()


def test_held_lock_is_refused_naming_its_holder(tmp_path):
    (tmp_path / LOCK_NAME).write_bytes(FOREIGN)
    with pytest.raises(StationLocked) as e:
        with station_lock(tmp_path, command="run"):
            pytest.fail("entered a held lock")
    exc = e.value
    assert str(exc) == f"the station is locked by another writer ({tmp_path / LOCK_NAME})"
    assert exc.path == tmp_path / LOCK_NAME
    assert "host: elsewhere" in exc.holder and "pid: 4242" in exc.holder
    assert "tool: llama" in exc.details
    assert exc.details[-1] == ("check it with: emcee lock show; remove it with: "
                               "emcee lock clear (only if that writer is gone)")
    assert (tmp_path / LOCK_NAME).read_bytes() == FOREIGN


def test_empty_lock_counts_as_held(tmp_path):
    (tmp_path / LOCK_NAME).write_bytes(b"")
    with pytest.raises(StationLocked) as e:
        acquire(tmp_path / LOCK_NAME, command="run")
    assert e.value.holder == "(empty lock file)"
    assert holder_text(b"") == "(empty lock file)"
    assert (tmp_path / LOCK_NAME).read_bytes() == b""


def test_garbage_lock_counts_as_held(tmp_path):
    (tmp_path / LOCK_NAME).write_bytes(b"\xff\x00junk")
    with pytest.raises(StationLocked) as e:
        acquire(tmp_path / LOCK_NAME, command="run")
    assert "junk" in e.value.holder
    assert "\x00" not in e.value.holder          # control bytes are shown escaped
    assert token_of(b"\xff\x00junk") is None
    assert (tmp_path / LOCK_NAME).read_bytes() == b"\xff\x00junk"


def test_lock_vanished_while_reading_is_still_a_refusal(tmp_path, monkeypatch):
    (tmp_path / LOCK_NAME).write_bytes(FOREIGN)

    def vanish(path):
        Path(path).unlink()
        raise FileNotFoundError(errno.ENOENT, "No such file or directory")

    monkeypatch.setattr(sl, "_read", vanish)
    with pytest.raises(StationLocked) as e:
        acquire(tmp_path / LOCK_NAME, command="run")
    assert e.value.holder == "(lock vanished while reading)"
    assert not (tmp_path / LOCK_NAME).exists()   # never retried


def test_second_acquire_in_one_process_raises_reentry(tmp_path):
    other = tmp_path / "other-missing"           # never created: the guard runs first
    with station_lock(tmp_path, command="run") as held:
        with pytest.raises(StationLockReentry):
            with station_lock(tmp_path, command="run"):
                pass
        with pytest.raises(StationLockReentry):
            with station_lock(other, command="run"):
                pass
        assert token_of((tmp_path / LOCK_NAME).read_bytes()) == held.token
    assert not (tmp_path / LOCK_NAME).exists()
    assert not other.exists()


def test_release_unlinks_only_its_own_token(tmp_path, capsys):
    with station_lock(tmp_path, command="run"):
        (tmp_path / LOCK_NAME).write_bytes(FOREIGN)
    assert (tmp_path / LOCK_NAME).read_bytes() == FOREIGN
    err = capsys.readouterr().err
    assert f"warning: the station lock at {tmp_path / LOCK_NAME} was not ours at release" in err
    assert "pid: 4242" in err
    assert "unguarded" in err


def test_release_warns_when_the_lock_is_missing(tmp_path, capsys):
    with station_lock(tmp_path, command="run"):
        (tmp_path / LOCK_NAME).unlink()
    err = capsys.readouterr().err
    assert "was not ours at release (missing); writes since " in err
    assert "ran unguarded" in err


def test_exception_inside_releases(tmp_path):
    with pytest.raises(ValueError, match="boom"):
        with station_lock(tmp_path, command="run"):
            raise ValueError("boom")
    assert not (tmp_path / LOCK_NAME).exists()
    # and the guard is clear: the next acquire works
    with station_lock(tmp_path, command="run"):
        pass


_HOLDER_SCRIPT = textwrap.dedent("""
    import sys, time
    from pathlib import Path
    from emcee.station_lock import station_lock
    with station_lock(Path(sys.argv[1]), command="sleep"):
        print("held", flush=True)
        time.sleep(60)
""")


def _signal_releases_the_lock(tmp_path, signum):
    proc = subprocess.Popen([sys.executable, "-c", _HOLDER_SCRIPT, str(tmp_path)],
                            stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "held"
        assert (tmp_path / LOCK_NAME).exists()
        proc.send_signal(signum)
        assert proc.wait(timeout=20) == 128 + signum
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        proc.stdout.close()
    assert not (tmp_path / LOCK_NAME).exists()


def test_sigterm_releases_the_lock(tmp_path):
    _signal_releases_the_lock(tmp_path, signal.SIGTERM)


def test_sighup_releases_the_lock(tmp_path):
    _signal_releases_the_lock(tmp_path, signal.SIGHUP)


def test_previous_signal_handlers_are_restored(tmp_path):
    def mine(signum, frame):
        pass

    saved = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP)}
    try:
        for s in saved:
            signal.signal(s, mine)
        with station_lock(tmp_path, command="run"):
            assert signal.getsignal(signal.SIGTERM) is not mine
            assert signal.getsignal(signal.SIGHUP) is not mine
        assert signal.getsignal(signal.SIGTERM) is mine
        assert signal.getsignal(signal.SIGHUP) is mine

        (tmp_path / LOCK_NAME).write_bytes(FOREIGN)     # acquire refuses
        with pytest.raises(StationLocked):
            with station_lock(tmp_path, command="run"):
                pass
        assert signal.getsignal(signal.SIGTERM) is mine
        assert signal.getsignal(signal.SIGHUP) is mine
    finally:
        for s, h in saved.items():
            signal.signal(s, h)


def test_write_failure_after_create_removes_the_file(tmp_path, monkeypatch):
    def broken_write(fd, data):
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(sl.os, "write", broken_write)
    with pytest.raises(OSError, match="Input/output error"):
        acquire(tmp_path / LOCK_NAME, command="run")
    monkeypatch.undo()
    assert not (tmp_path / LOCK_NAME).exists()
    assert sl._held is None


def test_create_error_other_than_eexist_is_a_refusal(tmp_path, monkeypatch):
    missing = tmp_path / "no-such-delivered"
    with pytest.raises(EmceeError) as e:
        acquire(missing / LOCK_NAME, command="run")
    assert type(e.value) is EmceeError
    assert str(e.value) == (f"cannot create the station lock at {missing / LOCK_NAME}: "
                            "[Errno 2] No such file or directory")
    assert "FileNotFoundError" not in str(e.value)

    def denied(*a, **k):
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(sl.os, "open", denied)
    with pytest.raises(EmceeError) as e:
        acquire(tmp_path / LOCK_NAME, command="run")
    assert type(e.value) is EmceeError
    assert "[Errno 13] Permission denied" in str(e.value)
    assert "PermissionError" not in str(e.value)
    assert sl._held is None


def test_release_unlink_error_warns_and_never_raises(tmp_path, monkeypatch, capsys):
    def busy(path, *a, **k):
        raise OSError(errno.EBUSY, "Resource busy")

    with station_lock(tmp_path, command="run"):
        monkeypatch.setattr(sl.os, "unlink", busy)
    monkeypatch.undo()
    err = capsys.readouterr().err
    assert f"warning: could not remove the station lock at {tmp_path / LOCK_NAME}" in err
    assert "clear it with: emcee lock clear" in err
    assert (tmp_path / LOCK_NAME).exists()
    assert sl._held is None


def test_release_read_error_warns_and_never_raises(tmp_path, monkeypatch, capsys):
    def unreadable(path):
        raise OSError(errno.EIO, "Input/output error")

    with station_lock(tmp_path, command="run"):
        monkeypatch.setattr(sl, "_read", unreadable)
    err = capsys.readouterr().err
    assert "warning: could not remove the station lock" in err
    assert (tmp_path / LOCK_NAME).exists()


def test_read_lock(tmp_path):
    assert read_lock(tmp_path) is None
    (tmp_path / LOCK_NAME).write_bytes(FOREIGN)
    assert read_lock(tmp_path) == FOREIGN
    assert token_of(FOREIGN) == "a" * 32
    assert token_of(b"lma-station-lock 2 " + b"a" * 32 + b"\n") is None
    assert token_of(b"lma-station-lock 1 " + b"A" * 32 + b"\n") is None


# --- fix round 1: acquire's tail and release are covered too --------------------


def test_close_error_after_write_removes_the_file(tmp_path, monkeypatch):
    real_close = os.close
    calls = []

    def close_then_fail(fd):
        calls.append(fd)
        real_close(fd)                       # the fd is gone, but close reports a deferred error
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(sl.os, "close", close_then_fail)
    with pytest.raises(OSError, match="Input/output error"):
        acquire(tmp_path / LOCK_NAME, command="run")
    monkeypatch.undo()
    assert len(calls) == 1                   # never closed twice
    assert not (tmp_path / LOCK_NAME).exists()
    assert sl._held is None


_WINDOW_SCRIPT = textwrap.dedent("""
    import os, signal, sys
    from pathlib import Path
    import emcee.station_lock as sl

    mode, delivered = sys.argv[1], Path(sys.argv[2])
    kill = lambda: os.kill(os.getpid(), signal.SIGTERM)
    if mode == "after-open":                 # between os.open returning and fd being stored
        real_open = os.open
        def opened(*a, **k):
            fd = real_open(*a, **k)
            kill()
            return fd
        sl.os.open = opened
    elif mode == "after-close":              # after the real close at the end of acquire
        real_close = os.close
        def closed(fd):
            real_close(fd)
            kill()
        sl.os.close = closed
    elif mode == "after-acquire":            # after acquire returns, before `held` is stored
        real_acquire = sl.acquire
        def acquired(*a, **k):
            h = real_acquire(*a, **k)
            kill()
            return h
        sl.acquire = acquired
    elif mode in ("before-acquire-block", "before-release-block"):
        real_block, calls = sl._block, []    # the signal lands just before the mask
        def block(on_main):
            calls.append(1)
            if len(calls) == (1 if mode == "before-acquire-block" else 2):
                kill()
            return real_block(on_main)
        sl._block = block
    elif mode == "second-in-release":        # a second signal while the first one releases
        real_release = sl.release
        def release(held):
            kill()
            return real_release(held)
        sl.release = release
    try:
        with sl.station_lock(delivered, command="window"):
            if mode == "in-release":         # between release's read and its unlink
                real_read = sl._read
                def read(path):
                    raw = real_read(path)
                    kill()
                    return raw
                sl._read = read
            if mode in ("second-in-release", "second-in-unwind"):
                try:
                    kill()                   # the first signal, inside the body
                finally:
                    if mode == "second-in-unwind":
                        kill()               # a second one while the first unwinds
            print("body", flush=True)
        print("after", flush=True)
    finally:
        blocked = set(signal.pthread_sigmask(signal.SIG_BLOCK, [])) & {signal.SIGTERM, signal.SIGHUP}
        print("blocked" if blocked else "unblocked", flush=True)
""")

_WINDOWS = ["after-open", "after-close", "after-acquire", "in-release", "before-acquire-block",
            "before-release-block", "second-in-release", "second-in-unwind"]


@pytest.mark.parametrize("mode", _WINDOWS)
def test_sigterm_in_any_window_leaves_no_lock_and_no_blocked_signals(tmp_path, mode):
    proc = subprocess.run([sys.executable, "-c", _WINDOW_SCRIPT, mode, str(tmp_path)],
                          capture_output=True, text=True, timeout=30)
    out = proc.stdout.split()
    assert proc.returncode == 128 + signal.SIGTERM, proc.stdout + proc.stderr
    assert not (tmp_path / LOCK_NAME).exists()
    assert "after" not in out
    assert out[-1] == "unblocked"
    # a signal during acquire fires once the lock is held, before the body runs;
    # one during or just before release fires only once the body has run
    assert ("body" in out) == (mode in ("in-release", "before-release-block"))
    assert "warning" not in proc.stderr       # released once, by its owner


def test_signal_mask_is_restored(tmp_path):
    before = signal.pthread_sigmask(signal.SIG_BLOCK, [])
    with station_lock(tmp_path, command="run"):
        assert signal.pthread_sigmask(signal.SIG_BLOCK, []) == before   # the body runs unblocked
    assert signal.pthread_sigmask(signal.SIG_BLOCK, []) == before
    (tmp_path / LOCK_NAME).write_bytes(FOREIGN)
    with pytest.raises(StationLocked):
        with station_lock(tmp_path, command="run"):
            pass
    assert signal.pthread_sigmask(signal.SIG_BLOCK, []) == before


def test_release_warns_missing_when_the_lock_vanishes_before_unlink(tmp_path, monkeypatch, capsys):
    real_read = sl._read

    def read_then_vanish(path):
        raw = real_read(path)
        Path(path).unlink()
        return raw

    with station_lock(tmp_path, command="run"):
        monkeypatch.setattr(sl, "_read", read_then_vanish)
    err = capsys.readouterr().err
    assert "was not ours at release (missing)" in err
    assert "could not remove" not in err


def test_read_lock_error_other_than_missing_is_a_refusal(tmp_path):
    (tmp_path / LOCK_NAME).mkdir()
    with pytest.raises(EmceeError) as e:
        read_lock(tmp_path)
    assert str(e.value).startswith(f"cannot read the station lock at {tmp_path / LOCK_NAME}: [Errno ")
