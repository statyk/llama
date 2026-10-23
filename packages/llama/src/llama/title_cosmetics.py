"""Title hygiene slice 5: cosmetic junk stripping on FINAL resolved titles.

Spec `docs/superpowers/specs/2026-10-22-title-hygiene-design.md`, "Slice 5"; plan Task 10.
Pure; wired into gather by a later task. Strips only these shapes: a leading m:ss /
h:mm:ss, an embedded identifier/disc-track stem, a `.wav`/`.flac[:md5]` tail and, by
Checkpoint B ruling 5, a leading `<artist> - ` (the show's own artist under
`fuzzy_norm_title` equality), a leading `Encore- `/`Encore - ` and a trailing ` H2`
recorder token. It keeps the result only when it is non-empty, not a placeholder, and
`is_real_title` or 2a-shaped, and (final review M-6) declines a strip that leaves an empty
bracket pair or edits inside one (`Esau (s2t01)` -> `Esau ()`). `E:` and set markers are
never touched."""

import re

from llama.models import Track
from llama.placeholders import is_junk_tag
from llama.structure import fuzzy_norm_title
from llama.titles import is_placeholder_text, is_real_title, tag_core

STRIP_SOURCES = frozenset({"tags", "sibling-format", "setlist", "setlist-gap",
                           "desc-position", "sibling-align"})

_LEADING_TIME = re.compile(r"^[(\[]?\d{1,2}:\d{2}(?::\d{2})?(?:[)\]]\s*|\s+-\s+)")
_STEM = re.compile(
    r"(?<![a-z0-9])(?:[a-z&]{2,10}\d{2,4}[.\-]\d{2}[.\-]\d{2,4}(?:\.[a-z0-9]+)*?\.?)?"
    r"(?:d|cd|s|set)\d{1,2}t\d{1,3}[\s\-_.:]*", re.I)
_TAIL = re.compile(r"\.(?:wav|flac)\s*$|\.flac:[0-9a-f]{32}\s*$", re.I)
_ENCORE_DASH = re.compile(r"^\s*encore ?- ", re.I)          # gratefuldead-1974-10-18 #24
_H2_TAIL = re.compile(r"\s+H2\s*$")                          # lotus-2008-02-07
_ARTIST_SEP = " - "                                          # greenskybluegrass-2013-05-04
_BRACKET_PAIR = re.compile(r"\([^()]*\)|\[[^\[\]]*\]")
_EMPTY_PAIR = re.compile(r"\(\s*\)|\[\s*\]")


def _strip_artist(text: str, artist: str | None) -> str:
    """A leading `<artist> - ` whose prefix is the show's artist (`fuzzy_norm_title`)."""
    if not artist:
        return text
    head, sep, rest = text.partition(_ARTIST_SEP)
    want = fuzzy_norm_title(artist)
    if sep and want and fuzzy_norm_title(head) == want:
        return rest
    return text


def _strip(title: str, artist: str | None = None) -> str:
    out = _LEADING_TIME.sub("", title)
    out = _STEM.sub("", out)
    out = _TAIL.sub("", out)
    out = _strip_artist(out.strip(), artist)
    out = _ENCORE_DASH.sub("", out, count=1)
    out = _H2_TAIL.sub("", out)
    return out.strip()


def _bracket_debris(old: str, new: str) -> bool:
    """M-6: the strip left an empty bracket pair, or a pair the original did not have (it
    cut inside one: `Banks of the Ohio (actually d2t10)` -> `(actually )`)."""
    return bool(_EMPTY_PAIR.search(new)) or not (
        set(_BRACKET_PAIR.findall(new)) <= set(_BRACKET_PAIR.findall(old)))


def _acceptable(text: str) -> bool:
    if not text or is_placeholder_text(text):
        return False
    if is_real_title(text):
        return True
    core = tag_core(text)
    return any(ch.isalnum() for ch in core) and not is_junk_tag(core)


def cosmetic_strip(tracks: list[Track], *, artist: str | None = None,
                   ) -> tuple[list[Track], list[str], list[int]]:
    """Returns (tracks, notes, changed 0-based positions); inputs are not mutated. `artist`
    is the show's artist (`compute_gather` threads it); None strips no artist prefix."""
    out: list[Track] = []
    notes: list[str] = []
    changed: list[int] = []
    for pos, t in enumerate(tracks):
        if t.title_source in STRIP_SOURCES:
            new = _strip(t.title, artist)
            if new != t.title and _acceptable(new) and not _bracket_debris(t.title, new):
                notes.append(f"cosmetic title strip: track {pos + 1} '{t.title}' -> '{new}'")
                changed.append(pos)
                t = t.model_copy(update={"title": new})
        out.append(t)
    return out, notes, changed
