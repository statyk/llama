"""Per-show verdict cache (`<show>/audio-check.json`) and the Checker.

Reading the cache is pure JSON: this module imports no numpy and does not import
`classify` at module level, so `identity` and `lookup` never load the runtime.
`Checker.check` imports `classify` only when it has to compute a verdict.

Cache file schema::

    {"entries": [
        {"identifier": str, "filename": str, "md5": str,      # or "size": str | int | None
         "verdict": "music" | "junk", "run_sec": int, "frac": float,
         "version": str, "checked_at": str (ISO 8601 UTC)},
        ...
    ]}

An entry's identity is its `identifier`, `filename` and exactly one of `md5` / `size`
(see `identity`). Failures are never stored: only `music` / `junk` verdicts.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from llama import workspace
from llama.audio_check import rule
from llama.errors import LlamaError

if TYPE_CHECKING:
    from llama.audio_check.classify import Result

_VERDICTS = ("music", "junk")
_IDENTITY_KEYS = ("identifier", "filename", "md5", "size")


class CacheUnreadable(LlamaError):
    """The verdict cache exists but cannot be used.

    Raised for invalid JSON, and for a wrong shape: the top level is not an object,
    its `entries` is missing or not a list, or any entry is not an object carrying a
    string `identifier`/`filename`, an `md5` or `size` key, a `verdict` of `music` or
    `junk`, an integer `run_sec`, a numeric `frac`, and string `version`/`checked_at`.
    Invalid encoding (not UTF-8) counts as invalid JSON.
    """


class CacheReadError(CacheUnreadable):
    """The verdict cache exists but could not be READ (an OSError other than a missing
    file: permission, a transient disk or SMB error). Its content may be fine, so
    `write_verdicts` refuses to overwrite it; `lookup` and `Checker` treat it like any
    other unreadable cache."""


@dataclass(frozen=True)
class Outcome:
    check: Literal["music", "junk", "unchecked"]
    run_sec: int | None
    frac: float | None
    error: str | None = None
    stale: bool = False


@dataclass(frozen=True)
class CachedVerdict:
    verdict: str
    run_sec: int
    frac: float
    version: str
    checked_at: str


def _file_entry(metadata: dict, filename: str) -> dict | None:
    files = metadata.get("files") if isinstance(metadata, dict) else None
    if not isinstance(files, list):
        return None
    for f in files:
        if isinstance(f, dict) and f.get("name") == filename:
            return f
    return None


def identity(identifier: str, filename: str, metadata: dict) -> dict:
    """The source file's identity: identifier, filename and the archive.org md5 from
    `metadata["files"]`; with no md5 there, the listed `size` (None when the file is
    not listed or has no size)."""
    f = _file_entry(metadata, filename) or {}
    md5 = f.get("md5")
    if md5:
        return {"identifier": identifier, "filename": filename, "md5": md5}
    return {"identifier": identifier, "filename": filename, "size": f.get("size")}


def _id_key(entry: dict) -> tuple:
    return tuple((k, entry[k]) for k in _IDENTITY_KEYS if k in entry)


def _valid_entry(e: object) -> bool:
    if not isinstance(e, dict):
        return False
    if not isinstance(e.get("identifier"), str) or not isinstance(e.get("filename"), str):
        return False
    if ("md5" in e) == ("size" in e):
        return False
    if e.get("verdict") not in _VERDICTS:
        return False
    run_sec, frac = e.get("run_sec"), e.get("frac")
    if not isinstance(run_sec, int) or isinstance(run_sec, bool):
        return False
    if not isinstance(frac, (int, float)) or isinstance(frac, bool):
        return False
    return isinstance(e.get("version"), str) and isinstance(e.get("checked_at"), str)


def _read_entries(cache_path: Path) -> list[dict] | None:
    """The stored entries; None when the file does not exist. Raises CacheReadError
    when the file cannot be read, CacheUnreadable when its content is corrupt."""
    try:
        raw = Path(cache_path).read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CacheReadError(f"cannot read {cache_path}: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise CacheUnreadable(f"{cache_path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise CacheUnreadable(f"{cache_path} has the wrong shape (no entries list)")
    if not all(_valid_entry(e) for e in data["entries"]):
        raise CacheUnreadable(f"{cache_path} has a malformed entry")
    return data["entries"]


def _find(entries: list[dict], ident: dict) -> CachedVerdict | None:
    key = _id_key(ident)
    for e in entries:
        if _id_key(e) == key:
            return CachedVerdict(e["verdict"], e["run_sec"], float(e["frac"]), e["version"], e["checked_at"])
    return None


def lookup(cache_path: Path, identifier: str, filename: str, metadata: dict) -> CachedVerdict | None:
    """The cached verdict for this source file (any version), or None. A missing file
    is None; a corrupt one raises CacheUnreadable."""
    entries = _read_entries(cache_path)
    if entries is None:
        return None
    return _find(entries, identity(identifier, filename, metadata))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_verdicts(cache_path: Path, entries: "list[tuple[dict, Result]]", *, now: str | None = None) -> None:
    """Merge `entries` into the cache by identity (a new verdict replaces the stored
    one for the same identity) and write atomically. Nothing to write writes nothing.

    An existing file whose CONTENT is corrupt (invalid encoding, invalid JSON, wrong
    shape) is overwritten. An existing file that cannot be READ raises CacheReadError
    and nothing is written, so a transient read error never erases stored verdicts.
    The atomic write itself may raise OSError. The caller must hold the show lock
    (this is a read-modify-write)."""
    if not entries:
        return
    try:
        existing = _read_entries(cache_path) or []
    except CacheReadError:
        raise
    except CacheUnreadable:
        existing = []
    at = now or _now()
    merged: dict[tuple, dict] = {_id_key(e): e for e in existing}
    for ident, result in entries:
        row = {**ident, "verdict": result.verdict, "run_sec": int(result.run_sec),
               "frac": float(result.frac), "version": rule.VERSION, "checked_at": at}
        merged[_id_key(ident)] = row
    Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
    workspace.atomic_write_text(Path(cache_path), json.dumps({"entries": list(merged.values())}, indent=2) + "\n")


class Checker:
    """Obtains each dropped file's outcome. `ia=None` is cache-only (replay, reapply):
    nothing is fetched or classified. Online, a missing or stale verdict is computed
    by fetching the file to a temp dir, classifying it, and deleting it; the new
    verdicts accumulate in `new_verdicts` for the caller to write. `check` never
    raises for a per-file failure: it returns `unchecked` with the reason."""

    def __init__(self, cache_path: Path, metadata: dict, identifier: str, *, ia=None,
                 tmp_dir: Path | None = None):
        self.cache_path = Path(cache_path)
        self.metadata = metadata
        self.identifier = identifier
        self.ia = ia
        self.tmp_dir = tmp_dir
        self.new_verdicts: list[tuple[dict, Result]] = []
        self._entries: list[dict] | None = None
        self._unreadable = False
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            self._entries = _read_entries(self.cache_path) or []
        except CacheUnreadable:
            self._entries = []
            self._unreadable = True

    def check(self, filename: str) -> Outcome:
        self._load()
        ident = identity(self.identifier, filename, self.metadata)
        key = _id_key(ident)
        for new_ident, r in self.new_verdicts:
            if _id_key(new_ident) == key:
                return Outcome(r.verdict, r.run_sec, r.frac)
        stored = _find(self._entries or [], ident)
        if stored is not None and stored.version == rule.VERSION:
            return Outcome(stored.verdict, stored.run_sec, stored.frac)
        if self.ia is None:
            if stored is not None:
                return Outcome(stored.verdict, stored.run_sec, stored.frac, stale=True)
            if self._unreadable:
                return Outcome("unchecked", None, None, error="verdict cache unreadable")
            return Outcome("unchecked", None, None, error="no cached verdict")
        result, error = self._compute(filename, ident)
        if result is not None:
            self.new_verdicts.append((ident, result))
            return Outcome(result.verdict, result.run_sec, result.frac)
        if stored is not None:
            return Outcome(stored.verdict, stored.run_sec, stored.frac, stale=True,
                           error=f"stale verdict kept; recompute {error}")
        return Outcome("unchecked", None, None, error=error)

    def _compute(self, filename: str, ident: dict) -> "tuple[Result | None, str | None]":
        """Fetch and classify one file; (result, None) or (None, reason)."""
        work: Path | None = None
        try:
            try:
                if self.tmp_dir is not None:
                    Path(self.tmp_dir).mkdir(parents=True, exist_ok=True)
                work = Path(tempfile.mkdtemp(prefix="audio-check-", dir=self.tmp_dir))
            except Exception as exc:
                return None, f"fetch failed: cannot make a temp dir: {exc}"
            dest = work / Path(filename).name
            try:
                path = self.ia.download_file(self.identifier, filename, dest, md5=ident.get("md5"))
            except Exception as exc:  # any fetch failure is unchecked, never a raise
                return None, f"fetch failed: {exc}"
            try:
                from llama.audio_check import classify, decode, model
            except Exception as exc:
                return None, f"classifier unavailable: {exc}"
            try:
                return classify.classify_file(Path(path or dest)), None
            except decode.DecodeError as exc:
                return None, f"decode failed: {exc}"
            except model.ClassifierUnavailable as exc:
                return None, f"classifier unavailable: {exc}"
            except Exception as exc:
                return None, f"audio check failed: {type(exc).__name__}: {exc}"
        finally:
            if work is not None:
                shutil.rmtree(work, ignore_errors=True)
