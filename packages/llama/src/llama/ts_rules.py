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

_SBD_WORDS = {"sbd", "soundboard", "board", "patch", "patched"}
_MATRIX_WORDS = {"matrix", "mtx"}
_FM_WORDS = {"fm", "prefm"}
_WEBCAST_WORDS = {"webcast", "stream", "streamed", "streaming", "livestream"}


def source_lines(description: str | None) -> list[str]:
    """Lines starting with Source/Src/Lineage/Transfer (after HTML to text).

    The `\\b` in the pattern deliberately excludes "Transferred by..." and
    "Sourcery", which are credits or prose, not source chains.
    """
    if not description:
        return []
    text = _TAG.sub("", _BREAK.sub("\n", description))
    text = html.unescape(text)
    out = []
    for line in text.splitlines():
        line = line.strip()
        if _SOURCE_LINE.match(line):
            out.append(line)
    return out


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _evidence_text(rec: RecordingSummary) -> list[str]:
    parts = [rec.identifier, rec.title, rec.source or "", rec.lineage or ""]
    parts.extend(source_lines(rec.description))
    return parts


def _has_phrase(toks: list[str], first: set[str], second: set[str]) -> bool:
    return any(a in first and b in second for a, b in zip(toks, toks[1:]))


def _non_id_list(rec: RecordingSummary) -> list[str]:
    toks: list[str] = []
    for part in _evidence_text(rec)[1:]:
        toks.extend(_tokens(part))
        toks.append("|")
    return toks


def classify(rec: RecordingSummary) -> LineageClass:
    toks: list[str] = []
    for part in _evidence_text(rec):
        toks.extend(_tokens(part))
        toks.append("|")  # fields never form a phrase across a boundary
    s = set(toks)
    # numeric mic models count outside the identifier only
    non_id = set()
    for part in _evidence_text(rec)[1:]:
        non_id.update(_tokens(part))
    markers = set()
    if s & _MATRIX_WORDS:
        markers.add("matrix")
    if s & _SBD_WORDS:
        markers.add("sbd")
    if s & _FM_WORDS:
        markers.add("fm")
    if s & _WEBCAST_WORDS:
        markers.add("webcast")
    if markers == {"matrix"} and _has_phrase(toks, {"aud", "audience"}, _MATRIX_WORDS):
        return "aud"
    for cls in ("matrix", "sbd", "fm", "webcast"):
        if cls in markers:
            return cls  # a marker beats gear
    usable = s - DECK_WORDS
    mics = (usable & (MIC_WORDS - _NUMERIC_MICS)) | ((non_id - DECK_WORDS) & _NUMERIC_MICS)
    if mics or usable & POSITION_WORDS:
        return "aud"
    # "taper section", "tapers section", "Taper's Section" (apostrophe splits to taper, s)
    if _has_phrase(toks, {"taper", "tapers"}, {"section"}) or any(
        a == "taper" and b == "s" and c == "section" for a, b, c in zip(toks, toks[1:], toks[2:])
    ):
        return "aud"
    if _has_phrase(_non_id_list(rec), *_NAK_MIC):
        return "aud"
    return "unknown"


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
