"""Fixed-a-priori junk-title classes for the held-backlog title slices.

Spec: docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md,
"2a -- Corroborated short tags" (the junk veto, `is_junk_tag`), "2b --
Junk-title detector" (the per-title and recording-level classes,
`is_placeholder_title` and `recording_level_junk`) and "New constants" (2b's
placeholder vocabulary and residue token set; 2a's date pattern and residue
shape). Every pattern here is fixed a priori: do not retune it after a harness
run.

These predicates sit BESIDE `titles.is_real_title` (ruling 2: narrow beside,
never loosen in place); nothing here changes that predicate or any other
do-not-retune constant. Pure: no IO, no state.
"""
import re

from llama.structure import fuzzy_norm_title

NUMBER_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
                "eighteen", "nineteen", "twenty")

# 2b placeholder vocabulary (spec "2b", "New constants"): Track/Trac/Trk/Tr/Cut
# + a number or number word, tmp/temp, No Title, Title. A full match, so
# `Tracks of My Tears`, `Title Fight` and `Temptation` stay out, and a bare
# `Track` (no number) is not a placeholder. Deliberately never `untitled`
# (bare `Untitled` is a real title, `Untitled #12` is how every source names a
# Railroad Earth song) and never `song\s*#?\d+` (Fugazi's `Song #1` is real).
_PLACEHOLDER = re.compile(
    r"(?:track|trac|trk|tr|cut)\s*[-_#.]?\s*(?:\d{1,3}|" + "|".join(NUMBER_WORDS) + r")"
    r"|tmp|temp|no\s*title|title",
    re.I)

# 2b timestamp class: a bare timestamp, optionally bracketed, optionally with
# a trailing dash (`27:36.27`, `05:27 -`, `[12:30]`). Full match, so
# `07:22 - IB49` (text after it) is not this class, and `3AM`/`2001` (no colon)
# never are.
_TIMESTAMP = re.compile(r"^[\[(]?\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?[\])]?\s*-?$")

# 2a's veto: a LEADING timestamp, so `07:22 - IB49` is junk to 2a though not a
# bare timestamp; `Jam 07:22` (timestamp not leading) and `3AM` are not.
_LEADING_TIMESTAMP = re.compile(r"[\[(]?\d{1,2}:\d{2}")

_MONTH = (r"(?:january|february|march|april|may|june|july|august|september|october|november"
          r"|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)")
# 2a date pattern (spec "2a", "New constants"): numeric day, month and year in
# any order with `-` `.` `/` separators (three parts, so `7-11` and `I-55` stay
# out), or a month name with a day and/or a year (so a bare `May` and a bare
# `1979` stay out; `1 in 7` has no month and only one separator-free run).
_DATE_PATTERNS = (
    re.compile(r"^\d{1,4}[-./]\d{1,2}[-./]\d{1,4}$"),
    re.compile(r"^" + _MONTH + r"\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{2,4})?$", re.I),
    re.compile(r"^\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTH + r"\.?(?:,?\s+\d{2,4})?$", re.I),
    re.compile(r"^" + _MONTH + r"\.?\s+\d{4}$", re.I),
)

# 2a filename-residue shape (spec "2a", "New constants"): an optional
# identifier+date prefix then an optional disc/set token and a track token
# (`gd73-06-10d1t04`, `d1t02`, `t1`), or an archive `NNNNNN_NN` stem. Full
# match, so `FF`, `42`, `J` and `7-11` (2a's targets) are never this shape.
_FILENAME_SHAPES = (
    re.compile(r"^(?:[a-z]{2,8}_*\d{2,4}[-.]\d{2}[-.]\d{2,4}\s*)?(?:[sd]\d{1,2})?t\d{1,3}$", re.I),
    re.compile(r"^\d{6,}_\d+$"),
    re.compile(r"^[sd]\d{1,2}t\d{1,3}$", re.I),
)

# 2b residue token set (spec "2b", "New constants"): what is deleted before
# counting the letters left. One regex, alternatives in this order:
RESIDUE_TOKENS = re.compile(
    # identifier+date prefix, START-ANCHORED like `_ID_PREFIX`: unanchored it
    # would eat `Begonias 1977-05-08` out of `Scarlet Begonias 1977-05-08`.
    r"^[a-z&]+\s*\d{2,4}[-._]\d{2}[-._]\d{2,4}"
    # disc/track tokens (`d2t05`, `t02`, `cd1t03`)
    r"|(?:s|d|cd|disc)?\d{0,2}t\d{2,3}\b"
    # long digit runs (archive stems, `123456_01`)
    r"|\b\d{6,}(?:_\d+)?\b"
    # audio extensions
    r"|\.(?:flac|shn|mp3|wav|ogg)\b"
    # lineage words (ruled: `Master`/`Matrix` alone ARE demoted, a documented
    # limitation -- demotion only leaves a track unresolved, i.e. held)
    r"|\b(?:sbd|aud|fob|dfc|matrix|mtx|flac\d*|shnf?|remaster\w*|master|soundboard)\b"
    # `track N`
    r"|\btrack\s*\d+\b",
    re.I)

# 2b's residue class leaves fewer than this many ASCII letters.
_RESIDUE_MIN_LETTERS = 3


def is_placeholder(s: str) -> bool:
    """2b placeholder vocabulary (`Track 01`, `track six`, `tmp`, `No Title`)."""
    return _PLACEHOLDER.fullmatch(s.strip()) is not None


def is_timestamp(s: str) -> bool:
    """2b timestamp class: the whole string is a timestamp (`27:36.27`, `05:27 -`)."""
    return _TIMESTAMP.match(s.strip()) is not None


def starts_with_timestamp(s: str) -> bool:
    """2a's veto arm: the string BEGINS with a timestamp (`07:22 - IB49`)."""
    return _LEADING_TIMESTAMP.match(s.strip()) is not None


def is_date_like(s: str) -> bool:
    """2a's date pattern (`12-28-99`, `Dec 28, 1999`, `May 1977`; not `7-11`, `May`)."""
    t = s.strip()
    return any(p.match(t) for p in _DATE_PATTERNS)


def looks_like_filename(s: str) -> bool:
    """2a's filename-residue shape (`d1t02`, `t1`, `123456_01`; not `FF`, `42`)."""
    t = s.strip()
    return any(p.fullmatch(t) for p in _FILENAME_SHAPES)


def letters_after_residue(s: str) -> int:
    """ASCII letters left once every `RESIDUE_TOKENS` match is deleted."""
    rest = RESIDUE_TOKENS.sub(" ", s)
    return sum(1 for c in rest if c.isascii() and c.isalpha())


def is_residue(t: str) -> bool:
    """2b's pure-filename-residue class alone. A pure 4-digit title (`1979`,
    `1759`, `1103`) is exempt; a blank title is never residue."""
    s = t.strip()
    return bool(s) and not re.fullmatch(r"\d{4}", s) and letters_after_residue(s) < _RESIDUE_MIN_LETTERS


def is_placeholder_title(title: str) -> bool:
    """2b's per-title classes: placeholder vocabulary, bare timestamp, or pure
    filename residue. A blank title is not judged (False)."""
    if not title.strip():
        return False
    return is_placeholder(title) or is_timestamp(title) or is_residue(title)


def is_junk_tag(core: str) -> bool:
    """2a's junk veto: a placeholder, a leading timestamp, a date, or filename
    residue. Deliberately does NOT count letters: a core with fewer than 3
    letters (`FF`, `J`, `42`) is exactly what 2a exists to accept."""
    return (is_placeholder(core) or starts_with_timestamp(core) or is_date_like(core)
            or looks_like_filename(core))


def recording_level_junk(titles: list[str], item_title: str | None) -> bool:
    """2b's recording-level class: on a recording of at least 3 tracks, one
    identical (case-folded) string on every track (`tmp` x 19), or the item's
    own title on every track. An item title that normalizes to nothing never
    matches, so a run of empty-normalizing tags is judged only by the first arm."""
    if len(titles) < 3:
        return False
    folded = {t.strip().lower() for t in titles}
    if len(folded) == 1 and next(iter(folded)):
        return True
    item_norm = fuzzy_norm_title(item_title) if item_title and item_title.strip() else ""
    return bool(item_norm) and all(fuzzy_norm_title(t) == item_norm for t in titles)
