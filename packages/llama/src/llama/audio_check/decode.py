"""Decode an MP3/FLAC to 16 kHz mono float32 for the classifier.

miniaudio and numpy are imported inside functions only.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from llama.errors import LlamaError

if TYPE_CHECKING:
    import numpy as np

SAMPLE_RATE = 16000


class DecodeError(LlamaError):
    """The file is unreadable, not MP3/FLAC by content, or truncated."""


def to_16k_mono(path: Path) -> "tuple[np.ndarray, float]":
    """Return (float32 wave in [-1, 1] at 16 kHz mono, decoded seconds)."""
    import miniaudio
    import numpy as np

    path = Path(path)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        decoded = miniaudio.decode(
            data,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1,
            sample_rate=SAMPLE_RATE,
        )
    except DecodeError:
        raise
    except Exception as exc:
        raise DecodeError(f"cannot decode {path.name}: {exc}") from exc
    _check_not_truncated(path, data, decoded.duration)
    samples = np.frombuffer(decoded.samples, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size == 0:
        raise DecodeError(f"cannot decode {path.name}: no audio")
    return samples, samples.size / SAMPLE_RATE



_BITRATES = {  # MPEG1 layer III, kbps by index
    1: 32, 2: 40, 3: 48, 4: 56, 5: 64, 6: 80, 7: 96, 8: 112,
    9: 128, 10: 160, 11: 192, 12: 224, 13: 256, 14: 320,
}
_RATES = {0: 44100, 1: 48000, 2: 32000}


def _check_not_truncated(path: Path, data: bytes, decoded_sec: float) -> None:
    """miniaudio returns partial audio for a cut file; turn that into DecodeError.

    FLAC: the STREAMINFO total length against what decoded. MP3 (MPEG1 layer III): walk
    the frame headers and see whether the last frame runs past the end of the file. On
    anything unexpected (other MPEG versions, lost sync, trailing tags) it does not flag.
    """
    if data[:4] == b"fLaC":
        if len(data) >= 26:
            rate = int.from_bytes(data[18:21], "big") >> 4
            total = int.from_bytes(data[21:26], "big") & 0xFFFFFFFFF
            if rate and total and decoded_sec < 0.98 * total / rate:
                raise DecodeError(f"cannot decode {path.name}: truncated FLAC")
        return
    pos = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        pos = 10 + ((data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9])
    n = len(data)
    while pos + 4 <= n:
        h = int.from_bytes(data[pos : pos + 4], "big")
        if (h >> 21) != 0x7FF or ((h >> 19) & 3) != 3 or ((h >> 17) & 3) != 1:
            return  # lost sync, tag, or not MPEG1 L3: do not guess
        br = _BITRATES.get((h >> 12) & 15)
        sr = _RATES.get((h >> 10) & 3)
        if br is None or sr is None:
            return
        flen = 144 * br * 1000 // sr + ((h >> 9) & 1)
        if pos + flen > n:
            raise DecodeError(f"cannot decode {path.name}: truncated MP3")
        pos += flen
