"""Title hygiene slice 5: cosmetic junk stripping on FINAL resolved titles.

Spec `docs/superpowers/specs/2026-10-22-title-hygiene-design.md`, "Slice 5"; plan Task 10.
Pure; wired into gather by a later task. Strips only three shapes (a leading m:ss /
h:mm:ss, an embedded identifier/disc-track stem, a `.wav`/`.flac[:md5]` tail), and keeps
the result only when it is non-empty, not a placeholder, and `is_real_title` or 2a-shaped.
`E:` and set markers are never touched."""

import re

from llama.models import Track
from llama.placeholders import is_junk_tag
from llama.titles import is_placeholder_text, is_real_title, tag_core

STRIP_SOURCES = frozenset({"tags", "sibling-format", "setlist", "setlist-gap",
                           "desc-position", "sibling-align"})

_LEADING_TIME = re.compile(r"^[(\[]?\d{1,2}:\d{2}(?::\d{2})?(?:[)\]]\s*|\s+-\s+)")
_STEM = re.compile(
    r"(?<![a-z0-9])(?:[a-z&]{2,10}\d{2,4}[.\-]\d{2}[.\-]\d{2,4}(?:\.[a-z0-9]+)*?\.?)?"
    r"(?:d|cd|s|set)\d{1,2}t\d{1,3}[\s\-_.:]*", re.I)
_TAIL = re.compile(r"\.(?:wav|flac)\s*$|\.flac:[0-9a-f]{32}\s*$", re.I)


def _strip(title: str) -> str:
    out = _LEADING_TIME.sub("", title)
    out = _STEM.sub("", out)
    out = _TAIL.sub("", out)
    return out.strip()


def _acceptable(text: str) -> bool:
    if not text or is_placeholder_text(text):
        return False
    if is_real_title(text):
        return True
    core = tag_core(text)
    return any(ch.isalnum() for ch in core) and not is_junk_tag(core)


def cosmetic_strip(tracks: list[Track]) -> tuple[list[Track], list[str], list[int]]:
    """Returns (tracks, notes, changed 0-based positions); inputs are not mutated."""
    out: list[Track] = []
    notes: list[str] = []
    changed: list[int] = []
    for pos, t in enumerate(tracks):
        if t.title_source in STRIP_SOURCES:
            new = _strip(t.title)
            if new != t.title and _acceptable(new):
                notes.append(f"cosmetic title strip: track {pos + 1} '{t.title}' -> '{new}'")
                changed.append(pos)
                t = t.model_copy(update={"title": new})
        out.append(t)
    return out, notes, changed
