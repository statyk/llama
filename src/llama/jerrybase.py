"""Best-effort jerrybase structure evidence from the vendored set_breaks.csv.

Defensive like setlistfm.py: nothing raises. Absence of evidence degrades to an
empty result. The CSV is one row per set per show; this module builds a lazy
(artist_key, date) -> list[JerrybaseEvent] index and offers deterministic
break-anchoring and closer cross-checks over it.
"""
import csv
import logging
import re
from collections.abc import Iterable
from importlib import resources

from llama.models import JerrybaseEvent, JerrybaseSet, Track
from llama.structure import norm_title

log = logging.getLogger("llama")

_INDEX: dict[tuple[str, str], list[JerrybaseEvent]] | None = None

# Roman numerals and spelled-out ordinals onto the canonical vocabulary.
_SET_WORDS = {
    "one": "1", "two": "2", "three": "3",
    "first": "1", "second": "2", "third": "3",
    "i": "1", "ii": "2", "iii": "3",
    "1": "1", "2": "2", "3": "3",
}


def artist_key(artist: str) -> str:
    """Lowercased alphanumerics only, so "Grateful Dead" and the CSV's
    "GratefulDead" collapse to the same key without an alias table."""
    return "".join(c for c in artist.lower() if c.isalnum())


def normalize_set_label(label: str) -> str | None:
    """Map a jerrybase show_set label onto "1"|"2"|"3"|"encore", or None if
    unmappable (unmappable rows are dropped by build_index)."""
    s = (label or "").strip().lower()
    if s.startswith("encore"):
        return "encore"
    if s in ("show", "set"):
        return "1"
    m = re.match(r"set\s*:?\s*(one|two|three|iii|ii|i|[123])\b", s)
    if m:
        return _SET_WORDS[m.group(1)]
    m = re.match(r"(first|second|third)\s+set\b", s)
    if m:
        return _SET_WORDS[m.group(1)]
    m = re.fullmatch(r"(one|two|three|first|second|third|iii|ii|i|[123])", s)
    if m:
        return _SET_WORDS[m.group(1)]
    return None


def build_index(rows: Iterable[dict]) -> tuple[dict[tuple[str, str], list[JerrybaseEvent]], int]:
    """Group rows into (artist_key, date) -> events ordered by ievent. Returns
    (index, skipped_count). A row is skipped when its set label is unmappable or
    its isong is not an integer. song_count is the isong delta from the prior set
    within one event; the first set of each event gets None. Never raises."""
    groups: dict[tuple[str, str], dict[str, list[dict]]] = {}
    skipped = 0
    for row in rows:
        label = normalize_set_label(row.get("show_set", ""))
        if label is None:
            skipped += 1
            continue
        try:
            isong = int(row["isong"])
        except (KeyError, ValueError, TypeError):
            skipped += 1
            continue
        key = (artist_key(row.get("artist", "")), row.get("date", ""))
        groups.setdefault(key, {}).setdefault(row.get("event_id", ""), []).append({
            "label": label,
            "closer": row.get("song", ""),
            "isong": isong,
            "break_length": row.get("break_length", ""),
            "venue": row.get("venue", ""),
            "city": row.get("city", ""),
            "state": row.get("state", ""),
            "ievent": row.get("ievent", ""),
        })

    index: dict[tuple[str, str], list[JerrybaseEvent]] = {}
    for key, by_event in groups.items():
        events: list[tuple[int, JerrybaseEvent]] = []
        for event_id, setrows in by_event.items():
            setrows.sort(key=lambda r: r["isong"])
            sets: list[JerrybaseSet] = []
            prev: int | None = None
            for r in setrows:
                count = None if prev is None else r["isong"] - prev
                prev = r["isong"]
                sets.append(JerrybaseSet(name=r["label"], closer=r["closer"],
                                         break_length=r["break_length"], song_count=count))
            first = setrows[0]
            try:
                ievent = int(first["ievent"])
            except (ValueError, TypeError):
                ievent = 0
            events.append((ievent, JerrybaseEvent(
                event_id=event_id, venue=first["venue"], city=first["city"],
                state=first["state"], sets=sets)))
        events.sort(key=lambda pair: pair[0])
        index[key] = [ev for _, ev in events]
    return index, skipped


def _load() -> dict[tuple[str, str], list[JerrybaseEvent]]:
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    try:
        with resources.files("llama.data").joinpath("set_breaks.csv").open(
                "r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        index, skipped = build_index(rows)
        if skipped:
            log.warning("jerrybase: skipped %d malformed rows", skipped)
        _INDEX = index
    except Exception as err:  # noqa: BLE001 - defensive: absence must never raise
        log.warning("jerrybase: could not load set_breaks.csv: %s", err)
        _INDEX = {}
    return _INDEX


def lookup(artist: str, date: str) -> list[JerrybaseEvent]:
    """Jerrybase events for (artist, date). Empty = no evidence; length > 1 =
    multi-event date. Never raises."""
    return _load().get((artist_key(artist), date), [])


def anchor_breaks(tracks: list[Track], event: JerrybaseEvent) -> list[str] | None:
    """Assign each track a set name by anchoring jerrybase set closers onto
    tracks (matched via norm_title). Succeeds only if every closer matches
    exactly one track and the matched positions are strictly increasing; then
    tracks up to and including closer i take set i's name, tracks after the last
    closer take the last set's name. Returns per-track set names (parallel to
    tracks) or None on any missing/ambiguous/out-of-order closer."""
    positions: list[int] = []
    for st in event.sets:
        target = norm_title(st.closer)
        hits = [i for i, t in enumerate(tracks) if norm_title(t.title) == target]
        if len(hits) != 1:
            return None
        positions.append(hits[0])
    if any(positions[k] >= positions[k + 1] for k in range(len(positions) - 1)):
        return None
    if not positions:
        return None
    names = [s.name for s in event.sets]
    out: list[str] = []
    si = 0
    for i in range(len(tracks)):
        while si < len(positions) and i > positions[si]:
            si += 1
        out.append(names[min(si, len(names) - 1)])
    return out
