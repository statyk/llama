"""The station lock: one writer at a time over the station's delivered folder.

The on-disk contract is shared with emcee's twin (`emcee.station_lock`),
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
a bug). Only command entry points (and `bulk_apply`'s per-show step) acquire
it, all through `for_package`, and never across an operator prompt.
`emcee lock show|clear` is the operator's way to inspect and remove a lock
left by a dead writer.

SIGTERM and SIGHUP (on the main thread, while `station_lock` is active)
release the lock and END THE PROCESS at once with `os._exit(128 + signum)`:
nothing is raised into the caller, so the caller's `except`/`finally`
cleanup does not run. For the writes that are a temp file plus an atomic
rename (emcee's manifest and clip writes, `emcee retitle`, llama's
clear-mark and bulk_apply's mark and unmark) an exit mid-sequence leaves at
most a stray temp file, as SIGKILL would, but without the stuck lock. Two
station writes are NOT atomic renames, and there an exit behaves like
SIGKILL minus the stuck lock: llama deliver's overlay copy
(`shutil.copytree(..., dirs_exist_ok=True)` straight into the live package,
which can leave a truncated manifest or audio file) and its replace path's
two renames (destination moved aside, then the staged copy renamed in; an
exit between them leaves no package at the destination, only the
`.<slug>.old-*` and `.<slug>.deliver-*` siblings). Keep every other station
write a temp plus rename. SIGINT is untouched: KeyboardInterrupt unwinds
normally and the `finally` releases.
"""

import os
import re
import secrets
import signal
import socket
import sys
import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from llama.errors import LlamaError

LOCK_NAME = ".lma-station.lock"
MAGIC = "lma-station-lock 1"

_FIRST_LINE = re.compile(re.escape(MAGIC) + r" ([0-9a-f]{32})")
_CLEAR_HINT = ("check it with: emcee lock show; "
               "remove it with: emcee lock clear (only if that writer is gone)")


class StationLocked(LlamaError):
    """Another writer holds the station lock (or a dead one left it).

    The whole refusal is in `str(self)` (header, holder lines, hint), not in
    `details`, so a batch that reports a show's error by its message alone
    still names the holder and the emcee commands."""

    def __init__(self, path: Path, holder: str):
        super().__init__("\n".join([f"the station is locked by another writer ({path}):",
                                    *(f"  {line}" for line in holder.splitlines()),
                                    f"  {_CLEAR_HINT}"]))
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


def _reason(exc: OSError) -> str:
    return f"[Errno {exc.errno}] {exc.strerror}"


def read_lock(delivered: Path) -> bytes | None:
    """The lock file's raw bytes, or None when there is no lock. Any other
    read error (EACCES, EIO, a directory at the path) is a `LlamaError`."""
    path = Path(delivered) / LOCK_NAME
    try:
        return _read(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise LlamaError(f"cannot read the station lock at {path}: {_reason(exc)}") from None


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
            f"tool: llama\n"
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
        raise LlamaError(f"cannot create the station lock at {path}: {_reason(exc)}") from None
    fd_open = True
    try:
        view = memoryview(body)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
        fd_open = False            # close releases the fd even when it reports an error
        os.close(fd)               # (SMB can report a deferred write error here)
    except BaseException:
        if fd_open:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    _held = Held(path, token, started)
    return _held


def release(held: Held) -> None:
    """Remove the lock if it still carries our token. Never raises."""
    global _held
    if _held == held:
        _held = None
    path = held.path
    try:
        raw = _read(path)
        if token_of(raw) == held.token:
            os.unlink(path)
            return
    except FileNotFoundError:          # gone before the read, or before the unlink
        raw = None
    except OSError as exc:
        print(f"warning: could not remove the station lock at {path} ({exc}); "
              "clear it with: emcee lock clear", file=sys.stderr)
        return
    holder = "missing" if raw is None else "; ".join(holder_text(raw).splitlines())
    print(f"warning: the station lock at {path} was not ours at release ({holder}); "
          f"writes since {held.started} ran unguarded", file=sys.stderr)


_SIGNALS = (signal.SIGTERM, signal.SIGHUP)

# The mask alone does not keep the handler out of acquire and release:
# `pthread_sigmask` blocks the main thread only, so with any other thread
# alive (llama's status heartbeat, say) the kernel hands a process-directed
# SIGTERM to that thread, and CPython then runs the Python handler on the
# main thread at its next bytecode boundary, mask or no mask. So while
# acquire or release runs, `_critical` is set and the handler only records
# the signal in `_deferred`; `_unblock` acts on it once the lock is fully
# held or fully released. `_exiting` makes a second signal during the
# handler's own release a no-op: the first handler is already ending the
# process.
_critical = False
_deferred: int | None = None
_exiting = False


def _block(unblock: tuple | None) -> None:
    """Enter acquire/release: defer the handler, and block SIGTERM and
    SIGHUP (main thread only: `unblock` is None off it)."""
    global _critical
    if unblock is not None:
        _critical = True
        signal.pthread_sigmask(signal.SIG_BLOCK, _SIGNALS)


def _unblock(unblock: tuple | None) -> None:
    """Leave acquire/release: unblock just the signals that were not blocked
    when `station_lock` began, leaving every other mask change alone, then
    act on a signal the handler deferred."""
    global _critical, _deferred
    if unblock is None:
        return
    # Limit (async KeyboardInterrupt): SIGINT is neither masked nor deferred, so
    # a Ctrl-C between the unmask and `_critical = False` raises out of here and
    # leaves `_critical` set (and maybe `_deferred`). That can never leave a stuck
    # lock: acquire/release have finished and the caller's `finally` still
    # releases. What it can leave is stale state: the `with` then restores the
    # previous handlers, and a stale `_deferred` would make a LATER
    # `station_lock` in the same process exit at its first `_unblock`
    # (llama's lock-taking commands exit on Ctrl-C, so none takes a second lock
    # after one).
    if unblock:
        signal.pthread_sigmask(signal.SIG_UNBLOCK, unblock)   # a pending one defers too
    _critical = False
    signum, _deferred = _deferred, None
    if signum is not None:
        _exit_on_signal(signum, None)


def _exit_on_signal(signum, frame):
    """SIGTERM/SIGHUP handler: release the lock, then end the process. It
    never raises, and returns only to defer (inside acquire or release) or
    when a first signal is already ending the process, so no caller code
    runs after the signal."""
    global _deferred, _exiting
    if _exiting:
        return
    if _critical:
        if _deferred is None:
            _deferred = signum
        return
    _exiting = True
    try:
        held = _held
        if held is not None:
            signal.pthread_sigmask(signal.SIG_BLOCK, _SIGNALS)   # no second handler mid-release
            release(held)
    finally:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except Exception:
                pass
        os._exit(128 + signum)


@contextmanager
def station_lock(delivered: Path, *, command: str) -> Iterator[Held]:
    """Hold the station lock over `delivered` for the `with` body.

    On the main thread SIGTERM and SIGHUP release the lock and exit the
    process (`_exit_on_signal`; see the module docstring); the previous
    handlers are restored when the `with` ends. While `acquire` and
    `release` run, both signals are blocked and the handler defers, so it
    never sees `_held` in flux, even when another thread takes the signal:
    a signal during acquire acts once the lock is fully held, one during
    release once release has finished. Off the main thread no
    handlers are installed and nothing is blocked: a SIGTERM there kills the
    process with default disposition and leaves the lock for `emcee lock clear`.
    """
    unblock: tuple | None = None       # the signals to unblock again; None off the main thread
    if threading.current_thread() is threading.main_thread():
        at_entry = signal.pthread_sigmask(signal.SIG_BLOCK, [])
        unblock = tuple(s for s in _SIGNALS if s not in at_entry)
    previous: dict[int, object] = {}
    held: Held | None = None
    try:
        if unblock is not None:
            for signum in _SIGNALS:
                previous[signum] = signal.signal(signum, _exit_on_signal)
        try:
            _block(unblock)
            held = acquire(Path(delivered).absolute() / LOCK_NAME, command=command)
        finally:
            _unblock(unblock)      # a pending signal fires here, with the lock fully held
        yield held
    finally:
        try:
            if held is not None:
                try:
                    _block(unblock)
                    release(held)
                finally:
                    _unblock(unblock)
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, signal.SIG_DFL if handler is None else handler)


def for_package(out: Path, *, command: str) -> AbstractContextManager[Held]:
    """Hold the station lock for writing the package directory `out`: the
    lock lives in `out`'s delivered folder, its absolute parent (so a relative
    `Path("slug")` locks the current directory, by absolute path). The one
    helper every llama caller uses."""
    return station_lock(Path(out).absolute().parent, command=command)
