import json
from pathlib import Path
from unittest.mock import patch

import pytest

import llama.stages.gather as gather_mod
from llama.config import StructureConfig
from herder import FakeProvider
from herder.limits import RateLimited
from llama.junk import filter_files
from llama.models import (Candidate, Overrides, ParsedSetlist, RecordingSummary,
                          SetlistItem)
from llama.setlistfm import SetlistFMClient
from llama.songs import normalize_song
from llama.stages.gather import (_HEAD_CHATTER, _drop_artist_items,
                                 _strip_footnote_markers, _strip_head_banner,
                                 run_gather)
from llama.structure import align, fuzzy_norm_title
from llama.workspace import ShowWorkspace, read_model, read_overrides, write_artifact
from llama import jerrybase
from llama.models import JerrybaseEvent, JerrybaseSet
from llama.models import ShowNotes
from llama.stages.gather import GatherResult, compute_gather
from llama.stages.gather import build_canonical
from llama.models import Track
from llama.stages.gather import accept_short_tags
from llama.stages.gather import two_venue_signature

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "gd73_metadata.json"
IDENT = "gd73-06-10.sbd.hollister.174.sbeok.shnf"
W_IDENT = "gd74-02-24.sbd.windsor.199.sbefail.shnf"
M_IDENT = "gd1974-02-24.sbd.miller.116902.flac16"
YMSB_FIXTURE = FIXTURES / "ymsb2005_metadata.json"
Y_IDENT = "ymsb2005-12-31.flac16.wav"


class StubIA:
    """Serves one metadata dict for every identifier (single-recording tests)."""

    def __init__(self, md=None):
        self.md = md or json.loads(FIXTURE.read_text())

    def metadata(self, identifier):
        return self.md


class MultiIA:
    """Serves per-identifier metadata (sibling-consensus tests)."""

    def __init__(self, mapping):
        self.mapping = mapping

    def metadata(self, identifier):
        return self.mapping[identifier]


class CountingIA(MultiIA):
    """Like MultiIA, but records every identifier `.metadata()` was called
    for -- used to pin how many times a sibling recording was actually
    fetched (the loosened gather fetch gate must skip the sibling-align pass
    entirely on a fully-tagged tape, not merely decline to adopt anything)."""

    def __init__(self, mapping):
        super().__init__(mapping)
        self.calls: list[str] = []

    def metadata(self, identifier):
        self.calls.append(identifier)
        return super().metadata(identifier)


def _gd73_donor(base_md: dict, titles: list[str], description: str = "") -> dict:
    """A fully-tagged sibling recording of gd73-06-10: one real title per kept
    audio file, in play order. `titles` must have exactly 6 entries."""
    sib = {"metadata": dict(base_md["metadata"], description=description),
           "files": [dict(f) for f in base_md["files"]]}
    sib_audio = sorted(
        (f for f in sib["files"]
         if f.get("format") == "VBR MP3" and f["name"].startswith("gd73-06-10d")),
        key=lambda f: f["name"])
    assert len(sib_audio) == len(titles)
    for f, title in zip(sib_audio, titles):
        f["title"] = title
    return sib


def make_candidate():
    return Candidate(
        performance_id="GratefulDead/1973-06-10", collection="GratefulDead",
        date="1973-06-10", venue="RFK Stadium", city="Washington, DC",
        recordings=[RecordingSummary(identifier=IDENT)],
    )


def gd74_candidate():
    return Candidate(
        performance_id="GratefulDead/1974-02-24", collection="GratefulDead",
        date="1974-02-24", venue="Winterland Arena", city="San Francisco, CA",
        recordings=[RecordingSummary(identifier=W_IDENT), RecordingSummary(identifier=M_IDENT)],
    )


def gd74_ia():
    return MultiIA({
        W_IDENT: json.loads((FIXTURES / "gd74_windsor_metadata.json").read_text()),
        M_IDENT: json.loads((FIXTURES / "gd74_miller_metadata.json").read_text()),
    })


def test_gather_builds_show_from_fixture(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert show.artist == "Grateful Dead"
    assert [t.title for t in show.tracks] == [
        "Morning Dew", "China Cat Sunflower", "I Know You Rider",
        "Dark Star", "Eyes of the World", "Johnny B. Goode",
    ]
    # d3t01 has no tag title -> resolved from parsed setlist
    assert show.tracks[5].title_source == "setlist"
    assert show.tracks[1].segue is True
    assert [t.set for t in show.tracks] == ["1", "1", "1", "2", "2", "encore"]
    assert show.set_breaks == [3, 5]
    assert any(e["filename"] == "FOLLOW-ME @BYPIKENO.mp3" for e in show.excluded_files)
    assert show.needs_review is False
    assert show.source_url.endswith(IDENT)
    assert sws.show.exists() and sws.reviews.exists()
    assert len(json.loads(sws.reviews.read_text())) == 2


def test_gather_llm_fallback_on_unparseable_description(tmp_path: Path):
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = "An amazing night of music, seeded with love."
    fallback = json.dumps({
        "items": [
            {"title": t, "normalized": t.lower(), "set": s, "segue": g}
            for t, s, g in [
                ("Morning Dew", "1", False), ("China Cat Sunflower", "1", True),
                ("I Know You Rider", "1", False), ("Dark Star", "2", True),
                ("Eyes of the World", "2", False), ("Johnny B. Goode", "encore", False),
            ]
        ],
        "confidence": "medium",
    })
    sws = ShowWorkspace(tmp_path / "show")
    fake = FakeProvider(completes=[fallback])
    show = run_gather(sws, StubIA(md), fake, make_candidate(), IDENT)
    assert fake.calls and fake.calls[0][0] == "complete"
    assert show.tracks[5].title == "Johnny B. Goode"


def test_gather_flags_unresolved(tmp_path: Path):
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = ""
    for f in md["files"]:
        f.pop("title", None)
    sws = ShowWorkspace(tmp_path / "show")
    # empty description -> no LLM fallback attempted -> unresolved titles flagged
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    assert show.needs_review is True
    assert any("unresolved" in f for f in show.review_flags)


def test_gather_recovers_structure_from_sibling(tmp_path: Path):
    """Regression: gratefuldead-1974-02-24 shipped with every track in set 1."""
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, gd74_ia(), FakeProvider(), gd74_candidate(), W_IDENT)
    # Piece 4 (spec 1, 2.3): the 82 s `Weather Report Suite Part I >` (D3_T02,
    # track 17) is a short-only drop whose tag is not junk, so it is now kept.
    assert len(show.tracks) == 28
    sets = [t.set for t in show.tracks]
    assert sets[:11] == ["1"] * 11                     # US Blues .. Playin' In The Band
    assert sets[11:27] == ["2"] * 16                   # Cumberland Blues .. Not Fade Away
    assert sets[27] == "encore"                        # E: It's All Over Now, Baby Blue
    assert show.set_breaks == [11, 27]
    assert show.structure is not None
    assert show.structure.source == f"lma:{M_IDENT}"
    assert show.structure.alignment == "deterministic"
    # `Part I` does not match the canonical `Part 1`, but it is short-kept and
    # spec 3's coverage clause leaves short-kept tracks out, so coverage is 1.0.
    assert show.structure.coverage == 1.0
    # segues from the sibling's taper notation
    assert show.tracks[6].segue is True                # China Cat Sunflower >
    assert show.tracks[12].segue is False               # Roses: windsor's own junk parse said True
    assert show.needs_review is False


def test_align_result_matched_reaches_the_track(tmp_path: Path):
    """AlignResult.matched was computed per track, used for coverage, and
    discarded. It is the only record of whether a title matched a canonical
    setlist item -- title_source says only where the title came from."""
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, gd74_ia(), FakeProvider(), gd74_candidate(), W_IDENT)
    assert show.structure.alignment == "deterministic"
    # Piece 4 (spec 1, 2.3): the kept 82 s `Weather Report Suite Part I >`
    # (track 17) does not match the canonical `Part 1`; it is the one unmatched
    # track, but it is short-kept, so spec 3's coverage clause leaves it out.
    assert show.structure.coverage == 1.0
    assert all(t.matched is not None for t in show.tracks), \
        "the deterministic path measures every track"
    # Every other track matched -- a weaker `any(... is True)` would pass even
    # if `matched` were fed the wrong per-track boolean list (e.g. segues,
    # which is also list[bool] and also has some True values), so it wouldn't
    # catch that class of mistake.
    assert [t.index for t in show.tracks if t.matched is not True] == [17]


def test_override_path_leaves_matched_unmeasured(tmp_path: Path):
    """The override path skips align() and forces coverage to 1.0, so there is
    no per-track match data. None must mean unknown, never matched."""
    sws = ShowWorkspace(tmp_path / "show")
    # encore_after names the last set-2 file, D4_T06 (track 27 since piece 4 keeps
    # D3_T02 at track 17, spec 1); the break follows D2_T01, track 11.
    write_artifact(sws.overrides, Overrides(set_breaks=["GD_022474_D2_T01.mp3"],
                                            encore_after="GD_022474_D4_T06.mp3"))
    show = run_gather(sws, gd74_ia(), FakeProvider(), gd74_candidate(), W_IDENT)
    assert show.structure.alignment == "override"
    assert all(t.matched is None for t in show.tracks)


def test_gather_setlistfm_wins_with_lma_segues(tmp_path: Path):
    import httpx

    slfm_body = json.loads((FIXTURES / "slfm_gd_1974_02_24.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=slfm_body)

    client = SetlistFMClient(
        cache_dir=tmp_path / "slfm-cache", api_key="k",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        backoff_s=0, rate_limit_s=0,
    )
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, gd74_ia(), FakeProvider(), gd74_candidate(), W_IDENT,
                      setlistfm=client)
    assert show.structure.source == "setlist.fm"
    assert show.set_breaks == [11, 27]                 # piece 4 keeps D3_T02 (spec 1)
    assert show.tracks[6].segue is True                # blended back from the LMA parse


def test_gather_flags_long_flat_show(tmp_path: Path):
    md = json.loads((FIXTURES / "gd74_windsor_metadata.json").read_text())
    # Strip the bare mid-line "E: " encore marker so the description is
    # genuinely flat (one unbroken comma list, no set/encore markers at
    # all) - the fixture's real "E:" now correctly splits off an encore
    # (see setlist._INLINE_MARKER), which would give this show a set break
    # and defeat the single-set guard this test exists to exercise.
    md["metadata"]["description"] = md["metadata"]["description"].replace(", E: ", ", ")
    ident = W_IDENT
    cand = Candidate(
        performance_id="GratefulDead/1974-02-24", collection="GratefulDead",
        date="1974-02-24", venue="Winterland Arena", city="San Francisco, CA",
        recordings=[RecordingSummary(identifier=ident)],   # no structured sibling
    )
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), cand, ident)
    assert show.needs_review is True
    assert any(f.startswith("single-set structure for a long show") for f in show.review_flags)


def test_gather_low_coverage_uses_llm_alignment(tmp_path: Path):
    md = json.loads(FIXTURE.read_text())
    # Wreck the tag titles so deterministic alignment can't match them,
    # while the description still yields a good canonical setlist.
    for i, f in enumerate(f for f in md["files"] if f.get("format") == "VBR MP3"):
        f["title"] = f"Track {i + 1}"
    llm_resp = json.dumps({"tracks": [
        {"index": 1, "set": "1", "segue": False, "matched_title": "Morning Dew"},
        {"index": 2, "set": "1", "segue": True, "matched_title": "China Cat Sunflower"},
        {"index": 3, "set": "1", "segue": False, "matched_title": "I Know You Rider"},
        {"index": 4, "set": "2", "segue": False, "matched_title": "Dark Star"},
        {"index": 5, "set": "2", "segue": False, "matched_title": "Eyes of the World"},
        {"index": 6, "set": "encore", "segue": False, "matched_title": "Johnny B. Goode"},
    ]})
    sws = ShowWorkspace(tmp_path / "show")
    align_fake = FakeProvider(completes=[llm_resp])
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT,
                      align_provider=align_fake)
    assert align_fake.calls, "align_structure LLM was not invoked"
    assert show.structure.alignment == "llm"
    assert [t.set for t in show.tracks] == ["1", "1", "1", "2", "2", "encore"]
    assert show.set_breaks == [3, 5]


def test_gather_rate_limit_during_llm_alignment_propagates_and_does_not_flag(tmp_path: Path):
    # Same setup as test_gather_llm_alignment_garbage_falls_back_and_flags
    # (wrecked tag titles force the deterministic alignment low enough to
    # reach the align_structure LLM fallback), except align_provider raises
    # RateLimited instead of returning garbage. Before the fix this was
    # swallowed by `except (TaskFailed, HerderError)`, logged, and papered
    # over with a `low-confidence structure alignment` flag the recording
    # did not earn -- and because should_run means gather never reruns once
    # show.json exists, that wrong flag would be permanent. The fix must
    # let RateLimited propagate instead, and nothing should be written to
    # disk in its place.
    md = json.loads(FIXTURE.read_text())
    for i, f in enumerate(f for f in md["files"] if f.get("format") == "VBR MP3"):
        f["title"] = f"Track {i + 1}"
    align_fake = FakeProvider(
        completes=[RateLimited("You've hit your session limit", scope="five_hour")])
    sws = ShowWorkspace(tmp_path / "show")
    with pytest.raises(RateLimited):
        run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT,
                  align_provider=align_fake)
    assert align_fake.calls, "align_structure LLM was not invoked"
    assert not sws.show.exists(), "show.json must not be written on a rate-limit abort"


def test_gather_llm_alignment_garbage_falls_back_and_flags(tmp_path: Path):
    md = json.loads(FIXTURE.read_text())
    for i, f in enumerate(f for f in md["files"] if f.get("format") == "VBR MP3"):
        f["title"] = f"Track {i + 1}"
    garbage = json.dumps({"tracks": [{"index": 1, "set": "afterparty"}]})
    sws = ShowWorkspace(tmp_path / "show")
    align_fake = FakeProvider(completes=[garbage, garbage, garbage])  # exhausts retries
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT,
                      align_provider=align_fake)
    assert show.needs_review is True
    assert "low-confidence structure alignment" in show.review_flags
    assert show.structure.alignment == "deterministic"


# ============================================================================
# Task 5: the guarded sibling-align transfer pass, wired into gather.
#
# The old positional "sibling" rung (`titles._sibling_titles`,
# `resolve_titles`'s `elif sibling_titles and len(sibling_titles) == n`) is
# GONE -- see test_shifted_fully_tagged_sibling_does_not_transfer_positionally
# below, the test the old rung could never pass. Its replacement is
# `llama.siblings` (a pure duration-alignment DP + two guards) wired here via
# `gather._sibling_transfer_full` (through `title_inputs`' `sibling_step`), which runs
# after the `overrides.titles` loop and before `adopt_gap_titles`.
# ============================================================================

SIB_ID = "gd73-06-10.aud.sibling"
REAL_TITLES = ["Morning Dew", "China Cat Sunflower", "I Know You Rider",
              "Dark Star", "Eyes of the World", "Johnny B. Goode"]


def test_sibling_transfer_adopts_into_a_bracketed_gap(tmp_path: Path):
    """The core happy path: two tag-verified anchors (tracks 1 and 6) bracket
    a 4-track unresolved run, a fully-tagged sibling agrees with both anchors
    (agreement 1.0 >= AUTO), and guard shape C+ finds the interior run
    count-forced between them -- so all four titles adopt, string for string,
    with title_source == "sibling-align". `matched` must be align()'s real
    per-track verdict, not forced to None: sibling-align is independent
    evidence, unlike the tautological setlist-gap/setlist rungs (invariant:
    do not add "sibling-align" to structure.TAUTOLOGICAL_TITLE_SOURCES)."""
    md = json.loads(FIXTURE.read_text())
    chosen = {"metadata": dict(md["metadata"], description=""),
              "files": [dict(f) for f in md["files"]]}
    by_name = {f["name"]: f for f in chosen["files"]}
    for name in ("gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3",
                 "gd73-06-10d2t01.mp3", "gd73-06-10d2t02.mp3"):
        by_name[name].pop("title", None)               # tracks 2-5: unresolved
    by_name["gd73-06-10d3t01.mp3"]["title"] = "Johnny B. Goode"  # track 6 anchor

    sib = _gd73_donor(md, REAL_TITLES)
    ia = MultiIA({IDENT: chosen, SIB_ID: sib})
    cand = make_candidate()
    cand.recordings.append(RecordingSummary(identifier=SIB_ID))
    show = run_gather(ShowWorkspace(tmp_path / "show"), ia, FakeProvider(), cand, IDENT)

    got = {t.index: t for t in show.tracks}
    assert [got[i].title for i in (2, 3, 4, 5)] == [
        "China Cat Sunflower", "I Know You Rider", "Dark Star", "Eyes of the World"]
    assert [got[i].title_source for i in (2, 3, 4, 5)] == ["sibling-align"] * 4
    assert all(got[i].matched is not None for i in (2, 3, 4, 5))


def test_operator_band_run_stays_unresolved_even_though_cplus_would_bracket_it(tmp_path: Path):
    """FIX ROUND 1, I1: the `rate_alignment` band gate (gather.py's
    `if res.band != "auto": ... return`) had ZERO content coverage -- both
    prior tests that name it use a ZERO-anchor tape, where `cplus_filter`
    declines every run regardless of the band gate, so they reach the right
    outcome through the wrong mechanism (deleting the gate left them green).

    This fixture discriminates: tracks 1, 2 and 5 keep their own tags and
    agree with the donor; track 6 is tagged "Bertha", which the donor
    disagrees with (the donor's real content is "Johnny B. Goode"). That is
    4 anchors, 3 agreeing -> 0.75, strictly between FLOOR (0.50) and AUTO
    (0.80) -> band == "operator". The interior run (tracks 3-4) IS properly
    bracketed by agreeing anchors and count-forced -- `cplus_filter` alone
    would let it through -- so only the band gate stands between it and
    adoption. It must stay unresolved."""
    md = json.loads(FIXTURE.read_text())
    chosen = {"metadata": dict(md["metadata"], description=""),
              "files": [dict(f) for f in md["files"]]}
    by_name = {f["name"]: f for f in chosen["files"]}
    for name in ("gd73-06-10d1t03.mp3", "gd73-06-10d2t01.mp3"):
        by_name[name].pop("title", None)               # tracks 3-4: unresolved
    by_name["gd73-06-10d3t01.mp3"]["title"] = "Bertha"  # track 6: disagreeing anchor
    # tracks 1, 2, 5 keep the base fixture's own correct tags (agreeing anchors)

    sib = _gd73_donor(md, REAL_TITLES)                  # donor's track 6 is the true "Johnny B. Goode"
    ia = MultiIA({IDENT: chosen, SIB_ID: sib})
    cand = make_candidate()
    cand.recordings.append(RecordingSummary(identifier=SIB_ID))
    show = run_gather(ShowWorkspace(tmp_path / "show"), ia, FakeProvider(), cand, IDENT)

    got = {t.index: t for t in show.tracks}
    assert [got[i].title_source for i in (3, 4)] == ["unresolved"] * 2
    assert [got[i].title for i in (3, 4)] == [got[i].filename for i in (3, 4)]
    assert show.structure is not None
    assert any(n == "sibling alignment needs operator review (anchor agreement 75%)"
              for n in show.structure.conflicts)


def test_a_sibling_fetch_failure_is_noted_not_fatal(tmp_path: Path):
    """FIX ROUND 1, I2: `ia.metadata` inside the sibling transfer pass was
    unguarded, so one sibling recording raising `IAError` (a real archive.org
    failure mode) aborted the entire gather stage instead of degrading
    gracefully -- unlike `_collect_parses`, which already catches exactly
    this call on exactly these identifiers and notes-and-continues. The two
    must not diverge: a flaky sibling must not lose the show.

    DUPLICATE-NOTE GUARD (deferred minor, final whole-branch review): both
    `_collect_parses` (called first, unconditionally, via `build_canonical`)
    and `load_donor_tapes` (called only when `_sibling_transfer_full` fires)
    independently catch this exact `IAError` on this exact identifier
    (`IAClient` never caches a failed fetch, so both really do retry) and
    each append their own byte-identical note -- so this note used to reach
    `StructureInfo.conflicts` TWICE, and `conflicts` is serialized straight
    into the briefing LLM prompt via `show.model_dump_json()`
    (`stages/brief.py:138`), making it duplicated prompt content, not merely
    a duplicated log line. Fixed at the join, not by suppressing either
    fetch: `run_gather`'s `_dedupe_ordered(conflicts + notes)` keeps the
    first occurrence of each distinct string and drops repeats, order
    preserved (an earlier cut threaded "already failed" state between the
    two fetchers instead -- reverted: it changed fetch behaviour, turning a
    transient failure that would have recovered on the second attempt into
    a permanent one). The assertion below counts occurrences rather than
    using `any(...)`, which cannot see a duplicate: removing the
    `_dedupe_ordered` call reproduces the double note (count 2) and reddens
    this; a dedupe that over-suppresses (drops every occurrence of a
    repeated item instead of keeping one) reddens it the other way (count
    0)."""
    from llama.ia_client import IAError

    class FlakySiblingIA(MultiIA):
        def metadata(self, identifier):
            if identifier == SIB_ID:
                raise IAError("boom 503")
            return super().metadata(identifier)

    # d3t01 (track 6) deliberately left untagged, matching the base fixture:
    # title_fraction is 5/6 < 1.0, so the fetch gate still fires and
    # `_sibling_transfer_full` actually attempts (and must survive) the failing
    # donor fetch -- a fully-tagged target would skip the gate entirely and
    # never exercise the fix.
    md = json.loads(FIXTURE.read_text())
    ia = FlakySiblingIA({IDENT: md})
    cand = make_candidate()
    cand.recordings.append(RecordingSummary(identifier=SIB_ID))

    show = run_gather(ShowWorkspace(tmp_path / "show"), ia, FakeProvider(), cand, IDENT)

    # Nothing crashed, and the show still resolved normally (track 6 via the
    # ordinary whole-tape setlist rung, since its own tag is genuinely
    # missing) -- sibling-align never got a chance to run at all.
    assert [t.title for t in show.tracks] == REAL_TITLES
    assert not any(t.title_source == "sibling-align" for t in show.tracks)
    assert show.structure is not None
    note = f"could not fetch sibling {SIB_ID}: boom 503"
    assert sum(1 for n in show.structure.conflicts if note in n) == 1


def test_the_higher_agreement_donor_wins_not_the_alphabetically_first_one(tmp_path: Path):
    """FIX ROUND 1, I3 (= spec review Q2): `_donor_key` (highest agreement,
    then lowest DP cost, then identifier) decides WHOSE TITLES SHIP and had
    zero test coverage -- inverting the whole ranking left the entire suite
    green. Donor A sorts FIRST alphabetically ("a-loser") so the identifier
    tie-break cannot accidentally produce the right answer, but agrees with
    only one of the two anchors (agreement 0.5, "operator" band alone) and
    proposes distinguishable wrong interior titles. Donor B ("z-winner")
    agrees with both anchors (agreement 1.0, "auto" band) and carries the
    true interior titles. Donor B must win."""
    md = json.loads(FIXTURE.read_text())
    chosen = {"metadata": dict(md["metadata"], description=""),
              "files": [dict(f) for f in md["files"]]}
    by_name = {f["name"]: f for f in chosen["files"]}
    for name in ("gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3",
                 "gd73-06-10d2t01.mp3", "gd73-06-10d2t02.mp3"):
        by_name[name].pop("title", None)               # tracks 2-5: unresolved
    by_name["gd73-06-10d3t01.mp3"]["title"] = "Johnny B. Goode"  # track 6 anchor

    loser_titles = ["Morning Dew", "Wrong Two", "Wrong Three", "Wrong Four",
                    "Wrong Five", "Truckin'"]            # disagrees on track 6
    donor_a = _gd73_donor(md, loser_titles)
    donor_b = _gd73_donor(md, REAL_TITLES)               # agrees with both anchors

    ia = MultiIA({IDENT: chosen, "gd73-06-10.aud.a-loser": donor_a,
                  "gd73-06-10.aud.z-winner": donor_b})
    cand = make_candidate()
    cand.recordings.append(RecordingSummary(identifier="gd73-06-10.aud.a-loser"))
    cand.recordings.append(RecordingSummary(identifier="gd73-06-10.aud.z-winner"))
    show = run_gather(ShowWorkspace(tmp_path / "show"), ia, FakeProvider(), cand, IDENT)

    got = {t.index: t for t in show.tracks}
    assert [got[i].title for i in (2, 3, 4, 5)] == [
        "China Cat Sunflower", "I Know You Rider", "Dark Star", "Eyes of the World"]
    assert not any(t.title.startswith("Wrong ") for t in show.tracks)


def test_fully_tagged_tape_does_not_fetch_a_sibling_for_title_transfer(tmp_path: Path):
    """The loosened fetch gate (`kept and title_fraction(...) < 1.0`) must
    still skip the sibling-align pass entirely once the tape's own tags
    already cover every kept file -- not merely decline to adopt anything.
    CountingIA pins the sibling identifier is fetched exactly once (by
    `_collect_parses`' description scan, which runs unconditionally for every
    recording), never a second time for title transfer."""
    md = json.loads(FIXTURE.read_text())
    for f in md["files"]:
        if f["name"] == "gd73-06-10d3t01.mp3":
            f["title"] = "Johnny B. Goode"
    ia = CountingIA({IDENT: md, SIB_ID: json.loads(FIXTURE.read_text())})
    cand = make_candidate()
    cand.recordings.append(RecordingSummary(identifier=SIB_ID))
    show = run_gather(ShowWorkspace(tmp_path / "show"), ia, FakeProvider(), cand, IDENT)

    assert [t.title for t in show.tracks] == REAL_TITLES
    assert all(t.title_source == "tags" for t in show.tracks)
    assert ia.calls.count(SIB_ID) == 1


def test_wholly_untagged_tape_gets_zero_automatic_sibling_adoptions(tmp_path: Path):
    """ymsb2005 (Phase B's trigger fixture): no tagged track on the target
    means no independent anchor, so `rate_alignment` reports band ==
    "no-anchors" regardless of how well a sibling's durations line up -- and
    gather must adopt nothing. This is the pin whose INVERSE Phase B shipped
    nine times (a wholly untagged tape must never get automatic titles)."""
    md = json.loads(YMSB_FIXTURE.read_text())
    sib = json.loads(YMSB_FIXTURE.read_text())
    for i, f in enumerate(sorted((f for f in sib["files"] if f.get("format") == "VBR MP3"),
                                 key=lambda f: f["name"])):
        f["title"] = f"Song Title {i + 1}"          # hygienic, but nothing anchors it
    ident = "ymsb2005-12-31.aud.sibling"
    ia = MultiIA({Y_IDENT: md, ident: sib})
    cand = _ymsb_candidate()
    cand.recordings.append(RecordingSummary(identifier=ident))
    show = run_gather(ShowWorkspace(tmp_path / "show"), ia, FakeProvider(), cand, Y_IDENT)

    assert all(t.title_source == "unresolved" for t in show.tracks)
    assert not any(t.title_source == "sibling-align" for t in show.tracks)


def test_below_floor_sibling_alignment_declines_with_a_note(tmp_path: Path):
    """5 of 6 tracks keep their own tags (title_fraction 0.833 < 1.0, so the
    fetch gate still fires); the donor agrees on only 1 of those 5 anchors
    (agreement 0.20 < FLOOR). That is a wrong alignment, not weak evidence of
    a right one -- `rate_alignment` declines it outright, and gather must
    surface why rather than silently doing nothing. Track 6 (no tag of its
    own) is untouched by this test either way: it is not an anchor, and a
    declined pair adopts nothing regardless."""
    md = json.loads(FIXTURE.read_text())
    chosen = {"metadata": dict(md["metadata"]),
              "files": [dict(f) for f in md["files"]]}   # d3t01 keeps its own no-tag state

    donor_titles = ["Morning Dew", "Sugar Magnolia", "Casey Jones",
                    "Ripple", "Bertha", "Jack Straw"]   # only track 1 agrees
    sib = _gd73_donor(md, donor_titles, description=chosen["metadata"]["description"])
    ia = MultiIA({IDENT: chosen, SIB_ID: sib})
    cand = make_candidate()
    cand.recordings.append(RecordingSummary(identifier=SIB_ID))
    show = run_gather(ShowWorkspace(tmp_path / "show"), ia, FakeProvider(), cand, IDENT)

    assert [t.title for t in show.tracks] == REAL_TITLES     # nothing overwritten
    assert not any(t.title_source == "sibling-align" for t in show.tracks)
    assert show.structure is not None
    assert any(n.startswith("sibling alignment declined (anchor agreement")
              for n in show.structure.conflicts)


def test_a_bracketing_failure_leaves_the_run_unresolved_with_its_reason_in_notes(tmp_path: Path):
    """Overall agreement is high (2/2 agreeing anchors -> auto band), but the
    unresolved run (tracks 3-6) reaches the tape's last track -- `gap_span`
    deliberately has no trailing-edge branch, so C+ cannot bracket it and
    demotes those rows to decline. Concern #2: that per-run reason is only
    visible on the (internal) SiblingRow otherwise, so it must reach notes."""
    md = json.loads(FIXTURE.read_text())
    chosen = {"metadata": dict(md["metadata"], description=""),
              "files": [dict(f) for f in md["files"]]}
    for f in chosen["files"]:
        if f["name"] in ("gd73-06-10d1t03.mp3", "gd73-06-10d2t01.mp3",
                         "gd73-06-10d2t02.mp3", "gd73-06-10d3t01.mp3"):
            f.pop("title", None)                      # tracks 3-6: unresolved

    sib = _gd73_donor(md, REAL_TITLES)
    ia = MultiIA({IDENT: chosen, SIB_ID: sib})
    cand = make_candidate()
    cand.recordings.append(RecordingSummary(identifier=SIB_ID))
    show = run_gather(ShowWorkspace(tmp_path / "show"), ia, FakeProvider(), cand, IDENT)

    got = {t.index: t for t in show.tracks}
    assert [got[i].title_source for i in (3, 4, 5, 6)] == ["unresolved"] * 4
    assert [got[i].title for i in (3, 4, 5, 6)] == [got[i].filename for i in (3, 4, 5, 6)]
    assert show.structure is not None
    assert any("tracks 3-6: not bracketed by agreeing anchors" in n
              for n in show.structure.conflicts)


def test_shifted_fully_tagged_sibling_does_not_transfer_positionally(tmp_path: Path):
    """OLD-RUNG REMOVAL PIN. Before this task, resolve_titles' "sibling" rung
    transferred a same-count sibling's titles onto the target POSITIONALLY
    with zero content verification -- a donor whose file COUNT matches but
    whose title CONTENT is rotated one song over would have shipped wrong
    titles at coverage 1.0, silently. The new sibling-align rung cannot make
    that mistake: this target carries no tag of its own at all, so it has no
    independent anchor and the pair routes to "no-anchors" regardless of how
    well the donor's durations line up. This is the test the old positional
    rung could never pass (see the acceptance mutation restoring it)."""
    md = json.loads(FIXTURE.read_text())
    chosen = {"metadata": dict(md["metadata"], description=""),
              "files": [dict(f) for f in md["files"]]}
    for f in chosen["files"]:
        f.pop("title", None)

    rotated = REAL_TITLES[1:] + REAL_TITLES[:1]        # every title one slot off
    sib = _gd73_donor(md, rotated)
    ia = MultiIA({IDENT: chosen, SIB_ID: sib})
    cand = make_candidate()
    cand.recordings.append(RecordingSummary(identifier=SIB_ID))
    show = run_gather(ShowWorkspace(tmp_path / "show"), ia, FakeProvider(), cand, IDENT)

    assert [t.title for t in show.tracks] == [t.filename for t in show.tracks]
    assert all(t.title_source == "unresolved" for t in show.tracks)


def test_an_already_titled_track_is_never_overwritten_by_a_surviving_adopt_row(tmp_path: Path):
    """CONCERN #1 (data loss). `cplus_filter` says nothing about a track that
    already has a title -- it gates FILL RUNS, and a track outside any run
    keeps whatever verdict `propose_rows` gave it. Track 2 here keeps its own
    tag "China Cat Sunflower" even though the donor proposes "Bertha" for it
    and that "adopt" row survives every guard: the other 4 of 5 tag-verified
    anchors agree (4/5 = 0.80 = AUTO exactly), so the pair still ships in the
    automatic band. Track 6 has no tag of its own (title_fraction 0.833 < 1.0,
    so the fetch gate still fires) and is not part of this test -- gather must
    intersect surviving adoptions with the UNRESOLVED set itself, or this
    overwrites the tape's own tag with the sibling's guess."""
    md = json.loads(FIXTURE.read_text())
    chosen = {"metadata": dict(md["metadata"], description=""),
              "files": [dict(f) for f in md["files"]]}   # d3t01 keeps its own no-tag state

    donor_titles = list(REAL_TITLES)
    donor_titles[1] = "Bertha"                          # disagrees with track 2's tag
    sib = _gd73_donor(md, donor_titles)
    ia = MultiIA({IDENT: chosen, SIB_ID: sib})
    cand = make_candidate()
    cand.recordings.append(RecordingSummary(identifier=SIB_ID))
    show = run_gather(ShowWorkspace(tmp_path / "show"), ia, FakeProvider(), cand, IDENT)

    track2 = show.tracks[1]
    assert track2.title == "China Cat Sunflower"
    assert track2.title_source == "tags"


def test_sibling_aligned_matches_count_as_independent_coverage_evidence(tmp_path: Path):
    """MUTATION A PIN (spec's independence invariant): sibling-align must NOT
    be in structure.TAUTOLOGICAL_TITLE_SOURCES, because align()'s match on a
    sibling-aligned track is real, independent evidence -- unlike
    setlist-gap/setlist, whose text IS the canonical item's own text.

    Track 1 here is tagged "Drums" -- a real, independently-sourced tag that
    matches no canonical setlist item -- and track 6 is tagged "Johnny B.
    Goode" (matches). Tracks 2-5 sibling-align onto the real middle-of-show
    songs and genuinely MATCH the canonical setlist too: real evidence, not a
    copy of it.

    Adding "sibling-align" to TAUTOLOGICAL_TITLE_SOURCES would drop tracks
    2-5 from the coverage denominator, shrinking it to the two weak anchors
    (1 match of 2 = 0.5, below the 0.8 default threshold) and wrongly firing
    "low-confidence structure alignment" on a show that is not actually
    low-confidence -- the mutation this test exists to catch."""
    md = json.loads(FIXTURE.read_text())
    # One extra encore item ("Space") the tape has no file for, so the
    # canonical item count (7) no longer equals the kept file count (6) --
    # otherwise resolve_titles' whole-tape "setlist" rung (aligned =
    # setlist.items if len(items) == n) would fill tracks 2-5 itself, before
    # the sibling-align pass ever sees them as unresolved.
    desc = md["metadata"]["description"].replace(
        "Encore:\nJohnny B. Goode", "Encore:\nJohnny B. Goode > Space")
    chosen = {"metadata": dict(md["metadata"], description=desc),
              "files": [dict(f) for f in md["files"]]}
    by_name = {f["name"]: f for f in chosen["files"]}
    by_name["gd73-06-10d1t01.mp3"]["title"] = "Drums"              # weak anchor: no match
    for name in ("gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3",
                "gd73-06-10d2t01.mp3", "gd73-06-10d2t02.mp3"):
        by_name[name].pop("title", None)                           # tracks 2-5: unresolved
    by_name["gd73-06-10d3t01.mp3"]["title"] = "Johnny B. Goode"     # strong anchor: matches

    sib_titles = ["Drums", "China Cat Sunflower", "I Know You Rider",
                 "Dark Star", "Eyes of the World", "Johnny B. Goode"]
    sib = _gd73_donor(md, sib_titles, description=desc)
    ia = MultiIA({IDENT: chosen, SIB_ID: sib})
    cand = make_candidate()
    cand.recordings.append(RecordingSummary(identifier=SIB_ID))
    show = run_gather(ShowWorkspace(tmp_path / "show"), ia, FakeProvider(), cand, IDENT)

    got = {t.index: t for t in show.tracks}
    assert got[1].title_source == "tags"
    assert [got[i].title for i in (2, 3, 4, 5)] == [
        "China Cat Sunflower", "I Know You Rider", "Dark Star", "Eyes of the World"]
    assert [got[i].title_source for i in (2, 3, 4, 5)] == ["sibling-align"] * 4
    assert got[6].title_source == "tags"
    assert show.structure is not None
    assert show.structure.coverage == 5 / 6
    assert show.needs_review is False
    assert "low-confidence structure alignment" not in show.review_flags


def test_prefixed_tag_titles_align(tmp_path: Path):
    md = json.loads(FIXTURE.read_text())
    md = {"metadata": dict(md["metadata"]), "files": [dict(f) for f in md["files"]]}
    for f in md["files"]:
        if f.get("title"):
            f["title"] = f"gd73-06-10d1t01 {f['title']}"
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    tagged = [t for t in show.tracks if t.title_source == "tags"]
    assert tagged and all(not t.title.startswith("gd73") for t in tagged)
    assert "low-confidence structure alignment" not in show.review_flags
    assert show.order_source in ("track-tags", "filename")  # recorded on the artifact


def _enumerate_tag_titles(md: dict) -> dict:
    """Rewrite every tagged file's title as a numbered tracklist - the shape of
    gus2018-01-13, where all 26 files are numbered 1..26."""
    md = {"metadata": dict(md["metadata"]), "files": [dict(f) for f in md["files"]]}
    n = 0
    for f in md["files"]:
        if f.get("title"):
            n += 1
            f["title"] = f"{n:02d} {f['title']}"
    return md


def test_gather_strips_track_numbers_on_an_enumerated_tape(tmp_path: Path):
    """An enumerated tape's numbers must not reach the manifest - emcee's
    scriptwriter reads the title verbatim."""
    md = _enumerate_tag_titles(json.loads(FIXTURE.read_text()))
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    tagged = [t for t in show.tracks if t.title_source == "tags"]
    assert tagged
    assert all(not t.title[0].isdigit() for t in tagged)


def test_gather_keeps_a_lone_numeric_title(tmp_path: Path):
    """One numbered title among unnumbered ones is a song, not enumeration.
    This should already pass before Task 2 - it is a regression guard."""
    md = json.loads(FIXTURE.read_text())
    md = {"metadata": dict(md["metadata"]), "files": [dict(f) for f in md["files"]]}
    tagged = [f for f in md["files"] if f.get("title")]
    tagged[1]["title"] = "100 Years"
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    assert "100 Years" in [t.title for t in show.tracks]


_LOSSLESS_TITLES = {
    "gd73-06-10d1t01": "Morning Dew", "gd73-06-10d1t02": "China Cat Sunflower",
    "gd73-06-10d1t03": "I Know You Rider", "gd73-06-10d2t01": "Dark Star",
    "gd73-06-10d2t02": "Eyes of the World", "gd73-06-10d3t01": "Johnny B. Goode",
}


def _with_tagged_lossless(md: dict, *, lossless_format: str = "Shorten",
                          tag_mp3: bool = False) -> dict:
    """The A3 shape: the mp3 derivatives carry no titles while the lossless
    originals of the SAME item are fully tagged, stems matching.

    The fixture's .shn entries have length=None, which filter_files excludes as
    'missing duration' - a length MUST be set here or the lossless set is empty
    and every assertion below becomes vacuous."""
    md = {"metadata": dict(md["metadata"]), "files": [dict(f) for f in md["files"]]}
    for f in md["files"]:
        stem = f["name"].rsplit(".", 1)[0]
        if f.get("format") == "VBR MP3" and not tag_mp3:
            f["title"] = None
        if f.get("format") == "Shorten":
            f["format"] = lossless_format
            f["length"] = "05:00"
            f["title"] = _LOSSLESS_TITLES.get(stem)
    return md


def test_the_tagged_lossless_helper_is_not_vacuous():
    """Guards the helper itself: if filter_files drops the lossless set, every
    recovery assertion below passes for a reason unrelated to recovery."""
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()))
    kept, _, _ = filter_files(md["files"], want_format="Shorten")
    assert len(kept) == 6


def test_gather_recovers_titles_from_the_lossless_sibling(tmp_path: Path):
    """The mp3 derivative carries no titles; the lossless originals of the same
    item are fully tagged. Measured at 166 of 1,444 two-format items."""
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()))
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    assert [t.title for t in show.tracks] == list(_LOSSLESS_TITLES.values())
    assert all(t.title_source == "sibling-format" for t in show.tracks)


def test_gather_recovers_from_24bit_flac(tmp_path: Path):
    """gd1971-02-23's shape: the lossless files are tagged '24bit Flac', which
    was invisible before the format-preference fix."""
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()),
                               lossless_format="24bit Flac")
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    assert [t.title for t in show.tracks] == list(_LOSSLESS_TITLES.values())
    assert all(t.title_source == "sibling-format" for t in show.tracks)


def test_gather_prefers_its_own_tags_when_they_are_good(tmp_path: Path):
    """Recovery must not fire on a healthy tape. The sibling titles are
    poisoned so a wrongly-firing recovery is visible rather than silent."""
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()), tag_mp3=True)
    for f in md["files"]:
        if f.get("format") == "Shorten":
            f["title"] = "WRONG"
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    assert "WRONG" not in [t.title for t in show.tracks]
    assert all(t.title_source != "sibling-format" for t in show.tracks)


def test_gather_declines_recovery_when_the_sibling_is_also_untagged(tmp_path: Path):
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()))
    for f in md["files"]:
        if f.get("format") == "Shorten":
            f["title"] = None
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    assert all(t.title_source != "sibling-format" for t in show.tracks)


def test_gather_declines_recovery_and_keeps_its_own_partial_tags(tmp_path: Path):
    """_RECOVER_SIBLING_ABOVE = 0.9, isolated. Own tags are partial - 2 of 6
    real, a 0.33 fraction, below _RECOVER_BELOW, so recovery IS attempted - and
    the lossless sibling is fully untagged, so the 0.9 floor must decline and
    format_titles must stay None.

    Asserted on title_source, never on the title: the gd73 description carries
    a real setlist, so the cascade supplies the right TITLE either way, which
    is exactly the false green this test exists to avoid. The discriminator is
    that the two tagged tracks read "tags". Delete the
    >= _RECOVER_SIBLING_ABOVE comparison and the all-empty recovered map stands
    in for the tag layer wholesale, suppressing both and dropping them to
    "setlist".

    Deliberately paired with test_gather_recovery_discards_usable_own_tags_
    wholesale: identical partially-tagged mp3 set, opposite sibling. That one
    has a fully TAGGED sibling and asserts every track reads "sibling-format";
    this one has a fully UNTAGGED sibling and asserts the own-tagged tracks
    read "tags". Together they pin both halves of "a manifest never interleaves
    two tag sources" - recovery fires wholesale, or it does not fire at all."""
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()))
    own_tagged = {"gd73-06-10d1t01.mp3": "Morning Dew", "gd73-06-10d2t01.mp3": "Dark Star"}
    for f in md["files"]:
        if f.get("format") == "Shorten":
            f["title"] = None
        if f["name"] in own_tagged:
            f["title"] = own_tagged[f["name"]]
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    by_name = {t.filename: t.title_source for t in show.tracks}
    assert [by_name[n] for n in own_tagged] == ["tags", "tags"]
    assert all(t.title_source != "sibling-format" for t in show.tracks)


def test_gather_recovery_discards_usable_own_tags_wholesale(tmp_path: Path):
    """Recovery replaces the tag layer WHOLESALE - a manifest never interleaves
    two tag sources. Own tags are partial (2 of 6 real, so recovery fires) and
    the lossless sibling is fully tagged, so all six tracks come back
    "sibling-format" INCLUDING the two whose own tags were perfectly usable.
    They are deliberately discarded.

    A gap-filling resolve_titles - own real tags win per track, recovered
    titles fill only the holes - passes every other recovery test in this file,
    because they all have zero usable own tags. It fails here twice over: those
    two tracks would read their own tag text and title_source "tags".

    Deliberately paired with test_gather_declines_recovery_and_keeps_its_own_
    partial_tags: identical partially-tagged mp3 set, opposite sibling (that
    one fully untagged so the 0.9 gate declines, this one fully tagged so
    recovery fires). Together they pin both halves of the rule."""
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()))
    own_tagged = {"gd73-06-10d1t01.mp3": "Own Tag Alpha", "gd73-06-10d2t01.mp3": "Own Tag Beta"}
    for f in md["files"]:
        if f["name"] in own_tagged:
            f["title"] = own_tagged[f["name"]]
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    assert all(t.title_source == "sibling-format" for t in show.tracks)
    assert [t.title for t in show.tracks] == list(_LOSSLESS_TITLES.values())


def test_gather_recovery_survives_an_operator_exclusion(tmp_path: Path):
    """overrides.exclude drops a file AFTER filtering. A positional recovery
    list would misalign every title after the hole; the filename-keyed map
    does not."""
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()))
    ws = ShowWorkspace(tmp_path / "show")
    write_artifact(ws.overrides, Overrides(exclude=["gd73-06-10d1t02.mp3"]))
    show = run_gather(ws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    assert [t.title for t in show.tracks] == [
        "Morning Dew", "I Know You Rider", "Dark Star",
        "Eyes of the World", "Johnny B. Goode",
    ]
    # Titles alone would still read correctly off the setlist; the source is
    # what says recovery is the layer that supplied them.
    assert all(t.title_source == "sibling-format" for t in show.tracks)


def test_readmitting_a_lossless_orphan_does_not_suppress_recovery(tmp_path: Path):
    """SYMMETRY FIX (2026-09-07). This test previously pinned the OPPOSITE
    behaviour and is deliberately inverted; its old body is the measurement
    that justified the change.

    `sibling_format_titles` requires an exact bijection in file COUNT between
    the delivered format and its lossless sibling, and FOLLOW-ME @BYPIKENO.mp3
    -- the fixture's junk file -- has no Shorten counterpart at all. When
    `_recover_format_titles` voted on the post-re-admission `kept`, re-admitting
    that one orphan took the mp3 side to 7 against the Shorten side's 6, the
    bijection declined, and `format_titles` came back None for the WHOLE tape:
    all six tracks that would have recovered cleanly lost "sibling-format"
    because of a file the operator asked to keep.

    Recording-level decisions now vote on `recovery_basis` -- the tape minus
    re-admissions -- so the six recover exactly as they do without the
    override. The orphan itself is absent from the recovered map and falls
    through the ordinary cascade: it gets no vote, and no free title."""
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()))
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, Overrides(include=["FOLLOW-ME @BYPIKENO.mp3"]))
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    by_name = {t.filename: t for t in show.tracks}
    assert "FOLLOW-ME @BYPIKENO.mp3" in by_name
    recovered = [t.filename for t in show.tracks if t.title_source == "sibling-format"]
    assert len(recovered) == 6, recovered
    assert "FOLLOW-ME @BYPIKENO.mp3" not in recovered


def test_including_a_file_that_was_never_dropped_keeps_its_vote(tmp_path: Path):
    """An `overrides.include` entry naming a file the junk filter never dropped
    re-admits nothing — but it must also take nothing away.

    The recording-level gates give re-admitted files no vote, and they decide
    that by asking `filter_files` what it ACTUALLY re-admitted, not by reading
    `overrides.include`. Filtering on the request instead would drop this
    already-kept file from `recovery_basis`, leaving 5 mp3s against 6 Shorten
    entries — `sibling_format_titles` declines on the count mismatch and the
    WHOLE tape loses recovery. That is the same defect the basis exists to
    prevent, re-entered from the other side, and silently: gather's "matched
    no file" warning cannot fire for a name that is in `kept`."""
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()))
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, Overrides(include=["gd73-06-10d1t01.mp3"]))
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    recovered = [t.filename for t in show.tracks if t.title_source == "sibling-format"]
    assert len(recovered) == 6, recovered


def test_readmission_does_not_stop_the_track_number_strip(tmp_path: Path):
    """The second recording-level gate, wired through `resolve_titles`'
    `gate_basis`. `clean_tag_titles` strips a leading track number only when
    the RECORDING looks enumerated (>=3 numbered files and >=80% coverage), so
    on a small tape one untagged re-admission drops coverage under the gate and
    would leave "01 " glued to every other track's title.

    Three numbered tracks plus the re-admitted junk file is 3 of 4 = 0.75,
    under _ENUMERATED_MIN_COVERAGE. Voting on the tape alone it is 3 of 3, so
    the strip still fires. Without gate_basis this test sees "01 Morning Dew"."""
    md = json.loads(FIXTURE.read_text())
    names = ["gd73-06-10d1t01.mp3", "gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3"]
    songs = {names[0]: "Morning Dew", names[1]: "China Cat Sunflower",
             names[2]: "I Know You Rider"}
    for f in md["files"]:
        if f["name"] in songs:
            f["title"] = f"0{names.index(f['name']) + 1} {songs[f['name']]}"
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, Overrides(
        include=["FOLLOW-ME @BYPIKENO.mp3"],
        exclude=["gd73-06-10d2t01.mp3", "gd73-06-10d2t02.mp3", "gd73-06-10d3t01.mp3"]))
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    by_name = {t.filename: t.title for t in show.tracks}
    assert [by_name[n] for n in names] == [
        "Morning Dew", "China Cat Sunflower", "I Know You Rider"]


def _jb_event(closers_and_names, venue="V", city="C", state="ST"):
    return JerrybaseEvent(
        event_id="1", venue=venue, city=city, state=state,
        sets=[JerrybaseSet(name=n, closer=c, break_length="long")
              for c, n in closers_and_names],
    )


def test_gather_multi_event_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [
        _jb_event([("I Know You Rider", "1")], venue="Fillmore East"),
        _jb_event([("Johnny B. Goode", "1")], venue="Fillmore East"),
    ])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.needs_review is True
    assert any(f.startswith("multi-event date: 2 jerrybase events") for f in show.review_flags)


def test_gather_adopts_venue_when_candidate_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("I Know You Rider", "1"), ("Eyes of the World", "2"),
         ("Johnny B. Goode", "encore")],
        venue="Barton Hall", city="Ithaca")])
    cand = make_candidate()
    cand.venue = None
    cand.city = None
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), cand, IDENT, jerrybase_enabled=True)
    assert show.venue == "Barton Hall"
    assert show.city == "Ithaca"
    assert show.venue_source == "jerrybase"
    assert show.needs_review is False


def test_gather_flags_venue_mismatch_never_overwrites(tmp_path, monkeypatch):
    # A genuinely different venue must still trip the flag, and never overwrite
    # the candidate's venue.
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("I Know You Rider", "1"), ("Eyes of the World", "2"),
         ("Johnny B. Goode", "encore")],
        venue="Boston Garden", city="Boston")])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.venue == "RFK Stadium"          # candidate venue preserved
    assert show.venue_source == "item"
    assert any("venue mismatch" in f for f in show.review_flags)


def test_gather_venue_equivalent_passes_no_mismatch(tmp_path, monkeypatch):
    # Spec integration test: archive "RFK Stadium" vs jerrybase "Robert F.
    # Kennedy Stadium" is a high-confidence equivalence -> no mismatch flag.
    # Slice 1 step 1 also requires compatible cities, so the event carries the
    # candidate's real state ("Washington, DC"), not _jb_event's "ST".
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("I Know You Rider", "1"), ("Eyes of the World", "2"),
         ("Johnny B. Goode", "encore")],
        venue="Robert F. Kennedy Stadium", city="Washington", state="DC")])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.venue == "RFK Stadium"          # never overwritten
    assert show.venue_source == "item"
    assert not any("venue mismatch" in f for f in show.review_flags)
    assert show.needs_review is False


def test_gather_anchors_over_a_confident_but_contradicted_alignment(tmp_path, monkeypatch):
    # gd73 aligns confidently to sets 1,1,1,2,2,encore (breaks [3,5]) — coverage
    # far above align_coverage_threshold. Jerrybase says set 1 ends on China Cat
    # Sunflower (track 2). Anchoring is no longer gated on low coverage, so it
    # runs and CORRECTS the breaks instead of merely flagging them. This is the
    # gd1973-08-01 failure shape: an alignment too good to trip the old gate.
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("China Cat Sunflower", "1"), ("Eyes of the World", "2"),
         ("Johnny B. Goode", "encore")])])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.structure is not None and show.structure.alignment == "jerrybase"
    assert show.set_breaks == [2, 5]
    # The tripwire is silent: anchoring places breaks at closers by construction.
    assert not any("set break" in f for f in show.review_flags)
    # ...so the overridden breaks are recorded instead, or a mis-anchor on a
    # high-coverage show would ship with no trace at all.
    assert any("anchored from jerrybase (was [3, 5])" in c
               for c in show.structure.conflicts)


def test_gather_tripwire_still_flags_when_anchoring_fails(tmp_path, monkeypatch):
    # Same contradiction, but one closer is absent from the tape, so anchoring
    # cannot run. The closer tripwire is what remains — and it still speaks.
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("China Cat Sunflower", "1"), ("Zzz Never Played", "2")])])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.structure is not None and show.structure.alignment != "jerrybase"
    assert show.needs_review is True
    assert any("China Cat Sunflower" in f and "set break" in f for f in show.review_flags)


def test_gather_anchors_a_tape_with_no_setlist_parse(tmp_path, monkeypatch):
    # No description -> no canonical setlist at all. Anchoring used to be
    # unreachable in that state; jerrybase evidence alone can now structure it.
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = ""
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("China Cat Sunflower", "1"), ("Eyes of the World", "2")])])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.structure is not None and show.structure.alignment == "jerrybase"
    assert show.set_breaks == [2]


def test_gather_flags_set_count_mismatch(tmp_path, monkeypatch):
    # jerrybase says 3 numbered sets; the tape aligns to 2 numbered sets (plus an
    # encore) -> genuine set-count mismatch. Fake closers (absent from the tape)
    # keep anchoring from running so this exercises the count comparison only.
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("Zzz One", "1"), ("Zzz Two", "2"), ("Zzz Three", "3")])])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert any("jerrybase shows 3" in f for f in show.review_flags)


def test_gather_set_count_ignores_encore(tmp_path, monkeypatch):
    # jerrybase says 2 sets; the tape has 2 numbered sets + an encore. That is NOT
    # a mismatch — an encore is a coda, not a set — so no set-count flag fires.
    # These closers are real gd73 titles, so anchoring now runs; the count still
    # matches only because the encore guard keeps the tape's trailing encore
    # instead of absorbing it into set 2 (jerrybase has no encore row here).
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("I Know You Rider", "1"), ("Johnny B. Goode", "2")])])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.structure is not None and show.structure.alignment == "jerrybase"
    assert [t.set for t in show.tracks][-1] == "encore"   # encore guard held
    assert not any("jerrybase shows" in f for f in show.review_flags)


def test_gather_anchoring_rescues_low_confidence_without_llm(tmp_path, monkeypatch):
    md = json.loads(FIXTURE.read_text())
    # Replace the description with a DIFFERENT setlist so deterministic alignment
    # covers almost nothing (low confidence) while the real tag titles remain.
    md["metadata"]["description"] = (
        "Set 1:\nBertha\nJack Straw > Deal\n\n"
        "Set 2:\nTruckin > Wharf Rat\n\nEncore:\nOne More Saturday Night\n")
    # jerrybase closers reference the real tag titles; anchoring breaks after
    # China Cat Sunflower (track 2) and Eyes of the World (track 5).
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("China Cat Sunflower", "1"), ("Eyes of the World", "2")])])
    sws = ShowWorkspace(tmp_path / "show")
    fake_align = FakeProvider()
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT,
                      align_provider=fake_align, jerrybase_enabled=True)
    assert fake_align.calls == []  # anchoring short-circuited the LLM fallback
    # Task 4 (lookahead bumped 3->8): the fixture's untitled disc-3 track
    # resolves to "One More Saturday Night", which is ALSO the fake
    # description's own encore item - at the shipped lookahead=8 the
    # deterministic pass reaches far enough (skip=5) to match it directly,
    # correctly labeling that one track "encore" even though every other
    # track still misses. That single correct match is what feeds jerrybase
    # anchoring's encore guard (`aligned_sets`, jerrybase.anchor_breaks),
    # which restores the trailing encore break the closer-only anchoring
    # would otherwise fold into set "2" - so set_breaks now surfaces BOTH
    # breaks the closers above describe, not just the first. At the pre-bump
    # lookahead=3 this track was unreachable (skip=5 > lookahead=3) and
    # set_breaks was [2] alone - see test_tail_guard_never_declines_a_
    # legitimate_one_item_skip_at_the_shipped_default in test_structure.py
    # for the general shape of this exact kind of far, legitimate, low-skip
    # tail match.
    assert show.set_breaks == [2, 5]
    assert show.structure is not None and show.structure.alignment == "jerrybase"
    assert any(c.startswith("set breaks anchored from jerrybase")
               for c in show.structure.conflicts)
    assert "low-confidence structure alignment" not in show.review_flags


def test_gather_records_soft_closer_notes_without_setlist_parse(tmp_path, monkeypatch):
    # Empty description -> no LMA parse and no LLM fallback (best is None), so
    # tracks resolve from the fixture's tags. A jerrybase closer absent from the
    # tracks must still be recorded as a soft note despite there being no
    # setlist source.
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = ""
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("Truckin", "1")], venue="RFK Stadium")])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.structure is not None
    assert show.structure.source == "none"
    assert any("Truckin" in c and "not found in tracks" in c
               for c in show.structure.conflicts)


def test_gather_jerrybase_disabled_is_noop(tmp_path, monkeypatch):
    def _boom(a, d):
        raise AssertionError("lookup must not be called when disabled")
    monkeypatch.setattr(jerrybase, "lookup", _boom)
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=False)
    assert show.needs_review is False
    assert show.venue_source == "item"


def _event_candidate(suffix):
    c = make_candidate()
    c.performance_id = f"GratefulDead/1973-06-10/{suffix}"
    return c


def test_gather_event_suffix_selects_right_event(tmp_path, monkeypatch):
    # e2's closers are gd73's real set-ends; e1's are songs gd73 never played.
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [
        _jb_event([("Bertha", "1"), ("Truckin", "2")], venue="Fillmore East", city="New York"),
        _jb_event([("I Know You Rider", "1"), ("Eyes of the World", "2"),
                   ("Johnny B. Goode", "encore")], venue="Fillmore West", city="San Francisco"),
    ])
    cand = _event_candidate("e2")
    cand.venue = None
    cand.city = None
    show = run_gather(ShowWorkspace(tmp_path / "s"), StubIA(), FakeProvider(), cand, IDENT,
                      jerrybase_enabled=True)
    assert show.venue == "Fillmore West"          # events[1] selected, not events[0]
    assert show.venue_source == "jerrybase"
    assert not any(f.startswith("multi-event date") for f in show.review_flags)
    assert not any("tape spans" in f for f in show.review_flags)
    assert show.needs_review is False


def test_gather_flags_tape_that_spans_events(tmp_path, monkeypatch):
    # /e1 candidate, but tracks carry closers from BOTH events -> mislabeled tape.
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [
        _jb_event([("I Know You Rider", "1"), ("Eyes of the World", "2"),
                   ("Johnny B. Goode", "encore")]),
        _jb_event([("Morning Dew", "1")]),
    ])
    show = run_gather(ShowWorkspace(tmp_path / "s"), StubIA(), FakeProvider(),
                      _event_candidate("e1"), IDENT, jerrybase_enabled=True)
    assert show.needs_review is True
    assert "tape spans 2 events" in show.review_flags


def test_gather_spans_candidate_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [
        _jb_event([("Turn On Your Lovelight", "1")]),
        _jb_event([("And We Bid You Good Night", "1")]),
    ])
    show = run_gather(ShowWorkspace(tmp_path / "s"), StubIA(), FakeProvider(),
                      _event_candidate("spans"), IDENT, jerrybase_enabled=True)
    assert show.needs_review is True
    assert "tape spans 2 events" in show.review_flags


def test_gather_unassigned_candidate_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [
        _jb_event([("Turn On Your Lovelight", "1")]),
        _jb_event([("And We Bid You Good Night", "1")]),
    ])
    show = run_gather(ShowWorkspace(tmp_path / "s"), StubIA(), FakeProvider(),
                      _event_candidate("unassigned"), IDENT, jerrybase_enabled=True)
    assert show.needs_review is True
    assert "unassigned multi-event recordings" in show.review_flags


def test_gather_drops_operator_excluded_file(tmp_path: Path):
    # First derive normally to learn a real filename.
    base = ShowWorkspace(tmp_path / "base")
    show0 = run_gather(base, StubIA(), FakeProvider(), make_candidate(), IDENT)
    drop = show0.tracks[-1].filename
    n = len(show0.tracks)

    ws = ShowWorkspace(tmp_path / "show")
    write_artifact(ws.overrides, Overrides(exclude=[drop]))
    show = run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)

    assert drop not in [t.filename for t in show.tracks]
    assert len(show.tracks) == n - 1
    assert [t.index for t in show.tracks] == list(range(1, n))  # contiguous
    assert any(x["filename"] == drop and "operator-excluded" in x["reasons"]
               for x in show.excluded_files)


def test_gather_exclude_no_match_warns_and_is_noop(tmp_path: Path, caplog):
    ws = ShowWorkspace(tmp_path / "show")
    write_artifact(ws.overrides, Overrides(exclude=["does-not-exist.mp3"]))
    with caplog.at_level("WARNING", logger="llama"):
        show = run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert len(show.tracks) == 6
    assert any("matched no file" in r.message for r in caplog.records)


def test_gather_title_override_forces_title(tmp_path: Path):
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(titles={"gd73-06-10d1t01.mp3": "Custom Opener"}))
    show = run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert show.tracks[0].title == "Custom Opener"
    assert show.tracks[0].title_source == "override"
    # the gd73 fixture resolves all titles, so no unresolved-titles hold exists;
    # an override can only ever remove such a flag, never add one.
    assert "unresolved track titles" not in show.review_flags


def test_gather_title_override_out_of_range_errors(tmp_path: Path):
    from llama.errors import LlamaError
    ws = ShowWorkspace(tmp_path / "s")
    # A title naming a file not in the track list (spec 4.1: the dangling refusal).
    write_artifact(ws.overrides, Overrides(titles={"gd73-06-10d9t99.mp3": "Nope"}))
    with pytest.raises(LlamaError, match="overrides name files not in the track list"):
        run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)


def test_gather_venue_city_date_overrides(tmp_path: Path):
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(venue="My Hall", city="Nowhere, ZZ",
                                           date="1973-06-11"))
    show = run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert show.venue == "My Hall" and show.venue_source == "override"
    assert show.city == "Nowhere, ZZ"
    assert show.date == "1973-06-11" and show.date_source == "override"
    assert show.item_date == "1973-06-10"   # original preserved


def test_gather_set_breaks_override_numbers_sets(tmp_path: Path):
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(set_breaks=["gd73-06-10d1t02.mp3",
                                                       "gd73-06-10d2t01.mp3"]))
    show = run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    # 6-track fixture -> sets: 1,1 | 2,2 | 3,3
    assert [t.set for t in show.tracks] == ["1", "1", "2", "2", "3", "3"]
    assert show.set_breaks == [2, 4]
    assert show.structure is not None and show.structure.alignment == "override"
    assert "low-confidence structure alignment" not in show.review_flags


def test_gather_set_breaks_out_of_range_errors(tmp_path: Path):
    from llama.errors import LlamaError
    ws = ShowWorkspace(tmp_path / "s")
    # A break after the last track is out of range (gd73 has 6 tracks).
    write_artifact(ws.overrides, Overrides(set_breaks=["gd73-06-10d3t01.mp3"]))
    with pytest.raises(LlamaError, match="out of range"):
        run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)


def test_gather_flags_a_merged_track_spanning_a_set_break(tmp_path: Path):
    """A merged track whose components land in different sets must hold the
    show rather than ship: the parse is provably wrong."""
    # The gd73 fixture's canonical setlist breaks between "I Know You Rider"
    # (end of set 1) and "Dark Star" (start of set 2). Retag the d1t03 track
    # (tagged "I Know You Rider") as though the taper merged it onto the next
    # set's opener across the actual intermission break.
    md = json.loads(FIXTURE.read_text())
    for f in md["files"]:
        if f.get("name") == "gd73-06-10d1t03.mp3":
            f["title"] = "I Know You Rider > Dark Star"
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    assert show.needs_review
    assert any("span a set break" in f for f in show.review_flags)


def test_gather_does_not_apply_dead_shorthand_for_a_non_family_artist(tmp_path: Path):
    """`aliases = GD_SHORTHAND if jerrybase.is_family_artist(artist) else {}`
    (gather.py) must be exercised end-to-end: `is_family_artist` and
    `align(aliases=...)` are each unit-tested separately, but nothing pinned
    their composition, and every other gather fixture's creator is "Grateful
    Dead" so the `else {}` branch never ran under any existing test."""
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["creator"] = "Phish"  # not in jerrybase's Garcia-universe family
    md["metadata"]["description"] = (
        "Set 1:\nTruckin'\n\nSet 2:\nScarlet Begonias\n\nEncore:\nJohnny B. Goode"
    )
    retitle = {
        "gd73-06-10d1t01.mp3": "Truckin'",
        "gd73-06-10d1t02.mp3": "Scarlet",   # taper shorthand for "Scarlet Begonias"
        "gd73-06-10d1t03.mp3": "Drums",
        "gd73-06-10d2t01.mp3": "Space",
        "gd73-06-10d2t02.mp3": "Jam",
        "gd73-06-10d3t01.mp3": "Johnny B. Goode",
    }
    for f in md["files"]:
        if f.get("name") in retitle:
            f["title"] = retitle[f["name"]]
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    assert show.artist == "Phish"
    # Without GD_SHORTHAND, "Scarlet" cannot resolve to "Scarlet Begonias" —
    # a bare word can only fuzzy-match a two-plus-word canonical title via the
    # shorthand alias table, and that table must not apply here. The track
    # stays unmatched and inherits the previous track's set instead of
    # advancing into set 2. (If the family gate were bypassed and
    # GD_SHORTHAND applied unconditionally, "Scarlet" would normalize to
    # "scarlet begonias", match exactly, and this track would land in set
    # "2" with "Scarlet Begonias" absent from the conflicts below — this
    # test fails under that hypothetical.)
    assert show.tracks[1].title == "Scarlet"
    assert show.tracks[1].set == "1"
    assert show.structure is not None
    assert "Scarlet Begonias" in show.structure.conflicts


MCCOURY_SONGS = ["Rain and Snow", "Nashville Cats", "1952 Vincent Black Lightning",
                 "Blue Side of Town", "Get Down On Your Knees and Pray", "All Aboard"]


def _mccoury_md(tagged: bool):
    """gd73 fixture restaged as a Del McCoury Band tape whose description opens
    with the band name on its own line — the shape ~90 corpus rows actually
    have. The song list is unmarked and single-set on purpose: a preamble ahead
    of an explicit "Set 1:" marker is discarded by the parser, so the header
    only survives as an item when there is no marker, which is exactly the case
    this filter exists for (and the non-Dead corpus is ~91% single-set).

    `tagged=False` strips every file's title tag, which is the common case for
    these same rows and the one that makes the header item actively harmful:
    it breaks `titles.resolve_titles`' `len(items) == n` gate."""
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["creator"] = "Del McCoury Band"
    md["metadata"]["description"] = (
        "Del McCoury Band\n" + "\n".join(MCCOURY_SONGS) + "\n")
    names = ["gd73-06-10d1t01.mp3", "gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3",
             "gd73-06-10d2t01.mp3", "gd73-06-10d2t02.mp3", "gd73-06-10d3t01.mp3"]
    retitle = dict(zip(names, MCCOURY_SONGS))
    for f in md["files"]:
        if f.get("name") in retitle:
            if tagged:
                f["title"] = retitle[f["name"]]
            else:
                f.pop("title", None)
    return md


def test_gather_drops_setlist_items_that_are_the_artist_name(tmp_path: Path):
    """A description header line ("Del McCoury Band") parses as a song. It can
    never match a track and it inflates the setlist, pushing the two-pointer
    behind until later songs fall outside the lookahead window."""
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(_mccoury_md(tagged=True)), FakeProvider(),
                      make_candidate(), IDENT)
    assert show.artist == "Del McCoury Band"
    assert [t.title for t in show.tracks] == MCCOURY_SONGS
    assert show.structure is not None
    # Without the filter the artist item survives as a seventh canonical item
    # that no track can ever match, and lands in conflicts.
    assert "Del McCoury Band" not in show.structure.conflicts
    assert all("mccoury" not in c.lower() for c in show.structure.conflicts)
    assert show.structure.conflicts == []


def test_gather_artist_item_does_not_block_title_resolution(tmp_path: Path):
    """The artist header must be dropped BEFORE the title rungs, not merely
    before `align`.

    With no title tags — the common case for exactly the rows this targets —
    the description is the only title source (this candidate has no sibling
    recording). Since title hygiene (piece 3) the description's own list is
    read by reader (ii), which exempts the artist line, and D fills all six
    tracks as `desc-position` (spec slice 1 "S with a `chosen` canonical",
    slice 2, Q1). The `enabled_slices=frozenset()` arm at the end keeps
    guarding `build_canonical`'s artist drop: there the whole-tape `setlist`
    rung fills only when the canonical's item count equals the track count, so
    a surviving header item (7 != 6) would leave every title "unresolved".
    (At the head of the list `_strip_head_banner` already removes it, since
    the artist is in `metadata_norms`; removing `_drop_artist_items` alone
    leaves this test green, removing both reddens it -- measured, Task 16
    fix round 1.)

    `matched` is None on every track (`desc-position`, like `setlist`, is in
    TAUTOLOGICAL_TITLE_SOURCES): the independent-evidence set _songish_coverage computes
    over is empty and coverage is the safe-direction 0.0. Before Task 17 that raised
    "low-confidence structure alignment" (the titles came entirely from the list the tape is
    checked against); spec Q2 now exempts a self-filled tape, so the show ships clean.

    Round 2 (review): `matched` is ALSO None on every track now, not just
    excluded from coverage's denominator -- gather.py's final assembly
    tests membership in the same TAUTOLOGICAL_TITLE_SOURCES constant
    _songish_coverage filters on, rather than naming "setlist-gap" alone,
    so a "setlist"-sourced track can no longer report matched=True (an
    independent match that never happened) while simultaneously being
    excluded from coverage as tautological -- the two signals describe the
    same fact and must agree."""
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(_mccoury_md(tagged=False)), FakeProvider(),
                      make_candidate(), IDENT)
    assert [t.title for t in show.tracks] == MCCOURY_SONGS
    # Title hygiene (piece 3): spec slice 1 "S with a `chosen` canonical", slice 2 (D) and
    # operator ruling Q1. The description's one-per-line list is admissible (reader (ii),
    # the artist line exempt) and count-matched, so S no longer fills; D does, all six,
    # as `desc-position` (also tautological, so `matched` stays None below). The
    # low-confidence assertion below changes only with Q2 (Task 17).
    assert all(t.title_source == "desc-position" for t in show.tracks)
    assert not any("unresolved" in f for f in show.review_flags)
    assert show.structure is not None
    assert show.structure.conflicts == []
    assert show.structure.coverage == 0.0
    # Spec Q2 (Task 17): every song-like track is `desc-position` and D passed, so the tape
    # is self-filled: no low-confidence flag, no hold.
    assert show.review_flags == []
    assert show.needs_review is False
    assert all(t.matched is None for t in show.tracks)

    # Today's rungs (no slices): the S rung fills all six from the canonical, which it
    # can only do because build_canonical dropped the artist item (7 != 6 otherwise;
    # see the docstring for which cleaning step drops it here).
    today = compute_gather(ShowWorkspace(tmp_path / "today"), StubIA(_mccoury_md(tagged=False)),
                           FakeProvider(), make_candidate(), IDENT,
                           enabled_slices=frozenset())
    assert [(t.title, t.title_source) for t in today.show.tracks] == [
        (s, "setlist") for s in MCCOURY_SONGS]


# --- Head-banner guard (spec 1b) -------------------------------------------

def _parsed(*titles: str) -> ParsedSetlist:
    return ParsedSetlist(
        items=[SetlistItem(title=t, normalized=normalize_song(t), set="1")
               for t in titles],
        confidence="high",
    )


def _norms(*values: str) -> set[str]:
    return {fuzzy_norm_title(v) for v in values}


def _titles(parsed: ParsedSetlist) -> list[str]:
    return [i.title for i in parsed.items]


def test_head_banner_strip_is_bounded_to_the_head_span():
    """The metadata span is searched in the first `_HEAD_K` items only.

    A song can legitimately be named after the city ("El Paso") — the bound is
    what keeps such a title from dragging the strip point down over the real
    songs above it. Without the bound this show loses every song: the banner is
    big enough that the coincidental match at index 11 still clears the majority
    rule, so the whole setlist is inside the span and the whole setlist goes."""
    norms = _norms("Grateful Dead", "The Fillmore West", "Fillmore West",
                   "San Francisco", "November 8 1970", "11/8/1970", "El Paso")
    parsed = _parsed(
        "Grateful Dead", "The Fillmore West", "Fillmore West",
        "San Francisco", "November 8 1970", "11/8/1970",
        "Casey Jones", "Me And My Uncle", "Big Railroad Blues",
        "Dire Wolf", "Truckin", "El Paso",
    )
    kept = _titles(_strip_head_banner(parsed, norms))
    assert kept == ["Casey Jones", "Me And My Uncle", "Big Railroad Blues",
                    "Dire Wolf", "Truckin", "El Paso"]


def test_head_banner_needs_a_metadata_majority():
    """A lone coincidental match must not eat the real songs above it.

    "Nashville" is both this show's city and a song title. It is the only
    metadata-looking item in the span it would define, so the span is not a
    banner and nothing is stripped."""
    norms = _norms("Nashville")
    parsed = _parsed("Bertha", "Jack Straw", "Deal", "Nashville",
                     "Sugaree", "Ripple")
    kept = _titles(_strip_head_banner(parsed, norms))
    assert kept == ["Bertha", "Jack Straw", "Deal", "Nashville",
                    "Sugaree", "Ripple"]


def test_head_chatter_run_stops_after_a_gap_of_two():
    """The stage-2 run tolerates a gap of at most `_HEAD_GAP` unrecognized
    items. Three real songs between two chatter lines end the run: an unbounded
    gap would swallow all of them to reach the later chatter line."""
    parsed = _parsed(
        "Source: Nakamichi CM-300",
        "Wharf Rat", "Franklins Tower", "Estimated Prophet",
        "24 bit / 48 khz",
        "Eyes Of The World", "Sugar Magnolia",
    )
    kept = _titles(_strip_head_banner(parsed, set()))
    assert kept == ["Wharf Rat", "Franklins Tower", "Estimated Prophet",
                    "24 bit / 48 khz", "Eyes Of The World", "Sugar Magnolia"]


def test_artist_items_are_dropped_anywhere_not_just_at_the_head():
    """The artist drop is global, unlike the banner strip. Tapers repeat the
    band name at a set break as often as they put it at the top, and unlike a
    venue name an artist name is never a plausible song title on that artist's
    own tape.

    The artist item sits at index 12, PAST `_HEAD_K`. That placement is the
    test: with it at index 4 the prescribed mutation (scoping the drop to the
    head) left the whole suite green, because the banner strip's own head span
    still reached it. A mutation table is code and needs the same scrutiny as
    the tests it validates."""
    norms = _norms("Grateful Dead")
    parsed = _parsed("Bertha", "Jack Straw", "Deal", "Sugaree", "Ripple",
                     "Casey Jones", "Truckin", "Dire Wolf", "Loser",
                     "Big River", "Brown Eyed Women", "Sugar Magnolia",
                     "Grateful Dead", "Uncle Johns Band")
    cleaned = _drop_artist_items(_strip_head_banner(parsed, norms), "Grateful Dead")
    assert "Grateful Dead" not in _titles(cleaned)
    assert _titles(cleaned) == [
        "Bertha", "Jack Straw", "Deal", "Sugaree", "Ripple", "Casey Jones",
        "Truckin", "Dire Wolf", "Loser", "Big River", "Brown Eyed Women",
        "Sugar Magnolia", "Uncle Johns Band"]


def test_footnote_markers_are_stripped_from_the_tail_only():
    """Trailing description apparatus goes; the title is otherwise
    byte-identical. Runs of markers ("* ^", "* # $") are one match, and a
    marker character INSIDE a title is untouched -- these are footnote keys
    ("* with Sam Bush" further down the description), not song names, and they
    otherwise ride into the manifest's ID3 title frame."""
    parsed = _parsed("Polly Put The Kettle On * ^", "Get Me Outta This City # %",
                     "High Lonesome Sound * # $", "Tear Down The Grand Ole Opry @",
                     "Steep Grade Sharp Curves *", "Cash $ Money",
                     "Money For Nothing")
    assert _titles(_strip_footnote_markers(parsed)) == [
        "Polly Put The Kettle On", "Get Me Outta This City",
        "High Lonesome Sound", "Tear Down The Grand Ole Opry",
        "Steep Grade Sharp Curves", "Cash $ Money", "Money For Nothing"]


def test_footnote_strip_leaves_a_marker_free_setlist_untouched():
    """No marker anywhere means the same object back -- the strip is apparatus
    removal, not a normalization pass, so it must not rewrite titles it has no
    business touching."""
    parsed = _parsed("Bertha", "Jack Straw", "Deal")
    assert _strip_footnote_markers(parsed) is parsed


def test_footnote_strip_never_eats_a_title_ending_in_a_marker_character():
    """THE LEADING WHITESPACE BOUND, pinned. A footnote marker is written as a
    separate token; a title character is not. Relaxing `_FOOTNOTE_TAIL`'s
    leading `\\s+` to `\\s*` turns "100%" into "100" and "Ke$ha $" style
    residue into nonsense -- the same failure mode as widening
    `titles._TRACK_NUM_PREFIX` past `\\d{1,3}`, which is why that bound has its
    own pin."""
    parsed = _parsed("100%", "Cost Of Living$", "Track#1")
    assert _titles(_strip_footnote_markers(parsed)) == [
        "100%", "Cost Of Living$", "Track#1"]


def test_footnote_strip_never_empties_a_title():
    """An item that is nothing BUT markers is left alone. An empty title is
    not a better outcome than a junk one: `align()` and `_window_match` treat
    an empty norm as a wildcard that can match any junk track, which is the
    exact hazard `structure.py`'s duration-strip fallback documents."""
    parsed = _parsed("* ^", "Deal")
    assert _titles(_strip_footnote_markers(parsed)) == ["* ^", "Deal"]


def test_footnote_strip_leaves_normalized_alone_because_it_cannot_differ():
    """`normalized` is not recomputed, and provably need not be:
    `normalize_song` already strips every non-alphanumeric character, so the
    stored norm of a marked title equals the norm of its stripped form. Pinned
    because `blend_segues` pools items on `normalized` -- if this ever stopped
    holding, the strip would silently move segues."""
    parsed = _parsed("High Lonesome Sound * # $")
    out = _strip_footnote_markers(parsed)
    assert out.items[0].title == "High Lonesome Sound"
    assert out.items[0].normalized == parsed.items[0].normalized
    assert out.items[0].normalized == normalize_song("High Lonesome Sound")


def test_head_chatter_never_matches_fade_titles():
    """MEASURED HAZARD: `fades?` in the chatter lexicon matches the word *Fade*
    and stripped the heads of "Not Fade Away" and "West L.A. Fade Away". The
    token is excluded, and this test is what says so."""
    norms = _norms("Grateful Dead", "Winterland")
    parsed = _parsed("Grateful Dead", "Winterland",
                     "Not Fade Away", "West L.A. Fade Away",
                     "Goin Down The Road Feeling Bad", "Sugar Magnolia")
    kept = _titles(_strip_head_banner(parsed, norms))
    assert kept == ["Not Fade Away", "West L.A. Fade Away",
                    "Goin Down The Road Feeling Bad", "Sugar Magnolia"]


def test_head_chatter_never_matches_bare_annotation_markers():
    """MEASURED HAZARD: bare `@` / `~` / `#` are the annotation markers Dead
    tapers hang off titles, not chatter. The lexicon anchors them positionally
    ("@ <digits>", leading `~`) so a marked-up song title survives."""
    norms = _norms("Grateful Dead", "Winterland")
    parsed = _parsed("Grateful Dead", "Winterland",
                     "Peggy-O @", "Raise The Roof #",
                     "China Cat Sunflower", "I Know You Rider")
    kept = _titles(_strip_head_banner(parsed, norms))
    assert kept == ["Peggy-O @", "Raise The Roof #",
                    "China Cat Sunflower", "I Know You Rider"]


def test_gather_strips_a_taper_banner_using_this_shows_own_metadata(tmp_path: Path):
    """End-to-end wiring: the vocabulary comes from `candidate.venue`,
    `candidate.city`, `candidate.date` and the item's creator — nothing here is
    a gazetteer, and the parser never sees any of it.

    Without the strip the six banner items sit at the head of the canonical
    setlist, where `align`'s two-pointer starts, and the show aligns 0/6."""
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["creator"] = "Del McCoury Band"
    md["metadata"]["coverage"] = "Washington, DC"
    md["metadata"]["description"] = (
        "Del McCoury Band\n"
        "RFK Stadium\n"
        "Washington\n"
        "DC\n"
        "June 10, 1973\n"
        "Source: Nakamichi CM-300 > Sony D8\n"
        + "\n".join(MCCOURY_SONGS) + "\n"
    )
    names = ["gd73-06-10d1t01.mp3", "gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3",
             "gd73-06-10d2t01.mp3", "gd73-06-10d2t02.mp3", "gd73-06-10d3t01.mp3"]
    for f in md["files"]:
        if f.get("name") in dict(zip(names, MCCOURY_SONGS)):
            f["title"] = dict(zip(names, MCCOURY_SONGS))[f["name"]]
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    assert [t.title for t in show.tracks] == MCCOURY_SONGS
    assert show.structure is not None
    assert show.structure.coverage == 1.0
    assert show.structure.conflicts == []


def test_gear_model_chatter_discriminates_on_position_not_letter_count():
    """A taper track prefix and a gear model are the SAME lexical shape —
    letters then digits. What separates them is POSITION: the prefix opens the
    item, the model is named inside one.

    Both directions matter and both are load-bearing. Discriminating on letter
    count instead (requiring ≥2 letters everywhere) was measured at −59 matched
    tracks and four shows to zero, because single-letter model numbers are real
    and common gear."""
    prefixes = ["t01) Shimmy She Wobble", "d101", "A01.", "B07.", "t02"]
    for title in prefixes:
        assert not _HEAD_CHATTER.search(title), f"{title!r} is a track prefix, not gear"
    gear = ["Telefunken M62 Hypercards Zoom F3", "Sony PCM-M10(24/96))",
            "mz-m200", "SKM140", "DR-70D", "SD722"]
    for title in gear:
        assert _HEAD_CHATTER.search(title), f"{title!r} is gear and must stay chatter"


def test_a_leading_track_prefix_does_not_start_a_chatter_run():
    """The whole point of the discrimination, at the level that costs songs: an
    enumerated tracklist whose every line opens with a taper prefix used to be
    chatter from end to end, so stage 2 — which has no cap — ate the entire
    setlist. Seven corpus shows were stripped to zero items that way."""
    parsed = _parsed("t01) Shimmy She Wobble", "t02) Goin' Down South",
                     "t03) Snake Drive", "t04) Drop Down Mama",
                     "t05) Lord Have Mercy")
    assert len(_strip_head_banner(parsed, set()).items) == 5


def test_a_declined_metadata_match_still_eats_songs_within_the_hop():
    """The majority rule bounds STAGE 1 ONLY.

    `is_chatter` includes `is_meta`, so this show's own metadata is a stage-2
    hop target — and stage 2 has neither `_HEAD_K` nor the majority rule. Here
    stage 1 explicitly DECLINES "Nashville" (one metadata item in a span of
    four is not a majority), and stage 2 hops to it anyway and takes the two
    songs above it.

    This pins current behaviour, which is a defect filed for 4b, not a
    property worth keeping. The fixture deliberately puts the coincidence
    WITHIN `_HEAD_GAP` of the head: `test_head_banner_needs_a_metadata_majority`
    sits one position past the hop's reach and so cannot see any of this."""
    norms = _norms("Nashville")
    assert _titles(_strip_head_banner(
        _parsed("Bertha", "Nashville", "Sugaree", "Ripple"), norms)) == [
        "Sugaree", "Ripple"]
    assert _titles(_strip_head_banner(
        _parsed("Bertha", "Jack Straw", "Nashville", "Sugaree", "Ripple"), norms)) == [
        "Sugaree", "Ripple"]
    # Gap 3 exceeds _HEAD_GAP, so the same coincidence is harmless one step
    # further down — the whole difference between the two tests.
    assert _titles(_strip_head_banner(
        _parsed("Bertha", "Jack Straw", "Deal", "Nashville", "Sugaree"), norms)) == [
        "Bertha", "Jack Straw", "Deal", "Nashville", "Sugaree"]


def test_a_wiped_setlist_is_flagged_for_review_not_shipped_silently(tmp_path: Path):
    """PRODUCT INVARIANT. `run_gather`'s low-coverage branch is guarded by
    `elif canonical.items and ...`, so an empty canonical short-circuits it and
    the show would otherwise ship with coverage 0.0, zero flags and
    needs_review False — strictly quieter than the same show with a
    bad-but-non-empty setlist, which IS flagged.

    This description is pure banner: band, venue, city, state, date, rig. The
    guard correctly removes all of it, and the show must then be held, not
    shipped.

    The tracks keep their title tags ON PURPOSE. Untagged files raise
    "unresolved track titles" on their own, which would hold the show whatever
    the setlist did and make this test pass against a broken guard — the flag
    asserted below has to be the ONLY thing holding it, or it pins nothing."""
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["creator"] = "Del McCoury Band"
    md["metadata"]["coverage"] = "Washington, DC"
    md["metadata"]["description"] = (
        "Del McCoury Band\nRFK Stadium\nWashington\nDC\nJune 10, 1973\n"
        "Nakamichi CM-300\n")
    names = ["gd73-06-10d1t01.mp3", "gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3",
             "gd73-06-10d2t01.mp3", "gd73-06-10d2t02.mp3", "gd73-06-10d3t01.mp3"]
    retitle = dict(zip(names, MCCOURY_SONGS))
    for f in md["files"]:
        if f.get("name") in retitle:
            f["title"] = retitle[f["name"]]
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    assert show.review_flags == ["low-confidence setlist"]
    assert show.needs_review is True


def test_sets_from_breaks_labels_the_encore():
    from llama.stages.gather import _sets_from_breaks

    labels = _sets_from_breaks(17, [7], encore_after=16)
    assert labels[:7] == ["1"] * 7
    assert labels[7:16] == ["2"] * 9
    assert labels[16] == "encore"


def test_sets_from_breaks_encore_without_numbered_breaks():
    from llama.stages.gather import _sets_from_breaks

    assert _sets_from_breaks(5, [], encore_after=4) == ["1", "1", "1", "1", "encore"]


def test_sets_from_breaks_unchanged_when_no_encore():
    from llama.stages.gather import _sets_from_breaks

    assert _sets_from_breaks(4, [2]) == ["1", "1", "2", "2"]


def test_overrides_accepts_encore_after():
    from llama.models import Overrides

    assert Overrides().encore_after is None
    assert Overrides(encore_after="gd73-06-10d2t01.mp3").encore_after == "gd73-06-10d2t01.mp3"
    assert Overrides(encore_after=16).encore_after == 16     # the legacy form still parses


def test_gather_encore_override_labels_tracks_and_implies_a_break(tmp_path: Path):
    """encore_after alone (no set_breaks) implies a break at that track, so
    the operator does not list it twice, and show.set_breaks reports it."""
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(encore_after="gd73-06-10d2t01.mp3"))
    show = run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    # 6-track fixture, encore after track 4 (d2t01) -> tracks 1-4 unbroken, 5-6 are the encore
    assert [t.set for t in show.tracks][-2:] == ["encore", "encore"]
    assert show.set_breaks == [4]
    assert show.structure is not None and show.structure.alignment == "override"
    assert show.structure.source == "override"


def test_encore_override_out_of_range_is_rejected():
    from llama.errors import LlamaError
    from llama.stages.gather import _validate_structure_override

    with pytest.raises(LlamaError, match="encore_after"):
        _validate_structure_override(n_tracks=5, breaks=[2], encore_after=9)


def test_encore_override_must_follow_every_set_break():
    from llama.errors import LlamaError
    from llama.stages.gather import _validate_structure_override

    with pytest.raises(LlamaError, match="greater than"):
        _validate_structure_override(n_tracks=17, breaks=[7, 16], encore_after=7)


def _ymsb_candidate():
    return Candidate(
        performance_id="YonderMountainStringBand/2005-12-31",
        collection="YonderMountainStringBand", date="2005-12-31",
        venue="Fillmore Auditorium", city="Denver, CO",
        recordings=[RecordingSummary(identifier=Y_IDENT)])


def test_gap_fill_resolves_a_mixed_show(tmp_path: Path):
    """Tagged tracks anchor; the count-forced unresolved run between them fills."""
    md = json.loads(FIXTURE.read_text())
    mp3s = [f for f in md["files"] if f.get("format") == "VBR MP3"]
    for i, f in enumerate(mp3s):
        f["title"] = None if i in (1, 2) else f.get("title")
    sws = ShowWorkspace(tmp_path / "show")
    # gd73's kept-file count exactly equals its canonical setlist's item count
    # (6 == 6), so titles.resolve_titles's whole-tape rung ("aligned = ...")
    # would otherwise resolve the blanked positions as "setlist" before
    # adopt_gap_titles ever sees an unresolved run to fill. Excluding the
    # trailing encore file (already untagged in the fixture, resolved via
    # that same whole-tape rung) breaks the exact count match (kept=5,
    # items=6) without touching either anchor or the gap under test — this
    # is exactly the LOCAL count-forcing-between-anchors scenario the rung
    # exists for, as opposed to the whole-tape one.
    write_artifact(sws.overrides, Overrides(exclude=["gd73-06-10d3t01.mp3"]))
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    filled = [t for t in show.tracks if t.title_source == "setlist-gap"]
    assert filled, "expected the blanked run to be gap-filled"
    assert all(t.title_source != "unresolved" for t in show.tracks)
    # Pins content, not just firing: a regression that adopted the wrong two
    # items (e.g. shifted by one) would still satisfy the assertions above.
    assert [t.title for t in filled] == ["China Cat Sunflower", "I Know You Rider"]


def test_a_fully_tagged_show_is_untouched(tmp_path: Path):
    md = json.loads(FIXTURE.read_text())
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    assert not any(t.title_source == "setlist-gap" for t in show.tracks)


def test_a_wholly_untagged_tape_gets_no_gap_fill(tmp_path: Path):
    """ymsb2005 has no tagged track, so there is no anchor -- but this test
    cannot tell you that's *why* adoption declines: it is 24 kept files
    against 25 canonical items, so count-forcing rejects independently of
    anchoring (verified by mutation: making the unanchored branch permissive
    leaves this test passing; the anchoring requirement is pinned instead by
    the unit-level test_unanchored_run_declines). What this test pins
    end-to-end on a real wholly-untagged tape is needs_review and the
    "unresolved track titles" flag. Piece 1 deliberately does NOT solve the
    whole-tape case; that is Piece 2's job."""
    md = json.loads(YMSB_FIXTURE.read_text())
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), _ymsb_candidate(), Y_IDENT)
    assert all(t.title_source == "unresolved" for t in show.tracks)
    assert show.needs_review is True
    assert "unresolved track titles" in show.review_flags


def _mixed_show_gap_setup(tmp_path: Path, subdir: str):
    """Shared setup (Minor 6, review round 1) for the wired/un-wired
    coverage-contamination comparison below: blank tracks 1 and 2 of gd73's
    MP3s and exclude the trailing encore file so titles.resolve_titles's
    whole-tape rung cannot pre-empt the local count-forced gap (see
    test_gap_fill_resolves_a_mixed_show's comment for why the exclude is
    needed). Returns (md, sws) so a caller can still run wired, or wrap the
    run_gather call in a monkeypatch for the un-wired half."""
    md = json.loads(FIXTURE.read_text())
    mp3s = [f for f in md["files"] if f.get("format") == "VBR MP3"]
    for i, f in enumerate(mp3s):
        f["title"] = None if i in (1, 2) else f.get("title")
    sws = ShowWorkspace(tmp_path / subdir)
    write_artifact(sws.overrides, Overrides(exclude=["gd73-06-10d3t01.mp3"]))
    return md, sws


def test_adopted_tracks_report_matched_none(tmp_path: Path):
    """Pins the I1 ruling (CORRECTED behaviour, decided, not open): because
    an adopted title *is* the canonical item's own text, align() matching it
    is tautological, not a measurement. So gather.py forces a setlist-gap
    track's final `matched` to None (= "not measured", per
    models.py:158-160) rather than align()'s tautological True.

    Renamed from test_adopted_tracks_report_matched_none_and_exclude_from_coverage
    (Minor 4, review round 1): on THIS fixture the three tag anchors already
    cover 100% by themselves, so this test cannot demonstrate the coverage
    EXCLUSION half numerically (mutation confirms: removing the exclusion
    clause leaves this test green) -- only the `matched` half. The coverage
    exclusion is pinned by test_songish_coverage_excludes_adopted_tracks
    (test_structure.py, a synthetic case built to discriminate) and by
    test_missed_anchor_flags_low_confidence_once_adopted_tracks_are_excluded
    below (an integration-level case built the same way).

    Compare to the identical show with adopt_gap_titles's wiring
    monkeypatched out below, where coverage is 0.6, two tracks are
    unmatched (False, not None -- they are actually-checked misses), and
    needs_review is True."""
    md, sws = _mixed_show_gap_setup(tmp_path, "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    assert show.structure is not None
    assert show.structure.coverage == 1.0
    assert [t.matched for t in show.tracks] == [True, None, None, True, True]
    assert show.needs_review is False
    assert show.review_flags == []

    # Title hygiene slice 1 "Declines bind setlist-gap": the cascade passes S's declined
    # positions as `declined=`, so the stand-in accepts it.
    def identity_adopt(tracks, canonical, *, metadata_norms, aliases, declined=frozenset()):
        return tracks

    md2, sws2 = _mixed_show_gap_setup(tmp_path, "show-unwired")
    with patch.object(gather_mod, "adopt_gap_titles", identity_adopt):
        unwired = gather_mod.run_gather(sws2, StubIA(md2), FakeProvider(),
                                        make_candidate(), IDENT)
    assert unwired.structure is not None
    assert unwired.structure.coverage == 0.6
    assert [t.matched for t in unwired.tracks] == [True, False, False, True, True]
    assert unwired.needs_review is True
    assert unwired.review_flags == [
        "low-confidence structure alignment", "unresolved track titles"]


def test_missed_anchor_flags_low_confidence_once_adopted_tracks_are_excluded(tmp_path: Path):
    """Important 1 (review round 1): the end-to-end purpose of the I1 ruling,
    demonstrated on THIS mixed-show fixture -- unlike
    test_adopted_tracks_report_matched_none, this case DOES change
    coverage's numeric value, because it adds a genuine miss on top of the
    same gap-fill setup: the last kept file ("Eyes of the World", tag
    title_source, an independent anchor) is retitled to "Zzyzx Road Blues",
    a song absent from the canonical setlist, so align() cannot match it on
    its own merits -- it stays title_source="tags" (a real tag, just a
    wrong one), so it is independent evidence that genuinely misses, not a
    tautological non-match.

    With adopted tracks excluded from coverage, that miss is judged against
    only the two OTHER independent anchors ("Morning Dew", "Dark Star": 2 of
    3 matched -> 0.6667), which is below align_coverage_threshold (0.8) and
    correctly raises "low-confidence structure alignment". Without the
    exclusion (verified by mutation below), the same miss is diluted by the
    two tautological setlist-gap "matches" (3 of 5 -> 0.8), which clears the
    threshold and ships silently clean -- the exact failure mode I1 exists
    to close: a real miss hidden behind adoption's own tautological
    matches."""
    md, sws = _mixed_show_gap_setup(tmp_path, "show")
    mp3s = [f for f in md["files"] if f.get("format") == "VBR MP3"]
    mp3s[4]["title"] = "Zzyzx Road Blues"  # last kept file; independent anchor that now misses
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    assert show.structure is not None
    assert [t.title_source for t in show.tracks] == [
        "tags", "setlist-gap", "setlist-gap", "tags", "tags"]
    assert [t.matched for t in show.tracks] == [True, None, None, True, False]
    assert show.structure.coverage == pytest.approx(2 / 3)
    assert show.review_flags == ["low-confidence structure alignment"]
    assert show.needs_review is True


def test_adopted_titles_make_the_closer_tripwire_reachable(tmp_path: Path):
    """With filenames as titles the closer check matches nothing and is
    silently inert. Once a gap is filled, a wrong closer must be able to
    speak. Pins the behaviour change so it is owned, not discovered.

    Task 3's original brief wrote this test without excluding a track, which
    (per M2/titles.py:129) makes gd73's kept-file count exactly equal its
    canonical setlist's item count -- so titles.resolve_titles's whole-tape
    "setlist" rung fires and resolves the blanked positions before
    adopt_gap_titles ever sees a gap; the test's own `assert adopted` then
    fails (adopted == []). Fixed by reusing the same exclude-a-track trick as
    test_gap_fill_resolves_a_mixed_show, so this exercises adopt_gap_titles
    specifically, not the dead whole-tape rung."""
    md = json.loads(FIXTURE.read_text())
    mp3s = [f for f in md["files"] if f.get("format") == "VBR MP3"]
    for i, f in enumerate(mp3s):
        if i in (1, 2):
            f["title"] = None
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, Overrides(exclude=["gd73-06-10d3t01.mp3"]))
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    adopted = [t for t in show.tracks if t.title_source == "setlist-gap"]
    assert adopted
    # every adopted title is a real song name, so norm_title comparisons in the
    # closer/spans checks now have something to match against
    assert all(not t.title.endswith(".mp3") for t in adopted)


def test_build_canonical_matches_what_gather_uses(tmp_path: Path):
    """The extraction must be behaviour-preserving: same items, same order."""
    from llama.stages.gather import build_canonical
    md = json.loads(FIXTURE.read_text())
    kept, _, _ = filter_files(md["files"], want_format=("VBR MP3",))
    cand = make_candidate()
    cb = build_canonical(StubIA(md), cand, IDENT, md["metadata"], kept, "Grateful Dead", [])
    canonical, source = cb.setlist, cb.source
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), cand, IDENT)
    assert [i.title for i in canonical.items]
    assert len(canonical.items) >= len([t for t in show.tracks if t.matched])
    assert source == "chosen"


def test_build_canonical_applies_the_cleaning_pass():
    """M1 mutation pin: `test_build_canonical_matches_what_gather_uses`
    above is the brief's own test, and its `>=` comparison does not fail
    when the cleaning pass is deleted from `build_canonical` -- measured:
    deleting `_strip_head_banner`/`_drop_artist_items` from the function
    leaves that test green while 4 pre-existing gather tests fail
    downstream. So the one test written to protect this extraction did not
    actually protect it; the extraction was guarded only by tests that
    predate it. This test closes that gap directly, on `build_canonical`
    alone.

    Constructs a description whose head is a 4-line taper banner (band
    name, venue, city, date) with NO "Set N:"/"Encore:" marker anywhere, so
    `parse_setlist`'s OWN header truncation (which fires only when such a
    marker starts a line) does not remove the banner first -- an earlier
    draft of this test reused the fixture's real description, which DOES
    start "Set 1:\n...", and `parse_setlist` truncated the banner on its
    own before `build_canonical` was ever called, making the test pass
    whether or not `_strip_head_banner` ran at all. This version instead
    joins songs with inline "&gt;" segue markers only, so the 4 banner
    lines survive into `parse_setlist`'s output as ordinary items --
    exactly the "recovered block is sometimes a taper banner" case
    `_strip_head_banner` exists for. Traced by hand and verified directly
    against `_show_metadata_norms`/`_strip_head_banner`'s stage-1 majority
    rule: 3 of the 4 head items are direct metadata matches (band name,
    venue, and "6/10/73" -- one of `_date_norms`'s own renderings of
    1973-06-10), which clears the majority threshold and drops the whole
    4-item span, carrying the one non-matching line ("Washington DC") along
    with it. Deleting the cleaning pass leaves all 4 banner lines in
    `canonical.items`, which the assertions below catch directly (verified
    against a mutated copy of `build_canonical` with the cleaning pass
    removed: this test fails there).
    """
    from llama.stages.gather import build_canonical
    md = json.loads(FIXTURE.read_text())
    meta = dict(md["metadata"])
    meta["description"] = (
        "Grateful Dead\nRFK Stadium\nWashington DC\n6/10/73\n"
        "Morning Dew\nChina Cat Sunflower &gt; I Know You Rider\n"
        "Dark Star &gt; Eyes of the World\nJohnny B. Goode"
    )
    kept, _, _ = filter_files(md["files"], want_format=("VBR MP3",))
    cand = make_candidate()
    canonical = build_canonical(StubIA(md), cand, IDENT, meta,
                                kept, "Grateful Dead", []).setlist
    titles = [i.title for i in canonical.items]
    assert titles == ["Morning Dew", "China Cat Sunflower", "I Know You Rider",
                      "Dark Star", "Eyes of the World", "Johnny B. Goode"]


def test_build_canonical_provider_none_never_reaches_the_llm_fallback(monkeypatch):
    """Regression pin for the provider=None guard: without it, a CLI edit
    command (llama fix --suggest-titles) could trigger a live LLM call.

    The brief's own version of this test (`fake = FakeProvider(); ...;
    assert not fake.calls`) is vacuous: `fake` is never passed to
    `build_canonical`, so the assertion is trivially true regardless of
    whether the guard exists. This version instead forces the exact branch
    the guard protects and proves it is reachable at all.

    Input: a single-recording candidate whose description has no setlist
    markers ("Just some random taper notes..."), so `parse_setlist` returns
    zero items and `rank_parses` has no non-empty candidate to pick --
    `best is None`, the precondition for the `extract_setlist` fallback.
    `run_json_task` is monkeypatched to raise, so its absence-of-a-call is
    directly observable rather than inferred from a mock's call list.
    """
    from llama.stages.gather import build_canonical

    def boom(*a, **k):
        raise AssertionError("run_json_task must not be called")

    monkeypatch.setattr(gather_mod, "run_json_task", boom)

    cand = Candidate(
        performance_id="Test/2000-01-01", collection="Test", date="2000-01-01",
        recordings=[RecordingSummary(identifier="only")],
    )
    meta = {"description": "Just some random taper notes with no songs listed at all."}

    # Guard: provider=None must not reach the fallback, even though `best is
    # None` (rank_parses has nothing to rank) makes this exactly the input
    # that would otherwise trigger it.
    canonical = build_canonical(None, cand, "only", meta, [], "Test Artist",
                                [], provider=None).setlist
    assert canonical.items == []

    # Positive control: the identical input WITH a provider must reach the
    # raiser. Without this half, a guard that always no-ops (e.g. if the
    # fallback code were deleted entirely) would pass the assertion above
    # for the wrong reason -- this proves the branch is genuinely reachable.
    with pytest.raises(AssertionError, match="run_json_task must not be called"):
        build_canonical(None, cand, "only", meta, [], "Test Artist",
                        [], provider=object())


# --- overrides.include (operator re-admission) ---

def test_gather_readmits_an_operator_included_file(tmp_path: Path):
    """gd73's spam file is the fixture's junk-filtered file. Naming it in
    overrides.include puts it in the track list, marks it, and takes it out of
    excluded_files."""
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, Overrides(include=["FOLLOW-ME @BYPIKENO.mp3"]))
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert "FOLLOW-ME @BYPIKENO.mp3" in [t.filename for t in show.tracks]
    assert [t.filename for t in show.tracks if t.included] == ["FOLLOW-ME @BYPIKENO.mp3"]
    assert all(e["filename"] != "FOLLOW-ME @BYPIKENO.mp3" for e in show.excluded_files)


def test_gather_leaves_ordinary_tracks_unmarked(tmp_path: Path):
    """Fix round 1, item 1: with an EMPTY overrides.include, the stamp block
    at gather.py never runs and this assertion is satisfied by Track.included
    defaulting to False, regardless of whether the stamp exists at all --
    caught by a reviewer mutation that deleted the whole block and one that
    forced `t.included = True` unconditionally, both of which stayed green
    against the old version of this test. Writing a real include entry makes
    the stamp block actually execute, and asserting every OTHER track is
    False makes the test sensitive to a stamp that over-marks.

    MEASURED SCOPE (whole-branch review M5), because the paragraph above
    over-claimed: this test catches the forced-`True` mutant, and does NOT
    catch deletion of the whole stamp block -- with the block gone, every
    track keeps `included=False` and every assertion here still holds. Its
    sibling `test_gather_readmits_an_operator_included_file` is what kills
    the deletion, by asserting the re-admitted track IS marked. Neither test
    covers both directions alone; the pair does."""
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, Overrides(include=["FOLLOW-ME @BYPIKENO.mp3"]))
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    others = [t for t in show.tracks if t.filename != "FOLLOW-ME @BYPIKENO.mp3"]
    assert others  # guard: the ordinary tracks must actually be present
    assert all(t.included is False for t in others)


def test_exclude_wins_when_a_file_is_in_both_override_lists(tmp_path: Path, caplog):
    """The CLI makes this state unreachable; gather still needs a defined
    answer for a hand-mangled overrides.json. include re-admits, exclude then
    drops -- so the file is out, with reason operator-excluded -- and (fix
    round 1, item 4) a warning names the ambiguity and says exclude wins."""
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, Overrides(include=["FOLLOW-ME @BYPIKENO.mp3"],
                                            exclude=["FOLLOW-ME @BYPIKENO.mp3"]))
    with caplog.at_level("WARNING"):
        show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert "FOLLOW-ME @BYPIKENO.mp3" not in [t.filename for t in show.tracks]
    dropped = next(e for e in show.excluded_files
                   if e["filename"] == "FOLLOW-ME @BYPIKENO.mp3")
    assert dropped["reasons"] == ["operator-excluded"]
    assert any("FOLLOW-ME @BYPIKENO.mp3" in r.message and "exclude wins" in r.message
               for r in caplog.records)


def test_gather_warns_when_an_include_entry_matches_no_file(tmp_path: Path, caplog):
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, Overrides(include=["not-on-this-tape.mp3"]))
    with caplog.at_level("WARNING"):
        run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    # caplog's handler formats each record on capture (Formatter.format sets
    # `.message` to the already-%-substituted string), so re-applying
    # `r.message % r.args` on a record that carries args raises TypeError --
    # observed against exactly this warning (`log.warning("...%r...", missing)`).
    # `.message` alone is already the fully rendered text.
    assert any("not-on-this-tape.mp3" in r.message for r in caplog.records)


def test_operator_excluded_entry_carries_duration_sec(tmp_path: Path):
    """Show.excluded_files must be homogeneous with what filter_files now
    produces: every entry, including operator-excluded ones, carries a
    duration_sec so Task 3's rendering never falls back to '?' for a file
    whose duration IS known from item metadata. gd73-06-10d1t01.mp3 is
    ordinarily kept by the junk filter, so this exercises the
    `operator-excluded` block, not junk filtering."""
    sws = ShowWorkspace(tmp_path / "show")
    excluded_name = "gd73-06-10d1t01.mp3"
    write_artifact(sws.overrides, Overrides(exclude=[excluded_name]))
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    entry = next(e for e in show.excluded_files if e["filename"] == excluded_name)
    assert isinstance(entry["duration_sec"], float)


# --- Tier 1 slice 0: LLM-free gather reports needs-LLM (spec "Slice 0") ---


def _low_coverage_candidate():
    """gd73 fixture with a description whose setlist shares nothing with the
    tape's tags, so align() lands under the threshold and the
    align_structure branch is reached."""
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = "Set 1: Alpha, Beta, Gamma, Delta, Epsilon, Zeta\nSet 2: Eta, Theta"
    return md


def test_compute_gather_reports_align_structure_without_a_provider(tmp_path):
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(_low_coverage_candidate()), None, make_candidate(), IDENT,
                         align_provider=None, jerrybase_enabled=False)
    assert isinstance(res, GatherResult)
    assert res.needs_llm == ("align_structure",)
    assert "low-confidence structure alignment" in res.show.review_flags   # degraded flag unchanged
    assert not sws.show.exists() and not sws.notes.exists()                 # compute writes nothing


def test_compute_gather_reports_extract_setlist_without_a_provider(tmp_path):
    md = json.loads(FIXTURE.read_text())
    # Parses to 0 items, so rank_parses returns None and the extract_setlist
    # fallback is reached (orchestrator ruling B1: the brief's prose text
    # parsed to 3 low-confidence items and never reached it).
    md["metadata"]["description"] = "An amazing night of music, seeded with love."
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(md), None, make_candidate(), IDENT, jerrybase_enabled=False)
    assert res.needs_llm == ("extract_setlist",)


def test_compute_gather_extract_with_a_provider_is_not_needs_llm(tmp_path):
    # The negative of the case above: the same unparseable description, but an
    # extract provider is passed, so the fallback is TAKEN and no verdict is
    # recorded (needs_llm is set only when the call is skipped for want of one).
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = "An amazing night of music, seeded with love."
    provider = FakeProvider(completes=[json.dumps({"items": [
        {"title": "Morning Dew", "normalized": "morning dew", "set": "1"}], "confidence": "low"})])
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(md), provider, make_candidate(), IDENT, jerrybase_enabled=False)
    assert provider.calls                                    # extract_setlist was called
    assert "extract_setlist" not in res.needs_llm


def test_compute_gather_empty_description_is_not_needs_llm(tmp_path):
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = ""
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(md), None, make_candidate(), IDENT, jerrybase_enabled=False)
    assert res.needs_llm == ()


def test_compute_gather_with_a_provider_records_nothing_and_calls_it(tmp_path):
    provider = FakeProvider(completes=[json.dumps({"tracks": [
        {"index": i, "set": "1", "segue": False, "matched_title": "x"} for i in range(1, 7)]})])
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(_low_coverage_candidate()), FakeProvider(), make_candidate(),
                         IDENT, align_provider=provider, jerrybase_enabled=False)
    assert res.needs_llm == ()
    assert provider.calls


def test_run_gather_writes_notes_json_and_returns_the_show(tmp_path):
    sws = ShowWorkspace(tmp_path / "s")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    notes = read_model(sws.notes, ShowNotes)
    assert notes == ShowNotes(gather=[], vet=[])
    assert show.tracks and sws.show.exists()


def test_run_gather_replaces_notes_json_on_force(tmp_path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.notes, ShowNotes(gather=["stale"], vet=["stale"]))
    run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT, force=True)
    assert read_model(sws.notes, ShowNotes) == ShowNotes()


# --- slice 2: the cross-source vocabulary (ruling 3) ---


def test_build_canonical_corroboration_excludes_the_chosen_description():
    base = json.loads(FIXTURE.read_text())
    chosen = dict(base["metadata"], description="Set 1\nOnly In The Chosen\nMorning Dew")
    sib = {"metadata": dict(base["metadata"], description="Set 1\nMorning Dew\nFrom A Sibling"),
           "files": []}
    ia = MultiIA({IDENT: {"metadata": chosen, "files": base["files"]}, "sib": sib})
    cand = make_candidate().model_copy(update={"recordings": [RecordingSummary(identifier=IDENT),
                                                               RecordingSummary(identifier="sib")]})
    kept, _, _ = filter_files(base["files"], want_format=("VBR MP3",))
    cb = build_canonical(ia, cand, IDENT, chosen, kept, "Grateful Dead", [])
    assert cb.corroboration == {fuzzy_norm_title("Morning Dew"): ("lma:sib",),
                                fuzzy_norm_title("From A Sibling"): ("lma:sib",)}
    assert fuzzy_norm_title("Only In The Chosen") not in cb.corroboration


def test_build_canonical_corroboration_names_setlistfm(tmp_path):
    import httpx
    slfm_body = json.loads((FIXTURES / "slfm_gd_1974_02_24.json").read_text())
    client = SetlistFMClient(
        cache_dir=tmp_path / "slfm-cache", api_key="k",
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=slfm_body))),
        backoff_s=0, rate_limit_s=0)
    ia = gd74_ia()
    meta = ia.metadata(W_IDENT)["metadata"]
    kept, _, _ = filter_files(ia.metadata(W_IDENT)["files"], want_format=("VBR MP3",))
    cb = build_canonical(ia, gd74_candidate(), W_IDENT, meta, kept, "Grateful Dead", [], setlistfm=client)
    assert any("setlist.fm" in sources for sources in cb.corroboration.values())
    assert any(sources == (f"lma:{M_IDENT}",) for sources in cb.corroboration.values()) or \
           any(f"lma:{M_IDENT}" in sources for sources in cb.corroboration.values())
    assert not any("chosen" in sources for sources in cb.corroboration.values())


def test_build_canonical_corroboration_drops_a_sibling_that_copies_the_chosen_description():
    # ruling 3: a byte-identical sibling (the bobbyleerodgers-2010-01-13 shape) is the same author
    base = json.loads(FIXTURE.read_text())
    chosen = dict(base["metadata"], description="Set 1\n07:22 - IB49\nMorning Dew")
    copy = {"metadata": dict(base["metadata"], description="Set 1\n07:22 - IB49\nMorning Dew"), "files": []}
    spaced = {"metadata": dict(base["metadata"], description="Set 1\n  07:22 - IB49\n\nMorning  Dew\n"),
              "files": []}
    ia = MultiIA({IDENT: {"metadata": chosen, "files": base["files"]}, "copy": copy, "spaced": spaced})
    cand = make_candidate().model_copy(update={"recordings": [RecordingSummary(identifier=IDENT),
                                                               RecordingSummary(identifier="copy"),
                                                               RecordingSummary(identifier="spaced")]})
    kept, _, _ = filter_files(base["files"], want_format=("VBR MP3",))
    cb = build_canonical(ia, cand, IDENT, chosen, kept, "Grateful Dead", [])
    assert cb.corroboration == {}


def test_build_canonical_corroboration_skips_items_that_normalize_to_nothing():
    """A `???` setlist line normalizes to "" -- an empty key would let any
    empty-normalizing tag count as corroborated (mutation (g) of task 8)."""
    base = json.loads(FIXTURE.read_text())
    chosen = dict(base["metadata"], description="Set 1\nMorning Dew")
    sib = {"metadata": dict(base["metadata"], description="Set 1\nMorning Dew\n???\nFrom A Sibling"),
           "files": []}
    ia = MultiIA({IDENT: {"metadata": chosen, "files": base["files"]}, "sib": sib})
    cand = make_candidate().model_copy(update={"recordings": [RecordingSummary(identifier=IDENT),
                                                               RecordingSummary(identifier="sib")]})
    kept, _, _ = filter_files(base["files"], want_format=("VBR MP3",))
    cb = build_canonical(ia, cand, IDENT, chosen, kept, "Grateful Dead", [])
    assert "" not in cb.corroboration
    assert set(cb.corroboration) == {fuzzy_norm_title("Morning Dew"), fuzzy_norm_title("From A Sibling")}


# --- FW3 (A): the segue donor is ranked only among segue-bearing LMA parses ---
#
# When setlist.fm wins the canonical (every item `segue=False`), the segues are
# blended back from the best LMA parse. `blend_segues` returns the winner
# unchanged when that donor has no segue at all, so a donor picked on item count
# alone could strip every real segue (gratefuldead-1988-06-23 lost 5 real marks).

_DONOR_SLFM = [["Bertha", "Deal"],
               ["Scarlet Begonias", "Fire On The Mountain", "Estimated Prophet",
                "Eyes Of The World"],
               ["Brokedown Palace"]]
_DONOR_FLAT = ("Set 1\nBertha\nDeal\nSet 2\nScarlet Begonias\nFire On The Mountain\n"
               "Estimated Prophet\nEyes Of The World\nEncore\nBrokedown Palace")
_DONOR_SEGUED = ("Set 1\nBertha > Deal\nSet 2\nScarlet Begonias > Fire On The Mountain\n"
                 "Estimated Prophet > Eyes Of The World\nDrums\nEncore\nBrokedown Palace")


def _donor_build(chosen_desc, sib_desc, n_kept):
    """build_canonical with setlist.fm present, the chosen recording and one
    sibling. Only `len(kept)` matters to build_canonical, so `kept` is a stub."""
    base = json.loads(FIXTURE.read_text())
    chosen = dict(base["metadata"], description=chosen_desc)
    sib = {"metadata": dict(base["metadata"], description=sib_desc), "files": []}
    ia = MultiIA({IDENT: {"metadata": chosen, "files": base["files"]}, "sib": sib})
    cand = make_candidate().model_copy(update={"recordings": [RecordingSummary(identifier=IDENT),
                                                               RecordingSummary(identifier="sib")]})
    kept = [{"name": f"t{i:02d}.mp3"} for i in range(n_kept)]
    return build_canonical(ia, cand, IDENT, chosen, kept, "Grateful Dead", [],
                           setlistfm=_FakeSetlistFM(*_DONOR_SLFM, encore=True))


def _segued(cb):
    return [i.title for i in cb.setlist.items if i.segue]


def test_build_canonical_segue_donor_skips_a_closer_in_count_parse_with_no_segue():
    # The chosen description (7 items, |7-7|=0) wins the count tie-break over the
    # sibling (8 items, |8-7|=1) but carries no `>`; the sibling's segues must still
    # reach the setlist.fm canonical.
    cb = _donor_build(_DONOR_FLAT, _DONOR_SEGUED, 7)
    assert cb.source == "setlist.fm"
    assert [i.title for i in cb.setlist.items] == [n for s in _DONOR_SLFM for n in s]
    assert _segued(cb) == ["Bertha", "Scarlet Begonias", "Estimated Prophet"]


def test_build_canonical_no_segue_bearing_lma_parse_leaves_setlistfm_unchanged():
    # (pin) No LMA parse carries a segue: no donor, the setlist.fm canonical as is.
    cb = _donor_build(_DONOR_FLAT, _DONOR_FLAT.replace("Encore", "Drums\nEncore"), 7)
    assert cb.source == "setlist.fm"
    assert [(i.title, i.set) for i in cb.setlist.items] == [
        (n, lbl) for s, lbl in zip(_DONOR_SLFM, ["1", "2", "encore"]) for n in s]
    assert _segued(cb) == []


def test_build_canonical_segue_donor_best_by_count_is_unchanged():
    # (pin) The segue-bearing chosen parse is already the closest by count, so the
    # donor is the one today's ranking picks; a segue-less sibling changes nothing.
    chosen = _DONOR_SEGUED.replace("\nDrums", "")
    cb = _donor_build(chosen, _DONOR_FLAT.replace("Encore", "Drums\nSpace\nEncore"), 7)
    assert cb.source == "setlist.fm"
    assert _segued(cb) == ["Bertha", "Scarlet Begonias", "Estimated Prophet"]


# --- slice 2b on a captured tape: furthur2012-07-15, every tag "tmp" ---

FURTHUR = FIXTURES / "furthur2012-07-15.json"
F_IDENT = "furthur2012-07-15"


def _furthur_candidate():
    return Candidate(performance_id="Furthur/2012-07-15", collection="Furthur", date="2012-07-15",
                     venue="Bethel Woods Center for the Arts", city="Bethel, NY",
                     recordings=[RecordingSummary(identifier=F_IDENT)])


def _furthur_without_short_tuning(md=None):
    """The furthur item without its `10.tuningup.*` files: the 19-file tape the
    filter kept before piece 4. Since piece 4 the mp3 copy (tag `tmp`, tagged
    under spec 2.2) is kept while the FLAC copy (`Tuning Up`, junk under 2.3) is
    not, so the tests about the 19-file shape build it explicitly."""
    md = md or json.loads(FURTHUR.read_text())
    md["files"] = [f for f in md["files"] if not f["name"].startswith("10.tuningup.")]
    return md


def test_2b_demotes_a_whole_tmp_tape_and_notes_each_track(tmp_path):
    """Every mp3 tag is `tmp`: 2b demotes and notes each track. Since piece 4
    the 01:54 `10.tuningup.mp3` (tag `tmp`, tagged under spec 2.2) is kept, so
    the tape's 20 files match the description's 20 entries and D fills every
    demoted track from it; before, 19 files left them all unresolved."""
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(json.loads(FURTHUR.read_text())), None, _furthur_candidate(),
                         F_IDENT, jerrybase_enabled=False)
    assert len(res.show.tracks) == 20
    assert all(t.title_source == "desc-position" for t in res.show.tracks)
    assert [t.title for t in res.show.tracks][9:11] == ["Tuning Up", "Terrapin Station"]
    assert "unresolved track titles" not in res.show.review_flags
    demotions = [n for n in res.notes if n.startswith("placeholder tag title: ")]
    assert len(demotions) == len(res.show.tracks)
    assert demotions[0] == f"placeholder tag title: track 1 '{'tmp'}' demoted to unresolved"


def test_2b_does_not_touch_a_real_tagged_tape(tmp_path):
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert not any(n.startswith("placeholder tag title") for n in res.notes)
    assert [t.title for t in res.show.tracks][:2] == ["Morning Dew", "China Cat Sunflower"]
    assert not any(n.startswith("format sibling tagged") for n in res.notes)


def test_2b_files_the_format_sibling_it_does_not_recover_from(tmp_path):
    """The furthur mp3s are all `tmp` (a real title by `is_real_title`, so
    `_RECOVER_BELOW` never fires), while the FLAC copy is fully tagged: the count
    is filed as a note, and recovery is not triggered.

    Run on the 19-file shape: on the captured item piece 4 keeps the mp3
    `10.tuningup.mp3` (`tmp`, spec 2.2) but not its FLAC original (`Tuning Up`,
    junk under 2.3), so 20 mp3s against 19 FLACs have no stem bijection and no
    note is filed."""
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(_furthur_without_short_tuning()), None, _furthur_candidate(),
                         F_IDENT, jerrybase_enabled=False)
    assert ("format sibling tagged: Flac title fraction 1.00 "
            "(recovery not triggered; filed, not acted on)") in res.notes
    captured = compute_gather(ShowWorkspace(tmp_path / "c"), StubIA(json.loads(FURTHUR.read_text())),
                              None, _furthur_candidate(), F_IDENT, jerrybase_enabled=False)
    assert not any(n.startswith("format sibling tagged") for n in captured.notes)
    # notes never reach the LLM (ruling 6)
    conflicts = res.show.structure.conflicts if res.show.structure else []
    assert not any("placeholder tag title" in c or "format sibling" in c
                   for c in conflicts + res.show.review_flags)


def test_2b_recomputes_fetch_siblings_over_demoted_titles(tmp_path):
    """`tmp` x 19 has title_fraction 1.0, so before 2b sibling-align never ran;
    the demotions now open the fetch gate."""
    sws = ShowWorkspace(tmp_path / "s")
    seen = []

    # Title hygiene slice 2 "Wholly untagged tapes" (b): gather reaches sibling-align
    # through `_sibling_transfer_full` (its donor is reused by D's sibling-duration check),
    # so that is the name patched; it returns the donor as a third element.
    def fake_transfer(ia, candidate, identifier, want, tracks, metadata_norms):
        seen.append(len(tracks))
        return list(tracks), [], None

    with patch.object(gather_mod, "_sibling_transfer_full", side_effect=fake_transfer):
        compute_gather(sws, StubIA(json.loads(FURTHUR.read_text())), None, _furthur_candidate(),
                       F_IDENT, jerrybase_enabled=False)
    assert seen and seen[0] > 0


def test_2b_never_judges_an_override_title(tmp_path):
    """Spec 576-577 (orchestrator ruling M9): a track position named in
    `overrides.titles` gets neither a demotion nor a demotion note."""
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.overrides, Overrides(titles={"01.tuningup.mp3": "Tuning Up",
                                                    "03.twodjinn.mp3": "Two Djinn"}))
    res = compute_gather(sws, StubIA(json.loads(FURTHUR.read_text())), None, _furthur_candidate(),
                         F_IDENT, jerrybase_enabled=False)
    tracks = res.show.tracks
    assert (tracks[0].title, tracks[0].title_source) == ("Tuning Up", "override")
    assert (tracks[2].title, tracks[2].title_source) == ("Two Djinn", "override")
    demoted = [n for n in res.notes if n.startswith("placeholder tag title: ")]
    assert len(demoted) == len(tracks) - 2
    assert not any(n.startswith(("placeholder tag title: track 1 ", "placeholder tag title: track 3 "))
                   for n in demoted)
    assert demoted[0] == "placeholder tag title: track 2 'tmp' demoted to unresolved"


def _furthur_md():
    return json.loads(FURTHUR.read_text())


def test_2b_demotes_a_recovered_sibling_format_placeholder_and_files_no_sibling_note(tmp_path):
    """Untagged mp3s beside FLACs tagged `Track NN`: format recovery fires (`Track
    01` passes is_real_title), so the tag layer IS the FLAC copy and its
    placeholders are demoted -- and the "recovery not triggered" note would be
    false, so it is not filed."""
    md = _furthur_md()
    for f in md["files"]:
        if f.get("format") == "VBR MP3":
            f["title"] = ""
        elif f.get("format") == "Flac":
            f["title"] = f"Track {f['name'][:2]}"
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(md), None, _furthur_candidate(), F_IDENT, jerrybase_enabled=False)
    # Since piece 4 `10.tuningup` is kept in both formats (the mp3's tag is its
    # original's `Track 10`, spec 2.2), so 20 tracks match the description's 20
    # entries and D fills every track 2b demoted (`sibling-format` had 2b not fired).
    assert {t.title_source for t in res.show.tracks} == {"desc-position"}
    assert "placeholder tag title: track 1 'Track 01' demoted to unresolved" in res.notes
    assert not any(n.startswith("format sibling tagged") for n in res.notes)


def test_2b_a_sibling_description_naming_the_tag_exempts_it(tmp_path):
    """The corroboration vocabulary reaches resolve_titles and the notes: a
    sibling recording whose description lists `tmp` exempts the tag."""
    md = _furthur_md()
    sib = {"metadata": dict(md["metadata"], description="Set 1\ntmp\nCold Rain And Snow\nTwo Djinn"),
           "files": []}
    cand = _furthur_candidate().model_copy(update={"recordings": [
        RecordingSummary(identifier=F_IDENT), RecordingSummary(identifier="sib")]})
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, MultiIA({F_IDENT: md, "sib": sib}), None, cand, F_IDENT,
                         jerrybase_enabled=False)
    assert {t.title_source for t in res.show.tracks} == {"tags"}
    assert not any(n.startswith("placeholder tag title") for n in res.notes)


def test_2b_item_title_reaches_the_recording_level_class(tmp_path):
    """Every file carries the item's own title, spelled two ways that agree
    only under fuzzy_norm_title (so the identical-string arm cannot fire)."""
    md = _furthur_md()
    item = md["metadata"]["title"]
    mp3s = [f for f in md["files"] if f.get("format") == "VBR MP3"]
    for i, f in enumerate(mp3s):
        f["title"] = item if i % 2 else item + " !"
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(md), None, _furthur_candidate(), F_IDENT, jerrybase_enabled=False)
    # Since piece 4 `10.tuningup.mp3` (tagged with the item title, spec 2.2) is
    # kept, the 20 tracks match the description's 20 entries and D fills every
    # track 2b demoted (`tags` had 2b not fired).
    assert {t.title_source for t in res.show.tracks} == {"desc-position"}
    assert any(n.startswith("placeholder tag title: track 1 ") for n in res.notes)


# --- slice 2a on a captured tape: tnd2006-12-13, "J >" tags ---


TND = FIXTURES / "tnd2006-12-13.json"
T_IDENT = "tnd2006-12-13.flac16"
T_SIB = "tnd2006-12-13.sib"
# Both descriptions list "J", but neither has 19 items (the tape's count), so the
# whole-tape `setlist` rung cannot fire and the "J >" tracks reach 2a unresolved.
CHOSEN_DESC = "Set 1\nJ >\nJ (Da Funk) >\nRavine > J\nG-nome > J >\nJ > G-nome\nSet 2\nGlide >\nHome\nJ > Moment #2 >\nVL Tone > J > VL Tone"
SIB_DESC = "set one: J > , J (Da Funk) > , Ravine > J\nset two: Glide > , Home, J > Moment #2"


def _tnd(with_sibling: bool):
    md = json.loads(TND.read_text())
    md["metadata"]["description"] = CHOSEN_DESC
    recs = [RecordingSummary(identifier=T_IDENT)]
    mapping = {T_IDENT: md}
    if with_sibling:
        recs.append(RecordingSummary(identifier=T_SIB))
        mapping[T_SIB] = {"metadata": dict(md["metadata"], description=SIB_DESC), "files": []}
    cand = Candidate(performance_id="TheNewDeal/2006-12-13", collection="TheNewDeal", date="2006-12-13",
                     venue="Water Street Music Hall", city="Rochester, NY", recordings=recs)
    return MultiIA(mapping), cand


def _files_tagged(ia, tag):
    return {f["name"] for f in ia.mapping[T_IDENT]["files"] if (f.get("title") or "").strip() == tag}


def test_2a_accepts_j_when_a_sibling_description_corroborates_it(tmp_path):
    ia, cand = _tnd(with_sibling=True)
    res = compute_gather(ShowWorkspace(tmp_path / "s"), ia, None, cand, T_IDENT, jerrybase_enabled=False)
    j_tracks = [t for t in res.show.tracks if t.filename in _files_tagged(ia, "J >")]
    assert len(j_tracks) >= 5 and all((t.title, t.title_source) == ("J", "tags") for t in j_tracks)
    assert f"accepted short tag title: track {j_tracks[0].index} 'J' corroborated by lma:{T_SIB}" in res.notes
    q_tracks = [t for t in res.show.tracks if t.filename in _files_tagged(ia, "? >")]
    assert q_tracks and all(t.title_source == "unresolved" for t in q_tracks)   # "?" never qualifies


def test_2a_does_not_count_the_chosen_recordings_own_description(tmp_path):
    ia, cand = _tnd(with_sibling=False)
    res = compute_gather(ShowWorkspace(tmp_path / "s"), ia, None, cand, T_IDENT, jerrybase_enabled=False)
    assert not any(n.startswith("accepted short tag title") for n in res.notes)
    assert all(t.title_source == "unresolved" for t in res.show.tracks if t.filename in _files_tagged(ia, "J >"))
    assert "unresolved track titles" in res.show.review_flags


def test_accept_short_tags_rules():
    tracks = [Track(index=i, set="1", title=f"t{i}.mp3", filename=f"t{i}.mp3", title_source="unresolved")
              for i in range(1, 8)]
    tracks[5] = tracks[5].model_copy(update={"title": "Ramone & Emiglio", "title_source": "setlist-gap"})
    tracks.append(Track(index=8, set="1", title="t8.mp3", filename="t8.mp3", title_source="unresolved"))
    # row 5 is the metadata-norms veto: "NY" fails is_real_title, so it reaches 2a and is vetoed there;
    # row 8 is the spec's named timestamp trap, corroborated (as by a copied description) and still vetoed
    tags = ["FF>", "? >", "05:27 -", "12-28-99", "NY", "R&E", "42", "07:22 - IB49"]
    corroboration = {fuzzy_norm_title("FF"): ("setlist.fm",), fuzzy_norm_title("?"): ("lma:x",),
                     fuzzy_norm_title("05:27"): ("lma:x",), fuzzy_norm_title("12-28-99"): ("lma:x",),
                     fuzzy_norm_title("NY"): ("lma:x",), fuzzy_norm_title("R&E"): ("lma:x",),
                     fuzzy_norm_title("42"): ("lma:x", "setlist.fm"),
                     fuzzy_norm_title("07:22 - IB49"): ("lma:x",)}
    out, notes = accept_short_tags(tracks, tags, "tags", corroboration=corroboration,
                                   metadata_norms={fuzzy_norm_title("NY")}, demoted=frozenset())
    assert [(t.title, t.title_source) for t in out] == [
        ("FF", "tags"), ("t2.mp3", "unresolved"), ("t3.mp3", "unresolved"), ("t4.mp3", "unresolved"),
        ("t5.mp3", "unresolved"), ("Ramone & Emiglio", "setlist-gap"), ("42", "tags"),
        ("t8.mp3", "unresolved")]
    assert notes == ["accepted short tag title: track 1 'FF' corroborated by setlist.fm",
                     "accepted short tag title: track 7 '42' corroborated by lma:x, setlist.fm"]
    assert tracks[0].title_source == "unresolved"     # input untouched


def test_accept_short_tags_ignores_tags_that_pass_is_real_title():
    # a 2b-demoted "tmp" is unresolved with a real-looking tag: 2a must not re-accept it
    tracks = [Track(index=1, set="1", title="t1.mp3", filename="t1.mp3", title_source="unresolved")]
    out, notes = accept_short_tags(tracks, ["tmp"], "tags", corroboration={fuzzy_norm_title("tmp"): ("lma:x",)},
                                   metadata_norms=set(), demoted=frozenset())
    assert out[0].title_source == "unresolved" and notes == []


def test_accept_short_tags_never_judges_a_real_title_tag():
    # Mutant (f) guard: "tmp" above is also caught by the junk veto, so it does not
    # pin the is_real_title gate on its own. "Jam > Jam" is the case only the gate
    # stops: a recording-level 2b demotion judges the WHOLE tag ("jam jam", not an
    # item) while 2a would judge per component ("jam" is one) and re-accept it.
    tracks = [Track(index=1, set="1", title="t1.mp3", filename="t1.mp3", title_source="unresolved")]
    out, notes = accept_short_tags(tracks, ["Jam > Jam"], "tags",
                                   corroboration={fuzzy_norm_title("Jam"): ("lma:x",)}, metadata_norms=set(), demoted=frozenset())
    assert out[0].title_source == "unresolved" and notes == []


def test_accept_short_tags_skips_positions_2b_demoted():
    # Review fix r1: 2b judges the WHOLE tag ("j j" is no item, so a "J > J" x 3 tape
    # is recording-level junk and demoted) while 2a judges components ("j" is one).
    # A 2b-demoted position must never be re-accepted by 2a (spec 2b: only
    # setlist-gap and sibling-align may still title it). Track 4 is the control:
    # the same tag, not demoted, is accepted.
    tracks = [Track(index=i, set="1", title=f"t{i}.mp3", filename=f"t{i}.mp3", title_source="unresolved")
              for i in range(1, 5)]
    out, notes = accept_short_tags(tracks, ["J > J"] * 4, "tags",
                                   corroboration={fuzzy_norm_title("J"): ("lma:x",)}, metadata_norms=set(),
                                   demoted=frozenset({0, 1, 2}))
    assert [(t.title, t.title_source) for t in out] == [
        ("t1.mp3", "unresolved"), ("t2.mp3", "unresolved"), ("t3.mp3", "unresolved"), ("J > J", "tags")]
    assert notes == ["accepted short tag title: track 4 'J > J' corroborated by lma:x"]


def test_2a_does_not_reaccept_a_recording_level_2b_demotion(tmp_path):
    # Wiring for the fix above: every tnd track tagged "J > J" is 2b recording-level
    # junk; the sibling description corroborates "J", and still nothing is accepted.
    ia, cand = _tnd(with_sibling=True)
    for f in ia.mapping[T_IDENT]["files"]:
        if f.get("title"):
            f["title"] = "J > J"
    res = compute_gather(ShowWorkspace(tmp_path / "s"), ia, None, cand, T_IDENT, jerrybase_enabled=False)
    assert any(n.startswith("placeholder tag title: track 1 'J > J'") for n in res.notes)
    assert not any(n.startswith("accepted short tag title") for n in res.notes)
    assert {t.title_source for t in res.show.tracks} == {"unresolved"}


def test_accept_short_tags_needs_every_segue_component_corroborated():
    # Mutant (c) guard: a multi-component core is accepted only when EVERY
    # component is a cross-source item; one uncorroborated component vetoes.
    # Row 2 is the positive control: both components corroborated, sources unioned.
    tracks = [Track(index=i, set="1", title=f"t{i}.mp3", filename=f"t{i}.mp3", title_source="unresolved")
              for i in (1, 2)]
    # Both tags fail is_real_title (2 letters), so both reach 2a's component test.
    corroboration = {fuzzy_norm_title("J"): ("lma:x",), fuzzy_norm_title("F"): ("setlist.fm",)}
    out, notes = accept_short_tags(tracks, ["J > X", "J > F >"], "tags",
                                   corroboration=corroboration, metadata_norms=set(), demoted=frozenset())
    assert [(t.title, t.title_source) for t in out] == [("t1.mp3", "unresolved"), ("J > F", "tags")]
    assert notes == ["accepted short tag title: track 2 'J > F' corroborated by lma:x, setlist.fm"]


def test_accept_short_tags_carries_the_tag_layer_source():
    # Format recovery fired: the accepted title is stamped `sibling-format`.
    tracks = [Track(index=1, set="1", title="t1.mp3", filename="t1.mp3", title_source="unresolved")]
    out, _ = accept_short_tags(tracks, ["ML**"], "sibling-format",
                               corroboration={fuzzy_norm_title("ML"): ("lma:x",)}, metadata_norms=set(), demoted=frozenset())
    assert (out[0].title, out[0].title_source, out[0].matched) == ("ML", "sibling-format", None)


def test_2a_never_judges_an_overridden_position(tmp_path):
    # M9: a position in overrides.titles is an override, never judged or noted by 2a.
    ia, cand = _tnd(with_sibling=True)
    sws = ShowWorkspace(tmp_path / "s")
    j_names = _files_tagged(ia, "J >")
    probe = compute_gather(ShowWorkspace(tmp_path / "probe"), ia, None, cand, T_IDENT, jerrybase_enabled=False)
    j = next(t for t in probe.show.tracks if t.filename in j_names)
    n = j.index
    write_artifact(sws.overrides, Overrides(titles={j.filename: "Jam"}))
    res = compute_gather(sws, ia, None, cand, T_IDENT, jerrybase_enabled=False)
    assert (res.show.tracks[n - 1].title, res.show.tracks[n - 1].title_source) == ("Jam", "override")
    assert not any(note.startswith(f"accepted short tag title: track {n} ") for note in res.notes)
    assert any(note.startswith("accepted short tag title") for note in res.notes)


RRE = FIXTURES / "rre2013-11-30.json"
R_IDENT = "RRE2013-11-30.ShermanTheaterStroudsburgPa"


def test_2c_strips_railroad_earths_glued_numbers_and_notes_each(tmp_path):
    cand = Candidate(performance_id="RailroadEarth/2013-11-30", collection="RailroadEarth",
                     date="2013-11-30", venue="Sherman Theater", city="Stroudsburg, PA",
                     recordings=[RecordingSummary(identifier=R_IDENT)])
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(json.loads(RRE.read_text())), None,
                         cand, R_IDENT, jerrybase_enabled=False)
    titles = [t.title for t in res.show.tracks]
    assert titles[:2] == ["Pig In A Pen", "Midnight Moonlight"]
    assert "stripped glued track number: track 1 '01Pig In A Pen' -> 'Pig In A Pen'" in res.notes
    # 25: piece 4 keeps the two short banter tracks, `08Peter Rowan Banter` and
    # `24Todd Banter` (spec 1, 2.3: stage banter is kept), and 2c strips theirs too.
    assert sum(n.startswith("stripped glued track number:") for n in res.notes) == 25
    assert not any(n.startswith("stripped joined track number:") for n in res.notes)


def _rre_joined(drop_mp3_titles=False):
    md = json.loads(RRE.read_text())
    for f in md["files"]:
        t = f.get("title")
        if t:
            f["title"] = t[:2] + "-" + t[2:]
            if drop_mp3_titles and f["format"] == "VBR MP3":
                f["title"] = t[:2] + "-x"   # unusable: recovery from the flac fires
    return md


def test_2d_strips_joined_numbers_and_notes_each(tmp_path):
    cand = Candidate(performance_id="RailroadEarth/2013-11-30", collection="RailroadEarth",
                     date="2013-11-30", venue="Sherman Theater", city="Stroudsburg, PA",
                     recordings=[RecordingSummary(identifier=R_IDENT)])
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(_rre_joined()), None,
                         cand, R_IDENT, jerrybase_enabled=False)
    assert [t.title for t in res.show.tracks][:2] == ["Pig In A Pen", "Midnight Moonlight"]
    assert "stripped joined track number: track 1 '01-Pig In A Pen' -> 'Pig In A Pen'" in res.notes
    # 25: piece 4 keeps the two short banter tracks (spec 1, 2.3); 2d strips theirs too.
    assert sum(n.startswith("stripped joined track number:") for n in res.notes) == 25
    assert not any(n.startswith("stripped glued track number:") for n in res.notes)


def test_2d_notes_nothing_under_format_recovery(tmp_path):
    cand = Candidate(performance_id="RailroadEarth/2013-11-30", collection="RailroadEarth",
                     date="2013-11-30", venue="Sherman Theater", city="Stroudsburg, PA",
                     recordings=[RecordingSummary(identifier=R_IDENT)])
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(_rre_joined(True)), None,
                         cand, R_IDENT, jerrybase_enabled=False)
    assert not any(n.startswith("stripped joined track number:") for n in res.notes)
    t1 = res.show.tracks[0]
    assert (t1.title, t1.title_source) == ("Pig In A Pen", "sibling-format")


# --- Task 11b (Checkpoint B, 2026-10-19): shipped-title cosmetics on the 2a/2c paths ---

def test_accept_short_tags_ships_and_notes_the_cleaned_title():
    tracks = [Track(index=i, set="1", title=f"t{i}.mp3", filename=f"t{i}.mp3", title_source="unresolved")
              for i in (1, 2, 3)]
    corroboration = {fuzzy_norm_title("M80"): ("setlist.fm",), fuzzy_norm_title("2x2"): ("lma:x",),
                     fuzzy_norm_title("42(1)"): ("lma:y",)}
    out, notes = accept_short_tags(tracks, ["M80,", "E: 2x2", "42(1)"], "tags",
                                   corroboration=corroboration, metadata_norms=set(), demoted=frozenset())
    assert [(t.title, t.title_source) for t in out] == [("M80", "tags"), ("2x2", "tags"), ("42", "tags")]
    assert notes == ["accepted short tag title: track 1 'M80' corroborated by setlist.fm",
                     "accepted short tag title: track 2 '2x2' corroborated by lma:x",
                     "accepted short tag title: track 3 '42' corroborated by lma:y"]


def test_2c_ships_and_notes_railroad_earths_titles_without_footnote_marks(tmp_path):
    cand = Candidate(performance_id="RailroadEarth/2013-11-30", collection="RailroadEarth",
                     date="2013-11-30", venue="Sherman Theater", city="Stroudsburg, PA",
                     recordings=[RecordingSummary(identifier=R_IDENT)])
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(json.loads(RRE.read_text())), None,
                         cand, R_IDENT, jerrybase_enabled=False)
    titles = [t.title for t in res.show.tracks]
    for want in ("The Cuckoo", "Cold Rain And Snow", "Walls Of Time"):
        assert want in titles
    assert not any(t.rstrip().endswith(("#", "^")) for t in titles)
    # Track numbers one later than before piece 4: `08Peter Rowan Banter` is now
    # kept at track 8 (spec 1, 2.3: stage banter is kept).
    assert "stripped glued track number: track 20 '20The Cuckoo #' -> 'The Cuckoo'" in res.notes
    assert "stripped glued track number: track 22 '22Walls Of Time #^' -> 'Walls Of Time'" in res.notes


# --- slice 1: venue tripwire steps, the swap, the signature, 1d (spec "Slice 1") ---


DSO = FIXTURES / "dso2003-01-25.json"; DSO_IDENT = "dso2003-01-25.shnf"
GUSTER = FIXTURES / "guster2003-07-10.json"; G_IDENT = "guster2003-07-10.shnf"
GD78 = FIXTURES / "gd78-11-17_dodd.json"; GD78_IDENT = "gd78-11-17.acoustic.sbd.dodd.7687.sbeok.shnf"


def _dso_candidate():
    return Candidate(performance_id="DarkStarOrchestra/2003-01-25", collection="DarkStarOrchestra",
                     date="2003-01-25", venue="The Pageant", city="St. Louis, MO",
                     recordings=[RecordingSummary(identifier="ds2003-01-25.shnf", venue="The Pageant",
                                                  coverage="St. Louis, MO"),
                                 RecordingSummary(identifier=DSO_IDENT, venue="Barrymore Theater",
                                                  coverage="Madison, WI")])


def _gather(tmp_path, fixture, cand, ident, **kw):
    sws = ShowWorkspace(tmp_path / "s")
    md = json.loads(fixture.read_text())
    return compute_gather(sws, StubIA(md), None, cand, ident, jerrybase_enabled=True, **kw)


def test_swap_ships_the_selected_venue_when_it_agrees_with_jerrybase_and_1d_still_holds(tmp_path):
    res = _gather(tmp_path, DSO, _dso_candidate(), DSO_IDENT)
    assert (res.show.venue, res.show.city) == ("Barrymore Theater", "Madison, WI")
    assert ("venue taken from the selected recording: 'Barrymore Theater' agrees with jerrybase "
            "'Barrymore Theatre' (vote was 'The Pageant')") in res.notes
    assert not any(f.startswith("venue mismatch") for f in res.show.review_flags)
    assert "recordings of this date disagree on city: 'Madison, WI' (selected) vs 'St. Louis, MO'" in res.show.review_flags


def test_an_operator_venue_override_suppresses_the_1d_hold(tmp_path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.overrides, Overrides(venue="Barrymore Theatre", city="Madison, WI"))
    res = compute_gather(sws, StubIA(json.loads(DSO.read_text())), None, _dso_candidate(), DSO_IDENT,
                         jerrybase_enabled=True)
    assert res.show.venue == "Barrymore Theatre" and res.show.venue_source == "override"
    assert not any("disagree on city" in f for f in res.show.review_flags)


def test_two_venue_signature_keeps_the_same_city_double_held(tmp_path):
    recs = [RecordingSummary(identifier="gd1978-11-17.135718.sbd.partial.schley.andrewf.flac1644",
                             venue="Uptown Theater", coverage="Chicago, IL"),
            RecordingSummary(identifier=GD78_IDENT, venue="Rambler Room, Loyola College", coverage="Chicago, IL"),
            RecordingSummary(identifier="gd78-11-17.paud.wiley.11488.sbeok.shnf", venue="Uptown Theatre",
                             coverage="Chicago, IL")]
    cand = Candidate(performance_id="GratefulDead/1978-11-17", collection="GratefulDead", date="1978-11-17",
                     venue="Rambler Room, Loyola College", city="Chicago, IL", recordings=recs)
    assert two_venue_signature(cand)
    res = _gather(tmp_path, GD78, cand, GD78_IDENT)
    assert "venue mismatch: archive 'Rambler Room, Loyola College' vs jerrybase 'Uptown Theatre'" in res.show.review_flags
    assert res.show.venue == "Rambler Room, Loyola College"
    assert not any(n.startswith("venue differs from jerrybase") for n in res.notes)


def test_signature_also_fires_on_spellings_of_one_hall():
    cand = Candidate(performance_id="GratefulDead/1981-09-26", collection="GratefulDead", date="1981-09-26",
                     recordings=[RecordingSummary(identifier="a", venue="Buffalo Auditorium", coverage="Buffalo, NY"),
                                 RecordingSummary(identifier="b", venue="Community War Memorial Auditorium",
                                                  coverage="Buffalo, NY")])
    assert two_venue_signature(cand)
    assert not two_venue_signature(cand.model_copy(update={"recordings": [cand.recordings[0]]}))


def test_1d_ships_the_selected_recording_on_a_city_conflict_without_jerrybase(tmp_path):
    cand = Candidate(performance_id="Guster/2003-07-10", collection="Guster", date="2003-07-10",
                     venue="Cities 97 Studio C", city="Minneapolis, MN",
                     recordings=[RecordingSummary(identifier="guster2003-07-10.fm.shnf", venue="Cities 97 Studio C",
                                                  coverage="Minneapolis, MN"),
                                 RecordingSummary(identifier=G_IDENT, venue="Weesner Amphitheater, MN Zoo",
                                                  coverage="Apple Valley, MN")])
    res = _gather(tmp_path, GUSTER, cand, G_IDENT)
    assert (res.show.venue, res.show.city) == ("Weesner Amphitheater, MN Zoo", "Apple Valley, MN")
    assert "recordings of this date disagree on city: 'Apple Valley, MN' (selected) vs 'Minneapolis, MN'" in res.show.review_flags


def test_1d_does_not_fire_without_a_selected_city_or_with_compatible_cities(tmp_path):
    base = _dso_candidate()
    no_city = base.model_copy(update={"recordings": [base.recordings[0],
                                                     base.recordings[1].model_copy(update={"coverage": None})]})
    res = _gather(tmp_path, DSO, no_city, DSO_IDENT)
    assert not any("disagree on city" in f for f in res.show.review_flags)
    same_city = base.model_copy(update={"city": "Madison, WI", "venue": "Barrymore Theatre"})
    res = _gather(tmp_path, DSO, same_city, DSO_IDENT)
    assert not any("disagree on city" in f for f in res.show.review_flags)
    assert res.show.venue == "Barrymore Theatre"          # step 1: the vote ships, no churn


def test_1a_blank_jerrybase_venue_is_no_evidence_when_cities_agree(tmp_path):
    md = json.loads(DSO.read_text())
    cand = Candidate(performance_id="DarkStarOrchestra/2012-05-19", collection="DarkStarOrchestra",
                     date="2012-05-19", venue="Mighty High Festival-Tuxedo Ridge", city="Tuxedo, NY",
                     recordings=[RecordingSummary(identifier=DSO_IDENT, venue="Mighty High Festival-Tuxedo Ridge",
                                                  coverage="Tuxedo, NY")])
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(md), None, cand, DSO_IDENT, jerrybase_enabled=True)
    assert not any(f.startswith("venue mismatch") for f in res.show.review_flags)
    far = cand.model_copy(update={"city": "Albany, NY",
                                  "recordings": [cand.recordings[0].model_copy(update={"coverage": "Albany, NY"})]})
    res = compute_gather(ShowWorkspace(tmp_path / "s2"), StubIA(md), None, far, DSO_IDENT, jerrybase_enabled=True)
    assert "venue mismatch: archive 'Mighty High Festival-Tuxedo Ridge' vs jerrybase ''" in res.show.review_flags


def test_1c_same_city_different_name_becomes_a_note_and_ships_the_selected_string(tmp_path):
    cand = _dso_candidate().model_copy(update={
        "venue": "Orpheum", "city": "Madison, WI",
        "recordings": [RecordingSummary(identifier=DSO_IDENT, venue="Orpheum", coverage="Madison, WI")]})
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Orpheum"
    assert "venue differs from jerrybase: archive 'Orpheum' vs 'Barrymore Theatre' (same city)" in res.notes
    assert not any(f.startswith("venue mismatch") for f in res.show.review_flags)


def test_1a_blank_vote_venue_on_a_blank_jerrybase_venue_takes_nothing_from_jerrybase(tmp_path):
    md = json.loads(DSO.read_text())
    cand = Candidate(performance_id="DarkStarOrchestra/2012-05-19", collection="DarkStarOrchestra",
                     date="2012-05-19", venue="", city="Tuxedo, NY",
                     recordings=[RecordingSummary(identifier=DSO_IDENT, coverage="Tuxedo, NY")])
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(md), None, cand, DSO_IDENT, jerrybase_enabled=True)
    assert (res.show.city, res.show.venue_source) == ("Tuxedo, NY", "item")   # not jerrybase's "Tuxedo Park"
    assert not any(f.startswith("venue mismatch") for f in res.show.review_flags)


def test_1c_does_not_apply_on_a_per_event_candidate_of_a_multi_event_date(tmp_path, monkeypatch):
    from llama.models import JerrybaseEvent
    early = JerrybaseEvent(event_id="e1", venue="Barrymore Theatre", city="Madison", state="WI")
    late = JerrybaseEvent(event_id="e2", venue="Barrymore Theatre", city="Madison", state="WI")
    monkeypatch.setattr(gather_mod.jerrybase, "lookup", lambda artist, date: [early, late])
    cand = _dso_candidate().model_copy(update={
        "performance_id": "DarkStarOrchestra/2003-01-25/e1", "venue": "Orpheum", "city": "Madison, WI",
        "recordings": [RecordingSummary(identifier=DSO_IDENT, venue="Orpheum", coverage="Madison, WI")]})
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert not any(n.startswith("venue differs from jerrybase") for n in res.notes)
    assert "venue mismatch: archive 'Orpheum' vs jerrybase 'Barrymore Theatre'" in res.show.review_flags


def test_1c_declines_on_incompatible_cities_and_keeps_the_flag(tmp_path):
    cand = _dso_candidate().model_copy(update={
        "recordings": [RecordingSummary(identifier=DSO_IDENT, venue="Orpheum", coverage="St. Louis, MO")]})
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert "venue mismatch: archive 'The Pageant' vs jerrybase 'Barrymore Theatre'" in res.show.review_flags


def test_selected_recording_missing_from_candidate_is_no_swap_and_no_1d(tmp_path):
    # Review Focus 1.
    cand = _dso_candidate().model_copy(update={"recordings": [_dso_candidate().recordings[0]]})
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "The Pageant"
    assert "venue mismatch: archive 'The Pageant' vs jerrybase 'Barrymore Theatre'" in res.show.review_flags
    assert not any("disagree on city" in f for f in res.show.review_flags)


def test_the_signature_blocks_the_swap_when_the_selected_tape_agrees_with_jerrybase(tmp_path):
    # Mutation (a) survivor: above, the selected dodd tape is the Rambler Room
    # one, so the swap could never fire there. Here the selected tape is the
    # Uptown one, which agrees with jerrybase: only the two-venue signature
    # keeps the vote and the hold.
    wiley = "gd78-11-17.paud.wiley.11488.sbeok.shnf"
    recs = [RecordingSummary(identifier=GD78_IDENT, venue="Rambler Room, Loyola College", coverage="Chicago, IL"),
            RecordingSummary(identifier=wiley, venue="Uptown Theatre", coverage="Chicago, IL")]
    cand = Candidate(performance_id="GratefulDead/1978-11-17", collection="GratefulDead", date="1978-11-17",
                     venue="Rambler Room, Loyola College", city="Chicago, IL", recordings=recs)
    res = _gather(tmp_path, GD78, cand, wiley)
    assert res.show.venue == "Rambler Room, Loyola College"
    assert "venue mismatch: archive 'Rambler Room, Loyola College' vs jerrybase 'Uptown Theatre'" in res.show.review_flags
    assert not any(n.startswith("venue taken from the selected recording") for n in res.notes)


# --- Task 13 fix round 1: the city check on step 1 and on the swap, 1d's blank vote city ---

def _penns_landing_event(monkeypatch):
    from llama.models import JerrybaseEvent
    ev = JerrybaseEvent(event_id="e1", venue="Penn's Landing", city="Philadelphia", state="PA")
    monkeypatch.setattr(gather_mod.jerrybase, "lookup", lambda artist, date: [ev])


def test_step_1_needs_compatible_cities_not_just_an_equivalent_venue(tmp_path, monkeypatch):
    # Task 13b re-target (narrowing S): the vote's venue is equivalent to
    # jerrybase's only under slice 1's 1b (the apostrophe deletion), and its
    # city (and the one recording's) is Camden against jerrybase's
    # Philadelphia: the city check applies, so no wrong clear.
    _penns_landing_event(monkeypatch)
    cand = Candidate(performance_id="DarkStarOrchestra/2003-01-25", collection="DarkStarOrchestra",
                     date="2003-01-25", venue="Penns Landing", city="Camden, NJ",
                     recordings=[RecordingSummary(identifier=DSO_IDENT, venue="Penns Landing",
                                                  coverage="Camden, NJ")])
    assert not two_venue_signature(cand)
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Penns Landing"
    assert "venue mismatch: archive 'Penns Landing' vs jerrybase 'Penn's Landing'" in res.show.review_flags


def test_step_1_newly_equivalent_pair_with_compatible_cities_clears(tmp_path, monkeypatch):
    _penns_landing_event(monkeypatch)
    cand = Candidate(performance_id="DarkStarOrchestra/2003-01-25", collection="DarkStarOrchestra",
                     date="2003-01-25", venue="Penns Landing", city="Philadelphia, PA",
                     recordings=[RecordingSummary(identifier=DSO_IDENT, venue="Penns Landing",
                                                  coverage="Philadelphia, PA")])
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Penns Landing"
    assert not any(f.startswith("venue mismatch") for f in res.show.review_flags)


def test_step_1_pre_slice_equivalent_pair_clears_without_a_city_check(tmp_path):
    # Narrowing S: Barrymore Theater/Theatre was equivalent before slice 1, so
    # step 1 passes on equivalence alone however the cities compare (the
    # Roosevelt Stadium 'Jersey City, NJ' vs jerrybase 'NY' shape).
    cand = Candidate(performance_id="DarkStarOrchestra/2003-01-25", collection="DarkStarOrchestra",
                     date="2003-01-25", venue="Barrymore Theater", city="St. Louis, MO",
                     recordings=[RecordingSummary(identifier=DSO_IDENT, venue="Barrymore Theater",
                                                  coverage="St. Louis, MO")])
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert (res.show.venue, res.show.city) == ("Barrymore Theater", "St. Louis, MO")
    assert not any(f.startswith("venue mismatch") for f in res.show.review_flags)
    assert not any("disagree on city" in f for f in res.show.review_flags)


def test_the_swap_needs_compatible_cities_not_just_an_equivalent_venue(tmp_path):
    cand = Candidate(performance_id="DarkStarOrchestra/2003-01-25", collection="DarkStarOrchestra",
                     date="2003-01-25", venue="The Pageant", city="St. Louis, MO",
                     recordings=[RecordingSummary(identifier=DSO_IDENT, venue="Barrymore Theater",
                                                  coverage="St. Louis, MO")])
    assert not two_venue_signature(cand)
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "The Pageant"
    assert "venue mismatch: archive 'The Pageant' vs jerrybase 'Barrymore Theatre'" in res.show.review_flags
    assert not any(n.startswith("venue taken from the selected recording") for n in res.notes)


def test_1d_a_whitespace_only_vote_city_is_unknown_and_no_conflict(tmp_path):
    cand = Candidate(performance_id="DarkStarOrchestra/2003-01-25", collection="DarkStarOrchestra",
                     date="2003-01-25", venue="Barrymore Theatre", city="   ",
                     recordings=[RecordingSummary(identifier=DSO_IDENT, venue="Barrymore Theater",
                                                  coverage="Madison, WI")])
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert not any("disagree on city" in f for f in res.show.review_flags)
    assert res.show.venue == "Barrymore Theatre"


# --- Task 13b, narrowing V: 1d only on a genuine second venue ---

def _red_rocks_candidate(vote_venue):
    # The mymorningjacket-2008-08-21 shape: Red Rocks is in Morrison, the vote
    # says Denver. Guster has no jerrybase data, so only 1d can speak.
    return Candidate(performance_id="Guster/2003-07-10", collection="Guster", date="2003-07-10",
                     venue=vote_venue, city="Denver, CO",
                     recordings=[RecordingSummary(identifier="guster2003-07-10.fm.shnf",
                                                  venue="Red Rocks Amphitheatre", coverage="Denver, CO"),
                                 RecordingSummary(identifier=G_IDENT, venue="Red Rocks Amphitheater",
                                                  coverage="Morrison, CO")])


def test_1d_does_not_fire_when_the_selected_venue_is_the_votes_hall(tmp_path):
    res = _gather(tmp_path, GUSTER, _red_rocks_candidate("Red Rocks Amphitheatre"), G_IDENT)
    assert not any("disagree on city" in f for f in res.show.review_flags)
    assert (res.show.venue, res.show.city) == ("Red Rocks Amphitheatre", "Denver, CO")


@pytest.mark.parametrize("vote_venue", ["", "   "])
def test_1d_a_blank_vote_venue_is_not_the_same_hall_and_still_holds(tmp_path, vote_venue):
    res = _gather(tmp_path, GUSTER, _red_rocks_candidate(vote_venue), G_IDENT)
    assert (res.show.venue, res.show.city) == ("Red Rocks Amphitheater", "Morrison, CO")
    assert "recordings of this date disagree on city: 'Morrison, CO' (selected) vs 'Denver, CO'" in res.show.review_flags


def test_5a_passes_numbered_sets_only_unless_the_encore_was_lost(tmp_path, monkeypatch):
    seen = {}
    real = gather_mod.structure_guard

    def spy(tracks, breaks, evidence_sets=None, **kw):
        seen["evidence"] = set(evidence_sets or ())
        return real(tracks, breaks, evidence_sets=evidence_sets, **kw)

    monkeypatch.setattr(gather_mod, "structure_guard", spy)
    compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(), FakeProvider(), make_candidate(), IDENT,
                   jerrybase_enabled=False)
    assert seen["evidence"] == {"1", "2"}            # the encore matched: dropped from the evidence
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = md["metadata"]["description"].replace("Johnny B. Goode", "Casey Jones")
    sixth = next(f for f in md["files"] if f["name"] == "gd73-06-10d3t01.mp3")
    sixth["title"] = "Johnny B. Goode"               # a real tag, so the count-equal setlist rung cannot copy "Casey Jones" onto it
    compute_gather(ShowWorkspace(tmp_path / "s2"), StubIA(md), FakeProvider(), make_candidate(), IDENT,
                   jerrybase_enabled=False)
    assert "encore" in seen["evidence"]              # the encore item no longer matches: kept


def test_5c1_filler_tail_note_goes_to_notes_json_never_to_structure_conflicts(tmp_path, monkeypatch):
    # The gd73 tape has no filler track, so jerrybase's filler predicate is
    # pointed at "I Know You Rider" (track 3, set 1): set 1's closer "China Cat
    # Sunflower" (track 2) is then followed only by "filler" before the break.
    # The missing set-2 closer keeps anchor_breaks declining, so the closer
    # tripwire runs.
    event = JerrybaseEvent(event_id="x", venue="RFK Stadium", city="Washington", state="DC", sets=[
        JerrybaseSet(name="1", closer="China Cat Sunflower", break_length="long"),
        JerrybaseSet(name="2", closer="Not On This Tape", break_length="long")])
    monkeypatch.setattr(gather_mod.jerrybase, "lookup", lambda artist, date: [event])
    monkeypatch.setattr(gather_mod.jerrybase, "is_filler", lambda title: title == "I Know You Rider")
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(), FakeProvider(), make_candidate(), IDENT,
                         jerrybase_enabled=True)
    assert res.show.structure.alignment == "deterministic"
    note = "jerrybase set closer 'China Cat Sunflower' is followed only by filler before the set break"
    assert note in res.notes
    assert note not in res.show.structure.conflicts
    assert "jerrybase set closer 'Not On This Tape' not found in tracks" in res.show.structure.conflicts
    assert not any(f.startswith("jerrybase set closer") for f in res.show.review_flags)


# --- slice B: venue tie-break ---

from llama.grouping import _make_candidate
from llama.stages.gather import venue_tie_break


def _cand(pid, coll, date, *specs):   # specs: (identifier, venue, coverage)
    return _make_candidate(pid, coll, [RecordingSummary(identifier=i, date=date, venue=v, coverage=c)
                                       for i, v, c in specs])


def _gd(tmp_path, cand):
    return compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(), None, cand, IDENT, jerrybase_enabled=False)


def _venue_flags(show):
    return [f for f in show.review_flags if f.startswith(("venue mismatch", "recordings of this date disagree"))]


def test_tie_ships_the_selected_recordings_string_without_jerrybase(tmp_path):
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("gd73-other", "R.F.K. Stadium", "Washington"), (IDENT, " RFK Stadium ", "Washington, DC"))
    assert cand.venue == "R.F.K. Stadium"                         # listing order won the 1-1 tie
    res = _gd(tmp_path, cand)
    assert (res.show.venue, res.show.city, res.show.venue_source) == ("RFK Stadium", "Washington, DC", "item")
    assert _venue_flags(res.show) == []


def test_a_tie_between_different_names_ships_the_vote_unchanged(tmp_path):
    # Owner ruling 2026-10-21: the tie-break applies only to venues_equivalent strings.
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("gd73-other", "9:30 Club", "Washington, DC"), (IDENT, "Nightclub", "Washington, DC"))
    assert cand.venue == "9:30 Club"
    res = _gd(tmp_path, cand)
    assert (res.show.venue, res.show.city) == ("9:30 Club", "Washington, DC")
    assert _venue_flags(res.show) == []


def test_a_majority_keeps_the_consensus(tmp_path):   # (pin)
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("a", "R.F.K. Stadium", "Washington, DC"), ("b", "R.F.K. Stadium", "Washington, DC"),
                 (IDENT, "RFK Stadium", "Washington, DC"))
    assert _gd(tmp_path, cand).show.venue == "R.F.K. Stadium"


def test_a_tie_whose_selected_city_is_incompatible_ships_the_vote_unchanged(tmp_path):   # (pin)
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("gd73-other", "RFK Stadium", "Washington, DC"), (IDENT, "RFK Stadium ", "Baltimore, MD"))
    res = _gd(tmp_path, cand)
    assert (res.show.venue, res.show.city) == ("RFK Stadium", "Washington, DC")


def test_a_tie_with_a_blank_selected_city_keeps_the_vote_city(tmp_path):
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("gd73-other", "R.F.K. Stadium", "Washington, DC"), (IDENT, "RFK Stadium", None))
    assert (lambda s: (s.venue, s.city))(_gd(tmp_path, cand).show) == ("RFK Stadium", "Washington, DC")


def test_a_whitespace_only_selected_venue_never_ships(tmp_path):   # (pin) Review Focus 3
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("gd73-other", "RFK Stadium", "Washington, DC"), (IDENT, "   ", "Washington, DC"))
    assert _gd(tmp_path, cand).show.venue == "RFK Stadium"


def test_step_1_tie_ships_the_selected_string_jerrybase_corroborates(tmp_path, monkeypatch):
    _penns_landing_event(monkeypatch)
    cand = _cand("DarkStarOrchestra/2003-01-25", "DarkStarOrchestra", "2003-01-25",
                 ("ds-other", "Penn's Landing", "Philadelphia, PA"), (DSO_IDENT, "Penns Landing", "Philadelphia, PA"))
    assert cand.venue == "Penn's Landing"
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Penns Landing" and _venue_flags(res.show) == []


def test_step_1_tie_keeps_the_vote_when_the_selected_string_is_newly_equivalent_and_cities_conflict(tmp_path, monkeypatch):   # (pin)
    # Narrowing S: the vote passes step 1 on pre-1b equivalence alone; the selected string is
    # equivalent only under 1b, and Camden is not jerrybase's Philadelphia, so it fails step 1's full test.
    _penns_landing_event(monkeypatch)
    cand = _cand("DarkStarOrchestra/2003-01-25", "DarkStarOrchestra", "2003-01-25",
                 ("ds-other", "Penn's Landing", "Camden, NJ"), (DSO_IDENT, "Penns Landing", "Camden, NJ"))
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Penn's Landing" and _venue_flags(res.show) == []


def test_step_1_tie_keeps_the_vote_when_jerrybase_does_not_corroborate_the_selected_string(tmp_path):   # (pin)
    cand = _cand("DarkStarOrchestra/2003-01-25", "DarkStarOrchestra", "2003-01-25",
                 ("ds-other", "Barrymore Theatre Madison", "Madison, WI"), (DSO_IDENT, "Madison", "Madison, WI"))
    # Reshaped under the 2026-10-21 narrowing: the pair must be venues_equivalent to
    # reach step 1's corroboration test ("Madison" is, to the vote, not to jerrybase).
    assert venue_tie_break(cand, cand.recordings[1]) is not None
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Barrymore Theatre Madison" and _venue_flags(res.show) == []


def _blank_venue_event(monkeypatch, city="Philadelphia", state="PA"):
    from llama.models import JerrybaseEvent
    ev = JerrybaseEvent(event_id="e1", venue="", city=city, state=state)
    monkeypatch.setattr(gather_mod.jerrybase, "lookup", lambda artist, date: [ev])


def test_1a_tie_ships_the_selected_string_when_cities_agree(tmp_path, monkeypatch):
    _blank_venue_event(monkeypatch)
    cand = _cand("DarkStarOrchestra/2003-01-25", "DarkStarOrchestra", "2003-01-25",
                 ("ds-other", "Penn's Landing", "Philadelphia, PA"), (DSO_IDENT, "Penns Landing", "Philadelphia, PA"))
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Penns Landing" and _venue_flags(res.show) == []


def test_1a_tie_keeps_the_vote_when_the_cities_conflict(tmp_path, monkeypatch):   # (pin)
    _blank_venue_event(monkeypatch)
    cand = _cand("DarkStarOrchestra/2003-01-25", "DarkStarOrchestra", "2003-01-25",
                 ("ds-other", "Penn's Landing", "Camden, NJ"), (DSO_IDENT, "Penns Landing", "Camden, NJ"))
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Penn's Landing"
    assert "venue mismatch: archive 'Penn's Landing' vs jerrybase ''" in res.show.review_flags


def test_an_operator_venue_override_takes_no_tie_break_city(tmp_path):
    # jackiegreene-2010-05-29 shape: tied vote, the selected recording's city differs only in case.
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("gd73-other", "Frogs Hall", "Angels Camp, California"),
                 (IDENT, "Frogs Hall Theatre", "angels camp, california"))
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.overrides, Overrides(venue="Operator Venue"))
    res = compute_gather(sws, StubIA(), None, cand, IDENT, jerrybase_enabled=False)
    assert (res.show.venue, res.show.city, res.show.venue_source) == (
        "Operator Venue", "Angels Camp, California", "override")


def test_a_city_only_override_keeps_the_tie_broken_venue(tmp_path):
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("gd73-other", "R.F.K. Stadium", "Washington, DC"), (IDENT, "RFK Stadium", "Washington, DC"))
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.overrides, Overrides(city="Elsewhere"))
    res = compute_gather(sws, StubIA(), None, cand, IDENT, jerrybase_enabled=False)
    assert (res.show.venue, res.show.city) == ("RFK Stadium", "Elsewhere")


def test_venue_tie_break_unit_cases():
    recs = [RecordingSummary(identifier="a", venue="X Hall", coverage="Austin, TX"),
            RecordingSummary(identifier="b", venue="X Hall ", coverage=None)]
    cand = _make_candidate("A/2000-01-01", "A", recs)
    assert venue_tie_break(cand, recs[1]) == ("X Hall", "Austin, TX")   # raw strings counted apart
    assert venue_tie_break(cand, recs[0]) is None                        # the selected string IS the vote
    assert venue_tie_break(cand, None) is None
    odd = cand.model_copy(update={"venue": "Elsewhere"})                 # a vote no recording carries
    assert venue_tie_break(odd, recs[1]) is None
    stray = RecordingSummary(identifier="z", venue="Y Hall", coverage=None)
    assert venue_tie_break(odd, stray) is None                           # 0 == 0 is not a tie


# --- Held-backlog piece 2, Task 4: the taper's markers own the structure -----
# (spec docs/superpowers/specs/2026-10-22-taper-set-markers-design.md, sections
# 2, 4 and 6). Every "exactly today" pin compares against the ORACLE: the same
# candidate gathered with `llama.taper.decide_taper` patched to a not-owned
# decision. Ruling R2: the comparison excludes the `taper` field on both sides
# (`_sans_taper`), since the oracle replaces the decision object by
# construction; every other field, `step1_alignment` and `taper_owned`
# included, must be equal.

import llama.taper as taper_mod
from llama.models import SetlistItem, StructureInfo
from llama.structure import align

TP_IDENT = "tb1999-07-04.sbd.flac16"
TP_SONGS = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf"]
TP_DESC = "Set 1:\nAlpha\nBravo\nCharlie\nSet 2:\nDelta\nEcho\nFoxtrot\nEncore:\nGolf"


def _tp_md(titles, description="", *, notes=None, lengths=None, creator="Taper Band"):
    """A one-recording item: lossless originals plus tagged mp3 derivatives."""
    files = []
    for i, title in enumerate(titles, 1):
        stem = f"tb1999-07-04t{i:02d}"
        files.append({"name": f"{stem}.flac", "source": "original", "format": "Flac",
                      "md5": f"{i:032x}"})
        files.append({"name": f"{stem}.mp3", "source": "derivative", "original": f"{stem}.flac",
                      "format": "VBR MP3", "length": (lengths or {}).get(i, "05:00"),
                      "md5": f"{i + 100:032x}", "title": title})
    meta = {"identifier": TP_IDENT, "creator": creator, "date": "1999-07-04",
            "description": description}
    if notes is not None:
        meta["notes"] = notes
    return {"metadata": meta, "files": files, "reviews": []}


def _tp_candidate():
    return Candidate(performance_id="TaperBand/1999-07-04", collection="TaperBand",
                     date="1999-07-04", venue="The Hall", city="Somewhere, ST",
                     recordings=[RecordingSummary(identifier=TP_IDENT)])


class _FakeSetlistFM:
    """`build_canonical`'s setlist.fm client: one fixed setlist. Each set is a
    list of names; `encore=True` marks the last set as setlist.fm's encore."""

    def __init__(self, *sets, encore=False):
        self.raw = {"sets": {"set": [
            {"song": [{"name": n} for n in names],
             **({"encore": 1} if encore and k == len(sets) - 1 else {})}
            for k, names in enumerate(sets)]}}

    def setlist(self, artist, date, *, venue=None, city=None):
        return self.raw


def _tp_gather(tmp_path, md, *, sub="s", overrides=None, cand=None, ident=TP_IDENT, **kw):
    sws = ShowWorkspace(tmp_path / sub)
    if overrides is not None:
        write_artifact(sws.overrides, overrides)
    return compute_gather(sws, StubIA(md), None, cand or _tp_candidate(), ident, **kw)


def _not_owned(tracks, meta, *, aliases, today_sets, today_reaches_llm):
    return taper_mod.TaperDecision(None, taper_mod.read_taper_structure(""), "none", "oracle")


def _oracle(tmp_path, monkeypatch, md, **kw):
    with monkeypatch.context() as m:
        m.setattr(taper_mod, "decide_taper", _not_owned)
        return _tp_gather(tmp_path, md, sub="oracle", **kw)


def _sans_taper(res):
    return res._replace(taper=None)


def _labels(res):
    return [t.set for t in res.show.tracks]


def _was_notes(res):
    return [n for n in res.notes if n.startswith("set breaks from the taper's markers")]


def test_taper_structure_beats_unlabelled_setlistfm(tmp_path, monkeypatch):
    md = _tp_md(TP_SONGS, TP_DESC)
    res = _tp_gather(tmp_path, md, setlistfm=_FakeSetlistFM(TP_SONGS))
    assert _labels(_oracle(tmp_path, monkeypatch, md, setlistfm=_FakeSetlistFM(TP_SONGS))) == ["1"] * 7
    assert _labels(res) == ["1", "1", "1", "2", "2", "2", "encore"]
    assert res.show.structure.source == "setlist.fm"
    assert res.show.structure.taper_owned is True
    assert res.show.structure.alignment == "taper"
    assert res.taper_owned is True
    assert res.step1_alignment == "deterministic"
    assert _was_notes(res) == ["set breaks from the taper's markers (was [] ['1'])"]
    assert not any(n.startswith("set breaks from the taper") for n in res.show.structure.conflicts)
    assert not any(f.startswith(("setlist evidence shows multiple sets", "single-set"))
                   for f in res.show.review_flags)


def test_taper_agreeing_with_today_keeps_alignment(tmp_path):
    res = _tp_gather(tmp_path, _tp_md(TP_SONGS, TP_DESC))
    assert _labels(res) == ["1", "1", "1", "2", "2", "2", "encore"]
    assert res.show.structure.alignment == "deterministic"
    assert res.show.structure.taper_owned is True
    assert res.taper_owned is True
    assert _was_notes(res) == []


def test_label_rename_at_same_positions_is_recorded(tmp_path, monkeypatch):
    md = _tp_md(TP_SONGS, TP_DESC)
    slfm = _FakeSetlistFM(TP_SONGS[:3], TP_SONGS[3:6], TP_SONGS[6:])
    assert _labels(_oracle(tmp_path, monkeypatch, md, setlistfm=slfm)) == [
        "1", "1", "1", "2", "2", "2", "3"]
    res = _tp_gather(tmp_path, md, setlistfm=slfm)
    assert _labels(res) == ["1", "1", "1", "2", "2", "2", "encore"]
    assert res.show.set_breaks == [3, 6]
    assert res.show.structure.alignment == "taper"
    assert _was_notes(res) == ["set breaks from the taper's markers (was [3, 6] ['1', '2', '3'])"]


def test_taper_beats_jerrybase_anchoring(tmp_path, monkeypatch):
    # A PLF-shaped jerrybase row: one set, closing on the tape's last song.
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event([("Golf", "1")])])
    md = _tp_md(TP_SONGS, "Set 1:\nAlpha\nBravo\nCharlie\nSet 2:\nDelta\nEcho\nFoxtrot\nGolf")
    oracle = _oracle(tmp_path, monkeypatch, md, jerrybase_enabled=True)
    assert _labels(oracle) == ["1"] * 7
    assert oracle.show.structure.alignment == "jerrybase"
    assert any(c.startswith("set breaks anchored from jerrybase")
               for c in oracle.show.structure.conflicts)
    res = _tp_gather(tmp_path, md, jerrybase_enabled=True)
    assert res.taper_owned is True
    assert res.step1_alignment == "jerrybase"
    assert _labels(res) == ["1", "1", "1", "2", "2", "2", "2"]
    assert res.show.structure.alignment == "taper"
    assert not any(c.startswith("set breaks anchored from jerrybase")
                   for c in res.show.structure.conflicts)
    assert not any(n.startswith("set breaks anchored from jerrybase") for n in res.notes)
    assert _was_notes(res) == ["set breaks from the taper's markers (was [] ['1'])"]


_MISMATCHED_SLFM = ["Zulu One", "Zulu Two", "Zulu Three", "Zulu Four", "Zulu Five",
                    "Zulu Six", "Zulu Seven"]


def test_taper_owned_skips_align_structure(tmp_path, monkeypatch):
    md = _tp_md(TP_SONGS, TP_DESC)
    slfm = _FakeSetlistFM(_MISMATCHED_SLFM)
    oracle = _oracle(tmp_path, monkeypatch, md, setlistfm=slfm, align_provider=None)
    assert "align_structure" in oracle.needs_llm          # today reaches the LLM branch
    res = _tp_gather(tmp_path, md, setlistfm=slfm, align_provider=None)
    assert res.taper_owned is True
    assert "align_structure" not in res.needs_llm


def test_taper_owned_never_calls_the_align_provider(tmp_path):
    provider = FakeProvider()
    res = _tp_gather(tmp_path, _tp_md(TP_SONGS, TP_DESC),
                     setlistfm=_FakeSetlistFM(_MISMATCHED_SLFM), align_provider=provider)
    assert res.taper_owned is True
    assert provider.calls == []


def test_owned_low_confidence_uses_reader_coverage(tmp_path):
    slfm = _FakeSetlistFM(_MISMATCHED_SLFM)
    # Step-1 coverage is 0 (setlist.fm shares nothing with the tape), no
    # anchoring. The reader's items all match: no flag, coverage 1.0.
    good = _tp_gather(tmp_path, _tp_md(TP_SONGS, TP_DESC), sub="good", setlistfm=slfm)
    assert good.taper_owned is True
    assert "low-confidence structure alignment" not in good.show.review_flags
    assert good.show.structure.coverage == 1.0
    assert good.needs_llm == ()
    # The reader's items match only the four boundary songs: 4 of 7 song tracks.
    # This show is on today's LLM path, so the taper must mark its encore to own
    # it at all (G1, llama-db reading of operator ruling (d), 2026-10-22).
    weak_desc = ("Set 1:\nZed One\nZed Two\nCharlie\nSet 2:\nDelta\nZed Three\nFoxtrot\n"
                 "Encore:\nGolf")
    weak = _tp_gather(tmp_path, _tp_md(TP_SONGS, weak_desc), sub="weak", setlistfm=slfm)
    assert weak.taper_owned is True
    assert "low-confidence structure alignment" in weak.show.review_flags
    assert weak.needs_llm == ()
    assert weak.show.structure.coverage == pytest.approx(4 / 7)
    reader = ParsedSetlist(items=[SetlistItem(title=i.title, normalized=normalize_song(i.title),
                                              set=i.set) for i in weak.taper.taper.items])
    assert weak.show.structure.coverage == align(weak.show.tracks, reader).coverage
    # No canonical items at all (no setlist.fm, a description with no setlist;
    # the notes carry the markers): today never reaches the flag, nor does this.
    bare = _tp_gather(tmp_path, _tp_md(TP_SONGS, "", notes=TP_DESC), sub="bare")
    assert bare.taper_owned is True
    assert "low-confidence structure alignment" not in bare.show.review_flags
    assert bare.show.structure.coverage == 1.0


# The owned-show flag needs ALL FOUR conditions (canonical items, no
# anchoring, step-1 coverage under the threshold, reader coverage under it).
# Each test below keeps the reader's coverage weak (2 of 7) and removes exactly
# one of the other three, so each condition is pinned on its own (fix round 1).
_WEAK_DESC = ("Set 1:\nZed One\nZed Two\nCharlie\nSet 2:\nDelta\nZed Three\nZed Four\n"
              "Zed Five")


def _assert_weak_reader_no_flag(res):
    assert res.taper_owned is True
    assert res.show.structure.coverage == pytest.approx(2 / 7)    # reader under the threshold
    assert "low-confidence structure alignment" not in res.show.review_flags
    assert res.needs_llm == ()


def test_owned_low_confidence_needs_canonical_items(tmp_path):
    # No setlist.fm and an empty description: no canonical items; the notes
    # carry the weak markers.
    res = _tp_gather(tmp_path, _tp_md(TP_SONGS, "", notes=_WEAK_DESC))
    assert res.taper.source == "notes"
    _assert_weak_reader_no_flag(res)


def test_owned_low_confidence_needs_no_anchoring(tmp_path, monkeypatch):
    # setlist.fm shares nothing with the tape (step-1 coverage 0), but
    # jerrybase anchoring succeeds, so today never reaches the LLM branch.
    monkeypatch.setattr(jerrybase, "lookup",
                        lambda a, d: [_jb_event([("Charlie", "1"), ("Golf", "2")])])
    res = _tp_gather(tmp_path, _tp_md(TP_SONGS, _WEAK_DESC),
                     setlistfm=_FakeSetlistFM(_MISMATCHED_SLFM), jerrybase_enabled=True)
    assert res.step1_alignment == "jerrybase"
    _assert_weak_reader_no_flag(res)


def test_owned_low_confidence_needs_weak_step_one(tmp_path):
    # setlist.fm matches the tape (step-1 coverage 1.0); only the reader is weak.
    res = _tp_gather(tmp_path, _tp_md(TP_SONGS, _WEAK_DESC), setlistfm=_FakeSetlistFM(TP_SONGS))
    assert res.step1_alignment == "deterministic"
    _assert_weak_reader_no_flag(res)


def test_track_title_veto_is_exactly_today(tmp_path, monkeypatch):
    titles = TP_SONGS[:6] + ["Encore: Box Of Rain"]
    md = _tp_md(titles, "Set 1:\nAlpha\nBravo\nCharlie\nSet 2:\nDelta\nEcho\nFoxtrot\nBox Of Rain")
    res = _tp_gather(tmp_path, md)
    assert res.taper.reason == "veto: track title"
    assert res.taper_owned is False
    assert res.show.structure.taper_owned is False
    assert _sans_taper(res) == _sans_taper(_oracle(tmp_path, monkeypatch, md))


def test_not_owned_is_exactly_today(tmp_path, monkeypatch):
    # `Charlie` closes set 1 and is listed again in set 2: unplaceable.
    md = _tp_md(TP_SONGS, "Set 1:\nAlpha\nBravo\nCharlie\nSet 2:\nDelta\nCharlie\nFoxtrot\n"
                          "Encore:\nGolf")
    res = _tp_gather(tmp_path, md, setlistfm=_FakeSetlistFM(TP_SONGS))
    assert res.taper.reason.startswith("unplaced:")
    assert res.taper_owned is False
    assert _sans_taper(res) == _sans_taper(
        _oracle(tmp_path, monkeypatch, md, setlistfm=_FakeSetlistFM(TP_SONGS)))


def test_structure_override_bypasses_the_taper(tmp_path, monkeypatch):
    md = _tp_md(TP_SONGS, TP_DESC)

    def boom(*a, **k):
        raise AssertionError("decide_taper must not run on the override path")

    breaks = Overrides(set_breaks=["tb1999-07-04t03.mp3"])
    oracle = _oracle(tmp_path, monkeypatch, md, overrides=breaks)
    monkeypatch.setattr(taper_mod, "decide_taper", boom)
    res = _tp_gather(tmp_path, md, overrides=breaks)
    assert res.taper_owned is False
    assert res.taper is None and res.step1_alignment is None
    assert res.show.structure.alignment == "override"
    assert res.show.structure.taper_owned is False
    assert _sans_taper(res) == _sans_taper(oracle)


def test_notes_lineage_never_places(tmp_path, monkeypatch):
    md = _tp_md(TP_SONGS, "\n".join(TP_SONGS),
                notes="Set 1: MSR> C> DAT\nSet 2: MSC> DAT> CD")
    res = _tp_gather(tmp_path, md)
    assert res.taper.source == "notes"
    assert res.taper_owned is False
    assert _sans_taper(res) == _sans_taper(_oracle(tmp_path, monkeypatch, md))


def test_notes_used_when_description_has_no_marker(tmp_path):
    md = _tp_md(TP_SONGS, "\n".join(TP_SONGS),
                notes="Set One: Alpha, Bravo, Charlie\nSet Two: Delta, Echo, Foxtrot, Golf")
    res = _tp_gather(tmp_path, md)
    assert res.taper.source == "notes"
    assert res.taper_owned is True
    assert _labels(res) == ["1", "1", "1", "2", "2", "2", "2"]


def test_segues_and_matched_come_from_step_one(tmp_path, monkeypatch):
    md = _tp_md(TP_SONGS, "Set 1:\nAlpha > Bravo\nCharlie\nSet 2:\nDelta > Echo\nFoxtrot\n"
                          "Encore:\nGolf")
    slfm = _FakeSetlistFM(TP_SONGS)
    res = _tp_gather(tmp_path, md, setlistfm=slfm)
    oracle = _oracle(tmp_path, monkeypatch, md, setlistfm=slfm)
    assert res.taper_owned is True
    assert _labels(res) != _labels(oracle)
    assert any(t.segue for t in res.show.tracks)
    assert ([(t.segue, t.matched) for t in res.show.tracks]
            == [(t.segue, t.matched) for t in oracle.show.tracks])


def test_owned_show_drops_merge_conflicts_not_owned_keeps_them(tmp_path, monkeypatch):
    titles = ["Alpha", "Bravo", "Charlie > Delta", "Echo", "Foxtrot", "Golf", "Hotel"]
    md = _tp_md(titles, "Set 1:\nAlpha\nBravo\nCharlie > Delta\nEcho\nSet 2:\nFoxtrot\nGolf\n"
                        "Hotel")
    slfm = _FakeSetlistFM(["Alpha", "Bravo", "Charlie"],
                          ["Delta", "Echo", "Foxtrot", "Golf", "Hotel"])
    oracle = _oracle(tmp_path, monkeypatch, md, setlistfm=slfm)
    assert "merged track(s) 3 span a set break" in oracle.show.review_flags
    res = _tp_gather(tmp_path, md, setlistfm=slfm)
    assert res.taper_owned is True
    assert not any(f.startswith("merged track(s)") for f in res.show.review_flags)


def test_structure_info_created_without_canonical(tmp_path, monkeypatch):
    md = _tp_md(TP_SONGS, "", notes=TP_DESC)
    oracle = _oracle(tmp_path, monkeypatch, md)
    assert oracle.show.structure is None                  # today: no canonical, no notes
    res = _tp_gather(tmp_path, md)
    assert res.taper_owned is True
    assert res.show.structure is not None
    assert res.show.structure.taper_owned is True
    assert res.show.structure.source == "none"


def test_today_sets_is_step_one_parallel_to_tracks(tmp_path, monkeypatch):
    seen = {}
    real = taper_mod.decide_taper

    def spy(tracks, meta, *, aliases, today_sets, today_reaches_llm):
        seen["n"], seen["today"] = len(tracks), list(today_sets)
        return real(tracks, meta, aliases=aliases, today_sets=today_sets,
                    today_reaches_llm=today_reaches_llm)

    md = _tp_md(TP_SONGS, TP_DESC)
    slfm = _FakeSetlistFM(TP_SONGS[:3], TP_SONGS[3:6], TP_SONGS[6:])
    monkeypatch.setattr(taper_mod, "decide_taper", spy)
    _tp_gather(tmp_path, md, setlistfm=slfm)
    assert seen["n"] == 7 and len(seen["today"]) == 7
    assert seen["today"] == ["1", "1", "1", "2", "2", "2", "3"]   # step 1's labels


# umphreysmcgee-2004-04-14 (um2004-04-14.shnf): the description excerpt and
# track list, copied verbatim once from ~/.llama/cache/md_um2004-04-14.shnf.json.
# Its `Disc 3 - Set 2 + Encore` line asserts nothing and the later `e:` starts
# the encore, so the taper owns the structure, identically to today. "Today" is
# the shipped show, whose canonical is setlist.fm's (`parse_setlist` does not
# read `Disc 2 - Set 2`): its set names, copied verbatim once from the cached
# setlist.fm response (~/.llama/cache/slfm_6f592f90d24abbb461b32c5a41207695adfa1584.json).
UM_IDENT = "um2004-04-14.shnf"
UM_DESC = ('Disc 1 - Set 1\n\n01. The Fuzz >\n02. "Jimmy Stewart" >\n03. The Fuzz\n'
           '04. Nothing Too Fancy >\n05. The Girl is Mine > Jane Says > The Girl is Mine >\n'
           '06. Nothing Too Fancy\n07. Wife Soup\n08. Slacker >\n09. Professor Wormbog >\n'
           '10. Slacker\n11. Divisions\n\n\nDisc 2 - Set 2\n\n01. Mail Package\n'
           '02. Front Porch >\n03. Resolution >\n04. Front Porch\n05. Thin Air\n\n\n'
           'Disc 3 - Set 2 + Encore\n\n01. The Stranger\n02. Walletsworth\n03. Ocean Billy\n'
           'e:\n04. Kabump >\n05. Nemo')
UM_FILES = [  # (name, title, length) of the VBR MP3 derivatives
    ("um2004-04-14d1t01", "The Fuzz >", "02:44"),
    ("um2004-04-14d1t02", '"Jimmy Stewart"', "05:49"),
    ("um2004-04-14d1t03", "The Fuzz", "02:52"),
    ("um2004-04-14d1t04", "Nothing Too Fancy >", "10:09"),
    ("um2004-04-14d1t05", "The Girl is Mine > Jane Says > The Girl is Mine >", "03:57"),
    ("um2004-04-14d1t06", "Nothing Too Fancy", "09:51"),
    ("um2004-04-14d1t07", "Wife Soup", "09:59"),
    ("um2004-04-14d1t08", "Slacker >", "02:25"),
    ("um2004-04-14d1t09", "Professor Wormbog >", "04:33"),
    ("um2004-04-14d1t10", "Slacker", "05:17"),
    ("um2004-04-14d1t11", "Divisions", "11:59"),
    ("um2004-04-14d2t01", "Mail Package", "06:46"),
    ("um2004-04-14d2t02", "Front Porch >", "01:14"),
    ("um2004-04-14d2t03", "Resolution >", "06:00"),
    ("um2004-04-14d2t04", "Front Porch", "05:26"),
    ("um2004-04-14d2t05", "Thin Air", "27:24"),
    ("um2004-04-14d3t01", "The Stranger", "09:23"),
    ("um2004-04-14d3t02", "Walletsworth", "05:32"),
    ("um2004-04-14d3t03", "Ocean Billy", "13:27"),
    ("um2004-04-14d3t04", "Kabump >", "07:29"),
    ("um2004-04-14d3t05", "Nemo", "05:00"),
]


UM_SLFM = (["The Fuzz", "Jimmy Stewart", "The Fuzz", "Nothing Too Fancy", "The Girl Is Mine",
            "Jane Says", "The Girl Is Mine", "Nothing Too Fancy", "Wife Soup", "Slacker",
            "Professor Wormbog", "Slacker", "Divisions"],
           ["Mail Package", "Front Porch", "Resolution", "Front Porch", "Thin Air",
            "The Stranger", "Walletsworth", "Ocean Billy"],
           ["Kabump", "Nemo"])


def _um_md():
    files = []
    for i, (stem, title, length) in enumerate(UM_FILES, 1):
        files.append({"name": f"{stem}.shn", "source": "original", "format": "Shorten",
                      "title": title, "md5": f"{i:032x}"})
        files.append({"name": f"{stem}.mp3", "source": "derivative", "original": f"{stem}.shn",
                      "format": "VBR MP3", "title": title, "length": length,
                      "md5": f"{i + 100:032x}"})
    return {"metadata": {"identifier": UM_IDENT, "creator": "Umphreys McGee",
                         "date": "2004-04-14", "description": UM_DESC},
            "files": files, "reviews": []}


def test_umphreys_2004_04_14_taper_owned_identical_to_today(tmp_path, monkeypatch):
    # Its set-1 opener `The Fuzz` is on the tape twice in set 1; B4 checks the latest hit
    # (llama-db ruling, 2026-10-22, narrowed the same day), and step 1 has no break before it.
    cand = Candidate(performance_id="UmphreysMcGee/2004-04-14", collection="UmphreysMcGee",
                     date="2004-04-14", venue="Cervante's Masterpiece", city="Denver, CO",
                     recordings=[RecordingSummary(identifier=UM_IDENT)])
    md = _um_md()
    res = _tp_gather(tmp_path, md, cand=cand, ident=UM_IDENT,
                     setlistfm=_FakeSetlistFM(*UM_SLFM, encore=True))
    oracle = _oracle(tmp_path, monkeypatch, md, cand=cand, ident=UM_IDENT,
                     setlistfm=_FakeSetlistFM(*UM_SLFM, encore=True))
    assert res.taper.source == "description"
    assert res.taper_owned is True
    assert _labels(res) == _labels(oracle)
    # Piece 4 (spec 1): set 2's 01:14 `Front Porch >` (d2t02) is now kept, so the
    # set-2 break falls one track later.
    assert res.show.set_breaks == oracle.show.set_breaks == [11, 19]
    assert _labels(res)[-2:] == ["encore", "encore"]
    assert res.show.review_flags == oracle.show.review_flags
    assert res.show.structure.alignment == oracle.show.structure.alignment == "deterministic"
    assert _was_notes(res) == []


def test_old_structure_info_reads_without_taper_owned():
    old = StructureInfo.model_validate({"source": "chosen", "alignment": "deterministic",
                                        "coverage": 1.0, "conflicts": []})
    assert old.taper_owned is False


# --- Held-backlog piece 2, Task 5: jerrybase disagreements become notes -----

from llama.stages.gather import demote_jerrybase_flags

_TP_CHINA = ["Alpha", "China Doll", "Let It Grow", "Delta", "Echo", "Foxtrot", "Golf"]
_TP_CHINA_DESC = ("Set 1:\nAlpha\nChina Doll\nLet It Grow\nSet 2:\nDelta\nEcho\nFoxtrot\n"
                  "Encore:\nGolf")


def _jb(monkeypatch, *closers_and_names):
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(list(closers_and_names))])


def _spy_tripwire(monkeypatch):
    calls = []
    real = jerrybase.closer_contradictions

    def spy(tracks, event):
        calls.append(1)
        return real(tracks, event)
    monkeypatch.setattr(jerrybase, "closer_contradictions", spy)
    return calls


def _closer_flags(res):
    return [f for f in res.show.review_flags if f.startswith("jerrybase set closer")]


def _count_flags(res):
    return [f for f in res.show.review_flags if "jerrybase shows" in f]


def test_set_count_disagreement_is_a_note_when_taper_text_disagrees(tmp_path, monkeypatch):
    _jb(monkeypatch, ("Charlie", "1"))
    res = _tp_gather(tmp_path, _tp_md(TP_SONGS, TP_DESC), jerrybase_enabled=True)
    assert res.taper_owned is True
    assert _count_flags(res) == []
    assert "structure has 2 sets but jerrybase shows 1 (taper's markers)" in res.notes
    assert not any("jerrybase shows" in c for c in res.show.structure.conflicts)


def test_agreeing_set_count_raises_neither_flag_nor_note(tmp_path, monkeypatch):
    """(pin)"""
    _jb(monkeypatch, ("Charlie", "1"), ("Foxtrot", "2"))
    res = _tp_gather(tmp_path, _tp_md(TP_SONGS, TP_DESC), jerrybase_enabled=True)
    assert res.taper_owned is True
    assert _count_flags(res) == []
    assert not any("jerrybase shows" in n for n in res.notes)
    assert _closer_flags(res) == []


def test_closer_flag_is_a_note_when_taper_text_names_another_closer(tmp_path, monkeypatch):
    _jb(monkeypatch, ("China Doll", "1"), ("Foxtrot", "2"))
    res = _tp_gather(tmp_path, _tp_md(_TP_CHINA, _TP_CHINA_DESC), jerrybase_enabled=True)
    assert res.taper_owned is True
    assert _closer_flags(res) == []
    assert ("jerrybase set closer 'China Doll' is not at a set break (taper's markers)"
            in res.notes)


def test_closer_flag_stays_hard_when_taper_text_agrees():
    taper = taper_mod.read_taper_structure(TP_DESC)
    event = _jb_event([("Charlie", "1"), ("Foxtrot", "2")])
    flag = "jerrybase set closer 'Charlie' is not at a set break"
    hard = [flag]
    assert flag in hard
    kept, count, notes = demote_jerrybase_flags(hard, None, event, taper)
    assert kept == [flag] and count is None and notes == []


def test_closer_for_a_set_the_taper_lacks_is_a_note(tmp_path, monkeypatch):
    _jb(monkeypatch, ("Charlie", "1"), ("Foxtrot", "2"), ("Echo", "3"))
    res = _tp_gather(tmp_path, _tp_md(TP_SONGS, TP_DESC), jerrybase_enabled=True)
    assert res.taper_owned is True
    assert _closer_flags(res) == []
    assert "jerrybase set closer 'Echo' is not at a set break (taper's markers)" in res.notes


def test_encore_closer_maps_to_the_taper_encore(tmp_path, monkeypatch):
    _jb(monkeypatch, ("Charlie", "1"), ("Foxtrot", "2"), ("Alpha", "encore"))
    res = _tp_gather(tmp_path, _tp_md(TP_SONGS, TP_DESC), jerrybase_enabled=True)
    assert res.taper_owned is True
    assert _closer_flags(res) == []
    assert "jerrybase set closer 'Alpha' is not at a set break (taper's markers)" in res.notes
    # the taper has no encore at all
    _jb(monkeypatch, ("Charlie", "1"), ("Golf", "2"), ("Echo", "encore"))
    res2 = _tp_gather(tmp_path, _tp_md(TP_SONGS, "Set 1:\nAlpha\nBravo\nCharlie\nSet 2:\n"
                                       "Delta\nEcho\nFoxtrot\nGolf"),
                      sub="s2", jerrybase_enabled=True)
    assert res2.taper_owned is True
    assert res2.taper.taper.has_encore is False
    assert _closer_flags(res2) == []
    assert "jerrybase set closer 'Echo' is not at a set break (taper's markers)" in res2.notes


def test_tripwire_skipped_when_numbered_breaks_came_from_anchoring(tmp_path, monkeypatch):
    """(pin) Not owned and anchoring succeeded: no tripwire, as today."""
    _jb(monkeypatch, ("Charlie", "1"), ("Foxtrot", "2"))
    calls = _spy_tripwire(monkeypatch)
    with monkeypatch.context() as m:
        m.setattr(taper_mod, "decide_taper", _not_owned)
        res = _tp_gather(tmp_path, _tp_md(TP_SONGS, TP_DESC), jerrybase_enabled=True)
    assert res.taper_owned is False
    assert res.show.structure.alignment == "jerrybase"
    assert calls == []


def test_tripwire_runs_on_owned_show_agreeing_with_anchoring(tmp_path, monkeypatch):
    _jb(monkeypatch, ("Charlie", "1"), ("Foxtrot", "2"))
    calls = _spy_tripwire(monkeypatch)
    res = _tp_gather(tmp_path, _tp_md(TP_SONGS, TP_DESC), jerrybase_enabled=True)
    assert res.taper_owned is True
    assert res.step1_alignment == "jerrybase"
    assert res.show.structure.alignment == "jerrybase"
    assert calls == [1]
    assert _closer_flags(res) == []


# --- Held-backlog piece 2, Task 8 (orchestrator ruling R14): killing tests for
# mutants the Task 4/5 reviews found surviving. The mutation record
# (docs/superpowers/2026-10-22-taper-set-markers-sdd/mutation.md) cites each.

from llama.stages.gather import _CLOSER_FLAG


def _closer_flag(closer):
    flag = f"jerrybase set closer '{closer}' is not at a set break"
    assert _CLOSER_FLAG.match(flag)          # the helper parses it, so `kept` is a verdict
    return flag


def test_set_count_note_excludes_the_taper_encore(tmp_path, monkeypatch):
    """Task 5 M5: the taper's numbered set count leaves its encore out. Two
    numbered sets plus an encore against jerrybase's three numbered sets
    disagree, so the count flag is a note; counting the encore would make
    the counts agree and keep the hold."""
    _jb(monkeypatch, ("Charlie", "1"), ("Echo", "2"), ("Foxtrot", "3"))
    res = _tp_gather(tmp_path, _tp_md(TP_SONGS, TP_DESC), jerrybase_enabled=True)
    assert res.taper_owned is True
    assert res.taper.taper.has_encore is True
    assert _count_flags(res) == []
    assert "structure has 2 sets but jerrybase shows 3 (taper's markers)" in res.notes


@pytest.mark.parametrize("taper_closer, jb_closer", [
    ("charlie brown", "Charlie Brown"),                                    # case
    ("Me & My Uncle", "Me and My Uncle"),                                  # & / and
    ("Mississippi Half Step", "Mississippi Half-Step Uptown Toodeloo"),    # dropped subtitle
])
def test_closer_agreement_uses_fuzzy_song_matching(taper_closer, jb_closer):
    """Task 5 M6: the taper's set-k last song is compared with jerrybase's
    closer by the fuzzy song matcher, so a spelling-only difference agrees
    and the flag stays hard (it is then about llama's placement)."""
    taper = taper_mod.read_taper_structure(
        f"Set 1:\nAlpha\nBravo\n{taper_closer}\nSet 2:\nDelta\nEcho\nFoxtrot\nEncore:\nGolf")
    assert [i.title for i in taper.items if i.set == "1"][-1] == taper_closer
    event = _jb_event([(jb_closer, "1"), ("Foxtrot", "2")])
    flag = _closer_flag(jb_closer)
    kept, count, notes = demote_jerrybase_flags([flag], None, event, taper)
    assert kept == [flag] and count is None and notes == []


def test_closer_maps_to_the_taper_set_of_the_same_number():
    """Task 5 M2: jerrybase set 1's closer is compared with the taper's SET 1
    last song, not with the last song of any taper set. Foxtrot closes the
    taper's set 2, so jerrybase's set-1 closer Foxtrot disagrees: a note."""
    taper = taper_mod.read_taper_structure(TP_DESC)
    event = _jb_event([("Foxtrot", "1"), ("Golf", "2")])
    flag = _closer_flag("Foxtrot")
    kept, count, notes = demote_jerrybase_flags([flag], None, event, taper)
    assert kept == [] and count is None
    assert notes == ["jerrybase set closer 'Foxtrot' is not at a set break (taper's markers)"]


def test_duplicate_closer_flags_consume_sets_in_order():
    """Task 5 M3: two jerrybase sets with the same closer give two identical
    flags; the first maps to set 1 and the second to set 2. The taper's set 1
    ends on Charlie (disagrees: a note) and its set 2 on Foxtrot (agrees:
    stays hard). Mapping both to set 1 would demote both."""
    taper = taper_mod.read_taper_structure(TP_DESC)
    event = _jb_event([("Foxtrot", "1"), ("Foxtrot", "2")])
    flag = _closer_flag("Foxtrot")
    kept, count, notes = demote_jerrybase_flags([flag, flag], None, event, taper)
    assert kept == [flag] and count is None
    assert notes == ["jerrybase set closer 'Foxtrot' is not at a set break (taper's markers)"]


def test_filler_only_label_difference_keeps_step_one_alignment(tmp_path, monkeypatch):
    """Task 4 M4: an owned decision whose labels differ from step 1's ONLY on a
    filler track is not a structure change: `alignment` stays step 1's and no
    "was" note is written. `decide_taper` is patched, since the real one
    cannot produce a filler-only difference while Task 2's filler rule holds."""
    titles = ["Alpha", "Bravo", "Charlie", "Tuning", "Delta", "Echo", "Foxtrot"]
    md = _tp_md(titles, "Set 1:\nAlpha\nBravo\nCharlie\nSet 2:\nDelta\nEcho\nFoxtrot")
    seen = {}

    def filler_only(tracks, meta, *, aliases, today_sets, today_reaches_llm):
        labels = list(today_sets)
        assert gather_mod.is_filler(tracks[3].title)
        labels[3] = "2" if labels[3] == "1" else "1"
        seen["step1"], seen["shipped"] = list(today_sets), labels
        bounds = tuple(i + 1 for i in range(len(labels) - 1) if labels[i] != labels[i + 1])
        return taper_mod.TaperDecision(
            taper_mod.TaperPlacement(sets=tuple(labels), boundaries=bounds),
            taper_mod.read_taper_structure(meta["description"]), "description", None)

    monkeypatch.setattr(taper_mod, "decide_taper", filler_only)
    res = _tp_gather(tmp_path, md)
    assert res.taper_owned is True
    assert seen["shipped"] != seen["step1"]                   # the labels do differ ...
    assert [i for i, (a, b) in enumerate(zip(seen["shipped"], seen["step1"])) if a != b] == [3]
    assert _labels(res) == seen["shipped"]                    # ... and ship
    assert res.show.structure.alignment == res.step1_alignment == "deterministic"
    assert _was_notes(res) == []


# --- Fix round 2 (t9-fix2), G1 (llama-db reading of operator ruling (d),
# 2026-10-22): with no recognised taper encore marker, the taper owns nothing
# when today's path would reach the LLM branch. One predicate, computed in
# `compute_gather` (canonical items, no anchoring, step-1 coverage under the
# threshold) and passed to `decide_taper`. Each conjunct is pinned on its own:
# the test removes exactly one and the no-encore taper owns again.
_NO_ENC_DESC = "Set 1:\nAlpha\nBravo\nCharlie\nSet 2:\nDelta\nEcho\nFoxtrot\nGolf"
_G1_REASON = "veto: no encore on today's LLM path"


def test_no_taper_encore_on_todays_llm_path_is_exactly_today(tmp_path, monkeypatch):
    md = _tp_md(TP_SONGS, _NO_ENC_DESC)
    slfm = _FakeSetlistFM(_MISMATCHED_SLFM)        # step-1 coverage 0, no jerrybase
    oracle = _oracle(tmp_path, monkeypatch, md, setlistfm=slfm, align_provider=None)
    res = _tp_gather(tmp_path, md, setlistfm=slfm, align_provider=None)
    assert res.taper_owned is False and res.taper.reason == _G1_REASON
    assert "align_structure" in res.needs_llm
    assert _sans_taper(res) == _sans_taper(oracle)


def test_taper_encore_marked_stays_owned_on_todays_llm_path(tmp_path):
    res = _tp_gather(tmp_path, _tp_md(TP_SONGS, TP_DESC),
                     setlistfm=_FakeSetlistFM(_MISMATCHED_SLFM), align_provider=None)
    assert res.taper_owned is True and res.taper.taper.has_encore
    assert "align_structure" not in res.needs_llm


def test_g1_needs_canonical_items(tmp_path):
    # No setlist.fm and an empty description: no canonical items; the notes
    # carry the markers, with no encore.
    res = _tp_gather(tmp_path, _tp_md(TP_SONGS, "", notes=_NO_ENC_DESC), align_provider=None)
    assert res.taper.source == "notes"
    assert res.taper_owned is True, res.taper.reason


def test_g1_needs_no_anchoring(tmp_path, monkeypatch):
    # setlist.fm shares nothing with the tape (step-1 coverage 0), but jerrybase
    # anchoring succeeds, so today never reaches the LLM branch.
    monkeypatch.setattr(jerrybase, "lookup",
                        lambda a, d: [_jb_event([("Charlie", "1"), ("Golf", "2")])])
    res = _tp_gather(tmp_path, _tp_md(TP_SONGS, _NO_ENC_DESC), align_provider=None,
                     setlistfm=_FakeSetlistFM(_MISMATCHED_SLFM), jerrybase_enabled=True)
    assert res.step1_alignment == "jerrybase"
    assert res.taper_owned is True, res.taper.reason


def test_g1_needs_weak_step_one(tmp_path):
    # setlist.fm matches the tape (step-1 coverage 1.0): today ships step 1.
    res = _tp_gather(tmp_path, _tp_md(TP_SONGS, _NO_ENC_DESC), align_provider=None,
                     setlistfm=_FakeSetlistFM(TP_SONGS))
    assert res.step1_alignment == "deterministic"
    assert res.taper_owned is True, res.taper.reason


# --- Title hygiene (piece 3), Task 11: additive seams --------------------------------------

def test_accept_short_tags_per_track_sources():
    """`tag_sources` stamps each accepted track with ITS layer source (slice 3 may mix
    `tags` and `sibling-format` on one tape); the single `tag_source` is then unused."""
    tracks = [Track(index=i, set="1", title=f"t{i}.mp3", filename=f"t{i}.mp3",
                    title_source="unresolved") for i in (1, 2)]
    corroboration = {fuzzy_norm_title("FF"): ("setlist.fm",), fuzzy_norm_title("42"): ("lma:x",)}
    out, notes = accept_short_tags(tracks, ["FF>", "42"], "tags", corroboration=corroboration,
                                   metadata_norms=set(), demoted=frozenset(),
                                   tag_sources=["tags", "sibling-format"])
    assert [(t.title, t.title_source) for t in out] == [("FF", "tags"), ("42", "sibling-format")]
    assert len(notes) == 2


def test_accept_short_tags_default_sources_unchanged():
    """(pin) `tag_sources=None` returns exactly today's tracks and notes, and so does a
    per-track list that repeats the single source."""
    tracks = [Track(index=i, set="1", title=f"t{i}.mp3", filename=f"t{i}.mp3",
                    title_source="unresolved") for i in range(1, 5)]
    tags = ["FF>", "? >", "42", "NY"]
    corroboration = {fuzzy_norm_title("FF"): ("setlist.fm",), fuzzy_norm_title("?"): ("lma:x",),
                     fuzzy_norm_title("42"): ("lma:x", "setlist.fm"),
                     fuzzy_norm_title("NY"): ("lma:x",)}
    kw = dict(corroboration=corroboration, metadata_norms={fuzzy_norm_title("NY")},
              demoted=frozenset())
    today = accept_short_tags(tracks, tags, "sibling-format", **kw)
    explicit = accept_short_tags(tracks, tags, "sibling-format", tag_sources=None, **kw)
    repeated = accept_short_tags(tracks, tags, "sibling-format",
                                 tag_sources=["sibling-format"] * 4, **kw)
    for got in (explicit, repeated):
        assert [t.model_dump() for t in got[0]] == [t.model_dump() for t in today[0]]
        assert got[1] == today[1]
    assert [(t.title, t.title_source) for t in today[0]] == [
        ("FF", "sibling-format"), ("t2.mp3", "unresolved"), ("42", "sibling-format"),
        ("t4.mp3", "unresolved")]
    assert today[1] == ["accepted short tag title: track 1 'FF' corroborated by setlist.fm",
                        "accepted short tag title: track 3 '42' corroborated by lma:x, setlist.fm"]


def _gd74_target(blank: list[int]):
    md = gd74_ia().metadata(W_IDENT)
    kept, _, _ = filter_files(md["files"], want_format=gather_mod.FORMAT_BY_AUDIO["mp3"])
    tracks = gather_mod.resolve_titles(kept, ParsedSetlist())
    return [t.model_copy(update={"title": t.filename, "title_source": "unresolved"})
            if i in blank else t for i, t in enumerate(tracks)]


def test_sibling_transfer_split_is_identical():
    """`_sibling_transfer` returns exactly what it returned before the split (literals
    captured from the pre-split code on these fixtures), and `_sibling_transfer_full`'s
    third element is `best_donor`'s `(donor, rows)`, None with no donor."""
    want = gather_mod.FORMAT_BY_AUDIO["mp3"]
    ia, cand = gd74_ia(), gd74_candidate()
    norms = gather_mod.show_metadata_norms("Grateful Dead", cand, ia.metadata(W_IDENT)["metadata"], [])

    # Auto band: tracks 4-6 blanked, bracketed by anchors, filled from Miller.
    target = _gd74_target([3, 4, 5])
    out, notes = gather_mod._sibling_transfer(ia, cand, W_IDENT, want, target, norms)
    assert notes == []
    assert [(t.title, t.title_source) for t in out[3:6]] == [
        ("Beat It On Down The Line", "sibling-align"), ("Candyman", "sibling-align"),
        ("Jack Straw", "sibling-align")]
    assert [t.model_dump() for i, t in enumerate(out) if i not in (3, 4, 5)] == \
        [t.model_dump() for i, t in enumerate(target) if i not in (3, 4, 5)]
    full = gather_mod._sibling_transfer_full(ia, cand, W_IDENT, want, target, norms)
    assert ([t.model_dump() for t in full[0]], full[1]) == ([t.model_dump() for t in out], notes)
    donor, rows, _, _ = gather_mod.best_donor(ia, cand, W_IDENT, want, target, norms)
    assert full[2] is not None and full[2][0] == donor and full[2][1] == rows
    assert donor.identifier == M_IDENT

    # No anchors: the pair routes to `no-anchors`; the donor is still returned.
    # Every track blanked: 28 since piece 4 keeps Windsor's D3_T02 (spec 1).
    target = _gd74_target(list(range(28)))
    out, notes = gather_mod._sibling_transfer(ia, cand, W_IDENT, want, target, norms)
    assert notes == [f"sibling alignment skipped ({M_IDENT}): tape has no independent anchors"]
    assert [t.model_dump() for t in out] == [t.model_dump() for t in target]
    full = gather_mod._sibling_transfer_full(ia, cand, W_IDENT, want, target, norms)
    assert full[1] == notes and full[2] is not None and full[2][0].identifier == M_IDENT

    # No donor at all.
    alone = cand.model_copy(update={"recordings": cand.recordings[:1]})
    out, notes = gather_mod._sibling_transfer(ia, alone, W_IDENT, want, target, norms)
    assert notes == [] and [t.model_dump() for t in out] == [t.model_dump() for t in target]
    assert gather_mod._sibling_transfer_full(ia, alone, W_IDENT, want, target, norms)[2] is None


# --- Title hygiene (piece 3), Task 16: title_inputs + title_cascade wired into gather ---------
#
# Spec docs/superpowers/specs/2026-10-22-title-hygiene-design.md. These drive the WIRED
# `compute_gather`; `test_title_cascade.py` places each slice on the cascade alone.

from llama import title_hygiene  # noqa: E402
from llama.stages.gather import CanonicalBuild  # noqa: E402


def _numbered(titles) -> str:
    return "\n".join(f"{i}. {t}" for i, t in enumerate(titles, 1))


def _untagged_gd73(description: str) -> dict:
    """The gd73 fixture with every title tag removed (wholly untagged) and the given
    description."""
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = description
    for f in md["files"]:
        f.pop("title", None)
    return md


def _setlistfm(titles):
    """Stands in for `build_canonical`: a count-matched setlist.fm canonical."""
    canon = ParsedSetlist(items=[SetlistItem(title=t, normalized=normalize_song(t), set="1")
                                 for t in titles], confidence="high")

    def build(*a, **kw):
        return CanonicalBuild(setlist=canon, notes=[], source="setlist.fm")
    return build


def test_gather_fills_from_the_taper_list(tmp_path: Path):
    """Slice 2 (D): an untagged tape whose own description is a count-matched numbered list
    ships the list's entries as `desc-position`, each `matched=None` (Tautology), and the
    titles are no longer unresolved."""
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(_untagged_gd73(
        _numbered(REAL_TITLES))), None, make_candidate(), IDENT)
    tracks = res.show.tracks
    assert [t.title for t in tracks] == REAL_TITLES
    assert all(t.title_source == "desc-position" for t in tracks)
    assert all(t.matched is None for t in tracks)
    assert "unresolved track titles" not in res.show.review_flags


def test_compute_gather_enabled_slices_kwarg(tmp_path: Path):
    """`enabled_slices=frozenset()` is today's gather: on the same tape the chosen canonical
    fills every track through the S rung (`setlist`), and no `desc-position` ships. The
    keyword never rebinds the module's `ENABLED_SLICES`."""
    before = title_hygiene.ENABLED_SLICES
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(_untagged_gd73(
        _numbered(REAL_TITLES))), None, make_candidate(), IDENT, enabled_slices=frozenset())
    assert [(t.title, t.title_source) for t in res.show.tracks] == [
        (t, "setlist") for t in REAL_TITLES]
    assert title_hygiene.ENABLED_SLICES is before
    assert title_hygiene.ENABLED_SLICES == title_hygiene.ALL_SLICES
    assert res.title_paths == ("S",) * 6 and res.self_filled is False


def test_gather_s_withdrawn_when_list_count_matched(tmp_path: Path):
    """Slice 1, "S with any other canonical", when the selected description yields a
    count-matched list: S makes no fill and D fills from the taper's own list, so the
    taper's wording ships, not setlist.fm's."""
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = _numbered(REAL_TITLES[:4] + ["Eyes Of The World",
                                                                 "Johnny B. Goode"])
    for f in md["files"]:
        if f["name"] == "gd73-06-10d2t02.mp3":
            f["title"] = None
    sfm = _setlistfm(REAL_TITLES[:4] + ["Eyes of the World (setlist.fm)", "Johnny B. Goode"])
    with patch.object(gather_mod, "build_canonical", side_effect=sfm):
        res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(md), None,
                             make_candidate(), IDENT)
    t = res.show.tracks
    assert [(x.title, x.title_source) for x in t[4:]] == [
        ("Eyes Of The World", "desc-position"), ("Johnny B. Goode", "desc-position")]
    assert not any(x.title_source == "setlist" for x in t)
    assert res.title_paths == ("", "", "", "", "D", "D")
    with patch.object(gather_mod, "build_canonical", side_effect=sfm):
        today = compute_gather(ShowWorkspace(tmp_path / "t"), StubIA(md), None,
                               make_candidate(), IDENT, enabled_slices=frozenset())
    assert today.show.tracks[4].title == "Eyes of the World (setlist.fm)"


def test_gather_q1_untagged_setlistfm_stays_unresolved(tmp_path: Path):
    """Operator ruling Q1: the S rung never fires on a wholly untagged tape. With a
    count-matched setlist.fm canonical and no taper list, every track stays unresolved,
    the show is held, and one operator note says why."""
    md = _untagged_gd73("An amazing night of music, seeded with love.")
    sfm = _setlistfm(REAL_TITLES)
    with patch.object(gather_mod, "build_canonical", side_effect=sfm):
        res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(md), None,
                             make_candidate(), IDENT)
    assert all(t.title_source == "unresolved" for t in res.show.tracks)
    assert "unresolved track titles" in res.show.review_flags
    assert "positional fill declined: setlist wholly untagged tape" in res.notes
    conflicts = res.show.structure.conflicts if res.show.structure else []
    assert not any(c.startswith("positional fill declined") for c in conflicts)


def test_gather_c1_fills_tmp_tape(tmp_path: Path):
    """Slice 3 (C1): every mp3 is tagged `tmp` (a 2b placeholder) while the Shorten copy of
    the same item is tagged; a count-matched list confirms each lossless title, so they ship
    per track as `sibling-format`, with one note each and no 2b demotion note."""
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()), tag_mp3=True)
    for f in md["files"]:
        if f.get("format") == "VBR MP3" and f["name"].startswith("gd73-06-10d"):
            f["title"] = "tmp"
    md["metadata"]["description"] = _numbered(_LOSSLESS_TITLES.values())
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(md), None, make_candidate(),
                         IDENT)
    assert [(t.title, t.title_source) for t in res.show.tracks] == [
        (t, "sibling-format") for t in _LOSSLESS_TITLES.values()]
    assert res.notes[0] == "lossless title: track 1 'tmp' -> 'Morning Dew' (C1)"
    assert sum(n.startswith("lossless title: ") for n in res.notes) == 6
    assert not any(n.startswith(("placeholder tag title", "format sibling tagged"))
                   for n in res.notes)
    assert "unresolved track titles" not in res.show.review_flags


def test_title_paths_reported(tmp_path: Path):
    """`GatherResult.title_paths`, `self_filled` and `title_record` carry the cascade's
    record (in-process only): the gd73 fixture's encore is S's fill; the untagged tape with
    a taper list is D's on every track."""
    res = compute_gather(ShowWorkspace(tmp_path / "a"), StubIA(), None, make_candidate(), IDENT)
    assert res.title_paths == ("", "", "", "", "", "S")
    assert res.self_filled is False
    assert res.title_record is not None and res.title_record.s_plan.mode == "gated"
    res = compute_gather(ShowWorkspace(tmp_path / "b"), StubIA(_untagged_gd73(
        _numbered(REAL_TITLES))), None, make_candidate(), IDENT)
    assert res.title_paths == ("D",) * 6
    assert res.self_filled is True
    assert res.title_record.d is not None and res.title_record.d.failed == ()
    assert "title_paths" not in res.show.model_dump_json()


def test_cascade_op_notes_lead_gather_notes(tmp_path: Path):
    """Brief Task 16 Step 3, notes order (op notes): the cascade's operator notes are the
    FIRST entries of `GatherResult.notes`, and notes raised after it (here the taper's
    `set breaks from the taper's markers`) follow them. Every tag carries a joined track
    number, so 2d writes a cascade note per track; the taper's markers own the structure."""
    md = _tp_md([f"{i:02d}-{t}" for i, t in enumerate(TP_SONGS, 1)], TP_DESC)
    res = _tp_gather(tmp_path, md, setlistfm=_FakeSetlistFM(TP_SONGS))
    cascade = [f"stripped joined track number: track {i} '{i:02d}-{t}' -> '{t}'"
               for i, t in enumerate(TP_SONGS, 1)]
    assert [t.title for t in res.show.tracks] == TP_SONGS
    assert res.notes[:len(cascade)] == cascade
    taper_note = "set breaks from the taper's markers (was [] ['1'])"
    assert taper_note in res.notes[len(cascade):]


def test_canonical_notes_precede_sibling_notes_in_conflicts(tmp_path: Path):
    """Brief Task 16 Step 3, notes order (structure notes): the canonical build's notes
    come first in `structure.conflicts`, sibling-align's after them. A third recording
    fails its first fetch (`build_canonical`'s note) and then serves an empty item, which
    `load_donor_tapes` skips silently, so each note has exactly one source. The donor
    recording is the operator-band shape of
    test_operator_band_run_stays_unresolved_even_though_cplus_would_bracket_it."""
    from llama.ia_client import IAError
    flaky = "gd73-06-10.flaky.once"

    class FlakyOnceIA(MultiIA):
        def __init__(self, mapping):
            super().__init__(mapping)
            self.failed = False

        def metadata(self, identifier):
            if identifier == flaky:
                if not self.failed:
                    self.failed = True
                    raise IAError("boom 503")
                return {"metadata": {}, "files": []}
            return super().metadata(identifier)

    md = json.loads(FIXTURE.read_text())
    chosen = {"metadata": dict(md["metadata"], description=""),
              "files": [dict(f) for f in md["files"]]}
    by_name = {f["name"]: f for f in chosen["files"]}
    for name in ("gd73-06-10d1t03.mp3", "gd73-06-10d2t01.mp3"):
        by_name[name].pop("title", None)
    by_name["gd73-06-10d3t01.mp3"]["title"] = "Bertha"
    ia = FlakyOnceIA({IDENT: chosen, SIB_ID: _gd73_donor(md, REAL_TITLES)})
    cand = make_candidate()
    cand.recordings += [RecordingSummary(identifier=SIB_ID), RecordingSummary(identifier=flaky)]
    res = compute_gather(ShowWorkspace(tmp_path / "s"), ia, None, cand, IDENT)
    assert res.show.structure.conflicts == [
        f"could not fetch sibling {flaky}: boom 503",
        "sibling alignment needs operator review (anchor agreement 75%)"]


# --- Title hygiene (piece 3), Task 17: Q2 self-filled tapes ship ------------------------

class _NoAlignProvider:
    """An `align_provider` that fails the test if the `align_structure` LLM branch calls it."""

    def __getattr__(self, name):
        raise AssertionError(f"align_structure LLM branch reached ({name})")


def _mccoury_one_tagged(tag="Rain and Snow"):
    """One independent title that AGREES with list entry 1 (so D passes check 3)."""
    md = _mccoury_md(tagged=False)
    for f in md["files"]:
        if f.get("name") == "gd73-06-10d1t01.mp3":
            f["title"] = tag
    return md


def _partial_slfm():
    """A setlist.fm canonical agreeing with 4 of the list's 6 items: D's agreement check
    passes (>= 0.5), and the canonical is not the description's own."""
    songs = list(MCCOURY_SONGS)
    return _FakeSetlistFM(["Zebra Stripes"] + songs[1:4] + ["Ostrich Dance", "All Aboard"])


def test_self_filled_tape_skips_align_structure_and_the_flag(tmp_path):
    """Spec Q2: every song-like track `desc-position` and D passed -> no align_structure
    call, no needs_align verdict, no low-confidence flag; labels are deterministic align()'s.
    Both a chosen canonical and a partial setlist.fm one ("whatever the canonical")."""
    for sub, slfm in (("chosen", None), ("slfm", _partial_slfm())):
        res = compute_gather(ShowWorkspace(tmp_path / sub), StubIA(_mccoury_md(tagged=False)),
                             None, make_candidate(), IDENT, setlistfm=slfm,
                             align_provider=_NoAlignProvider())    # raises if called
        assert res.self_filled is True, sub
        assert res.needs_llm == (), sub
        assert "low-confidence structure alignment" not in res.show.review_flags
        # labels are deterministic align()'s of the shipped titles over the canonical
        canon_titles = (MCCOURY_SONGS if slfm is None
                        else ["Zebra Stripes"] + MCCOURY_SONGS[1:4] + ["Ostrich Dance", "All Aboard"])
        canon = ParsedSetlist(items=[SetlistItem(title=t, normalized=normalize_song(t), set="1")
                                     for t in canon_titles])
        assert [t.set for t in res.show.tracks] == align(res.show.tracks, canon).sets, sub
        assert res.show.structure.alignment == "deterministic"
    # today's path for the same tape (slices off) does reach the flag
    today = compute_gather(ShowWorkspace(tmp_path / "t"), StubIA(_mccoury_md(tagged=False)),
                           None, make_candidate(), IDENT, enabled_slices=frozenset())
    assert today.self_filled is False
    assert "align_structure" in today.needs_llm


def test_one_independent_title_keeps_low_confidence(tmp_path):
    """(pin) Spec Q2's exception is narrow: D PASSES (the tag agrees with the list, the
    canonical agrees 4 of 6) but ONE track keeps an independent tag, so today's LLM branch
    and flag stay."""
    res = compute_gather(ShowWorkspace(tmp_path / "a"), StubIA(_mccoury_one_tagged()),
                         None, make_candidate(), IDENT, setlistfm=_partial_slfm())
    assert res.title_record.d is not None and res.title_record.d.failed == ()
    assert [t.title_source for t in res.show.tracks] == ["tags"] + ["desc-position"] * 5
    assert res.self_filled is False
    assert res.needs_llm == ("align_structure",)
    assert "low-confidence structure alignment" in res.show.review_flags


def test_d_declined_tape_with_a_disagreeing_tag_is_not_self_filled(tmp_path):
    """The D-declined case: a tag that DISAGREES with list entry 1 fails check 3."""
    res = compute_gather(ShowWorkspace(tmp_path / "a"),
                         StubIA(_mccoury_one_tagged("Zebra Stripes")),
                         None, make_candidate(), IDENT)
    assert res.title_record.d is not None and res.title_record.d.failed
    assert res.self_filled is False
    assert "align_structure" in res.needs_llm
    assert "low-confidence structure alignment" in res.show.review_flags


def test_jerrybase_anchoring_still_labels_a_self_filled_family_tape(tmp_path, monkeypatch):
    songs = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"]
    md = _mccoury_md(tagged=False)
    md["metadata"]["creator"] = "Grateful Dead"
    md["metadata"]["description"] = "\n".join(songs) + "\n"
    monkeypatch.setattr(jerrybase, "lookup",
                        lambda a, d: [_jb_event([("Charlie", "1"), ("Foxtrot", "2")])])
    res = compute_gather(ShowWorkspace(tmp_path / "a"), StubIA(md), None,
                         make_candidate(), IDENT, jerrybase_enabled=True,
                         align_provider=_NoAlignProvider())
    assert res.self_filled is True
    assert res.show.structure.alignment == "jerrybase"
    assert [t.set for t in res.show.tracks] == ["1", "1", "1", "2", "2", "2"]
    assert "low-confidence structure alignment" not in res.show.review_flags


def test_today_reaches_llm_unchanged_for_self_filled(tmp_path, monkeypatch):
    """The value passed to `decide_taper` is today's predicate, not suppressed by Q2."""
    seen = {}
    real = taper_mod.decide_taper

    def spy(tracks, meta, *, aliases, today_sets, today_reaches_llm):
        seen["llm"] = today_reaches_llm
        return real(tracks, meta, aliases=aliases, today_sets=today_sets,
                    today_reaches_llm=today_reaches_llm)

    monkeypatch.setattr(taper_mod, "decide_taper", spy)
    res = compute_gather(ShowWorkspace(tmp_path / "a"), StubIA(_mccoury_md(tagged=False)),
                         None, make_candidate(), IDENT)
    assert res.self_filled is True
    assert seen["llm"] is True


# --- Title hygiene (piece 3), Task 18: slice 5 wired before `Show` is built ------------------

def _slice5_md(include_stamp: bool = False) -> dict:
    md = json.loads(FIXTURE.read_text())
    for f in md["files"]:
        if f["name"] == "gd73-06-10d1t02.mp3":
            f["title"] = "06:58 - China Cat Sunflower"
    return md


def test_cosmetic_strip_runs_after_flags(tmp_path: Path):
    """Slice 5 ships `06:58 - China Cat Sunflower` as `China Cat Sunflower`, with one note
    at the END of the notes and a `+5` path, while flags and set labels equal the same gather
    with slice 5 off (computed from the pre-strip titles)."""
    on = compute_gather(ShowWorkspace(tmp_path / "a"), StubIA(_slice5_md()), None,
                        make_candidate(), IDENT)
    off = compute_gather(ShowWorkspace(tmp_path / "b"), StubIA(_slice5_md()), None,
                         make_candidate(), IDENT,
                         enabled_slices=title_hygiene.ALL_SLICES - {"slice5"})
    assert off.show.tracks[1].title == "06:58 - China Cat Sunflower"
    assert on.show.tracks[1].title == "China Cat Sunflower"
    assert on.show.tracks[1].title_source == "tags"
    assert on.show.review_flags == off.show.review_flags
    assert [t.set for t in on.show.tracks] == [t.set for t in off.show.tracks]
    note = "cosmetic title strip: track 2 '06:58 - China Cat Sunflower' -> 'China Cat Sunflower'"
    assert on.notes[-1] == note and on.notes[:-1] == off.notes
    assert off.title_paths[1] == "" and on.title_paths[1] == "+5"
    assert on.title_paths[0] == off.title_paths[0] == ""
    assert on.title_paths[2:] == off.title_paths[2:]


def test_cosmetic_strip_keeps_included_stamp(tmp_path: Path):
    """The strip copies tracks, so the operator `include` stamp (applied just before) rides
    along on the stripped track."""
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(include=["gd73-06-10d1t02.mp3"]))
    res = compute_gather(ws, StubIA(_slice5_md()), None, make_candidate(), IDENT)
    t = res.show.tracks[1]
    assert t.title == "China Cat Sunflower" and t.included is True
    assert res.show.tracks[0].included is False


def test_cosmetic_strip_off_when_slice5_disabled(tmp_path: Path):
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(_slice5_md()), None,
                         make_candidate(), IDENT,
                         enabled_slices=title_hygiene.ALL_SLICES - {"slice5"})
    assert res.show.tracks[1].title == "06:58 - China Cat Sunflower"
    assert not any(n.startswith("cosmetic title strip") for n in res.notes)


# --- Piece 4, Task 2: Track.short_kept, coverage and the junk note ----------

def _sk_md(titles, description, short=(8,)):
    """`_tp_md` with the 1-based tracks in `short` only 20 s long (below the floor)."""
    return _tp_md(titles, description, lengths={i: "00:20" for i in short})


_SK_TITLES = TP_SONGS + ["Murph"]


def test_unmatched_short_kept_track_does_not_lower_coverage(tmp_path):
    with_short = _tp_gather(tmp_path, _sk_md(_SK_TITLES, TP_DESC), sub="a")
    murph = [t for t in with_short.show.tracks if t.title == "Murph"]
    assert len(murph) == 1 and murph[0].short_kept is True
    without = _tp_gather(tmp_path, _tp_md(TP_SONGS, TP_DESC), sub="b")
    assert with_short.show.structure.coverage == without.show.structure.coverage
    assert not any("low-confidence" in f for f in with_short.show.review_flags)


def test_short_kept_survives_to_show_json(tmp_path):
    """Through align(), the structure-override path and taper ownership."""
    md = _sk_md(_SK_TITLES, TP_DESC)
    plain = _tp_gather(tmp_path, md, sub="a")
    assert [t.title for t in plain.show.tracks if t.short_kept] == ["Murph"]
    ovr = _tp_gather(tmp_path, md, sub="b",
                     overrides=Overrides(set_breaks=["tb1999-07-04t03.mp3", "tb1999-07-04t06.mp3"]))
    assert [t.title for t in ovr.show.tracks if t.short_kept] == ["Murph"]
    owned = _tp_gather(tmp_path, md, sub="c")
    assert owned.taper_owned is True
    assert [t.title for t in owned.show.tracks if t.short_kept] == ["Murph"]
    from llama.models import ManifestTrack
    assert "short_kept" not in ManifestTrack.model_fields


def test_old_show_json_reads_short_kept_false():
    t = Track.model_validate({"index": 1, "set": "1", "title": "A", "filename": "a.mp3",
                              "title_source": "tags"})
    assert t.short_kept is False


def _sk_junk_md(short):
    titles = ["Alpha", "Bravo", None, "Delta", "Echo"]
    md = _tp_md(titles, "1. Alpha\n2. Bravo\n3. Crowd Noise\n4. Delta\n5. Echo",
                lengths={3: "00:20"} if short else None)
    for f in md["files"]:
        if f.get("title") is None:
            f.pop("title", None)
    return md


def test_wholly_junk_final_title_notes(tmp_path):
    """Spec 2.5: a short-kept track whose final title is wholly junk is noted."""
    res = _tp_gather(tmp_path, _sk_junk_md(True), sub="a")
    t3 = res.show.tracks[2]
    assert t3.title == "Crowd Noise" and t3.short_kept is True
    assert "short-kept track 3 'Crowd Noise': its final title is wholly junk" in res.notes
    res2 = _tp_gather(tmp_path, _sk_junk_md(False), sub="b")
    assert res2.show.tracks[2].title == "Crowd Noise" and not res2.show.tracks[2].short_kept
    assert not any("wholly junk" in n for n in res2.notes)


def test_short_kept_file_votes_like_any_kept_file(tmp_path):
    """(pin) spec 2.5: a short-kept file is in both recording-level bases; an
    operator-included file is left out of both."""
    from test_title_cascade import _inputs_like_gather
    ia = StubIA(_sk_md(_SK_TITLES, TP_DESC))
    inp = _inputs_like_gather(ShowWorkspace(tmp_path / "a"), ia, _tp_candidate(), TP_IDENT)
    assert "tb1999-07-04t08.mp3" in inp.ordering["short_kept"]
    for basis in (inp.recovery_basis, inp.tag_gate_basis):
        assert "tb1999-07-04t08.mp3" in [f["name"] for f in basis]
    # a short file the rule drops (a wholly junk tag) and the operator re-admits
    ia2 = StubIA(_sk_md(_SK_TITLES + ["Crowd Noise"], TP_DESC, short=(8, 9)))
    sws2 = ShowWorkspace(tmp_path / "b")
    write_artifact(sws2.overrides, Overrides(include=["tb1999-07-04t09.mp3"]))
    inp2 = _inputs_like_gather(sws2, ia2, _tp_candidate(), TP_IDENT)
    assert "tb1999-07-04t09.mp3" in [f["name"] for f in inp2.kept]
    assert "tb1999-07-04t09.mp3" not in inp2.ordering["short_kept"]
    for basis in (inp2.recovery_basis, inp2.tag_gate_basis):
        names = [f["name"] for f in basis]
        assert "tb1999-07-04t09.mp3" not in names
        assert "tb1999-07-04t08.mp3" in names


def test_furthur_tuning_up_short_kept_is_noted_wholly_junk(tmp_path):
    """Spec 2.5: the kept mp3 `10.tuningup.mp3` (own tag `tmp`) is filled `Tuning Up`
    by D; that final title is wholly junk, so the note fires."""
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(_furthur_md()), None,
                         _furthur_candidate(), F_IDENT)
    t10 = res.show.tracks[9]
    assert (t10.title, t10.short_kept) == ("Tuning Up", True)
    assert "short-kept track 10 'Tuning Up': its final title is wholly junk" in res.notes


# --- piece 4 spec 4.1: filename-valued positional overrides, one resolver ---

def _windsor_kept() -> list[str]:
    md = json.loads((FIXTURES / "gd74_windsor_metadata.json").read_text())
    kept, _, _ = filter_files(md["files"], want_format=("VBR MP3",))
    return [f["name"] for f in kept]


def test_delmccoury_shape_through_gather(tmp_path: Path):
    """The delmccouryband-2008-05-24 shape (18 filename titles plus `set_breaks: []`):
    the structure-override path, forced no breaks, each title on its own file."""
    names = _windsor_kept()
    titles = {names[i]: f"Song {i + 1}" for i in range(18)}
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, Overrides(titles=titles, set_breaks=[]))
    res = compute_gather(sws, gd74_ia(), None, gd74_candidate(), W_IDENT)
    show = res.show
    assert show.structure.alignment == "override"
    assert show.set_breaks == []
    assert {t.set for t in show.tracks} == {"1"}
    by_file = {t.filename: t for t in show.tracks}
    for name, title in titles.items():
        assert by_file[name].title == title and by_file[name].title_source == "override"


def test_gather_refuses_a_legacy_overrides_file(tmp_path: Path):
    from llama.errors import LlamaError
    sws = ShowWorkspace(tmp_path / "show")
    sws.dir.mkdir(parents=True)
    sws.overrides.write_text(json.dumps({"titles": {"1": "Custom Opener"}}))
    with pytest.raises(LlamaError) as e:
        compute_gather(sws, StubIA(), None, make_candidate(), IDENT)
    # The library slug of the performance, never the workspace dir name (`show`).
    assert str(e.value) == ("gratefuldead-1973-06-10: overrides.json uses track-number "
                            "keys; run the migration")


def test_filename_title_follows_its_file_across_an_insertion(tmp_path: Path):
    """Piece 4 keeps the short D3_T02 at track 17 of windsor, shifting every later
    file one place. A title keyed by filename stays on its file: D3_T03 (track 17
    before the insertion, 18 now) carries it, and the file now at 17 does not."""
    names = _windsor_kept()
    assert names[16] == "GD_022474_D3_T02.mp3" and names[17] == "GD_022474_D3_T03.mp3"
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, Overrides(titles={"GD_022474_D3_T03.mp3": "Forced"},
                                            encore_after="GD_022474_D4_T06.mp3"))
    show = compute_gather(sws, gd74_ia(), None, gd74_candidate(), W_IDENT).show
    assert show.tracks[16].short_kept and show.tracks[16].title != "Forced"
    assert show.tracks[17].filename == "GD_022474_D3_T03.mp3"
    assert show.tracks[17].title == "Forced" and show.tracks[17].title_source == "override"
    assert [t.set for t in show.tracks][-1] == "encore"
    assert show.tracks[26].filename == "GD_022474_D4_T06.mp3"
    assert show.set_breaks == [27]


# --- piece 4 spec 4.2: gather's final kept list is one shared helper ---

_GD73_INCLUDE = "FOLLOW-ME @BYPIKENO.mp3"          # the spam file, junk-dropped
_GD73_EXCLUDE = "gd73-06-10d2t01.mp3"


def test_title_inputs_unchanged_by_final_kept():   # (pin)
    """`title_inputs`' filter / include / exclude block moved into `final_kept`
    verbatim: on gd73 with a re-admission and an exclusion, the kept list, the
    excluded rows, the ordering and the recovery basis are what they were before the
    move (literal values captured on 853239a)."""
    from llama.junk import FORMAT_BY_AUDIO
    from llama.stages.gather import title_inputs

    class CB:
        corroboration = ()
    seen = []

    def build(kept):
        seen.append([f["name"] for f in kept])
        return CB()
    ia = StubIA()
    inp = title_inputs(ia.metadata(IDENT),
                       Overrides(include=[_GD73_INCLUDE], exclude=[_GD73_EXCLUDE]),
                       ia=ia, candidate=make_candidate(), identifier=IDENT,
                       artist="Grateful Dead", want=FORMAT_BY_AUDIO["mp3"], events=[],
                       build=build, slug="gratefuldead-1973-06-10")
    kept = [_GD73_INCLUDE, "gd73-06-10d1t01.mp3", "gd73-06-10d1t02.mp3",
            "gd73-06-10d1t03.mp3", "gd73-06-10d2t02.mp3", "gd73-06-10d3t01.mp3"]
    assert [f["name"] for f in inp.kept] == kept and seen == [kept]
    assert inp.excluded == [{"filename": _GD73_EXCLUDE, "reasons": ["operator-excluded"],
                             "duration_sec": 1908.0}]
    assert inp.ordering == {"order_source": "filename", "reordered": False,
                            "format": "VBR MP3", "readmitted": [_GD73_INCLUDE],
                            "short_kept": []}
    assert [f["name"] for f in inp.recovery_basis] == [
        "gd73-06-10d1t01.mp3", "gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3",
        _GD73_EXCLUDE, "gd73-06-10d2t02.mp3", "gd73-06-10d3t01.mp3"]


def test_final_kept_is_title_inputs_block(caplog):
    """`final_kept` returns the unexcluded list (filter + include), the final kept
    list, the excluded rows and the ordering, with the block's warnings; and
    `short_keep` reaches the filter."""
    from llama.junk import FORMAT_BY_AUDIO
    from llama.stages.gather import FinalKept, final_kept

    files = StubIA().metadata(IDENT)["files"]
    want = FORMAT_BY_AUDIO["mp3"]
    ov = Overrides(include=[_GD73_INCLUDE, "nope.mp3"],
                   exclude=[_GD73_EXCLUDE, _GD73_INCLUDE, "gone.mp3"])
    with caplog.at_level("WARNING"):
        fk = final_kept(files, ov, want)
    assert isinstance(fk, FinalKept)
    assert [f["name"] for f in fk.unexcluded] == [
        _GD73_INCLUDE, "gd73-06-10d1t01.mp3", "gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3",
        _GD73_EXCLUDE, "gd73-06-10d2t02.mp3", "gd73-06-10d3t01.mp3"]
    assert [f["name"] for f in fk.kept] == [
        "gd73-06-10d1t01.mp3", "gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3",
        "gd73-06-10d2t02.mp3", "gd73-06-10d3t01.mp3"]
    assert [e["filename"] for e in fk.excluded] == [_GD73_INCLUDE, _GD73_EXCLUDE]
    assert fk.ordering["readmitted"] == [_GD73_INCLUDE]
    msgs = [r.getMessage() for r in caplog.records]
    assert "overrides.include entry 'nope.mp3' matched no file" in msgs
    assert "overrides.exclude entry 'gone.mp3' matched no file" in msgs
    assert (f"overrides: {_GD73_INCLUDE!r} is in both include and exclude; "
            "exclude wins") in msgs
    # short_keep is passed through to the filter.
    calls = []
    real = gather_mod.filter_files

    def spy(*a, **k):
        calls.append(k.get("short_keep"))
        return real(*a, **k)
    with patch.object(gather_mod, "filter_files", spy):
        final_kept(files, Overrides(), want)
        final_kept(files, Overrides(), want, short_keep=False)
    assert calls == [True, False]
