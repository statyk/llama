import math
import re

_PID = re.compile(r"^([^/]+)/(\d{4}-\d{2}-\d{2})(?:/e\d+)?$")


def parse_performance_id(text: str) -> tuple[str, str] | None:
    """(collection, date) from a canonical performance id, else None."""
    m = _PID.match(text)
    return (m.group(1), m.group(2)) if m else None


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "unknown"


def length_seconds(val) -> float | None:
    """Parse archive.org length values: 'MM:SS', 'HH:MM:SS', or plain seconds."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if ":" in s:
        try:
            parts = [float(p) for p in s.split(":")]
        except ValueError:
            return None
        secs = 0.0
        for p in parts:
            secs = secs * 60 + p
        return secs
    try:
        return float(s)
    except ValueError:
        return None


def capped_pick(items: list, key_of, n: int, cap: float) -> list:
    """Pick up to n items best-first, but no bucket (keyed by key_of) may
    hold more than ceil(n * cap) slots until every bucket is at its cap;
    any remaining slots then relax to best-first — quality earns the slots,
    the cap only bounds dominance. cap=1.0 is pure best-first; cap at or
    below 1/n degenerates to one-per-bucket round-robin. If every bucket
    hits the cap before n slots fill, the rest relax to best-first. Items
    must arrive best-first."""
    buckets: dict[str, list] = {}
    for item in items:
        buckets.setdefault(str(key_of(item)), []).append(item)
    if cap >= 1.0 or len(buckets) <= 1:
        return items[:n]
    max_per = max(1, math.ceil(n * cap))
    picked: list = []
    counts = {k: 0 for k in buckets}
    for item in items:
        if len(picked) >= n:
            return picked
        k = str(key_of(item))
        if counts[k] < max_per:
            counts[k] += 1
            picked.append(item)
    taken = {id(x) for x in picked}
    leftovers = [x for x in items if id(x) not in taken]
    return picked + leftovers[: n - len(picked)]


def cap_across_artists(items: list, artist_of, date_of, n: int, cap: float,
                       year_cap: float = 1.0) -> list:
    """Pick up to n items best-first, dominance bounded on two axes: no
    artist may hold more than ceil(n * cap) slots while other artists still
    have candidates, and each artist's own queue is year-capped by year_cap
    (relative to that artist's candidate count; 1.0 = score order decides).
    With a single artist this is exactly capped_pick over years."""
    year_of = lambda item: str(date_of(item))[:4]
    buckets: dict[str, list] = {}
    for item in items:
        buckets.setdefault(artist_of(item), []).append(item)
    if len(buckets) <= 1:
        return capped_pick(items, year_of, n, year_cap)
    # Score order decides WHOSE turn a slot is, the (year-capped) queue
    # decides WHICH of their shows fills it.
    queues = {a: capped_pick(b, year_of, len(b), year_cap) for a, b in buckets.items()}
    max_per = n if cap >= 1.0 else max(1, math.ceil(n * cap))
    picked: list = []
    counts = {a: 0 for a in queues}
    for item in items:
        if len(picked) >= n:
            return picked
        a = artist_of(item)
        if counts[a] < max_per:
            counts[a] += 1
            picked.append(queues[a].pop(0))
    taken = {id(x) for x in picked}
    leftovers = [x for x in items if id(x) not in taken]
    return picked + leftovers[: n - len(picked)]


def reviews_digest(reviews: list[dict], limit: int = 5) -> str:
    """Trimmed listener-review digest: what synthesize consumes and packages ship."""
    parts = []
    for r in reviews[:limit]:
        title = str(r.get("reviewtitle") or "").strip()
        body = str(r.get("reviewbody") or "").strip()[:800]
        parts.append(f"- {title}: {body}" if title else f"- {body}")
    return "\n".join(parts) or "(no reviews)"
