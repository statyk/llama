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
_TRACK_PREFIX = re.compile(
    r"^\s*(?:(?:d\d+t\d+|t\d{1,2})\s*[\s.\-:]+|\d{1,2}\s*[.)]\s+)", re.I
)
_SET_TOKEN = {"one": "1", "two": "2", "three": "3", "i": "1", "ii": "2", "iii": "3"}
# Lines that are lineage/provenance chatter, not songs. Checked before song splitting.
_NOISE = re.compile(
    r"(recorded|transfer|lineage|source|taper|shnid|seeded|thanks|conversion|remaster"
    r"|\bsbd\b|\bdat\b|\bflac\b|\bshn\b|cassette|master reel|\bvia\b|d\d+t\d+\s*$|disc\s*\d)",
    re.I,
)
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
        for title, segue in _split_songs(rest):
            if len(title) > MAX_TITLE_LEN:
                continue  # implausibly long fragment - prose, not a song title
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
