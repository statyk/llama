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
Directories are not restored: an empty directory a failed unit created stays.
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


def _tracked_files(show_ws: ShowWorkspace) -> Iterator[str]:
    """Posix relpaths of every file outside the top-level `.lock`, `.txn/`,
    `.audio-aside/` and `package/audio/`."""
    root = show_ws.dir
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        if rel_dir == Path("."):
            dirnames[:] = [d for d in dirnames if d not in (TXN_DIR, ASIDE_DIR)]
        elif rel_dir == Path("package"):
            dirnames[:] = [d for d in dirnames if d != "audio"]
        for name in filenames:
            rel = (rel_dir / name).as_posix()
            if rel != ".lock":
                yield rel


def _audio_names(show_ws: ShowWorkspace) -> list[str]:
    audio = show_ws.package_dir / "audio"
    if not audio.is_dir():
        return []
    return sorted(p.name for p in audio.iterdir() if p.is_file())


def take_snapshot(show_ws: ShowWorkspace) -> None:
    txn = show_ws.dir / TXN_DIR
    for rel in _tracked_files(show_ws):
        atomic_write_bytes(txn / "files" / rel, (show_ws.dir / rel).read_bytes())
    atomic_write_bytes(txn / _INDEX,
                       json.dumps({"audio": _audio_names(show_ws)}).encode())


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
            discard_snapshot(show_ws)
            raise
        discard_aside(show_ws)
        discard_snapshot(show_ws)
