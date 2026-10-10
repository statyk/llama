"""Shared test helpers.

This directory is the package `tests_transmitter`, not `tests`: llama's test
modules are top-level (`test_config`, `helpers`, …) and emcee's are the
`tests` package, so either name would collide in the repo-wide pytest run.
Import helpers as `from tests_transmitter.helpers import …`.
"""

import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path  # noqa: F401  (later tasks annotate helpers with Path)

import numpy as np
import pytest

HAVE_FFMPEG = shutil.which("ffmpeg") is not None
requires_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not on PATH")


def decode_adts(data: bytes) -> np.ndarray:
    """Decode an ADTS byte stream to float32 (n, 2) with ffmpeg. The decoder
    does NOT trim encoder priming from raw ADTS, so sample 0 of the result is
    the first sample of the priming frame."""
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-f", "aac", "-i", "pipe:0",
         "-f", "f32le", "-ac", "2", "-ar", "44100", "pipe:1"],
        input=data, capture_output=True, check=True,
    ).stdout
    return np.frombuffer(out, dtype="<f4").reshape(-1, 2)


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
