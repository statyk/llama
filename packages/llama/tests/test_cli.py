from pathlib import Path

from typer.testing import CliRunner

from llama.cli import app

runner = CliRunner()


def test_help_shows_description():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Live Music Archive" in result.output


def test_version_flag_works():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0


def test_version_is_no_longer_a_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_config_on_callback_works(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path}"\n')
    result = runner.invoke(app, ["--config", str(cfg), "status"])
    assert result.exit_code == 0, result.output


def test_config_after_subcommand_now_fails(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path}"\n')
    result = runner.invoke(app, ["status", "--config", str(cfg)])
    assert result.exit_code != 0


def test_artists_include_junk_accepted_all_rejected(tmp_path: Path, monkeypatch):
    import llama.cli as cli

    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "load_or_build", lambda ia, cache, refresh=False: [])
    accepted = runner.invoke(app, ["--config", str(cfg), "artists", "--include-junk"])
    assert "No such option" not in accepted.output
    rejected = runner.invoke(app, ["--config", str(cfg), "artists", "--all"])
    assert rejected.exit_code != 0
    assert "No such option" in rejected.output


def test_help_orders_and_panels_commands():
    out = runner.invoke(app, ["--help"]).output
    for panel in ["Acquire", "Watch", "Fix & ship", "Sessions & config"]:
        assert panel in out


def test_pipeline_exits_zero_with_no_config_present():
    result = runner.invoke(app, ["pipeline"])
    assert result.exit_code == 0, result.output


def test_pipeline_is_in_the_watch_panel():
    out = runner.invoke(app, ["--help"]).output
    assert "pipeline" in out


def test_pipeline_prints_stage_names_and_gates():
    out = runner.invoke(app, ["pipeline"]).output
    for stage in ["interpret", "search", "winnow", "select", "gather",
                  "research", "vet", "brief", "synthesize", "package", "deliver"]:
        assert stage in out, stage
    assert "gate 1" in out
    assert "gate 2" in out


def test_pipeline_prints_state_names():
    out = runner.invoke(app, ["pipeline"]).output
    for state in ["held", "selected", "gathered", "researched", "vetted",
                  "briefed", "scripted", "packaged", "delivered"]:
        assert state in out, state


def test_pipeline_prints_readiness_annotations_and_redo_hatch():
    out = runner.invoke(app, ["pipeline"]).output
    assert "voiced" in out
    assert "broadcast-ready" in out
    assert "fix" in out
    assert "redo --from" in out


def test_pipeline_makes_no_writes(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["pipeline"])
    assert result.exit_code == 0
    assert list(tmp_path.iterdir()) == []
