"""scripts/bulk_apply.py backfill: the overrule backfill from the overnight verdicts
(bulk-apply plan Task 14; spec "Overrules persist" (Backfill), "Undo", "Rollout").

Verdict fixtures of both layouts are written inline; no test touches the real
library, the real verdicts, tools or processes."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bulk_apply as ba
from llama import batch_snapshot, campaign_gate
from llama.models import Overrides, Show, Track
from llama.workspace import read_model

IDENT = "band2001-01-01.sbd"


# --- fixtures -------------------------------------------------------------------

def _lib(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "lib"
    (root / "shows").mkdir(parents=True)
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{root}"\n')
    verdicts = tmp_path / "verdicts"
    verdicts.mkdir()
    return cfg, root, verdicts


def _show(root: Path, slug: str, *, files=("t01.mp3", "t02.mp3", "t03.mp3"),
          unresolved=(), held=False, flags=(), packaged=True, identifier=IDENT) -> Path:
    d = root / "shows" / slug
    d.mkdir(parents=True)
    tracks = [Track(index=i, set="1", title=("" if fn in unresolved else f"Song {i}"),
                    filename=fn, title_source=("unresolved" if fn in unresolved else "tags"))
              for i, fn in enumerate(files, 1)]
    show = Show(performance_id=f"band/{slug}", identifier=identifier, artist="Band",
                date="2001-01-01", tracks=tracks, needs_review=held,
                review_flags=list(flags))
    (d / "show.json").write_text(show.model_dump_json(indent=2))
    if packaged:
        (d / "package").mkdir()
        (d / "package" / "manifest.json").write_text("{}")
    return d


def _row(slug, *, gather=(), vet=(), brief=(), title_sources=("tags", "tags", "tags"),
         outcome="newly-held", state="packaged") -> dict:
    return {"slug": slug, "outcome": outcome, "state": state, "gather_flags": list(gather),
            "vet_flags": list(vet), "brief_flags": list(brief),
            "title_sources": list(title_sources)}


def _base(*rows) -> dict:
    return {"sha": "e37f670", "shows": {r["slug"]: r for r in rows}}


def _verdict_a(verdicts: Path, slug: str, rulings, overrule_if_reheld_on=()) -> None:
    """Layout A: `flags[].{flag, verdict}`, `action.overrule_if_reheld_on`."""
    (verdicts / f"{slug}.json").write_text(json.dumps({
        "slug": slug,
        "flags": [{"flag": f, "verdict": v, "why": "w", "confidence": "high"}
                  for f, v in rulings],
        "evidence": [],
        "action": {"kind": "overrule", "steps": [], "rationale": "r",
                   "overrule_if_reheld_on": list(overrule_if_reheld_on)},
        "show_correct_after_action": True, "root_causes": [], "needed_beyond_bundle": [],
    }))


def _verdict_b(verdicts: Path, slug: str, rulings, other_flags=()) -> None:
    """Layout B: `claims[].{flag, verdict}`, `other_flags[].{flag, assessment}`."""
    (verdicts / f"{slug}.json").write_text(json.dumps({
        "slug": slug,
        "claims": [{"flag": f, "verdict": v, "why": "w", "decisive_evidence": [],
                    "confidence": "medium"} for f, v in rulings],
        "other_flags": [{"flag": f, "assessment": "a"} for f in other_flags],
        "design_notes": "",
        "action": {"kind": "hold", "commands": [], "rationale": "r"},
        "show_correct_after_action": False, "root_causes": [], "needed_beyond_bundle": [],
    }))


def _by_slug(plan) -> dict:
    return {s.slug: s for s in plan}


def _tree(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


# --- planning -------------------------------------------------------------------

def test_layout_a_spurious_is_recorded_real_is_listed(tmp_path):
    _, root, verdicts = _lib(tmp_path)
    _show(root, "a1")
    _verdict_a(verdicts, "a1", [
        ("research asserts unknown song: Golden", "spurious"),
        ("venue mismatch: archive 'The Fillmore' vs jerrybase 'Fillmore West'",
         "real-fixed-by-action"),
        ("low-confidence setlist", "undecidable"),
    ])
    base = _base(_row("a1",
                      gather=["venue mismatch: archive 'The Fillmore' vs jerrybase "
                              "'Fillmore West'", "low-confidence setlist",
                              "duration mismatch on t02.mp3: 100s vs 300s"],
                      vet=["research asserts unknown song: Golden",
                           "research asserts unknown song: Strangulation"]))
    s = _by_slug(ba.plan_backfill(root, base, verdicts, set()))["a1"]
    assert s.show_reason is None
    assert [(r.flag, r.kind, r.subject, r.source, r.identifier) for r in s.record] == [
        ("research asserts unknown song: Golden", "research-song", ["golden"], "backfill",
         IDENT)]
    assert sorted(s.listed) == sorted([
        ("venue mismatch: archive 'The Fillmore' vs jerrybase 'Fillmore West'",
         "ruled real-fixed-by-action"),
        ("low-confidence setlist", "ruled undecidable"),
        ("duration mismatch on t02.mp3: 100s vs 300s", "not overrulable (package flag)"),
        ("research asserts unknown song: Strangulation", "verdict never ruled on this flag"),
    ])


def test_layout_b_flag_spurious_recorded_research_right_show_wrong_listed(tmp_path):
    _, root, verdicts = _lib(tmp_path)
    _show(root, "b1")
    _verdict_b(verdicts, "b1", [
        ("research asserts unknown song: Catfish John", "flag-spurious"),
        ("research asserts unknown song: Jugband Song", "research-right-show-wrong"),
        ("research asserts wrong date: 1997-04-05", "research-wrong"),
        ("structure has 2 sets but jerrybase shows 1", "spurious"),   # layout A's value
    ], other_flags=["single-set structure for a long show (152 min)"])
    base = _base(_row("b1",
                      gather=["structure has 2 sets but jerrybase shows 1",
                              "single-set structure for a long show (152 min)"],
                      vet=["research asserts unknown song: Catfish John",
                           "research asserts unknown song: Jugband Song",
                           "research asserts wrong date: 1997-04-05"]))
    s = _by_slug(ba.plan_backfill(root, base, verdicts, set()))["b1"]
    assert [r.flag for r in s.record] == ["research asserts unknown song: Catfish John"]
    assert sorted(s.listed) == sorted([
        ("structure has 2 sets but jerrybase shows 1", "ruled spurious"),
        ("single-set structure for a long show (152 min)", "only in other_flags (free text)"),
        ("research asserts unknown song: Jugband Song", "ruled research-right-show-wrong"),
        ("research asserts wrong date: 1997-04-05", "ruled research-wrong"),
    ])


def test_overrule_if_reheld_on_records(tmp_path):
    _, root, verdicts = _lib(tmp_path)
    _show(root, "c1")
    _verdict_a(verdicts, "c1", [
        ("jerrybase set closer 'Sugar Magnolia' is not at a set break",
         "real-fixed-by-action"),
    ], overrule_if_reheld_on=[
        "jerrybase set closer 'Sugar Magnolia' is not at a set break",
        "research asserts 3 sets but structure has 2",
    ])
    base = _base(_row("c1", gather=["jerrybase set closer 'Sugar Magnolia' is not at a set "
                                    "break"],
                      vet=["research asserts 3 sets but structure has 2"]))
    s = _by_slug(ba.plan_backfill(root, base, verdicts, set()))["c1"]
    assert [(r.flag, r.kind, r.subject) for r in s.record] == [
        ("jerrybase set closer 'Sugar Magnolia' is not at a set break", "jerrybase-closer",
         ["sugar magnolia"]),
        ("research asserts 3 sets but structure has 2", "research-sets", None),
    ]
    assert s.listed == []


def test_no_verdict_lists_the_show(tmp_path, capsys):
    cfg, root, verdicts = _lib(tmp_path)
    _show(root, "d1")
    _show(root, "d2")
    _verdict_a(verdicts, "d2", [("low-confidence setlist", "spurious")])
    base = _base(_row("d1", gather=["low-confidence setlist"]),
                 _row("d2", gather=["low-confidence setlist"]))
    plan = _by_slug(ba.plan_backfill(root, base, verdicts, set()))
    assert plan["d1"].show_reason == "no verdict"
    assert plan["d1"].record == [] and plan["d1"].listed == []
    base_path = tmp_path / "base.json"
    base_path.write_text(json.dumps(base))
    assert ba.main(["backfill", "--base", str(base_path), "--verdicts", str(verdicts),
                    "--config", str(cfg)]) == 0
    out = capsys.readouterr().out
    assert "d1: no verdict" in out
    assert "record: low-confidence setlist" in out
    totals = out.strip().splitlines()[-2]
    assert ("shows considered 2, shows with no verdict 1, flags recorded 1, flags listed 0, "
            "shows fully covered 1 of 1") in totals


def test_show_held_today_is_skipped(tmp_path):
    _, root, verdicts = _lib(tmp_path)
    _show(root, "e1", held=True, flags=["low-confidence setlist"])
    _show(root, "e2")
    _show(root, "e3")
    for slug in ("e1", "e2", "e3"):
        _verdict_a(verdicts, slug, [("low-confidence setlist", "spurious")])
    base = _base(_row("e1", gather=["low-confidence setlist"]),          # held today
                 _row("e2", gather=["low-confidence setlist"], state="held"),  # held at base
                 _row("e3", gather=["low-confidence setlist"], outcome="still-held"),
                 _row("e4", gather=["low-confidence setlist"], outcome="clean"))
    assert ba.plan_backfill(root, base, verdicts, set()) == []


def test_titles_subject_from_base_title_sources(tmp_path):
    _, root, verdicts = _lib(tmp_path)
    # Today's show resolved every title (fixed since the base): the subject must come
    # from the base row's title_sources, never from today's show.json.
    _show(root, "f1", files=("a.mp3", "b.mp3", "c.mp3"))
    _show(root, "f2", files=("a.mp3", "b.mp3"))              # count differs from the base
    _show(root, "f3", files=("a.mp3", "b.mp3", "c.mp3"), unresolved=("a.mp3",))
    for slug in ("f1", "f2", "f3"):
        _verdict_a(verdicts, slug, [("unresolved track titles", "spurious")])
    base = _base(
        _row("f1", gather=["unresolved track titles"],
             title_sources=["unresolved", "tags", "unresolved"]),
        _row("f2", gather=["unresolved track titles"],
             title_sources=["unresolved", "tags", "unresolved"]),
        _row("f3", gather=["unresolved track titles"],
             title_sources=["tags", "unresolved", "tags"]))
    plan = _by_slug(ba.plan_backfill(root, base, verdicts, set()))
    [r] = plan["f1"].record
    assert (r.kind, r.subject, r.identifier) == ("titles", ["a.mp3", "c.mp3"], IDENT)
    assert plan["f2"].record == []
    assert plan["f2"].listed == [("unresolved track titles",
                                  "cannot derive the unresolved files")]
    [r3] = plan["f3"].record
    assert r3.subject == ["b.mp3"]          # base positions, not today's unresolved a.mp3


# --- apply ----------------------------------------------------------------------

def _pin(root: Path, monkeypatch) -> None:
    campaign_gate.write_pin(root, tag="v2.20.0", sha="abc", version="2.20.0",
                            worktree="/w", replace=False)
    monkeypatch.setattr("llama.replay.code_identity", lambda: "abc")


def _apply_fixture(tmp_path):
    cfg, root, verdicts = _lib(tmp_path)
    d = _show(root, "g1", files=("a.mp3", "b.mp3"))
    (d / "overrides.json").write_text(json.dumps({"narration": "vague"}))
    _show(root, "g2")                                     # nothing to record: untouched
    _verdict_a(verdicts, "g1", [("research asserts unknown song: Golden", "spurious"),
                                ("unresolved track titles", "spurious")])
    _verdict_a(verdicts, "g2", [("low-confidence setlist", "real-not-fixable")])
    base = _base(_row("g1", vet=["research asserts unknown song: Golden"],
                      gather=["unresolved track titles"],
                      title_sources=["tags", "unresolved"]),
                 _row("g2", gather=["low-confidence setlist"]))
    base_path = tmp_path / "base.json"
    base_path.write_text(json.dumps(base))
    (root / "rekey-applied.json").write_text(json.dumps({"snapshot": "/s"}))
    args = ["backfill", "--base", str(base_path), "--verdicts", str(verdicts),
            "--config", str(cfg)]
    return cfg, root, args


def test_apply_snapshots_retires_and_is_idempotent(tmp_path, monkeypatch, capsys):
    cfg, root, args = _apply_fixture(tmp_path)
    _pin(root, monkeypatch)
    order = []
    monkeypatch.setattr(ba, "require_tools", lambda echo, *, pin: order.append("tools"))
    real_take = batch_snapshot.take
    def take(snap, r, slugs, *, station_root):
        order.append(("take", list(slugs)))
        assert not json.loads((root / "rekey-applied.json").read_text()).get("retired")
        return real_take(snap, r, slugs, station_root=station_root)
    monkeypatch.setattr(ba.batch_snapshot, "take", take)
    g2_before = _tree(root / "shows" / "g2")

    assert ba.main(args + ["--apply"]) == 0
    assert order == ["tools", ("take", ["g1"])]
    ov = read_model(root / "shows" / "g1" / "overrides.json", Overrides)
    assert ov.narration == "vague"                                  # kept
    assert [(r.kind, r.subject, r.source) for r in ov.overrules] == [
        ("titles", ["b.mp3"], "backfill"), ("research-song", ["golden"], "backfill")]
    [bdir] = (root / "campaign" / "backfill").iterdir()
    stamp = bdir.name
    assert (bdir / "snapshot" / "manifest.json").exists()
    after = [json.loads(l) for l in (bdir / "snapshot" / "after.jsonl").read_text().splitlines()]
    assert [a["slug"] for a in after] == ["g1"]
    rec = [json.loads(l) for l in (bdir / "record.jsonl").read_text().splitlines()]
    assert [r["slug"] for r in rec] == ["g1"] and len(rec[0]["added"]) == 2
    retired = json.loads((root / "rekey-applied.json").read_text())["retired"]
    assert retired["by"] == f"bulk-apply overrule backfill {stamp}"
    assert _tree(root / "shows" / "g2") == g2_before
    # The after-record is the show's final state: a restore of this batch is not refused.
    results = batch_snapshot.restore(bdir / "snapshot", root, station_root=None, apply=False,
                                     echo=lambda _m: None)
    assert results and not any(a.startswith("refused") for _, a in results)

    before = _tree(root)
    assert ba.main(args + ["--apply"]) == 0                         # re-run
    assert _tree(root) == before                                    # wrote nothing
    assert len(list((root / "campaign" / "backfill").iterdir())) == 1


def test_apply_refuses_without_gates(tmp_path, monkeypatch, capsys):
    cfg, root, args = _apply_fixture(tmp_path)
    before = _tree(root)
    assert ba.main(args + ["--apply"]) == 2                         # no pin
    assert "pin" in capsys.readouterr().err
    assert _tree(root) == before
    _pin(root, monkeypatch)
    before = _tree(root)
    def refuse(echo, *, pin):
        raise campaign_gate.GateRefused("refusing: llama below 2.20.0: /a/llama 2.18.0")
    monkeypatch.setattr(ba, "require_tools", refuse)
    assert ba.main(args + ["--apply"]) == 2
    assert "below 2.20.0" in capsys.readouterr().err
    assert _tree(root) == before
    monkeypatch.setattr("llama.replay.code_identity", lambda: "abc-dirty")
    monkeypatch.setattr(ba, "require_tools", lambda echo, *, pin: None)
    assert ba.main(args + ["--apply"]) == 2                         # not the pinned code
    assert _tree(root) == before


def test_dry_run_writes_nothing(tmp_path, monkeypatch, capsys):
    cfg, root, args = _apply_fixture(tmp_path)
    before = _tree(tmp_path)
    called = []
    monkeypatch.setattr(ba, "require_tools", lambda echo, *, pin: called.append(1))
    assert ba.main(args) == 0
    assert _tree(tmp_path) == before
    assert not called
    out = capsys.readouterr().out
    assert "g1:" in out and "record: research asserts unknown song: Golden" in out
    assert "list: low-confidence setlist (ruled real-not-fixable)" in out
    assert "dry run: nothing written (pass --apply)" in out


def test_a_failed_after_record_rolls_the_show_back(tmp_path, monkeypatch, capsys):
    """Spec "Undo": a write the batch cannot record is undone, so every write of the batch
    stays restorable (review fix: no overrides.json left rewritten without an after-record)."""
    cfg, root, args = _apply_fixture(tmp_path)
    _pin(root, monkeypatch)
    monkeypatch.setattr(ba, "require_tools", lambda echo, *, pin: None)
    ov = root / "shows" / "g1" / "overrides.json"
    before = ov.read_bytes()
    real = batch_snapshot.record_after
    def boom(*a, **k):
        raise OSError("station mount dropped")
    monkeypatch.setattr(ba.batch_snapshot, "record_after", boom)
    assert ba.main(args + ["--apply"]) == 1
    assert ov.read_bytes() == before                                # rolled back
    [first] = (root / "campaign" / "backfill").iterdir()
    assert not (first / "snapshot" / "after.jsonl").exists()
    assert not (first / "record.jsonl").exists()
    assert not (root / "shows" / "g1" / ".txn").exists()
    [(_, action)] = batch_snapshot.restore(first / "snapshot", root, station_root=None,
                                           apply=False, echo=lambda _m: None)
    assert action == "untouched"

    monkeypatch.setattr(ba.batch_snapshot, "record_after", real)
    monkeypatch.setattr(ba, "_stamp", lambda: "20991231T000000Z")
    assert ba.main(args + ["--apply"]) == 0                         # the re-run writes it
    assert len(read_model(ov, Overrides).overrules) == 2
    second = root / "campaign" / "backfill" / "20991231T000000Z"
    after = [json.loads(l) for l in (second / "snapshot" / "after.jsonl").read_text().splitlines()]
    assert [a["slug"] for a in after] == ["g1"]
    assert [json.loads(l)["slug"] for l in (second / "record.jsonl").read_text().splitlines()] == ["g1"]
