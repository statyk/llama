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
