from pathlib import Path

from llama.catalog import ARCHIVE_URL, ConsideredRecording, RecordingInfo, recording_info
from llama.workspace import ShowWorkspace, write_artifact


def test_recording_info_three_scored_recordings(tmp_path: Path):
    ws = ShowWorkspace(tmp_path / "shows" / "s")
    write_artifact(ws.selection, {
        "identifier": "gd73-mid",
        "scores": {
            "gd73-low": {"score": 0.2, "lineage": "aud", "kept_tracks": 10},
            "gd73-mid": {"score": 0.5, "lineage": "sbd", "kept_tracks": 20},
            "gd73-high": {"score": 0.9, "lineage": "matrix", "kept_tracks": 22},
        },
    })

    info = recording_info(ws)

    assert info is not None
    assert info.identifier == "gd73-mid"
    assert info.url == ARCHIVE_URL.format(identifier="gd73-mid")
    assert info.url == "https://archive.org/details/gd73-mid"
    assert info.considered == [
        ConsideredRecording(identifier="gd73-high", score=0.9, lineage="matrix",
                            kept_tracks=22),
        ConsideredRecording(identifier="gd73-low", score=0.2, lineage="aud",
                            kept_tracks=10),
    ]


def test_recording_info_single_recording_yields_no_considered(tmp_path: Path):
    ws = ShowWorkspace(tmp_path / "shows" / "s")
    write_artifact(ws.selection, {
        "identifier": "gd73-only",
        "scores": {"gd73-only": {"score": 0.7, "lineage": "sbd", "kept_tracks": 20}},
    })

    info = recording_info(ws)

    assert info is not None
    assert info.identifier == "gd73-only"
    assert info.considered == []


def test_recording_info_missing_selection_returns_none(tmp_path: Path):
    ws = ShowWorkspace(tmp_path / "shows" / "s")

    assert recording_info(ws) is None


def test_recording_info_defaults_missing_optional_keys(tmp_path: Path):
    ws = ShowWorkspace(tmp_path / "shows" / "s")
    write_artifact(ws.selection, {
        "identifier": "gd73-chosen",
        "scores": {
            "gd73-chosen": {"score": 0.5},
            "gd73-sparse": {},
        },
    })

    info = recording_info(ws)

    assert info is not None
    assert info.considered == [
        ConsideredRecording(identifier="gd73-sparse", score=0.0, lineage="",
                            kept_tracks=0),
    ]
