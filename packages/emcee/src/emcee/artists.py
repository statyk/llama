"""Loose artist-name matching for `[assign.artists]` rules (spec section 2).

Pure and dependency-free: config validation and the effective-profile
resolver both use it, so it imports nothing from emcee.
"""

import re

_TRAILING_BRACKET = re.compile(r"\[[^\[\]]*\]\s*$")
_APOSTROPHES = ("'", "’")


def normalize_artist(name: str) -> str:
    """The comparison key for an artist name. In order: casefold; drop one
    trailing `[...]` group; `&` -> ` and `; delete apostrophes (`'` and the
    right single quote); replace every other character that is not a
    Unicode letter or digit with a space; collapse whitespace and strip;
    drop a leading `the `.

    "Karl Denson's Tiny Universe" meets "Karl Densons Tiny Universe";
    "Robert Randolph [and the Family Band]" meets "Robert Randolph";
    "Béla Fleck" keeps its é."""
    s = name.casefold()
    s = _TRAILING_BRACKET.sub("", s.rstrip(), count=1)
    s = s.replace("&", " and ")
    for mark in _APOSTROPHES:
        s = s.replace(mark, "")
    s = "".join(ch if (ch.isalpha() or ch.isdigit()) else " " for ch in s)
    s = " ".join(s.split())
    if s.startswith("the "):
        s = s[4:]
    return s
