import logging
import os
import sys
import threading
import time
from contextlib import contextmanager

log = logging.getLogger("llama")


def _dim(text: str) -> str:
    return f"\033[2m{text}\033[0m"


class NarrationFormatter(logging.Formatter):
    """INFO lines are work narration: indented and dimmed on a TTY so actual
    results stand out flush-left at full intensity. Warnings stay flush-left
    and loud. Non-TTY output (cron, piped logs) is byte-identical to plain
    '%(message)s' formatting."""

    def __init__(self, *, tty: bool, color: bool):
        super().__init__("%(message)s")
        self.tty = tty
        self.color = color

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        if not self.tty:
            return msg
        if record.levelno >= logging.ERROR:
            return msg
        if record.levelno >= logging.WARNING:
            return f"warning: {msg}"
        indented = f"  {msg}"
        return _dim(indented) if self.color else indented


def configure_logging(stream=None) -> None:
    """Install the narration handler on the llama logger (idempotent).

    Propagation stays on so pytest's caplog and any root handlers still see
    records; in normal CLI runs the root logger has no handler of its own.
    """
    stream = stream if stream is not None else sys.stderr
    llama_log = logging.getLogger("llama")
    if any(isinstance(h.formatter, NarrationFormatter) for h in llama_log.handlers):
        return
    tty = stream.isatty()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(NarrationFormatter(tty=tty, color=tty and not os.environ.get("NO_COLOR")))
    llama_log.addHandler(handler)
    llama_log.setLevel(logging.INFO)


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
        color = not os.environ.get("NO_COLOR")

        def pulse() -> None:
            while not stop.wait(interval_s):
                elapsed = _fmt_elapsed(time.monotonic() - start)
                line = f"  … still working: {label} ({elapsed})"
                print(_dim(line) if color else line, file=sys.stderr)

        thread = threading.Thread(target=pulse, daemon=True, name=f"heartbeat:{label}")
        thread.start()
    try:
        yield
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=1.0)
