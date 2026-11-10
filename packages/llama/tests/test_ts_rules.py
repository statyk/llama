import json
from pathlib import Path

import pytest

from llama import ts_rules
from llama.config import TaperssectionArtist
from llama.models import RecordingSummary
from llama.scoring import lineage_class
from llama.ts_rules import (
    DECK_WORDS,
    MIC_WORDS,
    POSITION_WORDS,
    allowed,
    classify,
    date_disagrees,
    dates_claimed,
    excluded,
    in_active_window,
    source_lines,
)

FIXTURES = Path(__file__).parent / "fixtures"

CASES = [
    ("Source: Schoeps CMC6/MK4 > 744T", "aud"),
    ("Source: SBD > DAT", "sbd"),
    ("Source: FM->DAT->CD", "fm"),
    ("Location: OTS (right of SBD)\nSource: DPA 4061 > R-09", "aud"),
    ("Source: AKG 480 AUD Matrix", "aud"),
    ("Source: SBD/AUD matrix (Schoeps)", "matrix"),
    ("This show was webcast live\nSource: Neumann AK43 > LC3", "aud"),
    # Checkpoint A ruling (C): patch with no board context is not sbd (was "sbd")
    ("Transfer: DAT (patch master)", "unknown"),
    ("Source: DAT master", "unknown"),
]


def _entry(lineages, **kw):
    return TaperssectionArtist(name="Phish", creators=["Phish"], lineages=lineages, **kw)


@pytest.mark.parametrize("text,expected", CASES)
def test_acceptance_cases(text, expected):
    assert classify(RecordingSummary(identifier="x", description=text)) == expected


@pytest.mark.parametrize("text,expected", CASES)
def test_acceptance_cases_html(text, expected):
    html = "<br />".join(text.replace(">", "&gt;").split("\n"))
    assert classify(RecordingSummary(identifier="x", description=html)) == expected


def _fixture_rec(name):
    meta = json.loads((FIXTURES / f"{name}.json").read_text())["metadata"]
    return RecordingSummary(
        identifier=name, title=meta["title"], description=meta["description"], date=meta["date"]
    )


def test_primary_fixture_is_aud_via_source_line():
    rec = _fixture_rec("phish1997-12-29.003886.newyork.mk41.cmc6.flac1644")
    assert any(l.startswith("Source:") for l in source_lines(rec.description))
    # classify on description alone (identifier neutral) also reads aud
    assert classify(RecordingSummary(identifier="x", description=rec.description)) == "aud"
    assert classify(rec) == "aud"


def test_secondary_fixture_is_aud_via_identifier_token():
    rec = _fixture_rec("ph2017-07-30.139097.mk4.miller.flac2496")
    assert source_lines(rec.description) == []
    assert classify(RecordingSummary(identifier="x", title=rec.title, description=rec.description)) == "unknown"
    assert classify(rec) == "aud"


def test_source_lines_html():
    d = "Phish<br />1997<br>Source: A&gt; B<p>src: x</p><div>Lineage: y</div>Transfer: z<br/>Sourcery"
    assert source_lines(d) == ["Source: A> B", "src: x", "Lineage: y", "Transfer: z"]
    assert source_lines(None) == []


def test_tokens_do_not_match_inside_words():
    for ident in ("calfmaker", "audrey-sbdx", "smtxy"):
        assert classify(RecordingSummary(identifier=ident)) == "unknown"
    assert classify(RecordingSummary(identifier="gd77-05-08.sbd.hicks.flac16")) == "sbd"
    assert classify(RecordingSummary(identifier="a.fob.b")) == "aud"
    assert classify(RecordingSummary(identifier="a.mtx.b")) == "matrix"


def test_source_and_lineage_fields():
    assert classify(RecordingSummary(identifier="x", source="FM broadcast")) == "fm"
    assert classify(RecordingSummary(identifier="x", lineage="soundboard")) == "sbd"


def test_lexicons_disjoint_and_nonempty():
    assert MIC_WORDS and POSITION_WORDS and DECK_WORDS
    assert not (MIC_WORDS & DECK_WORDS) and not (POSITION_WORDS & DECK_WORDS)


def test_exclude_ignores_prose():
    e = _entry(["aud"], exclude=["livephish"])
    prose = RecordingSummary(identifier="x", description="available as a download from LivePhish")
    assert excluded(prose, e) is False
    assert excluded(RecordingSummary(identifier="x", title="Phish LivePhish 2"), e) is True
    assert excluded(RecordingSummary(identifier="x", description="Source: LivePhish"), e) is True
    assert excluded(RecordingSummary(identifier="x", source="livePhish"), e) is True
    assert excluded(RecordingSummary(identifier="a.LIVEPHISH.b"), e) is True
    assert excluded(prose, _entry(["aud"])) is False


def test_date_disagrees():
    r = lambda i, d, t="": RecordingSummary(identifier=i, date=d, title=t)
    assert date_disagrees(r("2024-08-30-phish-fob", "2024-08-01")) is True
    assert date_disagrees(r("2024-08-30-phish-fob", "2024-08-30")) is False
    assert date_disagrees(r("phish-fob-something", "2024-08-30")) is False
    assert date_disagrees(r("Phish2027-07-27", "2025-07-27")) is True


def test_dates_claimed_forms():
    assert dates_claimed("ph971229.sbd", "") == {"1997-12-29"}
    assert dates_claimed("phish1997-12-29.003886.mk41.flac1644", "") == {"1997-12-29"}
    assert dates_claimed("x", "Phish 2017.07.30") == {"2017-07-30"}
    assert dates_claimed("x", "Phish 7-30-2017 MSG") == {"2017-07-30"}
    assert dates_claimed("ph170730", "") == {"2017-07-30"}
    assert dates_claimed("ph491229", "") == {"2049-12-29"}
    assert dates_claimed("ph501229", "") == {"1950-12-29"}
    # conservative: no date from ordinary numbers
    assert dates_claimed("flac192000.139097", "") == set()
    assert dates_claimed("ph2017-07-30.139097.mk4.flac2496", "") == {"2017-07-30"}
    assert dates_claimed("ph991332", "") == set()  # impossible
    assert dates_claimed("x", "2017-13-45 and 13-45-2017") == set()
    assert dates_claimed("123456", "") == set()  # no artist prefix


def test_in_active_window():
    e = _entry(["aud"], active_from="1990-01-01", active_until="2000-12-31")
    assert in_active_window("1990-01-01", e) and in_active_window("2000-12-31", e)
    assert not in_active_window("1989-12-31", e) and not in_active_window("2001-01-01", e)
    assert in_active_window("1850-01-01", _entry(["aud"]))


def test_allowed_rules():
    aud = RecordingSummary(identifier="a.fob.b")
    sbd = RecordingSummary(identifier="a.sbd.b")
    unk = RecordingSummary(identifier="a.b")
    e = _entry(["aud"])
    assert allowed(aud, e, rule="a") == "allowed"
    assert allowed(sbd, e, rule="a") == "forbidden"
    assert allowed(unk, e, rule="a") == "unknown"
    assert allowed(unk, e, rule="b") == "allowed"
    e2 = _entry(["sbd"])
    assert allowed(unk, e2, rule="a") == "unknown"
    assert allowed(unk, e2, rule="b") == "forbidden"
    e3 = _entry(["aud", "sbd", "matrix", "fm", "webcast"])
    for rule in ("a", "b"):
        for r in (aud, sbd, unk):
            assert allowed(r, e3, rule=rule) == "allowed"


def test_rule_constant():
    assert ts_rules.RULE == "a"


def test_lma_lineage_class_unchanged():
    assert lineage_class("gd77-05-08.sbd.hicks.4047.sbeok.shnf", {}) == "sbd"
    assert lineage_class("gd77-05-08.aud.vernon.1234.flac16", {}) == "aud"
    assert lineage_class("gd77-05-08.flac16", {}) == "unknown"


def _cls(**kw):
    return classify(RecordingSummary(**{"identifier": "x", **kw}))


def test_taper_credit_is_not_a_position():
    assert _cls(description="Source: DAT master (taper: Bob Smith)") == "unknown"
    assert _cls(description="Source: DAT master (tapers: A and B)") == "unknown"
    assert _cls(description="Source: taper section, DAT master") == "aud"
    assert _cls(description="Source: Tapers Section > DAT") == "aud"


def test_numeric_mic_models_not_from_identifier():
    assert classify(RecordingSummary(identifier="ph1994-06-22.4061.flac16")) == "unknown"
    assert _cls(description="Source: DPA 4061 > R-09") == "aud"
    assert _cls(title="B&K 4011 recording") == "aud"
    assert _cls(source="B&K 4011") == "aud"
    # alphanumeric models still count in the identifier
    assert classify(RecordingSummary(identifier="ph1994-06-22.km140.flac16")) == "aud"


def test_nakamichi_mics():
    assert _cls(description="Source: Nakamichi CM100 > cassette") == "aud"
    assert _cls(description="Source: CM300 > DAT") == "aud"
    assert _cls(description="Source: CM-700 > DAT") == "aud"
    assert _cls(description="Source: cm 5 > DAT") == "unknown"


def test_date_disagrees_without_rec_date_fails_closed():
    # No rec.date but the identifier claims one: counts as disagreeing (Task 5 drops it).
    assert date_disagrees(RecordingSummary(identifier="phish1997-12-29.x", date=None)) is True


def test_more_date_forms():
    assert dates_claimed("ph97-12-29", "") == {"1997-12-29"}
    assert dates_claimed("ph17.07.30.x", "") == {"2017-07-30"}
    assert dates_claimed("ph19971229", "") == {"1997-12-29"}
    assert dates_claimed("ph20170730", "") == {"2017-07-30"}
    assert dates_claimed("ph97-13-29", "") == set()
    assert dates_claimed("ph19971329", "") == set()
    assert dates_claimed("ph20170231", "") == set()


def test_yymmdd_prefix_restricted():
    for ident in ("shnid120101", "etree120101", "x.shnid120101.flac", "flac120101"):
        assert dates_claimed(ident, "") == set()
    assert dates_claimed("shnid97-12-29", "") == set()
    assert dates_claimed("ph971229", "") == {"1997-12-29"}


def test_possessive_taper_section():
    assert _cls(description="Source: Taper's Section > DAT") == "aud"
    assert _cls(description="Source: Taper’s Section") == "aud"
    assert _cls(description="Source: Tapers' Section") == "aud"
    assert _cls(title="Phish live, Taper's Section") == "aud"
    assert _cls(description="Source: DAT master (taper: Bob)") == "unknown"


# --- Task 2b: the operator's Checkpoint A ruling --------------------------------
# Real texts below are quoted from the hand-labelled 50-date sample
# (docs/superpowers/2026-11-09-taperssection-evidence/lineage.md, lineage-labels.csv),
# as the archive.org scrape serves them: one line, tags and breaks collapsed.


def test_rule_is_operator_ruling():
    # Operator ruling, Checkpoint A, 2026-11-09 (~11:18 EST): "all as recommended";
    # (A) rule (a): a still-unknown tape holds.
    assert ts_rules.RULE == "a"


# phish1992-05-02.131528.chicago.rsm191.flac1648
D_131528 = (
    "PHISH Cabaret Metro Chicago, Illinois May 2, 1992 Source:  (FOB/150deg/m/s) Neumann RSM-191AS "
    "&gt; MTX-191A &gt; Sony TCD-D3 &gt; DAT(m) Transfer:  DAT(m) &gt; Sony PCM-R500 &gt; SPDIF &gt; "
    "Tascam HD-P2 &gt; CDWave &gt; FLAC  (16/48) DAT(m) provided by Bryon Sosinski Transfer by Terry "
    "Watts Set I: 1. Jim 2. Forbin &gt; 3. Icculus &gt; 4. Mockingbird 5. Sparkle 6. Reba 7. Maze"
)

# phish1996-11-22.176530.spokane.akg414.at4031.wright.flac1648 (Transfer runs into the setlist)
D_176530 = (
    "Phish 11/22/1996 Spokane Arena - Spokane, WA Source: AKG 414/AT 4031 Matrix Transfer: Tascam "
    "DA-20 MKII &gt; Tascam DR-680 &gt; Audacity &gt; WAV &gt; xACT &gt; FLAC Taped (almost certainly) "
    "by Don Wright Transferred & Seeded by Bill Graves ~ Set 1 ~ 1. It's Ice 2. Runaway Jim 3. "
    "Wolfman's Brother 4. Taste 5. Ginseng Sullivan 6. Sample in a Jar"
)

# phish1994-05-28.089594.monterey.mk4.byron.flac1644: a Schoeps master with an SBD splice
# (labelled aud: an aud master with an SBD patch is aud). The second "source:" is a fill.
D_089594 = (
    "Phish May 28, 1994 Laguna Seca Raceway Monterey, CA source: Schoeps mk4 &gt; kc5 &gt; cmc5 &gt; "
    "Sonosax SX-M2 &gt; Sony TCD-D10 pro II (@ 48 kHz) transfer: Tascam DA-20MKII &gt; Tascam HD-P2 "
    "&gt; CF card &gt; usb 2.0 &gt; pc &gt; WaveLab 5.01b (fades, splice) &gt; r8brain v1.9 (resample "
    "to 44.1 kHz) &gt; CD Wave v1.96.1 &gt; FLAC v1.2.1 (Level 8) FLAC tags added with metaflac v1.2.1 "
    "recorded by Eliot Byron transferred by Jason Sobel (jasonsobel@gmail.com) seeded January 21, 2008 "
    "notes: The original 48 kHz .wav files from the DAT transfer have been archived. Disc 1 - [62:29] "
    "Set I 01 - [06:11] - Rift &gt; 02 - [04:52] - Sample in a Jar splice notes: The beginning of "
    "\"Rift\" was missing from Eliot's DAT. I spliced in the missing portion with the following "
    "source: SBD &gt; DAT http://db.etree.org/shn/8751 The SBD source was used for the following "
    "portion of Rift: [00:00] to [01:00]"
)

# phish1994-05-28.133678.monterey.mtx.flac1644: a true 2-source SBD + AUD matrix
D_133678 = (
    "Phish 1994/05/28 Laguna Seca Raceway - Monterey, CA 2-Source Matrix Matrixed using Audacity "
    "v2.0.3 by Steve M. *****Source 1***** shnid=8751 Source: SBD &gt; DAT Conversion: DAP1 @48khz "
    "&gt; COAX ~50% of the matrix *****Source 2***** shnid=89594 Source: Schoeps mk4 &gt; kc5 &gt; "
    "cmc5 &gt; Sonosax SX-M2 &gt; Sony TCD-D10 pro II (@ 48 kHz) Transfer: Tascam DA-20MKII"
)


def test_inline_labels_split_collapsed_text():
    assert source_lines(D_131528) == [
        "Source: (FOB/150deg/m/s) Neumann RSM-191AS > MTX-191A > Sony TCD-D3 > DAT(m)",
        "Transfer: DAT(m) > Sony PCM-R500 > SPDIF > Tascam HD-P2 > CDWave > FLAC (16/48) DAT(m) "
        "provided by Bryon Sosinski Transfer by Terry Watts",
    ]


def test_inline_label_forms():
    d = "Phish 1997 Src: Schoeps Sources: DPA Source info: AKG Transfers: DAT Lineage: CD"
    assert source_lines(d) == ["Src: Schoeps", "Sources: DPA", "Source info: AKG",
                               "Transfers: DAT", "Lineage: CD"]
    # word-anchored: a credit or a word containing a label is not one
    assert source_lines("Transferred by: Bob. Resource: none") == []


def test_inline_segment_stops_before_setlist_overrun():
    # lineage.md lexicon-error item 5: the Transfer segment ran into the setlist
    segs = source_lines(D_176530)
    assert segs[0] == "Source: AKG 414/AT 4031 Matrix"
    assert segs[1].startswith("Transfer: Tascam DA-20 MKII > Tascam DR-680")
    assert "It's Ice" not in segs[1] and "Set 1" not in segs[1]


def test_inline_segment_is_capped():
    segs = source_lines("Phish Source: " + "Schoeps " * 100)
    assert segs and len(segs[0]) <= 220


def test_fill_source_is_not_a_source_line():
    # lineage.md item 5: "the following source: SBD > DAT" is a splice fill, not the tape
    assert all("SBD" not in s for s in source_lines(D_089594))
    assert _cls(description=D_089594) == "aud"


def test_line_based_reading_unchanged_with_breaks():
    d = "Phish<br />Source: SBD > DAT the following source: AKG<br />Set 1: Ghost"
    assert source_lines(d) == ["Source: SBD > DAT the following source: AKG"]


# (C) patch / patched reads sbd only with board context
def test_patch_without_board_context_is_not_sbd():
    # phish2003-07-21.109173.noblesville.u89i.markham.sobel.flac1644
    assert _cls(description="Phish Source: Neumann u89i (hyper / 80 degrees) &gt; Apogee MiniMe "
                "transfer: Tascam DA-20mkII &gt; pc &gt; Samplitude SE v9.1.1 (patch, fades) &gt; "
                "r8brain PRO v1.5") == "aud"
    assert _cls(description="Phish transfer: Samplitude SE v9.1.1 (patch, fades) &gt; CD Wave") == "unknown"
    # phish1994-06-11.133981.morrison.tlm170i.flac1648
    assert _cls(description="Phish Transfer:  DAT(m) &gt; Sony PCM-R500 &gt; FLAC (16/48) Source by "
                "Doug Oade Patch DAT(m) provided by Bill Shaw") == "unknown"
    assert _cls(description="PHISH Red Rocks Source:    (omni/10' split) Neumann TLM-170i's &gt; Oade "
                "&gt; DAT(m) Transfer:  DAT(m) &gt; Sony PCM-R500 Source by Doug Oade Patch DAT(m) "
                "provided by Bill Shaw") == "aud"
    # phish1994-04-08.006044.statecollege.rsm190.flac1644
    assert _cls(description="Phish Transfer: My patch master dat from sony d-7&gt;Sony DTC-690") == "unknown"
    # phish1996-11-07.075699.lexington.mg300.mahan.flac1644
    assert _cls(description="PHiSH source: Microtech Gefell m300 &gt; Aerco Preamp transfer: Fostex "
                "D5 &gt; FLAC transfer/patch by Jordan Braunstein") == "aud"


def test_patch_with_board_context_is_sbd():
    assert _cls(description="Source: console patch > DAT") == "sbd"
    assert _cls(description="Source: patch from the soundboard > DAT") == "sbd"


# (C) board / SBD after a position word is a position, not a source
def test_board_as_position():
    # phish2024-07-19.168122.mansfield.mk41.flaschner.flac2448
    assert _cls(description="PHISH July 19, 2024 Source: Schoeps mk41&gt;kc5&gt;cmc6&gt;Mix3ii@ 24/96 "
                "(Dead center behind soundboard Sec6 Row e Seat 18) Recorded by: Dave Flaschner") == "aud"
    # phish1991-07-20.005751.parksville.akg451.flac1644
    assert _cls(description="phish @-arrowhead ranch, parksville,ny-91-07-20, /d1-d2./ "
                "source:akg 451+ck8a in sbd b00th, by kevin shapiro.... seeded: by mikey k") == "aud"
    # phish2009-12-05.103187.charlottesville.km140.evans.flac2496
    assert _cls(description="Phish Source: Neumann ak40's(nos)&gt;lc3&gt;km100&gt;722&gt;@24/96 (ots "
                "left back corner of sbd boomed over 8 inches inside sbd rail) Transfer: 722") == "aud"
    # corpus forms quoted in lineage.md item 2
    assert _cls(description="Phish Source: B&K 4011>SV255 at sbd") == "aud"
    assert _cls(description="Phish Source: aud/48khz-rec. center @sbd-7 1/2 ft height; AKG460b") == "aud"
    assert _cls(description="Phish Source: DPA 4018A(22cm-80deg/DFC/Behind SBD@12')") == "aud"
    assert _cls(description="Phish Source: Neumann TLM-170 (hypercards, 20' in front of the board)") == "aud"
    assert _cls(description="Phish Source: Schoeps 20 ft behind the board, right of SBD") == "aud"
    # a position alone is not a source: no sbd, and no mic so not aud either
    assert _cls(description="Phish Source: DAT master (behind the board)") == "unknown"
    # a real board still reads sbd
    assert _cls(description="Phish Source: SBD > DAT") == "sbd"
    assert _cls(description="Phish Source: Unknown Soundboard > Cass") == "sbd"


# (C) matrix only when board + audience are both indicated
def test_aud_rig_matrix_reads_aud():
    # phish1994-04-08.132135.universitypark.rsm190i.flac1648 (Neumann M/S box)
    assert _cls(description="PHISH Source:  Neumann RSM-191i &gt; Neumann MTX-191 &gt; Teac DAP-20 "
                "&gt; DAT(c) Transfer:  DAT(c)") == "aud"
    assert _cls(description=D_131528) == "aud"
    # phish1996-11-22.176530 (two audience rigs mixed)
    assert _cls(description=D_176530) == "aud"
    # ph-2024-07-30AKGmatrix (AKG ck63 + ck61), and corpus DPAmatrix / dhAUDmatrix identifiers
    assert classify(RecordingSummary(identifier="ph-2024-07-30AKGmatrix")) == "aud"
    assert classify(RecordingSummary(identifier="PH2025-09-16.DPAmatrix")) == "aud"
    assert classify(RecordingSummary(identifier="ph1997-02-26.Stuttgart.Germany.dhAUDmatrix.Dec2024.flac16441")) == "aud"


def test_board_plus_audience_matrix_stays_matrix():
    # the real identifier carries the mtx; the description's source segments name SBD and Schoeps
    assert classify(RecordingSummary(identifier="phish1994-05-28.133678.monterey.mtx.flac1644",
                                     description=D_133678)) == "matrix"
    assert _cls(description="Source: SBD/AUD matrix (Schoeps)") == "matrix"
    assert classify(RecordingSummary(identifier="a.mtx.b")) == "matrix"


# (C) broadcast words read fm (labelling convention: broadcast = fm)
def test_broadcast_words_read_fm():
    # phish1998-10-03.000770.tinleypark.broadcast.flac1644
    assert _cls(description="Phish 1998-10-03 Farm Aid Source: CMT DSS Broadcast &gt; Tbfiji &gt; "
                "Soundforge &gt; CD flac'd 2026-08-25 s1t01 - Birds of a Feather") == "fm"
    # phish1998-10-03.015186.tinleypark.sbd.flac1644 ("DishNetwork> Tbfiji> Soundforge>")
    assert _cls(source="DishNetwork> Tbfiji> Soundforge>") == "fm"
    assert _cls(source="Dish Network > DAT") == "fm"
    assert _cls(source="satellite feed > DAT") == "fm"


# Corpus-review pins (lineage.md "What Task 2b changed"): cases the sample lacked.
def test_dsbd_and_band_source_indicate_a_board():
    # phish1992-12-31.000500.boston.mtx.flac1644: a board + audience matrix, not aud
    assert _cls(description="Phish Source Info: Matrix(DSBD+Elektra AUD) DAT>CD") == "matrix"
    assert _cls(description="Phish SOURCE: DSBD > DAT > Protools > CD") == "sbd"
    # phish2000-06-15.098243.osaka.akgc1000.flac1644
    assert _cls(description="Phish Source info: Band Source AKG C1000s > ? (direct from Phish's "
                "mic source) It also could a matrix that's mostly AUD") == "matrix"


def test_weak_broadcast_words_need_no_audience_evidence():
    # phish1997-12-31.165734.newyork.mk41.flac1648 (DSS is a chain component here)
    assert _cls(description="Phish Source: Schoeps MK41 &gt; DSS &gt; Tascam DA-P1 &gt; Sony TCD-D7") == "aud"
    # phish2003-11-29.020756.philadelphia.at4051.clark.flac1644 (a Toshiba Satellite laptop)
    assert _cls(description="Phish Source: AT4051a -&gt; V2 -&gt; AD500e -&gt; D100 Mic Transfer: D100 "
                "-&gt; UA-5 -&gt; Toshiba Satellite 1135 -&gt; Soundforge 6.0") == "aud"
    # phish2000-10-03.007655.burbank.sat.flac1644
    assert _cls(description="Phish SOURCE: NBC Ku-band satellite feed &gt; DAT &gt; CDR") == "fm"


def test_per_set_source_annotations_do_not_end_a_segment():
    # phish2009-11-01.102339.indio.akg460.jbanyai.flac1644
    assert _cls(description="Phish Indio, CA 2009-11-01 Source: (Set 1) AKG c460b|a60m|ck3 &gt; Segue "
                "Dogstar XLRs &gt; Fostex FR-2LE (24bit/48khz) Transfer: CF Card") == "aud"
    # phish2024-12-29.169559.newyork.dpa4018.kutik.flac2448 ("(Set1: OTS ...)" mid-chain)
    assert _cls(description="PHISH Source: DPA4018 (Set1: OTS / 16\" LOC / 9' up)(Set2: DFC / 11' up) "
                "&gt; Edirol R4Pro (Oade preamp mod) @ 24/96 Recorded by Mike Kutik") == "aud"
    # phish1998-12-30.084945.newyork.mk4v.teddy.crow.flac1644
    assert source_lines("Phish source: set 1 = (FOB) Schoeps mk4v &gt; kcy transfer: DA-20")[0] == (
        "source: set 1 = (FOB) Schoeps mk4v > kcy")
    # phish2022-07-20.157402 ("(Source 1) Schoeps MK4v's ...") is not a numbered setlist
    assert "Schoeps" in source_lines("Phish Source: 32bit Float/48 (Source 1) Schoeps MK4v's &gt; "
                                     "Nbob Actives Location: TS")[0]


# Task 2b review fix round 1.
def test_band_mic_source_is_a_feed_not_aud():
    # phish2000-06-14.004147.fukuoka.akg1000.flac1644: siblings call the same chain
    # "DSBD+AUD Matrix Mix ... band source"; with "could [be] a matrix" it reads matrix.
    assert _cls(description="Phish Source info: AKG C1000s > DAT (direct from Phish's mic source) "
                "It also could a matrix that's mostly AUD also DAT") == "matrix"
    # phish2000-06-15.028257.osaka.mtx.flac1644, the second chain alone: a band feed
    assert _cls(description="Phish source: AKG C1000's > DAT(direct from Phish's mic source) from "
                "Billy Rickards 03/11/01") == "sbd"


def test_by_sbd_is_a_position_and_light_board_is_not_a_board():
    # Phish2022-08-05.AKGCK63.Flac24 / phish2022-08-05.157559
    assert _cls(source="AKG CK63 > ZOOM F3 Mic's were setup front right corner by SBD, 12 Feet High") == "aud"
    # phish2021-10-29.163512.lasvegas.ak40.waltmon.flac2448
    assert _cls(description="Phish Source: Neumann AK40 (110°/ ORTF / 8ft up / Front Left corner of "
                "light board) > Sound Devices MP10II @ 32/48 Recorded") == "aud"
    assert _cls(description="Phish Source: DAT (lighting board) > CD") == "unknown"


def test_x_stream_cable_is_not_a_webcast():
    # phish2003-07-31.019820.camden.ck61.akg480.watts.flac1644
    assert _cls(description="Phish Source: (DIN, OTS) AKG 481>Audio Magic X-Stream >DMIC20>D8 (48k)") == "aud"
    # phish1999-12-13.000922.providence.sr77.vernal.flac1644
    assert _cls(description="Phish Source Info: Earthworks SR-77 > audiomagic X-stream XLR > Lunatec V2") == "aud"
    assert _cls(description="Phish Source: webcast stream > WAV") == "webcast"
