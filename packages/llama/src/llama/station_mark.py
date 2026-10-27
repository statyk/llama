"""The station mark: `awaiting_fix` in a delivered package's `manifest.json`
(bulk-apply spec, "The `awaiting_fix` contract").

A strict surface: it writes station manifests that emcee, which takes no lock,
may be rewriting at the same moment. Every write is a read-modify-write on the
raw JSON dict (never llama's `Manifest` model, which gains no field), touching
only `MARK_KEY`, so `tracks`, `dj_notes`, `dj_audio` are untouched by
construction. The caller holds the llama show lock.

The rewrite (Review Focus 1): read the bytes and dict; build the new bytes; write
a unique temp in the same directory and flush it; re-read the station file's
bytes just before the rename and refuse (temp removed, nothing written) when
they changed; rename; re-read and require every other key equal to what was read
and `MARK_KEY` equal to what was written. On a mismatch after the rename, the
bytes read go back only when the file still holds this call's own bytes (never
over another writer's), and the call refuses. **Limitation:** a write landing
between the last byte check and the rename is overwritten undetected; the
caller's `emcee_running()` check before each write is the primary guard.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable
from uuid import uuid4

from llama import campaign_gate, catalog
from llama.errors import LlamaError

MARK_KEY = "awaiting_fix"
MANIFEST = "manifest.json"
COMPARED = ("source.identifier", "show.venue", "show.city", "show.date", "tracks.filename",
            "tracks.duration_sec", "tracks.title", "tracks.set", "tracks.segue", "set_breaks")

_ABSENT = object()


class StationRefused(LlamaError):
    """A station write that did not happen (or was put back): retryable."""


class StationUnreadable(StationRefused):
    """The ONE "station copy unreadable" exception: `<slug>: station copy
    unreadable: <detail>`. A station copy llama cannot read is never written."""


def _unreadable(out: Path, detail: str) -> StationUnreadable:
    return StationUnreadable(f"{out.name}: station copy unreadable: {' '.join(detail.split())}")


def _read_bytes(out: Path) -> bytes:
    mf = out / MANIFEST
    try:
        return mf.read_bytes()
    except FileNotFoundError as exc:
        detail = f"no {MANIFEST} in {out}" if out.is_dir() else f"no directory {out}"
        raise _unreadable(out, detail) from exc
    except OSError as exc:
        raise _unreadable(out, f"cannot read {mf} ({exc})") from exc


def _read(out: Path) -> tuple[bytes, dict]:
    raw = _read_bytes(out)
    try:
        data = json.loads(raw)
    except ValueError as exc:           # includes UnicodeDecodeError
        raise _unreadable(out, f"invalid JSON in {out / MANIFEST} ({exc})") from exc
    if not isinstance(data, dict):
        raise _unreadable(out, f"{out / MANIFEST} is not a JSON object "
                               f"({type(data).__name__})")
    return raw, data


def read_station_manifest(out: Path) -> tuple[bytes, dict]:
    """`out/manifest.json`'s bytes and dict. StationUnreadable when `out` or the
    file is missing, on any OSError, on invalid JSON, or when it is not an object."""
    return _read(out)


def mark_of(manifest: dict) -> dict | None:
    """The mark, or None when `awaiting_fix` is absent or null. Any other value is
    a mark (the contract); a non-object one comes back as `{}`, so test the result
    with `is not None`, never truthiness."""
    value = manifest.get(MARK_KEY)
    if value is None:
        return None
    return value if isinstance(value, dict) else {}


def destination_voiced(out: Path) -> bool:
    """`dj_audio` non-null. For delivered shows only: a missing dir or manifest is
    StationUnreadable here, never "unvoiced"."""
    _, data = _read(out)
    return data.get("dj_audio") is not None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _encode(data: dict, *, newline: bool) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + ("\n" if newline else "")).encode()


def _others(data: dict) -> dict:
    return {k: v for k, v in data.items() if k != MARK_KEY}


def _swap_in(out: Path, data: bytes, *, expect: bytes) -> None:
    """Unique temp in `out`, flushed; refuse (temp removed, nothing written) when
    the station file no longer holds `expect`; then rename over it."""
    mf = out / MANIFEST
    tmp = out / f".{MANIFEST}.llama-{uuid4().hex}.tmp"
    try:
        with open(tmp, "xb") as f:
            f.write(data)
        catalog._flush_to_disk(tmp)
        if _read_bytes(out) != expect:
            raise StationRefused(f"{out.name}: the station copy changed while llama was "
                                 "rewriting it; nothing written (retry)")
        os.replace(tmp, mf)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def _rewrite(out: Path, change: Callable[[dict], dict], *,
             want: object) -> tuple[bytes, bytes]:
    """Read, apply `change` (which adds or removes only MARK_KEY), swap in, verify.
    `want` is MARK_KEY's expected value afterwards (`_ABSENT`: no key)."""
    before, data = _read(out)
    after = _encode(change(data), newline=before.endswith(b"\n"))
    _swap_in(out, after, expect=before)
    try:
        _, got = _read(out)
        ok = (_others(got) == _others(data)
              and got.get(MARK_KEY, _ABSENT) == want)
    except StationUnreadable:
        ok = False
    if not ok:
        try:
            put_back(out, expect_sha256=_sha(after), data=before)
            what = "what llama read was put back"
        except StationRefused:
            what = "it was left as the other writer wrote it"
        raise StationRefused(f"{out.name}: the station copy changed while llama was "
                             f"rewriting it; {what} (retry)")
    return before, after


def write_mark(out: Path, *, reason: str, marked_at: str) -> tuple[bytes, bytes]:
    """Add (or replace in place) `awaiting_fix`; returns the (before, after) bytes."""
    mark = {"reason": reason, "marked_at": marked_at}

    def change(data: dict) -> dict:
        new = dict(data)             # an existing key keeps its position
        new[MARK_KEY] = mark
        return new

    return _rewrite(out, change, want=mark)


def clear_mark(out: Path) -> tuple[bytes, bytes]:
    """Remove `awaiting_fix`; returns the (before, after) bytes. An unmarked copy
    (absent or null) is refused, untouched."""
    _, data = _read(out)
    if mark_of(data) is None:
        raise StationRefused(f"{out.name}: the station copy is not marked; nothing to clear")

    def change(d: dict) -> dict:
        if mark_of(d) is None:       # cleared by someone else since the check
            raise StationRefused(f"{out.name}: the station copy is not marked; "
                                 "nothing to clear")
        return _others(d)

    return _rewrite(out, change, want=_ABSENT)


def put_back(out: Path, *, expect_sha256: str, data: bytes) -> None:
    """The reversal: replace `out/manifest.json` with `data` only while its sha256
    equals `expect_sha256` (checked first, and again just before the rename)."""
    current = _read_bytes(out)
    if _sha(current) != expect_sha256:
        raise StationRefused(f"{out.name}: the station copy changed since it was "
                             "written; not put back")
    _swap_in(out, data, expect=current)
    if _read_bytes(out) != data:
        raise StationRefused(f"{out.name}: the station copy changed while llama was "
                             "putting it back (retry)")


def _canon(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _value(manifest: dict, name: str):
    head, _, field = name.partition(".")
    value = manifest.get(head)
    if not field:
        return value
    if head == "tracks":
        if not isinstance(value, list):
            return ["not a list", value]
        return [t.get(field) if isinstance(t, dict) else ["not an object", t]
                for t in value]
    if value is None:
        return None
    return value.get(field) if isinstance(value, dict) else ["not an object", value]


def manifest_differences(library: dict, station: dict) -> list[str]:
    """The COMPARED names whose raw JSON values differ, in COMPARED order. Absent
    and null read the same; numbers compare by their JSON text (600 != 600.0)."""
    return [name for name in COMPARED
            if _canon(_value(library, name)) != _canon(_value(station, name))]


def emcee_running() -> list[str]:
    """The ps lines of running `emcee` processes (the caller and its ancestors
    never match). The check cannot see scripts that import emcee."""
    return campaign_gate.tool_processes(campaign_gate.ps_lines(), "emcee",
                                        self_pid=os.getpid())
