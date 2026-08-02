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
from llama.songs import GD_SHORTHAND
from llama.structure import fuzzy_title_eq, title_components

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
    "GratefulDead" collapse to the same key without an alias table.

    "&" folds to "and" first: the CSV spells them out ("DeadAndCompany",
    "PhilLeshAndFriends"), so stripping the character instead of folding it
    denied those two acts every piece of jerrybase evidence."""
    folded = artist.replace("&", " and ")
    return "".join(c for c in folded.lower() if c.isalnum())


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


# Family acts the vendored dataset has no rows for. Dead vocabulary still
# applies to them: vocabulary transfers across the family, event evidence
# does not.
_EXTRA_FAMILY = frozenset({"joerussosalmostdead", "jrad"})

_FAMILY: frozenset[str] | None = None


def is_family_artist(artist: str) -> bool:
    """True when `artist` belongs to the Garcia universe, and so may use the
    Dead shorthand vocabulary (`songs.GD_SHORTHAND`).

    Membership is derived from the vendored CSV's own artist keys — all ten of
    them are Garcia-universe (Grateful Dead, Dark Star Orchestra, Ratdog, Phil
    Lesh & Friends, Jerry Garcia Band, Furthur, Bob Weir, Dead & Company, The
    Dead, The Other Ones) — plus `_EXTRA_FAMILY`. Deriving rather than
    hardcoding means the nine side/tribute acts need no maintained list.

    Deliberately independent of `[jerrybase] enabled`: turning off *event
    evidence* must never silently turn off *vocabulary*."""
    global _FAMILY
    if _FAMILY is None:
        _FAMILY = frozenset({k for k, _ in _load()}) | _EXTRA_FAMILY
    return bool(artist) and artist_key(artist) in _FAMILY


def _closer_candidates(tracks: list[Track], closer: str) -> list[int]:
    """Track indices whose closing song matches `closer`, in recording order.

    A merged track ("China Cat Sunflower > I Know You Rider") closes on its last
    component. Matching tolerates "&"/"and" spellings and dropped subtitles,
    because taper tags and canonical names disagree constantly. Exact matches
    win outright: when any candidate matches exactly, the fuzzy ones are
    discarded, so "Not Fade Away" prefers the track actually called that over
    one called "Not Fade Away Chant".

    The Dead shorthand table is applied unconditionally here, with no
    caller-side family gate: a jerrybase event only exists for artists in the
    dataset, so this path is inherently gated already.

    The target itself goes through `title_components`, not `fuzzy_norm_title`
    directly, so both sides strip a trailing parenthetical the same way — the
    track side already did (Task 3), and leaving the closer side raw made
    "Caution (Do Not Stop on Tracks)" and "Playin' In The Band (reprise)"
    demote out of the exact tier or stop matching altogether."""
    target = title_components(closer, GD_SHORTHAND)[-1]
    exact = [i for i, t in enumerate(tracks)
             if title_components(t.title, GD_SHORTHAND)[-1] == target]
    if exact:
        return exact
    return [i for i, t in enumerate(tracks)
            if fuzzy_title_eq(title_components(t.title, GD_SHORTHAND)[-1], target)]


def _resolve_positions(candidates: list[list[int]]) -> list[int] | None:
    """Pick one track index per set from each set's candidate list.

    Resolved right-to-left: the last set closes on its last candidate, and each
    earlier set takes its latest candidate still strictly before the following
    set's chosen position. That is what a repeated closer means in practice — a
    set ends on the LAST time its closer is played before the next set's does.
    None if any set has no candidate below its successor."""
    if not candidates or any(not c for c in candidates):
        return None
    positions: list[int] = [-1] * len(candidates)
    positions[-1] = candidates[-1][-1]
    for k in range(len(candidates) - 2, -1, -1):
        below = [p for p in candidates[k] if p < positions[k + 1]]
        if not below:
            return None
        positions[k] = below[-1]
    return positions


def anchor_breaks(tracks: list[Track], event: JerrybaseEvent,
                  aligned_sets: list[str] | None = None) -> list[str] | None:
    """Assign each track a set name by anchoring jerrybase set closers onto
    tracks. Succeeds only if every closer matches at least one track and the
    resolved positions are strictly increasing; then tracks up to and including
    closer i take set i's name, tracks after the last closer take the last set's
    name. Returns per-track set names (parallel to tracks) or None on any
    missing or unresolvable closer.

    `aligned_sets` (the deterministic alignment's own per-track set names, if
    any) enables the encore guard: jerrybase frequently records only the
    numbered sets, and without the guard a tape's trailing encore would be
    absorbed into the final numbered set. The guard only ever restores a label
    the alignment already produced — it never invents one."""
    if not any(s.name != "encore" for s in event.sets):
        # An event with no numbered set carries no set-break information, so
        # anchoring on it would label the whole show "encore" with no breaks.
        # This is not hypothetical: normalize_set_label cannot map jerrybase
        # labels like "First part"/"Second part"/"1st Set", so build_index
        # truncates ~1% of events down to their Encore row alone.
        return None
    positions = _resolve_positions([_closer_candidates(tracks, st.closer)
                                    for st in event.sets])
    if positions is None:
        return None
    # Defence in depth: _resolve_positions already guarantees this by
    # construction (each set takes a candidate strictly below its successor).
    if any(positions[k] >= positions[k + 1] for k in range(len(positions) - 1)):
        return None
    names = [s.name for s in event.sets]
    out: list[str] = []
    si = 0
    for i in range(len(tracks)):
        while si < len(positions) and i > positions[si]:
            si += 1
        out.append(names[min(si, len(names) - 1)])
    if (aligned_sets is not None and len(aligned_sets) == len(tracks)
            and not any(n == "encore" for n in names)):
        # The restore may reach back over the last closer — jerrybase often
        # FOLDS an omitted encore into the final set, making that set's recorded
        # closer the encore song itself. What it may never do is consume the
        # final numbered set entirely: that set starts at positions[-2] + 1, so
        # the restore stops one track later and always leaves it inhabited.
        floor = positions[-2] + 2 if len(positions) > 1 else 1
        for i in reversed(range(floor, len(out))):
            if aligned_sets[i] != "encore":
                break
            out[i] = "encore"
    return out


def closer_contradictions(tracks: list[Track],
                          event: JerrybaseEvent) -> tuple[list[str], list[str]]:
    """Cross-check jerrybase closers against tracks that already carry final set
    labels. Returns (hard_flags, soft_notes): a closer matched to exactly one
    track that is not the last track of its set is a hard flag (needs-review); a
    closer absent from the tracks is a soft note (context only). Ambiguous
    closers (multiple matches) are ignored."""
    if not tracks:
        return [], []
    breaks = {t.index for t, nxt in zip(tracks, tracks[1:]) if nxt.set != t.set}
    last_index = tracks[-1].index
    hard: list[str] = []
    soft: list[str] = []
    for st in event.sets:
        hits = [tracks[i] for i in _closer_candidates(tracks, st.closer)]
        if not hits:
            soft.append(f"jerrybase set closer '{st.closer}' not found in tracks")
            continue
        if len(hits) != 1:
            continue  # ambiguous: no reliable position check
        tk = hits[0]
        if not (tk.index in breaks or tk.index == last_index):
            hard.append(f"jerrybase set closer '{st.closer}' is not at a set break")
    return hard, soft
