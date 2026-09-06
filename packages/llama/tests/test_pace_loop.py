"""The show loop's pause/resume bookkeeping, driven directly.

These sit below the end-to-end pause tests in test_sessions.py on purpose.
The end-to-end fixture processes ONE show, which cannot tell "the
interrupted show came back round" apart from "it was dropped and something
else finished the run" for every mutation of the queue arithmetic. Here the
run has three shows and a scripted process_show, so the exact set that comes
back after a pause is observable.
"""
import collections
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from herder import HerderError, TaskFailed
from herder.limits import RateLimited

import llama.cli as cli
from llama import pacing, pacing_state
from llama.config import Config, LLMTaskConfig, PacingConfig
from llama.locks import Locked
from llama.models import Candidate, Criteria, QualityAssessment, ShortlistEntry
from llama.sessions import (STATE_COMPLETE, STATE_INCOMPLETE, STATE_PAUSED,
                            iter_sessions)
from llama.workspace import RunWorkspace

NOW = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
RESET_5H = NOW + timedelta(hours=2)
RESET_7D = NOW + timedelta(days=3)


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
           pace=None, config=None, winnow=None,
           search=None, choose=None) -> tuple[RunWorkspace, list[str]]:
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
    monkeypatch.setattr(cli, "run_search", search or (lambda *a, **k: None))
    monkeypatch.setattr(cli, "run_winnow", winnow or (lambda *a, **k: entries))
    # `choose=` because this is set AFTER the caller's own monkeypatches and
    # would clobber one: a test that wants to see what `count` reaches
    # choose_entries as has to hand it in, not patch around this.
    monkeypatch.setattr(cli, "choose_entries",
                        choose or (lambda entries, *a, **k: entries))
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
    # Both printed durations have to parse. The prose one does because
    # parse_duration tolerates the space; the copy-pasteable one uses
    # duration_arg because it must additionally round UP -- a floored value
    # would be shorter than the wait it was printed for, so pasting it would
    # checkpoint again for the same reason.
    assert pacing.parse_duration("1h 0m") == 3600
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

    def _process(pid):
        if pid == "a":
            raise TaskFailed("LLM task 'brief' failed after 3 attempts")
        if pid == "b":
            raise RateLimited("You've hit your session limit", scope="five_hour",
                              resets_at=NOW + timedelta(minutes=10))
        return f"{pid}/package"

    ws, seen = _drive(tmp_path, monkeypatch, _process, ["a", "b", "c"],
                      pace=pacing.pace_options(Config()))

    assert seen == ["a", "b"]
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_PAUSED
    assert info.outcome == "1 failed"
    assert info.resume_after == "2026-09-04T08:12:00+00:00"
    # Same rule as the ordinary checkpoint: the interrupted marker is the only
    # durable record of the show this run had already lost.
    assert [f["show"] for f in info.failures] == ["a"]
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


def test_a_checkpoint_carries_the_failures_the_run_had_already_taken(
        tmp_path, monkeypatch):
    """A run can lose a show to a real error and THEN hit a limit. The pause
    marker is the only durable record of why that show was lost -- the
    per-show handler otherwise just prints to stderr -- so it has to carry
    the failure list, not an empty one."""
    _clock(monkeypatch, sleep_budget=0)

    def _process(pid):
        if pid == "a":
            raise TaskFailed("LLM task 'brief' failed after 3 attempts")
        raise RateLimited("You've hit your session limit", scope="five_hour",
                          resets_at=NOW + timedelta(hours=2))

    ws, seen = _drive(tmp_path, monkeypatch, _process, ["a", "b", "c"],
                      pace=pacing.pace_options(Config(), wait=False))

    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_PAUSED
    assert [f["show"] for f in info.failures] == ["a"]
    assert "brief" in info.failures[0]["error"]
    assert info.outcome == "1 failed"


def test_a_held_show_between_pauses_counts_as_progress(tmp_path, monkeypatch):
    """The no-progress guard sums packaged + held + failures. Drop `held` and
    a run whose only progress was a held show checkpoints prematurely -- the
    same operator-visible harm as dropping a show."""
    _clock(monkeypatch)
    refused = set()

    def _process(pid):
        if pid not in refused:
            refused.add(pid)
            raise RateLimited("You've hit your session limit", scope="five_hour",
                              resets_at=NOW + timedelta(minutes=10))
        return None if pid == "a" else f"{pid}/package"   # a is held, b packages

    ws, seen = _drive(tmp_path, monkeypatch, _process, ["a", "b"],
                      pace=pacing.pace_options(Config()))

    # a refused, slept; a held and b refused, slept AGAIN because the hold was
    # progress; b packaged.
    assert seen == ["a", "a", "b", "b"]
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_COMPLETE
    assert info.outcome == "1 packaged, 1 held"


def test_a_failed_show_between_pauses_counts_as_progress(tmp_path, monkeypatch):
    """Same for the third term. A show that failed is a show the run got
    through; the window was spent on it, so the next pause is not a stall."""
    _clock(monkeypatch)
    refused = set()

    def _process(pid):
        if pid not in refused:
            refused.add(pid)
            raise RateLimited("You've hit your session limit", scope="five_hour",
                              resets_at=NOW + timedelta(minutes=10))
        if pid == "a":
            raise TaskFailed("LLM task 'brief' failed after 3 attempts")
        return f"{pid}/package"

    ws, seen = _drive(tmp_path, monkeypatch, _process, ["a", "b"],
                      pace=pacing.pace_options(Config()))

    assert seen == ["a", "a", "b", "b"]
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_INCOMPLETE          # it lost a show, so not complete
    assert info.outcome == "1 packaged, 1 failed"


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
    # Equality, not containment: `str(limited)` mutated to `repr(limited)`
    # still contains the message, so a substring assertion cannot see it.
    assert marker["pause_reason"] == "You've hit your session limit"


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
# The run-level stages, which all run BEFORE the per-show loop holds its catch
# ---------------------------------------------------------------------------


def test_ratelimited_during_winnow_checkpoints_instead_of_exiting(tmp_path, monkeypatch):
    """Phase 1's stated gap: winnow runs BEFORE the per-show loop, so a limit
    there escaped _execute entirely -- exit 1, no marker, no resume_after.
    _drive returning normally is half the assertion."""
    _clock(monkeypatch)

    def _boom(*a, **k):
        raise RateLimited("You've hit your session limit", scope="five_hour",
                          resets_at=NOW + timedelta(hours=6))

    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config(), wait=False),
                      winnow=_boom)

    assert seen == []                                  # no show was reached
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED
    marker = json.loads(ws.session.read_text())
    assert marker["pause_scope"] == "five_hour"
    assert marker["resume_after"]                      # an instant, not None


def test_run_level_ratelimited_is_caught_before_herdererror(tmp_path, monkeypatch):
    """RateLimited subclasses HerderError. Ordered the other way this becomes
    an ordinary stage failure, so assert the PAUSED marker rather than merely
    that nothing propagated."""
    _clock(monkeypatch)

    def _boom(*a, **k):
        raise RateLimited("You've hit your session limit", scope="five_hour",
                          resets_at=None)

    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config(), wait=False),
                      search=_boom)

    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED


def test_ratelimited_during_discover_checkpoints_too(tmp_path, monkeypatch):
    """The guarded region has to START above the artist-matching branch, not
    below it: run_discover is a run-level LLM stage like the other two, and a
    region beginning at run_search leaves this one escaping. _drive cannot
    reach it -- it hard-codes a query with no soft preferences -- so this one
    drives _execute itself."""
    _clock(monkeypatch)
    ws = RunWorkspace(tmp_path, "r1")

    def _boom(*a, **k):
        raise RateLimited("You've hit your session limit", scope="five_hour",
                          resets_at=NOW + timedelta(hours=2))

    monkeypatch.setattr(cli, "make_providers",
                        lambda config: collections.defaultdict(lambda: None))
    monkeypatch.setattr(cli, "run_discover", _boom)
    monkeypatch.setattr(cli, "run_search", lambda *a, **k: None)
    monkeypatch.setattr(cli, "run_winnow", lambda *a, **k: [])
    monkeypatch.setattr(cli, "make_client", lambda config: None)

    cli._execute(Config(root=tmp_path), None, None, ws,
                 Criteria(query="x", soft_preferences="long jams"), 1,
                 auto=True, human_gate=False,
                 pace=pacing.pace_options(Config(), wait=False))

    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED


def test_a_run_level_pause_records_the_reset_plus_skew_once(tmp_path, monkeypatch):
    """`when` exists for a caller that already holds a skewed instant; a
    RateLimited caller passes nothing, so resume_at applies the skew exactly
    once -- reset + 2m, not + 4m."""
    _clock(monkeypatch)

    def _boom(*a, **k):
        raise RateLimited("You've hit your session limit", scope="five_hour",
                          resets_at=NOW + timedelta(hours=2))

    ws, _ = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                   pace=pacing.pace_options(Config(), wait=False), winnow=_boom)

    marker = json.loads(ws.session.read_text())
    assert marker["resume_after"] == "2026-09-04T10:02:00+00:00"   # reset + 2m
    assert marker["pause_reason"] == "You've hit your session limit"   # not repr
    assert marker["outcome"] is None        # no show ran, so nothing to report
    assert marker["failures"] == []


def test_a_run_level_pause_says_what_a_resume_will_redo(tmp_path, monkeypatch, capsys):
    """The loop's checkpoint reports how many shows are left; this one has no
    show queue to report, so the note is all the operator gets telling them
    the run stopped BEFORE any show and that a resume redoes a whole stage."""
    _clock(monkeypatch)

    def _boom(*a, **k):
        raise RateLimited("You've hit your session limit", scope="five_hour",
                          resets_at=NOW + timedelta(hours=2))

    _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
           pace=pacing.pace_options(Config(), wait=False), winnow=_boom)

    captured = capsys.readouterr()
    assert "session limit" in captured.err                 # why it stopped
    # Names the stages it covers: the operator must not read this as covering
    # `interpret`, which runs outside _execute and is not covered.
    assert "limit hit in discover/search/winnow, before any show ran" in captured.out
    assert "resume re-runs that whole stage" in captured.out
    assert "resume with: llama run resume r1" in captured.out


def test_an_ordinary_stage_failure_is_not_turned_into_a_pause(tmp_path, monkeypatch):
    """The arm is `except RateLimited`, not `except HerderError`. A stage that
    fails for any other reason is a failure, not an exhausted window: pausing
    on it would park the run waiting for a reset that fixes nothing."""
    _clock(monkeypatch, sleep_budget=0)

    def _boom(*a, **k):
        raise HerderError("provider blew up")

    with pytest.raises(HerderError):
        _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
               pace=pacing.pace_options(Config(), wait=False), winnow=_boom)

    assert iter_sessions(tmp_path) == []          # no paused marker


def test_checkpoint_pause_keeps_a_precomputed_instant_verbatim(tmp_path):
    """`when` is for a caller that already holds a skewed instant. Recomputing
    it through resume_at would add reset_skew a second time, so the helper has
    to record exactly what it was handed."""
    ws = RunWorkspace(tmp_path, "r1")
    when = NOW + timedelta(hours=3)

    cli._checkpoint_pause(ws, RateLimited("nearly out", scope="seven_day"),
                          pacing.pace_options(Config()), when=when)

    marker = json.loads(ws.session.read_text())
    assert marker["resume_after"] == when.isoformat()   # no second skew
    assert marker["pause_scope"] == "seven_day"


def test_pacing_disabled_lets_a_run_level_limit_propagate(tmp_path, monkeypatch):
    """--no-pacing keeps the old behaviour here too: the refusal reaches the
    CLI's top-level handler as an ordinary error and no marker is written.
    The show loop's escape hatch records a per-show failure and carries on,
    but at run level there is no next show to carry on to."""
    _clock(monkeypatch, sleep_budget=0)

    def _boom(*a, **k):
        raise RateLimited("You've hit your session limit", scope="five_hour",
                          resets_at=NOW + timedelta(hours=2))

    with pytest.raises(RateLimited):
        _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
               pace=pacing.pace_options(Config(pacing=PacingConfig(enabled=False))),
               winnow=_boom)

    assert iter_sessions(tmp_path) == []          # no marker at all


# ---------------------------------------------------------------------------
# The proactive gate: pausing BEFORE a window is exhausted
# ---------------------------------------------------------------------------


def _reading(five=10, seven=7):
    from herder.usage import Meter, UsageReading
    return UsageReading(five_hour=Meter(five, RESET_5H),
                        seven_day=Meter(seven, RESET_7D),
                        per_model={}, fetched_at=NOW)


def test_preflight_gate_pauses_before_any_stage_runs(tmp_path, monkeypatch):
    """The opening burst is the expensive place to pause -- winnow writes its
    shortlist only on success -- so the gate must fire BEFORE run_search."""
    _clock(monkeypatch)
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: _reading(five=99))
    searched = []

    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config(), wait=False),
                      search=lambda *a, **k: searched.append(1))

    assert searched == []                     # never entered the burst
    assert seen == []
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED


def test_per_show_gate_stops_between_shows(tmp_path, monkeypatch):
    """Reading order: pre-flight, before-a, after-a (the delta), before-b.
    The fourth read is over the ceiling, so 'a' is packaged and 'b' is not."""
    _clock(monkeypatch)
    calls = {"n": 0}

    def _read(*a, **kw):
        calls["n"] += 1
        return _reading(five=5 if calls["n"] <= 3 else 99)

    monkeypatch.setattr(cli, "read_usage", _read)
    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a", "b"],
                      pace=pacing.pace_options(Config(), wait=False))

    assert seen == ["a"]
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED


def test_gate_is_skipped_entirely_on_a_non_claude_cli_backend(tmp_path, monkeypatch):
    """The fake backend has no window; reading a meter for it would be both
    meaningless and non-deterministic in the offline suite."""
    _clock(monkeypatch)
    monkeypatch.setattr(cli, "read_usage",
                        lambda *a, **kw: pytest.fail("meter read on a fake backend"))
    cfg = Config(root=tmp_path, llm={"default": LLMTaskConfig(backend="fake")})

    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config()), config=cfg)

    assert seen == ["a"]
    # Nor is a boundary recorded: with no window to read there is nothing to
    # fold, and writing anyway leaves a pacing-state.json (plus a lock acquire
    # per show) in the workspace of a user who never paced.
    assert not (tmp_path / "pacing-state.json").exists()


def test_a_preflight_pause_exits_zero_like_every_other_pause(tmp_path, monkeypatch):
    """R20's resolution: a limit before any show ran is NOT a distinct failure
    signal. _execute returns normally; the session lands on the attention list."""
    _clock(monkeypatch)
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: _reading(five=99))
    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config(), wait=False))
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED


def test_a_proactive_pause_waits_for_the_meters_reset_not_the_unknown_default(
        tmp_path, monkeypatch):
    """The show loop does NOT route through _checkpoint_pause: it computes its
    own instant. `resume_at` reads `resets_at`, which a PauseUntil has not
    got, so routing one through it silently substitutes the one-hour
    unknown-reset default for the reset the meter actually named -- a green
    suite with the feature quietly broken.

    A PauseUntil already carries that instant WITH reset_skew folded in, so
    the fix is to keep it verbatim, not to give PauseUntil a `resets_at`
    (which would let resume_at apply the skew a second time).
    """
    _clock(monkeypatch, sleep_budget=0)
    calls = {"n": 0}

    def _read(*a, **kw):
        calls["n"] += 1
        return _reading(five=5 if calls["n"] == 1 else 99)   # pre-flight ok, show not

    monkeypatch.setattr(cli, "read_usage", _read)
    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config(), wait=False))

    assert seen == []                          # gated before the show ran
    marker = json.loads(ws.session.read_text())
    # The meter's own reset (NOW + 2h) plus the 2m skew, exactly once. The
    # unknown-reset default would put this at 09:00, an hour too early.
    assert marker["resume_after"] == "2026-09-04T10:02:00+00:00"
    assert marker["pause_scope"] == "five_hour"
    # Equality, not containment: it also pins PauseUntil.__str__ down to the
    # reason, since the dataclass repr contains the reason as a substring.
    assert marker["pause_reason"] == "5h window at 99%"


def test_a_preflight_pause_records_the_meters_reset_and_reason(
        tmp_path, monkeypatch, capsys):
    """The other pause site, which DOES route through _checkpoint_pause: it
    holds an already-skewed instant, so it has to hand it over as `when` --
    letting resume_at recompute would fall back to the unknown-reset default
    here too."""
    _clock(monkeypatch, sleep_budget=0)
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: _reading(five=99))

    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config(), wait=False))

    marker = json.loads(ws.session.read_text())
    assert marker["resume_after"] == "2026-09-04T10:02:00+00:00"   # reset + 2m
    assert marker["pause_reason"] == "5h window at 99%"
    assert marker["outcome"] is None and marker["failures"] == []
    captured = capsys.readouterr()
    assert "paused: 5h window at 99%" in captured.err
    assert "nothing has run yet" in captured.out


def test_a_proactive_pause_leaves_the_gated_show_for_the_resume(
        tmp_path, monkeypatch, capsys):
    """Same queue arithmetic as the reactive pause: the show the gate stopped
    IN FRONT OF has not run, so it belongs to the shows left. `pending[idx +
    1:]` drops it and the resume never comes back for it."""
    _clock(monkeypatch)
    calls = {"n": 0}

    def _read(*a, **kw):
        calls["n"] += 1
        return _reading(five=5 if calls["n"] <= 3 else 99)

    monkeypatch.setattr(cli, "read_usage", _read)
    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg",
                      ["a", "b", "c"],
                      pace=pacing.pace_options(Config(), wait=False))

    assert seen == ["a"]
    assert "2 shows left" in capsys.readouterr().out       # b, the gated one, and c


def test_the_learned_cost_folds_each_shows_own_before_and_after(tmp_path, monkeypatch):
    """The boundary that teaches the gate is `after this show` minus `before
    this show`. The pre-flight reading and the next show's own `before` sit
    one read either side of it, and folding either in measures a different
    interval than the show it is attributed to."""
    _clock(monkeypatch, sleep_budget=0)
    # pre-flight, before-a, after-a, before-b, after-b
    reads = [1, 2, 10, 12, 30]

    def _read(*a, **kw):
        assert reads, "more meter reads than the boundary protocol calls for"
        return _reading(five=reads.pop(0))

    monkeypatch.setattr(cli, "read_usage", _read)
    _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a", "b"],
           pace=pacing.pace_options(Config()))

    assert reads == []                       # exactly five, in that order
    state = json.loads((tmp_path / "pacing-state.json").read_text())
    assert state["samples"] == 2
    # a costs 8 (10 - 2), b costs 18 (30 - 12); EWMA at alpha 0.4 -> 12.0.
    assert state["per_show_delta"] == pytest.approx(12.0)


def test_the_gate_runs_before_the_show_lock_is_taken(tmp_path, monkeypatch):
    """Placed inside the lock instead, a show another run holds slips past the
    gate entirely: the non-blocking acquire raises first, the show goes to the
    deferred pass, and it is processed on an exhausted window."""
    _clock(monkeypatch, sleep_budget=0)
    real_file_lock = cli.file_lock

    def _file_lock(path, *, blocking=True):
        if not blocking:
            raise Locked(path)                 # another run holds every show
        return real_file_lock(path, blocking=blocking)

    monkeypatch.setattr(cli, "file_lock", _file_lock)
    calls = {"n": 0}

    def _read(*a, **kw):
        calls["n"] += 1
        return _reading(five=5 if calls["n"] == 1 else 99)

    monkeypatch.setattr(cli, "read_usage", _read)
    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config(), wait=False))

    assert seen == []
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED


def test_the_learned_cost_is_what_stops_the_next_show(tmp_path, monkeypatch):
    """The gate is on the PROJECTION, so the estimate a boundary produces has
    to reach the next decision. A meter comfortably under the ceiling still
    pauses when one more show of the measured size would carry it over --
    and a `record` whose result is dropped on the floor never pauses below
    the ceiling at all."""
    _clock(monkeypatch, sleep_budget=0)
    reads = [50, 50, 62, 85]      # pre-flight, before-a, after-a, before-b

    def _read(*a, **kw):
        assert reads, "the projection did not stop the second show"
        return _reading(five=reads.pop(0))

    monkeypatch.setattr(cli, "read_usage", _read)
    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a", "b"],
                      pace=pacing.pace_options(Config(), wait=False))

    assert seen == ["a"]
    marker = json.loads(ws.session.read_text())
    # 85 is under the 90 ceiling; 85 + the 12 that show `a` cost is not.
    assert marker["pause_reason"] == "5h window at 85%, est 12.0%/show"


def test_a_previous_runs_estimate_reaches_the_preflight_gate(tmp_path, monkeypatch):
    """The cross-run payoff, and the only test that reads a `pacing-state.json`
    this run did not write: 85% is under the 90 ceiling, but a show a PREVIOUS
    run measured at 12% is not, so the burst never starts.

    Without it the pre-flight gate can be disconnected from everything the
    persisted estimate exists for -- `Progress(None)`, or never reading the
    file -- and the suite stays green.
    """
    _clock(monkeypatch, sleep_budget=0)
    (tmp_path / "pacing-state.json").write_text(
        json.dumps({"per_show_delta": 12.0, "samples": 2}))
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: _reading(five=85))
    searched = []

    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config(), wait=False),
                      search=lambda *a, **k: searched.append(1))

    assert searched == [] and seen == []
    assert json.loads(ws.session.read_text())["pause_reason"] == \
        "5h window at 85%, est 12.0%/show"


def test_a_rate_limited_show_is_not_a_boundary(tmp_path, monkeypatch):
    """A refused show did PARTIAL work, so the meter moved by less than a show
    costs. Folding it in is the same under-estimate a deferred show would be --
    hence the record sitting below the `if limited` break, not above it.

    Every other reactive test runs with the meter stubbed to None, where
    `record` is a no-op and the ordering cannot matter; this one supplies a
    reading so it can.
    """
    _clock(monkeypatch, sleep_budget=0)
    reads = [10, 10, 14]          # pre-flight, before-a, and one spare

    def _read(*a, **kw):
        return _reading(five=reads.pop(0) if len(reads) > 1 else reads[0])

    monkeypatch.setattr(cli, "read_usage", _read)

    def _process(pid):
        raise RateLimited("You've hit your session limit", scope="five_hour",
                          resets_at=NOW + timedelta(hours=2))

    _drive(tmp_path, monkeypatch, _process, ["a"],
           pace=pacing.pace_options(Config(), wait=False))

    assert pacing_state.read_state(tmp_path).samples == 0


def test_a_deferred_show_is_not_a_boundary(tmp_path, monkeypatch):
    """A show another run holds the lock on never ran here, so the two
    readings around it bracket no work at all. Folding that in teaches the
    gate a zero-cost show, and an UNDER-estimate is exactly what lets a run
    walk into the wall."""
    _clock(monkeypatch, sleep_budget=0)
    real_file_lock = cli.file_lock

    def _file_lock(path, *, blocking=True):
        if not blocking and path.parent.name.endswith("a"):
            raise Locked(path)                 # another run holds `a`
        return real_file_lock(path, blocking=blocking)

    monkeypatch.setattr(cli, "file_lock", _file_lock)
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: _reading(five=5))
    _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
           pace=pacing.pace_options(Config()))

    # read_state, not the raw file: "no boundary" is equally well expressed by
    # never writing one, and the point is the estimate, not the artifact.
    state = pacing_state.read_state(tmp_path)
    assert state.samples == 0                # the deferred pass is not measured
    assert state.per_show_delta is None


def test_no_pacing_never_reads_the_meter(tmp_path, monkeypatch):
    """--no-pacing opts out of the whole feature. `decide` would return
    Proceed on any reading, so a meter read under it is a subprocess per show
    spent on an answer nothing consults."""
    _clock(monkeypatch, sleep_budget=0)
    monkeypatch.setattr(cli, "read_usage",
                        lambda *a, **kw: pytest.fail("meter read with pacing off"))

    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
                      pace=pacing.pace_options(Config(pacing=PacingConfig(enabled=False))))

    assert seen == ["a"]
    assert not (tmp_path / "pacing-state.json").exists()   # nothing to fold


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


# ---------------------------------------------------------------------------
# The run-start forecast line
# ---------------------------------------------------------------------------


def test_the_run_start_line_names_the_shortfall_without_shrinking_the_run(
        tmp_path, monkeypatch, capsys):
    """25 points of headroom at 10%/show is two shows of a three-show run.

    The consequence is printed, not acted on: `count` still reaches
    choose_entries intact, because it feeds the artist and year caps -- a
    run trimmed to what fits would pick DIFFERENT shows, not merely fewer,
    and the third one is not lost, it waits for the reset.
    """
    _clock(monkeypatch)
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: _reading(five=65))
    (tmp_path / "pacing-state.json").write_text(
        json.dumps({"per_show_delta": 10.0, "samples": 3}))
    counts = []

    ws, seen = _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg",
                      ["a", "b", "c"], pace=pacing.pace_options(Config()),
                      choose=lambda entries, count, *a, **k: (
                          counts.append(count) or entries))

    out = capsys.readouterr().out
    assert "pacing: 5h 65%" in out
    assert "est 10.0%/show" in out
    assert "~2 fit before" in out
    assert "the remaining 1 pause until the reset" in out
    assert counts == [3]                  # not trimmed to the two that fit
    assert seen == ["a", "b", "c"]


def test_the_run_start_line_forecasts_nothing_before_a_boundary_is_observed(
        tmp_path, monkeypatch, capsys):
    """No estimate is not zero. With nothing learned yet the line reports the
    meters and stops -- a forecast would be a number invented from nothing,
    and the shortfall clause would tell a run to expect a pause the policy
    has no basis to predict."""
    _clock(monkeypatch)
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: _reading(five=65))
    assert not (tmp_path / "pacing-state.json").exists()

    _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a", "b", "c"],
           pace=pacing.pace_options(Config()))

    out = capsys.readouterr().out
    assert "pacing: 5h 65%" in out
    assert "fit before" not in out
    assert "the remaining" not in out


def test_a_failed_read_on_a_paced_run_says_the_backstop_is_still_live(
        tmp_path, monkeypatch, capsys):
    """The ONE case the run-start line is for: pacing on, claude_cli backend,
    and the meter would not read. The proactive gate is blind, the reactive
    one is not, and that sentence is true only here."""
    _clock(monkeypatch)
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: None)

    _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
           pace=pacing.pace_options(Config()))

    # Prefixed like every other pacing line, and the claim itself unchanged.
    assert "pacing: usage read unavailable — pacing on limit errors only" \
        in capsys.readouterr().out


def test_no_pacing_prints_no_run_start_line_at_all(tmp_path, monkeypatch, capsys):
    """--no-pacing must print nothing, not "pacing on limit errors only".

    With pacing off the RateLimited handler re-raises and a limit FAILS the
    show, so that sentence promises a safety net at the exact moment the
    operator removed it. Silence is also the point of the flag.
    """
    _clock(monkeypatch)
    monkeypatch.setattr(cli, "read_usage",
                        lambda *a, **kw: pytest.fail("meter read under --no-pacing"))

    _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
           pace=pacing.pace_options(Config(), no_pacing=True))

    out = capsys.readouterr().out
    assert "pacing" not in out
    assert "unavailable" not in out


def test_a_backend_with_no_window_prints_no_run_start_line_at_all(
        tmp_path, monkeypatch, capsys):
    """fake/openrouter having no usage window is the steady state, not a
    degradation. Warning about it once per run would train the operator to
    ignore the line that matters."""
    _clock(monkeypatch)
    monkeypatch.setattr(cli, "read_usage",
                        lambda *a, **kw: pytest.fail("meter read on a fake backend"))
    cfg = Config(root=tmp_path, llm={"default": LLMTaskConfig(backend="fake")})

    _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a"],
           pace=pacing.pace_options(Config()), config=cfg)

    out = capsys.readouterr().out
    assert "pacing" not in out
    assert "unavailable" not in out


def test_the_line_survives_a_meter_that_named_no_reset():
    """`resets_at` is None whenever the reset clause did not parse, which
    `herder.limits.parse_reset` returns for an unrecognised clause, an
    unknown zone, an out-of-range minute and an out-of-bound target --
    and `pacing._pause` already branches on it. Without the guard,
    `.astimezone()` on None raises and takes down `llama get` at run start
    and `llama pacing` outright.
    """
    from herder.usage import Meter, UsageReading
    reading = UsageReading(five_hour=Meter(65, None),
                           seven_day=Meter(7, NOW + timedelta(days=3)),
                           per_model={}, fetched_at=NOW)

    line = cli._pacing_line(reading, pacing_state.PacingState(4.0, 3),
                            pacing.pace_options(Config()))

    assert line == "pacing: 5h 65% · weekly 7% · est 4.0%/show"
    assert "fit before" not in line          # nothing to render it against


@pytest.mark.parametrize("delta, pids, fits", [
    (12.5, ["a", "b"], 2),        # exactly what fits: the boundary `<` guards
    (5.0, ["a", "b"], 5),         # room to spare
])
def test_the_shortfall_clause_stays_quiet_unless_the_run_overruns(
        tmp_path, monkeypatch, capsys, delta, pids, fits):
    """`fits < count`, not `<=`: at equality the run fits exactly, and
    `<=` would print the operator-facing "the remaining 0 pause until the
    reset" -- a pause announced for no shows."""
    _clock(monkeypatch)
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: _reading(five=65))
    (tmp_path / "pacing-state.json").write_text(
        json.dumps({"per_show_delta": delta, "samples": 3}))

    _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", pids,
           pace=pacing.pace_options(Config()))

    out = capsys.readouterr().out
    assert f"~{fits} fit before" in out       # the forecast really is that number
    assert "the remaining" not in out


def test_the_line_names_the_weekly_window_and_dates_its_reset():
    """A weekly reset days out rendered as a bare `07:00` reads as "this
    morning" -- worse than a wrong count, because it looks like a bug rather
    than a weekly ceiling. So the weekly form says which window it is and
    carries the date; the 5-hour form, always within five hours, does not."""
    line = cli._pacing_line(_reading(five=20, seven=84),
                            pacing_state.PacingState(4.0, 5),
                            pacing.pace_options(Config()))

    assert "~1 fit before the weekly reset, " in line     # 1, not (90-20)//4
    when = RESET_7D.astimezone()                          # rendered in local time
    assert f"{when:%b}" in line and str(when.day) in line  # the date is carried


def test_the_line_leaves_a_session_reset_as_a_bare_clock_time():
    line = cli._pacing_line(_reading(five=65, seven=7),
                            pacing_state.PacingState(4.0, 5),
                            pacing.pace_options(Config()))

    assert f"~6 fit before {RESET_5H.astimezone():%H:%M}" in line
    assert "weekly reset" not in line                     # nothing to explain


def test_the_missing_reset_guard_follows_the_binding_window():
    """Round 1 pinned this for a binding 5-hour meter. The guard has to move
    with the forecast, or a weekly meter with no reset -- which is what
    /usage prints today for `Current week (Fable): 0% used` -- reaches
    `.astimezone()` on None and takes the command down."""
    from herder.usage import Meter, UsageReading
    reading = UsageReading(five_hour=Meter(20, RESET_5H),
                           seven_day=Meter(84, None),     # binds, names no reset
                           per_model={}, fetched_at=NOW)

    line = cli._pacing_line(reading, pacing_state.PacingState(4.0, 5),
                            pacing.pace_options(Config()))

    assert line == "pacing: 5h 20% · weekly 84% · est 4.0%/show"
    assert "fit before" not in line       # and emphatically not the 5h instant


def test_the_shortfall_clause_names_the_weekly_reset_when_the_weekly_binds(
        tmp_path, monkeypatch, capsys):
    """After "~1 fit before the weekly reset", a bare "the reset" in the
    same sentence would point at the sooner window the run is not waiting
    for."""
    _clock(monkeypatch)
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: _reading(five=20, seven=84))
    (tmp_path / "pacing-state.json").write_text(
        json.dumps({"per_show_delta": 4.0, "samples": 5}))

    _drive(tmp_path, monkeypatch, lambda pid: f"{pid}/pkg", ["a", "b", "c"],
           pace=pacing.pace_options(Config()))

    out = capsys.readouterr().out
    assert "the remaining 2 pause until the weekly reset" in out
