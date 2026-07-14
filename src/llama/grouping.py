import re
from collections import Counter

from llama.models import Candidate, RecordingSummary

_EARLY_LATE = re.compile(r"\b(early|late)\b", re.I)


def _first(value):
    """archive.org fields are sometimes lists; take the first element."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def group_candidates(collection: str, docs: list[dict]) -> list[Candidate]:
    groups: dict[str, list[RecordingSummary]] = {}
    for doc in docs:
        date = str(_first(doc.get("date")) or "")[:10]
        if not date:
            continue
        rating = _first(doc.get("avg_rating"))
        rec = RecordingSummary(
            identifier=doc["identifier"],
            title=str(_first(doc.get("title")) or ""),
            date=date,
            venue=_first(doc.get("venue")) or None,
            coverage=_first(doc.get("coverage")) or None,
            avg_rating=float(rating) if rating is not None else None,
            num_reviews=int(_first(doc.get("num_reviews")) or 0),
            description=str(_first(doc.get("description")) or "") or None,
        )
        pid = f"{collection}/{date}"
        m = _EARLY_LATE.search(doc["identifier"])
        if m:
            pid += f"/{m.group(1).lower()}"
        groups.setdefault(pid, []).append(rec)

    candidates = []
    for pid, recs in groups.items():
        venues = Counter(r.venue for r in recs if r.venue)
        cities = Counter(r.coverage for r in recs if r.coverage)
        candidates.append(
            Candidate(
                performance_id=pid,
                collection=collection,
                date=recs[0].date or "",
                venue=venues.most_common(1)[0][0] if venues else None,
                city=cities.most_common(1)[0][0] if cities else None,
                recordings=recs,
            )
        )
    return sorted(candidates, key=lambda c: (c.date, c.performance_id))
