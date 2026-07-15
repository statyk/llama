import json
from pathlib import Path

from llama.llm.fake import FakeProvider
from llama.models import Show, Track
from llama.stages.vet_research import normalize_date, run_vet_research
from llama.workspace import ShowWorkspace, write_artifact


def make_show():
    return Show(
        performance_id="GratefulDead/1973-06-10", identifier="gd73",
        artist="Grateful Dead", date="1973-06-10",
        tracks=[
            Track(index=1, set="1", title="Morning Dew", filename="a.mp3", title_source="tags"),
            Track(index=2, set="2", title="Dark Star", filename="b.mp3", title_source="tags"),
            Track(index=3, set="encore", title="Johnny B. Goode", filename="c.mp3", title_source="tags"),
        ],
        set_breaks=[1, 2],
    )


def vet_json(**overrides):
    d = {"asserted_songs": ["Morning Dew", "Dark Star"],
         "asserted_dates": ["1973-06-10", "June 10, 1973"],
         "context": "Peak 1973 tour"}
    d.update(overrides)
    return json.dumps(d)


def setup(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    return sws, show


def test_normalize_date_common_forms():
    assert normalize_date("1973-06-10") == "1973-06-10"
    assert normalize_date("1973-6-1") == "1973-06-01"
    assert normalize_date("6/10/73") == "1973-06-10"
    assert normalize_date("06/10/1973") == "1973-06-10"
    assert normalize_date("June 10, 1973") == "1973-06-10"
    assert normalize_date("Jun. 10th, 73") == "1973-06-10"
    assert normalize_date("10 June 1973") == "1973-06-10"
    assert normalize_date("the summer of '73") is None


def test_normalize_date_strips_leading_weekday():
    # Research prose loves the full form: "Sunday, December 7, 1969".
    assert normalize_date("Sunday, December 7, 1969") == "1969-12-07"
    assert normalize_date("Sun Dec 7, 1969") == "1969-12-07"
    assert normalize_date("Sunday, December 7") == "--12-07"


def test_normalize_date_yearless_forms():
    # Research prose often names the date without a year ("on December 2 the
    # band..."); normalize to the ISO 8601 year-less form for comparison.
    assert normalize_date("December 2") == "--12-02"
    assert normalize_date("June 10th") == "--06-10"
    assert normalize_date("2 December") == "--12-02"
    assert normalize_date("not a date") is None


def test_yearless_date_matching_show_passes(tmp_path: Path):
    sws, show = setup(tmp_path)  # show date 1973-06-10
    fake = FakeProvider(completes=[vet_json(asserted_dates=["June 10"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == []


def test_yearless_date_mismatch_flags_wrong_date(tmp_path: Path):
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json(asserted_dates=["December 2"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == ["research asserts wrong date: December 2"]


def test_clean_research_passes_and_writes_vetting(tmp_path: Path):
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json()])
    result = run_vet_research(sws, fake, show, "## Reputation\nLegendary.")
    assert result.flags == []
    assert result.vetting.context == "Peak 1973 tour"
    assert sws.vetting.exists()
    assert json.loads(sws.show.read_text())["needs_review"] is False


def test_alias_matching_uses_normalize_song(tmp_path: Path):
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json(asserted_songs=["JBG", "Morning Dew!"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == []


def test_segue_chains_match_partwise(tmp_path: Path):
    # Research prose uses standard notation: "A > B", comma-joined closers,
    # aliases inside chains. Every part is a known track here - no flags.
    sws, show = setup(tmp_path)
    chains = ["Morning Dew > Dark Star",
              "Dark Star > Johnny B. Goode, Morning Dew",
              "JBG > Morning Dew"]
    fake = FakeProvider(completes=[vet_json(asserted_songs=chains)])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == []


def test_segue_chain_with_unknown_part_still_flags(tmp_path: Path):
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json(
        asserted_songs=["Morning Dew > Werewolves of London"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == [
        "research asserts unknown song: Morning Dew > Werewolves of London"]


def test_comma_in_title_matches_whole_before_splitting(tmp_path: Path):
    sws, show = setup(tmp_path)
    show.tracks.append(Track(index=4, set="encore", title="Baby, What You Want Me to Do",
                             filename="d.mp3", title_source="tags"))
    write_artifact(sws.show, show)
    fake = FakeProvider(completes=[vet_json(
        asserted_songs=["Baby, What You Want Me to Do"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == []


def test_unknown_song_flags_needs_review(tmp_path: Path):
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json(asserted_songs=["Werewolves of London"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == ["research asserts unknown song: Werewolves of London"]
    saved = json.loads(sws.show.read_text())
    assert saved["needs_review"] is True
    assert saved["review_flags"] == result.flags


def test_wrong_and_unparseable_dates_flag(tmp_path: Path):
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json(asserted_dates=["1977-05-08", "that legendary night"])])
    result = run_vet_research(sws, fake, show, "r")
    assert "research asserts wrong date: 1977-05-08" in result.flags
    assert "research asserts unparseable date: that legendary night" in result.flags


def test_skips_when_vetting_exists(tmp_path: Path):
    sws, show = setup(tmp_path)
    run_vet_research(sws, FakeProvider(completes=[vet_json()]), show, "r")
    cached = run_vet_research(sws, FakeProvider(), show, "r")  # empty queue: any call would raise
    assert cached.vetting.context == "Peak 1973 tour"


def test_revet_after_artifact_delete_leaves_research_alone(tmp_path: Path):
    sws, show = setup(tmp_path)
    write_artifact(sws.research, "original research")
    run_vet_research(sws, FakeProvider(completes=[vet_json()]), show, "original research")
    sws.vetting.unlink()
    run_vet_research(sws, FakeProvider(completes=[vet_json()]), show, "original research")
    assert sws.research.read_text() == "original research"


def test_clean_revet_clears_vet_flags(tmp_path: Path):
    sws, show = setup(tmp_path)
    run_vet_research(sws, FakeProvider(completes=[vet_json(asserted_songs=["Werewolves of London"])]),
                     show, "r")
    assert json.loads(sws.show.read_text())["needs_review"] is True
    sws.vetting.unlink()
    result = run_vet_research(sws, FakeProvider(completes=[vet_json()]), show, "r")
    assert result.flags == []
    saved = json.loads(sws.show.read_text())
    assert saved["needs_review"] is False
    assert not any(f.startswith("research asserts ") for f in saved["review_flags"])


def test_revet_does_not_duplicate_flags(tmp_path: Path):
    sws, show = setup(tmp_path)
    bad = vet_json(asserted_songs=["Werewolves of London"])
    run_vet_research(sws, FakeProvider(completes=[bad]), show, "r")
    sws.vetting.unlink()
    result = run_vet_research(sws, FakeProvider(completes=[bad]), show, "r")
    assert result.flags == ["research asserts unknown song: Werewolves of London"]
    saved = json.loads(sws.show.read_text())
    assert saved["review_flags"] == ["research asserts unknown song: Werewolves of London"]


def test_clean_revet_preserves_non_vet_flags(tmp_path: Path):
    sws, show = setup(tmp_path)
    show.review_flags = ["duration mismatch on 01.mp3"]
    show.needs_review = True
    write_artifact(sws.show, show)
    result = run_vet_research(sws, FakeProvider(completes=[vet_json()]), show, "r")
    assert result.flags == []
    saved = json.loads(sws.show.read_text())
    assert saved["review_flags"] == ["duration mismatch on 01.mp3"]
    assert saved["needs_review"] is True
