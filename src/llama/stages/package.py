from pathlib import Path

from llama.audio import packaged_filename, read_duration, tag_audio
from llama.manifest import build_manifest, m3u_text
from llama.models import DJNotes, ManifestTrack, Show, VettingResult
from llama.status import detail
from llama.util import reviews_digest
from llama.workspace import ShowWorkspace, read_json, read_model, write_artifact

DURATION_TOLERANCE_S = 5.0


def run_package(show_ws: ShowWorkspace, ia, show: Show, notes: DJNotes | None = None, force: bool = False) -> Path:
    pkg = show_ws.package_dir
    manifest_path = pkg / "manifest.json"
    if manifest_path.exists() and not force:
        return pkg

    audio_dir = pkg / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    md5s = {f["name"]: f.get("md5") for f in ia.metadata(show.identifier).get("files", [])}

    venue_city = ", ".join(p for p in [show.venue, show.city] if p)

    packaged: list[ManifestTrack] = []
    flags: list[str] = []
    for t in show.tracks:
        out_name = packaged_filename(t.index, t.title, Path(t.filename).suffix)
        dest = audio_dir / out_name
        if not dest.exists() or force:
            detail(f"downloading {t.index}/{len(show.tracks)}: {t.filename}")
            ia.download_file(show.identifier, t.filename, dest, md5=md5s.get(t.filename))
        tag_audio(
            dest,
            artist=show.artist,
            album=f"{show.date} {venue_city}".strip(),
            title=t.title, track=t.index, date=show.date, comment=show.identifier,
        )
        real = read_duration(dest)
        if real is not None and t.duration_sec is not None and abs(real - t.duration_sec) > DURATION_TOLERANCE_S:
            flags.append(f"duration mismatch on {out_name}: file {real:.0f}s vs metadata {t.duration_sec:.0f}s")
        packaged.append(ManifestTrack(index=t.index, set=t.set, title=t.title,
                                      filename=out_name,
                                      duration_sec=real if real is not None else t.duration_sec,
                                      segue=t.segue))

    context = notes.context if notes is not None else ""
    vetted = False
    if show_ws.vetting.exists():
        vr = read_model(show_ws.vetting, VettingResult)
        if vr.vetting.context:
            context = vr.vetting.context
        vetted = not vr.flags

    research_name = None
    if show_ws.research.exists():
        write_artifact(pkg / "research.md", show_ws.research.read_text())
        research_name = "research.md"
    reviews = read_json(show_ws.reviews) if show_ws.reviews.exists() else []
    write_artifact(pkg / "reviews.md", reviews_digest(reviews))

    write_artifact(manifest_path, build_manifest(
        show, notes, packaged, context=context,
        research=research_name, reviews="reviews.md", research_vetted=vetted))
    write_artifact(pkg / "playlist.m3u", m3u_text([t.filename for t in packaged]))
    if show_ws.dj_notes_md.exists():
        write_artifact(pkg / "dj-notes.md", show_ws.dj_notes_md.read_text())
    if flags:
        current = read_model(show_ws.show, Show)
        current.review_flags = current.review_flags + flags
        current.needs_review = True
        write_artifact(show_ws.show, current)
    return pkg
