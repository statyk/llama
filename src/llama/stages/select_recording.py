import re

from llama.config import SelectionConfig
from llama.junk import FORMAT_BY_AUDIO, filter_files
from llama.models import Candidate, QualityAssessment
from llama.scoring import lineage_class, score_recording
from llama.workspace import ShowWorkspace, read_json, should_run, write_artifact


def _shnid(identifier: str) -> int:
    """Largest integer token: LMA identifiers embed the shnid, and a higher
    shnid is a later transfer (miller.32350 supersedes miller.32273)."""
    nums = [int(n) for n in re.findall(r"\d+", identifier)]
    return max(nums, default=0)


def _taper_bonuses(patterns: dict[str, float], prepared: list[dict]) -> dict[str, float]:
    """Reputation bonus per recording. Among several matches of one pattern
    (revisions by the same taper), the newest gets the full bonus and the
    rest half - newer transfers usually supersede older ones. Newness is the
    shnid, not addeddate: an old transfer can be (re-)uploaded years after a
    newer one (seen live: shnid 32273 added 2009, 32350 added 2008)."""
    bonuses = {p["rec"].identifier: 0.0 for p in prepared}
    for pattern, bonus in patterns.items():
        matches = [p for p in prepared if pattern.lower() in p["rec"].identifier.lower()]
        if not matches:
            continue
        newest = max(matches, key=lambda p: (_shnid(p["rec"].identifier), p["addeddate"]))
        for p in matches:
            ident = p["rec"].identifier
            bonuses[ident] = max(bonuses[ident], bonus if p is newest else bonus / 2)
    return bonuses


def _era_lineage_scores(selection: SelectionConfig, collection: str, date: str) -> dict[str, float] | None:
    for era in selection.lineage_eras:
        if era.collection == collection and era.date_from <= date <= era.date_to:
            return era.scores
    return None


def run_select_recording(
    show_ws: ShowWorkspace,
    ia,
    candidate: Candidate,
    assessment: QualityAssessment,
    audio_format: str = "mp3",
    force: bool = False,
    selection: SelectionConfig | None = None,
) -> str:
    if not should_run(show_ws.selection, force):
        return read_json(show_ws.selection)["identifier"]
    selection = selection or SelectionConfig()

    want = FORMAT_BY_AUDIO[audio_format]
    prepared = []
    for rec in candidate.recordings:
        md = ia.metadata(rec.identifier)
        meta = md.get("metadata", {})
        files = md.get("files", [])
        kept, _ = filter_files(files, want_format=want)
        prepared.append({
            "rec": rec,
            "lineage": lineage_class(rec.identifier, meta),
            "has_format": bool(kept),
            "kept_tracks": len(kept),
            "addeddate": str(meta.get("addeddate") or ""),
            "complaints": len(assessment.recording_complaints)
            if rec.identifier == assessment.reviewed_identifier else 0,
        })

    bonuses = _taper_bonuses(selection.tapers.get(candidate.collection, {}), prepared)
    era_scores = _era_lineage_scores(selection, candidate.collection, candidate.date)
    max_kept = max((p["kept_tracks"] for p in prepared), default=0) or 1
    scores = {}
    for p in prepared:
        scores[p["rec"].identifier] = {
            "score": score_recording(
                lineage=p["lineage"],
                avg_rating=p["rec"].avg_rating,
                num_reviews=p["rec"].num_reviews,
                has_wanted_format=p["has_format"],
                completeness=p["kept_tracks"] / max_kept,
                complaints=p["complaints"],
                taper_bonus=bonuses[p["rec"].identifier],
                lineage_scores=era_scores,
            ),
            "lineage": p["lineage"],
            "kept_tracks": p["kept_tracks"],
        }
    chosen = max(scores, key=lambda ident: scores[ident]["score"])
    write_artifact(show_ws.selection, {"identifier": chosen, "scores": scores})
    return chosen
