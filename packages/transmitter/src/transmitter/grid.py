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
