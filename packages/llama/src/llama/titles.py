import re

from llama.models import ParsedSetlist, Track
from llama.util import length_seconds

# Identifier prefix embedded in tag titles ("gd73-06-10d1t04 Here Comes
# Sunshine"): 2-5 letters, 2- or 4-digit year, -/. separated date, then
# optional disc/track tokens. Adapted from deadstream, extended to 4-digit
# years.
_ID_PREFIX = re.compile(r"^[a-zA-Z]{2,5}_*\d{2}(?:\d{2})?[-.]\d{2}[-.]\d{2}\s*(?:[td]\d+)*")
_AUDIO_EXT = re.compile(r"\.(?:mp3|flac|ogg|shn)\s*$", re.I)
_EDGE_JUNK = " \t-–—_.|"


def clean_tag_title(raw: str | None) -> str:
    """Strip identifier prefix / audio extension from an embedded tag title.
    "unknown" is never a real title and maps to ""."""
    s = _ID_PREFIX.sub("", str(raw or "").strip())
    s = _AUDIO_EXT.sub("", s)
    s = s.strip(_EDGE_JUNK)
    return "" if s.lower() == "unknown" else s


def is_real_title(cleaned: str) -> bool:
    """At least 3 ASCII letters: accepts real short titles (Deal, Jam),
    rejects date-less filename residue (d1t02)."""
    return sum(ch.isascii() and ch.isalpha() for ch in cleaned) >= 3


def resolve_titles(
    kept_files: list[dict],
    setlist: ParsedSetlist,
    sibling_titles: list[str] | None = None,
) -> list[Track]:
    """Resolve track titles (tags -> setlist -> sibling -> unresolved).

    Sets and segues are placeholders here; llama.structure.align stamps the
    real values from the canonical performance setlist. Callers pass
    kept_files in canonical play order (filter_files decides it)."""
    files = kept_files
    n = len(files)
    aligned = setlist.items if (setlist.confidence != "low" and len(setlist.items) == n) else None

    tracks: list[Track] = []
    for pos, f in enumerate(files):
        tag_title = clean_tag_title(f.get("title"))
        if is_real_title(tag_title):
            title, source = tag_title, "tags"
        elif aligned:
            title, source = aligned[pos].title, "setlist"
        elif sibling_titles and len(sibling_titles) == n:
            title, source = sibling_titles[pos], "sibling"
        else:
            title, source = f["name"], "unresolved"
        tracks.append(
            Track(index=pos + 1, set="1", title=title, filename=f["name"],
                  duration_sec=length_seconds(f.get("length")), segue=False,
                  title_source=source)
        )
    return tracks


def set_breaks(tracks: list[Track]) -> list[int]:
    return [prev.index for prev, nxt in zip(tracks, tracks[1:]) if nxt.set != prev.set]
