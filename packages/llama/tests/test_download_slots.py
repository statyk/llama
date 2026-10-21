import errno
import fcntl
import os
import random
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from llama.download_slots import DownloadSlots


class Boom(Exception):
    pass


def test_never_more_than_n_holders(tmp_path: Path):
    n, total = 8, 12
    go = threading.Event()
    cond = threading.Condition()
    state = {"held": 0, "max": 0, "polls": 0, "done": 0}

    def sleep(_s: float) -> None:
        with cond:
            state["polls"] += 1
            cond.notify_all()
        assert go.wait(30)

    def worker() -> None:
        slots = DownloadSlots(tmp_path / "slots", n, sleep=sleep, rng=random.Random(0))
        with slots.acquire():
            with cond:
                state["held"] += 1
                state["max"] = max(state["max"], state["held"])
                cond.notify_all()
            assert go.wait(30)
            with cond:
                state["held"] -= 1
                state["done"] += 1

    threads = [threading.Thread(target=worker) for _ in range(total)]
    for t in threads:
        t.start()
    with cond:  # failure-guard timeout only; correctness is by counters
        assert cond.wait_for(lambda: state["held"] == n and state["polls"] >= total - n, 30)
        assert state["held"] == n
    go.set()
    for t in threads:
        t.join(30)
    assert state["max"] == n
    assert state["done"] == total


def test_a_dead_holder_frees_its_slot(tmp_path: Path):
    slots_dir = tmp_path / "slots"
    code = (
        "import fcntl, os, sys\n"
        "d = sys.argv[1]; os.makedirs(d, exist_ok=True)\n"
        "fds = [os.open(f'{d}/{i}.lock', os.O_CREAT | os.O_RDWR) for i in range(8)]\n"
        "[fcntl.flock(fd, fcntl.LOCK_EX) for fd in fds]\n"
        "print('held', flush=True)\n"
        "sys.stdin.read()\n"
    )
    child = subprocess.Popen([sys.executable, "-c", code, str(slots_dir)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "held"

        def boom(_s: float) -> None:
            raise Boom

        with pytest.raises(Boom):
            with DownloadSlots(slots_dir, 8, sleep=boom).acquire():
                pass
        child.kill()
        child.wait()
        with DownloadSlots(slots_dir, 8, sleep=boom, clock=lambda: 0.0).acquire() as waited:
            assert waited == 0.0
    finally:
        child.kill()
        child.wait()
        child.stdout.close()
        child.stdin.close()


def test_on_wait_called_once_per_acquire(tmp_path: Path):
    n = 2
    holder = DownloadSlots(tmp_path / "slots", n)
    ctxs = [holder.acquire() for _ in range(n)]
    for c in ctxs:
        c.__enter__()
    polls = []

    def sleep(_s: float) -> None:
        polls.append(1)
        if len(polls) == 3:
            for c in ctxs:
                c.__exit__(None, None, None)

    waits = []
    now = [0.0]

    def clock() -> float:
        return now[0]

    def tick(s: float) -> None:
        now[0] += s
        sleep(s)

    slots = DownloadSlots(tmp_path / "slots", n, sleep=tick, clock=clock, rng=random.Random(0))
    with slots.acquire(on_wait=lambda: waits.append(1)) as waited:
        assert waited > 0
    assert len(polls) == 3
    assert waits == [1]


def test_slot_released_on_exit(tmp_path: Path):
    slots = DownloadSlots(tmp_path / "slots", 1)
    with slots.acquire():
        pass
    fd = os.open(tmp_path / "slots" / "0.lock", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(fd)


def test_a_flock_error_other_than_held_propagates(tmp_path: Path, monkeypatch):
    def broken(fd, op):
        raise OSError(errno.ENOLCK, "no locks available")

    monkeypatch.setattr("llama.download_slots.fcntl.flock", broken)

    def never(_s: float) -> None:
        raise AssertionError("must not poll on a persistent flock error")

    with pytest.raises(OSError) as info:
        with DownloadSlots(tmp_path / "slots", 2, sleep=never).acquire():
            pass
    assert info.value.errno == errno.ENOLCK
