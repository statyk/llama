"""audio_reuse (spec 5.4): pairing existing audio with source files by index,
and the per-file verification that falls back to a download."""
import json
import shutil
from pathlib import Path

import pytest

from helpers import (
    ReuseIA,
    audio_files,
    fake_audio,
    fake_source,
    packaged_reuse_show,
    patch_fake_durations,
    reuse_show,
)
from llama.audio_reuse import ASIDE_DIR, ReusePlan, plan_reuse, reuse_into
from llama.stages.package import DURATION_TOLERANCE_S, build_package
from llama.workspace import drop_stage_artifacts, write_artifact

OLD = (("A", "a.mp3", 300.0), ("B", "b.mp3", 400.0), ("X", "x.mp3", 500.0))


def _station(tmp_path: Path, ws) -> Path:
    """The delivered copy: the package directory as `deliver` copies it."""
    out = tmp_path / "station" / ws.dir.name
    shutil.copytree(ws.package_dir, out)
    return out


def test_plan_pairs_library_and_station_by_index(tmp_path, monkeypatch):
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*OLD))
    station = _station(tmp_path, ws)
    plan = plan_reuse(ws, station)
    assert plan == ReusePlan(
        library_names=("01 - A.mp3", "02 - B.mp3", "03 - X.mp3"),
        library={"a.mp3": "01 - A.mp3", "b.mp3": "02 - B.mp3", "x.mp3": "03 - X.mp3"},
        station={"a.mp3": station / "audio" / "01 - A.mp3",
                 "b.mp3": station / "audio" / "02 - B.mp3",
                 "x.mp3": station / "audio" / "03 - X.mp3"})
    assert plan_reuse(ws, None).station == {}


def test_pairing_is_by_index_and_any_title_mismatch_drops_the_copy(tmp_path, monkeypatch):
    # Review Focus 5: two tracks share a title at different indexes, and the
    # station manifest has the right length but one retitled index.
    patch_fake_durations(monkeypatch)
    show = reuse_show(("Jam", "j1.mp3", 300.0), ("B", "b.mp3", 400.0), ("Jam", "j2.mp3", 301.0))
    ws = packaged_reuse_show(tmp_path, show)
    station = _station(tmp_path, ws)
    m = json.loads((station / "manifest.json").read_text())
    m["tracks"][1]["title"] = "Bee"
    write_artifact(station / "manifest.json", m)
    plan = plan_reuse(ws, station)
    assert plan.library == {"j1.mp3": "01 - Jam.mp3", "b.mp3": "02 - B.mp3",
                            "j2.mp3": "03 - Jam.mp3"}
    assert plan.station == {}


def test_a_copy_of_another_length_contributes_nothing(tmp_path, monkeypatch):
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*OLD))
    station = _station(tmp_path, ws)
    write_artifact(ws.show, reuse_show(*OLD, ("Y", "y.mp3", 200.0)))
    plan = plan_reuse(ws, station)
    assert plan.library == {} and plan.station == {}
    assert plan.library_names == ("01 - A.mp3", "02 - B.mp3", "03 - X.mp3")


@pytest.mark.parametrize("show_json", [None, "{not json"])
def test_plan_without_show_json_pairs_nothing(tmp_path, monkeypatch, show_json):
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*OLD))
    station = _station(tmp_path, ws)
    if show_json is None:
        ws.show.unlink()
    else:
        ws.show.write_text(show_json)
    plan = plan_reuse(ws, station)
    assert plan.library == {} and plan.station == {}
    assert plan.library_names == ("01 - A.mp3", "02 - B.mp3", "03 - X.mp3")   # still read


@pytest.mark.parametrize("damage", ["missing", "not json", "no tracks", "track without title",
                                    "a path, not a name"])
def test_unreadable_station_manifest_contributes_nothing(tmp_path, monkeypatch, damage):
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*OLD))
    station = _station(tmp_path, ws)
    path = station / "manifest.json"
    m = json.loads(path.read_text())
    if damage == "missing":
        path.unlink()
    elif damage == "not json":
        path.write_text("{")
    elif damage == "no tracks":
        del m["tracks"]; write_artifact(path, m)
    elif damage == "track without title":
        del m["tracks"][0]["title"]; write_artifact(path, m)
    else:
        m["tracks"][0]["filename"] = "../01 - A.mp3"; write_artifact(path, m)
    plan = plan_reuse(ws, station)
    assert plan.station == {}
    assert plan.library == {"a.mp3": "01 - A.mp3", "b.mp3": "02 - B.mp3", "x.mp3": "03 - X.mp3"}


def test_unreadable_library_manifest_has_no_names(tmp_path, monkeypatch):
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*OLD))
    (ws.package_dir / "manifest.json").write_text("{")
    plan = plan_reuse(ws, None)
    assert plan.library_names is None and plan.library == {}


def test_duration_mismatch_or_unreadable_falls_back_to_download(tmp_path, monkeypatch):
    patch_fake_durations(monkeypatch)
    old = (*OLD, ("C", "c.mp3", 200.0))
    ws = packaged_reuse_show(tmp_path, reuse_show(*old))
    audio = ws.package_dir / "audio"
    (audio / "01 - A.mp3").write_bytes(fake_audio("a.mp3", 300.0 + DURATION_TOLERANCE_S + 1))
    (audio / "02 - B.mp3").write_bytes(b"no readable duration")
    (audio / "03 - X.mp3").write_bytes(fake_audio("x.mp3", 500.0 + DURATION_TOLERANCE_S))  # at the edge
    plan = plan_reuse(ws, None)
    new = reuse_show(("Crowd", "s.mp3", 20.0, True), *old)
    drop_stage_artifacts(ws, "package"); write_artifact(ws.show, new)
    ia = ReuseIA({**{t.filename: t.duration_sec for t in new.tracks}, "c.mp3": None})
    build_package(ws, ia, new, reuse=plan)
    # a: mismatch; b: unreadable; c: no cached metadata length; s: new, in no copy.
    assert ia.downloads == ["s.mp3", "a.mp3", "b.mp3", "c.mp3"]
    names = audio_files(ws)
    assert sorted(names) == ["01 - Crowd.mp3", "02 - A.mp3", "03 - B.mp3", "04 - X.mp3", "05 - C.mp3"]
    assert {n: fake_source(ws.package_dir / "audio" / n) for n in names} == {
        "01 - Crowd.mp3": "s.mp3", "02 - A.mp3": "a.mp3", "03 - B.mp3": "b.mp3",
        "04 - X.mp3": "x.mp3", "05 - C.mp3": "c.mp3"}


def test_station_copy_used_when_the_library_was_purged(tmp_path, monkeypatch):
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*OLD))
    station = _station(tmp_path, ws)
    station_bytes = {p.name: p.read_bytes() for p in (station / "audio").iterdir()}
    for p in (ws.package_dir / "audio").iterdir():      # deliver purged the library audio
        p.unlink()
    plan = plan_reuse(ws, station)
    drop_stage_artifacts(ws, "package")                 # an unchanged list, re-packaged
    show = reuse_show(*OLD)
    ia = ReuseIA({t.filename: t.duration_sec for t in show.tracks})
    build_package(ws, ia, show, reuse=plan)
    assert ia.downloads == []
    assert {n: fake_source(ws.package_dir / "audio" / n) for n in audio_files(ws)} == {
        "01 - A.mp3": "a.mp3", "02 - B.mp3": "b.mp3", "03 - X.mp3": "x.mp3"}
    assert not (ws.dir / ASIDE_DIR).exists()
    # the station copy is read, never moved or changed
    assert {p.name: p.read_bytes() for p in (station / "audio").iterdir()} == station_bytes


def test_reuse_into_tries_the_library_before_the_station(tmp_path, monkeypatch):
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*OLD))
    lib = ws.dir / ASIDE_DIR / "01 - A.mp3"
    lib.parent.mkdir(parents=True)
    lib.write_bytes(fake_audio("a.mp3", 300.0) + b"library")
    sta = tmp_path / "st" / "01 - A.mp3"
    sta.parent.mkdir(parents=True)
    sta.write_bytes(fake_audio("a.mp3", 300.0) + b"station")
    plan = ReusePlan(library_names=None, library={"a.mp3": "01 - A.mp3"}, station={"a.mp3": sta})
    dest = tmp_path / "out" / "01 - A.mp3"
    dest.parent.mkdir()
    assert reuse_into(dest, "a.mp3", 300.0, plan, ws, tolerance=5.0) == "library"
    assert dest.read_bytes().endswith(b"library") and lib.exists()      # copied, not moved
    lib.write_bytes(fake_audio("a.mp3", 900.0))                           # library now fails
    dest.unlink()
    assert reuse_into(dest, "a.mp3", 300.0, plan, ws, tolerance=5.0) == "station"
    assert dest.read_bytes().endswith(b"station")
    dest.unlink()
    assert reuse_into(dest, "a.mp3", None, plan, ws, tolerance=5.0) is None
    assert reuse_into(dest, "zzz.mp3", 300.0, plan, ws, tolerance=5.0) is None
    assert not dest.exists() and sorted(p.name for p in dest.parent.iterdir()) == []
