import json
from pathlib import Path

from llama.junk import FORMAT_BY_AUDIO, LOSSLESS_TITLE_FORMATS, filter_files

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
    assert ordering == {"order_source": "track-tags", "reordered": True, "format": "VBR MP3"}


def test_track_tags_agreeing_with_filenames_not_flagged():
    files = [_mp3("gd73d1t01.mp3", track="1"), _mp3("gd73d1t02.mp3", track="2")]
    _, _, ordering = filter_files(files)
    assert ordering == {"order_source": "track-tags", "reordered": False, "format": "VBR MP3"}


def test_duplicate_track_tags_fall_back_to_filename_order():
    # per-disc numbering restarts at 1 -> ambiguous -> filename order
    files = [_mp3("gd73d1t01.mp3", track="1"), _mp3("gd73d2t01.mp3", track="1")]
    kept, _, ordering = filter_files(files)
    assert [f["name"] for f in kept] == ["gd73d1t01.mp3", "gd73d2t01.mp3"]
    assert ordering == {"order_source": "filename", "reordered": False, "format": "VBR MP3"}


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
    assert ordering == {"order_source": "track-tags", "reordered": True, "format": "VBR MP3"}


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
