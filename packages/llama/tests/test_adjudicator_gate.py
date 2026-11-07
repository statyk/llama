"""The adjudicator's target validation and policy gate (spec "The policy gate", "Before
judging", the auto-switch bar under "Recording pin"). Pure: every Bundle is built
directly, with no IO. Each boundary test is a pass/fail pair whose comment names the
boundary it pins (the Task 5 mutation pass relies on them)."""
from __future__ import annotations

import dataclasses

import pytest

from llama.adjudicator.bundle import EVIDENCE_KINDS, Bundle, FileMeta, Row, escape_braces
from llama.adjudicator.gate import (LONG_BAR_KINDS, OVERRULE_BAR, REFUSED_INCLUDE_REASONS,
                                    STRUCTURE_KINDS, TAPER_SIDE_KINDS, TITLE_BAR_SOURCES,
                                    TITLE_WEAK_KINDS, EditGate, Facts, GateResult, evaluate,
                                    flag_passes, has_track_list_edit,
                                    has_track_list_or_structure_edit, is_filler_title, normalize,
                                    first_judgements, quote_ok, quote_rows, sibling_match,
                                    stem_in, validate_targets)
from llama.adjudicator.runner import held_proposal
from llama.adjudicator.verdict import Evidence, Verdict
from llama.junk import SPAM_REASON
from llama.models import Overrides, Show, Track
from llama.overrules import flag_key

CUR = "gd73-06-10.aud.cur"
SIB = "gd73-06-10.sbd.sib"
DESC, OTAG, DTAG, SIBT = "taper-description", "original-tag", "derivative-tag", "sibling-tracks"
SLFM, JB, REV = "setlistfm", "jerrybase", "review"
VENUE_FLAG = "venue mismatch: archive 'RFK' vs jerrybase 'RFK Stadium'"
SONG_FLAG = "research asserts unknown song: Dark Star"
SETS_FLAG = "research asserts 3 sets but structure has 2"
LINEAGE = {"sbd": 3.0, "matrix": 2.5, "aud": 1.0, "unknown": 0.0}


# ---------------------------------------------------------------- builders

def trk(fn, title=None, src="unresolved", dur=30.0, i=1, s="1"):
    return Track(index=i, set=s, title=title if title is not None else fn.rsplit(".", 1)[0],
                 filename=fn, duration_sec=dur, title_source=src)


def make_bundle(tracks=(), *, excluded=(), overrides=None, sections=None, files=None,
                selection=None, flags=()):
    tracks = [t.model_copy(update={"index": i}) for i, t in enumerate(tracks, 1)]
    show = Show(performance_id="gd-1973-06-10", identifier=CUR, artist="Grateful Dead",
                date="1973-06-10", tracks=tracks, excluded_files=list(excluded),
                review_flags=list(flags), needs_review=bool(flags))
    secs = {k: [] for k in EVIDENCE_KINDS}
    for k, rows in (sections or {}).items():
        secs[k] = [r if isinstance(r, Row) else Row(text=escape_braces(r)) for r in rows]
    # The default sibling keeps as many tracks as the show: the sibling-coverage veto
    # (tested on its own below) stays out of every other test.
    sel = selection if selection is not None else {
        "identifier": CUR, "scores": {CUR: {"lineage": "aud", "kept_tracks": 10},
                                      SIB: {"lineage": "sbd", "kept_tracks": len(tracks)}}}
    text = "\n".join(r.text for k in EVIDENCE_KINDS for r in secs[k])
    # By default each excluded file has a metadata row with a real tag (no length, so
    # `length_of` is unchanged): an include then has a determinable, real predicted title,
    # and the include placeholder check (tested on its own below) stays out of other tests.
    if files is None:
        files = {x["filename"]: FileMeta(name=x["filename"], source="original",
                                         format="VBR MP3", title="Bird Song", length_s=None,
                                         original=None) for x in excluded}
    return Bundle(slug="gd1973-06-10", show=show, overrides=overrides or Overrides(), view=None,
                  provenance=None, selection=sel, files=files, sections=secs, text=text)


def make_facts(bundle, *, delivered=False, marked=False, lineage=None, complaints=None):
    return Facts(bundle=bundle, delivered=delivered, marked=marked,
                 lineage=LINEAGE if lineage is None else lineage,
                 complaints={} if complaints is None else complaints)


def ev(kind, quote):
    return {"kind": kind, "quote": quote}


def ed(op, conf="high", evidence=None, **kw):
    return {"op": op, "confidence": conf, "why": "w",
            "evidence": evidence if evidence is not None else [ev(DESC, "taper notes")], **kw}


def judge(flag, verdict="spurious", conf="high"):
    return {"flag": flag, "verdict": verdict, "confidence": conf, "why": "w"}


def make_verdict(edits, flags=None, *, show=None, **kw):
    """`flags=None` judges every flag of `show` spurious/high."""
    if flags is None:
        flags = [judge(f) for f in (show.review_flags if show else [])]
    return Verdict.model_validate({"flags": flags, "edits": edits, "kind": "fix",
                                   "show_correct_after": "yes", "rationale": "r", **kw})


def run(edits, bundle, **facts_kw):
    v = make_verdict(edits, show=bundle.show)
    return evaluate(v, make_facts(bundle, **facts_kw))


DESC_ROWS = ["x-d1t1 is crowd noise", "taper notes", "track 7 is a repeat",
             "x-d1t10 is a repeat", "x-d1t1 and x-d1t10 are repeats", "ax-d1t1 is a repeat"]


def excludes(*durs, conf="medium", evidence=None):
    """(edits, bundle): one exclude per duration of an unresolved track x-d1tN.mp3."""
    tracks = [trk(f"x-d1t{i}.mp3", dur=d) for i, d in enumerate(durs, 1)]
    b = make_bundle(tracks, sections={DESC: DESC_ROWS})
    return [ed("exclude", conf, evidence, file=t.filename) for t in tracks], b


def exclude(dur, conf="medium", evidence=None):
    return excludes(dur, conf=conf, evidence=evidence)


def gates(case, **facts_kw) -> list[EditGate]:
    edits, b = case
    return run(edits, b, **facts_kw).edits


def gate_for(case, **facts_kw) -> EditGate:
    return gates(case, **facts_kw)[0]


STEM_QUOTE = [ev(DESC, "x-d1t1 is crowd noise")]


# ---------------------------------------------------------------- constants

def test_constants_have_the_specced_values():
    from llama.adjudicator import gate
    assert (gate.SHORT_EDIT_MAX_S, gate.VERDICT_SUM_MAX_S, gate.SIBLING_TOL_S,
            gate.SIBLING_TOL_FRAC, gate.COVERAGE_ADDED_MAX_S,
            gate.SIBLING_COVERAGE_TOL_S) == (60.0, 120.0, 2.0, 0.01, 60.0, 60.0)
    assert LONG_BAR_KINDS == {DESC, OTAG, SIBT}
    assert TITLE_WEAK_KINDS == {SLFM, JB, REV}
    assert TAPER_SIDE_KINDS == {DESC, OTAG, DTAG}
    assert REFUSED_INCLUDE_REASONS == {"duplicate-listing", "duplicate derivative", SPAM_REASON}
    assert STRUCTURE_KINDS == {"research-sets", "alignment", "single-set", "sets-not-found",
                               "jerrybase-set-count", "jerrybase-closer"}
    assert TITLE_BAR_SOURCES == {"unresolved", "tags", "desc-position", "sibling-format",
                                 "sibling-align", "sibling", "setlist", "setlist-gap"}


# ---------------------------------------------------------------- 60 s boundary (short vs long bar)

def test_exclude_at_exactly_60s_takes_short_bar():          # 60 s: inclusive on the short side
    g = gate_for(exclude(dur=60.0, conf="medium"))
    assert (g.bar, g.passed) == ("short", True)


def test_exclude_at_60_01s_takes_long_bar_and_medium_fails():   # 60 s: 60.01 is long
    g = gate_for(exclude(dur=60.01, conf="medium"))
    assert (g.bar, g.passed) == ("long", False)


def test_include_takes_the_same_60s_boundary():              # 60 s, include arm
    def case(d):
        b = make_bundle([trk("x-d1t2.mp3")], sections={DESC: DESC_ROWS},
                        excluded=[{"filename": "x-d1t1.mp3", "reasons": ["short"],
                                   "duration_sec": d}])
        return [ed("include", "medium", file="x-d1t1.mp3")], b
    assert gate_for(case(60.0)).bar == "short"
    assert gate_for(case(60.01)).bar == "long"


# unknown duration
def test_unknown_duration_is_long_bar():                     # unknown counts as > 60 s
    assert gate_for(exclude(dur=None, conf="medium")).bar == "long"
    assert gate_for(exclude(dur=10.0, conf="medium")).bar == "short"


# 120 s cumulative boundary
def test_three_40s_edits_sum_120_stay_short():               # 120 s sum: inclusive on short side
    assert all(g.bar == "short" for g in gates(excludes(40, 40, 40)))


def test_two_61s_free_sum_121_moves_short_edits_long():      # 120 s sum: 121 is long
    assert all(g.bar == "long" for g in gates(excludes(30, 30, 61.0)))


def test_sum_just_over_120_moves_every_edit_long():          # 120 s sum, every edit <= 60 s
    assert all(g.bar == "long" for g in gates(excludes(40, 40, 40.01)))


def test_unknown_in_verdict_sends_every_track_edit_long():   # one unknown makes the sum inf
    assert all(g.bar == "long" for g in gates(excludes(5, 5, None)))
    assert all(g.bar == "short" for g in gates(excludes(5, 5, 5)))


def test_length_is_the_larger_of_metadata_and_measured():    # Bundle.length_of feeds the bar
    edits, b = exclude(dur=30.0)
    b = make_bundle(b.show.tracks, sections={DESC: DESC_ROWS},
                    files={"x-d1t1.mp3": FileMeta("x-d1t1.mp3", "derivative", "VBR MP3", "",
                                                  90.0, None)})
    assert gate_for((edits, b)).bar == "long"


# ---------------------------------------------------------------- long-bar evidence

def test_long_bar_passes_with_description_quote_naming_stem():
    g = gate_for(exclude(dur=200, conf="high", evidence=STEM_QUOTE))
    assert (g.bar, g.passed) == ("long", True)


def _own_tag_case(quote_file_rows):
    files = {"x-d1t1.mp3": FileMeta("x-d1t1.mp3", "derivative", "VBR MP3", "", 200.0,
                                    "x-d1t1.flac"),
             "x-d1t1.flac": FileMeta("x-d1t1.flac", "original", "Flac", "", 200.0, None)}
    rows = [Row(text=t, filename=fn, length_s=200.0) for fn, t in quote_file_rows]
    b = make_bundle([trk("x-d1t1.mp3", dur=200.0)], files=files, sections={OTAG: rows})
    return [ed("exclude", "high", [ev(OTAG, "x-d1t1.flac | Flac")], file="x-d1t1.mp3")], b


def test_long_bar_fails_when_quote_only_in_own_tag_row():     # own-tag-row exclusion
    only_own = _own_tag_case([("x-d1t1.flac", "x-d1t1.flac | Flac | crowd | 200")])
    g = gate_for(only_own)
    assert (g.bar, g.passed) == ("long", False)
    also_other = _own_tag_case([("x-d1t1.flac", "x-d1t1.flac | Flac | crowd | 200"),
                                ("x-d1t2.flac", "x-d1t2.flac | note: x-d1t1.flac | Flac | 5")])
    assert gate_for(also_other).passed


def test_long_bar_fails_from_derivative_tag_kind():           # LONG_BAR_KINDS excludes derivative
    def case(kind):
        b = make_bundle([trk("x-d1t1.mp3", dur=200.0)],
                        sections={kind: ["x-d1t2.mp3 | VBR MP3 | after x-d1t1 | 200"]})
        return [ed("exclude", "high", [ev(kind, "after x-d1t1")], file="x-d1t1.mp3")], b
    assert not gate_for(case(DTAG)).passed
    assert gate_for(case(OTAG)).passed


def test_long_bar_fails_without_stem():                       # the stem clause
    assert not gate_for(exclude(dur=200, conf="high", evidence=[ev(DESC, "crowd noise")])).passed
    assert gate_for(exclude(dur=200, conf="high", evidence=STEM_QUOTE)).passed


def test_long_bar_fails_on_track_position_alone():            # "track 7" names no file
    g = gate_for(exclude(dur=200, conf="high", evidence=[ev(DESC, "track 7 is a repeat")]))
    assert (g.bar, g.passed) == ("long", False)


def test_long_bar_stem_is_token_bounded():                    # stem_in lookarounds
    # exclude of x-d1t1.mp3: a quote naming only "x-d1t10" fails; "x-d1t1 and x-d1t10" passes
    assert not gate_for(exclude(200, "high", [ev(DESC, "x-d1t10 is a repeat")])).passed
    assert gate_for(exclude(200, "high", [ev(DESC, "x-d1t1 and x-d1t10")])).passed


def test_long_bar_stem_is_token_bounded_on_the_left():        # the lookbehind alone
    assert not gate_for(exclude(200, "high", [ev(DESC, "ax-d1t1 is a repeat")])).passed


def test_stem_in_unit():
    assert stem_in("x-d1t1 and more", "x-d1t1.mp3")
    assert stem_in("(X-D1T1)", "x-d1t1.mp3")
    assert not stem_in("x-d1t10", "x-d1t1.mp3")
    assert not stem_in("ax-d1t1", "x-d1t1.mp3")
    assert stem_in("see gd73-06-10d1t05.", "gd73-06-10d1t05.mp3")


def test_long_bar_needs_high_confidence():                    # long bar: high only
    assert not gate_for(exclude(200, "medium", STEM_QUOTE)).passed
    assert gate_for(exclude(200, "high", STEM_QUOTE)).passed


def test_short_bar_needs_medium_or_high():                    # short bar: low fails
    assert not gate_for(exclude(10, "low")).passed
    assert gate_for(exclude(10, "medium")).passed


# ---------------------------------------------------------------- propose-only classes

def _exclude_titled(title, src="tags", dur=5.0):
    b = make_bundle([trk("x-d1t1.mp3", title, src, dur)], sections={DESC: DESC_ROWS})
    return [ed("exclude", "medium", file="x-d1t1.mp3")], b


def test_exclude_of_resolved_song_is_propose_only_any_length():   # resolved-song exclude rule
    g = gate_for(_exclude_titled("Sugaree"))
    assert (g.bar, g.passed) == ("propose-only", False)
    assert "resolved song title" in g.reason
    assert gate_for(_exclude_titled("Sugaree", dur=500.0)).bar == "propose-only"


def test_exclude_of_filler_titled_track_is_not_resolved_song():
    g = gate_for(_exclude_titled("Tuning"))
    assert (g.bar, g.passed) == ("short", True)


def test_exclude_of_placeholder_titled_track_is_not_resolved_song():
    assert gate_for(_exclude_titled("Track 3")).bar == "short"


def test_exclude_of_unresolved_track_is_not_resolved_song():
    assert gate_for(_exclude_titled("Sugaree", src="unresolved")).bar == "short"


def test_filler_segue_with_a_song_is_a_resolved_song():
    assert gate_for(_exclude_titled("Tuning > Promised Land")).bar == "propose-only"
    assert gate_for(_exclude_titled("Tuning -> Crowd")).bar == "short"


def test_is_filler_title_unit():
    assert is_filler_title("Tuning")
    assert is_filler_title("Tuning -> Crowd > Banter")
    assert not is_filler_title("Tuning > Promised Land")
    assert not is_filler_title("Sugaree")


def _include_row(reasons, *, overrides=None, dur=10.0):
    b = make_bundle([trk("x-d1t2.mp3")], sections={DESC: DESC_ROWS}, overrides=overrides,
                    excluded=[{"filename": "x-d1t1.mp3", "reasons": reasons,
                               "duration_sec": dur}])
    return [ed("include", "medium", file="x-d1t1.mp3")], b


@pytest.mark.parametrize("reason", ["duplicate-listing", "duplicate derivative",
                                    "spam-shaped name or tag"])
def test_include_of_refused_reason_is_propose_only(reason):    # REFUSED_INCLUDE_REASONS
    g = gate_for(_include_row(["short", reason]))
    assert (g.bar, g.passed) == ("propose-only", False)
    assert gate_for(_include_row(["short"])).passed


def test_include_of_operator_excluded_row_changes_existing_entry():   # existing-overrides rule
    g = gate_for(_include_row(["operator-excluded"]))
    assert (g.bar, g.passed) == ("propose-only", False)
    assert g.reason == "changes an existing overrides.json entry"


def test_include_of_a_file_in_overrides_exclude_changes_existing_entry():
    g = gate_for(_include_row(["short"], overrides=Overrides(exclude=["x-d1t1.mp3"])))
    assert (g.bar, g.reason) == ("propose-only", "changes an existing overrides.json entry")


def test_exclude_of_an_included_file_changes_existing_entry():
    b = make_bundle([trk("x-d1t1.mp3", dur=5.0)], sections={DESC: DESC_ROWS},
                    overrides=Overrides(include=["x-d1t1.mp3"]))
    g = gate_for(([ed("exclude", "medium", file="x-d1t1.mp3")], b))
    assert (g.bar, g.reason) == ("propose-only", "changes an existing overrides.json entry")
    assert gate_for(exclude(5.0)).passed


# ---------------------------------------------------------------- substring check

def b_with(*texts, kind=DESC):
    return make_bundle([trk("x-d1t1.mp3")], sections={kind: list(texts)})


def test_quote_normalisation_folds_case_whitespace_curly_quotes_and_entities():
    assert quote_ok(Evidence(kind="taper-description", quote="Bertha > ‘Greatest’"),
                    b_with("bertha &gt;  'greatest'"))
    assert quote_ok(Evidence(kind=DESC, quote="“Dark   Star”"), b_with('the "dark\nstar" jam'))
    assert normalize("A&amp;B  \n ‘x’ “y”") == "a&b 'x' \"y\""


def test_fabricated_quote_fails_the_edit():                    # quote_ok
    g = gate_for(exclude(10, "medium", [ev(DESC, "a quote nobody wrote")]))
    assert (g.passed, g.reason) == (False, "quote not found in taper-description")
    assert gate_for(exclude(10, "medium", [ev(DESC, "crowd noise")])).passed


def test_one_failing_quote_fails_the_edit():
    g = gate_for(exclude(10, "medium", [ev(DESC, "crowd noise"), ev(DESC, "invented")]))
    assert (g.passed, g.reason) == (False, "quote not found in taper-description")


def test_quote_checked_against_claimed_kind_only():           # claimed kind's section only
    b = make_bundle([trk("x-d1t1.mp3", dur=10.0)], sections={REV: ["x-d1t1 is crowd noise"]})
    claimed_desc = [ed("exclude", "medium", [ev(DESC, "x-d1t1 is crowd noise")],
                       file="x-d1t1.mp3")]
    assert not gate_for((claimed_desc, b)).passed
    claimed_rev = [ed("exclude", "medium", [ev(REV, "x-d1t1 is crowd noise")],
                      file="x-d1t1.mp3")]
    assert gate_for((claimed_rev, b)).passed


def test_quote_with_unescaped_braces_matches_escaped_bundle():   # quote "{{x}}" vs "{ {x} }"
    b = b_with("set {{x}} here")
    assert b.sections[DESC][0].text == "set { {x} } here"
    assert quote_ok(Evidence(kind=DESC, quote="{{x}}"), b)


def test_quote_that_normalises_to_nothing_fails():
    assert not quote_ok(Evidence(kind=DESC, quote="&#32;"), b_with("anything"))


def test_quote_rows_are_the_rows_containing_the_quote():
    b = b_with("one Sugaree", "two", "three sugaree")
    rows = quote_rows(Evidence(kind=DESC, quote="SUGAREE"), b)
    assert [r.text for r in rows] == ["one Sugaree", "three sugaree"]


# ---------------------------------------------------------------- sibling-match tolerance

def _sib_bundle(d, row_len, title="Sugaree", src="unresolved", cur_title=None, overrides=None):
    row = Row(text=f"{SIB} | s-d1t1.mp3 | {title} | {row_len}", filename="s-d1t1.mp3",
              identifier=SIB, length_s=row_len, title=title)
    return make_bundle([trk("x-d1t1.mp3", cur_title, src, d)], sections={SIBT: [row]},
                       overrides=overrides)


@pytest.mark.parametrize("d,row,ok", [(100, 102.0, True), (100, 102.01, False),   # 2 s floor
                                      (400, 404.0, True), (400, 404.01, False)])  # 1 % above 200 s
def test_sibling_match_tolerance(d, row, ok):
    b = _sib_bundle(d, row)
    assert sibling_match(Evidence(kind=SIBT, quote="s-d1t1.mp3 | Sugaree"), b,
                         b.show.tracks[0]) is ok


def test_sibling_match_is_symmetric_below():                   # abs(): shorter sibling file
    b = _sib_bundle(100, 98.0)
    assert sibling_match(Evidence(kind=SIBT, quote="Sugaree"), b, b.show.tracks[0])
    b = _sib_bundle(100, 97.99)
    assert not sibling_match(Evidence(kind=SIBT, quote="Sugaree"), b, b.show.tracks[0])


def test_sibling_match_unknown_duration_fails():
    b = _sib_bundle(None, 100.0)
    assert not sibling_match(Evidence(kind=SIBT, quote="Sugaree"), b, b.show.tracks[0])
    b = _sib_bundle(100, None)
    assert not sibling_match(Evidence(kind=SIBT, quote="Sugaree"), b, b.show.tracks[0])


# ---------------------------------------------------------------- title bar

def title_edit(title="Sugaree", conf="high", evidence=None, file="x-d1t1.mp3"):
    return ed("set_title", conf, evidence or [ev(DESC, "x-d1t1 Sugaree")], file=file, title=title)


def test_title_from_sibling_needs_match_and_title_in_quote():  # sibling path
    ok = _sib_bundle(100, 101.0)
    g = gate_for(([title_edit(evidence=[ev(SIBT, "s-d1t1.mp3 | Sugaree")])], ok))
    assert (g.bar, g.passed) == ("title", True)
    off = _sib_bundle(100, 110.0)
    assert not gate_for(([title_edit(evidence=[ev(SIBT, "s-d1t1.mp3 | Sugaree")])], off)).passed
    assert not gate_for(([title_edit(evidence=[ev(SIBT, "s-d1t1.mp3")])], ok)).passed


def test_title_must_appear_in_its_quote():                     # title-in-quote requirement
    b = make_bundle([trk("x-d1t1.mp3")], sections={DESC: ["x-d1t1 Sugaree"]})
    assert not gate_for(([title_edit(evidence=[ev(DESC, "x-d1t1")])], b)).passed
    assert gate_for(([title_edit(evidence=[ev(DESC, "x-d1t1 Sugaree")])], b)).passed


def test_title_from_taper_description_passes():
    b = make_bundle([trk("x-d1t1.mp3")], sections={DESC: ["x-d1t1 Sugaree"]})
    g = gate_for(([title_edit()], b))
    assert (g.bar, g.passed) == ("title", True)


def _otag_title_bundle():
    files = {"x-d1t1.mp3": FileMeta("x-d1t1.mp3", "derivative", "VBR MP3", "", 30.0,
                                    "x-d1t1.flac"),
             "x-d1t1.flac": FileMeta("x-d1t1.flac", "original", "Flac", "Sugaree", 30.0, None)}
    rows = [Row(text="x-d1t1.flac | Flac | Sugaree | 30", filename="x-d1t1.flac",
                length_s=30.0, title="Sugaree"),
            Row(text="x-d1t2.flac | Flac | Sugaree | 40", filename="x-d1t2.flac",
                length_s=40.0, title="Sugaree")]
    return make_bundle([trk("x-d1t1.mp3")], files=files, sections={OTAG: rows})


def test_title_from_own_original_tag_row_passes_other_row_fails():   # own-row anchor
    b = _otag_title_bundle()
    assert gate_for(([title_edit(evidence=[ev(OTAG, "x-d1t1.flac | Flac | Sugaree")])], b)).passed
    assert not gate_for(([title_edit(evidence=[ev(OTAG, "x-d1t2.flac | Flac | Sugaree")])],
                         b)).passed


@pytest.mark.parametrize("kinds", [(SLFM,), (JB,), (REV,), (SLFM, JB, REV)])
def test_title_from_setlistfm_jerrybase_or_review_alone_is_propose_only(kinds):  # weak branch
    b = make_bundle([trk("x-d1t1.mp3")], sections={k: ["Sugaree"] for k in kinds})
    g = gate_for(([title_edit(evidence=[ev(k, "Sugaree") for k in kinds])], b))
    assert (g.bar, g.passed) == ("propose-only", False)
    assert g.reason == "setlist.fm, JerryBase or reviews alone"


def test_title_with_a_weak_and_a_strong_quote_takes_the_title_bar():
    b = make_bundle([trk("x-d1t1.mp3")], sections={DESC: ["x-d1t1 Sugaree"], REV: ["Sugaree"]})
    g = gate_for(([title_edit(evidence=[ev(REV, "Sugaree"), ev(DESC, "x-d1t1 Sugaree")])], b))
    assert (g.bar, g.passed) == ("title", True)


def test_title_over_override_source_is_propose_only():         # existing-overrides rule (titles)
    b = make_bundle([trk("x-d1t1.mp3", "Bertha", "override")], sections={DESC: ["x-d1t1 Sugaree"]})
    g = gate_for(([title_edit()], b))
    assert (g.bar, g.reason) == ("propose-only", "changes an existing overrides.json entry")
    b = make_bundle([trk("x-d1t1.mp3")], sections={DESC: ["x-d1t1 Sugaree"]},
                    overrides=Overrides(titles={"x-d1t1.mp3": "Bertha"}))
    assert gate_for(([title_edit()], b)).bar == "propose-only"


def test_title_needs_high_confidence():                         # title bar: high only
    b = make_bundle([trk("x-d1t1.mp3")], sections={DESC: ["x-d1t1 Sugaree"]})
    assert not gate_for(([title_edit(conf="medium")], b)).passed
    assert gate_for(([title_edit(conf="high")], b)).passed


@pytest.mark.parametrize("src", sorted(TITLE_BAR_SOURCES))
def test_every_title_bar_source_is_eligible(src):
    b = make_bundle([trk("x-d1t1.mp3", "Bertha", src)], sections={DESC: ["x-d1t1 Sugaree"]})
    g = gate_for(([title_edit()], b))
    assert (g.bar, g.passed) == ("title", True)


def test_title_over_an_unknown_source_is_never_unless_placeholder():
    b = make_bundle([trk("x-d1t1.mp3", "Bertha", "mystery")], sections={DESC: ["x-d1t1 Sugaree"]})
    assert gate_for(([title_edit()], b)).bar == "never"
    b = make_bundle([trk("x-d1t1.mp3", "Track 3", "mystery")], sections={DESC: ["x-d1t1 Sugaree"]})
    assert gate_for(([title_edit()], b)).bar == "title"


# ---------------------------------------------------------------- structure bar

S_TRACKS = [trk(f"x-s1t0{i}.mp3", i=i) for i in (1, 2)] + [trk(f"x-s2t0{i}.mp3") for i in (1, 2)]


def struct(conf="high", evidence=None, breaks=("x-s1t02.mp3",), encore="x-s2t01.mp3"):
    return ed("structure", conf, evidence or [ev(OTAG, "x-s2t01.flac")],
              breaks_after=list(breaks), encore_after=encore)


def s_bundle(overrides=None):
    return make_bundle(S_TRACKS, overrides=overrides, sections={
        OTAG: ["x-s2t01.flac | Flac | Encore: U.S. Blues | 300"], DTAG: ["Set II"],
        DESC: ["Set II"], SIBT: ["Set II"], SLFM: ["Set II"], JB: ["Set II"], REV: ["Set II"]})


def test_structure_with_s1t_filename_quote_passes():
    g = gate_for(([struct()], s_bundle()))
    assert (g.bar, g.passed) == ("structure", True)


@pytest.mark.parametrize("kind", sorted(TAPER_SIDE_KINDS))
def test_structure_passes_from_each_taper_side_kind(kind):
    assert gate_for(([struct(evidence=[ev(kind, "Set II" if kind != OTAG else "x-s2t01")])],
                     s_bundle())).passed


@pytest.mark.parametrize("kinds", [(SLFM,), (JB,), (SLFM, JB)])
def test_structure_from_setlistfm_only_is_propose_only(kinds):   # taper-side requirement
    g = gate_for(([struct(evidence=[ev(k, "Set II") for k in kinds])], s_bundle()))
    assert (g.bar, g.passed) == ("propose-only", False)


@pytest.mark.parametrize("kind", [SIBT, REV])
def test_structure_from_other_non_taper_kinds_fails_the_bar(kind):
    g = gate_for(([struct(evidence=[ev(kind, "Set II")])], s_bundle()))
    assert (g.bar, g.passed) == ("structure", False)


def test_structure_needs_high_confidence():
    assert not gate_for(([struct(conf="medium")], s_bundle())).passed


@pytest.mark.parametrize("ov", [Overrides(set_breaks=[]), Overrides(set_breaks=["x-s1t01.mp3"]),
                                Overrides(encore_after="x-s2t01.mp3")])
def test_structure_over_existing_override_is_propose_only(ov):
    g = gate_for(([struct()], s_bundle(ov)))
    assert (g.bar, g.reason) == ("propose-only", "changes an existing overrides.json entry")


# I1 (R4 fix round 1): a structure edit naming a file the same verdict includes is
# propose-only: the included file's play position is not predicted, so neither is the split.
S_INC = "x-s1t03.mp3"


def _s_inc_run(structure_edit):
    b = make_bundle(S_TRACKS, excluded=[{"filename": S_INC, "reasons": ["short"],
                                         "duration_sec": 10.0}],
                    files={S_INC: FileMeta(S_INC, "original", "VBR MP3", "Bird Song", 10.0,
                                           None)},
                    sections={OTAG: ["x-s2t01.flac | Flac | Encore: U.S. Blues | 300"],
                              DESC: ["Set II"]})
    v = make_verdict([ed("include", "medium", [ev(DESC, "Set II")], file=S_INC),
                      structure_edit], show=b.show)
    return evaluate(v, make_facts(b))


@pytest.mark.parametrize("edit", [struct(breaks=("x-s1t02.mp3",), encore=S_INC),
                                  struct(breaks=(S_INC,), encore="x-s2t01.mp3")],
                         ids=["encore", "break"])
def test_structure_naming_an_included_file_is_propose_only(edit):
    r = _s_inc_run(edit)
    assert r.edits[0].passed and r.vetoes == []
    assert (r.edits[1].bar, r.edits[1].passed, r.edits[1].reason) == (
        "propose-only", False,
        "structure names a file this verdict includes; its position is not predicted")
    assert r.auto is False


def test_structure_on_current_files_beside_an_include_is_unaffected():
    r = _s_inc_run(struct())
    assert [(g.bar, g.passed) for g in r.edits] == [("short", True), ("structure", True)]
    assert r.auto is True


# ---------------------------------------------------------------- venue, city

def test_venue_medium_passes_low_fails_existing_override_proposes():   # venue override rule
    b = make_bundle([trk("x-d1t1.mp3")], sections={DESC: ["taper notes"]})
    assert gate_for(([ed("venue", "medium", venue="RFK")], b)) == EditGate(
        0, "venue", "medium", True, "")
    assert not gate_for(([ed("venue", "low", venue="RFK")], b)).passed
    b = make_bundle([trk("x-d1t1.mp3")], sections={DESC: ["taper notes"]},
                    overrides=Overrides(venue="Capital Centre"))
    g = gate_for(([ed("venue", "high", venue="RFK")], b))
    assert (g.bar, g.passed, g.reason) == ("propose-only", False,
                                            "changes an existing overrides.json entry")


def test_city_always_propose_only():
    b = make_bundle([trk("x-d1t1.mp3")], sections={DESC: ["taper notes"]})
    g = gate_for(([ed("city", "high", city="Washington, DC")], b))
    assert (g.bar, g.passed) == ("propose-only", False)


def test_propose_only_ops_are_propose_only():
    b = make_bundle([trk("x-d1t1.mp3")])
    for op in ("set_date", "untitled", "narration", "rm", "redo_research"):
        g = gate_for(([{"op": op, "confidence": "high", "why": "w"}], b))
        assert (g.op, g.bar, g.passed) == (op, "propose-only", False)


# ---------------------------------------------------------------- overrule bars by flag kind

OVERRULE_CASES = [
    (SONG_FLAG, "research-song", "title"),
    ("research asserts wrong date: 1973-06-11", "research-date", "title"),
    (SETS_FLAG, "research-sets", "structure"),
    ("low-confidence structure alignment (0.41)", "alignment", "structure"),
    ("single-set structure for a long show (150 min)", "single-set", "structure"),
    ("setlist evidence shows multiple sets but none were found", "sets-not-found", "structure"),
    ("structure has 1 sets but jerrybase shows 2", "jerrybase-set-count", "structure"),
    ("jerrybase set closer 'Sugaree' is not at a set break", "jerrybase-closer", "structure"),
    (VENUE_FLAG, "venue", "medium"),
    ("briefing mentions unknown song: Foo", "briefing-song", "medium"),
    ("briefing references nonexistent set: 3", "briefing-set", "medium"),
    ("briefing claims a 4-hour show", "briefing-other", "medium"),
    ("unresolved track titles: 3 of 10", "titles", "never"),
    ("low-confidence setlist parse (0.3)", "low-confidence-setlist", "never"),
    ("tape spans 1973-06-09 and 1973-06-10", "tape-spans", "never"),
    ("multi-event date: two shows", "multi-event", "never"),
    ("unassigned multi-event recordings: a, b", "events-unassigned", "never"),
    ("no playable tracks", "no-tracks", "never"),
    ("merged tracks x-d1t05 span a set break", "merged-tracks", "never"),
    ("recordings of this date disagree on city: 'A' (selected) vs 'B'", "city", "never"),
    ("something else entirely", "other", "never"),
]


def _overrule_case(flag, conf="high", evidence=None, verdict="spurious", jconf="high"):
    # A resolved title: the placeholder veto (tested on its own below) stays out.
    b = make_bundle([trk("x-d1t1.mp3", "Sugaree", "tags")], flags=[flag], sections={
        DESC: ["taper notes"], DTAG: ["taper notes"], SLFM: ["taper notes"],
        REV: ["taper notes"], OTAG: ["taper notes"], SIBT: ["taper notes"]})
    v = make_verdict([ed("overrule", conf, evidence, flag=flag)],
                     [judge(flag, verdict, jconf)])
    return v, b


def overrule_gate(flag, **kw) -> EditGate:
    v, b = _overrule_case(flag, **kw)
    return evaluate(v, make_facts(b)).edits[0]


@pytest.mark.parametrize("flag,kind,bar", OVERRULE_CASES)
def test_overrule_bar_by_kind(flag, kind, bar):               # each OVERRULE_BAR value
    b = make_bundle([trk("x-d1t1.mp3")], flags=[flag])
    assert flag_key(flag, b.show).kind == kind
    assert OVERRULE_BAR[kind] == bar
    high, med = overrule_gate(flag, conf="high"), overrule_gate(flag, conf="medium")
    assert high.bar == med.bar == bar
    assert (high.passed, med.passed) == {"title": (True, False), "structure": (True, False),
                                         "medium": (True, True), "never": (False, False)}[bar]


def test_overrule_table_covers_every_case_kind():
    assert set(OVERRULE_BAR) == {k for _, k, _ in OVERRULE_CASES}


def test_unmapped_overrule_kind_is_never():
    from llama.adjudicator.gate import overrule_bar
    from llama.overrules import FlagKey
    import llama.adjudicator.gate as gate
    show = make_bundle().show
    assert overrule_bar("no playable tracks", show) == "never"
    orig = gate.flag_key
    try:
        gate.flag_key = lambda f, s: FlagKey("brand-new-kind", None)
        assert overrule_bar("whatever", show) == "never"
    finally:
        gate.flag_key = orig


def test_medium_overrule_low_confidence_fails():
    assert not overrule_gate(VENUE_FLAG, conf="low").passed


def test_duration_mismatch_is_never_overruled():
    g = overrule_gate("duration mismatch on x-d1t1.mp3: tag 300 s vs file 200 s")
    assert (g.bar, g.passed) == ("never", False)


def test_overrule_of_flag_not_judged_spurious_fails():
    for verdict in ("real-fixed-by-action", "real-not-fixable", "undecidable"):
        g = overrule_gate(VENUE_FLAG, verdict=verdict)
        assert (g.passed, g.reason) == (False, "overrule of a flag not judged spurious")
    assert overrule_gate(VENUE_FLAG).passed


def test_title_and_structure_overrules_need_high_and_quote():
    for flag in (SONG_FLAG, SETS_FLAG):
        assert not overrule_gate(flag, conf="medium").passed
        assert overrule_gate(flag, conf="high").passed
        assert not overrule_gate(flag, evidence=[ev(DESC, "invented")]).passed


def test_structure_overrule_needs_taper_side_quote():          # setlistfm-only quote fails
    assert not overrule_gate(SETS_FLAG, evidence=[ev(SLFM, "taper notes")]).passed
    assert not overrule_gate(SETS_FLAG, evidence=[ev(SIBT, "taper notes")]).passed
    assert overrule_gate(SETS_FLAG, evidence=[ev(DTAG, "taper notes")]).passed


def test_title_overrule_from_weak_kinds_alone_fails():          # review-only quote fails
    assert not overrule_gate(SONG_FLAG, evidence=[ev(REV, "taper notes")]).passed
    assert not overrule_gate(SONG_FLAG, evidence=[ev(DTAG, "taper notes")]).passed
    for kind in (DESC, OTAG, SIBT):
        assert overrule_gate(SONG_FLAG, evidence=[ev(kind, "taper notes")]).passed


# ---------------------------------------------------------------- auto-switch bar

def switch_case(break_it=None):
    scores = {CUR: {"lineage": "aud", "kept_tracks": 10}, SIB: {"lineage": "sbd", "kept_tracks": 12}}
    facts_kw, ov = {}, Overrides()
    edits = [ed("switch_recording", "high", [ev(SIBT, "soundboard, complete")], identifier=SIB)]
    if break_it == "no_format":
        scores[SIB]["kept_tracks"] = 0
    elif break_it == "complaints":
        facts_kw["complaints"] = {SIB: 1}
    elif break_it == "worse_lineage":
        scores[SIB]["lineage"], scores[CUR]["lineage"] = "matrix", "sbd"
    elif break_it == "unknown_lineage":
        scores[SIB]["lineage"] = "weird"
    elif break_it == "unknown_current_lineage":
        scores[CUR]["lineage"] = "weird"
    elif break_it == "low_conf":
        edits[0]["confidence"] = "medium"
    elif break_it in ("delivered", "marked"):
        facts_kw[break_it] = True
    elif break_it == "keyed_entries":
        ov = Overrides(exclude=["x-d1t1.mp3"])
    elif break_it == "existing_pin":
        ov = Overrides(recording=SIB)
    elif break_it == "other_title_edit":
        edits.append(title_edit())
    elif break_it == "overrule_too":
        edits.append(ed("overrule", "medium", flag=VENUE_FLAG))
    elif break_it == "venue_too":
        edits.append(ed("venue", "medium", venue="RFK"))
    b = make_bundle([trk("x-d1t1.mp3")], flags=[VENUE_FLAG], overrides=ov,
                    selection={"identifier": CUR, "scores": scores},
                    sections={SIBT: ["soundboard, complete"], DESC: ["x-d1t1 Sugaree", "taper notes"]})
    return make_verdict(edits, show=b.show, better_sibling=SIB), make_facts(b, **facts_kw)


SWITCH_REASON = {
    "no_format": "sibling has no file in the wanted format",
    "complaints": "select found recording complaints against the sibling",
    "worse_lineage": "sibling's lineage class ranks worse than the current recording's",
    "unknown_lineage": "lineage class not in the lineage table",
    "low_conf": "switch needs high confidence",
    "delivered": "show is delivered",
    "marked": "show is station-marked",
    "keyed_entries": "overrides.json has filename-keyed entries",
    "existing_pin": "changes an existing overrides.json entry",
    "other_title_edit": "switch with a set_title edit",
    "overrule_too": "switch with a overrule edit",
}


@pytest.mark.parametrize("break_it", ["no_format", "complaints", "worse_lineage", "unknown_lineage",
                                      "low_conf", "delivered", "marked", "keyed_entries",
                                      "existing_pin", "other_title_edit", "overrule_too"])
def test_switch_fails_each_part(break_it):                     # each auto-switch part
    v, f = switch_case(break_it)
    r = evaluate(v, f)
    g = r.edits[0]
    assert g.op == "switch_recording" and not g.passed
    assert SWITCH_REASON[break_it] in g.reason
    assert not r.auto


def test_switch_unknown_current_lineage_is_propose_only():
    g = evaluate(*switch_case("unknown_current_lineage")).edits[0]
    assert (g.bar, g.passed) == ("propose-only", False)
    g = evaluate(*switch_case("unknown_lineage")).edits[0]
    assert (g.bar, g.passed) == ("propose-only", False)


def test_switch_passes_when_every_part_holds():
    r = evaluate(*switch_case())
    assert r.edits == [EditGate(0, "switch_recording", "switch", True, "")]
    assert r.auto and r.vetoes == []


def test_switch_with_equal_lineage_passes():                   # "no worse": equal is fine
    v, f = switch_case()
    f.bundle.selection["scores"][SIB]["lineage"] = "aud"
    assert evaluate(v, f).edits[0].passed


def test_switch_with_venue_only_passes():
    r = evaluate(*switch_case("venue_too"))
    assert [g.passed for g in r.edits] == [True, True] and r.auto


def test_switch_sibling_missing_from_complaints_counts_as_none():
    v, f = switch_case()
    f2 = make_facts(f.bundle, complaints={CUR: 3})
    assert evaluate(v, f2).edits[0].passed


# ---------------------------------------------------------------- vetoes

def veto_case(veto=None):
    flags = [VENUE_FLAG]
    b = make_bundle([trk("x-d1t1.mp3", dur=10.0)], flags=flags, sections={DESC: DESC_ROWS})
    judgements = [judge(VENUE_FLAG)]
    kw = {}
    edits = [ed("exclude", "medium", file="x-d1t1.mp3")]
    if veto == "kind_hold":
        kw["kind"] = "hold"
    elif veto == "not_correct_after":
        kw["show_correct_after"] = "unsure"
    elif veto == "not_fixable":
        judgements = [judge(VENUE_FLAG, "real-not-fixable")]
    elif veto == "undecidable":
        judgements = [judge(VENUE_FLAG, "undecidable")]
    elif veto == "unjudged_flag":
        judgements = []
    elif veto == "better_sibling_without_switch":
        kw["better_sibling"] = SIB
    elif veto == "no_edits":
        edits = []
    v = Verdict.model_validate({"flags": judgements, "edits": edits, "kind": "fix",
                                "show_correct_after": "yes", "rationale": "r", **kw})
    return v, make_facts(b)


VETO_TEXT = {
    "kind_hold": "kind is hold",
    "not_correct_after": "show not judged correct after the action (unsure)",
    "not_fixable": f"flag judged real-not-fixable: {VENUE_FLAG}",
    "undecidable": f"flag judged undecidable: {VENUE_FLAG}",
    "unjudged_flag": f"flag not judged: {VENUE_FLAG}",
    "better_sibling_without_switch": f"better_sibling {SIB} has no switch_recording edit to it",
    "no_edits": "no edits",
}


@pytest.mark.parametrize("veto", ["kind_hold", "not_correct_after", "not_fixable", "undecidable",
                                  "unjudged_flag", "better_sibling_without_switch", "no_edits"])
def test_verdict_level_vetoes(veto):                           # each veto
    r = evaluate(*veto_case(veto))
    assert r.vetoes == [VETO_TEXT[veto]]
    assert not r.auto


def test_no_veto_base_case_is_auto():
    r = evaluate(*veto_case())
    assert r.vetoes == [] and r.auto


def test_kind_overrule_is_not_vetoed():
    v, f = veto_case()
    v = v.model_copy(update={"kind": "overrule"})
    assert evaluate(v, f).vetoes == []


def test_better_sibling_with_a_switch_to_another_recording_is_vetoed():
    v, f = switch_case()
    v = v.model_copy(update={"better_sibling": "gd73-06-10.other"})
    assert "better_sibling gd73-06-10.other has no switch_recording edit to it" in \
        evaluate(v, f).vetoes


def test_better_sibling_is_compared_stripped():
    v, f = switch_case()
    v2 = Verdict.model_validate({**v.model_dump(), "better_sibling": f"  {SIB} "})
    assert evaluate(v2, f).vetoes == []


def test_any_failing_edit_blocks_auto():
    edits, b = excludes(10, 10)
    edits[1]["confidence"] = "low"
    r = run(edits, b)
    assert [g.passed for g in r.edits] == [True, False] and r.vetoes == [] and not r.auto


def test_propose_only_op_blocks_auto():
    edits, b = exclude(10)
    edits.append({"op": "set_date", "value": "1973-06-11", "confidence": "high", "why": "w"})
    r = run(edits, b)
    assert r.edits[1].bar == "propose-only" and not r.auto


def test_edit_gate_indexes_follow_the_verdict():
    edits, b = excludes(10, 10, 10)
    assert [g.index for g in run(edits, b).edits] == [0, 1, 2]


# ---------------------------------------------------------------- validation

VB = make_bundle([trk("gd73-06-10d1t01.mp3"), trk("gd73-06-10d1t02.mp3"),
                  trk("gd73-06-10d1t03.mp3")],
                 excluded=[{"filename": "gd73-06-10d1t04.mp3", "reasons": ["short"],
                            "duration_sec": 5.0}],
                 flags=[VENUE_FLAG], overrides=Overrides(titles={"gd73-06-10d1t03.mp3": "X"}))


def v_exclude(fn, flags=None):
    return make_verdict([ed("exclude", file=fn)], flags, show=VB.show)


def test_validate_accepts_a_valid_verdict():
    v = make_verdict([ed("exclude", file="gd73-06-10d1t01.mp3"),
                      ed("include", file="gd73-06-10d1t04.mp3"),
                      ed("set_title", file="gd73-06-10d1t02.mp3", title="Sugaree"),
                      ed("structure", breaks_after=["gd73-06-10d1t02.mp3"],
                         encore_after="gd73-06-10d1t03.mp3"),
                      ed("overrule", flag=VENUE_FLAG)], show=VB.show)
    assert validate_targets(v, VB) == []
    assert validate_targets(make_verdict([ed("switch_recording", identifier=SIB)], show=VB.show),
                            VB) == []


def test_validate_rejects_near_miss_filenames():
    b = VB
    for bad in ("GD73-06-10D1T01.mp3", "gd73-06-10d1t01.shn", "disc1/gd73-06-10d1t01.mp3", "1"):
        assert validate_targets(v_exclude(bad), b), bad


@pytest.mark.parametrize("edit", [
    ed("set_title", file="gd73-06-10d1t09.mp3", title="X"),
    ed("structure", breaks_after=["gd73-06-10d1t09.mp3"]),
    ed("structure", breaks_after=[], encore_after="gd73-06-10d1t09.mp3"),
    ed("include", file="gd73-06-10d1t01.mp3"),           # a track, not an excluded row
    ed("switch_recording", identifier=CUR),             # the current recording
    ed("switch_recording", identifier="gd73-06-10.unconsidered"),
    ed("overrule", flag="venue mismatch: archive 'RFK'"),   # not a current flag exactly
])
def test_validate_rejects_unknown_targets(edit):
    reasons = validate_targets(make_verdict([edit], show=VB.show), VB)
    assert len(reasons) == 1 and "edit 0" in reasons[0]


def test_validate_conflicts_and_keyed_exclude_and_unknown_flag_and_unconsidered_switch():
    t1, t2, t3 = "gd73-06-10d1t01.mp3", "gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3"
    def reasons(edits, flags=None):
        return validate_targets(make_verdict(edits, flags, show=VB.show), VB)
    # exclude + set_title of one file
    assert any("conflict" in r and t1 in r
               for r in reasons([ed("exclude", file=t1), ed("set_title", file=t1, title="X")]))
    # exclude of a file named by the structure edit
    assert any("conflict" in r and t2 in r
               for r in reasons([ed("exclude", file=t2), ed("structure", breaks_after=[t2])]))
    assert any("conflict" in r and t2 in r
               for r in reasons([ed("exclude", file=t2),
                                 ed("structure", breaks_after=[], encore_after=t2)]))
    # two set_titles of one file
    assert any("conflict" in r for r in reasons([ed("set_title", file=t1, title="X"),
                                                 ed("set_title", file=t1, title="Y")]))
    # exclude of a file carrying a titles key
    assert any("overrides.json" in r and t3 in r for r in reasons([ed("exclude", file=t3)]))
    # two structure edits, two switches
    assert any("more than one structure" in r
               for r in reasons([ed("structure", breaks_after=[t1]),
                                 ed("structure", breaks_after=[t2])]))
    assert any("more than one switch_recording" in r
               for r in reasons([ed("switch_recording", identifier=SIB),
                                 ed("switch_recording", identifier=SIB)]))
    # a judged flag that is not current, and a flag judged twice (differently: identical
    # repeats collapse, R5)
    assert any("not a current flag" in r
               for r in reasons([ed("exclude", file=t1)], [judge(VENUE_FLAG), judge("bogus")]))
    assert any("judged twice" in r
               for r in reasons([ed("exclude", file=t1)],
                                [judge(VENUE_FLAG), judge(VENUE_FLAG, "undecidable")]))
    # an unconsidered switch
    assert reasons([ed("switch_recording", identifier="nope")])


@pytest.mark.parametrize("ov", [Overrides(set_breaks=["gd73-06-10d1t01.mp3"]),
                                Overrides(encore_after="gd73-06-10d1t01.mp3"),
                                Overrides(titles={"gd73-06-10d1t01.mp3": "X"})])
def test_validate_rejects_exclude_of_a_keyed_file(ov):
    b = make_bundle(VB.show.tracks, overrides=ov, flags=[VENUE_FLAG])
    assert validate_targets(make_verdict([ed("exclude", file="gd73-06-10d1t01.mp3")],
                                         show=b.show), b)


# R4 (pilot-review §5, waynehancock): a set_title or structure edit may target a file the
# same verdict re-admits with an include; include + set_title of one file is no conflict.

T1, T4 = "gd73-06-10d1t01.mp3", "gd73-06-10d1t04.mp3"     # T4 is VB's one excluded row


def _vr(edits, flags=None):
    return validate_targets(make_verdict(edits, flags, show=VB.show), VB)


def test_validate_accepts_include_then_set_title_of_the_same_file():
    assert _vr([ed("include", file=T4), ed("set_title", file=T4, title="Sugaree")]) == []
    # either order
    assert _vr([ed("set_title", file=T4, title="Sugaree"), ed("include", file=T4)]) == []


@pytest.mark.parametrize("struct", [
    ed("structure", breaks_after=[], encore_after=T4),
    ed("structure", breaks_after=[T4], encore_after=None),
], ids=["encore", "break"])
def test_validate_accepts_include_then_structure_on_the_included_file(struct):
    assert _vr([ed("include", file=T4), struct]) == []


def test_validate_two_set_titles_on_an_included_file_conflict():
    r = _vr([ed("include", file=T4), ed("set_title", file=T4, title="X"),
             ed("set_title", file=T4, title="Y")])
    assert r == [f"edits 0, 1, 2: conflict on {T4}"]


def test_validate_two_set_titles_on_a_current_track_conflict():
    r = _vr([ed("set_title", file=T1, title="X"), ed("set_title", file=T1, title="Y")])
    assert r == [f"edits 0, 1: conflict on {T1}"]


def test_validate_include_and_exclude_of_one_file_conflict():
    r = _vr([ed("include", file=T4), ed("exclude", file=T4)])
    assert f"edits 0, 1: conflict on {T4}" in r


def test_validate_exclude_and_set_title_of_one_file_still_conflict():
    r = _vr([ed("exclude", file=T1), ed("set_title", file=T1, title="X")])
    assert r == [f"edits 0, 1: conflict on {T1}"]


@pytest.mark.parametrize("edit", [
    ed("set_title", file="gd73-06-10d1t09.mp3", title="X"),
    ed("set_title", file=T4, title="X"),                # excluded, but not included here
    ed("structure", breaks_after=[], encore_after=T4),
])
def test_validate_title_or_structure_on_a_file_neither_current_nor_included(edit):
    f = edit.get("file") or edit.get("encore_after")
    assert _vr([edit]) == [f"edit 0 {edit['op']}: {f} is not a current track or a file "
                           f"this verdict includes"]


def test_validate_an_included_near_miss_names_no_file():
    # exact and case-sensitive: an include of T4 does not admit a set_title of its near miss
    r = _vr([ed("include", file=T4), ed("set_title", file=T4.upper(), title="X")])
    assert r == [f"edit 1 set_title: {T4.upper()} is not a current track or a file this "
                 f"verdict includes"]


# R5 (pilot-review §5, discobiscuits): review_flags may carry a flag twice. Repeated
# judgements that agree on (verdict, confidence) collapse to the first; others are malformed.

DUP = make_bundle(VB.show.tracks, flags=[VENUE_FLAG, VENUE_FLAG, SONG_FLAG])


@pytest.mark.parametrize("second_why", ["first why", "other"], ids=["identical", "why-only"])
def test_validate_agreeing_repeated_judgements_collapse_to_the_first(second_why):
    first = {**judge(VENUE_FLAG), "why": "first why"}
    second = {**judge(VENUE_FLAG), "why": second_why}
    v = make_verdict([ed("overrule", flag=VENUE_FLAG)], [first, second, judge(SONG_FLAG)])
    assert validate_targets(v, DUP) == []
    kept = first_judgements(v)
    assert list(kept) == [VENUE_FLAG, SONG_FLAG] and kept[VENUE_FLAG].why == "first why"
    # the why shown in a held proposal (runner) is the first one's too
    hp = held_proposal(DUP.show, DUP.show, v)
    assert {f["judgement"]["why"] for f in hp["flags"] if f["flag"] == VENUE_FLAG} == {"first why"}


@pytest.mark.parametrize("second", [judge(VENUE_FLAG, "undecidable"),
                                    judge(VENUE_FLAG, conf="medium")],
                         ids=["verdict", "confidence"])
def test_validate_differing_repeated_judgements_are_malformed(second):
    v = make_verdict([ed("overrule", flag=VENUE_FLAG)],
                     [judge(VENUE_FLAG), second, judge(SONG_FLAG)])
    assert validate_targets(v, DUP) == [
        f"flag judgement {VENUE_FLAG!r}: judged twice with different verdicts or confidence"]


def test_a_duplicated_flag_judged_once_is_judged():
    v = make_verdict([ed("overrule", flag=VENUE_FLAG)], [judge(VENUE_FLAG), judge(SONG_FLAG)])
    r = evaluate(v, make_facts(DUP))
    assert not any("flag not judged" in x or "malformed" in x for x in r.vetoes), r.vetoes


# ---------------------------------------------------------------- flag_passes

FLAG_PASS_CASES = [
    ("real-fixed-by-action", "high", VENUE_FLAG, True),
    ("real-fixed-by-action", "medium", VENUE_FLAG, True),
    ("real-fixed-by-action", "low", VENUE_FLAG, False),
    ("real-fixed-by-action", "medium", "unresolved track titles: 3 of 10", True),
    ("spurious", "high", VENUE_FLAG, True),
    ("spurious", "medium", VENUE_FLAG, True),
    ("spurious", "low", VENUE_FLAG, False),
    ("spurious", "medium", "briefing claims a 4-hour show", True),
    ("spurious", "high", "unresolved track titles: 3 of 10", False),
    ("spurious", "high", "something else entirely", False),
    ("spurious", "high", "duration mismatch on x-d1t1.mp3: 300 vs 200", False),
    ("spurious", "high", SONG_FLAG, False),          # bare judgement, no overrule edit
    ("spurious", "high", SETS_FLAG, False),
    ("real-not-fixable", "high", VENUE_FLAG, False),
    ("undecidable", "high", VENUE_FLAG, False),
]


@pytest.mark.parametrize("verdict,conf,flag,ok", FLAG_PASS_CASES)
def test_flag_passes(verdict, conf, flag, ok):
    b = make_bundle([trk("x-d1t1.mp3")], flags=[flag])
    v = make_verdict([], [judge(flag, verdict, conf)])
    gate = evaluate(v, make_facts(b))
    assert flag_passes(v.flags[0], b.show, v, gate) is ok


@pytest.mark.parametrize("flag", [SONG_FLAG, SETS_FLAG])
def test_flag_passes_title_and_structure_kinds_need_a_passing_overrule_edit(flag):
    # spurious/high with no overrule edit fails; with a failing overrule edit fails; with a passing one passes
    v, b = _overrule_case(flag, conf="medium")
    gate = evaluate(v, make_facts(b))
    assert not gate.edits[0].passed
    assert not flag_passes(v.flags[0], b.show, v, gate)
    v, b = _overrule_case(flag, conf="high")
    gate = evaluate(v, make_facts(b))
    assert gate.edits[0].passed
    assert flag_passes(v.flags[0], b.show, v, gate)
    bare = make_verdict([], [judge(flag)])
    assert not flag_passes(bare.flags[0], b.show, bare, evaluate(bare, make_facts(b)))


def test_flag_passes_needs_the_overrule_edit_for_that_flag():
    flags = [SONG_FLAG, "research asserts unknown song: Bertha"]
    b = make_bundle([trk("x-d1t1.mp3", "Sugaree", "tags")], flags=flags,
                    sections={DESC: ["taper notes"]})
    v = make_verdict([ed("overrule", flag=SONG_FLAG)], [judge(f) for f in flags])
    gate = evaluate(v, make_facts(b))
    assert flag_passes(v.flags[0], b.show, v, gate)
    assert not flag_passes(v.flags[1], b.show, v, gate)


# ---------------------------------------------------------------- edit-class helpers

def test_has_track_list_edit_and_structure_variant():
    def v(*ops):
        es = {"include": ed("include", file="a"), "exclude": ed("exclude", file="a"),
              "switch_recording": ed("switch_recording", identifier=SIB),
              "structure": ed("structure", breaks_after=[]), "venue": ed("venue", venue="V"),
              "set_title": ed("set_title", file="a", title="T")}
        return make_verdict([es[o] for o in ops])
    for op in ("include", "exclude", "switch_recording"):
        assert has_track_list_edit(v(op)) and has_track_list_or_structure_edit(v(op))
    assert not has_track_list_edit(v("structure")) and has_track_list_or_structure_edit(v("structure"))
    assert not has_track_list_edit(v("venue", "set_title"))
    assert not has_track_list_or_structure_edit(v("venue", "set_title"))


def test_gate_result_shape():
    r = evaluate(*veto_case())
    assert isinstance(r, GateResult) and isinstance(r.edits[0], EditGate)


# ---------------------------------------------------------------- fix round 1 (t5-quality)

def test_switch_with_fabricated_quote_fails():                 # F1(a): switch quotes are checked
    v, f = switch_case()
    v.edits[0].evidence[0] = Evidence(kind=SIBT, quote="a quote nobody wrote")
    r = evaluate(v, f)
    g = r.edits[0]
    assert (g.passed, g.reason) == (False, "quote not found in sibling-tracks")
    assert not r.auto


def test_switch_with_no_evidence_fails():                      # F1(b): at least one checked quote
    from llama.adjudicator.verdict import SwitchRecording
    v, f = switch_case()
    bare = SwitchRecording.model_construct(op="switch_recording", confidence="high",
                                           evidence=[], why="w", identifier=SIB)
    v = v.model_copy(update={"edits": [bare]})
    g = evaluate(v, f).edits[0]
    assert not g.passed and "switch needs at least one checked quote" in g.reason
    assert evaluate(*switch_case()).edits[0].passed


def _malformed(edit, *, flags=(VENUE_FLAG,)):
    b = make_bundle([trk("x-d1t1.mp3", dur=10.0)], flags=list(flags),
                    excluded=[{"filename": "x-d1t9.mp3", "reasons": ["short"],
                               "duration_sec": 5.0}],
                    sections={DESC: DESC_ROWS, SIBT: ["soundboard, complete"]})
    v = make_verdict([edit], show=b.show)
    return evaluate(v, make_facts(b))


@pytest.mark.parametrize("edit", [
    ed("exclude", "medium", file="x-d1t2.mp3"),                       # not a track
    ed("set_title", "high", [ev(DESC, "x-d1t1 is crowd noise")], file="x-d1t2.mp3",
       title="crowd"),                                               # not a track
    ed("include", "medium", file="x-d1t1.mp3"),                       # a track, not an excluded row
    ed("switch_recording", "high", [ev(SIBT, "soundboard, complete")],
       identifier="gd73-06-10.unconsidered"),                       # not considered
    ed("overrule", "medium", flag="venue mismatch: archive 'RFK'"),   # not a current flag
], ids=["exclude", "set_title", "include", "switch", "overrule"])
def test_evaluate_fails_closed_on_a_malformed_target(edit):        # F2
    r = _malformed(edit)
    assert any(v.startswith("malformed: edit 0") for v in r.vetoes), r.vetoes
    assert not r.auto


def test_evaluate_malformed_veto_even_when_the_edit_bar_passes():  # F2: bar passes, still vetoed
    r = _malformed(ed("include", "medium", file="x-d1t1.mp3"))
    assert r.edits[0].passed           # a 10 s track named as an include: the short bar passes
    assert not r.auto
    ok = _malformed(ed("exclude", "medium", file="x-d1t1.mp3"))
    assert ok.auto and ok.vetoes == []


def test_long_bar_same_stem_row_is_own_when_original_unrecorded():   # F3
    files = {"x-d1t1.mp3": FileMeta("x-d1t1.mp3", "derivative", "VBR MP3", "", 200.0, None),
             "x-d1t1.flac": FileMeta("x-d1t1.flac", "original", "Flac", "", 200.0, None)}
    rows = [Row(text="x-d1t1.flac | Flac | crowd | 200", filename="x-d1t1.flac", length_s=200.0)]
    b = make_bundle([trk("x-d1t1.mp3", dur=200.0)], files=files, sections={OTAG: rows})
    assert b.own_row(OTAG, "x-d1t1.mp3") is None
    g = gate_for(([ed("exclude", "high", [ev(OTAG, "x-d1t1.flac | Flac")], file="x-d1t1.mp3")], b))
    assert (g.bar, g.passed) == ("long", False)
    rows.append(Row(text="x-d1t2.flac | Flac | after x-d1t1.flac | Flac | 5",
                    filename="x-d1t2.flac", length_s=5.0))
    b = make_bundle([trk("x-d1t1.mp3", dur=200.0)], files=files, sections={OTAG: rows})
    assert gate_for(([ed("exclude", "high", [ev(OTAG, "x-d1t1.flac | Flac")],
                         file="x-d1t1.mp3")], b)).passed


def test_long_bar_same_stem_compare_ignores_case():                   # F3 casefold
    files = {"x-d1t1.mp3": FileMeta("x-d1t1.mp3", "derivative", "VBR MP3", "", 200.0, None),
             "X-D1T1.flac": FileMeta("X-D1T1.flac", "original", "Flac", "", 200.0, None)}
    rows = [Row(text="X-D1T1.flac | Flac | crowd | 200", filename="X-D1T1.flac",
                length_s=200.0)]
    b = make_bundle([trk("x-d1t1.mp3", dur=200.0)], files=files, sections={OTAG: rows})
    assert b.own_row(OTAG, "x-d1t1.mp3") is None
    g = gate_for(([ed("exclude", "high", [ev(OTAG, "X-D1T1.flac | Flac")],
                      file="x-d1t1.mp3")], b))
    assert (g.bar, g.passed) == ("long", False)


def test_stem_without_a_letter_never_counts():                  # F4: a bare number is a position
    assert not stem_in("track 01 is a repeat", "01.mp3")
    assert not stem_in("01", "01.mp3")
    b = make_bundle([trk("01.mp3", dur=200.0)], sections={DESC: ["01 is crowd noise"]})
    g = gate_for(([ed("exclude", "high", [ev(DESC, "01 is crowd noise")], file="01.mp3")], b))
    assert (g.bar, g.passed) == ("long", False)
    assert stem_in("d01 is a repeat", "d01.mp3")


def test_stem_in_lookarounds_are_unicode_aware():               # F5
    assert not stem_in("éx-d1t1 is a repeat", "x-d1t1.mp3")
    assert not stem_in("x-d1t1é is a repeat", "x-d1t1.mp3")
    assert stem_in("«x-d1t1» is a repeat", "x-d1t1.mp3")
    assert stem_in("x-d1t1_vbr", "x-d1t1.mp3")


# ---------------------------------------------------------------- sibling coverage (R2)
# A verdict with no switch_recording edit is propose-only while a considered recording
# keeps more than the current one (pilot-review §3 fix 1), and also while the considered
# recordings' coverage cannot be read (fail closed: operator ruling 2026-11-07).

def _cov(scores, *, sib_s=None, cur_n=1, cur_s=30.0, dur=30.0, selection=None, edits=None,
         excluded=(), overrides=None):
    """One unresolved 30 s track, a passing short exclude of it, and `scores` beside the
    current recording's own entry (which keeps `cur_n`, `cur_s` seconds by select's filter)."""
    import dataclasses
    tracks = [trk("x-d1t1.mp3", dur=dur)]
    sel = selection if selection is not None else {
        "identifier": CUR, "scores": {CUR: {"lineage": "aud", "kept_tracks": cur_n}, **scores}}
    b = make_bundle(tracks, sections={DESC: DESC_ROWS}, selection=sel, excluded=excluded,
                    overrides=overrides)
    b = dataclasses.replace(b, sibling_kept_s=dict(sib_s or {}), current_kept_s=cur_s)
    return run(edits if edits is not None else [ed("exclude", "medium", file="x-d1t1.mp3")], b)


def _cov_vetoes(r: GateResult) -> list[str]:
    return [v for v in r.vetoes if v.startswith(("considered recording", "coverage of"))]


_INC_ROW = {"filename": "x-d1t9.mp3", "reasons": ["short"], "duration_sec": 5.0}


# Only a switch exempts a verdict from the veto (final2 F2): an include verdict is held
# to it like an exclude one.
@pytest.mark.parametrize("edits", [
    None, [ed("include", "medium", file="x-d1t9.mp3")]], ids=["exclude", "include"])
def test_coverage_sibling_with_more_tracks_vetoes(edits):          # tracks: 2 > 1
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 2}}, edits=edits, excluded=[_INC_ROW])
    assert r.vetoes == [f"considered recording {SIB} keeps more (2 tracks, ? s) than the "
                        f"current (1 tracks, 30 s); no switch_recording edit"]
    assert r.auto is False and all(g.passed for g in r.edits)


def test_coverage_sibling_with_equal_tracks_does_not_veto():        # tracks: 1 == 1
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 1}})
    assert r.vetoes == [] and r.auto is True


def test_coverage_sibling_with_fewer_tracks_does_not_veto():        # tracks: 0 < 1
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 0}})
    assert r.vetoes == [] and r.auto is True


# Duration is a tie-break only (Shawn's ruling, 2026-11-07): it is compared only when the
# sibling keeps exactly as many tracks as the current recording.

def test_coverage_fewer_tracks_with_more_duration_does_not_veto():   # 0 < 1; 90.01 > 30 + 60
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 0}}, sib_s={SIB: 90.01})
    assert r.vetoes == [] and r.auto is True


def test_coverage_equal_tracks_with_more_duration_beyond_tolerance_vetoes():   # 90.01 > 30 + 60
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 1}}, sib_s={SIB: 90.01})
    assert r.vetoes == [f"considered recording {SIB} keeps more duration on equal tracks "
                        f"(1 tracks, 90 s) than the current (1 tracks, 30 s); "
                        f"no switch_recording edit"]
    assert r.auto is False


def test_coverage_sibling_duration_within_tolerance_does_not_veto():     # 90.0 == 30 + 60
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 1}}, sib_s={SIB: 90.0})
    assert r.vetoes == [] and r.auto is True


def test_coverage_more_tracks_with_less_duration_vetoes():          # 2 > 1; 10 < 30
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 2}}, sib_s={SIB: 10.0})
    assert r.vetoes == [f"considered recording {SIB} keeps more (2 tracks, 10 s) than the "
                        f"current (1 tracks, 30 s); no switch_recording edit"]
    assert r.auto is False


def test_coverage_more_tracks_and_more_duration_is_one_track_veto():   # 2 > 1; 9999 > 90
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 2}}, sib_s={SIB: 9999.0})
    assert r.vetoes == [f"considered recording {SIB} keeps more (2 tracks, 9999 s) than the "
                        f"current (1 tracks, 30 s); no switch_recording edit"]


def test_coverage_equal_tracks_with_unknown_sibling_duration_does_not_veto():
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 1}})            # no sibling_kept_s entry
    assert r.vetoes == [] and r.auto is True


def test_coverage_unknown_current_duration_skips_only_the_duration_clause():
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 1}}, sib_s={SIB: 9999.0}, cur_s=None)
    assert r.vetoes == [] and r.auto is True
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 2}}, sib_s={SIB: 9999.0}, cur_s=None)
    assert r.vetoes == [f"considered recording {SIB} keeps more (2 tracks, 9999 s) than the "
                        f"current (1 tracks, ? s); no switch_recording edit"]


def test_coverage_veto_absent_for_a_verdict_with_a_switch_edit():
    edits = [ed("switch_recording", identifier=SIB, evidence=[ev(DESC, "taper notes")])]
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 9}}, sib_s={SIB: 9999.0}, edits=edits)
    assert _cov_vetoes(r) == [] and r.vetoes == []
    r = _cov({}, selection={}, edits=edits)
    assert _cov_vetoes(r) == []          # (malformed here: no considered recordings at all)


def test_coverage_the_current_recordings_own_entry_is_not_a_sibling():
    r = _cov({}, selection={"identifier": CUR, "scores": {CUR: {"kept_tracks": 9}}},
             sib_s={CUR: 9999.0})
    assert r.vetoes == [] and r.auto is True


def test_coverage_selection_with_no_other_recording_does_not_veto():
    r = _cov({})
    assert r.vetoes == [] and r.auto is True


@pytest.mark.parametrize("sel", [{}, {"identifier": CUR}, {"identifier": CUR, "scores": None},
                                 {"identifier": CUR, "scores": []}])
def test_coverage_no_selection_vetoes(sel):                          # fail closed
    r = _cov({}, selection=sel)
    assert r.vetoes == ["considered recordings unknown (no selection.json scores); "
                        "no switch_recording edit"]
    assert r.auto is False


@pytest.mark.parametrize("entry", [{"lineage": "sbd"}, {"kept_tracks": None},
                                   {"kept_tracks": "3"}, {"kept_tracks": -1},
                                   {"kept_tracks": True}, {"kept_tracks": 2.5}, None])
def test_coverage_considered_entry_without_usable_kept_tracks_vetoes(entry):   # fail closed
    r = _cov({SIB: entry})
    assert r.vetoes == [f"coverage of considered recording {SIB} unknown (no usable "
                        f"kept_tracks); no switch_recording edit"]
    assert r.auto is False


# Like with like (R2 fix 1): the current side is the current recording's OWN selection.json
# entry and its select-filtered metadata duration, never show.json's track list.

def test_coverage_current_count_is_its_selection_kept_tracks_not_show_tracks():
    # show.json ships 1 track, but select counted 3 for the current recording: a sibling at
    # 2 keeps fewer on the same basis
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 2}}, cur_n=3)
    assert r.vetoes == [] and r.auto is True
    # select counted 0 for the current recording: a sibling at 1 keeps more
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 1}}, cur_n=0)
    assert r.vetoes == [f"considered recording {SIB} keeps more (1 tracks, ? s) than the "
                        f"current (0 tracks, 30 s); no switch_recording edit"]


def test_coverage_current_duration_is_its_filtered_metadata_not_show_tracks():
    # show.json's track sums 30 s, the current recording's filtered metadata 100 s
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 1}}, sib_s={SIB: 150.0}, cur_s=100.0)
    assert r.vetoes == [] and r.auto is True
    # show.json's track sums 3000 s, the current recording's filtered metadata 10 s
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 1}}, sib_s={SIB: 80.0}, cur_s=10.0,
             dur=3000.0, edits=[ed("exclude", "high", STEM_QUOTE, file="x-d1t1.mp3")])
    assert r.vetoes == [f"considered recording {SIB} keeps more duration on equal tracks "
                        f"(1 tracks, 80 s) than the current (1 tracks, 10 s); "
                        f"no switch_recording edit"]


@pytest.mark.parametrize("scores", [{}, {CUR: None}, {CUR: {"lineage": "aud"}},
                                    {CUR: {"kept_tracks": "1"}}, {CUR: {"kept_tracks": -1}},
                                    {CUR: {"kept_tracks": True}}])
def test_coverage_current_without_usable_kept_tracks_vetoes(scores):      # fail closed
    r = _cov({}, selection={"identifier": CUR, "scores": {**scores, SIB: {"kept_tracks": 0}}})
    assert r.vetoes == [f"coverage of the current recording {CUR} unknown (no usable "
                        f"kept_tracks); no switch_recording edit"]
    assert r.auto is False


@pytest.mark.parametrize("ident", ["gd73-06-10.other", None])
def test_coverage_identifier_disagreement_vetoes(ident):                   # fail closed
    sel = {"scores": {CUR: {"kept_tracks": 1}, SIB: {"kept_tracks": 0}}}
    if ident is not None:
        sel["identifier"] = ident
    r = _cov({}, selection=sel)
    assert r.vetoes == [f"current recording unknown (show.json {CUR} vs selection.json "
                        f"{ident}); no switch_recording edit"]
    assert r.auto is False


# An operator recording pin exempts the show (Shawn's ruling, 2026-11-07, final2 Minor 2):
# his choice of recording is the decision. Only a pin on the CURRENT recording whose source
# is "operator" (or absent: every pin written before the field came from `fix`) counts; a
# pin the adjudicator wrote on an auto switch stays subject to the veto.

_MORE = {SIB: {"lineage": "sbd", "kept_tracks": 2}}            # 2 > 1: vetoes unpinned


@pytest.mark.parametrize("ov", [Overrides(recording=CUR, recording_source="operator"),
                                Overrides(recording=CUR)], ids=["operator", "legacy-no-source"])
def test_coverage_operator_pin_on_the_current_recording_exempts(ov):
    r = _cov(_MORE, overrides=ov)
    assert r.vetoes == [] and r.auto is True
    r = _cov({SIB: {"lineage": "sbd", "kept_tracks": 1}}, sib_s={SIB: 9999.0}, overrides=ov)
    assert r.vetoes == [] and r.auto is True                  # the duration tie-break too


@pytest.mark.parametrize("sel", [{}, {"identifier": "gd73-06-10.other", "scores": {}},
                                 {"identifier": CUR, "scores": {SIB: {"kept_tracks": None}}}],
                         ids=["no-scores", "ident-disagrees", "unusable-entry"])
def test_coverage_operator_pin_exempts_the_unknown_coverage_vetoes(sel):
    r = _cov({}, selection=sel, overrides=Overrides(recording=CUR, recording_source="operator"))
    assert _cov_vetoes(r) == [] and r.vetoes == [] and r.auto is True


def test_coverage_adjudicate_pin_is_still_vetoed():
    r = _cov(_MORE, overrides=Overrides(recording=CUR, recording_source="adjudicate"))
    assert r.vetoes == [f"considered recording {SIB} keeps more (2 tracks, ? s) than the "
                        f"current (1 tracks, 30 s); no switch_recording edit"]
    assert r.auto is False


def test_coverage_operator_pin_on_another_recording_is_no_exemption():
    r = _cov(_MORE, overrides=Overrides(recording=SIB, recording_source="operator"))
    assert r.vetoes == [f"considered recording {SIB} keeps more (2 tracks, ? s) than the "
                        f"current (1 tracks, 30 s); no switch_recording edit"]
    assert r.auto is False


# ---------------------------------------------------------------- placeholder veto (R3)
# While any shipped title of the current show is a placeholder (or unresolved, or blank:
# fail closed), every research-song overrule is propose-only (pilot-review §3 fix 2;
# operator ruling 2026-11-07). Strict: set_title edits in the same verdict do not lift it.

DATE_FLAG = "research asserts wrong date: 1973-06-11"
BRIEF_FLAG = "briefing mentions unknown song: Foo"
SONG = (DESC, "taper notes")


def _ph_bundle(*tracks, flags=(SONG_FLAG,)):
    return make_bundle(list(tracks), flags=list(flags), sections={DESC: [
        "taper notes", "1. Sugaree 2. Bertha"]})


def _ph_run(bundle, edits, flags=None):
    v = make_verdict(edits, [judge(f) for f in (flags or bundle.show.review_flags)])
    return evaluate(v, make_facts(bundle))


SUGAREE = trk("x-d1t1.mp3", "Sugaree", "tags")
TRACK2 = trk("x-d1t2.mp3", "Track 2", "tags")


def test_placeholder_veto_blocks_a_research_song_overrule():
    b = _ph_bundle(SUGAREE, TRACK2)
    v = make_verdict([ed("overrule", flag=SONG_FLAG, evidence=[ev(*SONG)])], [judge(SONG_FLAG)])
    r = evaluate(v, make_facts(b))
    g = r.edits[0]
    assert (g.bar, g.passed) == ("propose-only", False)
    assert g.reason == ("research-song overrule while 1 shipped title(s) are placeholders "
                        "(e.g. x-d1t2.mp3: 'Track 2')")
    assert r.vetoes == [] and r.auto is False
    assert not flag_passes(v.flags[0], b.show, v, r)     # the flag stays uncleared


def test_placeholder_veto_reason_counts_every_placeholder_and_names_the_first():
    b = _ph_bundle(SUGAREE, TRACK2, trk("x-d1t3.mp3", "tmp", "tags"))
    g = _ph_run(b, [ed("overrule", flag=SONG_FLAG)]).edits[0]
    assert g.reason == ("research-song overrule while 2 shipped title(s) are placeholders "
                        "(e.g. x-d1t2.mp3: 'Track 2')")


def test_no_placeholder_titles_lets_the_research_song_overrule_pass():
    b = _ph_bundle(SUGAREE, trk("x-d1t2.mp3", "Bertha", "setlist"))
    r = _ph_run(b, [ed("overrule", flag=SONG_FLAG)])
    assert (r.edits[0].bar, r.edits[0].passed, r.edits[0].reason) == ("title", True, "")
    assert r.vetoes == [] and r.auto is True


@pytest.mark.parametrize("flag,bar", [(DATE_FLAG, "title"), (BRIEF_FLAG, "medium"),
                                      (SETS_FLAG, "structure"), (VENUE_FLAG, "medium")])
def test_placeholder_veto_leaves_other_overrule_kinds_alone(flag, bar):
    b = _ph_bundle(SUGAREE, TRACK2, flags=(flag,))
    r = _ph_run(b, [ed("overrule", flag=flag)])
    assert (r.edits[0].bar, r.edits[0].passed, r.edits[0].reason) == (bar, True, "")
    assert r.auto is True


def test_placeholder_veto_leaves_non_overrule_edits_alone():
    b = _ph_bundle(SUGAREE, TRACK2, flags=())
    r = _ph_run(b, [ed("set_title", file="x-d1t2.mp3", title="Bertha",
                       evidence=[ev(DESC, "1. Sugaree 2. Bertha")])])
    assert (r.edits[0].bar, r.edits[0].passed) == ("title", True)
    assert r.auto is True


def test_placeholder_veto_holds_even_when_set_title_edits_replace_the_placeholders():
    b = _ph_bundle(SUGAREE, TRACK2)
    r = _ph_run(b, [ed("set_title", file="x-d1t2.mp3", title="Bertha",
                       evidence=[ev(DESC, "1. Sugaree 2. Bertha")]),
                    ed("overrule", flag=SONG_FLAG)])
    assert r.edits[0].passed                       # the fill passes its own bar ...
    assert (r.edits[1].bar, r.edits[1].passed) == ("propose-only", False)
    assert r.auto is False                         # ... but the mixed verdict is a proposal


@pytest.mark.parametrize("track", [
    trk("x-d1t2.mp3", "Bertha", "unresolved"),     # unresolved source, a real-looking title
    trk("x-d1t2.mp3", "", "tags"),                 # empty title
    trk("x-d1t2.mp3", "   ", "tags"),              # blank title
], ids=["unresolved", "empty", "blank"])
def test_placeholder_veto_counts_unresolved_and_blank_titles(track):
    b = _ph_bundle(SUGAREE, track)
    g = _ph_run(b, [ed("overrule", flag=SONG_FLAG)]).edits[0]
    assert (g.bar, g.passed) == ("propose-only", False)
    assert g.reason == ("research-song overrule while 1 shipped title(s) are placeholders "
                        f"(e.g. x-d1t2.mp3: {track.title!r})")


def test_placeholder_veto_counts_a_none_title():
    none = trk("x-d1t2.mp3", "x", "tags").model_construct(
        index=2, set="1", title=None, filename="x-d1t2.mp3", duration_sec=30.0,
        title_source="tags")
    b = _ph_bundle(SUGAREE, none)
    g = _ph_run(b, [ed("overrule", flag=SONG_FLAG)]).edits[0]
    assert (g.bar, g.passed) == ("propose-only", False)
    assert g.reason == ("research-song overrule while 1 shipped title(s) are placeholders "
                        "(e.g. x-d1t2.mp3: None)")


@pytest.mark.parametrize("title", ["dbb2010-07-31t01.mp3", "d1t02", "27:36.27", "05:27 -"],
                         ids=["filename-stem", "short-stem", "timestamp", "timestamp-dash"])
def test_placeholder_veto_counts_residue_and_timestamp_titles(title):
    # Not the placeholder vocabulary (`is_placeholder` is False for each): the residue and
    # timestamp classes of `is_placeholder_title`, which fire in the pilot (deepbananablackout).
    b = _ph_bundle(SUGAREE, trk("x-d1t2.mp3", title, "tags"))
    g = _ph_run(b, [ed("overrule", flag=SONG_FLAG)]).edits[0]
    assert (g.bar, g.passed) == ("propose-only", False)
    assert g.reason == ("research-song overrule while 1 shipped title(s) are placeholders "
                        f"(e.g. x-d1t2.mp3: {title!r})")


# Clause (b) (R3 fix round 1, operator amendment): the predicted post-verdict kept set,
# so an include re-admitting a placeholder-titled file cannot clear the hold either. Apply's
# whole-show re-check does not compare an included file's title (apply.py whole_show_diff).

INC = "x-d1t3.mp3"


def _inc_bundle(tag, *, meta=True):
    files = {INC: FileMeta(name=INC, source="original", format="VBR MP3", title=tag,
                           length_s=30.0, original=None)} if meta else {}
    return make_bundle([SUGAREE, trk("x-d1t2.mp3", "Bertha", "tags")], flags=[SONG_FLAG],
                       excluded=[{"filename": INC, "reasons": ["short"], "duration_sec": 30.0}],
                       files=files, sections={DESC: ["taper notes", "3. Dark Star"]})


def _inc_run(b, *extra):
    return _ph_run(b, [ed("include", "medium", file=INC), *extra,
                       ed("overrule", flag=SONG_FLAG)])


def test_placeholder_veto_counts_an_include_of_a_placeholder_titled_file():
    r = _inc_run(_inc_bundle("Track 3"))
    assert r.edits[0].passed                        # the include passes its own bar
    g = r.edits[1]
    assert (g.bar, g.passed) == ("propose-only", False)
    assert g.reason == ("research-song overrule while 1 predicted post-verdict title(s) are "
                        "placeholders (e.g. x-d1t3.mp3: 'Track 3')")
    assert r.vetoes == [] and r.auto is False


def test_an_include_with_a_real_tag_title_does_not_trigger_the_veto():
    r = _inc_run(_inc_bundle("Dark Star"))
    assert [(g.bar, g.passed) for g in r.edits] == [("short", True), ("title", True)]
    assert r.auto is True


def test_a_set_title_on_the_included_file_lifts_clause_b():
    # R4: a set_title may target a file the same verdict includes, and clause (b) takes
    # the set_title's title for it, so a real title clears the veto and the verdict is valid.
    r = _inc_run(_inc_bundle("Track 3"), ed("set_title", file=INC, title="Dark Star",
                                            evidence=[ev(DESC, "3. Dark Star")]))
    assert (r.edits[2].bar, r.edits[2].passed, r.edits[2].reason) == ("title", True, "")
    assert r.vetoes == [] and r.auto is True


def test_a_placeholder_set_title_on_the_included_file_triggers_clause_b():
    # The included file's real tag does not help when the verdict titles it a placeholder.
    r = _inc_run(_inc_bundle("Dark Star"), ed("set_title", file=INC, title="Track 3",
                                              evidence=[ev(DESC, "taper notes")]))
    g = r.edits[2]
    assert (g.bar, g.passed) == ("propose-only", False)
    assert g.reason == ("research-song overrule while 1 predicted post-verdict title(s) are "
                        "placeholders (e.g. x-d1t3.mp3: 'Track 3')")
    assert r.vetoes == [] and r.auto is False


def test_a_set_title_to_a_placeholder_on_a_current_track_triggers_clause_b():
    b = _ph_bundle(SUGAREE, trk("x-d1t2.mp3", "Bertha", "tags"))
    r = _ph_run(b, [ed("set_title", file="x-d1t2.mp3", title="Track 2",
                       evidence=[ev(DESC, "taper notes")]), ed("overrule", flag=SONG_FLAG)])
    assert (r.edits[1].bar, r.edits[1].passed) == ("propose-only", False)
    assert r.edits[1].reason == ("research-song overrule while 1 predicted post-verdict "
                                 "title(s) are placeholders (e.g. x-d1t2.mp3: 'Track 2')")


@pytest.mark.parametrize("tag,meta", [("", True), ("d1t03", True), ("unknown", True),
                                      ("Dark Star", False)],
                         ids=["blank-tag", "residue-tag", "unknown-tag", "no-metadata-row"])
def test_an_included_file_with_an_undeterminable_title_counts(tag, meta):     # fail closed
    g = _inc_run(_inc_bundle(tag, meta=meta)).edits[1]
    assert (g.bar, g.passed) == ("propose-only", False)
    assert g.reason == ("research-song overrule while 1 predicted post-verdict title(s) are "
                        "placeholders (e.g. x-d1t3.mp3: no determinable title)")


# Include placeholder check (final2 "Declined to judge" bullet 2, operator ruling
# 2026-11-07): an include whose predicted title (the same verdict's set_title, else the
# file's cleaned tag when real) is a placeholder or undeterminable is propose-only on any
# verdict, not only one with a research-song overrule. With one, clause (b) of the
# placeholder veto already makes the verdict propose-only (tests above stay as they were).

def _inc_only(tag, *, meta=True):
    """`_inc_bundle` with no review flags: an include-only verdict then passes or fails on
    its edits alone."""
    b = _inc_bundle(tag, meta=meta)
    return dataclasses.replace(b, show=b.show.model_copy(
        update={"review_flags": [], "needs_review": False}))


@pytest.mark.parametrize("tag,meta,shown", [
    ("d1t03", True, "no determinable title"), ("Track 3", True, "'Track 3'"),
    ("27:36.27", True, "no determinable title"), ("", True, "no determinable title"),
    ("Dark Star", False, "no determinable title")],
    ids=["residue", "track-n", "timestamp", "blank", "no-metadata-row"])
def test_an_include_whose_predicted_title_is_a_placeholder_is_propose_only(tag, meta, shown):
    r = _ph_run(_inc_only(tag, meta=meta), [ed("include", "medium", file=INC)], flags=[])
    g = r.edits[0]
    assert (g.bar, g.passed) == ("propose-only", False)
    assert g.reason == f"include ships a placeholder title ({INC}: {shown})"
    assert r.vetoes == [] and r.auto is False


def test_an_include_with_a_real_tag_is_unaffected_by_the_include_check():
    r = _ph_run(_inc_only("Dark Star"), [ed("include", "medium", file=INC)], flags=[])
    assert (r.edits[0].bar, r.edits[0].passed, r.edits[0].reason) == ("short", True, "")
    assert r.vetoes == [] and r.auto is True


def test_an_include_of_a_residue_file_with_a_real_set_title_is_unaffected():
    r = _ph_run(_inc_only("d1t03"), [ed("include", "medium", file=INC),
                                     ed("set_title", file=INC, title="Dark Star",
                                        evidence=[ev(DESC, "3. Dark Star")])], flags=[])
    assert [(g.bar, g.passed) for g in r.edits] == [("short", True), ("title", True)]
    assert r.vetoes == [] and r.auto is True


def test_an_include_with_a_placeholder_set_title_is_propose_only():
    r = _ph_run(_inc_only("Dark Star"), [ed("include", "medium", file=INC),
                                         ed("set_title", file=INC, title="Track 3",
                                            evidence=[ev(DESC, "taper notes")])], flags=[])
    assert (r.edits[0].bar, r.edits[0].passed, r.edits[0].reason) == (
        "propose-only", False, f"include ships a placeholder title ({INC}: 'Track 3')")
    assert r.auto is False
