from llama.models import Briefing, Show, Track
from llama.stages.brief import render_briefing_md


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
