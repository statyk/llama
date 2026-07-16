import json
import logging
from pathlib import Path

from llama.ledger import Ledger
from llama.llm.fake import FakeProvider
from llama.models import Candidate, Criteria, LedgerEntry, RecordingSummary, SetlistConstraint
from llama.stages.winnow import run_winnow
from llama.workspace import RunWorkspace, write_artifact

DESC = "Set 1:\nMorning Dew\nChina Cat Sunflower > I Know You Rider\nLooks Like Rain\nBrown Eyed Women"


def candidate(pid: str, date: str, desc: str | None = DESC, rating: float = 4.5, reviews: int = 10):
    return Candidate(
        performance_id=pid, collection="GratefulDead", date=date, venue="V",
        recordings=[RecordingSummary(identifier=f"{pid.split('/')[-1]}.sbd", date=date,
                                     avg_rating=rating, num_reviews=reviews, description=desc)],
    )


class StubIA:
    def metadata(self, identifier):
        return {"reviews": [{"reviewtitle": "great", "reviewbody": "crisp tape", "stars": "5"}]}


def assessments_json(pids: list[str]) -> str:
    return json.dumps({"assessments": [
        {"performance_id": pid, "quality_score": 9.0 - i, "non_attendee_evidence": "e",
         "recording_complaints": [], "rationale": "solid"}
        for i, pid in enumerate(pids)
    ]})


def setup(tmp_path: Path, cands, played=()):
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.candidates, cands)
    led = Ledger(tmp_path / "ledger.jsonl")
    for pid in played:
        led.record(LedgerEntry(performance_id=pid, artist="GD", date="x", status="selected",
                               run="r0", recorded_at="2026-01-01T00:00:00+00:00"))
    return ws, led


def test_winnow_full_flow(tmp_path: Path):
    cands = [
        candidate("GratefulDead/1973-06-10", "1973-06-10"),
        candidate("GratefulDead/1973-06-22", "1973-06-22"),          # will be ledger-excluded
        candidate("GratefulDead/1973-09-11", "1973-09-11",
                  desc="Set 1:\nBertha\nSugaree\nDeal\nLoser\nRow Jimmy"),  # no china>rider
        candidate("GratefulDead/1973-10-19", "1973-10-19", rating=2.0),     # below min rating
    ]
    ws, led = setup(tmp_path, cands, played=["GratefulDead/1973-06-22"])
    crit = Criteria(query="q", collection="GratefulDead",
                    setlist_constraints=[SetlistConstraint(sequence=["China Cat Sunflower", "I Know You Rider"])])
    fake = FakeProvider(
        completes=[assessments_json(["GratefulDead/1973-06-10"])],
        researches=["Ranked #3 all-time on some blog (blog.example)"],
    )
    entries = run_winnow(ws, fake, fake, StubIA(), crit, led)
    assert [e.candidate.performance_id for e in entries] == ["GratefulDead/1973-06-10"]
    assert entries[0].rank == 1
    assert entries[0].approved is None
    assert entries[0].assessment.reviewed_identifier == "1973-06-10.sbd"
    assert "blog.example" in entries[0].external_reputation
    assert ws.shortlist.exists()


def test_winnow_batches_llm_calls(tmp_path: Path):
    cands = [candidate(f"GratefulDead/1974-0{i}-01", f"1974-0{i}-01") for i in range(1, 6)]
    ws, led = setup(tmp_path, cands)
    pids = [c.performance_id for c in cands]
    fake = FakeProvider(
        completes=[assessments_json(pids[:2]), assessments_json(pids[2:4]), assessments_json(pids[4:])],
        researches=["r"] * 5,
    )
    crit = Criteria(query="q", collection="GratefulDead")
    entries = run_winnow(ws, fake, fake, StubIA(), crit, led, batch_size=2)
    assert len(entries) == 5
    n_completes = sum(1 for kind, _ in fake.calls if kind == "complete")
    assert n_completes == 3
    # ranked by quality_score descending
    scores = [e.assessment.quality_score for e in entries]
    assert scores == sorted(scores, reverse=True)


def test_winnow_skips_if_artifact_exists(tmp_path: Path):
    cands = [candidate("GratefulDead/1973-06-10", "1973-06-10")]
    ws, led = setup(tmp_path, cands)
    crit = Criteria(query="q", collection="GratefulDead")
    fake = FakeProvider(completes=[assessments_json([cands[0].performance_id])], researches=["r"])
    run_winnow(ws, fake, fake, StubIA(), crit, led)
    again = run_winnow(ws, FakeProvider(), FakeProvider(), StubIA(), crit, led)  # empty queues: must not call LLM
    assert len(again) == 1


def test_winnow_truncation_samples_across_years(tmp_path: Path):
    # 4 shows in 1969 (most-reviewed first: 30/20/10/5) + 2 in 1977; cap 4.
    # Old behavior kept the first 4 chronologically = all 1969. Stratified
    # sampling must keep the two most-reviewed of each year.
    cands = [
        candidate("GratefulDead/1969-02-01", "1969-02-01", reviews=5),
        candidate("GratefulDead/1969-03-01", "1969-03-01", reviews=30),
        candidate("GratefulDead/1969-04-01", "1969-04-01", reviews=10),
        candidate("GratefulDead/1969-05-01", "1969-05-01", reviews=20),
        candidate("GratefulDead/1977-05-08", "1977-05-08", reviews=8),
        candidate("GratefulDead/1977-05-09", "1977-05-09", reviews=4),
    ]
    ws, led = setup(tmp_path, cands)
    expected = ["GratefulDead/1969-03-01", "GratefulDead/1969-05-01",
                "GratefulDead/1977-05-08", "GratefulDead/1977-05-09"]
    fake = FakeProvider(completes=[assessments_json(expected)], researches=["r"] * 4)
    crit = Criteria(query="q", collection="GratefulDead")
    entries = run_winnow(ws, fake, fake, StubIA(), crit, led, max_metadata_fetch=4)
    assert sorted(e.candidate.performance_id for e in entries) == sorted(expected)


def test_winnow_shortlist_cut_spreads_years(tmp_path: Path):
    # Scores: 1977 shows 9.0 and 8.0, 1969 show 7.0. A shortlist of 2 must
    # not be the two 1977 shows; it takes each year's best, ranked by score.
    cands = [
        candidate("GratefulDead/1977-05-08", "1977-05-08"),
        candidate("GratefulDead/1977-05-09", "1977-05-09"),
        candidate("GratefulDead/1969-12-07", "1969-12-07"),
    ]
    ws, led = setup(tmp_path, cands)
    fake = FakeProvider(
        completes=[json.dumps({"assessments": [
            {"performance_id": "GratefulDead/1977-05-08", "quality_score": 9.0,
             "non_attendee_evidence": "e", "recording_complaints": [], "rationale": "r"},
            {"performance_id": "GratefulDead/1977-05-09", "quality_score": 8.0,
             "non_attendee_evidence": "e", "recording_complaints": [], "rationale": "r"},
            {"performance_id": "GratefulDead/1969-12-07", "quality_score": 7.0,
             "non_attendee_evidence": "e", "recording_complaints": [], "rationale": "r"},
        ]})],
        researches=["r"] * 2,
    )
    crit = Criteria(query="q", collection="GratefulDead")
    entries = run_winnow(ws, fake, fake, StubIA(), crit, led, shortlist_size=2)
    assert [e.candidate.performance_id for e in entries] == [
        "GratefulDead/1977-05-08", "GratefulDead/1969-12-07"]
    assert [e.rank for e in entries] == [1, 2]


def test_winnow_logs_progress(tmp_path: Path, caplog):
    cands = [candidate(f"GratefulDead/1974-0{i}-01", f"1974-0{i}-01") for i in range(1, 6)]
    ws, led = setup(tmp_path, cands)
    pids = [c.performance_id for c in cands]
    fake = FakeProvider(
        completes=[assessments_json(pids[:2]), assessments_json(pids[2:4]), assessments_json(pids[4:])],
        researches=["r"] * 5,
    )
    crit = Criteria(query="q", collection="GratefulDead")
    with caplog.at_level(logging.INFO, logger="llama"):
        run_winnow(ws, fake, fake, StubIA(), crit, led, batch_size=2)
    messages = [r.getMessage() for r in caplog.records]
    assert "winnow: fetching reviews (5 shows)" in messages
    assert any(m.startswith("5/5:") for m in messages)
    assert "winnow: scoring reviews (3 batches)" in messages
    assert "batch 3/3" in messages
    assert "winnow: researching shortlist (5 shows)" in messages
    assert any(m.endswith("(5/5)") for m in messages)
