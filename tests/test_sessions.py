import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.models import Criteria
from llama.sessions import (STATE_AWAITING, STATE_COMPLETE, STATE_INCOMPLETE,
                            SessionInfo, attention_sessions, iter_sessions,
                            mark_awaiting, mark_complete, session_state)
from llama.workspace import RunWorkspace, unique_run_name, write_artifact

from test_pipeline import FakeIA, fake_providers

runner = CliRunner()


def test_unique_run_name(tmp_path: Path):
    assert unique_run_name(tmp_path, "2026-07-27-x") == "2026-07-27-x"
    (tmp_path / "runs" / "2026-07-27-x").mkdir(parents=True)
    assert unique_run_name(tmp_path, "2026-07-27-x") == "2026-07-27-x-2"
    (tmp_path / "runs" / "2026-07-27-x-2").mkdir()
    assert unique_run_name(tmp_path, "2026-07-27-x") == "2026-07-27-x-3"


def test_marker_roundtrip(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    assert session_state(ws.dir) == STATE_INCOMPLETE          # absent
    mark_awaiting(ws)
    assert session_state(ws.dir) == STATE_AWAITING
    mark_complete(ws, "2 packaged, 1 held")
    assert session_state(ws.dir) == STATE_COMPLETE


def test_malformed_marker_is_incomplete(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    ws.dir.mkdir(parents=True)
    ws.session.write_text("{not json")
    assert session_state(ws.dir) == STATE_INCOMPLETE
    ws.session.write_text('{"state": "weird"}')
    assert session_state(ws.dir) == STATE_INCOMPLETE


def test_repeat_find_creates_a_second_run_not_a_silent_resume(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: None)
    cfg = str(tmp_path / "config.toml")

    first = runner.invoke(cli.app, ["find", "GD 1973 best soundboard", "--auto",
                                    "--config", cfg])
    assert first.exit_code == 0, first.output
    second = runner.invoke(cli.app, ["find", "GD 1973 best soundboard", "--auto",
                                     "--config", cfg])
    assert second.exit_code == 0, second.output

    run_dirs = sorted(d.name for d in (tmp_path / "runs").iterdir())
    assert len(run_dirs) == 2
    base, dupe = run_dirs
    assert dupe == f"{base}-2"
    # each run got its own freshly interpreted criteria, not a shared/resumed one
    assert json.loads((tmp_path / "runs" / base / "criteria.json").read_text())
    assert json.loads((tmp_path / "runs" / dupe / "criteria.json").read_text())


def test_execute_marks_complete_with_outcome(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    cfg = str(tmp_path / "config.toml")

    result = runner.invoke(cli.app, ["find", "GD 1973 best soundboard", "--auto", "--script",
                                     "--run-name", "sessiontest", "--config", cfg])
    assert result.exit_code == 0, result.output
    ws = RunWorkspace(tmp_path, "sessiontest")
    marker = json.loads(ws.session.read_text())
    assert marker["state"] == STATE_COMPLETE
    assert marker["outcome"]  # non-empty


def test_execute_marks_awaiting_at_human_gate(tmp_path: Path, monkeypatch):
    from llama.profiles import Profile, save_profile

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    save_profile(tmp_path, Profile(
        name="gated",
        criteria=Criteria(query="x", collection="GratefulDead", artist="Grateful Dead",
                          date_from="1973-01-01", date_to="1973-12-31"),
        count=1, human_gate=True,
    ))
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["profile", "run", "gated", "--auto", "--config", cfg])
    assert result.exit_code == 0, result.output
    run_dir = next((tmp_path / "runs").glob("*-gated"))
    assert session_state(run_dir) == STATE_AWAITING
    marker = json.loads((run_dir / "session.json").read_text())
    assert marker["outcome"] is None


def test_empty_winnow_still_marks_complete(tmp_path: Path, monkeypatch):
    from llama.llm.fake import FakeProvider

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[json.dumps({
                            "query": "x", "collection": "GratefulDead", "artist": "Grateful Dead",
                        })]), "score_reviews": FakeProvider(), "light_research": FakeProvider()})
    monkeypatch.setattr(cli, "run_search",
                        lambda ws, ia, criteria, artists=None, force=False, jerrybase_enabled=True: [])
    monkeypatch.setattr(cli, "run_winnow", lambda *a, **k: [])

    result = runner.invoke(cli.app, ["find", "GD 1973", "--auto",
                                     "--run-name", "emptywinnow", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert "No shows survived winnowing." in result.output
    ws = RunWorkspace(tmp_path, "emptywinnow")
    marker = json.loads(ws.session.read_text())
    assert marker["state"] == STATE_COMPLETE


def _session(tmp_path, name, *, state=None, query="q", profile=None):
    ws = RunWorkspace(tmp_path, name)
    write_artifact(ws.criteria, Criteria(query=query, profile=profile))
    if state == STATE_AWAITING:
        mark_awaiting(ws)
    elif state == STATE_COMPLETE:
        mark_complete(ws, "done")
    return ws


def test_iter_and_attention_sessions(tmp_path: Path):
    _session(tmp_path, "a-complete", state=STATE_COMPLETE)
    _session(tmp_path, "b-awaiting", state=STATE_AWAITING, profile="sunday-dead-hour")
    _session(tmp_path, "c-crashed")                    # no marker -> incomplete
    infos = {s.id: s for s in iter_sessions(tmp_path)}
    assert infos["a-complete"].state == STATE_COMPLETE
    assert infos["b-awaiting"].state == STATE_AWAITING
    assert infos["b-awaiting"].profile == "sunday-dead-hour"
    assert infos["c-crashed"].state == STATE_INCOMPLETE
    assert {s.id for s in attention_sessions(tmp_path)} == {"b-awaiting", "c-crashed"}


def test_session_without_criteria(tmp_path: Path):
    RunWorkspace(tmp_path, "bare").dir.mkdir(parents=True)
    info = {s.id: s for s in iter_sessions(tmp_path)}["bare"]
    assert info.query == "" and info.profile is None


def test_profile_run_stamps_profile_name_into_criteria(tmp_path: Path, monkeypatch):
    from llama.profiles import Profile, save_profile

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    save_profile(tmp_path, Profile(
        name="sunday-dead-hour",
        criteria=Criteria(query="x", collection="GratefulDead", artist="Grateful Dead",
                          date_from="1973-01-01", date_to="1973-12-31"),
        count=1,
    ))
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["profile", "run", "sunday-dead-hour", "--auto",
                                     "--config", cfg])
    assert result.exit_code == 0, result.output
    run_dir = next((tmp_path / "runs").glob("*-sunday-dead-hour"))
    criteria = json.loads((run_dir / "criteria.json").read_text())
    assert criteria["profile"] == "sunday-dead-hour"
