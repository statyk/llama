"""Regenerate packages/llama/src/llama/data/audio_check_tone.mp3.

A ~5 s synthetic tone (440 Hz plus harmonics), 44.1 kHz stereo so the 16 kHz
resampler is exercised. Dev-only: needs `lameenc` (already installed via emcee).
Fully synthetic, so it is the one MP3 committed besides model data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import lameenc
import numpy as np

OUT = Path(__file__).resolve().parents[1] / "packages/llama/src/llama/data/audio_check_tone.mp3"
RATE = 44100
SECONDS = 5.0


def main(out: Path = OUT) -> None:
    t = np.arange(int(RATE * SECONDS)) / RATE
    mono = sum(np.sin(2 * np.pi * 440 * k * t) / k for k in (1, 2, 3, 4)) / 2.2
    mono *= np.minimum(1.0, np.minimum(t, SECONDS - t) / 0.05)
    left = mono
    right = np.roll(mono, 40) * 0.9
    pcm = (np.stack([left, right], axis=1) * 0.5 * 32767).astype("<i2")
    enc = lameenc.Encoder()
    enc.set_bit_rate(96)
    enc.set_out_sample_rate(RATE)
    enc.set_in_sample_rate(RATE)
    enc.set_channels(2)
    enc.set_quality(2)
    data = enc.encode(pcm.tobytes()) + enc.flush()
    out.write_bytes(bytes(data))
    print(f"wrote {out} ({len(data)} bytes)")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT)
