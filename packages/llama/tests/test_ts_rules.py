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
    ("Transfer: DAT (patch master)", "sbd"),
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
