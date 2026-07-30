from collections import defaultdict

from llama.models import (
    DJAudio,
    DJNotes,
    Manifest,
    ManifestBriefing,
    ManifestTrack,
    SetBreak,
    Show,
)


def build_manifest(
    show: Show,
    notes: DJNotes | None,
    packaged: list[ManifestTrack],
    *,
    briefing: ManifestBriefing,
    context: str = "",
    research: str | None = None,
    reviews: str | None = None,
    research_vetted: bool = False,
    dj_audio: DJAudio | None = None,
    profile: str | None = None,
) -> Manifest:
    per_set: dict[str, float] = defaultdict(float)
    for t in packaged:
        per_set[t.set] += t.duration_sec or 0.0
    breaks = [SetBreak(after_track=idx) for idx in show.set_breaks]
    return Manifest(
        show={"artist": show.artist, "date": show.date, "venue": show.venue,
              "city": show.city, "context": context},
        source={"performance_id": show.performance_id, "identifier": show.identifier,
                "url": show.source_url, "lineage": show.lineage, "profile": profile},
        tracks=packaged,
        set_breaks=breaks,
        briefing=briefing,
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


def interleave_broadcast(tracks: list[ManifestTrack], dj_audio: DJAudio) -> list[str]:
    """Package-relative paths in broadcast order: each set's lead-in before
    that set's first track, then the tracks, then dj_audio.outro after the
    last one. An encore set has no key in set_intros and so gets no lead-in —
    it plays straight into the outro. Music paths are `audio/<file>`; the
    dj_audio paths already carry their own `dj-audio/` prefix.
    """
    paths: list[str] = []
    seen: set[str] = set()
    for t in tracks:
        if t.set not in seen:
            seen.add(t.set)
            intro = dj_audio.set_intros.get(t.set)
            if intro:
                paths.append(intro)
        paths.append(f"audio/{t.filename}")
    paths.append(dj_audio.outro)
    return paths


def broadcast_m3u_text(tracks: list[ManifestTrack], dj_audio: DJAudio) -> str:
    return "\n".join(["#EXTM3U", *interleave_broadcast(tracks, dj_audio)]) + "\n"
