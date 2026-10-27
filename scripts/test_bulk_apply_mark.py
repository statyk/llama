"""scripts/bulk_apply.py freeze / reselect-check / mark / unmark (bulk-apply plan Task 15;
spec "The `awaiting_fix` contract", "The library side" (Marking skips), "Re-processing"
(GD re-selections)). Strict surfaces 1 and 4: station manifests are written.

A fixture library and a fixture station under tmp_path and a hand-built arm; no test
touches the real library, the real station, tools or processes (`emcee_running` is
stubbed for every test: a real emcee on this machine would otherwise refuse writes)."""
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bulk_apply as ba
from llama import campaign, campaign_gate, station_mark
from llama.config import load_config
from llama.models import (Candidate, Overrides, Overrule, Provenance, QualityAssessment,
                          RecordingSummary, Show, Track)
from llama.replay import config_fingerprint, input_digests
from llama.workspace import ShowWorkspace

IDENT = "band2001-01-01.aud"
OTHER = "band2001-01-01.sbd"
T_ARM = "2026-10-27T10:00:00+00:00"
T_LATER = "2026-10-27T11:00:00+00:00"
T_EARLIER = "2026-10-27T09:00:00+00:00"
SONG_FLAG = "briefing mentions unknown song: Golden Road"


@pytest.fixture(autouse=True)
def _no_emcee(monkeypatch):
    """The real check reads `ps`; tests opt in to a running emcee."""
    monkeypatch.setattr(station_mark, "emcee_running", lambda: [])
    monkeypatch.setattr(campaign_gate, "ps_lines", lambda: [])


# --- fixtures -------------------------------------------------------------------

def _lib(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "lib"
    (root / "shows").mkdir(parents=True)
    station = tmp_path / "station"
    station.mkdir()
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{root}"\ndelivery_path = "{station}"\n')
    return cfg, root, station


def _station_manifest(identifier: str, files, *, voiced: bool) -> dict:
    return {"version": 3, "source": {"identifier": identifier, "profile": "dead"},
            "tracks": [{"filename": f, "title": f"Song {i}", "set": "1"}
                       for i, f in enumerate(files, 1)],
            "dj_notes": {"file": "dj-notes.md"} if voiced else None,
            "dj_audio": {"dir": "dj-audio", "presenter": "phil"} if voiced else None}


def _show(root: Path, slug: str, *, files=("t1.mp3", "t2.mp3"), held=False,
          packaged=True, briefed=True, delivered=False, voiced=False, station=None,
          identifier=IDENT, recordings=None) -> ShowWorkspace:
    d = root / "shows" / slug
    d.mkdir(parents=True)
    ws = ShowWorkspace(d)
    pid = f"band/{slug}"
    recs = recordings or [RecordingSummary(identifier=identifier)]
    prov = Provenance(performance_id=pid, run="r1", dossier="dossier",
                      candidate=Candidate(performance_id=pid, collection="Band",
                                          date="2001-01-01", recordings=recs),
                      assessment=QualityAssessment(performance_id=pid, quality_score=8.0,
                                                   rationale="r"),
                      processed_at="2026-01-01T00:00:00+00:00")
    ws.provenance.write_text(prov.model_dump_json(indent=2))
    tracks = [Track(index=i, set="1", title=f"Song {i}", filename=f, title_source="tags")
              for i, f in enumerate(files, 1)]
    show = Show(performance_id=pid, identifier=identifier, artist="Band", date="2001-01-01",
                tracks=tracks, needs_review=held,
                review_flags=["low-confidence setlist"] if held else [])
    ws.show.write_text(show.model_dump_json(indent=2))
    if briefed:
        ws.briefing_json.write_text("{}")
    if packaged:
        (d / "package").mkdir()
        (d / "package" / "manifest.json").write_text("{}")
    if delivered:
        with (root / "ledger.jsonl").open("a") as f:
            f.write(json.dumps({"performance_id": pid, "artist": "Band", "date": "2001-01-01",
                                "status": "delivered", "run": "r1",
                                "recorded_at": "2026-01-01T00:00:00Z"}) + "\n")
        if station is not None:
            out = station / slug
            out.mkdir()
            (out / "manifest.json").write_text(
                json.dumps(_station_manifest(identifier, files, voiced=voiced), indent=2) + "\n")
    return ws


def _row(ws: ShowWorkspace, *, outcome="clean", **kw) -> dict:
    show = Show.model_validate_json(ws.show.read_text())
    row = {"slug": ws.dir.name, "state": "packaged", "outcome": outcome,
           "stored_brief_guard": None, "needs_llm": [], "title_changes": [],
           "set_changes": [], "segue_changes": [], "set_breaks": None, "venue": None,
           "city": None, "date": None, "alignment": None, "digests": input_digests(ws),
           "filenames": [t.filename for t in show.tracks]}
    row.update(kw)
    return row


def _arm(cfg: Path, *rows, sha="abc", generated_at=T_ARM) -> dict:
    return {"sha": sha, "config_fingerprint": config_fingerprint(load_config(cfg)),
            "generated_at": generated_at, "shows": {r["slug"]: r for r in rows}}


def _processed(ws: ShowWorkspace, *, batch="old") -> None:
    campaign.add_mark(ws, reason="changed by the held-backlog fixes: titles",
                      start_stage="gather", batch=batch, at="2026-10-01T00:00:00.000000Z")
    assert campaign.mark_processed(ws, held=False)


def _by_slug(items) -> dict:
    return {i.slug: i for i in items}


def _tree(root: Path) -> dict[str, tuple[str, int]]:
    return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(),
                                       p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*")) if p.is_file()}


def _files(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _item(slug, reason="changed by the held-backlog fixes: titles", start="gather",
          digests=None):
    return ba.MarkItem(slug, reason, start, digests)


def _records(batch: Path) -> list[dict]:
    path = batch / "record.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# --- freeze -----------------------------------------------------------------------

def test_freeze_refuses_to_overwrite(tmp_path):
    cfg, root, _ = _lib(tmp_path)
    a = _show(root, "a")
    b = _show(root, "b")
    arm = _arm(cfg, _row(a, outcome="needs-llm", needs_llm=["stored alignment llm"]),
               _row(b, outcome="clean"))
    path = ba.freeze(root, arm)
    assert path == root / "campaign" / "needs-llm-frozen.json"
    data = json.loads(path.read_text())
    assert data == {"arm_sha": "abc", "arm_generated_at": T_ARM, "slugs": ["a"]}
    before = path.read_bytes()
    with pytest.raises(ba.LlamaError, match="exists"):
        ba.freeze(root, _arm(cfg, _row(b, outcome="needs-llm")))
    assert path.read_bytes() == before
    # --campaign-dir points it elsewhere
    other = tmp_path / "scratch"
    assert ba.freeze(root, arm, campaign_dir=other) == other / "needs-llm-frozen.json"


# --- planning -------------------------------------------------------------------

def test_plan_marks_visible_changes_frozen_guard_and_reselections(tmp_path):
    cfg, root, _ = _lib(tmp_path)
    swap = _show(root, "swap")
    label = _show(root, "label")
    multi = _show(root, "multi")
    frozen = _show(root, "frozen")
    guard = _show(root, "guard")
    resel = _show(root, "resel")
    proc_guard = _show(root, "proc-guard")
    proc_changed = _show(root, "proc-changed")
    clean = _show(root, "clean")
    _processed(proc_guard)
    _processed(proc_changed)
    title = [{"index": 1, "old": "Song 1", "new": "Other", "old_source": "tags",
              "new_source": "tags"}]
    arm = _arm(cfg,
               _row(swap, outcome="clean-changed", filenames=["t1.mp3", "t9.mp3"]),
               _row(label, outcome="clean-changed",
                    title_changes=[{"index": 1, "old": "Song 1", "new": "Song 1",
                                    "old_source": "tags", "new_source": "setlist"}],
                    alignment={"old": "deterministic", "new": "taper"},
                    stored_brief_guard=[SONG_FLAG]),          # label-only: never marked
               _row(multi, outcome="clean-changed", title_changes=title,
                    venue={"old": "A", "new": "B"}),
               _row(frozen, outcome="needs-llm", needs_llm=["stored alignment llm"]),
               _row(guard, outcome="clean", stored_brief_guard=[SONG_FLAG]),
               _row(resel, outcome="clean"),
               _row(proc_guard, outcome="clean", stored_brief_guard=[SONG_FLAG]),
               _row(proc_changed, outcome="clean-changed", title_changes=title),
               _row(clean, outcome="clean"))
    items, unplannable = ba.mark_plan(root, arm, {"frozen", "label"},
                                      [{"slug": "resel", "stored": IDENT, "pick": OTHER}],
                                      set())
    assert unplannable == []
    got = {i.slug: (i.reason, i.start_stage) for i in items}
    assert got == {
        "swap": ("changed by the held-backlog fixes: files", "gather"),
        "multi": ("changed by the held-backlog fixes: titles, venue", "gather"),
        "frozen": ("replay needs an LLM call: stored alignment llm", "gather"),
        "guard": ("stored briefing fails today's guard", "gather"),
        "resel": (f"recording re-selection: {IDENT} -> {OTHER}", "select"),
        "proc-changed": ("changed by the held-backlog fixes: titles", "gather"),
    }
    by = _by_slug(items)
    assert by["swap"].digests == arm["shows"]["swap"]["digests"]
    assert by["resel"].digests is None


def test_mark_plan_guard_uses_only_held_problems(tmp_path):
    """Pointer (a): `stored_brief_guard` ignores overrules; split it with the show's
    recorded overrules, and mark for the guard only when a held problem remains."""
    cfg, root, _ = _lib(tmp_path)
    allover = _show(root, "allover")
    some = _show(root, "some")
    rule = Overrule(identifier=IDENT, kind="briefing-song", subject=["golden road"],
                    flag=SONG_FLAG, source="fix", at="2026-10-01T00:00:00+00:00")
    for ws in (allover, some):
        ws.overrides.write_text(Overrides(overrules=[rule]).model_dump_json())
    other = "briefing mentions unknown song: Dark Star"
    arm = _arm(cfg, _row(allover, stored_brief_guard=[SONG_FLAG]),
               _row(some, stored_brief_guard=[SONG_FLAG, other]))
    items, unplannable = ba.mark_plan(root, arm, set(), [], set())
    assert unplannable == []
    assert {i.slug: i.reason for i in items} == {
        "some": "stored briefing fails today's guard"}


def test_mark_plan_skips_processed_needs_llm_row_with_diff(tmp_path):
    cfg, root, _ = _lib(tmp_path)
    ws = _show(root, "p")
    _processed(ws)
    arm = _arm(cfg, _row(ws, outcome="needs-llm", needs_llm=["stored alignment llm"],
                         set_changes=[{"index": 2, "old": "1", "new": "2"}],
                         filenames=["t1.mp3", "t9.mp3"]))
    assert ba.mark_plan(root, arm, {"p"}, [], set()) == ([], [])


def test_mark_plan_ignores_needs_llm_diff_off_frozen_list(tmp_path):
    cfg, root, _ = _lib(tmp_path)
    ws = _show(root, "n")
    gone = _show(root, "u")
    arm = _arm(cfg, _row(ws, outcome="needs-llm", needs_llm=["stored alignment llm"],
                         set_changes=[{"index": 2, "old": "1", "new": "2"}],
                         filenames=["t1.mp3", "t9.mp3"]),
               _row(gone, outcome="unreplayable", unreplayable="CacheMiss: x",
                    filenames=[], title_changes=[{"index": 1, "old": "a", "new": "b"}]))
    assert ba.mark_plan(root, arm, set(), [], set()) == ([], [])
    # the frozen list (unprocessed) or a re-selection still marks them
    items, unplannable = ba.mark_plan(root, arm, {"n"},
                                      [{"slug": "u", "stored": IDENT, "pick": OTHER}], set())
    assert unplannable == []
    assert {i.slug: i.start_stage for i in items} == {"n": "gather", "u": "select"}


# --- the CLI gates -----------------------------------------------------------------

def _cli_fixture(tmp_path, monkeypatch, *, resel_at=T_LATER, delivered=True, station_ok=True):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "d1", delivered=delivered, station=station)
    if not station_ok:
        (station / "d1" / "manifest.json").write_text("{not json")
    arm = _arm(cfg, _row(ws, outcome="clean-changed", filenames=["t1.mp3", "t9.mp3"]))
    arm_path = tmp_path / "arm.json"
    arm_path.write_text(json.dumps(arm))
    camp = root / "campaign"
    camp.mkdir()
    (camp / "needs-llm-frozen.json").write_text(
        json.dumps({"arm_sha": "abc", "arm_generated_at": T_EARLIER, "slugs": []}))
    (camp / "reselections.json").write_text(json.dumps({"written_at": resel_at, "rows": []}))
    monkeypatch.setattr("llama.replay.code_identity", lambda: "abc")
    monkeypatch.setattr(ba, "require_tools", lambda echo, *, pin: None)
    campaign_gate.write_pin(root, tag="v2.20.0", sha="abc", version="2.20.0",
                            worktree="/w", replace=False)
    args = ["--config", str(cfg), "mark", "--arm", str(arm_path)]
    return cfg, root, station, ws, args


def test_mark_refuses_reselections_older_than_the_arm(tmp_path, monkeypatch, capsys):
    cfg, root, station, ws, args = _cli_fixture(tmp_path, monkeypatch, resel_at=T_EARLIER)
    before_lib, before_station = _files(root), _files(station)
    assert ba.main(args + ["--apply"]) == 2
    assert ("reselections.json predates the arm; re-run: bulk_apply.py reselect-check --write"
            in capsys.readouterr().err)
    assert ba.main(args) == 2                                       # the dry run too
    assert _files(root) == before_lib and _files(station) == before_station


def test_mark_refuses_an_arm_of_other_code_or_config(tmp_path, monkeypatch, capsys):
    cfg, root, station, ws, args = _cli_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr("llama.replay.code_identity", lambda: "def")
    assert ba.main(args) == 2
    monkeypatch.setattr("llama.replay.code_identity", lambda: "abc")
    arm = json.loads(Path(args[-1]).read_text())
    arm["config_fingerprint"] = "other"
    Path(args[-1]).write_text(json.dumps(arm))
    assert ba.main(args) == 2
    assert "fingerprint" in capsys.readouterr().err


def test_mark_dry_run_prints_counts_and_writes_nothing(tmp_path, monkeypatch, capsys):
    cfg, root, station = _lib(tmp_path)
    du = _show(root, "du", delivered=True, station=station)
    dv = _show(root, "dv", delivered=True, station=station, voiced=True)
    bad = _show(root, "bad", delivered=True, station=station)
    (station / "bad" / "manifest.json").write_text("[]")
    pk = _show(root, "pk")
    held = _show(root, "held", held=True, packaged=False)
    unrep = _show(root, "unrep")
    swap = dict(outcome="clean-changed", filenames=["t1.mp3", "t9.mp3"])
    arm = _arm(cfg, _row(du, **swap), _row(dv, **swap), _row(bad, **swap), _row(pk, **swap),
               _row(held, outcome="needs-llm", needs_llm=["stored alignment llm"]),
               _row(unrep, outcome="unreplayable", unreplayable="CacheMiss: md_x.json"))
    arm_path = tmp_path / "arm.json"
    arm_path.write_text(json.dumps(arm))
    scratch = tmp_path / "scratch"
    monkeypatch.setattr("llama.replay.code_identity", lambda: "abc")
    called = []
    monkeypatch.setattr(ba, "require_tools", lambda echo, *, pin: called.append(1))
    base = ["--config", str(cfg)]
    assert ba.main(base + ["freeze", "--arm", str(arm_path), "--campaign-dir", str(scratch)]) == 0
    (scratch / "reselections.json").write_text(json.dumps({"written_at": T_LATER, "rows": []}))
    before_lib, before_station = _files(root), _files(station)
    capsys.readouterr()
    assert ba.main(base + ["mark", "--arm", str(arm_path), "--campaign-dir", str(scratch)]) == 0
    out = capsys.readouterr().out
    assert _files(root) == before_lib and _files(station) == before_station
    assert not called
    assert ("changed by the held-backlog fixes: delivered unvoiced 1, delivered voiced 1, "
            "packaged 1, briefed 0, held 0") in out
    assert ("replay needs an LLM call: delivered unvoiced 0, delivered voiced 0, "
            "packaged 0, briefed 0, held 1") in out
    assert "voiced: 1: dv" in out
    assert "unreadable station manifests: 1" in out and "  bad: " in out
    assert "unreplayable, not marked: 1: unrep" in out
    assert "emcee running: no" in out
    assert "dry run: nothing written (pass --apply)" in out


# --- apply ----------------------------------------------------------------------

def _batch(tmp_path) -> Path:
    b = tmp_path / "lib" / "campaign" / "marking" / "0123456789abcdef"
    b.mkdir(parents=True)
    return b


def test_apply_writes_record_before_station(tmp_path, monkeypatch):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "d1", delivered=True, station=station)
    pk = _show(root, "p1")
    out = station / "d1"
    original = (out / "manifest.json").read_bytes()
    real = station_mark.write_mark
    seen = []

    def write_mark(o, *, reason, marked_at):
        rec = campaign.read_record(ws)
        seen.append((o, campaign.awaiting_fix(rec), rec.marks[-1].at == marked_at))
        return real(o, reason=reason, marked_at=marked_at)
    monkeypatch.setattr(station_mark, "write_mark", write_mark)
    batch = _batch(tmp_path)
    items = [_item("d1", digests=input_digests(ws)), _item("p1", digests=input_digests(pk))]
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=lambda m: None) == 0
    assert seen == [(out, True, True)]
    data = json.loads((out / "manifest.json").read_text())
    rec = campaign.read_record(ws)
    assert data["awaiting_fix"] == {"reason": "changed by the held-backlog fixes: titles",
                                    "marked_at": rec.marks[-1].at}
    assert rec.marks[-1].batch == batch.name and rec.marks[-1].start_stage == "gather"
    assert campaign.awaiting_fix(campaign.read_record(pk))
    assert (batch / "before" / "d1.json").read_bytes() == original
    lines = _records(batch)
    assert [(l["slug"], l["station"], l["mark_added"]) for l in lines] == [
        ("d1", "marked", True), ("p1", "not delivered", True)]
    d1 = lines[0]
    assert set(d1) == {"slug", "reason", "start_stage", "mark_added", "station",
                       "before_sha256", "after_sha256", "at"}
    assert d1["before_sha256"] == _sha(original)
    assert d1["after_sha256"] == _sha((out / "manifest.json").read_bytes())
    assert lines[1]["before_sha256"] is None and lines[1]["after_sha256"] is None


def test_rerun_skips_marked_items(tmp_path, monkeypatch):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "d1", delivered=True, station=station)
    batch = _batch(tmp_path)
    items = [_item("d1", digests=input_digests(ws))]
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=lambda m: None) == 0
    snapshot = (_files(root), _files(station))
    calls = []
    monkeypatch.setattr(station_mark, "write_mark", lambda *a, **k: calls.append(1))
    msgs = []
    assert ba.mark_apply(root, items, station_root=station, batch=batch, echo=msgs.append) == 0
    assert calls == []
    assert (_files(root), _files(station)) == snapshot
    assert len(_records(batch)) == 1
    assert any("d1" in m and "already recorded" in m for m in msgs)


def test_unreadable_station_manifest_is_refused_and_listed_exit_1(tmp_path):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "bad", delivered=True, station=station)
    ok = _show(root, "ok", delivered=True, station=station)
    (station / "bad" / "manifest.json").write_text("{not json")
    before = (station / "bad" / "manifest.json").read_bytes()
    batch = _batch(tmp_path)
    msgs = []
    items = [_item("bad", digests=input_digests(ws)), _item("ok", digests=input_digests(ok))]
    assert ba.mark_apply(root, items, station_root=station, batch=batch, echo=msgs.append) == 1
    assert (station / "bad" / "manifest.json").read_bytes() == before
    assert campaign.awaiting_fix(campaign.read_record(ws))          # the library side holds
    lines = {l["slug"]: l for l in _records(batch)}
    assert lines["bad"]["station"].startswith("refused: ")
    assert "station copy unreadable" in lines["bad"]["station"]
    assert lines["bad"]["mark_added"] is True
    assert lines["ok"]["station"] == "marked"
    listing = "\n".join(msgs)
    assert "not marked" in listing and "bad" in listing.split("not marked")[-1]
    # a re-run retries the refused item only, and it is still refused
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=lambda m: None) == 1
    again = [l for l in _records(batch) if l["slug"] == "bad"]
    assert len(again) == 2 and again[-1]["station"].startswith("refused: ")
    assert again[-1]["mark_added"] is True                           # still this batch's mark
    assert len(campaign.read_record(ws).marks) == 1                  # not marked twice


def test_oserror_from_the_station_write_is_refused_not_fatal(tmp_path, monkeypatch):
    """Pointer (c): a dropped mount under `_swap_in` refuses that item and the batch
    goes on."""
    cfg, root, station = _lib(tmp_path)
    a = _show(root, "a", delivered=True, station=station)
    b = _show(root, "b", delivered=True, station=station)
    real = station_mark.write_mark

    def write_mark(o, **k):
        if o.name == "a":
            raise OSError(5, "Input/output error")
        return real(o, **k)
    monkeypatch.setattr(station_mark, "write_mark", write_mark)
    batch = _batch(tmp_path)
    items = [_item("a", digests=input_digests(a)), _item("b", digests=input_digests(b))]
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=lambda m: None) == 1
    lines = {l["slug"]: l["station"] for l in _records(batch)}
    assert lines["a"].startswith("refused: ") and "Input/output error" in lines["a"]
    assert lines["b"] == "marked"


def test_emcee_running_stops_the_batch(tmp_path, monkeypatch):
    cfg, root, station = _lib(tmp_path)
    wss = [_show(root, s, delivered=True, station=station) for s in ("a", "b", "c")]
    pk = _show(root, "p")
    calls = []

    def running():
        calls.append(1)
        return [] if len(calls) == 1 else ["4242 1 /usr/local/bin/emcee run"]
    monkeypatch.setattr(station_mark, "emcee_running", running)
    b_before = (station / "b" / "manifest.json").read_bytes()
    c_before = (station / "c" / "manifest.json").read_bytes()
    batch = _batch(tmp_path)
    msgs = []
    items = [_item(ws.dir.name, digests=input_digests(ws)) for ws in wss]
    items.append(_item("p", digests=input_digests(pk)))
    assert ba.mark_apply(root, items, station_root=station, batch=batch, echo=msgs.append) == 1
    assert station_mark.mark_of(json.loads((station / "a" / "manifest.json").read_text()))
    assert (station / "b" / "manifest.json").read_bytes() == b_before
    assert (station / "c" / "manifest.json").read_bytes() == c_before
    lines = {l["slug"]: l for l in _records(batch)}
    assert lines["a"]["station"] == "marked"
    assert lines["b"]["station"].startswith("refused: ") and "emcee" in lines["b"]["station"]
    assert "c" not in lines and "p" not in lines
    assert campaign.read_record(ShowWorkspace(root / "shows" / "c")) is None
    listing = "\n".join(msgs)
    assert "emcee" in listing and "4242" in listing
    tail = listing.split("not marked")[-1]
    assert "b" in tail and "c" in tail and "p" in tail


def test_already_marked_station_copy_is_recorded(tmp_path):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "d1", delivered=True, station=station)
    station_mark.write_mark(station / "d1", reason="earlier", marked_at=T_ARM)
    before = (station / "d1" / "manifest.json").read_bytes()
    batch = _batch(tmp_path)
    assert ba.mark_apply(root, [_item("d1", digests=input_digests(ws))], station_root=station,
                         batch=batch, echo=lambda m: None) == 0
    assert (station / "d1" / "manifest.json").read_bytes() == before
    [line] = _records(batch)
    assert line["station"] == "already marked" and line["mark_added"] is True


def _listed(msgs) -> str:
    """The batch's not-marked listing (everything after its header)."""
    text = "\n".join(msgs)
    assert "not marked (" in text, text
    return text.split("not marked (")[-1]


def test_missing_station_copy_is_listed_exit_1_and_stays_listed(tmp_path):
    """Review I1 (ruling 2, 3): a delivered show with no station copy is not marked; the
    batch exits 1 listing it, and a re-run of the batch still does."""
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "gone", delivered=True)                  # ledger-delivered, no copy
    ok = _show(root, "ok", delivered=True, station=station)
    batch = _batch(tmp_path)
    items = [_item("gone", digests=input_digests(ws)), _item("ok", digests=input_digests(ok))]
    msgs = []
    assert ba.mark_apply(root, items, station_root=station, batch=batch, echo=msgs.append) == 1
    assert "gone" in _listed(msgs) and "ok:" not in _listed(msgs)
    assert {l["slug"]: l["station"] for l in _records(batch)} == {
        "gone": "no station copy", "ok": "marked"}
    msgs.clear()
    assert ba.mark_apply(root, items, station_root=station, batch=batch, echo=msgs.append) == 1
    assert "gone" in _listed(msgs) and "no station copy" in _listed(msgs)
    assert len(_records(batch)) == 2                          # nothing re-recorded


def test_station_copy_stat_error_is_refused_then_retried(tmp_path, monkeypatch):
    """Review I1 (ruling 1): a stat error other than ENOENT on the station copy (a flaky
    SMB mount) refuses the item, listed and retried; it is never "no station copy"."""
    import errno
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "flaky", delivered=True, station=station)
    out = station / "flaky"
    before = (out / "manifest.json").read_bytes()
    real_stat = os.stat

    def stat(path, *a, **k):
        if Path(path) == out:
            raise OSError(errno.EIO, "Input/output error", str(out))
        return real_stat(path, *a, **k)
    monkeypatch.setattr(os, "stat", stat)
    batch = _batch(tmp_path)
    items = [_item("flaky", digests=input_digests(ws))]
    msgs = []
    assert ba.mark_apply(root, items, station_root=station, batch=batch, echo=msgs.append) == 1
    [line] = _records(batch)
    assert line["station"].startswith("refused: station copy unreadable (")
    assert "Input/output error" in line["station"]
    assert "flaky" in _listed(msgs)
    assert (out / "manifest.json").read_bytes() == before
    monkeypatch.setattr(os, "stat", real_stat)
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=lambda m: None) == 0
    assert _records(batch)[-1]["station"] == "marked"
    assert station_mark.mark_of(json.loads((out / "manifest.json").read_text()))


def test_unreadable_station_root_is_refused_per_item(tmp_path):
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "d1", delivered=True, station=station)
    batch = _batch(tmp_path)
    msgs = []
    gone = tmp_path / "unmounted"
    assert ba.mark_apply(root, [_item("d1", digests=input_digests(ws))], station_root=gone,
                         batch=batch, echo=msgs.append) == 1
    [line] = _records(batch)
    assert line["station"] == f"refused: station root {gone} is not readable"
    assert line["mark_added"] is True
    assert "d1" in _listed(msgs)


def test_inputs_changed_row_skipped(tmp_path):
    cfg, root, station = _lib(tmp_path)
    d = _show(root, "d1", delivered=True, station=station)
    p = _show(root, "p1")
    dig_d, dig_p = input_digests(d), input_digests(p)
    station_before = _files(station)
    for ws in (d, p):
        ws.overrides.write_text(json.dumps({"narration": "vague"}))   # changed since the arm
    batch = _batch(tmp_path)
    msgs = []
    assert ba.mark_apply(root, [_item("d1", digests=dig_d)], station_root=station,
                         batch=batch, echo=msgs.append) == 1
    assert any("d1" in m and "skipped: inputs changed" in m for m in msgs)
    assert campaign.read_record(d) is None
    assert _files(station) == station_before
    msgs.clear()
    assert ba.mark_apply(root, [_item("p1", digests=dig_p)], station_root=station,
                         batch=batch, echo=msgs.append) == 0
    assert any("p1" in m and "skipped: inputs changed" in m for m in msgs)
    assert campaign.read_record(p) is None


def _apply_cli(tmp_path, monkeypatch):
    cfg, root, station, ws, args = _cli_fixture(tmp_path, monkeypatch)
    (station / ".d1.swap").mkdir()
    (station / ".d1.swap" / "manifest.json").write_text("{}")
    (station / "nomanifest").mkdir()
    (root / "rekey-applied.json").write_text(json.dumps({"snapshot": "/s"}))
    return cfg, root, station, ws, args


def test_station_backup_taken_once(tmp_path, monkeypatch):
    cfg, root, station, ws, args = _apply_cli(tmp_path, monkeypatch)
    original = (station / "d1" / "manifest.json").read_bytes()
    assert ba.main(args + ["--apply"]) == 0
    backup = root / "campaign" / "station-backup"
    index = json.loads((backup / "index.json").read_text())
    assert index["manifests"] == {"d1": _sha(original)}
    assert (backup / "d1" / "manifest.json").read_bytes() == original
    assert not (backup / ".d1.swap").exists()
    assert "nomanifest" in index["missing"]
    stamp = (backup / "index.json").stat().st_mtime_ns
    taken = []
    monkeypatch.setattr(ba, "take_station_backup",
                        lambda *a, **k: taken.append(1))
    assert ba.main(args + ["--apply"]) == 0
    assert taken == []
    assert (backup / "index.json").stat().st_mtime_ns == stamp
    assert (backup / "d1" / "manifest.json").read_bytes() == original


def test_mark_apply_retires_the_rekey_restore(tmp_path, monkeypatch):
    cfg, root, station, ws, args = _apply_cli(tmp_path, monkeypatch)
    assert ba.main(args + ["--apply"]) == 0
    [batch] = (root / "campaign" / "marking").iterdir()
    retired = json.loads((root / "rekey-applied.json").read_text())["retired"]
    assert retired["by"] == f"bulk-apply marking {batch.name}"
    inputs = json.loads((batch / "inputs.json").read_text())
    arm_bytes = Path(args[-1]).read_bytes()
    camp = root / "campaign"
    want = hashlib.sha256(arm_bytes + (camp / "needs-llm-frozen.json").read_bytes()
                          + (camp / "reselections.json").read_bytes()).hexdigest()[:16]
    assert batch.name == want
    assert inputs["arm_sha256"] == _sha(arm_bytes)
    assert campaign.awaiting_fix(campaign.read_record(ws))


def test_mark_apply_refuses_without_the_pin_or_tools(tmp_path, monkeypatch, capsys):
    cfg, root, station, ws, args = _apply_cli(tmp_path, monkeypatch)
    before_lib, before_station = _files(root), _files(station)

    def refuse(echo, *, pin):
        raise campaign_gate.GateRefused("refusing: emcee below 2.20.0: /a/emcee 2.18.0")
    monkeypatch.setattr(ba, "require_tools", refuse)
    assert ba.main(args + ["--apply"]) == 2
    assert "below 2.20.0" in capsys.readouterr().err
    assert _files(root) == before_lib and _files(station) == before_station


# --- re-selection check ------------------------------------------------------------

def _md(lineage: str, ident: str) -> dict:
    return {"metadata": {"lineage": lineage},
            "files": [{"name": f"{ident}-t{i}.mp3", "source": "original",
                       "format": "VBR MP3", "length": "05:00"} for i in (1, 2)]}


def _resel_fixture(tmp_path):
    cfg, root, station = _lib(tmp_path)
    cache = root / "cache"
    cache.mkdir()
    for ident, lineage in ((IDENT, "AUD > CDR"), (OTHER, "SBD > DAT")):
        (cache / f"md_{ident}.json").write_text(json.dumps(_md(lineage, ident)))
    recs = [RecordingSummary(identifier=IDENT), RecordingSummary(identifier=OTHER)]
    return cfg, root, station, recs


def test_reselect_rows_write_nothing_under_the_library(tmp_path):
    cfg, root, station, recs = _resel_fixture(tmp_path)
    _show(root, "p1", recordings=recs)
    config = load_config(cfg)
    before = _tree(root)
    rows = ba.reselect_rows(root, config, [{"show": "p1", "stored": IDENT}])
    assert rows == [{"slug": "p1", "stored": IDENT, "pick": OTHER}]
    assert _tree(root) == before


def test_reselect_rows_drop_voiced_and_already_reselected(tmp_path):
    cfg, root, station, recs = _resel_fixture(tmp_path)
    _show(root, "voiced", recordings=recs, delivered=True, station=station, voiced=True)
    _show(root, "unvoiced", recordings=recs, delivered=True, station=station)
    _show(root, "done", recordings=recs, identifier=OTHER)          # already on the pick
    _show(root, "held", recordings=recs, held=True, packaged=False)
    rows = ba.reselect_rows(root, load_config(cfg), [
        {"show": "voiced"}, {"show": "unvoiced"}, {"slug": "done"}, {"show": "held"}])
    assert rows == [{"slug": "unvoiced", "stored": IDENT, "pick": OTHER},
                    {"slug": "held", "stored": IDENT, "pick": OTHER}]


def test_reselect_check_cli_writes_the_list(tmp_path, monkeypatch, capsys):
    cfg, root, station, recs = _resel_fixture(tmp_path)
    _show(root, "p1", recordings=recs)
    src = tmp_path / "m3.json"
    src.write_text(json.dumps([{"show": "p1", "stored": IDENT}]))
    scratch = tmp_path / "scratch"
    base = ["--config", str(cfg), "reselect-check", "--source", str(src),
            "--campaign-dir", str(scratch)]
    assert ba.main(base) == 0
    assert not (scratch / "reselections.json").exists()
    assert ba.main(base + ["--write"]) == 0
    data = json.loads((scratch / "reselections.json").read_text())
    assert data["rows"] == [{"slug": "p1", "stored": IDENT, "pick": OTHER}]
    assert isinstance(data["written_at"], str)
    assert not (root / "campaign").exists()


# --- unmark ---------------------------------------------------------------------

def _marked(tmp_path, *slugs_delivered, packaged=()):
    cfg, root, station = _lib(tmp_path)
    wss = {}
    for s in slugs_delivered:
        wss[s] = _show(root, s, delivered=True, station=station)
    for s in packaged:
        wss[s] = _show(root, s)
    originals = {s: (station / s / "manifest.json").read_bytes() for s in slugs_delivered}
    batch = _batch(tmp_path)
    items = [_item(s, digests=input_digests(ws)) for s, ws in wss.items()]
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=lambda m: None) == 0
    return root, station, batch, wss, originals


def test_unmark_restores_bytes_and_removes_the_batch_mark(tmp_path):
    root, station, batch, wss, originals = _marked(tmp_path, "d1")
    ws = wss["d1"]
    campaign.add_mark(ws, reason="other", start_stage="gather", batch="earlier",
                      at="2026-01-01T00:00:00.000000Z")
    marked = (station / "d1" / "manifest.json").read_bytes()
    assert ba.unmark(root, batch, station_root=station, apply=False, echo=lambda m: None) == 0
    assert (station / "d1" / "manifest.json").read_bytes() == marked     # dry run
    assert ba.unmark(root, batch, station_root=station, apply=True, echo=lambda m: None) == 0
    assert (station / "d1" / "manifest.json").read_bytes() == originals["d1"]
    assert [m.batch for m in campaign.read_record(ws).marks] == ["earlier"]
    # idempotent
    assert ba.unmark(root, batch, station_root=station, apply=True, echo=lambda m: None) == 0
    assert (station / "d1" / "manifest.json").read_bytes() == originals["d1"]


def test_unmark_removes_library_only_marks(tmp_path):
    cfg, root, station = _lib(tmp_path)
    pk = _show(root, "pk")
    bad = _show(root, "bad", delivered=True, station=station)
    (station / "bad" / "manifest.json").write_text("{not json")
    earlier = _show(root, "earlier", delivered=True, station=station)
    campaign.add_mark(earlier, reason="x", start_stage="gather", batch="b0",
                      at="2026-01-01T00:00:00.000000Z")
    station_before = _files(station)
    batch = _batch(tmp_path)
    items = [_item(s, digests=input_digests(w)) for s, w in
             (("pk", pk), ("bad", bad))]
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=lambda m: None) == 1
    # `earlier` was already awaiting: this batch adds no library mark, but marks the station.
    # Exit 1: the batch's record still holds `bad` refused (the exit covers the whole record).
    assert ba.mark_apply(root, [_item("earlier", digests=input_digests(earlier))],
                         station_root=station, batch=batch, echo=lambda m: None) == 1
    lines = {l["slug"]: l for l in _records(batch)}
    assert lines["earlier"]["mark_added"] is False and lines["earlier"]["station"] == "marked"
    earlier_marked = (station / "earlier" / "manifest.json").read_bytes()
    assert ba.unmark(root, batch, station_root=station, apply=True, echo=lambda m: None) == 0
    assert campaign.read_record(pk).marks == []
    assert campaign.read_record(bad).marks == []
    assert _files(station)["bad/manifest.json"] == station_before["bad/manifest.json"]
    assert [m.batch for m in campaign.read_record(earlier).marks] == ["b0"]   # kept
    assert (station / "earlier" / "manifest.json").read_bytes() == earlier_marked


def test_unmark_refuses_a_manifest_changed_since_marking(tmp_path):
    root, station, batch, wss, originals = _marked(tmp_path, "d1")
    mf = station / "d1" / "manifest.json"
    data = json.loads(mf.read_text())
    data["dj_audio"] = {"dir": "dj-audio"}                          # emcee voiced it since
    mf.write_text(json.dumps(data, indent=2) + "\n")
    changed = mf.read_bytes()
    rec = campaign.read_record(wss["d1"]).model_dump_json()
    msgs = []
    assert ba.unmark(root, batch, station_root=station, apply=True, echo=msgs.append) == 1
    assert any("d1" in m and "station copy changed since marking" in m for m in msgs)
    assert mf.read_bytes() == changed
    assert campaign.read_record(wss["d1"]).model_dump_json() == rec


def test_unmark_lists_processed_shows(tmp_path):
    root, station, batch, wss, originals = _marked(tmp_path, "d1", packaged=("p1",))
    for ws in wss.values():
        assert campaign.mark_processed(ws, held=False)
    marked = (station / "d1" / "manifest.json").read_bytes()
    recs = {s: campaign.read_record(ws).model_dump_json() for s, ws in wss.items()}
    msgs = []
    assert ba.unmark(root, batch, station_root=station, apply=True, echo=msgs.append) == 1
    for s in ("d1", "p1"):
        assert any(s in m and "processed since marked: re-deliver instead" in m for m in msgs)
        assert campaign.read_record(wss[s]).model_dump_json() == recs[s]
    assert (station / "d1" / "manifest.json").read_bytes() == marked


# --- Task 15b: M1 (a station mark without its record line), M2 (unplannable shows),
# --- M3 (--campaign-dir with --apply) ----------------------------------------------

def test_crash_after_station_write_is_reversible(tmp_path, monkeypatch):
    """M1: a crash between the station write and its record line. The re-run recognises
    the batch's own mark (its `marked_at` is this batch's library mark `at`) and records
    `marked` from the saved before copy, so `unmark` puts the station copy back."""
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "d1", delivered=True, station=station)
    mf = station / "d1" / "manifest.json"
    original = mf.read_bytes()
    batch = _batch(tmp_path)
    items = [_item("d1", digests=input_digests(ws))]
    real_write, real_append = station_mark.write_mark, ba._append_jsonl
    wrote = []

    def write_mark(o, **k):
        result = real_write(o, **k)
        wrote.append(o)
        return result

    def append(path, row):
        if wrote:
            raise RuntimeError("killed")             # the crash: after the rename
        return real_append(path, row)
    monkeypatch.setattr(station_mark, "write_mark", write_mark)
    monkeypatch.setattr(ba, "_append_jsonl", append)
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=lambda m: None) == 1
    assert _records(batch) == []
    marked_at = station_mark.mark_of(json.loads(mf.read_text()))["marked_at"]
    assert marked_at == campaign.read_record(ws).marks[-1].at
    monkeypatch.setattr(ba, "_append_jsonl", real_append)
    monkeypatch.setattr(station_mark, "write_mark", real_write)
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=lambda m: None) == 0
    [line] = _records(batch)
    assert line["station"] == "marked" and line["mark_added"] is True
    assert line["before_sha256"] == _sha(original)
    assert line["after_sha256"] == _sha(mf.read_bytes())
    assert ba.unmark(root, batch, station_root=station, apply=True, echo=lambda m: None) == 0
    assert mf.read_bytes() == original
    assert campaign.read_record(ws).marks == []


def _concurrent_then_unsaved(tmp_path, monkeypatch):
    """The second before-copy save fails after `write_mark` succeeded: the station copy
    changed between marking's read and `write_mark`'s (so the before copy is re-saved),
    and that re-save raises."""
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "d1", delivered=True, station=station)
    mf = station / "d1" / "manifest.json"
    original = mf.read_bytes()
    real_write, real_durable = station_mark.write_mark, ba._write_durable
    pre_mark = []

    def write_mark(o, **k):
        data = json.loads(mf.read_text())
        data["dj_notes"] = {"file": "dj-notes.md"}           # another writer, just now
        mf.write_text(json.dumps(data, indent=2) + "\n")
        pre_mark.append(mf.read_bytes())
        monkeypatch.setattr(station_mark, "write_mark", real_write)
        return real_write(o, **k)
    saves = []

    def durable(path, data):
        if path.parent.name == "before":
            saves.append(path)
            if len(saves) == 2:
                raise OSError(28, "No space left on device")
        return real_durable(path, data)
    monkeypatch.setattr(station_mark, "write_mark", write_mark)
    monkeypatch.setattr(ba, "_write_durable", durable)
    batch = _batch(tmp_path)
    items = [_item("d1", digests=input_digests(ws))]
    msgs = []
    rc = ba.mark_apply(root, items, station_root=station, batch=batch, echo=msgs.append)
    monkeypatch.setattr(ba, "_write_durable", real_durable)
    return root, station, ws, mf, original, pre_mark[0], batch, items, rc, msgs


def test_before_save_failure_after_write_is_not_recorded_refused(tmp_path, monkeypatch):
    """M1: the station IS marked, so the line is not `refused: ...` (a re-run would
    otherwise retry it, see the mark and record `already marked`). It is listed (the
    before copy on disk is stale), and `unmark` reverses it from the record's shas."""
    root, station, ws, mf, original, pre_mark, batch, items, rc, msgs = (
        _concurrent_then_unsaved(tmp_path, monkeypatch))
    assert rc == 1
    [line] = _records(batch)
    assert not line["station"].startswith("refused")
    assert line["station"].startswith("marked, before copy not saved")
    assert "No space left on device" in line["station"]
    assert line["before_sha256"] == _sha(pre_mark)
    assert line["after_sha256"] == _sha(mf.read_bytes())
    assert "d1" in _listed(msgs)
    assert (batch / "before" / "d1.json").read_bytes() == original      # stale
    assert ba.unmark(root, batch, station_root=station, apply=True, echo=lambda m: None) == 0
    assert mf.read_bytes() == pre_mark
    assert campaign.read_record(ws).marks == []


def test_rerun_heals_an_unsaved_before_copy(tmp_path, monkeypatch):
    """M1: a re-run retries the unsaved line; the before copy is rebuilt from the station
    copy and verified against the record's before sha, saved, and recorded `marked`."""
    root, station, ws, mf, original, pre_mark, batch, items, rc, msgs = (
        _concurrent_then_unsaved(tmp_path, monkeypatch))
    marked = mf.read_bytes()
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=lambda m: None) == 0
    assert mf.read_bytes() == marked                               # no station write
    line = _records(batch)[-1]
    assert line["station"] == "marked"
    assert (line["before_sha256"], line["after_sha256"]) == (_sha(pre_mark), _sha(marked))
    assert (batch / "before" / "d1.json").read_bytes() == pre_mark
    assert ba.unmark(root, batch, station_root=station, apply=True, echo=lambda m: None) == 0
    assert mf.read_bytes() == pre_mark


def test_unmark_never_reports_success_over_this_batchs_station_mark(tmp_path):
    """M1: an `already marked` line with `mark_added: true` whose station copy carries
    this batch's `marked_at`, and no before copy to put it back from: listed, exit 1,
    nothing touched."""
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "d1", delivered=True, station=station)
    batch = _batch(tmp_path)
    at = "2026-10-27T12:00:00.000000Z"
    campaign.add_mark(ws, reason="changed by the held-backlog fixes: titles",
                      start_stage="gather", batch=batch.name, at=at)
    station_mark.write_mark(station / "d1", reason="changed by the held-backlog fixes: titles",
                            marked_at=at)
    ba._append_jsonl(batch / "record.jsonl", {
        "slug": "d1", "reason": "changed by the held-backlog fixes: titles",
        "start_stage": "gather", "mark_added": True, "station": "already marked",
        "before_sha256": None, "after_sha256": None, "at": at})
    marked = (station / "d1" / "manifest.json").read_bytes()
    rec = campaign.read_record(ws).model_dump_json()
    msgs = []
    assert ba.unmark(root, batch, station_root=station, apply=True, echo=msgs.append) == 1
    assert any(m.startswith("d1: ") and "this batch's mark" in m for m in msgs), msgs
    assert (station / "d1" / "manifest.json").read_bytes() == marked
    assert campaign.read_record(ws).model_dump_json() == rec


def test_unmark_lists_a_before_copy_with_no_record_line(tmp_path, monkeypatch):
    """M1: a run stopped between the station write and the record line, never re-run:
    `unmark` cannot see the show from the record alone; the before copy names it."""
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "d1", delivered=True, station=station)
    ok = _show(root, "p1")
    batch = _batch(tmp_path)
    real_append = ba._append_jsonl

    def append(path, row):
        if row["slug"] == "d1":
            raise RuntimeError("killed")
        return real_append(path, row)
    monkeypatch.setattr(ba, "_append_jsonl", append)
    items = [_item("d1", digests=input_digests(ws)), _item("p1", digests=input_digests(ok))]
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=lambda m: None) == 1
    marked = (station / "d1" / "manifest.json").read_bytes()
    msgs = []
    assert ba.unmark(root, batch, station_root=station, apply=True, echo=msgs.append) == 1
    assert any(m.startswith("d1: ") and "re-run the batch" in m for m in msgs), msgs
    assert (station / "d1" / "manifest.json").read_bytes() == marked
    assert campaign.awaiting_fix(campaign.read_record(ws))
    assert campaign.read_record(ok).marks == []                    # the rest reversed


def test_missing_show_dir_is_reported_not_dropped(tmp_path, monkeypatch, capsys):
    """M2: a re-selection row whose show directory is gone is listed, not dropped."""
    cfg, root, station, ws, args = _cli_fixture(tmp_path, monkeypatch)
    (root / "campaign" / "reselections.json").write_text(json.dumps(
        {"written_at": T_LATER, "rows": [{"slug": "gone", "stored": IDENT, "pick": OTHER}]}))
    capsys.readouterr()
    assert ba.main(args) == 1
    out = capsys.readouterr().out
    assert "unplannable shows: 1\n  gone: no show directory\n" in out
    assert "marking plan: 1 show(s)" in out                        # d1 still planned
    items, unplannable = ba.mark_plan(
        root, json.loads(Path(args[-1]).read_text()), set(),
        [{"slug": "gone", "stored": IDENT, "pick": OTHER}], set())
    assert [i.slug for i in items] == ["d1"]
    assert unplannable == [("gone", "no show directory")]


def test_unreadable_show_json_is_reported_not_dropped(tmp_path, monkeypatch, capsys):
    """M2: a visibly changed arm row whose show.json is not JSON is listed, not dropped."""
    cfg, root, station, ws, args = _cli_fixture(tmp_path, monkeypatch)
    ws.show.write_text("{not json")
    capsys.readouterr()
    assert ba.main(args) == 1
    out = capsys.readouterr().out
    assert "unplannable shows: 1\n  d1: show.json unreadable (" in out
    assert "marking plan: 0 show(s)" in out


def test_apply_refuses_while_shows_are_unplannable(tmp_path, monkeypatch, capsys):
    cfg, root, station, ws, args = _apply_cli(tmp_path, monkeypatch)
    ws.show.write_text("{not json")
    before_lib, before_station = _files(root), _files(station)
    capsys.readouterr()
    assert ba.main(args + ["--apply"]) == 2
    err = capsys.readouterr().err
    assert "unplannable" in err and "d1" in err
    assert not (root / "campaign" / "marking").exists()
    assert not (root / "campaign" / "station-backup").exists()
    assert _files(root) == before_lib and _files(station) == before_station


def test_campaign_dir_refused_with_apply(tmp_path, monkeypatch, capsys):
    """M3: llama reads the frozen list from <root>/campaign only."""
    cfg, root, station, ws, args = _apply_cli(tmp_path, monkeypatch)
    scratch = tmp_path / "scratch"
    before_lib, before_station = _files(root), _files(station)
    capsys.readouterr()
    assert ba.main(args + ["--apply", "--campaign-dir", str(scratch)]) == 2
    assert capsys.readouterr().err == (
        f"refusing --campaign-dir with --apply: campaign state must live in {root}/campaign "
        "(the dry run may use a scratch dir)\n")
    assert not scratch.exists()
    assert _files(root) == before_lib and _files(station) == before_station


def test_rerun_marks_the_station_with_the_batchs_own_at(tmp_path, monkeypatch):
    """M1: a re-run after a refusal writes the station mark with the batch's library mark
    `at`, so a later crash after that write is still recognised as this batch's mark."""
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "d1", delivered=True, station=station)
    batch = _batch(tmp_path)
    items = [_item("d1", digests=input_digests(ws))]
    monkeypatch.setattr(station_mark, "emcee_running", lambda: ["4242 1 emcee run"])
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=lambda m: None) == 1
    at = campaign.read_record(ws).marks[-1].at
    monkeypatch.setattr(station_mark, "emcee_running", lambda: [])
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=lambda m: None) == 0
    mark = station_mark.mark_of(json.loads((station / "d1" / "manifest.json").read_text()))
    assert mark["marked_at"] == at
    assert _records(batch)[-1]["at"] == at


# --- Task 15b fix round 1: pin the review's surviving mutants M1, M2, M7 ------------

def _crash_after_station_write(tmp_path, monkeypatch, *, newline=True):
    """One delivered show marked by a run that stopped between its station write and
    its record line (the library mark and the before copy are on disk)."""
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "d1", delivered=True, station=station)
    mf = station / "d1" / "manifest.json"
    if not newline:                                   # llama's own encoding
        mf.write_bytes(json.dumps(json.loads(mf.read_text()), indent=2).encode())
    original = mf.read_bytes()
    batch = _batch(tmp_path)
    items = [_item("d1", digests=input_digests(ws))]
    real_append = ba._append_jsonl

    def append(path, row):
        raise RuntimeError("killed")
    monkeypatch.setattr(ba, "_append_jsonl", append)
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=lambda m: None) == 1
    monkeypatch.setattr(ba, "_append_jsonl", real_append)
    assert _records(batch) == []
    assert station_mark.mark_of(json.loads(mf.read_text())) is not None
    return root, station, ws, mf, original, batch, items


def test_unverified_own_mark_is_recorded_and_listed(tmp_path, monkeypatch):
    """Mutant M1: the station copy carries this batch's `marked_at`, but another writer
    changed it since (so neither kind of evidence verifies): `_UNVERIFIED`, listed, exit 1,
    the station copy untouched."""
    root, station, ws, mf, original, batch, items = _crash_after_station_write(
        tmp_path, monkeypatch)
    data = json.loads(mf.read_text())
    data["dj_notes"] = {"file": "dj-notes.md"}                   # emcee, since the mark
    mf.write_text(json.dumps(data, indent=2) + "\n")
    changed = mf.read_bytes()
    msgs = []
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=msgs.append) == 1
    [line] = _records(batch)
    assert line["station"] == ba._UNVERIFIED
    assert line["mark_added"] is True and line["before_sha256"] is None
    assert line["after_sha256"] == _sha(changed)
    assert "d1" in _listed(msgs)
    assert mf.read_bytes() == changed


@pytest.mark.parametrize("station_line", ["refused: Input/output error",
                                          "marked, before copy not saved (x)"])
def test_unmark_lists_an_unreadable_station_copy_with_a_before_copy(tmp_path, station_line):
    """Mutant M2: the batch saved a before copy (it attempted a station write) and the
    station copy cannot be read now: `unmark` cannot tell whether it carries this batch's
    mark, so it lists it (exit 1) and keeps the library mark."""
    cfg, root, station = _lib(tmp_path)
    ws = _show(root, "d1", delivered=True, station=station)
    mf = station / "d1" / "manifest.json"
    batch = _batch(tmp_path)
    at = "2026-10-27T12:00:00.000000Z"
    campaign.add_mark(ws, reason="changed by the held-backlog fixes: titles",
                      start_stage="gather", batch=batch.name, at=at)
    (batch / "before").mkdir()
    (batch / "before" / "d1.json").write_bytes(mf.read_bytes())
    mf.write_text("{not json")
    ba._append_jsonl(batch / "record.jsonl", {
        "slug": "d1", "reason": "changed by the held-backlog fixes: titles",
        "start_stage": "gather", "mark_added": True, "station": station_line,
        "before_sha256": None, "after_sha256": None, "at": at})
    rec = campaign.read_record(ws).model_dump_json()
    msgs = []
    assert ba.unmark(root, batch, station_root=station, apply=True, echo=msgs.append) == 1
    assert any(m.startswith("d1: cannot check the station copy for this batch's mark")
               for m in msgs), msgs
    assert campaign.read_record(ws).model_dump_json() == rec
    assert mf.read_text() == "{not json"


def test_recognises_own_mark_on_a_copy_with_no_trailing_newline(tmp_path, monkeypatch):
    """Mutant M7: evidence (1) re-encodes with the before copy's own trailing-newline
    rule, as `write_mark` does; a llama-encoded copy (no trailing newline) is recognised
    as `marked` and put back byte-identical."""
    root, station, ws, mf, original, batch, items = _crash_after_station_write(
        tmp_path, monkeypatch, newline=False)
    assert not original.endswith(b"\n")
    assert ba.mark_apply(root, items, station_root=station, batch=batch,
                         echo=lambda m: None) == 0
    [line] = _records(batch)
    assert line["station"] == "marked"
    assert line["before_sha256"] == _sha(original)
    assert ba.unmark(root, batch, station_root=station, apply=True, echo=lambda m: None) == 0
    assert mf.read_bytes() == original
