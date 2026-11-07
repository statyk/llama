"""`llama adjudicate`: selection, the pacing/failure loop, --dry-run/--force/--accept and
the exit code. The real runner against a real packaged library show (test_adjudicator_runner's
`Rig`), with `runner.adjudicate_show` replaced only where a test is about the loop."""
from __future__ import annotations

import json

import pytest
from herder import FakeProvider
from herder.limits import RateLimited

import llama.adjudicator.runner as runner
import llama.cli as cli
from conftest import cli_invoke
from llama.adjudicator.record import read_record
from llama.override_keys import filename_keyed_refusal
from llama.pacing import PauseUntil, Proceed
from llama.workspace import read_overrides
from test_adjudicator_runner import (ACCEPTABLE, V, judge, CLOSER_FLAG, EXCLUDE_B, POST_NO_B, TITLES_FLAG, VENUE_FLAG, Rig, mk, A, C)
from test_pipeline import fake_providers


@pytest.fixture
def rig(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch)
    r.cfg = tmp_path / "config.toml"

    def providers(config):
        return {**fake_providers(config), "adjudicate": r.provider}
    monkeypatch.setattr(cli, "make_providers", providers)
    r.pre()
    return r


def run(rig, *args, **kw):
    return cli_invoke(rig.cfg, "adjudicate", "--no-pacing", *args, **kw)


def test_default_selects_held_and_skips_current(rig):
    rig.stub(mk([A, C], flags=[CLOSER_FLAG]))
    rig.queue(EXCLUDE_B)
    r = run(rig)
    assert r.exit_code == 0, r.output
    assert (f"{rig.slug}: applied, still held" in r.output
            and "summary: 1 shows: applied, still held 1" in r.output)
    assert "    - b.mp3 (0:30) B" in r.output
    again = run(rig)
    assert f"{rig.slug}: skipped: current" in again.output and rig.calls() == 1


def test_slugs_and_selectors_are_exclusive(rig):
    r = run(rig, rig.slug, "--held")
    assert r.exit_code == 1 and "give shows OR selectors, not both" in r.output
    assert rig.calls() == 0


def test_dry_run_writes_dry_run_records_and_changes_nothing_else(rig):
    rig.queue(EXCLUDE_B)
    before = rig.ws.show.read_bytes()
    r = run(rig, "--dry-run")
    assert r.exit_code == 0 and f"{rig.slug}: dry-run" in r.output
    rec = read_record(rig.ws)
    assert rec.dry_run and rec.outcome == "dry-run"
    assert rig.ws.show.read_bytes() == before and not rig.ws.overrides.exists()


def test_dry_run_never_overwrites_a_proposal_without_force(rig):
    rig.proposal(ACCEPTABLE)
    rig.pre(flags=[TITLES_FLAG, VENUE_FLAG])         # the digest moved: not current
    rig.queue(EXCLUDE_B)
    r = run(rig, "--dry-run")
    assert f"{rig.slug}: skipped: has a record" in r.output
    assert read_record(rig.ws).outcome == "proposal" and rig.calls() == 1
    r = run(rig, "--dry-run", "--force")
    assert f"{rig.slug}: dry-run" in r.output and read_record(rig.ws).dry_run


def test_force_rejudges(rig):
    rig.stub(mk([A, C], flags=[CLOSER_FLAG]))
    rig.queue(EXCLUDE_B)
    assert run(rig).exit_code == 0 and rig.calls() == 1
    plain = run(rig)
    assert f"{rig.slug}: skipped: current" in plain.output and rig.calls() == 1
    rig.queue(EXCLUDE_B)
    forced = run(rig, "--force")
    assert rig.calls() == 2 and f"{rig.slug}: skipped: current" not in forced.output


def test_pause_before_show_prints_and_stops_with_report(rig, monkeypatch):
    many(rig, 3)
    verdicts = [Proceed(), PauseUntil.__new__(PauseUntil)]
    gate_calls = []

    def decide_(*a, **k):
        gate_calls.append(1)
        return verdicts[len(gate_calls) - 1]
    monkeypatch.setattr(cli, "decide", decide_)
    monkeypatch.setattr(PauseUntil, "__str__", lambda self: "5-hour window at 99%")
    seen = stub_runner(monkeypatch, lambda slug, n: runner.ShowOutcome(slug, runner.CURRENT))
    r = cli_invoke(rig.cfg, "adjudicate")
    assert r.exit_code == 0 and len(gate_calls) == 2 and len(seen) == 1
    assert r.output.count("paused: ") == 1 and "paused: 5-hour window at 99%" in r.output
    assert "  re-run the same command to continue (judged shows are skipped while current)" \
        in r.output
    assert "summary: 1 shows: skipped: current 1" in r.output


def test_ratelimited_pauses_and_leaves_show_unjudged(rig, monkeypatch):
    many(rig, 3)
    rig.stub(POST_NO_B)
    rig.queue(EXCLUDE_B)                      # show 1 is judged and applied
    rig.provider.__class__ = type("RL", (FakeProvider,), {
        "complete": lambda self, p: (_ for _ in ()).throw(RateLimited("window used up"))
        if self.calls else FakeProvider.complete(self, p)})
    r = run(rig)
    assert r.exit_code == 0, r.output
    assert r.output.count("paused: ") == 1 and "re-run the same command to continue" in r.output
    assert len(rig.provider.calls) == 1       # show 1's call; the second raised (unrecorded)
    assert "summary: 1 shows: " in r.output   # the report so far has the judged show
    slugs = sorted(p.name for p in rig.ws.dir.parent.iterdir() if p.is_dir())
    judged = [s for s in slugs if (rig.ws.dir.parent / s / "adjudication.json").exists()]
    assert len(judged) == 1


def stub_runner(monkeypatch, outcomes):
    seen = []

    def fake(ctx, entry, **kw):
        seen.append(entry.slug)
        o = outcomes(entry.slug, len(seen))
        if isinstance(o, BaseException):
            raise o
        return o
    monkeypatch.setattr(runner, "adjudicate_show", fake)
    return seen


def many(rig, n=4):
    """n held library shows (copies of the rig's show under other slugs)."""
    import shutil
    for i in range(n - 1):
        d = rig.ws.dir.parent / f"gratefuldead-1973-06-1{i + 1}"
        shutil.copytree(rig.ws.dir, d)
        s = json.loads((d / "show.json").read_text())
        s["performance_id"] = f"GratefulDead/1973-06-1{i + 1}"
        (d / "show.json").write_text(json.dumps(s))


def test_three_consecutive_llm_failures_stop(rig, monkeypatch):
    many(rig, 5)
    seen = stub_runner(monkeypatch, lambda slug, n: runner.ShowOutcome(
        slug, runner.FAILED, "adjudicate call: x", llm_failure=True))
    r = run(rig)
    assert len(seen) == 3 and r.exit_code == 1
    assert "stopping after 3 consecutive LLM failures" in r.output
    assert "summary: 3 shows: failed 3" in r.output


def test_a_judged_show_resets_the_failure_count(rig, monkeypatch):
    many(rig, 5)

    def o(slug, n):
        if n == 3:
            return runner.ShowOutcome(slug, runner.PROPOSAL, record=read_record_stub())
        return runner.ShowOutcome(slug, runner.FAILED, "x", llm_failure=True)
    seen = stub_runner(monkeypatch, o)
    run(rig)
    assert len(seen) == 5


def read_record_stub():
    from llama.adjudicator.record import AdjudicationRecord
    return AdjudicationRecord(outcome="proposal")


def test_one_bad_show_does_not_abort(rig, monkeypatch):
    many(rig, 2)
    seen = stub_runner(monkeypatch, lambda slug, n: OSError("disk gone") if n == 1
                       else runner.ShowOutcome(slug, runner.CURRENT))
    r = run(rig)
    assert len(seen) == 2 and r.exit_code == 1
    assert "failed (OSError: disk gone)" in r.output and "skipped: current" in r.output


def test_bundle_error_on_first_show_second_still_judged(rig, monkeypatch):
    many(rig, 2)
    rig.queue(ACCEPTABLE)                     # fails the gate: a stored proposal
    real = runner.build_bundle
    calls = []

    def bad(ws, ia, config):
        calls.append(ws.dir.name)
        if len(calls) == 1:
            raise OSError("no")
        return real(ws, ia, config)
    monkeypatch.setattr(runner, "build_bundle", bad)
    r = run(rig)
    assert len(calls) == 2 and r.exit_code == 1 and "failed (bundle: no)" in r.output
    assert f"{calls[1]}: held with proposal" in r.output and "summary: 2 shows: held with proposal 1, failed 1" \
        in r.output
    second = rig.ws.dir.parent / calls[1] / "adjudication.json"
    assert second.exists() and not (rig.ws.dir.parent / calls[0] / "adjudication.json").exists()


def test_exit_code_one_on_failure(rig, monkeypatch):
    stub_runner(monkeypatch, lambda slug, n: runner.ShowOutcome(slug, runner.FAILED, "x"))
    assert run(rig).exit_code == 1


def test_accept_requires_named_shows_and_yes_without_tty(rig):
    assert "--accept takes named shows" in run(rig, "--accept", "--yes").output
    r = run(rig, rig.slug, "--accept")
    assert r.exit_code == 1 and "--accept needs --yes when not interactive" in r.output
    for bad in ("--dry-run", "--force"):
        assert run(rig, rig.slug, "--accept", "--yes", bad).exit_code == 1


def test_accept_yes_applies_and_prints_proposal_first(rig):
    rig.proposal(ACCEPTABLE)
    rig.stub(POST_NO_B)
    r = run(rig, rig.slug, "--accept", "--yes")
    assert r.exit_code == 0, r.output
    lines = r.output.splitlines()
    assert lines[0].startswith("proposal (") and f"{rig.slug}: accepted" in r.output
    assert lines.index(f"{rig.slug}: accepted") > 0
    assert read_overrides(rig.ws).exclude == ["b.mp3"]
    assert read_record(rig.ws).outcome == "accepted"


def test_accept_interactive_decline_applies_nothing(rig, monkeypatch):
    rig.proposal(ACCEPTABLE)
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    r = run(rig, rig.slug, "--accept", input="n\n")
    assert "Accept this proposal? [y/N]" in r.output
    assert not rig.ws.overrides.exists()


def test_accept_without_a_proposal(rig):
    r = run(rig, rig.slug, "--accept", "--yes")
    assert f"{rig.slug}: no proposal" in r.output


def test_filename_keyed_refusal_text():
    keyed = [("exclude", "x.mp3"), ("titles", "t.mp3")]
    assert filename_keyed_refusal("s", keyed) == (
        "s: overrides.json has filename-keyed entries (exclude: x.mp3; titles: t.mp3); "
        "clear them first with: llama fix s --unexclude x.mp3 --clear-title t.mp3")


def test_redeliver_names_replace_voiced_for_a_voiced_destination(rig, monkeypatch, tmp_path):
    station = tmp_path / "station"
    (station / rig.slug).mkdir(parents=True)
    (station / rig.slug / "manifest.json").write_text(json.dumps({"dj_audio": {"x": 1}}))
    cfg_text = rig.cfg.read_text()
    rig.cfg.write_text(f'delivery_path = "{station}"\n' + cfg_text)
    stub_runner(monkeypatch, lambda slug, n: runner.ShowOutcome(
        slug, runner.APPLIED, delivered_changed=True))
    r = run(rig)
    assert f"  llama deliver {rig.slug} --replace-voiced" in r.output, r.output
    (station / rig.slug / "manifest.json").write_text(json.dumps({"dj_audio": None}))
    r = run(rig)
    assert f"  llama deliver {rig.slug}\n" in r.output + "\n"
    assert "--replace-voiced" not in r.output


def test_accept_prompts_only_when_there_is_an_acceptable_proposal(rig, monkeypatch):
    rig.queue(EXCLUDE_B)
    assert run(rig, "--dry-run").exit_code == 0           # a dry-run record: never acceptable
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    r = run(rig, rig.slug, "--accept")
    assert "Accept this proposal?" not in r.output and "proposal (" not in r.output
    assert f"{rig.slug}: no proposal" in r.output


@pytest.mark.parametrize("extra,answer", [("--yes", None), (None, "n\n")])
def test_accept_never_applies_when_the_proposal_cannot_be_rendered(rig, monkeypatch,
                                                                    extra, answer):
    import llama.adjudicator.report as report
    rig.proposal(ACCEPTABLE)
    before = (rig.ws.show.read_bytes(), rig.ws.adjudication.read_bytes())
    applied = []
    monkeypatch.setattr(runner, "accept_proposal", lambda *a, **k: applied.append(1))
    monkeypatch.setattr(report, "render_proposal",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("bad record")))
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    args = (rig.slug, "--accept") + ((extra,) if extra else ())
    r = run(rig, *args, **({"input": answer} if answer else {}))
    assert applied == [] and not rig.ws.overrides.exists()
    assert (f"{rig.slug}: no proposal (proposal could not be rendered: bad record)"
            in r.output)
    assert (rig.ws.show.read_bytes(), rig.ws.adjudication.read_bytes()) == before


def test_accept_shows_no_prompt_for_a_stale_proposal(rig, monkeypatch):
    rig.proposal(ACCEPTABLE)
    rig.ws.overrides.write_text(json.dumps({"venue": "Elsewhere"}))   # the show's digest moves
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    r = run(rig, rig.slug, "--accept")
    assert "Accept this proposal?" not in r.output and "proposal (" not in r.output
    assert f"{rig.slug}: proposal stale" in r.output


def test_accept_shows_no_prompt_for_a_propose_only_proposal(rig, monkeypatch):
    rig.proposal(V([{"op": "set_date", "value": "1973-06-11", "confidence": "high", "why": "w"}],
                   [judge(TITLES_FLAG, "undecidable")], kind="hold"))
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    r = run(rig, rig.slug, "--accept")
    assert "Accept this proposal?" not in r.output and "proposal (claude" not in r.output
    assert f"{rig.slug}: no proposal" in r.output


def test_accept_applies_nothing_when_the_record_changed_after_it_was_shown(rig, monkeypatch):
    import llama.adjudicator.report as report
    from llama.adjudicator.record import write_record
    rec = rig.proposal(ACCEPTABLE)
    rig.stub(POST_NO_B)
    real = report.render_proposal

    def render_then_rewrite(*a, **k):
        lines = real(*a, **k)
        write_record(rig.ws, rec.model_copy(update={"at": "2099-01-01T00:00:00+00:00"}))
        return lines
    monkeypatch.setattr(report, "render_proposal", render_then_rewrite)
    r = run(rig, rig.slug, "--accept", "--yes")
    assert f"{rig.slug}: no proposal (proposal changed since it was shown; re-run)" in r.output
    assert not rig.ws.overrides.exists()
