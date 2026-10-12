### Task 1: Spike A — package scaffold, grid, ID3, ADTS, segment assembly

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/pyproject.toml`, `packages/transmitter/LICENSE` (copy of `packages/emcee/LICENSE`)
- Create: `packages/transmitter/src/transmitter/{__init__,__main__,errors,cli,grid,id3,adts,segment}.py`
- Create: `packages/transmitter/tests_transmitter/{__init__,helpers}.py`, `test_no_llama_or_emcee_imports.py`, `test_grid.py`, `test_id3.py`, `test_adts.py`, `test_segment.py`, `test_cli.py`
- Modify: `pytest.ini` (testpaths)

**Interfaces:**
- Consumes: nothing.
- Produces (every later Python task relies on these exact names):
  - `transmitter.errors`: `TransmitterError(message, details=None)` and subclasses `ConfigError, AdtsError, EncodeError, DecodeError, AnalysisError, StationRootError, PlanError, LayoutError, RenderError, FrameCountDrift(RenderError), PublishError, PublishLocked, PutBudgetExceeded`.
  - `transmitter.grid`: `SAMPLE_RATE=44100, CHANNELS=2, FRAME_SAMPLES=1024, SEGMENT_FRAMES=441, SEGMENT_SAMPLES=451584, D_US=10_240_000, D_MS=10_240, TS_HZ=90_000, TS_PER_SEGMENT=921_600, TS_WRAP=2**33`; `segment_timestamp(n) -> int`; `segment_start_us(epoch_us, n) -> int`; `segment_index_at(epoch_us, t_us) -> int` (floor); `first_segment_at_or_after(epoch_us, t_us) -> int` (ceil); `samples_for_seconds(s) -> int`; `frames_ceil(samples) -> int`; `gap_frames(s) -> int`; `samples_to_us(samples) -> int`; `frame_to_us(frame) -> int`; `us_to_iso(us) -> str` (`…T…:…:….mmmZ`); `iso_to_us(text) -> int`.
  - `transmitter.id3`: `PRIV_OWNER: bytes`; `timestamp_tag(ts: int) -> bytes` (73 bytes); `parse_timestamp_tag(data: bytes) -> tuple[int, int]` (`(ts, tag_length)`).
  - `transmitter.adts`: `AdtsHeader(object_type, sample_rate_index, channel_config, frame_length)`; `parse_header(buf, pos=0) -> AdtsHeader`; `frame_offsets(buf) -> list[int]` (len = frames + 1); `split_frames(buf) -> list[bytes]`; `build_frame(payload, *, object_type=2, sample_rate_index=4, channel_config=2) -> bytes`; `require_station_format(h) -> None`.
  - `transmitter.segment`: `assemble(ts_index: int, frames: Sequence[bytes]) -> bytes`; `parse(data) -> tuple[int, list[bytes]]`; `segment_key(epoch_id, n) -> str` (`seg/<epoch_id>/<n>.aac`).
  - `transmitter.cli`: `app` (typer), `main_cli()`.
  - `tests_transmitter.helpers`: `HAVE_FFMPEG`, `requires_ffmpeg`.

- [ ] **Step 1: Scaffold the package**

`packages/transmitter/pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "llama-transmitter"
version = "0.1.0"
description = "Station playout: plans, renders and publishes the llama station's HLS stream"
requires-python = ">=3.11"
license = "GPL-3.0-or-later"
license-files = ["LICENSE"]
dependencies = [
    "typer>=0.12",
    "pydantic>=2.7",
    "numpy>=1.26",
    "boto3>=1.36",
]

[project.scripts]
transmitter = "transmitter.cli:main_cli"

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.hatch.build.targets.wheel]
packages = ["src/transmitter"]
```

```bash
cp packages/emcee/LICENSE packages/transmitter/LICENSE
```

`packages/transmitter/src/transmitter/__init__.py`:

```python
"""transmitter: plans, renders and publishes the station's HLS stream."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("llama-transmitter")
except PackageNotFoundError:  # raw checkout, no metadata
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
```

`packages/transmitter/src/transmitter/__main__.py`:

```python
"""Entry point for `python -m transmitter`."""

from transmitter.cli import main_cli

if __name__ == "__main__":
    main_cli()
```

`packages/transmitter/src/transmitter/errors.py`:

```python
"""Central exception taxonomy.

`TransmitterError` is the base for expected, operator-actionable failures:
the CLI boundary prints `error: <message>` (plus indented `details`) and
exits 1. Anything else is a bug and surfaces as a traceback. This module
imports nothing from the package, to stay import-cycle-free.
"""


class TransmitterError(Exception):
    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or []


class ConfigError(TransmitterError):
    """config.toml could not be parsed or failed validation."""


class AdtsError(TransmitterError):
    """Bytes that should be an ADTS frame sequence are not."""


class EncodeError(TransmitterError):
    """ffmpeg's AAC encode failed."""


class DecodeError(TransmitterError):
    """ffmpeg could not decode a package's audio file."""


class AnalysisError(TransmitterError):
    """A show's durations/loudness could not be measured."""


class StationRootError(TransmitterError):
    """The station root is unset, missing, or lacks its `.station-root` marker."""


class PlanError(TransmitterError):
    """The plan cannot be extended (e.g. nothing eligible)."""


class LayoutError(TransmitterError):
    """The plan's frame layout is inconsistent with what is on disk."""


class RenderError(TransmitterError):
    """A show could not be rendered (the show is skipped and re-planned)."""


class FrameCountDrift(RenderError):
    """The encoder produced a different frame count than planned. Fatal: it
    means the frame-count model is wrong on this ffmpeg, not that one show is bad."""


class PublishError(TransmitterError):
    """An upload/delete against R2 failed after retries."""


class PublishLocked(TransmitterError):
    """Another publish or prune holds the local lock."""


class PutBudgetExceeded(TransmitterError):
    """The local daily PUT budget is spent; publishing stops until tomorrow (UTC)."""
```

`packages/transmitter/src/transmitter/cli.py`:

```python
"""CLI boundary: typer app + `main_cli` error boundary (mirrors emcee's)."""

import sys
import traceback

import typer

from transmitter.errors import TransmitterError

app = typer.Typer(help="Plan, render and publish the station's HLS stream",
                  pretty_exceptions_enable=False, no_args_is_help=True)


def _version_callback(value: bool) -> None:
    if value:
        import transmitter

        typer.echo(transmitter.__version__)
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(None, "--version", callback=_version_callback,
                                 is_eager=True, help="Print the transmitter version and exit."),
) -> None:
    """Station playout."""


def main_cli() -> None:
    try:
        app()
    except TransmitterError as e:
        print(f"error: {e}", file=sys.stderr)
        for line in e.details:
            print(f"  {line}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except BrokenPipeError:
        raise SystemExit(0)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
```

`packages/transmitter/tests_transmitter/__init__.py`: empty file.

`packages/transmitter/tests_transmitter/helpers.py`:

```python
"""Shared test helpers.

This directory is the package `tests_transmitter`, not `tests`: llama's test
modules are top-level (`test_config`, `helpers`, …) and emcee's are the
`tests` package, so either name would collide in the repo-wide pytest run.
Import helpers as `from tests_transmitter.helpers import …`.
"""

import shutil

import pytest

HAVE_FFMPEG = shutil.which("ffmpeg") is not None
requires_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not on PATH")
```

Modify `pytest.ini` — the `testpaths` line becomes:

```ini
testpaths = packages/herder/tests packages/llama/tests packages/emcee/tests packages/transmitter/tests_transmitter scripts
```

Install into the worktree venv:

```bash
./.venv/bin/pip install -e "packages/transmitter[dev]"
./.venv/bin/python -c "import transmitter; print(transmitter.__file__)"   # must be inside the worktree
```

- [ ] **Step 2: Write the failing tests**

`tests_transmitter/test_no_llama_or_emcee_imports.py`:

```python
"""transmitter's only input is the package directory: it never imports llama
or emcee (spec "Architecture"). Checks both src and tests."""

import re
from pathlib import Path

FORBIDDEN = re.compile(
    r"^\s*(?:from|import)\s+(?:llama|emcee)\b"
    r"|(?:__import__|import_module)\s*\(\s*['\"](?:llama|emcee)\b",
    re.M,
)


def _offenders(root: Path) -> list[str]:
    py_files = sorted(root.rglob("*.py"))
    assert py_files, f"no .py files found under {root} — path anchor broke"
    return [str(p) for p in py_files if FORBIDDEN.search(p.read_text())]


def test_pattern_catches_both_forms():
    assert FORBIDDEN.search("import emcee\n")
    assert FORBIDDEN.search("from llama.catalog import x\n")
    # split so this file's own source does not match the pattern it scans for
    assert FORBIDDEN.search("importlib.import_" + "module('emcee.station')\n")
    assert not FORBIDDEN.search("import llama_thing\n")


def test_src_never_imports_llama_or_emcee():
    root = Path(__file__).resolve().parents[1]
    assert _offenders(root / "src") == []


def test_tests_never_import_llama_or_emcee():
    root = Path(__file__).resolve().parents[1]
    assert _offenders(root / "tests_transmitter") == []
```

`tests_transmitter/test_grid.py`:

```python
import pytest

from transmitter import grid


def test_segment_duration_is_exact():
    assert grid.SEGMENT_SAMPLES == 451_584
    assert grid.D_US == 10_240_000
    assert grid.D_MS == 10_240
    assert grid.TS_PER_SEGMENT == 921_600


def test_segment_timestamp_wraps_at_2_pow_33():
    assert grid.segment_timestamp(0) == 0
    assert grid.segment_timestamp(1) == 921_600
    assert grid.segment_timestamp(9320) == 8_589_312_000
    assert grid.segment_timestamp(9321) == 299_008
    assert grid.segment_timestamp(9321) == (9321 * 921_600) % (1 << 33)


def test_segment_timestamp_rejects_negative():
    with pytest.raises(ValueError):
        grid.segment_timestamp(-1)


def test_index_at_floors_and_goes_negative_before_the_epoch():
    e = 1_000_000_000_000
    assert grid.segment_index_at(e, e) == 0
    assert grid.segment_index_at(e, e + grid.D_US - 1) == 0
    assert grid.segment_index_at(e, e + grid.D_US) == 1
    assert grid.segment_index_at(e, e - 1) == -1


def test_first_segment_at_or_after_is_a_ceiling():
    assert grid.first_segment_at_or_after(0, 0) == 0
    assert grid.first_segment_at_or_after(0, 1) == 1
    assert grid.first_segment_at_or_after(0, grid.D_US) == 1
    assert grid.first_segment_at_or_after(0, grid.D_US + 1) == 2


def test_gap_frames_round_up_to_whole_frames():
    assert grid.gap_frames(2.0) == 87      # 88200 samples / 1024 = 86.13
    assert grid.gap_frames(0.75) == 33     # 33075 / 1024 = 32.3
    assert grid.gap_frames(0.0) == 0


def test_iso_round_trip():
    us = grid.iso_to_us("2026-10-10T12:00:00Z")
    assert grid.us_to_iso(us) == "2026-10-10T12:00:00.000Z"
    assert grid.iso_to_us(grid.us_to_iso(us + grid.D_US)) == us + grid.D_US


def test_iso_requires_an_offset():
    with pytest.raises(ValueError):
        grid.iso_to_us("2026-10-10T12:00:00")
```

`tests_transmitter/test_id3.py`:

```python
import pytest

from transmitter import id3


def test_timestamp_tag_layout():
    tag = id3.timestamp_tag(0x1_2345_6789)
    assert len(tag) == 73
    assert tag[:10] == b"ID3\x04\x00\x00\x00\x00\x00\x3f"          # v2.4, size 63 (syncsafe)
    assert tag[10:20] == b"PRIV\x00\x00\x00\x35\x00\x00"           # frame body 53 bytes
    assert tag[20:64] == b"com.apple.streaming.transportStreamTimestamp"
    assert tag[64:65] == b"\x00"
    assert tag[65:] == (0x1_2345_6789).to_bytes(8, "big")


@pytest.mark.parametrize("ts", [0, 1, 921_600, (1 << 33) - 1])
def test_round_trip(ts):
    assert id3.parse_timestamp_tag(id3.timestamp_tag(ts) + b"rest") == (ts, 73)


@pytest.mark.parametrize("ts", [-1, 1 << 33])
def test_rejects_out_of_range(ts):
    with pytest.raises(ValueError):
        id3.timestamp_tag(ts)


def test_parse_rejects_non_id3():
    with pytest.raises(ValueError):
        id3.parse_timestamp_tag(b"\xff\xf1\x50\x80\x03\xdf\xfc")
```

`tests_transmitter/test_adts.py`:

```python
import pytest

from transmitter import adts
from transmitter.errors import AdtsError


def test_build_frame_matches_ffmpeg_header():
    # ffmpeg 8.1 `-c:a aac -f adts`, 44.1 kHz stereo, first frame: fff1508003dffc (30 bytes)
    frame = adts.build_frame(bytes(23))
    assert frame[:7].hex() == "fff1508003dffc"
    assert len(frame) == 30


def test_parse_header_fields():
    h = adts.parse_header(adts.build_frame(b"x" * 100))
    assert (h.object_type, h.sample_rate_index, h.channel_config, h.frame_length) == (2, 4, 2, 107)


def test_split_frames_round_trip():
    frames = [adts.build_frame(bytes([i]) * (i + 1)) for i in range(5)]
    data = b"".join(frames)
    assert adts.split_frames(data) == frames
    assert adts.frame_offsets(data) == [0, 8, 17, 27, 38, 50]


def test_split_rejects_lost_sync():
    with pytest.raises(AdtsError, match="sync"):
        adts.split_frames(adts.build_frame(b"ab") + b"\x00\x00junkjunk")


def test_split_rejects_truncated_frame():
    with pytest.raises(AdtsError):
        adts.split_frames(adts.build_frame(b"abcdef")[:-1])


def test_require_station_format():
    adts.require_station_format(adts.parse_header(adts.build_frame(b"z")))
    with pytest.raises(AdtsError):
        adts.require_station_format(adts.parse_header(adts.build_frame(b"z", channel_config=1)))
```

`tests_transmitter/test_segment.py`:

```python
import pytest

from transmitter import adts, grid, segment


def test_assemble_prefixes_the_grid_timestamp():
    frames = [adts.build_frame(i.to_bytes(4, "big")) for i in range(441)]
    data = segment.assemble(9321, frames)
    ts, parsed = segment.parse(data)
    assert ts == grid.segment_timestamp(9321) == 299_008
    assert parsed == frames


def test_assemble_requires_exactly_441_frames():
    with pytest.raises(ValueError):
        segment.assemble(0, [adts.build_frame(b"x")] * 440)


def test_segment_key():
    assert segment.segment_key("e20261010T120000Z", 42) == "seg/e20261010T120000Z/42.aac"
```

`tests_transmitter/test_cli.py`:

```python
from typer.testing import CliRunner

import transmitter
from transmitter.cli import app


def test_version():
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == transmitter.__version__
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.grid'` (and id3/adts/segment); the import-guard and CLI tests pass.

- [ ] **Step 4: Implement grid, id3, adts, segment**

`packages/transmitter/src/transmitter/grid.py`:

```python
"""The station's time grid (spec "The core contract: the stream is a function
of the wall clock").

Segment N covers [E + N*d, E + (N+1)*d). d is exactly 441 AAC frames of 1024
samples at 44.1 kHz = 10.24 s, which is exact in microseconds, milliseconds
and 90 kHz ticks. Everything here is integer arithmetic; floats never touch
the grid.
"""

from datetime import datetime, timedelta, timezone

SAMPLE_RATE = 44_100
CHANNELS = 2
FRAME_SAMPLES = 1024
SEGMENT_FRAMES = 441
SEGMENT_SAMPLES = SEGMENT_FRAMES * FRAME_SAMPLES                # 451_584
D_US = SEGMENT_SAMPLES * 1_000_000 // SAMPLE_RATE               # 10_240_000
D_MS = D_US // 1000                                             # 10_240
TS_HZ = 90_000
TS_PER_SEGMENT = SEGMENT_SAMPLES * TS_HZ // SAMPLE_RATE         # 921_600
TS_WRAP = 1 << 33

if SEGMENT_SAMPLES * 1_000_000 % SAMPLE_RATE or SEGMENT_SAMPLES * TS_HZ % SAMPLE_RATE:
    raise AssertionError("segment duration must be exact in us and in 90 kHz ticks")

_UNIX = datetime(1970, 1, 1, tzinfo=timezone.utc)


def segment_timestamp(n: int) -> int:
    """90 kHz ID3 timestamp of segment n: (n*d*90000) mod 2^33."""
    if n < 0:
        raise ValueError(f"segment index must be >= 0, got {n}")
    return (n * TS_PER_SEGMENT) % TS_WRAP


def segment_start_us(epoch_us: int, n: int) -> int:
    return epoch_us + n * D_US


def segment_index_at(epoch_us: int, t_us: int) -> int:
    """Index of the segment airing at t (floor; negative before the epoch)."""
    return (t_us - epoch_us) // D_US


def first_segment_at_or_after(epoch_us: int, t_us: int) -> int:
    """Smallest n whose start is >= t (ceil)."""
    return -((epoch_us - t_us) // D_US)


def samples_for_seconds(seconds: float) -> int:
    return round(seconds * SAMPLE_RATE)


def frames_ceil(samples: int) -> int:
    return -(-samples // FRAME_SAMPLES)


def gap_frames(seconds: float) -> int:
    """A silence of `seconds`, rounded up to whole frames (spec: the
    inter-show gap is rounded up to whole frames)."""
    return frames_ceil(samples_for_seconds(seconds))


def samples_to_us(samples: int) -> int:
    return samples * 1_000_000 // SAMPLE_RATE


def frame_to_us(frame: int) -> int:
    return samples_to_us(frame * FRAME_SAMPLES)


def us_to_iso(us: int) -> str:
    dt = _UNIX + timedelta(microseconds=us)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def iso_to_us(text: str) -> int:
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"timestamp must carry a UTC offset: {text!r}")
    return (dt - _UNIX) // timedelta(microseconds=1)
```

`packages/transmitter/src/transmitter/id3.py`:

```python
"""The RFC 8216 §3.4 packed-audio timestamp: an ID3v2.4 tag holding one PRIV
frame owned by `com.apple.streaming.transportStreamTimestamp`, whose payload is
the segment's first-sample PTS as a 33-bit value in an 8-byte big-endian field."""

PRIV_OWNER = b"com.apple.streaming.transportStreamTimestamp"
_TS_LIMIT = 1 << 33


def _syncsafe(n: int) -> bytes:
    if not 0 <= n < 1 << 28:
        raise ValueError(f"syncsafe integer out of range: {n}")
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def _unsyncsafe(b: bytes) -> int:
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def timestamp_tag(ts: int) -> bytes:
    if not 0 <= ts < _TS_LIMIT:
        raise ValueError(f"timestamp must be a 33-bit value, got {ts}")
    body = PRIV_OWNER + b"\x00" + ts.to_bytes(8, "big")
    frame = b"PRIV" + _syncsafe(len(body)) + b"\x00\x00" + body
    return b"ID3" + bytes([4, 0, 0]) + _syncsafe(len(frame)) + frame


def parse_timestamp_tag(data: bytes) -> tuple[int, int]:
    """(timestamp, tag_length) of the ID3 tag at the start of `data`."""
    if data[:3] != b"ID3" or len(data) < 10:
        raise ValueError("data does not start with an ID3 tag")
    end = 10 + _unsyncsafe(data[6:10])
    pos = 10
    while pos + 10 <= end:
        frame_id = data[pos:pos + 4]
        size = _unsyncsafe(data[pos + 4:pos + 8])
        body = data[pos + 10:pos + 10 + size]
        if frame_id == b"PRIV" and body.startswith(PRIV_OWNER + b"\x00"):
            raw = body[len(PRIV_OWNER) + 1:]
            if len(raw) != 8:
                raise ValueError("transportStreamTimestamp payload is not 8 bytes")
            return int.from_bytes(raw, "big"), end
        pos += 10 + size
    raise ValueError("ID3 tag has no transportStreamTimestamp PRIV frame")
```

`packages/transmitter/src/transmitter/adts.py`:

```python
"""ADTS framing (ISO/IEC 13818-7): parse headers, split a stream into frames,
build headers (tests and the fMP4 contingency need them). Only 7-byte headers
(protection_absent=1) are built; parsing accepts either."""

from dataclasses import dataclass

from transmitter.errors import AdtsError

STATION_OBJECT_TYPE = 2        # AAC-LC
STATION_SAMPLE_RATE_INDEX = 4  # 44100 Hz
STATION_CHANNELS = 2


@dataclass(frozen=True)
class AdtsHeader:
    object_type: int
    sample_rate_index: int
    channel_config: int
    frame_length: int


def parse_header(buf: bytes, pos: int = 0) -> AdtsHeader:
    if len(buf) - pos < 7:
        raise AdtsError(f"truncated ADTS header at byte {pos}")
    b0, b1, b2, b3, b4, b5 = buf[pos:pos + 6]
    if b0 != 0xFF or (b1 & 0xF6) != 0xF0:
        raise AdtsError(f"lost ADTS sync at byte {pos}")
    length = ((b3 & 0x03) << 11) | (b4 << 3) | (b5 >> 5)
    if length < 7:
        raise AdtsError(f"ADTS frame length {length} at byte {pos} is shorter than its header")
    return AdtsHeader(
        object_type=((b2 >> 6) & 0x3) + 1,
        sample_rate_index=(b2 >> 2) & 0xF,
        channel_config=((b2 & 0x1) << 2) | (b3 >> 6),
        frame_length=length,
    )


def frame_offsets(buf: bytes) -> list[int]:
    """Byte offset of every frame, plus a final entry == len(buf)."""
    offsets = [0]
    pos = 0
    while pos < len(buf):
        length = parse_header(buf, pos).frame_length
        if pos + length > len(buf):
            raise AdtsError(f"truncated ADTS frame at byte {pos} ({length} bytes declared)")
        pos += length
        offsets.append(pos)
    return offsets


def split_frames(buf: bytes) -> list[bytes]:
    offsets = frame_offsets(buf)
    return [buf[a:b] for a, b in zip(offsets, offsets[1:])]


def build_frame(payload: bytes, *, object_type: int = STATION_OBJECT_TYPE,
                sample_rate_index: int = STATION_SAMPLE_RATE_INDEX,
                channel_config: int = STATION_CHANNELS) -> bytes:
    length = 7 + len(payload)
    if length >= 1 << 13:
        raise ValueError(f"ADTS frame too long: {length}")
    header = bytes([
        0xFF,
        0xF1,  # MPEG-4, layer 0, protection absent
        (((object_type - 1) & 0x3) << 6) | ((sample_rate_index & 0xF) << 2) | ((channel_config >> 2) & 0x1),
        ((channel_config & 0x3) << 6) | ((length >> 11) & 0x3),
        (length >> 3) & 0xFF,
        ((length & 0x7) << 5) | 0x1F,  # buffer fullness 0x7FF (VBR), high bits
        0xFC,                          # buffer fullness low bits; one raw data block
    ])
    return header + payload


def require_station_format(h: AdtsHeader) -> None:
    got = (h.object_type, h.sample_rate_index, h.channel_config)
    want = (STATION_OBJECT_TYPE, STATION_SAMPLE_RATE_INDEX, STATION_CHANNELS)
    if got != want:
        raise AdtsError(f"ADTS stream is (object type, rate index, channels) {got}, need {want}")
```

`packages/transmitter/src/transmitter/segment.py`:

```python
"""A packed-audio segment: the ID3 timestamp tag + exactly 441 ADTS frames.
`ts_index` is the grid index N for station segments and the loop index k for
fallback segments (spec: fallback segment timestamps are k·d)."""

from typing import Sequence

from transmitter import adts, grid, id3


def assemble(ts_index: int, frames: Sequence[bytes]) -> bytes:
    if len(frames) != grid.SEGMENT_FRAMES:
        raise ValueError(f"a segment is {grid.SEGMENT_FRAMES} frames, got {len(frames)}")
    return id3.timestamp_tag(grid.segment_timestamp(ts_index)) + b"".join(frames)


def parse(data: bytes) -> tuple[int, list[bytes]]:
    ts, tag_len = id3.parse_timestamp_tag(data)
    return ts, adts.split_frames(data[tag_len:])


def segment_key(epoch_id: str, n: int) -> str:
    return f"seg/{epoch_id}/{n}.aac"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS (all).

Run: `./.venv/bin/python -m pytest -q`
Expected: the whole repo suite PASSES — in particular no "import file mismatch" collection error (that would mean the `tests_transmitter` package name collides).

- [ ] **Step 6: Commit**

```bash
git add pytest.ini packages/transmitter
git commit -m "feat(transmitter): scaffold package; grid, ID3 timestamp, ADTS and segment assembly"
```

---

