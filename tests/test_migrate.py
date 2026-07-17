from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.migrate import apply_migration, plan_migration
from llama.models import (Candidate, Criteria, Provenance, QualityAssessment,
                          RecordingSummary, ShortlistEntry)
from llama.workspace import RunWorkspace, ShowWorkspace, read_model, write_artifact

runner = CliRunner()


def seed_run(root: Path, run: str, slug: str, pid: str, *, packaged: bool):
    """A legacy run with one nested show and a matching shortlist entry."""
    ws = RunWorkspace(root, run)
    write_artifact(ws.criteria, Criteria(query=f"{run} query", script=True))
    entry = ShortlistEntry(
        rank=1,
        candidate=Candidate(performance_id=pid, collection=pid.split("/")[0],
                            date=pid.split("/")[1],
                            recordings=[RecordingSummary(identifier="x")]),
        assessment=QualityAssessment(performance_id=pid, quality_score=9.0,
                                     rationale="great show"),
        external_reputation="ranked top-5 (example.org)")
    write_artifact(ws.shortlist, [entry])
    legacy = ws.dir / "shows" / slug
    (legacy / "package").mkdir(parents=True)
    (legacy / "selection.json").write_text('{"identifier": "x"}')
    if packaged:
        (legacy / "package" / "manifest.json").write_text('{"schema_version": 2}')
    return legacy


def test_migrate_moves_and_backfills_provenance(tmp_path: Path):
    seed_run(tmp_path, "r1", "gratefuldead-1973-06-10",
             "GratefulDead/1973-06-10", packaged=True)
    moves = plan_migration(tmp_path)
    assert len(moves) == 1 and moves[0].winner
    apply_migration(tmp_path, moves)
    dest = tmp_path / "shows" / "gratefuldead-1973-06-10"
    assert (dest / "selection.json").exists()
    assert not (tmp_path / "runs" / "r1" / "shows").exists()  # emptied and removed
    prov = read_model(ShowWorkspace(dest).provenance, Provenance)
    assert prov.run == "r1"
    assert prov.performance_id == "GratefulDead/1973-06-10"
    assert "great show" in prov.dossier and "ranked top-5" in prov.dossier
    assert prov.script is True
    assert prov.assessment is not None and prov.assessment.quality_score == 9.0


def test_migrate_collision_deeper_wins_loser_stays(tmp_path: Path):
    deep = seed_run(tmp_path, "r1", "gratefuldead-1973-06-10",
                    "GratefulDead/1973-06-10", packaged=True)
    shallow = seed_run(tmp_path, "r2", "gratefuldead-1973-06-10",
                       "GratefulDead/1973-06-10", packaged=False)
    moves = plan_migration(tmp_path)
    winners = [m for m in moves if m.winner]
    assert len(winners) == 1 and winners[0].src == deep
    apply_migration(tmp_path, moves)
    assert (tmp_path / "shows" / "gratefuldead-1973-06-10" / "package"
            / "manifest.json").exists()
    assert shallow.exists()  # loser left in place, nothing deleted


def test_migrate_idempotent_and_existing_target_wins(tmp_path: Path):
    legacy = seed_run(tmp_path, "r1", "gratefuldead-1973-06-10",
                      "GratefulDead/1973-06-10", packaged=False)
    (tmp_path / "shows" / "gratefuldead-1973-06-10").mkdir(parents=True)
    moves = plan_migration(tmp_path)
    assert [m.winner for m in moves] == [False]  # already-migrated target wins
    apply_migration(tmp_path, moves)
    assert legacy.exists()
    assert plan_migration(tmp_path) == moves  # stable on re-run


def test_status_clean_after_collision_migration(tmp_path: Path):
    # After a collision, the loser stays nested under runs/ (never-delete),
    # but its slug now exists canonically - so the legacy guard must let the
    # CLI through instead of deadlocking every command forever.
    seed_run(tmp_path, "r1", "gratefuldead-1973-06-10",
             "GratefulDead/1973-06-10", packaged=True)
    seed_run(tmp_path, "r2", "gratefuldead-1973-06-10",
             "GratefulDead/1973-06-10", packaged=False)
    apply_migration(tmp_path, plan_migration(tmp_path))
    assert (tmp_path / "runs" / "r2" / "shows" / "gratefuldead-1973-06-10").exists()
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    result = runner.invoke(cli.app, ["status", "--config",
                                     str(tmp_path / "config.toml")])
    assert result.exit_code == 0, result.output
    assert "gratefuldead-1973-06-10" in result.output


def test_migrate_cli_dry_run_moves_nothing(tmp_path: Path):
    seed_run(tmp_path, "r1", "gratefuldead-1973-06-10",
             "GratefulDead/1973-06-10", packaged=True)
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    result = runner.invoke(cli.app, ["migrate", "--dry-run", "--config",
                                     str(tmp_path / "config.toml")])
    assert result.exit_code == 0, result.output
    assert "gratefuldead-1973-06-10" in result.output
    assert not (tmp_path / "shows").exists()
