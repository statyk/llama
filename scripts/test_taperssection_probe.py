from llama import ts_rules
from llama.models import RecordingSummary
from taperssection_probe import classify_variant, inline_source_segments, source_lines_variant


def test_inline_segments_split_at_labels_and_stop_at_next_label():
    text = ("Phish 1997-12-05 Cleveland Source: Schoeps CMC6/mk41>PSP-2>DA-P1 Transfer: D8>CDwav>SHN "
            "Location: OTS Set 1: Ghost")
    assert inline_source_segments(text) == ["Source: Schoeps CMC6/mk41>PSP-2>DA-P1",
                                            "Transfer: D8>CDwav>SHN"]


def test_inline_segments_word_anchored_and_capped():
    assert inline_source_segments("Transferred by: Bob. Resource: none") == []
    seg = inline_source_segments("source info: " + "x" * 400)
    assert seg and len(seg[0]) <= len("source info: ") + 250


def test_variant_keeps_line_based_reading_when_breaks_exist():
    desc = "Phish<br />Source: SBD > DAT<br />Set 1: Ghost"
    assert source_lines_variant(desc) == ts_rules.source_lines(desc) == ["Source: SBD > DAT"]


def test_classify_variant_reads_inline_source_and_restores_source_lines():
    rec = RecordingSummary(identifier="phish1991-12-07.x", title="Phish 1991-12-07",
                           description="Phish 1991-12-07 Portsmouth Source: SBD > Cass Transfer: deck")
    # Task 2b adopted the in-line reading in the product (Checkpoint A ruling (B))
    assert ts_rules.classify(rec) == "sbd"
    assert classify_variant(rec) == "sbd"
    assert ts_rules.source_lines is not source_lines_variant


def test_precision_stats_counts_false_aud_and_unknowns():
    from taperssection_probe import precision_stats
    T = {"a": "aud", "b": "sbd", "c": "aud", "d": "fm", "e": "unknown"}
    M = {"a": "aud", "b": "aud", "c": "sbd", "d": "unknown", "e": "unknown"}
    s = precision_stats(M, T)
    assert s["false_aud"] == ["b"] and s["false_non"] == ["c"]
    assert s["unk_non"] == ["d"] and s["recall"] == (1, 2)


# --- score subcommand (Checkpoint B), offline ---------------------------------

import json
import re
from datetime import date, datetime, timezone

import pytest

import taperssection_probe as probe
from llama.artist_index import TS_INDEX_FILENAME
from llama.config import load_config
from llama.taperssection import Allowlist

CONFIG = '[[taperssection.artists]]\nname = "Phish"\ncreators = ["Phish"]\nlineages = ["aud"]\n'
TODAY = date(2026, 11, 9)
DATES = [f"{1990 + i // 3}-0{1 + i % 3}-1{i % 9}" for i in range(36)]


class FakeIA:
    def __init__(self):
        self.metadata_calls = 0

    def scrape(self, query, fields, count=None):
        return [{"identifier": f"ph{d}.aud", "creator": "Phish", "date": d, "title": f"Phish - {d} - Hampton",
                 "source": "Source: Schoeps CMC6 > DAT", "addeddate": "2020-01-01", "downloads": 100 + i,
                 "description": "x"} for i, d in enumerate(DATES)]

    def metadata(self, identifier):
        self.metadata_calls += 1
        return {"reviews": []}


class ScoringProvider:
    """Scores each show in the prompt: 7.0 in the first four calls, 5.0 + a bump for one show later."""

    def __init__(self):
        self.calls = []

    def complete(self, prompt):
        self.calls.append(prompt)
        pids = re.findall(r'"performance_id": "([^"]+)"', prompt)
        late = len(self.calls) > 4
        out = [{"performance_id": p, "quality_score": (5.0 if late else 7.0) + (2.5 if late and p.endswith("-1" + "0") else 0),
                "rationale": "r", "attribution": "ok"} for p in pids]
        return json.dumps({"assessments": out})


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG)
    work = tmp_path / "work"
    work.mkdir()
    al = Allowlist.from_config(load_config(cfg).taperssection)
    (work / TS_INDEX_FILENAME).write_text(json.dumps({
        "allowlist": al.fingerprint(), "built_at": datetime.now(timezone.utc).isoformat(),
        "artists": [{"identifier": "ts-phish", "title": "Phish", "allowlisted": True}],
        "items": {"ts-phish": {d: [{"identifier": f"ph{d}.aud", "downloads": 100 + i, "addeddate": "2020-01-01"}]
                               for i, d in enumerate(DATES)}}}))
    return {"home": home, "cfg": cfg, "work": work, "out": tmp_path / "scorer.md"}


def run(env, *extra, prov=None, ia=None):
    argv = ["score", "--config", str(env["cfg"]), "--workspace", str(env["work"]), "--out", str(env["out"]), *extra]
    return probe.main(argv, hooks={"ia": ia or FakeIA(), "providers": {"score_reviews": prov} if prov else None,
                                   "today": TODAY})


def test_sample_is_seeded_and_spans_eras():
    cands = [type("C", (), {"date": d, "performance_id": d})() for d in sorted(DATES)]
    a, b = probe.stratified_sample(cands, 12, 5), probe.stratified_sample(cands, 12, 5)
    assert [c.date for c in a] == [c.date for c in b]
    assert [c.date for c in a] != [c.date for c in probe.stratified_sample(cands, 12, 6)]
    assert a[0].date < DATES[5] and a[-1].date > "1999"  # first and last runs both represented
    assert len({c.date[:4] for c in a}) >= 8


def test_order_b_mixes_batches_differently():
    items = [f"p{i}" for i in range(20)]
    b = probe.mixed_order(items, 5, 1)
    assert sorted(b) == sorted(items) and b != items
    for i in range(0, 20, 5):
        for j in range(0, 20, 5):
            assert len(set(b[i:i + 5]) & set(items[j:j + 5])) <= 2


def test_score_writes_share_and_largest_diff(env):
    prov = ScoringProvider()
    assert run(env, prov=prov) == 0
    assert len(prov.calls) == 8
    assert "download_percentile" in prov.calls[0] and "recordings" in prov.calls[0]
    md = env["out"].read_text()
    k = sum(p.endswith("-10") for p in re.findall(r'"performance_id": "([^"]+)"', "".join(prov.calls[:4])))
    assert 0 < k < 20  # the bumped shows (B score 7.5) exist in the sample
    assert "Order A: 20/20 at or above 6.0 (100%)" in md
    assert f"Order B: {k}/20 at or above 6.0 ({5 * k}%)" in md
    assert f"Overall: {20 + k}/40 at or above 6.0 ({round(100 * (20 + k) / 40)}%)" in md
    m = re.search(r"Largest per-show difference between orders: (\S+) at (\S+) \(A (\S+), B (\S+)\)", md)
    assert m and m.group(1) == "2.0" and m.group(3) == "7.0" and m.group(4) == "5.0"
    assert "within +/-0.5 of their baseline" in md


def test_score_diff_is_exact_for_known_scores():
    pc = [type("C", (), {"date": f"1999-01-0{i}", "performance_id": f"ts-phish/1999-01-0{i}",
                         "recordings": []})() for i in (1, 2)]
    p1, p2 = pc[0].performance_id, pc[1].performance_id
    md = probe.render_scorer_md(pc, {p1: 70.0, p2: None}, {p1: 1.0, p2: 0.0},
                                {"A": {p1: 7.0, p2: 3.0}, "B": {p1: 6.0, p2: 4.0}},
                                {"A": {}, "B": {}}, {"A": [p1, p2], "B": [p2, p1]},
                                floor=6.0, today=TODAY, seed=1)
    assert "Order A: 1/2 at or above 6.0 (50%)" in md and "Order B: 1/2" in md
    assert "Overall: 2/4 at or above 6.0 (50%)" in md
    assert f"Largest per-show difference between orders: 1.0 at {p2} (A 3.0, B 4.0)" in md
    assert "baseline: 0/2" in md or "baseline: 1/2" in md
    assert "tied zero rates (tie-percentile caveat): " + p2 in md


def test_dry_run_makes_no_provider_call(env, capsys):
    prov = ScoringProvider()
    assert run(env, "--dry-run", prov=prov) == 0
    assert prov.calls == [] and not env["out"].exists()
    err = capsys.readouterr().err
    assert "planned scorer calls: ceil(20/5) x 2 = 8" in err and "dry run" in err


def test_max_calls_aborts_before_spending(env):
    prov = ScoringProvider()
    assert run(env, "--max-calls", "7", prov=prov) == 2
    assert prov.calls == []
    # and the runtime cap stops a provider retrying past the plan
    with pytest.raises(SystemExit):
        run(env, "--n", "5", "--max-calls", "2", prov=_BadJson())


class _BadJson:
    def complete(self, prompt):
        return "not json"


def test_refuses_config_or_workspace_under_llama_home(env, tmp_path):
    ll = env["home"] / ".llama"
    ll.mkdir()
    (ll / "config.toml").write_text(CONFIG)
    with pytest.raises(SystemExit, match="~/.llama"):
        probe.main(["score", "--config", str(ll / "config.toml"), "--workspace", str(env["work"])])
    with pytest.raises(SystemExit, match="~/.llama"):
        probe.main(["score", "--config", str(env["cfg"]), "--workspace", str(ll / "scratch")])
    assert not (ll / "scratch").exists()
