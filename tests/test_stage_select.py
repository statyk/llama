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


class MapIA:
    """metadata dict per identifier; every item gets two playable mp3s."""

    def __init__(self, meta_by_ident):
        self.meta_by_ident = meta_by_ident

    def metadata(self, identifier):
        return {"metadata": self.meta_by_ident[identifier],
                "files": [mp3(f"{identifier}-t01.mp3"), mp3(f"{identifier}-t02.mp3")]}


def gd_candidate(date, idents):
    return Candidate(
        performance_id=f"GratefulDead/{date}", collection="GratefulDead", date=date,
        recordings=[RecordingSummary(identifier=i, avg_rating=4.5, num_reviews=10)
                    for i in idents],
    )


def select(tmp_path, candidate, ia):
    sws = ShowWorkspace(tmp_path / "show")
    chosen = run_select_recording(sws, ia, candidate, assessment())
    return chosen, json.loads(sws.selection.read_text())["scores"]


def test_favored_taper_wins_between_equal_tapes(tmp_path: Path):
    cand = gd_candidate("1973-06-10", ["gd73-06-10.sbd.hollister.111",
                                       "gd73-06-10.sbd.miller.222"])
    ia = MapIA({i: {"source": "SBD"} for i in ["gd73-06-10.sbd.hollister.111",
                                               "gd73-06-10.sbd.miller.222"]})
    chosen, _ = select(tmp_path, cand, ia)
    assert chosen == "gd73-06-10.sbd.miller.222"


def test_newest_revision_of_same_taper_preferred(tmp_path: Path):
    # Newness = shnid in the identifier, NOT upload date: the real 1969-11-02
    # millers have the older transfer (32273) uploaded a year AFTER the newer
    # one (32350). The higher shnid must win regardless.
    old, new = "gd73-06-10.sbd.miller.32273", "gd73-06-10.sbd.miller.32350"
    cand = gd_candidate("1973-06-10", [old, new])
    ia = MapIA({old: {"source": "SBD", "addeddate": "2009-01-16 22:48:28"},
                new: {"source": "SBD", "addeddate": "2008-04-16 13:29:08"}})
    chosen, scores = select(tmp_path, cand, ia)
    assert chosen == new
    assert scores[new]["score"] > scores[old]["score"]


def test_early_80s_era_prefers_matrix_and_aud_over_sbd(tmp_path: Path):
    idents = ["gd82-04-06.sbd.x.1", "gd82-04-06.aud.y.2", "gd82-04-06.mtx.z.3"]
    cand = gd_candidate("1982-04-06", idents)
    ia = MapIA({i: {} for i in idents})
    chosen, scores = select(tmp_path, cand, ia)
    assert chosen == "gd82-04-06.mtx.z.3"
    assert scores["gd82-04-06.aud.y.2"]["score"] > scores["gd82-04-06.sbd.x.1"]["score"]


def test_gd_defaults_do_not_touch_other_collections(tmp_path: Path):
    cand = Candidate(
        performance_id="Mekons/1989-12-02", collection="Mekons", date="1989-12-02",
        recordings=[RecordingSummary(identifier="mek89.sbd.miller.1", avg_rating=4.0, num_reviews=5),
                    RecordingSummary(identifier="mek89.sbd.other.2", avg_rating=4.0, num_reviews=5)],
    )
    ia = MapIA({"mek89.sbd.miller.1": {"source": "SBD"}, "mek89.sbd.other.2": {"source": "SBD"}})
    _, scores = select(tmp_path, cand, ia)
    assert scores["mek89.sbd.miller.1"]["score"] == scores["mek89.sbd.other.2"]["score"]


def test_skips_when_selection_exists(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "show")
    run_select_recording(sws, StubIA(), make_candidate(), assessment())

    class ExplodingIA:
        def metadata(self, identifier):
            raise AssertionError("must not re-fetch")

    assert run_select_recording(sws, ExplodingIA(), make_candidate(), assessment()) == "gd73-06-10.sbd"
