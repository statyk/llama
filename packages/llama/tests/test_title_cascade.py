"""Title hygiene (piece 3), Task 11: the unwired builder `gather.title_inputs` and the
orchestrator `gather.title_cascade`.

`test_gather_threads_enabled_slices_to_the_cascade` was the in-suite form of the gate
probe's gate 0 (as `test_cascade_with_no_slices_equals_todays_gather`) until Task 16 wired
the cascade into `compute_gather`; it now pins the wiring (see its docstring). The other
tests place each slice where the spec puts it.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import llama.stages.gather as gather_mod
from llama.errors import LlamaError
from llama.junk import FORMAT_BY_AUDIO, filter_files
from llama.models import (Candidate, Overrides, ParsedSetlist, RecordingSummary, SetlistItem,
                          Track)
from llama.songs import normalize_song
from llama.stages.gather import (CanonicalBuild, build_canonical, compute_gather,
                                 gather_cleaner, title_cascade, title_inputs)
from llama.structure import fuzzy_norm_title
from llama.title_hygiene import ALL_SLICES
from llama.util import slugify
from llama.workspace import ShowWorkspace, read_overrides, write_artifact

from test_stage_gather import (FIXTURE, FURTHUR, F_IDENT, IDENT, REAL_TITLES, SIB_ID, T_IDENT,
                               W_IDENT, Y_IDENT, YMSB_FIXTURE, MultiIA, StubIA, _furthur_candidate,
                               _gd73_donor, _rre_joined, _tnd, _with_tagged_lossless,
                               _ymsb_candidate,
                               gd74_candidate, gd74_ia, make_candidate)

NONE = frozenset()
MP3 = FORMAT_BY_AUDIO["mp3"]


def _inputs_like_gather(sws: ShowWorkspace, ia, cand: Candidate, ident: str, *, build=None):
    """Only supplies `title_inputs`' arguments the way `compute_gather` computes them
    (jerrybase off, no providers, as the comparisons below call `compute_gather`). No
    field of the result is reconstructed here."""
    md = ia.metadata(ident)
    meta = md.get("metadata", {})
    artist = str(gather_mod._creator(meta) or cand.collection)
    events: list = []
    if build is None:
        def build(kept):
            return build_canonical(ia, cand, ident, meta, kept, artist, events,
                                   setlistfm=None, provider=None)
    return title_inputs(md, read_overrides(sws), ia=ia, candidate=cand, identifier=ident,
                        artist=artist, want=MP3, events=events, build=build,
                        slug=slugify(cand.performance_id))


def _today(sws: ShowWorkspace, ia, cand: Candidate, ident: str):
    """`compute_gather(..., enabled_slices=frozenset())`'s tracks just after 2a (before
    alignment), its operator notes up to that point, and the sibling-align notes, captured
    by wrapping `accept_short_tags` and `_sibling_transfer_full` (the note prefix is read
    from the caller's `op_notes`, which since Task 16 is the cascade's). Asserts that the
    wired `GatherResult.notes` begins with those notes, in order (Task 16 Step 3)."""
    cap: dict = {"sib": []}
    orig_short, orig_sib = gather_mod.accept_short_tags, gather_mod._sibling_transfer_full

    def short(tracks, *a, **kw):
        cap["prefix"] = list(sys._getframe(1).f_locals["op_notes"])
        out, notes = orig_short(tracks, *a, **kw)
        cap["tracks"], cap["short"] = out, list(notes)
        return out, notes

    def sib(*a, **kw):
        out, notes, donor = orig_sib(*a, **kw)
        cap["sib"] = list(notes)
        return out, notes, donor

    with patch.object(gather_mod, "accept_short_tags", short), \
            patch.object(gather_mod, "_sibling_transfer_full", sib):
        res = compute_gather(sws, ia, None, cand, ident, enabled_slices=NONE)
    notes = cap["prefix"] + cap["short"]
    assert res.notes[:len(notes)] == notes
    return cap["tracks"], notes, cap["sib"]


def _gd73_partly_blank():
    md = json.loads(FIXTURE.read_text())
    for f in md["files"]:
        if f["name"] in ("gd73-06-10d1t02.mp3", "gd73-06-10d2t01.mp3"):
            f["title"] = None
    return md


def _gd74_blank_ia():
    """Windsor with tracks 4-6 blanked: sibling-align's shape. Without D3_T02:
    since piece 4 keeps that 82 s `Weather Report Suite Part I >` (spec 1), the
    28-file tape count-matches its own description and the whole-tape S rung
    fills the blanks before sibling-align runs; the 27-file tape it was built
    on cannot."""
    ia = gd74_ia()
    ia.mapping[W_IDENT]["files"] = [f for f in ia.mapping[W_IDENT]["files"]
                                    if not f["name"].startswith("GD_022474_D3_T02.")]
    for f in ia.mapping[W_IDENT]["files"]:
        if f["name"].endswith(("D1_T04.mp3", "D1_T05.mp3", "D1_T06.mp3")):
            f["title"] = None
    return ia


def _rre(md=None):
    from test_stage_gather import R_IDENT, RRE
    md = md or json.loads(RRE.read_text())
    cand = Candidate(performance_id="RailroadEarth/2013-11-30", collection="RailroadEarth",
                     date="2013-11-30", venue="Sherman Theater", city="Stroudsburg, PA",
                     recordings=[RecordingSummary(identifier=R_IDENT)])
    return StubIA(md), cand, R_IDENT


def _gd73_gap():
    """Tracks 2-3 untagged and one canonical item more than the tape: no whole-tape S rung,
    so setlist-gap fills the bracketed run."""
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] += "\nSugar Magnolia"
    for f in md["files"]:
        if f["name"] in ("gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3"):
            f["title"] = None
    return md


def _furthur_without_short_tuning():
    """furthur-2012-07-15 without its `10.tuningup.*` files: the 19-file tape the filter
    kept before piece 4. Since piece 4 the mp3 copy (`tmp`, tagged under spec 2.2) is
    kept and its FLAC original (`Tuning Up`, junk under 2.3) is not, so 20 mp3s face 19
    FLACs; these C tests are about the 19-and-19 shape and build it explicitly."""
    md = json.loads(FURTHUR.read_text())
    md["files"] = [f for f in md["files"] if not f["name"].startswith("10.tuningup.")]
    return md


def _cases():
    tnd_ia, tnd_cand = _tnd(with_sibling=True)
    gd73_sib = _gd73_partly_blank()
    sib_ia = MultiIA({IDENT: gd73_sib, SIB_ID: _gd73_donor(json.loads(FIXTURE.read_text()),
                                                           REAL_TITLES)})
    sib_cand = make_candidate()
    sib_cand.recordings.append(RecordingSummary(identifier=SIB_ID))
    untagged = json.loads(FIXTURE.read_text())
    for f in untagged["files"]:
        f.pop("title", None)
    untagged_ia = MultiIA({IDENT: untagged, SIB_ID: _gd73_donor(json.loads(FIXTURE.read_text()),
                                                                REAL_TITLES)})
    return {
        "gd73": (StubIA(), make_candidate(), IDENT),
        "gd73-sibling": (sib_ia, sib_cand, IDENT),
        "gd73-gap": (StubIA(_gd73_gap()), make_candidate(), IDENT),
        "gd73-untagged-sibling": (untagged_ia, sib_cand, IDENT),
        "gd74": (gd74_ia(), gd74_candidate(), W_IDENT),
        "gd74-siblings": (_gd74_blank_ia(), gd74_candidate(), W_IDENT),
        "ymsb": (StubIA(json.loads(YMSB_FIXTURE.read_text())), _ymsb_candidate(), Y_IDENT),
        "lossless": (StubIA(_with_tagged_lossless(json.loads(FIXTURE.read_text()))),
                     make_candidate(), IDENT),
        "short-tags": (tnd_ia, tnd_cand, T_IDENT),
        "furthur": (StubIA(json.loads(FURTHUR.read_text())), _furthur_candidate(), F_IDENT),
        # The 19-file shape (no `10.tuningup.*`), where the format-sibling note fires: on
        # the captured item piece 4 keeps the mp3 copy (spec 2.2) but not the FLAC one
        # (2.3), and 20 mp3s against 19 FLACs file no note.
        "furthur-19": (StubIA(_furthur_without_short_tuning()), _furthur_candidate(), F_IDENT),
        "rre": _rre(),
        "rre-joined": _rre(_rre_joined()),
    }


@pytest.mark.parametrize("with_overrides", [False, True], ids=["as-is", "overrides"])
@pytest.mark.parametrize("case", list(_cases()))
def test_gather_threads_enabled_slices_to_the_cascade(tmp_path: Path, case, with_overrides):
    """Renamed from `test_cascade_with_no_slices_equals_todays_gather` (Task 16): before the
    wiring this compared the cascade with compute_gather's own copy of the title block (gate
    0). Task 16 deleted that copy, so the old name would claim a comparison that no longer
    exists. What it pins now: `compute_gather(enabled_slices=frozenset())` runs the cascade
    with no slices (tracks and notes equal a direct `title_cascade(enabled=frozenset())`),
    sibling-align's notes reach it, and `GatherResult.notes` begins with the cascade's
    op_notes in order (asserted in `_today`)."""
    ia, cand, ident = _cases()[case]
    sws = ShowWorkspace(tmp_path / "s")
    if with_overrides:
        kept, _, _ = filter_files(ia.metadata(ident)["files"], want_format=MP3)
        write_artifact(sws.overrides, Overrides(titles={kept[0]["name"]: "Operator Title",
                                                        kept[1]["name"]: "Second"},
                                                exclude=[kept[-1]["name"]]))
    tracks, notes, sib_notes = _today(sws, ia, cand, ident)
    out = title_cascade(_inputs_like_gather(sws, ia, cand, ident), enabled=NONE)
    assert [t.model_dump() for t in out.tracks] == [t.model_dump() for t in tracks]
    assert out.op_notes == notes
    assert out.struct_notes == sib_notes
    assert out.self_filled is False
    assert set(out.paths) <= {"", "S"}


def test_cascade_cases_are_not_vacuous(tmp_path: Path):
    """The comparison above exercises every rung it claims to: the S rung, setlist-gap,
    sibling-align, format recovery, 2a, 2b and 2c/2d all fire on some case."""
    seen: set[str] = set()
    notes: list[str] = []
    for case, (ia, cand, ident) in _cases().items():
        out = title_cascade(_inputs_like_gather(ShowWorkspace(tmp_path / case), ia, cand, ident),
                            enabled=NONE)
        seen |= {t.title_source for t in out.tracks}
        notes += out.op_notes + out.struct_notes
    assert {"tags", "setlist", "setlist-gap", "sibling-align", "sibling-format",
            "unresolved"} <= seen
    for prefix in ("placeholder tag title", "accepted short tag title", "format sibling tagged",
                   "stripped glued track number", "stripped joined track number",
                   "sibling alignment"):
        assert any(n.startswith(prefix) for n in notes), prefix


def test_cascade_out_of_range_override_raises_like_gather(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    # A title naming a file not in the track list (spec 4.1: the resolver's dangling
    # refusal, raised by `title_inputs` on both paths).
    write_artifact(sws.overrides, Overrides(titles={"gd73-06-10d9t09.mp3": "Nope"}))
    with pytest.raises(LlamaError) as today:
        compute_gather(sws, StubIA(), None, make_candidate(), IDENT)
    with pytest.raises(LlamaError) as cascade:
        title_cascade(_inputs_like_gather(sws, StubIA(), make_candidate(), IDENT), enabled=NONE)
    assert str(cascade.value) == str(today.value)


# --- gather_cleaner ------------------------------------------------------------------------

def _parsed(*titles: str) -> ParsedSetlist:
    return ParsedSetlist(items=[SetlistItem(title=t, normalized=normalize_song(t), set="1")
                                for t in titles], confidence="high")


def test_gather_cleaner_removed_indices():
    norms = {fuzzy_norm_title("RFK Stadium"), fuzzy_norm_title("Washington DC")}
    clean = gather_cleaner(norms, "Grateful Dead")
    # An artist item inside the banner span, and a footnote-marked title.
    cleaned, removed = clean(_parsed("RFK Stadium", "Grateful Dead", "Washington DC",
                                     "Morning Dew", "Grateful Dead", "Sugaree *"))
    assert removed == frozenset({0, 1, 2})
    assert [i.title for i in cleaned.items] == ["Morning Dew", "Grateful Dead", "Sugaree"]
    # An artist item right after the banner (the leading run) is removed and reported; the
    # mid-list one stays and is not; the footnote strip is a rewrite, never reported.
    cleaned, removed = clean(_parsed("RFK Stadium", "Washington DC", "Grateful Dead",
                                     "Morning Dew", "Grateful Dead", "Sugaree *"))
    assert removed == frozenset({0, 1, 2})
    assert [i.title for i in cleaned.items] == ["Morning Dew", "Grateful Dead", "Sugaree"]
    # Nothing to remove: nothing reported, even with a footnote rewrite.
    cleaned, removed = clean(_parsed("Morning Dew", "Sugaree *"))
    assert removed == frozenset() and [i.title for i in cleaned.items] == ["Morning Dew", "Sugaree"]


# --- Slice placement -----------------------------------------------------------------------

def test_gd73_chosen_canonical_s_fill_survives(tmp_path: Path):
    """The gd73 description has a segue line and no numbered lines: no admissible list, so
    S keeps its place under checks 1 and 2 (`gated`) and fills the encore."""
    out = title_cascade(_inputs_like_gather(ShowWorkspace(tmp_path / "s"), StubIA(),
                                            make_candidate(), IDENT), enabled=ALL_SLICES)
    assert (out.tracks[5].title, out.tracks[5].title_source) == ("Johnny B. Goode", "setlist")
    assert out.record.s_plan.mode == "gated"
    assert out.record.d is None
    assert out.paths == ("", "", "", "", "", "S")


def test_override_positions_are_not_s_positions(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.overrides, Overrides(titles={"gd73-06-10d3t01.mp3": "Forced Encore"}))
    out = title_cascade(_inputs_like_gather(sws, StubIA(), make_candidate(), IDENT),
                        enabled=ALL_SLICES)
    plan = out.record.s_plan
    assert 5 not in out.record.s_positions
    assert 5 not in plan.fills and 5 not in plan.declined and 5 not in plan.deferred
    assert (out.tracks[5].title, out.tracks[5].title_source) == ("Forced Encore", "override")
    assert out.paths[5] == ""


# A synthetic 8-track tape where each new rung fills one position (0-based):
#   0 Alpha (tag)  1 blank, lossless Bravo -> C1  2 Charlie (tag)  3 `J` -> slice 4
#   4 Echo (tag)   5 blank -> D (Foxtrot)          6 blank, entry `?` -> deferred S (Golf)
#   7 Hotel (tag)
# The canonical is a count-matched setlist.fm list, so S defers to after D. Its item 3 is
# `Jam`, so the cross-source vocabulary does not hold `j` and 2a stays out of slice 4's way.
SYN_ID = "tb1999-07-04.sbd.flac16"
SYN_TAGS = ["Alpha", "", "Charlie", "J", "Echo", "", "", "Hotel"]
SYN_LOSSLESS = ["Alpha", "Bravo", "Charlie", "J", "Echo", "", "", "Hotel"]
SYN_DESC = "1. Alpha\n2. Bravo\n3. Charlie\n4. J\n5. Echo\n6. Foxtrot\n7. ?\n8. Hotel"
SYN_CANON = ["Alpha", "Bravo", "Charlie", "Jam", "Echo", "Foxtrot", "Golf", "Hotel"]


def _syn_md(tags=SYN_TAGS, lossless=SYN_LOSSLESS, description=SYN_DESC, n=None):
    files = []
    for i in range(1, (n or len(tags)) + 1):
        stem = f"tb1999-07-04d1t{i:02d}"
        files.append({"name": f"{stem}.flac", "source": "original", "format": "Flac",
                      "length": "05:00", "md5": f"{i:032x}", "title": lossless[i - 1]})
        files.append({"name": f"{stem}.mp3", "source": "derivative", "original": f"{stem}.flac",
                      "format": "VBR MP3", "length": "05:00", "md5": f"{i + 100:032x}",
                      "title": tags[i - 1]})
    return {"metadata": {"identifier": SYN_ID, "creator": "Taper Band", "date": "1999-07-04",
                         "description": description}, "files": files, "reviews": []}


def _syn_candidate():
    return Candidate(performance_id="TaperBand/1999-07-04", collection="TaperBand",
                     date="1999-07-04", venue="The Hall", city="Somewhere, ST",
                     recordings=[RecordingSummary(identifier=SYN_ID)])


def _setlistfm_build(titles):
    canon = _parsed(*titles)
    return lambda kept: CanonicalBuild(setlist=canon, notes=[], source="setlist.fm")


def _syn(tmp_path, *, overrides=None, enabled=ALL_SLICES, md=None):
    sws = ShowWorkspace(tmp_path / "syn")
    if overrides is not None:
        write_artifact(sws.overrides, overrides)
    inp = _inputs_like_gather(sws, StubIA(md or _syn_md()), _syn_candidate(), SYN_ID,
                              build=_setlistfm_build(SYN_CANON))
    return title_cascade(inp, enabled=enabled)


def test_each_slice_runs_at_its_place(tmp_path: Path):
    out = _syn(tmp_path)
    assert out.paths == ("", "C1", "", "4", "", "D", "S-deferred", "")
    assert [(t.title, t.title_source) for t in out.tracks] == [
        ("Alpha", "tags"), ("Bravo", "sibling-format"), ("Charlie", "tags"), ("J", "tags"),
        ("Echo", "tags"), ("Foxtrot", "desc-position"), ("Golf", "setlist"), ("Hotel", "tags")]
    rec = out.record
    assert rec.s_plan.mode == "deferred" and rec.s_plan.declined == frozenset({3, 5, 6})
    # setlist-gap would fill [3] and [5, 6] from the same canonical; S's declines bind it.
    assert rec.gap_filled == ()
    assert rec.short4 == (3,) and rec.deferred_applied == (6,)
    assert rec.d is not None and rec.d.fills == {5: "Foxtrot"}
    assert rec.d.track_declines == {6: "slot placeholder"}
    assert out.op_notes[0] == "lossless title: track 2 '' -> 'Bravo' (C1)"
    assert "short tag title confirmed by the taper's list: track 4 'J'" in out.op_notes
    assert "positional fill declined: desc-position track 7 slot placeholder '?'" in out.op_notes
    assert out.self_filled is False


def test_s_declines_are_what_stop_setlist_gap(tmp_path: Path):
    """Control for the binding above: the cascade hands setlist-gap the plan's declined
    positions, and on the very tracks it saw, setlist-gap without them fills those runs."""
    seen: dict = {}
    orig = gather_mod.adopt_gap_titles

    def spy(tracks, canonical, **kw):
        seen["tracks"], seen["canonical"], seen["kw"] = tracks, canonical, kw
        return orig(tracks, canonical, **kw)

    with patch.object(gather_mod, "adopt_gap_titles", spy):
        _syn(tmp_path)
    assert seen["kw"]["declined"] == frozenset({3, 5, 6})
    free = dict(seen["kw"], declined=frozenset())
    unbound = orig(seen["tracks"], seen["canonical"], **free)
    assert [i for i, t in enumerate(unbound) if t.title_source == "setlist-gap"] == [3, 5, 6]


def test_d_reuses_the_sibling_donor(tmp_path: Path):
    """A wholly untagged tape with a tagged sibling: sibling-align runs (no anchors, so it
    adopts nothing) and D's sibling-duration check reads ITS donor; `best_donor` runs once."""
    base = json.loads(FIXTURE.read_text())
    chosen = {"metadata": dict(base["metadata"], description="\n".join(
        f"{i}. {t}" for i, t in enumerate(REAL_TITLES, 1))),
        "files": [dict(f) for f in base["files"]]}
    for f in chosen["files"]:
        f.pop("title", None)
    calls: list[int] = []
    orig = gather_mod.best_donor

    def counting(*a, **kw):
        calls.append(1)
        return orig(*a, **kw)

    for donor_titles, passes in ((REAL_TITLES, True), (REAL_TITLES[1:] + REAL_TITLES[:1], False)):
        calls.clear()
        ia = MultiIA({IDENT: chosen, SIB_ID: _gd73_donor(base, donor_titles)})
        cand = make_candidate()
        cand.recordings.append(RecordingSummary(identifier=SIB_ID))
        with patch.object(gather_mod, "best_donor", counting):
            out = title_cascade(_inputs_like_gather(ShowWorkspace(tmp_path / str(passes)), ia,
                                                    cand, IDENT), enabled=ALL_SLICES)
        assert len(calls) == 1
        rec = out.record
        assert rec.wholly_untagged and rec.fetch_siblings and rec.d is not None
        failed = [c for c, _ in rec.d.failed]
        if passes:
            assert failed == [] and out.paths == ("D",) * 6 and out.self_filled
            assert [t.title for t in out.tracks] == REAL_TITLES
        else:
            assert failed == ["sibling durations"]
            assert all(t.title_source == "unresolved" for t in out.tracks)


def test_donor_closures_return_none_without_durations(tmp_path: Path):
    """Review Focus 5: a target without per-file durations has no donor; neither closure
    raises."""
    base = json.loads(FIXTURE.read_text())
    sib = _gd73_donor(base, REAL_TITLES)
    ia = MultiIA({IDENT: base, SIB_ID: sib})
    cand = make_candidate()
    cand.recordings.append(RecordingSummary(identifier=SIB_ID))
    inp = _inputs_like_gather(ShowWorkspace(tmp_path / "s"), ia, cand, IDENT)
    tracks = [Track(index=i, set="1", title=f"t{i}.mp3", filename=f"t{i}.mp3",
                    title_source="unresolved") for i in range(1, 7)]
    assert all(t.duration_sec is None for t in tracks)
    assert inp.donor_check(tracks) is None
    out, notes, donor = inp.sibling_step(tracks)
    assert donor is None and [t.model_dump() for t in out] == [t.model_dump() for t in tracks]
    assert inp.donor_check([]) is None


def test_overrides_survive_every_new_rung_and_anchor_check_3(tmp_path: Path):
    """Review Focus 2. An override at a C position and at a D position keeps its title and
    source `override`: C neither changes nor notes it, D never fills it. As an independent
    title it anchors check 3 and slice 4's neighbour test: one disagreeing with its entry
    makes D fail `tape agreement` (and the deferred S decline with it) and slice 4 decline."""
    out = _syn(tmp_path, overrides=Overrides(titles={"tb1999-07-04d1t02.mp3": "Bravo",
                                                     "tb1999-07-04d1t06.mp3": "Foxtrot"}))
    t = out.tracks
    assert (t[1].title, t[1].title_source) == ("Bravo", "override")
    assert (t[5].title, t[5].title_source) == ("Foxtrot", "override")
    assert out.record.lossless.changed == {}
    assert not any(n.startswith("lossless title: track 2 ") for n in out.op_notes)
    assert out.paths[1] == "" and out.paths[5] == ""
    assert out.record.d is not None and out.record.d.failed == ()
    assert out.record.short4 == (3,)

    out = _syn(tmp_path, overrides=Overrides(titles={"tb1999-07-04d1t02.mp3": "Zulu",
                                                     "tb1999-07-04d1t06.mp3": "Foxtrot"}))
    t = out.tracks
    assert (t[1].title, t[1].title_source) == ("Zulu", "override")
    assert [c for c, _ in out.record.d.failed] == ["tape agreement"]
    assert out.record.short4_declined == {3: "neighbour disagrees"}
    assert t[6].title_source == "unresolved" and out.record.deferred_applied == ()
    assert "positional fill declined: setlist tape agreement (track 2 'Bravo')" in out.op_notes
    assert not any(n.startswith("lossless title: ") for n in out.op_notes)


def _furthur_19():
    """furthur-2012-07-15 with its description cut to the tape: the fixture's list has a
    second `Tuning Up` (20 entries) the 19 files lack, so it is no count-matched reference.
    (The 19 files: `_furthur_without_short_tuning`.)"""
    md = _furthur_without_short_tuning()
    desc = md["metadata"]["description"]
    md["metadata"]["description"] = desc.replace("2nd Set (93:46)\n\nTuning Up\n",
                                                 "2nd Set (93:46)\n\n")
    assert md["metadata"]["description"] != desc
    return md


def test_c_changed_stems_leave_2b_and_fetch_and_notes(tmp_path: Path):
    """furthur-2012-07-15: every mp3 is `tmp`, the FLAC copy is tagged. C fills all 19 (the
    count-matched list confirms each), so no 2b demotion note, no format-sibling note, and
    nothing left to fetch siblings for. Slice 3 off: today's 19 demotions, the note, and
    the fetch."""
    ia = StubIA(_furthur_19())
    inp = _inputs_like_gather(ShowWorkspace(tmp_path / "s"), ia, _furthur_candidate(), F_IDENT)
    assert inp.desc.used is not None and len(inp.desc.used.raws) == 19
    out = title_cascade(inp, enabled=ALL_SLICES)
    assert out.paths == ("C1",) * 19
    assert all(t.title_source == "sibling-format" for t in out.tracks)
    assert not any(n.startswith(("placeholder tag title", "format sibling tagged"))
                   for n in out.op_notes)
    assert sum(n.startswith("lossless title: ") for n in out.op_notes) == 19
    assert out.record.fetch_siblings is False
    off = title_cascade(inp, enabled=ALL_SLICES - {"slice3"})
    assert sum(n.startswith("placeholder tag title") for n in off.op_notes) == 19
    assert any(n.startswith("format sibling tagged") for n in off.op_notes)
    assert off.record.fetch_siblings is True


def test_c_declines_without_a_reference_and_2b_stands(tmp_path: Path):
    """The fixture's 20 list entries against 19 files and no consistent tags, so C1 is
    unconfirmed for the show; today's 2b demotions, note and fetch stand. (19 files: the
    item without `10.tuningup.*`, see `_furthur_without_short_tuning`.)"""
    ia = StubIA(_furthur_without_short_tuning())
    inp = _inputs_like_gather(ShowWorkspace(tmp_path / "s"), ia, _furthur_candidate(), F_IDENT)
    out = title_cascade(inp, enabled=ALL_SLICES)
    assert out.record.lossless.declined == "C1 unconfirmed" and out.record.lossless.changed == {}
    assert out.op_notes[0] == "lossless titles declined: C1 unconfirmed (track 1 'Tuning Up')"
    assert sum(n.startswith("placeholder tag title") for n in out.op_notes) == 19
    assert out.record.fetch_siblings is True


def test_wholly_untagged_evaluated_after_c(tmp_path: Path):
    """The furthur mp3 layer is all `tmp` (2b-demoted): wholly untagged before C. After C
    fills it from the lossless copy, it is not."""
    ia = StubIA(_furthur_19())
    inp = _inputs_like_gather(ShowWorkspace(tmp_path / "s"), ia, _furthur_candidate(), F_IDENT)
    assert title_cascade(inp, enabled=ALL_SLICES).record.wholly_untagged is False
    assert title_cascade(inp, enabled=ALL_SLICES - {"slice3"}).record.wholly_untagged is True


def test_exclusion_changes_the_count_d_sees(tmp_path: Path):
    """A 5-entry list against a 6-file tape is not count-matched; excluding the sixth file
    makes it so, and D fills the trailing blank that setlist-gap never fills."""
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = "\n".join(f"{i}. {t}" for i, t in enumerate(REAL_TITLES[:5], 1))
    for f in md["files"]:
        if f["name"] == "gd73-06-10d2t02.mp3":
            f["title"] = None
    out = title_cascade(_inputs_like_gather(ShowWorkspace(tmp_path / "a"), StubIA(md),
                                            make_candidate(), IDENT), enabled=ALL_SLICES)
    assert out.record.d is None and out.tracks[4].title_source == "unresolved"
    sws = ShowWorkspace(tmp_path / "b")
    write_artifact(sws.overrides, Overrides(exclude=["gd73-06-10d3t01.mp3"]))
    out = title_cascade(_inputs_like_gather(sws, StubIA(md), make_candidate(), IDENT),
                        enabled=ALL_SLICES)
    assert out.record.d is not None and out.record.d.fills == {4: "Eyes of the World"}
    assert (out.tracks[4].title, out.tracks[4].title_source) == ("Eyes of the World",
                                                                "desc-position")
    assert out.paths == ("", "", "", "", "D")


def _dso_2014_07_31():
    from test_lossless_titles import (DSO_2014_07_31_DESC, DSO_2014_07_31_ID,
                                      dso_2014_07_31_files)
    md = {"metadata": {"identifier": DSO_2014_07_31_ID, "creator": "Dark Star Orchestra",
                       "date": "2014-07-31", "description": DSO_2014_07_31_DESC},
          "files": dso_2014_07_31_files(), "reviews": []}
    cand = Candidate(performance_id="DarkStarOrchestra/2014-07-31",
                     collection="DarkStarOrchestra", date="2014-07-31",
                     venue="Gathering of the Vibes", city="Bridgeport, CT",
                     recordings=[RecordingSummary(identifier=DSO_2014_07_31_ID)])
    return StubIA(md), cand, DSO_2014_07_31_ID


_DSO_FLAC_4_20 = ["Dupree's Diamond Blues", "Black Throated Wind", "Cats Under The Stars",
                  "Cassidy", "Loser", "The Music Never Stopped",
                  "Bird Sing W/ Stanley Jordan-> OTher One-> Bird Song", "Tuning", "China Cat",
                  "Hey Pocky Way", "I Know You Rider", "Playin' In The Band", "Viola Lee Blues",
                  "Drumz/Space", "Alligator", "Uncle John's Band", "Playin' In The Band"]


def test_shifted_mp3_tag_set_darkstarorchestra_2014_07_31(tmp_path: Path):
    """Final review C-1, ruling 1: darkstarorchestra-2014-07-31's MP3 tags are shifted one
    early from track 3. Track 3 no longer ships `Duprees Diamond Blues` (the duplicate of
    track 4); the show is not cleared silently; tracks 4-20 keep the C2 corrections."""
    ia, cand, ident = _dso_2014_07_31()
    res = compute_gather(ShowWorkspace(tmp_path / "s"), ia, None, cand, ident)
    t = res.show.tracks
    assert fuzzy_norm_title(t[2].title) != fuzzy_norm_title("Duprees Diamond Blues")
    assert t[2].title_source in ("unresolved", "desc-position", "setlist")
    shipped_unconfirmed = [x for x in t if x.title_source == "tags"
                           and x.index not in (1, 2)]
    assert res.show.needs_review or res.show.review_flags or not shipped_unconfirmed
    assert [x.title for x in t[3:20]] == _DSO_FLAC_4_20
    assert all(x.title_source == "sibling-format" for x in t[3:20])
    assert res.title_paths[3:20] == ("C2",) * 17
    assert ("lossless titles: shifted delivered tag set; unconfirmed tags demoted: "
            "tracks 3") in res.notes
    # Today (slice 3 off) the tape ships as tagged, shifted throughout.
    off = compute_gather(ShowWorkspace(tmp_path / "off"), ia, None, cand, ident,
                         enabled_slices=ALL_SLICES - {"slice3"})
    assert off.show.tracks[2].title == "Duprees Diamond Blues"


def test_shifted_set_demotion_never_touches_an_override(tmp_path: Path):
    """Review Focus 2: an `overrides.titles` position is never demoted and never named in
    the note; with every demoted position overridden, there is no note."""
    ia, cand, ident = _dso_2014_07_31()
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.overrides, Overrides(titles={"dso2014-07-31d1t03.mp3":
                                                    "Greatest Story Ever Told"}))
    res = compute_gather(sws, ia, None, cand, ident)
    t = res.show.tracks
    assert (t[2].title, t[2].title_source) == ("Greatest Story Ever Told", "override")
    assert res.title_record.lossless.demoted == ()
    assert not any(n.startswith("lossless titles: shifted") for n in res.notes)
    assert [x.title for x in t[3:20]] == _DSO_FLAC_4_20


def test_cosmetic_strip_receives_the_show_artist(tmp_path: Path):
    """Ruling 5: compute_gather threads the show's artist into slice 5, so a leading
    `<artist> - ` strips (greenskybluegrass-2013-05-04's tag shape on the gd73 fixture)."""
    md = json.loads(FIXTURE.read_text())
    for f in md["files"]:
        if f["name"] == "gd73-06-10d1t01.mp3":
            f["title"] = "Grateful Dead - " + f["title"]
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(md), None, make_candidate(),
                         IDENT)
    assert res.show.tracks[0].title == "Morning Dew"
    assert ("cosmetic title strip: track 1 'Grateful Dead - Morning Dew' -> 'Morning Dew'"
            in res.notes)


def _shifted_list_show(mp3_titles, flac_titles, listed, *, ident="xyz2001-01-01.flac16"):
    """A synthetic one-set tape: `mp3_titles` on the MP3 derivatives, `flac_titles` (None =
    untitled) on the FLAC originals, and a count-matched numbered description `listed`."""
    desc = "Some Band\nJan 1 2001\n\n" + "\n".join(
        f"{i:02d} {t}" for i, t in enumerate(listed, 1))
    files = []
    for i, (mt, ft) in enumerate(zip(mp3_titles, flac_titles), 1):
        s = f"xyz2001-01-01t{i:02d}"
        flac = {"name": f"{s}.flac", "source": "original", "format": "Flac",
                "length": "400.0", "track": f"{i:02d}"}
        if ft is not None:
            flac["title"] = ft
        files += [flac, {"name": f"{s}.mp3", "source": "derivative", "format": "VBR MP3",
                         "length": "06:40", "title": mt, "original": f"{s}.flac",
                         "track": f"{i:02d}"}]
    md = {"metadata": {"identifier": ident, "creator": "Some Band", "date": "2001-01-01",
                       "description": desc}, "files": files, "reviews": []}
    cand = Candidate(performance_id="SomeBand/2001-01-01", collection="SomeBand",
                     date="2001-01-01", venue="Hall", city="Town, ST",
                     recordings=[RecordingSummary(identifier=ident)])
    return StubIA(md), cand, ident


_RIGHT_8 = ["Bertha", "Sugaree", "Deal", "Loser", "Jack Straw", "Stella Blue", "Big River",
            "Ripple"]


def test_shifted_reference_with_right_tags_demotes_nothing_c1_narrowing(tmp_path: Path):
    """Operator ruling (C-1 narrowing, fixwave-rr finding 1): all 8 MP3 tags are right; the
    FLAC is titled only on 1 and 8; the count-matched list is shifted over 2-6 (omits
    Sugaree, adds Mama Tried). The signature is symmetric, so with no C-confirmed signature
    position (C confirmed nothing) C-1 does not fire: no position is demoted and the
    shifted reference's titles never ship; the 8 right tags ship as tagged."""
    lst = ["Bertha", "Deal", "Loser", "Jack Straw", "Stella Blue", "Mama Tried", "Big River",
           "Ripple"]
    flac = [t if i in (0, 7) else None for i, t in enumerate(_RIGHT_8)]
    ia, cand, ident = _shifted_list_show(_RIGHT_8, flac, lst)
    res = compute_gather(ShowWorkspace(tmp_path / "s"), ia, None, cand, ident)
    assert [t.title for t in res.show.tracks] == _RIGHT_8
    assert not any(t.title_source == "setlist-gap" for t in res.show.tracks)
    assert res.title_record.lossless.demoted == ()
    assert not any(n.startswith("lossless titles: shifted") for n in res.notes)


def test_c1_demotion_note_loop_skips_demoted_glued_prefix_notes(tmp_path: Path):
    """fixwave-rr Minor 2: a position C-1 demoted no longer ships its tag, so notes.json
    carries no 'stripped glued track number' note for it (the shipped ones keep theirs)."""
    lst = ["Bertha", "Sugaree", "Deal", "Loser", "Jack Straw", "Stella Blue", "Ripple",
           "Brokedown Palace"]
    mp3 = ["01Bertha", "02Deal", "03Loser", "04Big River", "05Jack Straw", "06Stella Blue",
           "07Ripple", "08Brokedown Palace"]
    flac = ["Bertha", "Sugaree", "Deal", None, None, None, None, "Brokedown Palace"]
    ia, cand, ident = _shifted_list_show(mp3, flac, lst)
    res = compute_gather(ShowWorkspace(tmp_path / "s"), ia, None, cand, ident)
    assert res.title_record.lossless.demoted == (3,)
    assert res.show.tracks[3].title != "Big River"
    glued = [n for n in res.notes if n.startswith("stripped glued track number:")]
    assert glued and not any("track 4 " in n for n in glued)
