import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.ledger import Ledger
from llama.models import (
    Candidate, Criteria, LedgerEntry, QualityAssessment, RecordingSummary, ShortlistEntry,
)
from llama.workspace import RunWorkspace, ShowWorkspace, read_model_list, write_artifact

runner = CliRunner()


def make_entries():
    def entry(rank, pid):
        return ShortlistEntry(
            rank=rank,
            candidate=Candidate(performance_id=pid, collection="GratefulDead",
                                date=f"1973-06-{9 + rank:02d}", venue="V",
                                recordings=[RecordingSummary(identifier=f"id{rank}")]),
            assessment=QualityAssessment(performance_id=pid, quality_score=9.0,
                                         rationale="great show"),
        )
    return [entry(1, "GratefulDead/1973-06-10"), entry(2, "GratefulDead/1973-06-11")]


def test_review_approves_selected_ranks(tmp_path: Path):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.shortlist, make_entries())
    result = runner.invoke(cli.app, ["review", str(ws.dir), "--config",
                                     str(tmp_path / "config.toml")], input="1\n")
    assert result.exit_code == 0, result.output
    entries = read_model_list(ws.shortlist, ShortlistEntry)
    assert entries[0].approved is True
    assert entries[1].approved is False


def test_ledger_commands(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    add = runner.invoke(cli.app, ["ledger", "add", "GratefulDead/1977-05-08",
                                  "--artist", "Grateful Dead", "--date", "1977-05-08",
                                  "--config", cfg])
    assert add.exit_code == 0
    listing = runner.invoke(cli.app, ["ledger", "list", "--config", cfg])
    assert "1977-05-08" in listing.output
    rm = runner.invoke(cli.app, ["ledger", "remove", "GratefulDead/1977-05-08", "--config", cfg])
    assert rm.exit_code == 0
    assert Ledger(tmp_path / "ledger.jsonl").entries() == []


def test_deliver_copies_package_and_records(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    show_dir = tmp_path / "runs" / "r1" / "shows" / "gratefuldead-1973-06-10"
    pkg = show_dir / "package"
    (pkg / "audio").mkdir(parents=True)
    (pkg / "manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "show": {"artist": "Grateful Dead", "date": "1973-06-10", "venue": "RFK",
                 "city": None, "context": ""},
        "source": {"performance_id": "GratefulDead/1973-06-10"},
        "tracks": [], "set_breaks": [],
        "dj_notes": {"intro": "i", "set_intros": {}, "outro": "o"},
        "total_duration_sec": 0, "set_durations_sec": {},
    }))
    dest = tmp_path / "station-inbox"
    result = runner.invoke(cli.app, ["deliver", str(show_dir), "--dest", str(dest),
                                     "--config", cfg])
    assert result.exit_code == 0, result.output
    assert (dest / "gratefuldead-1973-06-10" / "manifest.json").exists()
    entries = Ledger(tmp_path / "ledger.jsonl").entries()
    assert entries[0].status == "delivered"
    assert entries[0].performance_id == "GratefulDead/1973-06-10"


def test_deliver_refuses_needs_review_without_force(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    show_dir = tmp_path / "runs" / "r1" / "shows" / "gratefuldead-1973-06-10"
    pkg = show_dir / "package"
    (pkg / "audio").mkdir(parents=True)
    (pkg / "manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "show": {"artist": "Grateful Dead", "date": "1973-06-10", "venue": "RFK",
                 "city": None, "context": ""},
        "source": {"performance_id": "GratefulDead/1973-06-10"},
        "tracks": [], "set_breaks": [],
        "dj_notes": {"intro": "i", "set_intros": {}, "outro": "o"},
        "total_duration_sec": 0, "set_durations_sec": {},
    }))
    (show_dir / "show.json").write_text(json.dumps({
        "performance_id": "GratefulDead/1973-06-10", "identifier": "gd73",
        "artist": "Grateful Dead", "date": "1973-06-10", "venue": "RFK",
        "needs_review": True, "review_flags": ["duration mismatch on 01.mp3"],
    }))
    dest = tmp_path / "station-inbox"

    result = runner.invoke(cli.app, ["deliver", str(show_dir), "--dest", str(dest), "--config", cfg])
    assert result.exit_code == 1
    assert "needs-review" in result.output
    assert not dest.exists()

    forced = runner.invoke(cli.app, ["deliver", str(show_dir), "--dest", str(dest),
                                     "--force", "--config", cfg])
    assert forced.exit_code == 0, forced.output
    assert (dest / "gratefuldead-1973-06-10" / "manifest.json").exists()


def test_run_unknown_stage_exits_with_message(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q"))

    result = runner.invoke(cli.app, ["run", str(ws.dir), "--stage", "bogus", "--config", cfg])
    assert result.exit_code == 1
    assert "unknown stage" in result.output


FUZZY_CRITERIA = json.dumps({
    "query": "x", "collection": None, "artist": None,
    "date_from": "1960-01-01", "date_to": "1979-12-31",
    "setlist_constraints": [], "soft_preferences": "folk/acoustic, well known",
    "min_avg_rating": 3.5, "min_reviews": 3, "count": 1,
})

ARTIST_COLLECTIONS = [
    {"identifier": "JoanBaez", "title": "Joan Baez"},
    {"identifier": "DocWatson", "title": "Doc and Merle Watson"},
    {"identifier": "TownesVanZandt", "title": "Townes Van Zandt"},
]


class FuzzyFakeIA:
    def __init__(self, *args, **kwargs):
        self.etree_queries = []

    def search(self, query, fields, rows=500):
        if "mediatype:collection" in query:
            return ARTIST_COLLECTIONS
        self.etree_queries.append(query)
        return []  # no shows: pipeline ends at "No shows survived winnowing."


def fuzzy_providers(config):
    from llama.llm.fake import FakeProvider
    return {
        "interpret": FakeProvider(completes=[FUZZY_CRITERIA]),
        "propose_artists": FakeProvider(completes=[json.dumps(
            {"artists": ["Joan Baez", "Doc Watson", "Townes Van Zandt"]})]),
        "score_reviews": FakeProvider(),
        "light_research": FakeProvider(),
        "extract_setlist": FakeProvider(),
        "deep_research": FakeProvider(),
        "synthesize": FakeProvider(),
    }


def _fuzzy_setup(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ia = FuzzyFakeIA()
    monkeypatch.setattr(cli, "make_providers", fuzzy_providers)
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: ia)
    return ia


def test_fuzzy_query_interactive_prune(tmp_path, monkeypatch):
    ia = _fuzzy_setup(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, [
        "find", "folk 60s-70s", "--run-name", "fz",
        "--config", str(tmp_path / "config.toml"),
    ], input="2\n")
    assert result.exit_code == 0, result.output
    assert "Doc and Merle Watson" in result.output
    assert len(ia.etree_queries) == 1
    assert "collection:DocWatson" in ia.etree_queries[0]
    saved = json.loads((tmp_path / "runs" / "fz" / "artists.json").read_text())
    assert [a["identifier"] for a in saved] == ["DocWatson"]


def test_fuzzy_query_auto_uses_all(tmp_path, monkeypatch):
    ia = _fuzzy_setup(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, [
        "find", "folk 60s-70s", "--auto", "--run-name", "fz2",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    assert len(ia.etree_queries) == 3


def test_fuzzy_query_zero_matches_exits_cleanly(tmp_path, monkeypatch):
    ia = _fuzzy_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "make_providers", lambda config: {
        **fuzzy_providers(config),
        "propose_artists": __import__("llama.llm.fake", fromlist=["FakeProvider"]).FakeProvider(
            completes=[json.dumps({"artists": ["Nick Drake"]})]),
    })
    result = runner.invoke(cli.app, [
        "find", "folk 60s-70s", "--auto", "--run-name", "fz3",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    assert "none of the proposed artists" in result.output
    assert ia.etree_queries == []


def test_fuzzy_query_invalid_prune_aborts(tmp_path, monkeypatch):
    ia = _fuzzy_setup(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, [
        "find", "folk 60s-70s", "--run-name", "fz4",
        "--config", str(tmp_path / "config.toml"),
    ], input="99\n")
    assert result.exit_code == 0, result.output
    assert "no valid selections" in result.output
    assert ia.etree_queries == []
    saved = json.loads((tmp_path / "runs" / "fz4" / "artists.json").read_text())
    assert len(saved) == 3  # artifact NOT overwritten with the empty prune


def test_profile_add_and_list(tmp_path: Path, monkeypatch):
    from llama.llm.fake import FakeProvider
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    criteria_json = json.dumps({
        "query": "x", "collection": "GratefulDead", "artist": "Grateful Dead",
        "date_from": None, "date_to": None, "setlist_constraints": [],
        "soft_preferences": None, "min_avg_rating": 4.0, "min_reviews": 3, "count": 1,
    })
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[criteria_json])})
    add = runner.invoke(cli.app, ["profile", "add", "sunday-dead", "GD classics",
                                  "--count", "2", "--human-gate", "--config", cfg])
    assert add.exit_code == 0, add.output
    assert (tmp_path / "profiles" / "sunday-dead.toml").exists()
    listing = runner.invoke(cli.app, ["profile", "list", "--config", cfg])
    assert "sunday-dead" in listing.output


def test_stage_vet_is_valid_and_maps_to_vetting_artifact(tmp_path: Path):
    assert "vet" in cli.VALID_STAGES
    sws = ShowWorkspace(tmp_path / "s")
    assert cli._show_stage_artifacts(sws, "vet") == [sws.vetting]


def test_stage_research_maps_to_research_and_vetting(tmp_path: Path):
    # re-researching with --force must also drop vetting.json so the fresh
    # document is re-vetted rather than shipping under the old extraction.
    sws = ShowWorkspace(tmp_path / "s")
    assert cli._show_stage_artifacts(sws, "research") == [sws.research, sws.vetting]
