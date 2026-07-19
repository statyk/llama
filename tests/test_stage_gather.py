import json
from pathlib import Path

from llama.config import StructureConfig
from llama.llm.fake import FakeProvider
from llama.models import Candidate, RecordingSummary
from llama.setlistfm import SetlistFMClient
from llama.stages.gather import run_gather
from llama.workspace import ShowWorkspace

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
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("I Know You Rider", "1"), ("Eyes of the World", "2"),
         ("Johnny B. Goode", "encore")],
        venue="Robert F. Kennedy Stadium", city="Washington")])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.venue == "RFK Stadium"          # candidate venue preserved
    assert show.venue_source == "item"
    assert any("venue mismatch" in f for f in show.review_flags)


def test_gather_confident_but_contradicted_break_flags(tmp_path, monkeypatch):
    # gd73 aligns confidently to sets 1,1,1,2,2,encore (breaks [3,5]); jerrybase
    # says set 1 ends on China Cat Sunflower (track 2, mid-set 1) -> tripwire.
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("China Cat Sunflower", "1"), ("Eyes of the World", "2"),
         ("Johnny B. Goode", "encore")])])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.needs_review is True
    assert any("China Cat Sunflower" in f and "set break" in f for f in show.review_flags)


def test_gather_flags_set_count_mismatch(tmp_path, monkeypatch):
    # jerrybase says 2 sets (closers at boundaries); alignment has 3 -> mismatch.
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("I Know You Rider", "1"), ("Johnny B. Goode", "2")])])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert any("jerrybase shows 2" in f for f in show.review_flags)


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
    assert show.set_breaks == [2]
    assert show.structure is not None and show.structure.alignment == "jerrybase"
    assert "set breaks anchored from jerrybase" in show.structure.conflicts
    assert "low-confidence structure alignment" not in show.review_flags


def test_gather_jerrybase_disabled_is_noop(tmp_path, monkeypatch):
    def _boom(a, d):
        raise AssertionError("lookup must not be called when disabled")
    monkeypatch.setattr(jerrybase, "lookup", _boom)
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=False)
    assert show.needs_review is False
    assert show.venue_source == "item"
