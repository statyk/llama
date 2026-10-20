import json
from pathlib import Path

import pytest

from herder import FakeProvider
from llama.models import ResearchVetting, Show, ShowNotes, Track, VettingResult
from llama.stages.vet_research import (
    RIGHT_SHOW_MIN_ASSERTED,
    RIGHT_SHOW_MIN_TAPE_FRACTION,
    VetOutcome,
    apply_vet,
    day_unknown_date,
    grounding_flags,
    normalize_date,
    right_show_gate,
    run_vet_research,
)
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


def test_apply_vet_is_pure_and_replaces_only_its_own_flags():
    show = make_show().model_copy(update={"review_flags": ["unresolved track titles",
                                                           "research asserts wrong date: 1970-01-01"],
                                          "needs_review": True})
    out = apply_vet(ResearchVetting(asserted_songs=["Morning Dew", "Dark Star"],
                                    asserted_dates=["1973-06-10"]), show)
    assert isinstance(out, VetOutcome)
    assert out.show.review_flags == ["unresolved track titles"]
    assert out.show.needs_review is True
    assert show.review_flags[1].startswith("research asserts")        # input untouched
    assert out.result.flags == [] and out.result.adopted_date is None
    assert out.notes == []


def test_apply_vet_adopts_a_placeholder_date_on_the_copy():
    show = make_show().model_copy(update={"date": "1973-01-01"})
    out = apply_vet(ResearchVetting(asserted_songs=["Morning Dew", "Dark Star"],
                                    asserted_dates=["1973-06-10"]), show)
    assert (out.show.date, out.show.item_date, out.show.date_source) == ("1973-06-10", "1973-01-01", "research")
    assert out.result.adopted_date == "1973-06-10"
    assert show.date == "1973-01-01"


def test_run_vet_research_writes_vet_notes_into_notes_json(tmp_path):
    sws, show = setup(tmp_path)
    write_artifact(sws.notes, ShowNotes(gather=["g"], vet=["stale"]))
    run_vet_research(sws, FakeProvider([vet_json()]), show, "research")
    assert read_model(sws.notes, ShowNotes) == ShowNotes(gather=["g"], vet=[])


# --- slice 4c/4b (spec "Slice 4") ---

@pytest.mark.parametrize("text, expected", [
    ("16/11/08", "2008-11-16"),          # month-first invalid, day-first valid: day-first
    ("11/16/08", "2008-11-16"),          # month-first valid stays month-first
    ("10/11/08", "2008-10-11"),          # both valid: month-first wins, not swapped
    ("13/13/08", None), ("2008-13-01", None), ("2008-00-10", None), ("June 32, 1973", None),
    ("0/5/08", None), ("31/4", "--04-31"),
])
def test_4c_normalize_date_ranges(text, expected):
    assert normalize_date(text) == expected


def _vet(dates, songs=("Morning Dew", "Dark Star")):
    return ResearchVetting(asserted_songs=list(songs), asserted_dates=list(dates))


def test_4b_adjacent_day_is_context_when_the_own_full_date_is_asserted():
    flags, _, _ = grounding_flags(_vet(["June 10, 1973", "1973-06-11"]), make_show())
    assert not any("wrong date" in f for f in flags)
    flags, _, _ = grounding_flags(_vet(["1973-06-10", "1973-06-09"]), make_show())
    assert not any("wrong date" in f for f in flags)


def test_4b_two_days_off_still_flags():
    flags, _, _ = grounding_flags(_vet(["1973-06-10", "1973-06-12"]), make_show())
    assert flags == ["research asserts wrong date: 1973-06-12"]


def test_4b_without_the_own_date_an_adjacent_date_still_flags():
    flags, _, _ = grounding_flags(_vet(["1973-06-11"]), make_show())
    assert flags == ["research asserts wrong date: 1973-06-11"]


def test_yearless_own_date_does_not_make_a_far_date_context():
    # Review Focus 5: "June 10" is not the own FULL date, so 1973-06-12 is not context.
    flags, _, _ = grounding_flags(_vet(["June 10", "1973-06-12"]), make_show())
    assert "research asserts wrong date: 1973-06-12" in flags


def test_4b_leaves_placeholder_adoption_unchanged():
    show = make_show().model_copy(update={"date": "1973-01-01"})
    flags, adopted, _ = grounding_flags(_vet(["1973-06-10"]), show)
    assert adopted == "1973-06-10" and flags == []


def test_run_vet_research_writes_vetting_json_last(tmp_path: Path, monkeypatch):
    # vetting.json is the stage's done-marker: a crash before it must re-run the stage.
    import llama.stages.vet_research as vr
    sws, show = setup(tmp_path)
    order = []
    real = vr.write_artifact
    monkeypatch.setattr(vr, "write_artifact", lambda path, obj: (order.append(path), real(path, obj))[1])
    run_vet_research(sws, FakeProvider(completes=[vet_json()]), show, "r")
    assert order == [sws.show, sws.notes, sws.vetting]


def test_4b_raw_date_flags_keep_what_the_window_hides_and_yearless_mismatches():
    from llama.stages.vet_research import _date_flags
    show = make_show()
    mismatched = {"1973-06-11": "1973-06-11"}
    yearless = {"--06-12": "June 12"}
    raw = _date_flags(mismatched, yearless, show, False, None)
    assert raw == ["research asserts wrong date: 1973-06-11", "research asserts wrong date: June 12"]
    assert _date_flags({}, yearless, show, False, None) == ["research asserts wrong date: June 12"]
    ph = _date_flags({"1973-06-11": "x"}, {}, show, True, None)
    assert ph == ["research asserts 1973-06-11; item date 1973-06-10 looks like a year-only placeholder"]
    assert _date_flags(mismatched, yearless, show, True, "1973-06-11") == []
    # end to end: the window hides the adjacent date but the yearless mismatch still flags
    flags, _, _ = grounding_flags(_vet(["1973-06-10", "1973-06-11", "June 12"]), show)
    assert flags == ["research asserts wrong date: June 12"]


# --- slice 4a (spec "Slice 4 — 4a") ---


def _tape(n_titled, n_unresolved=0, sources="tags"):
    tracks = [Track(index=i, set="1", title=f"Song {i}", filename=f"{i}.mp3", title_source=sources)
              for i in range(1, n_titled + 1)]
    tracks += [Track(index=i, set="1", title=f"{i}.mp3", filename=f"{i}.mp3", title_source="unresolved")
               for i in range(n_titled + 1, n_titled + n_unresolved + 1)]
    return make_show().model_copy(update={"tracks": tracks})


def test_constants_are_the_spec_values():
    assert RIGHT_SHOW_MIN_TAPE_FRACTION == 0.5 and RIGHT_SHOW_MIN_ASSERTED == 4


def test_4a_suppresses_unknown_songs_on_a_right_show_tape_and_notes_them():
    show = _tape(8)
    vet = ResearchVetting(asserted_songs=[f"Song {i}" for i in range(1, 6)] + ["Alpha", "Beta", "Gamma"],
                          asserted_dates=["June 10, 1973"])
    flags, _, notes = grounding_flags(vet, show)
    assert not any("unknown song" in f for f in flags)
    assert notes == ["unknown-song flags suppressed by the right-show gate: 5/8 tape tracks asserted "
                     "(ratio 0.62), 3 unclaimed: Alpha; Beta; Gamma; research date: June 10, 1973"]


@pytest.mark.parametrize("n_titled, n_unresolved, asserted, dates, expect_gate", [
    (8, 0, 5, ["1973-06-10"], True),
    (8, 0, 3, ["1973-06-10"], False),            # fewer than 4 asserted
    (10, 0, 4, ["1973-06-10"], False),           # 0.4: only the tape fraction fails
    (4, 0, 3, ["1973-06-10"], False),            # 0.75 but fewer than 4 asserted
    (8, 9, 5, ["1973-06-10"], False),            # over half the tape unresolved
    (8, 0, 5, ["June 10"], False),               # own date yearless only
    (8, 0, 5, [], False),                        # no own date
    (8, 0, 5, ["1973-06-10", "1973-06-11"], False),   # a date flag read BEFORE 4b suppresses it
])
def test_right_show_gate_table(n_titled, n_unresolved, asserted, dates, expect_gate):
    show = _tape(n_titled, n_unresolved)
    songs = [f"Song {i}" for i in range(1, asserted + 1)] + ["Alpha", "Beta"]
    vet = ResearchVetting(asserted_songs=songs, asserted_dates=dates)
    raw = ["research asserts wrong date: 1973-06-11"] if "1973-06-11" in dates else []
    ok, info = right_show_gate(vet, show, date_flags_raw=raw)
    assert ok is expect_gate


def test_right_show_gate_requires_the_own_full_date_with_year():
    # Review Focus 5.
    show = _tape(8)
    vet = ResearchVetting(asserted_songs=[f"Song {i}" for i in range(1, 6)] + ["Alpha", "Beta", "Gamma"],
                          asserted_dates=["June 10"])
    flags, _, notes = grounding_flags(vet, show)
    assert any("unknown song" in f for f in flags) and notes == []


def test_4a_unknown_songs_may_not_outnumber_the_asserted_tracks():
    show = _tape(8)
    vet = ResearchVetting(asserted_songs=[f"Song {i}" for i in range(1, 5)] + [f"X{i}" for i in range(5)],
                          asserted_dates=["1973-06-10"])
    ok, _ = right_show_gate(vet, show, date_flags_raw=[])
    assert ok is False


def test_4a_excludes_tautological_titles_from_both_sides():
    show = _tape(8, sources="setlist-gap")
    vet = ResearchVetting(asserted_songs=[f"Song {i}" for i in range(1, 9)] + ["Alpha", "Beta"],
                          asserted_dates=["1973-06-10"])
    ok, info = right_show_gate(vet, show, date_flags_raw=[])
    assert ok is False and info["resolved"] == 0


def test_4a_a_tmp_tape_demoted_by_2b_cannot_pass():
    show = _tape(0, n_unresolved=19)
    vet = ResearchVetting(asserted_songs=[f"Song {i}" for i in range(1, 20)], asserted_dates=["1973-06-10"])
    ok, _ = right_show_gate(vet, show, date_flags_raw=[])
    assert ok is False


def test_right_show_gate_holds_at_exactly_half_the_tape():
    # The fraction bound is inclusive: 4 of 8 resolved tracks asserted is enough.
    show = _tape(8)
    vet = ResearchVetting(asserted_songs=[f"Song {i}" for i in range(1, 5)] + ["Alpha", "Beta"],
                          asserted_dates=["1973-06-10"])
    ok, info = right_show_gate(vet, show, date_flags_raw=[])
    assert ok is True
    assert info == {"asserted": 4, "resolved": 8, "ratio": 0.5,
                    "unknown": ["Alpha", "Beta"], "date_text": "1973-06-10"}


def test_right_show_gate_excludes_filler_from_the_resolved_count():
    # 4 asserted of 8 songs is exactly half; two filler tracks must not dilute it.
    show = _tape(8)
    filler = [Track(index=9, set="1", title="Tuning", filename="9.mp3", title_source="tags"),
              Track(index=10, set="1", title="Crowd", filename="10.mp3", title_source="tags")]
    show = show.model_copy(update={"tracks": show.tracks + filler})
    vet = ResearchVetting(asserted_songs=[f"Song {i}" for i in range(1, 5)] + ["Alpha", "Beta"],
                          asserted_dates=["1973-06-10"])
    ok, info = right_show_gate(vet, show, date_flags_raw=[])
    assert ok is True and info["resolved"] == 8


def test_4a_reads_the_raw_date_flags_not_the_windowed_ones():
    # Wiring pin: 4b drops the adjacent day from the flags, but research naming
    # the adjacent night still disqualifies 4a (spec "Failure modes", 4a).
    show = _tape(8)
    vet = ResearchVetting(asserted_songs=[f"Song {i}" for i in range(1, 6)] + ["Alpha", "Beta", "Gamma"],
                          asserted_dates=["1973-06-10", "1973-06-11"])
    flags, _, notes = grounding_flags(vet, show)
    assert not any("wrong date" in f for f in flags)        # 4b's window applied
    assert [f for f in flags if "unknown song" in f] == [
        "research asserts unknown song: Alpha",
        "research asserts unknown song: Beta",
        "research asserts unknown song: Gamma",
    ]
    assert notes == []


def test_4a_note_only_when_the_unknown_song_flags_would_fire():
    # One unclaimed song of nine is grounded today: no flag, so nothing to suppress or note.
    show = _tape(8)
    vet = ResearchVetting(asserted_songs=[f"Song {i}" for i in range(1, 9)] + ["Alpha"],
                          asserted_dates=["1973-06-10"])
    flags, _, notes = grounding_flags(vet, show)
    assert flags == [] and notes == []


def test_4a_note_lands_in_vet_outcome_notes_and_flags_clear():
    show = _tape(8).model_copy(update={"review_flags": ["research asserts unknown song: Old"],
                                       "needs_review": True})
    vet = ResearchVetting(asserted_songs=[f"Song {i}" for i in range(1, 6)] + ["Alpha", "Beta", "Gamma"],
                          asserted_dates=["1973-06-10"])
    out = apply_vet(vet, show)
    assert out.show.review_flags == [] and out.show.needs_review is False
    assert out.result.flags == []
    assert len(out.notes) == 1 and out.notes[0].startswith("unknown-song flags suppressed by the right-show gate: 5/8")


# --- Task 16b (Checkpoint E): a day-00 date is a "day unknown" assertion ---


@pytest.mark.parametrize("text, expect", [
    ("1991-09-00", "1991-09-00"),
    ("9/0/91", "1991-09-00"),
    ("September 0, 1991", "1991-09-00"),
    ("0 September 1991", "1991-09-00"),
    ("1991-00-00", None),      # month 0
    ("1991-13-00", None),      # month 13
    ("0/0/91", None),          # month 0 either way round
    ("September 0", None),     # year-less
    ("0/5", None),             # year-less slash
    ("1991-09-01", None),      # an ordinary valid date
    ("1991-09-32", None),
])
def test_day_unknown_date(text, expect):
    assert day_unknown_date(text) == expect


def test_normalize_date_still_rejects_day_zero():
    assert normalize_date("1991-09-00") is None


def _show_on(date, source="item"):
    return make_show().model_copy(update={"date": date, "date_source": source})


def test_16b_billycorgan_shape_day00_is_the_only_flag():
    show = _show_on("1991-09-01")
    flags, adopted, _ = grounding_flags(
        _vet(["1991-09-01", "1991-09-00", "09/XX/1991", "September 1991, London"]), show)
    assert flags == ["research asserts wrong date: 1991-09-00"] and adopted is None


def test_16b_day00_in_another_month_flags():
    flags, _, _ = grounding_flags(_vet(["1973-06-10", "1973-09-00"]), make_show())
    assert flags == ["research asserts wrong date: 1973-09-00"]


def test_16b_day00_next_to_the_show_date_is_not_windowed_away():
    show = _show_on("1973-06-01")
    flags, _, _ = grounding_flags(_vet(["1973-06-01", "1973-06-00"]), show)
    assert flags == ["research asserts wrong date: 1973-06-00"]


def test_16b_day00_flag_uses_the_surface_text_and_orders_before_yearless():
    flags, _, _ = grounding_flags(
        _vet(["1973-06-10", "September 0, 1973", "December 2"]), make_show())
    assert flags == ["research asserts wrong date: September 0, 1973",
                     "research asserts wrong date: December 2"]


def test_16b_placeholder_show_ignores_day00():
    show = _show_on("1970-01-01")
    flags, adopted, _ = grounding_flags(_vet(["August 1970", "1970-08-00"]), show)
    assert flags == [] and adopted is None


def test_16b_placeholder_adoption_unchanged_by_a_day00_entry():
    show = _show_on("1970-01-01")
    base = grounding_flags(_vet(["1970-08-15"]), show)
    with_zero = grounding_flags(_vet(["1970-08-15", "1970-08-00"]), show)
    assert base[1] == "1970-08-15" and with_zero[:2] == base[:2]


def test_16b_day00_makes_the_right_show_gate_decline():
    show = _tape(8)
    vet = ResearchVetting(
        asserted_songs=[f"Song {i}" for i in range(1, 6)] + ["Alpha", "Beta", "Gamma"],
        asserted_dates=["1973-06-10", "1973-06-00"])
    flags, _, notes = grounding_flags(vet, show)
    assert notes == [] and any("unknown song" in f for f in flags)
    assert "research asserts wrong date: 1973-06-00" in flags
