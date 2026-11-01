#!/usr/bin/env python3
"""One-off: date already-voiced packages with `dj_audio.voiced_on` /
`voiced_before`.

For each package with a non-null `dj_audio` and neither key set (a null counts
as unset), take the newest mtime of the clips the block names (never the
manifest's: 198 manifests were touched later than their clips).

- Newest clip inside the NAS-copy window (below): `voiced_before:
  "2026-10-10"` and no `voiced_on` -- the copy stamped the clips, so the date
  says only that the voicing predates the copy.
- Otherwise `voiced_on: <local YYYY-MM-DD of that mtime>`.
- A clip the block names is missing: the package is left alone and printed.

Writes are a raw-JSON read-modify-write that adds one key to `dj_audio` and
nothing else (a legacy block is never round-tripped through a model; a manifest
whose bytes are not what `json.dumps(indent=2)` reproduces is skipped rather
than reformatted). The manifest's previous mtime is restored with `os.utime`:
transmitter treats a newer manifest mtime as "changing" for its quiet period,
so a plain rewrite would make every voiced show briefly ineligible. Per
package: stat the manifest, read it, build the new bytes, re-read the bytes
immediately before replacing (skip with a printed line on any change), write
with `atomic_write_bytes(..., fsync=True)`, then `os.utime`. ACCEPTED LIMIT:
the instant between the replace and the utime, and a writer landing between
the re-read and the replace, are not guarded.

Under `--apply` it refuses while an `emcee` or `llama` process runs (checked
before each write). Known limit: a sleeping sweep loop is invisible to that
check. Idempotent. Dry run by default; it prints counts per outcome and per
presenter.

Run this before any re-voice. Before the first `--apply`, the operator checks
on the mount that `os.utime` preserves mtime on one scratch file over SMB,
read back from hugo.
"""
import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter
from pathlib import Path

from emcee.config import load_config
from emcee.workspace import atomic_write_bytes
from llama.campaign_gate import ps_lines, tool_processes

# The NAS copy restamped clips and music in one pass: measured 118 packages
# inside this 11-minute-plus window (210 outside), clips and music stamped in
# the same second. Inclusive at both ends.
WINDOW_START = dt.datetime(2026, 10, 10, 19, 28, 0, tzinfo=dt.timezone(dt.timedelta(hours=-4)))
WINDOW_END = dt.datetime(2026, 10, 10, 19, 40, 0, tzinfo=dt.timezone(dt.timedelta(hours=-4)))
WINDOW_DATE = "2026-10-10"
SELF_SCRIPT = "backfill_voiced_on.py"


def running_tools() -> list[str]:
    lines = ps_lines()
    out: list[str] = []
    for tool in ("emcee", "llama"):
        out.extend(tool_processes(lines, tool, self_pid=os.getpid(), self_script=SELF_SCRIPT))
    return out


def _before_replace() -> None:
    """Seam for tests: runs after the new bytes are built, before the re-read."""


def clip_names(block: dict) -> list[str]:
    names: list[str] = []
    intros = block.get("set_intros")
    if isinstance(intros, dict):
        names.extend(v for v in intros.values() if isinstance(v, str))
    if isinstance(block.get("outro"), str):
        names.append(block["outro"])
    return names


def classify(pkg_dir: Path, block: dict) -> tuple[str, str] | str:
    """(key, date) to write, or a skip reason string."""
    names = clip_names(block)
    if not names:
        return "block names no clips"
    newest = 0.0
    for n in names:
        try:
            newest = max(newest, (pkg_dir / n).stat().st_mtime)
        except OSError:
            return f"clip missing ({n})"
    when = dt.datetime.fromtimestamp(newest, tz=dt.timezone.utc)
    if WINDOW_START <= when <= WINDOW_END:
        return ("voiced_before", WINDOW_DATE)
    return ("voiced_on", dt.datetime.fromtimestamp(newest).date().isoformat())


def apply_one(mp: Path, key: str, value: str) -> str | None:
    """Write one key; returns a skip reason or None when written."""
    st = mp.stat()
    old = mp.read_bytes()
    try:
        data = json.loads(old)
    except ValueError as exc:
        return f"unreadable: {exc}"
    canon = json.dumps(data, indent=2)
    if old not in ((canon + "\n").encode(), canon.encode()):
        return "formatting is not json.dumps(indent=2); not rewriting"
    data["dj_audio"][key] = value
    new = json.dumps(data, indent=2) + ("\n" if old.endswith(b"\n") else "")
    _before_replace()
    if mp.read_bytes() != old:
        return "manifest changed since read; skipped"
    atomic_write_bytes(mp, new.encode(), fsync=True)
    os.utime(mp, ns=(st.st_atime_ns, st.st_mtime_ns))
    return None


def backfill(station_root: Path, apply: bool) -> int:
    counts: Counter = Counter()
    by_presenter: Counter = Counter()
    for d in sorted(station_root.iterdir()):
        mp = d / "manifest.json"
        if not d.is_dir() or d.name.startswith(".") or not mp.exists():
            continue
        try:
            manifest = json.loads(mp.read_text())
        except (OSError, ValueError) as exc:
            print(f"skip {d.name}: {exc}")
            counts["skipped"] += 1
            continue
        block = manifest.get("dj_audio") if isinstance(manifest, dict) else None
        if not isinstance(block, dict) or block.get("voiced_on") or block.get("voiced_before"):
            continue
        verdict = classify(d, block)
        if isinstance(verdict, str):
            print(f"{d.name}: {verdict}; left alone")
            counts["skipped"] += 1
            continue
        key, value = verdict
        print(f"{d.name}: {key} {value}")
        if apply:
            found = running_tools()
            if found:
                print("refusing to write while emcee/llama runs:", *found, sep="\n  ")
                return 1
            why = apply_one(mp, key, value)
            if why:
                print(f"skip {d.name}: {why}")
                counts["skipped"] += 1
                continue
        counts[key] += 1
        by_presenter[block.get("presenter") or "?"] += 1
    print("outcomes: " + ", ".join(f"{k}: {counts[k]}" for k in ("voiced_before", "voiced_on", "skipped")))
    for name, n in sorted(by_presenter.items()):
        print(f"presenter {name}: {n}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--station-root", type=Path, default=None)
    ap.add_argument("--apply", action="store_true", help="write the manifests")
    args = ap.parse_args(argv)
    root = args.station_root or load_config().station.root
    if root is None:
        print("no station root: pass --station-root or set [station] root", file=sys.stderr)
        return 2
    rc = backfill(Path(root), args.apply)
    if not args.apply:
        print("dry run: pass --apply to write")
    return rc


if __name__ == "__main__":
    sys.exit(main())
