### Task 5: Station root guard and eligibility

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/station.py`
- Create: `packages/transmitter/tests_transmitter/test_station.py`
- Modify: `packages/transmitter/tests_transmitter/helpers.py` (package fixture)

**Interfaces:**
- Consumes: `errors.StationRootError`.
- Produces:
  - `MARKER = ".station-root"`; `Entry(path: str, kind: "clip"|"track", title: str)`; `Show(slug, dir: Path, entries: tuple[Entry, ...], key: str, meta: dict)` where `meta` has `artist, date, venue, city, profile, url, lineage`; `Ineligible(slug, reasons: tuple[str, ...])`.
  - `require_root(root) -> Path`; `read_m3u(path) -> list[str]`; `file_set_key(pkg_dir, rels) -> str` (20 hex chars over paths + sizes + mtimes); `evaluate(pkg_dir, *, now_s, quiet_s) -> Show | Ineligible` (ignores `dj-audio/*.tmp`, emcee's temp files; an `OSError` while stat-ing or hashing — a file vanished mid-scan — is `Ineligible` with a `changing: …` reason, never a crash); `scan(root, *, now_s, quiet_s) -> tuple[list[Show], list[Ineligible]]`.
  - helpers: `make_root(tmp_path) -> Path`, `build_package(root, slug="band-2005-11-01", *, tracks=3, voiced=True, profile="indie", age_s=3600.0, audio=None) -> Path`, `set_age(pkg, age_s)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests_transmitter/helpers.py`:

```python
import json
import os
import time
from typing import Callable


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "station"
    root.mkdir(parents=True)
    (root / ".station-root").write_text("")
    return root


def set_age(pkg: Path, age_s: float) -> None:
    t = time.time() - age_s
    for p in [pkg, *pkg.rglob("*")]:
        os.utime(p, (t, t))


def build_package(root: Path, slug: str = "band-2005-11-01", *, tracks: int = 3,
                  voiced: bool = True, profile: str | None = "indie", age_s: float = 3600.0,
                  audio: Callable[[Path, int], None] | None = None) -> Path:
    """A v3 package shaped like a real delivered one (cracker-2005-11-01):
    broadcast.m3u = dj-audio/set1-intro.mp3, audio/NN - Song N.mp3 ...,
    dj-audio/99-outro.mp3. `audio(path, index)` writes each audio file
    (default: placeholder bytes -- eligibility never decodes); index 0 is the
    intro, 99 the outro. Every file's mtime is set `age_s` in the past."""
    pkg = root / slug
    (pkg / "audio").mkdir(parents=True)
    (pkg / "dj-audio").mkdir()
    write = audio or (lambda path, i: path.write_bytes(b"ID3fake" + bytes([i])))
    rows = [{"index": i, "set": "1", "title": f"Song {i}", "filename": f"{i:02d} - Song {i}.mp3",
             "duration_sec": 60.0, "segue": False} for i in range(1, tracks + 1)]
    manifest = {
        "schema_version": 3,
        "show": {"artist": "Band", "date": "2005-11-01", "venue": "Club", "city": "Lincoln, NE"},
        "source": {"performance_id": "Band/2005-11-01", "identifier": "band2005",
                   "url": "https://archive.org/details/band2005", "lineage": "AUD > CDR",
                   "profile": profile},
        "tracks": rows, "set_breaks": [],
        "briefing": {"file": "briefing.md", "json": "briefing.json", "narration": "full", "vetted": True},
        "dj_notes": None, "dj_audio": None,
    }
    m3u = ["#EXTM3U"]
    if voiced:
        manifest["dj_notes"] = {"set_intros": {"1": "Hello."}, "outro": "Bye."}
        manifest["dj_audio"] = {"set_intros": {"1": "dj-audio/set1-intro.mp3"},
                                "outro": "dj-audio/99-outro.mp3", "presenter": None}
        (pkg / "dj-notes.md").write_text("# notes\n")
        write(pkg / "dj-audio" / "set1-intro.mp3", 0)
        m3u.append("dj-audio/set1-intro.mp3")
    for i, r in enumerate(rows, 1):
        write(pkg / "audio" / r["filename"], i)
        m3u.append(f"audio/{r['filename']}")
    if voiced:
        write(pkg / "dj-audio" / "99-outro.mp3", 99)
        m3u.append("dj-audio/99-outro.mp3")
        (pkg / "broadcast.m3u").write_text("\n".join(m3u) + "\n")
    (pkg / "briefing.md").write_text("A fine show.\n\nSecond paragraph.\n")
    (pkg / "manifest.json").write_text(json.dumps(manifest, indent=2))
    set_age(pkg, age_s)
    return pkg
```

`tests_transmitter/test_station.py`:

```python
import json
import time
from pathlib import Path

import pytest

from tests_transmitter.helpers import build_package, make_root, set_age
from transmitter import station
from transmitter.errors import StationRootError
from transmitter.station import Entry, Ineligible, Show


def _eval(pkg, quiet_s=600.0):
    return station.evaluate(pkg, now_s=time.time(), quiet_s=quiet_s)


def test_ready_package_is_eligible(tmp_path):
    pkg = build_package(make_root(tmp_path))
    show = _eval(pkg)
    assert isinstance(show, Show)
    assert show.slug == "band-2005-11-01"
    assert show.entries[0] == Entry("dj-audio/set1-intro.mp3", "clip", "DJ intro (set 1)")
    assert show.entries[1] == Entry("audio/01 - Song 1.mp3", "track", "Song 1")
    assert show.entries[-1] == Entry("dj-audio/99-outro.mp3", "clip", "DJ outro")
    assert show.meta["artist"] == "Band" and show.meta["profile"] == "indie"
    assert len(show.key) == 20


def _break(pkg, how):
    m = json.loads((pkg / "manifest.json").read_text())
    if how == "unvoiced":
        m["dj_audio"] = None
    elif how == "no-notes-file":
        (pkg / "dj-notes.md").unlink()
    elif how == "clip-missing":
        (pkg / "dj-audio" / "99-outro.mp3").unlink()
    elif how == "no-m3u":
        (pkg / "broadcast.m3u").unlink()
    elif how == "track-missing":
        (pkg / "audio" / "02 - Song 2.mp3").unlink()
    elif how == "m3u-entry-missing":
        (pkg / "broadcast.m3u").write_text("audio/01 - Song 1.mp3\naudio/nope.mp3\n")
    elif how == "m3u-escapes":
        (pkg / "broadcast.m3u").write_text("../other/audio/01.mp3\n")
    elif how == "m3u-absolute":
        (pkg / "broadcast.m3u").write_text("/etc/passwd\n")
    elif how == "v2":
        m["schema_version"] = 2
    (pkg / "manifest.json").write_text(json.dumps(m))
    set_age(pkg, 3600)


@pytest.mark.parametrize("how,reason", [
    ("unvoiced", "no DJ audio"),
    ("no-notes-file", "no DJ script"),
    ("clip-missing", "DJ clip(s) missing"),
    ("no-m3u", "no broadcast.m3u"),
    ("track-missing", "track file(s) missing"),
    ("m3u-entry-missing", "entry missing: audio/nope.mp3"),
    ("m3u-escapes", "escapes the package"),
    ("m3u-absolute", "escapes the package"),
    ("v2", "unsupported manifest"),
])
def test_each_leg_makes_a_package_ineligible(tmp_path, how, reason):
    pkg = build_package(make_root(tmp_path))
    _break(pkg, how)
    result = _eval(pkg)
    assert isinstance(result, Ineligible)
    assert any(reason in r for r in result.reasons), result.reasons


def test_quiet_period(tmp_path):
    pkg = build_package(make_root(tmp_path), age_s=60)
    assert isinstance(_eval(pkg, quiet_s=600), Ineligible)
    assert isinstance(_eval(pkg, quiet_s=30), Show)


def test_key_tracks_the_file_set(tmp_path):
    pkg = build_package(make_root(tmp_path))
    k1 = _eval(pkg).key
    assert _eval(pkg).key == k1
    f = pkg / "audio" / "01 - Song 1.mp3"
    f.write_bytes(f.read_bytes() + b"x")
    set_age(pkg, 3600)
    assert _eval(pkg).key != k1


def test_emcee_temp_files_do_not_hold_the_quiet_period(tmp_path):
    pkg = build_package(make_root(tmp_path))
    (pkg / "dj-audio" / "99-outro.mp3.k2j3.tmp").write_bytes(b"partial")     # emcee's mkstemp name; mtime: now
    assert isinstance(_eval(pkg), Show)


def test_a_file_vanishing_mid_scan_is_changing_not_a_crash(tmp_path, monkeypatch):
    pkg = build_package(make_root(tmp_path))
    dj_dir = pkg / "dj-audio"
    real_iterdir = Path.iterdir

    def iterdir(self):                 # listed, then gone before evaluate stats it
        yield from real_iterdir(self)
        if self == dj_dir:
            yield dj_dir / "set2-intro.mp3"

    monkeypatch.setattr(Path, "iterdir", iterdir)
    result = _eval(pkg)
    assert isinstance(result, Ineligible)
    assert result.reasons[0].startswith("changing")


def test_scan_skips_dot_dirs_and_non_packages(tmp_path):
    root = make_root(tmp_path)
    build_package(root, "a-show")
    build_package(root, ".swap-a-show")
    (root / "not-a-package").mkdir()
    (root / "._junk").write_text("")
    shows, skipped = station.scan(root, now_s=time.time(), quiet_s=600)
    assert [s.slug for s in shows] == ["a-show"] and skipped == []


def test_empty_root_without_marker_is_refused(tmp_path):
    root = tmp_path / "nfs"
    root.mkdir()                      # what a down NFS mount looks like on hugo
    with pytest.raises(StationRootError, match="marker"):
        station.scan(root, now_s=time.time(), quiet_s=0)


def test_missing_or_unset_root_is_refused(tmp_path):
    with pytest.raises(StationRootError, match="missing"):
        station.require_root(tmp_path / "gone")
    with pytest.raises(StationRootError, match=r"\[station\] root"):
        station.require_root(None)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_station.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.station'`.

- [ ] **Step 3: Implement `station.py`**

```python
"""The station root and package eligibility (spec "Station-root guard",
"Eligibility").

A package is eligible iff it passes emcee's four readiness legs, reimplemented
on files alone (transmitter never imports emcee) -- manifest v3+ with non-null
dj_notes and dj-notes.md present; non-null dj_audio with every named clip on
disk; broadcast.m3u present; every manifest track's audio on disk -- plus every
broadcast.m3u entry exists inside the package, and the newest mtime among
manifest.json, broadcast.m3u and dj-audio/* (bar emcee's *.tmp files) is older
than the quiet period. The playable unit is broadcast.m3u, in order. A file
that vanishes between listing and stat (emcee or llama mid-write) makes the
package "changing" -- ineligible this scan, never an exception.
"""

import hashlib
import json
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
    if not root.is_dir():
        raise StationRootError(f"station root {root} is missing (is the NFS share mounted?)")
    if not (root / MARKER).exists():
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
    return True


def file_set_key(pkg_dir: Path, rels: Iterable[str]) -> str:
    """The cache/plan key of a show: its broadcast.m3u paths + sizes + mtimes."""
    h = hashlib.sha256()
    for rel in rels:
        st = (pkg_dir / rel).stat()
        h.update(json.dumps([rel, st.st_size, st.st_mtime_ns]).encode() + b"\n")
    return h.hexdigest()[:20]


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
    pkg_dir = Path(pkg_dir)
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
        rels = read_m3u(m3u)
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
        key = file_set_key(pkg_dir, rels)
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
    return Show(slug, pkg_dir, entries, key, meta)


def scan(root: Path | None, *, now_s: float, quiet_s: float) -> tuple[list[Show], list[Ineligible]]:
    """Every non-dot subdirectory holding a manifest.json is a package (dot
    entries are llama's replace-swap siblings and AppleDouble files)."""
    root = require_root(root)
    shows: list[Show] = []
    skipped: list[Ineligible] = []
    for entry in sorted(root.iterdir()):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        if not (entry / "manifest.json").exists():
            continue
        result = evaluate(entry, now_s=now_s, quiet_s=quiet_s)
        (shows if isinstance(result, Show) else skipped).append(result)
    return shows, skipped
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_station.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): station-root guard and package eligibility"
```

---

