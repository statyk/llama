"""The station root and package eligibility (spec "Station-root guard",
"Eligibility").

A package is eligible iff it passes emcee's four file-level readiness legs, reimplemented
on files alone (transmitter never imports emcee) -- manifest v3+ with non-null
dj_notes and dj-notes.md present; non-null dj_audio with every named clip on
disk; broadcast.m3u present; every manifest track's audio on disk -- plus every
broadcast.m3u entry exists inside the package, and the newest mtime among
manifest.json, broadcast.m3u and dj-audio/* (bar emcee's *.tmp files) is older
than the quiet period. The playable unit is broadcast.m3u, in order. A file
that vanishes between listing and stat (emcee or llama mid-write) makes the
package "changing" -- ineligible this scan, never an exception.

emcee has a fifth readiness leg, the profile check (a package voiced as a
profile other than the one emcee would voice it as now, after an `emcee
move` or an `[assign.artists]` rule, is "pending" there). It is deliberately
NOT mirrored here: transmitter cannot see emcee's rules or moves, and such a
package keeps airing its existing voicing until its re-voice clears the DJ
blocks (ineligible while it runs, eligible again when it lands).
"""

import errno
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

from transmitter.errors import StationRootError

MARKER = ".station-root"


@dataclass(frozen=True)
class Entry:
    path: str
    kind: Literal["clip", "track"]
    title: str


@dataclass(frozen=True)
class Show:
    slug: str
    dir: Path
    entries: tuple[Entry, ...]
    key: str
    meta: dict = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class Ineligible:
    slug: str
    reasons: tuple[str, ...]


def require_root(root: Path | None) -> Path:
    if root is None:
        raise StationRootError("set [station] root in transmitter's config.toml")
    root = Path(root)
    try:
        is_dir = root.is_dir()
        has_marker = is_dir and (root / MARKER).exists()
    except OSError as exc:
        raise StationRootError(f"station root {root} is unreadable: {exc}") from exc
    if not is_dir:
        raise StationRootError(f"station root {root} is missing (is the NFS share mounted?)")
    if not has_marker:
        raise StationRootError(
            f"station root {root} has no {MARKER} marker -- refusing to treat it as an empty "
            "library (on hugo a down NFS mount is an ordinary empty directory)")
    return root


def read_m3u(path: Path) -> list[str]:
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def _inside(pkg_dir: Path, rel: str) -> bool:
    p = Path(rel)
    if p.is_absolute():
        return False
    try:
        (pkg_dir / p).resolve().relative_to(pkg_dir.resolve())
    except ValueError:
        return False
    except RuntimeError as exc:      # symlink loop (3.11); 3.13+ raises OSError itself
        raise OSError(errno.ELOOP, f"symlink loop resolving {rel}: {exc}") from exc
    return True


def file_set_key_and_sizes(pkg_dir: Path, rels: Iterable[str]) -> tuple[str, dict[str, int]]:
    """The show key and each entry's size, from one stat per entry."""
    h = hashlib.sha256()
    sizes: dict[str, int] = {}
    for rel in rels:
        st = (pkg_dir / rel).stat()
        sizes[rel] = st.st_size
        h.update(json.dumps([rel, st.st_size, st.st_mtime_ns]).encode() + b"\n")
    return h.hexdigest()[:20], sizes


def file_set_key(pkg_dir: Path, rels: Iterable[str]) -> str:
    """The cache/plan key of a show: its broadcast.m3u paths + sizes + mtimes."""
    return file_set_key_and_sizes(pkg_dir, rels)[0]


def _clips(dj_audio: dict) -> dict[str, str]:
    """clip path -> on-air title."""
    out: dict[str, str] = {}
    intros = dj_audio.get("set_intros") or {}
    if isinstance(intros, dict):
        for set_key, path in intros.items():
            if isinstance(path, str) and path:
                out[path] = f"DJ intro (set {set_key})"
    outro = dj_audio.get("outro")
    if isinstance(outro, str) and outro:
        out[outro] = "DJ outro"
    return out


def evaluate(pkg_dir: Path, *, now_s: float, quiet_s: float) -> Show | Ineligible:
    """Never raises for a package that is changing under us: an OSError (ESTALE,
    EIO, EACCES, a vanished file or a symlink loop, which `_inside` converts to
    OSError) anywhere in the evaluation is `Ineligible("changing: ...")`."""
    try:
        return _evaluate(Path(pkg_dir), now_s=now_s, quiet_s=quiet_s)
    except OSError as exc:
        return Ineligible(Path(pkg_dir).name, (f"changing: {exc}",))


def _evaluate(pkg_dir: Path, *, now_s: float, quiet_s: float) -> Show | Ineligible:
    slug = pkg_dir.name
    try:
        manifest = json.loads((pkg_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return Ineligible(slug, (f"unreadable manifest.json: {exc}",))
    if not isinstance(manifest, dict):
        return Ineligible(slug, ("manifest.json is not an object",))
    version = manifest.get("schema_version")
    if not isinstance(version, int) or version < 3:
        return Ineligible(slug, (f"unsupported manifest (schema_version {version!r}; need >= 3)",))

    reasons: list[str] = []
    if manifest.get("dj_notes") is None or not (pkg_dir / "dj-notes.md").exists():
        reasons.append("no DJ script (dj_notes block + dj-notes.md required)")

    clips: dict[str, str] = {}
    dj_audio = manifest.get("dj_audio")
    if not isinstance(dj_audio, dict):
        reasons.append("no DJ audio (unvoiced)")
    else:
        clips = _clips(dj_audio)
        missing = sorted(c for c in clips if not (pkg_dir / c).exists())
        if missing:
            reasons.append(f"{len(missing)} DJ clip(s) missing: {', '.join(missing)}")

    tracks = manifest.get("tracks") or []
    titles: dict[str, str] = {}
    missing_tracks: list[str] = []
    for t in tracks:
        fn = t.get("filename") if isinstance(t, dict) else None
        if not isinstance(fn, str) or not fn:
            reasons.append("manifest track without a filename")
            continue
        titles[f"audio/{fn}"] = t.get("title") or fn
        if not (pkg_dir / "audio" / fn).exists():
            missing_tracks.append(fn)
    if missing_tracks:
        reasons.append(f"{len(missing_tracks)} of {len(tracks)} track file(s) missing: "
                       + ", ".join(sorted(missing_tracks)))

    m3u = pkg_dir / "broadcast.m3u"
    rels: list[str] = []
    if not m3u.exists():
        reasons.append("no broadcast.m3u")
    else:
        try:
            rels = read_m3u(m3u)
        except UnicodeDecodeError as exc:    # persistent corruption, not a race
            return Ineligible(slug, (f"unreadable broadcast.m3u: {exc}",))
        if not rels:
            reasons.append("broadcast.m3u lists nothing")
        for rel in rels:
            if not _inside(pkg_dir, rel):
                reasons.append(f"broadcast.m3u entry escapes the package: {rel}")
            elif not (pkg_dir / rel).is_file():
                reasons.append(f"broadcast.m3u entry missing: {rel}")

    watched = [p for p in (pkg_dir / "manifest.json", m3u) if p.exists()]
    dj_dir = pkg_dir / "dj-audio"
    try:
        if dj_dir.is_dir():
            watched += [p for p in dj_dir.iterdir() if not p.name.endswith(".tmp")]
        newest = max((p.stat().st_mtime for p in watched), default=0.0)
    except OSError as exc:
        return Ineligible(slug, (f"changing: {exc}",))
    if now_s - newest < quiet_s:
        reasons.append(f"changed {now_s - newest:.0f}s ago (quiet period {quiet_s:.0f}s)")

    if reasons:
        return Ineligible(slug, tuple(reasons))
    try:
        key, sizes = file_set_key_and_sizes(pkg_dir, rels)
    except OSError as exc:
        return Ineligible(slug, (f"changing: {exc}",))
    entries = tuple(
        Entry(rel, "clip", clips[rel]) if rel in clips
        else Entry(rel, "track", titles.get(rel, Path(rel).stem))
        for rel in rels
    )
    show_meta = manifest.get("show") or {}
    source = manifest.get("source") or {}
    meta = {k: show_meta.get(k) for k in ("artist", "date", "venue", "city")}
    meta.update(profile=source.get("profile"), url=source.get("url"), lineage=source.get("lineage"))
    total = manifest.get("total_duration_sec")
    dj_profile = (manifest.get("dj_audio") or {}).get("profile")
    meta.update(
        total_duration_sec=(float(total) if isinstance(total, (int, float)) and not isinstance(total, bool)
                            and math.isfinite(total) and total >= 0 else None),
        voiced_profile=dj_profile if isinstance(dj_profile, str) and dj_profile else source.get("profile"),
        sizes=sizes)
    return Show(slug, pkg_dir, entries, key, meta)


def scan(root: Path | None, *, now_s: float, quiet_s: float) -> tuple[list[Show], list[Ineligible]]:
    """Every non-dot subdirectory holding a manifest.json is a package (dot
    entries are llama's replace-swap siblings and AppleDouble files)."""
    root = require_root(root)
    shows: list[Show] = []
    skipped: list[Ineligible] = []
    try:
        entries = sorted(root.iterdir())
    except OSError as exc:
        raise StationRootError(f"station root {root} cannot be listed: {exc}") from exc
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if not entry.is_dir() or not (entry / "manifest.json").exists():
                continue
        except OSError as exc:
            skipped.append(Ineligible(entry.name, (f"changing: {exc}",)))
            continue
        result = evaluate(entry, now_s=now_s, quiet_s=quiet_s)
        (shows if isinstance(result, Show) else skipped).append(result)
    return shows, skipped
