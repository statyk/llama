"""scripts/short_keep_probe.py: arm reports (spec 6) and the post-migration self-check (4.3)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import short_keep_probe as skp


def rtrack(n, f, title, src="tags", st="1", segue=False):
    return {"n": n, "file": f, "title": title, "src": src, "set": st, "segue": segue}


def ref_row(slug, tracks, flags=(), state="held", ov=None, replayed=True):
    return {"slug": slug, "state": state, "voiced": False, "flags": list(flags), "tracks": tracks,
            "ov": ov or {"include": [], "exclude": [], "titles": {}, "set_breaks": None,
                         "encore_after": None, "narration": "full"},
            "replayed": replayed}


def crow(tracks, flags=(), breaks=(), outcome="clean-changed", **kw):
    """tracks: (file, title, src, set, segue)."""
    row = {"outcome": outcome, "filenames": [t[0] for t in tracks], "titles": [t[1] for t in tracks],
           "title_sources": [t[2] for t in tracks], "sets": [t[3] for t in tracks],
           "segues": [t[4] for t in tracks], "breaks": list(breaks), "flags": list(flags),
           "unreplayable": None, "state": "held"}
    row.update(kw)
    return row


def write_ref(d, base_rows, r1_rows):
    d.mkdir(parents=True, exist_ok=True)
    for name, rows in (("arm_base.jsonl", base_rows), ("arm_r1.jsonl", r1_rows)):
        (d / name).write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def write_arm(p, shows):
    p.write_text(json.dumps({"shows": shows}))


def run_arms(tmp_path, base_rows, r1_rows, base_arm, cand_arm, capsys=None):
    ref = tmp_path / "ref"
    write_ref(ref, base_rows, r1_rows)
    write_arm(tmp_path / "base.json", base_arm)
    write_arm(tmp_path / "cand.json", cand_arm)
    out = tmp_path / "out"
    rc = skp.main(["arms", "--base", str(tmp_path / "base.json"), "--cand", str(tmp_path / "cand.json"),
                   "--ref-dir", str(ref), "--out", str(out)])
    return rc, out


T2 = [rtrack(1, "a.mp3", "A"), rtrack(2, "b.mp3", "B")]


def base_replay(tracks, **kw):
    row = {"outcome": "still-held", "titles": [t["title"] for t in tracks], "gather_flags": [],
           "vet_flags": [], "brief_flags": [], "stored_flags": []}
    row.update(kw)
    return row


def test_base_consistency_lists_mismatches(tmp_path):
    b1 = ref_row("s1", T2)
    b2 = ref_row("s2", T2, flags=["x"])
    base = {"s1": base_replay(T2), "s2": base_replay(T2)}   # s2 flags missing
    base["s1"]["titles"] = ["A", "changed"]
    cand = {s: crow([("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "1", False)])
            for s in ("s1", "s2")}
    rc, out = run_arms(tmp_path, [b1, b2], [b1, b2], base, cand)
    res = json.loads((out / "arms.json").read_text())
    assert any(m.startswith("s1: titles differ") for m in res["base_consistency"])
    assert any(m.startswith("s2: flags differ") for m in res["base_consistency"])
    assert (out / "arms.md").exists()


def test_base_consistency_counts_carried_package_flags(tmp_path):
    from llama.stages import package as package_stage
    pkg = package_stage.FLAG_PREFIX + " x"
    b1 = ref_row("s1", T2, flags=["g", pkg, "brief"])
    base = {"s1": base_replay(T2, gather_flags=["g"], stored_flags=[pkg, "venue mismatch: q"],
                              brief_flags=["brief"])}
    cand = {"s1": crow([("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "1", False)],
                       flags=["g", pkg, "brief"])}
    rc, out = run_arms(tmp_path, [b1], [b1], base, cand)
    assert json.loads((out / "arms.json").read_text())["base_consistency"] == []


def test_reference_reproduction_per_show(tmp_path):
    b = ref_row("s1", T2)
    r1 = ref_row("s1", [rtrack(1, "a.mp3", "A"), rtrack(2, "b.mp3", "B", src="setlist")])
    cand = {"s1": crow([("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "1", False)])}
    rc, out = run_arms(tmp_path, [b], [r1], {"s1": base_replay(T2)}, cand)
    rep = json.loads((out / "arms.json").read_text())["reference_reproduction"]
    assert rep == ["s1: title_sources differ"]


def test_tallies_match_m3_definitions(tmp_path):
    # s1 unchanged; s2 changed: file added, hold cleared; s3 changed: hold added (new unresolved)
    s1 = ref_row("s1", T2)
    s2 = ref_row("s2", T2, flags=["unresolved track titles: 1"], state="delivered")
    s3 = ref_row("s3", T2)
    c1 = crow([("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "1", False)])
    c2 = crow([("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "1", False),
               ("c.mp3", "C", "tags", "1", False)])
    c3 = crow([("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "1", False),
               ("z.mp3", "(unresolved)", "unresolved", "1", False)], flags=["unresolved track titles: 3"])
    base = {s: base_replay(T2) for s in ("s1", "s2", "s3")}
    base["s2"]["gather_flags"] = ["unresolved track titles: 1"]
    rc, out = run_arms(tmp_path, [s1, s2, s3], [s1, s2, s3], base, {"s1": c1, "s2": c2, "s3": c3})
    res = json.loads((out / "arms.json").read_text())
    assert res["counts"] == {"unchanged": 1, "changed": 2, "files added": 2, "cleared": 1, "added": 1}
    assert res["cleared_by_state"] == {"delivered": 1}
    assert res["added_by_state"] == {"held": 1}
    assert res["added_classes"] == {"new unresolved track": 1}
    assert [c[0] for c in res["cleared"]] == ["s2"]
    assert "s2" in (out / "arms.md").read_text()


def _added_case(i, kind):
    """A show that gains a hold of class `kind`."""
    s = ref_row(f"s{i}", T2)
    tr = [("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "1", False)]
    if kind == "new unresolved track":
        return s, crow(tr + [("z.mp3", "?", "unresolved", "1", False)], flags=["unresolved track titles: 3"])
    if kind == "long single-set show":
        return s, crow(tr + [("z.mp3", "Z", "tags", "1", False)],
                       flags=["single-set structure for a long show (160 min)"])
    if kind == "low confidence remains":
        return s, crow(tr, flags=["low-confidence structure alignment (0.5)"])
    if kind == "jerrybase closer not at a break":
        return s, crow(tr, flags=["jerrybase set closer X is not at a break"])
    return s, crow(tr, flags=["something else"])


def _many(tmp_path, counts):
    refs, cands, i = [], {}, 0
    for kind, n in counts.items():
        for _ in range(n):
            i += 1
            r, c = _added_case(i, kind)
            refs.append(r)
            cands[r["slug"]] = c
    base = {r["slug"]: base_replay(T2) for r in refs}
    return run_arms(tmp_path, refs, refs, base, cands)


def test_added_hold_classes_and_the_25_percent_rule(tmp_path, capsys):
    rc, out = _many(tmp_path, {"new unresolved track": 22, "long single-set show": 6, "other": 1})
    res = json.loads((out / "arms.json").read_text())
    assert res["added_classes"] == {"new unresolved track": 22, "long single-set show": 6, "other": 1}
    assert res["blocks"] == []          # 22 <= 1.25 * 18
    assert rc == 0
    tmp = tmp_path / "two"
    tmp.mkdir()
    rc, out = _many(tmp, {"new unresolved track": 23})
    res = json.loads((out / "arms.json").read_text())
    assert res["blocks"] == ["BLOCKS MERGE: new unresolved track 23 (expected 18)"]
    assert "BLOCKS MERGE: new unresolved track 23 (expected 18)" in (out / "arms.md").read_text()
    assert rc == 1
    t3 = tmp_path / "three"
    t3.mkdir()
    rc, out = _many(t3, {"low confidence remains": 3, "jerrybase closer not at a break": 2})
    assert json.loads((out / "arms.json").read_text())["blocks"] == []


def test_override_shift_blocks(tmp_path):
    ov = {"include": [], "exclude": [], "titles": {"2": "Right"}, "set_breaks": None,
          "encore_after": None, "narration": "full"}
    s = ref_row("s1", [rtrack(1, "a.mp3", "A"), rtrack(2, "b.mp3", "Right", src="override")], ov=ov)
    c = crow([("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "1", False),
              ("z.mp3", "Right", "override", "1", False)], flags=["unresolved track titles: 2"])
    rc, out = run_arms(tmp_path, [s], [s], {"s1": base_replay(s["tracks"])}, {"s1": c})
    res = json.loads((out / "arms.json").read_text())
    assert res["added_classes"] == {"override shift": 1}
    assert res["override_title_moved"] == ["s1"]
    assert res["blocks"] == ["BLOCKS MERGE: override shift 1 (expected 0)"]
    assert rc == 1


def test_override_structure_moved_is_reported(tmp_path):
    ov = {"include": [], "exclude": [], "titles": {}, "set_breaks": [2], "encore_after": 3,
          "narration": "full"}
    tr = [rtrack(1, "a.mp3", "A"), rtrack(2, "b.mp3", "B", st="1"), rtrack(3, "c.mp3", "C", st="2"),
          rtrack(4, "d.mp3", "D", st="encore")]
    s = ref_row("s1", tr, ov=ov)
    ok = crow([("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "1", False),
               ("c.mp3", "C", "tags", "2", False), ("d.mp3", "D", "tags", "encore", False)], breaks=[2])
    moved = crow([("a.mp3", "A", "tags", "1", False), ("x.mp3", "X", "tags", "1", False),
                  ("b.mp3", "B", "tags", "1", False), ("c.mp3", "C", "tags", "2", False),
                  ("d.mp3", "D", "tags", "encore", False)], breaks=[2])   # break now after x.mp3
    for case, cand, expect in (("ok", ok, []), ("moved", moved, ["break after b.mp3"])):
        d = tmp_path / case
        d.mkdir()
        rc, out = run_arms(d, [s], [s], {"s1": base_replay(tr)}, {"s1": cand})
        res = json.loads((out / "arms.json").read_text())
        got = res["override_structure_moved"]
        assert [m for _, ms in got for m in ms] == expect
    # the encore, too
    enc = crow([("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "1", False),
                ("c.mp3", "C", "tags", "encore", False), ("d.mp3", "D", "tags", "encore", False)],
               breaks=[2])
    d = tmp_path / "enc"
    d.mkdir()
    rc, out = run_arms(d, [s], [s], {"s1": base_replay(tr)}, {"s1": enc})
    assert json.loads((out / "arms.json").read_text())["override_structure_moved"] == \
        [["s1", ["encore after c.mp3"]]]


def test_positional_fills_lost_and_gained(tmp_path):
    lost = ref_row("lost", [rtrack(1, "a.mp3", "A", src="setlist")])
    gain = ref_row("gain", [rtrack(1, "a.mp3", "?", src="unresolved")])
    c_lost = crow([("a.mp3", "?", "unresolved", "1", False)])
    c_gain = crow([("a.mp3", "A", "desc-position", "1", False)])
    base = {"lost": base_replay(lost["tracks"]), "gain": base_replay(gain["tracks"])}
    rc, out = run_arms(tmp_path, [lost, gain], [lost, gain], base, {"lost": c_lost, "gain": c_gain})
    res = json.loads((out / "arms.json").read_text())
    assert res["positional_lost"] == [["lost", 1]] and res["positional_gained"] == [["gain", 1]]


def test_unreplayable_candidate_is_counted_and_listed(tmp_path):
    s = ref_row("s1", T2)
    c = {"outcome": "unreplayable", "unreplayable": "boom"}
    rc, out = run_arms(tmp_path, [s], [s], {"s1": base_replay(T2)}, {"s1": c})
    res = json.loads((out / "arms.json").read_text())
    assert res["unreplayable"] == [["s1", "boom"]]
    assert any("unreplayable in the candidate" in m for m in res["reference_reproduction"])


def test_arms_refuses_candidate_rows_without_fields_and_overlapping_out(tmp_path):
    s = ref_row("s1", T2)
    write_ref(tmp_path / "ref", [s], [s])
    write_arm(tmp_path / "base.json", {"s1": base_replay(T2)})
    write_arm(tmp_path / "cand.json", {"s1": {"outcome": "clean", "titles": ["A", "B"]}})
    args = ["arms", "--base", str(tmp_path / "base.json"), "--cand", str(tmp_path / "cand.json"),
            "--ref-dir", str(tmp_path / "ref")]
    assert skp.main(args + ["--out", str(tmp_path / "o")]) == 2
    assert skp.main(args + ["--out", str(tmp_path / "ref" / "o")]) == 2     # inside the reference dir


# --- repro ---

def arm_row(tracks=None, breaks=(1,), outcome="clean", **kw):
    tracks = tracks or [("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "2", False),
                        ("c.mp3", "C", "tags", "encore", False)]
    return crow(tracks, breaks=breaks, outcome=outcome, **kw)


def run_repro(tmp_path, pre, post):
    write_arm(tmp_path / "pre.json", pre)
    write_arm(tmp_path / "post.json", post)
    return skp.main(["repro", "--pre", str(tmp_path / "pre.json"), "--post", str(tmp_path / "post.json"),
                     "--out", str(tmp_path / "out")])


def test_repro_equal_passes(tmp_path):
    assert run_repro(tmp_path, {"s": arm_row()}, {"s": arm_row()}) == 0
    assert "equal replayable shows: 1" in (tmp_path / "out" / "repro.md").read_text()


@pytest.mark.parametrize("name,post", [
    ("segue", arm_row(tracks=[("a.mp3", "A", "tags", "1", True), ("b.mp3", "B", "tags", "2", False),
                              ("c.mp3", "C", "tags", "encore", False)])),
    ("break", arm_row(breaks=(2,))),
    ("encore", arm_row(tracks=[("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "encore", False),
                               ("c.mp3", "C", "tags", "encore", False)])),
    ("source", arm_row(tracks=[("a.mp3", "A", "override", "1", False), ("b.mp3", "B", "tags", "2", False),
                               ("c.mp3", "C", "tags", "encore", False)])),
    ("outcome", arm_row(outcome="clears")),
])
def test_repro_compares_tracks_breaks_and_encore(tmp_path, name, post):
    assert run_repro(tmp_path, {"s": arm_row()}, {"s": post}) == 1
    assert "differences (" in (tmp_path / "out" / "repro.md").read_text()


def test_repro_one_arm_only_exits_1(tmp_path):
    assert run_repro(tmp_path, {"s": arm_row(), "t": arm_row()}, {"s": arm_row()}) == 1


def test_repro_refuses_rows_without_the_fields(tmp_path):
    old = arm_row()
    del old["filenames"]
    assert run_repro(tmp_path, {"s": old}, {"s": arm_row()}) == 1
    assert "lacks" in (tmp_path / "out" / "repro.md").read_text()


def test_repro_treats_equal_unreplayable_as_equal(tmp_path):
    u = {"outcome": "unreplayable", "unreplayable": "CacheMiss: x"}
    assert run_repro(tmp_path, {"s": u}, {"s": dict(u)}) == 0
    assert "CacheMiss: x" in (tmp_path / "out" / "repro.md").read_text()
    v = {"outcome": "unreplayable", "unreplayable": "other"}
    assert run_repro(tmp_path, {"s": u}, {"s": v}) == 1
