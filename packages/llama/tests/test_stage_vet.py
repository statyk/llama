import json
from pathlib import Path

from herder import FakeProvider
from llama.models import Show, Track
from llama.stages.vet_research import normalize_date, run_vet_research
from llama.workspace import ShowWorkspace, read_model, write_artifact


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
    assert normalize_date("3/2") == "--03-02"
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
    # A chain with any unknown part counts as unknown; two of two unknown
    # assertions crosses the wrong-show threshold.
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json(
        asserted_songs=["Morning Dew > Werewolves of London", "Excitable Boy"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == [
        "research asserts unknown song: Morning Dew > Werewolves of London",
        "research asserts unknown song: Excitable Boy"]


def test_comma_in_title_matches_whole_before_splitting(tmp_path: Path):
    sws, show = setup(tmp_path)
    show.tracks.append(Track(index=4, set="encore", title="Baby, What You Want Me to Do",
                             filename="d.mp3", title_source="tags"))
    write_artifact(sws.show, show)
    fake = FakeProvider(completes=[vet_json(
        asserted_songs=["Baby, What You Want Me to Do"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == []


def test_mostly_unknown_songs_flag_needs_review(tmp_path: Path):
    # Wrong-show research: most assertions don't ground.
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json(
        asserted_songs=["Werewolves of London", "Excitable Boy", "Morning Dew"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == ["research asserts unknown song: Werewolves of London",
                            "research asserts unknown song: Excitable Boy"]
    saved = json.loads(sws.show.read_text())
    assert saved["needs_review"] is True
    assert saved["review_flags"] == result.flags


def test_single_stray_song_does_not_block(tmp_path: Path):
    # One unmatched title among grounded ones is a tracklist gap or variant,
    # not evidence of wrong-show research.
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json(
        asserted_songs=["Morning Dew", "Dark Star", "And We Bid You Goodnight"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == []
    assert json.loads(sws.show.read_text())["needs_review"] is False


def test_minority_unknowns_do_not_block(tmp_path: Path):
    # Two strays out of seven assertions: under a third, still no block.
    sws, show = setup(tmp_path)
    grounded = ["Morning Dew", "Dark Star", "Johnny B. Goode", "JBG", "Morning Dew!"]
    fake = FakeProvider(completes=[vet_json(
        asserted_songs=grounded + ["Jam", "Drums"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == []


def test_title_variants_match_by_containment(tmp_path: Path):
    sws, show = setup(tmp_path)
    show.tracks += [
        Track(index=4, set="2", title="Caution (Do Not Step on Tracks)",
              filename="d.mp3", title_source="tags"),
        Track(index=5, set="2", title="Weather Report Suite Prelude",
              filename="e.mp3", title_source="tags"),
        Track(index=6, set="2", title="Saturday Night",
              filename="f.mp3", title_source="tags"),
    ]
    write_artifact(sws.show, show)
    fake = FakeProvider(completes=[vet_json(asserted_songs=[
        "Caution",                    # assertion inside track title
        "Weather Report Suite",       # assertion is a prefix of the track
        "One More Saturday Night",    # track title inside the assertion
    ])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == []


def test_asserted_set_count_mismatch_flags(tmp_path: Path):
    # The steepcanyonrangers-2002-07-07 case: a mis-parsed description left the
    # structure single-set while research correctly reported two sets.
    sws, show = setup(tmp_path)
    show.tracks = [Track(index=1, set="1", title="Morning Dew",
                         filename="a.mp3", title_source="tags")]
    show.set_breaks = []
    write_artifact(sws.show, show)
    fake = FakeProvider(completes=[vet_json(asserted_songs=["Morning Dew"],
                                            asserted_set_count=2)])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == ["research asserts 2 sets but structure has 1"]
    assert json.loads(sws.show.read_text())["needs_review"] is True


def test_asserted_set_count_ignores_encore(tmp_path: Path):
    # Show has sets 1, 2, encore: "two sets" is correct, encore is not a set.
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json(asserted_set_count=2)])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == []


def test_absent_set_count_passes(tmp_path: Path):
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json(asserted_set_count=None)])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == []


def test_wrong_date_flags_unparseable_does_not(tmp_path: Path):
    sws, show = setup(tmp_path)
    fake = FakeProvider(completes=[vet_json(asserted_dates=["1977-05-08", "that legendary night"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == ["research asserts wrong date: 1977-05-08"]


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
    bad = vet_json(asserted_songs=["Werewolves of London", "Excitable Boy"])
    run_vet_research(sws, FakeProvider(completes=[bad]), show, "r")
    assert json.loads(sws.show.read_text())["needs_review"] is True
    sws.vetting.unlink()
    result = run_vet_research(sws, FakeProvider(completes=[vet_json()]), show, "r")
    assert result.flags == []
    saved = json.loads(sws.show.read_text())
    assert saved["needs_review"] is False
    assert not any(f.startswith("research asserts ") for f in saved["review_flags"])


def test_revet_does_not_duplicate_flags(tmp_path: Path):
    sws, show = setup(tmp_path)
    bad = vet_json(asserted_songs=["Werewolves of London", "Excitable Boy"])
    run_vet_research(sws, FakeProvider(completes=[bad]), show, "r")
    sws.vetting.unlink()
    result = run_vet_research(sws, FakeProvider(completes=[bad]), show, "r")
    assert result.flags == ["research asserts unknown song: Werewolves of London",
                            "research asserts unknown song: Excitable Boy"]
    saved = json.loads(sws.show.read_text())
    assert saved["review_flags"] == result.flags


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


def placeholder_show():
    s = make_show()
    s.performance_id = "CountryJoe/1976-01-01"
    s.date = "1976-01-01"
    return s


def cj_dates():
    return ["1976-02-08", "Sunday, February 8, 1976", "Feb 8, 1976",
            "February, 8th 1976"]


def test_placeholder_date_adopted_from_research(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.show, placeholder_show())
    fake = FakeProvider(completes=[vet_json(asserted_dates=cj_dates())])
    result = run_vet_research(sws, fake, placeholder_show(), "r")
    assert result.flags == []
    assert result.adopted_date == "1976-02-08"
    s = json.loads(sws.show.read_text())
    assert s["date"] == "1976-02-08"
    assert s["item_date"] == "1976-01-01"
    assert s["date_source"] == "research"
    assert s["needs_review"] is False


def test_adopted_revet_is_idempotent(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.show, placeholder_show())
    fake = FakeProvider(completes=[vet_json(asserted_dates=cj_dates()),
                                   vet_json(asserted_dates=cj_dates())])
    run_vet_research(sws, fake, placeholder_show(), "r")
    corrected = read_model(sws.show, Show)
    sws.vetting.unlink()  # force the re-vet
    result = run_vet_research(sws, fake, corrected, "r")
    assert result.flags == []
    assert result.adopted_date is None  # nothing left to adopt
    s = json.loads(sws.show.read_text())
    assert s["date"] == "1976-02-08" and s["date_source"] == "research"


def test_no_adoption_on_non_placeholder_date_dedups_flags(tmp_path: Path):
    sws, show = setup(tmp_path)  # date 1973-06-10 - not a placeholder
    fake = FakeProvider(completes=[vet_json(
        asserted_dates=["1973-07-27", "July 27, 1973", "Jul 27, 1973"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == ["research asserts wrong date: 1973-07-27"]
    assert result.adopted_date is None
    assert json.loads(sws.show.read_text())["date"] == "1973-06-10"


def test_no_adoption_on_conflicting_research_dates(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.show, placeholder_show())
    fake = FakeProvider(completes=[vet_json(
        asserted_dates=["1976-02-08", "1976-03-01"])])
    result = run_vet_research(sws, fake, placeholder_show(), "r")
    assert result.adopted_date is None
    assert sorted(result.flags) == [
        "research asserts 1976-02-08; item date 1976-01-01 looks like a year-only placeholder",
        "research asserts 1976-03-01; item date 1976-01-01 looks like a year-only placeholder",
    ]
    assert json.loads(sws.show.read_text())["date"] == "1976-01-01"


def test_no_adoption_on_yearless_contradiction(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.show, placeholder_show())
    fake = FakeProvider(completes=[vet_json(
        asserted_dates=["1976-02-08", "December 2"])])
    result = run_vet_research(sws, fake, placeholder_show(), "r")
    assert result.adopted_date is None
    assert ("research asserts 1976-02-08; item date 1976-01-01 looks like"
            " a year-only placeholder") in result.flags


def test_no_adoption_across_years(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.show, placeholder_show())
    fake = FakeProvider(completes=[vet_json(asserted_dates=["1977-02-08"])])
    result = run_vet_research(sws, fake, placeholder_show(), "r")
    assert result.adopted_date is None
    assert result.flags == [
        "research asserts 1977-02-08; item date 1976-01-01 looks like a year-only placeholder",
    ]


def test_adoption_does_not_swallow_set_count_mismatch(tmp_path: Path):
    # Date adoption resolves the date; an independent structure contradiction
    # must still hold the show.
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.show, placeholder_show())
    fake = FakeProvider(completes=[vet_json(asserted_dates=cj_dates(),
                                            asserted_set_count=4)])
    result = run_vet_research(sws, fake, placeholder_show(), "r")
    assert result.adopted_date == "1976-02-08"
    assert result.flags == ["research asserts 4 sets but structure has 2"]
    s = json.loads(sws.show.read_text())
    assert s["date"] == "1976-02-08" and s["needs_review"] is True


def test_no_adoption_when_songs_do_not_ground(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.show, placeholder_show())
    fake = FakeProvider(completes=[vet_json(
        asserted_songs=["Alien Song A", "Alien Song B", "Alien Song C"],
        asserted_dates=["1976-02-08"])])
    result = run_vet_research(sws, fake, placeholder_show(), "r")
    assert result.adopted_date is None
    assert ("research asserts 1976-02-08; item date 1976-01-01 looks like"
            " a year-only placeholder") in result.flags
    assert any("unknown song" in f for f in result.flags)
    assert json.loads(sws.show.read_text())["date"] == "1976-01-01"


def test_vet_does_not_adopt_over_manual_date(tmp_path):
    # A show whose date was manually overridden must not be re-dated by vet's
    # placeholder-adoption, even though it looks like a placeholder (YYYY-01-01):
    # adoption is gated on date_source == "item" (vet_research.py:124).
    ws = ShowWorkspace(tmp_path / "s")
    show = Show(performance_id="X/2003-01-01", identifier="x", artist="X",
                date="2003-01-01", date_source="override", item_date="2003-01-01",
                tracks=[Track(index=1, set="1", title="A", filename="a.mp3",
                              title_source="tags")])
    write_artifact(ws.show, show)
    # Same-year, unanimous alternate date - exactly the shape vet.py would
    # otherwise adopt over a genuine "item" placeholder.
    fake = FakeProvider(completes=[json.dumps({"asserted_dates": ["2003-03-15"]})])
    result = run_vet_research(ws, fake, show, "research text", force=True)
    assert result.adopted_date is None
    assert json.loads(ws.show.read_text())["date_source"] == "override"
    assert json.loads(ws.show.read_text())["date"] == "2003-01-01"
