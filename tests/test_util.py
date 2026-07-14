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
