"""Raw capture of failed backend invocations.

A failed `claude -p` reaches the caller as at most 500 characters of
`_error_detail`'s pick of the message, which is enough to read but not
enough to CLASSIFY: the envelope's structured fields (api_error_status,
subtype, terminal_reason) are gone by then. Capturing the whole thing is
what lets an unrecognized failure be diagnosed after the fact instead of
being reproduced on purpose.

The destination is module-level rather than a provider constructor
argument because providers are built deep inside `resolve.provider_ladder`,
which has no workspace to thread a path through. The app sets it once at
startup; tests set it to a tmp_path and reset it.
"""
import os
import time
from pathlib import Path

_capture_dir: Path | None = None


def set_capture_dir(path: Path | None) -> None:
    """Where to write captures. None disables capture entirely."""
    global _capture_dir
    _capture_dir = Path(path) if path is not None else None


def capture_failure(cmd: list[str], proc) -> Path | None:
    """Write a failed invocation's full stdout/stderr/exit code. Never raises.

    Returns the path written, or None when capture is off or impossible -
    a capture problem must never mask the backend failure being captured.
    """
    if _capture_dir is None:
        return None
    try:
        _capture_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%S")
        path = _capture_dir / f"{stamp}-{os.getpid()}-{time.monotonic_ns() % 1_000_000}.txt"
        path.write_text(
            f"cmd: {' '.join(cmd)}\n"
            f"exit_code: {getattr(proc, 'returncode', None)}\n"
            f"--- stdout ---\n{getattr(proc, 'stdout', '') or ''}\n"
            f"--- stderr ---\n{getattr(proc, 'stderr', '') or ''}\n",
            encoding="utf-8", errors="replace",
        )
        return path
    except Exception:  # noqa: BLE001 - defensive: a capture problem must never mask the backend failure being captured
        return None
