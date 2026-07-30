"""Atomic file writes, ported from llama's `workspace.py`.

Only `atomic_write_text`/`atomic_write_bytes` are ported here — the rest of
llama's `workspace.py` (`ShowWorkspace`, `RunWorkspace`, etc.) is
llama-library-side and out of scope for emcee. `emcee.presenters` uses
`atomic_write_text` today; Task 6's atomic manifest rewrite is meant to
import it from here too, rather than writing a second atomic writer.
"""

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Atomic write via a unique temp file + rename. Concurrent writers to the
    same target never interleave (each gets its own temp); last rename wins."""
    atomic_write_bytes(path, text.encode())


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
