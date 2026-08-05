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


# A leading track number on an enumerated tape: 1-3 digits, an optional single
# separator, then whitespace and a non-space character.
#
# The 1-3 digit bound is LOAD-BEARING and must not be widened to \d+: it is
# what puts "1952 Vincent Black Lightning" and a bare "2001" out of this rule's
# reach entirely, without the gate below having to save them. Pinned by
# test_clean_tag_titles_leaves_an_unnumbered_year_title_alone.
#
# The (?!\d) does none of that work and is provably INERT - the mandatory \s+
# already makes a 4th digit unmatchable, since backtracking to 3 digits leaves
# the 4th where a separator or space must be. Kept because it states the
# intent, at zero cost; do not credit it with the protection.
_TRACK_NUM_PREFIX = re.compile(r"^\d{1,3}(?!\d)[.)\-:]?\s+(?=\S)")

# Whether a leading number is a track number or part of the title cannot be
# decided from one string - "01 Intro - Ramona" and "100 Years" are identical
# in isolation. It is decided by the RECORDING: an enumerated tape numbers
# essentially every track, while a real numeric title is one lone numbered
# file among unnumbered ones.
#
# Measured over 2,095 cached archive.org items (see the spec's A1 evidence):
# this gate strips 94 of the 96 genuinely enumerated tapes, and mutilates NONE
# of the 105 items carrying a real numeric title. The two it misses keep their
# prefixes, which is today's behaviour - a false negative, never a destroyed
# title. Both floors are required; dropping either one breaks a pinned test.
_ENUMERATED_MIN_FILES = 3
_ENUMERATED_MIN_COVERAGE = 0.8


def title_fraction(titles: list[str]) -> float:
    """Fraction of cleaned titles that are usable. 0.0 for no titles."""
    return sum(1 for t in titles if is_real_title(t)) / len(titles) if titles else 0.0


def clean_tag_titles(kept_files: list[dict]) -> list[str]:
    """Cleaned embedded-tag titles for one recording's kept files, in play
    order. Wraps clean_tag_title with the one decision that needs the whole
    recording: whether to strip leading track numbers."""
    titles = [clean_tag_title(f.get("title")) for f in kept_files]
    numbered = sum(1 for t in titles if _TRACK_NUM_PREFIX.match(t))
    if numbered < _ENUMERATED_MIN_FILES or numbered < _ENUMERATED_MIN_COVERAGE * len(titles):
        return titles
    # Strip exactly one number, never loop: on an enumerated tape
    # "01 200 More Miles" must lose only the "01". The no-loop property comes
    # from the ^ anchor, which can only match at position 0, and is pinned by
    # test_clean_tag_titles_strips_once_never_loops; count=1 is provably INERT
    # and kept only because it states that intent at the call site.
    return [_TRACK_NUM_PREFIX.sub("", t, count=1) for t in titles]


def _stem_no_ext(name: str) -> str:
    """Filename without its extension, directory component retained - two
    files sharing a basename in different directories are different tracks."""
    head, sep, tail = name.rpartition(".")
    return head if sep and "/" not in tail else name


def sibling_format_titles(
    kept: list[dict], other_kept: list[dict]
) -> dict[str, str] | None:
    """Map each kept file's name to the title carried by the SAME track in a
    different-format copy of the same archive.org item.

    archive.org builds the lossy derivative from the lossless original and
    sometimes does not carry the tags across, leaving a fully-tagged FLAC
    beside an untagged MP3 of the same tracks. Matching is by filename stem
    and requires a bijection: anything less declines rather than guessing by
    position."""
    if not kept or len(kept) != len(other_kept):
        return None
    ours = {_stem_no_ext(f["name"]): f["name"] for f in kept}
    theirs = {_stem_no_ext(f["name"]): f for f in other_kept}
    if len(ours) != len(kept) or len(theirs) != len(other_kept) or set(ours) != set(theirs):
        return None
    titles = clean_tag_titles([theirs[stem] for stem in ours])
    return {name: title for name, title in zip(ours.values(), titles)}


def resolve_titles(
    kept_files: list[dict],
    setlist: ParsedSetlist,
    sibling_titles: list[str] | None = None,
    format_titles: dict[str, str] | None = None,
) -> list[Track]:
    """Resolve track titles (tags -> setlist -> sibling -> unresolved).

    `format_titles` (from gather's `_recover_format_titles`) is a filename ->
    title map lifted from a different-format copy of the SAME item; when it is
    present it stands in for the tag layer entirely.

    Sets and segues are placeholders here; llama.structure.align stamps the
    real values from the canonical performance setlist. Callers pass
    kept_files in canonical play order (filter_files decides it)."""
    files = kept_files
    n = len(files)
    aligned = setlist.items if (setlist.confidence != "low" and len(setlist.items) == n) else None

    # When format recovery fired, the delivered format's own tags are known
    # bad and are not consulted at all - a manifest never interleaves two tag
    # sources. A recovered title that is still unusable falls through to the
    # setlist/sibling cascade rather than back to the bad tags.
    if format_titles is not None:
        tag_titles = [format_titles.get(f["name"], "") for f in files]
        tag_source = "sibling-format"
    else:
        tag_titles = clean_tag_titles(files)
        tag_source = "tags"

    tracks: list[Track] = []
    for pos, f in enumerate(files):
        if is_real_title(tag_titles[pos]):
            title, source = tag_titles[pos], tag_source
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
