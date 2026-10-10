"""Shared test helpers.

This directory is the package `tests_transmitter`, not `tests`: llama's test
modules are top-level (`test_config`, `helpers`, …) and emcee's are the
`tests` package, so either name would collide in the repo-wide pytest run.
Import helpers as `from tests_transmitter.helpers import …`.
"""

import shutil
import subprocess
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
