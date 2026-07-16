import math
import re


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


def _round_robin(buckets: list[list], n: int) -> list:
    picked: list = []
    while len(picked) < n and any(buckets):
        for bucket in buckets:
            if bucket:
                picked.append(bucket.pop(0))
                if len(picked) >= n:
                    break
    return picked


def spread_across_years(items: list, date_of, n: int) -> list:
    """Pick up to n items, round-robin across years, preserving preference
    order within each year. Items must arrive best-first; the year cycle
    follows each year's first appearance, so the overall best item is always
    picked first. With a single year this is exactly items[:n]."""
    buckets: dict[str, list] = {}
    for item in items:
        buckets.setdefault(str(date_of(item))[:4], []).append(item)
    return _round_robin(list(buckets.values()), n)


def spread_across_artists(items: list, artist_of, date_of, n: int) -> list:
    """Pick up to n items, round-robin across artists so no single deep
    catalog monopolizes a style profile, with each artist's own picks spread
    across years. Items must arrive best-first; the artist cycle follows each
    artist's first appearance, so the overall best item is always picked
    first. With a single artist this is exactly spread_across_years."""
    buckets: dict[str, list] = {}
    for item in items:
        buckets.setdefault(artist_of(item), []).append(item)
    if len(buckets) <= 1:
        return spread_across_years(items, date_of, n)
    ordered = [spread_across_years(b, date_of, len(b)) for b in buckets.values()]
    return _round_robin(ordered, n)


def cap_across_artists(items: list, artist_of, date_of, n: int, cap: float) -> list:
    """Pick up to n items best-first, but while other artists still have
    candidates no artist may hold more than ceil(n * cap) slots — quality
    earns the slots, the cap only bounds dominance. Each artist's own slots
    are spread across years. cap=1.0 is pure best-first; cap at or below 1/n
    degenerates to one-per-artist round-robin. If every artist hits the cap
    before n slots fill, the rest relax to best-first. With a single artist
    this is exactly spread_across_years."""
    buckets: dict[str, list] = {}
    for item in items:
        buckets.setdefault(artist_of(item), []).append(item)
    if len(buckets) <= 1:
        return spread_across_years(items, date_of, n)
    # Year-spread queue per artist: score order decides WHOSE turn a slot is,
    # the queue decides WHICH of their shows fills it.
    queues = {a: spread_across_years(b, date_of, len(b)) for a, b in buckets.items()}
    max_per = max(1, math.ceil(n * cap))
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
