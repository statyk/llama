"""The per-show runner (spec "Before judging", "Adjudication record and loop guard",
"Proposals in triage"): its order against the loop guard, and how each failure class
maps to an outcome and to what is (and is not) written. Runs against a real packaged
library show (`helpers.reuse_gd73`) with the real `build_bundle`, gate and apply, the
real `cli._redo_show_locked` with stub stages, and `FakeProvider` verdicts."""
from __future__ import annotations

import json
import shlex

import pytest

import llama.adjudicator.runner as runner
import llama.cli as cli
import llama.pipeline as pipeline
from herder import FakeProvider, TaskFailed
from herder.limits import RateLimited
from llama import campaign
from llama.adjudicator.record import (AdjudicationRecord, is_current, read_record,
                                      show_digest, write_record)
from llama.adjudicator.runner import (ACCEPTED, APPLIED, APPLIED_HELD, CHANGED, CURRENT,
                                      DRY_RUN, FAILED, HAS_RECORD, MALFORMED, NO_PROPOSAL,
                                      NOT_HELD, PROPOSAL, PROPOSAL_STALE, STALE, UNJUDGED,
                                      Context, accept_proposal, adjudicate_show,
                                      hook_enabled)
from llama.config import Config, load_config
from llama.errors import LlamaError
from llama.ia_client import IAError
from llama.ledger import Ledger
from llama.models import Briefing, Overrides, Provenance, QualityAssessment, Show, Track
from llama.workspace import read_model, read_overrides, write_artifact

from helpers import ReuseIA, delivered_gd73, reuse_gd73, tree_bytes

AT = "2026-11-07T00:00:00+00:00"
PID = "GratefulDead/1973-06-10"
DESC = ("Taper notes. b.mp3 is a tuning fragment before the show. Recorded at RFK Stadium. "
        "The gd73-sib transfer is complete.")
TITLES_FLAG = "unresolved track titles"
VENUE_FLAG = "venue mismatch: archive 'RFK' vs jerrybase 'RFK Stadium'"
CLOSER_FLAG = "jerrybase set closer 'Morning Dew' is not at a set break"
OLD = (("A", "a.mp3", 300.0), ("B", "b.mp3", 30.0), ("C", "c.mp3", 400.0))


# ---------------------------------------------------------------- verdict builders

def ev(quote="b.mp3 is a tuning fragment", kind="taper-description"):
    return {"kind": kind, "quote": quote}


def ed(op, conf="high", evidence=None, **kw):
    return {"op": op, "confidence": conf, "why": "w", "evidence": evidence or [ev()], **kw}


def judge(flag, verdict="spurious", conf="high"):
    return {"flag": flag, "verdict": verdict, "confidence": conf, "why": "jw"}


def V(edits, flags=(), kind="fix", after="yes", **kw):
    return {"flags": list(flags), "edits": list(edits), "kind": kind,
            "show_correct_after": after, "rationale": "r", **kw}


def exclude_b(conf="medium"):
    return ed("exclude", conf, file="b.mp3")


EXCLUDE_B = V([exclude_b()], [judge(TITLES_FLAG, "real-fixed-by-action")])


def T(fn, title, dur, src="tags"):
    return Track(index=0, set="1", title=title, filename=fn, duration_sec=dur, title_source=src)


def mk(tracks, flags=(), ident="gd73", venue="RFK Stadium"):
    tracks = [t.model_copy(update={"index": i}) for i, t in enumerate(tracks, 1)]
    return Show(performance_id=PID, identifier=ident, artist="Grateful Dead", date="1973-06-10",
                venue=venue, tracks=tracks, review_flags=list(flags),
                needs_review=bool(flags))


A, B, C = T("a.mp3", "A", 300.0), T("b.mp3", "B", 30.0, "unresolved"), T("c.mp3", "C", 400.0)
POST_NO_B = mk([A, C])


# ---------------------------------------------------------------- the rig

class RigIA(ReuseIA):
    """ReuseIA with a taper description, so quotes have a section to land in."""

    def metadata(self, identifier):
        md = super().metadata(identifier)
        md["metadata"] = {"description": DESC}
        return md


class SideFake(FakeProvider):
    """A FakeProvider whose next complete() first runs `before` (a concurrent writer)."""

    before = None

    def complete(self, prompt):
        if self.before is not None:
            fn, self.before = self.before, None
            fn()
        return super().complete(prompt)


class Rig:
    def __init__(self, tmp_path, monkeypatch, *, delivered=False):
        if delivered:
            cfg, self.ws, self.ia, self.station = delivered_gd73(tmp_path, monkeypatch, OLD)
        else:
            cfg, self.ws, self.ia = reuse_gd73(tmp_path, monkeypatch, OLD)
        self.ia.__class__ = RigIA
        self.mp = monkeypatch
        self.config = load_config(cfg)
        self.ledger = Ledger(tmp_path / "ledger.jsonl")
        self.provider = SideFake()
        self.stages: list[str] = []
        self.slug = self.ws.dir.name
        monkeypatch.setattr(runner, "stale_message", lambda *a, **k: None)
        write_artifact(self.ws.selection, {"identifier": "gd73", "scores": {
            "gd73": {"lineage": "sbd", "kept_tracks": 3, "score": 3.0},
            "gd73-sib": {"lineage": "sbd", "kept_tracks": 3, "score": 2.0}}})
        self.ctx = Context(config=self.config, ia=self.ia, ledger=self.ledger,
                           provider=self.provider, redo=self.redo, now=lambda: AT)

    def redo(self, entry, stage):
        self.stages.append(stage)
        fresh = cli._resolve_show(self.config, self.ledger, entry.slug)
        return cli._redo_show_locked(self.config, self.ia, self.ledger, fresh, stage)

    def entry(self):
        return cli._resolve_show(self.config, self.ledger, self.slug)

    def pre(self, flags=(TITLES_FLAG,), tracks=(A, B, C)) -> Show:
        show = mk(list(tracks), flags=flags)
        write_artifact(self.ws.show, show)
        return show

    def stub(self, post: Show, *, select: str | None = None, fail=None):
        """Gather writes `post` when show.json was dropped; `fail` raises in gather."""
        def gather(show_ws, *a, **k):
            if fail is not None:
                raise fail
            if show_ws.show.exists():
                return read_model(show_ws.show, Show)
            write_artifact(show_ws.show, post)
            return post

        def brief(show_ws, *a, **k):
            write_artifact(show_ws.briefing_json, Briefing(context="c", significance="s"))
            write_artifact(show_ws.briefing_md, "# Briefing\n")
        self.ia.lengths.update({t.filename: t.duration_sec for t in post.tracks})
        self.mp.setattr(pipeline, "run_gather", gather)
        self.mp.setattr(pipeline, "run_research", lambda *a, **k: "research")
        self.mp.setattr(pipeline, "run_vet_research", lambda *a, **k: None)
        self.mp.setattr(pipeline, "run_brief", brief)
        if select is not None:
            def sel(show_ws, *a, **k):
                write_artifact(show_ws.selection, {"identifier": select, "scores": {}})
                return select
            self.mp.setattr(pipeline, "run_select_recording", sel)

    def queue(self, *verdicts):
        self.provider.completes += [json.dumps(v) if isinstance(v, dict) else v
                                    for v in verdicts]

    def run(self, **kw):
        return adjudicate_show(self.ctx, self.entry(), **kw)

    def accept(self):
        return accept_proposal(self.ctx, self.entry())

    def calls(self) -> int:
        return len(self.provider.calls)

    def complaints(self, ident: str, n: int):
        prov = read_model(self.ws.provenance, Provenance)
        a = prov.assessment or QualityAssessment(performance_id=PID, quality_score=5.0,
                                                 rationale="r")
        write_artifact(self.ws.provenance, prov.model_copy(update={"assessment": a.model_copy(
            update={"reviewed_identifier": ident,
                    "recording_complaints": [f"c{i}" for i in range(n)]})}))

    def proposal(self, verdict) -> AdjudicationRecord:
        self.queue(verdict)
        out = self.run()
        assert out.outcome == PROPOSAL, out
        return read_record(self.ws)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    return Rig(tmp_path, monkeypatch)


class ApplyCalled(BaseException):
    """A BaseException, so the runner's Exception catch-all cannot turn it into FAILED."""


def _no_apply(monkeypatch):
    def boom(*a, **k):
        raise ApplyCalled("apply_verdict must not be called")
    monkeypatch.setattr(runner, "apply_verdict", boom)


SWITCH = V([ed("switch_recording", identifier="gd73-sib",
               evidence=[ev("The gd73-sib transfer is complete")])],
           [judge(TITLES_FLAG, "real-fixed-by-action")])


# ---------------------------------------------------------------- skips

def test_not_held_and_current_are_skipped_without_llm_call(rig, monkeypatch):
    def stale(*a, **k):
        raise ApplyCalled("the stale check must come after the not-held and current skips")
    monkeypatch.setattr(runner, "stale_message", stale)
    rig.pre(flags=())
    assert rig.run().outcome == NOT_HELD
    rig.pre()
    write_record(rig.ws, AdjudicationRecord(outcome="proposal", digest=show_digest(rig.ws)))
    assert rig.run().outcome == CURRENT
    assert rig.calls() == 0


def test_force_rejudges_a_current_show(rig):
    rig.pre()
    write_record(rig.ws, AdjudicationRecord(outcome="proposal", digest=show_digest(rig.ws)))
    rig.queue(V([exclude_b("low")], [judge(TITLES_FLAG, "real-fixed-by-action")]))
    out = rig.run(force=True)
    assert out.outcome == PROPOSAL and rig.calls() == 1
    assert read_record(rig.ws).verdict["edits"][0]["confidence"] == "low"


def test_stale_show_is_not_judged(rig, monkeypatch):
    rig.pre()
    monkeypatch.setattr(runner, "stale_message", lambda ia, config, ws, slug: f"{slug}: stale!")
    out = rig.run()
    assert (out.outcome, out.detail) == (STALE, f"{rig.slug}: stale!")
    assert rig.calls() == 0 and not rig.ws.adjudication.exists()


def test_legacy_overrides_are_stale_and_not_judged(rig):
    rig.pre()
    rig.ws.overrides.write_text(json.dumps({"titles": {"3": "X"}}))
    out = rig.run()
    assert out.outcome == STALE and "track-number keys" in out.detail
    assert rig.calls() == 0 and not rig.ws.adjudication.exists()


# ---------------------------------------------------------------- failures before judging

def test_bundle_error_is_failed_and_writes_nothing(rig, monkeypatch):
    rig.pre()
    before = tree_bytes(rig.ws.dir)

    def down(identifier):
        raise IAError("archive.org down")
    monkeypatch.setattr(rig.ia, "metadata", down)
    out = rig.run()
    assert out.outcome == FAILED and "archive.org down" in out.detail
    assert rig.calls() == 0 and tree_bytes(rig.ws.dir) == before


def test_llm_failure_marks_llm_failure_and_writes_a_failed_record(rig):
    """I2: a failed call leaves a digest-keyed `failed` record and nothing else, so the
    pipeline hooks do not pay for the same unchanged show again."""
    rig.pre()
    before = tree_bytes(rig.ws.dir)
    rig.queue(TaskFailed("bad reply"))
    out = rig.run()
    assert (out.outcome, out.llm_failure) == (FAILED, True)
    rec = read_record(rig.ws)
    assert rec is not None and rec.outcome == "failed" and not rec.dry_run
    assert rec.digest == show_digest(rig.ws) and "bad reply" in rec.result["error"]
    assert is_current(rig.ws)
    after = tree_bytes(rig.ws.dir)
    after.pop("adjudication.json")
    assert after == before


def test_a_failed_record_is_current_by_default_and_retried_on_request(rig):
    """I2: the hooks' default skips a current `failed` record; the backlog command's
    `retry_failed` judges it again without --force."""
    rig.pre()
    rig.queue(TaskFailed("bad reply"))
    assert rig.run().outcome == FAILED
    assert rig.run().outcome == CURRENT and rig.calls() == 1
    rig.queue(TaskFailed("bad again"))
    assert rig.run(retry_failed=True).outcome == FAILED and rig.calls() == 2
    assert "bad again" in read_record(rig.ws).result["error"]


def test_retry_failed_still_skips_a_current_proposal(rig):
    rig.pre()
    rig.proposal(V([exclude_b("low")], [judge(TITLES_FLAG, "real-fixed-by-action")]))
    assert rig.run(retry_failed=True).outcome == CURRENT and rig.calls() == 1


def test_a_failed_record_is_rejudged_once_the_digest_moves(rig):
    rig.pre()
    rig.queue(TaskFailed("bad reply"))
    assert rig.run().outcome == FAILED
    rig.pre(flags=(TITLES_FLAG, VENUE_FLAG))                  # the show moved
    rig.queue(TaskFailed("bad reply"))
    assert rig.run().outcome == FAILED and rig.calls() == 2


def test_llm_failure_on_a_changed_show_writes_nothing(rig):
    """I2: CHANGED still writes nothing (the failed record is under the same writer)."""
    rig.pre()
    rig.provider.before = lambda: write_artifact(rig.ws.overrides, Overrides(venue="Kezar"))
    rig.queue(TaskFailed("bad reply"))
    out = rig.run()
    assert (out.outcome, out.llm_failure) == (FAILED, True)
    assert not rig.ws.adjudication.exists()


def test_llm_failure_in_a_dry_run_writes_nothing(rig):
    rig.pre()
    rig.queue(TaskFailed("bad reply"))
    assert rig.run(dry_run=True).outcome == FAILED
    assert not rig.ws.adjudication.exists()


def test_a_failed_record_is_never_acceptable(rig):
    from llama.adjudicator.runner import acceptable_state
    rig.pre()
    rig.queue(TaskFailed("bad reply"))
    rig.run()
    rec = read_record(rig.ws)
    assert acceptable_state(rig.ws, rec) == "none"
    rig.pre(flags=(TITLES_FLAG, VENUE_FLAG))                  # stale: still no proposal
    assert acceptable_state(rig.ws, rec) == "none"
    assert rig.accept().outcome == NO_PROPOSAL


def test_render_value_error_is_failed_without_llm_failure(rig, monkeypatch):
    rig.pre()

    def render(provider, bundle):
        raise ValueError("template")
    monkeypatch.setattr(runner, "call_adjudicator", render)
    out = rig.run()
    assert (out.outcome, out.llm_failure) == (FAILED, False)
    assert not rig.ws.adjudication.exists()


def test_no_provider_is_failed(rig):
    rig.pre()
    rig.ctx.provider = None
    out = rig.run()
    assert (out.outcome, out.detail) == (FAILED, "no adjudicate provider")
    assert not rig.ws.adjudication.exists()


def test_ratelimited_propagates_and_record_unchanged(rig):
    rig.pre()
    old = AdjudicationRecord(outcome="proposal", digest="old")
    write_record(rig.ws, old)
    rig.queue(RateLimited("window exhausted"))
    with pytest.raises(RateLimited):
        rig.run()
    assert read_record(rig.ws) == old


# ---------------------------------------------------------------- malformed and gate

def test_malformed_verdict_stores_record_and_stays_held(rig, monkeypatch):
    rig.pre()
    _no_apply(monkeypatch)              # C1: never reaches apply
    rig.queue(V([ed("exclude", file="zz.mp3")], [judge(TITLES_FLAG, "real-fixed-by-action")]))
    out = rig.run()
    rec = read_record(rig.ws)
    assert out.outcome == MALFORMED and rec.outcome == "malformed"
    assert rec.malformed == ["edit 0 exclude: zz.mp3 is not a current track"]
    assert rec.digest == show_digest(rig.ws) and is_current(rig.ws)
    assert read_model(rig.ws.show, Show).needs_review


def test_gate_failure_stores_proposal_with_gate_reasons(rig, monkeypatch):
    rig.pre()
    _no_apply(monkeypatch)
    rig.queue(V([exclude_b("low")], [judge(TITLES_FLAG, "real-fixed-by-action")]))
    out = rig.run()
    rec = read_record(rig.ws)
    assert out.outcome == PROPOSAL and rec.outcome == "proposal" and not rec.dry_run
    assert rec.gate[0]["passed"] is False
    assert rec.gate[0]["reason"] == "short bar needs medium or high confidence"
    assert rec.digest == show_digest(rig.ws) and rec.model


def test_switch_to_a_sibling_with_complaints_fails_the_gate(rig, monkeypatch):
    """C2: Facts.complaints is built from the provenance's assessment."""
    rig.pre()
    _no_apply(monkeypatch)
    rig.complaints("gd73-sib", 2)
    out = rig.proposal(SWITCH)
    assert out.gate[0]["reason"] == "select found recording complaints against the sibling"
    assert out.gate[0]["bar"] == "switch"


def test_switch_without_complaints_passes_the_gate(rig, monkeypatch):
    """The control for C2: the same switch, complaints against another recording only."""
    rig.pre()
    rig.complaints("gd73", 2)
    seen = []

    def spy(show_ws, verdict, **kw):
        seen.append(kw["gate"])
        raise LlamaError("stop here")
    monkeypatch.setattr(runner, "apply_verdict", spy)
    rig.queue(SWITCH)
    out = rig.run()
    assert seen and seen[0].auto, seen
    assert out.outcome == FAILED                 # C4: an unexpected error is a failure
    assert read_record(rig.ws).outcome == "failed"           # I2: a paid call is recorded


# ---------------------------------------------------------------- auto apply

def test_auto_apply_clears_and_writes_applied_record_with_post_digest(rig):
    rig.pre()
    rig.stub(POST_NO_B)
    rig.queue(EXCLUDE_B)
    out = rig.run()
    rec = read_record(rig.ws)
    assert out.outcome == APPLIED and rec.outcome == "applied" and rec.digest == show_digest(rig.ws)
    assert is_current(rig.ws)                     # loop guard: a later pipeline run skips it
    assert rec.applied[0]["evidence_kinds"] == ["taper-description"]
    assert rec.applied == [{"index": 0, "op": "exclude", "target": "b.mp3",
                            "evidence_kinds": ["taper-description"]}]
    assert rec.result["status"] == "applied" and rec.held_proposal is None
    assert out.changes == ["- b.mp3 (0:30) B"] and out.record == rec
    assert not out.delivered_changed and not out.fixed_eligible
    assert rig.stages == ["gather"]
    assert read_overrides(rig.ws).exclude == ["b.mp3"]
    assert rec.at == AT and rec.model and rec.gate and rec.vetoes == []


def test_applied_but_still_held_is_current_and_not_rejudged(rig):
    rig.pre()
    rig.stub(mk([A, C], flags=[CLOSER_FLAG]))
    rig.queue(EXCLUDE_B)
    out = rig.run()
    assert out.outcome == APPLIED_HELD
    rec = read_record(rig.ws)
    assert rec.held_proposal == {"flags": [{"flag": CLOSER_FLAG, "judgement": None}],
                                 "edits": []}
    assert rig.run().outcome == CURRENT and rig.calls() == 1


HELD_VERDICT = V([exclude_b(),
                  ed("overrule", "medium", evidence=[ev("Recorded at RFK Stadium")],
                     flag=VENUE_FLAG)],
                 [judge(TITLES_FLAG, "real-fixed-by-action"), judge(VENUE_FLAG, conf="low")])


def test_applied_but_still_held_stores_held_proposal_of_leftover_flags(rig):
    rig.pre(flags=[TITLES_FLAG, VENUE_FLAG])
    rig.stub(mk([A, C], flags=[VENUE_FLAG]))
    rig.queue(HELD_VERDICT)
    out = rig.run()
    assert out.outcome == APPLIED_HELD, out
    hp = read_record(rig.ws).held_proposal
    assert hp["flags"] == [{"flag": VENUE_FLAG, "judgement": judge(VENUE_FLAG, conf="low")}]
    assert hp["edits"] == [{"op": "overrule", "flag": VENUE_FLAG, "confidence": "low",
                            "why": "jw", "evidence": [ev("Recorded at RFK Stadium")]}]


def test_delivered_changed_by_digest_covers_venue_only_apply(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, delivered=True)
    rig.pre(flags=[VENUE_FLAG], tracks=[T("a.mp3", "A", 300.0), T("b.mp3", "B", 30.0),
                                        T("c.mp3", "C", 400.0)])
    rig.stub(mk([T("a.mp3", "A", 300.0), T("b.mp3", "B", 30.0), T("c.mp3", "C", 400.0)],
                venue="RFK Stadium, Washington"))
    rig.queue(V([ed("venue", "medium", evidence=[ev("Recorded at RFK Stadium")],
                    venue="RFK Stadium, Washington")], [judge(VENUE_FLAG, conf="medium")]))
    out = rig.run()
    assert out.outcome == APPLIED, out
    assert out.changes == [] and out.delivered_changed is True


def test_not_delivered_is_never_delivered_changed(rig):
    rig.pre(flags=[VENUE_FLAG], tracks=[T("a.mp3", "A", 300.0), T("b.mp3", "B", 30.0),
                                        T("c.mp3", "C", 400.0)])
    rig.stub(mk([T("a.mp3", "A", 300.0), T("b.mp3", "B", 30.0), T("c.mp3", "C", 400.0)],
                venue="RFK Stadium, Washington"))
    rig.queue(V([ed("venue", "medium", evidence=[ev("Recorded at RFK Stadium")],
                    venue="RFK Stadium, Washington")], [judge(VENUE_FLAG, conf="medium")]))
    out = rig.run()
    assert out.outcome == APPLIED and out.delivered_changed is False


def test_fixed_eligible_for_marked_show_whose_campaign_record_ends_processed(rig):
    rig.pre()
    campaign.add_mark(rig.ws, reason="piece 4", start_stage="gather", batch="w1",
                      at="2026-01-01T00:00:00Z")
    rig.stub(POST_NO_B)
    rig.queue(EXCLUDE_B)
    out = rig.run()
    assert out.outcome == APPLIED and out.fixed_eligible is True


def test_accept_of_a_marked_show_is_fixed_eligible(rig):             # M2
    rig.pre()
    campaign.add_mark(rig.ws, reason="piece 4", start_stage="gather", batch="w1",
                      at="2026-01-01T00:00:00Z")
    rig.proposal(ACCEPTABLE)
    rig.stub(POST_NO_B)
    out = rig.accept()
    assert out.outcome == ACCEPTED and out.fixed_eligible is True


def test_accept_of_an_unmarked_show_is_not_fixed_eligible(rig):         # M2
    rig.pre()
    rig.proposal(ACCEPTABLE)
    rig.stub(POST_NO_B)
    out = rig.accept()
    assert out.outcome == ACCEPTED and out.fixed_eligible is False


def test_unreadable_campaign_counts_as_marked_and_is_not_fixed_eligible(rig, monkeypatch):
    rig.pre()
    rig.ws.campaign.write_text("{broken")
    seen = []

    def spy(show_ws, verdict, **kw):
        seen.append(True)
        raise LlamaError("stop")
    monkeypatch.setattr(runner, "apply_verdict", spy)
    rig.queue(SWITCH)
    out = rig.run()
    rec = read_record(rig.ws)
    assert out.outcome == PROPOSAL and not seen
    assert "show is station-marked" in rec.gate[0]["reason"]


def test_restored_apply_becomes_proposal_with_pre_state_digest(rig):
    rig.pre()
    pre_digest = show_digest(rig.ws)
    before = tree_bytes(rig.ws.dir)
    rig.stub(mk([T("a.mp3", "Bertha", 300.0), C]))          # a's title moved: not predicted
    rig.queue(EXCLUDE_B)
    out = rig.run()
    rec = read_record(rig.ws)
    assert out.outcome == PROPOSAL and rec.outcome == "proposal"
    assert rec.result["status"] == "restored" and rec.result["diff"]
    assert rec.digest == pre_digest == show_digest(rig.ws)
    after = tree_bytes(rig.ws.dir)
    after.pop("adjudication.json")
    assert after == before


def test_refused_apply_becomes_proposal_carrying_the_error(rig):
    rig.pre()
    rig.stub(POST_NO_B, fail=LlamaError("station copy does not pair"))
    rig.queue(EXCLUDE_B)
    out = rig.run()
    rec = read_record(rig.ws)
    assert out.outcome == PROPOSAL
    assert (rec.result["status"], rec.result["error"]) == ("refused", "station copy does not pair")


def test_transient_apply_failure_writes_a_failed_record(rig):
    """I2: an unjudged transient leaves a `failed` record of the pre-state digest."""
    rig.pre()
    pre_digest = show_digest(rig.ws)
    before = tree_bytes(rig.ws.dir)
    rig.stub(POST_NO_B, fail=IAError("download of b.mp3 failed"))
    rig.queue(EXCLUDE_B)
    out = rig.run()
    assert out.outcome == UNJUDGED
    rec = read_record(rig.ws)
    assert rec.outcome == "failed" and rec.digest == pre_digest == show_digest(rig.ws)
    assert "download of b.mp3 failed" in rec.result["error"] and rec.verdict["edits"]
    after = tree_bytes(rig.ws.dir)
    after.pop("adjudication.json")
    assert after == before
    assert rig.run().outcome == CURRENT and rig.calls() == 1


@pytest.mark.parametrize("exc", [ValueError("boom"), OSError("disk")])
def test_unexpected_apply_error_is_failed_not_a_crash(rig, exc):
    """C4: an exception apply lets through fails the show, not the backlog run."""
    rig.pre()
    before = tree_bytes(rig.ws.dir)
    rig.stub(POST_NO_B, fail=exc)
    rig.queue(EXCLUDE_B)
    out = rig.run()
    assert out.outcome == FAILED and str(exc) in out.detail
    rec = read_record(rig.ws)                                  # I2
    assert rec.outcome == "failed" and str(exc) in rec.result["error"]
    after = tree_bytes(rig.ws.dir)
    after.pop("adjudication.json")
    assert after == before


def test_apply_ratelimited_propagates_with_nothing_written(rig):
    rig.pre()
    before = tree_bytes(rig.ws.dir)
    rig.stub(POST_NO_B, fail=RateLimited("window"))
    rig.queue(EXCLUDE_B)
    with pytest.raises(RateLimited):
        rig.run()
    assert tree_bytes(rig.ws.dir) == before


def test_proposal_write_refused_by_changed_view_is_changed(rig):
    rig.pre()
    rig.provider.before = lambda: write_artifact(rig.ws.overrides, Overrides(venue="Kezar"))
    rig.queue(V([exclude_b("low")], [judge(TITLES_FLAG, "real-fixed-by-action")]))
    assert rig.run().outcome == CHANGED
    assert not rig.ws.adjudication.exists()


def test_concurrent_change_writes_nothing(rig):
    rig.pre()
    rig.stub(POST_NO_B)
    rig.provider.before = lambda: write_artifact(rig.ws.overrides, Overrides(venue="Kezar"))
    rig.queue(EXCLUDE_B)
    assert rig.run().outcome == CHANGED and not rig.ws.adjudication.exists()
    assert rig.stages == [] and read_overrides(rig.ws) == Overrides(venue="Kezar")


def test_malformed_write_refused_by_changed_view_is_changed(rig):
    rig.pre()
    rig.provider.before = lambda: write_artifact(rig.ws.overrides, Overrides(venue="Kezar"))
    rig.queue(V([ed("exclude", file="zz.mp3")], [judge(TITLES_FLAG, "real-fixed-by-action")]))
    assert rig.run().outcome == CHANGED and not rig.ws.adjudication.exists()


# ---------------------------------------------------------------- dry run

def test_dry_run_record_is_never_current_and_never_accepted(rig):
    rig.pre()
    rig.queue(EXCLUDE_B, EXCLUDE_B)
    out = rig.run(dry_run=True)
    rec = read_record(rig.ws)
    assert out.outcome == DRY_RUN and rec.outcome == "dry-run" and rec.dry_run
    assert rec.gate and rig.stages == []
    assert not is_current(rig.ws)
    assert rig.run(dry_run=True).outcome == DRY_RUN and rig.calls() == 2
    assert rig.accept().outcome == NO_PROPOSAL


def test_dry_run_keeps_proposal_and_applied_records_unless_forced(rig):
    rig.pre()
    for outcome in ("proposal", "applied", "accepted"):
        rec = AdjudicationRecord(outcome=outcome, digest="stale-digest")
        write_record(rig.ws, rec)
        out = rig.run(dry_run=True)
        assert out.outcome == HAS_RECORD and "--force" in out.detail
        assert read_record(rig.ws) == rec and rig.calls() == 0
    rig.queue(EXCLUDE_B)
    assert rig.run(dry_run=True, force=True).outcome == DRY_RUN
    assert read_record(rig.ws).dry_run
    # a malformed record is not kept from a dry run
    write_record(rig.ws, AdjudicationRecord(outcome="malformed", digest="stale-digest"))
    rig.queue(EXCLUDE_B)
    assert rig.run(dry_run=True).outcome == DRY_RUN


def test_trial_policy_true_trials_and_restores_false_records_dry_run(rig):
    rig.pre()
    before = tree_bytes(rig.ws.dir)
    rig.stub(POST_NO_B)
    rig.queue(EXCLUDE_B)
    out = rig.run(dry_run=True, trial_policy=lambda v, g: True)
    rec = read_record(rig.ws)
    assert out.outcome == DRY_RUN and rec.dry_run and rec.result["status"] == "applied"
    assert rec.result["changes"] == ["- b.mp3 (0:30) B"]
    assert rig.stages == ["gather"] and rig.calls() == 1
    after = tree_bytes(rig.ws.dir)
    after.pop("adjudication.json")
    assert after == before                               # restored by the unit
    rig.queue(EXCLUDE_B)
    out = rig.run(dry_run=True, trial_policy=lambda v, g: False)
    rec = read_record(rig.ws)
    assert out.outcome == DRY_RUN and rec.result == {} and rig.stages == ["gather"]
    assert rig.calls() == 2


def test_sink_writes_to_pilot_dir_not_adjudication_json(rig, tmp_path):
    rig.pre()
    rig.ctx.sink = tmp_path / "pilot"
    rig.queue(EXCLUDE_B)
    out = rig.run(dry_run=True)
    assert out.outcome == DRY_RUN and not rig.ws.adjudication.exists()
    rec = AdjudicationRecord.model_validate_json(
        (tmp_path / "pilot" / f"{rig.slug}.json").read_text())
    assert rec.dry_run and rec.digest == show_digest(rig.ws)


# ---------------------------------------------------------------- accept

ACCEPTABLE = V([exclude_b("low"), {"op": "set_date", "value": "1973-06-11", "confidence": "low",
                                   "why": "w"}],
               [judge(TITLES_FLAG, "real-fixed-by-action")])


def test_accept_applies_failed_gate_edits_but_not_propose_only(rig):
    rig.pre()
    rig.proposal(ACCEPTABLE)
    rig.stub(POST_NO_B)
    out = rig.accept()
    assert (out.outcome, out.detail) == (ACCEPTED, ""), out
    ov = read_overrides(rig.ws)
    assert ov.exclude == ["b.mp3"] and ov.date is None
    rec = read_record(rig.ws)
    assert rec.outcome == "accepted" and rec.digest == show_digest(rig.ws)
    assert [a["op"] for a in rec.applied] == ["exclude"]
    assert out.changes == ["- b.mp3 (0:30) B"]


# An include whose file lands with a placeholder title is restored by the apply backstop,
# in every mode. Only the accept message names the way forward (Shawn's ruling, option iii).
INCLUDE_X = V([ed("include", "low", file="x.mp3")], [judge(TITLES_FLAG, "real-fixed-by-action")])
X_EXCLUDED = [{"filename": "x.mp3", "reasons": ["short"], "duration_sec": 20.0}]


def _include_rig(rig, title="Track 3"):
    show = mk([A, B, C], flags=(TITLES_FLAG,))
    write_artifact(rig.ws.show, show.model_copy(update={"excluded_files": X_EXCLUDED}))
    rig.stub(mk([A, B, C, T("x.mp3", title, 20.0, "unresolved")]))


def test_accept_placeholder_include_restore_names_the_way_forward(rig):
    _include_rig(rig)
    rig.proposal(INCLUDE_X)
    out = rig.accept()
    assert out.outcome == FAILED, out
    assert out.detail == (
        "accept restored: x.mp3: included with a placeholder title 'Track 3'\n"
        f"to include it anyway: llama fix {rig.slug} --include x.mp3, then find its number "
        f"with llama show {rig.slug} --tracks and run "
        f'llama fix {rig.slug} --set-title N="<title>"')


def test_accept_hint_quotes_a_filename_with_a_space_and_an_apostrophe(rig):
    name = "01 Goin' Down.mp3"
    show = mk([A, B, C], flags=(TITLES_FLAG,))
    write_artifact(rig.ws.show, show.model_copy(update={"excluded_files": [
        {"filename": name, "reasons": ["short"], "duration_sec": 20.0}]}))
    rig.stub(mk([A, B, C, T(name, name, 20.0, "unresolved")]))
    rig.proposal(V([ed("include", "low", file=name)],
                   [judge(TITLES_FLAG, "real-fixed-by-action")]))
    out = rig.accept()
    assert out.outcome == FAILED, out
    hint = out.detail.split("\nto include it anyway: ", 1)[1]
    step1 = hint.split(", then find", 1)[0]
    assert shlex.split(step1) == ["llama", "fix", rig.slug, "--include", name], hint
    assert shlex.split(hint.split("with ", 1)[1].split(" and run ")[0])[:3] == [
        "llama", "show", rig.slug]


def test_a_title_naming_the_phrase_makes_no_bogus_hint(rig):
    # a.mp3 is not an include; its set_title line carries the phrase in the title
    rig.pre()
    rig.proposal(V([ed("set_title", "low", file="a.mp3",
                       title="Foo: included with a placeholder title 'bar")],
                   [judge(TITLES_FLAG, "real-fixed-by-action")]))
    rig.stub(mk([T("a.mp3", "Other", 300.0), C]))
    out = rig.accept()
    assert out.outcome == FAILED, out
    assert "to include it anyway" not in out.detail


def test_accept_restore_for_another_reason_has_no_include_hint(rig):
    rig.pre()
    rig.proposal(ACCEPTABLE)
    rig.stub(mk([T("a.mp3", "Bertha", 300.0), C]))
    out = rig.accept()
    assert out.outcome == FAILED and "to include it anyway" not in out.detail


def test_auto_placeholder_include_restore_is_unchanged(rig):
    # The gate predicts a real title (the set_title), so apply runs; gather lands a
    # placeholder and the backstop restores. The auto record carries the bare diff.
    _include_rig(rig)
    rig.queue(V([ed("include", "high", file="x.mp3"),
                 ed("set_title", "high", file="x.mp3", title="Tuning")],
                [judge(TITLES_FLAG, "real-fixed-by-action")]))
    out = rig.run()
    rec = read_record(rig.ws)
    assert out.outcome == PROPOSAL, (out, rec.gate, rec.result)
    assert rec.result.get("status") == "restored", (rec.gate, rec.result)
    assert "x.mp3: included with a placeholder title 'Track 3'" in rec.result["diff"]
    assert "to include it anyway" not in json.dumps(rec.model_dump())
    assert "to include it anyway" not in out.detail


def test_accept_with_expected_at_applies_only_the_record_that_was_shown(rig, monkeypatch):
    rig.pre()
    rec = rig.proposal(ACCEPTABLE)
    rig.stub(POST_NO_B)
    write_record(rig.ws, rec.model_copy(update={"at": "2099-01-01T00:00:00+00:00"}))
    before = rig.ws.show.read_bytes()
    _no_apply(monkeypatch)
    out = accept_proposal(rig.ctx, rig.entry(), expected_at=rec.at)
    assert (out.outcome, out.detail) == (
        NO_PROPOSAL, "proposal changed since it was shown; re-run")
    assert rig.ws.show.read_bytes() == before and not rig.ws.overrides.exists()


def test_accept_with_a_matching_expected_at_applies(rig):
    rig.pre()
    rec = rig.proposal(ACCEPTABLE)
    rig.stub(POST_NO_B)
    assert accept_proposal(rig.ctx, rig.entry(), expected_at=rec.at).outcome == ACCEPTED


def test_accept_still_held_detail(rig):
    rig.pre()
    rig.proposal(ACCEPTABLE)
    rig.stub(mk([A, C], flags=[CLOSER_FLAG]))
    out = rig.accept()
    assert (out.outcome, out.detail) == (ACCEPTED, "still held")


def test_accept_of_only_propose_only_edits_is_no_proposal(rig, monkeypatch):
    """C3: accept never calls apply with nothing applicable."""
    rig.pre()
    rec = rig.proposal(V([{"op": "set_date", "value": "1973-06-11", "confidence": "high",
                           "why": "w"}], [judge(TITLES_FLAG, "undecidable")], kind="hold"))
    _no_apply(monkeypatch)
    assert rig.accept().outcome == NO_PROPOSAL
    assert read_record(rig.ws) == rec


def test_accept_without_a_proposal_is_no_proposal(rig, monkeypatch):
    rig.pre()
    _no_apply(monkeypatch)
    assert rig.accept().outcome == NO_PROPOSAL                       # no record
    write_record(rig.ws, AdjudicationRecord(outcome="malformed", digest=show_digest(rig.ws)))
    assert rig.accept().outcome == NO_PROPOSAL
    write_record(rig.ws, AdjudicationRecord(outcome="applied", digest=show_digest(rig.ws),
                                            held_proposal={"flags": [], "edits": []}))
    assert rig.accept().outcome == NO_PROPOSAL
    write_record(rig.ws, AdjudicationRecord(outcome="proposal", dry_run=True,
                                            digest=show_digest(rig.ws), verdict=ACCEPTABLE))
    assert rig.accept().outcome == NO_PROPOSAL


def test_accept_refuses_stale_digest(rig, monkeypatch):
    rig.pre()
    rec = rig.proposal(ACCEPTABLE)
    write_artifact(rig.ws.overrides, Overrides(venue="Kezar"))
    _no_apply(monkeypatch)
    assert rig.accept().outcome == PROPOSAL_STALE
    assert read_record(rig.ws) == rec


def test_accept_race_show_changes_between_check_and_write_refuses(rig, monkeypatch):
    rig.pre()
    rec = rig.proposal(ACCEPTABLE)
    rig.stub(POST_NO_B)
    real = runner.build_bundle

    def racing(show_ws, ia, config):
        b = real(show_ws, ia, config)
        write_artifact(show_ws.overrides, Overrides(venue="Kezar"))
        return b
    monkeypatch.setattr(runner, "build_bundle", racing)
    out = rig.accept()
    assert out.outcome == CHANGED
    assert read_record(rig.ws) == rec and rig.stages == []
    assert read_overrides(rig.ws) == Overrides(venue="Kezar")
    assert read_model(rig.ws.show, Show).needs_review


def test_accept_revalidates_targets(rig, monkeypatch):
    rig.pre()
    rec = rig.proposal(ACCEPTABLE)
    # The same digest, but b.mp3 is no longer a track in the bundle the accept builds.
    real = runner.build_bundle

    def gone(show_ws, ia, config):
        b = real(show_ws, ia, config)
        return b.__class__(**{**b.__dict__, "show": b.show.model_copy(
            update={"tracks": [t for t in b.show.tracks if t.filename != "b.mp3"]})})
    monkeypatch.setattr(runner, "build_bundle", gone)
    _no_apply(monkeypatch)
    out = rig.accept()
    assert out.outcome == MALFORMED and "b.mp3" in out.detail
    assert read_record(rig.ws) == rec


def test_accept_switch_refuses_with_keyed_entries(rig, monkeypatch):
    rig.pre()
    write_artifact(rig.ws.overrides, Overrides(exclude=["zz.mp3"]))
    rec = rig.proposal(SWITCH)
    _no_apply(monkeypatch)
    out = rig.accept()
    assert out.outcome == FAILED
    assert out.detail == (f"{rig.slug}: overrides.json has filename-keyed entries "
                          f"(exclude: zz.mp3); clear them first with: "
                          f"llama fix {rig.slug} --unexclude zz.mp3")
    assert read_record(rig.ws) == rec


def test_accept_switch_coverage_failure_restores_and_names_fix_recording(rig):
    rig.pre(tracks=[T("a.mp3", "Bertha", 300.0), B, T("c.mp3", "Sugaree", 400.0)])
    rig.complaints("gd73-sib", 1)
    rec = rig.proposal(SWITCH)
    before = tree_bytes(rig.ws.dir)
    rig.stub(mk([T("a.mp3", "Bertha", 300.0), T("d.mp3", "Dark Star", 900.0)],
                ident="gd73-sib"), select="gd73-sib")
    out = rig.accept()
    assert out.outcome == FAILED, out
    assert out.detail == ("accept restored: missing title: Sugaree not in the new recording; "
                          f"to switch anyway: llama fix {rig.slug} --recording gd73-sib")
    assert read_record(rig.ws) == rec and tree_bytes(rig.ws.dir) == before


def _accepted_switch(rig):
    """A switch proposal (held back by sibling complaints) whose accept commits."""
    tracks = [T("a.mp3", "Bertha", 300.0), B, T("c.mp3", "Sugaree", 400.0)]
    rig.pre(tracks=tracks)
    rig.complaints("gd73-sib", 1)
    rig.proposal(SWITCH)
    rig.stub(mk(tracks, ident="gd73-sib"), select="gd73-sib")


def test_accept_switch_records_the_pin_as_the_operators(rig):
    # Shawn's ruling (2026-11-07): an accepted switch is his choice of recording.
    _accepted_switch(rig)
    assert rig.accept().outcome == ACCEPTED
    ov = read_overrides(rig.ws)
    assert (ov.recording, ov.recording_source) == ("gd73-sib", "operator")


@pytest.mark.parametrize("result", ["restored", "refused", "transient", "changed"])
def test_accept_non_commit_leaves_record_unchanged(rig, monkeypatch, result):
    rig.pre()
    rec = rig.proposal(ACCEPTABLE)
    if result == "restored":
        rig.stub(mk([T("a.mp3", "Bertha", 300.0), C]))
        want = (FAILED, "accept restored: a.mp3: title 'A' -> 'Bertha' (not predicted)")
    elif result == "refused":
        rig.stub(POST_NO_B, fail=LlamaError("station copy does not pair"))
        want = (FAILED, "station copy does not pair")
    elif result == "transient":
        rig.stub(POST_NO_B, fail=IAError("download of b.mp3 failed"))
        want = (FAILED, "transient: download of b.mp3 failed; try again")
    else:
        rig.stub(POST_NO_B)
        real = runner.build_bundle

        def racing(show_ws, ia, config):
            b = real(show_ws, ia, config)
            write_artifact(show_ws.overrides, Overrides(venue="Kezar"))
            return b
        monkeypatch.setattr(runner, "build_bundle", racing)
        want = (CHANGED, None)
    out = rig.accept()
    assert out.outcome == want[0], out
    if want[1] is not None:
        assert out.detail == want[1]
    assert read_record(rig.ws) == rec


def test_accept_ratelimited_propagates_and_record_unchanged(rig):
    rig.pre()
    rec = rig.proposal(ACCEPTABLE)
    rig.stub(POST_NO_B, fail=RateLimited("window"))
    with pytest.raises(RateLimited):
        rig.accept()
    assert read_record(rig.ws) == rec


def test_accept_unexpected_error_is_failed(rig):
    rig.pre()
    rec = rig.proposal(ACCEPTABLE)
    rig.stub(POST_NO_B, fail=OSError("disk"))
    out = rig.accept()
    assert out.outcome == FAILED and "disk" in out.detail
    assert read_record(rig.ws) == rec


def test_accept_held_proposal_overrules_leftover_flags(rig):
    rig.pre(flags=[TITLES_FLAG, VENUE_FLAG])
    rig.stub(mk([A, C], flags=[VENUE_FLAG]))
    rig.queue(HELD_VERDICT)
    assert rig.run().outcome == APPLIED_HELD
    rig.stub(mk([A, C]))
    out = rig.accept()
    assert (out.outcome, out.detail) == (ACCEPTED, ""), out
    rules = read_overrides(rig.ws).overrules
    assert [(r.kind, r.source) for r in rules] == [("venue", "adjudicate")]
    rec = read_record(rig.ws)
    # the index of the stored verdict's own overrule edit for that flag key
    assert rec.outcome == "accepted" and rec.applied == [
        {"index": 1, "op": "overrule", "target": VENUE_FLAG,
         "evidence_kinds": ["taper-description"]}]
    assert not read_model(rig.ws.show, Show).needs_review


def test_hook_enabled_tristate():
    assert hook_enabled(Config(), None) and not hook_enabled(Config(), False)
    assert hook_enabled(Config(), True)
    off = Config.model_validate({"adjudicate": {"enabled": False}})
    assert not hook_enabled(off, None) and hook_enabled(off, True)


# ---------------------------------------------------------------- fix round 1

def test_accept_record_index_points_into_the_stored_verdict(rig):
    """I1: a propose-only edit first; the exclude keeps its own index (1), not 0."""
    rig.pre()
    rig.proposal(V([{"op": "set_date", "value": "1973-06-11", "confidence": "low", "why": "w"},
                    exclude_b("low")], [judge(TITLES_FLAG, "real-fixed-by-action")]))
    rig.stub(POST_NO_B)
    out = rig.accept()
    assert out.outcome == ACCEPTED, out
    rec = read_record(rig.ws)
    assert rec.applied == [{"index": 1, "op": "exclude", "target": "b.mp3",
                            "evidence_kinds": ["taper-description"]}]
    assert rec.verdict["edits"][1]["op"] == "exclude"


def test_held_proposal_overrule_without_its_own_edit_has_index_none(rig):
    rig.pre(flags=[TITLES_FLAG, VENUE_FLAG])
    rig.stub(mk([A, C], flags=[VENUE_FLAG]))
    rig.queue(V([exclude_b()], [judge(TITLES_FLAG, "real-fixed-by-action"),
                                judge(VENUE_FLAG, conf="low")]))
    assert rig.run().outcome == APPLIED_HELD
    rig.stub(mk([A, C]))
    out = rig.accept()
    assert out.outcome == ACCEPTED, out
    assert read_record(rig.ws).applied == [
        {"index": None, "op": "overrule", "target": VENUE_FLAG, "evidence_kinds": []}]


def test_trial_ratelimited_propagates_with_nothing_written(rig):
    """I2."""
    rig.pre()
    old = AdjudicationRecord(outcome="malformed", digest="old")
    write_record(rig.ws, old)
    before = tree_bytes(rig.ws.dir)
    rig.stub(POST_NO_B, fail=RateLimited("w"))
    rig.queue(EXCLUDE_B)
    with pytest.raises(RateLimited):
        rig.run(dry_run=True, trial_policy=lambda v, g: True)
    assert read_record(rig.ws) == old and tree_bytes(rig.ws.dir) == before


def test_trial_showchanged_is_changed_with_nothing_written(rig):
    rig.pre()
    rig.stub(POST_NO_B)
    rig.provider.before = lambda: write_artifact(rig.ws.overrides, Overrides(venue="Kezar"))
    rig.queue(EXCLUDE_B)
    out = rig.run(dry_run=True, trial_policy=lambda v, g: True)
    assert out.outcome == CHANGED and not rig.ws.adjudication.exists()
    assert rig.stages == []


@pytest.mark.parametrize("force", [False, True])
def test_corrupt_show_json_is_failed_before_any_call(rig, force):
    """M1."""
    rig.pre()
    entry = rig.entry()                     # resolved before the corruption (as a batch is)
    rig.ws.show.write_text("{corrupt")
    out = adjudicate_show(rig.ctx, entry, force=force)
    assert out.outcome == FAILED and out.detail.startswith("read show: ")
    assert rig.calls() == 0 and not rig.ws.adjudication.exists()


@pytest.mark.parametrize("bad", [
    {"outcome": "proposal", "verdict": {"edits": "nonsense"}},
    {"outcome": "applied", "verdict": EXCLUDE_B,
     "held_proposal": {"flags": [], "edits": [{"op": "overrule"}]}},
    {"outcome": "applied", "verdict": EXCLUDE_B,
     "held_proposal": {"flags": [{"flag": VENUE_FLAG, "judgement": "x"}],
                       "edits": [{"op": "overrule", "flag": VENUE_FLAG, "confidence": "low",
                                  "why": "w"}]}},
])
def test_unreadable_stored_proposal_is_no_proposal(rig, monkeypatch, bad):
    """M2."""
    rig.pre()
    rec = AdjudicationRecord(digest=show_digest(rig.ws), **bad)
    write_record(rig.ws, rec)
    _no_apply(monkeypatch)
    out = rig.accept()
    assert out.outcome == NO_PROPOSAL and out.detail.startswith("stored proposal unreadable: ")
    assert read_record(rig.ws) == rec


def test_rehold_at_runner_level_clears_and_records_reheld(rig):
    """M6: a successful re-hold auto-overrule; the record is the final state."""
    rig.pre(flags=[TITLES_FLAG, VENUE_FLAG])
    rig.stub(mk([A, C], flags=[VENUE_FLAG]))
    rig.queue(V([exclude_b()], [judge(TITLES_FLAG, "real-fixed-by-action"),
                                judge(VENUE_FLAG, conf="medium")]))
    out = rig.run()
    assert out.outcome == APPLIED, out
    rec = read_record(rig.ws)
    assert rec.digest == show_digest(rig.ws) and is_current(rig.ws)
    assert rec.held_proposal is None and rec.result["reheld"] == [VENUE_FLAG]
    assert rig.stages == ["gather", "package"]
    assert [(r.kind, r.source) for r in read_overrides(rig.ws).overrules] == [
        ("venue", "adjudicate")]
    assert not read_model(rig.ws.show, Show).needs_review


def test_accept_delivered_changed(tmp_path, monkeypatch):
    """M6: accept's delivered_changed, by digest, on a venue-only accept."""
    rig = Rig(tmp_path, monkeypatch, delivered=True)
    tracks = [T("a.mp3", "A", 300.0), T("b.mp3", "B", 30.0), T("c.mp3", "C", 400.0)]
    rig.pre(flags=[VENUE_FLAG], tracks=tracks)
    rig.proposal(V([ed("venue", "low", evidence=[ev("Recorded at RFK Stadium")],
                       venue="RFK Stadium, Washington")], [judge(VENUE_FLAG, conf="medium")]))
    rig.stub(mk(tracks, venue="RFK Stadium, Washington"))
    out = rig.accept()
    assert out.outcome == ACCEPTED, out
    assert out.changes == [] and out.delivered_changed is True


def test_accept_not_delivered_is_not_delivered_changed(rig):
    rig.pre()
    rig.proposal(ACCEPTABLE)
    rig.stub(POST_NO_B)
    out = rig.accept()
    assert out.outcome == ACCEPTED and out.delivered_changed is False


# ---------------------------------------------------------------- sibling coverage (R2)

def test_a_fuller_sibling_without_a_switch_holds_with_the_proposal_stored(rig, monkeypatch):
    """An otherwise auto verdict (EXCLUDE_B) on a show whose considered sibling keeps more
    tracks lands as a proposal carrying the coverage veto; nothing is applied."""
    rig.pre()
    write_artifact(rig.ws.selection, {"identifier": "gd73", "scores": {
        "gd73": {"lineage": "sbd", "kept_tracks": 3, "score": 3.0},
        "gd73-sib": {"lineage": "sbd", "kept_tracks": 4, "score": 2.0}}})
    _no_apply(monkeypatch)
    before = tree_bytes(rig.ws.dir)
    out = rig.proposal(EXCLUDE_B)
    assert out.vetoes == ["considered recording gd73-sib keeps more (4 tracks, 0 s) than the "
                          "current (3 tracks, 0 s); no switch_recording edit"]
    assert all(g["passed"] for g in out.gate) and out.applied == []
    assert read_overrides(rig.ws).exclude == [] and rig.stages == []
    after = tree_bytes(rig.ws.dir)
    assert {k: v for k, v in after.items() if k != "adjudication.json"} == before


# ---------------------------------------------------------------- placeholder veto (R3)

SONG_FLAG = "research asserts unknown song: Dark Star"
SONG_OVERRULE = V([ed("overrule", flag=SONG_FLAG, evidence=[ev("Recorded at RFK Stadium")])],
                  [judge(SONG_FLAG)], kind="overrule")


def test_a_research_song_overrule_over_a_placeholder_title_holds_with_the_proposal_stored(
        rig, monkeypatch):
    """An otherwise auto overrule verdict on a show shipping a `Track N` title lands as a
    proposal with the overrule edit not passed; nothing is applied."""
    rig.pre(flags=(SONG_FLAG,), tracks=(T("a.mp3", "Bertha", 300.0), T("b.mp3", "Track 2", 30.0),
                                       T("c.mp3", "Sugaree", 400.0)))
    _no_apply(monkeypatch)
    before = tree_bytes(rig.ws.dir)
    out = rig.proposal(SONG_OVERRULE)
    assert out.vetoes == []
    assert [(g["bar"], g["passed"], g["reason"]) for g in out.gate] == [
        ("propose-only", False, "research-song overrule while 1 shipped title(s) are "
                                "placeholders (e.g. b.mp3: 'Track 2')")]
    assert out.applied == [] and rig.stages == []
    assert read_overrides(rig.ws).overrules == []
    after = tree_bytes(rig.ws.dir)
    assert {k: v for k, v in after.items() if k != "adjudication.json"} == before
