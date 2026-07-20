import logging
import re

from llama import jerrybase
from llama.config import StructureConfig
from llama.junk import FORMAT_BY_AUDIO, filter_files
from llama.ia_client import IAError
from llama.llm.provider import LLMError, TaskFailed
from llama.llm.tasks import run_json_task
from llama.models import (AlignedStructure, Candidate, ParsedSetlist, Show,
                          SourcedParse, StructureInfo)
from llama.setlist import parse_setlist
from llama.structure import (align, apply_llm_alignment, blend_segues,
                             from_setlistfm, norm_title, rank_parses, structure_guard)
from llama.titles import clean_tag_title, is_real_title, resolve_titles, set_breaks
from llama.workspace import ShowWorkspace, read_model, should_run, write_artifact

log = logging.getLogger("llama")


_EVENT_SUFFIX = re.compile(r"/e(\d+)$")


def _event_kind(pid: str) -> tuple[str | None, int | None]:
    """Read the per-event grouping suffix: ('event', N) | ('spans', None) |
    ('unassigned', None) | (None, None)."""
    m = _EVENT_SUFFIX.search(pid)
    if m:
        return "event", int(m.group(1))
    tail = pid.rsplit("/", 1)[-1]
    if tail in ("spans", "unassigned"):
        return tail, None
    return None, None


def _norm_place(s: str) -> str:
    """Lowercase, alphanumerics and spaces only, collapsed whitespace - the
    normal form for comparing archive and jerrybase venue strings."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split())


def _description(meta: dict) -> str:
    desc = meta.get("description") or ""
    if isinstance(desc, list):
        desc = "\n".join(str(d) for d in desc)
    return str(desc)


def _creator(meta: dict) -> str | None:
    creator = meta.get("creator")
    if isinstance(creator, list):
        creator = creator[0] if creator else None
    return creator


def _sibling_titles(ia, candidate: Candidate, identifier: str, want: str, n: int) -> list[str] | None:
    for rec in candidate.recordings:
        if rec.identifier == identifier:
            continue
        kept, _, _ = filter_files(ia.metadata(rec.identifier).get("files", []), want_format=want)
        titles = [clean_tag_title(f.get("title")) for f in kept]
        if len(kept) == n and all(is_real_title(t) for t in titles):
            return titles
    return None


def _collect_parses(ia, candidate: Candidate, identifier: str, chosen_meta: dict):
    """Parse every recording's description. Chosen recording first so it wins
    rank ties among copy-paste descriptions."""
    parses: list[SourcedParse] = []
    notes: list[str] = []
    descriptions: list[str] = []
    ordered = sorted(candidate.recordings, key=lambda r: r.identifier != identifier)
    for rec in ordered:
        if rec.identifier == identifier:
            meta = chosen_meta
        else:
            try:
                meta = ia.metadata(rec.identifier).get("metadata", {})
            except IAError as err:
                notes.append(f"could not fetch sibling {rec.identifier}: {err}")
                continue
        desc = _description(meta)
        descriptions.append(desc)
        source = "chosen" if rec.identifier == identifier else f"lma:{rec.identifier}"
        parses.append(SourcedParse(source=source, parsed=parse_setlist(desc)))
    return parses, notes, descriptions


def _format_tracks(tracks) -> str:
    return "\n".join(
        f"{t.index} | {t.filename} | {t.title} | {t.duration_sec or '?'}" for t in tracks
    )


def _format_setlist(canonical: ParsedSetlist) -> str:
    return "\n".join(
        f"[set {i.set}] {i.title}{' >' if i.segue else ''}" for i in canonical.items
    )


def run_gather(
    show_ws: ShowWorkspace,
    ia,
    provider,
    candidate: Candidate,
    identifier: str,
    audio_format: str = "mp3",
    force: bool = False,
    align_provider=None,
    setlistfm=None,
    structure_cfg: StructureConfig | None = None,
    jerrybase_enabled: bool = False,
) -> Show:
    if not should_run(show_ws.show, force):
        return read_model(show_ws.show, Show)
    structure_cfg = structure_cfg or StructureConfig()

    md = ia.metadata(identifier)
    meta = md.get("metadata", {})
    artist = str(_creator(meta) or candidate.collection)
    want = FORMAT_BY_AUDIO[audio_format]
    kept, excluded, ordering = filter_files(md.get("files", []), want_format=want)

    # Canonical performance setlist: every recording's description, plus
    # setlist.fm when configured, ranked pick-best.
    parses, notes, descriptions = _collect_parses(ia, candidate, identifier, meta)
    if setlistfm is not None:
        raw = setlistfm.setlist(artist, candidate.date,
                                venue=candidate.venue, city=candidate.city)
        converted = from_setlistfm(raw) if raw else None
        if converted is not None:
            parses.insert(0, SourcedParse(source="setlist.fm", parsed=converted))

    best = rank_parses(parses, target_count=len(kept))
    if best is None:
        longest = max(descriptions, key=len, default="")
        if longest.strip():
            parsed = run_json_task(provider, "extract_setlist", ParsedSetlist,
                                   description=longest)
            best = SourcedParse(source="llm", parsed=parsed)
    canonical = best.parsed if best else ParsedSetlist()
    if best is not None and best.source == "setlist.fm":
        best_lma = rank_parses([p for p in parses if p.source != "setlist.fm"],
                               target_count=len(kept))
        canonical = blend_segues(canonical, best_lma.parsed if best_lma else None)

    siblings = None
    if any(not is_real_title(clean_tag_title(f.get("title"))) for f in kept) and (
        canonical.confidence == "low" or len(canonical.items) != len(kept)
    ):
        siblings = _sibling_titles(ia, candidate, identifier, want, len(kept))
    tracks = resolve_titles(kept, canonical, sibling_titles=siblings)

    # Jerrybase structure evidence (no-op for artists absent from the dataset).
    # A per-event candidate (/eN) selects events[N-1] for every evidence check.
    events = jerrybase.lookup(artist, candidate.date) if jerrybase_enabled else []
    kind, n = _event_kind(candidate.performance_id)
    if kind == "event" and events and 1 <= n <= len(events):
        event = events[n - 1]
    elif kind == "event":
        event = None
    elif len(events) == 1:
        event = events[0]
    else:
        event = None

    result = align(tracks, canonical)
    alignment = "deterministic"
    flags = []
    if canonical.items and result.coverage < structure_cfg.align_coverage_threshold:
        anchored = jerrybase.anchor_breaks(tracks, event) if event is not None else None
        if anchored is not None:
            # Deterministic break anchoring from jerrybase closers: skip the LLM.
            result = result.model_copy(update={"sets": anchored})
            alignment = "jerrybase"
            notes.append("set breaks anchored from jerrybase")
        else:
            llm_result = None
            if align_provider is not None:
                try:
                    resp = run_json_task(align_provider, "align_structure", AlignedStructure,
                                         tracks=_format_tracks(tracks),
                                         setlist=_format_setlist(canonical))
                    llm_result = apply_llm_alignment(tracks, resp)
                except (TaskFailed, LLMError) as err:
                    log.warning("align_structure failed: %s", err)
            if llm_result is not None and llm_result.coverage >= structure_cfg.align_coverage_threshold:
                # Deliberate trade-off: apply_llm_alignment never populates
                # conflicts, so any deterministic-alignment conflicts are
                # dropped when the LLM realignment wins.
                result, alignment = llm_result, "llm"
            else:
                flags.append("low-confidence structure alignment")

    tracks = [t.model_copy(update={"set": s, "segue": g})
              for t, s, g in zip(tracks, result.sets, result.segues)]
    breaks = set_breaks(tracks)

    # Multi-event handling. Held grouping catch-alls flag directly; an
    # unpartitioned multi-event date keeps the blanket flag (defensive); a
    # per-event candidate whose aligned tracks span >1 event was mislabeled.
    if kind == "spans":
        flags.append(f"tape spans {len(events)} events")
    elif kind == "unassigned":
        flags.append("unassigned multi-event recordings")
    elif kind is None and len(events) > 1:
        venue_list = ", ".join(sorted({e.venue for e in events}))
        flags.append(f"multi-event date: {len(events)} jerrybase events at {venue_list}")
    elif kind == "event" and len(events) > 1:
        spanned = sum(
            1 for ev in events
            if any(norm_title(t.title) == norm_title(s.closer)
                   for s in ev.sets for t in tracks)
        )
        if spanned > 1:
            flags.append(f"tape spans {len(events)} events")

    # Venue enrichment + cross-check (single-event only; never overwrite a venue).
    venue, city, venue_source = candidate.venue, candidate.city, "item"
    if event is not None:
        if not (venue and venue.strip()):
            venue, city, venue_source = event.venue, event.city, "jerrybase"
        elif _norm_place(venue) != _norm_place(event.venue):
            flags.append(f"venue mismatch: archive '{venue}' vs jerrybase '{event.venue}'")

    # Closer tripwire (single-event, non-anchored alignments; anchoring places
    # breaks at closers by construction, so it cannot contradict itself).
    if event is not None and alignment != "jerrybase":
        hard, soft = jerrybase.closer_contradictions(tracks, event)
        flags += hard
        notes += soft

    expected_sets = len({s.name for s in event.sets}) if event is not None else None
    guard = structure_guard(tracks, breaks,
                            evidence_sets={i.set for i in canonical.items},
                            min_minutes=structure_cfg.guard_min_minutes,
                            expected_set_count=expected_sets)
    if guard:
        flags.append(guard)

    if any(t.title_source == "unresolved" for t in tracks):
        flags.append("unresolved track titles")
    if canonical.confidence == "low":
        flags.append("low-confidence setlist")
    if not tracks:
        flags.append("no playable tracks")

    structure_info = None
    if best is not None:
        structure_info = StructureInfo(source=best.source, alignment=alignment,
                                       coverage=result.coverage,
                                       conflicts=result.conflicts + notes)

    show = Show(
        performance_id=candidate.performance_id,
        identifier=identifier,
        artist=artist,
        date=candidate.date,
        venue=venue,
        city=city,
        venue_source=venue_source,
        tracks=tracks,
        set_breaks=breaks,
        excluded_files=excluded,
        order_source=ordering["order_source"],
        reordered=ordering["reordered"],
        lineage=meta.get("lineage") or meta.get("source"),
        source_url=f"https://archive.org/details/{identifier}",
        needs_review=bool(flags),
        review_flags=flags,
        structure=structure_info,
    )
    write_artifact(show_ws.show, show)
    write_artifact(show_ws.reviews, md.get("reviews", []))
    return show
