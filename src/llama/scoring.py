import math
import re

LINEAGE_SCORES = {"sbd": 3.0, "matrix": 2.5, "aud": 1.0, "unknown": 0.0}

_MATRIX = re.compile(r"matrix|\bmtx\b", re.I)
_SBD = re.compile(r"\bsbd\b|soundboard", re.I)
_AUD = re.compile(r"\baud\b|\baudience\b", re.I)


def lineage_class(identifier: str, metadata: dict) -> str:
    text = identifier + " " + " ".join(
        str(metadata.get(k, "")) for k in ("lineage", "source", "title")
    )
    if _MATRIX.search(text):
        return "matrix"
    if _SBD.search(text):
        return "sbd"
    if _AUD.search(text):
        return "aud"
    return "unknown"


def score_recording(
    *,
    lineage: str,
    avg_rating: float | None,
    num_reviews: int,
    has_wanted_format: bool,
    completeness: float,
    complaints: int,
    taper_bonus: float = 0.0,
    lineage_scores: dict[str, float] | None = None,
) -> float:
    table = LINEAGE_SCORES if lineage_scores is None else lineage_scores
    score = table.get(lineage, 0.0)
    score += (avg_rating or 0.0) * math.log10(1 + max(num_reviews, 0))
    score += taper_bonus  # reputation rides with lineage, inside the completeness scale
    if has_wanted_format:
        score += 0.5
    # Completeness (0..1, kept-track count vs best sibling) scales the whole
    # score: a fragment of the show forfeits up to half its appeal, so a
    # hot-rated partial recording loses to a complete one of the same
    # performance, while lineage still dominates across recording types.
    score *= 0.5 + 0.5 * completeness
    score -= 0.5 * min(complaints, 4)
    return round(score, 3)
