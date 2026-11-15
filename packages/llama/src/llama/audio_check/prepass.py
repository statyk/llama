"""`llama audio-prepass`: fill each library show's verdict cache before the rollout's
replay arm (spec 2026-11-14-junk-drop-audio-check-design, "Replay and the rollout").

Replay and reapply are cache-only, so a drop with no cached verdict is `unchecked`
there. This pass classifies every candidate drop of every library show ahead of the
arm, so the cache-only runs find verdicts.

**Input** per show, deduplicated by source filename:
- every `show.json` track whose title is in the junk-title vocabulary, ignoring the
  position conditions (`is_a_title or is_intro_title or is_outro_title`);
- with `--arm`, every `junk_drops` filename of that show's arm row;
- with `--from-skips`, the files named by every `skipped: unchecked drop (<files>)`
  row of a reapply `progress.jsonl`. The names are matched against the show's own
  file names (show.json tracks and excluded rows, the reuse anchor), never split
  naively on `", "`, so a file name containing `", "` is still found.

**Audio:** the station copy when `audio_reuse.plan_reuse` pairs it (show.json, else
`reuse-anchor.json`) and its decoded length is within the tolerance `reuse_into` is
given (`stages.package.DURATION_TOLERANCE_S`) of the source's metadata length; else
the source is fetched from archive.org into a temp dir under `DIR`, deleted after.

**Writes:** only `<show>/audio-check.json` (via `cache.write_verdicts`, under the
library show lock) and `DIR/summary.json` (atomic, rewritten after every show so an
interrupted run leaves a valid file). Never the station lock, never the station tree.

**Resumable:** a file whose cache already holds a verdict of the current
`rule.VERSION` is not re-classified; it is listed with `cached: true` and its stored
verdict. Failures (fetch, decode, runtime, an unreadable cache) are listed `failed`
with their reason and never cached, so a re-run retries them.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from llama import audio_reuse, junk_titles
from llama.audio import read_duration
from llama.audio_check import cache, rule
from llama.errors import LlamaError
from llama.locks import file_lock
from llama.models import Show
from llama.util import length_seconds
from llama.workspace import ShowWorkspace, atomic_write_text, read_model

SUMMARY = "summary.json"
EXIT_UNAVAILABLE = 3
EXIT_BAD_INPUT = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _tolerance() -> float:
    # The tolerance `build_package` passes to `audio_reuse.reuse_into`: one constant.
    from llama.stages.package import DURATION_TOLERANCE_S
    return DURATION_TOLERANCE_S


def _overlaps(a: Path, b: Path) -> bool:
    a, b = a.resolve(), b.resolve()
    return a == b or a in b.parents or b in a.parents


def is_junk_title(title: str) -> bool:
    """Any rule A/B/C vocabulary match, ignoring the position conditions."""
    return (junk_titles.is_a_title(title) or junk_titles.is_intro_title(title)
            or junk_titles.is_outro_title(title))


# --- input sources ---------------------------------------------------------------

def read_arm(path: Path) -> dict[str, list[str]]:
    """slug -> the arm row's `junk_drops` filenames. Raises LlamaError when the arm
    cannot be read or has no `shows` rows."""
    try:
        doc = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise LlamaError(f"cannot read the arm {path}: {exc}") from exc
    rows = doc.get("shows") if isinstance(doc, dict) else None
    if not isinstance(rows, dict):
        raise LlamaError(f"the arm {path} has no `shows` rows")
    out: dict[str, list[str]] = {}
    for slug, row in rows.items():
        if not isinstance(row, dict):
            continue
        names = [d.get("filename") for d in (row.get("junk_drops") or []) if isinstance(d, dict)]
        names = [n for n in names if isinstance(n, str) and n]
        if names:
            out[slug] = names
    return out


def read_skips(path: Path) -> dict[str, list[str]]:
    """slug -> the raw parenthesised file lists of every `skipped: unchecked drop
    (...)` row of a reapply progress file (one JSON object per line; a line that does
    not parse is skipped, as `reapply.read_progress` does)."""
    from llama.reapply import UNCHECKED_DROP
    try:
        text = Path(path).read_text()
    except OSError as exc:
        raise LlamaError(f"cannot read the progress file {path}: {exc}") from exc
    prefix = UNCHECKED_DROP + " ("
    out: dict[str, list[str]] = {}
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or not isinstance(row.get("slug"), str):
            continue
        outcome = row.get("outcome")
        if isinstance(outcome, str) and outcome.startswith(prefix) and outcome.endswith(")"):
            out.setdefault(row["slug"], []).append(outcome[len(prefix):-1])
    return out


def split_names(inner: str, known: set[str]) -> list[str] | None:
    """`inner` (reapply's `", "`-joined file names) as the known file names it joins,
    in order; None when it is not exactly such a join. Matching against the show's
    own names keeps a name containing `", "` whole."""
    memo: dict[int, list[str] | None] = {}

    def at(pos: int) -> list[str] | None:
        if pos in memo:
            return memo[pos]
        found = None
        for name in sorted(known, key=len, reverse=True):
            if not inner.startswith(name, pos):
                continue
            end = pos + len(name)
            if end == len(inner):
                found = [name]
                break
            if inner.startswith(", ", end):
                rest = at(end + 2)
                if rest is not None:
                    found = [name, *rest]
                    break
        memo[pos] = found
        return found

    return at(0) if inner else None


def _known_names(ws: ShowWorkspace, show: Show) -> set[str]:
    names = {t.filename for t in show.tracks}
    names |= {r["filename"] for r in show.excluded_files
              if isinstance(r, dict) and isinstance(r.get("filename"), str)}
    try:
        anchor = json.loads(ws.reuse_anchor.read_text())
        names |= {t["filename"] for t in anchor["tracks"] if isinstance(t.get("filename"), str)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return names


# --- the run ---------------------------------------------------------------------

@dataclass
class Summary:
    path: Path
    started_at: str = field(default_factory=_now)
    finished_at: str | None = None
    files: list[dict] = field(default_factory=list)

    def write(self) -> None:
        doc = {"version": rule.VERSION, "started_at": self.started_at,
               "finished_at": self.finished_at, "files": self.files}
        atomic_write_text(self.path, json.dumps(doc, indent=1, ensure_ascii=False) + "\n")


def _row(slug, source, outcome, *, run_sec=None, frac=None, error=None, cached=False,
         audio=None) -> dict:
    return {"slug": slug, "source_file": source, "outcome": outcome, "run_sec": run_sec,
            "frac": frac, "error": error, "cached": cached, "audio": audio}


def _classify(path: Path) -> "tuple[object | None, str | None]":
    """(Result, None) or (None, reason). Never raises for a per-file failure."""
    from llama.audio_check import classify, decode, model
    try:
        return classify.classify_file(Path(path)), None
    except decode.DecodeError as exc:
        return None, f"decode failed: {exc}"
    except model.ClassifierUnavailable as exc:
        return None, f"classifier unavailable: {exc}"
    except Exception as exc:
        return None, f"audio check failed: {type(exc).__name__}: {exc}"


def _station_copy(source: str, plan, lengths: dict[str, float | None]) -> Path | None:
    """The paired station file, only when its decoded length matches the metadata."""
    path = plan.station.get(source)
    expected = lengths.get(source)
    if path is None or expected is None or not path.is_file():
        return None
    real = read_duration(path)
    if real is None or abs(real - expected) > _tolerance():
        return None
    return path


def _fetch_and_classify(ia, identifier: str, source: str, md5: str | None,
                        tmp_root: Path) -> "tuple[object | None, str | None]":
    work: Path | None = None
    try:
        try:
            tmp_root.mkdir(parents=True, exist_ok=True)
            work = Path(tempfile.mkdtemp(prefix="fetch-", dir=tmp_root))
        except Exception as exc:
            return None, f"fetch failed: cannot make a temp dir: {exc}"
        dest = work / Path(source).name
        try:
            got = ia.download_file(identifier, source, dest, md5=md5)
        except Exception as exc:
            return None, f"fetch failed: {exc}"
        return _classify(Path(got or dest))
    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)


def _one_show(ws: ShowWorkspace, slug: str, extra: list[str], raw_skips: list[str],
              ia, station_root: Path | None, tmp_root: Path) -> list[dict]:
    """The summary rows of one show; the caller holds the show lock."""
    try:
        show = read_model(ws.show, Show)
    except Exception as exc:
        names = list(dict.fromkeys(extra)) or ["(show)"]
        return [_row(slug, n, "failed", error=f"cannot read show.json: {exc}") for n in names]
    rows: list[dict] = []
    wanted = [t.filename for t in show.tracks if is_junk_title(t.title)]
    wanted += extra
    if raw_skips:
        known = _known_names(ws, show)
        for inner in raw_skips:
            names = split_names(inner, known)
            if names is None:
                rows.append(_row(slug, inner, "failed",
                                 error="skipped files do not match this show's file names"))
            else:
                wanted += names
    wanted = list(dict.fromkeys(wanted))
    if not wanted:
        return rows
    try:
        metadata = ia.metadata(show.identifier)
    except Exception as exc:
        return rows + [_row(slug, n, "failed", error=f"cannot read metadata: {exc}") for n in wanted]
    files = metadata.get("files") if isinstance(metadata, dict) else None
    files = [f for f in files if isinstance(f, dict)] if isinstance(files, list) else []
    lengths = {f.get("name"): length_seconds(f.get("length")) for f in files}
    try:
        entries = cache._read_entries(ws.audio_check) or []
    except cache.CacheReadError as exc:
        return rows + [_row(slug, n, "failed", error=f"verdict cache unreadable: {exc}")
                       for n in wanted]
    except cache.CacheUnreadable:
        entries = []                      # corrupt content: this pass rewrites it
    station_dir = station_root / slug if station_root is not None else None
    plan = audio_reuse.plan_reuse(ws, station_dir)
    new: list[tuple[dict, object, dict]] = []
    for source in wanted:
        ident = cache.identity(show.identifier, source, metadata)
        stored = cache._find(entries, ident)
        if stored is not None and stored.version == rule.VERSION:
            rows.append(_row(slug, source, stored.verdict, run_sec=stored.run_sec,
                             frac=stored.frac, cached=True))
            continue
        copy = _station_copy(source, plan, lengths)
        if copy is not None:
            result, error = _classify(copy)
            audio = "station"
        else:
            result, error = _fetch_and_classify(ia, show.identifier, source,
                                                ident.get("md5"), tmp_root)
            audio = "archive.org"
        if result is None:
            if stored is not None:
                error = f"{error} (stale verdict kept)"
            rows.append(_row(slug, source, "failed", error=error, audio=audio))
            continue
        row = _row(slug, source, result.verdict, run_sec=int(result.run_sec),
                   frac=float(result.frac), audio=audio)
        rows.append(row)
        new.append((ident, result, row))
    if new:
        try:
            cache.write_verdicts(ws.audio_check, [(i, r) for i, r, _ in new])
        except (cache.CacheReadError, OSError) as exc:
            for _i, _r, row in new:
                row.update(outcome="failed", run_sec=None, frac=None,
                           error=f"cannot write the verdict cache: {exc}")
    return rows


def run(root: Path, ia, out: Path, *, station_root: Path | None, arm: Path | None = None,
        from_skips: Path | None = None, slugs: list[str] | None = None,
        echo: Callable[[str], None] = print, err: Callable[[str], None] = print) -> int:
    """The whole pass; returns the exit code."""
    from llama.audio_check import classify, model
    for what, p in (("library root", root), ("station root", station_root)):
        if p is not None and _overlaps(Path(out), Path(p)):
            err(f"audio-prepass: refusing --out {out}: it overlaps the {what} {p}")
            return EXIT_BAD_INPUT
    try:
        arm_drops = read_arm(arm) if arm is not None else {}
        skips = read_skips(from_skips) if from_skips is not None else {}
    except LlamaError as exc:
        err(f"audio-prepass: {exc}")
        return EXIT_BAD_INPUT
    try:
        classify.get_model()
    except model.ClassifierUnavailable as exc:
        err(f"audio-prepass: classifier unavailable ({exc}); nothing written")
        return EXIT_UNAVAILABLE
    shows_dir = Path(root) / "shows"
    if slugs:
        order = list(dict.fromkeys(slugs))
    else:
        on_disk = sorted(p.name for p in shows_dir.iterdir()
                         if (p / "show.json").is_file()) if shows_dir.is_dir() else []
        order = list(dict.fromkeys([*on_disk, *sorted(arm_drops), *sorted(skips)]))
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    summary = Summary(out / SUMMARY)
    summary.write()
    tmp_root = out / ".fetch"
    try:
        for i, slug in enumerate(order, 1):
            ws = ShowWorkspace(shows_dir / slug)
            if not ws.dir.is_dir():
                names = list(dict.fromkeys(arm_drops.get(slug, []) + skips.get(slug, [])))
                rows = [_row(slug, n, "failed", error="no library show directory")
                        for n in names or ["(show)"]]
            else:
                with file_lock(ws.lock):
                    rows = _one_show(ws, slug, arm_drops.get(slug, []), skips.get(slug, []),
                                     ia, station_root, tmp_root)
            summary.files.extend(rows)
            summary.write()
            if rows:
                counts = _counts(rows)
                echo(f"[{i}/{len(order)}] {slug}: " + ", ".join(f"{k} {v}" for k, v in counts.items() if v))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    summary.finished_at = _now()
    summary.write()
    totals = _counts(summary.files)
    held = len({r["slug"] for r in summary.files if r["outcome"] == "music"})
    echo(f"audio-prepass: {len(summary.files)} file(s): music {totals['music']}, junk "
         f"{totals['junk']}, failed {totals['failed']} ({totals['cached']} already cached); "
         f"shows with a music verdict: {held}; summary {summary.path}")
    return 0


def _counts(rows: list[dict]) -> dict[str, int]:
    c = {"music": 0, "junk": 0, "failed": 0, "cached": 0}
    for r in rows:
        c[r["outcome"]] = c.get(r["outcome"], 0) + 1
        c["cached"] += bool(r.get("cached"))
    return c
