from llama.util import length_seconds, slugify


def test_slugify():
    assert slugify("GratefulDead/1973-06-10") == "gratefuldead-1973-06-10"
    assert slugify("  RFK Stadium!! ") == "rfk-stadium"
    assert slugify("***") == "unknown"


def test_length_seconds():
    assert length_seconds("07:32") == 452.0
    assert length_seconds("1:02:03") == 3723.0
    assert length_seconds("452.5") == 452.5
    assert length_seconds(None) is None
    assert length_seconds("n/a") is None


def test_reviews_digest_formats_caps_and_handles_empty():
    from llama.util import reviews_digest

    reviews = [{"reviewtitle": "Wow", "reviewbody": "x" * 900},
               {"reviewbody": "no title here"}]
    out = reviews_digest(reviews)
    lines = out.splitlines()
    assert lines[0].startswith("- Wow: ") and len(lines[0]) <= 800 + len("- Wow: ")
    assert lines[1] == "- no title here"
    assert reviews_digest([]) == "(no reviews)"
    assert len(reviews_digest([{"reviewbody": str(i)} for i in range(9)]).splitlines()) == 5


def test_spread_across_years_round_robins_by_year():
    from llama.util import spread_across_years

    items = [("a", "1977-05-08"), ("b", "1977-05-09"),
             ("c", "1969-12-07"), ("d", "1972-08-27")]  # preference order
    date_of = lambda it: it[1]
    # one per year first, cycling years in order of their best item
    assert spread_across_years(items, date_of, 3) == [
        ("a", "1977-05-08"), ("c", "1969-12-07"), ("d", "1972-08-27")]
    # then each year's second-best
    assert spread_across_years(items, date_of, 4) == [
        ("a", "1977-05-08"), ("c", "1969-12-07"), ("d", "1972-08-27"), ("b", "1977-05-09")]


def test_spread_across_years_single_year_is_plain_top_n():
    from llama.util import spread_across_years

    items = [("a", "1977-05-08"), ("b", "1977-05-09"), ("c", "1977-06-07")]
    assert spread_across_years(items, lambda it: it[1], 2) == items[:2]
    assert spread_across_years(items, lambda it: it[1], 9) == items


def test_spread_across_artists_round_robins_artists():
    from llama.util import spread_across_artists

    # preference order: CharlieHunter dominates the top of the list
    items = [("h1", "CharlieHunter", "2002-07-05"), ("h2", "CharlieHunter", "2000-08-23"),
             ("h3", "CharlieHunter", "2001-12-08"), ("g1", "GarageATrois", "1998-04-25"),
             ("s1", "SnarkyPuppy", "2014-03-01")]
    artist_of, date_of = (lambda it: it[1]), (lambda it: it[2])
    # every artist gets a slot before anyone gets a second
    assert [it[0] for it in spread_across_artists(items, artist_of, date_of, 3)] == \
        ["h1", "g1", "s1"]
    assert [it[0] for it in spread_across_artists(items, artist_of, date_of, 4)] == \
        ["h1", "g1", "s1", "h2"]


def test_spread_across_artists_year_spreads_within_an_artist():
    from llama.util import spread_across_artists

    items = [("h1", "CharlieHunter", "2002-07-05"), ("h2", "CharlieHunter", "2002-08-23"),
             ("h3", "CharlieHunter", "1994-01-11"), ("g1", "GarageATrois", "1998-04-25")]
    artist_of, date_of = (lambda it: it[1]), (lambda it: it[2])
    # CharlieHunter's second slot goes to his best 1994 show, not his second 2002 one
    assert [it[0] for it in spread_across_artists(items, artist_of, date_of, 3)] == \
        ["h1", "g1", "h3"]


def test_spread_across_artists_single_artist_falls_back_to_year_spread():
    from llama.util import spread_across_artists

    items = [("a", "GratefulDead", "1977-05-08"), ("b", "GratefulDead", "1977-05-09"),
             ("c", "GratefulDead", "1969-12-07")]
    artist_of, date_of = (lambda it: it[1]), (lambda it: it[2])
    assert [it[0] for it in spread_across_artists(items, artist_of, date_of, 2)] == ["a", "c"]
