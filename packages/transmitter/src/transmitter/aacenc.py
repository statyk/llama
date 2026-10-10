"""AAC-LC encoding with ffmpeg's native `aac` encoder (present in ffmpeg 5.1;
no libfdk). 128 kbps target, 44.1 kHz stereo, ADTS output.

The native encoder has no strict CBR mode: `-b:a 128k` targets 128 kbps and
digital silence encodes to tiny frames. Frame counts are what matter here:
for input padded to whole frames the encoder emits `padded/1024 + extra`
frames, with `extra` measured by `extra_frames()` rather than assumed (1 on
ffmpeg 8.1; the Debian 12 run checks 5.1)."""

import functools
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from transmitter import adts
from transmitter.errors import EncodeError
from transmitter.grid import CHANNELS, FRAME_SAMPLES, SAMPLE_RATE

ENCODER_PRIMING_SAMPLES = 1024   # ffmpeg aac's declared initial_padding
BITRATE = "128k"


def encode_cmd(ffmpeg: str) -> list[str]:
    return [ffmpeg, "-nostdin", "-hide_banner", "-v", "error",
            "-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-i", "pipe:0",
            "-c:a", "aac", "-b:a", BITRATE, "-f", "adts", "pipe:1"]


def as_station_pcm(pcm: np.ndarray) -> np.ndarray:
    arr = np.ascontiguousarray(pcm, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[1] != CHANNELS:
        raise ValueError(f"station PCM is float32 shaped (n, {CHANNELS}); got {arr.shape}")
    return arr


def encode_pcm(pcm: np.ndarray, ffmpeg: str = "ffmpeg") -> bytes:
    """Encode a whole (small) PCM buffer in one ffmpeg call."""
    try:
        proc = subprocess.run(encode_cmd(ffmpeg), input=as_station_pcm(pcm).tobytes(),
                              capture_output=True)
    except OSError as exc:
        raise EncodeError(f"cannot run {ffmpeg}: {exc}") from exc
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace").strip()[-500:]
        raise EncodeError(f"ffmpeg aac encode failed (exit {proc.returncode}): {tail}")
    return proc.stdout


class AacFileEncoder:
    """Streams PCM into one ffmpeg encode whose ADTS output appears at
    `out_path` atomically on close(). stdout goes straight to a unique temp
    file and stderr to an anonymous temp file, so no pipe can fill up and
    deadlock the writer."""

    def __init__(self, out_path: Path, ffmpeg: str = "ffmpeg"):
        self.out_path = Path(out_path)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.out_path.parent, prefix=f".{self.out_path.name}.",
                                   suffix=".tmp")
        self._tmp = Path(tmp)
        self._out = os.fdopen(fd, "wb")
        self._err = tempfile.TemporaryFile()
        try:
            self._proc = subprocess.Popen(encode_cmd(ffmpeg), stdin=subprocess.PIPE,
                                          stdout=self._out, stderr=self._err)
        except OSError as exc:
            self._out.close()
            self._cleanup()
            raise EncodeError(f"cannot run {ffmpeg}: {exc}") from exc
        self.samples_written = 0
        self._closed = False

    def __enter__(self) -> "AacFileEncoder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.abort()

    def write(self, pcm: np.ndarray) -> None:
        arr = as_station_pcm(pcm)
        try:
            self._proc.stdin.write(arr.tobytes())
        except BrokenPipeError as exc:
            raise EncodeError(f"ffmpeg aac encoder exited early: {self._stderr_tail()}") from exc
        self.samples_written += len(arr)

    def write_silence(self, samples: int, chunk: int = 1 << 16) -> None:
        while samples > 0:
            n = min(samples, chunk)
            self.write(np.zeros((n, CHANNELS), np.float32))
            samples -= n

    def close(self) -> Path:
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        rc = self._proc.wait()
        self._out.close()
        self._closed = True
        if rc != 0:
            tail = self._stderr_tail()
            self._cleanup()
            raise EncodeError(f"ffmpeg aac encode failed (exit {rc}): {tail}")
        self._err.close()
        os.replace(self._tmp, self.out_path)
        return self.out_path

    def abort(self) -> None:
        if self._closed:
            return
        self._proc.kill()
        self._proc.wait()
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        self._out.close()
        self._closed = True
        self._cleanup()

    def _cleanup(self) -> None:
        self._err.close()
        self._tmp.unlink(missing_ok=True)

    def _stderr_tail(self) -> str:
        self._err.seek(0)
        return self._err.read().decode(errors="replace").strip()[-500:]


def pad_to_frame(samples: int) -> int:
    return -(-samples // FRAME_SAMPLES) * FRAME_SAMPLES


def frames_for(padded_samples: int, extra: int) -> int:
    if padded_samples % FRAME_SAMPLES:
        raise ValueError("pad the input to a whole number of frames first")
    return padded_samples // FRAME_SAMPLES + extra


@functools.cache
def extra_frames(ffmpeg: str = "ffmpeg") -> int:
    """Frames the encoder emits beyond padded_samples/1024 (priming + flush)."""
    probe = 8
    got = len(adts.split_frames(encode_pcm(np.zeros((probe * FRAME_SAMPLES, CHANNELS), np.float32), ffmpeg)))
    extra = got - probe
    if extra < 0:
        raise EncodeError(f"{ffmpeg} emitted {got} frames for {probe} frames of input")
    return extra


@functools.cache
def silent_frame(ffmpeg: str = "ffmpeg") -> bytes:
    """One steady-state encoded frame of digital silence, repeated to fill
    gaps between shows (spec: "pre-encoded silent frames fill the gap")."""
    frames = adts.split_frames(encode_pcm(np.zeros((16 * FRAME_SAMPLES, CHANNELS), np.float32), ffmpeg))
    frame = frames[len(frames) // 2]
    adts.require_station_format(adts.parse_header(frame))
    return frame
