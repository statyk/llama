"""scripts/junk_drop_rollout.py list (junk-tag-drop plan Task 13; spec
`docs/superpowers/specs/2026-11-13-junk-tag-drop-design.md`, "Rollout" step 2, Membership).

A fixture library, station and arm under tmp_path; `code_identity` is stubbed. Nothing
real is touched, and `list` must write nothing outside `--out`."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import junk_drop_rollout as jdr
from llama import reapply
from llama.config import load_config
from llama.models import Overrides, Show, Track
from llama.replay import config_fingerprint, input_digests
from llama.workspace import ShowWorkspace

IDENT = "band2001-01-01.aud"
SHA = "abc"


@pytest.fixture(autouse=True)
def _identity(monkeypatch):
    monkeypatch.setattr("llama.replay.code_identity", lambda: SHA)


def _lib(tmp_path: Path):
    root = tmp_path / "lib"
    (root / "shows").mkdir(parents=True)
    station = tmp_path / "station"
    station.mkdir()
    (station / "placeholder").mkdir()     # a mounted station is never empty
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{root}"\ndelivery_path = "{station}"\n')
    return cfg, root, station


def _tracks(titles, sets=None, durations=None, segues=None):
    sets = sets or ["1"] * len(titles)
    durations = durations or [300.0] * len(titles)
    segues = segues or [False] * len(titles)
    return [Track(index=i, set=s, title=t, filename=f"t{i}.mp3", duration_sec=d, segue=g,
                  title_source="tags")
            for i, (t, s, d, g) in enumerate(zip(titles, sets, durations, segues), 1)]


def _show(root: Path, slug: str, titles, *, sets=None, durations=None, segues=None,
          include=None) -> ShowWorkspace:
    d = root / "shows" / slug
    d.mkdir(parents=True)
    ws = ShowWorkspace(d)
    show = Show(performance_id=f"band/{slug}", identifier=IDENT, artist="Band",
                date="2001-01-01", tracks=_tracks(titles, sets, durations, segues))
    ws.show.write_text(show.model_dump_json(indent=2))
    if include:
        ws.overrides.write_text(Overrides(include=list(include)).model_dump_json(indent=2))
    return ws


def _station(station: Path, slug: str, titles, *, sets=None, segues=None, dj_audio=None,
             identifier=IDENT):
    out = station / slug
    out.mkdir()
    sets = sets or ["1"] * len(titles)
    segues = segues or [False] * len(titles)
    tracks = [{"index": i, "set": s, "title": t, "filename": f"{i:02d} - {t}.mp3",
               "duration_sec": 300.0, "segue": g}
              for i, (t, s, g) in enumerate(zip(titles, sets, segues), 1)]
    (out / "manifest.json").write_text(json.dumps(
        {"schema_version": 3, "source": {"identifier": identifier, "profile": "dead"},
         "tracks": tracks, "dj_notes": None, "dj_audio": dj_audio}, indent=2) + "\n")
    return out


def _drop(filename, title, *, set="1", after_track=0, duration_sec=300.0, rule="A",
          held=False):
    return {"filename": filename, "title": title, "set": set, "after_track": after_track,
            "duration_sec": duration_sec, "rule": rule, "held": held}


def _row(ws: ShowWorkspace, *, outcome="clean-changed", drops=(), briefing="fresh",
         keep=None, **kw) -> dict:
    """An arm row whose predicted tracks are show.json's minus the drops (or `keep`)."""
    show = Show.model_validate_json(ws.show.read_text())
    gone = {d["filename"] for d in drops}
    kept = [t for t in show.tracks if t.filename not in gone] if keep is None else keep
    row = {"slug": ws.dir.name, "state": "delivered", "outcome": outcome,
           "needs_llm": ["alignment llm"] if outcome == "needs-llm" else [],
           "briefing": briefing, "digests": input_digests(ws),
           "junk_drops": list(drops), "filenames": [t.filename for t in kept],
           "titles": [t.title for t in kept], "sets": [t.set for t in kept],
           "segues": [bool(t.segue) for t in kept]}
    row.update(kw)
    return row


def _arm(tmp_path, cfg, *rows, sha=SHA, fingerprint=None) -> Path:
    path = tmp_path / "arm.json"
    fp = fingerprint or config_fingerprint(load_config(cfg))
    path.write_text(json.dumps({"sha": sha, "config_fingerprint": fp,
                                "shows": {r["slug"]: r for r in rows}}, indent=1))
    return path


def _status(tmp_path, *rows) -> Path:
    path = tmp_path / "status.json"
    path.write_text(json.dumps(list(rows)))
    return path


def _list(tmp_path, cfg, arm, status=None, out=None):
    out = out or tmp_path / "out"
    status = status or _status(tmp_path)
    rc = jdr.main(["list", "--config", str(cfg), "--arm", str(arm),
                   "--emcee-status", str(status), "--out", str(out)])
    return rc, out


def _members(out: Path) -> dict[str, dict]:
    return {r["slug"]: r for r in json.loads((out / "members.json").read_text())["rows"]}


def _doc(out: Path, name: str) -> dict:
    return json.loads((out / name).read_text())


VOICED = {"dir": "dj-audio", "presenter": "phil",
          "set_intros": {"1": "dj-audio/set1.mp3", "2": "dj-audio/set2.mp3"},
          "outro": "dj-audio/outro.mp3", "tts": {"backend": "voxtral", "voice": "x"}}


# --- membership -------------------------------------------------------------------

def test_member_by_paired_station_track(tmp_path):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "s1", ["Tuning", "Bertha", "Sugaree"])
    _station(station, "s1", ["Tuning", "Bertha", "Sugaree"])
    arm = _arm(tmp_path, cfg, _row(ws, drops=[_drop("t1.mp3", "Tuning")]))
    rc, out = _list(tmp_path, cfg, arm)
    assert rc == 0
    m = _members(out)["s1"]
    assert m["outcome"] == "member"
    assert m["drop_source"] == "replay"
    assert m["needs_llm"] is False
    assert m["briefing"] == "fresh"
    assert m["digests"] == input_digests(ws)
    assert m["station"]["state"] == "unvoiced"
    assert m["drops"] == [{"source_file": "t1.mp3", "title": "Tuning", "duration_sec": 300.0,
                           "set": "1", "after_track": 0, "rule": "A", "held": False}]
    assert m["held"] is False
    assert m["pairs"] == [{"station_file": "01 - Tuning.mp3", "station_title": "Tuning",
                           "source_file": "t1.mp3"}]
    assert m["other_differences"] == []
    doc = _doc(out, "members.json")
    assert doc["sha"] == SHA
    assert doc["config_fingerprint"] == config_fingerprint(load_config(cfg))
    assert doc["arm_sha256"] == hashlib.sha256(arm.read_bytes()).hexdigest()
    assert doc["written_at"]


def test_not_on_station_member(tmp_path):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "s1", ["Bertha", "Crowd"])
    plain = _show(root, "plain", ["Bertha", "Sugaree"])
    arm = _arm(tmp_path, cfg, _row(ws, drops=[_drop("t2.mp3", "Crowd", rule="A",
                                                     after_track=1)]),
               _row(plain))
    rc, out = _list(tmp_path, cfg, arm)
    assert rc == 0
    members = _members(out)
    assert sorted(members) == ["s1"]
    m = members["s1"]
    assert m["station"] == {"state": "not on station", "presenter": None,
                            "backend_now": None, "clips": 0}
    assert m["pairs"] == []
    assert [d["source_file"] for d in m["drops"]] == ["t2.mp3"]


def test_unpaired_is_left_out_and_listed(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "s1", ["Tuning", "Bertha", "Sugaree"])
    _station(station, "s1", ["Tuning", "Bertha", "Sugaree Jam"])     # a title moved
    arm = _arm(tmp_path, cfg, _row(ws, drops=[_drop("t1.mp3", "Tuning")]))
    rc, out = _list(tmp_path, cfg, arm)
    assert rc == 0
    assert _members(out) == {}
    unpaired = _doc(out, "unpaired.json")
    assert [r["slug"] for r in unpaired["rows"]] == ["s1"]
    assert unpaired["rows"][0]["drops"][0]["source_file"] == "t1.mp3"
    assert "unpaired: 1" in capsys.readouterr().out


def test_unpaired_pairs_through_the_reuse_anchor(tmp_path):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "s1", ["Tuning", "Bertha", "Sugaree Jam"])
    _station(station, "s1", ["Tuning", "Bertha", "Sugaree"])
    ws.reuse_anchor.write_text(json.dumps(
        {"identifier": IDENT, "written_at": "2026-11-01T00:00:00+00:00",
         "tracks": [{"filename": f"t{i}.mp3", "title": t}
                    for i, t in enumerate(["Tuning", "Bertha", "Sugaree"], 1)]}))
    arm = _arm(tmp_path, cfg, _row(ws, drops=[_drop("t1.mp3", "Tuning")]))
    rc, out = _list(tmp_path, cfg, arm)
    assert rc == 0
    m = _members(out)["s1"]
    assert m["pairs"][0]["source_file"] == "t1.mp3"
    assert m["other_differences"] == ["title t3.mp3: 'Sugaree' -> 'Sugaree Jam'"]


def test_station_track_not_dropped_is_not_member(tmp_path):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "s1", ["Bertha", "Sugaree"])
    _station(station, "s1", ["Bertha", "Sugaree"])
    # The replay drops a file the station copy never held (not in show.json either).
    row = _row(ws, drops=[_drop("t9.mp3", "Tuning", after_track=2)])
    nodrop = _show(root, "s2", ["Bertha", "Sugaree"])
    _station(station, "s2", ["Bertha", "Sugaree"])
    arm = _arm(tmp_path, cfg, row, _row(nodrop))
    rc, out = _list(tmp_path, cfg, arm)
    assert rc == 0
    assert _members(out) == {}
    assert _doc(out, "unpaired.json")["rows"] == []


def test_needs_llm_row_uses_show_json(tmp_path):
    cfg, root, station = _lib(tmp_path)
    # Intro at a set start (B), a short Tuning (A), a Crowd past the breaker (held), and
    # an included Tuning that stays.
    ws = _show(root, "s1", ["Intro", "Bertha", "Tuning", "Sugaree", "Tuning", "Crowd"],
               sets=["1", "1", "1", "2", "2", "2"],
               durations=[60.0, 400.0, 30.0, 300.0, 20.0, 900.0],
               segues=[False, True, False, False, False, False], include=["t5.mp3"])
    _station(station, "s1", ["Intro", "Bertha", "Tuning", "Sugaree", "Tuning", "Crowd"],
             sets=["1", "1", "1", "2", "2", "2"])
    # The arm row's own (empty) drops and predicted lists are ignored for needs-LLM.
    row = _row(ws, outcome="needs-llm", briefing="none", drops=[], keep=[])
    arm = _arm(tmp_path, cfg, row)
    rc, out = _list(tmp_path, cfg, arm)
    assert rc == 0
    m = _members(out)["s1"]
    assert m["drop_source"] == "show.json"
    assert m["needs_llm"] is True
    assert [(d["source_file"], d["rule"], d["after_track"], d["held"]) for d in m["drops"]] == [
        ("t1.mp3", "B", 0, False), ("t3.mp3", "A", 1, False), ("t6.mp3", "A", 3, True)]
    assert m["held"] is True
    assert [p["source_file"] for p in m["pairs"]] == ["t1.mp3", "t3.mp3", "t6.mp3"]
    # show.json's t2 segue into the dropped t3 goes (gather's rule), matching the station.
    assert m["other_differences"] == []


def test_with_gather_llm_shows_are_their_own_wave(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    a = _show(root, "a", ["Tuning", "Bertha"])
    b = _show(root, "b", ["Tuning", "Bertha"])
    c = _show(root, "c", ["Crowd", "Bertha"])
    arm = _arm(tmp_path, cfg, _row(a, drops=[_drop("t1.mp3", "Tuning")]),
               _row(b, outcome="needs-llm", briefing="none"),
               _row(c, outcome="needs-llm", briefing="none"))
    rc, out = _list(tmp_path, cfg, arm)
    assert rc == 0
    rep = _doc(out, "reapply-replayable.json")["rows"]
    llm = _doc(out, "reapply-needs-llm.json")["rows"]
    assert [r["slug"] for r in rep] == ["a"]
    assert [r["slug"] for r in llm] == ["b", "c"]
    assert rep[0] == {"slug": "a", "outcome": "clean-changed", "briefing": "fresh",
                      "digests": input_digests(a)}
    assert llm[0]["outcome"] == "needs-llm"
    printed = capsys.readouterr().out
    assert "with-gather-llm wave: 2\n" in printed


def test_reapply_lists_load_with_reapply_load_list(tmp_path):
    cfg, root, station = _lib(tmp_path)
    a = _show(root, "a", ["Tuning", "Bertha"])
    b = _show(root, "b", ["Tuning", "Bertha"])
    arm = _arm(tmp_path, cfg, _row(a, drops=[_drop("t1.mp3", "Tuning")]),
               _row(b, outcome="needs-llm", briefing="none"))
    rc, out = _list(tmp_path, cfg, arm)
    assert rc == 0
    fp = config_fingerprint(load_config(cfg))
    for name, slugs in (("reapply-replayable.json", ["a"]), ("reapply-needs-llm.json", ["b"])):
        data = reapply.load_list(out / name, sha=SHA, fingerprint=fp)
        assert [r["slug"] for r in data["rows"]] == slugs


def test_voiced_entry_carries_clips_presenter_backend(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    rows, status = [], []
    for slug, tts_now in (("v1", {"backend": "voxtral", "model": "m"}), ("v2", None),
                          ("v3", {"unresolved": "no such presenter"})):
        ws = _show(root, slug, ["Tuning", "Bertha", "Sugaree"])
        _station(station, slug, ["Tuning", "Bertha", "Sugaree"], dj_audio=VOICED)
        rows.append(_row(ws, drops=[_drop("t1.mp3", "Tuning")]))
        status.append({"slug": slug, "state": "voiced", "voiced_by": "phil", "tts_now": tts_now})
    one = {**VOICED, "set_intros": {"1": "dj-audio/set1.mp3"}, "outro": None}
    ws = _show(root, "v4", ["Tuning", "Bertha"])
    _station(station, "v4", ["Tuning", "Bertha"], dj_audio=one)
    rows.append(_row(ws, drops=[_drop("t1.mp3", "Tuning")]))
    status.append({"slug": "v4", "voiced_by": "jamesbrown",
                   "tts_now": {"backend": "mlx_audio", "model": "q"}})
    arm = _arm(tmp_path, cfg, *rows)
    rc, out = _list(tmp_path, cfg, arm, status=_status(tmp_path, *status))
    assert rc == 0
    m = _members(out)
    assert m["v1"]["station"] == {"state": "voiced", "presenter": "phil",
                                  "backend_now": "voxtral", "clips": 3}
    assert m["v2"]["station"]["backend_now"] is None
    assert m["v3"]["station"]["backend_now"] == "unresolved"
    assert m["v4"]["station"] == {"state": "voiced", "presenter": "jamesbrown",
                                  "backend_now": "mlx_audio", "clips": 1}
    printed = capsys.readouterr().out
    assert "voiced: 4" in printed
    assert "voxtral 1" in printed and "mlx_audio 1" in printed and "unresolved 1" in printed


def test_other_differences_reported(tmp_path):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "s1", ["Tuning", "Bertha", "Sugaree", "Deal"])
    _station(station, "s1", ["Tuning", "Bertha", "Sugaree", "Deal"],
             segues=[False, True, False, False])
    show = Show.model_validate_json(ws.show.read_text())
    t1, t2, t3, t4 = show.tracks
    new = Track(index=4, set="2", title="Morning Dew", filename="t5.mp3", title_source="tags")
    keep = [t2.model_copy(update={"title": "Bertha (alt)"}),
            t3.model_copy(update={"set": "2"}), new]
    arm = _arm(tmp_path, cfg, _row(ws, drops=[_drop("t1.mp3", "Tuning")], keep=keep))
    rc, out = _list(tmp_path, cfg, arm)
    assert rc == 0
    assert _members(out)["s1"]["other_differences"] == [
        "title t2.mp3: 'Bertha' -> 'Bertha (alt)'",
        "segue t2.mp3: true -> false",
        "set t3.mp3: 1 -> 2",
        "removed t4.mp3 'Deal'",
        "added t5.mp3 'Morning Dew'",
    ]


# --- refusals ---------------------------------------------------------------------

def _refused(tmp_path, capsys, cfg, arm, needle, out=None):
    rc, out = _list(tmp_path, cfg, arm, out=out)
    assert rc == 2
    assert needle in capsys.readouterr().err
    assert not (out / "members.json").exists()


def test_refuses_stale_arm_and_unmounted_station(tmp_path, capsys, monkeypatch):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "s1", ["Tuning", "Bertha"])
    row = _row(ws, drops=[_drop("t1.mp3", "Tuning")])
    _refused(tmp_path, capsys, cfg, _arm(tmp_path, cfg, row, sha="old"), "old")
    _refused(tmp_path, capsys, cfg, _arm(tmp_path, cfg, row, sha="abc-dirty"), "uncommitted")
    _refused(tmp_path, capsys, cfg, _arm(tmp_path, cfg, row, fingerprint="f0"),
             "config")
    monkeypatch.setattr("llama.replay.code_identity", lambda: "abc-dirty")
    _refused(tmp_path, capsys, cfg, _arm(tmp_path, cfg, row, sha="abc-dirty"), "uncommitted")
    monkeypatch.setattr("llama.replay.code_identity", lambda: SHA)
    arm = _arm(tmp_path, cfg, row)
    # --out inside the library or the station
    _refused(tmp_path, capsys, cfg, arm, "overlaps", out=root / "out")
    _refused(tmp_path, capsys, cfg, arm, "overlaps", out=station / "out")
    # an empty (unmounted) station root
    (station / "placeholder").rmdir()
    _refused(tmp_path, capsys, cfg, arm, "empty")
    # a missing station root
    station.rmdir()
    _refused(tmp_path, capsys, cfg, arm, "station root")
    # no delivery_path at all
    cfg.write_text(f'root = "{root}"\n')
    _refused(tmp_path, capsys, cfg, _arm(tmp_path, cfg, row), "delivery_path")


def test_list_writes_nothing_outside_out(tmp_path):
    cfg, root, station = _lib(tmp_path)
    a = _show(root, "a", ["Tuning", "Bertha", "Sugaree"])
    _station(station, "a", ["Tuning", "Bertha", "Sugaree"], dj_audio=VOICED)
    b = _show(root, "b", ["Crowd", "Bertha"])
    c = _show(root, "c", ["Intro", "Bertha"], include=["t9.mp3"])
    _station(station, "c", ["Intro", "Bertha"])
    arm = _arm(tmp_path, cfg, _row(a, drops=[_drop("t1.mp3", "Tuning")]),
               _row(b, drops=[_drop("t1.mp3", "Crowd")]),
               _row(c, outcome="needs-llm", briefing="none"))
    status = _status(tmp_path, {"slug": "a", "voiced_by": "phil",
                                "tts_now": {"backend": "voxtral", "model": "m"}})

    def tree(base: Path):
        return {str(p.relative_to(base)): (hashlib.sha256(p.read_bytes()).hexdigest()
                                           if p.is_file() else None, p.stat().st_mtime_ns)
                for p in sorted(base.rglob("*"))}
    before = {k: tree(p) for k, p in (("lib", root), ("station", station))}
    inputs = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (arm, status, cfg)}
    rc, out = _list(tmp_path, cfg, arm, status=status)
    assert rc == 0
    assert sorted(_members(out)) == ["a", "b", "c"]
    assert {k: tree(p) for k, p in (("lib", root), ("station", station))} == before
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in inputs} == inputs
    assert sorted(p.name for p in out.iterdir()) == sorted(jdr.OUTPUT_FILES)
