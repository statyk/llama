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


# One transient status line lives at the bottom of a TTY session: heartbeats and
# progress counts redraw it in place instead of stacking a line per update. Real
# log lines must erase it first or they'd be appended to the partial line.
_lock = threading.RLock()
_line_active = False
_current: dict | None = None  # state of the innermost running step() on a TTY


def _write_transient(text: str, color: bool) -> None:
    global _line_active
    with _lock:
        sys.stderr.write("\r\x1b[2K" + (_dim(text) if color else text))
        sys.stderr.flush()
        _line_active = True


def _clear_transient() -> None:
    global _line_active
    with _lock:
        if _line_active:
            sys.stderr.write("\r\x1b[2K")
            sys.stderr.flush()
            _line_active = False


class NarrationHandler(logging.StreamHandler):
    """StreamHandler that erases the transient status line before emitting."""

    def emit(self, record: logging.LogRecord) -> None:
        with _lock:
            _clear_transient()
            super().emit(record)


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
    handler = NarrationHandler(stream)
    handler.setFormatter(NarrationFormatter(tty=tty, color=tty and not os.environ.get("NO_COLOR")))
    llama_log.addHandler(handler)
    llama_log.setLevel(logging.INFO)


def _fmt_elapsed(seconds: float) -> str:
    secs = int(seconds)
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m{secs % 60:02d}s"


def _render_current() -> None:
    with _lock:
        if _current is None:
            return
        text = f"  … still working: {_current['label']}"
        if _current["detail"]:
            text += f" — {_current['detail']}"
        text += f" ({_fmt_elapsed(time.monotonic() - _current['start'])})"
        _write_transient(text, _current["color"])


@contextmanager
def step(label: str, *, interval_s: float = 1.0):
    """Log `label`; while the block runs on a TTY, keep a single status line
    (label, latest detail(), elapsed) redrawn in place on stderr and erase it
    when the block ends. Non-TTY (cron, piped logs) gets exactly the one log line.
    """
    global _current
    log.info("%s", label)
    stop = threading.Event()
    thread: threading.Thread | None = None
    if sys.stderr.isatty():
        with _lock:
            _current = {"label": label, "detail": None, "start": time.monotonic(),
                        "color": not os.environ.get("NO_COLOR")}

        def pulse() -> None:
            while not stop.wait(interval_s):
                _render_current()

        thread = threading.Thread(target=pulse, daemon=True, name=f"heartbeat:{label}")
        thread.start()
    try:
        yield
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=1.0)
            with _lock:
                _current = None
                _clear_transient()


def detail(text: str) -> None:
    """Progress note for the running step (e.g. "downloading 12/17: f.mp3").

    On a TTY it updates the step's in-place status line immediately; when piped
    (cron, logs) or outside a step it is an ordinary log line, so scripted
    output is unchanged.
    """
    with _lock:
        if _current is not None:
            _current["detail"] = text
            _render_current()
            return
    log.info("%s", text)
