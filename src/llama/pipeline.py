import logging
from datetime import datetime, timezone
from pathlib import Path

from llama.config import Config
from llama.ledger import Ledger
from llama.llm import provider_ladder
from llama.models import DJNotes, LedgerEntry, Show, ShortlistEntry
from llama.stages.gather import run_gather
from llama.stages.package import run_package
from llama.stages.research import run_research
from llama.stages.select_recording import run_select_recording
from llama.stages.synthesize import run_synthesize
from llama.util import cap_across_artists
from llama.stages.vet_research import run_vet_research
from llama.status import step
from llama.workspace import RunWorkspace, drop_stage_artifacts, read_json, read_model

log = logging.getLogger("llama")

TASK_KEYS = ["interpret", "score_reviews", "light_research",
             "extract_setlist", "deep_research", "synthesize",
             "find_artists", "align_structure", "vet_research"]


def make_providers(config: Config) -> dict:
    return {key: provider_ladder(config, key) for key in TASK_KEYS}


def choose_entries(shortlist: list[ShortlistEntry], count: int, human_gate: bool,
                   artist_cap: float = 1 / 3, year_cap: float = 1.0):
    approved = [e for e in shortlist if e.approved is True]
    if approved:
        return approved[:count]  # explicit human picks: no capping
    if human_gate:
        return None  # gate required, nothing approved yet
    unrejected = [e for e in shortlist if e.approved is not False]
    picked = cap_across_artists(unrejected, lambda e: e.candidate.collection,
                                lambda e: e.candidate.date, count, artist_cap,
                                year_cap)
    return sorted(picked, key=lambda e: e.rank)


def process_show(
    run_ws: RunWorkspace,
    ia,
    ledger: Ledger,
    entry: ShortlistEntry,
    providers: dict,
    run_name: str,
    audio_format: str = "mp3",
    force: bool = False,
    script: bool = False,
    setlistfm=None,
    structure_cfg=None,
    selection_cfg=None,
    force_stage: str | None = None,
) -> Path | None:
    cand = entry.candidate
    show_ws = run_ws.show_ws(cand.performance_id)
    if force_stage:
        drop_stage_artifacts(show_ws, force_stage)

    pid = cand.performance_id
    with step(f"[{pid}] selecting recording"):
        identifier = run_select_recording(show_ws, ia, cand, entry.assessment,
                                          audio_format=audio_format, force=force,
                                          selection=selection_cfg)
    with step(f"[{pid}] gathering"):
        show = run_gather(show_ws, ia, providers["extract_setlist"], cand, identifier,
                          audio_format=audio_format, force=force,
                          align_provider=providers.get("align_structure"),
                          setlistfm=setlistfm, structure_cfg=structure_cfg)
    dossier = entry.assessment.rationale
    if entry.external_reputation:
        dossier += "\n\nExternal reputation: " + entry.external_reputation
    with step(f"[{pid}] researching"):
        research_md = run_research(show_ws, providers["deep_research"], show, dossier, force=force)
    with step(f"[{pid}] vetting research"):
        run_vet_research(show_ws, providers["vet_research"], show, research_md, force=force)
    show = read_model(show_ws.show, Show)  # vet may have flagged it
    if show.needs_review:
        log.warning("skipping %s: needs review (%s)", cand.performance_id, "; ".join(show.review_flags))
        return None
    notes = None
    if not script and show_ws.dj_notes_json.exists():
        # replaying a later stage (e.g. package) from a prior --script run: reuse the
        # cached script so the rebuilt manifest agrees with the dj-notes.md in the package.
        notes = read_model(show_ws.dj_notes_json, DJNotes)
    if script:
        reviews = read_json(show_ws.reviews) if show_ws.reviews.exists() else []
        with step(f"[{pid}] synthesizing"):
            notes = run_synthesize(show_ws, providers["synthesize"], show, research_md, reviews, force=force)
        show = read_model(show_ws.show, Show)  # synthesize may have flagged it
        if show.needs_review:
            log.warning("skipping %s: needs review (%s)", cand.performance_id, "; ".join(show.review_flags))
            return None
    with step(f"[{pid}] packaging"):
        pkg = run_package(show_ws, ia, show, notes, force=force)
    show = read_model(show_ws.show, Show)  # package may have flagged it
    if show.needs_review:
        log.warning("holding %s: flagged during packaging (%s)",
                    cand.performance_id, "; ".join(show.review_flags))
        return None
    ledger.record(LedgerEntry(
        performance_id=cand.performance_id, artist=show.artist, date=show.date,
        venue=show.venue, status="selected", run=run_name,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    ))
    return pkg
