"""The station stream's frame layout (spec "Per-show encode, frame-count
segmentation"). Plan rows place each show's encoded AAC frames on one
continuous frame line whose frame 0 is at the epoch; frames between rows are
pre-encoded silence; segment N is frames [441N, 441N+441). Grid alignment is by
counting, never by ffmpeg cut points.

Container seam: `FrameStore.build_segment` is the only place frames become a
segment (via `segment.assemble`). Appendix A of the phase-1 plan swaps that
call for an fMP4 fragment writer if the container spike fails.
"""

from collections import OrderedDict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from transmitter import adts, segment
from transmitter.errors import LayoutError
from transmitter.grid import SEGMENT_FRAMES


@dataclass(frozen=True)
class PlanRow:
    seq: int
    slug: str
    dir: str            # package directory name under the station root
    key: str            # file-set key of the package when planned
    start_frame: int
    frames: int         # the encoder's full output for this show
    run_start: bool = False        # first row of a contiguous run (start-up or recovery)
    cut_frame: int | None = None   # set when an outage cut the show (recovery)

    @property
    def end_frame(self) -> int:
        return self.cut_frame if self.cut_frame is not None else self.start_frame + self.frames

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> "PlanRow":
        return cls(**data)


@dataclass(frozen=True)
class Piece:
    key: str | None   # None = pre-encoded silence
    offset: int       # first frame within the show's encode (0 for silence)
    count: int


def validate_rows(rows: Sequence[PlanRow]) -> None:
    prev = None
    for r in rows:
        if r.frames <= 0:
            raise LayoutError(f"plan row {r.seq} ({r.slug}) has no frames")
        if r.cut_frame is not None and not r.start_frame < r.cut_frame <= r.start_frame + r.frames:
            raise LayoutError(f"plan row {r.seq} ({r.slug}) has a cut outside the show")
        if r.run_start and r.start_frame % SEGMENT_FRAMES:
            raise LayoutError(f"plan row {r.seq} ({r.slug}) starts a run but is not segment-aligned")
        if prev is not None and r.start_frame < prev.end_frame:
            raise LayoutError(f"plan rows {prev.seq} and {r.seq} overlap")
        prev = r


def pieces(rows: Sequence[PlanRow], start: int, stop: int) -> list[Piece]:
    """Frames [start, stop) as runs of show frames and silence."""
    if stop < start:
        raise ValueError("stop < start")
    out: list[Piece] = []
    pos = start
    for r in rows:
        if pos >= stop:
            break
        if r.end_frame <= pos:
            continue
        if r.start_frame >= stop:
            break
        if r.start_frame > pos:
            out.append(Piece(None, 0, r.start_frame - pos))
            pos = r.start_frame
        take = min(stop, r.end_frame)
        out.append(Piece(r.key, pos - r.start_frame, take - pos))
        pos = take
    if pos < stop:
        out.append(Piece(None, 0, stop - pos))
    return out


def segment_pieces(rows: Sequence[PlanRow], n: int) -> list[Piece]:
    return pieces(rows, n * SEGMENT_FRAMES, (n + 1) * SEGMENT_FRAMES)


def rows_overlapping(rows: Sequence[PlanRow], start: int, stop: int) -> list[PlanRow]:
    return [r for r in rows if r.start_frame < stop and r.end_frame > start]


class FrameStore:
    """Slices frames out of each show's encode (`render/shows/<key>.aac`).
    Keeps the `keep` most recently used encodes in memory (a 3 h show is
    ~170 MB of ADTS)."""

    def __init__(self, shows_dir: Path, silent_frame: bytes, *, keep: int = 2):
        self.shows_dir = Path(shows_dir)
        self.silent_frame = silent_frame
        self._keep = keep
        self._cache: OrderedDict[str, tuple[bytes, list[int]]] = OrderedDict()

    def path(self, key: str) -> Path:
        return self.shows_dir / f"{key}.aac"

    def has(self, key: str) -> bool:
        return self.path(key).exists()

    def _load(self, key: str) -> tuple[bytes, list[int]]:
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            return hit
        try:
            data = self.path(key).read_bytes()
        except FileNotFoundError as exc:
            raise LayoutError(f"show encode {key} is missing") from exc
        entry = (data, adts.frame_offsets(data))
        self._cache[key] = entry
        while len(self._cache) > self._keep:
            self._cache.popitem(last=False)
        return entry

    def frame_count(self, key: str) -> int:
        return len(self._load(key)[1]) - 1

    def frames(self, key: str, offset: int, count: int) -> list[bytes]:
        data, offsets = self._load(key)
        if offset < 0 or offset + count > len(offsets) - 1:
            raise LayoutError(f"show encode {key} has {len(offsets) - 1} frames; "
                              f"asked for [{offset}, {offset + count})")
        return [data[offsets[i]:offsets[i + 1]] for i in range(offset, offset + count)]

    def build_segment(self, n: int, rows: Sequence[PlanRow]) -> bytes:
        if not rows or (n + 1) * SEGMENT_FRAMES > rows[-1].end_frame:
            raise LayoutError(f"segment {n} extends past the end of the plan")
        for r in rows_overlapping(rows, n * SEGMENT_FRAMES, (n + 1) * SEGMENT_FRAMES):
            have = self.frame_count(r.key)
            if have != r.frames:
                raise LayoutError(f"show encode {r.key} ({r.slug}) has {have} frames; "
                                  f"the plan says {r.frames}")
        parts: list[bytes] = []
        for p in segment_pieces(rows, n):
            if p.key is None:
                parts.extend([self.silent_frame] * p.count)
            else:
                parts.extend(self.frames(p.key, p.offset, p.count))
        return segment.assemble(n, parts)
