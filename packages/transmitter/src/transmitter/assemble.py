"""Concert-break assembler: joins voiced pieces (`piece-<id>.mp3`, written by
emcee) into one lossless WAV clip that renders as an ordinary interstitial.

Pieces are joined with the settings' gaps, the house bed (when set) is mixed
under the whole clip, and the result is a one-clip `Show` named
`concert-<content hash>`. The content hash covers the pieces' file-set keys,
the gaps, the bed's key and gain and `ASSEMBLY_VERSION`, so identical content
reuses its file. A reused clip is left completely untouched (its own file-set
key hashes its mtime, and plan rows already carry that key). Loudness is not
normalised here: emcee levels the pieces and render normalises the whole clip.
"""

import hashlib
import io
import json
import os
import stat
import wave
from pathlib import Path

import numpy as np

from transmitter import analysis as analysis_mod
from transmitter.announce_config import AnnounceSettings
from transmitter.audio import iter_decode
from transmitter.concert import BreakContent
from transmitter.errors import AssemblyError, PieceUndecodable
from transmitter.grid import CHANNELS, SAMPLE_RATE
from transmitter.layout import CONCERT_ROLE
from transmitter.station import Entry, Show, file_set_key_and_sizes
from transmitter.workspace import atomic_write_bytes

ASSEMBLY_VERSION = 1
CLIP_PREFIX = "concert-"
BED_FADE_IN_S = 0.1


def _decode(path: Path, ffmpeg: str) -> np.ndarray:
    chunks = list(iter_decode(path, ffmpeg))
    if not chunks:
        raise ValueError(f"{path} decoded to no audio")
    return np.concatenate(chunks).astype(np.float32, copy=False)


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x.astype(np.float64))))) if len(x) else 0.0


class Assembler:
    def __init__(self, *, pieces: Path, out_dir: Path, settings: AnnounceSettings, ffmpeg: str = "ffmpeg"):
        self.pieces = Path(pieces)
        self.out_dir = Path(out_dir)
        self.settings = settings
        self.ffmpeg = ffmpeg
        self._decoded: dict[str, np.ndarray] = {}

    def _piece_name(self, pid: str) -> str:
        return f"piece-{pid}.mp3"

    def _piece_key(self, pid: str) -> str:
        try:
            return file_set_key_and_sizes(self.pieces, [self._piece_name(pid)])[0]
        except Exception as exc:
            raise PieceUndecodable(pid, f"piece {pid}: {exc}") from exc

    def _piece_pcm(self, pid: str, key: str) -> np.ndarray:
        got = self._decoded.get(key)
        if got is None:
            try:
                got = _decode(self.pieces / self._piece_name(pid), self.ffmpeg)
            except Exception as exc:
                raise PieceUndecodable(pid, f"piece {pid}: {exc}") from exc
            self._decoded[key] = got
        return got

    def _bed_key(self) -> str | None:
        bed = self.settings.bed
        if bed is None:
            return None
        try:
            return file_set_key_and_sizes(Path(bed).parent, [Path(bed).name])[0]
        except Exception as exc:
            raise AssemblyError(f"bed {bed} is unreadable: {exc}") from exc

    def _slug(self, piece_keys: list[str], bed_key: str | None) -> str:
        blob = json.dumps([piece_keys, self.settings.gaps.model_dump(), bed_key,
                           self.settings.bed_under_db, ASSEMBLY_VERSION])
        return CLIP_PREFIX + hashlib.sha256(blob.encode()).hexdigest()[:16]

    def _gap_s(self, index: int, content: BreakContent) -> float:
        g = self.settings.gaps
        if index == 0 and content.phrases[:1] == ("id",):
            return g.after_id
        text = content.pieces[index][1].rstrip()
        if text.endswith(","):
            return g.after_comma
        if text.endswith("."):
            return g.after_period
        return g.within

    def build(self, content: BreakContent) -> Show:
        if not content.pieces:
            raise AssemblyError("a break needs at least one piece")
        keys = [self._piece_key(pid) for pid, _ in content.pieces]
        bed_key = self._bed_key()
        slug = self._slug(keys, bed_key)
        name = f"{slug}.wav"
        path = self.out_dir / name
        if not path.exists():
            self._write(path, content, keys)
        try:
            key, sizes = file_set_key_and_sizes(self.out_dir, [name])
        except Exception as exc:
            raise AssemblyError(f"{path}: {exc}") from exc
        return Show(slug, self.out_dir, (Entry(name, "clip", "Announcement"),), key,
                    {"role": CONCERT_ROLE, "ann_id": None, "sizes": sizes})

    def _write(self, path: Path, content: BreakContent, keys: list[str]) -> None:
        parts: list[np.ndarray] = []
        voiced: list[np.ndarray] = []
        for i, ((pid, _), key) in enumerate(zip(content.pieces, keys)):
            pcm = self._piece_pcm(pid, key)
            parts.append(pcm)
            voiced.append(pcm)
            if i < len(content.pieces) - 1:
                parts.append(np.zeros((round(self._gap_s(i, content) * SAMPLE_RATE), CHANNELS), np.float32))
        voice = np.concatenate(parts)
        mix = voice
        if self.settings.bed is not None:
            mix = self._with_bed(voice, _rms(np.concatenate(voiced)))
        out = np.clip(mix, -1.0, 1.0)
        pcm16 = np.round(out * 32767.0).astype("<i2")
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(CHANNELS)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm16.tobytes())
        try:
            atomic_write_bytes(path, buf.getvalue())
        except Exception as exc:
            raise AssemblyError(f"cannot write {path}: {exc}") from exc

    def _with_bed(self, voice: np.ndarray, voice_rms: float) -> np.ndarray:
        g = self.settings.gaps
        bed_path = Path(self.settings.bed)
        try:
            bed = _decode(bed_path, self.ffmpeg)
            bed_rms = _rms(bed)
            if bed_rms <= 0:
                raise ValueError("bed is silent")
        except Exception as exc:
            raise AssemblyError(f"bed {bed_path} is unreadable: {exc}") from exc
        lead = round(g.bed_lead_in * SAMPLE_RATE)
        tail = round(g.bed_tail * SAMPLE_RATE)
        total = lead + len(voice) + tail
        looped = np.tile(bed, (total // len(bed) + 1, 1))[:total].copy()
        looped *= (voice_rms * 10 ** (-self.settings.bed_under_db / 20)) / bed_rms
        fade_in = min(round(BED_FADE_IN_S * SAMPLE_RATE), total)
        if fade_in:
            looped[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)[:, None]
        if tail:
            looped[-tail:] *= np.linspace(1.0, 0.0, tail, dtype=np.float32)[:, None]
        looped[lead:lead + len(voice)] += voice
        return looped


def scan_clips(out_dir: Path) -> list[Show]:
    """The assembled clips in `out_dir`. No quiet period: they are written
    atomically by this process, never by an outside writer."""
    try:
        paths = sorted(Path(out_dir).iterdir())
    except OSError:
        return []
    shows: list[Show] = []
    for p in paths:
        name = p.name
        if name.startswith(".") or not name.startswith(CLIP_PREFIX) or not name.endswith(".wav"):
            continue
        try:
            st = p.stat()
            if not stat.S_ISREG(st.st_mode) or st.st_size == 0:
                continue
            key, sizes = file_set_key_and_sizes(Path(out_dir), [name])
        except OSError:
            continue
        shows.append(Show(p.stem, Path(out_dir), (Entry(name, "clip", "Announcement"),), key,
                          {"role": CONCERT_ROLE, "ann_id": None, "sizes": sizes}))
    return shows


def gc_clips(out_dir: Path, cache_dir: Path, keep: set[str], *, now_s: float, min_age_s: float = 3600) -> int:
    """Delete unreferenced clips (slugs not in `keep`) older than `min_age_s`,
    with their `cache/<key>.json`, and dot-temps older than `min_age_s`. The age
    floor protects candidates never appended; referenced clips are protected by
    `keep`. Returns the number of files removed from `out_dir`."""
    try:
        paths = sorted(Path(out_dir).iterdir())
    except OSError:
        return 0
    removed = 0
    for p in paths:
        name = p.name
        is_temp = name.startswith(".") and name.endswith(".tmp")
        is_clip = name.startswith(CLIP_PREFIX) and name.endswith(".wav")
        if not (is_temp or is_clip):
            continue
        if is_clip and (p.stem in keep or name in keep):
            continue
        try:
            st = p.stat()
            if not stat.S_ISREG(st.st_mode) or now_s - st.st_mtime < min_age_s:
                continue
            if is_clip:
                key = file_set_key_and_sizes(Path(out_dir), [name])[0]
                analysis_mod.drop_cached(cache_dir, key)
            os.unlink(p)
            removed += 1
        except OSError:
            continue
    return removed
