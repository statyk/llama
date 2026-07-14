from llama.junk import FORMAT_BY_AUDIO, filter_files
from llama.models import Candidate, QualityAssessment
from llama.scoring import lineage_class, score_recording
from llama.workspace import ShowWorkspace, read_json, should_run, write_artifact


def run_select_recording(
    show_ws: ShowWorkspace,
    ia,
    candidate: Candidate,
    assessment: QualityAssessment,
    audio_format: str = "mp3",
    force: bool = False,
) -> str:
    if not should_run(show_ws.selection, force):
        return read_json(show_ws.selection)["identifier"]

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
            "complaints": len(assessment.recording_complaints)
            if rec.identifier == assessment.reviewed_identifier else 0,
        })

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
            ),
            "lineage": p["lineage"],
            "kept_tracks": p["kept_tracks"],
        }
    chosen = max(scores, key=lambda ident: scores[ident]["score"])
    write_artifact(show_ws.selection, {"identifier": chosen, "scores": scores})
    return chosen
