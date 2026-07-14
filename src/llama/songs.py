import re

# Keys and values are in normalized form (lowercase, no punctuation, apostrophes dropped).
# GD-heavy to start, per spec; extend as other artists come up.
DEFAULT_ALIASES: dict[str, str] = {
    "china cat": "china cat sunflower",
    "rider": "i know you rider",
    "gdtrfb": "goin down the road feeling bad",
    "going down the road feeling bad": "goin down the road feeling bad",
    "going down the road feelin bad": "goin down the road feeling bad",
    "goin down the road feelin bad": "goin down the road feeling bad",
    "playin in the band": "playing in the band",
    "nfa": "not fade away",
    "st stephen": "saint stephen",
    "uncle john": "uncle johns band",
    "jbg": "johnny b goode",
    "one more sat night": "one more saturday night",
    "wharf rat": "wharf rat",
}

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")


def normalize_song(name: str, aliases: dict[str, str] | None = None) -> str:
    s = name.lower().replace("'", "")
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    table = DEFAULT_ALIASES if aliases is None else {**DEFAULT_ALIASES, **aliases}
    return table.get(s, s)


def matches_sequence(setlist: list[str], sequence: list[str]) -> bool:
    """True if `sequence` appears as an adjacent, in-order run within `setlist`."""
    norm = [normalize_song(s) for s in setlist]
    seq = [normalize_song(s) for s in sequence]
    if not seq:
        return True
    return any(norm[i : i + len(seq)] == seq for i in range(len(norm) - len(seq) + 1))
