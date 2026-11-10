import math
import re
from datetime import date, datetime, timezone

from llama import ts_measure, ts_rules
from llama.config import SelectionConfig, TaperssectionArtist
from llama.junk import FORMAT_BY_AUDIO, filter_files
from llama.models import Candidate, QualityAssessment, RecordingSummary
from llama.scoring import LINEAGE_SCORES, lineage_class, score_recording
from llama.titles import clean_tag_titles, title_fraction
from llama.errors import LlamaError
from llama.taperssection import Allowlist
from llama.workspace import (ShowWorkspace, drop_stage_artifacts, read_json, read_overrides,
                             should_run, write_artifact)


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


def lineage_table(selection: SelectionConfig, collection: str, date: str) -> dict[str, float]:
    """The lineage scores in force for this collection and date: the era's, else
    the global `scoring.LINEAGE_SCORES`."""
    return _era_lineage_scores(selection, collection, date) or LINEAGE_SCORES


def _ts_policy(candidate: Candidate, entry: TaperssectionArtist,
               pin: str | None) -> tuple[list[RecordingSummary], dict[str, str]]:
    """The taperssection per-tape policy filter (spec "Select-recording and the
    per-tape policy filter"): forbidden and `exclude`-matching tapes are removed;
    an unknown tape competes only when no allowed sibling remains, or when it is
    the pin. Returns (the recordings to score, {identifier: lineage class}).
    Raises LlamaError on a pin to a removed tape or on an empty remaining set."""
    pid = candidate.performance_id
    verdict = {rec.identifier: ts_rules.verdict(rec, entry) for rec in candidate.recordings}
    if pin is not None and verdict.get(pin) == "forbidden":
        raise LlamaError(f"{pid}: pinned recording {pin} is forbidden by the taperssection policy")
    any_allowed = "allowed" in verdict.values()
    kept = [rec for rec in candidate.recordings
            if verdict[rec.identifier] == "allowed"
            or (verdict[rec.identifier] == "unknown" and (not any_allowed or rec.identifier == pin))]
    if not kept:
        raise LlamaError(f"{pid}: no recording allowed by the taperssection policy")
    return kept, {rec.identifier: ts_rules.classify(rec) for rec in kept}


def run_select_recording(
    show_ws: ShowWorkspace,
    ia,
    candidate: Candidate,
    assessment: QualityAssessment,
    audio_format: str = "mp3",
    force: bool = False,
    selection: SelectionConfig | None = None,
    allowlist: Allowlist | None = None,
    today: date | None = None,
) -> str:
    # Fail closed first: a ts candidate with no usable allowlist raises even when
    # a stored selection would otherwise short-cut (None for an LMA candidate).
    entry = Allowlist.for_candidate(allowlist, candidate.collection)
    if not should_run(show_ws.selection, force):
        stored = read_json(show_ws.selection)["identifier"]
        if entry is None:
            return stored
        # Re-check the stored pick under the CURRENT entry: an entry tightened
        # since the show was selected must not ship a now-forbidden tape. A
        # forbidden pin raises; any other forbidden pick is stale and re-selects.
        # A stored identifier that is not a recording of the candidate is kept.
        rec = next((r for r in candidate.recordings if r.identifier == stored), None)
        if rec is None or ts_rules.verdict(rec, entry) != "forbidden":
            return stored
        if stored == read_overrides(show_ws).recording:
            raise LlamaError(f"{candidate.performance_id}: pinned recording {stored} is "
                             "forbidden by the taperssection policy")
        # The stale pick is replaced: drop gather and everything after it, so
        # gather recomputes on the new pick (and its R27 check applies) instead of
        # short-cutting to a show.json, research or package built on the old tape.
        drop_stage_artifacts(show_ws, "gather")
    selection = selection or SelectionConfig()
    pin = read_overrides(show_ws).recording

    recordings = candidate.recordings
    ts_lineage: dict[str, str] | None = None
    if entry is not None:
        today = today or datetime.now(timezone.utc).date()   # winnow's UTC date
        recordings, ts_lineage = _ts_policy(candidate, entry, pin)

    want = FORMAT_BY_AUDIO[audio_format]
    prepared = []
    for rec in recordings:
        md = ia.metadata(rec.identifier)
        meta = md.get("metadata", {})
        files = md.get("files", [])
        kept, _, _ = filter_files(files, want_format=want)
        prepared.append({
            "rec": rec,
            "lineage": (ts_lineage[rec.identifier] if ts_lineage is not None
                        else lineage_class(rec.identifier, meta)),
            "has_format": bool(kept),
            "kept_tracks": len(kept),
            "title_fraction": title_fraction(clean_tag_titles(kept)),
            "addeddate": str(meta.get("addeddate") or ""),
            "complaints": len(assessment.recording_complaints)
            if rec.identifier == assessment.reviewed_identifier else 0,
        })

    bonuses = _taper_bonuses(selection.tapers.get(candidate.collection, {}), prepared)
    era_scores = _era_lineage_scores(selection, candidate.collection, candidate.date)
    max_kept = max((p["kept_tracks"] for p in prepared), default=0) or 1
    if ts_lineage is not None:
        # Allowlisted siblings: the age-adjusted per-day rate (None, no evidence -> 0).
        for p in prepared:
            p["downloads"] = ts_measure.rate(p["rec"].downloads,
                                             p["rec"].addeddate or p["addeddate"], today) or 0.0
    else:
        for p in prepared:
            p["downloads"] = p["rec"].downloads
    max_log_downloads = max((math.log1p(p["downloads"]) for p in prepared), default=0.0)
    scores = {}
    for p in prepared:
        downloads_norm = (
            math.log1p(p["downloads"]) / max_log_downloads if max_log_downloads else 0.0
        )
        scores[p["rec"].identifier] = {
            "score": score_recording(
                lineage=p["lineage"],
                avg_rating=p["rec"].avg_rating,
                num_reviews=p["rec"].num_reviews,
                has_wanted_format=p["has_format"],
                completeness=p["kept_tracks"] / max_kept,
                complaints=p["complaints"],
                taper_bonus=bonuses[p["rec"].identifier],
                downloads_norm=downloads_norm,
                title_fraction=p["title_fraction"],
                lineage_scores=era_scores,
            ),
            "lineage": p["lineage"],
            "kept_tracks": p["kept_tracks"],
            "downloads_norm": round(downloads_norm, 3),
            "title_fraction": round(p["title_fraction"], 3),
        }
    if pin is not None and pin not in scores:
        slug = show_ws.dir.name
        raise LlamaError(f"{slug}: overrides.recording {pin} is not a recording of this "
                         f"performance; clear it with: llama fix {slug} --clear-recording")
    chosen = pin if pin is not None else max(scores, key=lambda ident: scores[ident]["score"])
    out = {"identifier": chosen, "scores": scores}
    if pin is not None:
        out["pinned"] = True
    if ts_lineage is not None:
        out["ts_lineage"] = {ident: ts_lineage[ident] for ident in scores}
    write_artifact(show_ws.selection, out)
    return chosen
