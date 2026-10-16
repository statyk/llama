"""normalize_artist: the loose artist-name key for [assign.artists] (spec section 2)."""

import pytest

from emcee.artists import normalize_artist


@pytest.mark.parametrize("a, b", [
    ("Karl Denson's Tiny Universe", "Karl Densons Tiny Universe"),
    ("Karl Denson’s Tiny Universe", "Karl Densons Tiny Universe"),
    ("Robert Randolph [and the Family Band]", "Robert Randolph"),
    ("Robert Walter's 20th Congress", "Robert Walters 20th Congress"),
    ("JJ Grey & MOFRO", "JJ Grey and MOFRO"),
    ("The Motet", "Motet"),
    ("TEDESCHI TRUCKS BAND", "Tedeschi Trucks Band"),
    ("  Lettuce!! ", "Lettuce"),
])
def test_spelling_variants_meet(a, b):
    assert normalize_artist(a) == normalize_artist(b)


@pytest.mark.parametrize("a, b", [
    ("Robert Randolph", "Robert Walter's 20th Congress"),
    ("Soulive", "Lettuce"),
    ("Theory of a Deadman", "Ory of a Deadman"),
])
def test_different_artists_stay_different(a, b):
    assert normalize_artist(a) != normalize_artist(b)


def test_each_rule_in_order():
    assert normalize_artist("Béla Fleck") == "béla fleck"      # unicode letters kept
    assert normalize_artist("A [x] [y]") == "a x"                       # only ONE trailing group dropped
    assert normalize_artist("Tom & Jerry") == "tom and jerry"
    assert normalize_artist("The Band") == "band"                       # leading "the " dropped
    assert normalize_artist("Theory of a Deadman") == "theory of a deadman"
    assert normalize_artist("Ween/Phish-ish") == "ween phish ish"


@pytest.mark.parametrize("name", ["[Family Band]", "!!!", "   "])
def test_names_that_normalize_to_nothing(name):
    assert normalize_artist(name) == ""
