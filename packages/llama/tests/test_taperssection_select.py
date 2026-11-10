"""Task 9: select-recording for allowlisted (`ts-`) shows (spec "Select-recording
and the per-tape policy filter").

The entry comes from `Allowlist.for_candidate`; each recording is classified with
`ts_rules.classify` over its stored `RecordingSummary`; forbidden and excluded
tapes are removed before scoring and never reach `scores`; unknown tapes compete
only when no allowed sibling remains (or when pinned); downloads_norm is the
age-adjusted per-day rate. An LMA candidate selects exactly as before.
"""
import inspect
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from llama.config import TaperssectionArtist
from llama.errors import LlamaError
from llama.models import (Candidate, Overrides, Provenance, QualityAssessment,
                          RecordingSummary)
from llama.stages.select_recording import run_select_recording
from llama.taperssection import Allowlist
from llama.workspace import ShowWorkspace, read_model, read_overrides, write_artifact

TODAY = date(2026, 11, 9)
PID = "ts-phish/1997-11-22"
PHISH = TaperssectionArtist(name="Phish", creators=["Phish"], lineages=["aud"],
                            exclude=["bootleg-dub"])
AL = Allowlist([PHISH])

AUD = "ph1997-11-22.schoeps.flac16"
AUD2 = "ph1997-11-22.dpa.flac16"
SBD = "ph1997-11-22.sbd.flac16"
UNK = "ph1997-11-22.flac16"
EXC = "ph1997-11-22.bootleg-dub.flac16"


def mp3(name):
    return {"name": name, "source": "original", "format": "VBR MP3", "length": "05:00"}


class IA:
    """Every item has the same two mp3 tracks; records which items were fetched."""

    def __init__(self):
        self.fetched: list[str] = []

    def metadata(self, identifier):
        self.fetched.append(identifier)
        return {"metadata": {}, "files": [mp3(f"{identifier}-t01.mp3"),
                                          mp3(f"{identifier}-t02.mp3")]}


def rec(ident, *, source=None, downloads=0, added="2020-01-01T00:00:00Z"):
    return RecordingSummary(identifier=ident, creator="Phish", date="1997-11-22",
                            source=source, downloads=downloads, addeddate=added)


R_AUD = rec(AUD, source="Schoeps CMC6/MK4 > 744T")
R_AUD2 = rec(AUD2, source="DPA 4061 > R-09")
R_SBD = rec(SBD, source="SBD > DAT")
R_UNK = rec(UNK, source="DAT master")
R_EXC = rec(EXC, source="Schoeps MK41 > DAT")


def cand(*recs, collection="ts-phish"):
    return Candidate(performance_id=PID, collection=collection, date="1997-11-22",
                     recordings=list(recs))


def qa():
    return QualityAssessment(performance_id=PID, quality_score=8.0, rationale="r")


def select(tmp_path, candidate, *, pin=None, allowlist=AL, ia=None):
    sws = ShowWorkspace(tmp_path / "show")
    if pin is not None:
        write_artifact(sws.overrides, Overrides(recording=pin))
    chosen = run_select_recording(sws, ia or IA(), candidate, qa(), allowlist=allowlist,
                                  today=TODAY)
    return chosen, json.loads(sws.selection.read_text())


def test_forbidden_never_in_scores(tmp_path):
    # an sbd with a far better download count still never competes under aud-only
    sbd = R_SBD.model_copy(update={"downloads": 100000})
    ia = IA()
    chosen, sel = select(tmp_path, cand(R_AUD, sbd, R_EXC), ia=ia)
    assert chosen == AUD
    assert set(sel["scores"]) == {AUD}
    assert sel["ts_lineage"] == {AUD: "aud"}
    assert sel["scores"][AUD]["lineage"] == "aud"
    assert SBD not in ia.fetched and EXC not in ia.fetched     # removed before scoring


def test_unknown_excluded_when_allowed_sibling(tmp_path):
    unk = R_UNK.model_copy(update={"downloads": 100000})
    chosen, sel = select(tmp_path, cand(unk, R_AUD))
    assert chosen == AUD and set(sel["scores"]) == {AUD}


def test_unknown_competes_when_alone(tmp_path):
    chosen, sel = select(tmp_path, cand(R_UNK, R_SBD))
    assert chosen == UNK and set(sel["scores"]) == {UNK}
    assert sel["ts_lineage"] == {UNK: "unknown"}
    assert sel["scores"][UNK]["lineage"] == "unknown"


def test_empty_set_raises_llamaerror_not_valueerror(tmp_path):
    with pytest.raises(LlamaError) as ei:
        select(tmp_path, cand(R_SBD, R_EXC))
    assert str(ei.value) == f"{PID}: no recording allowed by the taperssection policy"
    assert not (tmp_path / "show" / "selection.json").exists()


@pytest.mark.parametrize("ident", [SBD, EXC])
def test_pin_to_forbidden_raises(tmp_path, ident):
    with pytest.raises(LlamaError) as ei:
        select(tmp_path, cand(R_AUD, R_SBD, R_EXC), pin=ident)
    assert str(ei.value) == (f"{PID}: pinned recording {ident} is forbidden by the "
                             "taperssection policy")


def test_pin_to_unknown_selected(tmp_path):
    chosen, sel = select(tmp_path, cand(R_AUD, R_UNK), pin=UNK)
    assert chosen == UNK and sel["pinned"] is True
    assert set(sel["scores"]) == {AUD, UNK}
    assert sel["ts_lineage"] == {AUD: "aud", UNK: "unknown"}


def test_entry_allowing_every_lineage_filters_only_exclude(tmp_path):
    every = PHISH.model_copy(update={"lineages": ["aud", "sbd", "matrix", "fm", "webcast"]})
    chosen, sel = select(tmp_path, cand(R_AUD, R_SBD, R_UNK, R_EXC),
                         allowlist=Allowlist([every]))
    assert set(sel["scores"]) == {AUD, SBD, UNK}
    assert chosen == SBD                                    # sbd outscores aud as today


def test_rate_tiebreak(tmp_path):
    # same lineage, completeness and format: the per-day rate decides, not raw
    # downloads. A has more downloads but over a far longer life.
    old = R_AUD.model_copy(update={"downloads": 3000, "addeddate": "2006-11-09"})   # ~0.41/day
    new = R_AUD2.model_copy(update={"downloads": 1000, "addeddate": "2025-11-09"})  # ~2.74/day
    chosen, sel = select(tmp_path, cand(old, new))
    assert chosen == AUD2
    assert sel["scores"][AUD2]["downloads_norm"] == 1.0
    assert 0 < sel["scores"][AUD]["downloads_norm"] < 1.0


def test_rate_under_75_days_is_zero(tmp_path):
    young = R_AUD2.model_copy(update={"downloads": 100000, "addeddate": "2026-10-01"})
    aged = R_AUD.model_copy(update={"downloads": 100, "addeddate": "2020-01-01"})
    chosen, sel = select(tmp_path, cand(young, aged))
    assert sel["scores"][AUD2]["downloads_norm"] == 0.0
    assert chosen == AUD


@pytest.mark.parametrize("allowlist", [None, Allowlist.empty()])
def test_ts_candidate_without_allowlist_raises(tmp_path, allowlist):
    with pytest.raises(LlamaError):
        select(tmp_path, cand(R_AUD), allowlist=allowlist)


def test_ts_candidate_without_allowlist_raises_even_when_selected(tmp_path):
    select(tmp_path, cand(R_AUD))
    with pytest.raises(LlamaError):     # fail closed before the should_run short-cut
        run_select_recording(ShowWorkspace(tmp_path / "show"), IA(), cand(R_AUD), qa())


def test_lma_selection_unchanged(tmp_path):
    import test_stage_select as tss
    out = []
    for i, al in enumerate((None, AL)):
        sws = ShowWorkspace(tmp_path / f"s{i}")
        run_select_recording(sws, tss.StubIA(), tss.make_candidate(), tss.assessment(),
                             allowlist=al, today=TODAY)
        out.append(json.loads(sws.selection.read_text()))
    assert out[0] == out[1]
    assert "ts_lineage" not in out[0]


def test_lma_selection_unchanged_on_real_fixture(tmp_path):
    import test_pipeline as tp
    fixture = json.loads(tp.FIXTURE.read_text())
    c = Candidate(performance_id="GratefulDead/1973-06-10", collection="GratefulDead",
                  date="1973-06-10",
                  recordings=[RecordingSummary(identifier=tp.IDENT, avg_rating=4.8,
                                               num_reviews=40, downloads=1234,
                                               description=fixture["metadata"]["description"])])
    a = QualityAssessment(performance_id=c.performance_id, quality_score=9.0, rationale="r")
    out = []
    for i, al in enumerate((None, AL)):
        sws = ShowWorkspace(tmp_path / f"s{i}")
        run_select_recording(sws, tp.FakeIA(), c, a, allowlist=al, today=TODAY)
        out.append(sws.selection.read_bytes())
    assert out[0] == out[1]


# --- process_show ------------------------------------------------------------

def test_process_show_requires_allowlist():
    from llama.pipeline import process_show
    param = inspect.signature(process_show).parameters["allowlist"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        process_show(None, None, None, None, {}, "run")


def test_process_show_passes_allowlist_to_select_and_gather(tmp_path, monkeypatch):
    import llama.pipeline as pipeline
    from llama.ledger import Ledger
    from llama.models import ShortlistEntry
    from llama.workspace import RunWorkspace
    seen = {}

    def sel(show_ws, ia, c, a, **k):
        seen["select"] = k.get("allowlist")
        raise LlamaError("stop after gather check")

    monkeypatch.setattr(pipeline, "run_select_recording", sel)
    entry = ShortlistEntry(rank=1, candidate=cand(R_AUD), assessment=qa())
    with pytest.raises(LlamaError):
        pipeline.process_show(RunWorkspace(tmp_path, "r"), IA(), Ledger(tmp_path / "l.jsonl"),
                              entry, {}, "r", allowlist=AL)
    assert seen["select"] is AL

    monkeypatch.setattr(pipeline, "run_select_recording", lambda *a, **k: AUD)

    def gather(*a, **k):
        seen["gather"] = k.get("allowlist")
        raise LlamaError("stop")
    monkeypatch.setattr(pipeline, "run_gather", gather)
    with pytest.raises(LlamaError):
        pipeline.process_show(RunWorkspace(tmp_path, "r"), IA(), Ledger(tmp_path / "l.jsonl"),
                              entry, {"extract_setlist": None}, "r", allowlist=AL)
    assert seen["gather"] is AL


def test_process_show_real_select_ts_candidate(tmp_path):
    """The real select inside process_show applies the policy (a forbidden-only
    candidate fails the show with the policy error, before gather)."""
    from llama.ledger import Ledger
    from llama.models import ShortlistEntry
    from llama.pipeline import process_show
    from llama.workspace import RunWorkspace
    entry = ShortlistEntry(rank=1, candidate=cand(R_SBD), assessment=qa())
    with pytest.raises(LlamaError, match="no recording allowed by the taperssection policy"):
        process_show(RunWorkspace(tmp_path, "r"), IA(), Ledger(tmp_path / "l.jsonl"), entry,
                     {"extract_setlist": None}, "r", allowlist=AL)


# --- the adjudicator's switch path --------------------------------------------

def test_adjudicator_switch_to_forbidden_raises(tmp_path, monkeypatch):
    """A `switch_recording` verdict onto an sbd tape of an aud-only ts show, through
    `apply_verdict` and the real `cli._redo_show_locked` -> `process_show` ->
    select: the select refuses, the show is restored byte-identical, and the error
    is surfaced on the result."""
    import test_adjudicator_apply as taa
    from helpers import tree_bytes
    from llama.models import Show

    lib = taa.Lib(tmp_path, monkeypatch)
    # Make the packaged library show a ts-phish show: the dir is named for its pid.
    ts_dir = tmp_path / "shows" / "ts-phish-1997-11-22"
    shutil.move(str(lib.ws.dir), str(ts_dir))
    lib.ws = ShowWorkspace(ts_dir)
    prov = read_model(lib.ws.provenance, Provenance)
    c = cand(R_AUD, R_SBD)
    write_artifact(lib.ws.provenance, prov.model_copy(update={
        "performance_id": PID, "candidate": c,
        "assessment": prov.assessment.model_copy(update={"performance_id": PID})}))
    write_artifact(lib.ws.selection, {"identifier": AUD, "scores": {}})
    lib.cfg.write_text(lib.cfg.read_text() + (
        '[[taperssection.artists]]\nname = "Phish"\ncreators = ["Phish"]\n'
        'lineages = ["aud"]\n'))
    show = lib.pre(flags=[taa.VENUE_FLAG])
    write_artifact(lib.ws.show, show.model_copy(update={"performance_id": PID,
                                                        "identifier": AUD}))
    before = tree_bytes(lib.ws.dir)
    post = taa.mk([taa.T("a1.mp3", "A", dur=300.0)], ident=SBD)
    v = taa.V([taa.switch(SBD)], [taa.judge(taa.VENUE_FLAG, conf="medium")])
    r = lib.apply(v, lib.redo(post))                       # real select: no stub
    assert lib.stages == ["select"]
    assert (r.status, r.held) == ("refused", True), r
    assert r.error == f"{PID}: pinned recording {SBD} is forbidden by the taperssection policy"
    assert tree_bytes(lib.ws.dir) == before
    assert read_overrides(lib.ws).recording is None
    assert read_model(lib.ws.show, Show).identifier == AUD


# --- a stored selection is re-checked under the CURRENT entry (review round 1) --

def _stored(tmp_path, ident, *, pin=None):
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.selection, {"identifier": ident, "scores": {}})
    if pin is not None:
        write_artifact(sws.overrides, Overrides(recording=pin))
    return sws


def test_stored_forbidden_selection_reselects_allowed_sibling(tmp_path):
    # selected under an older, looser entry; the entry is now aud-only
    sws = _stored(tmp_path, SBD)
    ia = IA()
    chosen = run_select_recording(sws, ia, cand(R_AUD, R_SBD), qa(), allowlist=AL, today=TODAY)
    assert chosen == AUD
    sel = json.loads(sws.selection.read_text())
    assert sel["identifier"] == AUD and set(sel["scores"]) == {AUD}
    assert SBD not in ia.fetched


def test_stored_excluded_selection_reselects(tmp_path):
    sws = _stored(tmp_path, EXC)
    chosen = run_select_recording(sws, IA(), cand(R_AUD, R_EXC), qa(), allowlist=AL, today=TODAY)
    assert chosen == AUD
    assert json.loads(sws.selection.read_text())["identifier"] == AUD


def test_stored_forbidden_pinned_selection_raises(tmp_path):
    sws = _stored(tmp_path, SBD, pin=SBD)
    before = sws.selection.read_bytes()
    with pytest.raises(LlamaError) as ei:
        run_select_recording(sws, IA(), cand(R_AUD, R_SBD), qa(), allowlist=AL, today=TODAY)
    assert str(ei.value) == (f"{PID}: pinned recording {SBD} is forbidden by the "
                             "taperssection policy")
    assert sws.selection.read_bytes() == before


@pytest.mark.parametrize("ident", [AUD, UNK, "not-a-recording-of-this-show"])
def test_stored_allowed_unknown_or_foreign_selection_reused_untouched(tmp_path, ident):
    sws = _stored(tmp_path, ident)
    before = sws.selection.read_bytes()
    ia = IA()
    chosen = run_select_recording(sws, ia, cand(R_AUD, R_UNK, R_SBD), qa(), allowlist=AL,
                                  today=TODAY)
    assert chosen == ident and ia.fetched == []
    assert sws.selection.read_bytes() == before


def test_lma_stored_selection_shortcut_unchanged(tmp_path):
    import test_stage_select as tss
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.selection, {"identifier": "gd73-06-10.aud", "scores": {}})
    before = sws.selection.read_bytes()

    class Boom:
        def metadata(self, identifier):
            raise AssertionError("short-cut fetched metadata")
    for al in (None, AL):
        assert run_select_recording(sws, Boom(), tss.make_candidate(), tss.assessment(),
                                    allowlist=al, today=TODAY) == "gd73-06-10.aud"
    assert sws.selection.read_bytes() == before


# --- final review I1: a stale pick re-selected on resume must not ship the old tape --

def test_process_show_resume_after_tightening_regathers_new_pick(tmp_path, monkeypatch):
    """A run paused after gather picked an sbd tape under a looser entry; the entry is
    then tightened to aud-only and the run resumes (process_show, force=False). Select
    re-picks the aud tape, and gather must recompute on it (where R27 applies) rather
    than short-cut to the stored sbd `show.json`; every later artifact derived from
    the old tape is dropped."""
    import llama.pipeline as pipeline
    import llama.stages.gather as gather_mod
    from llama.ledger import Ledger
    from llama.models import ShortlistEntry, Show
    from llama.workspace import RunWorkspace

    run_ws = RunWorkspace(tmp_path, "r")
    sws = run_ws.show_ws(PID)
    write_artifact(sws.selection, {"identifier": SBD, "scores": {}})
    write_artifact(sws.show, Show(performance_id=PID, identifier=SBD, artist="Phish",
                                  date="1997-11-22"))
    write_artifact(sws.reviews, [])
    write_artifact(sws.research, "# research on the sbd gather")
    write_artifact(sws.vetting, {"stale": True})

    seen = {}

    def compute_gather(show_ws, ia, provider, candidate, identifier, **k):
        seen["gather"] = identifier
        raise LlamaError("stop at gather")

    def research(show_ws, provider, show, dossier, force=False):
        seen["research"] = show.identifier
        raise LlamaError("stop at research")

    monkeypatch.setattr(gather_mod, "compute_gather", compute_gather)
    monkeypatch.setattr(pipeline, "run_research", research)
    entry = ShortlistEntry(rank=1, candidate=cand(R_AUD, R_SBD), assessment=qa())
    with pytest.raises(LlamaError):
        pipeline.process_show(run_ws, IA(), Ledger(tmp_path / "l.jsonl"), entry,
                              {"extract_setlist": None, "deep_research": None}, "r", allowlist=AL)
    assert "research" not in seen, f"resume carried the stale {seen['research']} past gather"
    assert seen["gather"] == AUD
    assert json.loads(sws.selection.read_text())["identifier"] == AUD
    for stale in (sws.show, sws.reviews, sws.research, sws.vetting):
        assert not stale.exists(), stale


def test_process_show_resume_with_allowed_stored_pick_keeps_artifacts(tmp_path, monkeypatch):
    """The re-check only acts on a forbidden pick: an allowed stored pick short-cuts
    select AND gather exactly as before, and nothing is dropped."""
    import llama.pipeline as pipeline
    import llama.stages.gather as gather_mod
    from llama.ledger import Ledger
    from llama.models import ShortlistEntry, Show
    from llama.workspace import RunWorkspace

    run_ws = RunWorkspace(tmp_path, "r")
    sws = run_ws.show_ws(PID)
    write_artifact(sws.selection, {"identifier": AUD, "scores": {}})
    write_artifact(sws.show, Show(performance_id=PID, identifier=AUD, artist="Phish",
                                  date="1997-11-22"))
    write_artifact(sws.research, "# research")
    seen = {}

    def compute_gather(*a, **k):
        raise AssertionError("gather recomputed for an allowed stored pick")

    def research(show_ws, provider, show, dossier, force=False):
        seen["research"] = show.identifier
        raise LlamaError("stop at research")

    monkeypatch.setattr(gather_mod, "compute_gather", compute_gather)
    monkeypatch.setattr(pipeline, "run_research", research)
    entry = ShortlistEntry(rank=1, candidate=cand(R_AUD, R_SBD), assessment=qa())
    with pytest.raises(LlamaError, match="stop at research"):
        pipeline.process_show(run_ws, IA(), Ledger(tmp_path / "l.jsonl"), entry,
                              {"extract_setlist": None, "deep_research": None}, "r", allowlist=AL)
    assert seen["research"] == AUD
    assert sws.show.exists() and sws.research.exists()


def test_default_today_is_the_utc_date_like_winnow(tmp_path, monkeypatch):
    """Final review M4: with no `today`, select's 75-day cutoff uses the UTC date
    (winnow's), not the local one."""
    import datetime as real
    import llama.stages.select_recording as sr
    seen = []

    class FakeDT(real.datetime):
        @classmethod
        def now(cls, tz=None):
            seen.append(tz)
            return real.datetime(2026, 11, 9, 23, 30, tzinfo=real.timezone.utc)

    monkeypatch.setattr(sr, "datetime", FakeDT)
    # an addeddate at the 75-day edge of the UTC date
    edge = R_AUD.model_copy(update={"downloads": 750, "addeddate": "2026-08-26T00:00:00Z"})
    sws = ShowWorkspace(tmp_path / "show")
    run_select_recording(sws, IA(), cand(edge), qa(), allowlist=AL)
    implicit = json.loads(sws.selection.read_text())["scores"][AUD]
    sws2 = ShowWorkspace(tmp_path / "show2")
    run_select_recording(sws2, IA(), cand(edge), qa(), allowlist=AL, today=TODAY)
    assert seen == [real.timezone.utc]
    assert implicit == json.loads(sws2.selection.read_text())["scores"][AUD]
