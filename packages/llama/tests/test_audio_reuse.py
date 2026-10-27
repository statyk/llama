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
                 "x.mp3": station / "audio" / "03 - X.mp3"},
        identifier="gd73")
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


def test_set_aside_refuses_when_an_aside_already_exists(tmp_path, monkeypatch):
    from llama.audio_reuse import set_aside
    from llama.errors import LlamaError
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*OLD))
    stale = ws.dir / ASIDE_DIR / "03 - X.mp3"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"ORIGINAL")
    audio = audio_files(ws)
    with pytest.raises(LlamaError, match="audio aside already exists"):
        set_aside(ws)
    assert audio_files(ws) == audio and stale.read_bytes() == b"ORIGINAL"


def _set_manifest_identifier(manifest: Path, ident) -> None:
    data = json.loads(manifest.read_text())
    if ident is None:
        data["source"].pop("identifier", None)
    else:
        data["source"]["identifier"] = ident
    manifest.write_text(json.dumps(data))


@pytest.mark.parametrize("ident", ["gd73-other-taper", None, ""])
def test_a_station_manifest_from_another_or_unnamed_item_pairs_nothing(tmp_path, monkeypatch, ident):
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*OLD))
    station = _station(tmp_path, ws)
    _set_manifest_identifier(station / "manifest.json", ident)
    plan = plan_reuse(ws, station)
    assert plan.station == {} and plan.library      # the library copy is of the same item


@pytest.mark.parametrize("ident", ["gd73-other-taper", None])
def test_a_library_manifest_from_another_or_unnamed_item_pairs_nothing(tmp_path, monkeypatch, ident):
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*OLD))
    station = _station(tmp_path, ws)
    _set_manifest_identifier(ws.package_dir / "manifest.json", ident)
    plan = plan_reuse(ws, station)
    assert plan.library == {} and plan.station      # the station copy is of the same item
    assert plan.library_names == ("01 - A.mp3", "02 - B.mp3", "03 - X.mp3")   # the aside rule still sees the names


# --- strict station reuse and the held-outcome anchor (bulk-apply Task 8) -------------

def _delivered_purged(tmp_path: Path, old=OLD):
    """A packaged show delivered to the station, its library audio purged."""
    ws = packaged_reuse_show(tmp_path, reuse_show(*old))
    station = _station(tmp_path, ws)
    for p in (ws.package_dir / "audio").iterdir():      # deliver purged the library audio
        p.unlink()
    return ws, station


def test_strict_downloads_only_files_the_station_never_held(tmp_path, monkeypatch, caplog):
    # Review Focus 3: the fixed list adds a newly kept short file.
    import logging
    patch_fake_durations(monkeypatch)
    ws, station = _delivered_purged(tmp_path)
    plan = plan_reuse(ws, station, strict=True)
    assert plan.strict is True and plan.station_problem is None
    new = reuse_show(("A", "a.mp3", 300.0), ("Jam", "s.mp3", 20.0, True), *OLD[1:])
    drop_stage_artifacts(ws, "package"); write_artifact(ws.show, new)
    ia = ReuseIA({t.filename: t.duration_sec for t in new.tracks})
    tally: dict[str, int] = {}
    with caplog.at_level(logging.INFO, logger="llama"):
        build_package(ws, ia, new, reuse=plan, tally=tally)
    assert ia.downloads == ["s.mp3"]
    assert tally == {"reused": 3, "downloaded": 1}
    assert "audio reused 3, downloaded 1" in [r.getMessage() for r in caplog.records]
    assert {n: fake_source(ws.package_dir / "audio" / n) for n in audio_files(ws)} == {
        "01 - A.mp3": "a.mp3", "02 - Jam.mp3": "s.mp3", "03 - B.mp3": "b.mp3",
        "04 - X.mp3": "x.mp3"}


def test_strict_refuses_a_source_with_no_metadata_length(tmp_path, monkeypatch):
    from llama.audio_reuse import StationUnpaired
    patch_fake_durations(monkeypatch)
    ws, station = _delivered_purged(tmp_path)
    plan = plan_reuse(ws, station, strict=True)
    drop_stage_artifacts(ws, "package")
    show = reuse_show(*OLD)
    ia = ReuseIA({"a.mp3": 300.0, "b.mp3": None, "x.mp3": 500.0})
    with pytest.raises(StationUnpaired) as exc:
        build_package(ws, ia, show, reuse=plan)
    assert str(exc.value) == "s: station copy does not pair: b.mp3 has no metadata length"
    assert ia.downloads == []


def test_strict_refuses_a_paired_copy_failing_its_length_check_in_the_build(tmp_path, monkeypatch):
    from llama.audio_reuse import StationUnpaired
    patch_fake_durations(monkeypatch)
    ws, station = _delivered_purged(tmp_path)
    (station / "audio" / "02 - B.mp3").write_bytes(fake_audio("b.mp3", 400.0 + DURATION_TOLERANCE_S + 1))
    plan = plan_reuse(ws, station, strict=True)
    drop_stage_artifacts(ws, "package")
    show = reuse_show(*OLD)
    ia = ReuseIA({t.filename: t.duration_sec for t in show.tracks})
    with pytest.raises(StationUnpaired) as exc:
        build_package(ws, ia, show, reuse=plan)
    assert str(exc.value) == "s: station copy does not pair: b.mp3 failed its length check"
    assert ia.downloads == []


def test_strict_refuses_another_recording_in_the_build(tmp_path, monkeypatch):
    from llama.audio_reuse import StationUnpaired
    patch_fake_durations(monkeypatch)
    ws, station = _delivered_purged(tmp_path)
    plan = plan_reuse(ws, station, strict=True)
    drop_stage_artifacts(ws, "package")
    show = reuse_show(*OLD).model_copy(update={"identifier": "gd73-other-taper"})
    ia = ReuseIA({t.filename: t.duration_sec for t in show.tracks})
    with pytest.raises(StationUnpaired) as exc:
        build_package(ws, ia, show, reuse=plan)
    assert str(exc.value) == "s: station copy does not pair: a different recording"
    assert ia.downloads == []


def test_check_pairs_strict_only(tmp_path, monkeypatch):
    from llama.audio_reuse import StationUnpaired, check_pairs
    from llama.station_mark import StationUnreadable
    patch_fake_durations(monkeypatch)
    ws, station = _delivered_purged(tmp_path)
    m = json.loads((station / "manifest.json").read_text())
    m["tracks"][0]["title"] = "Retitled"
    write_artifact(station / "manifest.json", m)
    check_pairs(plan_reuse(ws, station), ws)                 # not strict: nothing to check
    with pytest.raises(StationUnpaired) as exc:
        check_pairs(plan_reuse(ws, station, strict=True), ws)
    assert str(exc.value) == "s: station copy does not pair: no copy pairs"
    plan = plan_reuse(ws, None, strict=True)
    assert plan.station_problem == "no delivery_path in config"
    with pytest.raises(StationUnreadable) as exc2:
        check_pairs(plan, ws)
    assert str(exc2.value) == "s: station copy unreadable: no delivery_path in config"


def test_strict_plan_records_why_the_station_copy_is_unreadable(tmp_path, monkeypatch):
    from llama.audio_reuse import check_pairs
    from llama.station_mark import StationUnreadable
    patch_fake_durations(monkeypatch)
    ws, station = _delivered_purged(tmp_path)
    (station / "manifest.json").write_text("{")
    plan = plan_reuse(ws, station, strict=True)
    assert plan.station == {} and plan.station_problem.startswith("invalid JSON in ")
    with pytest.raises(StationUnreadable, match=r"^s: station copy unreadable: invalid JSON in "):
        check_pairs(plan, ws)
    shutil.rmtree(station)
    plan = plan_reuse(ws, station, strict=True)
    assert plan.station_problem == f"no directory {station}"
    assert plan_reuse(ws, station).station_problem is None    # not strict: no problem recorded


def test_strict_passes_when_the_library_copy_pairs(tmp_path, monkeypatch):
    from llama.audio_reuse import check_pairs
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*OLD))    # library audio still present
    plan = plan_reuse(ws, tmp_path / "station" / "nowhere", strict=True)
    assert plan.station == {} and plan.station_problem is not None
    _station(tmp_path, ws)
    m = json.loads((tmp_path / "station" / "s" / "manifest.json").read_text())
    m["tracks"][0]["title"] = "Retitled"
    write_artifact(tmp_path / "station" / "s" / "manifest.json", m)
    plan = plan_reuse(ws, tmp_path / "station" / "s", strict=True)
    assert plan.station == {} and plan.library
    check_pairs(plan, ws)                                    # the library copy pairs: no refusal


def test_anchor_is_written_once(tmp_path, monkeypatch):
    from llama.audio_reuse import ANCHOR, write_anchor_if_absent
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*OLD))
    assert write_anchor_if_absent(ws) is True
    first = (ws.dir / ANCHOR).read_bytes()
    data = json.loads(first)
    assert data["identifier"] == "gd73"
    assert data["tracks"] == [{"filename": "a.mp3", "title": "A"}, {"filename": "b.mp3", "title": "B"},
                              {"filename": "x.mp3", "title": "X"}]
    assert isinstance(data["written_at"], str) and data["written_at"]
    write_artifact(ws.show, reuse_show(("Z", "z.mp3", 1.0)))
    assert write_anchor_if_absent(ws) is False
    assert (ws.dir / ANCHOR).read_bytes() == first


def _retitle(ws, titles=("A2", "B2", "X2")):
    """A held commit: show.json carries a retitled list and the library manifest is gone."""
    new = reuse_show(*((t, f, s) for t, (_old, f, s) in zip(titles, OLD)))
    write_artifact(ws.show, new)
    (ws.package_dir / "manifest.json").unlink()
    return new


def test_anchor_pairs_after_a_held_commit(tmp_path, monkeypatch):
    from llama.audio_reuse import ANCHOR, write_anchor_if_absent
    patch_fake_durations(monkeypatch)
    ws, station = _delivered_purged(tmp_path)
    write_anchor_if_absent(ws)
    new = _retitle(ws)
    assert plan_reuse(ws, station).station != {}             # through the anchor, strict or not
    plan = plan_reuse(ws, station, strict=True)
    assert plan.station == {"a.mp3": station / "audio" / "01 - A.mp3",
                            "b.mp3": station / "audio" / "02 - B.mp3",
                            "x.mp3": station / "audio" / "03 - X.mp3"}
    ia = ReuseIA({t.filename: t.duration_sec for t in new.tracks})
    build_package(ws, ia, new, reuse=plan)
    assert ia.downloads == []
    assert {n: fake_source(ws.package_dir / "audio" / n) for n in audio_files(ws)} == {
        "01 - A2.mp3": "a.mp3", "02 - B2.mp3": "b.mp3", "03 - X2.mp3": "x.mp3"}
    assert not (ws.dir / ANCHOR).exists()                    # a package build removes it


def test_anchor_of_another_item_pairs_nothing(tmp_path, monkeypatch):
    from llama.audio_reuse import ANCHOR, write_anchor_if_absent
    patch_fake_durations(monkeypatch)
    ws, station = _delivered_purged(tmp_path)
    write_anchor_if_absent(ws)
    data = json.loads((ws.dir / ANCHOR).read_text())
    data["identifier"] = "gd73-other-taper"
    (ws.dir / ANCHOR).write_text(json.dumps(data))
    _retitle(ws)
    assert plan_reuse(ws, station).station == {}


def test_anchor_pairs_library_audio_of_a_packaged_show(tmp_path, monkeypatch):
    from llama.audio_reuse import ANCHOR, write_anchor_if_absent
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*OLD))     # undelivered: library audio in place
    write_anchor_if_absent(ws)
    new = _retitle(ws)
    plan = plan_reuse(ws, None)
    assert plan.library == {"a.mp3": "01 - A.mp3", "b.mp3": "02 - B.mp3", "x.mp3": "03 - X.mp3"}
    ia = ReuseIA({t.filename: t.duration_sec for t in new.tracks})
    build_package(ws, ia, new, reuse=plan)
    assert ia.downloads == []
    assert {n: fake_source(ws.package_dir / "audio" / n) for n in audio_files(ws)} == {
        "01 - A2.mp3": "a.mp3", "02 - B2.mp3": "b.mp3", "03 - X2.mp3": "x.mp3"}
    assert not (ws.dir / ANCHOR).exists()


def test_undelivered_reuse_unchanged(tmp_path, monkeypatch):   # (pin)
    patch_fake_durations(monkeypatch)
    ws, station = _delivered_purged(tmp_path)
    (station / "audio" / "02 - B.mp3").write_bytes(fake_audio("b.mp3", 999.0))
    plan = plan_reuse(ws, station)
    assert plan.strict is False and plan.station_problem is None
    drop_stage_artifacts(ws, "package")
    show = reuse_show(*OLD, ("C", "c.mp3", None))
    ia = ReuseIA({"a.mp3": 300.0, "b.mp3": 400.0, "x.mp3": None, "c.mp3": 50.0})
    build_package(ws, ia, show, reuse=plan)
    # b: fails its length check; x: no metadata length; c: never held -- all download
    assert ia.downloads == ["b.mp3", "x.mp3", "c.mp3"]


def test_anchor_pairs_no_station_copy_for_a_show_json_of_another_item(tmp_path, monkeypatch):
    # A held re-selection moved show.json to another item: the anchor and the station copy
    # are both of the old one, and their audio must not ship under the new item's sources.
    from llama.audio_reuse import write_anchor_if_absent
    patch_fake_durations(monkeypatch)
    ws, station = _delivered_purged(tmp_path)
    write_anchor_if_absent(ws)
    write_artifact(ws.show, reuse_show(*OLD).model_copy(update={"identifier": "gd73-other-taper"}))
    (ws.package_dir / "manifest.json").unlink()
    assert plan_reuse(ws, station).station == {}
    assert plan_reuse(ws, station, strict=True).station == {}
