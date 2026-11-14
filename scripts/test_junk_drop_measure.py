"""scripts/junk_drop_measure.py compare: synthetic arms, baseline TSV and library under tmp_path."""
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import junk_drop_measure as jm

HEAD = ["slug", "index", "filename", "title", "rule", "duration_sec", "pct_show", "x_median",
        "held", "station", "voiced_backend"]


def _drop(fn, title, rule="A", set_="1", after=0, held=False, dur=100.0):
    return {"filename": fn, "title": title, "set": set_, "after_track": after,
            "duration_sec": dur, "rule": rule, "held": held}


def _row(files, titles=None, sets=None, segues=None, outcome="packaged", drops=None, needs_llm=()):
    r = {"filenames": list(files), "titles": list(titles or [f"T-{f}" for f in files]),
         "sets": list(sets or ["1"] * len(files)), "segues": list(segues or [False] * len(files)),
         "outcome": outcome, "needs_llm": list(needs_llm)}
    if drops is not None:
        r["junk_drops"] = drops
    return r


def _arm(path, shows):
    path.write_text(json.dumps({"shows": shows}))
    return path


def _tsv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(HEAD)
        for slug, fn, title, rule, held in rows:
            w.writerow([slug, 1, fn, title, rule, 100.0, 1.0, 0.5, held, True, ""])
    return path


def _library(root, shows, overrides=None):
    lib = root / "lib" / "shows"
    for slug, tracks in shows.items():
        d = lib / slug
        d.mkdir(parents=True)
        (d / "show.json").write_text(json.dumps({"tracks": [
            {"filename": f, "title": t, "set": "1", "index": i + 1}
            for i, (f, t) in enumerate(tracks)]}))
        if overrides and slug in overrides:
            (d / "overrides.json").write_text(json.dumps(overrides[slug]))
    return lib


def _run(tmp_path, base, cand, tsv, lib, out=None):
    out = out or tmp_path / "out"
    code = jm.main(["compare", "--base", str(base), "--cand", str(cand), "--baseline", str(tsv),
                    "--shows", str(lib), "--out", str(out)])
    return code, out


def _diffs(out):
    with open(out / "differences.tsv") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _cat(out, side, slug, fn):
    return [r["category"] for r in _diffs(out)
            if (r["side"], r["slug"], r["filename"]) == (side, slug, fn)]


def test_candidate_only_categories(tmp_path):
    lib = _library(tmp_path, {"s": [("a.mp3", "Tuning"), ("b.mp3", "Tuning / Banana"), ("c.mp3", "Tuning"),
                                    ("e.mp3", "Intro"), ("g.mp3", "Tuning"), ("k.mp3", "Real")]})
    base = _arm(tmp_path / "b.json", {"s": _row(["a.mp3", "b.mp3", "c.mp3", "e.mp3", "g.mp3", "k.mp3", "z.mp3"])})
    drops = [_drop("a.mp3", "Tuning (renamed)"),       # show.json title differs
             _drop("zz.mp3", "Tuning"),                 # not in show.json
             _drop("b.mp3", "Tuning / Banana"),         # parts-split: no regex matches
             _drop("e.mp3", "Intro", rule="B"),         # edge-run
             _drop("g.mp3", "Tuning")]                  # other
    cand = _arm(tmp_path / "c.json", {"s": _row(["k.mp3"], drops=drops)})
    tsv = _tsv(tmp_path / "d.tsv", [])
    code, out = _run(tmp_path, base, cand, tsv, lib)
    assert code == 3    # the Banana and (renamed) parts are outside the vocabulary
    assert _cat(out, "cand", "s", "a.mp3") == ["title-differs"]
    assert _cat(out, "cand", "s", "zz.mp3") == ["not-in-show.json"]
    assert _cat(out, "cand", "s", "b.mp3") == ["parts-split"]
    assert _cat(out, "cand", "s", "e.mp3") == ["edge-run"]
    assert _cat(out, "cand", "s", "g.mp3") == ["other"]
    assert "title_baseline" in (out / "differences.tsv").read_text().splitlines()[0]


def test_baseline_only_categories(tmp_path):
    names = ["inc", "arr", "llm", "tdf", "nk", "oth"]
    lib = _library(tmp_path, {
        "s": [(f"{n}.mp3", "Tuning") for n in names],
        "u": [("u.mp3", "Tuning")]},
        overrides={"s": {"include": ["inc.mp3"]}})
    files = [f"{n}.mp3" for n in names]
    base = _arm(tmp_path / "b.json", {"s": _row(files), "u": _row(["u.mp3"])})
    cand = _arm(tmp_path / "c.json", {
        "s": _row(["inc.mp3", "arr.mp3", "tdf.mp3", "oth.mp3"],
                  titles=["Tuning", "Tuning >", "Tuning (x)", "Tuning"]),
        "u": _row([], outcome="needs-llm", needs_llm=["x"])})
    tsv = _tsv(tmp_path / "d.tsv", [("s", f, "Tuning", "A", False) for f in files]
               + [("u", "u.mp3", "Tuning", "A", False)])
    code, out = _run(tmp_path, base, cand, tsv, lib)
    assert code == 0
    got = {fn: _cat(out, "baseline", slug, fn) for slug, fn in
           [("s", f) for f in files] + [("u", "u.mp3")]}
    assert got == {"inc.mp3": ["operator-include"], "arr.mp3": ["arrowed"],
                   "llm.mp3": ["not-kept"], "tdf.mp3": ["title-differs"],
                   "nk.mp3": ["not-kept"], "oth.mp3": ["other"], "u.mp3": ["needs-llm-row"]}


def test_agreeing_drop_is_not_a_difference(tmp_path):
    lib = _library(tmp_path, {"s": [("a.mp3", "Tuning"), ("k.mp3", "Real")]})
    base = _arm(tmp_path / "b.json", {"s": _row(["a.mp3", "k.mp3"])})
    cand = _arm(tmp_path / "c.json", {"s": _row(["k.mp3"], drops=[_drop("a.mp3", "Tuning")])})
    tsv = _tsv(tmp_path / "d.tsv", [("s", "a.mp3", "Tuning", "A", False)])
    code, out = _run(tmp_path, base, cand, tsv, lib)
    assert code == 0 and _diffs(out) == []
    assert "A" in (out / "summary.md").read_text()


def test_vocabulary_violation_exits_3(tmp_path):
    lib = _library(tmp_path, {"s": [("a.mp3", "Tuning"), ("b.mp3", "Tuning / Banana"), ("k.mp3", "R")]})
    base = _arm(tmp_path / "b.json", {"s": _row(["a.mp3", "b.mp3", "k.mp3"])})
    cand = _arm(tmp_path / "c.json", {"s": _row(["k.mp3"], drops=[
        _drop("a.mp3", "Tuning"), _drop("b.mp3", "Tuning / Banana")])})
    code, out = _run(tmp_path, base, cand, _tsv(tmp_path / "d.tsv", []), lib)
    assert code == 3
    text = (out / "vocabulary.txt").read_text()
    assert "b.mp3" in text and "a.mp3" not in text


def test_vocabulary_clean_exits_0_with_empty_file(tmp_path):
    lib = _library(tmp_path, {"s": [("a.mp3", "Crowd Noise"), ("k.mp3", "R")]})
    base = _arm(tmp_path / "b.json", {"s": _row(["a.mp3", "k.mp3"])})
    cand = _arm(tmp_path / "c.json", {"s": _row(["k.mp3"], drops=[_drop("a.mp3", "Crowd Noise")])})
    code, out = _run(tmp_path, base, cand, _tsv(tmp_path / "d.tsv", []), lib)
    assert code == 0 and (out / "vocabulary.txt").read_text() == ""


def test_base_row_without_junk_drops(tmp_path):
    lib = _library(tmp_path, {"s": [("k.mp3", "R")]})
    base = _arm(tmp_path / "b.json", {"s": _row(["k.mp3"])})
    assert "junk_drops" not in base.read_text()
    cand = _arm(tmp_path / "c.json", {"s": _row(["k.mp3"])})
    code, out = _run(tmp_path, base, cand, _tsv(tmp_path / "d.tsv", []), lib)
    assert code == 0 and _diffs(out) == []


def test_kept_track_set_change_is_reported(tmp_path):
    lib = _library(tmp_path, {"s": [("a.mp3", "Tuning"), ("k.mp3", "R"), ("m.mp3", "M"), ("n.mp3", "N")]})
    base = _arm(tmp_path / "b.json", {"s": _row(
        ["a.mp3", "k.mp3", "m.mp3", "n.mp3"], sets=["1", "1", "1", "2"], segues=[False, False, False, False])})
    cand = _arm(tmp_path / "c.json", {"s": _row(
        ["k.mp3", "m.mp3", "n.mp3"], titles=["T-k.mp3", "T-m.mp3", "T-n.mp3"],
        sets=["2", "1", "2"], segues=[False, False, False], drops=[_drop("a.mp3", "Tuning")])})
    code, out = _run(tmp_path, base, cand, _tsv(tmp_path / "d.tsv", []), lib)
    with open(out / "kept_track_deltas.tsv") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    assert [(r["filename"], r["set_base"], r["set_cand"], r["adjacent_to_drop"]) for r in rows] == [
        ("k.mp3", "1", "2", "False")]
    # a.mp3 is the track before k.mp3; adjacency is the NEXT pre-drop track: nothing drops after k.
    assert "segue_base" in (out / "kept_track_deltas.tsv").read_text().splitlines()[0]


def test_kept_track_adjacent_to_drop(tmp_path):
    lib = _library(tmp_path, {"s": [("k.mp3", "R"), ("a.mp3", "Tuning"), ("m.mp3", "M")]})
    base = _arm(tmp_path / "b.json", {"s": _row(["k.mp3", "a.mp3", "m.mp3"], segues=[True, False, False])})
    cand = _arm(tmp_path / "c.json", {"s": _row(
        ["k.mp3", "m.mp3"], titles=["T-k.mp3", "T-m.mp3"], segues=[False, False],
        drops=[_drop("a.mp3", "Tuning", after=1)])})
    code, out = _run(tmp_path, base, cand, _tsv(tmp_path / "d.tsv", []), lib)
    with open(out / "kept_track_deltas.tsv") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    assert [(r["filename"], r["segue_base"], r["segue_cand"], r["adjacent_to_drop"]) for r in rows] == [
        ("k.mp3", "True", "False", "True")]


def test_override_keys_name_a_dropped_file(tmp_path):
    lib = _library(tmp_path, {"s": [("k.mp3", "R"), ("a.mp3", "Tuning"), ("m.mp3", "M")]},
                   overrides={"s": {"set_breaks": ["a.mp3"], "encore_after": "zz.mp3"}})
    base = _arm(tmp_path / "b.json", {"s": _row(["k.mp3", "a.mp3", "m.mp3"])})
    cand = _arm(tmp_path / "c.json", {"s": _row(
        ["k.mp3", "m.mp3"], sets=["1", "2"], drops=[_drop("a.mp3", "Tuning", after=1)])})
    code, out = _run(tmp_path, base, cand, _tsv(tmp_path / "d.tsv", []), lib)
    with open(out / "override_keys.tsv") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    assert [(r["slug"], r["key"], r["filename"], r["set_before"], r["set_after"]) for r in rows] == [
        ("s", "set_breaks", "a.mp3", "1", "2")]


def test_refuses_out_inside_shows(tmp_path):
    lib = _library(tmp_path, {"s": [("k.mp3", "R")]})
    base = _arm(tmp_path / "b.json", {"s": _row(["k.mp3"])})
    cand = _arm(tmp_path / "c.json", {"s": _row(["k.mp3"])})
    for out in (lib.parent / "out", lib / "out", lib.parent):
        code, _ = _run(tmp_path, base, cand, _tsv(tmp_path / "d.tsv", []), lib, out=out)
        assert code == 2
    assert not (lib.parent / "out").exists() and not (lib / "out").exists()


def test_baseline_slug_missing_from_candidate_arm_is_not_in_arm(tmp_path):
    lib = _library(tmp_path, {"s": [("k.mp3", "R")], "gone": [("a.mp3", "Tuning")]})
    base = tmp_path / "b.json"
    base.write_text(json.dumps({"scope": "all", "shows": {"s": _row(["k.mp3"]), "e": _row([])}}))
    cand = tmp_path / "c.json"
    cand.write_text(json.dumps({"scope": "held", "shows": {"s": _row(["k.mp3"])}}))
    tsv = _tsv(tmp_path / "d.tsv", [("gone", "a.mp3", "Tuning", "A", False)])
    code, out = _run(tmp_path, base, cand, tsv, lib)
    assert code == 0
    assert _cat(out, "baseline", "gone", "a.mp3") == ["not-in-arm"]
    text = (out / "summary.md").read_text()
    assert "base arm shows: 2 (scope all)" in text
    assert "candidate arm shows: 1 (scope held)" in text
    assert "in both arms: 1" in text
    assert "absent from the candidate arm: 1" in text
    assert "absent from the base arm: 1" in text
    assert "empty filenames (skipped by kept-track deltas), base: 1" in text
    assert "- not-in-arm: 1" in text
