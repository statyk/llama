"""Loose artist-name matching for `[assign.artists]` rules (spec section 2).

Pure and dependency-free: config validation and the effective-profile
resolver both use it, so it imports nothing from emcee.
"""

import re
import unicodedata

_TRAILING_BRACKET = re.compile(r"\[[^\[\]]*\]\s*$")
_APOSTROPHES = ("'", "’")


def normalize_artist(name: str) -> str:
    """The comparison key for an artist name. In order: casefold, then NFC
    (casefold can itself emit decomposed sequences, so NFC goes after it);
    drop one trailing `[...]` group; `&` -> ` and `; delete apostrophes
    (`'` and the right single quote); replace every other character that
    is not a Unicode letter, digit or combining mark with a space; collapse
    whitespace and strip; drop a leading `the `.

    "Karl Denson's Tiny Universe" meets "Karl Densons Tiny Universe";
    "Robert Randolph [and the Family Band]" meets "Robert Randolph";
    "Béla Fleck" keeps its é, whether typed precomposed or decomposed; a
    combining mark with no precomposed form stays inside its word."""
    s = unicodedata.normalize("NFC", name.casefold())
    s = _TRAILING_BRACKET.sub("", s.rstrip(), count=1)
    s = s.replace("&", " and ")
    for mark in _APOSTROPHES:
        s = s.replace(mark, "")
    s = "".join(ch if (ch.isalpha() or ch.isdigit()
                       or unicodedata.category(ch).startswith("M")) else " " for ch in s)
    s = " ".join(s.split())
    if s.startswith("the "):
        s = s[4:]
    return s
