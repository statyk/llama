"""A per-workspace cap on concurrent audio downloads (spec 2026-10-21 §2).

N slot files `<dir>/0.lock .. <dir>/{n-1}.lock`; a download holds an exclusive
non-blocking `flock` on one for the length of a single attempt. flock dies with
the process, so a killed holder frees its slot without any reaping.
"""

import os
import random
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None

DOWNLOAD_SLOTS = 8
SLOT_POLL_MIN_S = 0.5
SLOT_POLL_MAX_S = 1.0


class DownloadSlots:
    def __init__(self, dir: Path, n: int = DOWNLOAD_SLOTS, *,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 rng: random.Random | None = None):
        self.dir = dir
        self.n = n
        self.sleep = sleep
        self.clock = clock
        self.rng = rng or random.Random()

    def _try_take(self) -> int | None:
        """The fd of the first free slot, locked, or None when all are held."""
        for i in range(self.n):
            fd = os.open(self.dir / f"{i}.lock", os.O_CREAT | os.O_RDWR, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:  # BlockingIOError: held (any other OSError: treat as held)
                os.close(fd)
                continue
            return fd
        return None

    @contextmanager
    def acquire(self, *, on_wait: Callable[[], None] | None = None) -> Iterator[float]:
        """Hold a slot; yields the seconds spent waiting for it. Never blocks on
        one slot: polls them all, and when every one is held calls `on_wait`
        (first miss only) and sleeps a jittered interval before polling again."""
        self.dir.mkdir(parents=True, exist_ok=True)
        if fcntl is None:  # pragma: no cover - non-POSIX fallback
            yield 0.0
            return
        start = self.clock()
        waited_once = False
        while (fd := self._try_take()) is None:
            if not waited_once:
                waited_once = True
                if on_wait is not None:
                    on_wait()
            self.sleep(self.rng.uniform(SLOT_POLL_MIN_S, SLOT_POLL_MAX_S))
        try:
            yield self.clock() - start
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
