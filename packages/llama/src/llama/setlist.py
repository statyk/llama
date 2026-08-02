import html
import re

from llama.models import ParsedSetlist, SetlistItem
from llama.songs import normalize_song

_SET_LINE = re.compile(
    r"^(?:set\s*(one|two|three|i{1,3}|[123])|([123])(?:st|nd|rd)\s+set)\s*[:\-]?\s*(.*)$", re.I
)
# Labeled set headers: "Early Set - Grove Stage", "Acoustic Set: Ripple, ...".
# Header-shaped only — the label word starts the line and "set" is followed by
# a colon (inline songs), a dash (stage/venue label, never songs), or the line
# end — so prose like "Early set highlights include..." never matches.
# Ordinal labels carry their own number; the rest get sequential numbers in
# order of appearance.
_LABELED_SET_LINE = re.compile(
    r"^(first|second|third|early|late|opening|closing|acoustic|electric"
    r"|morning|afternoon|evening)\s+set\b\s*(?::\s*(.*)|[-–—].*)?$",
    re.I,
)
_LABELED_ORDINAL = {"first": "1", "second": "2", "third": "3"}
_ENCORE_LINE = re.compile(r"^(?:encore|e\d?)\s*(?::|-\s|$)\s*(.*)$", re.I)
# A set/encore marker mid-line ("... Bertha Set II: Playin' ...") starts a new
# set: break the line there. Inline markers must carry a colon/dash - unlike
# line-start markers - so prose like "the second set" never splits a title.
_INLINE_MARKER = re.compile(
    r"\s+(?=(?:set\s*(?:one|two|three|i{1,3}|[123])|[123](?:st|nd|rd)\s+set|encore|e\d)\s*[:\-])",
    re.I,
)
# Two kinds of leading number: UNAMBIGUOUS forms are stripped unconditionally
# regardless of the enumerated-gate below — a disc/track token (d1t04, t02),
# or a bare number immediately followed by punctuation *and* a space
# ("1. Bertha", "2) Sugaree"). The digits-punctuation-space combination only
# ever shows up in a real numbered tracklist, even a two-line fragment (an
# encore-only snippet, a sibling recording's short description) that never
# reaches the >=3 threshold below — so gating it on `enumerated` would have
# regressed short descriptions that used to be stripped unconditionally
# before this task widened `_TRACK_PREFIX`'s scope. It cannot touch any of
# the hazard titles ("1952 Vincent...", "72 (This Highway's Mean)", "8 Miles
# High", "50 Ways..."): the punctuation must sit immediately against the
# digits, and none of those titles have punctuation there. That immunity is
# local to this regex alone, though: _TRACK_PREFIX and _NUM_PREFIX compose,
# so once the enumerated gate is open a punctuated prefix like "02. 72 (This
# Highway's Mean)" is stripped here to "72 (This Highway's Mean)" and then
# _NUM_PREFIX strips the "72 " too - don't read the sentence above as "the
# punctuated branch makes hazard titles safe" overall.
_TRACK_PREFIX = re.compile(
    r"^\s*(?:(?:d\d+t\d+|t\d{1,2})\s*[\s.\-:]+|\d{1,3}[.)]\s+)", re.I
)
# A bare leading number is AMBIGUOUS: "01 Bertha" is a track number, but
# "1952 Vincent Black Lightning", "8 Miles High" and "72 (This Highway's Mean)"
# are song titles. Only strip it when the description is ENUMERATED — several
# lines carry one — which is what distinguishes a numbered tracklist from a
# song that happens to start with a digit.
#
# The gate only protects hazard titles while it is SHUT. Once open, every
# digit-leading line in the description is presumed numbered, so a hazard
# title sharing a description with a real numbered tracklist still loses its
# leading digits — that is inherent to a document-level discriminator, not a
# defect. What this regex fixes is *how* it loses them: `[.)]*` and both
# `\s*` here are all zero-width-satisfiable, so with the naive
# `\d{1,3}\s*[.)]*\s*` a description containing "1952 Vincent Black
# Lightning" alongside real track numbers used to corrupt it to "2 Vincent
# Black Lightning" (the `\d{1,3}` cap truncates to "195", then the
# zero-width tail still matches, consuming just "195"). Mirroring
# `_NUM_LINE`'s two branches instead — punctuation may abut the title, but a
# bare number requires a following space — makes the whole leading run
# either fully matched or not matched at all, so "1952..." is left
# completely intact (clean over-strip beats corruption, but 3 of the 4
# hazard titles are still stripped whenever the gate is open — measured at
# ~2% of corpus setlist items: ~10 distinct songs across ~40 of 2055 rows,
# e.g. "40 Miles From Denver", "100 Years", "200 More Miles").
_NUM_PREFIX = re.compile(r"^\s*\d{1,3}(?:\s*[.)]+\s*|\s+)")
# Two branches: punctuation may directly abut the title ("1.Sugaree",
# "205....Scarlet"), but a *bare* number (no punctuation) still requires a
# following space ("01 Bertha") — requiring whitespace unconditionally would
# miss "1.Sugaree"; dropping it unconditionally would false-match a
# multi-digit title like "1952 Vincent Black Lightning", since `\d{1,3}`
# truncates it to "195" and the stray "2" would look like the title start.
_NUM_LINE = re.compile(r"^\s*\d{1,3}\s*(?:[.)]+\s*|\s+)\S")


def _enumerated_prefix(lines: list[str]) -> bool:
    """True when at least 3 lines begin with a number followed by
    punctuation or whitespace and then a non-space character, i.e. the
    description is a numbered tracklist rather than prose containing a
    numeric title. The punctuation-or-space requirement is load-bearing:
    without it, a multi-digit title truncated by `\\d{1,3}`'s 3-digit cap
    (e.g. "1952 Vincent Black Lightning" -> "195") would count as a
    numbered line. Lines `_NOISE` will discard are excluded from the count
    too: digit-leading lineage/provenance chatter ("24 bit 96 khz", "2 discs
    total") would otherwise open the gate on its own on a description with
    no numbered tracklist at all, corrupting real digit-leading titles that
    happen to share the description."""
    return sum(1 for ln in lines if _NUM_LINE.match(ln) and not _NOISE.search(ln)) >= 3


_SET_TOKEN = {"one": "1", "two": "2", "three": "3", "i": "1", "ii": "2", "iii": "3"}
# Lines that are lineage/provenance chatter, not songs. Checked before song splitting.
_NOISE = re.compile(
    r"(recorded|transfer|lineage|source|taper|shnid|seeded|thanks|conversion|remaster"
    r"|\bsbd\b|\bdat\b|\bflac\b|\bshn\b|cassette|master reel|\bvia\b|d\d+t\d+\s*$"
    r"|disc\s*#?\s*\d"
    # "Jerry Garcia - guitar", "Bill Kreutzmann - drums": a name, a dash, an
    # instrument. Anchored on the dash so a bare "Drums" song line is untouched.
    r"|[a-z]\s+[-–—]\s*(guitar|bass|drums?|vocals?|keyboards?|piano"
    r"|organ|percussion|harmonica|mandolin|fiddle|banjo|sax(?:ophone)?)\s*$"
    r"|^comments?\b)",
    re.I,
)

# Emitted-title junk: a bare duration or a disc marker that survived line-level
# noise filtering because it sat inside a comma-separated run.
_JUNK_TITLE = re.compile(r"^\(?\d{1,3}[:.]\d{2}\)?$|^disc\s*#?\s*\d+$", re.I)


def _is_junk_title(title: str) -> bool:
    return bool(_JUNK_TITLE.match(title.strip()))


# Older LMA items often give the whole setlist as one unbroken, comma/segue-separated
# line with no per-set headers or line breaks at all. A per-line length cap would throw
# the entire thing out, so the length guard against prose noise is applied per split
# song title instead — legitimate titles are short; a paragraph of unstructured text
# with no separators becomes one implausibly long "title" and is dropped here.
MAX_TITLE_LEN = 80


def _split_songs(chunk: str) -> list[tuple[str, bool]]:
    """Split a text chunk into (title, segues_into_next). '>' or '->' marks a segue."""
    parts = re.split(r"(->|>|,|;)", chunk)
    songs: list[tuple[str, bool]] = []
    for i in range(0, len(parts), 2):
        title = parts[i].strip().strip("*").strip()
        if not title:
            continue
        sep = parts[i + 1] if i + 1 < len(parts) else ""
        songs.append((title, sep in (">", "->")))
    return songs


def parse_setlist(description: str) -> ParsedSetlist:
    text = re.sub(r"<br\s*/?>", "\n", description, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html.unescape(text)  # "&gt;" segues, "&amp;" in titles
    text = _INLINE_MARKER.sub("\n", text)
    lines = [ln.strip() for ln in text.splitlines()]
    # If any set/encore marker exists, the setlist starts there: header lines above
    # (band name, venue, lineage) must not be parsed as songs.
    first_marker = next(
        (i for i, ln in enumerate(lines)
         if _SET_LINE.match(ln) or _LABELED_SET_LINE.match(ln) or _ENCORE_LINE.match(ln)),
        None,
    )
    if first_marker is not None:
        lines = lines[first_marker:]
    enumerated = _enumerated_prefix(lines)
    current_set: str | None = None
    last_num = 0
    saw_marker = False
    items: list[SetlistItem] = []
    for line in lines:
        if not line:
            continue
        m = _SET_LINE.match(line)
        lm = _LABELED_SET_LINE.match(line) if not m else None
        if m:
            token = (m.group(1) or m.group(2)).lower()
            current_set = _SET_TOKEN.get(token, token)
            saw_marker = True
            rest = m.group(3)
        elif lm:
            label = lm.group(1).lower()
            current_set = _LABELED_ORDINAL.get(label) or str(last_num + 1)
            saw_marker = True
            rest = lm.group(2) or ""
        else:
            em = _ENCORE_LINE.match(line)
            if em:
                current_set = "encore"
                saw_marker = True
                rest = em.group(1)
            else:
                if _NOISE.search(line):
                    continue
                rest = line
        if current_set and current_set.isdigit():
            last_num = int(current_set)
        rest = _TRACK_PREFIX.sub("", rest)
        if enumerated:
            rest = _NUM_PREFIX.sub("", rest)
        for title, segue in _split_songs(rest):
            if len(title) > MAX_TITLE_LEN:
                continue  # implausibly long fragment - prose, not a song title
            if _is_junk_title(title):
                continue
            items.append(
                SetlistItem(
                    title=title,
                    normalized=normalize_song(title),
                    set=current_set or "1",
                    segue=segue,
                )
            )
    if saw_marker and len(items) >= 5:
        confidence = "high"
    elif len(items) >= 5:
        confidence = "medium"
    else:
        confidence = "low"
    return ParsedSetlist(items=items, confidence=confidence)
