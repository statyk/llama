import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
import llama.pipeline as pipeline
from herder import FakeProvider

runner = CliRunner()
FIXTURE = Path(__file__).parent / "fixtures" / "gd73_metadata.json"
IDENT = "gd73-06-10.sbd.hollister.174.sbeok.shnf"

# gd73-06-10 is a real in-dataset jerrybase performance; end-to-end tests that
# expect a clean packaged show use a synthesized candidate whose venue ("RFK
# Stadium") differs from jerrybase's ("Robert F. Kennedy Stadium"). Disable
# jerrybase for those tests so they stay isolated from the dataset (byte-identical
# to pre-feature behavior). Tests exercising jerrybase itself live in
# tests/test_stage_gather.py and call run_gather(..., jerrybase_enabled=True).
JB_OFF = "\n[jerrybase]\nenabled = false\n"

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
    "set_intros": {"1": "Tonight, the Grateful Dead at RFK Stadium. Morning Dew opens.",
                   "2": "A monumental Dark Star."},
    "outro": "Johnny B. Goode sends us off. From the hollister soundboard.",
    "mentioned_songs": ["Morning Dew", "Dark Star", "Johnny B. Goode"],
})

VET = json.dumps({
    "asserted_songs": ["Morning Dew", "Dark Star"],
    "asserted_dates": ["1973-06-10"],
    "context": "Peak 1973, RFK Stadium",
})

GOOD_BRIEFING_JSON = json.dumps({
    "context": "Peak-era Dead.", "significance": "Worth airing.",
    "per_set": {"1": ["Opens hot"]}, "notable_moments": [],
    "review_sentiment": "Praised.", "non_attendee_sentiment": True,
    "cautions": [], "narration": "full", "mentioned_songs": []})


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
        "brief": FakeProvider(completes=[GOOD_BRIEFING_JSON]),
        "synthesize": FakeProvider(completes=[NOTES]),
        "align_structure": FakeProvider(),
        "vet_research": FakeProvider(completes=[VET]),
    }


def test_make_providers_includes_align_structure():
    from llama.config import Config
    from llama.pipeline import make_providers

    assert "align_structure" in make_providers(Config())


def test_make_providers_builds_ladders():
    from llama.config import Config
    from llama.pipeline import make_providers

    providers = make_providers(Config())
    # interpret is a medium task: base, base, escalated-to-high
    assert [p.model for p in providers["interpret"]] == ["sonnet", "sonnet", "opus"]
    # synthesize is already high: no headroom
    assert [p.model for p in providers["synthesize"]] == ["opus", "opus", "opus"]


def test_find_end_to_end(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(pipeline, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973 best soundboard", "--auto", "--script",
        "--name", "testrun"])
    assert result.exit_code == 0, result.output

    show_dir = tmp_path / "shows" / "gratefuldead-1973-06-10"
    pkg = show_dir / "package"
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["show"]["artist"] == "Grateful Dead"
    assert len(manifest["tracks"]) == 6
    assert manifest["set_breaks"] == [{"after_track": 3}, {"after_track": 5}]
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
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    providers["synthesize"] = FakeProvider(completes=["not json"] * 3)
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--script", "--name", "testrun3"])
    assert result.exit_code == 0, result.output
    assert "FAILED" in result.output

    show_dir = tmp_path / "shows" / "gratefuldead-1973-06-10"
    failure = show_dir / "llm-failure.txt"
    assert failure.exists()
    assert failure.read_text() == "not json"
    assert not (show_dir / "package" / "manifest.json").exists()
    assert not (tmp_path / "ledger.jsonl").exists()


def test_needs_review_show_is_skipped_and_not_recorded(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    providers = fake_providers(None)
    bad_notes = json.dumps({**json.loads(NOTES), "mentioned_songs": ["Fake Invented Song"]})
    providers["synthesize"] = FakeProvider(completes=[bad_notes, bad_notes])  # retry also fails
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--script", "--name", "testrun2"])
    assert result.exit_code == 0
    assert "needs-review" in result.output
    show_dir = tmp_path / "shows" / "gratefuldead-1973-06-10"
    assert not (show_dir / "package" / "manifest.json").exists()
    assert not (tmp_path / "ledger.jsonl").exists()


def test_find_default_includes_script(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--name", "defscript"])
    assert result.exit_code == 0, result.output
    pkg = tmp_path / "shows" / "gratefuldead-1973-06-10" / "package"
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["dj_notes"] is not None
    assert (pkg / "dj-notes.md").exists()


def test_find_no_script_skips_script(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    providers["synthesize"] = FakeProvider()  # any call would raise: queue is empty
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--no-script", "--name", "noscript"])
    assert result.exit_code == 0, result.output
    pkg = tmp_path / "shows" / "gratefuldead-1973-06-10" / "package"
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["dj_notes"] is None
    assert manifest["research"] == "research.md"
    assert manifest["show"]["context"] == "Peak 1973, RFK Stadium"
    assert (pkg / "research.md").exists() and (pkg / "reviews.md").exists()
    assert not (pkg / "dj-notes.md").exists()


def test_find_stamps_limit_and_script_into_criteria(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[CRITERIA])})
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: None)
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"), "get", "GD 1973", "--limit", "5", "--no-script",
                                     "--name", "stamped"])
    assert result.exit_code == 0, result.output
    saved = json.loads((tmp_path / "runs" / "stamped" / "criteria.json").read_text())
    assert saved["count"] == 5 and saved["script"] is False


def test_vet_failure_skips_show_before_packaging(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    providers = fake_providers(None)
    providers["vet_research"] = FakeProvider(completes=[json.dumps({
        "asserted_songs": ["Werewolves of London", "Excitable Boy"],
        "asserted_dates": [], "context": "",
    })])
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--name", "badresearch"])
    assert result.exit_code == 0, result.output
    assert "needs-review" in result.output
    show_dir = tmp_path / "shows" / "gratefuldead-1973-06-10"
    saved = json.loads((show_dir / "show.json").read_text())
    assert any("unknown song" in f for f in saved["review_flags"])
    assert not (show_dir / "package" / "manifest.json").exists()
    assert not (tmp_path / "ledger.jsonl").exists()


def test_choose_entries_year_cap_is_opt_in_on_auto_pick():
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
    # default: rank order, even though ranks 1+2 are both 1977
    assert [e.rank for e in choose_entries(entries, 2, human_gate=False)] == [1, 2]
    # year_cap 0.5 -> one per year: each year's best in rank order
    assert [e.rank for e in choose_entries(entries, 2, human_gate=False,
                                           year_cap=0.5)] == [1, 3]
    # explicit approvals are a human decision: never capped
    approved = [entry(1, "1977-05-08", approved=True), entry(2, "1977-05-09", approved=True),
                entry(3, "1969-12-07")]
    assert [e.rank for e in choose_entries(approved, 2, human_gate=False,
                                           year_cap=0.5)] == [1, 2]


def test_choose_entries_spreads_artists_on_auto_pick():
    from llama.models import Candidate, QualityAssessment, RecordingSummary, ShortlistEntry
    from llama.pipeline import choose_entries

    def entry(rank, collection, date):
        pid = f"{collection}/{date}"
        return ShortlistEntry(
            rank=rank,
            candidate=Candidate(performance_id=pid, collection=collection, date=date,
                                recordings=[RecordingSummary(identifier=f"id{rank}")]),
            assessment=QualityAssessment(performance_id=pid, quality_score=10.0 - rank,
                                         rationale="r"),
        )

    # one artist's catalog dominates the top ranks of a style profile
    entries = [entry(1, "CharlieHunter", "2002-07-05"), entry(2, "CharlieHunter", "2000-08-23"),
               entry(3, "CharlieHunter", "2001-12-08"), entry(4, "GarageATrois", "1998-04-25"),
               entry(5, "SnarkyPuppy", "2014-03-01")]
    picked = choose_entries(entries, 3, human_gate=False)
    assert [e.candidate.collection for e in picked] == \
        ["CharlieHunter", "GarageATrois", "SnarkyPuppy"]
    # a raised artist_cap lets quality dominate again
    picked = choose_entries(entries, 3, human_gate=False, artist_cap=1.0)
    assert [e.candidate.collection for e in picked] == ["CharlieHunter"] * 3


def test_process_show_writes_provenance(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(pipeline, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973 best soundboard", "--auto", "--script",
        "--name", "provrun"])
    assert result.exit_code == 0, result.output

    from llama.models import Provenance
    from llama.workspace import read_model
    prov_path = tmp_path / "shows" / "gratefuldead-1973-06-10" / "provenance.json"
    prov = read_model(prov_path, Provenance)
    assert prov.performance_id == "GratefulDead/1973-06-10"
    assert prov.run == "provrun"
    assert prov.script is True
    assert "monumental Dark Star" in prov.dossier          # rationale
    assert "Widely ranked top-5" in prov.dossier           # external reputation
    assert prov.candidate.collection == "GratefulDead"
    assert prov.processed_at  # ISO timestamp present
    assert prov.assessment is not None                     # winnow assessment carried
    assert prov.assessment.quality_score == 9.5


def test_task_keys_include_brief():
    from llama.pipeline import TASK_KEYS
    assert "brief" in TASK_KEYS
    from llama.config import DEFAULT_TIERS
    assert DEFAULT_TIERS["brief"] == "high"


def test_process_show_runs_brief_and_writes_artifacts(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(pipeline, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973 best soundboard", "--auto", "--script",
        "--name", "briefrun"])
    assert result.exit_code == 0, result.output

    from llama.workspace import RunWorkspace
    show_ws = RunWorkspace(tmp_path, "briefrun").show_ws("GratefulDead/1973-06-10")
    assert show_ws.briefing_json.exists()
    assert show_ws.briefing_md.exists()


def test_process_show_holds_on_briefing_guard_failure(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    # claims 3 sets where the fixture only has one -- briefing_guard rejects it
    bad_briefing = json.dumps({
        "context": "Peak-era Dead.", "significance": "Worth airing.",
        "per_set": {"1": ["There were three sets tonight."]}, "notable_moments": [],
        "review_sentiment": "Praised.", "non_attendee_sentiment": True,
        "cautions": [], "narration": "full", "mentioned_songs": []})
    providers["brief"] = FakeProvider(completes=[bad_briefing, bad_briefing])
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--script", "--name", "briefhold"])
    assert result.exit_code == 0, result.output
    assert "needs-review" in result.output
    show_dir = tmp_path / "shows" / "gratefuldead-1973-06-10"
    assert not (show_dir / "package" / "manifest.json").exists()
    # synthesize/package providers untouched: still full queues
    assert len(providers["synthesize"].completes) == 1
    assert not (tmp_path / "ledger.jsonl").exists()


def test_process_show_stamps_voice_and_forwards_speech(tmp_path: Path):
    from llama.ledger import Ledger
    from llama.models import (Candidate, Provenance, QualityAssessment,
                              RecordingSummary, ShortlistEntry)
    from llama.pipeline import process_show
    from llama.tts.fake import FakeSpeechProvider
    from llama.workspace import RunWorkspace, read_model

    fixture = json.loads(FIXTURE.read_text())
    cand = Candidate(
        performance_id="GratefulDead/1973-06-10", collection="GratefulDead",
        date="1973-06-10", venue="RFK Stadium", city="Washington, DC",
        recordings=[RecordingSummary(identifier=IDENT, avg_rating=4.8, num_reviews=40,
                                     description=fixture["metadata"]["description"])],
    )
    entry = ShortlistEntry(
        rank=1, candidate=cand,
        assessment=QualityAssessment(performance_id=cand.performance_id,
                                     quality_score=9.5, rationale="monumental"))
    providers = {
        "extract_setlist": FakeProvider(),
        "align_structure": FakeProvider(),
        "deep_research": FakeProvider(researches=[
            "## Reputation\nLegendary.\n## Performance highlights\nDark Star.\n"
            "## Context\nPeak 73 tour.\n## Recording notes\nHollister SBD."]),
        "vet_research": FakeProvider(completes=[VET]),
        "brief": FakeProvider(completes=[GOOD_BRIEFING_JSON]),
        "synthesize": FakeProvider(completes=[NOTES]),
    }
    speech = FakeSpeechProvider()
    ws = RunWorkspace(tmp_path, "voicerun")
    pkg = process_show(ws, FakeIA(), Ledger(tmp_path / "ledger.jsonl"), entry,
                       providers, "voicerun", script=True, voice="v-abc",
                       speech=speech, jerrybase_enabled=False)
    assert pkg is not None
    prov = read_model(tmp_path / "shows" / "gratefuldead-1973-06-10" / "provenance.json",
                      Provenance)
    assert prov.voice == "v-abc"
    assert prov.script is True
    assert len(speech.calls) > 0                      # speech reached run_package
    assert (pkg / "dj-audio" / "set1-intro.mp3").exists()
