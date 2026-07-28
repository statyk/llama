import multiprocessing as mp
import os
import time
from pathlib import Path

import pytest

from llama.locks import Locked, file_lock

CTX = mp.get_context("fork")


def test_acquire_release_creates_sidecar(tmp_path: Path):
    lock = tmp_path / "x.lock"
    with file_lock(lock):
        assert lock.exists()
    # released; re-acquirable in-process
    with file_lock(lock, blocking=False):
        pass


def _hold_until(lock_path, started, release):
    with file_lock(Path(lock_path)):
        started.set()
        release.wait(5)


def test_nonblocking_raises_when_held(tmp_path: Path):
    lock = tmp_path / "x.lock"
    started, release = CTX.Event(), CTX.Event()
    p = CTX.Process(target=_hold_until, args=(str(lock), started, release))
    p.start()
    try:
        assert started.wait(5)
        with pytest.raises(Locked):
            with file_lock(lock, blocking=False):
                pass
    finally:
        release.set()
        p.join(5)


def _acquire_then_die(lock_path, started):
    fd_ctx = file_lock(Path(lock_path))
    fd_ctx.__enter__()
    started.set()
    os._exit(0)  # die without releasing


def test_lock_auto_released_on_process_death(tmp_path: Path):
    lock = tmp_path / "x.lock"
    started = CTX.Event()
    p = CTX.Process(target=_acquire_then_die, args=(str(lock), started))
    p.start()
    assert started.wait(5)
    p.join(5)
    # OS released the dead process's flock; we can take it non-blocking.
    with file_lock(lock, blocking=False):
        pass
