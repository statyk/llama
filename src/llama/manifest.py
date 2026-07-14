from collections import defaultdict

from llama.models import DJNotes, Manifest, ManifestTrack, SetBreak, Show


def build_manifest(show: Show, notes: DJNotes, packaged: list[ManifestTrack]) -> Manifest:
    per_set: dict[str, float] = defaultdict(float)
    for t in packaged:
        per_set[t.set] += t.duration_sec or 0.0
    return Manifest(
        show={"artist": show.artist, "date": show.date, "venue": show.venue,
              "city": show.city, "context": notes.context},
        source={"performance_id": show.performance_id, "identifier": show.identifier,
                "url": show.source_url, "lineage": show.lineage},
        tracks=packaged,
        set_breaks=[SetBreak(after_track=idx, note_index=i)
                    for i, idx in enumerate(show.set_breaks)],
        dj_notes=notes,
        total_duration_sec=sum(t.duration_sec or 0.0 for t in packaged),
        set_durations_sec=dict(per_set),
    )


def m3u_text(filenames: list[str]) -> str:
    return "\n".join(["#EXTM3U", *[f"audio/{name}" for name in filenames]]) + "\n"
