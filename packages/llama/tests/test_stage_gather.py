import json
from pathlib import Path

import pytest

from llama.config import StructureConfig
from herder import FakeProvider
from llama.junk import filter_files
from llama.models import (Candidate, Overrides, ParsedSetlist, RecordingSummary,
                          SetlistItem)
from llama.setlistfm import SetlistFMClient
from llama.songs import normalize_song
from llama.stages.gather import (_HEAD_CHATTER, _drop_artist_items,
                                 _strip_head_banner, run_gather)
from llama.structure import fuzzy_norm_title
from llama.workspace import ShowWorkspace, read_overrides, write_artifact

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "gd73_metadata.json"
IDENT = "gd73-06-10.sbd.hollister.174.sbeok.shnf"
W_IDENT = "gd74-02-24.sbd.windsor.199.sbefail.shnf"
M_IDENT = "gd1974-02-24.sbd.miller.116902.flac16"


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
    assert len(show.tracks) == 27
    sets = [t.set for t in show.tracks]
    assert sets[:11] == ["1"] * 11                     # US Blues .. Playin' In The Band
    assert sets[11:26] == ["2"] * 15                   # Cumberland Blues .. Not Fade Away
    assert sets[26] == "encore"                        # E: It's All Over Now, Baby Blue
    assert show.set_breaks == [11, 26]
    assert show.structure is not None
    assert show.structure.source == f"lma:{M_IDENT}"
    assert show.structure.alignment == "deterministic"
    assert show.structure.coverage == 1.0
    # segues from the sibling's taper notation
    assert show.tracks[6].segue is True                # China Cat Sunflower >
    assert show.tracks[12].segue is False               # Roses: windsor's own junk parse said True
    assert show.needs_review is False


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
    assert show.set_breaks == [11, 26]
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


def test_sibling_titles_are_cleaned(tmp_path: Path):
    md = json.loads(FIXTURE.read_text())
    titles = ["Morning Dew", "China Cat Sunflower", "I Know You Rider",
              "Dark Star", "Eyes of the World", "Johnny B. Goode"]
    chosen = {"metadata": dict(md["metadata"], description=""),
              "files": [dict(f) for f in md["files"]]}
    for f in chosen["files"]:
        f.pop("title", None)
    sib = {"metadata": dict(md["metadata"], description=""),
           "files": [dict(f) for f in md["files"]]}
    # Restrict to the dominant naming convention: the fixture's spam file
    # ("FOLLOW-ME @BYPIKENO.mp3") is also tagged "VBR MP3" and would sort
    # alphabetically first, shifting every title assignment below by one.
    sib_audio = [f for f in sib["files"]
                 if f.get("format") == "VBR MP3" and f["name"].startswith("gd73-06-10d")]
    for f, title in zip(sorted(sib_audio, key=lambda f: f["name"]), titles):
        f["title"] = f"gd73-06-10d1t01 {title}"  # id-prefixed tag
    ia = MultiIA({IDENT: chosen, "gd73-06-10.aud.sibling": sib})
    cand = make_candidate()
    cand.recordings.append(RecordingSummary(identifier="gd73-06-10.aud.sibling"))
    show = run_gather(ShowWorkspace(tmp_path / "show"), ia, FakeProvider(), cand, IDENT)
    assert [t.title for t in show.tracks] == titles          # prefix stripped
    assert all(t.title_source == "sibling" for t in show.tracks)


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
    "setlist"."""
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
    two tracks would read their own tag text and title_source "tags"."""
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


from llama import jerrybase
from llama.models import JerrybaseEvent, JerrybaseSet


def _jb_event(closers_and_names, venue="V", city="C"):
    return JerrybaseEvent(
        event_id="1", venue=venue, city=city, state="ST",
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
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("I Know You Rider", "1"), ("Eyes of the World", "2"),
         ("Johnny B. Goode", "encore")],
        venue="Robert F. Kennedy Stadium", city="Washington")])
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
    write_artifact(ws.overrides, Overrides(titles={1: "Custom Opener"}))
    show = run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert show.tracks[0].title == "Custom Opener"
    assert show.tracks[0].title_source == "override"
    # the gd73 fixture resolves all titles, so no unresolved-titles hold exists;
    # an override can only ever remove such a flag, never add one.
    assert "unresolved track titles" not in show.review_flags


def test_gather_title_override_out_of_range_errors(tmp_path: Path):
    from llama.errors import LlamaError
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(titles={999: "Nope"}))
    with pytest.raises(LlamaError):
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
    write_artifact(ws.overrides, Overrides(set_breaks=[2, 4]))
    show = run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    # 6-track fixture -> sets: 1,1 | 2,2 | 3,3
    assert [t.set for t in show.tracks] == ["1", "1", "2", "2", "3", "3"]
    assert show.set_breaks == [2, 4]
    assert show.structure is not None and show.structure.alignment == "override"
    assert "low-confidence structure alignment" not in show.review_flags


def test_gather_set_breaks_out_of_range_errors(tmp_path: Path):
    from llama.errors import LlamaError
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(set_breaks=[99]))
    with pytest.raises(LlamaError):
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
    """The artist header must be dropped BEFORE `resolve_titles`, not merely
    before `align`.

    With no title tags — the common case for exactly the rows this targets —
    the setlist is the only title source (this candidate has no sibling
    recording). `titles.resolve_titles` only trusts it when the item count
    equals the track count, so the surviving header item makes 7 != 6 and every
    title falls through to "unresolved", holding the show for review and
    leaving all six real songs stranded in conflicts. Dropping the header at
    the point the data enters fixes the whole cascade at once."""
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(_mccoury_md(tagged=False)), FakeProvider(),
                      make_candidate(), IDENT)
    assert [t.title for t in show.tracks] == MCCOURY_SONGS
    assert all(t.title_source == "setlist" for t in show.tracks)
    assert not any("unresolved" in f for f in show.review_flags)
    assert show.needs_review is False
    assert show.structure is not None
    assert show.structure.conflicts == []
    assert show.structure.coverage == 1.0


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
