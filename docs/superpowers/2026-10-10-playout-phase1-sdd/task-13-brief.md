### Task 13: Fallback render and upload

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/fallback.py`
- Create: `packages/transmitter/tests_transmitter/test_fallback.py`

**Interfaces:**
- Consumes: `aacenc.encode_pcm`, `adts.split_frames`, `segment.assemble`, `audio.iter_decode/LoudnessMeter`, `analysis.gain_db`, `grid`, Task 11's `Publisher`, `publish_lock`, `guard_blocks_publishing`, `put_json`, `horizon_doc`, `AAC_TYPE/IMMUTABLE/HORIZON_KEY/STATE_CACHE`; `state.*`; `workspace.atomic_write_bytes/write_json`.
- Produces: `FallbackBuild(version: str, segments: tuple[bytes, ...], notice: bytes)` with `.index() -> {"len", "notice", "d"}`; `build_fallback(loop_path, notice_path, *, ffmpeg, music_target_lufs, speech_target_lufs, extra) -> FallbackBuild`; `write_local(ws, build) -> Path`; `upload_fallback(p, build, now_us) -> None` (segments, then notice, then `index.json` last; records the version locally; rewrites `state/horizon.json` with the new `fallback_version` when a horizon exists; refuses while the guard is tripped).

- [ ] **Step 1: Write the failing tests**

`tests_transmitter/test_fallback.py`:

```python
import pytest

from tests_transmitter.helpers import FakeBucket, make_publisher, requires_ffmpeg, stereo_sine, write_mp3
from transmitter import aacenc, adts, fallback, grid, segment
from transmitter.errors import PublishError
from transmitter.state import PublishState, load_fallback_version, save_publish_state
from transmitter.workspace import Workspace


def _build(tmp_path, notice=True):
    write_mp3(tmp_path / "loop.mp3", stereo_sine(25.0, 330.0, 0.2))
    notice_path = None
    if notice:
        write_mp3(tmp_path / "notice.mp3", stereo_sine(14.0, 500.0, 0.1))   # longer than d: truncated
        notice_path = tmp_path / "notice.mp3"
    return fallback.build_fallback(tmp_path / "loop.mp3", notice_path, ffmpeg="ffmpeg",
                                   music_target_lufs=-16.0, speech_target_lufs=-16.0,
                                   extra=aacenc.extra_frames())


@requires_ffmpeg
def test_loop_segments_are_whole_and_timestamped_k_d(tmp_path):
    b = _build(tmp_path)
    assert len(b.segments) == 3                       # ceil((1077 + extra) / 441)
    for k, data in enumerate(b.segments):
        ts, frames = segment.parse(data)
        assert ts == grid.segment_timestamp(k) and len(frames) == grid.SEGMENT_FRAMES
    ts, frames = segment.parse(b.notice)
    assert ts == 0 and len(frames) == grid.SEGMENT_FRAMES
    assert b.index() == {"len": 3, "notice": f"fallback/{b.version}/notice.aac", "d": 10.24}


@requires_ffmpeg
def test_version_is_content_addressed(tmp_path):
    assert _build(tmp_path).version == _build(tmp_path).version
    assert _build(tmp_path, notice=False).version != _build(tmp_path).version


@requires_ffmpeg
def test_write_local(tmp_path):
    b = _build(tmp_path)
    d = fallback.write_local(Workspace(tmp_path / "ws"), b)
    assert d == tmp_path / "ws" / "render" / "fallback" / b.version
    assert sorted(p.name for p in d.iterdir()) == ["0.aac", "1.aac", "2.aac", "index.json", "notice.aac"]


def _fake_build():
    seg = segment.assemble(0, [adts.build_frame(b"x")] * 441)
    return fallback.FallbackBuild("abc123def456", (seg, seg), seg)


def test_upload_order_and_horizon_refresh(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    save_publish_state(p.ws, PublishState(epoch_id="etest", first=100, last=200, runs=[[100, 200]]))
    fallback.upload_fallback(p, _fake_build(), p.epoch.start_us(150))
    assert bucket.puts() == ["fallback/abc123def456/0.aac", "fallback/abc123def456/1.aac",
                             "fallback/abc123def456/notice.aac", "fallback/abc123def456/index.json",
                             "state/horizon.json"]
    assert bucket.objects["fallback/abc123def456/index.json"]["CacheControl"] == "public, max-age=31536000, immutable"
    assert bucket.json("state/horizon.json")["fallback_version"] == "abc123def456"
    assert (bucket.json("state/horizon.json")["first"], bucket.json("state/horizon.json")["last"]) == (100, 200)
    assert load_fallback_version(p.ws) == "abc123def456"


def test_upload_without_a_horizon_only_records_the_version(tmp_path):
    bucket = FakeBucket()
    p = make_publisher(tmp_path, bucket)
    fallback.upload_fallback(p, _fake_build(), p.epoch.start_us(150))
    assert "state/horizon.json" not in bucket.objects
    assert load_fallback_version(p.ws) == "abc123def456"


def test_upload_refuses_while_the_guard_is_tripped(tmp_path):
    bucket = FakeBucket()
    bucket.objects["state/guard.json"] = {"Body": b'{"tripped": true}', "ContentType": "", "CacheControl": ""}
    p = make_publisher(tmp_path, bucket)
    with pytest.raises(PublishError, match="guard"):
        fallback.upload_fallback(p, _fake_build(), p.epoch.start_us(150))
    assert bucket.puts() == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_fallback.py -q`
Expected: FAIL — `ImportError: cannot import name 'fallback'`.

- [ ] **Step 3: Implement `fallback.py`**

```python
"""The fallback loop and the off-air notice (spec "R2 object contract",
"The clock"): `fallback/<version>/<k>.aac` (a short station-ID loop whose
segment k carries timestamp k·d, played as segment N mod len on the grid),
`notice.aac` (one segment) and `index.json` ({len, notice, d}). Rendered once
by `transmitter fallback render`; immutable, never pruned; the version is a
content hash, so re-rendering identical audio is a no-op key-wise."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from transmitter import aacenc, adts, grid, segment
from transmitter.analysis import gain_db
from transmitter.audio import LoudnessMeter, iter_decode
from transmitter.errors import EncodeError, PublishError
from transmitter.grid import CHANNELS, FRAME_SAMPLES, SEGMENT_FRAMES
from transmitter.publish import (AAC_TYPE, HORIZON_KEY, IMMUTABLE, STATE_CACHE, Publisher,
                                 guard_blocks_publishing, horizon_doc, publish_lock, put_json)
from transmitter.state import load_publish_state, save_fallback_version
from transmitter.workspace import Workspace, atomic_write_bytes, write_json


@dataclass(frozen=True)
class FallbackBuild:
    version: str
    segments: tuple[bytes, ...]
    notice: bytes

    def index(self) -> dict:
        return {"len": len(self.segments), "notice": f"fallback/{self.version}/notice.aac",
                "d": grid.D_US / 1_000_000}


def _decode_all(path: Path, ffmpeg: str) -> np.ndarray:
    chunks = list(iter_decode(path, ffmpeg))
    return np.concatenate(chunks) if chunks else np.zeros((0, CHANNELS), np.float32)


def _gained(pcm: np.ndarray, target: float, ffmpeg: str) -> np.ndarray:
    meter = LoudnessMeter(ffmpeg)
    meter.write(pcm)
    loud = meter.finish()
    gain = 10.0 ** (gain_db(target, loud.i_lufs, loud.tp_dbfs) / 20.0)
    return np.clip(pcm * gain, -1.0, 1.0).astype(np.float32)


def _fit(pcm: np.ndarray, samples: int) -> np.ndarray:
    """Truncate (with a 50 ms fade-out) or zero-pad to exactly `samples`."""
    if len(pcm) > samples:
        pcm = pcm[:samples].copy()
        fade = min(samples, grid.samples_for_seconds(0.05))
        if fade:
            pcm[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)[:, None]
        return pcm
    return np.concatenate([pcm, np.zeros((samples - len(pcm), CHANNELS), np.float32)])


def _encode_exact(pcm: np.ndarray, n_frames: int, extra: int, ffmpeg: str) -> list[bytes]:
    frames = adts.split_frames(aacenc.encode_pcm(_fit(pcm, (n_frames - extra) * FRAME_SAMPLES), ffmpeg))
    if len(frames) != n_frames:
        raise EncodeError(f"fallback encode produced {len(frames)} frames, expected {n_frames}")
    return frames


def build_fallback(loop_path: Path, notice_path: Path | None, *, ffmpeg: str,
                   music_target_lufs: float, speech_target_lufs: float, extra: int) -> FallbackBuild:
    loop = _decode_all(loop_path, ffmpeg)
    if len(loop) == 0:
        raise EncodeError(f"{loop_path} decoded to no audio")
    loop = _gained(loop, music_target_lufs, ffmpeg)
    n_segs = max(1, -(-(grid.frames_ceil(len(loop)) + extra) // SEGMENT_FRAMES))
    frames = _encode_exact(loop, n_segs * SEGMENT_FRAMES, extra, ffmpeg)
    segments = tuple(segment.assemble(k, frames[k * SEGMENT_FRAMES:(k + 1) * SEGMENT_FRAMES])
                     for k in range(n_segs))
    notice_pcm = (_gained(_decode_all(notice_path, ffmpeg), speech_target_lufs, ffmpeg)
                  if notice_path is not None else np.zeros((0, CHANNELS), np.float32))
    notice = segment.assemble(0, _encode_exact(notice_pcm, SEGMENT_FRAMES, extra, ffmpeg))
    h = hashlib.sha256()
    for s in segments:
        h.update(s)
    h.update(notice)
    return FallbackBuild(h.hexdigest()[:12], segments, notice)


def write_local(ws: Workspace, build: FallbackBuild) -> Path:
    d = ws.fallback_dir(build.version)
    for k, data in enumerate(build.segments):
        atomic_write_bytes(d / f"{k}.aac", data)
    atomic_write_bytes(d / "notice.aac", build.notice)
    write_json(d / "index.json", build.index())
    return d


def upload_fallback(p: Publisher, build: FallbackBuild, now_us: int) -> None:
    v = build.version
    with publish_lock(p.ws):
        if guard_blocks_publishing(p.uploader, p.ws, now_us / 1e6, p.cfg.publish.guard_check_minutes * 60):
            raise PublishError("the cost guard is tripped (state/guard.json); not uploading")
        for k, data in enumerate(build.segments):
            p.uploader.put(f"fallback/{v}/{k}.aac", data, AAC_TYPE, IMMUTABLE)
        p.uploader.put(f"fallback/{v}/notice.aac", build.notice, AAC_TYPE, IMMUTABLE)
        put_json(p.uploader, f"fallback/{v}/index.json", build.index(), IMMUTABLE)   # last: names the rest
        save_fallback_version(p.ws, v)
        state = load_publish_state(p.ws)
        if state.first is not None and state.last is not None:
            put_json(p.uploader, HORIZON_KEY, horizon_doc(p.epoch, state.first, state.last, now_us, v),
                     STATE_CACHE)
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_fallback.py -q`
Expected: PASS.

Run: `packages/transmitter/scripts/test-in-debian12.sh`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): fallback loop and off-air notice render + upload"
```

---

