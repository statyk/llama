"""Piece 4 fix wave, part 1 (operator rulings 2026-10-25, relayed by llama-db).

I-1: with `short_keep=True`, `filter_files` picks, among the configured audio
format's formats, the one whose KEPT files have the greatest total running time;
`FORMAT_BY_AUDIO` order breaks ties only, and when no format keeps anything the
first format with any audio is returned (so `excluded` explains). Before this, the
first format with ANY kept file won, so a 16-bit `Flac` format holding one
rule-kept 61 s "Outro" beat a 24-bit format holding the whole show.

I-2: within the winning format, at most one derivative per `original` is kept,
long and short (the doubled `X.mp3` / `X_vbr.mp3` class). The plain `X.mp3` is
preferred (`junk.PREFER_VBR_DERIVATIVE`); dropped copies go to `excluded` with
reason `junk.DUPLICATE_DERIVATIVE_REASON`, and `overrides.include` can re-admit
one.

Orchestrator ruling: with `short_keep=False` both changes are off, so the filter
and `final_kept` stay byte-identical to v2.17.0 (the migration's consistency
check reads legacy show.json files that way)."""
import importlib.util
import json
from collections import Counter
from pathlib import Path

from llama import junk
from llama.junk import FORMAT_BY_AUDIO, filter_files
from llama.models import Overrides
from llama.stages.gather import final_kept

# The constants are read through the module, so a missing one fails its own test only.
DUP = "duplicate derivative"
FIXTURES = Path(__file__).parent / "fixtures"
FLAC = FORMAT_BY_AUDIO["flac"]


def _load(name):
    return json.loads((FIXTURES / name).read_text())["files"]


def _v2_17_0():
    spec = importlib.util.spec_from_file_location("junk_v2_17_0", FIXTURES / "junk_v2_17_0.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _names(kept):
    return [f["name"] for f in kept]


def _reasons(excluded):
    return {e["filename"]: e["reasons"] for e in excluded}


def _flac(name, fmt, length="300.0", title=None):
    d = {"name": name, "format": fmt, "source": "original", "length": length}
    if title is not None:
        d["title"] = title
    return d


def _mp3(name, *, original, length="300.0", title=None, track=None):
    d = {"name": name, "format": "VBR MP3", "source": "derivative",
         "original": original, "length": length}
    if title is not None:
        d["title"] = title
    if track is not None:
        d["track"] = track
    return d


# --- I-1: format choice by kept running time ---------------------------------

def test_tsp_shape_whole_24bit_show_beats_one_short_16bit_file():
    """tsp2007-07-28.csb.flac24 (real cache capture): `Flac` holds one file, t34
    "Outro" (60.82 s), which the short-keep rule keeps; `24bit Flac` holds the
    other 33 tracks. The 24-bit format has the greater kept running time and
    wins; before the fix `Flac` won with that one file."""
    files = _load("tsp2007-07-28.csb.flac24.json")
    kept, excluded, ordering = filter_files(files, FLAC)
    assert ordering["format"] == "24bit Flac"
    assert len(kept) == 33
    assert "tsp2007-07-28.csb.t34.flac" not in _names(kept)
    assert all(f["format"] == "24bit Flac" for f in kept)


def test_a_longer_second_format_wins_over_a_non_empty_first():
    """The rule is running time, not 'first non-empty' and not 'first with a
    floor-passing file': a 5-track Flac copy loses to a 12-track 24-bit one."""
    files = ([_flac(f"a1t0{i}.flac", "Flac") for i in range(1, 6)]
             + [_flac(f"b1t{i:02d}.flac", "24bit Flac") for i in range(1, 13)])
    kept, _, ordering = filter_files(files, FLAC)
    assert ordering["format"] == "24bit Flac"
    assert len(kept) == 12


def test_a_running_time_tie_is_broken_by_preference_order():
    """(pin) FORMAT_BY_AUDIO order breaks ties only."""
    files = ([_flac(f"a1t0{i}.flac", "Flac") for i in range(1, 6)]
             + [_flac(f"b1t0{i}.flac", "24bit Flac") for i in range(1, 6)])
    assert filter_files(files, FLAC)[2]["format"] == "Flac"
    assert filter_files(files, tuple(reversed(FLAC)))[2]["format"] == "24bit Flac"


def test_no_format_keeps_anything_falls_back_to_the_first_with_audio():
    """(pin) Unchanged fallback: when no format keeps a file, the first format
    with any audio is returned and `excluded` explains its files. A preferred
    format with no audio at all is skipped."""
    files = ([_flac(f"a1t0{i}.flac", "Flac", length=None) for i in range(1, 4)]
             + [_flac(f"b1t0{i}.flac", "24bit Flac", length=None) for i in range(1, 4)])
    kept, excluded, ordering = filter_files(files, FLAC)
    assert kept == []
    assert ordering["format"] == "Flac"
    assert _reasons(excluded) == {f"a1t0{i}.flac": ["missing duration"] for i in range(1, 4)}

    only_24 = [f for f in files if f["format"] == "24bit Flac"]
    kept, excluded, ordering = filter_files(only_24, FLAC)
    assert kept == [] and ordering["format"] == "24bit Flac"
    assert set(_reasons(excluded)) == {f"b1t0{i}.flac" for i in range(1, 4)}


def test_short_keep_false_keeps_the_first_non_empty_choice():
    """(pin) Orchestrator ruling: the legacy filter still picks the first
    format with a non-empty kept set, exactly as v2.17.0 does."""
    files = ([_flac(f"a1t0{i}.flac", "Flac") for i in range(1, 6)]
             + [_flac(f"b1t{i:02d}.flac", "24bit Flac") for i in range(1, 13)])
    kept, excluded, ordering = filter_files(files, FLAC, short_keep=False)
    assert ordering["format"] == "Flac"
    o_kept, o_excl, o_ord = _v2_17_0().filter_files(files, FLAC)
    ordering.pop("short_kept")
    assert (_names(kept), excluded, ordering) == (_names(o_kept), o_excl, o_ord)


# --- I-2: at most one derivative per original --------------------------------

def _doubled(n=7, *, short=(), titles=None, vbr_title=True, tracks=False):
    """An n-track tape whose every flac original has two VBR MP3 derivatives,
    `xNN.mp3` and `xNN_vbr.mp3` (the sci1999-12-31 / doubled-GD shape)."""
    titles = titles or {}
    files = []
    for i in range(1, n + 1):
        orig = f"x1t{i:02d}.flac"
        length = "30.0" if i in short else "300.0"
        files.append(_flac(orig, "Flac", length=length))
        t = titles.get(i)
        tr = str(i) if tracks else None
        files.append(_mp3(f"x1t{i:02d}.mp3", original=orig, length=length, title=t, track=tr))
        files.append(_mp3(f"x1t{i:02d}_vbr.mp3", original=orig, length=length,
                          title=t if vbr_title else None, track=tr))
    return files


def test_the_preference_is_the_plain_copy():
    """Operator ruling: the plain X.mp3 (measured: the newer re-derivation in
    2017/2017 cached pairs)."""
    assert junk.PREFER_VBR_DERIVATIVE is False
    assert junk.DUPLICATE_DERIVATIVE_REASON == DUP


def test_a_long_doubled_pair_keeps_the_plain_copy():
    kept, excluded, _ = filter_files(_doubled())
    assert _names(kept) == [f"x1t{i:02d}.mp3" for i in range(1, 8)]
    assert _reasons(excluded) == {f"x1t{i:02d}_vbr.mp3": [DUP]
                                  for i in range(1, 8)}
    e = next(e for e in excluded if e["filename"] == "x1t03_vbr.mp3")
    assert e == {"filename": "x1t03_vbr.mp3", "reasons": ["duplicate derivative"],
                 "duration_sec": 300.0}


def test_a_short_doubled_pair_keeps_one_copy_and_short_kept_names_it_only():
    """Both copies of a short tagged piece pass the short-keep rule; only the
    plain one is kept, and `ordering["short_kept"]` never names the dropped one."""
    kept, excluded, ordering = filter_files(_doubled(short=(4,), titles={4: "Drums"}))
    names = _names(kept)
    assert "x1t04.mp3" in names and "x1t04_vbr.mp3" not in names
    assert _reasons(excluded)["x1t04_vbr.mp3"] == [DUP]
    assert ordering["short_kept"] == ["x1t04.mp3"]
    assert len(names) == 7


def _tag_tape(doubled):
    """Seven tracks whose originals' tags (1,2,3,5,6,7,4) disagree with filename
    order; x1t07 is an untagged 30 s file, LAST by filename and track 4 by tag."""
    files = []
    for i, t in zip(range(1, 8), (1, 2, 3, 5, 6, 7, 4)):
        orig = f"x1t{i:02d}.flac"
        length = "30.0" if i == 7 else "300.0"
        files.append({**_flac(orig, "Flac", length=length), "track": str(t)})
        files.append(_mp3(f"x1t{i:02d}.mp3", original=orig, length=length))
        if doubled:
            files.append(_mp3(f"x1t{i:02d}_vbr.mp3", original=orig, length=length))
    return files


def test_the_derivative_dedupe_never_changes_play_order():
    """The dedupe only drops. The order is decided as if the dropped copies
    were still there: their shared track tags are not unique, so the doubled
    tape stays in filename order, as before the dedupe, and the short-keep
    rule's interior test (whose pool keeps both copies) reads that same order:
    x1t07 is the last file, an edge, and drops."""
    s_kept, _, s_ord = filter_files(_tag_tape(False))
    assert s_ord["order_source"] == "track-tags" and "x1t07.mp3" in _names(s_kept)

    kept, excluded, ordering = filter_files(_tag_tape(True))
    assert ordering["order_source"] == "filename" and ordering["reordered"] is False
    assert _names(kept) == [f"x1t{i:02d}.mp3" for i in range(1, 7)]
    assert _reasons(excluded)["x1t07.mp3"] == ["implausibly short"]
    assert ordering["short_kept"] == []
    assert {n for n, r in _reasons(excluded).items() if r == [DUP]} == {
        f"x1t{i:02d}_vbr.mp3" for i in range(1, 7)}


# The originals' `track` tags of jrad2023-05-12, copied from the raw cache entry:
# capture_fixture.py's slim shape drops `track`, and the stale tags are the point.
JRAD_TRACKS = {
    "01 Crowd.flac": "01", "02 Jam.flac": "02", "03 Here Comes Sunshine.flac": "03",
    "04 Foolish Heart.flac": "04", "05 Gonesville.flac": "05", "06 Mr Charlie.flac": "06",
    "07 Hey Bulldog.flac": "07", "08 Viola Lee Blues.flac": "08",
    "09 Dancin In The Streets .flac": "09", "10 Crowd.flac": "10", "11 Jam.flac": "11",
    "12 Terrapin Station.flac": "12", "12.5 The Other One.flac": "14",
    "14.5 Bird Song.flac": "13", "15 Lost Sailor.flac": "15",
    "16 Saint OF Curcumstance.flac": "16", "16.5 Morning Dew.flac": "18",
    "17 Casey Jones.flac": "17",
}


def test_jrad_stale_derivative_keeps_the_filename_order():
    """jrad2023-05-12 (real cache capture): the uploader renamed originals and
    their tags went stale (`12.5 The Other One` tagged 14, `14.5 Bird Song` 13,
    `16.5 Morning Dew` 18, after the encore `17 Casey Jones`), and a stale
    derivative `14 The Other One.mp3` of `12.5 The Other One.flac` survives.
    It is dropped as a duplicate; the order stays the (correct) filename order
    the duplicate tag forced before, never the stale tags' order. Measured
    (FW1 M2): the only library show the dedupe would otherwise reorder."""
    files = [{**f, "track": JRAD_TRACKS[f["name"]]} if f["name"] in JRAD_TRACKS else f
             for f in _load("jrad2023-05-12.json")]
    kept, excluded, ordering = filter_files(files)
    assert _names(kept) == [
        "02 Jam.mp3", "03 Here Comes Sunshine.mp3", "04 Foolish Heart.mp3",
        "05 Gonesville.mp3", "06 Mr Charlie.mp3", "07 Hey Bulldog.mp3",
        "08 Viola Lee Blues.mp3", "09 Dancin In The Streets .mp3", "11 Jam.mp3",
        "12 Terrapin Station.mp3", "12.5 The Other One.mp3", "13 Bird Song.mp3",
        "15 Lost Sailor.mp3", "16 Saint OF Curcumstance.mp3", "16.5 Morning Dew.mp3",
        "17 Casey Jones.mp3"]
    assert ordering["order_source"] == "filename" and ordering["reordered"] is False
    assert _reasons(excluded)["14 The Other One.mp3"] == [DUP]

    kept, _, ordering = filter_files(files, readmit=frozenset({"14 The Other One.mp3"}))
    assert "14 The Other One.mp3" in _names(kept)
    assert ordering["order_source"] == "filename"

    # Guard: without the stale derivative the same tags DO reorder the tape, so
    # the assertions above are not passing for want of live tags.
    single = [f for f in files if f["name"] != "14 The Other One.mp3"]
    kept, _, ordering = filter_files(single)
    assert ordering["order_source"] == "track-tags" and ordering["reordered"] is True
    assert _names(kept)[-1] == "16.5 Morning Dew.mp3"


def test_an_edge_short_untagged_pair_drops_like_the_single_copy():
    """(pin) Both copies of an untagged short first track sit at the edge."""
    kept, excluded, ordering = filter_files(_doubled(short=(1,)))
    assert _names(kept) == [f"x1t{i:02d}.mp3" for i in range(2, 8)]
    assert _reasons(excluded)["x1t01.mp3"] == ["implausibly short"]
    assert "x1t01_vbr.mp3" in _reasons(excluded)
    assert ordering["short_kept"] == []


def test_include_re_admits_a_dropped_duplicate():
    kept, excluded, ordering = filter_files(_doubled(), readmit=frozenset({"x1t03_vbr.mp3"}))
    assert "x1t03_vbr.mp3" in _names(kept) and "x1t03.mp3" in _names(kept)
    assert ordering["readmitted"] == ["x1t03_vbr.mp3"]
    assert "x1t03_vbr.mp3" not in _reasons(excluded)


def test_files_without_an_original_are_never_duplicates():
    """Two VBR MP3 ORIGINALS with the X / X_vbr names carry no `original`
    field and are both kept; only derivatives are grouped."""
    files = []
    for i in range(1, 6):
        files.append({"name": f"x1t{i:02d}.mp3", "format": "VBR MP3",
                      "source": "original", "length": "300.0"})
        files.append({"name": f"x1t{i:02d}_vbr.mp3", "format": "VBR MP3",
                      "source": "original", "length": "300.0"})
    kept, excluded, _ = filter_files(files)
    assert len(kept) == 10 and excluded == []


def test_short_keep_false_keeps_both_derivatives():
    """(pin) Orchestrator ruling: the legacy filter is v2.17.0's."""
    files = _doubled(short=(4,), titles={4: "Drums"})
    kept, excluded, ordering = filter_files(files, short_keep=False)
    assert "x1t03_vbr.mp3" in _names(kept)
    o_kept, o_excl, o_ord = _v2_17_0().filter_files(files, "VBR MP3")
    ordering.pop("short_kept")
    assert (_names(kept), excluded, ordering) == (_names(o_kept), o_excl, o_ord)
    fk = final_kept(files, Overrides(), ("VBR MP3",), short_keep=False)
    assert _names(fk.kept) == _names(o_kept)


# --- the stringcheeseincident-1999-12-31 shape (real cache capture) ----------

# The show's own overrides.json include/exclude lists, as the library holds them
# (copied here; the test reads no library path). The operator repaired the doubled
# delivery by excluding every long `_vbr` copy and re-admitting the short plain
# copies, plus the four post-show d4 tracks in both copies.
SCI_EXCLUDE = [
    *[f"sci1999-12-31d1/sci1999-12-31d1t{i:02d}_vbr.mp3" for i in range(1, 7)],
    *[f"sci1999-12-31d2/sci1999-12-31d2t{i:02d}_vbr.mp3" for i in (1, 3, 4, 5, 6)],
    *[f"sci1999-12-31d3/sci1999-12-31d3t{i:02d}_vbr.mp3" for i in (1, 2, 3, 4, 5, 8, 10)],
    *[f"sci1999-12-31d4/sci1999-12-31d4t{i:02d}_vbr.mp3" for i in range(1, 7)],
    *[f"sci1999-12-31d4/sci1999-12-31d4t{i:02d}.mp3" for i in range(3, 7)],
]
SCI_INCLUDE = [
    "sci1999-12-31d2/sci1999-12-31d2t02.mp3",
    *[f"sci1999-12-31d3/sci1999-12-31d3t{i:02d}.mp3" for i in (6, 7, 9, 11)],
]


def test_sci_hand_repaired_show_ships_each_song_once():
    """Final review I-2: the operator excluded every long `_vbr` copy; the
    short `_vbr` copies (Countdown, Mean Mr. Mustard, Polythene Pam, Golden
    Slumbers, The End) were dropped by the short arm then and are kept by the
    rule now. Each original ships once, and the four post-show d4 tracks the
    operator excluded in both copies stay out."""
    files = _load("sci1999-12-31.dsbd.shnf.json")
    fk = final_kept(files, Overrides(exclude=SCI_EXCLUDE, include=SCI_INCLUDE), ("VBR MP3",))
    names = _names(fk.kept)
    by_orig = Counter(f["original"] for f in fk.kept)
    assert max(by_orig.values()) == 1
    assert len(names) == 25
    assert not any(n.endswith("_vbr.mp3") for n in names)
    for i in (2,):
        assert f"sci1999-12-31d2/sci1999-12-31d2t{i:02d}.mp3" in names
    for i in (6, 7, 9, 11):
        assert f"sci1999-12-31d3/sci1999-12-31d3t{i:02d}.mp3" in names
    titles = [f.get("title") for f in fk.kept]
    for song in ("Countdown >", "Mean Mr. Mustard >", "Polythene Pam >",
                 "Gloden Slumbers >", "The End"):
        assert titles.count(song) == 1, song
    assert not any(n.startswith("sci1999-12-31d4/sci1999-12-31d4t0") and
                   n[-6:-4] in ("03", "04", "05", "06") for n in names)


def test_sci_unrepaired_ships_each_original_once():
    """The same item with no overrides: every one of its 29 originals ships
    once, as its plain copy."""
    files = _load("sci1999-12-31.dsbd.shnf.json")
    kept, excluded, _ = filter_files(files)
    assert len(kept) == 29
    assert Counter(f["original"] for f in kept).most_common(1)[0][1] == 1
    assert not any(n.endswith("_vbr.mp3") for n in _names(kept))
    assert sum(e["reasons"] == [DUP] for e in excluded) == 29
