from llama.models import Briefing, Show, Track
from llama.stages.brief import generate_briefing, render_briefing_md


def _show(sets=("1", "2"), encore=True) -> Show:
    tracks, idx = [], 1
    for s in sets:
        tracks.append(Track(index=idx, set=s, title=f"Song {idx}", filename=f"t{idx}.mp3",
                            title_source="tags"))
        idx += 1
    if encore:
        tracks.append(Track(index=idx, set="encore", title=f"Song {idx}",
                            filename=f"t{idx}.mp3", title_source="tags"))
    return Show(performance_id="GratefulDead/1973-06-10", identifier="gd73",
                artist="Grateful Dead", date="1973-06-10", venue="RFK Stadium",
                tracks=tracks)


def _briefing(**kw) -> Briefing:
    base = dict(context="Peak-era Dead on the summer '73 run.",
                significance="A standout show from a strong year.",
                per_set={"1": ["Opens hot"], "2": ["The big jam"]},
                notable_moments=["A monster Dark Star"],
                review_sentiment="Widely praised, including by non-attendees.",
                non_attendee_sentiment=True,
                cautions=["research is thin"],
                mentioned_songs=[])
    base.update(kw)
    return Briefing(**base)


def test_briefing_defaults():
    b = _briefing()
    assert b.narration == "full"
    assert b.mentioned_songs == []


def test_render_briefing_md_sections_and_determinism():
    b, show = _briefing(), _show()
    md = render_briefing_md(b, show)
    assert md == render_briefing_md(b, show)  # pure function
    assert md.startswith("# Briefing: Grateful Dead — 1973-06-10, RFK Stadium")
    for heading in ["## Context", "## Why this show", "## Set 1", "## Set 2",
                    "## Notable moments", "## Reception",
                    "## Cautions for the scriptwriter"]:
        assert heading in md
    assert "- Opens hot" in md and "- research is thin" in md
    # Set sections are sorted with encore last; encore label renders as "Encore"
    b2 = _briefing(per_set={"1": ["a"], "encore": ["short sweet closer"]})
    md2 = render_briefing_md(b2, _show())
    assert "## Encore" in md2
    assert md2.index("## Set 1") < md2.index("## Encore")


def test_render_briefing_md_omits_empty_optional_sections():
    b = _briefing(notable_moments=[], cautions=[], per_set={})
    md = render_briefing_md(b, _show())
    assert "## Notable moments" not in md
    assert "## Cautions" not in md
    assert "## Set" not in md


from llama.stages.brief import briefing_guard


def test_guard_passes_clean_full_briefing():
    assert briefing_guard(_briefing(), _show()) == []


def test_guard_flags_unknown_song():
    b = _briefing(mentioned_songs=["Song 1", "Not A Real Song"])
    problems = briefing_guard(b, _show())
    assert problems == ["briefing mentions unknown song: Not A Real Song"]


def test_guard_flags_bogus_set_key_but_allows_encore():
    b = _briefing(per_set={"1": ["a"], "2": ["b"], "3": ["nope"], "encore": ["ok"]})
    assert briefing_guard(b, _show()) == ["briefing references nonexistent set: 3"]


def test_guard_flags_wrong_set_count_claim_in_prose():
    b = _briefing(significance="They played three sets that night.")
    assert briefing_guard(b, _show()) == [
        "briefing claims 3 sets but structure has 2"]
    b2 = _briefing(notable_moments=["The fourth set closed with fireworks."])
    assert briefing_guard(b2, _show()) == [
        "briefing mentions the fourth set but structure has 2 sets"]


def test_guard_accepts_correct_set_count_claim():
    assert briefing_guard(_briefing(context="Both sets stretch out."), _show()) == []


def test_guard_vague_mode_violations():
    b = _briefing(narration="vague", per_set={"1": ["a"]}, mentioned_songs=["Song 1"])
    problems = briefing_guard(b, _show())
    assert "briefing has per-set talking points under vague narration" in problems
    assert "briefing names songs under vague narration" in problems
    # a set-count claim is a violation under vague even when numerically right
    b2 = _briefing(narration="vague", per_set={}, mentioned_songs=[],
                   context="They played two sets.")
    assert briefing_guard(b2, _show()) == [
        "briefing asserts set structure under vague narration"]


def test_guard_vague_mode_clean():
    b = _briefing(narration="vague", per_set={}, mentioned_songs=[],
                  context="A revered night from the '73 run.")
    assert briefing_guard(b, _show()) == []


def test_guard_flags_empty_per_set_under_full():
    b = _briefing(per_set={})
    assert briefing_guard(b, _show()) == ["briefing has no per-set talking points"]


import json

from herder.fake import FakeProvider
from llama.models import Overrides, VettingResult, ResearchVetting
from llama.stages.brief import run_brief, vetting_summary
from llama.workspace import ShowWorkspace, write_artifact

GOOD_BRIEFING = json.dumps({
    "context": "Peak-era Dead on the summer '73 run.",
    "significance": "A standout show from a strong year.",
    "per_set": {"1": ["Opens hot"], "2": ["The big jam"]},
    "notable_moments": [], "review_sentiment": "Praised.",
    "non_attendee_sentiment": True, "cautions": [],
    "narration": "full", "mentioned_songs": []})

BAD_BRIEFING = json.dumps({
    "context": "", "significance": "They played three sets.",
    "per_set": {"1": ["a"], "2": ["b"]}, "notable_moments": [],
    "review_sentiment": "", "non_attendee_sentiment": False, "cautions": [],
    "narration": "full", "mentioned_songs": []})


def _ws(tmp_path, show) -> ShowWorkspace:
    ws = ShowWorkspace(tmp_path / "show")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.show, show)
    return ws


def test_run_brief_writes_artifacts_and_stamps_narration(tmp_path):
    show = _show()
    ws = _ws(tmp_path, show)
    provider = FakeProvider(completes=[GOOD_BRIEFING])
    b = run_brief(ws, provider, show, "research text", [], force=False)
    assert ws.briefing_json.exists() and ws.briefing_md.exists()
    assert b.narration == "full"
    assert "## Context" in ws.briefing_md.read_text()
    # the prompt carried the inputs
    prompt = provider.calls[0][1]
    assert "research text" in prompt and "RFK Stadium" in prompt


def test_run_brief_skips_when_artifact_exists(tmp_path):
    show = _show()
    ws = _ws(tmp_path, show)
    run_brief(ws, FakeProvider(completes=[GOOD_BRIEFING]), show, "", [], force=False)
    # no queued responses: a second call must not hit the provider
    again = run_brief(ws, FakeProvider(completes=[]), show, "", [], force=False)
    assert again.context == "Peak-era Dead on the summer '73 run."


def test_run_brief_self_heals_missing_briefing_md(tmp_path):
    show = _show()
    ws = _ws(tmp_path, show)
    run_brief(ws, FakeProvider(completes=[GOOD_BRIEFING]), show, "", [], force=False)
    ws.briefing_md.unlink()
    assert not ws.briefing_md.exists()
    # no queued responses: re-rendering briefing.md must not hit the provider
    b = run_brief(ws, FakeProvider(completes=[]), show, "", [], force=False)
    assert ws.briefing_md.exists()
    assert "## Context" in ws.briefing_md.read_text()
    assert b.context == "Peak-era Dead on the summer '73 run."


def test_run_brief_narration_stamp_overrides_llm_value(tmp_path):
    show = _show()
    ws = _ws(tmp_path, show)
    write_artifact(ws.overrides, Overrides(narration="vague"))
    vague_ok = json.dumps({"context": "A revered night.", "significance": "Legendary.",
                           "per_set": {}, "notable_moments": [],
                           "review_sentiment": "Praised.", "non_attendee_sentiment": True,
                           "cautions": [], "narration": "full", "mentioned_songs": []})
    b = run_brief(ws, FakeProvider(completes=[vague_ok]), show, "", [], force=False)
    assert b.narration == "vague"          # stamped from overrides, LLM said "full"
    assert json.loads(ws.briefing_json.read_text())["narration"] == "vague"


def test_run_brief_retries_with_feedback_then_holds(tmp_path):
    from llama.models import Show
    show = _show()
    ws = _ws(tmp_path, show)
    provider = FakeProvider(completes=[BAD_BRIEFING, BAD_BRIEFING])
    run_brief(ws, provider, show, "", [], force=False)
    assert len(provider.calls) == 2
    assert "failed fact-checking" in provider.calls[1][1]
    held = Show.model_validate_json(ws.show.read_text())
    assert held.needs_review is True
    assert any("briefing claims 3 sets" in f for f in held.review_flags)
    assert ws.briefing_json.exists()       # artifacts still written when held


def test_run_brief_recovers_on_retry(tmp_path):
    from llama.models import Show
    show = _show()
    ws = _ws(tmp_path, show)
    provider = FakeProvider(completes=[BAD_BRIEFING, GOOD_BRIEFING])
    run_brief(ws, provider, show, "", [], force=False)
    assert Show.model_validate_json(ws.show.read_text()).needs_review is False


def test_run_brief_vague_narration_retries_when_llm_fills_per_set(tmp_path):
    # The prompt tells the model to leave per_set empty under vague narration;
    # this covers what happens when it doesn't comply on the first attempt.
    show = _show()
    ws = _ws(tmp_path, show)
    write_artifact(ws.overrides, Overrides(narration="vague"))
    non_compliant = json.dumps({
        "context": "A revered night.", "significance": "Legendary.",
        "per_set": {"1": ["Opens hot"]}, "notable_moments": [],
        "review_sentiment": "Praised.", "non_attendee_sentiment": True,
        "cautions": [], "narration": "full", "mentioned_songs": []})
    compliant = json.dumps({
        "context": "A revered night.", "significance": "Legendary.",
        "per_set": {}, "notable_moments": [],
        "review_sentiment": "Praised.", "non_attendee_sentiment": True,
        "cautions": [], "narration": "full", "mentioned_songs": []})
    provider = FakeProvider(completes=[non_compliant, compliant])
    b = run_brief(ws, provider, show, "", [], force=False)
    assert len(provider.calls) == 2
    assert "per-set talking points under vague narration" in provider.calls[1][1]
    assert b.per_set == {}


def test_vetting_summary(tmp_path):
    ws = _ws(tmp_path, _show())
    assert vetting_summary(ws) == "(no vetting data)"
    write_artifact(ws.vetting, VettingResult(
        vetting=ResearchVetting(context="Summer '73 stadium run."),
        flags=["research asserts a song not in the show"],
        adopted_date="1973-06-10"))
    text = vetting_summary(ws)
    assert "research asserts a song not in the show" in text
    assert "1973-06-10" in text and "Summer '73 stadium run." in text


# --- slice 3 (spec "Slice 3 — Briefing guard") ---

import pytest

from llama.songs import normalize_song
from llama.stages.brief import briefing_guard, known_song, normalize_briefing, song_components
from llama.workspace import read_model


def test_3a_empty_sets_are_dropped_and_the_guard_never_sees_them():
    b = _briefing(per_set={"1": ["a"], "2": ["b"], "encore": []})
    assert briefing_guard(b, _show(encore=False)) == ["briefing references nonexistent set: encore"]  # today's reading, pre-normalisation
    n = normalize_briefing(b)
    assert n.per_set == {"1": ["a"], "2": ["b"]}
    assert briefing_guard(n, _show(encore=False)) == []
    assert "## Encore" not in render_briefing_md(n, _show(encore=False))


def test_3a_normalize_leaves_everything_else_byte_identical():
    b = _briefing(per_set={"1": ["a"], "2": [], "encore": ["c"]}, mentioned_songs=["Song 1"])
    n = normalize_briefing(b)
    assert n.per_set == {"1": ["a"], "encore": ["c"]}
    assert n.model_dump(exclude={"per_set"}) == b.model_dump(exclude={"per_set"})
    assert b.per_set == {"1": ["a"], "2": [], "encore": ["c"]}     # a copy: the input is untouched
    assert normalize_briefing(n) == n
    # an empty per_set dict stays empty: no talking points at all is still a problem
    assert briefing_guard(normalize_briefing(_briefing(per_set={})), _show()) == [
        "briefing has no per-set talking points"]


def test_run_brief_normalises_before_the_guard_and_the_writes(tmp_path):
    show = _show(encore=False)
    ws = _ws(tmp_path, show)
    with_empty_encore = json.dumps({**json.loads(GOOD_BRIEFING), "per_set": {"1": ["a"], "2": ["b"], "encore": []}})
    run_brief(ws, FakeProvider(completes=[with_empty_encore]), show, "r", [])
    assert read_model(ws.show, Show).needs_review is False
    assert "encore" not in json.loads(ws.briefing_json.read_text())["per_set"]
    assert "## Encore" not in ws.briefing_md.read_text()


@pytest.mark.parametrize("song, titles, known", [
    ("E1: Ripple", ["Ripple"], True),
    ("Encore: Ripple", ["Ripple"], True),
    ("1979 (Kerry Brown on drums)", ["1979"], True),
    ("Storms (fades in)", ["Storms"], True),
    ("Drums > Space", ["Drums", "Space"], True),
    ("Drums > Space", ["Drums > Space"], True),
    ("Drums", ["Drums > Space"], True),               # a merged track's component is a known title
    ("Scarlet Begonias", ["Scarlet Begonias > Fire on the Mountain"], True),
    ("Fire", ["Scarlet Begonias > Fire on the Mountain"], False),   # no subphrase matching
    ("Ripple", ["Ripple (reprise)"], True),
    ("44 Blues", ["Ripple"], False),
    ("Dark Star", ["Dark Star Jam"], False),          # no loosely_same_title
    ("Drums > Nope", ["Drums"], False),               # EVERY component must be known, not any
])
def test_3b_tolerant_matching_narrowly(song, titles, known):
    exact = {normalize_song(t) for t in titles}
    comps = exact | {c for t in titles for c in song_components(t)} | {" ".join(song_components(t)) for t in titles}
    assert known_song(song, exact, comps) is known


def test_3b_is_a_superset_of_todays_matcher():
    # every pair today's exact test accepts, the new one accepts
    titles = ["Ripple", "Drums > Space", "E: Casey Jones", "1979 (live)", "Me & My Uncle"]
    exact = {normalize_song(t) for t in titles}
    comps = exact | {c for t in titles for c in song_components(t)} | {" ".join(song_components(t)) for t in titles}
    for t in titles:
        assert normalize_song(t) in exact
        assert known_song(t, exact, comps)


@pytest.mark.parametrize("prose, claims, ordinals", [
    ("two electric sets tonight", set(), {}),
    ("two excellent sets", {2}, {}),
    ("two sets that night", {2}, {}),
    ("two night sets", set(), {}),
    ("there is no second set", set(), {}),
    ("not three sets but two", set(), {}),          # "three sets" negated; "but two" is not followed by "sets"
    ("instead of the usual two sets", set(), {}),
    ("expected two sets", set(), {}),
    ("without the second set", set(), {}),
    ("two sets each night of the run", set(), {}),
    ("two sets a night", set(), {}),
    ("two sets per weekend", set(), {}),
    ("the second of Panic's two weekend sets", set(), {}),   # "second of" is not "second set"; the count is qualified
    ("two hard-hitting sets", set(), {}),                     # no match today, none now: the word stays \w+
    ("the band played both sets", {2}, {}),
    ("two sets of fiddle tunes", set(), {}),
    ("a monster second set", set(), {2: "second"}),
    # fix round 1: a negation word qualifies only its own clause, never an earlier one
    ("The band did not disappoint. Second set opened hot.", set(), {2: "second"}),
    ("Fans could not complain: two sets and an encore.", {2}, {}),
    ("As expected, the second set was a monster.", set(), {2: "second"}),
])
def test_3c_set_count_claims(prose, claims, ordinals):
    from llama.stages.brief import _claim_counts
    assert _claim_counts(prose) == (claims, ordinals)


def test_3c_leaves_the_vague_branch_on_todays_regexes():
    show = _show(encore=False)
    # under full narration 3c drops this qualified count; under vague today's regex still catches it
    b = _briefing(per_set={}, narration="vague", context="the band played two electric sets")
    assert "briefing asserts set structure under vague narration" in briefing_guard(b, show)
    # ... and a negated ordinal, which 3c drops under full narration, still counts under vague
    b2 = _briefing(per_set={}, narration="vague", context="there is no second set")
    assert briefing_guard(b2, show) == ["briefing asserts set structure under vague narration"]


def test_3c_negation_does_not_cross_a_briefing_field_boundary():
    from llama.stages.brief import _claim_counts, _guard_prose
    b = _briefing(context="Was it the best night of the run? Probably not", significance="",
                  review_sentiment="", notable_moments=[],
                  per_set={"1": ["Second set: opened hot."]})
    assert _claim_counts(_guard_prose(b)) == (set(), {2: "second"})
    assert briefing_guard(b, _show(sets=("1",), encore=False)) == [
        "briefing mentions the second set but structure has 1 sets"]


def test_3c_scope_window_does_not_cross_a_briefing_field_boundary():
    from llama.stages.brief import _claim_counts
    # a claim ending one field is NOT scoped by the next field opening "A night ..."
    assert _claim_counts("The band played two sets\nA night to remember") == ({2}, {})
    # the same words on one line are still scoped below the show
    assert _claim_counts("The band played two sets a night to remember") == (set(), {})


def test_set_count_of_lookahead_stops_at_the_field_boundary_full():
    from llama.stages.brief import _claim_counts
    assert _claim_counts("The band played two sets\nOf note, the encore was long") == ({2}, {})
    assert _claim_counts("two sets of fiddle tunes") == (set(), {})


def test_set_count_of_lookahead_stops_at_the_field_boundary_vague():
    show = _show(encore=False)
    b = _briefing(per_set={}, narration="vague", context="The band played two sets",
                  significance="Of note, the encore was long")
    assert briefing_guard(b, show) == ["briefing asserts set structure under vague narration"]
    b2 = _briefing(per_set={}, narration="vague", context="two sets of fiddle tunes")
    assert briefing_guard(b2, show) == []


def test_set_count_of_lookahead_end_to_end_full_narration():
    show = _show(sets=("1", "2", "3"), encore=False)
    b = _briefing(per_set={"1": ["Opens hot"]}, context="The band played two sets",
                  significance="Of note, the encore was long")
    assert "briefing claims 2 sets but structure has 3" in briefing_guard(b, show)


def test_guard_prose_field_marker_leaves_todays_matches_unchanged():
    # the field boundary is a newline, which today's `\s+` spans exactly as it
    # spanned the old single space: same matches, same spans, same vague verdict
    # (except the `of` lookahead, which stops at the newline: fw4)
    import re as _re
    from llama.stages.brief import _ORDINAL_SET, _SET_COUNT_CLAIM, _guard_prose
    b = _briefing(context="they played two", significance="sets that night, and the",
                  review_sentiment="second", notable_moments=["set was long"],
                  per_set={"1": ["both"], "2": ["electric sets of tunes"]})
    old = " ".join([b.context, b.significance, b.review_sentiment, *b.notable_moments,
                    *(p for pts in b.per_set.values() for p in pts)])
    new = _guard_prose(b)
    assert len(new) == len(old)
    for rx in (_SET_COUNT_CLAIM, _ORDINAL_SET):
        assert [(m.span(), m.group(0).split()) for m in rx.finditer(new)] == \
            [(m.span(), m.group(0).split()) for m in rx.finditer(old)] != []
    vague = b.model_copy(update={"narration": "vague", "per_set": {}, "mentioned_songs": []})
    assert briefing_guard(vague, _show()) == ["briefing asserts set structure under vague narration"]


def test_3b_3c_wired_into_the_full_branch():
    show = Show(performance_id="GratefulDead/1973-06-10", identifier="gd73",
                artist="Grateful Dead", date="1973-06-10",
                tracks=[Track(index=1, set="1", title="Drums > Space", filename="a.mp3",
                              title_source="tags"),
                        Track(index=2, set="2", title="E: Ripple", filename="b.mp3",
                              title_source="tags")])
    b = _briefing(mentioned_songs=["Drums", "Encore: Ripple", "Fire"],
                  context="They played three electric sets, not a fourth set.")
    assert briefing_guard(b, show) == ["briefing mentions unknown song: Fire"]


def test_generate_briefing_returns_the_normalised_briefing_and_problems_without_writing(tmp_path):
    show = _show()
    ok = json.dumps(dict(context="c", significance="s", per_set={"1": ["a"], "2": ["b"], "encore": []},
                         mentioned_songs=[]))
    b, problems = generate_briefing(FakeProvider([ok]), show, "r", [], narration="full", vetting=None)
    assert problems == [] and b.per_set == {"1": ["a"], "2": ["b"]} and b.narration == "full"
    bad = json.dumps(dict(context="c", significance="s", per_set={"1": ["a"], "2": ["b"]},
                          mentioned_songs=["Nope"]))
    b, problems = generate_briefing(FakeProvider([bad, bad]), show, "r", [], narration="full", vetting=None)
    assert problems == ["briefing mentions unknown song: Nope"]


# fw5: comma-merged track titles contribute their parts to the known-song set
from llama.stages.brief import song_comma_components

_MERGED = "Stay With Me (tease), Girl Named Sandoz (tease), Happy Birthday (tease)"


def _merged_show(title=_MERGED) -> Show:
    show = _show(sets=("1",), encore=False)
    show.tracks[0].title = title
    return show


def test_comma_merged_title_parts_are_known_songs():
    b = _briefing(per_set={"1": ["x"]},
                  mentioned_songs=["Girl Named Sandoz", "Stay With Me", "Happy Birthday"])
    assert briefing_guard(b, _merged_show()) == []


def test_song_in_no_title_is_still_flagged_with_merged_title():
    b = _briefing(per_set={"1": ["x"]}, mentioned_songs=["Mayonaise"])
    assert briefing_guard(b, _merged_show()) == ["briefing mentions unknown song: Mayonaise"]


def test_commas_inside_parentheses_never_split():
    title = "Jam (w/ Bob Weir, Phil Lesh)"
    assert song_comma_components(title) == []
    b = _briefing(per_set={"1": ["x"]}, mentioned_songs=["Phil Lesh"])
    assert briefing_guard(b, _merged_show(title)) == ["briefing mentions unknown song: Phil Lesh"]


def test_single_part_title_has_no_comma_components():
    assert song_comma_components("Ripple (reprise)") == []
    assert song_comma_components("Ripple,") == []


def test_unannotated_comma_titles_never_split():
    assert song_comma_components("Talk To Me Devil, Again") == []
    assert song_comma_components("Lawyers, Guns and Money (Warren Zevon)") == []
    b = _briefing(per_set={"1": ["x"]}, mentioned_songs=["Again"])
    assert briefing_guard(b, _merged_show("Talk To Me Devil, Again")) == [
        "briefing mentions unknown song: Again"]
