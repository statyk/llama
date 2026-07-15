import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
import llama.pipeline as pipeline
from llama.llm.fake import FakeProvider

runner = CliRunner()
FIXTURE = Path(__file__).parent / "fixtures" / "gd73_metadata.json"
IDENT = "gd73-06-10.sbd.hollister.174.sbeok.shnf"

CRITERIA = json.dumps({
    "query": "x", "collection": "GratefulDead", "artist": "Grateful Dead",
    "date_from": "1973-01-01", "date_to": "1973-12-31",
    "setlist_constraints": [], "soft_preferences": None,
    "min_avg_rating": 3.5, "min_reviews": 2, "count": 1,
})


def assessments(pid: str) -> str:
    return json.dumps({"assessments": [{
        "performance_id": pid, "quality_score": 9.5,
        "non_attendee_evidence": "couchtaper praises the tape",
        "recording_complaints": [], "rationale": "monumental Dark Star",
    }]})


NOTES = json.dumps({
    "context": "Peak 1973",
    "intro": "Tonight, the Grateful Dead at RFK Stadium.",
    "set_intros": {"1": "Morning Dew opens.", "2": "A monumental Dark Star.",
                   "encore": "Johnny B. Goode."},
    "set_break_notes": ["End of set one.", "End of set two."],
    "outro": "From the hollister soundboard.",
    "mentioned_songs": ["Morning Dew", "Dark Star", "Johnny B. Goode"],
})

VET = json.dumps({
    "asserted_songs": ["Morning Dew", "Dark Star"],
    "asserted_dates": ["1973-06-10"],
    "context": "Peak 1973, RFK Stadium",
})


class FakeIA:
    def __init__(self, *args, **kwargs):
        self.fixture = json.loads(FIXTURE.read_text())

    def scrape(self, query, fields, count=10000):
        return [{"identifier": IDENT, "date": "1973-06-10T00:00:00Z",
                 "venue": "RFK Stadium", "coverage": "Washington, DC",
                 "avg_rating": 4.8, "num_reviews": 40,
                 "description": self.fixture["metadata"]["description"]}]

    def metadata(self, identifier):
        return self.fixture

    def download_file(self, identifier, filename, dest, md5=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00" * 64)
        return dest


def fake_providers(config):
    return {
        "interpret": FakeProvider(completes=[CRITERIA]),
        "score_reviews": FakeProvider(completes=[assessments("GratefulDead/1973-06-10")]),
        "light_research": FakeProvider(researches=["Widely ranked top-5 1973 (example.org)"]),
        "extract_setlist": FakeProvider(),
        "deep_research": FakeProvider(researches=[
            "## Reputation\nLegendary RFK show.\n## Performance highlights\nDark Star.\n"
            "## Context\nPeak 73 tour.\n## Recording notes\nHollister SBD."]),
        "synthesize": FakeProvider(completes=[NOTES]),
        "align_structure": FakeProvider(),
        "vet_research": FakeProvider(completes=[VET]),
    }


def test_make_providers_includes_align_structure():
    from llama.config import Config
    from llama.pipeline import make_providers

    assert "align_structure" in make_providers(Config())


def test_find_end_to_end(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(pipeline, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, [
        "find", "GD 1973 best soundboard", "--auto", "--script",
        "--run-name", "testrun", "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output

    show_dir = tmp_path / "runs" / "testrun" / "shows" / "gratefuldead-1973-06-10"
    pkg = show_dir / "package"
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["show"]["artist"] == "Grateful Dead"
    assert len(manifest["tracks"]) == 6
    assert manifest["set_breaks"] == [{"after_track": 3, "note_index": 0},
                                      {"after_track": 5, "note_index": 1}]
    assert (pkg / "audio" / "01 - Morning Dew.mp3").exists()
    assert (pkg / "playlist.m3u").read_text().splitlines()[1] == "audio/01 - Morning Dew.mp3"
    assert (pkg / "dj-notes.md").exists()
    assert (pkg / "research.md").exists()
    assert (pkg / "reviews.md").exists()
    assert manifest["schema_version"] == 2
    assert manifest["show"]["context"] == "Peak 1973, RFK Stadium"
    # ledger records the clean show
    ledger_lines = (tmp_path / "ledger.jsonl").read_text().splitlines()
    assert json.loads(ledger_lines[0])["performance_id"] == "GratefulDead/1973-06-10"
    assert json.loads(ledger_lines[0])["status"] == "selected"


def test_show_failure_is_isolated_and_raw_output_saved(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    providers = fake_providers(None)
    providers["synthesize"] = FakeProvider(completes=["not json"] * 3)
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, [
        "find", "GD 1973", "--auto", "--script", "--run-name", "testrun3",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    assert "FAILED" in result.output

    show_dir = tmp_path / "runs" / "testrun3" / "shows" / "gratefuldead-1973-06-10"
    failure = show_dir / "llm-failure.txt"
    assert failure.exists()
    assert failure.read_text() == "not json"
    assert not (show_dir / "package" / "manifest.json").exists()
    assert not (tmp_path / "ledger.jsonl").exists()


def test_needs_review_show_is_skipped_and_not_recorded(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    providers = fake_providers(None)
    providers["synthesize"] = FakeProvider(completes=[
        json.dumps({**json.loads(NOTES), "mentioned_songs": ["Fake Invented Song"]})
    ])
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, [
        "find", "GD 1973", "--auto", "--script", "--run-name", "testrun2",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0
    assert "needs-review" in result.output
    show_dir = tmp_path / "runs" / "testrun2" / "shows" / "gratefuldead-1973-06-10"
    assert not (show_dir / "package" / "manifest.json").exists()
    assert not (tmp_path / "ledger.jsonl").exists()


def test_find_default_skips_script(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    providers = fake_providers(None)
    providers["synthesize"] = FakeProvider()  # any call would raise: queue is empty
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, [
        "find", "GD 1973", "--auto", "--run-name", "noscript",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    pkg = tmp_path / "runs" / "noscript" / "shows" / "gratefuldead-1973-06-10" / "package"
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["dj_notes"] is None
    assert manifest["research"] == "research.md"
    assert manifest["set_breaks"][0]["note_index"] is None
    assert manifest["show"]["context"] == "Peak 1973, RFK Stadium"
    assert (pkg / "research.md").exists() and (pkg / "reviews.md").exists()
    assert not (pkg / "dj-notes.md").exists()


def test_package_replay_without_script_keeps_cached_notes(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(pipeline, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    cfg = str(tmp_path / "config.toml")

    first = runner.invoke(cli.app, [
        "find", "GD 1973", "--auto", "--script", "--run-name", "replay",
        "--config", cfg,
    ])
    assert first.exit_code == 0, first.output
    run_dir = tmp_path / "runs" / "replay"

    # Re-package WITHOUT --script: cached dj-notes.json must still drive the manifest.
    replay = runner.invoke(cli.app, [
        "run", str(run_dir), "--stage", "package", "--force", "--config", cfg,
    ])
    assert replay.exit_code == 0, replay.output

    pkg = run_dir / "shows" / "gratefuldead-1973-06-10" / "package"
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["dj_notes"] is not None
    assert manifest["set_breaks"] == [{"after_track": 3, "note_index": 0},
                                      {"after_track": 5, "note_index": 1}]
    assert (pkg / "dj-notes.md").exists()


def test_stage_synthesize_implies_script(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(pipeline, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    cfg = str(tmp_path / "config.toml")

    first = runner.invoke(cli.app, [
        "find", "GD 1973", "--auto", "--run-name", "synthreplay", "--config", cfg,
    ])
    assert first.exit_code == 0, first.output
    show_dir = tmp_path / "runs" / "synthreplay" / "shows" / "gratefuldead-1973-06-10"
    assert not (show_dir / "dj-notes.json").exists()

    replay = runner.invoke(cli.app, [
        "run", str(show_dir.parent.parent), "--stage", "synthesize", "--force",
        "--config", cfg,
    ])
    assert replay.exit_code == 0, replay.output
    assert (show_dir / "dj-notes.json").exists()


def test_vet_failure_skips_show_before_packaging(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    providers = fake_providers(None)
    providers["vet_research"] = FakeProvider(completes=[json.dumps({
        "asserted_songs": ["Werewolves of London", "Excitable Boy"],
        "asserted_dates": [], "context": "",
    })])
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, [
        "find", "GD 1973", "--auto", "--run-name", "badresearch",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    assert "needs-review" in result.output
    show_dir = tmp_path / "runs" / "badresearch" / "shows" / "gratefuldead-1973-06-10"
    saved = json.loads((show_dir / "show.json").read_text())
    assert any("unknown song" in f for f in saved["review_flags"])
    assert not (show_dir / "package" / "manifest.json").exists()
    assert not (tmp_path / "ledger.jsonl").exists()


def test_choose_entries_spreads_years_on_auto_pick():
    from llama.models import Candidate, QualityAssessment, RecordingSummary, ShortlistEntry
    from llama.pipeline import choose_entries

    def entry(rank, date, approved=None):
        pid = f"GratefulDead/{date}"
        return ShortlistEntry(
            rank=rank, approved=approved,
            candidate=Candidate(performance_id=pid, collection="GratefulDead", date=date,
                                recordings=[RecordingSummary(identifier=f"id{rank}")]),
            assessment=QualityAssessment(performance_id=pid, quality_score=10.0 - rank,
                                         rationale="r"),
        )

    entries = [entry(1, "1977-05-08"), entry(2, "1977-05-09"),
               entry(3, "1969-12-07"), entry(4, "1972-08-27")]
    # auto pick of 2: each year's best, in rank order - not ranks 1+2 (both 1977)
    picked = choose_entries(entries, 2, human_gate=False)
    assert [e.rank for e in picked] == [1, 3]
    # explicit approvals are a human decision: no spreading applied
    approved = [entry(1, "1977-05-08", approved=True), entry(2, "1977-05-09", approved=True),
                entry(3, "1969-12-07")]
    assert [e.rank for e in choose_entries(approved, 2, human_gate=False)] == [1, 2]
