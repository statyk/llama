"""The station lock: one writer at a time over the station's delivered folder.

The on-disk contract is shared with llama's twin (`llama.station_lock`),
which cannot import this module, so the file name and format below are the
contract, not an implementation detail:

- the file is `<delivered folder>/.lma-station.lock`;
- it is created with `O_CREAT|O_EXCL|O_WRONLY`, mode 0644, written, then
  fsynced; its UTF-8 contents are `lma-station-lock 1 <32 lowercase hex
  token>` and then `tool:`, `command:`, `host:`, `pid:` and `started:`
  lines, with a trailing newline;
- any existing file is held, empty or unparseable included; a tool releases
  only on its own token; nothing breaks a lock automatically or expires it.
  The holder text is for the operator: no tool parses it.

A process holds at most one station lock (`StationLockReentry` otherwise:
a bug). Only command entry points acquire it, and never across an operator
prompt. `emcee lock show|clear` is the operator's way to inspect and remove
a lock left by a dead writer.
"""

import os
import re
import secrets
import signal
import socket
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from emcee.errors import EmceeError

LOCK_NAME = ".lma-station.lock"
MAGIC = "lma-station-lock 1"

_FIRST_LINE = re.compile(re.escape(MAGIC) + r" ([0-9a-f]{32})")
_CLEAR_HINT = ("check it with: emcee lock show; "
               "remove it with: emcee lock clear (only if that writer is gone)")


class StationLocked(EmceeError):
    """Another writer holds the station lock (or a dead one left it)."""

    def __init__(self, path: Path, holder: str):
        super().__init__(f"the station is locked by another writer ({path})",
                         holder.splitlines() + [_CLEAR_HINT])
        self.path = path
        self.holder = holder


class StationLockReentry(RuntimeError):
    """A second acquire in a process that already holds the lock: a bug."""


@dataclass(frozen=True)
class Held:
    path: Path
    token: str
    started: str = "?"


_held: Held | None = None


def _read(path: Path) -> bytes:
    return Path(path).read_bytes()


def read_lock(delivered: Path) -> bytes | None:
    """The lock file's raw bytes, or None when there is no lock."""
    try:
        return _read(Path(delivered) / LOCK_NAME)
    except FileNotFoundError:
        return None


def holder_text(raw: bytes) -> str:
    """The lock's contents for display: decoded leniently, control characters
    escaped so a garbage file cannot drive the terminal."""
    if not raw:
        return "(empty lock file)"
    text = raw.decode("utf-8", errors="backslashreplace").rstrip("\n")
    return "".join(c if c.isprintable() or c in "\n\t" else repr(c)[1:-1] for c in text)


def token_of(raw: bytes) -> str | None:
    """The token on a well-formed first line, else None."""
    try:
        first = raw.decode("utf-8").split("\n", 1)[0]
    except UnicodeDecodeError:
        return None
    m = _FIRST_LINE.fullmatch(first)
    return m.group(1) if m else None


def _one_line(text: str) -> str:
    return " ".join(text.split())


def acquire(path: Path, *, command: str) -> Held:
    """Create the lock at `path` or refuse. Never retries, never breaks."""
    global _held
    if _held is not None:
        raise StationLockReentry(
            f"this process already holds the station lock at {_held.path}; "
            f"a second acquire ({path}) is a bug")
    token = secrets.token_hex(16)
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    body = (f"{MAGIC} {token}\n"
            f"tool: emcee\n"
            f"command: {_one_line(command)}\n"
            f"host: {socket.gethostname()}\n"
            f"pid: {os.getpid()}\n"
            f"started: {started}\n").encode("utf-8")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        try:
            holder = holder_text(_read(path))
        except FileNotFoundError:
            holder = "(lock vanished while reading)"
        except OSError as exc:
            holder = f"(cannot read the lock: {exc})"
        raise StationLocked(path, holder) from None
    except OSError as exc:
        raise EmceeError(f"cannot create the station lock at {path}: "
                         f"[Errno {exc.errno}] {exc.strerror}") from None
    try:
        view = memoryview(body)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    os.close(fd)
    _held = Held(path, token, started)
    return _held


def release(held: Held) -> None:
    """Remove the lock if it still carries our token. Never raises."""
    global _held
    if _held == held:
        _held = None
    path = held.path
    try:
        try:
            raw = _read(path)
        except FileNotFoundError:
            raw = None
        if raw is not None and token_of(raw) == held.token:
            os.unlink(path)
            return
    except OSError as exc:
        print(f"warning: could not remove the station lock at {path} ({exc}); "
              "clear it with: emcee lock clear", file=sys.stderr)
        return
    holder = "missing" if raw is None else "; ".join(holder_text(raw).splitlines())
    print(f"warning: the station lock at {path} was not ours at release ({holder}); "
          f"writes since {held.started} ran unguarded", file=sys.stderr)


def _raise_exit(signum, frame):
    raise SystemExit(128 + signum)


@contextmanager
def station_lock(delivered: Path, *, command: str) -> Iterator[Held]:
    """Hold the station lock over `delivered` for the `with` body.

    On the main thread SIGTERM and SIGHUP raise `SystemExit(128 + signum)`
    so the `finally` releases; the previous handlers are restored on exit.
    """
    previous: dict[int, object] = {}
    held: Held | None = None
    try:
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGTERM, signal.SIGHUP):
                previous[signum] = signal.signal(signum, _raise_exit)
        held = acquire(Path(delivered).absolute() / LOCK_NAME, command=command)
        yield held
    finally:
        try:
            if held is not None:
                release(held)
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, signal.SIG_DFL if handler is None else handler)
