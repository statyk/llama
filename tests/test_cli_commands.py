import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.ledger import Ledger
from llama.models import (
    Candidate, LedgerEntry, QualityAssessment, RecordingSummary, ShortlistEntry,
)
from llama.workspace import RunWorkspace, read_model_list, write_artifact

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
