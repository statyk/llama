"""Re-use audio llama already has when a show is re-packaged (spec 5.4).

Re-packaging a show whose track list changed would otherwise download audio
llama already holds: the library's own `package/audio/` (carrying the OLD
track numbers) or the station's delivered copy (the library's was purged at
delivery). md5 and size cannot verify such a file, because `build_package`
renames and re-tags every file, so a copy is paired with its source file by
index against the current `show.json`, and each paired file is checked by its
decoded length against the source's cached metadata length.

`plan_reuse` reads both manifests BEFORE the re-gather rewrites `show.json`.
`build_package(reuse=...)` then moves the old library audio aside into
`<show>/.audio-aside/` (never leaving an old-numbered file where a renumbered
track sharing its title would inherit it), copies a paired file to its new
packaged name, and downloads whatever is left. The per-show unit puts the
aside back under its old names on failure and deletes it on success.

Anything unpaired or failing a check downloads from archive.org exactly as
before; the worst case of a bad reuse is re-shipping audio this show already
packaged.

**Strict** (bulk-apply spec, "Audio reuse never silently falls back"): a
delivered show's re-package (not a re-selection) plans with `strict=True`.
Then `build_package` refuses (`StationUnpaired`, or the station mark's
`StationUnreadable`) instead of downloading when no copy pairs, when the station
copy is unreadable or missing, or when a source paired at plan time has no
metadata length or its copy fails the length check; only a source no copy ever
held downloads.

**The held-outcome anchor** (`reuse-anchor.json`): the pre-commit `show.json`
track list, written once before a packaged or delivered show is re-processed and
removed only by a package build. When `show.json` itself pairs nothing (a held
commit moved its titles), the station copy pairs through the anchor, and the
library's own `package/audio/` files under the anchor's packaged names do too.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from datetime import datetime, timezone

from llama.audio import packaged_filename, read_duration
from llama.errors import LlamaError
from llama.models import Show
from llama.station_mark import StationUnreadable, read_station_manifest
from llama.workspace import ShowWorkspace, atomic_write_bytes, read_model

ASIDE_DIR = ".audio-aside"     # <show>/.audio-aside/: outside package/, skipped by show_unit
ANCHOR = "reuse-anchor.json"   # <show>/reuse-anchor.json (`ShowWorkspace.reuse_anchor`)


class StationUnpaired(LlamaError):
    """`<slug>: station copy does not pair: <detail>`: a strict re-package that
    would have downloaded audio the station copy holds. Nothing is downloaded."""


def unpaired(show_ws: ShowWorkspace, detail: str) -> StationUnpaired:
    return StationUnpaired(f"{show_ws.dir.name}: station copy does not pair: {detail}")


@dataclass(frozen=True)
class ReusePlan:
    library_names: tuple[str, ...] | None  # the library package/manifest.json's packaged names, in
                                           # order, read at plan time; None when missing or unreadable
    library: dict[str, str]                # source filename -> packaged name (library manifest paired)
    station: dict[str, Path]               # source filename -> <station>/audio/<packaged name>
    identifier: str | None = None          # the plan-time show.identifier; None without a show.json
    strict: bool = False                   # a delivered show's re-package: never download a paired source
    station_problem: str | None = None     # strict only: why the station copy cannot be read


def _manifest_tracks(path: Path) -> list[tuple[str, str]] | None:
    """`(title, packaged filename)` per manifest track, in order; None when the
    manifest is missing or unreadable in any way (a malformed track included).
    A packaged filename that is not a bare name is unreadable too."""
    try:
        tracks = json.loads(path.read_text())["tracks"]
        out = [(t["title"], t["filename"]) for t in tracks]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    for title, name in out:
        if not (isinstance(title, str) and isinstance(name, str)) \
                or name in ("", ".", "..") or Path(name).name != name:
            return None
    return out


def _manifest_identifier(path: Path) -> str | None:
    """The archive.org item the manifest was packaged from (`source.identifier`);
    None when missing or unreadable, which pairs nothing (the safe direction)."""
    try:
        ident = json.loads(path.read_text())["source"]["identifier"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return ident if isinstance(ident, str) and ident else None


def _pair(show: Show | None, tracks: list[tuple[str, str]] | None) -> dict[str, str]:
    """Source filename -> packaged name, pairing by index: the copy must have
    exactly show.json's length and the same title at every index, else it
    contributes nothing."""
    if show is None or tracks is None or len(tracks) != len(show.tracks):
        return {}
    if any(t.title != title for t, (title, _name) in zip(show.tracks, tracks)):
        return {}
    return {t.filename: name for t, (_title, name) in zip(show.tracks, tracks)}


def _read_anchor(show_ws: ShowWorkspace) -> tuple[str, list[tuple[str, str]]] | None:
    """`(identifier, [(source filename, title), ...])` from the anchor; None when
    it is missing or unreadable in any way, which pairs nothing."""
    try:
        data = json.loads(show_ws.reuse_anchor.read_text())
        ident = data["identifier"]
        tracks = [(t["filename"], t["title"]) for t in data["tracks"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not (isinstance(ident, str) and ident) or not all(
            isinstance(f, str) and f and isinstance(t, str) for f, t in tracks):
        return None
    return ident, tracks


def _pair_anchor(anchor: list[tuple[str, str]],
                 tracks: list[tuple[str, str]] | None) -> dict[str, str]:
    """`_pair`'s rule (same length, same title at every index) against the
    anchor's track list instead of show.json's."""
    if tracks is None or len(tracks) != len(anchor):
        return {}
    if any(a_title != title for (_f, a_title), (title, _n) in zip(anchor, tracks)):
        return {}
    return {f: name for (f, _t), (_title, name) in zip(anchor, tracks)}


def plan_reuse(show_ws: ShowWorkspace, station_dir: Path | None, *,
               strict: bool = False) -> ReusePlan:
    """Pair the library and station copies with the CURRENT show.json. Without
    a readable show.json both pairings are {} (library_names is still read, so
    the aside rule in `build_package` still runs).

    When show.json pairs nothing, the anchor is tried, only when its identifier
    equals show.json's (the item being packaged): the station copy pairs with
    the anchor's list when the station manifest's `source.identifier` is that
    item too; the library pairs each anchor track i with
    `packaged_filename(i, title, suffix)` when that file is in `package/audio/`.

    `strict` records in `station_problem` why the station copy cannot be read
    (no `delivery_path`, a missing directory or manifest, an unreadable one);
    `check_pairs` refuses on it."""
    try:
        show = read_model(show_ws.show, Show)
    except Exception:
        show = None
    anchor = _read_anchor(show_ws)
    # A manifest pairs only when it was packaged from the SAME archive.org item as
    # show.json now names: file names repeat across items, the audio does not.
    def same_item(manifest: Path) -> bool:
        return show is not None and _manifest_identifier(manifest) == show.identifier
    lib_manifest = show_ws.package_dir / "manifest.json"
    library_tracks = _manifest_tracks(lib_manifest)
    library_names = tuple(name for _t, name in library_tracks) if library_tracks is not None else None
    library = _pair(show, library_tracks if same_item(lib_manifest) else None)
    # The anchor speaks only for the item show.json names now: after a held
    # re-selection it lists the OLD item's files, whose audio must not ship.
    if anchor is not None and (show is None or anchor[0] != show.identifier):
        anchor = None
    if not library and anchor is not None:
        audio = show_ws.package_dir / "audio"
        for i, (source, title) in enumerate(anchor[1], 1):
            name = packaged_filename(i, title, Path(source).suffix)
            if (audio / name).is_file():
                library[source] = name
    station: dict[str, Path] = {}
    problem: str | None = None
    if station_dir is None:
        if strict:
            problem = "no delivery_path in config"
    else:
        if strict:
            try:
                read_station_manifest(station_dir)
            except StationUnreadable as exc:
                problem = exc.detail or str(exc)
        st_manifest = station_dir / "manifest.json"
        st_tracks = _manifest_tracks(st_manifest)
        paired = _pair(show, st_tracks if same_item(st_manifest) else None)
        if not paired and anchor is not None and _manifest_identifier(st_manifest) == anchor[0]:
            paired = _pair_anchor(anchor[1], st_tracks)
        station = {src: station_dir / "audio" / name for src, name in paired.items()}
    return ReusePlan(library_names=library_names, library=library, station=station,
                     identifier=show.identifier if show is not None else None,
                     strict=strict, station_problem=problem)


def check_pairs(plan: ReusePlan, show_ws: ShowWorkspace) -> None:
    """Strict only (a no-op otherwise): refuse a station copy that cannot be read
    (`StationUnreadable`), and refuse when nothing pairs: the station pairing is
    empty and no library pairing names a file in `package/audio/`."""
    if not plan.strict:
        return
    if plan.station_problem is not None:
        exc = StationUnreadable(
            f"{show_ws.dir.name}: station copy unreadable: {plan.station_problem}")
        exc.detail = plan.station_problem
        raise exc
    audio = show_ws.package_dir / "audio"
    if not plan.station and not any((audio / name).is_file() for name in plan.library.values()):
        raise unpaired(show_ws, "no copy pairs")


def write_anchor_if_absent(show_ws: ShowWorkspace) -> bool:
    """Write the anchor from the current show.json unless one exists (the first
    one is the list the existing copies were packaged from, so it is never
    replaced). False when an anchor exists or there is no readable show.json."""
    if show_ws.reuse_anchor.exists():
        return False
    try:
        show = read_model(show_ws.show, Show)
    except Exception:
        return False
    data = {"identifier": show.identifier,
            "tracks": [{"filename": t.filename, "title": t.title} for t in show.tracks],
            "written_at": datetime.now(timezone.utc).isoformat()}
    atomic_write_bytes(show_ws.reuse_anchor, json.dumps(data, indent=2).encode())
    return True


def drop_anchor(show_ws: ShowWorkspace) -> None:
    show_ws.reuse_anchor.unlink(missing_ok=True)


def _aside(show_ws: ShowWorkspace) -> Path:
    return show_ws.dir / ASIDE_DIR


def set_aside(show_ws: ShowWorkspace) -> None:
    """Move every file in `package/audio/` into ASIDE_DIR (same filesystem,
    `os.replace`), keeping its name. The aside is single-use: an existing one
    holds the audio a put-back must restore (a second re-packaging in the same
    unit, or a leftover nobody deleted), so this refuses, moving nothing,
    rather than overwrite it."""
    aside = _aside(show_ws)
    if aside.exists():
        raise LlamaError(f"{show_ws.dir.name}: an audio aside already exists at {aside}; "
                         "re-packaging twice in one unit is not supported")
    audio = show_ws.package_dir / "audio"
    if not audio.is_dir():
        return
    aside.mkdir(parents=True)
    for p in sorted(audio.iterdir()):
        if p.is_file():
            os.replace(p, aside / p.name)


def reuse_into(dest: Path, source: str, expected_sec: float | None, plan: ReusePlan,
               show_ws: ShowWorkspace, *, tolerance: float) -> str | None:
    """Place a verified existing copy of `source` at `dest`: the aside library
    file first, then the station file. A copy is used only when it exists, its
    decoded length is readable and `expected_sec` (the source's cached metadata
    length) is known, and the two are within `tolerance`. Copies (never moves:
    the aside must survive for a put-back); returns "library", "station" or
    None when nothing was placed."""
    if expected_sec is None:
        return None
    candidates: list[tuple[str, Path]] = []
    if source in plan.library:
        candidates.append(("library", _aside(show_ws) / plan.library[source]))
    if source in plan.station:
        candidates.append(("station", plan.station[source]))
    for label, path in candidates:
        if not path.is_file():
            continue
        real = read_duration(path)
        if real is None or abs(real - expected_sec) > tolerance:
            continue
        tmp = dest.with_name(f".{dest.name}.reuse.tmp")
        try:
            shutil.copyfile(path, tmp)
            os.replace(tmp, dest)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return label
    return None


def put_back(show_ws: ShowWorkspace) -> None:
    """Return every aside file to `package/audio/` under its old name
    (replacing whatever a failed package stage left there), then remove the
    aside directory."""
    aside = _aside(show_ws)
    if not aside.is_dir():
        return
    audio = show_ws.package_dir / "audio"
    audio.mkdir(parents=True, exist_ok=True)
    for p in sorted(aside.iterdir()):
        if p.is_file():
            os.replace(p, audio / p.name)
    shutil.rmtree(aside, ignore_errors=True)


def discard_aside(show_ws: ShowWorkspace) -> None:
    shutil.rmtree(_aside(show_ws), ignore_errors=True)
