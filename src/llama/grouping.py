import re
from collections import Counter

from llama import jerrybase
from llama.models import Candidate, RecordingSummary
from llama.songs import normalize_song
from llama.structure import norm_title

_EARLY_LATE = re.compile(r"\b(early|late)\b", re.I)
_EARLY = re.compile(r"\bearly\b", re.I)
_LATE = re.compile(r"\blate\b", re.I)


def _first(value):
    """archive.org fields are sometimes lists; take the first element."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _summary(doc: dict, date: str) -> RecordingSummary:
    rating = _first(doc.get("avg_rating"))
    return RecordingSummary(
        identifier=doc["identifier"],
        title=str(_first(doc.get("title")) or ""),
        date=date,
        venue=_first(doc.get("venue")) or None,
        coverage=_first(doc.get("coverage")) or None,
        avg_rating=float(rating) if rating is not None else None,
        num_reviews=int(_first(doc.get("num_reviews")) or 0),
        downloads=int(_first(doc.get("downloads")) or 0),
        description=str(_first(doc.get("description")) or "") or None,
    )


def _make_candidate(pid, collection, recs, venue=None, city=None) -> Candidate:
    venues = Counter(r.venue for r in recs if r.venue)
    cities = Counter(r.coverage for r in recs if r.coverage)
    return Candidate(
        performance_id=pid,
        collection=collection,
        date=recs[0].date or "",
        venue=venues.most_common(1)[0][0] if venues else venue,
        city=cities.most_common(1)[0][0] if cities else city,
        recordings=recs,
    )


def _contains(tokens: list[str], closer: str) -> bool:
    """True if the normalized closer appears as a contiguous run of description
    tokens (norm_title containment)."""
    seq = norm_title(closer).split()
    if not seq:
        return False
    return any(tokens[i:i + len(seq)] == seq
               for i in range(len(tokens) - len(seq) + 1))


def _assign_recording(rec: RecordingSummary, events: list) -> list[int]:
    """0-based event indices this recording belongs to. [] = unassignable;
    one index = that event; multiple = the tape spans the evening.

    Signals in priority order: (1) early/late text (2-event dates only) in
    identifier/title/description; (2) description set-closer containment."""
    if len(events) == 2:
        text = f"{rec.identifier} {rec.title} {rec.description or ''}"
        early = bool(_EARLY.search(text))
        late = bool(_LATE.search(text))
        if early and late:
            return [0, 1]
        if early:
            return [0]
        if late:
            return [1]
    tokens = normalize_song(rec.description or "").split()
    hits: list[int] = []
    for i, ev in enumerate(events):
        if any(_contains(tokens, s.closer) for s in ev.sets if s.closer):
            hits.append(i)
    return hits


def _partition(collection: str, date: str, recs: list, events: list) -> list[Candidate]:
    by_event: dict[int, list] = {}
    spans: list = []
    unassigned: list = []
    for rec in recs:
        idxs = _assign_recording(rec, events)
        if len(idxs) == 1:
            by_event.setdefault(idxs[0], []).append(rec)
        elif len(idxs) > 1:
            spans.append(rec)
        else:
            unassigned.append(rec)
    out: list[Candidate] = []
    for i in sorted(by_event):
        ev = events[i]
        out.append(_make_candidate(f"{collection}/{date}/e{i + 1}", collection,
                                   by_event[i], venue=ev.venue, city=ev.city))
    if spans:
        out.append(_make_candidate(f"{collection}/{date}/spans", collection, spans))
    if unassigned:
        out.append(_make_candidate(f"{collection}/{date}/unassigned", collection, unassigned))
    return out


def _legacy_split(collection: str, date: str, recs: list) -> list[Candidate]:
    """No-jerrybase-data path: preserve today's per-recording early/late
    identifier-sniff split byte-for-byte."""
    groups: dict[str, list] = {}
    for rec in recs:
        pid = f"{collection}/{date}"
        m = _EARLY_LATE.search(rec.identifier)
        if m:
            pid += f"/{m.group(1).lower()}"
        groups.setdefault(pid, []).append(rec)
    return [_make_candidate(pid, collection, grp) for pid, grp in groups.items()]


def group_candidates(collection: str, docs: list[dict],
                     jerrybase_enabled: bool = True) -> list[Candidate]:
    by_date: dict[str, list[RecordingSummary]] = {}
    for doc in docs:
        date = str(_first(doc.get("date")) or "")[:10]
        if not date:
            continue
        by_date.setdefault(date, []).append(_summary(doc, date))

    candidates: list[Candidate] = []
    for date, recs in by_date.items():
        events = jerrybase.lookup(collection, date) if jerrybase_enabled else []
        if len(events) > 1:
            candidates.extend(_partition(collection, date, recs, events))
        elif len(events) == 1:
            candidates.append(_make_candidate(f"{collection}/{date}", collection, recs))
        else:
            candidates.extend(_legacy_split(collection, date, recs))
    return sorted(candidates, key=lambda c: (c.date, c.performance_id))
