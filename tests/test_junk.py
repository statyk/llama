import json
from pathlib import Path

from llama.junk import filter_files

FIXTURE = Path(__file__).parent / "fixtures" / "gd73_metadata.json"


def load_files() -> list[dict]:
    return json.loads(FIXTURE.read_text())["files"]


def test_keeps_real_tracks_sorted():
    kept, _ = filter_files(load_files())
    assert [f["name"] for f in kept] == [
        "gd73-06-10d1t01.mp3", "gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3",
        "gd73-06-10d2t01.mp3", "gd73-06-10d2t02.mp3", "gd73-06-10d3t01.mp3",
    ]


def test_spam_file_excluded_with_reasons():
    _, excluded = filter_files(load_files())
    spam = next(e for e in excluded if e["filename"] == "FOLLOW-ME @BYPIKENO.mp3")
    assert "filename convention mismatch" in spam["reasons"]
    assert "implausibly short" in spam["reasons"]


def test_non_audio_files_ignored_silently():
    _, excluded = filter_files(load_files())
    names = {e["filename"] for e in excluded}
    assert "gd73-06-10.txt" not in names  # not want_format: never a candidate, not logged


def test_orphan_derivative_excluded():
    files = [
        {"name": "x1t01.mp3", "source": "derivative", "original": "ghost.shn",
         "format": "VBR MP3", "length": "05:00"},
    ]
    _, excluded = filter_files(files)
    assert excluded[0]["reasons"] == ["derivative of unknown original"]
