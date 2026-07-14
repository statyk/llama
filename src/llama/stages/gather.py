from llama.junk import FORMAT_BY_AUDIO, filter_files
from llama.models import Candidate, ParsedSetlist, Show
from llama.setlist import parse_setlist
from llama.llm.tasks import run_json_task
from llama.titles import resolve_titles, set_breaks
from llama.workspace import ShowWorkspace, read_model, should_run, write_artifact


def _description(meta: dict) -> str:
    desc = meta.get("description") or ""
    if isinstance(desc, list):
        desc = "\n".join(str(d) for d in desc)
    return str(desc)


def _sibling_titles(ia, candidate: Candidate, identifier: str, want: str, n: int) -> list[str] | None:
    for rec in candidate.recordings:
        if rec.identifier == identifier:
            continue
        kept, _ = filter_files(ia.metadata(rec.identifier).get("files", []), want_format=want)
        if len(kept) == n and all(str(f.get("title") or "").strip() for f in kept):
            return [f["title"] for f in sorted(kept, key=lambda f: f["name"])]
    return None


def run_gather(
    show_ws: ShowWorkspace,
    ia,
    provider,
    candidate: Candidate,
    identifier: str,
    audio_format: str = "mp3",
    force: bool = False,
) -> Show:
    if not should_run(show_ws.show, force):
        return read_model(show_ws.show, Show)

    md = ia.metadata(identifier)
    meta = md.get("metadata", {})
    want = FORMAT_BY_AUDIO[audio_format]
    kept, excluded = filter_files(md.get("files", []), want_format=want)

    desc = _description(meta)
    parsed = parse_setlist(desc)
    if parsed.confidence == "low" and desc.strip():
        parsed = run_json_task(provider, "extract_setlist", ParsedSetlist, description=desc)

    siblings = None
    if any(not str(f.get("title") or "").strip() for f in kept) and (
        parsed.confidence == "low" or len(parsed.items) != len(kept)
    ):
        siblings = _sibling_titles(ia, candidate, identifier, want, len(kept))

    tracks = resolve_titles(kept, parsed, sibling_titles=siblings)
    flags = []
    if any(t.title_source == "unresolved" for t in tracks):
        flags.append("unresolved track titles")
    if parsed.confidence == "low":
        flags.append("low-confidence setlist")
    if not tracks:
        flags.append("no playable tracks")

    creator = meta.get("creator")
    if isinstance(creator, list):
        creator = creator[0] if creator else None
    show = Show(
        performance_id=candidate.performance_id,
        identifier=identifier,
        artist=str(creator or candidate.collection),
        date=candidate.date,
        venue=candidate.venue,
        city=candidate.city,
        tracks=tracks,
        set_breaks=set_breaks(tracks),
        excluded_files=excluded,
        lineage=meta.get("lineage") or meta.get("source"),
        source_url=f"https://archive.org/details/{identifier}",
        needs_review=bool(flags),
        review_flags=flags,
    )
    write_artifact(show_ws.show, show)
    write_artifact(show_ws.reviews, md.get("reviews", []))
    return show
