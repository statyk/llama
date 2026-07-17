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


ARTIST_OF, DATE_OF = (lambda it: it[1]), (lambda it: it[2])


def test_cap_across_artists_bounds_dominance_without_guaranteeing_inclusion():
    from llama.util import cap_across_artists

    # score order: CharlieHunter's catalog out-scores everyone
    items = [("h1", "CH", "2002-01-01"), ("h2", "CH", "2000-01-01"),
             ("h3", "CH", "2001-01-01"), ("h4", "CH", "2003-01-01"),
             ("g1", "GAT", "1998-01-01"), ("s1", "SP", "2014-01-01"),
             ("a1", "Allmark", "2010-01-01")]
    # n=6, cap=1/3 -> at most 2 CH slots while alternatives remain; once every
    # other artist is in, the last slot relaxes back to CH's next-best
    picked = [it[0] for it in cap_across_artists(items, ARTIST_OF, DATE_OF, 6, 1 / 3)]
    assert picked == ["h1", "h2", "g1", "s1", "a1", "h3"]


def test_cap_across_artists_cap_one_is_pure_best_first():
    from llama.util import cap_across_artists

    items = [("h1", "CH", "2002-01-01"), ("h2", "CH", "2000-01-01"),
             ("h3", "CH", "2001-01-01"), ("g1", "GAT", "1998-01-01")]
    assert [it[0] for it in cap_across_artists(items, ARTIST_OF, DATE_OF, 3, 1.0)] == \
        ["h1", "h2", "h3"]


def test_cap_across_artists_tiny_cap_is_one_per_artist():
    from llama.util import cap_across_artists

    items = [("h1", "CH", "2002-01-01"), ("h2", "CH", "2000-01-01"),
             ("g1", "GAT", "1998-01-01"), ("s1", "SP", "2014-01-01")]
    assert [it[0] for it in cap_across_artists(items, ARTIST_OF, DATE_OF, 3, 0.01)] == \
        ["h1", "g1", "s1"]


def test_cap_across_artists_relaxes_when_every_artist_is_capped():
    from llama.util import cap_across_artists

    # 2 artists, n=4, cap=1/4 -> max_per=1; caps only cover 2 slots, the
    # remaining 2 relax to best-first instead of under-delivering
    items = [("h1", "CH", "2002-01-01"), ("h2", "CH", "2000-01-01"),
             ("g1", "GAT", "1998-01-01"), ("g2", "GAT", "1999-01-01")]
    picked = [it[0] for it in cap_across_artists(items, ARTIST_OF, DATE_OF, 4, 0.25)]
    assert picked == ["h1", "g1", "h2", "g2"]


def test_cap_across_artists_year_spread_is_opt_in_within_an_artists_slots():
    from llama.util import cap_across_artists

    items = [("h1", "CH", "2002-01-01"), ("h2", "CH", "2002-06-01"),
             ("h3", "CH", "1994-01-01"), ("g1", "GAT", "1998-01-01")]
    # default (year_cap off): CH's two slots are his two best shows
    assert [it[0] for it in cap_across_artists(items, ARTIST_OF, DATE_OF, 3, 0.5)] == \
        ["h1", "h2", "g1"]


def test_cap_across_artists_single_artist_is_year_capped_pick():
    from llama.util import cap_across_artists

    items = [("a", "GD", "1977-05-08"), ("b", "GD", "1977-05-09"),
             ("c", "GD", "1969-12-07")]
    # year_cap off (default): plain top-n
    assert [it[0] for it in cap_across_artists(items, ARTIST_OF, DATE_OF, 2, 1 / 3)] == \
        ["a", "b"]


def test_capped_pick_cap_one_is_identity_prefix():
    from llama.util import capped_pick

    items = [("a", "1977"), ("b", "1977"), ("c", "1969")]
    assert capped_pick(items, lambda it: it[1], 2, 1.0) == items[:2]


def test_capped_pick_soft_cap_bounds_dominance():
    from llama.util import capped_pick

    # best-first: three 1977 shows out-rank everything
    items = [("a", "1977"), ("b", "1977"), ("c", "1977"),
             ("d", "1972"), ("e", "1969")]
    # n=4, cap=1/2 -> at most 2 per year while other years have candidates
    picked = capped_pick(items, lambda it: it[1], 4, 0.5)
    assert picked == [("a", "1977"), ("b", "1977"), ("d", "1972"), ("e", "1969")]


def test_capped_pick_tiny_cap_is_one_per_bucket_then_relaxes():
    from llama.util import capped_pick

    items = [("a", "1977"), ("b", "1977"), ("c", "1969"), ("d", "1972")]
    # max_per=1: one per year in score order, then best-first relax
    assert capped_pick(items, lambda it: it[1], 4, 0.25) == \
        [("a", "1977"), ("c", "1969"), ("d", "1972"), ("b", "1977")]


def test_capped_pick_single_bucket_is_plain_top_n():
    from llama.util import capped_pick

    items = [("a", "1977"), ("b", "1977")]
    assert capped_pick(items, lambda it: it[1], 1, 0.1) == [("a", "1977")]


def test_cap_across_artists_year_cap_off_is_score_order_within_artist():
    from llama.util import cap_across_artists

    # CH's two best shows are both 2002; year_cap off must NOT swap in 1994
    items = [("h1", "CH", "2002-01-01"), ("h2", "CH", "2002-06-01"),
             ("h3", "CH", "1994-01-01"), ("g1", "GAT", "1998-01-01")]
    picked = [it[0] for it in cap_across_artists(items, ARTIST_OF, DATE_OF, 3, 0.5)]
    assert picked == ["h1", "h2", "g1"]


def test_cap_across_artists_year_cap_caps_within_an_artists_slots():
    from llama.util import cap_across_artists

    items = [("h1", "CH", "2002-01-01"), ("h2", "CH", "2002-06-01"),
             ("h3", "CH", "1994-01-01"), ("g1", "GAT", "1998-01-01")]
    # year_cap 0.25 on CH's 3-show queue -> ceil(3*0.25)=1 per year
    picked = [it[0] for it in cap_across_artists(items, ARTIST_OF, DATE_OF, 3, 0.5,
                                                 year_cap=0.25)]
    assert picked == ["h1", "h3", "g1"]


def test_cap_across_artists_single_artist_year_cap_off_is_top_n():
    from llama.util import cap_across_artists

    items = [("a", "GD", "1977-05-08"), ("b", "GD", "1977-05-09"),
             ("c", "GD", "1969-12-07")]
    assert [it[0] for it in cap_across_artists(items, ARTIST_OF, DATE_OF, 2, 1 / 3)] == \
        ["a", "b"]


def test_cap_across_artists_single_artist_year_cap_bounds_years():
    from llama.util import cap_across_artists

    items = [("a", "GD", "1977-05-08"), ("b", "GD", "1977-05-09"),
             ("c", "GD", "1969-12-07")]
    # n=2, year_cap=0.5 -> ceil(1)=1 per year: old round-robin behavior
    assert [it[0] for it in cap_across_artists(items, ARTIST_OF, DATE_OF, 2, 1 / 3,
                                               year_cap=0.5)] == ["a", "c"]
