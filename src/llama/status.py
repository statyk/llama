import logging
import sys
import threading
import time
from contextlib import contextmanager

log = logging.getLogger("llama")


def _fmt_elapsed(seconds: float) -> str:
    secs = int(seconds)
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m{secs % 60:02d}s"


@contextmanager
def step(label: str, *, interval_s: float = 15.0):
    """Log `label`; while the block runs on a TTY, pulse a heartbeat to stderr.

    Non-TTY (cron, piped logs) gets exactly the one log line.
    """
    log.info("%s", label)
    stop = threading.Event()
    thread: threading.Thread | None = None
    if sys.stderr.isatty():
        start = time.monotonic()

        def pulse() -> None:
            while not stop.wait(interval_s):
                elapsed = _fmt_elapsed(time.monotonic() - start)
                print(f"  … still working: {label} ({elapsed})", file=sys.stderr)

        thread = threading.Thread(target=pulse, daemon=True, name=f"heartbeat:{label}")
        thread.start()
    try:
        yield
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=1.0)
