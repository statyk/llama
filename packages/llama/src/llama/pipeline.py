import logging
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path

from herder import provider_ladder
from llama.audio_reuse import ReusePlan
from llama.config import Config
from llama.ledger import Ledger
from llama.models import LedgerEntry, Provenance, Show, ShortlistEntry
from llama.stages import brief, package
from llama.stages.brief import run_brief
from llama.stages.gather import run_gather
from llama.stages.package import run_package
from llama.stages.research import run_research
from llama.stages.select_recording import run_select_recording
from llama.util import cap_across_artists
from llama.stages.vet_research import run_vet_research
from llama.status import step
from llama.workspace import (RunWorkspace, ShowWorkspace, drop_stage_artifacts,
                             read_json, read_model, write_artifact)

log = logging.getLogger("llama")

TASK_KEYS = ["interpret", "score_reviews", "light_research",
             "extract_setlist", "deep_research", "brief",
             "find_artists", "align_structure", "vet_research"]


def make_providers(config: Config) -> dict:
    settings = config.llm_settings()
    return {key: provider_ladder(settings, key) for key in TASK_KEYS}


class _CountedProvider:
    """Delegates to a provider, counting `complete`/`research` calls on the
    shared counter BEFORE delegating, so a call that raises still counts."""

    def __init__(self, inner, counter: list[int]):
        self._inner = inner
        self._counter = counter

    def complete(self, *args, **kwargs):
        self._counter[0] += 1
        return self._inner.complete(*args, **kwargs)

    def research(self, *args, **kwargs):
        self._counter[0] += 1
        return self._inner.research(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _CountedProviders(Mapping):
    """Lazy view over `inner` (so a defaultdict's missing keys still answer)
    whose values are wrapped: ladder -> list of wrappers, provider -> wrapper,
    None -> None."""

    def __init__(self, inner: Mapping, counter: list[int]):
        self._inner = inner
        self._counter = counter

    def __getitem__(self, key):
        value = self._inner[key]
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return [_CountedProvider(p, self._counter) for p in value]
        return _CountedProvider(value, self._counter)

    def __iter__(self):
        return iter(self._inner)

    def __len__(self):
        return len(self._inner)


def count_llm_calls(providers: Mapping) -> tuple[Mapping, Callable[[], int]]:
    """Wrap `providers` so LLM calls through it are counted. A show that made
    none (download-only resume, already packaged) is not a pacing sample."""
    counter = [0]
    return _CountedProviders(providers, counter), lambda: counter[0]


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


def _blocking_flags(show_ws: ShowWorkspace, show: Show) -> list[str]:
    """The review flags that hold `show` now. A brief or package flag whose
    artifact is gone (a redo dropped it) judged something that no longer
    exists: that stage is about to run and replace its own flags, so it does
    not block. The flag itself stays in show.json until the re-run succeeds,
    so a failed redo leaves the show held."""
    stale = tuple(prefix for prefix, marker in (
        (brief.FLAG_PREFIX, show_ws.briefing_json),
        (package.FLAG_PREFIX, show_ws.package_dir / "manifest.json"))
        if not marker.exists())
    return [f for f in show.review_flags if not f.startswith(stale)]


def process_show(
    run_ws: RunWorkspace,
    ia,
    ledger: Ledger,
    entry: ShortlistEntry,
    providers: dict,
    run_name: str,
    audio_format: str = "mp3",
    force: bool = False,
    setlistfm=None,
    structure_cfg=None,
    selection_cfg=None,
    jerrybase_enabled: bool = True,
    force_stage: str | None = None,
    profile: str | None = None,
    audio_reuse: ReusePlan | None = None,
) -> Path | None:
    cand = entry.candidate
    show_ws = run_ws.show_ws(cand.performance_id)
    if force_stage:
        drop_stage_artifacts(show_ws, force_stage)

    pid = cand.performance_id
    dossier = entry.assessment.rationale
    if entry.external_reputation:
        dossier += "\n\nExternal reputation: " + entry.external_reputation
    write_artifact(show_ws.provenance, Provenance(
        performance_id=pid, run=run_name, profile=profile, dossier=dossier, candidate=cand,
        assessment=entry.assessment,
        processed_at=datetime.now(timezone.utc).isoformat(),
    ))
    with step(f"[{pid}] selecting recording"):
        identifier = run_select_recording(show_ws, ia, cand, entry.assessment,
                                          audio_format=audio_format, force=force,
                                          selection=selection_cfg)
    with step(f"[{pid}] gathering"):
        show = run_gather(show_ws, ia, providers["extract_setlist"], cand, identifier,
                          audio_format=audio_format, force=force,
                          align_provider=providers.get("align_structure"),
                          setlistfm=setlistfm, structure_cfg=structure_cfg,
                          jerrybase_enabled=jerrybase_enabled)
    with step(f"[{pid}] researching"):
        research_md = run_research(show_ws, providers["deep_research"], show, dossier, force=force)
    with step(f"[{pid}] vetting research"):
        run_vet_research(show_ws, providers["vet_research"], show, research_md, force=force)
    show = read_model(show_ws.show, Show)  # vet may have flagged it
    if blocking := _blocking_flags(show_ws, show):
        log.warning("skipping %s: needs review (%s)", cand.performance_id, "; ".join(blocking))
        return None
    reviews = read_json(show_ws.reviews) if show_ws.reviews.exists() else []
    with step(f"[{pid}] briefing"):
        run_brief(show_ws, providers["brief"], show, research_md, reviews, force=force)
    show = read_model(show_ws.show, Show)  # brief's guard may have flagged it
    if blocking := _blocking_flags(show_ws, show):
        log.warning("skipping %s: needs review (%s)", cand.performance_id, "; ".join(blocking))
        return None
    with step(f"[{pid}] packaging"):
        pkg = run_package(show_ws, ia, show, force=force, profile=profile, reuse=audio_reuse)
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
