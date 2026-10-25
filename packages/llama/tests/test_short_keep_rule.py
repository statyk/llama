"""Piece 4: keep short files that belong to the show (spec
docs/superpowers/specs/2026-10-23-junk-short-keep-design.md, sections 1 and
2.1-2.5, strict surface (c)).

A file whose ONLY drop reason is the short-duration arm is kept unless it trips
the spam-shape tripwire or its tag is wholly junk; an untagged one is kept only
when interior in play order and its filename stem is not wholly junk."""
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

from llama.junk import (
    FORMAT_BY_AUDIO,
    SPAM_REASON,
    filter_files,
    short_filename_is_junk,
    short_is_spam,
    short_tag_is_junk,
    short_verdict,
)

FIXTURES = Path(__file__).parent / "fixtures"
CORPUS = FIXTURES / "short_keep_corpus.jsonl"


def _mp3(name, *, track=None, title=None, source="original", original=None,
         length="300.0"):
    d = {"name": name, "format": "VBR MP3", "source": source, "length": length}
    if track is not None:
        d["track"] = track
    if title is not None:
        d["title"] = title
    if original is not None:
        d["original"] = original
    return d


def _names(kept):
    return [f["name"] for f in kept]


def _reasons(excluded):
    return {e["filename"]: e["reasons"] for e in excluded}


# --- the deny vocabulary, measured (spec 2.3) ---

def test_deny_vocabulary_corpus():
    """Strict surface (c). Every one of the library's 3,547 short-only drops,
    re-decided by `short_verdict`, must reproduce the census decision `r1_dec`
    (the r1 round, ~/.llama-harness/piece45/spec/r1/r1_files.py).

    What this does NOT cover: the corpus `pos` is the census's own (`r.py`), so
    the filter's interior derivation (play order, the kept-and-tagged-kept
    neighbour set) and the original-title fallback are not exercised here;
    Task 9's reference reproduction is their end-to-end gate."""
    rows = [json.loads(line) for line in CORPUS.read_text().splitlines()]
    assert len(rows) == 3547
    verdicts = Counter()
    classes = Counter()
    for r in rows:
        v = short_verdict(r["name"], r["tag"], None, interior=(r["pos"] == "interior"))
        dec = r["r1_dec"]
        verdicts[v] += 1
        classes[dec] += 1
        where = (r["slug"], r["name"], r["tag"], dec, v)
        assert (v == "keep") == dec.startswith("keep"), where
        if dec in ("drop-junk", "drop-nonperf"):
            assert v == "junk", where
        elif dec == "drop-filename":
            assert v == "filename", where
        elif dec == "drop-edge":
            assert v in ("edge", "filename"), where
    assert classes["keep"] + classes["keep-untagged"] == 2816
    assert classes["drop-junk"] + classes["drop-nonperf"] == 691
    assert classes["drop-filename"] == 3
    assert classes["drop-edge"] == 37
    # The two `01 Crowd.mp3` edge rows are filename junk: short_verdict checks
    # filename junk before the interior test.
    assert dict(verdicts) == {"keep": 2816, "junk": 691, "filename": 5, "edge": 35}


@pytest.mark.parametrize("tag", [
    "intro/tuning", "tuning/banter", "Take A Step Back/Tuning",
    "Mexican Hat Dance Tuning", "crowd/tuning jam", "Bob Weir comment to crowd",
    "Stage Announcements", "Banter Promote CD", "banter - promoting the new CD",
    "Stage Banter: Consummation Station", "Mohammed's Radio", "Radio Blues",
    "Jesus on the Radio", "Radio Free Europe", "DJ Logic / Jam",
    "", "--",
])
def test_junk_test_examples_kept(tag):
    """Spec 2.3 notes: per-part anchoring, radio/DJ need a broadcast
    qualifier, stage banter is kept, empty cleaning is not junk."""
    assert short_tag_is_junk(tag) is False


@pytest.mark.parametrize("tag", [
    "crowd/tuning", "Crowd & Tuning", "2: crowd/tuning ->", "Radio Outro",
    "radio ID", "tuning", "Tunning",
])
def test_junk_test_examples_junk(tag):
    assert short_tag_is_junk(tag) is True


# --- Checkpoint A rulings, 2026-10-24 ---

@pytest.mark.parametrize("tag", [
    'Rock and Roll (Played over PA - fades in)',
    'Mardi Gras Celebration (Hey Pocky Way on PA)',
    'WXRT Intro',
    'Host #03 "General Banter"',
    'HOST #12 "Intermission..."',
    'HOST #16 "Post-Show Banter"',
    "Closing Music", "exit music", "Outro Music", "KDHX ID", "WXRT-FM Station Announcer",
])
def test_ruling2_nonperf_additions_drop(tag):
    assert short_tag_is_junk(tag) is True


@pytest.mark.parametrize("tag", [
    "Ardmore, PA", "WAR", "Not Fade Away", "Terrapin Station", "Intro", "Band Intro",
    "Stage Banter", "kdhx intro", "wake intro", "Wake Up Intro", "Hostile", "Host",
    "Sgt. Pepper's PA/crowd",
])
def test_ruling2_keep_cases_stay_kept(tag):
    """Call letters are case-sensitive: lowercase `kdhx intro` and the word
    `wake` do not read as a call sign."""
    assert short_tag_is_junk(tag) is False


def test_ruling1_zero_duration_stub_is_not_kept():
    """A tagged file whose length is `00:00` (0.0, not None, so the `missing
    duration` arm does not fire) keeps `implausibly short` and is dropped."""
    files = [_mp3(f"band1t0{i}.mp3") for i in range(1, 6)]
    files.append(_mp3("band1t06.mp3", title="Promised Land", length="00:00"))
    files.append(_mp3("band1t07.mp3"))
    kept, excluded, ordering = filter_files(files)
    assert "band1t06.mp3" not in _names(kept)
    assert _reasons(excluded) == {"band1t06.mp3": ["implausibly short"]}
    assert ordering["short_kept"] == []


def test_ruling1_short_nonzero_file_still_kept():
    files = [_mp3(f"band1t0{i}.mp3") for i in range(1, 6)]
    files.append(_mp3("band1t06.mp3", title="Promised Land", length="4"))
    files.append(_mp3("band1t07.mp3"))
    kept, excluded, ordering = filter_files(files)
    assert "band1t06.mp3" in _names(kept)
    assert ordering["short_kept"] == ["band1t06.mp3"]


@pytest.mark.parametrize("tag", ["Not Fade Away Chant", "Crowd Doing Not Fade Away"])
def test_a_not_fade_away_crowd_chant_is_kept_operator_ruling(tag):  # (pin)
    """Operator ruling 2, Checkpoint B (2026-10-24): "An NFA chant should absolutely
    not be dropped; other crowd chants could go either way but inclusion is safer."
    The library tags `Not Fade Away Chant` (deadandcompany-2015-11-17) and `Crowd
    Doing Not Fade Away` (thedead-2015-07-05) are kept by the short rule: no later
    vocabulary change may drop them."""
    assert short_tag_is_junk(tag) is False
    files = [_mp3(f"band1t0{i}.mp3") for i in range(1, 6)]
    files.append(_mp3("band1t06.mp3", title=tag, length="40.0"))
    files.append(_mp3("band1t07.mp3"))
    kept, excluded, ordering = filter_files(files)
    assert "band1t06.mp3" in _names(kept)
    assert excluded == []
    assert ordering["short_kept"] == ["band1t06.mp3"]


# --- the spam tripwire (spec 2.3) ---

@pytest.mark.parametrize("filename", [
    "band05 www.x.mp3", "band05 foo.com.mp3",
    "band05 @bypikeno.mp3", "band05-follow-me.mp3", "band05 download.mp3",
    "band05 subscribe now.mp3",
])
def test_tripwire_spam_stems(filename):
    """The `https?://` term cannot fire on a stem: the basename is cut at the
    last `/`. It is exercised on a tag below."""
    assert short_is_spam(filename, None, None) is True


@pytest.mark.parametrize("own,original", [
    ("Follow me on X", None), ("follow us", None), ("http://x.example", None),
    (None, "Follow me on X"),           # the original's title is read too
    ("Drums", "see www.x"),
])
def test_tripwire_spam_tags(own, original):
    assert short_is_spam("band05.mp3", own, original) is True


@pytest.mark.parametrize("filename,own", [
    ("band05.mp3", "John follows his fingers"),   # mountaingoats-2017-06-02
    ("band05.mp3", "I'll Follow the Sun"),
    ("band05.mp3", "Follow You Down"),            # bare words count in the stem only
    ("bwww1996-12-31t01.mp3", None),              # `www` not at a word boundary
])
def test_tripwire_not_spam(filename, own):
    assert short_is_spam(filename, own, None) is False


def test_tripwire_reads_no_album_or_artist():
    """album/artist/creator are item-wide strings (venue `@` signs, taper
    domains: 7 false hits, 0 true); the function has no parameter for them."""
    import inspect
    assert list(inspect.signature(short_is_spam).parameters) == [
        "filename", "own_title", "original_title"]
    # and the filter does not read them either
    item_wide = {"album": "Summerdance@Nelson Ledges", "artist": "SeparateReality.org",
                 "creator": "www.taper.com"}
    files = ([{**_mp3(f"band1t0{i}.mp3"), **item_wide} for i in range(1, 6)]
             + [{**_mp3("band1t06.mp3", title="Drums", length="40.0"), **item_wide},
                {**_mp3("band1t07.mp3"), **item_wide}])
    kept, _, ordering = filter_files(files)
    assert "band1t06.mp3" in _names(kept)
    assert ordering["short_kept"] == ["band1t06.mp3"]


def test_tripwire_drop_records_its_own_reason():
    """Spec 2.3 'Its own reason' and 2.5. The spam file carries the item's
    dominant stem (`band1t`) so it reaches the short arm alone: a bare
    `follow-me-now.mp3` would fail the filename-convention arm too and is not
    a short-only drop at all."""
    files = [_mp3(f"band1t0{i}.mp3") for i in range(1, 6)]
    files.insert(2, _mp3("band1t09 follow-me-now.mp3", length="40.0"))   # interior, untagged
    files.append(_mp3("band1t08.mp3", length="40.0"))                      # edge, untagged
    kept, excluded, ordering = filter_files(files)
    assert "band1t09 follow-me-now.mp3" not in _names(kept)
    assert _reasons(excluded) == {
        "band1t09 follow-me-now.mp3": [SPAM_REASON],
        "band1t08.mp3": ["implausibly short"],
    }
    assert SPAM_REASON == "spam-shaped name or tag"
    assert ordering["short_kept"] == []


def test_spam_tag_on_an_interior_tagged_file_drops():
    files = [_mp3(f"band1t0{i}.mp3") for i in range(1, 6)]
    files.insert(2, _mp3("band1t09.mp3", title="Follow me on X", length="40.0"))
    _, excluded, _ = filter_files(files)
    assert _reasons(excluded) == {"band1t09.mp3": [SPAM_REASON]}


# --- untagged short files (spec 2.4) ---

def test_untagged_interior_kept_edge_dropped():
    """Spec 2.4. U2 is the case that catches Task 21 mutant (e): counting
    untagged candidates as neighbours would give it U1 before and keep it."""
    files = [
        _mp3("band1t01.mp3", length="30.0"),   # U1, edge
        _mp3("band1t02.mp3", length="30.0"),   # U2, edge (only U1 before it)
        _mp3("band1t03.mp3"),
        _mp3("band1t04.mp3"),
        _mp3("band1t05.mp3", length="30.0"),   # interior
        _mp3("band1t06.mp3"),
        _mp3("band1t07.mp3"),
        _mp3("band1t08.mp3", length="30.0"),   # last, edge
    ]
    kept, excluded, ordering = filter_files(files)
    assert _names(kept) == ["band1t03.mp3", "band1t04.mp3", "band1t05.mp3",
                            "band1t06.mp3", "band1t07.mp3"]
    assert _reasons(excluded) == {
        "band1t01.mp3": ["implausibly short"],
        "band1t02.mp3": ["implausibly short"],
        "band1t08.mp3": ["implausibly short"],
    }
    assert ordering["short_kept"] == ["band1t05.mp3"]


def _tag_order_tape(drums_track):
    """Filename order b01..b07; the untagged short b07 is LAST by filename but
    track 4 (interior) by tag. b06 is a tagged short file the rule keeps."""
    return [
        _mp3("b01.mp3", track="2"), _mp3("b02.mp3", track="3"),
        _mp3("b03.mp3", track="5"), _mp3("b04.mp3", track="6"),
        _mp3("b05.mp3", track="7"),
        _mp3("b06.mp3", track=drums_track, title="Drums", length="30.0"),
        _mp3("b07.mp3", track="4", length="30.0"),
    ]


def test_interior_uses_track_tag_order_only_when_complete_and_unique():
    """Spec 2.4: play order is track-tag order when every file in the set
    (kept, tagged-kept and untagged candidates) has a unique track number,
    else filename order."""
    kept, _, ordering = filter_files(_tag_order_tape("8"))
    assert "b07.mp3" in _names(kept)
    assert ordering["order_source"] == "track-tags"
    assert ordering["short_kept"] == ["b06.mp3", "b07.mp3"]

    # one duplicate tag (the tagged-kept b06 shares b01's "2"): filename order,
    # where b07 is last -> edge -> dropped
    kept, excluded, ordering = filter_files(_tag_order_tape("2"))
    assert "b07.mp3" not in _names(kept)
    assert _reasons(excluded) == {"b07.mp3": ["implausibly short"]}
    assert ordering["short_kept"] == ["b06.mp3"]

    # incomplete (b06 carries no track number): filename order too
    kept, _, _ = filter_files(_tag_order_tape(None))
    assert "b07.mp3" not in _names(kept)


def test_interior_ignores_spam_and_filename_junk_neighbours():
    """Spam and filename-junk files are not in the play-order set, so they
    cannot make an untagged file interior."""
    files = [
        _mp3("01 a.mp3"), _mp3("02 b.mp3"), _mp3("03 c.mp3"), _mp3("04 d.mp3"),
        _mp3("05 e.mp3"),
        _mp3("06 x.mp3", length="30.0"),           # untagged, only junk after it
        _mp3("07 Crowd.mp3", length="30.0"),       # filename junk
        _mp3("08 www.x.mp3", length="30.0"),       # spam
    ]
    _, excluded, ordering = filter_files(files)
    assert _reasons(excluded) == {
        "06 x.mp3": ["implausibly short"],
        "07 Crowd.mp3": ["implausibly short"],
        "08 www.x.mp3": [SPAM_REASON],
    }
    assert ordering["short_kept"] == []


def test_filename_junk_drops_untagged_only():
    """Spec 2.4 'Filename junk' (untagged only) and 2.2 (a placeholder tag such
    as `tmp` counts as tagged, so the filename is never consulted)."""
    files = [
        _mp3("01 a.mp3"),
        _mp3("0201tuning.mp3", length="30.0"),
        _mp3("03 b.mp3"),
        _mp3("10 Crowd.mp3", length="30.0"),
        _mp3("10.tuningup.mp3", title="tmp", length="30.0"),
        _mp3("11 c.mp3"),
        _mp3("12 d.mp3"),
    ]
    kept, excluded, ordering = filter_files(files)
    assert _reasons(excluded) == {
        "0201tuning.mp3": ["implausibly short"],
        "10 Crowd.mp3": ["implausibly short"],
    }
    assert "10.tuningup.mp3" in _names(kept)
    assert ordering["short_kept"] == ["10.tuningup.mp3"]
    assert short_filename_is_junk("10 Crowd.mp3")
    assert short_filename_is_junk("0201tuning.mp3")
    assert short_filename_is_junk("dir/09 Crowd.flac")
    assert not short_filename_is_junk("05 Slipknot.mp3")


def test_tag_falls_back_to_the_original_title():
    """Review Focus 1 / spec 2.2: a derivative with no `title` takes its
    original's. The `Drums` derivative is at the tape's edge (untagged it
    would drop); the `tuning` one is interior (untagged it would be kept)."""
    files = []
    for i in range(1, 8):
        files.append({"name": f"x1t0{i}.flac", "format": "Flac", "source": "original"})
    files[2]["title"] = "tuning"
    files[6]["title"] = "Drums"
    for i in range(1, 8):
        short = i in (3, 7)
        files.append(_mp3(f"x1t0{i}.mp3", source="derivative", original=f"x1t0{i}.flac",
                          length="30.0" if short else "300.0"))
    kept, excluded, ordering = filter_files(files)
    assert "x1t07.mp3" in _names(kept)
    assert _reasons(excluded) == {"x1t03.mp3": ["implausibly short"]}
    assert ordering["short_kept"] == ["x1t07.mp3"]


def test_short_kept_names_survive_dedupe_only():
    """Review Focus 2: a short candidate that is also a duplicate listing.
    Dedupe still drops the second copy, and only the surviving copy is named
    in ordering["short_kept"]."""
    files = [_mp3(f"band1t0{i}.mp3") for i in range(1, 6)]
    files += [_mp3("band1t06.mp3", title="Drums", length="40.0"),
              _mp3("band99/band1t06.mp3", title="Drums", length="40.0"),
              _mp3("band1t07.mp3")]
    kept, excluded, ordering = filter_files(files)
    assert _names(kept).count("band1t06.mp3") == 1
    assert "band99/band1t06.mp3" not in _names(kept)
    assert _reasons(excluded) == {"band99/band1t06.mp3": ["duplicate-listing"]}
    assert ordering["short_kept"] == ["band1t06.mp3"]


def _doubled(short_track: int, *, prefix: str = "band99/") -> list[dict]:
    """A 7-track tape listed twice, at top level and under an <identifier>/
    prefix (the ymsb2005 donor shape), every copy carrying its track tag; track
    `short_track` is an untagged 30 s file. The duplicate track numbers force
    filename order, where the two listings sort as two blocks."""
    one = [_mp3(f"band1t0{i}.mp3", track=str(i),
                length="30.0" if i == short_track else "300.0") for i in range(1, 8)]
    return one + [{**f, "name": prefix + f["name"]} for f in one]


@pytest.mark.parametrize("short_track", [1, 7], ids=["first", "last"])
def test_doubled_listing_untagged_short_edge_file_drops(short_track):
    """Spec 2.4 (ruling 4), strict surface (c): play order for the interior
    test is derived the way filter_files derives it, over one copy per listing.
    Over both listings, the top-level copy of an untagged short FIRST track has
    the whole prefixed block after it, and the prefixed copy of an untagged
    short LAST track has the whole top-level block before it; neither is
    interior. Both copies drop, as on the single listing."""
    name = f"band1t0{short_track}.mp3"
    single_kept, single_excl, _ = filter_files(_doubled(short_track)[:7])
    assert _reasons(single_excl) == {name: ["implausibly short"]}
    kept, excluded, ordering = filter_files(_doubled(short_track))
    assert name not in _names(kept) and "band99/" + name not in _names(kept)
    reasons = _reasons(excluded)
    assert reasons[name] == reasons["band99/" + name] == ["implausibly short"]
    assert ordering["short_kept"] == []
    assert [f["name"].rsplit("/", 1)[-1] for f in kept] == _names(single_kept)


def test_doubled_listing_untagged_short_interior_file_is_kept():
    kept, excluded, ordering = filter_files(_doubled(4))
    assert [f["name"] for f in kept] == [f"band1t0{i}.mp3" for i in range(1, 8)]
    assert ordering["short_kept"] == ["band1t04.mp3"]
    assert _reasons(excluded)["band99/band1t04.mp3"] == ["duplicate-listing"]


def test_doubled_listing_order_follows_unique_tags_after_dedupe():
    """The "complete and unique" test runs on the collapsed pool too: one copy
    per listing has unique track tags, so the interior test follows them. The
    untagged short file is LAST by filename and track 4 by tag: kept."""
    one = [_mp3(f"band1t0{i}.mp3", track=str(t)) for i, t in
           zip(range(1, 7), (1, 2, 3, 5, 6, 7))]
    one.append(_mp3("band1t07.mp3", track="4", length="30.0"))
    kept, _, ordering = filter_files(one + [{**f, "name": "band99/" + f["name"]} for f in one])
    assert ordering["order_source"] == "track-tags"
    assert ordering["short_kept"] == ["band1t07.mp3"]
    assert [f["name"] for f in kept][3] == "band1t07.mp3"


# --- what does not change (spec 2.1, 2.5) ---

def test_other_reasons_untouched():
    """(pin) Spec 2.1: a file failing the short arm AND another arm keeps both
    reasons and stays excluded, whatever its tag; the gd73 spam file is still
    excluded with its convention reason."""
    files = [_mp3(f"band1t0{i}.mp3") for i in range(1, 6)]
    files.insert(2, _mp3("other1t09.mp3", title="Drums", length="40.0"))
    _, excluded, ordering = filter_files(files)
    assert _reasons(excluded) == {
        "other1t09.mp3": ["filename convention mismatch", "implausibly short"]}
    assert ordering["short_kept"] == []

    gd73 = json.loads((FIXTURES / "gd73_metadata.json").read_text())["files"]
    kept, excluded, _ = filter_files(gd73)
    spam = _reasons(excluded)["FOLLOW-ME @BYPIKENO.mp3"]
    assert "filename convention mismatch" in spam
    assert "implausibly short" in spam
    assert "FOLLOW-ME @BYPIKENO.mp3" not in _names(kept)


def _load_v2_17_0():
    spec = importlib.util.spec_from_file_location(
        "junk_v2_17_0", FIXTURES / "junk_v2_17_0.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixture_file_lists():
    out = []
    for p in sorted(FIXTURES.glob("*.json")):
        data = json.loads(p.read_text())
        if isinstance(data, dict) and data.get("files"):
            out.append((p.name, data["files"]))
    return out


def test_short_keep_false_reproduces_today():
    """(pin) Spec 2.5: `short_keep=False` reproduces e37f670's filter exactly,
    apart from the always-present `ordering["short_kept"] == []`."""
    old = _load_v2_17_0()
    lists = _fixture_file_lists()
    assert len(lists) >= 10
    for name, files in lists:
        for audio in ("mp3", "flac"):
            want = FORMAT_BY_AUDIO[audio]
            o_kept, o_excl, o_ord = old.filter_files(files, want)
            kept, excl, ordering = filter_files(files, want, short_keep=False)
            assert ordering.pop("short_kept") == [], (name, audio)
            assert (_names(kept), excl, ordering) == (_names(o_kept), o_excl, o_ord), (name, audio)
            assert all(a is b for a, b in zip(kept, o_kept)), (name, audio)


def test_short_keep_true_changes_some_fixture():
    """Guard for the pin above: the rule is live on the real fixtures (a
    `short_keep=False` that were ignored would pass it trivially)."""
    changed = [name for name, files in _fixture_file_lists()
               if _names(filter_files(files)[0])
               != _names(filter_files(files, short_keep=False)[0])]
    assert "dso2003-01-25.json" in changed
    assert "gd73_metadata.json" not in changed


def test_floor_unchanged_by_kept_short_files():
    """(pin) Spec 2.1 'The floor': a kept short file does not change the floor.
    A (band1t01, edge) is kept when tagged and dropped when not; B (band1t08,
    the other edge, untagged) is short either way and its excluded entry, and
    every reported duration_sec, are identical."""
    def tape(a_title):
        return ([_mp3("band1t01.mp3", title=a_title, length="40.0")]
                + [_mp3(f"band1t0{i}.mp3", length=f"{280 + i}.0") for i in range(2, 8)]
                + [_mp3("band1t08.mp3", length="60.0")])
    kept_t, excl_t, _ = filter_files(tape("Drums"))
    kept_u, excl_u, _ = filter_files(tape(None))
    assert "band1t01.mp3" in _names(kept_t)
    assert "band1t01.mp3" not in _names(kept_u)
    b_t = next(e for e in excl_t if e["filename"] == "band1t08.mp3")
    b_u = next(e for e in excl_u if e["filename"] == "band1t08.mp3")
    assert b_t == b_u == {"filename": "band1t08.mp3", "reasons": ["implausibly short"],
                          "duration_sec": 60.0}
    assert [e for e in excl_t] == [b_t]
    assert [e for e in excl_u if e["filename"] != "band1t01.mp3"] == [b_u]


def test_short_keep_false_returns_no_names():
    files = [_mp3(f"band1t0{i}.mp3") for i in range(1, 6)]
    files.insert(2, _mp3("band1t09.mp3", title="Drums", length="40.0"))
    kept, excluded, ordering = filter_files(files, short_keep=False)
    assert "band1t09.mp3" not in _names(kept)
    assert _reasons(excluded) == {"band1t09.mp3": ["implausibly short"]}
    assert ordering["short_kept"] == []
