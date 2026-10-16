"""Test fixture: fabricate a full v3 package on disk.

Modeled on llama's own `packages/llama/tests/helpers.py::build_ready` v3
manifest shape -- kept byte-shape-compatible by hand since emcee never
imports llama. Every later emcee task's tests build their fixtures through
`build_package`, so its output shape is load-bearing beyond this task.
"""

import json
from pathlib import Path

from emcee.moves import Moves

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
    artist: str = "Grateful Dead",
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
            "artist": artist,
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


_NO_ROOT = Path("/nonexistent-emcee-root")


def no_moves() -> Moves:
    """An absent moves.json: the explicit 'no moves' every resolver call needs."""
    return Moves(path=_NO_ROOT / "moves.json", exists=False, entries={})


def voicing_for(config, pkg):
    """The one resolution `_process_one` would make for `pkg` with no moves:
    for tests that drive `process_package` directly."""
    from emcee.process import resolve_voicing
    return resolve_voicing(config, no_moves(), pkg.manifest())


def moves_of(targets: dict[str, str | None]) -> Moves:
    """A loaded moves.json mapping performance_id -> target profile."""
    return Moves(path=_NO_ROOT / "moves.json", exists=True, entries={
        pid: {"profile": profile, "package": pid.rsplit("/", 1)[-1],
              "moved_at": "2026-10-16T00:00:00Z"}
        for pid, profile in targets.items()})


def set_dj_audio(pkg_dir: Path, **fields) -> None:
    """Merge `fields` into a voiced fixture's dj_audio block (raw JSON), e.g.
    profile="southern", profile_source="move", presenter="gregg"."""
    path = pkg_dir / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["dj_audio"].update(fields)
    _write_json(path, manifest)


def write_moves_file(home: Path, targets: dict[str, str | None]) -> Path:
    """<home>/moves.json mapping performance_id -> target profile."""
    path = home / "moves.json"
    _write_json(path, {pid: {"profile": profile, "package": pid.rsplit("/", 1)[-1],
                             "moved_at": "2026-10-16T00:00:00Z"}
                       for pid, profile in targets.items()})
    return path


HOUSE_TTS = '[tts]\nbackend = "fake"\nvoice = "house-voice"\n'


def station_home(tmp_path: Path, monkeypatch, *, assign: str = "",
                 tts: str = HOUSE_TTS) -> tuple[Path, Path]:
    """An emcee home at <tmp>/home (EMCEE_ROOT set to it) whose config.toml
    points [station] root at <tmp>/station. `tts` and `assign` are TOML
    appended verbatim. Returns (home, station)."""
    home = tmp_path / "home"
    station = tmp_path / "station"
    station.mkdir(parents=True)
    home.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text(f'[station]\nroot = "{station}"\n\n{tts}\n{assign}\n')
    return home, station


def forbid_spend(monkeypatch) -> None:
    """Building any LLM or TTS provider fails the test."""
    import emcee.process as process_mod

    def boom(*a, **k):
        raise AssertionError("LLM or TTS spend")
    monkeypatch.setattr(process_mod, "provider_for", boom)
    monkeypatch.setattr(process_mod, "speech_provider_for", boom)


def notes_json() -> str:
    """A scriptwrite reply that passes script_guard for `build_package`'s
    default two-set show; for `FakeProvider(completes=[notes_json()])`."""
    return json.dumps({
        "context": "Spring '73 tour",
        "set_intros": {"1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
                       "2": "China Cat Sunflower leads set two."},
        "outro": "I Know You Rider sends us off. Thanks for listening.",
        "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"],
    })
