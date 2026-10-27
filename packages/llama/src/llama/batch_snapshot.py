"""Per-batch library snapshots and the guarded restore (bulk-apply spec "Undo";
strict surface 4: rewriting library show files in bulk).

Each library write batch (the overrule backfill, each wave) calls `take` over its
own shows before its first write: every file outside `package/audio/`,
`.audio-aside/`, `.txn/` and the top-level `.lock` is copied to
`<snap>/shows/<slug>/<rel>`, sha256-verified against its source and flushed
(`F_FULLFSYNC`), with each show's station `manifest.json` sha256 recorded (None:
no station copy); `manifest.json` is written last, so a directory without one is
no snapshot. Each show the batch writes then gets `record_after` from inside the
batch's own show lock, appending the show's post-write state to
`<snap>/after.jsonl`.

`restore` rewinds, per show under its show lock, only a show whose library files
and station manifest are still exactly what the batch left (its after-record);
any later change is refused, since putting the snapshot back over it would lose
it, and a station copy re-delivered or re-voiced since can only be rolled
forward. A show the batch recorded no write for is left alone. `restore` never
writes the station and rewinds no station mark (a show left marked is safe).

The copy/flush/verify pattern is ported from `scripts/rekey_overrides.py`
(`_write_copy`, `_sync_dir`, `verify_snapshot`); the migration's gates are not.

Locks: `take`, `restore` and `seal` take each show's lock themselves;
`record_after` takes none (its callers hold it: reapply's `after_commit` hook,
the backfill's per-show unit). Lock order run > show > ledger is unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Callable

from llama.audio_reuse import ASIDE_DIR
from llama.catalog import _sync_fd
from llama.errors import LlamaError
from llama.locks import file_lock
from llama.show_unit import TXN_DIR
from llama.station_mark import MANIFEST as STATION_MANIFEST
from llama.workspace import ShowWorkspace

MANIFEST = "manifest.json"
AFTER = "after.jsonl"
_MANIFEST_TMP = ".manifest.json.tmp"
_PACKAGE_MANIFEST = "package/manifest.json"
_AUDIO = "package/audio"

NO_WRITE = "changed, and this batch recorded no write for it"
LIBRARY_CHANGED = "library files changed after the batch: {rel}"
STATION_CHANGED = ("station manifest changed after the batch (re-delivered or re-voiced): "
                   "roll forward instead")


class _Unfit(LlamaError):
    """A show directory (or station copy) that cannot be snapshotted or compared."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_copy(dst: Path, data: bytes) -> None:
    """Create `dst` (never over an existing file) holding `data`, flushed to stable
    storage (`F_FULLFSYNC`) before it is closed."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        _sync_fd(fd)
    finally:
        os.close(fd)


def _sync_dir(d: Path) -> None:
    fd = os.open(d, os.O_RDONLY)
    try:
        _sync_fd(fd)
    finally:
        os.close(fd)


def _durable_replace(path: Path, data: bytes) -> None:
    """Atomic, flushed replacement of `path` (unique temp in its directory, then
    rename); the caller syncs the directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
            _sync_fd(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _check_slug(slug: str) -> None:
    if (not isinstance(slug, str) or not slug or "/" in slug or "\\" in slug
            or slug in (".", "..")):
        raise LlamaError(f"{slug!r}: not a show name")


def _check_station_root(station_root: Path | None) -> None:
    if station_root is not None and not station_root.is_dir():
        raise LlamaError(f"station root {station_root} is not a directory "
                         f"(is the station mounted?)")


def _show_dir(root: Path, slug: str) -> Path | None:
    d = root / "shows" / slug
    return None if d.is_symlink() or not d.is_dir() else d


def _metadata_files(d: Path) -> list[str]:
    """Posix relpaths of every file under show dir `d` outside `package/audio/`,
    `.audio-aside/` and `.txn/`, the top-level `.lock` aside, sorted. A symlink or any
    other non-regular entry is `_Unfit`: it cannot be copied faithfully."""
    out: list[str] = []

    def walk(p: Path, rel: str) -> None:
        with os.scandir(p) as it:
            entries = sorted(it, key=lambda e: e.name)
        for e in entries:
            r = f"{rel}/{e.name}" if rel else e.name
            real_dir = e.is_dir(follow_symlinks=False)
            if r == ".lock" or (real_dir and r in (ASIDE_DIR, TXN_DIR, _AUDIO)):
                continue
            if real_dir:
                walk(Path(e.path), r)
            elif e.is_file(follow_symlinks=False):
                out.append(r)
            else:
                raise _Unfit(f"{d.name}/{r}: not a regular file or directory")
    walk(d, "")
    return out


def _file_shas(d: Path) -> dict[str, str]:
    return {rel: _sha((d / rel).read_bytes()) for rel in _metadata_files(d)}


def _station_sha(station_root: Path | None, slug: str) -> str | None:
    """sha256 of the station copy's manifest; None when there is no station copy."""
    if station_root is None:
        return None
    path = station_root / slug / STATION_MANIFEST
    try:
        return _sha(path.read_bytes())
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _Unfit(f"{slug}: station manifest unreadable: {' '.join(str(exc).split())}") \
            from exc


# --- take ---

def take(snap: Path, root: Path, slugs: list[str], *, station_root: Path | None) -> None:
    """Snapshot `slugs`' library files into the new directory `snap` (see the module
    docstring). Any failure removes the partial directory and raises `LlamaError`;
    an existing `snap` is refused and left as it is."""
    _check_station_root(station_root)
    order = list(dict.fromkeys(slugs))
    for slug in order:
        _check_slug(slug)
    snap.parent.mkdir(parents=True, exist_ok=True)
    try:
        snap.mkdir()
    except FileExistsError as exc:
        raise LlamaError(f"refusing to snapshot: {snap} exists") from exc
    try:
        files: dict[str, str] = {}
        station: dict[str, str | None] = {}
        out_shows = snap / "shows"
        out_shows.mkdir()
        for slug in order:
            d = _show_dir(root, slug)
            if d is None:
                raise _Unfit(f"{slug}: no show directory {root / 'shows' / slug}")
            with file_lock(ShowWorkspace(d).lock):
                rels = _metadata_files(d)
                if not rels:
                    raise _Unfit(f"{slug}: holds no file outside {_AUDIO}/ to snapshot")
                top = out_shows / slug
                dirs = {top}
                for rel in rels:
                    data = (d / rel).read_bytes()
                    want = _sha(data)
                    dst = top / rel
                    _write_copy(dst, data)
                    got = _sha(dst.read_bytes())
                    if got != want:
                        raise _Unfit(f"{slug}/{rel}: the copy differs from its source "
                                     f"(sha256 {got} vs {want})")
                    files[f"{slug}/{rel}"] = want
                    p = dst.parent
                    while p != top:             # every directory the copy created
                        dirs.add(p)
                        p = p.parent
                station[slug] = _station_sha(station_root, slug)
            for p in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
                _sync_dir(p)
        _sync_dir(out_shows)
        manifest = {"created_at": _now(), "slugs": order, "files": files,
                    "station": station}
        tmp = snap / _MANIFEST_TMP
        _write_copy(tmp, json.dumps(manifest, indent=2).encode())
        os.rename(tmp, snap / MANIFEST)
        _sync_dir(snap)
        _sync_dir(snap.parent)          # the snapshot directory's own entry
        problems = verify(snap)
        if problems:
            raise _Unfit("the written snapshot does not verify: " + "; ".join(problems))
    except BaseException as exc:
        removed = _discard_partial(snap)
        if not isinstance(exc, Exception):
            raise
        what = str(exc) if isinstance(exc, LlamaError) else f"{type(exc).__name__}: {exc}"
        tail = (f"removed {snap}" if removed else
                f"could not remove {snap}; it has no {MANIFEST}, so it is no snapshot: "
                f"remove it by hand")
        raise LlamaError(f"snapshot failed: {what}; {tail}") from exc


def _discard_partial(snap: Path) -> bool:
    """Remove a failed snapshot: manifest.json first, so whatever remains is no
    snapshot, then the directory. True when it is gone."""
    try:
        (snap / MANIFEST).unlink(missing_ok=True)
    except OSError:
        pass
    shutil.rmtree(snap, ignore_errors=True)
    return not os.path.lexists(snap)


# --- verify ---

def _key_problem(key: str) -> str | None:
    p = PurePosixPath(key)
    if (not key or p.is_absolute() or "\\" in key or len(p.parts) < 2
            or any(part in ("", ".", "..") for part in key.split("/"))):
        return f"{key!r}: not a <slug>/<path> entry inside the snapshot"
    return None


def _first_line(exc: BaseException) -> str:
    return (str(exc).splitlines() or [type(exc).__name__])[0]


def verify(snap: Path) -> list[str]:
    """Problems with snapshot directory `snap`; [] means it verifies: `manifest.json`
    is readable and well-formed, every entry's file exists under `shows/` with its
    sha256, every recorded slug has an entry and a station value (sha256 or null),
    and every entry belongs to a recorded slug. A file the manifest does not list is
    no problem: nothing reads it."""
    mpath = snap / MANIFEST
    if not mpath.is_file():
        return [f"no {MANIFEST}"]
    try:
        m = json.loads(mpath.read_bytes())
    except Exception as exc:
        return [f"{MANIFEST} unreadable: {_first_line(exc)}"]
    if not isinstance(m, dict):
        return [f"{MANIFEST} unreadable: a JSON {type(m).__name__}, not an object"]
    problems = []
    created = m.get("created_at")
    try:
        if (not isinstance(created, str)
                or datetime.fromisoformat(created).utcoffset() != timedelta(0)):
            raise ValueError
    except ValueError:
        problems.append(f"{MANIFEST}: created_at {created!r} is not a UTC ISO time")
    slugs, files, station = m.get("slugs"), m.get("files"), m.get("station")
    if (not isinstance(slugs, list) or not all(isinstance(s, str) and s for s in slugs)
            or len(set(slugs)) != len(slugs)):
        problems.append(f"{MANIFEST}: slugs is not a list of distinct names")
        slugs = None
    if not isinstance(files, dict) or not all(isinstance(v, str) for v in files.values()):
        problems.append(f"{MANIFEST}: files is not a path -> sha256 object")
        files = None
    if (not isinstance(station, dict)
            or not all(v is None or isinstance(v, str) for v in station.values())):
        problems.append(f"{MANIFEST}: station is not a slug -> sha256-or-null object")
        station = None
    if slugs is None or files is None or station is None:
        return problems
    recorded = set(slugs)
    if set(station) != recorded:
        problems.append(f"{MANIFEST}: station does not name exactly the recorded slugs")
    covered = set()
    for key, sha in files.items():
        bad = _key_problem(key)
        if bad:
            problems.append(bad)
            continue
        slug = key.split("/", 1)[0]
        if slug not in recorded:
            problems.append(f"{key}: {slug} is not a recorded slug")
        covered.add(slug)
        path = snap / "shows" / key
        if path.is_symlink() or not path.is_file():
            problems.append(f"{key}: missing from the snapshot")
            continue
        try:
            got = _sha(path.read_bytes())
        except OSError as exc:
            problems.append(f"{key}: unreadable ({exc})")
            continue
        if got != sha:
            problems.append(f"{key}: sha256 {got} differs from the manifest's {sha}")
    for slug in slugs:
        if slug not in covered:
            problems.append(f"{slug}: recorded slug has no entry")
    return problems


def _load_manifest(snap: Path) -> dict:
    """The snapshot's manifest, shape-checked but not hash-verified (`verify`)."""
    try:
        m = json.loads((snap / MANIFEST).read_bytes())
    except (OSError, ValueError) as exc:
        raise LlamaError(f"{snap}: no readable snapshot {MANIFEST} "
                         f"({_first_line(exc)})") from exc
    if (not isinstance(m, dict) or not isinstance(m.get("slugs"), list)
            or not isinstance(m.get("files"), dict) or not isinstance(m.get("station"), dict)):
        raise LlamaError(f"{snap}: snapshot {MANIFEST} is malformed")
    return m


# --- after-records ---

def record_after(snap: Path, slug: str, root: Path, *, station_root: Path | None) -> None:
    """Append `{slug, files: {rel: sha}, station: sha|None, at}` to `<snap>/after.jsonl`,
    flushed. Takes no lock: the caller holds the show lock. Refuses (LlamaError) a slug
    the snapshot does not record: a write with no undo point must not go ahead."""
    m = _load_manifest(snap)
    if slug not in m["slugs"]:
        raise LlamaError(f"{slug}: not in the batch snapshot {snap}")
    _check_station_root(station_root)
    d = _show_dir(root, slug)
    if d is None:
        raise LlamaError(f"{slug}: no show directory {root / 'shows' / slug}")
    row = {"slug": slug, "files": _file_shas(d),
           "station": _station_sha(station_root, slug), "at": _now()}
    line = (json.dumps(row) + "\n").encode()
    fd = os.open(snap / AFTER, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        view = memoryview(line)
        while view:
            view = view[os.write(fd, view):]
        _sync_fd(fd)
    finally:
        os.close(fd)
    _sync_dir(snap)


def _after_records(snap: Path) -> dict[str, dict]:
    """The latest after-record per slug. An unreadable line refuses the restore."""
    path = snap / AFTER
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    try:
        text = path.read_text()
    except (OSError, ValueError) as exc:
        raise LlamaError(f"{path} unreadable ({_first_line(exc)}); nothing restored") from exc
    for n, line in enumerate(text.splitlines(), 1):
        try:
            row = json.loads(line)
            ok = (isinstance(row, dict) and isinstance(row.get("slug"), str)
                  and isinstance(row.get("files"), dict)
                  and all(isinstance(v, str) for v in row["files"].values())
                  and (row.get("station") is None or isinstance(row.get("station"), str)))
        except ValueError:
            ok = False
        if not ok:
            raise LlamaError(f"{path} line {n} is not an after-record; nothing restored")
        out[row["slug"]] = row
    return out


def seal(snap: Path, root: Path, *, station_root: Path | None) -> None:
    """`record_after` for every show the snapshot records, each under its show lock.
    A show directory that is gone gets no record (restore then refuses it)."""
    m = _load_manifest(snap)
    for slug in m["slugs"]:
        d = _show_dir(root, slug)
        if d is None:
            continue
        with file_lock(ShowWorkspace(d).lock):
            record_after(snap, slug, root, station_root=station_root)


# --- restore ---

def restore(snap: Path, root: Path, *, station_root: Path | None, apply: bool,
            slugs: set[str] | None = None,
            echo: Callable[[str], None]) -> list[tuple[str, str]]:
    """Rewind the batch's shows (all recorded slugs, or those in `slugs`), each under
    its show lock; echo and return `(slug, action)` per show, a refusal reading
    `refused: <why>`. Without `apply` it only reports. Never writes the station.
    A snapshot that does not verify, or an unreadable after.jsonl, refuses the whole
    restore before any show is read."""
    problems = verify(snap)
    if problems:
        raise LlamaError(f"snapshot {snap} does not verify; nothing restored", problems)
    m = _load_manifest(snap)
    _check_station_root(station_root)
    after = _after_records(snap)
    recorded = m["slugs"]
    want = recorded if slugs is None else (
        [s for s in recorded if s in slugs] + sorted(set(slugs) - set(recorded)))
    results = []
    for slug in want:
        if slug not in recorded:
            action = "refused: not in this snapshot"
        else:
            action = _restore_one(snap, m, slug, root, station_root, after.get(slug),
                                  apply=apply)
        echo(f"{slug}: {action}")
        results.append((slug, action))
    return results


def _restore_one(snap: Path, m: dict, slug: str, root: Path, station_root: Path | None,
                 after: dict | None, *, apply: bool) -> str:
    snap_files = {key.split("/", 1)[1]: sha for key, sha in m["files"].items()
                  if key.split("/", 1)[0] == slug}
    d = _show_dir(root, slug)
    if d is None:                       # never lock it: file_lock would recreate the dir
        return "refused: the show directory is gone"
    with file_lock(ShowWorkspace(d).lock):
        try:
            current = _file_shas(d)
            station = _station_sha(station_root, slug)
        except _Unfit as exc:
            return f"refused: {exc}"
        if after is None:
            if current == snap_files and station == m["station"][slug]:
                return "untouched"
            return f"refused: {NO_WRITE}"
        if current == snap_files and station == after["station"]:
            return "untouched" if after["files"] == snap_files else "already restored"
        if current != after["files"]:
            first = min(k for k in set(current) | set(after["files"])
                        if current.get(k) != after["files"].get(k))
            return "refused: " + LIBRARY_CHANGED.format(rel=first)
        if station != after["station"]:
            return f"refused: {STATION_CHANGED}"
        empty = snap_files.get(_PACKAGE_MANIFEST) != current.get(_PACKAGE_MANIFEST)
        if not apply:
            return "would restore" + ("; would empty package/audio" if empty else "")
        _rewind(snap, slug, d, snap_files, current, empty=empty)
        return "restored" + ("; package/audio emptied" if empty else "")


def _rewind(snap: Path, slug: str, d: Path, snap_files: dict[str, str],
            current: dict[str, str], *, empty: bool) -> None:
    """Empty `package/audio/` (when the package manifest differs), delete tracked
    files the snapshot lacks, write back the snapshot's files that differ. Every
    snapshot copy is read and hash-checked before the first write."""
    data = {}
    for rel, sha in snap_files.items():
        if current.get(rel) == sha:
            continue
        blob = (snap / "shows" / slug / rel).read_bytes()
        if _sha(blob) != sha:
            raise LlamaError(f"{slug}/{rel}: the snapshot copy no longer matches its "
                             f"sha256; nothing restored for {slug}")
        data[rel] = blob
    touched: set[Path] = set()
    try:
        if empty:
            audio = d / _AUDIO
            if audio.is_dir() and not audio.is_symlink():
                with os.scandir(audio) as it:
                    for e in it:
                        if not e.is_dir(follow_symlinks=False):
                            os.unlink(e.path)
                _sync_dir(audio)
        keep_dirs = {d / PurePosixPath(rel).parent for rel in snap_files}
        for rel in sorted(set(current) - set(snap_files)):
            path = d / rel
            path.unlink()
            touched.add(path.parent)
            p = path.parent
            while p != d and p not in keep_dirs and not any(p.iterdir()):
                p.rmdir()
                touched.discard(p)
                touched.add(p.parent)
                p = p.parent
        for rel, blob in sorted(data.items()):
            _durable_replace(d / rel, blob)
            touched.add((d / rel).parent)
        for p in sorted(touched, key=lambda p: len(p.parts), reverse=True):
            if p.is_dir():
                _sync_dir(p)
    except OSError as exc:
        raise LlamaError(f"{slug}: restore failed part-way ({exc}); the show is partly "
                         f"restored and a re-run will refuse it: copy its files back "
                         f"by hand from {snap / 'shows' / slug}") from exc
