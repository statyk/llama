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
    # Set sections follow show order; encore label renders as "Encore"
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
