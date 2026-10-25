import json
import logging
from types import SimpleNamespace

from tests_transmitter.helpers import E
from transmitter import grid, history
from transmitter.history import AiredRow, Recency, append_aired, aired_rows_due, load_aired, recency
from transmitter.layout import PlanRow
from transmitter.workspace import Epoch, Workspace

EP = Epoch("etest", E)
S = grid.SEGMENT_FRAMES


def _row(seq, start, frames=441, **kw):
    return PlanRow(seq=seq, slug=kw.pop("slug", f"s{seq}"), dir="d", key="k", start_frame=start, frames=frames, **kw)


def _end_us(frame):
    return E + grid.frame_to_us(frame)


def test_only_published_and_past_rows_are_appended(tmp_path):
    ws = Workspace(tmp_path)
    rows = [_row(0, 0), _row(1, S), _row(2, 2 * S)]
    # published through segment 1 -> rows 0 and 1 are published; row 2 is not
    assert append_aired(ws, EP, rows, 1, _end_us(10 * S)) == 2
    assert [r.start_frame for r in load_aired(ws)] == [0, S]
    # published, but row 1 has not finished airing yet
    ws2 = Workspace(tmp_path / "b")
    assert append_aired(ws2, EP, rows, 1, _end_us(2 * S) - 1) == 1
    assert aired_rows_due(rows, EP, None, _end_us(10 * S)) == []


def test_append_is_idempotent_across_restarts(tmp_path):
    ws = Workspace(tmp_path)
    rows = [_row(0, 0), _row(1, S)]
    assert append_aired(ws, EP, rows, 1, _end_us(10 * S)) == 2
    assert append_aired(ws, EP, rows, 1, _end_us(10 * S)) == 0
    assert len(ws.aired_path.read_text().splitlines()) == 2


def test_a_cut_row_records_its_cut_end(tmp_path):
    ws = Workspace(tmp_path)
    rows = [_row(0, 0, frames=3 * S, cut_frame=S)]
    assert append_aired(ws, EP, rows, 0, _end_us(10 * S)) == 1
    (a,) = load_aired(ws)
    assert a.end_frame == S and a.end == grid.us_to_iso(_end_us(S))
    # the uncut end (3*S) lies beyond segment 0; the cut end is what counts
    assert aired_rows_due(rows, EP, 0, _end_us(10 * S))[0].end_frame == S


def test_backfill_from_a_phase1_plan(tmp_path):
    ws = Workspace(tmp_path)
    rows = [PlanRow(seq=0, slug="band-2005-11-01", dir="band-2005-11-01", key="k", start_frame=0, frames=S)]
    assert not ws.aired_path.exists()
    assert append_aired(ws, EP, rows, 0, _end_us(5 * S)) == 1
    (a,) = load_aired(ws)
    assert a.kind == "show" and a.package == "band-2005-11-01" and a.epoch_id == "etest"


def test_corrupt_line_is_skipped(tmp_path, caplog):
    ws = Workspace(tmp_path)
    append_aired(ws, EP, [_row(0, 0)], 0, _end_us(5 * S))
    with open(ws.aired_path, "a") as f:
        f.write("{not json\n")
        f.write(json.dumps({**AiredRow.to_json(load_aired(ws)[0]), "start_frame": S, "future": 1}) + "\n")
    with caplog.at_level(logging.WARNING):
        got = load_aired(ws)
    assert [r.start_frame for r in got] == [0, S]
    assert "skipped" in caplog.text


def test_recency_counts_persisted_unaired_rows(tmp_path):
    meta = {"p0": ("Band A", "1977-05-08"), "p1": ("Band B", "1990-01-01")}
    aired = [AiredRow.from_json({"epoch_id": "etest", "start_frame": 0, "end_frame": S, "kind": "show",
                                 "slug": "p0", "package": "p0", "start": grid.us_to_iso(E)})]
    rows = [_row(0, 0, slug="p0"), _row(1, S, slug="p1"),
            _row(2, 2 * S, slug="clip", kind="interstitial")]
    r = recency(aired, rows, EP, "UTC", lambda p: meta.get(p, (None, None)))
    assert len(r.uses) == 3                                    # row 0 deduped by identity
    assert r.last_aired_us("p1") == E + grid.frame_to_us(S)   # unaired, but persisted
    assert r.last_aired_us("zzz") is None
    assert r.last_used_us("clip") == E + grid.frame_to_us(2 * S)
    assert r.last_aired_us("clip") is None
    assert sorted(r.artist_years_on(grid.us_to_iso(E)[:10])) == [("Band A", 1977), ("Band B", 1990)]


def test_artists_on_uses_the_clock_timezone(tmp_path):
    # 2026-01-02 02:00Z is 21:00 on 2026-01-01 in New York
    epoch = Epoch("etest", grid.iso_to_us("2026-01-02T02:00:00Z"))
    r = recency([], [_row(0, 0, slug="p0")], epoch, "America/New_York", lambda p: ("Band A", "1977-05-08"))
    assert r.artists_on("2026-01-01") == ["Band A"]
    assert r.artists_on("2026-01-02") == []
    piece = SimpleNamespace(kind="show", slug="p9", package="p9", artist="Band Z", year=1980)
    r2 = r.with_piece(piece, epoch.epoch_us + 5, "2026-01-02")
    assert r2.artists_on("2026-01-02") == ["Band Z"] and r.artists_on("2026-01-02") == []
    assert r2.last_aired_us("p9") == epoch.epoch_us + 5
