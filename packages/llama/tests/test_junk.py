import json
from pathlib import Path

from llama.junk import FORMAT_BY_AUDIO, LOSSLESS_TITLE_FORMATS, filter_files
from llama.titles import clean_tag_titles

FIXTURE = Path(__file__).parent / "fixtures" / "gd73_metadata.json"


def load_files() -> list[dict]:
    return json.loads(FIXTURE.read_text())["files"]


def test_keeps_real_tracks_sorted():
    kept, _, _ = filter_files(load_files())
    assert [f["name"] for f in kept] == [
        "gd73-06-10d1t01.mp3", "gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3",
        "gd73-06-10d2t01.mp3", "gd73-06-10d2t02.mp3", "gd73-06-10d3t01.mp3",
    ]


def test_spam_file_excluded_with_reasons():
    _, excluded, _ = filter_files(load_files())
    spam = next(e for e in excluded if e["filename"] == "FOLLOW-ME @BYPIKENO.mp3")
    assert "filename convention mismatch" in spam["reasons"]
    assert "implausibly short" in spam["reasons"]


def _tape(durations: list[float], stem: str = "band1983t") -> list[dict]:
    """A synthetic single-format tape: every file clean except its duration."""
    return [
        {"name": f"{stem}{i:02d}.mp3", "format": "VBR MP3", "source": "original",
         "length": f"{secs}"}
        for i, secs in enumerate(durations, start=1)
    ]


def _short_reasons(files: list[dict]) -> set[str]:
    _, excluded, _ = filter_files(files)
    return {e["filename"] for e in excluded if "implausibly short" in e["reasons"]}


def test_short_song_tape_keeps_its_songs():
    """A hardcore/punk tape whose songs are ~60s must not be gutted.

    The floor is relative to the tape's OWN median, so a tape of one-minute
    songs has a one-minute-scale floor. Measured on minutemen1983-03-09: an
    absolute 90s floor dropped 27 of 38 real songs and the package still
    shipped at coverage 1.00 with no review flag."""
    assert _short_reasons(_tape([62, 58, 71, 65, 60, 55, 68, 74])) == set()


def test_long_song_tape_still_drops_tuning():
    """The junk arm must keep working where it always did: a 40s tuning
    snippet among five-minute songs is still junk."""
    files = _tape([310, 288, 340, 295, 302, 40])
    assert _short_reasons(files) == {"band1983t06.mp3"}


def test_relative_floor_falls_back_to_absolute_on_a_tiny_sample():
    """Too few durations to trust a median — keep the old absolute behaviour
    rather than inferring a floor from two files."""
    files = _tape([62, 58])
    assert _short_reasons(files) == {"band1983t01.mp3", "band1983t02.mp3"}


def test_non_audio_files_ignored_silently():
    _, excluded, _ = filter_files(load_files())
    names = {e["filename"] for e in excluded}
    assert "gd73-06-10.txt" not in names  # not want_format: never a candidate, not logged


def test_orphan_derivative_excluded():
    files = [
        {"name": "x1t01.mp3", "source": "derivative", "original": "ghost.shn",
         "format": "VBR MP3", "length": "05:00"},
    ]
    _, excluded, _ = filter_files(files)
    assert excluded[0]["reasons"] == ["derivative of unknown original"]


def _mp3(name, track=None, source="original", original=None, length="300.0"):
    d = {"name": name, "format": "VBR MP3", "source": source, "length": length}
    if track is not None:
        d["track"] = track
    if original is not None:
        d["original"] = original
    return d


def test_unique_track_tags_reorder():
    # filename order d1t01,d1t02,d1t03 but tags say d1t03 plays first
    files = [_mp3("gd73d1t01.mp3", track="2"), _mp3("gd73d1t02.mp3", track="3/16"),
             _mp3("gd73d1t03.mp3", track="1")]
    kept, _, ordering = filter_files(files)
    assert [f["name"] for f in kept] == ["gd73d1t03.mp3", "gd73d1t01.mp3", "gd73d1t02.mp3"]
    assert ordering == {"order_source": "track-tags", "reordered": True, "format": "VBR MP3", "readmitted": []}


def test_track_tags_agreeing_with_filenames_not_flagged():
    files = [_mp3("gd73d1t01.mp3", track="1"), _mp3("gd73d1t02.mp3", track="2")]
    _, _, ordering = filter_files(files)
    assert ordering == {"order_source": "track-tags", "reordered": False, "format": "VBR MP3", "readmitted": []}


def test_duplicate_track_tags_fall_back_to_filename_order():
    # per-disc numbering restarts at 1 -> ambiguous -> filename order
    files = [_mp3("gd73d1t01.mp3", track="1"), _mp3("gd73d2t01.mp3", track="1")]
    kept, _, ordering = filter_files(files)
    assert [f["name"] for f in kept] == ["gd73d1t01.mp3", "gd73d2t01.mp3"]
    assert ordering == {"order_source": "filename", "reordered": False, "format": "VBR MP3", "readmitted": []}


def test_missing_track_tag_falls_back_to_filename_order():
    files = [_mp3("gd73d1t01.mp3", track="1"), _mp3("gd73d1t02.mp3")]
    _, _, ordering = filter_files(files)
    assert ordering["order_source"] == "filename"


def test_derivative_inherits_original_track_number():
    # originals are Shorten (not the wanted format) but carry the tags
    files = [
        {"name": "gd73d1t01.shn", "format": "Shorten", "source": "original", "track": "2"},
        {"name": "gd73d1t02.shn", "format": "Shorten", "source": "original", "track": "1"},
        _mp3("gd73d1t01.mp3", source="derivative", original="gd73d1t01.shn"),
        _mp3("gd73d1t02.mp3", source="derivative", original="gd73d1t02.shn"),
    ]
    kept, _, ordering = filter_files(files)
    assert [f["name"] for f in kept] == ["gd73d1t02.mp3", "gd73d1t01.mp3"]
    assert ordering == {"order_source": "track-tags", "reordered": True, "format": "VBR MP3", "readmitted": []}


def audio(name: str, fmt: str, length: str = "05:00") -> dict:
    return {"name": name, "format": fmt, "source": "original", "length": length}


def test_filter_files_falls_back_to_24bit_flac():
    """A 24-bit-only item must not read as 'no lossless available'."""
    files = [audio("t01.flac", "24bit Flac"), audio("t02.flac", "24bit Flac")]
    kept, _, ordering = filter_files(files, want_format=FORMAT_BY_AUDIO["flac"])
    assert [f["name"] for f in kept] == ["t01.flac", "t02.flac"]
    assert ordering["format"] == "24bit Flac"


def test_filter_files_prefers_plain_flac_and_never_unions():
    """5 corpus items carry both Flac and 24bit Flac. A union would keep every
    track of those items twice."""
    files = [
        audio("t01.flac", "Flac"), audio("t02.flac", "Flac"),
        audio("t01.24.flac", "24bit Flac"), audio("t02.24.flac", "24bit Flac"),
    ]
    kept, _, ordering = filter_files(files, want_format=FORMAT_BY_AUDIO["flac"])
    assert [f["name"] for f in kept] == ["t01.flac", "t02.flac"]
    assert ordering["format"] == "Flac"


def test_filter_files_skips_a_format_whose_kept_set_is_empty():
    """gd1985-07-01.144157.nak304.guy.pailes.miller.clugston.flac2496's shape:
    every `Flac` entry is junk while a clean `24bit Flac` set sits in the same
    item. Preference is decided on the KEPT set, not the raw format-matched
    list, or a flac-configured user sees no lossless at all on that show.
    (Durationless entries are junk the same way the gd73 fixture's .shn files
    are.)"""
    files = [
        audio("t01.flac", "Flac", length=None),
        audio("t02.flac", "Flac", length=None),
        audio("t01.24.flac", "24bit Flac"), audio("t02.24.flac", "24bit Flac"),
    ]
    kept, _, ordering = filter_files(files, want_format=FORMAT_BY_AUDIO["flac"])
    assert [f["name"] for f in kept] == ["t01.24.flac", "t02.24.flac"]
    assert ordering["format"] == "24bit Flac"


def test_filter_files_falls_back_to_the_first_format_when_every_kept_set_is_empty():
    """A genuinely unusable item keeps today's behaviour: the first format that
    had any audio entries at all is reported, so `excluded` still explains WHY
    the item was rejected instead of coming back empty and saying nothing."""
    files = [
        audio("t01.flac", "Flac", length=None),
        audio("t01.24.flac", "24bit Flac", length=None),
    ]
    kept, excluded, ordering = filter_files(files, want_format=FORMAT_BY_AUDIO["flac"])
    assert kept == []
    assert ordering["format"] == "Flac"
    assert [e["filename"] for e in excluded] == ["t01.flac"]
    assert "missing duration" in excluded[0]["reasons"]


def test_filter_files_still_accepts_a_bare_format_string():
    files = [audio("t01.mp3", "VBR MP3")]
    kept, _, ordering = filter_files(files, want_format="VBR MP3")
    assert len(kept) == 1
    assert ordering["format"] == "VBR MP3"


def test_filter_files_reports_no_format_when_nothing_matches():
    kept, _, ordering = filter_files([audio("t01.ogg", "Ogg Vorbis")],
                                     want_format=FORMAT_BY_AUDIO["flac"])
    assert kept == []
    assert ordering["format"] == ""


def test_lossless_title_formats_is_broader_than_the_delivery_formats():
    """Shorten is a title-reading source only - recovery never downloads it,
    and adding it to delivery would change what llama ships."""
    assert "Shorten" in LOSSLESS_TITLE_FORMATS
    assert "Shorten" not in FORMAT_BY_AUDIO["flac"]


def test_duplicate_listing_keeps_the_titled_copy():
    """Some archive.org items list every track twice - once at top level,
    once under an <identifier>/ prefix - with identical durations and a
    title on only one copy (ymsb2005's donor: 56 files for 28 tracks). The
    prefix "band99" is chosen so its own leading text before a digit ("band")
    matches the filename's ("band1t01.mp3" -> stem "band"), the same reason
    real archive.org identifiers collide with their own track filenames'
    naming convention - otherwise the mismatched copy would be dropped by
    the filename-convention arm before dedupe ever sees it."""
    files = [
        _mp3("band1t01.mp3", length="300.0"),
        {**_mp3("band99/band1t01.mp3", length="300.0"), "title": "Alpha"},
    ]
    kept, excluded, _ = filter_files(files)
    assert len(kept) == 1
    assert clean_tag_titles(kept) == ["Alpha"]
    dropped = next(e for e in excluded if e["filename"] == "band1t01.mp3")
    assert dropped["reasons"] == ["duplicate-listing"]


def test_same_basename_different_duration_both_kept():
    """Two files sharing a basename but with different lengths are different
    tracks, not a duplicate listing - both must survive."""
    files = [
        _mp3("band1t01.mp3", length="180.0"),
        _mp3("band99/band1t01.mp3", length="420.0"),
    ]
    kept, excluded, _ = filter_files(files)
    assert {f["name"] for f in kept} == {"band1t01.mp3", "band99/band1t01.mp3"}
    assert not any("duplicate-listing" in e["reasons"] for e in excluded)


def test_dedupe_runs_before_play_order_derivation():
    """Play order must be derived from the DEDUPED list, per the brief. With
    both duplicate pairs still present the two "1" track tags (and the two
    "2"s) are non-unique, so ordering falls back to filename order; only
    once the duplicates collapse do the tags become unique and
    order_source can read "track-tags". (Here the titled copies are the
    prefixed ones and win the swap - the real ymsb2005 item is the other
    way around, with the top-level copies carrying the tags; either
    direction should collapse onto whichever copy has a title.)"""
    files = [
        _mp3("band1t02.mp3", track="2", length="300.0"),
        _mp3("band1t01.mp3", track="1", length="180.0"),
        {**_mp3("band99/band1t01.mp3", track="1", length="180.0"), "title": "Alpha"},
        {**_mp3("band99/band1t02.mp3", track="2", length="300.0"), "title": "Beta"},
    ]
    kept, _, ordering = filter_files(files)
    assert ordering["order_source"] == "track-tags"
    assert [f["name"] for f in kept] == ["band99/band1t01.mp3", "band99/band1t02.mp3"]


def test_dedupe_runs_after_junk_filtering():
    """Dedupe must run AFTER _keep_and_exclude for the winning format, not
    on the raw file list: a titled copy of bad provenance must never win
    the swap and displace the clean untitled original, or the track would
    be junk-filtered away entirely instead of surviving as the clean
    copy."""
    files = [
        _mp3("band1t01.mp3", length="300.0"),
        {**_mp3("band99/band1t01.mp3", length="300.0", source="mystery"),
         "title": "Alpha"},
    ]
    kept, _, _ = filter_files(files)
    assert [f["name"] for f in kept] == ["band1t01.mp3"]


def test_clean_item_byte_identical_through_filter_files():
    """An item with no duplicate listings must pass through unchanged: same
    kept objects (not copies), same names, no duplicate-listing reasons."""
    files = load_files()
    kept, excluded, _ = filter_files(files)
    assert [f["name"] for f in kept] == [
        "gd73-06-10d1t01.mp3", "gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3",
        "gd73-06-10d2t01.mp3", "gd73-06-10d2t02.mp3", "gd73-06-10d3t01.mp3",
    ]
    assert not any("duplicate-listing" in e["reasons"] for e in excluded)
    by_name = {f["name"]: f for f in files}
    for f in kept:
        assert f is by_name[f["name"]]


# --- operator re-admission (overrides.include) ---

def test_readmit_returns_an_excluded_file_to_kept():
    """The gd73 fixture's spam file is dropped by two arms at once; naming it
    in `readmit` puts it back and takes it out of `excluded` entirely."""
    kept, excluded, _ = filter_files(
        load_files(), readmit=frozenset({"FOLLOW-ME @BYPIKENO.mp3"}))
    assert "FOLLOW-ME @BYPIKENO.mp3" in {f["name"] for f in kept}
    assert all(e["filename"] != "FOLLOW-ME @BYPIKENO.mp3" for e in excluded)


def test_readmit_of_an_unknown_filename_changes_nothing():
    base_kept, base_excluded, base_order = filter_files(load_files())
    kept, excluded, order = filter_files(load_files(), readmit=frozenset({"nope.mp3"}))
    assert [f["name"] for f in kept] == [f["name"] for f in base_kept]
    assert [e["filename"] for e in excluded] == [e["filename"] for e in base_excluded]
    assert order == base_order


def test_readmit_does_not_move_the_duration_floor():
    """The two-pass invariant: the floor is the median of files passing every
    OTHER arm, computed before any re-admission. Re-admitting files dropped by
    a NON-duration arm must not let their durations join that median --
    otherwise one operator override would quietly lower the junk threshold
    for the whole tape.

    Review round 1 finding: the original version of this test used only
    duration-arm exclusions, whose durations are already in the median
    sample before re-admission, so no placement of the re-admission step
    could move the floor for that data -- the test passed against a mutant
    that moved re-admission before the floor computation (measured floor
    75.0 either way). This dataset excludes the re-admitted files by
    PROVENANCE (`source="mystery"`) instead, so they start outside
    `clean_secs` and only join it if re-admission runs too early."""
    files = ([_mp3(f"band1t0{i}.mp3") for i in range(1, 6)]              # 5 x 300s, clean
             + [_mp3(f"band1t1{i}.mp3", source="mystery", length="20.0") # 5 x 20s, dropped
                for i in range(5)]                                       #   by provenance
             + [_mp3("band1t20.mp3", length="50.0")])                    # the canary
    readmit = frozenset(f"band1t1{i}.mp3" for i in range(5))
    kept, excluded, _ = filter_files(files, readmit=readmit)
    assert readmit <= {f["name"] for f in kept}
    # The floor stays 0.25 * median([300]*5 + [50]) = 75, so the 50s canary is
    # still junk. If re-admission moved ahead of the floor computation the five
    # 20s files would join the sample, the median would fall to 50 and the
    # canary would be licensed.
    assert {e["filename"] for e in excluded
            if "implausibly short" in e["reasons"]} == {"band1t20.mp3"}


def test_readmit_lands_in_filename_play_order():
    files = [_mp3("band1t01.mp3"), _mp3("band1t02.mp3", length="40.0"),
             _mp3("band1t03.mp3"), _mp3("band1t04.mp3"), _mp3("band1t05.mp3"),
             _mp3("band1t06.mp3")]
    kept, _, _ = filter_files(files, readmit=frozenset({"band1t02.mp3"}))
    assert [f["name"] for f in kept] == [f"band1t0{i}.mp3" for i in range(1, 7)]


def test_readmitting_an_untagged_file_falls_back_to_filename_order():
    """Play order is derived ONCE, over the final kept set. A re-admitted file
    with no track tag therefore breaks the completeness test at junk.py's
    ordering block and the whole recording reverts to filename order. This is
    the accepted price of not splicing a file into an order derived without
    it (spec section 2)."""
    files = [_mp3("band1t01.mp3", track="5", length="310.0"),
             _mp3("band1t02.mp3", track="4", length="288.0"),
             _mp3("band1t03.mp3", track="3", length="340.0"),
             _mp3("band1t04.mp3", track="2", length="295.0"),
             _mp3("band1t05.mp3", track="1", length="302.0"),
             _mp3("band1t06.mp3", length="40.0")]
    _, _, base_order = filter_files(files)
    assert base_order["order_source"] == "track-tags"
    kept, _, order = filter_files(files, readmit=frozenset({"band1t06.mp3"}))
    assert order["order_source"] == "filename"
    assert [f["name"] for f in kept] == [f"band1t0{i}.mp3" for i in range(1, 7)]


def test_readmit_of_a_duplicate_listing_ships_the_track_twice():
    """Owner decision 2026-09-07: no reason is refused. Re-admitting a
    duplicate listing therefore ships that recording twice, deliberately --
    the excluded table names the reason next to the handle."""
    files = [
        _mp3("band1t01.mp3", length="300.0"),
        {**_mp3("band99/band1t01.mp3", length="300.0"), "title": "Alpha"},
    ]
    kept, excluded, _ = filter_files(files, readmit=frozenset({"band1t01.mp3"}))
    assert {f["name"] for f in kept} == {"band1t01.mp3", "band99/band1t01.mp3"}
    assert excluded == []


def test_excluded_entries_carry_a_duration():
    """The operator has to judge a dropped file from the listing, so every
    excluded entry records how long it was (None when the item had no length,
    which is itself one of the exclusion reasons)."""
    _, excluded, _ = filter_files(load_files())
    spam = next(e for e in excluded if e["filename"] == "FOLLOW-ME @BYPIKENO.mp3")
    assert isinstance(spam["duration_sec"], float)
    assert all("duration_sec" in e for e in excluded)
