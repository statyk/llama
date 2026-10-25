#!/usr/bin/env python3
"""One-off migration: re-key each show's positional overrides from track numbers to
filenames (piece 4 spec 4.3).

`overrides.json`'s `titles`, `set_breaks` and `encore_after` were keyed by track number
(v2.17.0). The short-keep rule inserts tracks, which would re-point every key after an
insertion silently, so the new code keys them by filename (`llama.override_keys`). This
script maps each legacy number N to `show.json`'s `tracks[N-1].filename`, and only after
proving, per show, that the stored positions, the stored `show.json` and the current
inputs agree. An ambiguous show is never guessed: it is refused with its repair route.

Run it from the repo with the tree's own interpreter, never through a `.venv/bin/*`
console script from a copy:

    /Users/shawn/projects/llama/.venv/bin/python scripts/rekey_overrides.py [--config P]

With no option it is a DRY RUN: it checks every show, prints what it would re-key and
every refusal with its repair route, and what the process check finds. It takes no lock
and creates no file. Its checks read only `overrides.json`, `show.json` and the cached
metadata of the item `show.json` names.

`--snapshot` copies every show's metadata (every file outside `package/audio/` and
`.audio-aside/`, the `.lock` aside) into `<root>/rekey-snapshot-<UTC start>/`, each copy
verified against its source's sha256 and flushed, then writes `manifest.json` last. It is
the migration's only rollback point: a directory without `manifest.json` is no snapshot.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

import llama
from llama.audio_reuse import ASIDE_DIR
from llama.catalog import _sync_fd, human_bytes
from llama.config import DEFAULT_ROOT, load_config
from llama.junk import FORMAT_BY_AUDIO
from llama.errors import LlamaError
from llama.locks import Locked, file_lock
from llama.models import Overrides, Show
from llama.override_keys import classify, filename_values, legacy_int
from llama.replay import CacheMiss, CacheOnlyIA
from llama.stages.gather import _validate_structure_override, final_kept
from llama.workspace import ShowWorkspace

# The migration contracts (Tasks 17-20).
REKEY_MIN_VERSION = "2.18.0"          # the piece-4 release version (operator: confirmed)
SNAPSHOT_PREFIX = "rekey-snapshot-"   # <root>/rekey-snapshot-<YYYYmmddTHHMMSSZ>/ (UTC copy start)
APPLIED = "rekey-applied.json"        # <root>/rekey-applied.json
LOCK = ".rekey.lock"                  # <root>/.rekey.lock, flock, outermost

# Spec 4.3 "Routes with no CLI form": a titles key of -1 or below, two keys collapsing
# to one number, and a `redo --from gather` route that cannot run.
HAND_EDIT_ROUTE = "a hand edit of overrides.json, with v2.17.0 still installed"

_REDO = "`llama redo <show> --from gather`"

# reason -> its repair route, the spec 4.3 table's text (step 3, v2.17.0 installed). The
# table's "(below)" is spelled out as HAND_EDIT_ROUTE, since the output has no "below".
REASONS = {
    "unreadable": "the operator repairs the file by hand; the dry run lists every such file",
    "mixed": ("only a hand edit can produce this (writers refuse legacy files, 4.1): undo "
              "that hand edit. The refusal names each filename-valued key. Do it first, since "
              "v2.17.0 cannot run on a library holding the file"),
    "duplicate key": HAND_EDIT_ROUTE,
    "no show.json": _REDO,
    "title out of range": (f"`llama fix <show> --clear-title k`; a key of -1 or below needs "
                           f"{HAND_EDIT_ROUTE}"),
    "title not applied": _REDO,
    "structure out of range": ("note the values, `llama fix <show> --clear-set-breaks` / "
                               "`--clear-encore`, then set corrected values with "
                               "`--set-breaks` / `--set-encore`"),
    "structure not applied": _REDO,
    "repeated filename": ("note the affected keys' values, clear them with `llama fix <show> "
                          "--clear-title k` / `--clear-set-breaks` / `--clear-encore`, then "
                          "migrate. A filename key cannot name a repeated file, so that show "
                          "carries no title/break/encore override on those files until the "
                          "duplicate is resolved (accepted limitation; 0 shows today)"),
    "kept list differs": _REDO,
}

# The reasons whose route is `llama redo <show> --from gather`.
_REDO_REASONS = frozenset(k for k, v in REASONS.items() if v == _REDO)


@dataclass(frozen=True)
class Refusal:
    slug: str
    reason: str          # one of REASONS' keys
    detail: str          # the values involved (keys, numbers, filenames)
    route: str           # REASONS[reason], the spec 4.3 table's repair text


@dataclass(frozen=True)
class Rekey:
    slug: str
    titles: int
    breaks: int
    encore: bool


class _Refused(Exception):
    """Exit 1 with this message before any show is read."""


def _show_dirs(root: Path) -> list[Path]:
    shows = root / "shows"
    return sorted(d for d in shows.iterdir() if d.is_dir()) if shows.is_dir() else []


def _read(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def _quoted(keys: Iterable[str]) -> str:
    return ", ".join(repr(str(k)) for k in keys)


def _reads_as(keys: Iterable[str]) -> str:
    """Each key with the number v2.17.0 reads it as (`'7_0' (reads as 70)`)."""
    return ", ".join(f"{str(k)!r} (reads as {legacy_int(k)})" for k in keys)


def _first_line(exc: BaseException) -> str:
    text = str(exc).strip()
    return text.splitlines()[0] if text else type(exc).__name__


def check_show(ws: ShowWorkspace, ia, want: Sequence[str], *,
               overrides_bytes: bytes | None = None,
               show_bytes: bytes | None = None) -> Rekey | list[Refusal] | None:
    """Judge one show (spec 4.3 "Checks"): a `Rekey` when every check passes, the list of
    refusals when any fails, None when its overrides.json holds no legacy value (absent,
    none, or already migrated). Reads only overrides.json, show.json and
    `ia.metadata(show.identifier)`; the bytes arguments, when given, are judged in place
    of the files (so --apply judges exactly what it re-read under the lock).

    `unreadable` and `mixed` each stop further checks; every other check runs and every
    failure is reported."""
    slug = ws.dir.name

    def refuse(reason: str, detail: str, route: str | None = None) -> Refusal:
        return Refusal(slug=slug, reason=reason, detail=detail,
                       route=REASONS[reason] if route is None else route)

    if overrides_bytes is None:
        try:
            overrides_bytes = _read(ws.overrides)
        except OSError as exc:
            return [refuse("unreadable", f"overrides.json: {exc}")]
        if overrides_bytes is None:
            return None
    try:
        raw = json.loads(overrides_bytes)
        if not isinstance(raw, dict):
            raise ValueError(f"a JSON {type(raw).__name__}, not an object")
        ov = Overrides.model_validate_json(overrides_bytes)
    except Exception as exc:   # invalid JSON, or the new model cannot read it
        return [refuse("unreadable", f"overrides.json: {_first_line(exc)}")]

    kind = classify(raw)
    if kind == "mixed":
        named = ", ".join(f"{k} {f}" for k, f in filename_values(raw))
        return [refuse("mixed", f"filename-valued: {named}")]
    if kind != "legacy":
        return None

    titles: dict[str, str] = raw.get("titles") or {}
    set_breaks = raw.get("set_breaks")
    encore_after = raw.get("encore_after")
    structure = set_breaks is not None or encore_after is not None
    out: list[Refusal] = []

    # A redo route that cannot run (no provenance.json) names the hand edit instead.
    def route_of(reason: str) -> str | None:
        if reason in _REDO_REASONS and not ws.provenance.exists():
            return (f"{HAND_EDIT_ROUTE} ({_REDO} cannot run without provenance.json; "
                    f"spec 4.3 \"Routes with no CLI form\")")
        return None

    def add(reason: str, detail: str, route: str | None = None) -> None:
        out.append(refuse(reason, detail, route if route is not None else route_of(reason)))

    # duplicate key: two titles keys parse to the same number ("7" and "07").
    by_number: dict[int, list[str]] = {}
    for k in titles:
        by_number.setdefault(legacy_int(k), []).append(k)
    dups = [f"titles keys {_quoted(ks)} all read as {n}"
            for n, ks in by_number.items() if len(ks) > 1]
    if dups:
        add("duplicate key", "; ".join(dups))

    show = None
    try:
        if show_bytes is None:
            show_bytes = _read(ws.show)
        if show_bytes is None:
            add("no show.json", "show.json is missing")
        else:
            show = Show.model_validate_json(show_bytes)
    except Exception as exc:
        add("no show.json", f"show.json unreadable: {_first_line(exc)}")

    if show is None:
        # Without a track list only a key of -1 or below is known to be out of range.
        negative = [k for k in titles if legacy_int(k) <= -1]
        if negative:
            add("title out of range", f"titles keys {_reads_as(negative)} below 1",
                HAND_EDIT_ROUTE)
        return out

    tracks = show.tracks
    n_tracks = len(tracks)

    # title out of range: a key outside 1..len(tracks). -1 or below has no CLI form.
    outside = [k for k in titles if not 1 <= legacy_int(k) <= n_tracks]
    cli = [k for k in outside if legacy_int(k) > -1]
    negative = [k for k in outside if legacy_int(k) <= -1]
    if cli:
        add("title out of range", f"titles keys {_reads_as(cli)} outside 1..{n_tracks}")
    if negative:
        add("title out of range", f"titles keys {_reads_as(negative)} outside 1..{n_tracks}",
            HAND_EDIT_ROUTE)

    # title not applied: the track at the key is not an override with exactly that title.
    unapplied = []
    for k, forced in titles.items():
        n = legacy_int(k)
        if not 1 <= n <= n_tracks:
            continue
        t = tracks[n - 1]
        if t.title_source != "override" or t.title != forced:
            unapplied.append(f"track {n} ({t.filename}): title_source {t.title_source}, "
                             f"title {t.title!r}, forced {forced!r}")
    if unapplied:
        add("title not applied", "; ".join(unapplied))

    # The structure checks, only when set_breaks or encore_after is present.
    if structure:
        breaks = [legacy_int(v) for v in (set_breaks or [])]
        encore = None if encore_after is None else legacy_int(encore_after)
        try:
            _validate_structure_override(n_tracks, breaks, encore)
        except LlamaError as exc:
            add("structure out of range", str(exc))
        want_breaks = sorted(set(breaks) | ({encore} if encore is not None else set()))
        if show.set_breaks != want_breaks:
            add("structure not applied", f"show.json set_breaks {show.set_breaks}, overrides "
                                         f"give {want_breaks} (set_breaks {breaks}, "
                                         f"encore_after {encore})")

    # repeated filename.
    repeated = sorted(f for f, c in Counter(t.filename for t in tracks).items() if c > 1)
    if repeated:
        add("repeated filename", ", ".join(repeated))

    # kept list differs: show.json's list against today's rule (short_keep=False), from
    # the current cached metadata plus include minus exclude.
    names = [t.filename for t in tracks]
    try:
        md = ia.metadata(show.identifier)
        kept = [f["name"] for f in final_kept(md.get("files", []), ov, want,
                                              short_keep=False).kept]
    except CacheMiss as exc:
        add("kept list differs", f"no cached metadata for {show.identifier} ({exc})")
    except Exception as exc:
        add("kept list differs", f"cannot compute the kept list for {show.identifier}: "
                                 f"{type(exc).__name__}: {exc}")
    else:
        if kept != names:
            add("kept list differs", _kept_diff(names, kept))

    if out:
        return out
    return Rekey(slug=slug, titles=len(titles), breaks=len(set_breaks or []),
                 encore=encore_after is not None)


def _kept_diff(names: list[str], kept: list[str]) -> str:
    at = next((i for i, (a, b) in enumerate(zip(names, kept)) if a != b),
              min(len(names), len(kept)))
    left = names[at] if at < len(names) else "(end)"
    right = kept[at] if at < len(kept) else "(end)"
    return (f"show.json has {len(names)} tracks, today's rule keeps {len(kept)}; first "
            f"difference at track {at + 1}: {left} vs {right}")


def _form(ws: ShowWorkspace) -> str | None:
    """classify() of a readable overrides.json, else None (absent or unreadable)."""
    try:
        data = _read(ws.overrides)
        raw = json.loads(data) if data is not None else None
    except Exception:
        return None
    return classify(raw) if isinstance(raw, dict) else None


def check_library(root: Path, ia, want) -> tuple[list[Rekey], list[Refusal], list[str]]:
    """Every show dir under `<root>/shows`, sorted: (the shows to re-key, every refusal,
    the migrated slugs, i.e. those whose overrides.json classifies `filename`)."""
    rekeys: list[Rekey] = []
    refused: list[Refusal] = []
    migrated: list[str] = []
    for d in _show_dirs(root):
        ws = ShowWorkspace(d)
        got = check_show(ws, ia, want)
        if isinstance(got, Rekey):
            rekeys.append(got)
        elif got:
            refused += got
        elif _form(ws) == "filename":
            migrated.append(d.name)
    return rekeys, refused, migrated


# --- the process check (spec 4.3 "The process check") ---

_SHELLS = frozenset({"sh", "bash", "zsh"})
_SEPARATORS = re.compile(r"&&|\|\||[;|\n]")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_LEADERS = frozenset({"do", "then", "else", "("})
SELF_SCRIPT = "rekey_overrides.py"
# What the check cannot see: a loop typed at an interactive prompt runs in the login
# shell (`-zsh`, no `-c`), so while it sleeps nothing in ps names llama.
PROCESS_NOTE = ("note: the process check cannot see a sweep loop typed at an interactive "
                "prompt while it sleeps; stop it by hand (runbook step 1)")


def _unquote(word: str) -> str:
    return word.strip("'\"")


def _shell_string(args: list[str]) -> str | None:
    """The `-c` string of a shell's arguments (ps joins argv with spaces, so it is the
    rest of the line), else None. `-c` may sit in an option cluster (`-lc`)."""
    for i, a in enumerate(args):
        if a.startswith("-") and not a.startswith("--") and "c" in a[1:]:
            s = " ".join(args[i + 1:]).strip()
            if len(s) >= 2 and s[0] in "'\"" and s[-1] == s[0]:
                s = s[1:-1]
            return s
    return None


def _simple_commands(s: str) -> list[list[str]]:
    out = []
    for piece in _SEPARATORS.split(s):
        words = [_unquote(w) for w in piece.split()]
        words = [w for w in words if w]
        while words:
            if words[0] in _LEADERS or _ASSIGNMENT.match(words[0]):
                words.pop(0)
            elif words[0].startswith("(") and len(words[0]) > 1:
                words[0] = words[0][1:]
            else:
                break
        if words:
            out.append(words)
    return out


def _runs_llama(words: list[str]) -> bool:
    """`llama` in command position: the first word's basename is `llama`; a python whose
    arguments hold `-m llama`, or whose first non-option argument is a `.py` under a
    `scripts/` directory (not this script) or a `llama` console script; a shell's `-c`
    string, judged per simple command."""
    if not words:
        return False
    first = _unquote(words[0])
    base = first.rsplit("/", 1)[-1]
    args = [_unquote(w) for w in words[1:]]
    if base == "llama":
        return True
    if base.lower().startswith("python"):
        if any(a == "-m" and b == "llama" for a, b in zip(args, args[1:])):
            return True
        script = next((a for a in args if not a.startswith("-")), None)
        if script is None:
            return False
        p = PurePosixPath(script)
        if p.name == "llama":
            # A console script run through its interpreter: how macOS ps shows a venv
            # `llama` (Homebrew's framework Python re-execs; measured 2026-10-24).
            return True
        return (p.suffix == ".py" and "scripts" in p.parts[:-1] and p.name != SELF_SCRIPT)
    if base in _SHELLS:
        s = _shell_string(args)
        return s is not None and any(_runs_llama(c) for c in _simple_commands(s))
    return False


def llama_processes(ps_lines: Iterable[str], *, self_pid: int) -> list[str]:
    """The `ps -axo pid=,ppid=,command=` lines whose command runs llama, other than this
    script: `self_pid` and every ancestor of it never match."""
    rows: list[tuple[int, int, str, str]] = []
    for line in ps_lines:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        rows.append((pid, ppid, parts[2], line.strip()))
    parent = {pid: ppid for pid, ppid, _, _ in rows}
    skip, cur = set(), self_pid
    while cur not in skip:
        skip.add(cur)
        if cur not in parent:
            break
        cur = parent[cur]
    return [line for pid, _, cmd, line in rows
            if pid not in skip and _runs_llama(cmd.split())]


def _ps_lines() -> list[str]:
    done = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True,
                          text=True, check=True)
    return done.stdout.splitlines()


# --- --snapshot (spec 4.3 "`--snapshot`") ---

MANIFEST = "manifest.json"
_MANIFEST_TMP = ".manifest.json.tmp"
_STAMP = "%Y%m%dT%H%M%SZ"


def _is_husk(d: Path) -> bool:
    """A show directory holding no file other than its top-level `.lock`: an `rm` husk
    (show_unit limitation 2). It is not a show. Anything that is not a real directory
    (a file, a symlink, anything else) counts as content, at any depth."""
    def empty(p: Path, top: bool) -> bool:
        with os.scandir(p) as it:
            for e in it:
                if top and e.name == ".lock":
                    continue
                if e.is_dir(follow_symlinks=False):
                    if not empty(Path(e.path), False):
                        return False
                else:
                    return False
        return True
    return empty(d, True)


def library_shows(root: Path) -> list[Path]:
    """Every show directory under `<root>/shows`, sorted, `.lock`-only husks left out:
    the set the snapshot records and every coverage check compares against."""
    return [d for d in _show_dirs(root) if not _is_husk(d)]


def _form_problem(data: bytes | None) -> str | None:
    """Why an overrides.json (its bytes, None = absent) bars a snapshot: it holds a
    filename value (`filename` or `mixed`), or it cannot be read as an object, so it
    cannot be shown not to. None when it is fine (absent, none or legacy)."""
    if data is None:
        return None
    try:
        raw = json.loads(data)
    except Exception as exc:
        return f"unreadable ({_first_line(exc)})"
    if not isinstance(raw, dict):
        return f"unreadable (a JSON {type(raw).__name__}, not an object)"
    kind = classify(raw)
    if kind in ("filename", "mixed"):
        named = ", ".join(f"{k} {f}" for k, f in filename_values(raw))
        return f"{kind} (filename-valued: {named})"
    return None


def _process_gate(echo) -> None:
    """The process check (spec 4.3): refuse while anything other than this script runs
    llama, or when the check itself cannot run."""
    try:
        found = llama_processes(_ps_lines(), self_pid=os.getpid())
    except Exception as exc:
        raise _Refused(f"process check failed: {type(exc).__name__}: {exc}") from exc
    if found:
        echo("llama processes running:")
        for line in found:
            echo(f"  {line}")
        raise _Refused("refusing: llama is running; stop it first (runbook step 1)")
    echo("llama processes running: none")
    echo(PROCESS_NOTE)


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


class _SnapshotFailed(Exception):
    pass


def _metadata_files(d: Path) -> list[str]:
    """Posix relpaths of every file under show dir `d` outside `package/audio/` and
    `.audio-aside/`, the top-level `.lock` aside, sorted. A symlink or any other
    non-regular entry fails the snapshot: it cannot be copied faithfully."""
    out: list[str] = []

    def walk(p: Path, rel: str) -> None:
        with os.scandir(p) as it:
            entries = sorted(it, key=lambda e: e.name)
        for e in entries:
            r = f"{rel}/{e.name}" if rel else e.name
            real_dir = e.is_dir(follow_symlinks=False)
            if r == ".lock" or (real_dir and r in (ASIDE_DIR, "package/audio")):
                continue
            if real_dir:
                walk(Path(e.path), r)
            elif e.is_file(follow_symlinks=False):
                out.append(r)
            else:
                raise _SnapshotFailed(f"{d.name}/{r}: not a regular file or directory")
    walk(d, "")
    return out


def snapshot(root: Path, *, echo, now: datetime | None = None) -> Path:
    """Take the migration's rollback point (spec 4.3 "`--snapshot`") and return its
    directory. Refuses (`_Refused`, nothing created, the lock file included) while llama
    runs or when any show's overrides.json holds a filename value or cannot be read.
    Then, under the migration lock and each show's lock, copies every metadata file,
    verifies each copy's sha256 against its source and flushes it, and writes
    `manifest.json` last, durably. Any failure leaves no manifest.json, removes the
    partial directory and raises `_Refused` (KeyboardInterrupt and the like re-raised)."""
    shows_dir = root / "shows"
    if not shows_dir.is_dir():
        raise _Refused(f"refusing to snapshot: {shows_dir} is not a directory")
    _process_gate(echo)
    barred = []
    try:
        shows = library_shows(root)
    except OSError as exc:
        raise _Refused(f"refusing to snapshot: cannot list {shows_dir}: {exc}") from exc
    for d in shows:
        try:
            problem = _form_problem(_read(d / "overrides.json"))
        except OSError as exc:
            problem = f"unreadable ({exc})"
        if problem:
            barred.append(f"  {d.name}: {problem}")
    if barred:
        for line in barred:
            echo(line)
        raise _Refused(f"refusing to snapshot: {len(barred)} show(s) above hold a filename "
                       f"value or an unreadable overrides.json; a partly migrated library is "
                       f"no rollback point")

    with contextlib.ExitStack() as stack:
        try:
            stack.enter_context(file_lock(root / LOCK, blocking=False))
        except Locked as exc:
            raise _Refused(f"refusing to snapshot: {root / LOCK} is held by another "
                           f"rekey_overrides run") from exc
        return _take_snapshot(root, echo=echo, now=now)


def _take_snapshot(root: Path, *, echo, now: datetime | None) -> Path:
    start = datetime.now(timezone.utc) if now is None else now
    if start.utcoffset() is None:
        raise ValueError("snapshot: `now` must be timezone-aware")
    start = start.astimezone(timezone.utc)
    snap = root / (SNAPSHOT_PREFIX + start.strftime(_STAMP))
    try:
        snap.mkdir()
    except FileExistsError as exc:
        raise _Refused(f"refusing to snapshot: {snap} exists") from exc
    t0 = time.monotonic()
    try:
        files: dict[str, str] = {}
        size = 0
        slugs = [d.name for d in library_shows(root)]
        out_shows = snap / "shows"
        out_shows.mkdir()
        for i, slug in enumerate(slugs):
            if i and i % 100 == 0:
                echo(f"  {i}/{len(slugs)} shows copied")
            d = root / "shows" / slug
            if d.is_symlink() or not d.is_dir():
                raise _SnapshotFailed(f"{slug}: no longer a show directory")
            with file_lock(ShowWorkspace(d).lock):
                rels = _metadata_files(d)
                if not rels:
                    raise _SnapshotFailed(
                        f"{slug}: holds no file outside package/audio/ and {ASIDE_DIR}/ "
                        f"to snapshot; remove or repair the directory by hand")
                top = out_shows / slug
                dirs = {top}
                for rel in rels:
                    data = (d / rel).read_bytes()
                    want = hashlib.sha256(data).hexdigest()
                    dst = out_shows / slug / rel
                    _write_copy(dst, data)
                    got = hashlib.sha256(dst.read_bytes()).hexdigest()
                    if got != want:
                        raise _SnapshotFailed(f"{slug}/{rel}: the copy differs from its "
                                              f"source (sha256 {got} vs {want})")
                    if rel == "overrides.json":
                        problem = _form_problem(data)
                        if problem:
                            raise _SnapshotFailed(f"{slug}: overrides.json changed before "
                                                  f"its show lock: {problem}")
                    files[f"{slug}/{rel}"] = want
                    size += len(data)
                    p = dst.parent
                    while p != top:             # every directory the copy created
                        dirs.add(p)
                        p = p.parent
                for p in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
                    _sync_dir(p)
        _sync_dir(out_shows)
        manifest = {"created_at": start.isoformat(), "slugs": slugs, "files": files}
        tmp = snap / _MANIFEST_TMP
        _write_copy(tmp, json.dumps(manifest, indent=2).encode())
        os.rename(tmp, snap / MANIFEST)
        _sync_dir(snap)
        problems = verify_snapshot(snap)
        if problems:
            raise _SnapshotFailed("the written snapshot does not verify: "
                                  + "; ".join(problems))
    except BaseException as exc:
        removed = _discard_partial(snap)
        if not isinstance(exc, Exception):
            raise
        what = str(exc) if isinstance(exc, (_SnapshotFailed, _Refused)) \
            else f"{type(exc).__name__}: {exc}"
        tail = (f"removed {snap}" if removed else
                f"could not remove {snap}; it has no {MANIFEST}, so it is no snapshot: "
                f"remove it by hand")
        raise _Refused(f"snapshot failed: {what}; {tail}") from exc
    echo(f"snapshot: {snap} ({len(slugs)} shows, {len(files)} files, {human_bytes(size)}, "
         f"{time.monotonic() - t0:.1f} s)")
    return snap


def _discard_partial(snap: Path) -> bool:
    """Remove a failed snapshot: manifest.json first, so whatever remains is no
    snapshot, then the directory. True when it is gone."""
    try:
        (snap / MANIFEST).unlink(missing_ok=True)
    except OSError:
        pass
    shutil.rmtree(snap, ignore_errors=True)
    return not snap.exists() and not os.path.lexists(snap)


def _key_problem(key: str) -> str | None:
    p = PurePosixPath(key)
    if (not key or p.is_absolute() or "\\" in key or len(p.parts) < 2
            or any(part in ("", ".", "..") for part in key.split("/"))):
        return f"{key!r}: not a <slug>/<path> entry inside the snapshot"
    return None


def verify_snapshot(snap: Path) -> list[str]:
    """Problems with snapshot directory `snap`; [] means it verifies: `manifest.json` is
    readable and well-formed, every entry's file exists under `shows/` with its sha256,
    every recorded slug has an entry and every entry belongs to a recorded slug. A file
    the manifest does not list (a Finder `.DS_Store`) is no problem: nothing reads it."""
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
    slugs, files = m.get("slugs"), m.get("files")
    if not isinstance(slugs, list) or not all(isinstance(s, str) and s for s in slugs):
        problems.append(f"{MANIFEST}: slugs is not a list of names")
        slugs = None
    if not isinstance(files, dict) or not all(isinstance(v, str) for v in files.values()):
        problems.append(f"{MANIFEST}: files is not a path -> sha256 object")
        files = None
    if slugs is None or files is None:
        return problems
    recorded = set(slugs)
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
            got = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            problems.append(f"{key}: unreadable ({exc})")
            continue
        if got != sha:
            problems.append(f"{key}: sha256 {got} differs from the manifest's {sha}")
    for slug in slugs:
        if slug not in covered:
            problems.append(f"{slug}: recorded slug has no entry")
    return problems


def find_snapshot(root: Path) -> Path | None:
    """The lexically newest `rekey-snapshot-*` directory under `root` that holds a
    `manifest.json` (it is not verified here: `verify_snapshot`)."""
    found = sorted(p for p in root.glob(SNAPSHOT_PREFIX + "*")
                   if p.is_dir() and (p / MANIFEST).is_file())
    return found[-1] if found else None


# --- main ---

def _check_identity() -> None:
    """`llama.__file__` (read at call time) must resolve under this tree's
    `packages/llama/src`, as `replay_holds._check_identity` (CLAUDE.md: never through a
    copied console script)."""
    tree = Path(__file__).resolve().parents[1]
    src = tree / "packages" / "llama" / "src"
    print(f"llama: {llama.__file__}", file=sys.stderr)
    if not Path(llama.__file__).resolve().is_relative_to(src):
        raise _Refused(f"refusing to run: llama imports from {llama.__file__}, "
                       f"not from this tree {tree}")


def _rekey_line(verb: str, r: Rekey) -> str:
    encore = ", encore" if r.encore else ""
    return f"{verb}: {r.slug} ({r.titles} titles, {r.breaks} breaks{encore})"


def _print_refusal(r: Refusal) -> None:
    """The route with the slug in place of `<show>`, so it can be pasted (the Refusal
    keeps REASONS' template)."""
    print(f"refused: {r.slug}: {r.reason} ({r.detail})")
    print(f"  repair: {r.route.replace('<show>', r.slug)}")


def dry_run(root: Path, ia, want) -> int:
    """Read and print only: no lock, no file."""
    gate_failed = False
    try:
        found = llama_processes(_ps_lines(), self_pid=os.getpid())
    except Exception as exc:
        print(f"process check failed: {type(exc).__name__}: {exc}")
        gate_failed = True
    else:
        if found:
            print("llama processes running:")
            for line in found:
                print(f"  {line}")
        else:
            print("llama processes running: none")
    print(PROCESS_NOTE)

    rekeys, refused, migrated = check_library(root, ia, want)
    by_slug: dict[str, list[Refusal]] = {}
    for r in refused:
        by_slug.setdefault(r.slug, []).append(r)
    rekey_of = {r.slug: r for r in rekeys}
    for slug in sorted(set(rekey_of) | set(by_slug)):
        if slug in rekey_of:
            print(_rekey_line("would rekey", rekey_of[slug]))
        for r in by_slug.get(slug, []):
            _print_refusal(r)
    total = len(_show_dirs(root))
    none = total - len(rekeys) - len(by_slug) - len(migrated)
    print(f"{len(rekeys)} to rekey, {len(by_slug)} refused, {len(migrated)} already migrated, "
          f"{none} without positional keys")
    return 1 if gate_failed or refused else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=None,
                    help="config file (default ~/.llama/config.toml, as llama)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--snapshot", action="store_true",
                      help="copy every show's metadata into <root>/rekey-snapshot-<UTC>/")
    args = ap.parse_args(argv)
    try:
        _check_identity()
        if args.config is not None and not args.config.exists():
            raise _Refused(f"no such config: {args.config}")
        config = load_config(args.config or DEFAULT_ROOT / "config.toml")   # as `llama` does
    except _Refused as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.snapshot:
        try:
            snapshot(config.root, echo=print)
        except _Refused as exc:
            print(str(exc))
            return 1
        return 0
    ia = CacheOnlyIA(config.root / "cache")
    want = FORMAT_BY_AUDIO[config.audio_format]
    return dry_run(config.root, ia, want)


if __name__ == "__main__":
    sys.exit(main())
