"""The title backfill (`emcee retitle`): its plan and raw single-field writer.

Stamps `dj_audio.title` on already-voiced station packages without
re-voicing them. STRICT surface: it rewrites `manifest.json` on the live
station share, so

- it works on the raw dict and sets only `dj_audio["title"]` (a block that
  lacks the key gets it LAST, as on the voicing path); every other key,
  `awaiting_fix` included, is carried untouched, and `dj_audio` is never
  round-tripped through `DJAudioBlock`;
- it refuses, rather than reformats, any manifest whose bytes are not
  exactly `encode(json.loads(bytes))`;
- it keeps the original mtime, set on the closed temp BEFORE the rename
  (hugo's transmitter treats a manifest younger than `quiet_minutes` as
  ineligible, and its NFS attribute cache can show a post-rename mtime for
  up to a minute), then re-checked after it;
- every step leaves the manifest fully old or fully new, at most with a stray
  `.manifest.json.emcee-<hex>.tmp`, wherever the process stops (the station
  lock's SIGTERM handler ends the process with `os._exit`, no cleanup).

Library code: nothing here takes the station lock; the command does.
"""
from __future__ import annotations

import json
import os
import secrets
import stat
from dataclasses import dataclass, field
from pathlib import Path

from emcee.config import EmceeConfig
from emcee.errors import EmceeError
from emcee.package_io import MIN_SUPPORTED_SCHEMA_VERSION
from emcee.process import assignment_for
from emcee.station import awaiting_fix_reason, manifest_voiced_profile

MANIFEST = "manifest.json"
NOT_ENCODED = "not in emcee's encoding"


def encode(data: dict) -> bytes:
    """emcee's manifest encoding (ensure_ascii left at its default)."""
    return (json.dumps(data, indent=2) + "\n").encode()


@dataclass(frozen=True)
class TitleWrite:
    slug: str
    dir: Path
    raw: bytes            # the manifest bytes the plan was built from
    old: str | None
    new: str | None


@dataclass
class RetitlePlan:
    writes: list[TitleWrite] = field(default_factory=list)
    awaiting: list[str] = field(default_factory=list)          # slugs, skipped
    refused: list[tuple[str, str]] = field(default_factory=list)  # (slug, reason)
    unchanged: int = 0
    unvoiced: int = 0


class TitleWriteFailed(EmceeError):
    """The post-rename check of a title write failed; the message says whether
    the original was put back or another writer's bytes were left in place."""


def _packages(station_root: Path) -> list[Path]:
    """`station.scan`'s rule: non-dot directories holding a manifest.json, sorted."""
    root = Path(station_root)
    if not root.is_dir():
        return []
    return [e for e in sorted(root.iterdir(), key=lambda p: p.name)
            if e.is_dir() and not e.name.startswith(".") and (e / MANIFEST).exists()]


def _parse(raw: bytes) -> dict | str:
    """The manifest dict, or a refusal reason."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        return "manifest.json is not valid JSON"
    if not isinstance(data, dict):
        return "manifest.json is not a JSON object"
    return data


def plan_retitle(station_root: Path, config: EmceeConfig) -> RetitlePlan:
    """Classify every package under `station_root`. Reads only."""
    plan = RetitlePlan()
    for pkg in _packages(station_root):
        slug = pkg.name
        try:
            raw = (pkg / MANIFEST).read_bytes()
        except OSError as exc:
            plan.refused.append((slug, f"cannot read manifest.json ({exc.strerror or exc})"))
            continue
        data = _parse(raw)
        if isinstance(data, str):
            plan.refused.append((slug, data))
            continue
        version = data.get("schema_version", 0)
        if (not isinstance(version, int) or isinstance(version, bool)
                or version < MIN_SUPPORTED_SCHEMA_VERSION):
            plan.refused.append((slug, f"unsupported (v{version}; re-deliver from llama)"))
            continue
        dj_audio = data.get("dj_audio")
        if dj_audio is None:
            plan.unvoiced += 1
            continue
        if not isinstance(dj_audio, dict):
            plan.refused.append((slug, "dj_audio is not an object"))
            continue
        if raw != encode(data):
            plan.refused.append((slug, NOT_ENCODED))
            continue
        if awaiting_fix_reason(data) is not None:
            plan.awaiting.append(slug)
            continue
        target = assignment_for(config, manifest_voiced_profile(data)).title
        current = dj_audio.get("title")
        if current == target:
            plan.unchanged += 1
            continue
        plan.writes.append(TitleWrite(slug=slug, dir=pkg, raw=raw, old=current, new=target))
    return plan


def _canon(value: object) -> str:
    # Compare JSON values by their encoding: Python's `==` takes 1 == 1.0 == True.
    return json.dumps(value, sort_keys=True)


def _unchanged_except_title(before: dict, after: dict, title: str | None) -> bool:
    """`after` is `before` with only `dj_audio["title"]` set to `title`."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    if list(before) != list(after):
        return False
    if any(_canon(before[k]) != _canon(after[k]) for k in before if k != "dj_audio"):
        return False
    b, a = before.get("dj_audio"), after.get("dj_audio")
    if not isinstance(b, dict) or not isinstance(a, dict) or "title" not in a:
        return False
    if _canon(a["title"]) != _canon(title):
        return False
    rest_b = {k: v for k, v in b.items() if k != "title"}
    rest_a = {k: v for k, v in a.items() if k != "title"}
    return list(rest_b) == list(rest_a) and _canon(rest_b) == _canon(rest_a)


class _BeforeRename(Exception):
    """An OSError in `_swap` before its rename: the target was not touched."""


class _AfterRename(Exception):
    """An OSError in `_swap` after its rename: the target holds the payload,
    its mtime possibly not restored."""


def _swap(path: Path, payload: bytes, st: os.stat_result, *, current: bytes) -> bool:
    """Replace `path` with `payload`, keeping `st`'s times and permission bits,
    only if it still holds `current` immediately before the rename. False
    (nothing written, no temp left) when it does not, or when it is gone.

    Order: unique temp in the same directory ("xb"), fchmod to the original's
    mode, write, flush, fsync, close; `os.utime` on the closed temp; re-read and
    compare; `os.replace`; re-apply the times once if the rename moved the
    mtime. An OSError is raised as `_BeforeRename` or `_AfterRename`."""
    tmp = path.parent / f".{path.name}.emcee-{secrets.token_hex(8)}.tmp"
    times = (st.st_atime_ns, st.st_mtime_ns)
    try:
        f = open(tmp, "xb")
    except OSError as exc:
        raise _BeforeRename(exc) from exc      # not ours: never unlink it
    try:
        with f:
            os.fchmod(f.fileno(), stat.S_IMODE(st.st_mode))
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.utime(tmp, ns=times)
        try:
            unchanged = path.read_bytes() == current
        except FileNotFoundError:
            unchanged = False
        if not unchanged:
            tmp.unlink()
            return False
        os.replace(tmp, path)
    except BaseException as exc:
        tmp.unlink(missing_ok=True)
        if isinstance(exc, OSError):
            raise _BeforeRename(exc) from exc
        raise
    try:
        if os.stat(path).st_mtime_ns != st.st_mtime_ns:
            os.utime(path, ns=times)
    except OSError as exc:
        raise _AfterRename(exc) from exc
    return True


def write_title(pkg_dir: Path, *, expect: bytes, title: str | None) -> bytes | None:
    """Set `dj_audio["title"]` in `pkg_dir/manifest.json`, whose bytes the caller
    planned from as `expect`. Returns the bytes written, or None when the file no
    longer held `expect`, or was gone, before the rename (nothing written).
    Raises `TitleWriteFailed` on any OSError (the message says what the file
    holds: unchanged, this write's bytes, or unknown) and when the post-rename
    check fails, after putting the original back if the file still holds
    exactly this write's bytes.

    `expect` must be in emcee's encoding with `dj_audio` an object (the plan's
    rules); anything else is a caller bug (ValueError, nothing written)."""
    pkg_dir = Path(pkg_dir)
    slug = pkg_dir.name
    path = pkg_dir / MANIFEST
    before = _parse(expect)
    if (isinstance(before, str) or not isinstance(before.get("dj_audio"), dict)
            or encode(before) != expect):
        raise ValueError(f"{slug}: expect is not a voiced manifest in emcee's encoding")
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise TitleWriteFailed(f"{slug}: cannot stat manifest.json ({exc}); "
                               "the file is unchanged") from exc
    data = json.loads(expect)
    data["dj_audio"]["title"] = title
    new = encode(data)
    try:
        if not _swap(path, new, st, current=expect):
            return None
    except _BeforeRename as exc:
        raise TitleWriteFailed(f"{slug}: the title write failed before its rename "
                               f"({exc.__cause__}); the file is unchanged") from exc
    except _AfterRename as exc:
        raise TitleWriteFailed(f"{slug}: restoring the mtime after the title write "
                               f"failed ({exc.__cause__}); manifest.json holds this "
                               "write's bytes, its mtime unknown") from exc

    try:
        after_raw = path.read_bytes()
    except FileNotFoundError:
        raise TitleWriteFailed(f"{slug}: manifest.json is gone after the write; "
                               "left as the other writer wrote it") from None
    except OSError as exc:
        raise TitleWriteFailed(f"{slug}: cannot re-read manifest.json after the title "
                               f"write ({exc}); what it holds is unknown") from exc
    after = _parse(after_raw)
    if (after_raw == new and not isinstance(after, str)
            and _unchanged_except_title(before, after, title)):
        return new
    if after_raw == new:
        try:
            put_back = _swap(path, expect, st, current=new)
        except _BeforeRename as exc:
            raise TitleWriteFailed(f"{slug}: manifest.json did not verify after the title "
                                   f"write, and putting the original back failed "
                                   f"({exc.__cause__}); it holds this write's bytes") from exc
        except _AfterRename as exc:
            raise TitleWriteFailed(f"{slug}: manifest.json did not verify after the title "
                                   "write; the original was put back, but restoring its "
                                   f"mtime failed ({exc.__cause__})") from exc
        if put_back:
            raise TitleWriteFailed(f"{slug}: manifest.json did not verify after the "
                                   "title write; the original was put back")
    raise TitleWriteFailed(f"{slug}: manifest.json changed after the title write; "
                           "left as the other writer wrote it")
