"""Shared test helpers.

This directory is the package `tests_transmitter`, not `tests`: llama's test
modules are top-level (`test_config`, `helpers`, …) and emcee's are the
`tests` package, so either name would collide in the repo-wide pytest run.
Import helpers as `from tests_transmitter.helpers import …`.
"""

import io
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from botocore.exceptions import ClientError

from transmitter import adts
from transmitter import grid as _grid
from transmitter.analysis import FileAnalysis, ShowAnalysis
from transmitter.config import TransmitterConfig
from transmitter.errors import RenderError
from transmitter.pipeline import Station
from transmitter.render import planned_frames
from transmitter.workspace import Epoch, Workspace

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


def stereo_sine(seconds: float, freq: float, amp: float, phase: float = 0.0,
                rate: int = 44_100) -> np.ndarray:
    n = round(seconds * rate)
    t = np.arange(n, dtype=np.float64)
    mono = amp * np.sin(phase + 2 * np.pi * freq * t / rate)
    return np.repeat(mono.astype(np.float32)[:, None], 2, axis=1)


def write_mp3(path: Path, pcm: np.ndarray, rate: int = 44_100) -> None:
    """Encode float32 PCM (n, channels) to MP3 with libmp3lame, which writes
    the Xing/LAME header carrying encoder delay and padding (the gapless info
    archive.org derivatives carry)."""
    channels = 1 if pcm.ndim == 1 else pcm.shape[1]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "f32le", "-ar", str(rate),
         "-ac", str(channels), "-i", "pipe:0", "-c:a", "libmp3lame", "-b:a", "192k", str(path)],
        input=np.ascontiguousarray(pcm, dtype=np.float32).tobytes(), check=True,
    )


def fake_frame(key: str, i: int) -> bytes:
    """A valid ADTS frame whose payload names its show and index."""
    return adts.build_frame(f"{key}:{i}".encode())


def write_fake_show(path: Path, key: str, n_frames: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(fake_frame(key, i) for i in range(n_frames)))


def payloads(frames: list[bytes]) -> list[str]:
    return [f[7:].decode() for f in frames]


# An epoch on a whole second (2096-10-02). Test packages carry real-clock
# mtimes while the quiet-period check runs at the simulated NOW, so E must sit
# far enough in the future that NOW stays after every package's mtime for the
# life of the suite (1_800_000_000 s, 2027-01-15, would expire within months).
E = 4_000_000_000 * 1_000_000
NOW = E + 1_000 * _grid.D_US


class FakeEngine:
    """An Engine without ffmpeg: a show's "encode" is fake ADTS frames whose
    payload is '<key>:<i>', so segment contents can be read back."""

    def __init__(self, samples_per_file: int = 60 * 44_100, extra: int = 1,
                 fail: set[str] | None = None, drift: int = 0, pause_seconds: float = 0.75):
        self.samples_per_file = samples_per_file
        self.extra = extra
        self.fail = fail or set()
        self.drift = drift
        self.pause_samples = _grid.samples_for_seconds(pause_seconds)
        self.encoded: list[str] = []
        self.analyzed: list[str] = []

    def analyze(self, show):
        # Computes like production's analyze, but never writes the analysis
        # cache: tests that publish prove the timeline does not depend on it.
        self.analyzed.append(show.slug)
        files = tuple(FileAnalysis(e.path, e.kind, e.title, self.samples_per_file) for e in show.entries)
        return ShowAnalysis(key=show.key, slug=show.slug, files=files, tracks_i_lufs=-20.0,
                            tracks_tp_dbfs=-3.0, meta=dict(show.meta))

    def extra_frames(self):
        return self.extra

    def silent_frame(self):
        return fake_frame("silence", 0)

    def encode_show(self, show, analysis, out_path):
        if show.slug in self.fail:
            raise RenderError(f"{show.slug}: simulated decode failure")
        frames = planned_frames(analysis, self.pause_samples, self.extra) + self.drift
        write_fake_show(out_path, show.key, frames)
        self.encoded.append(show.slug)
        return frames


def make_station(tmp_path: Path, n_packages: int = 3, engine=None) -> tuple[Station, list[str]]:
    root = make_root(tmp_path)
    for i in range(n_packages):
        build_package(root, f"band-2005-11-{i + 1:02d}")
    cfg = TransmitterConfig(root=tmp_path / "tx",
                            station={"root": root, "quiet_minutes": 0},
                            planner={"start_delay_minutes": 0.5},
                            render={"lead_hours": 0.1, "low_water_hours": 0.05})
    logs: list[str] = []
    st = Station(ws=Workspace(cfg.root), cfg=cfg, epoch=Epoch("etest", E),
                 engine=engine or FakeEngine(), log=logs.append)
    return st, logs


class FakeBucket:
    """An in-memory R2 bucket speaking the boto3 S3 calls transmitter uses.
    Any other call (list_objects*, delete_objects, …) fails the test."""

    def __init__(self):
        self.objects: dict[str, dict] = {}
        self.log: list[tuple[str, str]] = []
        self.fail_puts: dict[str, int] = {}
        self.fail_gets: set[str] = set()

    def put_object(self, *, Bucket, Key, Body, ContentType, CacheControl):
        self.log.append(("put", Key))
        if self.fail_puts.get(Key, 0) > 0:
            self.fail_puts[Key] -= 1
            raise ClientError({"Error": {"Code": "InternalError", "Message": "boom"}}, "PutObject")
        self.objects[Key] = {"Body": bytes(Body), "ContentType": ContentType, "CacheControl": CacheControl}
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_object(self, *, Bucket, Key):
        self.log.append(("get", Key))
        if Key in self.fail_gets:
            raise ClientError({"Error": {"Code": "InternalError", "Message": "boom"}}, "GetObject")
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key]["Body"])}

    def delete_object(self, *, Bucket, Key):
        self.log.append(("delete", Key))
        self.objects.pop(Key, None)
        return {"ResponseMetadata": {"HTTPStatusCode": 204}}

    def __getattr__(self, name):
        raise AssertionError(f"unexpected S3 call: {name}")

    def json(self, key):
        return json.loads(self.objects[key]["Body"])

    def puts(self):
        return [k for op, k in self.log if op == "put"]


def write_seg(ws, epoch_id: str, n: int) -> None:
    from transmitter import segment as _segment

    path = ws.seg_dir(epoch_id) / f"{n}.aac"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_segment.assemble(n, [fake_frame("seg", n)] * 441))


FALLBACK_VERSION = "fb0123456789"
TEMPLATE_PATH = Path(__file__).resolve().parents[3] / "antenna" / "templates" / "show.html"


def make_publisher(tmp_path: Path, bucket: "FakeBucket", *, batch: int = 360, budget: int = 17_500,
                   sleep=None, rows=None, run_start_n: int = 100, prune_min: int = 1,
                   station_root: Path | None = None, fallback_version: str | None = FALLBACK_VERSION):
    """A Publisher over a workspace holding one planned show (key "k1"),
    starting a run at segment `run_start_n`. Its analyses are served from
    memory by `analysis_for` (none is cached on disk); `p.analyses` holds them.
    A fallback version is recorded locally (as `transmitter fallback render`
    does) unless `fallback_version` is None: publishing refuses without one."""
    from transmitter import planner, publish
    from transmitter.layout import PlanRow
    from transmitter.state import save_fallback_version

    cfg = TransmitterConfig(root=tmp_path / "tx", station={"root": station_root},
                            publish={"bucket": "b", "batch_segments": batch, "daily_put_budget": budget,
                                     "prune_min_segments": prune_min})
    ws = Workspace(cfg.root)
    if fallback_version is not None:
        save_fallback_version(ws, fallback_version)
    epoch = Epoch("etest", E)
    rows = rows or [PlanRow(seq=0, slug="band-1", dir="band-1", key="k1",
                            start_frame=run_start_n * 441, frames=441 * 50, run_start=True)]
    planner.write_plan(ws.plan_path, rows)
    files = (FileAnalysis("audio/01.mp3", "track", "Song 1", 441 * 1024 * 40),)
    meta = {"artist": "Band", "date": "2005-11-01", "venue": "Club", "city": "Lincoln, NE",
            "profile": "indie", "url": "https://archive.org/details/band1", "lineage": "AUD"}
    analyses = {r.key: ShowAnalysis(r.key, r.slug, files, -18.0, -2.0, meta) for r in rows}
    sleeps = []
    uploader = publish.Uploader(bucket, "b", publish.PutBudget(ws.puts_path, budget, today=lambda: "2027-01-15"),
                                sleep=sleep or sleeps.append)
    p = publish.Publisher(ws=ws, cfg=cfg, epoch=epoch, uploader=uploader,
                          template=TEMPLATE_PATH.read_text(),
                          analysis_for=lambda row: analyses.get(row.key), log=lambda m: None)
    p.sleeps = sleeps
    p.analyses = analyses
    return p


LIBRARY_DURATIONS = Path(__file__).parent / "fixtures" / "library_durations.json"


def show_piece(slug: str, *, artist: str | None = None, date: str | None = None,
               profile: str | None = None, frames: int = 441_000, exact: bool = True):
    """A scheduler show `Piece` with no files behind it."""
    from transmitter.pieces import Piece
    from transmitter.station import Show
    meta = {"artist": artist, "date": date, "voiced_profile": profile}
    return Piece("show", Show(slug, Path(slug), (), f"k-{slug}", meta), slug, frames, exact)


def library_pieces() -> list:
    """The fixture library (`fixtures/make_library_durations.py`) as show pieces."""
    rows = json.loads(LIBRARY_DURATIONS.read_text())
    return [show_piece(r["slug"], artist=r["artist"], date=r["date"], profile=r["profile"],
                       frames=r["frames"]) for r in rows]
