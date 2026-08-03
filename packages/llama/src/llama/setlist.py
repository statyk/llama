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
# `_ENCORE_LINE` gets the same leading-decoration tolerance as the set
# markers above. This used to be withheld: recognizing "---encore:" as an
# encore marker is *correct*, but `parse_setlist`'s header truncation used to
# treat ANY first marker as the start of the setlist, so a correctly
# recognized encore marker sitting below a long tracklist would discard that
# whole tracklist as "header". That coupling is now discharged - see
# `_may_start_a_show` and the truncation block in `parse_setlist` below, which
# only lets a marker that could plausibly OPEN a show truncate anything an
# encore marker never can, so recognizing "---encore:" here is safe.
# `test_encore_rule_above_a_tracklist_does_not_truncate` still guards the
# combination.
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
_ENCORE_LINE = re.compile(
    rf"^{_LEAD_DECOR}" + r"(?:encore|e\d?)\s*(?::|-\s|$)\s*(.*)$", re.I)
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
# NOT the same regex as `structure._TRACK_PREFIX`, and deliberately so: this one
# strips prefixes off DESCRIPTION lines, that one matches them on TRACK titles,
# and the two vocabularies have diverged on purpose. Do not sync them.
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

# Personnel credit LINES: "Jerry Garcia - guitar", "Bruce Hornsby - Piano,
# Accordion", "Chris Whitley: vocals, guitar; Alan Gevaert: bass; Louie
# Lepore: guitar; Billy Ward: drums". A grammar, not a widened word list -
# see the measurement note on `_NOISE` below for why that distinction
# matters. One or more NAME + separator + INSTR-list ENTRYs, optionally
# `;`-joined, with a little leading/trailing decoration tolerated.
_CREDIT_INSTR = (
    r"guitars?|bass|drums?|vocals?|keyboards?|keys|piano|organ|percussion"
    r"|harmonica|harp|mandolin|mandola|fiddle|violin|viola|cello|banjo"
    r"|sax(?:ophone)?|trumpet|trombone|horns?|dobro|accordion|cowbell"
    r"|shakers?|tambourine|congas?|bongos|agogo|timbales?|flute|clarinet"
    r"|synth(?:esizer)?|moog|clavinet|rhodes|vibes|marimba|washboard"
    r"|ukulele|drumitar|b-?3|melodica|didgeridoo|tabla|theremin|guitarron"
    # "drumz" is a misspelling that appears in real credit lines - of the
    # 22 distinct description lines containing it across both measured
    # corpora, exactly one is a credit line: "Oteil Burbridge - bass &
    # vocals & drumz" (also a real example of the multi-instrument
    # connector case) - which is why it is listed here as an instrument
    # token - even though `Drumz` is also a SONG by standing domain ruling
    # (see the hazard note on `_NOISE` below), so the same word is
    # simultaneously credit vocabulary in one context and a title
    # elsewhere.
    r"|bells|beam|steel|drumz"
)
_CREDIT_MOD = (
    r"lead|rhythm|acoustic|electric|upright|backing|back-up|background"
    r"|pedal|lap|slide|hand|talking|bass|baritone|tenor|alto|soprano"
    r"|harmony|additional|second|hammond|grand|steel|12-string|six-string"
    r"|all|main|nylon|string|b-?3"
)
_CREDIT_PHRASE = rf"(?:(?:{_CREDIT_MOD})\s+){{0,3}}(?:{_CREDIT_INSTR})"
_CREDIT_JOIN = r"(?:\s*(?:,|&|\+|/|\band\b|\bw/\b)\s*)+"
_CREDIT_LIST = rf"{_CREDIT_PHRASE}(?:{_CREDIT_JOIN}{_CREDIT_PHRASE})*"
# NAME: any Unicode letter (not just A-Za-z - a real name like "Béla Fleck"
# is otherwise unreachable), and up to 3 further "words" each either an
# ordinary name-word or one short quoted nickname aside ('Brad "The EZB"
# Morgan'). Bounded-length quotes only (no wildcard growth), and this widens
# NAME alone - the `^...$` whole-line anchor around the whole grammar is
# untouched. Net corpus effect is folded into the `_NOISE` note below (866
# vs 853 total, items-gained down from 7 to 4) rather than stated standalone
# here: measured over all 31,923 distinct description lines, the widening
# newly drops 10 lines. 7 of those were NOT dropped by the pre-task-3 code -
# those 7 are precisely what moves the "853" figure to "866". The remaining
# 3 were ALREADY dropped by the pre-task-3 code via the same quoted-
# nickname/non-ASCII shape; they are the recovered residual that moved
# items-gained from 7 to 4.
# 0 tracks lost/re-pointed, 0 rows losing `align()` coverage, hazard probe
# clean (see `_NOISE`'s comment for the one pre-existing, already-accepted
# exception).
#
# The widening was ratified on the further measurement that it enlarges the
# already-accepted "<song title> - <instrument>" exposure class by exactly
# 10 real corpus titles (+100 synthetic acceptances over 14,817 real track
# titles x 10 instruments; 60,370 -> 60,470 - a +0.17% move inside a change
# that shrinks that same surface 32% versus the pre-branch code). The
# condition of that ratification was that the 10 titles be named here so
# the instance is on record:
#     'Béla Solo'      'Béla talks'     'Béla’s Banjo Demo'     'Cliché Guevara'
#     'Good Morning Aztlán'    'Más y Más'    'Más y más'    'Serenata Norteña'
#     'Simon Says "The Kingpin"'     'Simon Sayz "The Kingpin"'
# Every one is admitted for the same reason: a non-ASCII letter or a quoted
# aside. None of them is dropped standing alone - the exposure is only for
# the synthetic "<title> - <instrument>" whole-line shape.
_CREDIT_LETTER = r"[^\W\d_]"  # any Unicode letter: a "word" char, minus digits/underscore
_CREDIT_NAME_CHAR = rf"(?:{_CREDIT_LETTER}|[.'’\-])"
_CREDIT_NICK = r'"[^"\n]{1,24}"'  # a short quoted nickname aside
_CREDIT_NAME = (
    rf"{_CREDIT_LETTER}{_CREDIT_NAME_CHAR}*"
    rf"(?:\s+(?:{_CREDIT_NAME_CHAR}+|{_CREDIT_NICK})){{0,3}}"
)
_CREDIT_ENTRY = rf"{_CREDIT_NAME}\s*[-–—:]\s*{_CREDIT_LIST}"
# Leading decor also tolerates a literal `w/`/`#w/` prefix ("w/ Oteil
# Burbridge - bass" is a common "with guest X" phrasing) - a fixed literal
# alternative, not a wildcard, so it doesn't loosen the anchor itself.
_CREDIT_LINE = (
    rf"^[\s*\-–—]*(?:#?w/\s*)?{_CREDIT_ENTRY}(?:\s*;\s*{_CREDIT_ENTRY})*\s*[*#$%!.†‡]?\s*$"
)

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
    # Personnel credit lines (`_CREDIT_LINE` above). The WHOLE-LINE anchor
    # (`^...$`) is the false-positive guard here, not the instrument
    # vocabulary: a line is dropped only if EVERY token on it is a name, a
    # separator, a connector, a modifier or an instrument - nothing may be
    # left over. That is what keeps a bare "Drums" or "Space" song line (or
    # a set-break line like "Drums > Space") untouched, and it is why this
    # is a grammar rather than a widened word list: measured, the dominant
    # failure modes of the old dash-anchored rule were SHAPE, not
    # vocabulary (trailing decoration, a modifier between the dash and the
    # instrument, no space before the dash, a colon instead of a dash -
    # vocabulary alone was the smallest of five dimensions). Measured over a
    # combined 1841-row corpus (1121 Dead + 720 non-Dead), in-process
    # against the real parser and real `align()`: 866 junk items dropped
    # (453 Dead / 413 non-Dead - this figure includes the NAME widening
    # below), 0 tracks lost a match, 0 tracks re-pointed, 0 rows lost
    # `align()` coverage. One track GAINED a match (a curiosity on an
    # already-broken row, not a win worth relying on).
    #
    # This REPLACES the old dash-anchored alternative rather than adding
    # the new grammar alongside it, per the ruling - and that has one
    # measured, honestly-reported cost the original (additive) measurement
    # didn't surface: the old alternative used `.search()` with no leading
    # anchor, so it dropped a credit line through ANY prefix, decoration or
    # not. `_CREDIT_NAME`'s Unicode-letter/quoted-nickname/`w/`-prefix
    # tolerance (see its own comment above) recovers most of that - what's
    # left is 4 ITEMS (3 distinct lines) `_NOISE` still declines: ALL THREE
    # carry a leading footnote-number marker before "w/" ("1. w/ Donna Jean
    # Godchaux - vocals", "1. w/ Oteil Burbridge - bass", "2. w/ Anna Moss -
    # vocals, Joel Ludford - guitar"), and the third of those ALSO joins two
    # full NAME-instrument entries with a bare comma instead of `;`. Both
    # root causes sit OUTSIDE "widen NAME only" - the number-marker is a
    # leading-decor problem that interacts with the enumerated-tracklist
    # number-stripping logic, the bare-comma join is an entry-separator
    # problem that risks confusing the instrument-list comma with an
    # entry-list comma - so neither was attempted; per the "one attempt,
    # then stop" ruling on this widening, they are recorded here as
    # accepted residual rather than chased. None of the 4 is a real song
    # and none touches `align()` (still 0 tracks lost/re-pointed) - a
    # same-class, smaller-than-before residual, not a new hazard.
    #
    # Residual exposure, named rather than left implicit: this grammar
    # would accept a synthetic whole-line "Space - Drums" or "Jam - Drums"
    # (a SONG title, a dash, an instrument word) - `Space` and `Drums` are
    # songs by standing domain ruling. Measured at 0 occurrences of that
    # WHOLE-LINE shape across 1841 real descriptions (both corpora), which
    # is why this is an accepted risk rather than a blocker - it is not
    # evidence the case cannot occur. A related but distinct case is
    # nonzero and NOT a false positive: a tail COMPONENT of a correctly
    # dropped multi-instrument credit line can textually equal a real song
    # title - e.g. "Oteil Burbridge - vocals, bass, drums" is correctly
    # dropped on tapes whose track list also contains a real "Drums" track.
    # The drop is still correct (the line as a whole is credit-shaped, not
    # the standalone song) and `align()` is unaffected; it just means the
    # "0 occurrences" above is scoped to the whole-line hazard shape, not
    # to every string that could ever appear as a substring of a dropped
    # line.
    rf"|{_CREDIT_LINE}"
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

# Emitted-title junk, three classes:
#   1. a bare or bracketed duration, or 2. a disc marker, that survived
#      line-level noise filtering because it sat inside a comma-separated run
#      (e.g. a comma-separated "Set 1: Bertha, Disc Two, Sugaree" line never
#      reaches the line-level _NOISE check at all, since the line matched
#      _SET_LINE first). Word-numeral disc markers get the same treatment as
#      _NOISE's, for the same reason.
#   3. a "Total time"/"Total Time" summary line — a different animal from the
#      first two: it is a whole line _NOISE simply does not cover (it doesn't
#      match _NOISE's patterns and isn't dropped as a comma-run survivor), not
#      a title that leaked through a comma-separated run. Widened to match
#      any item whose title STARTS with "total time"/"total running time"
#      (optionally inside an opening bracket), with no constraint on what
#      follows: measured, the narrower `total time[:=]<duration>` shape left
#      21 total-time items surviving corpus-wide in forms it didn't cover
#      (`[Total Time 1:47:37]`, `Total Time ~ 03:17:25.981`, `Total Time-
#      97:30`, bare `Total Time`, `Total running time [79:48]` with no
#      `[:=]` separator at all, `Total Running Time TRT 46:29`...). Kept
#      ITEM-level rather than folded into `_NOISE`'s line-level rule: two of
#      the 21 are the remainder of a line after a `Set One:`/`Set Two:`
#      marker (`_NOISE` never sees that text - the marker branch takes the
#      line before `_NOISE` is consulted), so only an item-level rule
#      reaches all 21; every one of the 21 is a whole single emitted item,
#      so item-level loses nothing; and unlike a line-level rule, this one
#      cannot take a glued-on song down with it. Measured: 21/21 of the
#      residue dropped, 0 tracks lost a match, 0 items gained. Declines
#      `Total Eclipse Of The Heart` and `Totally Wired` - "total" must be
#      followed by whitespace then "time" (optionally "running time"), so
#      neither the missing space in "Totally" nor the unrelated word
#      "Eclipse" can satisfy it.
# Kept as a SEPARATE regex, not merged with _NOISE's, since the two guard
# different paths (whole line vs. a title surviving a comma run) and a shared
# regex would blur that distinction for a future maintainer.
_JUNK_TITLE = re.compile(
    r"^[(\[]?\d{1,3}[:.]\d{2}[)\]]?$"
    r"|^discs?\s*#?\s*(?:\d+|one|two|three|four|five|six|i{1,3})$"
    r"|^\[?\s*total\s+(?:running\s+)?time\b",
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


# A block above a non-show-starting marker is kept when it parses to at least
# this many items on its own - the parser's own confidence floor. Below it, the
# block is junk (track-number stubs, a duration header) and truncating is right.
_RECOVER_FLOOR = 5


def _may_start_a_show(line: str) -> bool:
    """True when this marker could plausibly be the FIRST marker of a show.

    "Set 1" can. An encore marker cannot - no show opens with its encore - and
    neither can "Set 2". A labeled set line whose ordinal the parser does not
    recognize resolves to set 1 in the parse loop below, so it gets the same
    answer here rather than a second, divergent opinion.
    """
    m = _SET_LINE.match(line)
    if m:
        token = (m.group(1) or m.group(2)).lower()
        return _SET_TOKEN.get(token, token) == "1"
    lm = _LABELED_SET_LINE.match(line)
    if lm:
        return _LABELED_ORDINAL.get(lm.group(1).lower(), "1") == "1"
    return False


def _emit_items(raw_lines: list[str]) -> tuple[list[SetlistItem], bool]:
    """Turn already-preprocessed lines into items. Returns (items, saw_marker).

    This is the whole body of the parse, MINUS preprocessing and MINUS
    truncation - which is the point. `parse_setlist` calls it once on the
    post-truncation lines, and the recovery probe calls it once on the block
    above a non-show-starting marker; neither call can re-run `html.unescape`
    or tag stripping, and neither can truncate.

    That structure is load-bearing, not tidiness. The probe used to recurse
    into `parse_setlist`, on the argument that "the block contains no markers
    by construction" - which is FALSE. Preprocessing runs `<br>` substitution
    BEFORE `html.unescape`, so an escaped `&lt;br&gt;` survives the first pass
    as the literal text `<br>` and a second pass converts it to a line break,
    manufacturing a marker inside the probe's own input. The probe then
    truncated, fell under the floor, and the outer parse discarded the real
    songs. The general statement of the hazard, which is why the fix is
    structural rather than a "no markers after unescaping" check: THE PROBE IS
    A PROXY AND NOT A FAITHFUL ONE - it asks what the parser would make of the
    block in isolation, and the block is never parsed in isolation.
    """
    # Everything here - the inline split, the enumerated gate and the parse
    # loop alike - operates on post-truncation, post-split lines.
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
    return items, saw_marker


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
    # cached LMA descriptions, that cost 31 descriptions their setlists (28 of
    # them losing >10 items and collapsing to an encore-only parse). Doing the
    # split after truncation makes split-created markers structurally incapable
    # of truncating anything - no provenance tracking needed.
    raw_lines = [ln.strip() for ln in text.splitlines()]
    first_marker = next(
        (i for i, ln in enumerate(raw_lines)
         if _SET_LINE.match(ln) or _LABELED_SET_LINE.match(ln) or _ENCORE_LINE.match(ln)),
        None,
    )
    if first_marker is not None and not _may_start_a_show(raw_lines[first_marker]):
        # The marker cannot open a show, so the block above is the main body,
        # not a header. Probe it with `_emit_items`, which has no truncation
        # step and does no preprocessing - see that function's docstring for
        # why "the block contains no markers by construction" was false.
        above = [ln for ln in raw_lines[:first_marker] if ln]
        if len(_emit_items(above)[0]) >= _RECOVER_FLOOR:
            first_marker = None
    if first_marker is not None:
        raw_lines = raw_lines[first_marker:]
    items, saw_marker = _emit_items(raw_lines)
    if saw_marker and len(items) >= 5:
        confidence = "high"
    elif len(items) >= 5:
        confidence = "medium"
    else:
        confidence = "low"
    return ParsedSetlist(items=items, confidence=confidence)
