import html
import re

from llama.models import ParsedSetlist, SetlistItem
from llama.songs import normalize_song

# Set headers are routinely written with decorative rules around them:
# "- Set One -", "-----Set 1-----", "* Early Set:". Tolerate a leading run of
# dashes/asterisks (and any spaces between them) before a LINE-START marker,
# so such a header is recognized where it sits instead of being missed - a
# missed header means no truncation point, and the band/venue/lineage block
# above it gets parsed as songs (measured: ruthiefoster2007-02-25.blues gained
# 11 junk items that way, and an inflated setlist is exactly what pushes the
# alignment two-pointer out of its window).
#
# Deliberately NARROW: dashes and asterisks only, never arbitrary leading
# punctuation. Widening it would let ordinary annotations ("(2) Set closer
# was...") and prose bullets pose as set headers.
#
# LINE-START recognition only. `_INLINE_MARKER` is intentionally NOT given this
# tolerance: mid-line it has only whitespace to anchor on, and a bare dash run
# mid-sentence is punctuation far more often than it is a header.
#
# SET MARKERS ONLY - `_ENCORE_LINE` is deliberately NOT given this prefix, and
# that omission is COUPLED, not caution. Recognizing "---encore:" as an encore
# marker is *correct*; it is harmful only because `parse_setlist`'s header
# truncation would then treat that correct recognition as the start of the
# setlist and discard everything above it. Measured: enabling it costs
# nmas2013-02-13 26 real songs (32 items -> 6), and 149 of 923 cached LMA
# descriptions already sit in that first-marker-is-an-encore shape. The encore
# half is built and measured and must land WITH the truncation fix, never
# before it - same coupling as fuzzy matching needing evidence-triggered
# anchoring alongside it. `test_encore_rule_above_a_tracklist_does_not_truncate`
# is the guard that fails loudly if someone enables it early.
#
# The run is zero-width-satisfiable, so every undecorated header matches
# exactly as it did before. It is a single character class rather than a nested
# quantifier (`(?:[-*]+\s*)*`) so matching stays linear on long dash rules.
_LEAD_DECOR = r"[-–—*\s]*"

_SET_LINE = re.compile(
    rf"^{_LEAD_DECOR}(?:set\s*(one|two|three|i{{1,3}}|[123])"
    r"|([123])(?:st|nd|rd)\s+set)\s*[:\-]?\s*(.*)$",
    re.I,
)
# Labeled set headers: "Early Set - Grove Stage", "Acoustic Set: Ripple, ...".
# Header-shaped only — the label word starts the line and "set" is followed by
# a colon (inline songs), a dash (stage/venue label, never songs), or the line
# end — so prose like "Early set highlights include..." never matches.
# Ordinal labels carry their own number; the rest get sequential numbers in
# order of appearance.
_LABELED_SET_LINE = re.compile(
    rf"^{_LEAD_DECOR}(first|second|third|early|late|opening|closing|acoustic"
    r"|electric|morning|afternoon|evening)\s+set\b\s*(?::\s*(.*)|[-–—].*)?$",
    re.I,
)
_LABELED_ORDINAL = {"first": "1", "second": "2", "third": "3"}
_ENCORE_LINE = re.compile(r"^(?:encore|e\d?)\s*(?::|-\s|$)\s*(.*)$", re.I)
# A set/encore marker mid-line ("... Bertha Set II: Playin' ...") starts a new
# set: break the line there. Inline markers must carry a colon or a dash
# followed by space - unlike line-start markers - so prose like "the second
# set" never splits a title.
#
# The encore digit is OPTIONAL, matching _ENCORE_LINE's "e\d?": a bare "E:"
# mid-line is the single most common encore marker in LMA descriptions, and
# requiring the digit left the encore songs labelled with the preceding set.
_INLINE_MARKER = re.compile(
    r"\s+(?=(?:set\s*(?:one|two|three|i{1,3}|[123])|[123](?:st|nd|rd)\s+set"
    r"|encore|e\d?)\s*(?::|-\s))",
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

# Lines that are lineage/provenance chatter, not songs. Checked before song splitting.
_NOISE = re.compile(
    r"(recorded|transfer|lineage|source|taper|shnid|seeded|thanks|conversion|remaster"
    r"|\bsbd\b|\bdat\b|\bflac\b|\bshn\b|cassette|master reel|\bvia\b|d\d+t\d+\s*$"
    # Disc markers, digit form ("Disc #2") and word-numeral form ("Disc Two",
    # "Disc II") - archive.org descriptions use both conventions. Measured:
    # word-numeral form newly catches 37 distinct/44 occurrences (Dead) and
    # 16 distinct/54 occurrences (non-Dead) of pure junk, 0 false positives
    # on real songs. Two known casualties, 2 occurrences against that 98:
    # a noise line with a real song glued onto it in the same physical line
    # ("Disc Two 1. Eyes of the World", "5. Drums Set Two Disc Three
    # 1. Space") loses the glued-on song too, since a whole matching line is
    # dropped outright below. Same compound-heuristic class as the
    # _TRACK_PREFIX/_NUM_PREFIX composition note above - an accepted trade,
    # not a clean win.
    r"|\bdiscs?\s*#?\s*(?:\d|one|two|three|four|five|six|i{1,3}\b)"
    # "Jerry Garcia - guitar", "Bill Kreutzmann - drums": a name, a dash, an
    # instrument. Anchored on the dash so a bare "Drums" song line is untouched.
    r"|[a-z]\s+[-–—]\s*(?:guitar|bass|drums?|vocals?|keyboards?|piano"
    r"|organ|percussion|harmonica|mandolin|fiddle|banjo|sax(?:ophone)?)\s*$"
    r"|^comments?\b)",
    re.I,
)


def _enumerated_prefix(lines: list[str]) -> bool:
    """True when at least 3 lines begin with a number followed by
    punctuation or whitespace and then a non-space character, i.e. the
    description is a numbered tracklist rather than prose containing a
    numeric title. The punctuation-or-space requirement is load-bearing:
    without it, a multi-digit title truncated by `\\d{1,3}`'s 3-digit cap
    (e.g. "1952 Vincent Black Lightning" -> "195") would count as a
    numbered line.

    Lines `_NOISE` will discard are excluded from the count too. This is
    defensive hardening, not a fix for a measured corpus problem: a line
    the parser is about to discard anyway (lineage/provenance chatter
    matching `_NOISE`, e.g. "1 SBD source", "3 FLAC files seeded by taper")
    should not get a vote on whether the description is an enumerated
    tracklist, on principle - it would otherwise open the gate on its own
    on a description with no real numbered tracklist at all, corrupting
    real digit-leading titles that happen to share the description. Rows
    with >=3 digit-leading format-chatter lines `_NOISE` does NOT already
    catch are measured at 0 across both corpora, but that is not evidence
    the scenario can't occur: the corpus stores post-parse setlists, so any
    line `_NOISE` already dropped is structurally invisible to it - this
    change's true effect is unmeasurable by that instrument, not
    measured-zero."""
    return sum(1 for ln in lines if _NUM_LINE.match(ln) and not _NOISE.search(ln)) >= 3


_SET_TOKEN = {"one": "1", "two": "2", "three": "3", "i": "1", "ii": "2", "iii": "3"}

# Emitted-title junk: a bare duration or a disc marker that survived line-level
# noise filtering because it sat inside a comma-separated run (e.g. a
# comma-separated "Set 1: Bertha, Disc Two, Sugaree" line never reaches the
# line-level _NOISE check at all, since the line matched _SET_LINE first).
# Word-numeral disc markers get the same treatment as _NOISE's, for the same
# reason - kept as a SEPARATE regex, not merged with _NOISE's, since the two
# guard different paths (whole line vs. a title surviving a comma run) and a
# shared regex would blur that distinction for a future maintainer.
_JUNK_TITLE = re.compile(
    r"^\(?\d{1,3}[:.]\d{2}\)?$"
    r"|^discs?\s*#?\s*(?:\d+|one|two|three|four|five|six|i{1,3})$",
    re.I,
)


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
    # ORDER IS LOAD-BEARING: truncate the header first, split inline markers
    # second. If any set/encore marker exists, the setlist starts there: header
    # lines above (band name, venue, lineage) must not be parsed as songs - but
    # only a marker that ALREADY starts a line in the source may make that call.
    # Splitting first manufactures new lines, and a manufactured marker line
    # deciding where the setlist begins is catastrophic: a correct encore marker
    # embedded in a numbered tracklist ("21. E: Laziest Encore Ever") becomes the
    # first _ENCORE_LINE match, so header truncation discards the entire setlist
    # above it and everything surviving is labelled `encore`. Measured over 923
    # cached LMA descriptions: this fix alone (059c549) improved 34 descriptions
    # (dead=5, nondead=29 - the defect is overwhelmingly a non-Dead phenomenon:
    # Spin Doctors, Los Lobos, Drive-By Truckers, Blues Traveler tapes with an
    # inline "E:") and regressed 1 (spindoctors1994-06-13, fully recovered by
    # the later dash-tolerance fix). On the shipped tree (HEAD) the net is 31
    # improved / 0 regressed, 29 of the 31 recovering from an encore-only
    # collapse of >10 items; 0 songs lost anywhere, in either state. Doing the
    # split after truncation makes split-created markers structurally incapable
    # of truncating anything - no provenance tracking needed.
    raw_lines = [ln.strip() for ln in text.splitlines()]
    first_marker = next(
        (i for i, ln in enumerate(raw_lines)
         if _SET_LINE.match(ln) or _LABELED_SET_LINE.match(ln) or _ENCORE_LINE.match(ln)),
        None,
    )
    if first_marker is not None:
        raw_lines = raw_lines[first_marker:]
    # Everything downstream - the enumerated gate and the parse loop alike -
    # operates on the post-truncation, post-split lines, exactly as before.
    lines = [ln.strip() for ln in _INLINE_MARKER.sub("\n", "\n".join(raw_lines)).splitlines()]
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
