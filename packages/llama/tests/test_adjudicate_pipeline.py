"""The adjudicator as a pipeline step (spec "Pipeline step"): the hooks in `get`, `run
approve`, `run resume` (all via `_execute`) and `redo` (single and batch), the tri-state
`--adjudicate/--no-adjudicate`, the pause semantics and the boundary that includes the
adjudication. `runner.adjudicate_show` is a spy except where the real one is the point
(the apply's own redo never adjudicates)."""
from __future__ import annotations

import collections
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer.testing as typer_testing
from herder import FakeProvider
from herder.limits import RateLimited

import llama.adjudicator.runner as runner
import llama.cli as cli
from conftest import cli_invoke
from llama import pacing
from llama.config import Config
from llama.locks import Locked, file_lock
from llama.models import Criteria, Show
from llama.sessions import STATE_COMPLETE, STATE_PAUSED, iter_sessions
from llama.util import slugify
from llama.workspace import RunWorkspace, ShowWorkspace, read_model, write_artifact
from test_catalog import build
from test_cli_commands import _approved_run
from test_pace_loop import NOW, _clock, _entry, _reading
from test_pipeline import FakeIA, GOOD_BRIEFING_JSON, JB_OFF, fake_providers

PID = "GratefulDead/1973-06-10"
SLUG = "gratefuldead-1973-06-10"


# ---------------------------------------------------------------- spies and rigs

class Spy:
    """Stands in for `runner.adjudicate_show`. Each effect is consumed per call: an
    exception is raised, a callable is called with (ctx, entry) and its result returned,
    None returns a `held with proposal` outcome."""

    def __init__(self, *effects):
        self.calls: list[str] = []
        self.effects = list(effects)

    def __call__(self, ctx, entry, *, dry_run=False, force=False, **kw):
        self.calls.append(entry.slug)
        eff = self.effects.pop(0) if self.effects else None
        if isinstance(eff, BaseException):
            raise eff
        if callable(eff):
            return eff(ctx, entry)
        return runner.ShowOutcome(entry.slug, runner.PROPOSAL)


def _spy(monkeypatch, *effects) -> Spy:
    spy = Spy(*effects)
    monkeypatch.setattr(runner, "adjudicate_show", spy)
    return spy


def _limited(minutes=10):
    from datetime import timedelta
    return RateLimited("You've hit your session limit", scope="five_hour",
                       resets_at=NOW + timedelta(minutes=minutes))


def _held_json(root: Path, pid: str) -> ShowWorkspace:
    sws = ShowWorkspace(root / "shows" / slugify(pid))
    write_artifact(sws.show, Show(performance_id=pid, identifier="x", artist="C",
                                  date="1973-06-10", needs_review=True,
                                  review_flags=["unresolved track titles"]))
    return sws


def _drive(tmp_path, monkeypatch, pids, *, pace, adjudicate=True, llm=False,
           packaged=()) -> list[str]:
    """`_execute` over `pids` with a scripted process_show: every show ends held (a held
    show.json written) unless named in `packaged`. Returns the pids process_show saw."""
    config = Config(root=tmp_path)
    ws = RunWorkspace(tmp_path, "r1")
    entries = [_entry(p, i + 1) for i, p in enumerate(pids)]
    seen: list[str] = []

    def _process_show(_ws, _ia, _ledger, entry, providers, *a, **k):
        pid = entry.candidate.performance_id
        seen.append(pid)
        if llm:
            providers["brief"][0].complete("x")
        if pid in packaged:
            return f"{pid}/package"
        _held_json(tmp_path, pid)
        return None

    monkeypatch.setattr(cli, "make_providers", lambda config: collections.defaultdict(
        lambda: [FakeProvider(completes=["x"] * 50)]))
    monkeypatch.setattr(cli, "run_search", lambda *a, **k: None)
    monkeypatch.setattr(cli, "run_winnow", lambda *a, **k: entries)
    monkeypatch.setattr(cli, "choose_entries", lambda entries, *a, **k: entries)
    monkeypatch.setattr(cli, "make_client", lambda config: None)
    monkeypatch.setattr(cli, "process_show", _process_show)
    monkeypatch.setattr(cli, "_resolve_show", lambda config, ledger, name: SimpleNamespace(
        slug=name, ws=ShowWorkspace(config.root / "shows" / name)))
    cli._execute(config, None, None, ws, Criteria(query="x"), len(pids), auto=True,
                 human_gate=False, pace=pace, adjudicate=adjudicate)
    return seen


def _get_held(tmp_path, monkeypatch, *flags, config_body=""):
    """A real `get` whose one show ends held (the briefing guard holds it)."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path}"\n{config_body}')
    providers = fake_providers(None)
    bad = json.dumps({**json.loads(GOOD_BRIEFING_JSON),
                      "mentioned_songs": ["Fake Invented Song"]})
    providers["brief"] = FakeProvider(completes=[bad, bad])
    providers["adjudicate"] = FakeProvider()
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    return cli_invoke(cfg, "get", "GD 1973", "--auto", "--name", "r", *flags)


def _captured(monkeypatch) -> list[dict]:
    seen: list[dict] = []
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: seen.append(k))
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: None)
    return seen


def _config_hook(monkeypatch):
    monkeypatch.setattr(cli, "_adjudicate_enabled", runner.hook_enabled)


def _cfg(tmp_path, body="") -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path}"\n{body}')
    return cfg


def _seeded_run(tmp_path, name="r1"):
    ws = RunWorkspace(tmp_path, name)
    write_artifact(ws.criteria, Criteria(query="q"))
    return ws


# ---------------------------------------------------------------- get / _execute

def test_get_adjudicates_a_show_that_ends_held_and_counts_it_in_the_boundary(
        tmp_path, monkeypatch, capsys):
    _clock(monkeypatch)
    recorded = []
    monkeypatch.setattr(cli.pacing_state, "record",
                        lambda root, before, after: recorded.append((before, after))
                        or cli.pacing_state.PacingState())
    monkeypatch.setattr(cli, "_meter", lambda config, pace: _reading())

    def calls_the_llm(ctx, entry):
        ctx.provider[0].complete("judge")          # through the counted providers
        return runner.ShowOutcome(entry.slug, runner.PROPOSAL)

    spy = _spy(monkeypatch, calls_the_llm)
    # process_show itself makes no LLM call: only the adjudication can make this a sample
    seen = _drive(tmp_path, monkeypatch, ["C/a"], pace=pacing.pace_options(Config()))
    assert seen == ["C/a"] and spy.calls == [slugify("C/a")]
    assert len(recorded) == 1                       # recorded AFTER the adjudication
    assert "adjudicated C/a: held with proposal" in capsys.readouterr().out
    assert iter_sessions(tmp_path)[0].outcome == "1 held"


def test_a_packaged_show_is_never_adjudicated(tmp_path, monkeypatch):
    _clock(monkeypatch)
    spy = _spy(monkeypatch)
    _drive(tmp_path, monkeypatch, ["C/a"], pace=pacing.pace_options(Config()),
           packaged={"C/a"})
    assert spy.calls == []


def test_a_held_show_with_a_current_record_is_not_adjudicated(tmp_path, monkeypatch):
    _clock(monkeypatch)
    spy = _spy(monkeypatch)
    import llama.adjudicator.record as record
    monkeypatch.setattr(record, "is_current", lambda ws, **k: True)
    _drive(tmp_path, monkeypatch, ["C/a"], pace=pacing.pace_options(Config()))
    assert spy.calls == []


@pytest.mark.parametrize("flags, body, called", [
    ((), "", True),                                        # config default: enabled
    (("--no-adjudicate",), "", False),
    ((), "\n[adjudicate]\nenabled = false\n", False),
    (("--adjudicate",), "\n[adjudicate]\nenabled = false\n", True),
])
def test_get_no_adjudicate_flag_and_config_false_skip(tmp_path, monkeypatch, flags, body,
                                                       called):
    _config_hook(monkeypatch)
    spy = _spy(monkeypatch)
    r = _get_held(tmp_path, monkeypatch, *flags, config_body=body)
    assert r.exit_code == 0, r.output
    assert "needs-review, skipped" in r.output
    assert spy.calls == ([SLUG] if called else [])
    assert (f"adjudicated {PID}: held with proposal" in r.output) == called


def test_config_default_enables_hook(monkeypatch):
    # The suite's own default is off (conftest), so no held-show test adjudicates by accident.
    assert cli._adjudicate_enabled(Config(), None) is False
    assert cli._adjudicate_enabled(Config(), True) is True
    monkeypatch.setattr(cli, "_adjudicate_enabled", runner.hook_enabled)
    assert cli._adjudicate_enabled(Config(), None) is True
    off = Config(adjudicate={"enabled": False})
    assert cli._adjudicate_enabled(off, None) is False
    assert cli._adjudicate_enabled(off, True) is True
    assert cli._adjudicate_enabled(Config(), False) is False


def test_adjudication_runs_after_the_show_lock_is_released(tmp_path, monkeypatch):
    _clock(monkeypatch)
    free = []

    def probe(ctx, entry):
        try:
            with file_lock(entry.ws.lock, blocking=False):
                free.append(True)
        except Locked:
            free.append(False)
        return runner.ShowOutcome(entry.slug, runner.PROPOSAL)

    _spy(monkeypatch, probe)
    _drive(tmp_path, monkeypatch, ["C/a"], pace=pacing.pace_options(Config()))
    assert free == [True]


def test_the_deferred_pass_adjudicates_after_its_lock_too(tmp_path, monkeypatch):
    _clock(monkeypatch)
    real = cli.file_lock
    monkeypatch.setattr(cli, "file_lock", lambda path, *, blocking=True: (
        (_ for _ in ()).throw(Locked(path)) if not blocking else real(path, blocking=True)))
    free = []

    def probe(ctx, entry):
        try:
            with real(entry.ws.lock, blocking=False):
                free.append(True)
        except Locked:
            free.append(False)
        return runner.ShowOutcome(entry.slug, runner.PROPOSAL)

    _spy(monkeypatch, probe)
    seen = _drive(tmp_path, monkeypatch, ["C/a"], pace=pacing.pace_options(Config()))
    assert seen == ["C/a"] and free == [True]


def test_ratelimited_in_adjudication_pauses_run_and_resume_adjudicates_it(
        tmp_path, monkeypatch, capsys):
    _clock(monkeypatch)
    spy = _spy(monkeypatch, _limited(), None, None)
    seen = _drive(tmp_path, monkeypatch, ["C/a", "C/b"], pace=pacing.pace_options(Config()))
    # a: processed once, judged twice (refused, then after the nap); b after it
    assert seen == ["C/a", "C/b"]
    assert spy.calls == [slugify("C/a"), slugify("C/a"), slugify("C/b")]
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_COMPLETE and info.outcome == "2 held"
    assert "paused after 1 shows" in capsys.readouterr().out


def test_a_checkpointed_adjudication_pause_resumes_through_the_run(
        tmp_path, monkeypatch, capsys):
    _clock(monkeypatch)
    spy = _spy(monkeypatch, _limited(minutes=120))
    pace = pacing.pace_options(Config(), max_wait="1h")
    seen = _drive(tmp_path, monkeypatch, ["C/a", "C/b"], pace=pace)
    assert seen == ["C/a"] and spy.calls == [slugify("C/a")]
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_PAUSED and info.failures == []
    assert "2 shows left" in capsys.readouterr().out       # a's judgement plus b
    # the resume re-runs process_show (stages skip) and then adjudicates
    seen = _drive(tmp_path, monkeypatch, ["C/a", "C/b"], pace=pace)
    assert seen == ["C/a", "C/b"]
    assert spy.calls == [slugify("C/a"), slugify("C/a"), slugify("C/b")]
    assert iter_sessions(tmp_path)[0].state == STATE_COMPLETE


def test_an_adjudication_pause_with_a_failed_show_exits_1(tmp_path, monkeypatch):
    import typer
    _clock(monkeypatch)
    _spy(monkeypatch, _limited(minutes=120))
    pace = pacing.pace_options(Config(), max_wait="1h")

    def process_show(_ws, _ia, _ledger, entry, providers, *a, **k):
        from llama.errors import LlamaError
        if entry.candidate.performance_id == "C/a":
            raise LlamaError("boom")
        _held_json(tmp_path, entry.candidate.performance_id)

    with pytest.raises(typer.Exit) as exc:
        _drive_with(tmp_path, monkeypatch, ["C/a", "C/b", "C/c"], pace, process_show)
    assert exc.value.exit_code == 1
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED   # the checkpoint stands
    assert not cli._is_crash(exc.value)          # a sweep reads it as paused, not crashed


def _drive_with(tmp_path, monkeypatch, pids, pace, process_show, resolve=None):
    config = Config(root=tmp_path)
    ws = RunWorkspace(tmp_path, "r1")
    entries = [_entry(p, i + 1) for i, p in enumerate(pids)]
    monkeypatch.setattr(cli, "make_providers", lambda config: collections.defaultdict(
        lambda: [FakeProvider(completes=["x"] * 50)]))
    monkeypatch.setattr(cli, "run_search", lambda *a, **k: None)
    monkeypatch.setattr(cli, "run_winnow", lambda *a, **k: entries)
    monkeypatch.setattr(cli, "choose_entries", lambda entries, *a, **k: entries)
    monkeypatch.setattr(cli, "make_client", lambda config: None)
    monkeypatch.setattr(cli, "process_show", process_show)
    monkeypatch.setattr(cli, "_resolve_show", resolve or (
        lambda config, ledger, name: SimpleNamespace(
            slug=name, ws=ShowWorkspace(config.root / "shows" / name))))
    cli._execute(config, None, None, ws, Criteria(query="x"), len(pids), auto=True,
                 human_gate=False, pace=pace, adjudicate=True)


def test_pacing_pause_before_adjudication_puts_show_on_adjudication_pending(
        tmp_path, monkeypatch):
    _clock(monkeypatch, sleep_budget=20)
    n = {"reads": 0}

    def meter(config, pace):
        n["reads"] += 1
        # 1 pre-flight, 2 before a, 3 a's adjudication gate: over the ceiling
        return _reading(five=99 if n["reads"] == 3 else 10)

    monkeypatch.setattr(cli, "_meter", meter)
    spy = _spy(monkeypatch)
    seen = _drive(tmp_path, monkeypatch, ["C/a", "C/b"], pace=pacing.pace_options(Config()))
    assert seen == ["C/a", "C/b"]                   # a never re-processed
    assert spy.calls == [slugify("C/a"), slugify("C/b")]   # the gate stopped a's first call
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_COMPLETE and info.outcome == "2 held"


def test_a_gate_pause_before_adjudication_checkpoints_without_judging(tmp_path, monkeypatch):
    _clock(monkeypatch)
    n = {"reads": 0}

    def meter(config, pace):
        n["reads"] += 1
        return _reading(five=99 if n["reads"] == 3 else 10)

    monkeypatch.setattr(cli, "_meter", meter)
    spy = _spy(monkeypatch)
    seen = _drive(tmp_path, monkeypatch, ["C/a"], pace=pacing.pace_options(Config(), wait=False))
    assert seen == ["C/a"] and spy.calls == []
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED


def test_ratelimited_in_adjudication_under_no_pacing_counts_held_unjudged(
        tmp_path, monkeypatch, capsys):
    _clock(monkeypatch)
    _spy(monkeypatch, _limited())
    seen = _drive(tmp_path, monkeypatch, ["C/a"],
                  pace=pacing.pace_options(Config(), no_pacing=True))
    assert seen == ["C/a"]
    assert "adjudicated C/a: unjudged" in capsys.readouterr().out
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_COMPLETE and info.outcome == "1 held" and info.failures == []


def test_adjudication_failure_never_touches_committed_result(tmp_path, monkeypatch):
    _config_hook(monkeypatch)
    spy = _spy(monkeypatch, OSError("disk on fire"))
    r = _get_held(tmp_path, monkeypatch)
    assert r.exit_code == 0, r.output
    assert spy.calls == [SLUG]
    assert f"adjudicated {PID}: failed (OSError: disk on fire)" in r.output
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_COMPLETE and info.outcome == "1 held" and info.failures == []
    assert read_model(tmp_path / "shows" / SLUG / "show.json", Show).needs_review


def test_a_resolve_failure_is_an_outcome_line_not_a_crash(tmp_path, monkeypatch, capsys):
    from llama.errors import LlamaError
    _clock(monkeypatch)
    spy = _spy(monkeypatch)
    pace = pacing.pace_options(Config())

    def process_show(_ws, _ia, _ledger, entry, providers, *a, **k):
        _held_json(tmp_path, entry.candidate.performance_id)

    def boom(config, ledger, name):
        raise LlamaError("no show matches")

    _drive_with(tmp_path, monkeypatch, ["C/a"], pace, process_show, resolve=boom)
    assert "adjudicated C/a: failed (LlamaError: no show matches)" in capsys.readouterr().out
    assert spy.calls == []
    assert iter_sessions(tmp_path)[0].state == STATE_COMPLETE


# ---------------------------------------------------------------- flag plumbing

def test_run_resume_flag_passes_through_and_all_sweep_too(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _seeded_run(tmp_path)
    seen = _captured(monkeypatch)
    for flags, want in ((("--adjudicate",), True), (("--no-adjudicate",), False),
                        ((), False)):                      # conftest: no flag means off
        seen.clear()
        r = cli_invoke(cfg, "run", "resume", "r1", *flags)
        assert r.exit_code == 0, r.output
        assert seen[0]["adjudicate"] is want, flags
    monkeypatch.setattr(cli, "attention_sessions", lambda root: [SimpleNamespace(
        id="r1", updated_at="2026-01-01T00:00:00+00:00")])
    monkeypatch.setattr(cli, "sweep_verdict", lambda info, path, now: None)
    for flags, want in ((("--adjudicate",), True), (("--no-adjudicate",), False)):
        seen.clear()
        cli_invoke(cfg, "run", "resume", "--all", *flags)
        assert seen and seen[0]["adjudicate"] is want, flags


def test_run_resume_default_comes_from_the_config(tmp_path, monkeypatch):
    _config_hook(monkeypatch)
    _seeded_run(tmp_path)
    seen = _captured(monkeypatch)
    assert cli_invoke(_cfg(tmp_path), "run", "resume", "r1").exit_code == 0
    assert seen[0]["adjudicate"] is True


@pytest.mark.parametrize("body, want", [("", True),
                                        ("\n[adjudicate]\nenabled = false\n", False)])
def test_run_approve_uses_config_value(tmp_path, monkeypatch, body, want):
    _config_hook(monkeypatch)
    cfg, ws = _approved_run(tmp_path)
    Path(cfg).write_text(Path(cfg).read_text() + body)
    seen = _captured(monkeypatch)
    r = cli_invoke(cfg, "run", "approve", "r1", input="1\ny\n")
    assert r.exit_code == 0, r.output
    assert seen[0]["adjudicate"] is want


def test_redo_run_level_passes_redo_flag(tmp_path, monkeypatch):
    _config_hook(monkeypatch)
    cfg = _cfg(tmp_path)
    _seeded_run(tmp_path)
    seen = _captured(monkeypatch)
    r = cli_invoke(cfg, "redo", "--run", "r1", "--from", "winnow", "--no-adjudicate")
    assert r.exit_code == 0, r.output
    assert seen[0]["adjudicate"] is False
    seen.clear()
    assert cli_invoke(cfg, "redo", "--run", "r1", "--from", "winnow").exit_code == 0
    assert seen[0]["adjudicate"] is True


def test_get_passes_the_flag_in_both_modes(tmp_path, monkeypatch):
    from llama.profiles import Profile, save_profile
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(cli, "run_interpret", lambda ws, provider, query, **kw: Criteria(query=query))
    monkeypatch.setattr(cli, "make_providers", lambda config: collections.defaultdict(lambda: None))
    seen = _captured(monkeypatch)
    assert cli_invoke(cfg, "get", "q", "--auto", "--name", "r1", "--adjudicate").exit_code == 0
    assert seen[0]["adjudicate"] is True
    save_profile(tmp_path, Profile(name="p", criteria=Criteria(query="q"), count=1))
    seen.clear()
    r = cli_invoke(cfg, "get", "--profile", "p", "--auto", "--adjudicate")
    assert r.exit_code == 0, r.output
    assert seen[0]["adjudicate"] is True


def test_request_json_never_records_adjudicate(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(cli, "run_interpret", lambda ws, provider, query, **kw: Criteria(query=query))
    monkeypatch.setattr(cli, "make_providers", lambda config: collections.defaultdict(lambda: None))
    _captured(monkeypatch)
    r = cli_invoke(cfg, "get", "q", "--auto", "--name", "r1", "--adjudicate")
    assert r.exit_code == 0, r.output
    req = json.loads((tmp_path / "runs" / "r1" / "request.json").read_text())
    assert "adjudicate" not in req and "adjudicate" not in json.dumps(req)


# ---------------------------------------------------------------- redo

def _held_build(tmp_path, slug="heldpkg"):
    return build(tmp_path, slug, stages={"select", "gather", "research", "vet", "package"},
                 needs_review=True)


def _redo_stays_held(monkeypatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda config, ia, ledger, e, stage, **k: calls.append(e.slug))
    return calls


def test_redo_single_adjudicates_still_held_and_keeps_redo_exit_code(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_build(tmp_path)
    _redo_stays_held(monkeypatch)
    spy = _spy(monkeypatch, None,
               lambda ctx, e: runner.ShowOutcome(e.slug, runner.FAILED, "apply: boom"))
    r = cli_invoke(cfg, "redo", "heldpkg", "--from", "package", "--adjudicate")
    assert r.exit_code == 0, r.output
    assert "still held: heldpkg" in r.output
    assert "adjudicated heldpkg: held with proposal" in r.output
    r = cli_invoke(cfg, "redo", "heldpkg", "--from", "package", "--adjudicate")
    assert r.exit_code == 0, r.output
    assert "adjudicated heldpkg: failed (apply: boom)" in r.output
    assert spy.calls == ["heldpkg", "heldpkg"]
    spy.effects.append(OSError("gone"))
    r = cli_invoke(cfg, "redo", "heldpkg", "--from", "package", "--adjudicate")
    assert r.exit_code == 0, r.output
    assert "adjudicated heldpkg: failed (OSError: gone)" in r.output


def test_redo_single_no_adjudicate_and_packaged_skip(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_build(tmp_path)
    _redo_stays_held(monkeypatch)
    spy = _spy(monkeypatch)
    assert cli_invoke(cfg, "redo", "heldpkg", "--from", "package").exit_code == 0
    assert spy.calls == []
    monkeypatch.setattr(cli, "_redo_show", lambda *a, **k: Path("/pkg"))
    assert cli_invoke(cfg, "redo", "heldpkg", "--from", "package",
                      "--adjudicate").exit_code == 0
    assert spy.calls == []


def test_redo_single_adjudicates_outside_the_show_lock(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_build(tmp_path)
    _redo_stays_held(monkeypatch)
    free = []

    def probe(ctx, entry):
        try:
            with file_lock(entry.ws.lock, blocking=False):
                free.append(True)
        except Locked:
            free.append(False)
        return runner.ShowOutcome(entry.slug, runner.PROPOSAL)

    _spy(monkeypatch, probe)
    assert cli_invoke(cfg, "redo", "heldpkg", "--from", "package",
                      "--adjudicate").exit_code == 0
    assert free == [True]


def test_redo_single_pause_prints_later_command(tmp_path, monkeypatch):
    _clock(monkeypatch)
    cfg = _cfg(tmp_path)
    _held_build(tmp_path)
    _redo_stays_held(monkeypatch)
    spy = _spy(monkeypatch, _limited())
    r = cli_invoke(cfg, "redo", "heldpkg", "--from", "package", "--adjudicate")
    assert r.exit_code == 0, r.output
    assert "still held: heldpkg" in r.output
    assert ("paused adjudication: You've hit your session limit; "
            "judge it later with: llama adjudicate heldpkg") in r.output
    # the gate, before any call
    monkeypatch.setattr(cli, "_meter", lambda config, pace: _reading(five=99))
    r = cli_invoke(cfg, "redo", "heldpkg", "--from", "package", "--adjudicate")
    assert r.exit_code == 0, r.output
    assert "paused adjudication: " in r.output
    assert "; judge it later with: llama adjudicate heldpkg" in r.output
    assert spy.calls == ["heldpkg"]


def test_redo_batch_gate_stops_adjudicating_but_not_redoing(tmp_path, monkeypatch):
    _clock(monkeypatch)
    cfg = _cfg(tmp_path)
    for s in ("aheld", "bheld", "cheld"):
        _held_build(tmp_path, s)
    redos = _redo_stays_held(monkeypatch)
    spy = _spy(monkeypatch, None, _limited())
    r = cli_invoke(cfg, "redo", "--held", "--from", "package", "--yes", "--adjudicate")
    assert r.exit_code == 0, r.output
    assert redos == ["aheld", "bheld", "cheld"]
    assert spy.calls == ["aheld", "bheld"]
    assert "adjudicated aheld: held with proposal" in r.output
    assert r.output.count("paused adjudication") == 1
    assert ("paused adjudication: You've hit your session limit; "
            "judge it later with: llama adjudicate --held") in r.output


def test_redo_batch_gate_runs_before_each_adjudication(tmp_path, monkeypatch):
    _clock(monkeypatch)
    cfg = _cfg(tmp_path)
    for s in ("aheld", "bheld"):
        _held_build(tmp_path, s)
    redos = _redo_stays_held(monkeypatch)
    reads = iter([10, 99, 10])
    monkeypatch.setattr(cli, "_meter", lambda config, pace: _reading(five=next(reads)))
    spy = _spy(monkeypatch)
    r = cli_invoke(cfg, "redo", "--held", "--from", "package", "--yes", "--adjudicate")
    assert r.exit_code == 0, r.output
    assert redos == ["aheld", "bheld"] and spy.calls == ["aheld"]
    assert r.output.count("paused adjudication") == 1


def test_redo_run_show_level_batch_takes_the_flag(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _held_build(tmp_path, "aheld")
    _redo_stays_held(monkeypatch)
    spy = _spy(monkeypatch)
    # --run batches drop held shows unless asked; use a packaged-then-held redo instead
    build(tmp_path, "ready", stages={"select", "gather", "research", "vet", "package"})

    def rehold(config, ia, ledger, e, stage, **k):
        _held_build(tmp_path, e.slug)
    monkeypatch.setattr(cli, "_redo_show", rehold)
    r = cli_invoke(cfg, "redo", "--run", "r1", "--from", "package", "--yes", "--adjudicate")
    assert r.exit_code == 0, r.output
    assert spy.calls == ["ready"]


# ---------------------------------------------------------------- never adjudicate

@pytest.fixture
def always_on(monkeypatch):
    monkeypatch.setattr(cli, "_adjudicate_enabled", lambda config, flag: True)


def _rehold_locked(monkeypatch):
    def redo(config, ia, ledger, e, stage, **kw):
        show = read_model(e.ws.show, Show)
        write_artifact(e.ws.show, show.model_copy(update={
            "needs_review": True, "review_flags": ["unresolved track titles"]}))
        return None
    monkeypatch.setattr(cli, "_redo_show_locked", redo)


def test_fix_triage_reapply_never_adjudicate(tmp_path, monkeypatch, always_on):
    from llama import reapply as reapply_mod
    from llama.reapply import ReapplyOutcome
    cfg = _cfg(tmp_path)
    build(tmp_path, SLUG, stages={"select", "gather"}, needs_review=True)
    _rehold_locked(monkeypatch)
    spy = _spy(monkeypatch)
    r = cli_invoke(cfg, "fix", SLUG, "--set-venue", "Hall")
    assert r.exit_code == 0, r.output
    assert read_model(tmp_path / "shows" / SLUG / "show.json", Show).needs_review
    monkeypatch.setattr(typer_testing._NamedTextIOWrapper, "isatty", lambda self: True)
    r = cli_invoke(cfg, "triage", input="v\n")
    assert r.exit_code == 0, r.output
    assert read_model(tmp_path / "shows" / SLUG / "show.json", Show).needs_review
    monkeypatch.setattr(reapply_mod, "reapply_show", lambda *a, **k: ReapplyOutcome(
        slug=SLUG, outcome="held", briefing="none", flags=[], delivered=False, written=[]))
    r = cli_invoke(cfg, "reapply", SLUG)
    assert r.exit_code == 0, r.output
    assert f"reapplied: {SLUG} -> held" in r.output
    assert spy.calls == []


def test_apply_redo_never_adjudicates(tmp_path, monkeypatch):
    """A real auto-apply that ends held, reached from `redo`: the apply's own redo runs
    the show again (`_redo_show_locked`) and never re-enters the adjudicator."""
    from test_adjudicator_runner import CLOSER_FLAG, EXCLUDE_B, Rig, mk, A, C
    rig = Rig(tmp_path, monkeypatch)
    cfg = tmp_path / "config.toml"
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {**fake_providers(config), "adjudicate": rig.provider})
    rig.pre()
    rig.stub(mk([A, C], flags=[CLOSER_FLAG]))
    rig.queue(EXCLUDE_B)
    real = runner.adjudicate_show
    calls = []
    monkeypatch.setattr(runner, "adjudicate_show",
                        lambda *a, **k: calls.append(1) or real(*a, **k))
    r = cli_invoke(cfg, "redo", rig.slug, "--from", "package", "--adjudicate")
    assert r.exit_code == 0, r.output
    assert f"adjudicated {rig.slug}: applied, still held" in r.output
    assert len(calls) == 1 and rig.calls() == 1


# ---------------------------------------------------------------- fix round 1

def test_a_deferred_pass_adjudication_pause_judges_without_reprocessing(
        tmp_path, monkeypatch):
    """I1: a show another run held (first pass Locked) is processed in the deferred pass;
    its adjudication is refused, and the next cycle only judges it."""
    _clock(monkeypatch)
    real = cli.file_lock
    monkeypatch.setattr(cli, "file_lock", lambda path, *, blocking=True: (
        (_ for _ in ()).throw(Locked(path)) if not blocking else real(path, blocking=True)))
    spy = _spy(monkeypatch, _limited(), None)
    seen = _drive(tmp_path, monkeypatch, ["C/a"], pace=pacing.pace_options(Config()))
    assert seen == ["C/a"]                                  # processed once
    assert spy.calls == [slugify("C/a"), slugify("C/a")]
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_COMPLETE and info.outcome == "1 held"


def test_a_cycle_that_only_judged_counts_as_progress(tmp_path, monkeypatch, capsys):
    """I2: cycle 2 judges a (no show processed), then b's gate pauses. That cycle made
    progress, so the second pause sleeps rather than checkpointing."""
    _clock(monkeypatch, sleep_budget=20)
    n = {"reads": 0}

    def meter(config, pace):
        n["reads"] += 1
        # 1 pre-flight, 2 before a, 3 a's gate, (a refused) 4 a's gate, 5 before b: over
        return _reading(five=99 if n["reads"] == 5 else 10)

    monkeypatch.setattr(cli, "_meter", meter)
    spy = _spy(monkeypatch, _limited(minutes=10), None, None)
    seen = _drive(tmp_path, monkeypatch, ["C/a", "C/b"], pace=pacing.pace_options(Config()))
    out = capsys.readouterr().out
    assert "no progress" not in out
    assert seen == ["C/a", "C/b"]
    assert spy.calls == [slugify("C/a"), slugify("C/a"), slugify("C/b")]
    info = iter_sessions(tmp_path)[0]
    assert info.state == STATE_COMPLETE and info.outcome == "2 held"


def _recording(monkeypatch) -> list:
    recorded: list = []
    monkeypatch.setattr(cli.pacing_state, "record",
                        lambda root, before, after: recorded.append((before, after))
                        or cli.pacing_state.PacingState())
    return recorded


def test_a_gate_pause_before_adjudication_still_records_the_shows_boundary(
        tmp_path, monkeypatch):
    """M2 ruling: the show was fully processed before the adjudication gate paused, so
    its processing cost is a valid sample."""
    _clock(monkeypatch)
    recorded = _recording(monkeypatch)
    n = {"reads": 0}

    def meter(config, pace):
        n["reads"] += 1
        return _reading(five=99 if n["reads"] == 3 else 10)   # 3: a's adjudication gate

    monkeypatch.setattr(cli, "_meter", meter)
    spy = _spy(monkeypatch)
    seen = _drive(tmp_path, monkeypatch, ["C/a"], llm=True,
                  pace=pacing.pace_options(Config(), wait=False))
    assert seen == ["C/a"] and spy.calls == []
    assert len(recorded) == 1
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED


def test_a_refused_adjudication_records_no_boundary(tmp_path, monkeypatch):
    """M2 ruling, other half: a RateLimited in the adjudication call is a refused show
    (partial work), excluded like any refused show."""
    _clock(monkeypatch)
    recorded = _recording(monkeypatch)
    monkeypatch.setattr(cli, "_meter", lambda config, pace: _reading())
    _spy(monkeypatch, _limited(minutes=120))
    _drive(tmp_path, monkeypatch, ["C/a"], llm=True,
           pace=pacing.pace_options(Config(), max_wait="1h"))
    assert recorded == []
    assert iter_sessions(tmp_path)[0].state == STATE_PAUSED


def test_two_resume_passes_over_a_failing_adjudication_call_once(tmp_path, monkeypatch,
                                                                  capsys):
    """I2: the real runner behind `_execute`. The first pass's call fails and leaves a
    `failed` record; the second pass (a `run resume` of the same unchanged show) skips it
    with no call. A digest move judges it again."""
    from herder import TaskFailed
    from test_adjudicator_runner import Rig, TITLES_FLAG, VENUE_FLAG
    _clock(monkeypatch)
    rig = Rig(tmp_path, monkeypatch)
    rig.pre()
    pid = rig.entry().ws.dir.name
    rig.queue(*[TaskFailed("bad reply")] * 6)
    providers = collections.defaultdict(lambda: [FakeProvider(completes=["x"] * 50)])
    providers["adjudicate"] = rig.provider
    monkeypatch.setattr(cli, "make_providers", lambda config: providers)
    monkeypatch.setattr(cli, "run_search", lambda *a, **k: None)
    entries = [_entry(PID, 1)]
    monkeypatch.setattr(cli, "run_winnow", lambda *a, **k: entries)
    monkeypatch.setattr(cli, "choose_entries", lambda entries, *a, **k: entries)
    monkeypatch.setattr(cli, "make_client", lambda config: None)
    monkeypatch.setattr(cli, "process_show", lambda *a, **k: None)     # still held
    pace = pacing.pace_options(Config(), no_pacing=True)

    def one_pass():
        cli._execute(rig.config, rig.ia, rig.ledger, RunWorkspace(tmp_path, "r1"),
                     Criteria(query="x"), 1, auto=True, human_gate=False, pace=pace,
                     adjudicate=True)
    one_pass()
    first = rig.calls()
    assert first >= 1 and f"adjudicated {PID}: failed" in capsys.readouterr().out
    one_pass()
    assert rig.calls() == first
    assert f"adjudicated {PID}" not in capsys.readouterr().out
    rig.pre(flags=(TITLES_FLAG, VENUE_FLAG))                      # the digest moves
    one_pass()
    assert rig.calls() > first
    assert pid == SLUG
