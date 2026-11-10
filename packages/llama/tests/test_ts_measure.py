from datetime import date

import pytest

from llama.ts_measure import (
    NO_EVIDENCE_AGE_DAYS,
    catalogue_rates,
    parse_title_venue,
    percentile,
    rate,
    show_rate,
)

TODAY = date(2026, 11, 9)


def test_rate_none_under_75_days():
    assert NO_EVIDENCE_AGE_DAYS == 75
    assert rate(0, "2026-10-01", TODAY) is None
    assert rate(500, None, TODAY) is None
    assert rate(500, "garbage", TODAY) is None


def test_rate_boundary_74_vs_75():
    d75 = date.fromordinal(TODAY.toordinal() - 75).isoformat()
    d74 = date.fromordinal(TODAY.toordinal() - 74).isoformat()
    assert rate(150, d74, TODAY) is None
    assert rate(150, d75, TODAY) == 2.0


def test_rate_steady_and_formats():
    assert rate(100, "2026-01-09 14:03:11", TODAY) == pytest.approx(100 / 304)
    assert rate(100, "2026-01-09T14:03:11Z", TODAY) == pytest.approx(100 / 304)
    # evidence-bearing but downloads missing/None counts as zero downloads
    assert rate(None, "2026-01-09T14:03:11Z", TODAY) == 0.0
    # future addeddate: no evidence
    assert rate(5, "2027-01-01", TODAY) is None


def test_show_rate_takes_best():
    items = [
        {"identifier": "a", "downloads": 10, "addeddate": "2026-01-09"},
        {"identifier": "b", "downloads": 400, "addeddate": "2026-01-09"},
        {"identifier": "c", "downloads": 0, "addeddate": "2026-11-01"},
        {"identifier": "d", "downloads": 9, "addeddate": None},
    ]
    assert show_rate(items, TODAY) == pytest.approx(400 / 304)
    assert show_rate([items[2], items[3]], TODAY) is None
    assert show_rate([], TODAY) is None


def test_percentile_bounds():
    pop = [1.0, 2.0, 3.0, 4.0]
    assert percentile(1.0, pop) == 25.0
    assert percentile(1.0, pop) > 0
    assert percentile(4.0, pop) == 100.0
    assert percentile(2.5, pop) == 50.0


def test_percentile_empty_population_is_none():
    assert percentile(1.0, []) is None


def test_catalogue_rates_drops_nones():
    store = {
        "1997-11-22": [{"identifier": "a", "downloads": 304, "addeddate": "2026-01-09"}],
        "1998-01-01": [{"identifier": "b", "downloads": 0, "addeddate": "2026-11-01"}],
        "1999-01-01": [{"identifier": "c", "downloads": 3, "addeddate": None}],
    }
    assert catalogue_rates(store, TODAY) == [pytest.approx(1.0)]


def test_parse_title_venue_three_forms():
    assert parse_title_venue(
        "Phish - 1999-07-12 - Tweeter Center - Mansfield, MA"
    ) == ("Tweeter Center", "Mansfield, MA")
    assert parse_title_venue("Phish Live at The Centrum on 1993-12-30") == ("The Centrum", None)
    assert parse_title_venue("Phish 1977-05-08 @ Old Waldorf, SF") == ("Old Waldorf", "SF")
    assert parse_title_venue(
        "PHiSH 2009-08-08 @ The Gorge Amphitheatre - George, WA - Nakamichi CM700/CP702"
    ) == ("The Gorge Amphitheatre", "George, WA")
    assert parse_title_venue("Phish @ Old Waldorf, SF") == ("Old Waldorf", "SF")


@pytest.mark.parametrize("title", [
    "Phish 1997-11-22",
    "Phish - 1997-11-22",
    "Phish - 1997-11-22 - Set 1",
    "Jerry Garcia live at 1980-03-04",
    "Jerry Garcia Live on 1980-03-04",
    "Phish Live at on 1993-12-30",
    "Phish @ 1997-11-22",
    "",
])
def test_parse_title_venue_rejects(title):
    assert parse_title_venue(title) == (None, None)


def test_venue_never_a_date():
    v, c = parse_title_venue("Phish - 1999-07-12 - 1999-07-12 - Mansfield, MA")
    assert v is None


def test_live_at_splits_city():
    assert parse_title_venue(
        "Jerry Garcia live at Keystone, Berkeley, CA on 1974-01-17"
    ) == ("Keystone", "Berkeley, CA")


@pytest.mark.parametrize("title", [
    "Phish 1997-11-22 mk4 hv-32p @ 9624.fixed",
    "Phish 1997-11-22 Schoeps @ 24/96",
    "Phish 1997-11-22 Schoeps @ 2496",
])
def test_at_sign_rejects_bitrate(title):
    assert parse_title_venue(title) == (None, None)


@pytest.mark.parametrize("title", [
    "Phish - 1999-07-12 - Unknown Venue - Somewhere, NY",
    "Phish - 1999-07-12 - unknown Date & Location",
    "Phish - 1999-07-12 - Demo",
    "Phish Live at Demo Tape on 1999-07-12",
])
def test_placeholder_venues_are_none(title):
    assert parse_title_venue(title) == (None, None)


def test_city_trailing_format_tag_stripped():
    assert parse_title_venue(
        "Phish - 2018-10-20 - Hampton Coliseum - Hampton, VA[FLAC 24-48]"
    ) == ("Hampton Coliseum", "Hampton, VA")


def test_percentile_all_ties_is_100():
    assert percentile(5.0, [5.0, 5.0, 5.0]) == 100.0
