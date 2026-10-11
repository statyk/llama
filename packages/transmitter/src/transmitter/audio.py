"""Gapless decode and loudness measurement (spec "Renderer", "Loudness").

Decoding is ffmpeg to float32 44.1 kHz stereo PCM. ffmpeg's MP3 demuxer reads
the Xing/LAME header and trims encoder delay and padding, so consecutive tracks
of a segue concatenate with no inserted silence. Loudness is ffmpeg's
`ebur128` filter (BS.1770 integrated loudness + true peak), fed the same PCM
through a pipe. Every subprocess writes stderr to an anonymous temp file, so
no pipe can fill and deadlock the reader/writer.
"""

import math
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from transmitter.aacenc import as_station_pcm
from transmitter.errors import AnalysisError, DecodeError
from transmitter.grid import CHANNELS, SAMPLE_RATE

CHUNK_FRAMES = 1 << 16
_BYTES_PER_FRAME = 4 * CHANNELS
METER_FILTER = "ebur128=peak=true:framelog=verbose"
SILENCE_LUFS = -70.0   # ebur128's absolute gate: nothing measurable


def decode_cmd(ffmpeg: str, path: Path) -> list[str]:
    return [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-i", str(path),
            "-map", "0:a:0", "-f", "f32le", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "pipe:1"]


def iter_decode(path: Path, ffmpeg: str = "ffmpeg") -> Iterator[np.ndarray]:
    err = tempfile.TemporaryFile()
    try:
        proc = subprocess.Popen(decode_cmd(ffmpeg, path), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=err)
    except OSError as exc:
        err.close()
        raise DecodeError(f"cannot run {ffmpeg}: {exc}") from exc
    finished = False
    try:
        pending = b""
        while True:
            chunk = proc.stdout.read(CHUNK_FRAMES * _BYTES_PER_FRAME)
            if not chunk:
                break
            data = pending + chunk
            usable = len(data) - len(data) % _BYTES_PER_FRAME
            pending = data[usable:]
            if usable:
                yield np.frombuffer(data[:usable], dtype="<f4").reshape(-1, CHANNELS)
        rc = proc.wait()
        if rc != 0 or pending:
            err.seek(0)
            tail = err.read().decode(errors="replace").strip()[-500:]
            raise DecodeError(f"{path}: ffmpeg decode failed (exit {rc}): {tail}")
        finished = True
    finally:
        if not finished and proc.poll() is None:
            proc.kill()
        proc.stdout.close()
        proc.wait()
        err.close()


@dataclass(frozen=True)
class Loudness:
    i_lufs: float | None     # None = nothing above the gate (silence)
    tp_dbfs: float | None    # None = -inf (digital silence)


_I_RE = re.compile(r"Integrated loudness:\s*\n\s*I:\s*(\S+)\s+LUFS")
_TP_RE = re.compile(r"True peak:\s*\n\s*Peak:\s*(\S+)\s+dBFS")


def _finite(text: str) -> float | None:
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def parse_ebur128_summary(text: str) -> Loudness:
    at = text.rfind("Summary:")
    if at < 0:
        raise AnalysisError("ffmpeg ebur128 printed no summary")
    tail = text[at:]
    m_i = _I_RE.search(tail)
    if m_i is None:
        raise AnalysisError("ffmpeg ebur128 summary has no integrated loudness")
    m_tp = _TP_RE.search(tail)
    i = _finite(m_i.group(1))
    if i is not None and i <= SILENCE_LUFS:
        i = None
    return Loudness(i, _finite(m_tp.group(1)) if m_tp else None)


class LoudnessMeter:
    """Feeds PCM into `ffmpeg -af ebur128` and parses its summary. The process
    starts lazily, so a meter that never receives samples reports (None, None)."""

    def __init__(self, ffmpeg: str = "ffmpeg"):
        self._ffmpeg = ffmpeg
        self._proc: subprocess.Popen | None = None
        self._err = None
        self.samples = 0

    def _start(self) -> None:
        self._err = tempfile.TemporaryFile()
        cmd = [self._ffmpeg, "-nostdin", "-hide_banner", "-nostats",
               "-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-i", "pipe:0",
               "-af", METER_FILTER, "-f", "null", "-"]
        try:
            self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                          stderr=self._err)
        except OSError as exc:
            self._err.close()
            raise AnalysisError(f"cannot run {self._ffmpeg}: {exc}") from exc

    def write(self, pcm: np.ndarray) -> None:
        if len(pcm) == 0:
            return
        if self._proc is None:
            self._start()
        try:
            self._proc.stdin.write(as_station_pcm(pcm).tobytes())
        except BrokenPipeError as exc:
            raise AnalysisError(f"ffmpeg ebur128 exited early: {self._stderr()[-500:]}") from exc
        self.samples += len(pcm)

    def finish(self) -> Loudness:
        if self._proc is None:
            return Loudness(None, None)
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        rc = self._proc.wait()
        text = self._stderr()
        self._err.close()
        self._proc = None
        if rc != 0:
            raise AnalysisError(f"ffmpeg ebur128 failed (exit {rc}): {text.strip()[-500:]}")
        return parse_ebur128_summary(text)

    def abort(self) -> None:
        if self._proc is None:
            return
        self._proc.kill()
        self._proc.wait()
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        self._err.close()
        self._proc = None

    def _stderr(self) -> str:
        self._err.seek(0)
        return self._err.read().decode(errors="replace")
