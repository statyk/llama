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
from llama.workspace import (RunWorkspace, claim_run_dir, read_model,
                             write_artifact)

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
    the usage-window-exhausted case T6b exists for, and `_get_query` now
    catches it (`_interpret_with_pause`) and parks the run -- so this
    artifact is the one thing that checkpoint has to point at, and it is
    written before the call that produces the checkpoint or not at all.

    `--no-wait` because this refusal names no reset: `resume_at` falls back
    to `unknown_reset_wait` (1h, inside the 6h cap), so a waiting pause here
    would sleep for a real hour."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')

    def boom(*a, **k):
        raise RateLimited("You've hit your session limit", scope="five_hour")
    monkeypatch.setattr(cli, "run_interpret", boom)

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973",
                                     "--auto", "--no-wait", "--name", "req2"])
    assert result.exit_code == 0, result.output
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED

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


# --- `run resume` re-interprets a session parked before criteria (T6b) -----


def test_run_resume_reinterprets_a_session_that_never_got_criteria(
        tmp_path: Path, monkeypatch):
    """The branch T6b exists for: a session parked before interpret finished
    has a request but no criteria, and today `run resume` refuses it."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    ws = RunWorkspace(tmp_path, "reinterp")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"query": "GD 1973", "limit": 1,
                                           "artist_cap": None, "min_score": None,
                                           "year_cap": None, "auto": True,
                                           "plan": False}))
    mark_paused(ws, None, [], "2026-09-06T15:10:00+00:00", "five_hour", "limit")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "reinterp"])

    assert result.exit_code == 0, result.output
    assert ws.criteria.exists()                    # interpret ran and persisted
    assert iter_sessions(tmp_path)[0].state == STATE_COMPLETE
    # The three assertions above are also satisfied by a resume that never
    # interpreted anything -- writing a default Criteria straight to disk and
    # falling through would pass all of them. The interpret provider's own
    # recorded prompt is what separates "re-interpreted THIS request" from
    # "the run completed some other way", so pin the call and its query.
    assert any(kind == "complete" and "GD 1973" in prompt
               for kind, prompt in providers["interpret"].calls), \
        providers["interpret"].calls
    assert "packaged:" in result.output, result.output


def test_run_resume_replays_the_flags_the_request_recorded(
        tmp_path: Path, monkeypatch):
    """A resumed interpret must behave like the original command, not like
    the defaults -- the flags were stamped into criteria on the first pass and
    have to be stamped again here or the replay silently differs."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    ws = RunWorkspace(tmp_path, "flags")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"query": "GD 1973", "limit": 3,
                                           "artist_cap": 0.5, "min_score": 7.5,
                                           "year_cap": None, "auto": True,
                                           "plan": False}))
    mark_paused(ws, None, [], "2026-09-06T15:10:00+00:00", "five_hour", "limit")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "flags"])

    assert result.exit_code == 0, result.output
    criteria = read_model(ws.criteria, Criteria)
    # None of these three is a Criteria default (count=1, artist_cap=1/3,
    # min_quality_score=6.0) nor the interpret fixture's own value (count=1),
    # so each one fails if the flag came from anywhere but the request.
    assert criteria.count == 3
    assert criteria.artist_cap == 0.5
    assert criteria.min_quality_score == 7.5


def test_run_resume_still_refuses_a_dir_with_neither_artifact(tmp_path: Path):
    """The pre-existing "not a llama run dir" case must keep its message."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    ws = RunWorkspace(tmp_path, "empty")
    ws.dir.mkdir(parents=True)

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "empty"])

    assert result.exit_code == 1
    assert "no criteria.json" in result.output


def test_run_resume_does_not_stamp_an_unspecified_limit(tmp_path: Path, monkeypatch):
    """`--limit` is `typer.Option(0, ...)`, so an unspecified limit persists as
    0, not null. The stamp test must therefore be falsy: `is not None` would
    read that 0 as an explicit choice and stamp `count=0` onto every resumed
    run, quietly shortlisting nothing. Only a comment guarded this fork before
    -- and a comment is not a constraint."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    ws = RunWorkspace(tmp_path, "nolimit")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"query": "GD 1973", "limit": 0,
                                           "artist_cap": None, "min_score": None,
                                           "year_cap": None, "auto": True,
                                           "plan": False}))
    mark_paused(ws, None, [], "2026-09-06T15:10:00+00:00", "five_hour", "limit")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "nolimit"])

    assert result.exit_code == 0, result.output
    criteria = read_model(ws.criteria, Criteria)
    # The interpret fixture's own count, left alone -- NOT the persisted 0.
    assert criteria.count == 1


# --- the persisted `--plan` flag is honored on a criteria-less resume ------


def test_run_resume_honors_a_persisted_plan_and_parks_awaiting_approval(
        tmp_path: Path, monkeypatch):
    """A session parked before interpret ever finished, with `--plan` set on
    the original request, must resume into the SAME shortlist-only stop --
    not into full acquisition. Before this fix, `request.json`'s `plan` was
    persisted but never read back on resume, so this resume ran the whole
    pipeline instead of stopping at the shortlist."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    ws = RunWorkspace(tmp_path, "planned")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"query": "GD 1973", "limit": 1,
                                           "artist_cap": None, "min_score": None,
                                           "year_cap": None, "auto": True,
                                           "plan": True}))
    mark_paused(ws, None, [], "2026-09-06T15:10:00+00:00", "five_hour", "limit")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "planned"])

    assert result.exit_code == 0, result.output
    # Discriminating assertions: a resume that silently drops `plan` still
    # exits 0 and prints something, so pin the specific absence (nothing
    # packaged) alongside the specific --plan hint, not just "it didn't
    # crash".
    assert "packaged:" not in result.output, result.output
    assert "to approve & process:  llama run approve planned" in result.output
    assert session_state(ws.dir) == STATE_AWAITING


def test_run_resume_without_plan_still_processes_normally(
        tmp_path: Path, monkeypatch):
    """Guards the opposite failure mode: replaying `plan` unconditionally
    (e.g. hardcoded True, or read from the wrong key) would make every
    criteria-less resume stop short, even one that never asked for --plan."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    ws = RunWorkspace(tmp_path, "unplanned")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"query": "GD 1973", "limit": 1,
                                           "artist_cap": None, "min_score": None,
                                           "year_cap": None, "auto": True,
                                           "plan": False}))
    mark_paused(ws, None, [], "2026-09-06T15:10:00+00:00", "five_hour", "limit")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "unplanned"])

    assert result.exit_code == 0, result.output
    assert "packaged:" in result.output, result.output
    assert iter_sessions(tmp_path)[0].state == STATE_COMPLETE


# --- ...and on the criteria-PRESENT path, which is the likelier one ---------

# The criteria the run-level `RateLimited` catch would have left behind: same
# shape as test_pipeline's interpret fixture, so the fake pipeline can carry
# a resume all the way to a package.
PARKED_CRITERIA = Criteria(query="GD 1973", collection="GratefulDead",
                           artist="Grateful Dead", date_from="1973-01-01",
                           date_to="1973-12-31", min_avg_rating=3.5,
                           min_reviews=2, count=1)


def test_run_resume_honors_plan_when_the_run_parked_after_interpret(
        tmp_path: Path, monkeypatch):
    """A `--plan` run that hit the limit in discover/search/winnow -- the
    run-level `RateLimited` catch -- is parked WITH criteria.json, so it
    resumes down the criteria-PRESENT branch. That branch used to hardcode
    `plan = False`, so it acquired and packaged shows the operator had asked
    only to shortlist. This is the more likely of the two paths: interpret is
    one LLM call, those three stages are where a window actually empties."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    ws = RunWorkspace(tmp_path, "midrun")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.criteria, PARKED_CRITERIA)
    write_artifact(ws.request, json.dumps({"query": "GD 1973", "limit": 1,
                                           "artist_cap": None, "min_score": None,
                                           "year_cap": None, "auto": True,
                                           "plan": True}))
    # No shortlist.json: winnow is exactly where this run died.
    assert not ws.shortlist.exists()
    mark_paused(ws, None, [], "2026-09-06T15:10:00+00:00", "five_hour", "limit")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "midrun"])

    assert result.exit_code == 0, result.output
    assert "packaged:" not in result.output, result.output
    assert "to approve & process:  llama run approve midrun" in result.output
    assert session_state(ws.dir) == STATE_AWAITING


def test_run_resume_processes_once_a_shortlist_already_exists(
        tmp_path: Path, monkeypatch):
    """The trap in the naive fix. `request.json` says `plan: true` for the
    life of the run, so replaying it whenever the artifact exists makes EVERY
    later `run resume` re-park the session awaiting and process nothing,
    permanently -- including the `llama run resume <name>` that `run approve`
    itself prints when the operator declines to process immediately.

    `--plan` means "stop AT the shortlist"; once a shortlist exists that
    directive has been satisfied. Pins the `and not ws.shortlist.exists()`
    clause: drop it and this run never packages."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    planned = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973",
                                      "--auto", "--plan", "--name", "shortlisted"])
    assert planned.exit_code == 0, planned.output
    assert "packaged:" not in planned.output, planned.output
    ws = RunWorkspace(tmp_path, "shortlisted")
    assert ws.shortlist.exists()                      # the real artifact, not a stub
    assert json.loads(ws.request.read_text())["plan"] is True
    assert session_state(ws.dir) == STATE_AWAITING

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "shortlisted"])

    assert result.exit_code == 0, result.output
    assert "packaged:" in result.output, result.output
    assert session_state(ws.dir) == STATE_COMPLETE


def test_run_resume_with_no_request_artifact_still_resumes(
        tmp_path: Path, monkeypatch):
    """Backward compatibility for run dirs predating `request.json` entirely
    (v2.4.0 and earlier wrote none). The criteria-present branch now reads the
    request to recover `plan`, so an unguarded read would crash every one of
    those resumes."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    ws = RunWorkspace(tmp_path, "ancient")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.criteria, PARKED_CRITERIA)
    assert not ws.request.exists()

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "ancient"])

    assert result.exit_code == 0, result.output
    assert "packaged:" in result.output, result.output
    assert session_state(ws.dir) == STATE_COMPLETE



def test_run_resume_never_replays_auto_over_the_explicit_flag(
        tmp_path: Path, monkeypatch):
    """`plan` is replayed off `request.json`; `auto` deliberately is NOT --
    `run resume` has its own `--auto/--interactive` flag, and a persisted
    value must never override an explicit one. Only a comment said so, and a
    comment is not a constraint: replaying `auto` here went uncaught by the
    whole suite. Asserted in BOTH directions so the pin cannot be satisfied
    by a hardcoded constant either."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(cli, "make_providers", lambda config: fake_providers(None))
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    captured = {}

    def fake_execute(config, ia, ledger, ws, criteria, count, auto, human_gate,
                     force=False, force_stage=None,
                     full_rationale=False, plan=False, pace=None):
        captured["auto"] = auto

    monkeypatch.setattr(cli, "_execute", fake_execute)

    def park(name: str, auto: bool):
        ws = RunWorkspace(tmp_path, name)
        ws.dir.mkdir(parents=True)
        write_artifact(ws.request, json.dumps({"query": "GD 1973", "limit": 1,
                                               "artist_cap": None, "min_score": None,
                                               "year_cap": None, "auto": auto,
                                               "plan": False}))
        mark_paused(ws, None, [], "2026-09-06T15:10:00+00:00", "five_hour", "limit")

    # persisted auto=True, resumed --interactive -> the flag wins
    park("wasauto", auto=True)
    r = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "wasauto",
                                "--interactive"])
    assert r.exit_code == 0, r.output
    assert captured["auto"] is False

    # persisted auto=False, resumed with the default --auto -> the flag wins
    park("wasinteractive", auto=False)
    r = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "wasinteractive"])
    assert r.exit_code == 0, r.output
    assert captured["auto"] is True


# --- T6b: the pre-flight gate runs before interpret is paid for --------------

PF_NOW = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)


def _preflight_reading(five=10, seven=7):
    from herder.usage import Meter, UsageReading
    return UsageReading(five_hour=Meter(five, PF_NOW + timedelta(hours=2)),
                        seven_day=Meter(seven, PF_NOW + timedelta(days=3)),
                        per_model={}, fetched_at=PF_NOW)


def test_the_preflight_gate_runs_before_interpret_is_paid_for(
        tmp_path: Path, monkeypatch):
    """The gate lives at the top of `_execute`, which in query mode runs
    AFTER run_interpret -- so interpret was the one LLM call a run made with
    no proactive check at all, and an unattended `--wait` run could be
    defeated by its own first call."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n{JB_OFF}\n[llm.default]\nbackend = "claude_cli"\n')
    providers = {k: CountingProvider(v) for k, v in fake_providers(None).items()}
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: _preflight_reading(five=99))
    monkeypatch.setattr(pacing, "_now", lambda: PF_NOW)
    monkeypatch.setattr(pacing, "_sleep", lambda s: pytest.fail("must not sleep"))

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973", "--auto",
                                     "--no-wait", "--name", "gated"])

    assert result.exit_code == 0, result.output
    assert providers["interpret"].calls == 0        # never paid for
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED
    # Added beyond the brief: the three assertions above are all satisfied by
    # a gate that pauses a run nothing can resume, which is precisely the
    # failure Tasks 4/5 exist to prevent and the reason this task lands after
    # them. The checkpoint is only worth writing if the request survived it
    # and criteria never appeared -- that pair is what `run resume`'s
    # re-interpret branch keys off.
    ws = RunWorkspace(tmp_path, "gated")
    assert ws.request.exists()
    assert not ws.criteria.exists()


def test_resuming_a_criteria_less_session_gates_before_re_interpreting(
        tmp_path: Path, monkeypatch):
    """`run resume`'s re-interpret branch is the one path that exists to
    recover from a limit during interpret -- and it spends an interpret call
    of its own before `_execute`'s gate is ever reached. Ungated, a resume
    fired against the same still-exhausted window pays exactly the call T6b
    exists to stop, on the command whose whole job is recovery.

    The call count is the load-bearing assertion, not the paused state: a
    gate that merely EXISTS on this branch but sits after
    `_interpret_and_stamp` still pauses, still exits 0, and still leaves the
    session paused -- it just does so having spent the call. Only
    `calls == 0` discriminates "the gate runs first" from "a gate is
    present".
    """
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n{JB_OFF}\n[llm.default]\nbackend = "claude_cli"\n')
    providers = {k: CountingProvider(v) for k, v in fake_providers(None).items()}
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: _preflight_reading(five=99))
    monkeypatch.setattr(pacing, "_now", lambda: PF_NOW)
    monkeypatch.setattr(pacing, "_sleep", lambda s: pytest.fail("must not sleep"))

    ws = RunWorkspace(tmp_path, "regated")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"query": "GD 1973", "limit": 1,
                                           "artist_cap": None, "min_score": None,
                                           "year_cap": None, "auto": True,
                                           "plan": False}))
    mark_paused(ws, None, [], "2026-09-06T07:10:00+00:00", "five_hour", "limit")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "regated",
                                     "--no-wait"])

    assert result.exit_code == 0, result.output
    assert providers["interpret"].calls == 0        # the call this branch used to spend
    assert not ws.criteria.exists()                 # nothing was interpreted
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED
    assert ws.request.exists()                      # still resumable, again


# --- T6b: a limit DURING interpret parks a resumable run ---------------------

def test_a_limit_during_interpret_parks_a_resumable_session(
        tmp_path: Path, monkeypatch):
    """Before T6b this exited 1 with nothing written. It is the first LLM
    call of the run, so an unattended run could spend its whole night here."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(pacing, "_now", lambda: PF_NOW)
    monkeypatch.setattr(pacing, "_sleep", lambda s: pytest.fail("must not sleep"))
    providers = fake_providers(None)
    # 30h out, past the 6h default cap, so it checkpoints rather than sleeps
    providers["interpret"] = LimitedProvider(PF_NOW + timedelta(hours=30))
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973",
                                     "--auto", "--name", "interp"])

    assert result.exit_code == 0, result.output          # parked, not failed
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_PAUSED
    assert info.failures == []                           # not a show failure
    assert info.query == "GD 1973"                       # readable on run list
    assert "run resume interp" in result.output
    # Added beyond the brief. `exit 0 + STATE_PAUSED + failures == []` is also
    # what a catch that merely called `mark_paused(ws, None, [], ...)` itself
    # would produce -- and such a catch would have none of the arithmetic the
    # shared renderer exists for. These three discriminate:
    ws = RunWorkspace(tmp_path, "interp")
    assert providers["interpret"].calls == 1             # refused, not skipped
    assert not ws.criteria.exists()                      # nothing interpreted
    # PF_NOW + 30h + the 2m reset skew: the resume instant came from the
    # refusal's own reset through `resume_at`, not from a bare "now".
    assert info.resume_after.startswith("2026-09-07T14:02")

    # Step 5: the end-to-end property all four T6b tasks exist for, which no
    # single task's tests assert. The parked session must actually resume.
    providers["interpret"] = fake_providers(None)["interpret"]   # window reset
    resumed = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "interp"])
    assert resumed.exit_code == 0, resumed.output
    assert iter_sessions(tmp_path)[0].state == STATE_COMPLETE
    # Added beyond the brief: STATE_COMPLETE is also reached by a resume that
    # short-circuits on a session it thinks has nothing to do. The criteria
    # this run never had is what proves it re-interpreted and then ran.
    assert ws.criteria.exists()
    assert read_model(ws.criteria, Criteria).query == "GD 1973"


def test_a_limit_during_interpret_within_max_wait_sleeps_and_finishes(
        tmp_path: Path, monkeypatch):
    clock = {"now": PF_NOW}
    monkeypatch.setattr(pacing, "_now", lambda: clock["now"])
    monkeypatch.setattr(pacing, "_sleep",
                        lambda s: clock.update(now=clock["now"] + timedelta(seconds=s)))
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    real = providers["interpret"]
    providers["interpret"] = LimitedProvider(PF_NOW + timedelta(hours=2),
                                             times=1, then=real)
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973",
                                     "--auto", "--name", "slept"])

    assert result.exit_code == 0, result.output
    assert iter_sessions(tmp_path)[0].state == STATE_COMPLETE
    # The state above holds just as well if interpret were skipped entirely.
    # This is what pins that it was refused once and then actually retried.
    assert providers["interpret"].calls >= 2
    # Added beyond the brief: `calls >= 2` is equally satisfied by a retry
    # loop that never sleeps at all -- which is the same hot spin the
    # `stalled` guard exists to prevent, just one pass earlier. The clock
    # only moves through `_sleep`, so this is what pins that it waited for
    # the window the refusal named.
    assert clock["now"] >= PF_NOW + timedelta(hours=2)
    assert iter_sessions(tmp_path)[0].failures == []


def test_a_limit_while_resume_re_interprets_parks_the_session_again(
        tmp_path: Path, monkeypatch):
    """`run resume` is the one command that exists to recover from a limit
    during interpret, and its re-interpret branch spends an interpret call of
    its own. A resume that dies there with an unhandled RateLimited is the
    same defect wearing a different command name, on the very path built to
    undo it -- and a pre-flight meter read that passes can still be followed
    by a refusal.
    """
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(pacing, "_now", lambda: PF_NOW)
    monkeypatch.setattr(pacing, "_sleep", lambda s: pytest.fail("must not sleep"))
    providers = fake_providers(None)
    providers["interpret"] = LimitedProvider(PF_NOW + timedelta(hours=30))
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    ws = RunWorkspace(tmp_path, "reparked")
    ws.dir.mkdir(parents=True)
    write_artifact(ws.request, json.dumps({"query": "GD 1973", "limit": 1,
                                           "artist_cap": None, "min_score": None,
                                           "year_cap": None, "auto": True,
                                           "plan": False}))
    mark_paused(ws, None, [], "2026-09-06T07:10:00+00:00", "five_hour", "limit")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "reparked"])

    assert result.exit_code == 0, result.output          # parked again, not failed
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_PAUSED
    assert providers["interpret"].calls == 1             # refused, not skipped
    assert not ws.criteria.exists()                      # still nothing interpreted
    assert ws.request.exists()                           # still resumable, again
    # The checkpoint was REWRITTEN from this refusal, not left at the stale
    # instant the session was parked with -- a re-park that kept 07:10 would
    # tell the operator to come back to an already-exhausted window.
    assert info.resume_after.startswith("2026-09-07T14:02")


def test_no_pacing_lets_a_limit_during_interpret_fail_the_run(
        tmp_path: Path, monkeypatch):
    """`--no-pacing` opts out of BOTH halves, as `_execute`'s run-level catch
    already does with its own `if not pace.enabled: raise`. Without the same
    guard here the new fourth pause site would quietly pause a run that asked
    for the pre-pacing behaviour."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(pacing, "_now", lambda: PF_NOW)
    monkeypatch.setattr(pacing, "_sleep", lambda s: pytest.fail("must not sleep"))
    providers = fake_providers(None)
    providers["interpret"] = LimitedProvider(PF_NOW + timedelta(hours=30))
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973", "--auto",
                                     "--name", "nopace", "--no-pacing"])

    assert result.exit_code != 0
    assert iter_sessions(tmp_path)[0].state != STATE_PAUSED


def test_a_limit_during_interpret_sleeps_at_most_once(tmp_path: Path, monkeypatch):
    """Added beyond the brief: nothing else reaches a SECOND pause at this
    site, so without this the `stalled` guard ships unpinned.

    A window that refuses again after the nap names the same reset, now in
    the past -- and `sleep_until` returns immediately on a `when` already
    gone. Without `stalled` the retry loop becomes a hot spin: it never
    calls `_sleep` again, so no sleep-budget assertion can see it.

    `times=99` is load-bearing and is what keeps that mutant a RED TEST
    rather than a hung suite. All three states were measured on
    `stalled=stalled` -> `stalled=False`: at `times=99` the spin exhausts
    the provider and this test FAILS in 0.2s; at `times=10**9` the same
    mutant hangs (exit 124 under `timeout 60`), which is what production
    would do; and with the guard restored the unbounded provider passes in
    0.5s -- so it is the guard, not the bound, that stops the spin.
    """
    clock = {"now": PF_NOW}
    monkeypatch.setattr(pacing, "_now", lambda: clock["now"])
    monkeypatch.setattr(pacing, "_sleep",
                        lambda s: clock.update(now=clock["now"] + timedelta(seconds=s)))
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    providers = fake_providers(None)
    # Refuses forever, always naming the same reset: two hours out on the
    # first refusal, already elapsed on the second.
    providers["interpret"] = LimitedProvider(PF_NOW + timedelta(hours=2), times=99)
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973",
                                     "--auto", "--name", "twice"])

    assert result.exit_code == 0, result.output
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED
    # Exactly two attempts: refused, slept once, refused again, checkpointed.
    # A third would mean it napped on an instant already behind it.
    assert providers["interpret"].calls == 2
    assert "no progress since last pause" in result.output
