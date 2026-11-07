"""The adjudicator's target validation and policy gate (spec "The policy gate", "Before
judging", the auto-switch bar under "Recording pin"). Pure: every Bundle is built
directly, with no IO. Each boundary test is a pass/fail pair whose comment names the
boundary it pins (the Task 5 mutation pass relies on them)."""
from __future__ import annotations

import pytest

from llama.adjudicator.bundle import EVIDENCE_KINDS, Bundle, FileMeta, Row, escape_braces
from llama.adjudicator.gate import (LONG_BAR_KINDS, OVERRULE_BAR, REFUSED_INCLUDE_REASONS,
                                    STRUCTURE_KINDS, TAPER_SIDE_KINDS, TITLE_BAR_SOURCES,
                                    TITLE_WEAK_KINDS, EditGate, Facts, GateResult, evaluate,
                                    flag_passes, has_track_list_edit,
                                    has_track_list_or_structure_edit, is_filler_title, normalize,
                                    quote_ok, quote_rows, sibling_match, stem_in,
                                    validate_targets)
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
    sel = selection if selection is not None else {
        "identifier": CUR, "scores": {CUR: {"lineage": "aud", "kept_tracks": 10},
                                      SIB: {"lineage": "sbd", "kept_tracks": 12}}}
    text = "\n".join(r.text for k in EVIDENCE_KINDS for r in secs[k])
    return Bundle(slug="gd1973-06-10", show=show, overrides=overrides or Overrides(), view=None,
                  provenance=None, selection=sel, files=files or {}, sections=secs, text=text)


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
            gate.SIBLING_TOL_FRAC, gate.COVERAGE_ADDED_MAX_S) == (60.0, 120.0, 2.0, 0.01, 60.0)
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
    b = make_bundle([trk("x-d1t1.mp3")], flags=[flag], sections={
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
    # a judged flag that is not current, and a flag judged twice
    assert any("not a current flag" in r
               for r in reasons([ed("exclude", file=t1)], [judge(VENUE_FLAG), judge("bogus")]))
    assert any("judged twice" in r
               for r in reasons([ed("exclude", file=t1)], [judge(VENUE_FLAG), judge(VENUE_FLAG)]))
    # an unconsidered switch
    assert reasons([ed("switch_recording", identifier="nope")])


@pytest.mark.parametrize("ov", [Overrides(set_breaks=["gd73-06-10d1t01.mp3"]),
                                Overrides(encore_after="gd73-06-10d1t01.mp3"),
                                Overrides(titles={"gd73-06-10d1t01.mp3": "X"})])
def test_validate_rejects_exclude_of_a_keyed_file(ov):
    b = make_bundle(VB.show.tracks, overrides=ov, flags=[VENUE_FLAG])
    assert validate_targets(make_verdict([ed("exclude", file="gd73-06-10d1t01.mp3")],
                                         show=b.show), b)


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
    b = make_bundle([trk("x-d1t1.mp3")], flags=flags, sections={DESC: ["taper notes"]})
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
