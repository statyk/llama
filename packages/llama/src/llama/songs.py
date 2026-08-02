import re

# Keys and values are in normalized form (lowercase, no punctuation, apostrophes dropped).
# GD-heavy to start, per spec; extend as other artists come up.
DEFAULT_ALIASES: dict[str, str] = {
    "china cat": "china cat sunflower",
    "rider": "i know you rider",
    "u s blues": "us blues",
    "gdtrfb": "goin down the road feeling bad",
    "going down the road feeling bad": "goin down the road feeling bad",
    "going down the road feelin bad": "goin down the road feeling bad",
    "goin down the road feelin bad": "goin down the road feeling bad",
    "playin in the band": "playing in the band",
    "playin": "playing in the band",
    "nfa": "not fade away",
    "st stephen": "saint stephen",
    "uncle john": "uncle johns band",
    "jbg": "johnny b goode",
    "one more sat night": "one more saturday night",
    "wharf rat": "wharf rat",
}

# Dead-canon shorthand: single-word stand-ins and closed-up spellings that
# tapers use constantly. Keys and values are in normalized form, so this table
# is applied AFTER `normalize_song` (which has already applied DEFAULT_ALIASES).
#
# Kept separate from DEFAULT_ALIASES and NOT applied globally: "scarlet",
# "help", "dew", "eyes", "wheel", "saint" and "stephen" are ordinary English
# words, and a Beatles cover titled "Help" on a punk tape must not become "help
# on the way". Callers gate it on `jerrybase.is_family_artist`; the jerrybase
# closer path applies it unconditionally because an event only exists for
# artists in the dataset.
#
# Every value below was checked present in the vendored set_breaks.csv song
# vocabulary. Note the deliberate split of the two "saint" cases: bare "Saint"
# in Dead usage is the "Sailor > Saint" pairing, while St. Stephen is written
# out (DEFAULT_ALIASES already maps "st stephen").
GD_SHORTHAND: dict[str, str] = {
    "scarlet": "scarlet begonias",
    "fire": "fire on the mountain",
    "help": "help on the way",
    "slip": "slipknot",
    "frank": "franklins tower",
    "estimated": "estimated prophet",
    "eyes": "eyes of the world",
    "sailor": "lost sailor",
    "saint": "saint of circumstance",
    "dew": "morning dew",
    "wheel": "the wheel",
    "stephen": "saint stephen",
    "china": "china cat sunflower",
    "chinacat": "china cat sunflower",
    # --- Spelling variants (same song, two spellings). Each recurs across many
    # corpus shows: 22, 15, 10 and 8 distinct shows respectively.
    "touch of gray": "touch of grey",
    "mississippi half step uptown toodleloo": "mississippi half step uptown toodeloo",
    "drumz": "drums",
    "throwin stones": "throwing stones",
    # --- True synonym: the same song under two full names, 21 shows. Neither
    # is a subphrase of the other, so no general rule can ever connect them —
    # this is the case a table exists for. "Man Smart, Woman Smarter" is the
    # calypso title; "Women Are Smarter" is what Dead setlists usually say.
    "women are smarter": "man smart woman smarter",
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
