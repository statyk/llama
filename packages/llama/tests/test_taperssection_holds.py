"""Task 10: the taperssection gather holds (spec "Holds").

Two new review flags, raised by gather for a `ts-` show only:
- `unclassified lineage for <name> (allowed: <lineages>): <identifier>` when the
  selected recording's verdict under the CURRENT entry is unknown (recomputed from
  `candidate.recordings` the way select classifies; no stored field);
- `possible misattribution: <reason>` when the winnow assessment's `attribution` is
  "suspect", or None (the scorer gave no verdict).
Each has an overrule kind (`lineage-unknown`, raw identifier subject;
`misattribution`, no subject), an adjudicator bar (never; medium) and a replay
flag family; replay reproduces both from provenance. A selected recording that the
current entry forbids raises (ruling R27): no path re-gathers a forbidden tape.
"""
import json
from pathlib import Path

import pytest

from llama.adjudicator.gate import OVERRULE_BAR, overrule_bar
from llama.config import Config, TaperssectionArtist, TaperssectionConfig
from llama.errors import LlamaError
from llama.models import (Candidate, Overrides, Provenance, QualityAssessment,
                          RecordingSummary, Show)
from llama.overrules import FlagKey, flag_key, records_for
from llama.replay import compute_legs, config_fingerprint, flag_family
from llama.stages.gather import compute_gather, run_gather
from llama.taperssection import Allowlist
from llama.workspace import ShowWorkspace, read_json, read_model, write_artifact

FIXTURES = Path(__file__).parent / "fixtures"
G_FIXTURE = "jg82-06-24.079428.jgb.sbd.late.sbeok.t-flac16"
G_DATE = "1982-06-24"
PID = f"ts-jerry-garcia/{G_DATE}"

UNK = "jgb1982-06-24.flac16"                          # no lineage evidence: unknown
AUD = "jgb1982-06-24.schoeps.flac16"                  # Schoeps source: aud
SBD = "jgb1982-06-24.sbd.flac16"                      # sbd

GARCIA = TaperssectionArtist(name="Jerry Garcia", creators=["Garcia, Jerry"],
                             lineages=["aud", "matrix"])
UNK_FLAG = f"unclassified lineage for Jerry Garcia (allowed: aud, matrix): {UNK}"
NO_VERDICT = "possible misattribution: scorer gave no attribution verdict"


def _al(*entries):
    return Allowlist.from_config(TaperssectionConfig(artists=list(entries or (GARCIA,))))


def _md() -> dict:
    md = json.loads((FIXTURES / f"{G_FIXTURE}.json").read_text())
    md["metadata"]["creator"] = "Garcia, Jerry"
    return md


class _IA:
    """Every identifier serves the same Garcia fixture item."""

    def metadata(self, identifier):
        return _md()


def _rec(ident, source):
    return RecordingSummary(identifier=ident, creator="Garcia, Jerry", date=G_DATE,
                            source=source)


R_UNK = _rec(UNK, "DAT master")
R_AUD = _rec(AUD, "Schoeps CMC6/MK4 > DAT")
R_SBD = _rec(SBD, "SBD > DAT")


def _cand(*recs, collection="ts-jerry-garcia"):
    return Candidate(performance_id=f"{collection}/{G_DATE}", collection=collection,
                     date=G_DATE, recordings=list(recs))


def _qa(attribution="ok", reason=None, pid=PID):
    return QualityAssessment(performance_id=pid, quality_score=8.0, rationale="r",
                             attribution=attribution, attribution_reason=reason)


def _gather(tmp_path, cand, ident, *, assessment=None, allowlist=None, name="show"):
    return compute_gather(ShowWorkspace(tmp_path / name), _IA(), None, cand, ident,
                          allowlist=allowlist if allowlist is not None else _al(),
                          assessment=assessment)


def _ts_flags(show: Show) -> list[str]:
    return [f for f in show.review_flags
            if f.startswith(("unclassified lineage for", "possible misattribution:"))]


# ---------------------------------------------------------------- gather flags

def test_gather_flags_selected_unknown(tmp_path):
    res = _gather(tmp_path, _cand(R_UNK), UNK, assessment=_qa())
    assert _ts_flags(res.show) == [UNK_FLAG]
    assert res.show.needs_review
    # An allowed selection raises no lineage flag.
    ok = _gather(tmp_path, _cand(R_AUD, R_UNK), AUD, assessment=_qa(), name="ok")
    assert _ts_flags(ok.show) == []


def test_gather_flags_pinned_unknown_beside_allowed_sibling(tmp_path):
    # Checkpoint A ruling (a): select picks a PINNED unknown with no hold (Task 9);
    # gather is what holds it, allowed sibling or not.
    res = _gather(tmp_path, _cand(R_AUD, R_UNK), UNK, assessment=_qa())
    assert _ts_flags(res.show) == [UNK_FLAG]


def test_entry_allowing_every_lineage_never_flags_unknown(tmp_path):
    every = GARCIA.model_copy(update={"lineages": ["aud", "sbd", "matrix", "fm", "webcast"]})
    res = _gather(tmp_path, _cand(R_UNK), UNK, assessment=_qa(), allowlist=_al(every))
    assert _ts_flags(res.show) == []


def test_selected_not_among_recordings_holds_as_unknown(tmp_path):
    # Fail closed: a selection the candidate does not list cannot be classified.
    res = _gather(tmp_path, _cand(R_AUD), UNK, assessment=_qa())
    assert _ts_flags(res.show) == [UNK_FLAG]


def test_gather_flags_misattribution(tmp_path):
    res = _gather(tmp_path, _cand(R_AUD), AUD,
                  assessment=_qa("suspect", "creator  reads\n'Garcia Tribute Band'"))
    assert _ts_flags(res.show) == ["possible misattribution: creator reads 'Garcia Tribute Band'"]
    blank = _gather(tmp_path, _cand(R_AUD), AUD, assessment=_qa("suspect", None), name="b")
    assert _ts_flags(blank.show) == ["possible misattribution: scorer gave no reason"]


def test_gather_flags_missing_attribution(tmp_path):
    # The fake scorer omits the field: the assessment parses with attribution None.
    qa = QualityAssessment.model_validate({"performance_id": PID, "quality_score": 8.0,
                                           "rationale": "r"})
    assert qa.attribution is None
    res = _gather(tmp_path, _cand(R_AUD), AUD, assessment=qa)
    assert _ts_flags(res.show) == [NO_VERDICT]
    # No assessment at all (an old provenance.json) fails closed the same way.
    none = _gather(tmp_path, _cand(R_AUD), AUD, assessment=None, name="none")
    assert _ts_flags(none.show) == [NO_VERDICT]


def test_both_flags_in_order(tmp_path):
    res = _gather(tmp_path, _cand(R_UNK), UNK, assessment=_qa("suspect", "tribute act"))
    assert _ts_flags(res.show) == [UNK_FLAG, "possible misattribution: tribute act"]
    assert res.show.review_flags[-2:] == [UNK_FLAG, "possible misattribution: tribute act"]


def test_lma_show_never_flagged(tmp_path):
    lma = _cand(R_UNK, collection="JerryGarcia")
    res = _gather(tmp_path, lma, UNK, assessment=_qa(None, None, pid=lma.performance_id))
    assert _ts_flags(res.show) == []
    # Same flags as a gather without the new keyword at all.
    base = compute_gather(ShowWorkspace(tmp_path / "base"), _IA(), None, lma, UNK)
    assert res.show == base.show


def test_run_gather_threads_assessment(tmp_path):
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, _IA(), None, _cand(R_AUD), AUD, allowlist=_al(), assessment=None)
    assert _ts_flags(show) == [NO_VERDICT]
    assert read_model(sws.show, Show).review_flags == show.review_flags


# ---------------------------------------------------------------- R27: forbidden selection

def test_gather_raises_on_forbidden_selection(tmp_path):
    with pytest.raises(LlamaError, match=(rf"^{PID}: selected recording {SBD} is forbidden by "
                                          r"the taperssection policy; re-select with redo "
                                          r"--from select$")):
        _gather(tmp_path, _cand(R_SBD, R_AUD), SBD, assessment=_qa())
    excl = GARCIA.model_copy(update={"exclude": ["schoeps"]})
    with pytest.raises(LlamaError, match="forbidden by the taperssection policy"):
        _gather(tmp_path, _cand(R_AUD), AUD, assessment=_qa(), allowlist=_al(excl))
    sws = ShowWorkspace(tmp_path / "rg")
    with pytest.raises(LlamaError, match="re-select with redo --from select"):
        run_gather(sws, _IA(), None, _cand(R_SBD), SBD, allowlist=_al(), assessment=_qa())
    assert not sws.show.exists()


def test_lma_sbd_selection_never_raises(tmp_path):
    lma = _cand(R_SBD, collection="JerryGarcia")
    res = _gather(tmp_path, lma, SBD, assessment=None)
    assert res.show.identifier == SBD


# ---------------------------------------------------------------- overrules

def test_flag_keys_and_families(tmp_path):
    show = _gather(tmp_path, _cand(R_UNK), UNK, assessment=_qa("suspect", "x")).show
    assert flag_key(UNK_FLAG, show) == FlagKey("lineage-unknown", (UNK,))
    assert flag_key("possible misattribution: anything (at all): x", show) == \
        FlagKey("misattribution", None)
    assert flag_family(UNK_FLAG) == "lineage-unknown"
    assert flag_family(NO_VERDICT) == "misattribution"


def test_overrule_clears_each(tmp_path):
    res = _gather(tmp_path, _cand(R_UNK), UNK, assessment=_qa("suspect", "tribute act"))
    ts = _ts_flags(res.show)
    assert len(ts) == 2
    recs = records_for(ts, res.show, source="fix", at="2026-11-09T00:00:00Z")
    assert [(r.kind, r.subject) for r in recs] == [("lineage-unknown", [UNK]),
                                                   ("misattribution", None)]
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, Overrides(overrules=recs))
    again = compute_gather(sws, _IA(), None, _cand(R_UNK), UNK, allowlist=_al(),
                           assessment=_qa("suspect", "another reason"))
    assert _ts_flags(again.show) == []
    assert f"overruled: {UNK_FLAG}" in again.notes
    assert "overruled: possible misattribution: another reason" in again.notes
    # The lineage overrule is scoped to the identifier: another unknown tape holds.
    other = "jgb1982-06-24.other.flac16"
    moved = compute_gather(sws, _IA(), None, _cand(_rec(other, "DAT")), other,
                           allowlist=_al(), assessment=_qa())
    assert [f for f in moved.show.review_flags if f.startswith("unclassified")] == [
        f"unclassified lineage for Jerry Garcia (allowed: aud, matrix): {other}"]


def test_adjudicator_bar_lineage_never(tmp_path):
    assert OVERRULE_BAR["lineage-unknown"] == "never"
    assert OVERRULE_BAR["misattribution"] == "medium"
    show = _gather(tmp_path, _cand(R_UNK), UNK, assessment=_qa("suspect", "x")).show
    assert overrule_bar(UNK_FLAG, show) == "never"
    assert overrule_bar("possible misattribution: x", show) == "medium"


# ---------------------------------------------------------------- replay

def _library_show(root: Path, cand: Candidate, ident: str, assessment) -> ShowWorkspace:
    sws = ShowWorkspace(root / "lib" / "shows" / "ts-jerry-garcia-1982-06-24")
    write_artifact(sws.provenance, Provenance(performance_id=cand.performance_id, run="r",
                                              candidate=cand, assessment=assessment,
                                              processed_at="2026-11-09T00:00:00+00:00"))
    res = compute_gather(ShowWorkspace(root / "first"), _IA(), None, cand, ident,
                         allowlist=_al(), assessment=assessment)
    write_artifact(sws.show, res.show)
    return sws


def _config(root, *entries):
    return Config(root=root, taperssection=TaperssectionConfig(artists=list(entries or (GARCIA,))))


def test_replay_keeps_both_flags(tmp_path):
    cand = _cand(R_AUD, R_UNK)
    sws = _library_show(tmp_path, cand, UNK, _qa("suspect", "tribute act"))
    assert _ts_flags(read_model(sws.show, Show)) == [UNK_FLAG,
                                                     "possible misattribution: tribute act"]
    legs = compute_legs(sws, config=_config(tmp_path), ia=_IA(), slfm=None,
                        scratch=tmp_path / "scratch" / "x")
    assert _ts_flags(legs.gather.show) == [UNK_FLAG, "possible misattribution: tribute act"]
    assert UNK_FLAG in legs.flags
    # A provenance assessment with no attribution verdict replays as suspect.
    sws2 = _library_show(tmp_path / "b", _cand(R_AUD), AUD,
                         QualityAssessment(performance_id=PID, quality_score=8.0, rationale="r"))
    legs2 = compute_legs(sws2, config=_config(tmp_path), ia=_IA(), slfm=None,
                         scratch=tmp_path / "scratch" / "y")
    assert _ts_flags(legs2.gather.show) == [NO_VERDICT]


def test_replay_raises_on_selection_forbidden_by_tightened_entry(tmp_path):
    sws = _library_show(tmp_path, _cand(R_AUD), AUD, _qa())
    tightened = GARCIA.model_copy(update={"exclude": ["schoeps"]})
    with pytest.raises(LlamaError, match=f"selected recording {AUD} is forbidden"):
        compute_legs(sws, config=_config(tmp_path, tightened), ia=_IA(), slfm=None,
                     scratch=tmp_path / "scratch" / "x")


# ---------------------------------------------------------------- fingerprint

def test_fingerprint_unchanged_when_empty(monkeypatch):
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)
    # Today's payload, verbatim: an empty allowlist adds no key.
    import hashlib
    cfg = Config()
    payload = {"audio_format": cfg.audio_format, "structure": cfg.structure.model_dump(),
               "jerrybase": cfg.jerrybase.model_dump(), "setlistfm_configured": False}
    want = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    assert config_fingerprint(cfg) == want
    assert config_fingerprint(Config(taperssection=TaperssectionConfig(artists=[]))) == want


def test_fingerprint_changes_on_allowlist_edit(monkeypatch, tmp_path):
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)
    empty = config_fingerprint(Config())
    one = config_fingerprint(_config(tmp_path))
    assert one != empty
    renamed = GARCIA.model_copy(update={"name": "Jerry Garcia Band"})
    assert config_fingerprint(_config(tmp_path, renamed)) != one
    widened = GARCIA.model_copy(update={"lineages": ["aud", "matrix", "sbd"]})
    assert config_fingerprint(_config(tmp_path, widened)) != one
    with_jb = GARCIA.model_copy(update={"jerrybase": "Jerry Garcia Band"})
    assert config_fingerprint(_config(tmp_path, with_jb)) != one
    # A `note`-only edit changes nothing.
    noted = GARCIA.model_copy(update={"note": "a comment"})
    assert config_fingerprint(_config(tmp_path, noted)) == one


def test_process_show_passes_assessment_to_gather(tmp_path, monkeypatch):
    import llama.pipeline as pipeline
    from llama.ledger import Ledger
    from llama.models import ShortlistEntry
    from llama.workspace import RunWorkspace
    seen = {}
    qa = _qa("suspect", "tribute act")
    monkeypatch.setattr(pipeline, "run_select_recording", lambda *a, **k: AUD)

    def gather(*a, **k):
        seen.update(k)
        raise LlamaError("stop")
    monkeypatch.setattr(pipeline, "run_gather", gather)
    entry = ShortlistEntry(rank=1, candidate=_cand(R_AUD), assessment=qa)
    with pytest.raises(LlamaError):
        pipeline.process_show(RunWorkspace(tmp_path, "r"), _IA(), Ledger(tmp_path / "l.jsonl"),
                              entry, {"extract_setlist": None}, "r", allowlist=_al())
    assert seen["assessment"] is entry.assessment


class _NoFetchIA:
    def metadata(self, identifier):
        raise AssertionError(f"metadata fetched for {identifier}")


def test_forbidden_selection_raises_before_any_fetch(tmp_path):
    # Review round 1 (ruling R29.2): under replay a CacheOnlyIA miss must not mask the
    # re-select message, so the check runs before `ia.metadata`.
    from llama.replay import CacheMiss
    with pytest.raises(LlamaError, match="re-select with redo --from select"):
        compute_gather(ShowWorkspace(tmp_path / "s"), _NoFetchIA(), None, _cand(R_SBD), SBD,
                       allowlist=_al(), assessment=_qa())

    class _MissIA:
        def metadata(self, identifier):
            raise CacheMiss(identifier)
    sws = _library_show(tmp_path, _cand(R_AUD), AUD, _qa())
    tightened = GARCIA.model_copy(update={"exclude": ["schoeps"]})
    with pytest.raises(LlamaError, match=f"selected recording {AUD} is forbidden"):
        compute_legs(sws, config=_config(tmp_path, tightened), ia=_MissIA(), slfm=None,
                     scratch=tmp_path / "scratch" / "x")
    # A ts key without its allowlist also fails closed before any fetch.
    with pytest.raises(LlamaError, match="needs an allowlist"):
        compute_gather(ShowWorkspace(tmp_path / "t"), _NoFetchIA(), None, _cand(R_AUD), AUD,
                       allowlist=None)


def test_ts_verdict_is_public_in_ts_rules():
    from llama import ts_rules
    import llama.stages.select_recording as sr
    assert not hasattr(sr, "_ts_verdict")
    assert ts_rules.verdict(R_SBD, GARCIA) == "forbidden"
    assert ts_rules.verdict(R_AUD, GARCIA) == "allowed"
    assert ts_rules.verdict(R_UNK, GARCIA) == "unknown"
    assert ts_rules.verdict(R_AUD, GARCIA.model_copy(update={"exclude": ["schoeps"]})) == \
        "forbidden"
