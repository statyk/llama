import json
import multiprocessing as mp
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

import llama.cli as cli
from llama import pacing
from llama.models import Criteria
from llama.sessions import (STATE_AWAITING, STATE_COMPLETE, STATE_INCOMPLETE,
                            STATE_PAUSED, SessionInfo, attention_sessions,
                            iter_sessions, mark_awaiting, mark_complete,
                            mark_incomplete, mark_paused, session_state)
from llama.workspace import RunWorkspace, claim_run_dir, write_artifact

from herder import FakeProvider
from herder.limits import RateLimited

from test_pipeline import JB_OFF, FakeIA, fake_providers

runner = CliRunner()

CTX = mp.get_context("fork")


def test_claim_run_dir_suffixes(tmp_path: Path):
    # Each call creates the dir itself, so successive calls auto-suffix.
    assert claim_run_dir(tmp_path, "2026-07-27-x") == "2026-07-27-x"
    assert claim_run_dir(tmp_path, "2026-07-27-x") == "2026-07-27-x-2"
    assert claim_run_dir(tmp_path, "2026-07-27-x") == "2026-07-27-x-3"


def _claim(root, base, out):
    out.put(claim_run_dir(Path(root), base))


def test_claim_run_dir_race_distinct_names(tmp_path: Path):
    out = CTX.Queue()
    procs = [CTX.Process(target=_claim, args=(str(tmp_path), "2026-07-28-q", out))
             for _ in range(6)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(5)
    names = sorted(out.get() for _ in procs)
    assert len(set(names)) == 6                                   # all distinct
    assert len(list((tmp_path / "runs").iterdir())) == 6          # 6 dirs claimed


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

    first = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973 best soundboard", "--auto"])
    assert first.exit_code == 0, first.output
    second = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973 best soundboard", "--auto"])
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

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973 best soundboard", "--auto",
                                     "--name", "sessiontest"])
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

    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "gated", "--auto"])
    assert result.exit_code == 0, result.output
    run_dir = next((tmp_path / "runs").glob("*-gated"))
    assert session_state(run_dir) == STATE_AWAITING
    marker = json.loads((run_dir / "session.json").read_text())
    assert marker["outcome"] is None


def test_empty_winnow_still_marks_complete(tmp_path: Path, monkeypatch):
    from herder import FakeProvider

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[json.dumps({
                            "query": "x", "collection": "GratefulDead", "artist": "Grateful Dead",
                        })]), "score_reviews": FakeProvider(), "light_research": FakeProvider()})
    monkeypatch.setattr(cli, "run_search",
                        lambda ws, ia, criteria, artists=None, force=False, jerrybase_enabled=True: [])
    monkeypatch.setattr(cli, "run_winnow", lambda *a, **k: [])

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973", "--auto",
                                     "--name", "emptywinnow"])
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


def test_get_persists_the_request_before_interpreting(tmp_path: Path, monkeypatch):
    """The query lives only in argv. Without this artifact a limit during
    interpret parks a session nothing can resume -- which is why T6b was a
    resumability design and not a try/except."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973",
                                     "--auto", "--name", "req", "--limit", "2"])
    assert result.exit_code == 0, result.output

    req = json.loads((tmp_path / "runs" / "req" / "request.json").read_text())
    assert req["query"] == "GD 1973"
    assert req["limit"] == 2
    assert req["auto"] is True


def test_request_is_written_even_when_interpret_fails(tmp_path: Path, monkeypatch):
    """The write must happen BEFORE run_interpret, not merely before the run
    finishes -- a checkpoint written after the call it is meant to survive
    is worthless. RateLimited is the realistic failure here: it is exactly
    the usage-window-exhausted case T6b exists for, and _get_query
    deliberately does not catch it around this call (see the comment above
    the `run_interpret(...)` call site), so it propagates straight out of
    `get` uncaught."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')

    def boom(*a, **k):
        raise RateLimited("You've hit your session limit", scope="five_hour")
    monkeypatch.setattr(cli, "run_interpret", boom)

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973",
                                     "--auto", "--name", "req2"])
    assert result.exit_code != 0

    req = json.loads((tmp_path / "runs" / "req2" / "request.json").read_text())
    assert req["query"] == "GD 1973"


def test_run_list_shows_the_query_of_a_run_with_no_criteria(tmp_path: Path):
    """A run paused at interpret has no criteria.json, and `iter_sessions`
    defaults `query` to "" -- so the one run whose query the operator most
    needs to see would list as an empty pair of quotes."""
    ws = RunWorkspace(tmp_path, "parked")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"query": "GD 1977 Cornell"}))
    mark_paused(ws, None, [], "2026-09-06T15:10:00+00:00", "five_hour", "limit")

    info = iter_sessions(tmp_path)[0]

    assert info.query == "GD 1977 Cornell"
    assert info.profile is None


def test_run_list_json_survives_a_session_with_no_criteria(tmp_path: Path):
    """`run list --json` renders the same sessions through `_session_json`.
    A run parked before interpret is the first session in this codebase to
    reach either renderer without a criteria.json, so both paths are pinned."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    ws = RunWorkspace(tmp_path, "parked2")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"query": "GD 1977 Cornell"}))
    mark_paused(ws, None, [], "2026-09-06T15:10:00+00:00", "five_hour", "limit")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "list", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]["query"] == "GD 1977 Cornell"

    # The human-table renderer (`_print_sessions`) is the other of the "both
    # paths"/"either renderer" this docstring claims -- pin it too.
    table_result = runner.invoke(cli.app, ["--config", cfg, "run", "list"])
    assert table_result.exit_code == 0, table_result.output
    assert "GD 1977 Cornell" in table_result.output


def test_status_by_run_shows_the_query_of_a_run_with_no_criteria(tmp_path: Path):
    """`llama status --by-run` renders through `_by_run_rollup`, which
    duplicates the criteria lookup instead of going through `iter_sessions`
    -- so it needs its own `ws.request` fallback, independent of the one
    `iter_sessions` already has."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    ws = RunWorkspace(tmp_path, "parked3")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"query": "GD 1977 Cornell"}))
    mark_paused(ws, None, [], "2026-09-06T15:10:00+00:00", "five_hour", "limit")

    result = runner.invoke(cli.app, ["--config", cfg, "status", "--by-run"])

    assert result.exit_code == 0, result.output
    assert "GD 1977 Cornell" in result.output


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

    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "sunday-dead-hour", "--auto"])
    assert result.exit_code == 0, result.output
    run_dir = next((tmp_path / "runs").glob("*-sunday-dead-hour"))
    criteria = json.loads((run_dir / "criteria.json").read_text())
    assert criteria["profile"] == "sunday-dead-hour"


# --- a run that lost shows stays on the attention list ---------------------
# A per-show failure (usage limit, dropped connection, IA error) used to be
# counted and forgotten: the run marked itself `complete` regardless, so
# `run list` -- an attention list of state != complete -- never mentioned it
# again, and the reasons existed only in the terminal.


def _run_ws(tmp_path: Path) -> RunWorkspace:
    ws = RunWorkspace(tmp_path, "2026-08-29-dead")
    ws.dir.mkdir(parents=True, exist_ok=True)
    return ws


def test_mark_incomplete_records_state_outcome_and_failures(tmp_path: Path):
    ws = _run_ws(tmp_path)
    failures = [{"show": "GratefulDead/1968-02-14", "error": "usage limit reached"}]

    mark_incomplete(ws, "5 packaged, 3 held, 1 failed", failures)

    marker = json.loads(ws.session.read_text())
    assert marker["state"] == STATE_INCOMPLETE
    assert marker["outcome"] == "5 packaged, 3 held, 1 failed"
    assert marker["failures"] == failures


def test_incomplete_session_appears_on_the_attention_list(tmp_path: Path):
    ws = _run_ws(tmp_path)

    mark_incomplete(ws, "1 failed", [{"show": "x", "error": "boom"}])

    assert [s.id for s in attention_sessions(tmp_path)] == ["2026-08-29-dead"]


def test_session_info_carries_the_outcome_and_failures(tmp_path: Path):
    ws = _run_ws(tmp_path)
    failures = [{"show": "GratefulDead/1968-02-14", "error": "usage limit reached"}]

    mark_incomplete(ws, "1 failed", failures)

    info = attention_sessions(tmp_path)[0]
    assert info.outcome == "1 failed"
    assert info.failures == failures


def test_a_clean_re_mark_clears_the_earlier_failures(tmp_path: Path):
    ws = _run_ws(tmp_path)
    mark_incomplete(ws, "1 failed", [{"show": "x", "error": "boom"}])

    mark_complete(ws, "6 packaged")

    # The marker is rewritten wholesale, so a successful resume erases the
    # stale failure list by construction -- nothing to clean up separately.
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_COMPLETE
    assert info.failures == []
    assert attention_sessions(tmp_path) == []


def test_a_complete_session_carries_no_failures(tmp_path: Path):
    ws = _run_ws(tmp_path)

    mark_complete(ws, "6 packaged")

    assert iter_sessions(tmp_path)[0].failures == []


def test_a_run_that_lost_a_show_ends_incomplete_and_records_why(tmp_path: Path, monkeypatch):
    """End-to-end: the per-show failure handler used to count the loss and
    call mark_complete anyway, so the run vanished from the attention list
    and the reason survived only in the terminal."""
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    providers["brief"] = FakeProvider(completes=["not json"] * 3)
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--name", "lostrun"])
    assert result.exit_code == 0, result.output

    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_INCOMPLETE
    assert info.outcome == "1 failed"
    assert [f["show"] for f in info.failures] == ["GratefulDead/1973-06-10"]
    assert info.failures[0]["error"]  # the exception text, not an empty string


def test_a_clean_run_still_ends_complete(tmp_path: Path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--name", "cleanrun"])
    assert result.exit_code == 0, result.output

    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_COMPLETE
    assert info.failures == []
    assert attention_sessions(tmp_path) == []


def test_paused_round_trips_the_resume_time(tmp_path):
    ws = _run_ws(tmp_path)
    mark_paused(ws, "3 packaged", [], "2026-09-04T15:10:00+00:00",
                "five_hour", "session limit")
    assert session_state(ws.dir) == STATE_PAUSED
    info = [s for s in attention_sessions(tmp_path) if s.id == ws.name][0]
    assert info.state == STATE_PAUSED
    assert info.resume_after == "2026-09-04T15:10:00+00:00"
    assert info.pause_reason == "session limit"


def test_a_paused_run_is_on_the_attention_list(tmp_path):
    ws = _run_ws(tmp_path)
    mark_paused(ws, None, [], "2026-09-04T15:10:00+00:00", "five_hour", "x")
    assert [s.id for s in attention_sessions(tmp_path)] == [ws.name]


def test_completing_a_paused_run_erases_the_pause_block(tmp_path):
    ws = _run_ws(tmp_path)
    mark_paused(ws, None, [], "2026-09-04T15:10:00+00:00", "five_hour", "x")
    mark_complete(ws, "13 packaged")
    assert session_state(ws.dir) == STATE_COMPLETE
    assert attention_sessions(tmp_path) == []
    marker = json.loads((ws.dir / "session.json").read_text())
    assert "resume_after" not in marker or marker["resume_after"] is None


class LimitedProvider:
    """Raises a usage limit for the first `times` calls, then defers to `then`."""

    def __init__(self, resets_at, times=1, then=None):
        self.resets_at, self.times, self.then = resets_at, times, then
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        if self.calls <= self.times:
            raise RateLimited("You've hit your session limit", scope="five_hour",
                              resets_at=self.resets_at)
        return self.then.complete(prompt)

    def research(self, brief: str) -> str:
        return self.complete(brief)


def test_a_usage_limit_pauses_the_run_instead_of_failing_the_show(
        tmp_path: Path, monkeypatch):
    """A limit is not a show failure: nothing is wrong with the show, so it
    is left for the resume rather than recorded in failures[]."""
    now = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(pacing, "_now", lambda: now)
    monkeypatch.setattr(pacing, "_sleep", lambda s: pytest.fail("must not sleep"))

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    # 30h out, well past the 6h default cap, so it checkpoints rather than sleeps
    providers["brief"] = LimitedProvider(now + timedelta(hours=30))
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--name", "pausedrun"])
    assert result.exit_code == 0, result.output

    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_PAUSED
    assert info.failures == []                    # NOT a failure
    assert info.resume_after.startswith("2026-09-05")
    assert info in attention_sessions(tmp_path)
    assert "run resume pausedrun" in result.output


def test_a_usage_limit_within_max_wait_sleeps_and_then_finishes(
        tmp_path: Path, monkeypatch):
    clock = {"now": datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(pacing, "_now", lambda: clock["now"])
    monkeypatch.setattr(pacing, "_sleep",
                        lambda s: clock.update(now=clock["now"] + timedelta(seconds=s)))

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    real_brief = providers["brief"]
    providers["brief"] = LimitedProvider(clock["now"] + timedelta(hours=2),
                                         times=1, then=real_brief)
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--name", "sleptrun"])
    assert result.exit_code == 0, result.output

    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_COMPLETE           # slept, retried, finished
    assert info.failures == []
    assert clock["now"] >= datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
    # The three assertions above ALL hold if the interrupted show is silently
    # dropped from the queue instead of retried, which is exactly the bug this
    # test exists to catch. These two are what actually pin it: the show came
    # back round, and it packaged.
    assert providers["brief"].calls >= 2          # refused once, then retried
    assert info.outcome == "1 packaged"
    assert "packaged:" in result.output


def test_no_pacing_restores_the_old_failure_behaviour(tmp_path: Path, monkeypatch):
    """--no-pacing is the escape hatch: the limit is a per-show failure again."""
    now = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(pacing, "_now", lambda: now)
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    providers["brief"] = LimitedProvider(now + timedelta(hours=2), times=99)
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--name", "nopacing", "--no-pacing"])
    assert result.exit_code == 0, result.output

    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_INCOMPLETE
    assert [f["show"] for f in info.failures] == ["GratefulDead/1973-06-10"]


class CountingProvider:
    """Wraps a provider and counts every call that reaches it."""

    def __init__(self, inner):
        self.inner, self.calls = inner, 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        return self.inner.complete(prompt)

    def research(self, brief: str) -> str:
        self.calls += 1
        return self.inner.research(brief)


def test_resuming_a_packaged_run_costs_no_llm_calls(tmp_path: Path, monkeypatch):
    """`CLAUDE.md` promises operators that "resuming costs nothing for shows
    already packaged": a resume genuinely RE-ENTERS the show (`run_winnow`
    runs again, the stages walk from the top) and every stage's own
    `should_run` gate finds nothing to do, so zero LLM calls are spent. A
    pause is only cheap to recover from if this holds -- and it is
    `should_run`'s property specifically, not an artifact of the show never
    being revisited at all: if the library/ledger dedup in `run_winnow`
    dropped the candidate before re-entry (e.g. a broken `should_run` that
    always re-ran everything, defeated by a *different* short-circuit further
    up the pipeline), the call count would still hold at zero for the wrong
    reason. The `"packaged:"` assertion below pins that the resumed run
    actually walked back into the show and packaged it again, not that it
    quietly gave up before getting there.
    """
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = {k: CountingProvider(v) for k, v in fake_providers(None).items()}
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    first = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973",
                                    "--auto", "--name", "cheap"])
    assert first.exit_code == 0, first.output

    spent = sum(p.calls for p in providers.values())
    # The non-empty precondition, and the reason this test is worth having:
    # `== spent` below is satisfied just as happily by a run that never
    # happened. Assert the work occurred before asserting it is not repeated.
    assert spent > 0

    resumed = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "cheap"])
    assert resumed.exit_code == 0, resumed.output
    # Pins re-entry, not mere cheapness: a `should_run` bug that made every
    # stage always re-run would still hit `spent` calls, but a *different*
    # short-circuit (winnow's library/ledger dedup dropping the now-known
    # show before any stage is reached) would spend zero for the wrong
    # reason and exit with "No shows survived winnowing." instead of this.
    assert "packaged:" in resumed.output, resumed.output

    assert sum(p.calls for p in providers.values()) == spent
