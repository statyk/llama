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
})

# Taper positions and audience words. "fob" (front of board), "ots", "dfc"
# (directly from center) and friends say where the mics stood, which only an
# audience taper reports; "aud"/"audience" name the lineage itself. Phrases
# such as "taper section" are matched separately in _has_taper_section.
POSITION_WORDS: frozenset[str] = frozenset({
    "fob", "dfob", "nfob", "ots", "dfc", "dfa", "taper", "tapers", "tapersection",
    "aud", "audience",
})

# Recorders, decks and transfer gear. They appear in board feeds and audience
# rigs alike, so they are never evidence for aud (or for any class). Listed so
# the exclusion is explicit and tested (disjoint from the two sets above).
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


def classify(rec: RecordingSummary) -> LineageClass:
    toks: list[str] = []
    for part in _evidence_text(rec):
        toks.extend(_tokens(part))
        toks.append("|")  # fields never form a phrase across a boundary
    s = set(toks)
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
    if usable & MIC_WORDS or usable & POSITION_WORDS:
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
# Prefixes that are formats or lineage words, never an artist: "flac192000".
_NOT_ARTIST = {"flac", "mp", "mp3", "shn", "shnf", "wav", "sbd", "aud", "fm", "mtx", "dat",
               "cd", "md", "vbr", "kbps", "bit", "track", "disc", "set", "ogg", "m4a"}


def _iso(y: int, m: int, d: int) -> str | None:
    try:
        return _date(y, m, d).isoformat()
    except ValueError:
        return None


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
            if not m or m[1] in _NOT_ARTIST:
                continue
            yy = int(m[2])
            iso = _iso(1900 + yy if yy >= 50 else 2000 + yy, int(m[3]), int(m[4]))
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
