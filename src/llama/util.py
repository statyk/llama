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


def spread_across_years(items: list, date_of, n: int) -> list:
    """Pick up to n items, round-robin across years, preserving preference
    order within each year. Items must arrive best-first; the year cycle
    follows each year's first appearance, so the overall best item is always
    picked first. With a single year this is exactly items[:n]."""
    buckets: dict[str, list] = {}
    for item in items:
        buckets.setdefault(str(date_of(item))[:4], []).append(item)
    picked: list = []
    while len(picked) < n and any(buckets.values()):
        for bucket in buckets.values():
            if bucket:
                picked.append(bucket.pop(0))
                if len(picked) >= n:
                    break
    return picked


def reviews_digest(reviews: list[dict], limit: int = 5) -> str:
    """Trimmed listener-review digest: what synthesize consumes and packages ship."""
    parts = []
    for r in reviews[:limit]:
        title = str(r.get("reviewtitle") or "").strip()
        body = str(r.get("reviewbody") or "").strip()[:800]
        parts.append(f"- {title}: {body}" if title else f"- {body}")
    return "\n".join(parts) or "(no reviews)"
