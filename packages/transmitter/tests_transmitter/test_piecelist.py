import json
import os
import time
from pathlib import Path

import pytest

from tests_transmitter.helpers import NOW, build_package, make_root, make_station, set_age
from transmitter import alerts, concert, pipeline, piecelist
from transmitter.clock import IMPLICIT_CLOCK
from transmitter.concert import NeededPiece, piece_id
from transmitter.station import Ineligible, evaluate
from transmitter.workspace import Workspace

NOW_S = NOW / 1e6


def _needed(*texts: str) -> list[NeededPiece]:
    return [NeededPiece(piece_id(t), t, "time") for t in texts]


def _folder(tmp_path: Path) -> Path:
    f = tmp_path / "pieces"
    f.mkdir()
    return f


def _station_with_pieces(tmp_path, **kw):
    st, logs = make_station(tmp_path, **kw)
    folder = piecelist.pieces_folder(st.cfg)
    folder.mkdir(parents=True)
    return st, logs, folder


def _txts(folder: Path) -> set[str]:
    return {p.name for p in folder.glob("piece-*.txt")}


def test_ineligible_records_carry_the_artist(tmp_path):
    pkg = build_package(make_root(tmp_path), voiced=False, artist="Band")
    result = evaluate(pkg, now_s=NOW_S, quiet_s=0.0)
    assert isinstance(result, Ineligible) and result.artist == "Band"
    bad = build_package(make_root(tmp_path / "x"), voiced=False)
    (bad / "manifest.json").write_text("[]")
    assert evaluate(bad, now_s=NOW_S, quiet_s=0.0).artist is None


def test_writes_missing_texts_only(tmp_path):
    folder = _folder(tmp_path)
    old = _needed("with Old.")[0]
    (folder / f"piece-{old.id}.txt").write_text("with Old.")
    os.utime(folder / f"piece-{old.id}.txt", (1000, 1000))
    needed = [old, *_needed("with New.", "Ünï 2")]
    assert piecelist.write_texts(folder, needed, now_s=NOW_S) == (2, 0)
    assert (folder / f"piece-{old.id}.txt").stat().st_mtime == 1000
    for p in needed[1:]:
        assert (folder / f"piece-{p.id}.txt").read_bytes() == p.text.encode()
    assert not [p for p in folder.iterdir() if p.name.startswith(".")]
    assert piecelist.write_texts(folder, needed, now_s=NOW_S) == (0, 0)


def test_never_creates_the_folder(tmp_path):
    folder = tmp_path / "pieces"
    with pytest.raises(OSError):
        piecelist.write_texts(folder, _needed("a"), now_s=NOW_S)
    assert not folder.exists()


def test_caps_writes_per_step(tmp_path):
    folder = _folder(tmp_path)
    needed = _needed(*(f"text {i}" for i in range(300)))
    assert piecelist.write_texts(folder, needed, now_s=NOW_S) == (250, 50)
    assert piecelist.write_texts(folder, needed, now_s=NOW_S) == (50, 0)
    assert len(_txts(folder)) == 300


def test_dot_temps_are_never_present(tmp_path):
    folder = _folder(tmp_path)
    (folder / ".piece-aaaaaaaaaaaa.mp3.1-x.tmp").write_bytes(b"x")
    (folder / ".piece-aaaaaaaaaaaa.mp3").write_bytes(b"x")
    os.utime(folder / ".piece-aaaaaaaaaaaa.mp3", (1000, 1000))
    assert piecelist.present_ids(folder, now_s=NOW_S, quiet_s=0) == frozenset()


def test_old_dot_temps_are_cleaned_young_ones_kept(tmp_path):
    folder = _folder(tmp_path)
    old, young, emcee = (folder / ".piece-x.txt.t.tmp", folder / ".piece-y.txt.t.tmp",
                         folder / ".piece-x.mp3.t.tmp")
    for p in (old, young, emcee):
        p.write_text("x")
    os.utime(old, (NOW_S - 7200, NOW_S - 7200))
    os.utime(emcee, (NOW_S - 7200, NOW_S - 7200))
    os.utime(young, (NOW_S - 60, NOW_S - 60))
    piecelist.write_texts(folder, [], now_s=NOW_S)
    assert not old.exists() and young.exists() and emcee.exists()


def test_presence_and_counts_ignore_clutter(tmp_path):
    st, _, folder = _station_with_pieces(tmp_path)
    needed = _needed("a one", "b two", "c three", "d four")
    piecelist.save_needed(st.ws, needed, now_us=NOW)
    a, b, c, d = (p.id for p in needed)
    (folder / "notes.txt").write_text("hi")
    (folder / f"piece-{a}.mp3").write_bytes(b"audio")                 # present
    (folder / f"piece-{b}.mp3").write_bytes(b"")                      # zero-byte
    (folder / f"piece-{c}.mp3").write_bytes(b"audio")                 # young
    (folder / "piece-zzzz.failed").write_text("{}")                   # garbage name
    (folder / f"piece-{d}.failed").mkdir()                            # a subdir, not a file
    (folder / "sub").mkdir()
    for n in (a, b):
        os.utime(folder / f"piece-{n}.mp3", (NOW_S - 600, NOW_S - 600))
    os.utime(folder / f"piece-{c}.mp3", (NOW_S - 5, NOW_S - 5))
    assert piecelist.present_ids(folder, now_s=NOW_S, quiet_s=60) == {a}
    assert piecelist.failed_ids(folder) == frozenset()
    assert piecelist.counts(st.ws, folder, now_s=NOW_S, quiet_s=60) == \
        piecelist.PieceCounts(needed=4, present=1, failed=0, missing=3)


def test_failed_without_mp3_counts_failed(tmp_path):
    st, _, folder = _station_with_pieces(tmp_path)
    needed = _needed("a one", "b two")
    piecelist.save_needed(st.ws, needed, now_us=NOW)
    (folder / f"piece-{needed[0].id}.failed").write_text("{}")
    assert piecelist.failed_ids(folder) == {needed[0].id}
    assert piecelist.counts(st.ws, folder, now_s=NOW_S, quiet_s=0) == \
        piecelist.PieceCounts(needed=2, present=0, failed=1, missing=1)
    assert piecelist.counts(st.ws, None, now_s=NOW_S, quiet_s=0) == \
        piecelist.PieceCounts(needed=2, present=0, failed=0, missing=2)


def test_load_needed_never_raises(tmp_path):
    ws = Workspace(tmp_path / "tx")
    assert piecelist.load_needed(ws) is None
    assert piecelist.counts(ws, None, now_s=NOW_S, quiet_s=0) is None
    ws.root.mkdir()
    for junk in ("{not json", "[]", '{"pieces": 3}', '{"pieces": [{"id": 1}]}'):
        ws.pieces_needed_path.write_text(junk)
        assert piecelist.load_needed(ws) is None


def test_save_needed_rewrites_only_on_change(tmp_path):
    ws = Workspace(tmp_path / "tx")
    needed = _needed("a one", "b two")
    piecelist.save_needed(ws, needed, now_us=NOW)
    first = ws.pieces_needed_path.read_bytes()
    os.utime(ws.pieces_needed_path, (1000, 1000))
    piecelist.save_needed(ws, needed, now_us=NOW + 5_000_000)
    assert ws.pieces_needed_path.stat().st_mtime == 1000 and ws.pieces_needed_path.read_bytes() == first
    piecelist.save_needed(ws, needed[:1], now_us=NOW + 9_000_000)
    assert piecelist.load_needed(ws) == needed[:1]
    assert ws.pieces_needed_path.read_bytes() != first
    assert piecelist.load_needed(ws) is not None


def test_plan_step_writes_the_list_including_ineligible_artists(tmp_path):
    st, _, folder = _station_with_pieces(
        tmp_path, packages=[{"slug": "band-2005-11-01"},
                            {"slug": "new-2005-11-02", "voiced": False, "artist": "New Artist"}])
    pipeline.plan_step(st, NOW)
    pid = piece_id("with New Artist.")
    assert (folder / f"piece-{pid}.txt").read_text() == "with New Artist."
    assert (folder / f"piece-{piece_id('with Band.')}.txt").exists()
    listed = piecelist.load_needed(st.ws)
    assert pid in {p.id for p in listed}
    assert _txts(folder) == {f"piece-{p.id}.txt" for p in listed}


def test_plan_step_writes_the_list_even_when_already_covered(tmp_path):
    st, _, folder = _station_with_pieces(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    for p in folder.iterdir():
        p.unlink()
    st.ws.pieces_needed_path.unlink()
    assert pipeline.plan_step(st, NOW) == rows            # the early-return path
    assert _txts(folder) and st.ws.pieces_needed_path.exists()


def test_plan_step_with_no_pieces_folder_writes_no_texts_and_no_alert(tmp_path, monkeypatch):
    fired = []
    monkeypatch.setattr(alerts, "alert", lambda code, msg: fired.append(code))
    st, logs = make_station(tmp_path)
    pipeline.plan_step(st, NOW)
    assert not piecelist.pieces_folder(st.cfg).exists()
    assert "announce-pieces" not in fired and not [m for m in logs if "piece list" in m]
    assert piecelist.load_needed(st.ws)                    # the workspace list is still kept


def test_a_write_failure_alerts_and_planning_goes_on(tmp_path, monkeypatch):
    fired = []
    monkeypatch.setattr(alerts, "alert", lambda code, msg: fired.append(code))
    plain = pipeline.plan_step(make_station(tmp_path / "probe")[0], NOW)
    st, logs, folder = _station_with_pieces(tmp_path)

    def boom(*a, **k):
        raise OSError(5, "input/output error")
    monkeypatch.setattr(piecelist, "write_texts", boom)
    rows = pipeline.plan_step(st, NOW)
    assert [(r.slug, r.start_frame, r.end_frame) for r in rows] == \
        [(r.slug, r.start_frame, r.end_frame) for r in plain]
    assert fired == ["announce-pieces"]
    assert any(m.startswith("piece list: ") for m in logs)


def test_any_exception_in_the_writer_is_contained(tmp_path, monkeypatch):
    fired = []
    monkeypatch.setattr(alerts, "alert", lambda code, msg: fired.append(code))
    st, _, _ = _station_with_pieces(tmp_path)
    monkeypatch.setattr(concert, "needed_pieces", lambda *a, **k: 1 / 0)
    assert pipeline.plan_step(st, NOW)
    assert fired == ["announce-pieces"]


def test_an_unencodable_artist_does_not_poison_the_list(tmp_path):
    st, _, folder = _station_with_pieces(
        tmp_path, packages=[{"slug": "band-2005-11-01", "artist": "Bad\ud800Name"},
                            {"slug": "ok-2005-11-02", "artist": "Good Band"}])
    pipeline.plan_step(st, NOW)
    assert (folder / f"piece-{piece_id('with Good Band.')}.txt").exists()


def test_the_list_is_written_with_announcements_switched_off(tmp_path):
    st, _, folder = _station_with_pieces(tmp_path)
    assert not st.ws.announce_path.exists()
    pipeline.plan_step(st, NOW)
    assert _txts(folder)


def test_read_only_views_write_no_texts(tmp_path):
    from transmitter import service
    st, _, folder = _station_with_pieces(tmp_path)
    pipeline.plan_step(st, NOW)
    for p in folder.iterdir():
        p.unlink()
    st.ws.pieces_needed_path.unlink()
    service.schedule_report(st.cfg, NOW)
    service.status_lines(st.cfg, NOW)
    service.library_report(st.cfg, NOW)
    assert list(folder.iterdir()) == [] and not st.ws.pieces_needed_path.exists()
