"""Variants of llama.taper at HEAD with one Checkpoint A change reverted, by monkeypatch.

noB: no (b) annotation in any header regex.
noC: the pre-(c) disc-first regex (disc word only, `(` or dash/slash) and no set-first regex.
noItem: the pre-R-ITEM `_song_titles`.
noPre: the pre-split (`_split_set_and_encore`) off.
"""
import re, html, contextlib
from llama import taper as T
from llama.setlist import _TRACK_PREFIX, _NUM_PREFIX, _INLINE_MARKER, _split_songs, MAX_TITLE_LEN, is_junk_title
from llama.structure import is_filler

HEAD = {"_SET_HEADERS": T._SET_HEADERS, "_song_titles": T._song_titles, "_preprocess": T._preprocess}

def _headers(annot: bool, c: bool):
    A = T._ANNOT if annot else ""
    D, SC = T._DECOR, T._SET_CORE
    sh = re.compile(rf"^{D}{SC}{A}(?:{T._TAIL_ALONE}|{T._TAIL_SONGS})", re.I)
    if c:
        ds = re.compile(
            rf"^{D}(?:{T._DISC}\s*(?:(?P<open>[(\[])\s*|[-–—/:,]\s*|(?<=\s))|{T._DISC_WORD}\s*/\s*)"
            rf"{SC}{A}(?(open)\s*[)\]]){A}(?:{T._TAIL_ALONE}|{T._TAIL_SONGS})", re.I)
        sd = re.compile(rf"^{D}{SC}\s*(?:[-–—/]\s*)?{T._DISC}{A}(?:{T._TAIL_ALONE}|{T._TAIL_SONGS})", re.I)
        return (sh, ds, sd)
    ds = re.compile(
        rf"^{D}disc\s*#?\s*(?:\d{{1,2}}|one|two|three|four|five|six|iv|i{{1,3}})(?!\w)\s*"
        rf"(?P<open>\()?(?(open)\s*|[-–—/]\s*){SC}{A}(?(open)\s*\)){A}"
        rf"(?:{T._TAIL_ALONE}|{T._TAIL_SONGS})", re.I)
    return (sh, ds)

def old_song_titles(rest, enumerated, *, header_rest=False):
    rest = _TRACK_PREFIX.sub("", rest)
    if enumerated:
        rest = _NUM_PREFIX.sub("", rest)
    if T._BARE_NUMBER.match(rest.strip()):
        return []
    rest = T._LEAD_TIMESTAMP.sub("", rest.strip())
    titles = []
    for title, _s in _split_songs(rest):
        if len(title) > MAX_TITLE_LEN or is_junk_title(title) or T._TIMESTAMP_ONLY.match(title):
            continue
        if is_filler(title):
            continue
        titles.append(title)
    return titles

def old_preprocess(text):
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html.unescape(text)
    raw = [ln.strip() for ln in text.splitlines()]
    return [ln.strip() for ln in _INLINE_MARKER.sub("\n", "\n".join(raw)).splitlines()]

def patch(name):
    T._SET_HEADERS = HEAD["_SET_HEADERS"]; T._song_titles = HEAD["_song_titles"]; T._preprocess = HEAD["_preprocess"]
    for part in name.split("+"):
        if part == "head":
            pass
        elif part == "noB":
            T._SET_HEADERS = _headers(False, len(T._SET_HEADERS) == 3)
        elif part == "noC":
            T._SET_HEADERS = _headers(True, False) if T._SET_HEADERS is HEAD["_SET_HEADERS"] else _headers(False, False)
        elif part == "noItem":
            T._song_titles = old_song_titles
        elif part == "noPre":
            T._preprocess = old_preprocess
        else:
            raise ValueError(part)

VARIANTS = ["head", "noB", "noC", "noB+noC", "noItem", "noPre"]
