"""The show loop's pause/resume bookkeeping, driven directly.

These sit below the end-to-end pause tests in test_sessions.py on purpose.
The end-to-end fixture processes ONE show, which cannot tell "the
interrupted show came back round" apart from "it was dropped and something
else finished the run" for every mutation of the queue arithmetic. Here the
run has three shows and a scripted process_show, so the exact set that comes
back after a pause is observable.
"""
import collections
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from herder.limits import RateLimited

import llama.cli as cli
from llama import pacing
from llama.config import Config, PacingConfig
from llama.locks import Locked
from llama.models import Candidate, Criteria, QualityAssessment, ShortlistEntry
from llama.sessions import STATE_COMPLETE, STATE_PAUSED, iter_sessions
from llama.workspace import RunWorkspace

NOW = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)


def _entry(pid: str, rank: int) -> ShortlistEntry:
    return ShortlistEntry(
        candidate=Candidate(performance_id=pid, collection="C", date="1973-06-10",
                            recordings=[]),
        assessment=QualityAssessment(performance_id=pid, quality_score=9.0,
                                     rationale="fine"),
        rank=rank)


def _clock(monkeypatch, *, sleep_budget: int = 4) -> dict:
    """A frozen clock that only moves when the loop sleeps.

    Resets in these tests are minutes out, not hours, so one pause costs one
    `_sleep` call: sleep_until naps in 15-minute chunks, and a budget
    expressed in chunks would not measure pauses.

    The budget is a guard, not a fixture detail: without the no-progress
    guard a backend that keeps refusing naps forever, and a hanging test is
    a much worse failure report than a failing one.
    """
    state = {"now": NOW, "sleeps": 0}

    def _sleep(seconds):
        state["sleeps"] += 1
        if state["sleeps"] > sleep_budget:
            raise AssertionError(f"slept more than {sleep_budget} times - "
                                 "the loop is not making progress")
        state["now"] = state["now"] + timedelta(seconds=seconds)

    monkeypatch.setattr(pacing, "_now", lambda: state["now"])
    monkeypatch.setattr(pacing, "_sleep", _sleep)
    return state


def _drive(tmp_path: Path, monkeypatch, process, pids, *,
           pace=None, config=None) -> tuple[RunWorkspace, list[str]]:
    """Run `_execute` over `pids` with `process` standing in for process_show."""
    config = config or Config(root=tmp_path)
    ws = RunWorkspace(tmp_path, "r1")
    entries = [_entry(p, i + 1) for i, p in enumerate(pids)]
    seen: list[str] = []

    def _process_show(_ws, _ia, _ledger, entry, *args, **kwargs):
        pid = entry.candidate.performance_id
        seen.append(pid)
        return process(pid)

    # run_winnow/run_search are stubbed, but their argument lists are still
    # evaluated, so the provider map has to answer every key by name.
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: collections.defaultdict(lambda: None))
    monkeypatch.setattr(cli, "run_search", lambda *a, **k: None)
    monkeypatch.setattr(cli, "run_winnow", lambda *a, **k: entries)
    monkeypatch.setattr(cli, "choose_entries", lambda entries, *a, **k: entries)
    monkeypatch.setattr(cli, "make_client", lambda config: None)
    monkeypatch.setattr(cli, "process_show", _process_show)

    cli._execute(config, None, None, ws, Criteria(query="x"), len(pids),
                 auto=True, human_gate=False, pace=pace)
    return ws, seen


def _limits_once(pid_to_limit: str, resets_at):
    """process_show that refuses `pid_to_limit` the first time and packages
    everything else."""
    refused = {"done": False}

    def _process(pid):
        if pid == pid_to_limit and not refused["done"]:
            refused["done"] = True
            raise RateLimited("You've hit your session limit", scope="five_hour",
                              resets_at=resets_at)
        return f"{pid}/package"
    return _process


def test_the_show_that_hit_the_limit_is_retried_not_dropped(tmp_path, monkeypatch):
    """The interrupted show must be at the FRONT of the queue the resume
    works through -- `pending[idx:]`, not `pending[idx + 1:]`, and not a
    slice taken on the following iteration."""
    _clock(monkeypatch)
    pace = pacing.pace_options(Config())          # wait, 6h cap
    ws, seen = _drive(tmp_path, monkeypatch,
                      _limits_once("b", NOW + timedelta(minutes=10)),
                      ["a", "b", "c"], pace=pace)

    assert seen == ["a", "b", "b", "c"]           # b came back round
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_COMPLETE
    assert info.outcome == "3 packaged"           # nothing silently lost


def test_a_checkpoint_leaves_the_interrupted_show_for_the_resume(tmp_path, monkeypatch):
    """Same arithmetic on the branch that does not sleep: the show that hit
    the limit is one of the shows left, not one of the shows done."""
    _clock(monkeypatch)
    pace = pacing.pace_options(Config(), max_wait="1h")   # 2h reset exceeds it
    ws, seen = _drive(tmp_path, monkeypatch,
                      _limits_once("b", NOW + timedelta(hours=2)),
                      ["a", "b", "c"], pace=pace)

    assert seen == ["a", "b"]                     # c never reached
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_PAUSED
    assert info.outcome == "1 packaged"           # only a
    assert info.failures == []


def test_a_checkpoint_reports_how_many_shows_are_left(tmp_path, monkeypatch, capsys):
    _clock(monkeypatch)
    pace = pacing.pace_options(Config(), max_wait="1h")
    _drive(tmp_path, monkeypatch, _limits_once("b", NOW + timedelta(hours=2)),
           ["a", "b", "c"], pace=pace)

    out = capsys.readouterr().out
    # b and c: the interrupted show plus the untouched tail.
    assert "2 shows left" in out
    assert "llama run resume r1" in out


def test_the_resume_hint_prints_a_max_wait_the_shell_can_actually_take(
        tmp_path, monkeypatch, capsys):
    """A checkpoint over the cap suggests raising it. The suggested value has
    to parse -- format_delta's "2h 0m" does not -- and has to cover the wait
    it was printed for, or the rerun checkpoints again for the same reason."""
    _clock(monkeypatch, sleep_budget=0)
    pace = pacing.pace_options(Config(), max_wait="1h")
    _drive(tmp_path, monkeypatch, _limits_once("a", NOW + timedelta(hours=2, seconds=30)),
           ["a"], pace=pace)

    out = capsys.readouterr().out
    assert "exceeds --max-wait 1h 0m" in out                # prose, unchanged
    hint = out.split("--max-wait ")[-1].strip()             # the copy-pasteable one
    assert pacing.parse_duration(hint) >= 2 * 3600 + 30 + 120


def test_an_interrupt_during_the_wait_checkpoints_rather_than_losing_the_run(
        tmp_path, monkeypatch, capsys):
    """Ctrl-C out of a multi-hour nap is the likeliest way this loop ends in
    practice; it must leave the same resumable marker a checkpoint does."""
    state = {"now": NOW}
    monkeypatch.setattr(pacing, "_now", lambda: state["now"])

    def _interrupt(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(pacing, "_sleep", _interrupt)
    ws, seen = _drive(tmp_path, monkeypatch,
                      _limits_once("b", NOW + timedelta(minutes=10)),
                      ["a", "b", "c"], pace=pacing.pace_options(Config()))

    assert seen == ["a", "b"]
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_PAUSED
    assert info.outcome == "1 packaged"
    assert info.resume_after == "2026-09-04T08:12:00+00:00"
    assert "interrupted; resume with: llama run resume r1" in capsys.readouterr().out


def test_a_backend_that_keeps_refusing_checkpoints_instead_of_napping_forever(
        tmp_path, monkeypatch, capsys):
    """The no-progress guard. One pause cycle that buys nothing is enough:
    the second refusal checkpoints rather than sleeping again."""
    clock = _clock(monkeypatch, sleep_budget=4)

    def _always_limited(pid):
        raise RateLimited("You've hit your session limit", scope="five_hour",
                          resets_at=clock["now"] + timedelta(minutes=10))

    _drive(tmp_path, monkeypatch, _always_limited, ["a", "b"],
           pace=pacing.pace_options(Config()))

    out = capsys.readouterr().out
    assert "no progress since last pause" in out
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED
    assert clock["sleeps"] >= 1        # it did try once before giving up


def test_progress_between_pauses_still_earns_another_sleep(tmp_path, monkeypatch):
    """The guard must key on progress, not on "we have paused before" --
    otherwise a long run that hits two windows stops at the second."""
    clock = _clock(monkeypatch)
    limited = {"a": True, "c": True}

    def _process(pid):
        if limited.get(pid):
            limited[pid] = False
            raise RateLimited("You've hit your session limit", scope="five_hour",
                              resets_at=clock["now"] + timedelta(minutes=10))
        return f"{pid}/package"

    ws, seen = _drive(tmp_path, monkeypatch, _process, ["a", "b", "c"],
                      pace=pacing.pace_options(Config()))

    assert seen == ["a", "a", "b", "c", "c"]
    assert iter_sessions(tmp_path)[0].state == STATE_COMPLETE
    assert clock["sleeps"] >= 2


def test_a_limit_on_a_deferred_show_keeps_it_queued(tmp_path, monkeypatch):
    """The second bookkeeping site: shows another run held the lock on are
    processed in a later pass, and a limit there must re-queue that show
    too."""
    _clock(monkeypatch)
    real_file_lock = cli.file_lock
    held = {"b"}

    def _file_lock(path, *, blocking=True):
        if not blocking and path.parent.name.endswith("b"):
            raise Locked(path)
        return real_file_lock(path, blocking=blocking)

    monkeypatch.setattr(cli, "file_lock", _file_lock)
    ws, seen = _drive(tmp_path, monkeypatch,
                      _limits_once("b", NOW + timedelta(minutes=10)),
                      ["a", "b"], pace=pacing.pace_options(Config()))

    assert seen == ["a", "b", "b"]          # a first, b deferred, refused, retried
    assert iter_sessions(tmp_path)[0].state == STATE_COMPLETE
    assert held == {"b"}


def test_a_limit_mid_pass_keeps_the_shows_another_run_had_locked(tmp_path, monkeypatch):
    """The two queues merge: shows deferred earlier in the same pass are as
    unprocessed as the tail after the limit, and dropping them loses a show
    from a run that then reports itself complete."""
    _clock(monkeypatch)
    real_file_lock = cli.file_lock

    def _file_lock(path, *, blocking=True):
        if not blocking and path.parent.name.endswith("a"):
            raise Locked(path)                 # another run holds `a`
        return real_file_lock(path, blocking=blocking)

    monkeypatch.setattr(cli, "file_lock", _file_lock)
    ws, seen = _drive(tmp_path, monkeypatch,
                      _limits_once("b", NOW + timedelta(minutes=10)),
                      ["a", "b", "c"], pace=pacing.pace_options(Config()))

    # a deferred, b refused mid-pass; the resume works through b, c and a.
    assert sorted(seen) == ["a", "b", "b", "c"]
    assert seen[0] == "b"                      # the interrupted show goes first
    assert iter_sessions(tmp_path)[0].outcome == "3 packaged"


def test_the_run_switches_on_raw_capture_for_every_provider(tmp_path, monkeypatch):
    """_execute is the one place herder's capture destination is set; without
    it an unrecognized backend failure leaves only 500 truncated characters."""
    from herder import failures

    monkeypatch.setattr(failures, "_capture_dir", None)
    _clock(monkeypatch, sleep_budget=0)
    _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/package", ["a"],
           pace=pacing.pace_options(Config()))

    assert failures._capture_dir == tmp_path / "llm-failures"


def test_pacing_disabled_records_the_limit_as_a_show_failure(tmp_path, monkeypatch):
    """The escape hatch keeps the old behaviour exactly: a failure entry, the
    run carries on to the next show, and nothing sleeps."""
    _clock(monkeypatch, sleep_budget=0)
    pace = pacing.pace_options(Config(pacing=PacingConfig(enabled=False)))
    ws, seen = _drive(tmp_path, monkeypatch,
                      _limits_once("b", NOW + timedelta(hours=2)),
                      ["a", "b", "c"], pace=pace)

    assert seen == ["a", "b", "c"]          # no retry, no pause
    info = iter_sessions(tmp_path)[0]
    assert [f["show"] for f in info.failures] == ["b"]
    assert info.outcome == "2 packaged, 1 failed"


def test_no_wait_checkpoints_even_inside_the_cap(tmp_path, monkeypatch, capsys):
    _clock(monkeypatch, sleep_budget=0)
    pace = pacing.pace_options(Config(), wait=False)
    _drive(tmp_path, monkeypatch, _limits_once("a", NOW + timedelta(minutes=30)),
           ["a", "b"], pace=pace)

    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED
    assert "2 shows left" in capsys.readouterr().out


def test_a_pause_records_the_reset_time_and_the_scope(tmp_path, monkeypatch):
    _clock(monkeypatch)
    pace = pacing.pace_options(Config(), wait=False)
    ws, _ = _drive(tmp_path, monkeypatch,
                   _limits_once("a", NOW + timedelta(hours=2)),
                   ["a"], pace=pace)

    import json
    marker = json.loads((ws.dir / "session.json").read_text())
    assert marker["resume_after"] == "2026-09-04T10:02:00+00:00"   # reset + 2m skew
    assert marker["pause_scope"] == "five_hour"
    assert "session limit" in marker["pause_reason"]


def test_a_limit_with_no_named_reset_waits_the_configured_default(tmp_path, monkeypatch):
    clock = _clock(monkeypatch)

    def _process(pid):
        raise RateLimited("usage limit reached")     # no resets_at

    _drive(tmp_path, monkeypatch, _process, ["a"],
           pace=pacing.pace_options(Config(), wait=False))

    import json
    ws = RunWorkspace(tmp_path, "r1")
    marker = json.loads((ws.dir / "session.json").read_text())
    assert marker["resume_after"] == "2026-09-04T09:00:00+00:00"   # +1h default
    assert marker["pause_scope"] is None
    assert clock["sleeps"] == 0


# ---------------------------------------------------------------------------
# The CLI flags: what reaches _execute, and what fails before the run starts
# ---------------------------------------------------------------------------

from typer.testing import CliRunner                                    # noqa: E402

from llama.workspace import write_artifact                             # noqa: E402

runner = CliRunner()


def _captured_pace(tmp_path, monkeypatch, argv, *, config_body="") -> list:
    """Invoke the CLI with _execute stubbed, returning the pace it was given."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path}"\n{config_body}')
    seen = []

    def _fake_execute(*args, pace=None, **kwargs):
        seen.append(pace)

    monkeypatch.setattr(cli, "_execute", _fake_execute)
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: None)
    result = runner.invoke(cli.app, ["--config", str(cfg)] + argv)
    return result, seen


def _seeded_run(tmp_path, name="r1"):
    ws = RunWorkspace(tmp_path, name)
    write_artifact(ws.criteria, Criteria(query="q"))
    return ws


def test_get_passes_the_pacing_flags_through_to_the_loop(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_interpret", lambda ws, provider, query: Criteria(query=query))
    monkeypatch.setattr(cli, "make_providers", lambda config: collections.defaultdict(lambda: None))
    result, seen = _captured_pace(tmp_path, monkeypatch,
                                  ["get", "q", "--auto", "--name", "r1",
                                   "--no-wait", "--max-wait", "30h"])
    assert result.exit_code == 0, result.output
    assert seen[0].wait is False
    assert seen[0].max_wait_s == 30 * 3600
    assert seen[0].enabled is True


def test_get_defaults_come_from_the_config(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "run_interpret", lambda ws, provider, query: Criteria(query=query))
    monkeypatch.setattr(cli, "make_providers", lambda config: collections.defaultdict(lambda: None))
    result, seen = _captured_pace(tmp_path, monkeypatch,
                                  ["get", "q", "--auto", "--name", "r1"],
                                  config_body="[pacing]\nwait = false\nmax_wait = \"90m\"\n")
    assert result.exit_code == 0, result.output
    assert seen[0].wait is False
    assert seen[0].max_wait_s == 90 * 60


def test_no_pacing_reaches_the_loop_disabled(tmp_path, monkeypatch):
    _seeded_run(tmp_path)
    result, seen = _captured_pace(tmp_path, monkeypatch,
                                  ["run", "resume", "r1", "--no-pacing"])
    assert result.exit_code == 0, result.output
    assert seen[0].enabled is False


def test_run_resume_passes_the_pacing_flags_through(tmp_path, monkeypatch):
    _seeded_run(tmp_path)
    result, seen = _captured_pace(tmp_path, monkeypatch,
                                  ["run", "resume", "r1", "--max-wait", "12h"])
    assert result.exit_code == 0, result.output
    assert seen[0].max_wait_s == 12 * 3600


@pytest.mark.parametrize("argv", [
    ["get", "q", "--auto", "--max-wait", "soon"],
    ["run", "resume", "r1", "--max-wait", "soon"],
    ["run", "approve", "r1", "--max-wait", "soon"],
])
def test_a_malformed_max_wait_fails_before_the_run_starts(tmp_path, monkeypatch, argv):
    """Eagerly validated on every command that takes it: a typo must not
    surface four shows in, when the pause it governs finally happens."""
    _seeded_run(tmp_path)
    result, seen = _captured_pace(tmp_path, monkeypatch, argv)
    assert result.exit_code == 1
    assert "not a duration" in result.output
    assert seen == []                       # _execute never ran
