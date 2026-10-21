import os
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None


class Locked(Exception):
    """A non-blocking acquire found the lock held by another process."""


@contextmanager
def file_lock(path: Path, *, blocking: bool = True):
    """Advisory exclusive lock on the sidecar file `path`.

    Auto-released when the context exits and when the process dies (flock is
    tied to the open fd). Non-blocking mode raises Locked if held elsewhere.
    On non-POSIX platforms this is a no-op (single-process behavior).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None:  # pragma: no cover - non-POSIX fallback
        yield
        return
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError as exc:
            raise Locked(path) from exc
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)



class RunMissing(Exception):
    """The run dir does not exist, or its lock file was replaced while we
    waited for it (a `run rm` landed): either way there is no run to work."""


@contextmanager
def run_lock(run_dir: Path, *, blocking: bool):
    """Exclusive lock on `run_dir/.lock`, held for the life of the context.

    Never creates `run_dir`: the lock file is opened with O_CREAT but the dir
    is not made, so a lock attempt that loses a race with `run rm` cannot
    resurrect the run (RunMissing). Non-blocking mode raises Locked when held.

    After acquiring, the locked fd must still be THE file at `run_dir/.lock`
    (same inode and device). A `run rm` (and a re-create) landing while we
    waited would otherwise leave us holding a lock on a deleted file while
    our artifacts recreate the dir unlocked, and a second worker could start
    on it. Spec §4; the remaining `.lock`-only-husk window is documented there.
    """
    path = run_dir / ".lock"
    if fcntl is None:  # pragma: no cover - non-POSIX fallback
        if not run_dir.is_dir():
            raise RunMissing(run_dir)
        yield
        return
    try:
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise RunMissing(run_dir) from exc
    try:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError as exc:
            raise Locked(path) from exc
        try:
            on_disk = os.stat(path)
        except FileNotFoundError as exc:
            raise RunMissing(run_dir) from exc
        held = os.fstat(fd)
        if (held.st_ino, held.st_dev) != (on_disk.st_ino, on_disk.st_dev):
            raise RunMissing(run_dir)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def run_is_live(run_dir: Path) -> bool:
    """True when another holder has the run's lock: a non-blocking acquire and
    an immediate release. Opens only an EXISTING lock file (no O_CREAT), so a
    missing file or dir is "not live" and a reader never creates either. Only
    a held lock is "live"; any other error propagates rather than reading as
    "not live", which would let a second worker start."""
    if fcntl is None:  # pragma: no cover - non-POSIX fallback
        return False
    try:
        fd = os.open(run_dir / ".lock", os.O_RDONLY)
    except (FileNotFoundError, NotADirectoryError):
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)
