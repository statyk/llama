"""scripts/bulk_apply.py revoice-list / trial-report (bulk-apply plan Task 17; spec "Delivery
after the fix" (ranked re-voice list) and "The trial").

Fixture libraries under tmp_path; nothing real is touched."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bulk_apply as ba
from llama import campaign, campaign_gate, station_mark
from test_bulk_apply_mark import _arm, _lib, _row, _show

MARK_AT = "2026-10-01T00:00:00.000000Z"
RESET = "2026-10-27T15:00:00+00:00"


@pytest.fixture(autouse=True)
def _no_emcee(monkeypatch):
    monkeypatch.setattr(station_mark, "emcee_running", lambda: [])
    monkeypatch.setattr(campaign_gate, "ps_lines", lambda: [])
    monkeypatch.setattr("llama.replay.code_identity", lambda: "abc")


def _run(cfg, *argv):
    return ba.main(["--config", str(cfg), *argv])


# ---------------------------------------------------------------- revoice-list

def _voiced_world(tmp_path, specs):
    """specs: slug -> (arm-row overrides dict). Every show is voiced, delivered, awaiting fix,
    with library tracks t1/t2 (titles Song 1/2, set 1, no segue)."""
    cfg, root, station = _lib(tmp_path)
    rows = []
    for slug, kw in specs.items():
        ws = _show(root, slug, delivered=True, station=station, voiced=True)
        campaign.add_mark(ws, reason="changed by the held-backlog fixes: titles",
                          start_stage="gather", batch="b1", at=MARK_AT)
        kw = dict(kw)
        outcome = kw.pop("outcome", "clean")
        base = {"filenames": ["t1.mp3", "t2.mp3"], "titles": ["Song 1", "Song 2"],
                "sets": ["1", "1"], "segues": [False, False]}
        base.update(kw)
        rows.append(_row(ws, outcome=outcome, **base))
    arm = tmp_path / "arm.json"
    arm.write_text(json.dumps(_arm(cfg, *rows)))
    return cfg, arm


def _status(tmp_path, entries):
    path = tmp_path / "status.json"
    out = []
    for slug, (voiced_by, tts_now) in entries.items():
        out.append({"slug": slug, "voiced_by": voiced_by, "tts_now": tts_now,
                    "awaiting_fix": True})
    path.write_text(json.dumps(out))
    return path


def _lines(capsys):
    return [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]


VOX = {"backend": "voxtral", "model": "m"}


def test_ranking_is_lexicographic_and_explained(tmp_path, capsys):
    specs = {
        # tracks: 1 added -> (1, 0, 0, 0, 0)
        "a-tracks": {"filenames": ["t1.mp3", "t2.mp3", "t3.mp3"], "titles": ["Song 1", "Song 2", "X"],
                     "sets": ["1", "1", "1"], "segues": [False, False, False]},
        # set moves 2, titles 2 -> (0, 2, 2, 0, 0)
        "b-sets": {"sets": ["2", "2"], "titles": ["A", "B"]},
        # titles 1 -> (0, 0, 1, 0, 0)
        "c-title": {"titles": ["Song 1", "Other"]},
        # many metadata but nothing above -> (0,0,0,0,1)
        "d-meta": {"venue": ["a", "b"]},
        # segue only -> (0,0,0,1,0)
        "e-segue": {"segues": [True, False]},
        # ties with c-title: same key, slug order
        "f-title": {"titles": ["Song 1", "Other"]},
    }
    cfg, arm = _voiced_world(tmp_path, specs)
    status = _status(tmp_path, {s: ("phil", VOX) for s in specs})
    assert _run(cfg, "revoice-list", "--arm", str(arm), "--emcee-status", str(status)) == 0
    lines = _lines(capsys)
    order = [next(s for s in specs if f" {s} " in f" {ln} ") for ln in lines]
    assert order == ["a-tracks", "b-sets", "c-title", "f-title", "e-segue", "d-meta"]
    first = lines[0]
    assert first.startswith("1 ") or first.startswith("1.")
    assert "tracks +1/-0" in first and "phil" in first and "set moves 0" in first
    assert "set moves 2" in lines[1] and "titles 2" in lines[1]
    assert "segues 1" in lines[4] and "metadata 1" in lines[5]


def test_cost_from_tts_now(tmp_path, capsys):
    specs = {s: {} for s in ("v", "m", "e", "u", "n")}
    cfg, arm = _voiced_world(tmp_path, specs)
    status = _status(tmp_path, {
        "v": ("phil", VOX), "m": ("kurt", {"backend": "mlx_audio", "model": "q"}),
        "e": ("x", {"backend": "elevenlabs", "model": "q"}),
        "u": ("x", {"unresolved": "no key"}), "n": ("x", None)})
    assert _run(cfg, "revoice-list", "--arm", str(arm), "--emcee-status", str(status)) == 0
    got = {ln.split()[1]: ln for ln in _lines(capsys)}
    assert "1 Voxtral credit" in got["v"]
    assert "free (local)" in got["m"]
    assert "ElevenLabs" in got["e"]
    assert got["u"].count("unknown") >= 1 and "cost unknown" in got["u"]
    assert "cost unknown" in got["n"]
    # --backend filters
    assert _run(cfg, "revoice-list", "--arm", str(arm), "--emcee-status", str(status),
                "--backend", "mlx_audio") == 0
    lines = _lines(capsys)
    assert len(lines) == 1 and " m " in lines[0]


def test_needs_llm_rows_last(tmp_path, capsys):
    specs = {"a-needs": {"outcome": "needs-llm"},
             "b-small": {"titles": ["Song 1", "Other"]},
             "c-needs": {"outcome": "needs-llm"}}
    cfg, arm = _voiced_world(tmp_path, specs)
    status = _status(tmp_path, {s: ("phil", VOX) for s in specs})
    assert _run(cfg, "revoice-list", "--arm", str(arm), "--emcee-status", str(status)) == 0
    lines = _lines(capsys)
    assert [ln.split()[1] for ln in lines] == ["b-small", "a-needs", "c-needs"]
    assert "unknown until re-processed" in lines[1] and "unknown until re-processed" in lines[2]
    assert "unknown until re-processed" not in lines[0]


def test_unvoiced_and_processed_shows_are_not_listed(tmp_path, capsys):
    cfg, arm = _voiced_world(tmp_path, {"v": {}, "p": {}})
    root = tmp_path / "lib"
    from llama.workspace import ShowWorkspace
    assert campaign.mark_processed(ShowWorkspace(root / "shows" / "p"), held=False)
    status = _status(tmp_path, {"v": ("phil", VOX), "p": ("phil", VOX)})
    data = json.loads(status.read_text())
    data.append({"slug": "u", "voiced_by": None, "tts_now": VOX, "awaiting_fix": True})
    status.write_text(json.dumps(data))
    assert _run(cfg, "revoice-list", "--arm", str(arm), "--emcee-status", str(status)) == 0
    assert [ln.split()[1] for ln in _lines(capsys)] == ["v"]


# ----------------------------------------------------------------- trial-report

def _meter(five, seven, resets=RESET):
    return {"five_hour": five, "five_hour_resets": resets, "seven_day": seven,
            "seven_day_resets": "2026-10-31T00:00:00+00:00"}


def _block(tmp_path, name, n, five, seven, *, kind="fresh", resets=(RESET, RESET), calls=1,
           extra_rows=None, align=None):
    """A batch dir with n spending rows; first row before = five[0]/seven[0], last row
    after = five[1]/seven[1]."""
    d = tmp_path / name
    d.mkdir()
    slugs = [f"{name}-{i}" for i in range(n)]
    (d / "list.json").write_text(json.dumps({"rows": [{"slug": s, "kind": kind} for s in slugs]}))
    lines = []
    for i, s in enumerate(slugs):
        before = _meter(five[0], seven[0], resets[0]) if i == 0 else _meter(five[0], seven[0])
        after = _meter(five[1], seven[1], resets[1]) if i == n - 1 else _meter(five[1], seven[1])
        row = {"slug": s, "outcome": "cleared", "retryable": False,
               "at": f"2026-10-27T10:{i:02d}:00+00:00", "kind": kind, "llm_calls": calls,
               "meter": {"before": before, "after": after}}
        if align is not None:
            row["align_reproduced"] = align[i]
        lines.append(row)
    lines += extra_rows or []
    (d / "progress.jsonl").write_text("".join(json.dumps(r) + "\n" for r in lines))
    return d


def _queue(tmp_path, q):
    path = tmp_path / "counts.json"
    path.write_text(json.dumps(q))
    return path


def _report(cfg, capsys, *argv):
    rc = _run(cfg, "trial-report", *argv)
    return rc, capsys.readouterr().out


def test_block_cost_and_ratio(tmp_path, capsys):
    cfg, _, _ = _lib(tmp_path)
    d = _block(tmp_path, "b", 20, (30, 40), (10, 12))
    q = _queue(tmp_path, {})
    rc, out = _report(cfg, capsys, "--block", f"dead-fresh={d}", "--queue", str(q),
                      "--weekly-share", "50")
    assert rc == 0
    assert "per-show 5h: 0.5" in out
    assert "7d/5h ratio: 0.2" in out
    assert "per-show 7d: 0.1" in out


def test_block_crossing_a_reset_is_discarded(tmp_path, capsys):
    cfg, _, _ = _lib(tmp_path)
    d = _block(tmp_path, "b", 20, (30, 40), (10, 12), resets=(RESET, "2026-10-27T20:00:00+00:00"))
    q = _queue(tmp_path, {})
    rc, out = _report(cfg, capsys, "--block", f"dead-fresh={d}", "--queue", str(q),
                      "--weekly-share", "50")
    assert "discarded: crossed a 5-hour reset; re-run" in out
    assert "per-show 5h" not in out
    assert rc == 0


def test_small_block_reports_its_bound(tmp_path, capsys):
    cfg, _, _ = _lib(tmp_path)
    d = _block(tmp_path, "b", 20, (30, 33), (10, 11))
    q = _queue(tmp_path, {})
    rc, out = _report(cfg, capsys, "--block", f"dead-fresh={d}", "--queue", str(q),
                      "--weekly-share", "50")
    assert "delta5 3 < 5 points" in out
    assert "error bound ±1/20 = ±0.05 points per show" in out


def _add_row(d, slug, kind, at, calls):
    lst = json.loads((d / "list.json").read_text())
    lst["rows"].append({"slug": slug, "kind": kind})
    (d / "list.json").write_text(json.dumps(lst))
    row = {"slug": slug, "outcome": "cleared", "retryable": False, "kind": kind, "at": at,
           "llm_calls": calls, "meter": {"before": _meter(90, 90), "after": _meter(95, 95)}}
    with (d / "progress.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")


def test_non_spending_and_other_kind_rows_are_not_counted(tmp_path, capsys):
    cfg, _, _ = _lib(tmp_path)
    d = _block(tmp_path, "b", 20, (30, 40), (10, 12))
    _add_row(d, "zz", "reuse", "2026-10-27T10:05:30+00:00", 0)          # inside, no spend
    _add_row(d, "yy", "needs-llm", "2026-10-27T12:00:00+00:00", 2)      # outside, spent
    q = _queue(tmp_path, {})
    rc, out = _report(cfg, capsys, "--block", f"dead-fresh={d}", "--queue", str(q),
                      "--weekly-share", "50")
    assert "shows=20" in out and "per-show 5h: 0.5" in out
    assert "not contiguous" not in out


def test_interleaved_spend_of_another_kind_means_no_measurement(tmp_path, capsys):
    cfg, _, _ = _lib(tmp_path)
    d = _block(tmp_path, "b", 20, (30, 40), (10, 12))
    _add_row(d, "zz", "needs-llm", "2026-10-27T10:05:30+00:00", 2)      # inside, spent
    q = _queue(tmp_path, {"dead": {"fresh": {"unvoiced": 5, "voiced": 0}}})
    rc, out = _report(cfg, capsys, "--block", f"dead-fresh={d}", "--queue", str(q),
                      "--weekly-share", "50")
    assert ("dead-fresh: not contiguous: 1 spending row(s) of another kind inside it; "
            "re-run as one block per kind") in out
    assert "per-show 5h" not in out and "7d/5h ratio" not in out
    assert "no usable block" in out


def test_projection_in_weeks(tmp_path, capsys):
    cfg, _, _ = _lib(tmp_path)
    d = _block(tmp_path, "b", 20, (30, 40), (10, 12))
    cell = lambda n: {"unvoiced": n, "voiced": 0}
    q = _queue(tmp_path, {"dead": {"fresh": cell(6), "reuse": cell(100), "label-only": cell(100),
                                   "held": cell(100)}, "(none)": {"fresh": cell(4)}})
    rc, out = _report(cfg, capsys, "--block", f"dead-fresh={d}", "--queue", str(q),
                      "--weekly-share", "50")
    assert rc == 0
    # 6 x 0.1 = 0.6 points -> 0.012 weeks; (none) is outside every shape: 4 x 0.1 = 0.4
    assert "projection dead: 0.6 points = 0.012 weeks" in out
    assert "projection (none): 0.4 points = 0.008 weeks" in out
    assert "projection total: 1 points = 0.02 weeks" in out


def test_material_difference_keeps_shapes_apart(tmp_path, capsys):
    cfg, _, _ = _lib(tmp_path)
    dead = _block(tmp_path, "dead", 20, (30, 40), (10, 12))
    funk = _block(tmp_path, "funk", 20, (0, 20), (0, 4))
    cell = lambda n: {"unvoiced": n, "voiced": 0}
    q = _queue(tmp_path, {"dead": {"fresh": cell(10)}, "dead-family": {"fresh": cell(10)},
                          "funk": {"fresh": cell(10)}, "bluegrass": {"fresh": cell(10)}})
    rc, out = _report(cfg, capsys, "--block", f"dead-fresh={dead}", "--block", f"funk-fresh={funk}",
                      "--queue", str(q), "--weekly-share", "50",
                      "--shape", "dead=dead,dead-family", "--shape", "funk=funk")
    assert rc == 0
    assert "7d/5h ratio: 0.2" in out
    assert "fresh: shapes kept apart" in out
    assert "projection dead: 1 points" in out
    assert "projection dead-family: 1 points" in out
    assert "projection funk: 2 points" in out
    assert "projection bluegrass: 2 points" in out         # outside every shape: the higher cost
    assert "projection total: 6 points = 0.12 weeks" in out


def test_similar_shapes_pool(tmp_path, capsys):
    cfg, _, _ = _lib(tmp_path)
    dead = _block(tmp_path, "dead", 20, (30, 40), (10, 12))
    funk = _block(tmp_path, "funk", 20, (0, 12), (0, 2))     # 0.6 vs 0.5 per show: within 0.25
    cell = lambda n: {"unvoiced": n, "voiced": 0}
    q = _queue(tmp_path, {"dead": {"fresh": cell(22)}, "bluegrass": {"fresh": cell(22)}})
    rc, out = _report(cfg, capsys, "--block", f"dead-fresh={dead}", "--block", f"funk-fresh={funk}",
                      "--queue", str(q), "--weekly-share", "50")
    assert "fresh: pooled" in out
    # pooled 5h = 22 points / 40 shows = 0.55; ratio = 4/22; per-show 7d = 0.1
    assert "projection dead: 2.2 points" in out
    assert "projection bluegrass: 2.2 points" in out


def test_align_reproduced_rate(tmp_path, capsys):
    cfg, _, _ = _lib(tmp_path)
    d = _block(tmp_path, "nl", 4, (30, 40), (10, 12), kind="needs-llm",
               align=[True, True, False, None])
    q = _queue(tmp_path, {})
    rc, out = _report(cfg, capsys, "--block", f"dead-needs-llm={d}", "--queue", str(q),
                      "--weekly-share", "50")
    assert rc == 0
    assert "align_reproduced: 2/3" in out


def _append_line(d, slug, kind, at, calls):
    row = {"slug": slug, "outcome": "cleared", "retryable": False, "kind": kind, "at": at,
           "llm_calls": calls, "meter": {"before": _meter(90, 90), "after": _meter(95, 95)}}
    with (d / "progress.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")


def test_foreign_spend_hidden_by_a_later_retry_is_caught(tmp_path, capsys):
    cfg, _, _ = _lib(tmp_path)
    d = _block(tmp_path, "b", 20, (30, 40), (10, 12))
    _add_row(d, "zz", "needs-llm", "2026-10-27T10:05:30+00:00", 2)      # inside, spent
    _append_line(d, "zz", "needs-llm", "2026-10-27T12:00:00+00:00", 2)  # re-run outside
    q = _queue(tmp_path, {"dead": {"fresh": {"unvoiced": 5, "voiced": 0}}})
    rc, out = _report(cfg, capsys, "--block", f"dead-fresh={d}", "--queue", str(q),
                      "--weekly-share", "50")
    assert ("dead-fresh: not contiguous: 1 spending row(s) of another kind inside it; "
            "re-run as one block per kind") in out
    assert "per-show 5h" not in out and "7d/5h ratio" not in out
    assert "no usable block" in out


@pytest.mark.parametrize("at", ["2026-10-27T10:00:00+00:00", "2026-10-27T10:19:00+00:00"])
def test_foreign_window_is_inclusive(tmp_path, capsys, at):
    cfg, _, _ = _lib(tmp_path)
    d = _block(tmp_path, "b", 20, (30, 40), (10, 12))
    _add_row(d, "zz", "needs-llm", at, 2)       # exactly the block's first / last row's `at`
    q = _queue(tmp_path, {"dead": {"fresh": {"unvoiced": 5, "voiced": 0}}})
    rc, out = _report(cfg, capsys, "--block", f"dead-fresh={d}", "--queue", str(q),
                      "--weekly-share", "50")
    assert "not contiguous: 1 spending row(s) of another kind inside it" in out
