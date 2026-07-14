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
