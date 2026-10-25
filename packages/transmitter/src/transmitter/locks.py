"""Local advisory locks.

`plan_lock` serialises everything that appends to plan.jsonl or renders from
it: the service's plan and render steps and the `plan`/`render` commands. It
never waits (a second holder is refused with PlanLocked), mirroring
`publish.publish_lock`.
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager

from transmitter.errors import PlanLocked
from transmitter.workspace import Workspace


@contextmanager
def plan_lock(ws: Workspace) -> Iterator[None]:
    ws.root.mkdir(parents=True, exist_ok=True)
    fd = os.open(ws.plan_lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PlanLocked("another transmitter plan or render holds the lock "
                             "(is `transmitter run` running?); not waiting") from exc
        yield
    finally:
        os.close(fd)
