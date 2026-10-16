"""moves.json: the operator's one-off profile moves (spec section 3).

`<config.root>/moves.json` maps a manifest's `source.performance_id` to
`{"profile": str | null, "package": str, "moved_at": str, ...}`. It is the
ONLY record of these decisions, so it is never read leniently (strict
surface 2): any read or parse failure, or a shape other than
`{str: {"profile": non-empty str | null, ...}}`, is an `EmceeError` naming
the file. A missing file is "no moves", unless a package records that it
was voiced under a move (`Moves.require_present`).

Writers (`record_move`, `clear_move`) hold an advisory `fcntl.flock` on
`moves.json.lock` beside the file around load-modify-write, edit the raw
dict in place so unknown keys survive, and write unique temp + fsync +
rename. The lock copies llama's `locks.file_lock` pattern: emcee never
imports llama.
"""

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None

from emcee.errors import EmceeError
from emcee.workspace import atomic_write_bytes

MOVES_FILE = "moves.json"
LOCK_FILE = "moves.json.lock"


def moves_path(root: Path) -> Path:
    return Path(root) / MOVES_FILE


def _malformed(path: Path, why: str) -> EmceeError:
    return EmceeError(
        f"{path} is unreadable or malformed ({why}); fix or restore it: emcee never "
        "reads it as no moves, since that would re-voice every moved show under its "
        "old profile")


def _validated(data: object, path: Path) -> dict[str, dict]:
    if not isinstance(data, dict):
        raise _malformed(path, "the top level is not a JSON object")
    for pid, entry in data.items():
        if not isinstance(entry, dict):
            raise _malformed(path, f"entry {pid!r} is not an object")
        if "profile" not in entry:
            raise _malformed(path, f'entry {pid!r} has no "profile"')
        profile = entry["profile"]
        if profile is not None and (not isinstance(profile, str) or not profile):
            raise _malformed(path, f'entry {pid!r}: "profile" must be a non-empty string or null')
    return data


def _read(path: Path) -> dict[str, dict] | None:
    """The validated raw dict, or None when the file does not exist."""
    try:
        text = path.read_text()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise _malformed(path, f"{type(exc).__name__}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _malformed(path, f"invalid JSON: {exc}") from exc
    return _validated(data, path)


def read_moves_data(root: Path) -> dict[str, dict]:
    """The validated raw dict (`{}` when the file is missing), for a writer
    to modify in place while holding `moves_lock`."""
    data = _read(moves_path(root))
    return {} if data is None else data


@dataclass(frozen=True)
class Moves:
    """moves.json as loaded once per command invocation."""
    path: Path
    exists: bool
    entries: dict[str, dict]

    def get(self, performance_id: object) -> dict | None:
        if not isinstance(performance_id, str):
            return None
        return self.entries.get(performance_id)

    def require_present(self, voiced_by_move: list[tuple[str, str | None, str | None]]) -> None:
        """Refuse a missing moves.json while any package records that it was
        voiced under a move (`dj_audio.profile_source == "move"`). Each tuple
        is (slug, performance_id, voiced profile)."""
        if self.exists or not voiced_by_move:
            return
        rows = [f"{slug}: performance_id {pid or '(none)'}, voiced as "
                f"{profile if profile is not None else '(none)'}"
                for slug, pid, profile in voiced_by_move]
        raise EmceeError(
            f"{self.path} is missing, but {len(voiced_by_move)} package(s) were voiced under a "
            'recorded move (dj_audio.profile_source = "move"); refusing to read that as no moves',
            details=[*rows,
                     f"either rebuild {self.path} by hand from the packages above: "
                     '{"<performance_id>": {"profile": "<profile>"}, ...}',
                     f"or write {{}} to {self.path} to accept the loss (those packages are "
                     "then re-voiced under their current profile)"])


def load_moves(root: Path) -> Moves:
    path = moves_path(root)
    data = _read(path)
    return Moves(path=path, exists=data is not None, entries={} if data is None else data)


@contextmanager
def moves_lock(root: Path) -> Iterator[None]:
    """Exclusive advisory lock on `<root>/moves.json.lock`. Released when the
    context exits or the process dies. A no-op where fcntl is missing."""
    path = Path(root) / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None:  # pragma: no cover - non-POSIX fallback
        yield
        return
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def write_moves(root: Path, data: dict[str, dict]) -> None:
    """Unique temp + fsync + rename: a crash leaves the old file or the new
    one, never a torn one."""
    payload = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()
    atomic_write_bytes(moves_path(root), payload, fsync=True)


def record_move(root: Path, performance_id: str, profile: str | None, package: str, *,
                moved_at: str) -> bool:
    """Record (or retarget) one move under the lock. False, with no write,
    when the identical profile is already recorded for this id."""
    with moves_lock(root):
        data = read_moves_data(root)
        entry = data.get(performance_id)
        if entry is not None and entry["profile"] == profile:
            return False
        entry = data.setdefault(performance_id, {})
        entry.update(profile=profile, package=package, moved_at=moved_at)
        write_moves(root, data)
        return True


def clear_move(root: Path, show: str, live_performance_id: Callable[[], str]) -> str:
    """Remove one move under the lock and return its performance_id.

    Recorded entries match first, by exact performance_id or exact recorded
    package name, so a stale move whose package is gone can be cleared.
    Only when none matches is `live_performance_id()` called to resolve
    `show` as a live package. More than one recorded match is refused,
    listing the ids, so the operator can clear one exactly."""
    with moves_lock(root):
        data = read_moves_data(root)
        hits = sorted(pid for pid, entry in data.items()
                      if pid == show or entry.get("package") == show)
        if len(hits) > 1:
            raise EmceeError(f"{show!r} matches {len(hits)} recorded moves; clear one by its "
                             "performance_id", hits)
        pid = hits[0] if hits else live_performance_id()
        if pid not in data:
            raise EmceeError(f"no move is recorded for {show!r} (performance_id {pid})")
        del data[pid]
        write_moves(root, data)
        return pid
