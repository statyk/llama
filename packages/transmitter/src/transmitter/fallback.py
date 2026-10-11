"""The fallback loop and the off-air notice (spec "R2 object contract",
"The clock"): `fallback/<version>/<k>.aac` (a short station-ID loop whose
segment k carries timestamp k*d, played as segment N mod len on the grid),
`notice.aac` (one segment) and `index.json` ({len, notice, d}). Rendered once
by `transmitter fallback render`; immutable, never pruned; the version is a
content hash, so re-rendering identical audio is a no-op key-wise."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from transmitter import aacenc, adts, grid, segment
from transmitter.analysis import gain_db
from transmitter.audio import LoudnessMeter, iter_decode
from transmitter.errors import EncodeError, PublishError
from transmitter.grid import CHANNELS, FRAME_SAMPLES, SEGMENT_FRAMES
from transmitter.publish import (AAC_TYPE, HORIZON_KEY, IMMUTABLE, STATE_CACHE, Publisher,
                                 check_epoch, guard_blocks_publishing, horizon_doc, publish_lock, put_json)
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
    for f in frames:                      # whole frames of the station format, every one
        adts.require_station_format(adts.parse_header(f))
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


def upload_fallback(p: Publisher, build: FallbackBuild, now_us: int) -> bool:
    """Upload the fallback objects (segments, notice, then index.json last) and
    record the version locally. Returns True if state/horizon.json was rewritten
    with the new version, False if it was deferred (no horizon yet, or the
    high-water rule) -- the next publish batch then carries the version."""
    v = build.version
    with publish_lock(p.ws):
        if guard_blocks_publishing(p.uploader, p.ws, now_us / 1e6, p.cfg.publish.guard_check_minutes * 60):
            raise PublishError("the cost guard is tripped (state/guard.json); not uploading")
        state = load_publish_state(p.ws)
        check_epoch(state, p.epoch)           # before ANY upload, like the other horizon writers
        for k, data in enumerate(build.segments):
            p.uploader.put(f"fallback/{v}/{k}.aac", data, AAC_TYPE, IMMUTABLE)
        p.uploader.put(f"fallback/{v}/notice.aac", build.notice, AAC_TYPE, IMMUTABLE)
        put_json(p.uploader, f"fallback/{v}/index.json", build.index(), IMMUTABLE)   # last: names the rest
        save_fallback_version(p.ws, v)
        if state.first is None or state.last is None:
            return False
        if state.high_water is not None and state.high_water > state.last:
            # R2's horizon may already list up to the high-water mark; rewriting
            # it at `last` would move it backwards. The next publish batch
            # carries the recorded version instead.
            p.log("horizon not rewritten: high-water mark is above last; next publish batch carries "
                  "the new fallback version")
            return False
        put_json(p.uploader, HORIZON_KEY, horizon_doc(p.epoch, state.first, state.last, now_us, v),
                 STATE_CACHE)
        return True
