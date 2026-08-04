import re
from collections import Counter
from collections.abc import Sequence

from llama.util import length_seconds

# Delivery formats, in preference order. archive.org tags lossless files
# either "Flac" or "24bit Flac"; matching only the first made every 24-bit
# item look like it had no lossless copy at all, so audio_format="flac"
# yielded zero kept files and the recording became unselectable.
FORMAT_BY_AUDIO = {"mp3": ("VBR MP3",), "flac": ("Flac", "24bit Flac")}

# Lossless formats worth READING titles from. Deliberately broader than the
# delivery formats: title recovery reads metadata strings and never downloads
# these files, so Shorten is safe here - and deliberately absent above, since
# adding it would change what llama ships.
LOSSLESS_TITLE_FORMATS = ("Flac", "24bit Flac", "Shorten")

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
    files: list[dict], want_format: str | Sequence[str] = "VBR MP3"
) -> tuple[list[dict], list[dict], dict]:
    """Returns (kept, excluded, ordering) with kept in canonical play order.

    `want_format` may be one format or an ordered preference list. A list is
    tried in order and the FIRST one present wins - never a union, because an
    item carrying both Flac and 24bit Flac would otherwise keep every track
    twice."""
    wanted = (want_format,) if isinstance(want_format, str) else tuple(want_format)
    audio: list[dict] = []
    matched = ""
    for fmt in wanted:
        audio = [f for f in files if f.get("format") == fmt]
        if audio:
            matched = fmt
            break
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
    ordering = {"order_source": "filename", "reordered": False, "format": matched}
    # Track-tag order only when complete and unique: per-disc numbering
    # restarts at 1, which makes duplicates ambiguous.
    if kept and all(n is not None for n in nums) and len(set(nums)) == len(nums):
        by_track = [f for _, f in sorted(zip(nums, kept), key=lambda p: p[0])]
        ordering = {"order_source": "track-tags", "reordered": by_track != kept,
                    "format": matched}
        kept = by_track
    return kept, excluded, ordering
