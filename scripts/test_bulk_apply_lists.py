"""scripts/bulk_apply.py lists / wave-check / spot-check (bulk-apply plan Task 16; spec
"Pacing, ordering and resumability" (selection), "Re-processing", "Pacing").

Fixture libraries and stations under tmp_path; nothing real is touched."""
import json
import shutil
import sys
from collections import namedtuple
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bulk_apply as ba
from llama import campaign, campaign_gate, reapply, station_mark
from llama.models import Provenance, Show
from llama.replay import config_fingerprint
from llama.config import load_config
from test_bulk_apply_mark import _arm, _lib, _row, _show

MARK_AT = "2026-10-01T00:00:00.000000Z"


@pytest.fixture(autouse=True)
def _no_emcee(monkeypatch):
    monkeypatch.setattr(station_mark, "emcee_running", lambda: [])
    monkeypatch.setattr(campaign_gate, "ps_lines", lambda: [])
    monkeypatch.setattr("llama.replay.code_identity", lambda: "abc")


def _pin(root, sha="abc"):
    campaign_gate.write_pin(root, tag="v2.20.0", sha=sha, version="2.20.0",
                            worktree="/w", replace=True)


def _mark(ws, stage="gather", batch="b1"):
    campaign.add_mark(ws, reason="changed by the held-backlog fixes: titles",
                      start_stage=stage, batch=batch, at=MARK_AT)


def _profile(ws, profile):
    prov = Provenance.model_validate_json(ws.provenance.read_text())
    prov.profile = profile
    ws.provenance.write_text(prov.model_dump_json(indent=2))


def _write_arm(tmp_path, cfg, *rows, **kw):
    path = tmp_path / "arm.json"
    path.write_text(json.dumps(_arm(cfg, *rows, **kw)))
    return path


def _run(cfg, *argv):
    return ba.main(["--config", str(cfg), *argv])


def _listed(out):
    return {r["slug"]: r for r in json.loads(Path(out).read_text())["rows"]}


def _world(tmp_path):
    cfg, root, station = _lib(tmp_path)
    _pin(root)
    shows = {}
    shows["fresh"] = _show(root, "fresh")
    shows["reuse"] = _show(root, "reuse")
    shows["done"] = _show(root, "done")                       # processed
    shows["resel"] = _show(root, "resel")                     # re-selection
    shows["voiced"] = _show(root, "voiced", delivered=True, station=station, voiced=True)
    shows["unvoiced"] = _show(root, "unvoiced", delivered=True, station=station)
    shows["famous"] = _show(root, "famous")
    shows["label"] = _show(root, "label")                     # label-only, no record
    shows["newly"] = _show(root, "newly", held=True)
    shows["plain"] = _show(root, "plain")                     # no change, no record
    for n in ("fresh", "reuse", "voiced", "unvoiced", "famous"):
        _mark(shows[n])
    _mark(shows["resel"], stage="select")
    _mark(shows["done"])
    assert campaign.mark_processed(shows["done"], held=False)
    _profile(shows["fresh"], "dead")
    _profile(shows["reuse"], "dead")
    _profile(shows["unvoiced"], "funk")
    _profile(shows["voiced"], "funk")
    chg = dict(outcome="clean-changed", filenames=["t1.mp3", "t9.mp3"])
    rows = [
        _row(shows["fresh"], briefing="fresh", **chg),
        _row(shows["reuse"], briefing="reuse", **chg),
        _row(shows["done"], briefing="reuse", **chg),
        _row(shows["resel"], briefing="reuse", **chg),
        _row(shows["voiced"], briefing="reuse", **chg),
        _row(shows["unvoiced"], briefing="reuse", **chg),
        _row(shows["famous"], briefing="reuse", **chg),
        _row(shows["label"], briefing="reuse",
             title_changes=[{"old": "Song 1", "new": "Song 1"}]),
        _row(shows["newly"], outcome="newly-held", briefing="none", filenames=chg["filenames"]),
        _row(shows["plain"], briefing="reuse"),
    ]
    arm = _write_arm(tmp_path, cfg, *rows)
    (root / "campaign").mkdir(exist_ok=True)
    (root / "campaign" / "reselections.json").write_text(json.dumps(
        {"written_at": "2026-10-27T12:00:00+00:00",
         "rows": [{"slug": "resel", "stored": "a", "pick": "b"}]}))
    return cfg, root, station, shows, arm


def test_lists_select_by_profile_state_kind_and_exclude_voiced_processed_reselection(
        tmp_path):
    cfg, root, station, shows, arm = _world(tmp_path)
    famous = tmp_path / "famous.txt"
    famous.write_text("famous\n")
    out = tmp_path / "wave.json"
    assert _run(cfg, "lists", "--arm", str(arm), "--out", str(out),
                "--famous", str(famous)) == 0
    rows = _listed(out)
    assert sorted(rows) == ["fresh", "label", "newly", "reuse", "unvoiced"]   # slug order too
    assert list(json.loads(out.read_text())["rows"][0]) == [
        "slug", "outcome", "briefing", "kind", "digests"]
    assert {s: r["kind"] for s, r in rows.items()} == {
        "fresh": "fresh", "reuse": "reuse", "label": "label-only", "newly": "held",
        "unvoiced": "reuse"}
    doc = json.loads(out.read_text())
    assert doc["campaign"] == {"version": "2.20.0", "pin_sha": "abc"}
    assert doc["sha"] == "abc" and doc["config_fingerprint"]
    # filters
    o2 = tmp_path / "w2.json"
    assert _run(cfg, "lists", "--arm", str(arm), "--out", str(o2), "--profile", "dead",
                "--kind", "fresh") == 0
    assert sorted(_listed(o2)) == ["fresh"]
    assert _run(cfg, "lists", "--arm", str(arm), "--out", str(o2), "--state", "delivered") == 0
    assert sorted(_listed(o2)) == ["unvoiced"]
    assert _run(cfg, "lists", "--arm", str(arm), "--out", str(o2), "--limit", "2") == 0
    assert sorted(_listed(o2)) == ["famous", "fresh"]            # the first two in slug order
    sl = tmp_path / "slugs.txt"
    sl.write_text("reuse\nvoiced\n")
    assert _run(cfg, "lists", "--arm", str(arm), "--out", str(o2), "--slugs", str(sl)) == 0
    assert sorted(_listed(o2)) == ["reuse"]
    assert _run(cfg, "lists", "--arm", str(arm), "--out", str(o2), "--include-voiced",
                "--slugs", str(sl)) == 0
    assert sorted(_listed(o2)) == ["reuse", "voiced"]


def test_lists_refuse_an_arm_not_at_the_pin(tmp_path, capsys):
    cfg, root, station, shows, arm = _world(tmp_path)
    _pin(root, sha="other")
    monkey_out = tmp_path / "wave.json"
    assert _run(cfg, "lists", "--arm", str(arm), "--out", str(monkey_out)) == 2
    assert not monkey_out.exists()
    _pin(root, sha="abc")
    bad = json.loads(arm.read_text())
    bad["sha"] = "zzz"
    arm.write_text(json.dumps(bad))
    assert _run(cfg, "lists", "--arm", str(arm), "--out", str(monkey_out)) == 2
    assert "zzz" in capsys.readouterr().err and not monkey_out.exists()


def test_unreadable_campaign_record_is_reported_not_listed(tmp_path, capsys):
    cfg, root, station, shows, arm = _world(tmp_path)
    shows["fresh"].campaign.write_text("{not json")
    out = tmp_path / "wave.json"
    assert _run(cfg, "lists", "--arm", str(arm), "--out", str(out)) == 0
    assert "fresh" not in _listed(out)
    assert ("fresh: cannot read campaign.json" in capsys.readouterr().err)


def test_famous_shows_go_to_a_packet(tmp_path):
    cfg, root, station, shows, arm = _world(tmp_path)
    famous = tmp_path / "famous.txt"
    famous.write_text("famous\n")
    doc = json.loads(arm.read_text())
    # same files as the stored show, so rows pair by filename and only the fields differ
    doc["shows"]["famous"].update(filenames=["t1.mp3", "t2.mp3"],
                                  titles=["Song 1", "Renamed"], sets=["1", "2"],
                                  segues=[False, True])
    arm.write_text(json.dumps(doc))
    out = tmp_path / "wave.json"
    assert _run(cfg, "lists", "--arm", str(arm), "--out", str(out),
                "--famous", str(famous)) == 0
    assert "famous" not in _listed(out)
    text = Path(str(out) + ".famous.txt").read_text()
    lines = text.splitlines()
    assert lines[0] == "== famous"
    one = next(l for l in lines if l.lstrip("* ").startswith("1 "))
    two = next(l for l in lines if l.lstrip("* ").startswith("2 "))
    assert not one.startswith("*")
    assert two.startswith("*")
    assert "set 1->2" in two and "title Song 2->Renamed" in two and "segue none->'>'" in two


def test_lists_refuse_a_missing_station_root_or_delivery_path(tmp_path, capsys):
    cfg, root, station, shows, arm = _world(tmp_path)
    out = tmp_path / "wave.json"
    station.rename(tmp_path / "gone")
    assert _run(cfg, "lists", "--arm", str(arm), "--out", str(out)) == 2
    assert not out.exists()
    assert "not mounted or not a directory" in capsys.readouterr().err
    assert _run(cfg, "lists", "--arm", str(arm), "--counts") == 2
    assert capsys.readouterr().out == ""
    (tmp_path / "gone").rename(station)
    cfg.write_text(f'root = "{root}"\n')
    assert _run(cfg, "lists", "--arm", str(arm), "--out", str(out)) == 2
    assert not out.exists()
    assert "no delivery_path in config" in capsys.readouterr().err
    assert _run(cfg, "lists", "--arm", str(arm), "--counts") == 2


def test_render_side_by_side_stars_differing_rows():
    before = [{"filename": "a", "set": "1", "title": "A", "segue": False},
              {"filename": "b", "set": "1", "title": "B", "segue": False}]
    after = [{"filename": "a", "set": "1", "title": "A", "segue": False},
             {"filename": "b", "set": "2", "title": "B2", "segue": True}]
    lines = ba.render_side_by_side(before, after)
    assert len(lines) == 2
    assert not lines[0].lstrip().startswith("*") and "*" not in lines[0]
    assert "*" in lines[1] and "1->2" in lines[1] and "B->B2" in lines[1]


def test_counts_shape(tmp_path, capsys):
    cfg, root, station, shows, arm = _world(tmp_path)
    assert _run(cfg, "lists", "--arm", str(arm), "--counts") == 0
    counts = json.loads(capsys.readouterr().out)
    assert counts["dead"] == {"fresh": {"unvoiced": 1, "voiced": 0},
                              "reuse": {"unvoiced": 1, "voiced": 0}}
    assert counts["funk"] == {"reuse": {"unvoiced": 1, "voiced": 1}}


def test_kind_held_from_briefing_none(tmp_path):
    cfg, root, station = _lib(tmp_path)
    (station / "placeholder").mkdir()           # an empty station root now refuses (RF2)
    _pin(root)
    a, b = _show(root, "a", held=True), _show(root, "b")
    chg = dict(filenames=["t1.mp3", "t9.mp3"])
    arm = _write_arm(tmp_path, cfg,
                     _row(a, outcome="held", briefing="none", **chg),
                     _row(b, outcome="needs-llm", briefing="none"))
    _mark(a)
    _mark(b)
    out = tmp_path / "w.json"
    assert _run(cfg, "lists", "--arm", str(arm), "--out", str(out)) == 0
    assert {s: r["kind"] for s, r in _listed(out).items()} == {"a": "held", "b": "needs-llm"}


def test_list_feeds_reapply(tmp_path):
    cfg, root, station, shows, arm = _world(tmp_path)
    out = tmp_path / "wave.json"
    assert _run(cfg, "lists", "--arm", str(arm), "--out", str(out)) == 0
    doc = reapply.load_list(out, sha="abc", fingerprint=config_fingerprint(load_config(cfg)))
    assert [r["slug"] for r in doc["rows"]]


def _wave_list(tmp_path, cfg, slugs):
    path = tmp_path / "wl.json"
    path.write_text(json.dumps({"sha": "abc", "config_fingerprint": "x", "rows": [
        {"slug": s, "outcome": "clean", "briefing": "reuse", "kind": "reuse", "digests": {}}
        for s in slugs]}))
    return path


def _audio(station, slug, sizes):
    d = station / slug / "audio"
    d.mkdir()
    for i, n in enumerate(sizes):
        (d / f"{i}.mp3").write_bytes(b"x" * n)


def test_wave_check_refuses_when_the_disk_is_short(tmp_path, monkeypatch, capsys):
    cfg, root, station = _lib(tmp_path)
    _show(root, "d1", delivered=True, station=station)
    _show(root, "p1")
    _audio(station, "d1", [100, 200])
    wl = _wave_list(tmp_path, cfg, ["d1", "p1"])
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(ba.shutil, "disk_usage",
                        lambda p: Usage(10**12, 0, ba.WAVE_DISK_MARGIN_BYTES + 300))
    assert _run(cfg, "wave-check", "--list", str(wl)) == 0
    out = capsys.readouterr().out
    assert "300" in out and str(ba.WAVE_DISK_MARGIN_BYTES) in out
    monkeypatch.setattr(ba.shutil, "disk_usage",
                        lambda p: Usage(10**12, 0, ba.WAVE_DISK_MARGIN_BYTES + 299))
    assert _run(cfg, "wave-check", "--list", str(wl)) == 2
    assert ba.WAVE_DISK_MARGIN_BYTES == 20 * 10**9


def test_wave_check_refuses_an_unreadable_station(tmp_path, monkeypatch, capsys):
    cfg, root, station = _lib(tmp_path)
    _show(root, "d1", delivered=True, station=station)
    (station / "d1" / "manifest.json").write_text("{nope")
    wl = _wave_list(tmp_path, cfg, ["d1"])
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(ba.shutil, "disk_usage", lambda p: Usage(10**12, 0, 10**12))
    assert _run(cfg, "wave-check", "--list", str(wl)) == 2
    assert "d1" in capsys.readouterr().err
    # a station root that is not a directory
    station.rename(tmp_path / "gone")
    assert _run(cfg, "wave-check", "--list", str(wl)) == 2


def test_spot_check_is_seeded_and_side_by_side(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    batch = tmp_path / "batch"
    slugs = [f"s{i}" for i in range(8)]
    prog = []
    for s in slugs:
        ws = _show(root, s)
        snap = batch / "snapshot" / "shows" / s
        snap.mkdir(parents=True)
        (snap / "show.json").write_text(ws.show.read_text())
        show = Show.model_validate_json(ws.show.read_text())
        show.tracks[1].title = "Changed"
        ws.show.write_text(show.model_dump_json(indent=2))
        prog.append({"slug": s, "outcome": "cleared" if s != "s3" else "unchanged"})
    batch.mkdir(exist_ok=True)
    (batch / "progress.jsonl").write_text("".join(json.dumps(r) + "\n" for r in prog))
    assert _run(cfg, "spot-check", "--batch", str(batch), "--n", "3", "--seed", "7") == 0
    first = capsys.readouterr().out
    assert "seed: 7" in first and "Song 2->Changed" in first and "*" in first
    assert "s3" not in first                              # unchanged rows are not sampled
    assert _run(cfg, "spot-check", "--batch", str(batch), "--n", "3", "--seed", "7") == 0
    assert capsys.readouterr().out == first
    assert first.count("== s") == 3
    assert _run(cfg, "spot-check", "--batch", str(batch), "--n", "3") == 0
    assert "seed: " in capsys.readouterr().out


def test_lists_refuse_an_empty_station_root(tmp_path, capsys):
    cfg, root, station, shows, arm = _world(tmp_path)
    out = tmp_path / "wave.json"
    for child in station.iterdir():
        shutil.rmtree(child)
    (station / ".hidden").mkdir()               # only dot-entries still counts as empty
    assert _run(cfg, "lists", "--arm", str(arm), "--out", str(out)) == 2
    assert not out.exists()
    assert (f"station root {station} is empty (is the station mounted?)"
            in capsys.readouterr().err)
    assert _run(cfg, "lists", "--arm", str(arm), "--counts") == 2
    assert capsys.readouterr().out == ""


def test_wave_check_refuses_an_empty_station_root(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    wl = _wave_list(tmp_path, cfg, ["d1"])
    assert _run(cfg, "wave-check", "--list", str(wl)) == 2
    assert (f"station root {station} is empty (is the station mounted?)"
            in capsys.readouterr().err)


def test_render_side_by_side_pairs_by_filename_so_an_added_track_is_one_row():
    # antibalasmusic-2004-11-03: short-keep restores d1t1 "Intro" at the front; by index
    # every later row read as a title shift.
    before = [{"filename": "t2", "set": "1", "title": "B", "segue": False},
              {"filename": "t3", "set": "1", "title": "C", "segue": False}]
    after = [{"filename": "t1", "set": "1", "title": "Intro", "segue": False}] + before
    lines = ba.render_side_by_side(before, after)
    assert len(lines) == 3
    assert lines[0].startswith("*") and "title ?->Intro" in lines[0]
    assert [l.startswith("*") for l in lines[1:]] == [False, False]
    assert "title B->B" in lines[1] and "title C->C" in lines[2]


def test_render_side_by_side_shows_a_dropped_track_as_one_row():
    before = [{"filename": "t1", "set": "1", "title": "A", "segue": False},
              {"filename": "t2", "set": "1", "title": "B", "segue": False},
              {"filename": "t3", "set": "1", "title": "C", "segue": False}]
    after = [before[0], before[2]]
    lines = ba.render_side_by_side(before, after)
    assert len(lines) == 3
    assert [l.startswith("*") for l in lines] == [False, True, False]
    assert "title B->?" in lines[1] and "title C->C" in lines[2]
