import json
import logging
from pathlib import Path

from llama.models import DJNotes, ResearchVetting, Show, Track, VettingResult
from llama.stages import package as package_stage
from llama.stages.package import run_package
from llama.workspace import ShowWorkspace, write_artifact


class StubIA:
    def __init__(self):
        self.downloads = []
        self.md = {"files": [
            {"name": "d1t01.mp3", "md5": "m1"}, {"name": "d2t01.mp3", "md5": "m2"},
        ]}

    def metadata(self, identifier):
        return self.md

    def download_file(self, identifier, filename, dest, md5=None):
        self.downloads.append((filename, md5))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00" * 64)
        return dest


def make_show():
    return Show(
        performance_id="GratefulDead/1973-06-10", identifier="gd73",
        artist="Grateful Dead", date="1973-06-10", venue="RFK Stadium",
        tracks=[
            Track(index=1, set="1", title="Morning Dew", filename="d1t01.mp3",
                  duration_sec=600.0, title_source="tags"),
            Track(index=2, set="2", title="Dark Star", filename="d2t01.mp3",
                  duration_sec=1800.0, title_source="tags"),
        ],
        set_breaks=[1],
    )


def make_notes():
    return DJNotes(context="from the notes", intro="i", outro="o",
                   set_intros={"1": "a", "2": "b"}, set_break_notes=["x"])


def setup(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    write_artifact(sws.dj_notes_md, "# notes")
    return sws, show


def test_package_layout_and_manifest(tmp_path: Path):
    sws, show = setup(tmp_path)
    ia = StubIA()
    pkg = run_package(sws, ia, show, make_notes())
    assert (pkg / "manifest.json").exists()
    assert (pkg / "playlist.m3u").exists()
    assert (pkg / "dj-notes.md").read_text() == "# notes"
    assert (pkg / "audio" / "01 - Morning Dew.mp3").exists()
    assert ia.downloads == [("d1t01.mp3", "m1"), ("d2t01.mp3", "m2")]  # md5s passed through
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["tracks"][0]["filename"] == "01 - Morning Dew.mp3"
    assert m["set_breaks"] == [{"after_track": 1, "note_index": 0}]
    # dummy bytes are unreadable audio -> falls back to metadata duration, no mismatch flag
    assert m["tracks"][0]["duration_sec"] == 600.0
    assert json.loads(sws.show.read_text())["needs_review"] is False


def test_duration_mismatch_flags_needs_review(tmp_path: Path, monkeypatch):
    sws, show = setup(tmp_path)
    monkeypatch.setattr(package_stage, "read_duration", lambda path: 100.0)
    run_package(sws, StubIA(), show, make_notes())
    saved = json.loads(sws.show.read_text())
    assert saved["needs_review"] is True
    assert any("duration mismatch" in f for f in saved["review_flags"])


def test_package_skips_when_manifest_exists(tmp_path: Path):
    sws, show = setup(tmp_path)
    ia = StubIA()
    run_package(sws, ia, show, make_notes())
    run_package(sws, ia, show, make_notes())
    assert len(ia.downloads) == 2  # no re-downloads on second call


def test_package_logs_downloads(tmp_path: Path, caplog):
    sws, show = setup(tmp_path)
    with caplog.at_level(logging.INFO, logger="llama"):
        run_package(sws, StubIA(), show, make_notes())
    messages = [r.getMessage() for r in caplog.records]
    assert "downloading 1/2: d1t01.mp3" in messages
    assert "downloading 2/2: d2t01.mp3" in messages


def write_vetting(sws, context="Peak 1973, RFK", flags=None):
    write_artifact(sws.vetting, VettingResult(
        vetting=ResearchVetting(context=context), flags=flags or []))


def test_package_ships_research_reviews_and_vetting_context(tmp_path: Path):
    sws, show = setup(tmp_path)
    write_artifact(sws.research, "## Reputation\nLegendary.")
    write_artifact(sws.reviews, [{"reviewtitle": "Wow", "reviewbody": "great tape"}])
    write_vetting(sws)
    pkg = run_package(sws, StubIA(), show, make_notes())
    assert (pkg / "research.md").read_text() == "## Reputation\nLegendary."
    assert (pkg / "reviews.md").read_text() == "- Wow: great tape"
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["schema_version"] == 2
    assert m["research"] == "research.md" and m["reviews"] == "reviews.md"
    assert m["research_vetted"] is True
    assert m["show"]["context"] == "Peak 1973, RFK"  # vetting wins over notes.context


def test_package_without_script(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)  # no dj-notes.md written
    write_artifact(sws.research, "r")
    write_vetting(sws)
    pkg = run_package(sws, StubIA(), show, notes=None)
    assert not (pkg / "dj-notes.md").exists()
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["dj_notes"] is None
    assert m["set_breaks"] == [{"after_track": 1, "note_index": None}]
    assert (pkg / "reviews.md").read_text() == "(no reviews)"


def test_package_without_vetting_falls_back_to_notes_context(tmp_path: Path):
    sws, show = setup(tmp_path)
    pkg = run_package(sws, StubIA(), show, make_notes())
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["show"]["context"] == make_notes().context
    assert m["research"] is None and m["research_vetted"] is False
