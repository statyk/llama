"""One edit of a show as a unit: snapshot, run, restore on any failure.

`show_unit` takes the show lock, verifies the show is still what the caller
saw, snapshots every file outside `package/audio/` into `<show>/.txn/`, and on
any exception (BaseException, so KeyboardInterrupt too) restores those files
byte-identical, deletes the snapshot and re-raises.

Documented limitations (spec C2):
  1. Audio retagged in place by a failed package stage stays retagged: audio
     is never copied, and only audio files the unit ADDED are removed.
  2. A racing `rm` can leave a `.lock`-only husk of the show directory.
  3. SIGKILL (or a restore that itself fails) leaves a stale `.txn/`. The next
     unit deletes it WITHOUT restoring; `llama redo <show> --from gather`
     repairs the show. A leftover `.txn/` that cannot be removed refuses the
     unit before anything is written ("cannot remove leftover snapshot").
  4. The unit protects the workspace it is given, while `process_show` writes
     to `show_ws(prov.performance_id)`; a show directory whose name is not
     `slugify(performance_id)` (renamed by hand) is outside the guarantee, as
     it is today.
  5. A re-packaging `build_package(reuse=...)` moves the old library audio
     into `<show>/.audio-aside/` (spec 5.4): a failed unit puts it back under
     its old names after the restore, a successful one deletes it. SIGKILL
     (or a failed restore) leaves the aside behind, and the next unit deletes
     it with the stale `.txn/`, never putting it back: that audio is lost and
     `llama redo <show> --from package` re-downloads it. A put-back that
     itself fails part-way leaves `.txn/` and a partial aside for the next
     unit's entry to delete (the files it had not moved back are lost the same
     way), and its exception masks the original (which is its `__context__`).
     A leftover aside that cannot be removed refuses the unit like a leftover
     `.txn/`. The aside is single-use: a second set-aside in one unit refuses.
Directories: after a failed unit's restore and put-back, every directory the
unit created (absent from the snapshot's directory set) that the restore left
empty is removed, deepest first, with `rmdir` only. A directory that existed
before the unit is never removed, empty or not; a created directory still
holding content the snapshot does not track (e.g. a subdirectory of
`package/audio/`) stays, with its parents. Best-effort: an `rmdir` error skips
that directory and never masks the original exception. A successful unit
keeps the directories it created.
Listing: the snapshot refuses (a `LlamaError`, before the body runs, leaving no
`.txn/`) if any part of the show dir cannot be listed or a file in it cannot be
read; a restore that cannot list a subtree skips it, which only means fewer
removals.
"""
from __future__ import annotations

import json
import os
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from llama.audio_reuse import ASIDE_DIR, discard_aside, put_back
from llama.errors import LlamaError
from llama.locks import file_lock
from llama.workspace import ShowWorkspace, atomic_write_bytes

TXN_DIR = ".txn"
_INDEX = "index.json"


@dataclass(frozen=True)
class ShowView:
    provenance: bool
    overrides: bytes | None
    show: bytes | None


class ShowChanged(LlamaError):
    """The show changed (or was removed) between what the caller saw and the lock."""


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def capture_view(show_ws: ShowWorkspace) -> ShowView:
    return ShowView(provenance=show_ws.provenance.exists(),
                    overrides=_read(show_ws.overrides),
                    show=_read(show_ws.show))


def _refuse(show_ws: ShowWorkspace, path, err: OSError) -> LlamaError:
    """The snapshot's refusal when reading the show dir fails (raise it `from err`)."""
    return LlamaError(f"{show_ws.dir.name}: cannot snapshot {path}: {err}")


def _walk(show_ws: ShowWorkspace, strict: bool):
    """`os.walk` of the show dir. Strict (the snapshot): a directory that cannot be
    listed raises `LlamaError`; otherwise (a restore) it is skipped, as by default."""
    def refuse(err: OSError) -> None:
        raise _refuse(show_ws, err.filename, err) from err
    return os.walk(show_ws.dir, onerror=refuse if strict else None)


def _tracked_files(show_ws: ShowWorkspace, *, strict: bool = False) -> Iterator[str]:
    """Posix relpaths of every file outside the top-level `.lock`, `.txn/`,
    `.audio-aside/` and `package/audio/`. `strict`: see `_walk`."""
    root = show_ws.dir
    for dirpath, dirnames, filenames in _walk(show_ws, strict):
        rel_dir = Path(dirpath).relative_to(root)
        if rel_dir == Path("."):
            dirnames[:] = [d for d in dirnames if d not in (TXN_DIR, ASIDE_DIR)]
        elif rel_dir == Path("package"):
            dirnames[:] = [d for d in dirnames if d != "audio"]
        for name in filenames:
            rel = (rel_dir / name).as_posix()
            if rel != ".lock":
                yield rel


def _dirs(show_ws: ShowWorkspace, *, strict: bool = False) -> list[str]:
    """Posix relpaths of every directory under the show dir, except the top-level
    `.txn/` and `.audio-aside/` (and everything under them). The show dir itself
    is not listed. `strict`: see `_walk`."""
    root = show_ws.dir
    out = []
    for dirpath, dirnames, _ in _walk(show_ws, strict):
        rel_dir = Path(dirpath).relative_to(root)
        if rel_dir == Path("."):
            dirnames[:] = [d for d in dirnames if d not in (TXN_DIR, ASIDE_DIR)]
        out.extend((rel_dir / d).as_posix() for d in dirnames)
    return sorted(out)


def _audio_names(show_ws: ShowWorkspace) -> list[str]:
    audio = show_ws.package_dir / "audio"
    if not audio.is_dir():
        return []
    return sorted(p.name for p in audio.iterdir() if p.is_file())


def take_snapshot(show_ws: ShowWorkspace) -> None:
    """Every read of the show dir that fails refuses (`_refuse`); a failing write into
    `.txn/` is not about the show and propagates as itself."""
    txn = show_ws.dir / TXN_DIR
    dirs = _dirs(show_ws, strict=True)                 # before .txn/ itself exists
    for rel in _tracked_files(show_ws, strict=True):
        src = show_ws.dir / rel
        try:
            data = src.read_bytes()
        except OSError as err:
            raise _refuse(show_ws, src, err) from err
        atomic_write_bytes(txn / "files" / rel, data)
    try:
        audio = _audio_names(show_ws)
    except OSError as err:
        raise _refuse(show_ws, show_ws.package_dir / "audio", err) from err
    atomic_write_bytes(txn / _INDEX, json.dumps({"audio": audio, "dirs": dirs}).encode())


def restore_snapshot(show_ws: ShowWorkspace) -> None:
    txn = show_ws.dir / TXN_DIR
    files = txn / "files"
    saved = {p.relative_to(files).as_posix() for p in files.rglob("*") if p.is_file()} \
        if files.is_dir() else set()
    keep_audio = set(json.loads((txn / _INDEX).read_text())["audio"])
    for rel in list(_tracked_files(show_ws)):          # (a) drop files the unit created
        if rel not in saved:
            (show_ws.dir / rel).unlink(missing_ok=True)
    for rel in sorted(saved):                          # (b) put the originals back
        atomic_write_bytes(show_ws.dir / rel, (files / rel).read_bytes())
    for name in _audio_names(show_ws):                 # (c) drop audio the unit added
        if name not in keep_audio:
            (show_ws.package_dir / "audio" / name).unlink(missing_ok=True)


def remove_created_dirs(show_ws: ShowWorkspace) -> None:
    """Remove (rmdir only, deepest first) every directory not in the snapshot's
    `dirs` that is empty now. Best-effort: an OSError skips that directory.
    An index without `dirs` removes nothing (defensive only: a leftover `.txn/`
    is deleted at unit entry, never restored, so every index this reads was
    written by this code)."""
    try:
        before = json.loads((show_ws.dir / TXN_DIR / _INDEX).read_text()).get("dirs")
    except (OSError, ValueError):
        return
    if before is None:
        return
    keep = set(before)
    created = [rel for rel in _dirs(show_ws) if rel not in keep]
    for rel in sorted(created, key=lambda r: r.count("/"), reverse=True):
        try:
            os.rmdir(show_ws.dir / rel)
        except OSError:
            pass                                       # non-empty, permission, gone


def discard_snapshot(show_ws: ShowWorkspace) -> None:
    shutil.rmtree(show_ws.dir / TXN_DIR, ignore_errors=True)


def _discard_leftover(show_ws: ShowWorkspace) -> None:
    """Entry discard: a leftover that cannot be removed would be mixed into the
    new snapshot (or, for the audio aside, put back on failure), so refuse
    before anything is written."""
    discard_snapshot(show_ws)
    txn = show_ws.dir / TXN_DIR
    if txn.exists():
        raise LlamaError(f"{show_ws.dir.name}: cannot remove leftover snapshot {txn}")
    discard_aside(show_ws)
    aside = show_ws.dir / ASIDE_DIR
    if aside.exists():
        raise LlamaError(f"{show_ws.dir.name}: cannot remove leftover audio aside {aside}")


@contextmanager
def show_unit(show_ws: ShowWorkspace, expect: ShowView | None) -> Iterator[None]:
    with file_lock(show_ws.lock):
        now = capture_view(show_ws)
        if expect is None:
            expect = now
        if now != expect:
            slug = show_ws.dir.name
            if expect.provenance and not now.provenance:
                raise ShowChanged(f"{slug}: the show was removed; nothing changed")
            raise ShowChanged(f"{slug}: changed by another command; run it again")
        _discard_leftover(show_ws)         # a leftover (.txn/, .audio-aside/) is deleted, never restored
        try:
            take_snapshot(show_ws)
        except BaseException:
            discard_snapshot(show_ws)
            raise
        try:
            yield
        except BaseException:
            restore_snapshot(show_ws)      # if this raises, .txn/ stays; original is __context__
            put_back(show_ws)              # the old audio, under its old names
            remove_created_dirs(show_ws)   # after put_back (it may mkdir package/audio/)
            discard_snapshot(show_ws)
            raise
        discard_aside(show_ws)
        discard_snapshot(show_ws)
