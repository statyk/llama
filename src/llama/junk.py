from collections import Counter

from llama.util import length_seconds

FORMAT_BY_AUDIO = {"mp3": "VBR MP3", "flac": "Flac"}
MIN_PLAUSIBLE_SEC = 90.0


def _stem(name: str) -> str:
    """Filename up to the first digit — the item's naming-convention signature."""
    for i, ch in enumerate(name):
        if ch.isdigit():
            return name[:i]
    return name


def filter_files(files: list[dict], want_format: str = "VBR MP3") -> tuple[list[dict], list[dict]]:
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
    return kept, excluded
