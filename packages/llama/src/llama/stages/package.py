from pathlib import Path

from llama import audio_reuse
from llama.audio import packaged_filename, read_duration, tag_audio
from llama.errors import LlamaError
from llama.manifest import build_manifest, m3u_text
from llama.models import (
    Briefing,
    ManifestBriefing,
    ManifestTrack,
    Show,
    VettingResult,
)
from llama.status import detail
from llama.util import length_seconds, reviews_digest
from llama.workspace import (
    ShowWorkspace,
    read_json,
    read_model,
    write_artifact,
)

DURATION_TOLERANCE_S = 5.0
# Every packaging review flag starts with this.
FLAG_PREFIX = "duration mismatch on "


def build_package(show_ws: ShowWorkspace, ia, show: Show,
                  force: bool = False, profile: str | None = None, *,
                  reuse: audio_reuse.ReusePlan | None = None) -> tuple[Path, list[str]]:
    """Build the package (audio, briefing copies, research, reviews, m3u,
    manifest last) and return `(package dir, package-stage flags)`. Writes no
    `show.json`: `run_package` replaces its own flags with these, and `llama
    reapply` (spec slice 6) writes them in its one final `show.json` write. An existing
    manifest short-circuits with no flags unless `force`.

    `reuse` (spec 5.4, from `audio_reuse.plan_reuse` before the re-gather)
    re-uses audio this show already has instead of downloading it. The files
    in `package/audio/` stay in place only when the library manifest's names,
    read at plan time, equal the new packaged names; otherwise they are moved
    aside first, because a name that exists is never downloaded and an
    old-numbered file would be inherited by a renumbered track sharing its
    title. The decision is made from what is on disk, never from show.json
    (a held re-gather can already have written the new list over audio that
    carries the old numbering). A still-missing file is then copied from the
    paired aside or station file when its length checks out, else
    downloaded. The caller's unit puts the aside back on failure and deletes
    it on success. `reuse=None` is the old behaviour; under `force` every
    file downloads as before (the aside step still runs)."""
    pkg = show_ws.package_dir
    manifest_path = pkg / "manifest.json"
    if manifest_path.exists() and not force:
        return pkg, []

    audio_dir = pkg / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    files = ia.metadata(show.identifier).get("files", [])
    md5s = {f["name"]: f.get("md5") for f in files}

    if reuse is not None:
        names = [packaged_filename(t.index, t.title, Path(t.filename).suffix) for t in show.tracks]
        in_place = reuse.library_names is not None and list(reuse.library_names) == names
        if not in_place and any(p.is_file() for p in audio_dir.iterdir()):
            audio_reuse.set_aside(show_ws)
        lengths = {f["name"]: length_seconds(f.get("length")) for f in files}

    venue_city = ", ".join(p for p in [show.venue, show.city] if p)

    packaged: list[ManifestTrack] = []
    flags: list[str] = []
    for t in show.tracks:
        out_name = packaged_filename(t.index, t.title, Path(t.filename).suffix)
        dest = audio_dir / out_name
        if not dest.exists() or force:
            placed = None
            if reuse is not None and not force:
                placed = audio_reuse.reuse_into(dest, t.filename, lengths.get(t.filename), reuse,
                                                show_ws, tolerance=DURATION_TOLERANCE_S)
            if placed is None:
                detail(f"downloading {t.index}/{len(show.tracks)}: {t.filename}")
                ia.download_file(show.identifier, t.filename, dest, md5=md5s.get(t.filename))
            else:
                detail(f"re-using {t.index}/{len(show.tracks)}: {t.filename} ({placed} copy)")
        tag_audio(
            dest,
            artist=show.artist,
            album=f"{show.date} {venue_city}".strip(),
            title=t.title, track=t.index, date=show.date, comment=show.identifier,
        )
        real = read_duration(dest)
        if real is not None and t.duration_sec is not None and abs(real - t.duration_sec) > DURATION_TOLERANCE_S:
            flags.append(f"{FLAG_PREFIX}{out_name}: file {real:.0f}s vs metadata {t.duration_sec:.0f}s")
        packaged.append(ManifestTrack(index=t.index, set=t.set, title=t.title,
                                      filename=out_name,
                                      duration_sec=real if real is not None else t.duration_sec,
                                      segue=t.segue))

    context = ""
    vetted = False
    if show_ws.vetting.exists():
        vr = read_model(show_ws.vetting, VettingResult)
        if vr.vetting.context:
            context = vr.vetting.context
        vetted = not vr.flags

    if not (show_ws.briefing_json.exists() and show_ws.briefing_md.exists()):
        raise LlamaError(
            f"{show.performance_id}: package requires a briefing but this show "
            "has no briefing artifacts; run `llama redo` from the brief stage")
    briefing = read_model(show_ws.briefing_json, Briefing)
    write_artifact(pkg / "briefing.md", show_ws.briefing_md.read_text())
    write_artifact(pkg / "briefing.json", show_ws.briefing_json.read_text())

    research_name = None
    if show_ws.research.exists():
        write_artifact(pkg / "research.md", show_ws.research.read_text())
        research_name = "research.md"
    reviews = read_json(show_ws.reviews) if show_ws.reviews.exists() else []
    write_artifact(pkg / "reviews.md", reviews_digest(reviews))

    write_artifact(pkg / "playlist.m3u", m3u_text([t.filename for t in packaged]))
    # Manifest last: it is the package's "outputs written only on success" marker.
    write_artifact(manifest_path, build_manifest(
        show, packaged,
        briefing=ManifestBriefing(narration=briefing.narration, vetted=vetted),
        context=context,
        research=research_name, reviews="reviews.md", research_vetted=vetted,
        profile=profile))
    return pkg, flags


def run_package(show_ws: ShowWorkspace, ia, show: Show,
                force: bool = False, profile: str | None = None) -> Path:
    built = force or not (show_ws.package_dir / "manifest.json").exists()
    pkg, flags = build_package(show_ws, ia, show, force=force, profile=profile)
    if built:
        # Replace this stage's own flags (a redo's stale verdict included).
        current = read_model(show_ws.show, Show)
        kept = [f for f in current.review_flags if not f.startswith(FLAG_PREFIX)] + flags
        if kept != current.review_flags:
            write_artifact(show_ws.show, current.model_copy(
                update={"review_flags": kept, "needs_review": bool(kept)}))
    return pkg
