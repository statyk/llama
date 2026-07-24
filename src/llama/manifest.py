from collections import defaultdict

from llama.models import DJAudio, DJNotes, Manifest, ManifestTrack, SetBreak, Show


def build_manifest(
    show: Show,
    notes: DJNotes | None,
    packaged: list[ManifestTrack],
    context: str = "",
    research: str | None = None,
    reviews: str | None = None,
    research_vetted: bool = False,
    dj_audio: DJAudio | None = None,
) -> Manifest:
    per_set: dict[str, float] = defaultdict(float)
    for t in packaged:
        per_set[t.set] += t.duration_sec or 0.0
    breaks = [SetBreak(after_track=idx) for idx in show.set_breaks]
    return Manifest(
        show={"artist": show.artist, "date": show.date, "venue": show.venue,
              "city": show.city, "context": context},
        source={"performance_id": show.performance_id, "identifier": show.identifier,
                "url": show.source_url, "lineage": show.lineage},
        tracks=packaged,
        set_breaks=breaks,
        dj_notes=notes,
        dj_audio=dj_audio,
        research=research,
        reviews=reviews,
        research_vetted=research_vetted,
        total_duration_sec=sum(t.duration_sec or 0.0 for t in packaged),
        set_durations_sec=dict(per_set),
    )


def m3u_text(filenames: list[str]) -> str:
    return "\n".join(["#EXTM3U", *[f"audio/{name}" for name in filenames]]) + "\n"
