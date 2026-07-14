import json
from pathlib import Path

from llama.models import Candidate, QualityAssessment, RecordingSummary
from llama.stages.select_recording import run_select_recording
from llama.workspace import ShowWorkspace


def mp3(name, length="05:00"):
    return {"name": name, "source": "original", "format": "VBR MP3", "length": length}


class StubIA:
    def __init__(self):
        self.md = {
            "gd73-06-10.sbd": {"metadata": {"lineage": "SBD > DAT"},
                               "files": [mp3("gd73-06-10d1t01.mp3"), mp3("gd73-06-10d1t02.mp3")]},
            "gd73-06-10.aud": {"metadata": {"source": "AUD"},
                               "files": [mp3("gd73a-d1t01.mp3"), mp3("gd73a-d1t02.mp3")]},
        }

    def metadata(self, identifier):
        return self.md[identifier]


def make_candidate():
    return Candidate(
        performance_id="GratefulDead/1973-06-10", collection="GratefulDead", date="1973-06-10",
        recordings=[
            RecordingSummary(identifier="gd73-06-10.aud", avg_rating=4.0, num_reviews=5),
            RecordingSummary(identifier="gd73-06-10.sbd", avg_rating=4.5, num_reviews=30),
        ],
    )


def assessment(complaints=None, reviewed="gd73-06-10.sbd"):
    return QualityAssessment(performance_id="GratefulDead/1973-06-10", quality_score=9.0,
                             rationale="r", recording_complaints=complaints or [],
                             reviewed_identifier=reviewed)


def test_sbd_wins_and_scores_recorded(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "show")
    chosen = run_select_recording(sws, StubIA(), make_candidate(), assessment())
    assert chosen == "gd73-06-10.sbd"
    sel = json.loads(sws.selection.read_text())
    assert sel["identifier"] == "gd73-06-10.sbd"
    assert set(sel["scores"]) == {"gd73-06-10.sbd", "gd73-06-10.aud"}
    assert sel["scores"]["gd73-06-10.sbd"]["lineage"] == "sbd"


def test_complaints_apply_only_to_reviewed_recording(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "show")
    # pile complaints onto the sbd until the aud outscores it
    chosen = run_select_recording(
        sws, StubIA(), make_candidate(),
        assessment(complaints=["hiss", "cuts", "dropouts", "levels"], reviewed="gd73-06-10.sbd"),
    )
    sel = json.loads(sws.selection.read_text())
    sbd, aud = sel["scores"]["gd73-06-10.sbd"], sel["scores"]["gd73-06-10.aud"]
    assert sbd["score"] < score_without_complaints(sws, tmp_path)  # penalized
    assert chosen in ("gd73-06-10.sbd", "gd73-06-10.aud")  # decided by score, not order


def score_without_complaints(sws, tmp_path):
    clean = ShowWorkspace(tmp_path / "clean")
    run_select_recording(clean, StubIA(), make_candidate(), assessment())
    return json.loads(clean.selection.read_text())["scores"]["gd73-06-10.sbd"]["score"]


def test_skips_when_selection_exists(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "show")
    run_select_recording(sws, StubIA(), make_candidate(), assessment())

    class ExplodingIA:
        def metadata(self, identifier):
            raise AssertionError("must not re-fetch")

    assert run_select_recording(sws, ExplodingIA(), make_candidate(), assessment()) == "gd73-06-10.sbd"
