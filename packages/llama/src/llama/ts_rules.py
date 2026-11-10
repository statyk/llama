"""Pure policy rules for allowlisted Taper's Section artists.

One classifier, one exclude matcher and one date cross-check, shared by search,
select and gather. LMA classification (`scoring.lineage_class`) is untouched.
"""
from __future__ import annotations

import html
import re
from datetime import date as _date
from typing import Literal

from llama.config import TaperssectionArtist
from llama.models import RecordingSummary

LineageClass = Literal["aud", "sbd", "matrix", "fm", "webcast", "unknown"]

# Set after Checkpoint A (spec "Lineage classification"): "a" keeps a tape with
# no evidence unknown (it holds); "b" reads it as aud.
RULE: Literal["a", "b"] = "a"

# Microphone makes and models. A mic in a source chain is positive evidence of
# an audience recording (a board feed has no capsule). Tokens only: the text is
# split on non-alphanumerics, so "MK4" and "CMC6/MK41" yield "mk4", "cmc6",
# "mk41"; "B&K 4011" yields "4011".
MIC_WORDS: frozenset[str] = frozenset({
    "schoeps", "cmc6", "cmc64", "cmc641", "mk2", "mk21", "mk22", "mk4", "mk41", "mk5", "mk3",
    "mk6", "mk8", "mk012", "ccm4", "ccm41", "ccm5",
    "akg", "c414", "c451", "c451b", "ck1", "ck61", "ck91", "c460", "c480",
    "dpa", "4006", "4007", "4003", "4011", "4015", "4021", "4022", "4023", "4060", "4061", "4062",
    "neumann", "km130", "km131", "km140", "km143", "km84", "km184", "ak40", "ak43", "u87",
    "sennheiser", "mkh", "mkh20", "mkh30", "mkh40", "mkh60", "mkh70", "mkh80", "mkh800",
    "mkh8020", "mkh8040", "mkh8050", "me66", "me64",
    "bk", "audiotechnica", "at853", "at831", "at4051", "at4041", "at933", "at4022",
    "josephson", "c617", "c42", "sanken", "cos11", "cos11d", "ecm", "ecm909", "ecm959",
    "oktava", "earthworks", "qtc", "qtc40", "qtc1", "gefell", "m296", "rode", "nt5", "nt55",
    "microphone", "mics", "mic", "capsules", "omni", "cardioid", "hypercardioid",
    "cm100", "cm300", "cm700",  # Nakamichi mics ("CM-300" splits to cm, 300: see _NAK_MIC)
})
# Purely numeric mic models collide with 4-digit shnids in identifiers
# ("ph1994-06-22.4061.flac16"), so they count only outside the identifier.
_NUMERIC_MICS = frozenset(w for w in MIC_WORDS if w.isdigit())
_NAK_MIC = ({"cm"}, {"100", "300", "700"})

# Taper positions and audience words. "fob" (front of board), "ots", "dfc"
# (directly from center) and friends say where the mics stood, which only an
# audience taper reports (dfob/nfob = direct/near front of board, dfa = direct
# from audience); "aud"/"audience" name the lineage itself. The phrase "taper
# section" is matched separately in classify via _has_phrase; a bare "taper"
# is a credit ("taper: Bob Smith"), not a position, so it is not listed.
POSITION_WORDS: frozenset[str] = frozenset({
    "fob", "dfob", "nfob", "ots", "dfc", "dfa", "tapersection",
    "aud", "audience",
})

# Recorders, decks and transfer gear. They appear in board feeds and audience
# rigs alike, so they are never evidence for aud (or for any class). Listed so
# the exclusion is explicit and tested (disjoint from the two sets above).
# Documentation/disjointness only: it never adds evidence.
DECK_WORDS: frozenset[str] = frozenset({
    "dat", "tascam", "sony", "744t", "722", "788t", "702", "nakamichi", "nak", "cassette",
    "minidisc", "md", "r09", "r-09", "edirol", "zoom", "marantz", "hhb", "da3", "da20",
    "pcm", "pcmd50", "dr2d", "dr100", "sound", "devices", "sv", "sx", "cd", "lc3", "sbm1",
    "sonosax", "usb", "flac", "wav", "shn", "cdr", "reel", "deck",
})

_SOURCE_LINE = re.compile(r"^(sources?|src|lineage|transfers?)\b", re.I)
_BREAK = re.compile(r"<\s*br\s*/?\s*>|<\s*/?\s*(?:p|div)\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]*>")
_TOKEN = re.compile(r"[a-z0-9]+")

# In-line source labels (Checkpoint A ruling (B)). The archive.org scrape serves
# every description with its line breaks and tags collapsed, so a line-anchored
# reader sees one line. A description with no line break is instead split at
# in-line labels: Source(s)( info/information), Src, Lineage, Transfer(s).
_INLINE_LABEL = re.compile(
    r"(?<![a-z0-9])(?:sources?(?:\s+info(?:rmation)?)?|src|lineage|transfers?)\s*:", re.I)
# A label preceded by one of these words introduces a fill or splice source, or is
# prose ("I spliced in the missing portion with the following source: SBD > DAT",
# "Patch Source: ..."): it does not describe the tape, so it is not read.
_FILL_WORDS = frozenset({"following", "patch", "patched", "fill", "fills", "filler",
                         "splice", "spliced"})
_PREV_WORD = re.compile(r"([A-Za-z]+)\W{0,3}$")
# A segment ends at the next in-line source label, the next "Label:"-shaped
# token (one word, then a colon, not a URL), the start of a setlist, or at
# SEGMENT_CAP characters, whichever comes first.
_NEXT_LABEL = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z']{0,24}\s*:(?!//)")
# Not after "(": "(Set 1) AKG c460b ...", "DPA4018 (Set1: OTS ...)" annotate a
# per-set source inside the chain. A numbered list is "1. Title" ("1)" also
# numbers sources: "(Source 1) Schoeps ...").
_SETLIST_START = re.compile(
    r"(?<![a-z0-9(])(?:[sd]\d{1,2}t\d{1,2}"
    r"|set\s*(?:[1-4]|i{1,3}|iv|one|two|three|four)(?![a-z0-9])"
    r"|dis[ck]\s*(?:[1-4]|one|two|three|four)(?![a-z0-9])"
    r"|encore(?![a-z])|\*+\s*setlist"
    r"|0?1\.\s+[a-z]|01\s*-\s)",
    re.I)
# A setlist marker this close to the label is part of the source text, not
# after it ("source: set 1 = (FOB) Schoeps ...", "Source info: 1) Neumann ...").
_SETLIST_MIN_OFFSET = 3
SEGMENT_CAP = 200

_SBD_WORDS = {"sbd", "dsbd", "soundboard", "board"}
# "Band Source AKG C1000s (direct from Phish's mic source)": the band's own feed.
_SBD_PHRASES = ({"band"}, {"source", "feed"})
# Checkpoint A ruling (C): "patch"/"patched" is a splice edit or a digital copy in
# taper text ("Samplitude (patch, fades)", "Patch DAT(m) provided by"); it reads
# sbd only with board context in the same field.
_PATCH_WORDS = {"patch", "patched"}
_BOARD_CONTEXT = _SBD_WORDS | {"console", "desk"}
_MATRIX_WORDS = {"matrix", "mtx"}
# Broadcasts read fm (ruling (C), labelling convention (D): broadcast = fm).
# "radio" is deliberately absent: Radio Shack mics are audience gear.
_FM_WORDS = {"fm", "prefm", "broadcast", "broadcasts", "dishnetwork", "simulcast"}
# Weak broadcast words: "satellite" is also a laptop ("Toshiba Satellite") and
# "DSS" a chain component ("Schoeps MK41 > DSS > Tascam"), so they read fm only
# on a tape with no audience evidence ("NBC Ku-band satellite feed > DAT").
_FM_WEAK_WORDS = {"dss", "satellite"}
_FM_PHRASES = ({"dish"}, {"network"})
_WEBCAST_WORDS = {"webcast", "stream", "streamed", "streaming", "livestream"}


def _inline_segments(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text)
    out = []
    for m in _INLINE_LABEL.finditer(text):
        prev = _PREV_WORD.search(text[max(0, m.start() - 30):m.start()])
        if prev and prev.group(1).lower() in _FILL_WORDS:
            continue
        rest = text[m.end():m.end() + SEGMENT_CAP]
        stops = [x.start() for x in (_INLINE_LABEL.search(rest), _NEXT_LABEL.search(rest),
                                     _SETLIST_START.search(rest, _SETLIST_MIN_OFFSET)) if x]
        body = rest[:min(stops)] if stops else rest
        body = body.strip().rstrip("~-*#|,;").strip()
        if body:
            out.append(f"{m.group(0)} {body}")
    return out


def source_lines(description: str | None) -> list[str]:
    """The source text of a description (after HTML to text).

    A description with line breaks: the lines starting with
    Source/Src/Lineage/Transfer. The `\\b` in the pattern deliberately excludes
    "Transferred by..." and "Sourcery", which are credits or prose, not source
    chains. A description with no line break (what the archive.org scrape
    serves): one segment per in-line label, bounded (see `_inline_segments`).
    """
    if not description:
        return []
    text = _TAG.sub("", _BREAK.sub("\n", description))
    text = html.unescape(text)
    # The reader is chosen on whether the text has ANY line break: a partly-broken
    # description whose labels sit mid-line takes the line reader and misses them.
    # That costs recall (the tape stays unknown and holds), never a false ship.
    if "\n" not in text.strip():
        return _inline_segments(text)
    out = []
    for line in text.splitlines():
        line = line.strip()
        if _SOURCE_LINE.match(line):
            out.append(line)
    return out


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


# Checkpoint A ruling (C): a board named as where the mics stood is a position,
# not a source ("Dead center behind soundboard", "in sbd b00th", "right of SBD",
# "at sbd", "@sbd-7", "20' in front of the board"). The match is blanked before
# tokenizing, so it yields no sbd marker; the mic chain then decides.
_BOARD = r"(?:sbd|soundboard|sound\s*board|board)"
_BOARD_POSITION = re.compile(
    r"(?<![a-z0-9])(?:behind|in\s+front\s+of|front\s+of|near|beside|next\s+to|above|inside|at|by"
    r"|(?:side|sides|corner|right|left|rear|back|front|center|centre)\s+of)"
    rf"\s*(?:the\s+)?{_BOARD}(?![a-z0-9])"
    rf"|@\s*(?:the\s+)?{_BOARD}(?![a-z0-9])"
    rf"|(?<![a-z0-9]){_BOARD}\s*(?:booth|b00th|rail|riser|area|platform|tower|cage)(?![a-z0-9])",
    re.I)
# Not source evidence at all: a lighting board ("Front Left corner of light
# board") is not a sound board, and Audio Magic's "X-Stream" is a mic cable, not
# a stream. Blanked before tokenizing.
_NOT_EVIDENCE = re.compile(
    r"(?<![a-z0-9])(?:light(?:ing)?\s*board|x\s*-?\s*stream)(?![a-z0-9])", re.I)
# The band's own feed: "AKG C1000s > DAT (direct from Phish's mic source)" (the
# 2000 Japan tapes; siblings call the same chain "Band Source" and "DSBD+AUD
# Matrix Mix"). Rewritten to a board word, so it reads sbd (matrix with a matrix
# word beside it).
_BAND_FEED = re.compile(
    r"['’]s\s+mic\s+source|(?<![a-z0-9])direct\s+from\b[^.>]{0,40}?\bmic\s+source", re.I)


def _field_tokens(text: str) -> list[str]:
    """Tokens of one evidence field, as classify reads them.

    Lighting boards and X-Stream cables, then board positions, are blanked; a
    band mic-source phrase becomes "sbd"; a compound matrix token is split ("akgmatrix",
    "30akgmatrix", "dhaudmatrix" -> its rig prefix, plus "aud" when the prefix
    ends in aud, plus "matrix"); "mtx" before "191..." is the Neumann RSM-191's
    M/S matrix box, a microphone part, not a matrix of sources.
    """
    text = _BOARD_POSITION.sub(" ", _NOT_EVIDENCE.sub(" ", text))
    raw = _tokens(_BAND_FEED.sub(" sbd ", text))
    out: list[str] = []
    for i, t in enumerate(raw):
        if t == "mtx" and i + 1 < len(raw) and raw[i + 1].startswith("191"):
            out.append("neumann")  # the RSM-191 system; Neumann makes only mics here
            continue
        if t.endswith("matrix") and len(t) > len("matrix"):
            prefix = t[: -len("matrix")].lstrip("0123456789")
            if prefix:
                out.append(prefix)
                if prefix.endswith("aud"):
                    out.append("aud")
            out.append("matrix")
            continue
        out.append(t)
    return out


def _evidence_text(rec: RecordingSummary) -> list[str]:
    parts = [rec.identifier, rec.title, rec.source or "", rec.lineage or ""]
    parts.extend(source_lines(rec.description))
    return parts


def _has_phrase(toks: list[str], first: set[str], second: set[str]) -> bool:
    return any(a in first and b in second for a, b in zip(toks, toks[1:]))


def _non_id_list(rec: RecordingSummary) -> list[str]:
    toks: list[str] = []
    for part in _evidence_text(rec)[1:]:
        toks.extend(_field_tokens(part))
        toks.append("|")
    return toks


def classify(rec: RecordingSummary) -> LineageClass:
    parts = _evidence_text(rec)
    fields = [_field_tokens(p) for p in parts]
    toks: list[str] = []
    for f in fields:
        toks.extend(f)
        toks.append("|")  # fields never form a phrase across a boundary
    s = set(toks)
    # numeric mic models count outside the identifier only
    non_id = {t for f in fields[1:] for t in f}
    markers = set()
    if s & _MATRIX_WORDS:
        markers.add("matrix")
    if (s & _SBD_WORDS or _has_phrase(toks, *_SBD_PHRASES)
            or any(set(f) & _PATCH_WORDS and set(f) & _BOARD_CONTEXT for f in fields)):
        markers.add("sbd")
    if s & _WEBCAST_WORDS:
        markers.add("webcast")
    usable = s - DECK_WORDS
    mics = (usable & (MIC_WORDS - _NUMERIC_MICS)) | ((non_id - DECK_WORDS) & _NUMERIC_MICS)
    aud = bool(
        mics
        or usable & POSITION_WORDS
        # "taper section", "tapers section", "Taper's Section" (apostrophe splits to taper, s)
        or _has_phrase(toks, {"taper", "tapers"}, {"section"})
        or any(a == "taper" and b == "s" and c == "section"
               for a, b, c in zip(toks, toks[1:], toks[2:]))
        or _has_phrase(_non_id_list(rec), *_NAK_MIC)
    )
    if s & _FM_WORDS or _has_phrase(toks, *_FM_PHRASES) or (s & _FM_WEAK_WORDS and not aud):
        markers.add("fm")
    if "matrix" in markers:
        # Checkpoint A ruling (C): matrix only when board and audience are both
        # indicated. A matrix word with audience evidence and no board, fm or
        # webcast marker is a mix of audience rigs ("AKG 414/AT 4031 Matrix"):
        # aud. A bare matrix word with no other evidence keeps the convention.
        if markers & {"sbd", "fm", "webcast"} or not aud:
            return "matrix"
        return "aud"
    for cls in ("sbd", "fm", "webcast"):
        if cls in markers:
            return cls  # a marker beats gear
    return "aud" if aud else "unknown"


def excluded(rec: RecordingSummary, entry: TaperssectionArtist) -> bool:
    hay = " ".join(
        [rec.identifier, rec.title, rec.source or "", *source_lines(rec.description)]
    ).casefold()
    return any(t.strip() and t.casefold() in hay for t in entry.exclude)


# --- date cross-check -------------------------------------------------------

_YMD = re.compile(r"(?<!\d)((?:19|20)\d\d)([-.])(\d\d)\2(\d\d)(?!\d)")
_MDY = re.compile(r"(?<!\d)(\d{1,2})([-/])(\d{1,2})\2((?:19|20)\d\d)(?!\d)")
_TOKEN_YYMMDD = re.compile(r"^([a-z]{2,12})(\d\d)(\d\d)(\d\d)$")
_TOKEN_YYYYMMDD = re.compile(r"^([a-z]{2,12})((?:19|20)\d\d)(\d\d)(\d\d)$")
_YY_SEP = re.compile(r"(?<![a-z0-9])([a-z]{2,12})(\d\d)([-.])(\d\d)\3(\d\d)(?!\d)", re.I)
# Prefixes that are formats or lineage words, never an artist: "flac192000".
_NOT_ARTIST = {"flac", "mp", "mp3", "shn", "shnf", "wav", "sbd", "aud", "fm", "mtx", "dat",
               "cd", "md", "vbr", "kbps", "bit", "track", "disc", "set", "ogg", "m4a",
               "shnid", "etree", "id", "lma", "vol", "archive", "gdadt", "dt"}


def _iso(y: int, m: int, d: int) -> str | None:
    try:
        return _date(y, m, d).isoformat()
    except ValueError:
        return None


def _year2(yy: int) -> int:
    return 1900 + yy if yy >= 50 else 2000 + yy


def dates_claimed(identifier: str, title: str) -> set[str]:
    out: set[str] = set()
    for text in (identifier, title):
        for m in _YMD.finditer(text):
            iso = _iso(int(m[1]), int(m[3]), int(m[4]))
            if iso:
                out.add(iso)
        for m in _MDY.finditer(text):
            iso = _iso(int(m[4]), int(m[1]), int(m[3]))
            if iso:
                out.add(iso)
        for tok in _tokens(text):
            m = _TOKEN_YYMMDD.match(tok)
            if m and m[1] not in _NOT_ARTIST:
                iso = _iso(_year2(int(m[2])), int(m[3]), int(m[4]))
                if iso:
                    out.add(iso)
            m = _TOKEN_YYYYMMDD.match(tok)
            if m and m[1] not in _NOT_ARTIST:
                iso = _iso(int(m[2]), int(m[3]), int(m[4]))
                if iso:
                    out.add(iso)
        for m in _YY_SEP.finditer(text):
            if m[1].lower() in _NOT_ARTIST:
                continue
            iso = _iso(_year2(int(m[2])), int(m[4]), int(m[5]))
            if iso:
                out.add(iso)
    return out


def date_disagrees(rec: RecordingSummary) -> bool:
    claimed = dates_claimed(rec.identifier, rec.title)
    return bool(claimed) and (rec.date or "")[:10] not in claimed


def in_active_window(date: str, entry: TaperssectionArtist) -> bool:
    d = date[:10]
    if entry.active_from and d < entry.active_from:
        return False
    if entry.active_until and d > entry.active_until:
        return False
    return True


def allowed(
    rec: RecordingSummary, entry: TaperssectionArtist, *, rule: Literal["a", "b"]
) -> Literal["allowed", "forbidden", "unknown"]:
    if set(entry.lineages) >= {"aud", "sbd", "matrix", "fm", "webcast"}:
        return "allowed"
    cls = classify(rec)
    if cls == "unknown":
        if rule == "a":
            return "unknown"
        cls = "aud"
    return "allowed" if cls in entry.lineages else "forbidden"


def verdict(rec: RecordingSummary, entry: TaperssectionArtist) -> Literal["allowed", "forbidden", "unknown"]:
    """allowed | forbidden | unknown under the entry, with the shipped rule. "forbidden"
    also covers a tape matching one of the entry's `exclude` terms. The one verdict
    select (the per-tape policy filter) and gather (the lineage hold, the forbidden
    re-check) both use."""
    if excluded(rec, entry):
        return "forbidden"
    return allowed(rec, entry, rule=RULE)
