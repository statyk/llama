import json
import logging
from pathlib import Path

import pytest

from llama.errors import LlamaError
from llama.models import Briefing, ResearchVetting, Show, Track, VettingResult
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


def _briefing(**kw) -> Briefing:
    base = dict(context="Peak-era Dead on the summer '73 run.",
                significance="A standout show from a strong year.",
                per_set={"1": ["Opens hot"], "2": ["The big jam"]},
                notable_moments=["A monster Dark Star"],
                review_sentiment="Widely praised, including by non-attendees.",
                non_attendee_sentiment=True,
                cautions=[],
                mentioned_songs=[])
    base.update(kw)
    return Briefing(**base)


def write_briefing(sws: ShowWorkspace, **kw) -> Briefing:
    b = _briefing(**kw)
    write_artifact(sws.briefing_json, b)
    write_artifact(sws.briefing_md, "# Briefing: Grateful Dead — 1973-06-10\n")
    return b


def setup(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    write_briefing(sws)
    return sws, show


def test_package_layout_and_manifest(tmp_path: Path):
    sws, show = setup(tmp_path)
    ia = StubIA()
    pkg = run_package(sws, ia, show, profile="prime-dead")
    assert (pkg / "manifest.json").exists()
    assert (pkg / "playlist.m3u").exists()
    assert (pkg / "audio" / "01 - Morning Dew.mp3").exists()
    assert ia.downloads == [("d1t01.mp3", "m1"), ("d2t01.mp3", "m2")]  # md5s passed through
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["tracks"][0]["filename"] == "01 - Morning Dew.mp3"
    assert m["set_breaks"] == [{"after_track": 1}]
    # dummy bytes are unreadable audio -> falls back to metadata duration, no mismatch flag
    assert m["tracks"][0]["duration_sec"] == 600.0
    assert m["source"]["profile"] == "prime-dead"  # emcee reads this to assign presenter/title
    assert json.loads(sws.show.read_text())["needs_review"] is False


def test_package_never_writes_dj_notes_or_dj_audio(tmp_path: Path):
    # llama never generates a DJ script anymore -- that's emcee's job,
    # downstream of the manifest this stage writes. The fields stay in the
    # schema (passthrough) but llama's own packages never populate them.
    sws, show = setup(tmp_path)
    pkg = run_package(sws, StubIA(), show)
    assert not (pkg / "dj-notes.md").exists()
    assert not (pkg / "dj-audio").exists()
    assert not (pkg / "broadcast.m3u").exists()
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["dj_notes"] is None
    assert m["dj_audio"] is None


def test_duration_mismatch_flags_needs_review(tmp_path: Path, monkeypatch):
    sws, show = setup(tmp_path)
    monkeypatch.setattr(package_stage, "read_duration", lambda path: 100.0)
    run_package(sws, StubIA(), show)
    saved = json.loads(sws.show.read_text())
    assert saved["needs_review"] is True
    assert any("duration mismatch" in f for f in saved["review_flags"])


def test_package_skips_when_manifest_exists(tmp_path: Path):
    sws, show = setup(tmp_path)
    ia = StubIA()
    run_package(sws, ia, show)
    run_package(sws, ia, show)
    assert len(ia.downloads) == 2  # no re-downloads on second call


def test_package_logs_downloads(tmp_path: Path, caplog):
    sws, show = setup(tmp_path)
    with caplog.at_level(logging.INFO, logger="llama"):
        run_package(sws, StubIA(), show)
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
    pkg = run_package(sws, StubIA(), show)
    assert (pkg / "research.md").read_text() == "## Reputation\nLegendary."
    assert (pkg / "reviews.md").read_text() == "- Wow: great tape"
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["schema_version"] == 3
    assert m["research"] == "research.md" and m["reviews"] == "reviews.md"
    assert m["research_vetted"] is True
    assert m["show"]["context"] == "Peak 1973, RFK"


def test_package_context_defaults_empty_without_vetting(tmp_path: Path):
    # context now comes solely from the vet stage's context -- no notes.context
    # fallback (llama never generates notes anymore).
    sws, show = setup(tmp_path)
    pkg = run_package(sws, StubIA(), show)
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["show"]["context"] == ""
    assert m["research"] is None and m["research_vetted"] is False


def test_package_copies_briefing_and_emits_v3(tmp_path: Path):
    sws, show = setup(tmp_path)
    pkg = run_package(sws, StubIA(), show, force=True)
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["schema_version"] == 3
    assert manifest["briefing"]["json"] == "briefing.json"
    assert manifest["briefing"]["narration"] == "full"
    assert (pkg / "briefing.md").exists() and (pkg / "briefing.json").exists()


def test_package_manifest_briefing_reflects_the_real_briefing(tmp_path: Path):
    sws, show = setup(tmp_path)
    write_briefing(sws, narration="vague", per_set={}, mentioned_songs=[])
    write_vetting(sws)                      # flags=[] -> vetted True
    pkg = run_package(sws, StubIA(), show, force=True)
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["briefing"]["narration"] == "vague"
    assert m["briefing"]["vetted"] is True
    assert (pkg / "briefing.json").read_text() == sws.briefing_json.read_text()


def test_package_hard_fails_without_briefing(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    with pytest.raises(LlamaError, match="no briefing"):
        run_package(sws, StubIA(), show, force=True)
