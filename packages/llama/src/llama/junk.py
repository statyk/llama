import re
from collections import Counter

from llama.util import length_seconds

FORMAT_BY_AUDIO = {"mp3": "VBR MP3", "flac": "Flac"}
MIN_PLAUSIBLE_SEC = 90.0

_LEADING_INT = re.compile(r"\s*(\d+)")


def _stem(name: str) -> str:
    """Filename up to the first digit — the item's naming-convention signature."""
    for i, ch in enumerate(name):
        if ch.isdigit():
            return name[:i]
    return name


def _track_number(f: dict, orig_tracks: dict[str, object]) -> int | None:
    """Leading integer of the file's track tag ("5", "05", "5/16"). A
    derivative takes its original's tag - derivative entries often lack it."""
    raw = f.get("track") if f.get("source") == "original" else orig_tracks.get(f.get("original"))
    m = _LEADING_INT.match(str(raw)) if raw is not None else None
    return int(m.group(1)) if m else None


def filter_files(
    files: list[dict], want_format: str = "VBR MP3"
) -> tuple[list[dict], list[dict], dict]:
    """Returns (kept, excluded, ordering) with kept in canonical play order."""
    audio = [f for f in files if f.get("format") == want_format]
    original_names = {f["name"] for f in files if f.get("source") == "original"}
    stems = Counter(_stem(f["name"]) for f in audio)
    dominant = stems.most_common(1)[0][0] if stems else ""

    kept: list[dict] = []
    excluded: list[dict] = []
    for f in audio:
        reasons: list[str] = []
        if f.get("source") == "derivative":
            if f.get("original") not in original_names:
                reasons.append("derivative of unknown original")
        elif f.get("source") != "original":
            reasons.append("unknown provenance")
        if _stem(f["name"]) != dominant:
            reasons.append("filename convention mismatch")
        secs = length_seconds(f.get("length"))
        if secs is None:
            reasons.append("missing duration")
        elif secs < MIN_PLAUSIBLE_SEC:
            reasons.append("implausibly short")
        if reasons:
            excluded.append({"filename": f["name"], "reasons": reasons})
        else:
            kept.append(f)
    kept.sort(key=lambda f: f["name"])
    orig_tracks = {f["name"]: f.get("track") for f in files if f.get("source") == "original"}
    nums = [_track_number(f, orig_tracks) for f in kept]
    ordering = {"order_source": "filename", "reordered": False}
    # Track-tag order only when complete and unique: per-disc numbering
    # restarts at 1, which makes duplicates ambiguous.
    if kept and all(n is not None for n in nums) and len(set(nums)) == len(nums):
        by_track = [f for _, f in sorted(zip(nums, kept), key=lambda p: p[0])]
        ordering = {"order_source": "track-tags", "reordered": by_track != kept}
        kept = by_track
    return kept, excluded, ordering
