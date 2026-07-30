"""Test fixture: fabricate a full v3 package on disk.

Modeled on llama's own `packages/llama/tests/helpers.py::build_ready` v3
manifest shape -- kept byte-shape-compatible by hand since emcee never
imports llama. Every later emcee task's tests build their fixtures through
`build_package`, so its output shape is load-bearing beyond this task.
"""

import json
from pathlib import Path

SONGS = [
    "Morning Dew",
    "Sugaree",
    "Jack Straw",
    "China Cat Sunflower",
    "I Know You Rider",
    "Truckin'",
    "Not Fade Away",
    "Wharf Rat",
    "Sugar Magnolia",
    "One More Saturday Night",
]


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def build_package(
    root: Path,
    slug: str = "gd1973-06-10",
    *,
    voiced: bool = False,
    profile: str | None = None,
    narration: str = "full",
    sets: tuple[str, ...] = ("1", "2"),
    encore: bool = True,
) -> Path:
    """Fabricate a full v3 package at `root / slug` and return its directory.

    `sets` drives the non-encore set labels ("1", "2", ...); `encore=True`
    appends an "encore" set with one track. `set_breaks` entries land at the
    physical track boundary after each set (including after the last
    non-encore set, i.e. before the encore, when there is one).

    `set_intros`/`dj_audio.set_intros` (when `voiced`) are keyed by the
    non-encore `sets` labels only -- the encore folds into `outro`, matching
    llama's settled DJ-segment-consolidation design; do not add an encore
    intro key.
    """
    pkg_dir = root / slug
    audio_dir = pkg_dir / "audio"

    all_sets = list(sets) + (["encore"] if encore else [])
    tracks: list[dict] = []
    set_breaks: list[dict] = []
    index = 0
    song_i = 0
    for set_label in all_sets:
        track_count = 1 if set_label == "encore" else 2
        for _ in range(track_count):
            index += 1
            title = SONGS[song_i % len(SONGS)]
            song_i += 1
            filename = f"{index:02d} - {title}.mp3"
            tracks.append(
                {
                    "index": index,
                    "set": set_label,
                    "title": title,
                    "filename": filename,
                }
            )
        set_breaks.append({"after_track": index})
    # The break after the very last track (end of show) isn't a "break" --
    # only interior boundaries are meaningful.
    if set_breaks:
        set_breaks.pop()

    # llama's real Manifest model always serializes "profile" (default None)
    # whether or not a run came from a profile -- match that shape
    # explicitly rather than omitting the key when profile is None.
    source = {"performance_id": f"GratefulDead/{slug}", "profile": profile}

    manifest: dict = {
        "schema_version": 3,
        "briefing": {
            "file": "briefing.md",
            "json": "briefing.json",
            "narration": narration,
            "vetted": False,
        },
        "show": {
            "artist": "Grateful Dead",
            "date": "1973-06-10",
            "venue": "Some Venue",
            "city": None,
            "context": "",
        },
        "source": source,
        "tracks": tracks,
        "set_breaks": set_breaks,
        # llama's real Manifest model always serializes these two keys
        # (default None) whether or not a show is voiced -- match that
        # shape explicitly rather than omitting the keys, so a package
        # fabricated with voiced=False is byte-shape-identical to what
        # `deliver` actually writes.
        "dj_notes": None,
        "dj_audio": None,
        "total_duration_sec": 0,
        "set_durations_sec": {},
    }

    if voiced:
        non_encore_sets = list(sets)
        manifest["dj_notes"] = {
            "context": "Spring '73",
            "set_intros": {s: f"Welcome to set {s}." for s in non_encore_sets},
            "outro": "Thanks for listening.",
            "mentioned_songs": [],
        }
        manifest["dj_audio"] = {
            "set_intros": {
                s: f"dj-audio/set{s}-intro.mp3" for s in non_encore_sets
            },
            "outro": "dj-audio/99-outro.mp3",
        }

    _write_json(pkg_dir / "manifest.json", manifest)

    briefing_json = {
        "context": "Spring '73 tour context.",
        "significance": "A well-loved show.",
        "per_set": {s: [f"Highlights of set {s}."] for s in sets},
        "notable_moments": [],
        "review_sentiment": "Reviewers loved it.",
        "non_attendee_sentiment": True,
        "cautions": [],
        "narration": narration,
        "mentioned_songs": [],
    }
    _write_json(pkg_dir / "briefing.json", briefing_json)
    _write_text(pkg_dir / "briefing.md", "# Some Venue -- 1973-06-10\n\nA well-loved show.\n")

    for t in tracks:
        _write_text(audio_dir / t["filename"], "x")

    if voiced:
        for s in sets:
            _write_text(pkg_dir / "dj-audio" / f"set{s}-intro.mp3", "x")
        _write_text(pkg_dir / "dj-audio" / "99-outro.mp3", "x")
        _write_text(pkg_dir / "dj-notes.md", "Welcome to the show.\n")
        _write_text(pkg_dir / "broadcast.m3u", "#EXTM3U\n")

    return pkg_dir
