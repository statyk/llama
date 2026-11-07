"""Applying a verdict in one unit (spec "Apply and re-check", the coverage bullet under
"Recording pin"). The pure checks are tested on Shows built directly; `apply_verdict` runs
against a real packaged library show (`helpers.reuse_gd73`) with the real
`cli._redo_show_locked` and stub stages, whose gather writes the post `show.json` each
test wants. This is the strict surface: each check has a pass/fail pair the Task 6
mutation pass relies on."""
from __future__ import annotations

import pytest

import llama.cli as cli
import llama.pipeline as pipeline
from herder import HerderError, TaskFailed
from herder.limits import RateLimited
from llama.adjudicator.apply import (ApplyResult, TrackRow, apply_verdict, capture_before,
                                     coverage_failures, earliest_stage, rehold_flags,
                                     silenced_flags, track_changes, whole_show_diff,
                                     write_edits)
from llama.adjudicator.gate import EditGate, GateResult
from llama.adjudicator.verdict import Verdict
from llama.audio_reuse import StationUnpaired
from llama.config import load_config
from llama.errors import LlamaError
from llama.ia_client import IAError
from llama.ledger import Ledger
from llama.models import Briefing, Overrides, Show, Track
from llama.show_unit import ShowChanged, capture_view
from llama.station_mark import StationUnreadable
from llama.workspace import ShowWorkspace, read_model, read_overrides, write_artifact

from helpers import reuse_gd73, tree_bytes

AT = "2026-11-07T00:00:00+00:00"
PID = "GratefulDead/1973-06-10"
DESC = "taper-description"
VENUE_FLAG = "venue mismatch: archive 'RFK' vs jerrybase 'RFK Stadium'"
VENUE_FLAG_2 = "venue mismatch: archive 'RFK' vs jerrybase 'Kezar'"
SETS_FLAG = "research asserts 3 sets but structure has 2"
ALIGN_FLAG = "low-confidence structure alignment (coverage 0.50)"
CLOSER_FLAG = "jerrybase set closer 'Morning Dew' is not at a set break"
DATE_FLAG = "research asserts wrong date: 1974-01-01"
BRIEF_FLAG = "briefing mentions unknown song: Dark Star"


# ---------------------------------------------------------------- builders

def T(fn, title=None, src="tags", s="1", dur=200.0, segue=False, short=False):
    return Track(index=0, set=s, title=title if title is not None else fn.split(".")[0].upper(),
                 filename=fn, duration_sec=dur, title_source=src, segue=segue, short_kept=short)


def mk(tracks, flags=(), excluded=(), ident="gd73", held=None):
    tracks = [t.model_copy(update={"index": i}) for i, t in enumerate(tracks, 1)]
    return Show(performance_id=PID, identifier=ident, artist="Grateful Dead", date="1973-06-10",
                venue="RFK Stadium", tracks=tracks, excluded_files=list(excluded),
                review_flags=list(flags), needs_review=bool(flags) if held is None else held)


def ev(kind=DESC, quote="taper notes"):
    return {"kind": kind, "quote": quote}


def ed(op, conf="high", **kw):
    return {"op": op, "confidence": conf, "why": "w", "evidence": [ev()], **kw}


def judge(flag, verdict="spurious", conf="high"):
    return {"flag": flag, "verdict": verdict, "confidence": conf, "why": "w"}


def V(edits, flags=()):
    return Verdict.model_validate({"flags": list(flags), "edits": edits, "kind": "fix",
                                   "show_correct_after": "yes", "rationale": "r"})


def edits(*raw):
    return V(list(raw)).edits


def passing(v: Verdict) -> GateResult:
    return GateResult(edits=[EditGate(index=i, op=e.op, bar="medium", passed=True, reason="")
                             for i, e in enumerate(v.edits)], vetoes=[], auto=True)


def exclude(f, **kw):
    return ed("exclude", file=f, **kw)


def include(f, **kw):
    return ed("include", file=f, **kw)


def set_title(f, title, **kw):
    return ed("set_title", file=f, title=title, **kw)


def structure(breaks, encore=None, **kw):
    return ed("structure", breaks_after=breaks, encore_after=encore, **kw)


def overrule(flag, **kw):
    return ed("overrule", flag=flag, **kw)


def switch(ident, **kw):
    return ed("switch_recording", identifier=ident, **kw)


def ws_with(tmp_path, show: Show, ov: Overrides | None = None) -> ShowWorkspace:
    ws = ShowWorkspace(tmp_path / "shows" / "s")
    write_artifact(ws.show, show)
    if ov is not None:
        write_artifact(ws.overrides, ov)
    return ws


ABC = [T("a.mp3", "A"), T("b.mp3", "B"), T("c.mp3", "C")]


# ---------------------------------------------------------------- write_edits

def test_write_edits_is_filename_keyed_and_records_adjudicate_overrules(tmp_path):
    show = mk(ABC, flags=[VENUE_FLAG])
    ws = ws_with(tmp_path, show)
    ov = write_edits(ws, edits(exclude("b.mp3"), set_title("c.mp3", "Jam"), structure(["c.mp3"]),
                               overrule(VENUE_FLAG)), show=show, at=AT,
                     defer_subjectless_structure=False)
    assert ov.exclude == ["b.mp3"] and ov.titles == {"c.mp3": "Jam"} and ov.set_breaks == ["c.mp3"]
    assert ov.encore_after is None
    assert [(r.kind, r.source, r.at) for r in ov.overrules] == [("venue", "adjudicate", AT)]
    assert read_overrides(ws) == ov                      # written, not only returned


def test_write_edits_structure_in_play_order_and_empty_is_kept(tmp_path):
    show = mk(ABC + [T("d.mp3")])
    ws = ws_with(tmp_path, show)
    ov = write_edits(ws, edits(structure(["c.mp3", "a.mp3"], "d.mp3")), show=show, at=AT,
                     defer_subjectless_structure=False)
    assert ov.set_breaks == ["a.mp3", "c.mp3"] and ov.encore_after == "d.mp3"
    ov = write_edits(ws, edits(structure([])), show=show, at=AT,
                     defer_subjectless_structure=False)
    assert ov.set_breaks == [] and read_overrides(ws).set_breaks == []   # forced no breaks


def test_write_edits_metadata_and_propose_only_ignored(tmp_path):
    show = mk(ABC)
    ws = ws_with(tmp_path, show, Overrides(narration="full"))
    ov = write_edits(ws, edits(ed("venue", venue="Kezar"), ed("city", city="SF"),
                               switch("gd73-other"),
                               {"op": "narration", "value": "vague", "confidence": "high",
                                "why": "w"},
                               {"op": "set_date", "value": "1974-01-01", "confidence": "high",
                                "why": "w"}),
                     show=show, at=AT, defer_subjectless_structure=False)
    assert (ov.venue, ov.city, ov.recording) == ("Kezar", "SF", "gd73-other")
    assert ov.narration == "full" and ov.date is None


def test_write_edits_include_of_operator_excluded_row_unexcludes(tmp_path):
    show = mk(ABC, excluded=[{"filename": "x.mp3", "reasons": ["operator-excluded"]},
                             {"filename": "y.mp3", "reasons": ["implausibly short"]}])
    ws = ws_with(tmp_path, show, Overrides(exclude=["x.mp3"], include=["b.mp3"]))
    ov = write_edits(ws, edits(include("x.mp3"), include("y.mp3"), exclude("b.mp3")),
                     show=show, at=AT, defer_subjectless_structure=False)
    assert ov.exclude == ["b.mp3"]            # x un-excluded, b excluded
    assert ov.include == ["y.mp3"]            # y re-admitted, b no longer included


def test_write_edits_defers_subjectless_structure_overrules_with_track_list_edit(tmp_path):
    show = mk(ABC, flags=[VENUE_FLAG, SETS_FLAG, CLOSER_FLAG])
    ws = ws_with(tmp_path, show)
    e = edits(exclude("b.mp3"), overrule(VENUE_FLAG), overrule(SETS_FLAG), overrule(CLOSER_FLAG))
    ov = write_edits(ws, e, show=show, at=AT, defer_subjectless_structure=True)
    # research-sets is subject-less: deferred; jerrybase-closer has a subject: written
    assert [r.kind for r in ov.overrules] == ["venue", "jerrybase-closer"]
    ov = write_edits(ws_with(tmp_path / "2", show), e, show=show, at=AT,
                     defer_subjectless_structure=False)
    assert [r.kind for r in ov.overrules] == ["venue", "research-sets", "jerrybase-closer"]


def test_write_edits_merges_overrules_without_duplicates(tmp_path):
    show = mk(ABC, flags=[VENUE_FLAG])
    ws = ws_with(tmp_path, show)
    write_edits(ws, edits(overrule(VENUE_FLAG)), show=show, at=AT,
                defer_subjectless_structure=False)
    ov = write_edits(ws, edits(overrule(VENUE_FLAG)), show=show, at="later",
                     defer_subjectless_structure=False)
    assert [(r.kind, r.at) for r in ov.overrules] == [("venue", AT)]


# ---------------------------------------------------------------- earliest_stage

def test_earliest_stage_mapping():
    assert earliest_stage(edits(overrule(BRIEF_FLAG))) == "brief"
    assert earliest_stage(edits(overrule(DATE_FLAG))) == "vet"
    assert earliest_stage(edits(overrule(DATE_FLAG), overrule(BRIEF_FLAG))) == "vet"
    assert earliest_stage(edits(overrule(VENUE_FLAG), overrule(DATE_FLAG))) == "gather"
    for e in (exclude("a.mp3"), include("a.mp3"), set_title("a.mp3", "X"), structure([]),
              ed("venue", venue="V"), ed("city", city="C")):
        assert earliest_stage(edits(e, overrule(BRIEF_FLAG))) == "gather", e["op"]
    assert earliest_stage(edits(overrule(BRIEF_FLAG), switch("x"), exclude("a.mp3"))) == "select"
    # propose-only ops need no stage
    assert earliest_stage(edits({"op": "rm", "confidence": "high", "why": "w"},
                                overrule(BRIEF_FLAG))) == "brief"


# ---------------------------------------------------------------- whole_show_diff

def test_whole_show_diff_accepts_exact_prediction():
    pre = mk([T("a.mp3", "A"), T("b.mp3", "B", src="unresolved"), T("c.mp3", "C", s="2")])
    post = mk([T("a.mp3", "A"), T("x.mp3", "X", src="unresolved"),
               T("c.mp3", "Jam", src="override", s="2")])
    assert whole_show_diff(capture_before(pre), post,
                           edits(exclude("b.mp3"), include("x.mp3"),
                                 set_title("c.mp3", "Jam"))) == []


def test_whole_show_diff_catches_unnamed_title_shift():
    # an include shifts desc-position titles one over: an unnamed title changes
    pre = mk([T("a.mp3", "A", src="desc-position"), T("b.mp3", "B", src="desc-position")])
    post = mk([T("x.mp3", "A", src="desc-position"), T("a.mp3", "B", src="desc-position"),
               T("b.mp3", "C", src="desc-position")])
    d = whole_show_diff(capture_before(pre), post, edits(include("x.mp3")))
    assert "a.mp3: title 'A' -> 'B' (not predicted)" in d
    assert "b.mp3: title 'B' -> 'C' (not predicted)" in d


def test_whole_show_diff_catches_title_source_change():
    pre = mk([T("a.mp3", "A", src="tags"), T("b.mp3", "B")])
    post = mk([T("a.mp3", "A", src="sibling-align")])
    d = whole_show_diff(capture_before(pre), post, edits(exclude("b.mp3")))
    assert d == ["a.mp3: title_source 'tags' -> 'sibling-align' (not predicted)"]


def test_whole_show_diff_catches_reorder_and_set_change_and_extra_drop():
    pre = mk([T("a.mp3"), T("b.mp3"), T("c.mp3"), T("d.mp3")])
    # reorder of unnamed tracks
    d = whole_show_diff(capture_before(pre), mk([T("b.mp3"), T("a.mp3"), T("c.mp3"),
                                                 T("d.mp3")]), [])
    assert any("order" in line for line in d), d
    # an unnamed set change
    d = whole_show_diff(capture_before(pre), mk([T("a.mp3"), T("b.mp3"), T("c.mp3", s="2"),
                                                 T("d.mp3")]), [])
    assert d == ["c.mp3: set '1' -> '2' (not predicted)"]
    # an extra drop beside the predicted exclude
    d = whole_show_diff(capture_before(pre), mk([T("a.mp3"), T("c.mp3")]),
                        edits(exclude("b.mp3")))
    assert d == ["d.mp3: dropped (not predicted)"]
    # an extra addition
    d = whole_show_diff(capture_before(pre), mk([T("a.mp3"), T("b.mp3"), T("c.mp3"),
                                                 T("d.mp3"), T("z.mp3")]), [])
    assert d == ["z.mp3: added (not predicted)"]
    # an exclude that did not land
    d = whole_show_diff(capture_before(pre), mk([T("a.mp3"), T("b.mp3"), T("c.mp3"),
                                                 T("d.mp3")]), edits(exclude("b.mp3")))
    assert d == ["b.mp3: exclude did not land (not predicted)"]


def test_whole_show_diff_catches_include_that_did_not_land():
    pre = mk([T("a.mp3"), T("b.mp3")])
    d = whole_show_diff(capture_before(pre), mk([T("a.mp3"), T("b.mp3")]), edits(include("x.mp3")))
    assert d == ["x.mp3: dropped (not predicted)"]


def test_whole_show_diff_catches_reordered_set_title_target():
    pre = mk([T("a.mp3"), T("b.mp3", src="unresolved"), T("c.mp3")])
    post = mk([T("b.mp3", "Jam", src="override"), T("a.mp3"), T("c.mp3")])
    d = whole_show_diff(capture_before(pre), post, edits(set_title("b.mp3", "Jam")))
    assert d == ["order of kept tracks changed: ['a.mp3', 'b.mp3', 'c.mp3'] -> "
                 "['b.mp3', 'a.mp3', 'c.mp3'] (not predicted)"]


def test_whole_show_diff_catches_unnamed_segue_change_without_structure():
    pre = mk([T("a.mp3", segue=True), T("b.mp3")])
    d = whole_show_diff(capture_before(pre), mk([T("a.mp3"), T("b.mp3")]), [])
    assert d == ["a.mp3: segue True -> False (not predicted)"]


def test_whole_show_diff_predicts_structure_labels_and_ignores_segue_loss():
    pre = mk([T("a.mp3", segue=True), T("b.mp3"), T("c.mp3"), T("d.mp3"), T("e.mp3")])
    e = edits(structure(["b.mp3"], "d.mp3"))
    post = mk([T("a.mp3"), T("b.mp3"), T("c.mp3", s="2"), T("d.mp3", s="2"),
               T("e.mp3", s="encore")])
    assert whole_show_diff(capture_before(pre), post, e) == []
    # labels one off from the prediction are caught
    off = mk([T("a.mp3"), T("b.mp3", s="2"), T("c.mp3", s="2"), T("d.mp3", s="2"),
              T("e.mp3", s="encore")])
    assert whole_show_diff(capture_before(pre), off, e) == [
        "b.mp3: set '1' -> '2' (predicted '1')"]
    # positions are counted in the AFTER list: an include before the break shifts them
    e2 = edits(include("x.mp3"), structure(["b.mp3"]))
    post2 = mk([T("x.mp3", s="9"), T("a.mp3"), T("b.mp3"), T("c.mp3", s="2"),
                T("d.mp3", s="2"), T("e.mp3", s="2")])
    assert whole_show_diff(capture_before(pre), post2, e2) == []


def test_whole_show_diff_does_not_predict_included_track_title():
    pre = mk([T("a.mp3"), T("b.mp3")])
    post = mk([T("a.mp3"), T("x.mp3", "whatever", src="unresolved", s="7"), T("b.mp3")])
    assert whole_show_diff(capture_before(pre), post, edits(include("x.mp3"))) == []


def test_whole_show_diff_checks_set_title_target():
    pre = mk([T("a.mp3", "A", src="unresolved")])
    e = edits(set_title("a.mp3", "Jam"))
    assert whole_show_diff(capture_before(pre), mk([T("a.mp3", "Jam", src="override")]), e) == []
    d = whole_show_diff(capture_before(pre), mk([T("a.mp3", "Jim", src="override")]), e)
    assert d == ["a.mp3: title 'Jim' (predicted 'Jam')"]
    d = whole_show_diff(capture_before(pre), mk([T("a.mp3", "Jam", src="tags")]), e)
    assert d == ["a.mp3: title_source 'tags' (predicted 'override')"]


def test_track_changes_lines():
    pre = mk([T("a.mp3", "A", dur=65.0), T("b.mp3", "B", dur=None), T("c.mp3", "C")])
    post = mk([T("a.mp3", "Alpha", dur=65.0), T("c.mp3", "C", s="2"),
               T("x.mp3", "X", dur=125.4)])
    assert track_changes(capture_before(pre), post) == [
        "~ a.mp3: 'A' -> 'Alpha'", "~ c.mp3: set 1 -> 2", "+ x.mp3 (2:05) X",
        "- b.mp3 (?) B"]


def test_capture_before_rows():
    pre = mk([T("a.mp3", "A", src="desc-position", s="2", dur=None, segue=True)])
    assert capture_before(pre) == [TrackRow("a.mp3", "A", "desc-position", "2", True, None)]


# ---------------------------------------------------------------- silenced_flags

def test_silenced_flags_auto_needs_a_passing_judgement():
    pre = mk(ABC, flags=[VENUE_FLAG, DATE_FLAG])
    post = mk(ABC)
    v = V([exclude("b.mp3")], [judge(VENUE_FLAG, conf="low"), judge(DATE_FLAG)])
    # venue (medium bar) at low fails; research-date (title bar) has no passed overrule edit
    assert silenced_flags(pre, post, v, passing(v), mode="auto") == [VENUE_FLAG, DATE_FLAG]
    v = V([exclude("b.mp3"), overrule(DATE_FLAG)],
          [judge(VENUE_FLAG, conf="medium"), judge(DATE_FLAG)])
    assert silenced_flags(pre, post, v, passing(v), mode="auto") == []
    # a flag still present (same key) is not silenced, whatever its judgement
    v = V([exclude("b.mp3")], [judge(VENUE_FLAG, "undecidable")])
    assert silenced_flags(pre, mk(ABC, flags=[VENUE_FLAG, DATE_FLAG]), v, passing(v),
                          mode="auto") == []
    # same kind, other subject: the old key is gone
    assert silenced_flags(pre.model_copy(update={"review_flags": [VENUE_FLAG]}),
                          mk(ABC, flags=[VENUE_FLAG_2]), v, passing(v), mode="auto") == [VENUE_FLAG]


def test_silenced_flag_in_accept_mode_counts_any_confidence_spurious_or_fixed(tmp_path):
    pre = mk(ABC, flags=[VENUE_FLAG, DATE_FLAG, BRIEF_FLAG])
    post = mk(ABC)
    v = V([exclude("b.mp3")], [judge(VENUE_FLAG, conf="low"),
                               judge(DATE_FLAG, "real-fixed-by-action", "low"),
                               judge(BRIEF_FLAG, "undecidable")])
    assert silenced_flags(pre, post, v, None, mode="accept") == [BRIEF_FLAG]


def test_silenced_flags_keyless_flag_compared_by_text():
    dm = "duration mismatch on 3 tracks"
    v = V([exclude("b.mp3")], [])
    assert silenced_flags(mk(ABC, flags=[dm]), mk(ABC), v, passing(v), mode="auto") == [dm]
    assert silenced_flags(mk(ABC, flags=[dm]), mk(ABC, flags=[dm]), v, passing(v),
                          mode="auto") == []


# ---------------------------------------------------------------- coverage

def _cov_pair(rule):
    pre = mk([T("a.mp3", "Bertha", dur=300.0), T("b.mp3", "Jam", src="unresolved", dur=20.0)])
    good = mk([T("a1.mp3", "bertha", dur=300.0), T("b1.mp3", "Jam", src="unresolved", dur=20.0),
               T("c1.mp3", "Dark Star", dur=600.0)], ident="sib")
    if rule == "missing_title":
        bad = mk([T("b1.mp3", "Jam", src="unresolved", dur=20.0),
                  T("c1.mp3", "Dark Star", dur=900.0), T("d1.mp3", "Other", dur=10.0)], ident="sib")
    elif rule == "total_duration":
        bad = mk([T("a1.mp3", "Bertha", dur=290.0), T("b1.mp3", "Jam", src="unresolved", dur=20.0),
                  T("c1.mp3", "Dark Star", dur=5.0)], ident="sib")
    elif rule == "added_duration":
        bad = mk([T("a1.mp3", "Bertha", dur=300.0), T("b1.mp3", "Jam", src="unresolved", dur=20.0),
                  T("c1.mp3", "Space", src="unresolved", dur=61.0)], ident="sib")
    elif rule == "gain":
        bad = mk([T("a1.mp3", "Bertha", dur=320.0), T("b1.mp3", "Jam", src="unresolved", dur=20.0)],
                 ident="sib")
    else:
        bad = good.model_copy(update={"needs_review": True, "review_flags": [VENUE_FLAG]})
    return pre, good, bad


@pytest.mark.parametrize("rule", ["missing_title", "total_duration", "added_duration", "gain",
                                  "held"])
def test_coverage_failures_each_rule(rule):
    pre, good, bad = _cov_pair(rule)
    assert coverage_failures(pre, good, mode="auto") == []
    fails = coverage_failures(pre, bad, mode="auto")
    assert len(fails) == 1 and fails[0].startswith(rule.replace("_", " ")), fails


def test_coverage_added_duration_boundary():
    pre = mk([T("a.mp3", "Bertha", dur=300.0)])

    def post(d):
        return mk([T("a1.mp3", "Bertha", dur=300.0), T("s1.mp3", "S", short=True, dur=d)],
                  ident="sib")
    assert coverage_failures(pre, post(60.0), mode="auto") == []
    assert [f.split(":")[0] for f in coverage_failures(pre, post(60.01), mode="auto")] == [
        "added duration"]
    # measured against the pre show's own unresolved/short-kept time
    pre2 = mk([T("a.mp3", "Bertha", dur=300.0), T("u.mp3", "U", src="unresolved", dur=30.0)])
    p2 = mk([T("a1.mp3", "Bertha", dur=300.0), T("u1.mp3", "U", src="unresolved", dur=90.0),
             T("x1.mp3", "Dark Star", dur=10.0)], ident="sib")
    assert coverage_failures(pre2, p2, mode="auto") == []


def test_coverage_post_title_must_be_a_resolved_song():
    # a resolved pre title does not "appear" through an unresolved post track of that text
    pre = mk([T("a.mp3", "Bertha", dur=300.0)])
    rest = [T("b1.mp3", "Dark Star", dur=300.0)]
    post = mk([T("a1.mp3", "Bertha", src="unresolved", dur=30.0)] + rest, ident="sib")
    assert [f.split(":")[0] for f in coverage_failures(pre, post, mode="auto")] == [
        "missing title"]
    # control: the same title on a resolved post track passes
    post = mk([T("a1.mp3", "Bertha", dur=30.0)] + rest, ident="sib")
    assert coverage_failures(pre, post, mode="auto") == []


def test_coverage_unknown_duration_fails_closed():
    pre = mk([T("a.mp3", "Bertha", dur=300.0)])
    post = mk([T("a1.mp3", "Bertha", dur=300.0), T("b1.mp3", "B", dur=None)], ident="sib")
    assert [f.split(":")[0] for f in coverage_failures(pre, post, mode="auto")] == [
        "total duration"]


def test_coverage_accept_mode_skips_gain_and_held():
    for rule in ("gain", "held"):
        pre, _, bad = _cov_pair(rule)
        assert coverage_failures(pre, bad, mode="accept") == []
    pre, _, bad = _cov_pair("missing_title")
    assert coverage_failures(pre, bad, mode="accept") != []


# ---------------------------------------------------------------- rehold_flags

def test_rehold_flags_pure_all_or_nothing():
    pre = mk(ABC, flags=[VENUE_FLAG, BRIEF_FLAG])
    v = V([set_title("c.mp3", "Jam")], [judge(VENUE_FLAG, conf="medium"), judge(BRIEF_FLAG)])
    g = passing(v)
    assert rehold_flags(pre, mk(ABC, flags=[VENUE_FLAG]), v, g) == [VENUE_FLAG]
    assert rehold_flags(pre, mk(ABC, flags=[VENUE_FLAG, BRIEF_FLAG]), v, g) == [VENUE_FLAG,
                                                                                BRIEF_FLAG]
    # one flag that does not qualify sinks the lot
    assert rehold_flags(pre, mk(ABC, flags=[VENUE_FLAG, VENUE_FLAG_2]), v, g) is None
    # a judgement below its bar does not qualify
    v_low = V([set_title("c.mp3", "Jam")], [judge(VENUE_FLAG, conf="low"), judge(BRIEF_FLAG)])
    assert rehold_flags(pre, mk(ABC, flags=[VENUE_FLAG]), v_low, passing(v_low)) is None
    # nor does a real-fixed-by-action one
    v_fx = V([set_title("c.mp3", "Jam")], [judge(VENUE_FLAG, "real-fixed-by-action"),
                                           judge(BRIEF_FLAG)])
    assert rehold_flags(pre, mk(ABC, flags=[VENUE_FLAG]), v_fx, passing(v_fx)) is None
    # a held show with no flags is not re-held
    assert rehold_flags(pre, mk(ABC, held=True), v, g) is None


def test_rehold_never_alignment_or_subjectless_structure_after_track_edit():
    pre = mk(ABC, flags=[ALIGN_FLAG, SETS_FLAG])
    j = [judge(ALIGN_FLAG), judge(SETS_FLAG)]
    v = V([set_title("c.mp3", "Jam"), overrule(SETS_FLAG)], j)
    # positive control: research-sets qualifies with no track-list or structure edit
    assert rehold_flags(pre, mk(ABC, flags=[SETS_FLAG]), v, passing(v)) == [SETS_FLAG]
    for extra in (exclude("b.mp3"), structure(["a.mp3"])):
        v2 = V([set_title("c.mp3", "Jam"), overrule(SETS_FLAG), extra], j)
        assert rehold_flags(pre, mk(ABC, flags=[SETS_FLAG]), v2, passing(v2)) is None
    va = V([set_title("c.mp3", "Jam"), overrule(ALIGN_FLAG)], j)
    assert rehold_flags(pre, mk(ABC, flags=[ALIGN_FLAG]), va, passing(va)) is None
    dm = "duration mismatch on 1 track"
    vd = V([set_title("c.mp3", "Jam")], [judge(dm)])
    assert rehold_flags(mk(ABC, flags=[dm]), mk(ABC, flags=[dm]), vd, passing(vd)) is None


# ---------------------------------------------------------------- apply_verdict harness

OLD = (("A", "a.mp3", 300.0), ("B", "b.mp3", 30.0), ("C", "c.mp3", 400.0))


class Lib:
    def __init__(self, tmp_path, monkeypatch):
        self.cfg, self.ws, self.ia = reuse_gd73(tmp_path, monkeypatch, OLD)
        self.mp = monkeypatch
        self.root = tmp_path
        self.stages: list[str] = []
        self.commits: list = []

    def pre(self, flags=(), tracks=None) -> Show:
        tracks = tracks or [T("a.mp3", "A", dur=300.0), T("b.mp3", "B", src="unresolved",
                                                           dur=30.0), T("c.mp3", "C", dur=400.0)]
        show = mk(tracks, flags=flags)
        write_artifact(self.ws.show, show)
        return show

    def redo(self, post: Show, *, select: str | None = None, post_fn=None):
        """The real `_redo_show_locked`, with gather writing `post` when show.json was
        dropped (else the existing show stands, as `should_run`), and with select stubbed
        to `select` when given."""
        ws = self.ws
        self.ia.lengths.update({t.filename: t.duration_sec for t in post.tracks})

        def gather(show_ws, *a, **k):
            if show_ws.show.exists():
                return read_model(show_ws.show, Show)
            write_artifact(show_ws.show, post)
            return post

        def brief(show_ws, *a, **k):
            write_artifact(show_ws.briefing_json, Briefing(context="c", significance="s"))
            write_artifact(show_ws.briefing_md, "# Briefing\n")
        self.mp.setattr(pipeline, "run_gather", gather)
        self.mp.setattr(pipeline, "run_research", lambda *a, **k: "research")
        self.mp.setattr(pipeline, "run_vet_research", lambda *a, **k: None)
        self.mp.setattr(pipeline, "run_brief", brief)
        if select is not None:
            def sel(show_ws, *a, **k):
                write_artifact(show_ws.selection, {"identifier": select, "scores": {}})
                return select
            self.mp.setattr(pipeline, "run_select_recording", sel)
        config = load_config(self.cfg)
        ledger = Ledger(self.root / "ledger.jsonl")

        def redo(stage):
            self.stages.append(stage)
            entry = cli._resolve_show(config, ledger, ws.dir.name)
            return cli._redo_show_locked(config, self.ia, ledger, entry, stage)
        return redo

    def apply(self, verdict, redo, *, mode="auto", gate="pass", trial=False, on_commit=None,
              expect=None):
        if gate == "pass":
            gate = passing(verdict) if mode == "auto" else None
        return apply_verdict(self.ws, verdict, expect=expect or capture_view(self.ws), redo=redo,
                             mode=mode, gate=gate, trial=trial,
                             on_commit=on_commit or (lambda post, res: self.commits.append(res)),
                             at=AT)


@pytest.fixture
def lib(tmp_path, monkeypatch):
    return Lib(tmp_path, monkeypatch)


def _post_excluding_b(flags=()):
    return mk([T("a.mp3", "A", dur=300.0), T("c.mp3", "C", dur=400.0)], flags=flags)


def test_apply_exclude_commits_and_reports_changes(lib):
    lib.pre(flags=["unresolved track titles"])
    v = V([exclude("b.mp3")], [judge("unresolved track titles", "real-fixed-by-action")])
    r = lib.apply(v, lib.redo(_post_excluding_b()))
    assert r == ApplyResult("applied", False, [], ["- b.mp3 (0:30) B"], None, [])
    assert lib.stages == ["gather"] and lib.commits == [r]
    assert read_overrides(lib.ws).exclude == ["b.mp3"]
    assert (lib.ws.package_dir / "manifest.json").exists()
    assert not (lib.ws.dir / ".txn").exists()


def test_apply_unpredicted_change_restores(lib):
    lib.pre(flags=["unresolved track titles"])
    before = tree_bytes(lib.ws.dir)
    v = V([exclude("b.mp3")], [judge("unresolved track titles", "real-fixed-by-action")])
    post = mk([T("a.mp3", "Alpha", dur=300.0), T("c.mp3", "C", dur=400.0)])
    r = lib.apply(v, lib.redo(post))
    assert r.status == "restored" and r.diff == ["a.mp3: title 'A' -> 'Alpha' (not predicted)"]
    assert r.held is True and lib.commits == []
    assert tree_bytes(lib.ws.dir) == before


def test_apply_include_that_did_not_land_restores(lib):
    lib.pre(flags=["unresolved track titles"])
    before = tree_bytes(lib.ws.dir)
    v = V([include("x.mp3")], [judge("unresolved track titles", "real-fixed-by-action")])
    post = mk([T("a.mp3", "A", dur=300.0), T("b.mp3", "B", src="unresolved", dur=30.0),
               T("c.mp3", "C", dur=400.0)])          # gather did not re-admit x.mp3
    r = lib.apply(v, lib.redo(post))
    assert (r.status, r.diff) == ("restored", ["x.mp3: dropped (not predicted)"]), r
    assert tree_bytes(lib.ws.dir) == before


@pytest.mark.parametrize("mode", ["auto", "accept"])
def test_switch_with_a_non_venue_edit_is_refused_before_writing(lib, mode):
    lib.pre(flags=[VENUE_FLAG])
    before = tree_bytes(lib.ws.dir)
    calls = []
    v = V([switch("gd73-sib"), exclude("b.mp3")], [judge(VENUE_FLAG, conf="medium")])
    r = lib.apply(v, calls.append, mode=mode)
    assert r.status == "refused" and r.held is True and calls == []
    assert r.error == ("switch_recording cannot be applied with other edits (exclude); "
                       "only venue may accompany it")
    assert tree_bytes(lib.ws.dir) == before and not (lib.ws.dir / ".txn").exists()


def test_structure_only_verdict_writes_subjectless_structure_overrule(lib):
    # no track-list edit: the research-sets overrule is written before the redo
    lib.pre(flags=[SETS_FLAG])
    v = V([structure(["a.mp3"]), overrule(SETS_FLAG)], [judge(SETS_FLAG)])
    post = mk([T("a.mp3", "A", dur=300.0), T("b.mp3", "B", src="unresolved", dur=30.0, s="2"),
               T("c.mp3", "C", dur=400.0, s="2")])
    r = lib.apply(v, lib.redo(post))
    assert r.status == "applied", r
    assert [o.kind for o in read_overrides(lib.ws).overrules] == ["research-sets"]


def test_track_list_verdict_defers_subjectless_structure_overrule(lib):
    lib.pre(flags=[SETS_FLAG])
    v = V([exclude("b.mp3"), overrule(SETS_FLAG)], [judge(SETS_FLAG)])
    r = lib.apply(v, lib.redo(_post_excluding_b()))
    assert r.status == "applied", r
    assert read_overrides(lib.ws).overrules == []


def test_silenced_flag_without_passing_judgement_restores(lib):
    lib.pre(flags=[VENUE_FLAG])
    before = tree_bytes(lib.ws.dir)
    # gather drops the venue flag, judged spurious at LOW confidence: below the medium bar
    v = V([exclude("b.mp3")], [judge(VENUE_FLAG, conf="low")])
    r = lib.apply(v, lib.redo(_post_excluding_b()))
    assert r.status == "restored" and tree_bytes(lib.ws.dir) == before
    assert r.diff == [f"flag silenced without a passing judgement: {VENUE_FLAG}"]
    # at medium it passes
    v = V([exclude("b.mp3")], [judge(VENUE_FLAG, conf="medium")])
    assert lib.apply(v, lib.redo(_post_excluding_b())).status == "applied"


def test_silenced_flag_in_accept_mode_apply(lib):
    lib.pre(flags=[VENUE_FLAG])
    v = V([exclude("b.mp3")], [judge(VENUE_FLAG, conf="low")])
    r = lib.apply(v, lib.redo(_post_excluding_b()), mode="accept")
    assert r.status == "applied", r


def test_switch_also_runs_silenced_flags(lib):
    lib.pre(flags=[VENUE_FLAG])
    before = tree_bytes(lib.ws.dir)
    post = mk([T("a1.mp3", "A", dur=300.0), T("b1.mp3", "B", src="unresolved", dur=30.0),
               T("c1.mp3", "C", dur=400.0), T("d1.mp3", "D", dur=100.0)], ident="gd73")
    v = V([switch("gd73-sib")], [judge(VENUE_FLAG, "undecidable")])
    r = lib.apply(v, lib.redo(post, select="gd73"), mode="accept")
    assert lib.stages == ["select"]
    assert r.status == "restored" and r.diff == [
        f"flag silenced without a passing judgement: {VENUE_FLAG}"]
    assert tree_bytes(lib.ws.dir) == before
    # judged spurious: the switch applies, and the whole-show check is not run on it
    v = V([switch("gd73-sib"), ed("venue", venue="RFK Stadium")],
          [judge(VENUE_FLAG, conf="low")])
    r = lib.apply(v, lib.redo(post, select="gd73"), mode="accept")
    assert r.status == "applied", r                  # venue may accompany a switch
    assert (read_overrides(lib.ws).recording, read_overrides(lib.ws).venue) == (
        "gd73-sib", "RFK Stadium")


def test_switch_coverage_failure_restores_snapshot(lib):
    lib.pre(flags=[VENUE_FLAG], tracks=[T("a.mp3", "Bertha", dur=300.0),
                                        T("b.mp3", "B", src="unresolved", dur=30.0),
                                        T("c.mp3", "Dark Star", dur=400.0)])
    before = tree_bytes(lib.ws.dir)
    post = mk([T("b1.mp3", "B", src="unresolved", dur=30.0), T("c1.mp3", "Dark Star", dur=900.0),
               T("d1.mp3", "Wharf Rat", dur=600.0), T("e1.mp3", "Sugaree", dur=300.0)])
    v = V([switch("gd73-sib")], [judge(VENUE_FLAG, conf="medium")])
    r = lib.apply(v, lib.redo(post, select="gd73"))
    assert r.status == "restored" and r.diff == [
        "missing title: Bertha not in the new recording"], r
    assert tree_bytes(lib.ws.dir) == before


def test_rehold_overrules_only_full_key_matches_all_or_nothing(lib):
    lib.pre(flags=[VENUE_FLAG])
    v = V([set_title("b.mp3", "Jam")], [judge(VENUE_FLAG, conf="medium")])
    post = mk([T("a.mp3", "A", dur=300.0), T("b.mp3", "Jam", src="override", dur=30.0),
               T("c.mp3", "C", dur=400.0)], flags=[VENUE_FLAG])
    r = lib.apply(v, lib.redo(post))
    assert (r.status, r.held, r.reheld) == ("applied", False, [VENUE_FLAG]), r
    assert lib.stages == ["gather", "package"]
    rules = read_overrides(lib.ws).overrules
    assert [(o.kind, o.source, o.flag) for o in rules] == [("venue", "adjudicate", VENUE_FLAG)]
    s = read_model(lib.ws.show, Show)
    assert s.needs_review is False and s.review_flags == []
    assert (lib.ws.package_dir / "manifest.json").exists()


def test_rehold_package_failure_restores(lib):
    lib.pre(flags=[VENUE_FLAG])
    before = tree_bytes(lib.ws.dir)
    v = V([set_title("b.mp3", "Jam")], [judge(VENUE_FLAG, conf="medium")])
    post = mk([T("a.mp3", "A", dur=300.0), T("b.mp3", "Jam", src="override", dur=30.0),
               T("c.mp3", "C", dur=400.0)], flags=[VENUE_FLAG])
    real = lib.redo(post)

    def redo(stage):
        if stage == "package":
            write_artifact(lib.ws.adjudication, {"partial": True})
            raise LlamaError("package refused")
        return real(stage)
    r = lib.apply(v, redo)
    assert (r.status, r.error) == ("refused", "package refused"), r
    assert lib.stages == ["gather"] and lib.commits == []
    assert tree_bytes(lib.ws.dir) == before


def test_rehold_any_unmatched_flag_keeps_the_hold(lib, tmp_path):
    lib.pre(flags=[VENUE_FLAG])
    v = V([set_title("b.mp3", "Jam")], [judge(VENUE_FLAG, conf="medium")])
    post = mk([T("a.mp3", "A", dur=300.0), T("b.mp3", "Jam", src="override", dur=30.0),
               T("c.mp3", "C", dur=400.0)], flags=[VENUE_FLAG, CLOSER_FLAG])
    r = lib.apply(v, lib.redo(post))
    assert (r.status, r.held, r.reheld) == ("applied", True, []), r
    assert lib.stages == ["gather"]
    assert read_overrides(lib.ws).overrules == []
    assert read_model(lib.ws.show, Show).needs_review is True


def test_accept_mode_skips_rehold(lib):
    lib.pre(flags=[VENUE_FLAG])
    v = V([set_title("b.mp3", "Jam")], [judge(VENUE_FLAG, conf="medium")])
    post = mk([T("a.mp3", "A", dur=300.0), T("b.mp3", "Jam", src="override", dur=30.0),
               T("c.mp3", "C", dur=400.0)], flags=[VENUE_FLAG])
    r = lib.apply(v, lib.redo(post), mode="accept")
    assert (r.status, r.held, r.reheld) == ("applied", True, []), r
    assert lib.stages == ["gather"]


def test_applied_record_written_inside_unit_commits(lib):
    lib.pre(flags=["unresolved track titles"])
    seen = []

    def on_commit(post, res):
        assert (lib.ws.dir / ".txn").exists()            # inside the unit
        write_artifact(lib.ws.adjudication, {"result": res.status})
        seen.append((post.tracks[-1].filename, capture_view(lib.ws)))
    v = V([exclude("b.mp3")], [judge("unresolved track titles", "real-fixed-by-action")])
    r = lib.apply(v, lib.redo(_post_excluding_b()), on_commit=on_commit)
    assert r.status == "applied" and seen and seen[0][0] == "c.mp3"
    assert lib.ws.adjudication.exists()                   # committed with the show


def test_on_commit_failure_restores(lib):
    lib.pre(flags=["unresolved track titles"])
    before = tree_bytes(lib.ws.dir)

    def on_commit(post, res):
        write_artifact(lib.ws.adjudication, {"x": 1})
        raise LlamaError("record failed")
    v = V([exclude("b.mp3")], [judge("unresolved track titles", "real-fixed-by-action")])
    r = lib.apply(v, lib.redo(_post_excluding_b()), on_commit=on_commit)
    assert (r.status, r.error) == ("refused", "record failed")
    assert tree_bytes(lib.ws.dir) == before


def test_trial_restores_but_reports_applied(lib):
    lib.pre(flags=["unresolved track titles"])
    before = tree_bytes(lib.ws.dir)
    v = V([exclude("b.mp3")], [judge("unresolved track titles", "real-fixed-by-action")])
    r = lib.apply(v, lib.redo(_post_excluding_b()), trial=True,
                  on_commit=lambda post, res: write_artifact(lib.ws.adjudication, {"x": 1}))
    assert r == ApplyResult("applied", False, [], ["- b.mp3 (0:30) B"], None, [])
    assert tree_bytes(lib.ws.dir) == before and not lib.ws.adjudication.exists()
    assert not (lib.ws.dir / ".txn").exists()


def _raising_redo(lib, exc):
    def redo(stage):
        write_artifact(lib.ws.show, _post_excluding_b())
        write_artifact(lib.ws.adjudication, {"partial": True})
        raise exc
    return redo


@pytest.mark.parametrize("exc", [StationUnpaired("s: station copy does not pair: no copy pairs"),
                                 StationUnreadable("s: station copy unreadable: x"),
                                 LlamaError("overrides.set_breaks: out of range")])
def test_station_refusal_restores_and_becomes_proposal(lib, exc):
    lib.pre(flags=[VENUE_FLAG])
    before = tree_bytes(lib.ws.dir)
    v = V([exclude("b.mp3")], [judge(VENUE_FLAG, conf="medium")])
    r = lib.apply(v, _raising_redo(lib, exc))
    assert (r.status, r.error, r.held) == ("refused", str(exc), True)
    assert tree_bytes(lib.ws.dir) == before and lib.commits == []


@pytest.mark.parametrize("exc", [IAError("download of a.mp3 failed"), TaskFailed("brief failed"),
                                 HerderError("transport")])
def test_transient_failure_restores_and_is_transient(lib, exc):
    lib.pre(flags=[VENUE_FLAG])
    before = tree_bytes(lib.ws.dir)
    v = V([exclude("b.mp3")], [judge(VENUE_FLAG, conf="medium")])
    r = lib.apply(v, _raising_redo(lib, exc))
    assert (r.status, r.error) == ("transient", str(exc))
    assert tree_bytes(lib.ws.dir) == before


@pytest.mark.parametrize("exc", [RateLimited("limit"), ShowChanged("s: the show was removed")])
def test_ratelimited_propagates_after_restore(lib, exc):
    lib.pre(flags=[VENUE_FLAG])
    before = tree_bytes(lib.ws.dir)
    v = V([exclude("b.mp3")], [judge(VENUE_FLAG, conf="medium")])
    with pytest.raises(type(exc)):
        lib.apply(v, _raising_redo(lib, exc))
    assert tree_bytes(lib.ws.dir) == before and not (lib.ws.dir / ".txn").exists()


def test_showchanged_when_expect_is_stale(lib):
    lib.pre(flags=[VENUE_FLAG])
    expect = capture_view(lib.ws)
    write_artifact(lib.ws.overrides, Overrides(venue="X"))
    before = tree_bytes(lib.ws.dir)
    calls = []
    v = V([exclude("b.mp3")], [judge(VENUE_FLAG, conf="medium")])
    with pytest.raises(ShowChanged):
        lib.apply(v, calls.append, expect=expect)
    assert calls == [] and tree_bytes(lib.ws.dir) == before


def test_interrupt_mid_redo_restores_everything(lib):
    lib.pre(flags=[VENUE_FLAG])
    before = tree_bytes(lib.ws.dir)
    v = V([exclude("b.mp3")], [judge(VENUE_FLAG, conf="medium")])
    with pytest.raises(KeyboardInterrupt):
        lib.apply(v, _raising_redo(lib, KeyboardInterrupt()))
    assert tree_bytes(lib.ws.dir) == before and not (lib.ws.dir / ".txn").exists()


def test_auto_mode_needs_a_gate(lib):
    lib.pre(flags=[VENUE_FLAG])
    v = V([exclude("b.mp3")], [judge(VENUE_FLAG, conf="medium")])
    with pytest.raises(ValueError):
        lib.apply(v, lib.redo(_post_excluding_b()), gate=None)
