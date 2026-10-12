### Task 4: Frame layout and FrameStore (the segmenter)

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/layout.py`
- Create: `packages/transmitter/tests_transmitter/test_layout.py`
- Modify: `packages/transmitter/tests_transmitter/helpers.py` (fake frames)

**Interfaces:**
- Consumes: `adts.build_frame/frame_offsets`, `segment.assemble`, `grid.SEGMENT_FRAMES`, `errors.LayoutError`.
- Produces:
  - `PlanRow(seq: int, slug: str, dir: str, key: str, start_frame: int, frames: int, run_start: bool = False, cut_frame: int | None = None)` with `.end_frame` (cut-aware, exclusive), `.to_json() -> dict`, `PlanRow.from_json(d)`.
  - `Piece(key: str | None, offset: int, count: int)` (`key=None` = silence).
  - `validate_rows(rows)`; `pieces(rows, start, stop) -> list[Piece]`; `segment_pieces(rows, n) -> list[Piece]`; `rows_overlapping(rows, start, stop) -> list[PlanRow]`.
  - `FrameStore(shows_dir, silent_frame, *, keep=2)` with `.path(key) -> Path`, `.has(key) -> bool`, `.frame_count(key) -> int`, `.frames(key, offset, count) -> list[bytes]`, `.build_segment(n, rows) -> bytes`.
  - helpers: `fake_frame(key, i) -> bytes`, `write_fake_show(path, key, n_frames)`, `payloads(frames) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests_transmitter/helpers.py`:

```python
from pathlib import Path

from transmitter import adts


def fake_frame(key: str, i: int) -> bytes:
    """A valid ADTS frame whose payload names its show and index."""
    return adts.build_frame(f"{key}:{i}".encode())


def write_fake_show(path: Path, key: str, n_frames: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(fake_frame(key, i) for i in range(n_frames)))


def payloads(frames: list[bytes]) -> list[str]:
    return [f[7:].decode() for f in frames]
```

`tests_transmitter/test_layout.py`:

```python
import pytest

from tests_transmitter.helpers import fake_frame, payloads, write_fake_show
from transmitter import grid, segment
from transmitter.errors import LayoutError
from transmitter.layout import FrameStore, Piece, PlanRow, pieces, rows_overlapping, segment_pieces, validate_rows

F = grid.SEGMENT_FRAMES


def row(seq, key, start, frames, **kw):
    return PlanRow(seq=seq, slug=f"s{seq}", dir=f"s{seq}", key=key, start_frame=start, frames=frames, **kw)


def test_pieces_show_gap_show():
    rows = [row(0, "a", 0, 100), row(1, "b", 187, 50)]
    assert pieces(rows, 90, 200) == [Piece("a", 90, 10), Piece(None, 0, 87), Piece("b", 0, 13)]


def test_pieces_before_the_first_row_and_after_the_last_are_silence():
    rows = [row(0, "a", 10, 5)]
    assert pieces(rows, 0, 20) == [Piece(None, 0, 10), Piece("a", 0, 5), Piece(None, 0, 5)]


def test_pieces_respect_a_cut_row():
    rows = [row(0, "a", 0, 1000, cut_frame=441), row(1, "b", 882, 441, run_start=True)]
    assert rows[0].end_frame == 441
    assert segment_pieces(rows, 1) == [Piece(None, 0, 441)]
    assert segment_pieces(rows, 2) == [Piece("b", 0, 441)]


def test_validate_rows_rejects_overlap_and_unaligned_run_start():
    with pytest.raises(LayoutError, match="overlap"):
        validate_rows([row(0, "a", 0, 100), row(1, "b", 50, 10)])
    with pytest.raises(LayoutError, match="segment-aligned"):
        validate_rows([row(0, "a", 5, 100, run_start=True)])


def test_rows_overlapping():
    rows = [row(0, "a", 0, 100), row(1, "b", 187, 50)]
    assert rows_overlapping(rows, 100, 187) == []
    assert rows_overlapping(rows, 99, 188) == rows


def test_plan_row_json_round_trip():
    r = row(3, "k", 882, 1234, run_start=True, cut_frame=1000)
    assert PlanRow.from_json(r.to_json()) == r


def test_build_segment_spans_show_end_gap_and_next_show(tmp_path):
    write_fake_show(tmp_path / "a.aac", "a", 600)
    write_fake_show(tmp_path / "b.aac", "b", 900)
    rows = [row(0, "a", 0, 600), row(1, "b", 687, 900)]
    store = FrameStore(tmp_path, fake_frame("silence", 0))
    ts, frames = segment.parse(store.build_segment(1, rows))
    assert ts == grid.segment_timestamp(1)
    got = payloads(frames)
    assert got[:159] == [f"a:{i}" for i in range(441, 600)]
    assert got[159:246] == ["silence:0"] * 87
    assert got[246:] == [f"b:{i}" for i in range(0, 195)]


def test_build_segment_refuses_past_the_plan(tmp_path):
    write_fake_show(tmp_path / "a.aac", "a", 500)
    store = FrameStore(tmp_path, fake_frame("silence", 0))
    with pytest.raises(LayoutError, match="past the end of the plan"):
        store.build_segment(1, [row(0, "a", 0, 500)])


def test_build_segment_checks_the_encode_matches_the_plan(tmp_path):
    write_fake_show(tmp_path / "a.aac", "a", 400)
    store = FrameStore(tmp_path, fake_frame("silence", 0))
    with pytest.raises(LayoutError, match="400 frames"):
        store.build_segment(0, [row(0, "a", 0, 900)])


def test_missing_encode_is_a_layout_error(tmp_path):
    store = FrameStore(tmp_path, fake_frame("silence", 0))
    with pytest.raises(LayoutError, match="missing"):
        store.build_segment(0, [row(0, "zz", 0, 900)])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_layout.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transmitter.layout'`.

- [ ] **Step 3: Implement `layout.py`**

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_layout.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): frame layout, plan rows and the frame-count segmenter"
```

---

