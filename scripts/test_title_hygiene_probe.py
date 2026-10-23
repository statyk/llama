"""scripts/title_hygiene_probe.py dump: the title-hygiene gate probe (plan Task 13).

A tmp library of gd73/gd74 fixture shows (cache files, provenance and show dirs; one
show with an `overrides.json` holding titles and a structure override), dumped on the
fresh-get and as-is views. Gate 0 is the proof that `title_inputs` + `title_cascade` with
every slice off reproduce today's `compute_gather` title block.
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "llama" / "tests"))

import title_hygiene_probe as thp
from fixture_library import FIXTURES, IDENT, build_library, replay_config
from herder import FakeProvider
from llama.models import (Candidate, Overrides, Provenance, RecordingSummary, ResearchVetting,
                          Track, VettingResult)
from llama.stages.gather import title_cascade
from llama.title_cosmetics import cosmetic_strip
from llama.title_hygiene import ALL_SLICES
from llama.workspace import ShowWorkspace, write_artifact

W_IDENT = "gd74-02-24.sbd.windsor.199.sbefail.shnf"
M_IDENT = "gd1974-02-24.sbd.miller.116902.flac16"
N_IDENT = "gd73-06-12.numbered.test"
GD74 = "gratefuldead-1974-02-24"
NUMBERED = "gratefuldead-1973-06-12"
NUMBERED_DESC = ("1. Morning Dew\n2. China Cat Sunflower\n3. I Know You Rider\n"
                 "4. Dark Star\n5. Eyes of the World\n6. Johnny B. Goode")


class _IA:
    def __init__(self, mapping):
        self.mapping = mapping

    def metadata(self, identifier):
        return json.loads(json.dumps(self.mapping[identifier]))


def _gathered_show(root: Path, slug: str, cand: Candidate, ident: str, mapping: dict):
    for i, md in mapping.items():
        (root / "cache" / f"md_{i}.json").write_text(json.dumps(md))
    ws = ShowWorkspace(root / "shows" / slug)
    write_artifact(ws.provenance, Provenance(performance_id=cand.performance_id, run="r1",
                                             dossier="d", candidate=cand,
                                             processed_at="2026-10-23T00:00:00+00:00"))
    cfg = replay_config(root)
    from llama.stages.gather import run_gather
    show = run_gather(ws, _IA(mapping), FakeProvider(), cand, ident,
                      structure_cfg=cfg.structure, jerrybase_enabled=cfg.jerrybase.enabled)
    write_artifact(ws.show, show)
    write_artifact(ws.vetting, VettingResult(vetting=ResearchVetting(
        asserted_songs=[], asserted_dates=[cand.date])))
    return ws


def _library(root: Path) -> Path:
    """build_library's two gd73 shows (track 1's tag made `Morning Dew.wav`, a slice-5
    shape), plus the gd74 Windsor show (Miller sibling) with title and structure
    overrides, plus a gd73 copy with a numbered count-matched description and blank tags
    at tracks 2, 3 and 6 (D's rung)."""
    build_library(root)
    md = json.loads((FIXTURES / "gd73_metadata.json").read_text())
    md["files"] = [dict(f, title="Morning Dew.wav") if f["name"] == "gd73-06-10d1t01.mp3"
                   else f for f in md["files"]]
    (root / "cache" / f"md_{IDENT}.json").write_text(json.dumps(md))

    gd74 = Candidate(performance_id="GratefulDead/1974-02-24", collection="GratefulDead",
                     date="1974-02-24", venue="Winterland Arena", city="San Francisco, CA",
                     recordings=[RecordingSummary(identifier=W_IDENT),
                                 RecordingSummary(identifier=M_IDENT)])
    mapping = {W_IDENT: json.loads((FIXTURES / "gd74_windsor_metadata.json").read_text()),
               M_IDENT: json.loads((FIXTURES / "gd74_miller_metadata.json").read_text())}
    for f in mapping[W_IDENT]["files"]:        # sibling-align's shape (test_title_cascade)
        if f["name"].endswith(("D1_T04.mp3", "D1_T05.mp3", "D1_T06.mp3")):
            f["title"] = None
    ws = _gathered_show(root, GD74, gd74, W_IDENT, mapping)
    write_artifact(ws.overrides, Overrides(titles={1: "Operator Title", 4: "Fourth"},
                                           set_breaks=[10]))

    num = json.loads((FIXTURES / "gd73_metadata.json").read_text())
    num["metadata"]["description"] = NUMBERED_DESC
    for f in num["files"]:
        if f["name"] in ("gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3", "gd73-06-10d3t01.mp3"):
            f["title"] = None
        if f["name"] == "gd73-06-10d2t01.mp3":
            f["title"] = "Dark Star.wav"
    cand = Candidate(performance_id="GratefulDead/1973-06-12", collection="GratefulDead",
                     date="1973-06-12", venue="RFK Stadium", city="Washington, DC",
                     recordings=[RecordingSummary(identifier=N_IDENT)])
    _gathered_show(root, NUMBERED, cand, N_IDENT, {N_IDENT: num})
    return root / "config.toml"


def _dump(tmp_path: Path, *extra: str, out: str = "out") -> tuple[dict, list[dict]]:
    cfg = tmp_path / "lib" / "config.toml"
    if not cfg.exists():
        _library(tmp_path / "lib")
    rc = thp.main(["dump", "--config", str(cfg), "--out", str(tmp_path / out), *extra])
    assert rc == 0
    lines = (tmp_path / out / "dump.jsonl").read_text().splitlines()
    meta = json.loads(lines[0])
    return meta, [json.loads(ln) for ln in lines[1:]]


@pytest.fixture(autouse=True)
def _no_setlistfm(monkeypatch):
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)


def test_gate0_parity_on_fixtures(tmp_path):
    meta, rows = _dump(tmp_path)
    assert set(meta["_meta"]) >= {"sha", "config_fingerprint", "setlistfm_configured", "n"}
    assert meta["_meta"]["n"] == len(rows) == 4
    for r in rows:
        assert r["unreplayable"] is None, r["slug"]
        # The `gate0`/`gate0_as_is` asserts are gone (plan Task 16, orchestrator ruling):
        # gate 0 was the PRE-WIRING proof that title_inputs + title_cascade with no slices
        # reproduce compute_gather's own title block, measured 3983/3983 on both views at
        # Checkpoint A. Since Task 16 compute_gather runs the cascade itself (all slices);
        # on this tree `today` is not the old block and gate 0 measures nothing.
    # Not vacuous: D fills on the numbered show, sibling-align ran on gd74, S on gd73.
    by = {r["slug"]: r for r in rows}
    # Read from arm `none` (Task 16): on the wired tree `today` is the all-slices gather, where
    # slice 3 (spec "Placement: the tag layer, per track") fills Windsor's blanked tracks from
    # the item's own lossless copy before sibling-align runs.
    assert "sibling-align" in {t["source"] for t in by[GD74]["arms"]["none"]["tracks"]}
    assert "setlist" in {t["source"] for t in by["gratefuldead-1973-06-10"]["today"]}
    assert "D" in by[NUMBERED]["arms"]["all"]["paths"]
    assert by[NUMBERED]["desc"]["used"] == "numbered"


def test_gate0_reports_the_first_difference(tmp_path, monkeypatch):
    real = thp.G.title_cascade

    def bent(inp, *, enabled):
        out = real(inp, enabled=enabled)
        if not enabled:
            t = out.tracks[1]
            out.tracks[1] = t.model_copy(update={"title": "Bent"})
        return out
    monkeypatch.setattr(thp.G, "title_cascade", bent)
    _, rows = _dump(tmp_path)
    r = next(r for r in rows if r["slug"] == "gratefuldead-1973-06-11")
    assert r["gate0"] is False and r["gate0_as_is"] is False
    assert r["gate0_diff"].startswith("track 2 title:")


def test_strips_titles_and_structure_overrides_in_the_shadow(tmp_path):
    cfg = _library(tmp_path / "lib")
    live = tmp_path / "lib" / "shows" / GD74 / "overrides.json"
    before = hashlib.sha256(live.read_bytes()).hexdigest()
    _, rows = _dump(tmp_path)
    assert hashlib.sha256(live.read_bytes()).hexdigest() == before
    r = next(r for r in rows if r["slug"] == GD74)
    assert r["stripped"] == {"titles": {"1": "Operator Title", "4": "Fourth"}, "set_breaks": [10],
                              "encore_after": None}
    assert r["structure_override"] is True and r["title_override"] is True
    assert r["today"][0]["title"] != "Operator Title"
    assert r["today_as_is"][0] == {"title": "Operator Title", "source": "override"}
    assert all(t["source"] != "override" for t in r["arms"]["none"]["tracks"])
    assert r["arms_as_is"]["none"]["tracks"][3]["source"] == "override"
    other = next(r for r in rows if r["slug"] == NUMBERED)
    assert other["stripped"] == {} and other["structure_override"] is False


def test_arms_present_and_slice5_applied_last(tmp_path):
    _, rows = _dump(tmp_path)
    want = {"none", "all"} | {f"all-{s}" for s in ALL_SLICES}
    plus5 = 0
    for r in rows:
        assert set(r["arms"]) == want
        assert set(r["arms_as_is"]) == {"none"}
        for name, arm in r["arms"].items():
            enabled = thp.ARMS[name]
            if "slice5" not in enabled:
                assert not any(p.endswith("+5") for p in arm["paths"])
            plus5 += sum(p.endswith("+5") for p in arm["paths"])
    assert plus5  # the `.wav` tags strip
    # Applied LAST: the arm's tracks are exactly cosmetic_strip over the cascade's output.
    inp = thp.inputs_for(tmp_path / "lib" / "config.toml", NUMBERED)
    for name, enabled in thp.ARMS.items():
        raw = title_cascade(inp, enabled=enabled).tracks
        want_tracks = cosmetic_strip(raw)[0] if "slice5" in enabled else raw
        r = next(r for r in rows if r["slug"] == NUMBERED)
        assert [t["title"] for t in r["arms"][name]["tracks"]] == [t.title for t in want_tracks]
    r = next(r for r in rows if r["slug"] == NUMBERED)
    assert r["arms"]["all"]["tracks"][3]["title"] == "Dark Star"
    assert r["arms"]["all-slice5"]["tracks"][3]["title"] == "Dark Star.wav"


ALT_KEYS = ("alt_bare_number", "alt_hygiene_all_entries", "alt_encore_restart", "alt_c1",
            "alt_bracketed_s", "alt_encore_fold", "alt_check2_cleaned", "alt_c2_containment",
            "alt_filler_confirm")


def test_alternatives_present(tmp_path):
    _, rows = _dump(tmp_path)
    for r in rows:
        for key in ALT_KEYS:
            assert key in r, (r["slug"], key)
    n = next(r for r in rows if r["slug"] == NUMBERED)
    assert n["alt_encore_restart"]["default"] == "admitted"
    # the narrow baseline can only be stricter than the default reader
    assert n["alt_encore_restart"]["narrow"] == "admitted"
    assert not n["alt_encore_restart"]["admits_new"]
    assert n["alt_hygiene_all_entries"] is not None
    assert n["alt_encore_fold"] is not None


def test_jobs_workers_capture(tmp_path):
    m1, one = _dump(tmp_path, "--jobs", "1", out="one")
    m2, two = _dump(tmp_path, "--jobs", "2", out="two")
    assert m1 == m2
    assert one == two


def test_refuses_out_inside_library(tmp_path, capsys):
    cfg = _library(tmp_path / "lib")
    rc = thp.main(["dump", "--config", str(cfg), "--out", str(tmp_path / "lib" / "gate")])
    assert rc == 2
    assert "overlaps the library root" in capsys.readouterr().err
    assert not (tmp_path / "lib" / "gate").exists()


def test_refuses_a_llama_from_another_tree(tmp_path, monkeypatch, capsys):
    import llama
    monkeypatch.setattr(llama, "__file__", str(tmp_path / "elsewhere" / "llama" / "__init__.py"))
    rc = thp.main(["dump", "--config", str(tmp_path / "nope.toml"), "--out", str(tmp_path / "o")])
    assert rc == 2
    assert "refusing to run: llama imports from" in capsys.readouterr().err


# --- the alternatives' own rules, on synthetic inputs ----------------------------------------

def _t(i, title, source="tags"):
    return Track(index=i + 1, set="1", title=title, filename=f"t{i + 1:02d}.mp3",
                 title_source=source)


def test_check2_cleaned_compares_a_cleaned_neighbour():
    tracks = [_t(0, "Bertha (4:47)"), _t(1, "x", "unresolved"), _t(2, "Loser")]
    assert thp.adjacent_duplicate_cleaned({1: "Bertha"}, tracks) == (1, "Bertha", "Bertha")
    from llama.title_hygiene import adjacent_duplicate
    assert adjacent_duplicate({1: "Bertha"}, tracks) is None   # the built check: raw title


def test_bracketed_s_keeps_only_runs_closed_by_independent_song_titles():
    tracks = [_t(0, "Bertha"), _t(1, "A", "setlist"), _t(2, "Loser"),
              _t(3, "B", "setlist"), _t(4, "Tuning")]
    got = thp.bracketed_s(tracks, ["", "S", "", "S", ""])
    assert got["remain"] == [1] and got["dropped"] == [3]


def test_c2_containment_flags_agreement_only_through_containment():
    assert thp.c2_arms("Mood To Move", "Mood To Move")["strict"] is True
    arms = thp.c2_arms("Jam", "Dark Star Jam")
    assert arms["strict"] is False and arms["containment"] is True


def test_bracketed_s_both_sides_excludes_the_leading_edge_run():
    tracks = [_t(0, "A", "setlist"), _t(1, "Bertha"), _t(2, "Loser")]
    got = thp.bracketed_s(tracks, ["S", "", ""])
    assert got["remain"] == [0]                    # gap_span's one-sided leading branch
    assert got["remain_both_sides"] == [] and got["dropped_both_sides"] == [0]
    both = thp.bracketed_s([_t(0, "Bertha"), _t(1, "A", "setlist"), _t(2, "Loser")],
                           ["", "S", ""])
    assert both["remain_both_sides"] == [1]


def test_c2_containment_only_is_the_containment_arm_alone():
    assert thp.c2_arms("Jam", "Dark Star Jam")["containment_only"] is True
    assert thp.c2_arms("Mood To Move", "Mood To Move")["containment_only"] is False
    # containment AND a ratio at or over LOOSE_TITLE_RATIO is not containment-only
    assert thp.c2_arms("Dark Star Jam", "Dark Star Jams")["containment_only"] is False
    # the ratio arm alone, no containment
    assert thp.c2_arms("Mister Charlie", "Mr Charlie")["containment_only"] is False
    # a short core never uses the containment arm
    assert thp.c2_arms("Me", "Me And My Uncle")["containment_only"] is False


def test_gate0_failures_counts_none_on_replayable_rows():
    assert thp.gate0_failures({"unreplayable": None, "gate0": None,
                               "unreplayable_as_is": None, "gate0_as_is": True}) == 1
    assert thp.gate0_failures({"unreplayable": "x", "gate0": None,
                               "unreplayable_as_is": "x", "gate0_as_is": None}) == 0
    assert thp.gate0_failures({"unreplayable": None, "gate0": False,
                               "unreplayable_as_is": None, "gate0_as_is": False}) == 2


# --- the gate table (plan Task 14) -------------------------------------------------------------

import copy  # noqa: E402

HEADINGS = [f"R{i}" for i in range(20)] + ["R2b", "Notes for Checkpoint A"]


def _rec(**kw):
    base = {"wholly_untagged": False, "fetch_siblings": False, "s_positions": [], "lossless": None,
            "s_plan": {"mode": "none", "fills": {}, "deferred": {}, "declined": [], "notes": []},
            "d": None, "short4": [], "short4_declined": {}, "gap_filled": [],
            "deferred_applied": []}
    base.update(kw)
    return base


def _arm(titles, sources, paths=None, *, rec=None, cov=1.0, self_filled=False, notes=()):
    return {"tracks": [{"title": t, "source": s} for t, s in zip(titles, sources)],
            "paths": list(paths or [""] * len(titles)), "coverage": cov,
            "self_filled": self_filled, "op_notes": list(notes), "struct_notes": [],
            "record": rec or _rec()}


def _row(slug, today, new, paths, *, flags=(), rec=None, canon="setlist.fm", **kw):
    """today / new: [(title, source)]."""
    none = _arm([t for t, _ in today], [s for _, s in today])
    allarm = _arm([t for t, _ in new], [s for _, s in new], paths, rec=rec)
    arms = {"none": none, "all": allarm}
    for s in ("slice1", "slice2", "slice3", "slice4", "slice5"):
        arms[f"all-{s}"] = copy.deepcopy(allarm)
    row = {"slug": slug, "today": [{"n": i + 1, "title": t, "source": s}
                                   for i, (t, s) in enumerate(today)],
           "today_flags": list(flags), "today_notes": [], "arms": arms, "arms_as_is": {"none": none},
           "canonical": {"source": canon, "confidence": "high", "needs_llm": False, "items": []},
           "desc": {"used": None}, "structure_override": False, "title_override": False,
           "gate0": True, "gate0_as_is": True, "unreplayable": None, "unreplayable_as_is": None,
           "s_candidates": [], "alt_bare_number": [], "alt_hygiene_all_entries": None,
           "alt_encore_restart": None, "alt_c1": None, "alt_bracketed_s": {"applies": False},
           "alt_encore_fold": None, "alt_check2_cleaned": {"calls": [], "would_decline": {}},
           "alt_c2_containment": None, "alt_filler_confirm": []}
    row.update(kw)
    return row


def _hc_row(cls, slug, tracks, verdict):
    return {"slug": slug, "class": cls, "show_verdict": verdict, "note": "",
            "tracks": [{"n": n, "candidate": c, "verdict": v, "correct_title": ct, "why": ""}
                       for n, c, v, ct in tracks]}


def _write_gate_inputs(tmp_path, rows, hc):
    d = tmp_path / "dump.jsonl"
    meta = {"_meta": {"sha": "x", "config_fingerprint": "f", "setlistfm_configured": True,
                      "n": len(rows), "align_coverage_threshold": 0.8}}
    d.write_text("\n".join(json.dumps(x) for x in [meta, *rows]) + "\n")
    hdir = tmp_path / "handcheck"
    for cls, items in hc.items():
        (hdir / cls).mkdir(parents=True)
        (hdir / cls / "rows.jsonl").write_text("\n".join(json.dumps(i) for i in items) + "\n")
    return d, hdir


def _three_rows():
    d_rec = _rec(wholly_untagged=True,
                 d={"fills": {"0": "Bertha", "1": "Loser"}, "failed": [], "track_declines": {},
                    "shift": False})
    a = _row("a-2000-01-01", [("01.mp3", "unresolved"), ("02.mp3", "unresolved")],
             [("Bertha", "desc-position"), ("Loser", "desc-position")], ["D", "D"], rec=d_rec,
             flags=["unresolved track titles"])
    a["arms"]["all"]["self_filled"] = True
    b = _row("b-2000-01-02", [("X", "setlist"), ("Y", "setlist")],
             [("X", "unresolved"), ("Y", "unresolved")], ["", ""], canon="chosen",
             rec=_rec(s_plan={"mode": "untagged", "fills": {}, "deferred": {}, "declined": [0, 1],
                              "notes": ["positional fill declined: setlist wholly untagged tape"]}))
    c = _row("c-2000-01-03", [("Dark Star.wav", "tags"), ("Jam", "tags")],
             [("Dark Star", "tags"), ("Jam", "tags")], ["+5", ""])
    return [a, b, c]


def _hc():
    return {"D": [_hc_row("D", "a-2000-01-01", [(1, "Bertha", "right", "Bertha"),
                                                 (2, "Loser", "wrong", "Row Jimmy")],
                          "some-wrong-not-shift")],
            "S0": [_hc_row("S", "b-2000-01-02", [(1, "X", "wrong", "Z")], "shifted")],
            "A": [_hc_row("A", "c-2000-01-03", [(1, "Dark Star", "right-partial", "Dark Star")],
                          "strip-fixes-it")]}


def test_judged_vs_inferred_vs_unjudged(tmp_path):
    _, hdir = _write_gate_inputs(tmp_path, [], {"D": [_hc_row(
        "D", "s", [(1, "Bertha", "right", "Bertha"), (2, "Loser", "wrong", "Row Jimmy"),
                   (3, "Jam", "cant-tell", None), (4, "X", "wrong", "Dark Star")], "all-right")]})
    hc = thp.HandCheck.load(hdir)
    assert hc.judge("s", 1, "Bertha") == ("judged", "right")
    assert hc.judge("s", 2, "Loser") == ("judged", "wrong")
    assert hc.judge("s", 3, "Jam") == ("judged", "cant-tell")
    # a candidate that differs from the new title: inferred from correct_title via agrees()
    assert hc.judge("s", 4, "Dark Star") == ("inferred", "right")
    assert hc.judge("s", 4, "Eyes of the World") == ("inferred", "wrong")
    assert hc.judge("s", 3, "Something Else") == ("unjudged", None)   # no correct_title
    assert hc.judge("s", 9, "Nope") == ("unjudged", None)
    assert hc.judge("s", 1, "Bertha", classes={"S"}) == ("unjudged", None)  # another class


def test_show_verdict_mapping():
    g = thp.verdict_group
    assert [g(v) for v in ("all-right", "fix-helps", "strip-fixes-it")] == ["good"] * 3
    assert [g(v) for v in ("shifted", "some-wrong-not-shift", "fix-hurts", "mixed",
                           "strip-would-damage", "strip-not-enough")] == ["bad"] * 6
    assert g("fix-neutral") == "neutral" and g("cant-tell") == "cant-tell"
    # never pooled: the tally keeps its own columns
    t = thp.tally_groups(["good", "bad", "neutral", "cant-tell", None])
    assert t == {"good": 1, "bad": 1, "neutral": 1, "cant-tell": 1, "unchecked": 1}


def test_newly_held_approximation():
    r = _row("h", [("a", "unresolved")], [("a", "desc-position")], ["D"],
             flags=["unresolved track titles", "low-confidence structure alignment"])
    # today's flags minus the two, plus low-confidence unless self-filled or covered, plus
    # `unresolved track titles` when any track is unresolved
    assert thp.held_arm(r, "all", 0.8) is False           # coverage 1.0 reaches the threshold
    r["arms"]["all"]["coverage"] = 0.5
    assert thp.held_arm(r, "all", 0.8) is True
    r["arms"]["all"]["self_filled"] = True
    assert thp.held_arm(r, "all", 0.8) is False
    r["arms"]["all"]["tracks"][0]["source"] = "unresolved"
    assert thp.held_arm(r, "all", 0.8) is True
    r["arms"]["all"]["tracks"][0]["source"] = "tags"
    r["today_flags"] = ["research asserts 2 sets but structure has 1"]
    assert thp.held_arm(r, "all", 0.8) is True
    assert thp.held_today(r) is True


def test_untagged_unchecked_list(tmp_path):
    rows = _three_rows()
    for slug, wholly in (("a-2000-01-01", True), ("b-2000-01-02", True), ("c-2000-01-03", True)):
        r = next(x for x in rows if x["slug"] == slug)
        r["arms"]["all"]["record"]["wholly_untagged"] = wholly
        n = len(r["arms"]["all"]["tracks"])
        r["desc"] = {"used": "numbered", "numbered": {"n": n}}
    rows[2]["desc"] = {"used": "numbered", "numbered": {"n": 5}}        # not count-matched
    d, hdir = _write_gate_inputs(tmp_path, rows, {
        "U0": [_hc_row("U", "a-2000-01-01", [(1, "Bertha", "right", "Bertha")], "all-right")]})
    out = tmp_path / "out"
    assert thp.main(["gate", "--dump", str(d), "--handcheck", str(hdir),
                     "--census", str(tmp_path / "none.jsonl"), "--out", str(out)]) == 0
    assert (out / "untagged_unchecked.txt").read_text().split() == ["b-2000-01-02"]
    table = (out / "gate_table.md").read_text()
    assert "R13" in table


def test_alternative_rows_read_the_dump(tmp_path):
    rows = _three_rows()
    a, b, c = rows
    b["alt_bracketed_s"] = {"applies": True, "fills": [0, 1], "remain": [0], "dropped": [1],
                            "remain_both_sides": [], "dropped_both_sides": [0, 1], "runs": []}
    a["alt_bare_number"] = [{"pos": 0, "text": "7", "own_core": "", "judge": {"ok": False},
                             "exemption_decided": True}]
    a["alt_hygiene_all_entries"] = {"d_ran": True, "candidates": [0], "failures": [],
                                    "extra": [{"pos": 5, "check": "hygiene:timestamp",
                                               "text": "12:00", "candidate": False}]}
    a["alt_encore_restart"] = {"default": "admitted", "encore_header": "admitted", "narrow": "non-contiguous at 9",
                               "admits_new": True, "count_matched": True}
    c["alt_c1"] = {"declined": "C1 unconfirmed", "c_holds": None,
                   "targets": [{"pos": 0, "a": True, "b": None, "adopted": False},
                               {"pos": 1, "a": False, "b": False, "adopted": False}],
                   "would_pass_alone": 1, "via_c_where_ab_disagreed": []}
    d, hdir = _write_gate_inputs(tmp_path, rows, _hc())
    out = tmp_path / "out"
    assert thp.main(["gate", "--dump", str(d), "--handcheck", str(hdir),
                     "--census", str(tmp_path / "none.jsonl"), "--out", str(out)]) == 0
    data = {json.loads(ln)["row"]: json.loads(ln)["data"]
            for ln in (out / "gate_rows.jsonl").read_text().splitlines()}
    assert data["R4"]["gap_span"]["shows_with_drops"] == 1
    assert data["R4"]["gap_span"]["dropped"] == 1
    assert data["R4"]["both_sides"]["dropped"] == 2
    assert data["R14"]["shows"] == 1
    assert data["R15"]["shows_with_extra"] == 1
    assert data["R16"]["admits_new"] == 1
    assert data["R17"]["declined_shows"] == 1
    assert data["R17"]["targets"] == 2 and data["R17"]["would_pass_alone"] == 1


def test_q1_declines_need_a_non_empty_decline(tmp_path):
    rows = _three_rows()
    quiet = copy.deepcopy(rows[1])
    quiet["slug"] = "q-2000-01-04"
    quiet["arms"]["all"]["record"]["s_plan"] = {"mode": "untagged", "fills": {}, "deferred": {},
                                                "declined": [], "notes": []}
    notes_only = copy.deepcopy(quiet)
    notes_only["slug"] = "n-2000-01-05"
    notes_only["arms"]["all"]["record"]["s_plan"]["notes"] = ["positional fill declined: x"]
    d, hdir = _write_gate_inputs(tmp_path, [*rows, quiet, notes_only], _hc())
    out = tmp_path / "out"
    assert thp.main(["gate", "--dump", str(d), "--handcheck", str(hdir),
                     "--census", str(tmp_path / "none.jsonl"), "--out", str(out)]) == 0
    data = {json.loads(ln)["row"]: json.loads(ln)["data"]
            for ln in (out / "gate_rows.jsonl").read_text().splitlines()}
    assert data["R5"]["q1"]["shows"] == 1            # the mode-only show is not a Q1 decline
    assert data["R5"]["q1"]["tracks"] == 2
    assert data["R5"]["q1"]["verdicts"]["bad"] == 1


def test_gate0_row_treats_none_as_failing(tmp_path):
    rows = _three_rows()
    rows[0]["gate0"] = None
    d, hdir = _write_gate_inputs(tmp_path, rows, _hc())
    out = tmp_path / "out"
    assert thp.main(["gate", "--dump", str(d), "--handcheck", str(hdir),
                     "--census", str(tmp_path / "none.jsonl"), "--out", str(out)]) == 0
    data = {json.loads(ln)["row"]: json.loads(ln)["data"]
            for ln in (out / "gate_rows.jsonl").read_text().splitlines()}
    assert data["R0"]["fresh"] == {"pass": 2, "total": 3}


def test_every_row_heading_present(tmp_path):
    d, hdir = _write_gate_inputs(tmp_path, _three_rows(), _hc())
    out = tmp_path / "out"
    assert thp.main(["gate", "--dump", str(d), "--handcheck", str(hdir),
                     "--census", str(tmp_path / "none.jsonl"), "--out", str(out)]) == 0
    table = (out / "gate_table.md").read_text()
    for h in HEADINGS:
        assert f"## {h}" in table or f"## {h}." in table or f"## {h} " in table, h
    assert (out / "samples").is_dir() and (out / "untagged_unchecked.txt").exists()
    assert table.index("## R19") < table.index("## Notes for Checkpoint A")


def test_notes_section_reads_the_dump(tmp_path):
    rows = _three_rows()
    rows[0]["desc"] = {"used": "parse", "numbered": {"reason": "non-contiguous at 9"},
                       "parse": {"reason": None, "reader": "parse", "n": 2, "entries": []}}
    rows[1]["desc"] = {"used": None, "numbered": {"reason": "no numbered lines"},
                       "parse": {"reason": "per-line count disagrees"}}
    rows[0]["alt_c1"] = {"declined": None, "c_holds": True, "targets": [],
                         "would_pass_alone": 0, "via_c_where_ab_disagreed": [3]}
    d, hdir = _write_gate_inputs(tmp_path, rows, _hc())
    out = tmp_path / "out"
    assert thp.main(["gate", "--dump", str(d), "--handcheck", str(hdir),
                     "--census", str(tmp_path / "none.jsonl"), "--out", str(out)]) == 0
    data = {json.loads(ln)["row"]: json.loads(ln)["data"]
            for ln in (out / "gate_rows.jsonl").read_text().splitlines()}
    n = data["NOTES"]
    assert n["reader_i_reasons"] == {"no numbered lines": 1, "non-contiguous at N": 1}
    assert n["reader_ii_reasons"] == {"per-line count disagrees": 1}
    assert n["parse_with_noncontiguous_numbered"]["shows"] == 1
    assert n["c1_via_c_disagreed"]["shows"] == 1


def _gate(tmp_path, rows, hc):
    d, hdir = _write_gate_inputs(tmp_path, rows, hc)
    out = tmp_path / "out"
    assert thp.main(["gate", "--dump", str(d), "--handcheck", str(hdir),
                     "--census", str(tmp_path / "none.jsonl"), "--out", str(out)]) == 0
    data = {json.loads(ln)["row"]: json.loads(ln)["data"]
            for ln in (out / "gate_rows.jsonl").read_text().splitlines()}
    return data, (out / "gate_table.md").read_text()


def test_ablation_counts_only_positions_where_the_slice_arm_differs(tmp_path):
    data, table = _gate(tmp_path, _three_rows(), _hc())     # every all-<slice> equals `all`
    for s in ("slice1", "slice2", "slice3", "slice4", "slice5"):
        assert data["R1"]["ablation"][s]["score"]["tracks"] == 0, s
    rows = _three_rows()
    rows[0]["arms"]["all-slice2"]["tracks"][1] = {"title": "02.mp3", "source": "unresolved"}
    (tmp_path / "b").mkdir()
    data, _ = _gate(tmp_path / "b", rows, _hc())
    assert data["R1"]["ablation"]["slice2"]["score"]["tracks"] == 1
    assert data["R1"]["ablation"]["slice1"]["score"]["tracks"] == 0
    assert "residual" in table


def test_changed_means_different_from_today(tmp_path):
    rows = _three_rows()
    same = _row("s-2000-01-06", [("X", "setlist")], [("X", "setlist")], ["S"],
                rec=_rec(s_positions=[0]))
    data, _ = _gate(tmp_path, [*rows, same], _hc())
    assert data["R5"]["ships_silently"]["slice1"]["changed_shows"] == 1   # b only (removed S)
    assert data["R1"]["ablation"]["slice1"]["path_shows"] == 1


def test_removed_fills_keep_judged_and_inferred_apart(tmp_path):
    rows = _three_rows()
    hc = _hc()
    hc["S0"] = [_hc_row("S", "b-2000-01-02", [(1, "X", "wrong", "Z"), (2, "Other", "wrong", "Q")],
                        "shifted")]
    data, table = _gate(tmp_path, rows, hc)
    rem = data["R1"]["removed"]["S removed"]
    assert (rem["judged_wrong"], rem["inferred_wrong"], rem["unjudged"]) == (1, 1, 0)
    assert "wrong+inferred" not in table


def test_slice1_bar_counts_newly_held_non_q1_good_shows(tmp_path):
    lost = _row("g-2000-01-07", [("X", "setlist")], [("g.mp3", "unresolved")], [""],
                rec=_rec(s_plan={"mode": "gated", "fills": {}, "deferred": {}, "declined": [0],
                                 "notes": []}))
    already = _row("h-2000-01-08", [("X", "setlist")], [("h.mp3", "unresolved")], [""],
                   flags=["unresolved track titles"],
                   rec=_rec(s_plan={"mode": "gated", "fills": {}, "deferred": {},
                                    "declined": [0], "notes": []}))
    hc = _hc()
    hc["S1"] = [_hc_row("S", "g-2000-01-07", [(1, "X", "right", "X")], "all-right"),
                _hc_row("S", "h-2000-01-08", [(1, "X", "right", "X")], "all-right")]
    data, table = _gate(tmp_path, [lost, already], hc)
    assert data["R2"]["good_lost_other"] == 2
    assert data["R2"]["bar_newly_held_non_q1_good"] == 1


def test_r11_splits_d_from_non_d(tmp_path):
    d_row = _row("d-2000-01-09", [("a", "unresolved")], [("A", "desc-position")], ["D"],
                 flags=[thp.LOWC_FLAG],
                 rec=_rec(d={"fills": {"0": "A"}, "failed": [], "track_declines": {}}))
    d_row["arms"]["all"]["self_filled"] = True
    no_d = _row("e-2000-01-10", [("a", "tags")], [("a", "tags")], [""], flags=[thp.LOWC_FLAG])
    no_d["arms"]["all"]["self_filled"] = True
    data, _ = _gate(tmp_path, [d_row, no_d], {})
    assert data["R11"]["newly_above"] == 2 and data["R11"]["with_d"] == 1
    assert sum(data["R11"]["by_denominator"].values()) == 1


def test_r4_good_shows_exclude_already_held(tmp_path):
    held = _row("k-2000-01-11", [("X", "setlist")], [("k.mp3", "unresolved")], [""],
                alt_bracketed_s={"applies": True, "fills": [0], "remain": [], "dropped": [0],
                                 "remain_both_sides": [], "dropped_both_sides": [0], "runs": []})
    hc = {"S0": [_hc_row("S", "k-2000-01-11", [(1, "X", "right", "X")], "all-right")]}
    data, _ = _gate(tmp_path, [held], hc)
    assert data["R4"]["gap_span"]["shows_with_drops"] == 1
    assert data["R4"]["gap_span"]["good_lost"] == 0


def test_note_four_names_dates(tmp_path):
    _, table = _gate(tmp_path, _three_rows(), _hc())
    assert "dates" in table.split("## Notes for Checkpoint A")[1]


# --- Task 19: parity and packets ----------------------------------------------------------------

def _dump_row(slug, titles, *, wholly=False, desc="1. A\n2. B", paths=None, ident=None):
    tr = [{"title": t, "source": s} for t, s in titles]
    return {"slug": slug, "unreplayable": None, "state": "held", "identifier": ident or f"id-{slug}",
            "description": desc, "canonical": {"source": "chosen", "items": []},
            "today": [{"n": i + 1, "title": "Track %02d" % (i + 1), "source": "unresolved",
                       "duration": 100.0 + i, "filename": f"f{i + 1}.mp3", "raw_tag": None}
                      for i in range(len(titles))],
            "arms": {"all": {"tracks": tr, "paths": paths or [""] * len(tr),
                             "record": {"wholly_untagged": wholly}}}}


def _write_dump(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(x) for x in [{"_meta": {"sha": "s", "n": len(rows)}}, *rows]) + "\n")


def test_parity_lists_mismatches(tmp_path):
    dump = tmp_path / "gate" / "dump.jsonl"
    _write_dump(dump, [
        _dump_row("same", [("A", "tags"), ("B", "desc-position")]),
        _dump_row("diff", [("A", "tags"), ("B", "desc-position")]),
        _dump_row("short", [("A", "tags")]),
        _dump_row("gone", [("A", "tags")]),
    ])
    rows = {"same": [("A", "tags"), ("B", "desc-position")],
            "diff": [("A", "tags"), ("Bee", "desc-position")],
            "short": [("A", "tags"), ("Z", "setlist")]}
    shows = {s: {"outcome": "clean", "titles": [t for t, _ in v], "title_sources": [x for _, x in v]}
             for s, v in rows.items()}
    shows["gone"] = {"outcome": "unreplayable", "titles": [], "title_sources": []}
    arm = tmp_path / "cand.json"
    arm.write_text(json.dumps({"title_overrides_stripped": True, "structure_overrides_stripped": True,
                               "disabled_slices": [], "shows": shows}))
    out = tmp_path / "out"
    assert thp.main(["parity", "--arm", str(arm), "--dump", str(dump), "--out", str(out)]) == 1
    text = (out / "parity.txt").read_text()
    assert "compared 3, matching 1, mismatching 2" in text
    assert "diff  #2: dump ('B', 'desc-position') vs arm ('Bee', 'desc-position')" in text
    assert "short  track count: dump 1 vs arm 2" in text
    assert "same" not in text.split("== mismatches")[1]
    assert "gone" in text and "skipped" in text      # unreplayable arm row is skipped, not compared
    # a clean arm exits 0, and a non-fresh-get arm is flagged
    arm.write_text(json.dumps({"shows": {"same": shows["same"]}}))
    assert thp.main(["parity", "--arm", str(arm), "--dump", str(dump), "--out", str(out)]) == 0
    assert "WARNING: arm is not a fresh-get arm" in (out / "parity.txt").read_text()


def _titles_row(state="held", cleared=True, d=0, self_filled=False, paths=None, changes=None,
                slice4=False, n=3):
    return {"state": state, "base_outcome": "still-held", "cand_outcome": "clears",
            "newly_cleared": cleared, "self_filled": self_filled, "d_fills": d, "slice4": slice4,
            "titles": [f"T{i}" for i in range(n)], "title_sources": ["desc-position"] * n,
            "title_paths": paths or ["D"] * n,
            "changes": changes if changes is not None else
            [{"index": i + 1, "old": "Track", "new": f"T{i}", "old_source": "unresolved",
              "new_source": "desc-position", "path": "D", "kind": "text"} for i in range(n)]}


def _packets_setup(tmp_path, shows, dump_rows):
    cmp_dir = tmp_path / "cmp"
    cmp_dir.mkdir()
    root = tmp_path / "lib"
    (root / "cache").mkdir(parents=True)
    (cmp_dir / "title_rows.json").write_text(json.dumps({"cand_sha": "x", "root": str(root),
                                                        "shows": shows}))
    dump = tmp_path / "gate" / "dump.jsonl"
    _write_dump(dump, dump_rows)
    return cmp_dir, dump, root


def test_packets_strata(tmp_path):
    shows, rows = {}, []
    # stratum 1: wholly untagged, newly cleared, 3+ D fills; and a self-filled one with 2 fills
    shows["wu3"] = _titles_row(d=3)
    shows["wu-self"] = _titles_row(d=2, self_filled=True)
    shows["wu2"] = _titles_row(d=2)            # fewer than 3 D fills and not self-filled: the sample
    for s in ("wu3", "wu-self", "wu2"):
        rows.append(_dump_row(s, [("T0", "desc-position")] * 3, wholly=True))
    # 70 other newly cleared shows over two path signatures
    for i in range(70):
        s = f"oth{i:02d}"
        shows[s] = _titles_row(paths=["C1" if i % 2 else "D"] * 3)
        rows.append(_dump_row(s, [("T0", "tags")] * 3))
    # every changed title on a delivered show (text only); a source-only change is not listed
    shows["del-text"] = _titles_row(state="delivered", cleared=False)
    shows["del-src"] = _titles_row(state="delivered", cleared=False, changes=[
        {"index": 1, "old": "A", "new": "A", "old_source": "setlist", "new_source": "desc-position",
         "path": "D", "kind": "source"}])
    shows["pk"] = _titles_row(state="packaged", cleared=False)        # not delivered: in no stratum
    shows["s4"] = _titles_row(state="packaged", cleared=False, slice4=True, paths=["", "4", ""],
                              changes=[{"index": 2, "old": "J", "new": "J", "old_source": "unresolved",
                                        "new_source": "tags", "path": "4", "kind": "source"}])
    for s in ("del-text", "del-src", "pk", "s4"):
        rows.append(_dump_row(s, [("T0", "tags")] * 3))
    extra = tmp_path / "enc.txt"
    extra.write_text("pk\n\nnot-in-dump\n")
    cmp_dir, dump, root = _packets_setup(tmp_path, shows, rows)
    out = tmp_path / "packets"
    args = ["packets", "--cmp", str(cmp_dir), "--dump", str(dump), "--out", str(out),
            "--extra", f"r16-encore={extra}"]
    assert thp.main(args) == 0
    ls = lambda d: sorted(p.stem for p in (out / d).glob("*.md"))     # noqa: E731
    assert ls("wholly_untagged_d3") == ["wu-self", "wu3"]
    sample = ls("newly_cleared_sample")
    assert len(sample) == 60
    assert not set(sample) & {"wu3", "wu-self"}
    assert ls("delivered_changes") == ["del-text"]
    assert ls("slice4") == ["s4"]
    assert ls("r16-encore") == ["not-in-dump", "pk"]
    idx = (out / "strata_index.txt").read_text().splitlines()
    assert "s4\tslice4\t#2 4" in idx
    assert "wu3\twholly_untagged_d3\t#1 D; #2 D; #3 D" in idx
    # both path signatures are in the sample (stratified, not a prefix of the sorted list)
    assert any(s in sample for s in (f"oth{i:02d}" for i in range(1, 70, 2)))
    assert any(s in sample for s in (f"oth{i:02d}" for i in range(0, 70, 2)))
    # deterministic: a second run reproduces the sample and the index byte for byte
    out2 = tmp_path / "packets2"
    assert thp.main(["packets", "--cmp", str(cmp_dir), "--dump", str(dump), "--out", str(out2),
                     "--extra", f"r16-encore={extra}"]) == 0
    assert (out2 / "strata_index.txt").read_text() == (out / "strata_index.txt").read_text()
    # a packet carries description, per-file titles/durations and the changed positions
    pkt = (out / "wholly_untagged_d3" / "wu3.md").read_text()
    assert "1. A" in pkt and "f1.mp3" in pkt and "T0" in pkt and "100s" in pkt
    assert "not in the dump" in (out / "r16-encore" / "not-in-dump.md").read_text()


def test_packets_siblings_and_name_refusals(tmp_path, capsys):
    shows = {"a": _titles_row(d=3)}
    cmp_dir, dump, root = _packets_setup(tmp_path, shows, [_dump_row("a", [("T0", "x")] * 3, wholly=True)])
    (root / "shows" / "a").mkdir(parents=True)
    (root / "shows" / "a" / "selection.json").write_text(json.dumps({"scores": {
        "id-a": {"title_fraction": 0.0}, "sib1": {"title_fraction": 0.95, "score": 3, "kept_tracks": 2},
        "sib2": {"title_fraction": 0.2, "score": 2}}}))
    (root / "cache" / "md_sib1.json").write_text(json.dumps({"files": [
        {"name": "s1.mp3", "title": "Sugaree", "length": "301.5"},
        {"name": "s2.mp3", "title": "Deal", "length": "4:10"}]}))
    out = tmp_path / "p"
    assert thp.main(["packets", "--cmp", str(cmp_dir), "--dump", str(dump), "--out", str(out)]) == 0
    pkt = (out / "wholly_untagged_d3" / "a.md").read_text()
    assert "sib1" in pkt and "Sugaree" in pkt and "250s" in pkt and "sib2" not in pkt
    for bad in ("x/y=" + str(tmp_path / "f"), "slice4=" + str(tmp_path / "f"), "nofile"):
        assert thp.main(["packets", "--cmp", str(cmp_dir), "--dump", str(dump),
                         "--out", str(tmp_path / "q"), "--extra", bad]) == 2


def test_packets_and_parity_refuse_an_out_inside_the_library(tmp_path, capsys):
    cmp_dir, dump, root = _packets_setup(tmp_path, {"a": _titles_row(d=3)},
                                         [_dump_row("a", [("T0", "x")] * 3, wholly=True)])
    assert thp.main(["packets", "--cmp", str(cmp_dir), "--dump", str(dump),
                     "--out", str(root / "p")]) == 2
    arm = tmp_path / "arm.json"
    arm.write_text(json.dumps({"root": str(root), "shows": {}}))
    assert thp.main(["parity", "--arm", str(arm), "--dump", str(dump), "--out", str(root / "q")]) == 2
    assert "overlaps the library root" in capsys.readouterr().err
    assert not (root / "p").exists() and not (root / "q").exists()
    # a packet states where its candidate titles came from
    out = tmp_path / "ok"
    assert thp.main(["packets", "--cmp", str(cmp_dir), "--dump", str(dump), "--out", str(out)]) == 0
    assert "candidate title source: the compare arm" in (out / "wholly_untagged_d3" / "a.md").read_text()
