"""`adjudicator/report.py`: the propose-only commands, a stored proposal as lines, and the
run report."""
from __future__ import annotations

from llama.adjudicator import runner
from llama.adjudicator.record import AdjudicationRecord
from llama.adjudicator.report import proposal_commands, render_proposal, render_report
from llama.adjudicator.runner import ShowOutcome
from llama.adjudicator.verdict import Verdict
from llama.models import Show

SHOW = Show(performance_id="GratefulDead/1973-06-10", identifier="gd73",
            artist="Grateful Dead", date="1973-06-10")
SLUG = "gratefuldead-1973-06-10"
EV = {"kind": "taper-description", "quote": "b.mp3 is a tuning fragment"}
FLAG = "unresolved track titles"


def verdict(edits=(), flags=(), **kw):
    return Verdict.model_validate({"flags": list(flags), "edits": list(edits), "kind": "fix",
                                   "show_correct_after": "yes", "rationale": "r", **kw})


def record(v: dict, **kw) -> AdjudicationRecord:
    return AdjudicationRecord(at="2026-11-07T00:00:00+00:00", model="opus", outcome="proposal",
                              verdict=v, **kw)


def test_proposal_commands_per_op():
    v = verdict([{"op": op, "confidence": "high", "why": "w", "evidence": [], **kw}
                 for op, kw in (("set_date", {"value": "1973-06-11"}), ("untitled", {}),
                                ("narration", {"value": "short"}), ("rm", {}),
                                ("redo_research", {}))]
                + [{"op": "exclude", "confidence": "high", "why": "w", "evidence": [EV],
                    "file": "b.mp3"}])
    assert proposal_commands("s1", v) == [
        "llama fix s1 --set-date 1973-06-11", "llama fix s1 --untitled",
        "llama fix s1 --narration short", "llama rm s1", "llama redo s1 --from research"]


def test_render_proposal_layout():
    v = verdict(
        [{"op": "exclude", "confidence": "high", "why": "w", "evidence": [EV], "file": "b.mp3"},
         {"op": "rm", "confidence": "high", "why": "w"}],
        [{"flag": FLAG, "verdict": "real-fixed-by-action", "confidence": "high", "why": "jw"}],
        kind="hold", show_correct_after="unsure", decide="keep or drop?", partial_tape=True)
    rec = record(v.model_dump(mode="json"), partial_tape=True, gate=[
        {"index": 0, "op": "exclude", "bar": "short", "passed": False, "reason": "too long"},
        {"index": 1, "op": "rm", "bar": "propose-only", "passed": True, "reason": ""}])
    lines = render_proposal(rec, SHOW, slug=SLUG)
    assert lines[0] == "proposal (opus, 2026-11-07T00:00:00+00:00): hold; correct after: unsure"
    assert f"  flag: {FLAG} -> real-fixed-by-action (high): jw" in lines
    assert "  edit 0: exclude b.mp3 [short: too long]" in lines
    assert '    taper-description: "b.mp3 is a tuning fragment"' in lines
    assert "  edit 1: rm [propose-only: passed]" in lines
    assert lines[-3:] == ["  decide: keep or drop?", "  partial tape", f"  run: llama rm {SLUG}"]


def test_render_proposal_renders_held_proposal():
    rec = AdjudicationRecord(
        at="T", model="opus", outcome="applied", verdict=verdict().model_dump(mode="json"),
        held_proposal={"flags": [{"flag": "v", "judgement": {"verdict": "spurious",
                                                             "confidence": "low", "why": "jw"}},
                                 {"flag": "w", "judgement": None}],
                       "edits": [{"op": "overrule", "flag": "v", "confidence": "low",
                                  "why": "jw", "evidence": [EV]}]})
    assert render_proposal(rec, SHOW, slug=SLUG) == [
        "applied (opus, T), still held:", "  flag: v -> spurious (low): jw",
        "  flag: w -> not judged", "  edit 0: overrule v",
        '    taper-description: "b.mp3 is a tuning fragment"']


def out(slug, outcome, **kw):
    return ShowOutcome(slug, outcome, **kw)


def test_report_sections_and_omits_empty():
    lines = render_report([out("a", runner.CURRENT), out("b", runner.APPLIED)],
                          voiced=lambda s: False)
    assert lines == ["summary: 2 shows: applied 1, skipped: current 1"]


def test_report_summary_follows_constant_order():
    lines = render_report([out("a", runner.FAILED), out("b", runner.PROPOSAL),
                           out("c", runner.APPLIED), out("d", runner.STALE, detail="x")],
                          voiced=lambda s: False)
    assert lines[0] == ("summary: 4 shows: applied 1, held with proposal 1, "
                        "stale: reprocess first 1, failed 1")
    assert "stale: reprocess first:" in lines and "  d: x" in lines


def test_report_lists_track_changes_from_diff_with_durations():
    lines = render_report([out("s1", runner.APPLIED,
                               changes=["- gd73-06-10d2t01.mp3 (3:10) Jam"])],
                          voiced=lambda s: False)
    assert lines[1:] == ["auto-applied track-list changes:", "  s1:",
                         "    - gd73-06-10d2t01.mp3 (3:10) Jam"]


def test_report_accepted_changes_get_their_own_section():
    lines = render_report(
        [out("s1", runner.APPLIED, changes=["- a.mp3 (1:00) A"]),
         out("s2", runner.ACCEPTED, changes=["- b.mp3 (0:30) B"])], voiced=lambda s: False)
    i, j = lines.index("auto-applied track-list changes:"), lines.index(
        "accepted track-list changes:")
    assert lines[i:j] == ["auto-applied track-list changes:", "  s1:", "    - a.mp3 (1:00) A"]
    assert lines[j:] == ["accepted track-list changes:", "  s2:", "    - b.mp3 (0:30) B"]
    only = render_report([out("s2", runner.ACCEPTED, changes=["x"])], voiced=lambda s: False)
    assert "auto-applied track-list changes:" not in only


def test_render_proposal_names_the_callers_slug():
    v = verdict([{"op": "rm", "confidence": "high", "why": "w"}])
    lines = render_proposal(record(v.model_dump(mode="json")), SHOW, slug="custom-slug")
    assert lines[-1] == "  run: llama rm custom-slug"


def test_report_names_redeliver_command_for_voiced():
    lines = render_report([out("s1", runner.APPLIED, delivered_changed=True),
                           out("s2", runner.APPLIED, delivered_changed=True)],
                          voiced=lambda s: s == "s1")
    assert "delivered shows changed (re-deliver):" in lines
    assert "  llama deliver s1 --replace-voiced" in lines and "  llama deliver s2" in lines


def test_report_lists_fixed_eligible_shows_apart_from_redeliver():
    lines = render_report([out("s1", runner.APPLIED, delivered_changed=True, fixed_eligible=True),
                           out("s2", runner.APPLIED, delivered_changed=True)],
                          voiced=lambda s: False)
    assert lines[lines.index("eligible for llama deliver --fixed:") + 1] == "  s1"
    assert "  llama deliver s1" not in lines and "  llama deliver s2" in lines


def test_report_held_with_proposal_reasons():
    gated = record({}, gate=[{"index": 0, "op": "e", "bar": "short", "passed": True, "reason": ""},
                             {"index": 1, "op": "e", "bar": "long", "passed": False,
                              "reason": "no quote"}], vetoes=["v1"])
    vetoed = record({}, vetoes=["a veto"])
    diffed = record({}, result={"diff": ["track x changed"]})
    errored = record({}, result={"error": "boom"})
    still = AdjudicationRecord(outcome="applied", held_proposal={
        "flags": [{"flag": "venue mismatch", "judgement": None}], "edits": []})
    lines = render_report(
        [out("g", runner.PROPOSAL, record=gated), out("v", runner.PROPOSAL, record=vetoed),
         out("d", runner.PROPOSAL, record=diffed), out("e", runner.PROPOSAL, record=errored),
         out("h", runner.APPLIED_HELD, record=still)], voiced=lambda s: False)
    i = lines.index("held with proposal:")
    assert lines[i + 1:i + 6] == ["  g: no quote", "  v: a veto", "  d: track x changed",
                                  "  e: boom", "  h: applied, still held: venue mismatch"]


def test_report_lists_applied_still_held_under_held_with_proposal():
    still = AdjudicationRecord(outcome="applied", held_proposal={
        "flags": [{"flag": "f1", "judgement": None}], "edits": []})
    lines = render_report([out("h", runner.APPLIED_HELD, record=still)],
                          voiced=lambda s: False)
    assert lines == ["summary: 1 shows: applied, still held 1", "held with proposal:",
                     "  h: applied, still held: f1"]
