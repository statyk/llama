"""Task 8: winnow for allowlisted (`ts-`) shows (spec "Winnow").

Offline: FakeProvider for the scorer and research, a fake IA for metadata and
the taperssection scrape, `cache_dir` is tmp_path.
"""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from herder import FakeProvider

from llama.artist_index import TS_INDEX_FILENAME
from llama.config import TaperssectionArtist
from llama.errors import LlamaError
from llama.ledger import Ledger
from llama.models import Candidate, Criteria, RecordingSummary
from llama.stages import winnow
from llama.stages.winnow import _is_ts, _ts_evidence, run_winnow, split_sample
from llama.taperssection import Allowlist
from llama.workspace import RunWorkspace, write_artifact

GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "score_reviews_pre_ts.txt"
TODAY = date(2026, 11, 9)
PHISH = TaperssectionArtist(name="Phish", creators=["Phish"], lineages=["aud"])
AL = Allowlist([PHISH])


# --- fixtures -----------------------------------------------------------------

def lma_candidate(pid: str, d: str, reviews: int = 10, rating: float = 4.5) -> Candidate:
    return Candidate(
        performance_id=pid, collection=pid.split("/")[0], date=d, venue="Winterland",
        recordings=[RecordingSummary(identifier=f"{pid.split('/')[0].lower()}{d}.sbd", date=d,
                                     avg_rating=rating, num_reviews=reviews,
                                     description="Set 1:\nBertha\nSugaree")],
    )


def ts_candidate(d: str, reviews: int = 0, n: int = 1) -> Candidate:
    return Candidate(
        performance_id=f"ts-phish/{d}", collection="ts-phish", date=d, venue="Hampton Coliseum",
        recordings=[RecordingSummary(identifier=f"ph{d}.aud{i}", date=d, num_reviews=reviews,
                                     creator="Phish", title=f"Phish - {d} - Hampton Coliseum",
                                     description="x" * 700, addeddate="2024-01-01")
                    for i in range(n)],
    )


LMA_CANDS = [lma_candidate("GratefulDead/1977-05-08", "1977-05-08"),
             lma_candidate("GratefulDead/1977-05-09", "1977-05-09", reviews=7)]


class FakeIA:
    def __init__(self, scrape_docs=None, scrape_error=None):
        self.scrape_docs = scrape_docs or []
        self.scrape_error = scrape_error
        self.scrapes = 0

    def metadata(self, identifier):
        return {"reviews": [{"reviewtitle": "great", "reviewbody": "crisp tape", "stars": "5"}]}

    def scrape(self, query, fields, count=None):
        self.scrapes += 1
        if self.scrape_error:
            raise self.scrape_error
        return list(self.scrape_docs)


def store(cache_dir: Path, items: dict[str, list[dict]], allowlist: Allowlist = AL) -> None:
    """A fresh taperssection index for ts-phish with the given per-date items."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / TS_INDEX_FILENAME).write_text(json.dumps({
        "allowlist": allowlist.fingerprint(),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "artists": [{"identifier": "ts-phish", "title": "Phish", "allowlisted": True}],
        "items": {"ts-phish": items},
    }))


def item(ident: str, downloads: int, added: str) -> dict:
    return {"identifier": ident, "downloads": downloads, "addeddate": added}


def setup(tmp_path: Path, cands):
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.candidates, cands)
    return ws, Ledger(tmp_path / "ledger.jsonl")


def assessments(pids, scores=None, extra=None) -> str:
    rows = []
    for i, pid in enumerate(pids):
        row = {"performance_id": pid,
               "quality_score": scores[i] if scores else 9.0 - 0.1 * i,
               "non_attendee_evidence": "e", "recording_complaints": [], "rationale": "r"}
        row.update((extra or {}).get(pid, {}))
        rows.append(row)
    return json.dumps({"assessments": rows})


def scorer_prompts(fake: FakeProvider) -> list[str]:
    return [p for kind, p in fake.calls if kind == "complete"]


def payload_of(prompt: str) -> list[dict]:
    start = prompt.index("Candidates (JSON):\n") + len("Candidates (JSON):\n")
    end = prompt.index("\n\nProgrammer's style/mood guidance")
    return json.loads(prompt[start:end])


def lma_batch_prompt(tmp_path: Path, allowlist=None) -> str:
    """Today's LMA-only scorer prompt for LMA_CANDS (Step 1's golden input)."""
    ws, led = setup(tmp_path, LMA_CANDS)
    fake = FakeProvider(completes=[assessments([c.performance_id for c in LMA_CANDS])],
                        researches=["r"] * len(LMA_CANDS))
    kw = {} if allowlist is None else {"allowlist": allowlist, "cache_dir": tmp_path / "cache"}
    run_winnow(ws, fake, fake, FakeIA(), Criteria(query="q", collection="GratefulDead"), led, **kw)
    return scorer_prompts(fake)[0]


# --- guarded surface ----------------------------------------------------------

def test_lma_batch_prompt_and_payload_identical_with_allowlist(tmp_path: Path):
    without = lma_batch_prompt(tmp_path / "a")
    with_al = lma_batch_prompt(tmp_path / "b", allowlist=AL)
    assert without == GOLDEN.read_text()
    assert with_al == GOLDEN.read_text()
    assert payload_of(without) == payload_of(with_al)


def test_lma_only_run_never_builds_ts_index(tmp_path: Path):
    # R20: an LMA-only run never calls load_ts_index, even with an IA whose
    # taperssection scrape would fail.
    ws, led = setup(tmp_path, LMA_CANDS)
    ia = FakeIA(scrape_error=LlamaError("boom"))
    fake = FakeProvider(completes=[assessments([c.performance_id for c in LMA_CANDS])],
                        researches=["r"] * 2)
    run_winnow(ws, fake, fake, ia, Criteria(query="q", collection="GratefulDead"), led,
               cache_dir=tmp_path / "cache", allowlist=AL, today=TODAY)
    assert ia.scrapes == 0
    assert not (tmp_path / "cache" / TS_INDEX_FILENAME).exists()


def test_ts_index_failure_raises_naming_cause(tmp_path: Path):
    # R20: ts candidates + a failing build + no cache -> LlamaError; never
    # scored without rates, never silently dropped.
    ws, led = setup(tmp_path, [ts_candidate("1997-11-22")])
    ia = FakeIA(scrape_error=LlamaError("scrape endpoint down"))
    fake = FakeProvider()
    with pytest.raises(LlamaError, match="scrape endpoint down"):
        run_winnow(ws, fake, fake, ia, Criteria(query="q", collection="ts-phish"), led,
                   cache_dir=tmp_path / "cache", allowlist=AL, today=TODAY)
    assert scorer_prompts(fake) == []


def test_ts_candidate_without_allowlist_fails_closed(tmp_path: Path):
    ws, led = setup(tmp_path, [ts_candidate("1997-11-22")])
    store(tmp_path / "cache", {})
    with pytest.raises(LlamaError, match="ts-phish"):
        run_winnow(ws, FakeProvider(), FakeProvider(), FakeIA(),
                   Criteria(query="q", collection="ts-phish"), led,
                   cache_dir=tmp_path / "cache", today=TODAY)


# --- rules ----------------------------------------------------------------------

def test_is_ts():
    assert _is_ts(ts_candidate("1997-11-22"))
    assert not _is_ts(LMA_CANDS[0])


def test_ts_skips_review_floor(tmp_path: Path):
    cands = [ts_candidate("1997-11-22", reviews=0),
             lma_candidate("GratefulDead/1977-05-08", "1977-05-08", reviews=0)]
    ws, led = setup(tmp_path, cands)
    store(tmp_path / "cache", {"1997-11-22": [item("ph1997-11-22.aud0", 3000, "2024-01-01")]})
    fake = FakeProvider(completes=[assessments(["ts-phish/1997-11-22"])], researches=["r"])
    entries = run_winnow(ws, fake, fake, FakeIA(), Criteria(query="q"), led,
                         cache_dir=tmp_path / "cache", allowlist=AL, today=TODAY)
    assert [e.candidate.performance_id for e in entries] == ["ts-phish/1997-11-22"]


def test_split_sample_proportional_and_both_present():
    lma, ts = list(range(50)), list(range(100, 150))
    a, b = split_sample(lma, ts, 40)
    assert (len(a), len(b)) == (20, 20)
    a, b = split_sample(list(range(99)), [1], 10)
    assert len(b) == 1 and len(a) == 9
    a, b = split_sample([1], list(range(99)), 10)
    assert len(a) == 1 and len(b) == 9
    assert split_sample(lma, [], 10) == (lma[:10], [])
    assert split_sample([], ts, 10) == ([], ts[:10])
    a, b = split_sample(lma, ts, 1)
    assert len(a) + len(b) == 1


def test_mixed_pool_samples_both_sources(tmp_path: Path):
    lma = [lma_candidate(f"GratefulDead/1977-{m:02d}-{d:02d}", f"1977-{m:02d}-{d:02d}")
           for m in range(1, 6) for d in range(1, 11)]
    ts = [ts_candidate(f"1997-{m:02d}-{d:02d}") for m in range(1, 6) for d in range(1, 11)]
    ws, led = setup(tmp_path, lma + ts)
    store(tmp_path / "cache", {c.date: [item(f"ph{c.date}", 1000 + i, "2024-01-01")]
                               for i, c in enumerate(ts)})

    class Scorer(FakeProvider):
        def complete(self, prompt):
            self.calls.append(("complete", prompt))
            return assessments([p["performance_id"] for p in payload_of(prompt)])

    fake = Scorer(researches=["r"] * 12)
    run_winnow(ws, fake, fake, FakeIA(), Criteria(query="q"), led, max_metadata_fetch=40,
               cache_dir=tmp_path / "cache", allowlist=AL, today=TODAY)
    scored = [p["performance_id"] for pr in scorer_prompts(fake) for p in payload_of(pr)]
    assert len(scored) == 40
    assert sum(1 for p in scored if p.startswith("ts-")) == 20
    assert sum(1 for p in scored if p.startswith("GratefulDead/")) == 20


def test_ts_sorted_by_rate_not_date(tmp_path: Path):
    # Later dates carry the higher rates: they are sampled first.
    ts = [ts_candidate(f"1997-11-{d:02d}") for d in range(10, 20)]
    ws, led = setup(tmp_path, ts)
    store(tmp_path / "cache", {c.date: [item(f"ph{c.date}", 100 * i, "2024-01-01")]
                               for i, c in enumerate(ts)})
    keep = ["ts-phish/1997-11-19", "ts-phish/1997-11-18", "ts-phish/1997-11-17"]
    fake = FakeProvider(completes=[assessments(keep)], researches=["r"] * 3)
    run_winnow(ws, fake, fake, FakeIA(), Criteria(query="q", collection="ts-phish"), led,
               max_metadata_fetch=3, cache_dir=tmp_path / "cache", allowlist=AL, today=TODAY)
    assert sorted(p["performance_id"] for p in payload_of(scorer_prompts(fake)[0])) == sorted(keep)


def test_ts_evidence_reviews_then_rate():
    c = ts_candidate("1997-11-22", reviews=2, n=2)
    assert _ts_evidence(c, {"ts-phish/1997-11-22": 3.5}) == (4, 3.5)
    assert _ts_evidence(c, {"ts-phish/1997-11-22": None}) == (4, -1)
    assert _ts_evidence(c, {}) == (4, -1)


def test_ts_payload_and_prompt_block(tmp_path: Path):
    ts = [ts_candidate("1997-11-22", n=2), ts_candidate("1997-11-23")]
    ws, led = setup(tmp_path, ts + LMA_CANDS)
    store(tmp_path / "cache", {
        "1997-11-22": [item("ph1997-11-22.aud0", 3000, "2024-01-01")],
        "1997-11-23": [item("ph1997-11-23.aud0", 10, "2024-01-01")],
    })
    lma_pids = [c.performance_id for c in LMA_CANDS]
    ts_pids = [c.performance_id for c in ts]
    fake = FakeProvider(completes=[assessments(lma_pids), assessments(ts_pids)],
                        researches=["r"] * 4)
    run_winnow(ws, fake, fake, FakeIA(), Criteria(query="q"), led,
               cache_dir=tmp_path / "cache", allowlist=AL, today=TODAY)
    lma_prompt, ts_prompt = scorer_prompts(fake)
    # the LMA batch is today's prompt, byte for byte
    assert lma_prompt == GOLDEN.read_text()
    p = payload_of(ts_prompt)
    assert [x["performance_id"] for x in p] == ts_pids
    assert p[0]["download_percentile"] == 100.0
    assert p[1]["download_percentile"] == 50.0
    recs = p[0]["recordings"]
    assert [r["identifier"] for r in recs] == ["ph1997-11-22.aud0", "ph1997-11-22.aud1"]
    assert recs[0]["creator"] == "Phish"
    assert recs[0]["title"] == "Phish - 1997-11-22 - Hampton Coliseum"
    assert len(recs[0]["description"]) == 600
    assert "download_percentile" in ts_prompt and "attribution" in ts_prompt
    assert "attribution" not in lma_prompt


def test_no_evidence_show_gets_null_percentile(tmp_path: Path):
    # 1997-11-23's only recording is under 75 days old: no percentile.
    ts = [ts_candidate("1997-11-22"), ts_candidate("1997-11-23")]
    ws, led = setup(tmp_path, ts)
    store(tmp_path / "cache", {
        "1997-11-22": [item("a", 3000, "2024-01-01")],
        "1997-11-23": [item("b", 0, "2026-10-01")],
    })
    fake = FakeProvider(completes=[assessments([c.performance_id for c in ts])],
                        researches=["r"] * 2)
    run_winnow(ws, fake, fake, FakeIA(), Criteria(query="q", collection="ts-phish"), led,
               cache_dir=tmp_path / "cache", allowlist=AL, today=TODAY)
    p = {x["performance_id"]: x for x in payload_of(scorer_prompts(fake)[0])}
    assert p["ts-phish/1997-11-22"]["download_percentile"] == 100.0
    assert p["ts-phish/1997-11-23"]["download_percentile"] is None


def test_empty_population_all_null_percentile(tmp_path: Path):
    ts = [ts_candidate("2026-10-01"), ts_candidate("2026-10-02")]
    for c in ts:
        for r in c.recordings:
            r.addeddate = "2026-10-05"
    ws, led = setup(tmp_path, ts)
    store(tmp_path / "cache", {c.date: [item(f"x{c.date}", 0, "2026-10-05")] for c in ts})
    fake = FakeProvider(completes=[assessments([c.performance_id for c in ts])],
                        researches=["r"] * 2)
    run_winnow(ws, fake, fake, FakeIA(), Criteria(query="q", collection="ts-phish"), led,
               cache_dir=tmp_path / "cache", allowlist=AL, today=TODAY)
    assert [x["download_percentile"] for x in payload_of(scorer_prompts(fake)[0])] == [None, None]


def test_pinned_roster_builds_store_when_missing(tmp_path: Path):
    docs = [{"identifier": "ph1997-11-22.aud0", "creator": "Phish", "date": "1997-11-22",
             "year": "1997", "downloads": 500, "addeddate": "2024-01-01T00:00:00Z"}]
    ia = FakeIA(scrape_docs=docs)
    ws, led = setup(tmp_path, [ts_candidate("1997-11-22")])
    fake = FakeProvider(completes=[assessments(["ts-phish/1997-11-22"])], researches=["r"])
    cache = tmp_path / "cache"
    assert not (cache / TS_INDEX_FILENAME).exists()
    run_winnow(ws, fake, fake, ia, Criteria(query="q", artists=["ts-phish"]), led,
               cache_dir=cache, allowlist=AL, today=TODAY)
    assert (cache / TS_INDEX_FILENAME).exists()
    assert payload_of(scorer_prompts(fake)[0])[0]["download_percentile"] == 100.0


def _scored_low(tmp_path: Path, crit: Criteria):
    cands = [ts_candidate("1997-11-22"), lma_candidate("GratefulDead/1997-11-22", "1997-11-22")]
    ws, led = setup(tmp_path, cands)
    store(tmp_path / "cache", {"1997-11-22": [item("a", 3000, "2024-01-01")]})
    fake = FakeProvider(completes=[assessments(["GratefulDead/1997-11-22"], [3.0]),
                                   assessments(["ts-phish/1997-11-22"], [3.0])],
                        researches=["r"] * 2)
    entries = run_winnow(ws, fake, fake, FakeIA(), crit, led,
                         cache_dir=tmp_path / "cache", allowlist=AL, today=TODAY)
    return [e.candidate.performance_id for e in entries], len(scorer_prompts(fake))


def test_single_date_skips_quality_floor_ts_only(tmp_path: Path):
    kept, n_scored = _scored_low(tmp_path, Criteria(query="q", date_from="1997-11-22",
                                                    date_to="1997-11-22"))
    assert kept == ["ts-phish/1997-11-22"]
    assert n_scored == 2  # the scorer still runs


def test_undated_ts_run_keeps_floor(tmp_path: Path):
    kept, _ = _scored_low(tmp_path, Criteria(query="q"))
    assert kept == []


def test_date_range_keeps_floor(tmp_path: Path):
    kept, _ = _scored_low(tmp_path, Criteria(query="q", date_from="1997-11-01",
                                             date_to="1997-11-30"))
    assert kept == []


def test_attribution_suspect_recorded_on_assessment(tmp_path: Path):
    ts = [ts_candidate("1997-11-22"), ts_candidate("1997-11-23")]
    ws, led = setup(tmp_path, ts)
    store(tmp_path / "cache", {"1997-11-22": [item("a", 3000, "2024-01-01")]})
    extra = {"ts-phish/1997-11-22": {"attribution": "suspect",
                                     "attribution_reason": "a 2015 tribute set"}}
    fake = FakeProvider(completes=[assessments([c.performance_id for c in ts], extra=extra)],
                        researches=["r"] * 2)
    entries = run_winnow(ws, fake, fake, FakeIA(), Criteria(query="q", collection="ts-phish"),
                         led, cache_dir=tmp_path / "cache", allowlist=AL, today=TODAY)
    by = {e.candidate.performance_id: e.assessment for e in entries}
    assert by["ts-phish/1997-11-22"].attribution == "suspect"
    assert by["ts-phish/1997-11-22"].attribution_reason == "a 2015 tribute set"
    assert by["ts-phish/1997-11-23"].attribution is None  # omitted: gather decides (Task 10)
    assert by["ts-phish/1997-11-23"].attribution_reason is None


def test_light_research_artist_is_entry_name(tmp_path: Path):
    ws, led = setup(tmp_path, [ts_candidate("1997-11-22")])
    store(tmp_path / "cache", {"1997-11-22": [item("a", 3000, "2024-01-01")]})
    fake = FakeProvider(completes=[assessments(["ts-phish/1997-11-22"])], researches=["r"])
    run_winnow(ws, fake, fake, FakeIA(), Criteria(query="q", collection="ts-phish"), led,
               cache_dir=tmp_path / "cache", allowlist=AL, today=TODAY)
    research = [p for kind, p in fake.calls if kind == "research"]
    assert "Phish" in research[0] and "ts-phish" not in research[0]


def test_execute_passes_allowlist_and_cache_dir_to_winnow(tmp_path: Path, monkeypatch):
    from llama import cli
    from llama.config import Config, TaperssectionConfig

    config = Config(root=tmp_path, taperssection=TaperssectionConfig(artists=[PHISH]))
    seen = {}

    def fake_winnow(*a, **k):
        seen.update(k)
        return []

    monkeypatch.setattr(cli, "run_search", lambda *a, **k: [])
    monkeypatch.setattr(cli, "run_winnow", fake_winnow)
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"score_reviews": None, "light_research": None})
    ws = RunWorkspace(tmp_path, "r1")
    cli._execute(config, FakeIA(), None, ws, Criteria(query="q", collection="ts-phish"),
                 count=1, auto=True, human_gate=False)
    assert seen["allowlist"].require("ts-phish").name == "Phish"
    assert seen["cache_dir"] == tmp_path / "cache"


def test_ts_index_ia_error_raises_llama_error(tmp_path: Path):
    from llama.ia_client import IAError

    ws, led = setup(tmp_path, [ts_candidate("1997-11-22")])
    with pytest.raises(LlamaError, match="cannot score taperssection shows"):
        run_winnow(ws, FakeProvider(), FakeProvider(), FakeIA(scrape_error=IAError("503")),
                   Criteria(query="q", collection="ts-phish"), led,
                   cache_dir=tmp_path / "cache", allowlist=AL, today=TODAY)
