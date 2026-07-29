"""Instrumental "bed" music mixed under the spoken DJ clips.

A bed plays at a fixed low level under each DJ segment (no ducking — the clips
have no concurrent music track). Pure PCM math via numpy; the only I/O is
reading the bed WAV with the stdlib wave module. See
docs/superpowers/specs/2026-07-25-bed-music-design.md.
"""
from dataclasses import dataclass
from pathlib import Path
import wave

import numpy as np

from llama.tts.provider import SpeechError

BED_RATE = 24000        # required bed sample rate (matches the voice PCM)
_INT16_MAX = 32767
_INT16_MIN = -32768


@dataclass(frozen=True)
class Bed:
    """A resolved bed: the WAV path plus the station gain applied under voice."""
    path: Path
    gain_db: float


def load_bed_pcm(path: Path) -> tuple[bytes, int, int, int]:
    """Read a bed WAV, returning (pcm, framerate, channels, sampwidth).

    Requires 24kHz mono 16-bit PCM (matching the voice); anything else — or a
    missing/unreadable file — raises SpeechError naming the required format.
    """
    try:
        with wave.open(str(path), "rb") as w:
            framerate, channels, sampwidth = w.getframerate(), w.getnchannels(), w.getsampwidth()
            pcm = w.readframes(w.getnframes())
    except (OSError, wave.Error) as err:
        raise SpeechError(f"bed music: cannot read {path}: {err}") from err
    if (framerate, channels, sampwidth) != (BED_RATE, 1, 2):
        raise SpeechError(
            f"bed music {path} must be 24kHz mono 16-bit WAV, got "
            f"{framerate}Hz {channels}ch {sampwidth * 8}-bit")
    return pcm, framerate, channels, sampwidth


def _fade_envelope(n: int, fade: int) -> np.ndarray:
    """Length-n gain envelope: linear 0->1 over the first `fade` samples and
    1->0 over the last `fade`, flat 1.0 between. `fade` is clamped to n//2 so
    the ramps never overlap."""
    env = np.ones(n, dtype=np.float32)
    fade = min(fade, n // 2)
    if fade > 0:
        ramp = np.linspace(0.0, 1.0, fade, endpoint=False, dtype=np.float32)
        env[:fade] = ramp
        env[n - fade:] = ramp[::-1]
    return env


def mix_bed(voice_pcm: bytes, bed_pcm: bytes, framerate: int, *,
            gain_db: float, pre_roll_s: float = 1.5, tail_s: float = 2.0,
            fade_s: float = 1.0) -> bytes:
    """Mix a bed under one voice clip and return int16 PCM.

    Layout: pre_roll (music alone) + voice (bed under voice) + tail (music
    alone). The bed is tiled to the full length, attenuated by gain_db, faded
    in/out over fade_s, then the voice is summed in at the pre_roll offset. The
    sum is hard-clipped to int16. Both inputs are 16-bit mono PCM at framerate.
    """
    voice = np.frombuffer(voice_pcm, dtype="<i2").astype(np.float32)
    bed = np.frombuffer(bed_pcm, dtype="<i2").astype(np.float32)
    if bed.size == 0:
        raise SpeechError("bed music: empty bed audio")

    pre = int(round(pre_roll_s * framerate))
    tail = int(round(tail_s * framerate))
    fade = int(round(fade_s * framerate))
    total = pre + voice.size + tail

    reps = -(-total // bed.size)  # ceil division
    bed_track = np.tile(bed, reps)[:total]
    bed_track *= 10.0 ** (gain_db / 20.0)
    bed_track *= _fade_envelope(total, fade)

    bed_track[pre:pre + voice.size] += voice
    np.clip(bed_track, _INT16_MIN, _INT16_MAX, out=bed_track)
    return bed_track.astype("<i2").tobytes()
