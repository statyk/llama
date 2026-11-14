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


# --- mark (plan Task 14; spec "Rollout" step 3, Stakes) ----------------------------

import bulk_apply as ba   # noqa: E402
from llama import campaign, campaign_gate, station_lock, station_mark   # noqa: E402


@pytest.fixture(autouse=True)
def _no_tools(monkeypatch):
    """No real emcee check, pin or PATH probe: `mark --apply`'s gates are stubbed and
    recorded (a test that wants them to refuse replaces them)."""
    monkeypatch.setattr(station_mark, "emcee_running", lambda: [])
    monkeypatch.setattr(campaign_gate, "ps_lines", lambda: [])
    seen: dict = {}
    pin = {"tag": "v2.24.0", "sha": SHA, "version": "2.24.0"}
    monkeypatch.setattr(jdr, "require_pinned_code", lambda root: seen.setdefault("pin", root)
                        and pin)
    monkeypatch.setattr(jdr, "require_tools",
                        lambda echo, *, pin, minimum=None: seen.setdefault(
                            "tools", {"pin": pin, "minimum": minimum}))
    return seen


def _deliver(root: Path, slug: str) -> None:
    with (root / "ledger.jsonl").open("a") as f:
        f.write(json.dumps({"performance_id": f"band/{slug}", "artist": "Band",
                            "date": "2001-01-01", "status": "delivered", "run": "r1",
                            "recorded_at": "2026-01-01T00:00:00Z"}) + "\n")


def _member(ws: ShowWorkspace, *, state="unvoiced", held=False) -> dict:
    return {"slug": ws.dir.name, "outcome": "member", "briefing": "fresh",
            "digests": input_digests(ws), "needs_llm": False, "drop_source": "replay",
            "station": {"state": state, "presenter": None, "backend_now": None, "clips": 0},
            "drops": [{"source_file": "t1.mp3", "title": "Tuning", "duration_sec": 300.0,
                       "set": "1", "after_track": 0, "rule": "A", "held": held}],
            "held": held, "pairs": [], "other_differences": []}


def _list_file(tmp_path, cfg, *members, sha=SHA, fingerprint=None) -> Path:
    path = tmp_path / "out" / "members.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    fp = fingerprint or config_fingerprint(load_config(cfg))
    path.write_text(json.dumps({"sha": sha, "config_fingerprint": fp,
                                "written_at": "2026-11-14T00:00:00+00:00",
                                "arm_sha256": "0" * 64, "rows": list(members)}, indent=1))
    return path


def _mark(cfg, lst, *, apply=False) -> int:
    return jdr.main(["mark", "--list", str(lst), "--config", str(cfg)]
                    + (["--apply"] if apply else []))


def _batch_of(root: Path, lst: Path) -> Path:
    return root / "campaign" / "marking" / hashlib.sha256(lst.read_bytes()).hexdigest()[:16]


def _lines(batch: Path) -> dict[str, dict]:
    return {json.loads(l)["slug"]: json.loads(l)
            for l in (batch / "record.jsonl").read_text().splitlines()}


def _stat(path: Path) -> tuple[bytes, int]:
    return path.read_bytes(), path.stat().st_mtime_ns


def _marks(ws: ShowWorkspace) -> list[tuple[str, str]]:
    rec = campaign.read_record(ws)
    return [(m.reason, m.batch) for m in rec.marks] if rec else []


def test_mark_never_station_marks_a_voiced_copy(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "v1", ["Tuning", "Bertha", "Sugaree"])
    out = _station(station, "v1", ["Tuning", "Bertha", "Sugaree"], dj_audio=VOICED)
    _deliver(root, "v1")
    arm = _arm(tmp_path, cfg, _row(ws, drops=[_drop("t1.mp3", "Tuning")]))
    rc, listed = _list(tmp_path, cfg, arm, status=_status(
        tmp_path, {"slug": "v1", "voiced_by": "phil", "tts_now": {"backend": "voxtral"}}))
    assert rc == 0 and _members(listed)["v1"]["station"]["state"] == "voiced"
    lst = listed / "members.json"
    before = _stat(out / "manifest.json")
    capsys.readouterr()
    assert _mark(cfg, lst) == 0                                   # dry run
    dry = capsys.readouterr().out
    assert "v1: voiced: campaign mark only" in dry and ": would station-mark" not in dry
    assert _mark(cfg, lst, apply=True) == 0
    assert _stat(out / "manifest.json") == before                 # bytes and mtime
    assert sorted(p.name for p in out.iterdir()) == ["manifest.json"]
    batch = _batch_of(root, lst)
    assert _marks(ws) == [("junk-title drop", batch.name)]
    line = _lines(batch)["v1"]
    assert line["station"] == "voiced: campaign mark only"
    assert line["reason"] == "junk-title drop" and line["start_stage"] == "gather"
    assert not (batch / "before" / "v1.json").exists()


def test_mark_station_marks_unvoiced_held_or_not(tmp_path):
    cfg, root, station = _lib(tmp_path)
    shows = {}
    for slug, held in (("plain", False), ("held", True)):
        shows[slug] = _show(root, slug, ["Tuning", "Bertha"])
        _station(station, slug, ["Tuning", "Bertha"])
        _deliver(root, slug)
    originals = {s: (station / s / "manifest.json").read_bytes() for s in shows}
    lst = _list_file(tmp_path, cfg, _member(shows["plain"]), _member(shows["held"], held=True))
    assert _mark(cfg, lst, apply=True) == 0
    batch = _batch_of(root, lst)
    lines = _lines(batch)
    for slug, ws in shows.items():
        data = json.loads((station / slug / "manifest.json").read_text())
        rec = campaign.read_record(ws)
        assert data["awaiting_fix"] == {"reason": "junk-title drop",
                                        "marked_at": rec.marks[-1].at}
        assert _marks(ws) == [("junk-title drop", batch.name)]
        assert lines[slug]["station"] == "marked"
        assert (batch / "before" / f"{slug}.json").read_bytes() == originals[slug]
    inputs = json.loads((batch / "inputs.json").read_text())
    assert inputs["list"] == str(lst)
    assert inputs["list_sha256"] == hashlib.sha256(lst.read_bytes()).hexdigest()
    assert inputs["sha"] == SHA and inputs["station_root"] == str(station)
    assert inputs["created_at"]


def test_voiced_check_reads_under_the_lock(tmp_path, monkeypatch, capsys):
    """The copy is voiced after the dry run read it and before the apply's locked
    re-read: the apply sees it voiced and leaves it unmarked."""
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "s1", ["Tuning", "Bertha"])
    out = _station(station, "s1", ["Tuning", "Bertha"])
    _deliver(root, "s1")
    lst = _list_file(tmp_path, cfg, _member(ws))
    assert _mark(cfg, lst) == 0
    assert "s1: unvoiced: would station-mark" in capsys.readouterr().out
    real = station_lock.for_package
    held = []

    @__import__("contextlib").contextmanager
    def voiced_once_locked(o, *, command):
        with real(o, command=command) as h:
            held.append(command)
            data = json.loads((Path(o) / "manifest.json").read_text())
            data["dj_audio"] = VOICED                        # emcee voiced it meanwhile
            (Path(o) / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
            yield h
    monkeypatch.setattr(ba.station_lock, "for_package", voiced_once_locked)
    voiced = (out / "manifest.json")
    assert _mark(cfg, lst, apply=True) == 0
    assert held == ["bulk_apply mark"]
    data = json.loads(voiced.read_text())
    assert data["dj_audio"] == VOICED and data.get("awaiting_fix") is None
    batch = _batch_of(root, lst)
    assert _lines(batch)["s1"]["station"] == "voiced: campaign mark only"
    assert _marks(ws) == [("junk-title drop", batch.name)]


def test_not_on_station_member_gets_campaign_mark_only(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "lib1", ["Bertha", "Crowd"])
    lst = _list_file(tmp_path, cfg, _member(ws, state="not on station"))
    assert _mark(cfg, lst) == 0
    assert "lib1: not delivered: campaign mark only" in capsys.readouterr().out
    station_before = sorted(p.name for p in station.iterdir())
    assert _mark(cfg, lst, apply=True) == 0
    batch = _batch_of(root, lst)
    assert _lines(batch)["lib1"]["station"] == "not delivered"
    assert _marks(ws) == [("junk-title drop", batch.name)]
    assert sorted(p.name for p in station.iterdir()) == station_before


def test_delivered_without_station_copy_is_ok(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    slug = "philleshandfriends-2008-11-01"
    ws = _show(root, slug, ["Intro", "Bertha"])
    _deliver(root, slug)                                          # delivered, copy gone
    lst = _list_file(tmp_path, cfg, _member(ws, state="not on station"))
    assert _mark(cfg, lst) == 0
    assert f"{slug}: no station copy: campaign mark only" in capsys.readouterr().out
    assert _mark(cfg, lst, apply=True) == 0
    batch = _batch_of(root, lst)
    assert _lines(batch)[slug]["station"] == "no station copy"
    assert _marks(ws) == [("junk-title drop", batch.name)]
    # the same item through bulk_apply's batch without the flag still exits 1
    other = root / "campaign" / "marking" / "0000000000000000"
    item = ba.MarkItem(slug, ba.REASON_JUNK, "gather", input_digests(ws))
    assert ba.mark_apply(root, [item], station_root=station, batch=other,
                         echo=lambda m: None) == 1


def test_bulk_unmark_reverses_a_junk_batch(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    u1 = _show(root, "u1", ["Tuning", "Bertha"])
    _station(station, "u1", ["Tuning", "Bertha"])
    v1 = _show(root, "v1", ["Tuning", "Bertha"])
    _station(station, "v1", ["Tuning", "Bertha"], dj_audio=VOICED)
    p1 = _show(root, "p1", ["Tuning", "Bertha"])
    _station(station, "p1", ["Tuning", "Bertha"])
    for s in ("u1", "v1", "p1"):
        _deliver(root, s)
    originals = {s: (station / s / "manifest.json").read_bytes() for s in ("u1", "v1", "p1")}
    lst = _list_file(tmp_path, cfg, _member(u1), _member(v1, state="voiced"), _member(p1))
    assert _mark(cfg, lst, apply=True) == 0
    batch = _batch_of(root, lst)
    assert campaign.mark_processed(p1, held=False)                # processed since marking
    p1_station = (station / "p1" / "manifest.json").read_bytes()
    capsys.readouterr()
    assert ba.main(["unmark", "--batch", str(batch), "--config", str(cfg), "--apply"]) == 1
    text = capsys.readouterr().out
    assert (station / "u1" / "manifest.json").read_bytes() == originals["u1"]
    assert (station / "v1" / "manifest.json").read_bytes() == originals["v1"]
    assert _marks(u1) == [] and _marks(v1) == []
    assert _marks(p1) == [("junk-title drop", batch.name)]        # left alone
    assert (station / "p1" / "manifest.json").read_bytes() == p1_station
    assert "p1: processed since marked: re-deliver instead" in text


def test_rerun_skips_recorded_items(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    u1 = _show(root, "u1", ["Tuning", "Bertha"])
    _station(station, "u1", ["Tuning", "Bertha"])
    v1 = _show(root, "v1", ["Tuning", "Bertha"])
    _station(station, "v1", ["Tuning", "Bertha"], dj_audio=VOICED)
    lib1 = _show(root, "lib1", ["Tuning", "Bertha"])
    for s in ("u1", "v1"):
        _deliver(root, s)
    lst = _list_file(tmp_path, cfg, _member(u1), _member(v1, state="voiced"),
                     _member(lib1, state="not on station"))
    assert _mark(cfg, lst, apply=True) == 0
    batch = _batch_of(root, lst)

    def snap(p):
        return {str(f.relative_to(p)): _stat(f) for f in sorted(p.rglob("*")) if f.is_file()}
    before = (snap(root), snap(station))
    capsys.readouterr()
    assert _mark(cfg, lst, apply=True) == 0
    text = capsys.readouterr().out
    for s in ("u1", "v1", "lib1"):
        assert f"{s}: skipped: already recorded" in text
    after_root = snap(root)
    assert (after_root, snap(station)) == before
    assert len((batch / "record.jsonl").read_text().splitlines()) == 3


def test_mark_refuses_stale_list(tmp_path, capsys, monkeypatch, _no_tools):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "s1", ["Tuning", "Bertha"])
    _station(station, "s1", ["Tuning", "Bertha"])
    _deliver(root, "s1")
    originals = (station / "s1" / "manifest.json").read_bytes()
    cases = [({"sha": "other"}, "running code is abc"),
             ({"fingerprint": "f" * 16}, "under config ffffffffffffffff")]
    for kw, needle in cases:
        lst = _list_file(tmp_path, cfg, _member(ws), **kw)
        for apply in (False, True):
            capsys.readouterr()
            assert _mark(cfg, lst, apply=apply) == 2
            assert needle in capsys.readouterr().err
    monkeypatch.setattr("llama.replay.code_identity", lambda: SHA + "-dirty")
    lst = _list_file(tmp_path, cfg, _member(ws), sha=SHA + "-dirty")
    assert _mark(cfg, lst, apply=True) == 2
    assert "uncommitted" in capsys.readouterr().err
    monkeypatch.setattr("llama.replay.code_identity", lambda: SHA)
    # an unmounted (empty) station refuses
    lst = _list_file(tmp_path, cfg, _member(ws))
    empty = tmp_path / "empty"
    empty.mkdir()
    cfg2 = tmp_path / "config2.toml"
    cfg2.write_text(f'root = "{root}"\ndelivery_path = "{empty}"\n')
    assert _mark(cfg2, _list_file(tmp_path, cfg2, _member(ws)), apply=True) == 2
    assert "mounted" in capsys.readouterr().err
    # nothing written by any refusal
    assert not (root / "campaign").exists()
    assert campaign.read_record(ws) is None
    assert (station / "s1" / "manifest.json").read_bytes() == originals
    assert "tools" not in _no_tools


def test_mark_apply_requires_pin_and_tools_floor(tmp_path, capsys, monkeypatch, _no_tools):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "s1", ["Tuning", "Bertha"])
    lst = _list_file(tmp_path, cfg, _member(ws, state="not on station"))
    assert _mark(cfg, lst) == 0                                   # the dry run needs neither
    assert _no_tools == {}
    assert _mark(cfg, lst, apply=True) == 0
    assert _no_tools["pin"] == root
    assert _no_tools["tools"] == {"pin": {"tag": "v2.24.0", "sha": SHA, "version": "2.24.0"},
                                  "minimum": jdr.JUNK_MARK_TOOLS_FLOOR}
    assert jdr.JUNK_MARK_TOOLS_FLOOR == "2.23.0"

    def refuse(root):
        raise campaign_gate.GateRefused("no pin: campaign/pin.json is missing")
    monkeypatch.setattr(jdr, "require_pinned_code", refuse)
    ws2 = _show(root, "s2", ["Tuning", "Bertha"])
    lst2 = _list_file(tmp_path, cfg, _member(ws2, state="not on station"))
    capsys.readouterr()
    assert _mark(cfg, lst2, apply=True) == 2
    assert "no pin" in capsys.readouterr().err
    assert campaign.read_record(ws2) is None
    assert not _batch_of(root, lst2).exists()


def test_mark_dry_run_writes_nothing(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    u1 = _show(root, "u1", ["Tuning", "Bertha"])
    _station(station, "u1", ["Tuning", "Bertha"])
    h1 = _show(root, "h1", ["Tuning", "Bertha"])
    _station(station, "h1", ["Tuning", "Bertha"])
    for s in ("u1", "h1"):
        _deliver(root, s)
    lst = _list_file(tmp_path, cfg, _member(u1), _member(h1, held=True))

    def snap(p):
        return {str(f.relative_to(p)): _stat(f) for f in sorted(p.rglob("*")) if f.is_file()}
    before = (snap(root), snap(station))
    assert _mark(cfg, lst) == 0
    text = capsys.readouterr().out
    assert "u1: unvoiced: would station-mark" in text
    assert "h1: unvoiced (held): would station-mark" in text
    assert "dry run: nothing written (pass --apply)" in text
    assert (snap(root), snap(station)) == before


# --- approval and recheck (plan Task 15; spec "Rollout" step 6, Stakes) --------------

def _reprocess(ws: ShowWorkspace, dropped=("t1.mp3",), *, flags=()) -> None:
    """The library show.json after step 4's re-process: each dropped file leaves `tracks`
    for an `excluded_files` row with reason `junk title`; `flags` hold the show."""
    show = Show.model_validate_json(ws.show.read_text())
    gone = [t for t in show.tracks if t.filename in dropped]
    kept = [t for t in show.tracks if t.filename not in dropped]
    rows = [{"filename": t.filename, "reasons": ["junk title"], "duration_sec": t.duration_sec,
             "title": t.title, "set": t.set, "after_track": 0} for t in gone]
    show = show.model_copy(update={"tracks": kept,
                                   "excluded_files": show.excluded_files + rows,
                                   "review_flags": list(flags), "needs_review": bool(flags)})
    ws.show.write_text(show.model_dump_json(indent=2))


def _voiced_member(ws: ShowWorkspace, *, state="voiced", presenter="phil",
                   backend_now="voxtral", clips=3, other=()) -> dict:
    m = _member(ws, state=state)
    m["station"] = {"state": state, "presenter": presenter, "backend_now": backend_now,
                    "clips": clips}
    m["drops"][0]["duration_sec"] = 280.0
    m["pairs"] = [{"station_file": "01 - Tuning.mp3", "station_title": "Tuning",
                   "source_file": "t1.mp3"}]
    m["other_differences"] = list(other)
    return m


def _voiced_show(root, station, slug, *, dj_audio=VOICED):
    ws = _show(root, slug, ["Tuning", "Bertha", "Sugaree"])
    _station(station, slug, ["Tuning", "Bertha", "Sugaree"], dj_audio=dj_audio)
    _reprocess(ws)
    return ws


def _approval(cfg, lst, status, *extra) -> int:
    return jdr.main(["approval", "--list", str(lst), "--emcee-status", str(status),
                     "--config", str(cfg), *extra])


def _recheck(cfg, lst, slug) -> int:
    return jdr.main(["recheck", "--list", str(lst), "--config", str(cfg), slug])


def _section(text: str, head: str) -> str:
    """The lines under the `head` heading, up to the next unindented line."""
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(head))
    out = []
    for l in lines[start + 1:]:
        if l and not l.startswith(" "):
            break
        out.append(l)
    return "\n".join(out)


def test_approval_uses_live_state(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    a = _voiced_show(root, station, "a")                 # voiced then and now
    b = _voiced_show(root, station, "b")                 # voiced since the list
    c = _voiced_show(root, station, "c")                 # unvoiced since the list
    lst = _list_file(tmp_path, cfg, _voiced_member(a, other=["set t3.mp3: 1 -> 2"]),
                     _voiced_member(b, state="unvoiced", presenter=None, backend_now=None,
                                    clips=0),
                     _voiced_member(c))
    one = {**VOICED, "set_intros": {"1": "dj-audio/set1.mp3"}, "outro": None}
    data = json.loads((station / "b" / "manifest.json").read_text())
    data["dj_audio"] = one
    (station / "b" / "manifest.json").write_text(json.dumps(data))
    data = json.loads((station / "c" / "manifest.json").read_text())
    data["dj_audio"] = None
    (station / "c" / "manifest.json").write_text(json.dumps(data))
    status = _status(tmp_path,
                     {"slug": "a", "voiced_by": "bob", "tts_now": {"backend": "mlx_audio"}},
                     {"slug": "b", "voiced_by": "phil", "tts_now": {"backend": "voxtral"}})
    assert _approval(cfg, lst, status) == 0
    text = capsys.readouterr().out
    ok = _section(text, "approvable")
    assert "a: presenter bob, backend_now mlx_audio, clips 3" in ok      # fresh, not listed
    assert "drop 'Tuning' 4:40 held no" in ok
    assert "other set t3.mp3: 1 -> 2" in ok
    assert "library hold flags: none" in ok
    assert "b: presenter phil, backend_now voxtral, clips 1" in ok
    assert "c:" not in ok
    assert "  c" in _section(text, "no longer voiced (unvoiced route)")


def test_approval_lists_held_apart(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    a = _voiced_show(root, station, "a")
    h = _voiced_show(root, station, "h")
    _reprocess(h, flags=["briefing contradicts the setlist: 'Dark Star'"])
    lst = _list_file(tmp_path, cfg, _voiced_member(a), _voiced_member(h))
    status = _status(tmp_path, *({"slug": s, "voiced_by": "phil",
                                  "tts_now": {"backend": "voxtral"}} for s in ("a", "h")))
    out = tmp_path / "approved.txt"
    assert _approval(cfg, lst, status, "--out", str(out)) == 0
    text = capsys.readouterr().out
    held = _section(text, "held (not approvable)")
    assert "h: presenter phil" in held
    assert "library hold flags: briefing contradicts the setlist: 'Dark Star'" in held
    assert "h:" not in _section(text, "approvable")
    assert out.read_text() == "a\n"


def test_approval_shows_null_and_unresolved_backend(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    shows = {s: _voiced_show(root, station, s) for s in ("n", "u", "x")}
    lst = _list_file(tmp_path, cfg, *(_voiced_member(ws) for ws in shows.values()))
    status = _status(tmp_path, {"slug": "n", "voiced_by": "phil", "tts_now": None},
                     {"slug": "u", "voiced_by": "phil",
                      "tts_now": {"unresolved": "no such presenter"}},
                     {"slug": "x", "voiced_by": "phil", "tts_now": {"backend": "voxtral"}})
    assert _approval(cfg, lst, status) == 0
    ok = _section(capsys.readouterr().out, "approvable")
    assert "n: presenter phil, backend_now null, clips 3" in ok
    assert "u: presenter phil, backend_now unresolved, clips 3" in ok
    # --backend narrows the voiced entries to one live backend
    assert _approval(cfg, lst, status, "--backend", "voxtral") == 0
    ok = _section(capsys.readouterr().out, "approvable")
    assert "x: presenter phil" in ok and "n:" not in ok and "u:" not in ok


def test_approval_writes_approvable_slugs(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    a = _voiced_show(root, station, "a")
    b = _voiced_show(root, station, "b")
    h = _voiced_show(root, station, "h")
    _reprocess(h, flags=["vet: research asserts a song not in the show"])
    g = _voiced_show(root, station, "g")
    data = json.loads((station / "g" / "manifest.json").read_text())
    data["dj_audio"] = None
    (station / "g" / "manifest.json").write_text(json.dumps(data))
    lst = _list_file(tmp_path, cfg, *(_voiced_member(ws) for ws in (a, b, h, g)))
    status = _status(tmp_path, *({"slug": s, "voiced_by": "phil",
                                  "tts_now": {"backend": "voxtral"}} for s in "abhg"))
    out = tmp_path / "approved.txt"
    assert _approval(cfg, lst, status, "--out", str(out)) == 0
    assert out.read_text() == "a\nb\n"
    # an --out inside the library or the station is refused, nothing written
    for bad in (root / "approved.txt", station / "approved.txt"):
        capsys.readouterr()
        assert _approval(cfg, lst, status, "--out", str(bad)) == 2
        assert "overlaps" in capsys.readouterr().err
        assert not bad.exists()
    # a list from other code or config is accepted (no identity gate); its identity is
    # printed as information
    capsys.readouterr()
    stale = _list_file(tmp_path, cfg, _voiced_member(a), sha="old", fingerprint="f" * 16)
    assert _approval(cfg, stale, status, "--out", str(out)) == 0
    text = capsys.readouterr().out
    assert "list: sha old, config_fingerprint ffffffffffffffff" in text
    assert "not checked" in text
    assert out.read_text() == "a\n"


def test_recheck_passes(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    ws = _voiced_show(root, station, "s1")
    lst = _list_file(tmp_path, cfg, _voiced_member(ws))
    assert _recheck(cfg, lst, "s1") == 0
    text = capsys.readouterr().out
    assert "FAIL" not in text and "leave s1 out" not in text
    assert text.count(": ok") == 4


def _recheck_fails(cfg, lst, slug, capsys, needle):
    capsys.readouterr()
    assert _recheck(cfg, lst, slug) == 1
    text = capsys.readouterr().out
    fail = [l for l in text.splitlines() if "FAIL" in l]
    assert fail and needle in fail[0]
    assert f"leave {slug} out of this batch" in text


def test_recheck_fails_after_include(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "s1", ["Tuning", "Bertha", "Sugaree"])
    _station(station, "s1", ["Tuning", "Bertha", "Sugaree"], dj_audio=VOICED)
    lst = _list_file(tmp_path, cfg, _voiced_member(ws))
    # `llama fix s1 --include t1.mp3`: the source file is kept, not excluded
    _recheck_fails(cfg, lst, "s1", capsys, "pair")
    # excluded for another reason is not the junk-title drop either
    show = Show.model_validate_json(ws.show.read_text())
    show = show.model_copy(update={
        "tracks": show.tracks[1:],
        "excluded_files": [{"filename": "t1.mp3", "reasons": ["operator excluded"]}]})
    ws.show.write_text(show.model_dump_json(indent=2))
    _recheck_fails(cfg, lst, "s1", capsys, "pair")
    # not a member at all
    _recheck_fails(cfg, lst, "nope", capsys, "member")


def test_recheck_fails_when_station_track_gone(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    ws = _voiced_show(root, station, "s1")
    lst = _list_file(tmp_path, cfg, _voiced_member(ws))
    path = station / "s1" / "manifest.json"
    data = json.loads(path.read_text())
    data["tracks"][0]["title"] = "Tuning Jam"            # same file, other title
    path.write_text(json.dumps(data))
    _recheck_fails(cfg, lst, "s1", capsys, "pair")
    data["tracks"] = data["tracks"][1:]                  # the file is gone
    path.write_text(json.dumps(data))
    _recheck_fails(cfg, lst, "s1", capsys, "pair")
    # an unvoiced copy fails the voiced check too
    ws2 = _voiced_show(root, station, "s2", dj_audio=None)
    lst = _list_file(tmp_path, cfg, _voiced_member(ws), _voiced_member(ws2))
    _recheck_fails(cfg, lst, "s2", capsys, "voiced")


def test_recheck_fails_on_held(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    ws = _voiced_show(root, station, "s1")
    _reprocess(ws, dropped=(), flags=["junk-title drop held for review: 'Tuning' (4:40, ...)"])
    show = Show.model_validate_json(ws.show.read_text())
    assert show.needs_review and any(r["filename"] == "t1.mp3" for r in show.excluded_files)
    lst = _list_file(tmp_path, cfg, _voiced_member(ws))
    _recheck_fails(cfg, lst, "s1", capsys, "held")


def test_recheck_reads_without_writing(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    ok = _voiced_show(root, station, "ok")
    held = _voiced_show(root, station, "held")
    _reprocess(held, dropped=(), flags=["vet: x"])
    lst = _list_file(tmp_path, cfg, _voiced_member(ok), _voiced_member(held))
    status = _status(tmp_path, {"slug": "ok", "voiced_by": "phil",
                                "tts_now": {"backend": "voxtral"}})

    def tree(base: Path):
        return {str(p.relative_to(base)): (hashlib.sha256(p.read_bytes()).hexdigest()
                                           if p.is_file() else None, p.stat().st_mtime_ns)
                for p in sorted(base.rglob("*"))}
    before = tree(tmp_path)
    assert _recheck(cfg, lst, "ok") == 0
    assert _recheck(cfg, lst, "held") == 1
    assert _recheck(cfg, lst, "nope") == 1
    assert _approval(cfg, lst, status) == 0
    assert tree(tmp_path) == before


def test_recheck_accepts_a_list_from_other_code(tmp_path, capsys, monkeypatch):
    cfg, root, station = _lib(tmp_path)
    ws = _voiced_show(root, station, "s1")
    lst = _list_file(tmp_path, cfg, _voiced_member(ws), sha="old", fingerprint="f" * 16)
    monkeypatch.setattr("llama.replay.code_identity", lambda: SHA + "-dirty")
    assert _recheck(cfg, lst, "s1") == 0
    assert "list: sha old, config_fingerprint ffffffffffffffff" in capsys.readouterr().out


def test_recheck_refuses_unmounted_station(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    ws = _voiced_show(root, station, "s1")
    lst = _list_file(tmp_path, cfg, _voiced_member(ws))
    empty = tmp_path / "empty"
    empty.mkdir()
    cfg2 = tmp_path / "config2.toml"
    cfg2.write_text(f'root = "{root}"\ndelivery_path = "{empty}"\n')
    capsys.readouterr()
    assert _recheck(cfg2, lst, "s1") == 2
    assert "empty" in capsys.readouterr().err
    gone = tmp_path / "gone"
    cfg2.write_text(f'root = "{root}"\ndelivery_path = "{gone}"\n')
    assert _recheck(cfg2, lst, "s1") == 2
    assert "station root" in capsys.readouterr().err


def test_recheck_refuses_a_damaged_list(tmp_path, capsys):
    cfg, root, station = _lib(tmp_path)
    ws = _voiced_show(root, station, "s1")
    twice = _list_file(tmp_path, cfg, _voiced_member(ws), _voiced_member(ws))
    capsys.readouterr()
    assert _recheck(cfg, twice, "s1") == 2
    assert "s1 is listed twice" in capsys.readouterr().err
    bad = {k: v for k, v in _voiced_member(ws).items() if k != "slug"}
    noslug = _list_file(tmp_path, cfg, _voiced_member(ws), bad)
    assert _recheck(cfg, noslug, "s1") == 2
    assert "a row without a slug or digests" in capsys.readouterr().err
