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


# --- fix round 1: per-field reproduction, class precedence, the library-root guard ---

REPRO_FIELDS = {
    "filenames": lambda c: c.update(filenames=["a.mp3", "q.mp3"]),
    "titles": lambda c: c.update(titles=["A", "Bx"]),
    "title_sources": lambda c: c.update(title_sources=["tags", "setlist"]),
    "sets": lambda c: c.update(sets=["1", "2"]),
    "segues": lambda c: c.update(segues=[False, True]),
    "flags": lambda c: c.update(flags=["a flag"]),
}


@pytest.mark.parametrize("field", sorted(REPRO_FIELDS))
def test_reference_reproduction_pins_each_field(tmp_path, field):
    b = ref_row("s1", T2)
    cand = crow([("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "1", False)])
    REPRO_FIELDS[field](cand)
    rc, out = run_arms(tmp_path, [b], [b], {"s1": base_replay(T2)}, {"s1": cand})
    res = json.loads((out / "arms.json").read_text())
    assert res["reference_reproduction"] == [f"s1: {field} differ"]


def _classify(tmp_path, ref, cand):
    rc, out = run_arms(tmp_path, [ref], [ref], {ref["slug"]: base_replay(ref["tracks"])},
                       {ref["slug"]: cand})
    return json.loads((out / "arms.json").read_text())["added_classes"]


def test_class_precedence_positional_lost_beats_new_unresolved(tmp_path):
    # the ratdog-2007-08-12 shape: a setlist fill reverts, a kept file is unresolved, and the
    # show carries low-confidence, structure, unresolved and research flags
    ref = ref_row("ratdog", [rtrack(1, "a.mp3", "A", src="setlist"), rtrack(2, "b.mp3", "B")])
    cand = crow([("a.mp3", "?", "unresolved", "1", False), ("b.mp3", "B", "tags", "1", False),
                 ("z.mp3", "?", "unresolved", "1", False)],
                flags=["low-confidence structure alignment", "unresolved track titles: 1, 3",
                       "research asserts unknown song: Cassidy"])
    assert _classify(tmp_path, ref, cand) == {"positional rung lost": 1}


def test_class_precedence_new_unresolved_beats_later_classes(tmp_path):
    ref = ref_row("s1", T2)
    cand = crow([("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "1", False),
                 ("z.mp3", "?", "unresolved", "1", False)],
                flags=["single-set structure for a long show (160 min)", "jerrybase set closer X"])
    assert _classify(tmp_path, ref, cand) == {"new unresolved track": 1}


def test_class_precedence_long_single_set_beats_closer(tmp_path):
    ref = ref_row("s1", T2)
    cand = crow([("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "1", False)],
                flags=["jerrybase set closer X", "single-set structure for a long show (160 min)"])
    assert _classify(tmp_path, ref, cand) == {"long single-set show": 1}


def test_low_confidence_plus_another_new_flag_is_not_low_confidence_remains(tmp_path):
    ref = ref_row("s1", T2)
    cand = crow([("a.mp3", "A", "tags", "1", False), ("b.mp3", "B", "tags", "1", False)],
                flags=["low-confidence structure alignment", "research asserts unknown song: X"])
    assert _classify(tmp_path, ref, cand) == {"other": 1}


def _config(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{lib}"\n')
    return cfg, lib


def test_arms_refuses_an_out_inside_the_configured_library_root(tmp_path):
    cfg, lib = _config(tmp_path)
    s = ref_row("s1", T2)
    write_ref(tmp_path / "ref", [s], [s])
    write_arm(tmp_path / "base.json", {"s1": base_replay(T2)})
    write_arm(tmp_path / "cand.json", {"s1": crow([("a.mp3", "A", "tags", "1", False),
                                                   ("b.mp3", "B", "tags", "1", False)])})
    args = ["arms", "--base", str(tmp_path / "base.json"), "--cand", str(tmp_path / "cand.json"),
            "--ref-dir", str(tmp_path / "ref"), "--config", str(cfg)]
    assert skp.main(args + ["--out", str(lib / "o")]) == 2
    assert not (lib / "o").exists()
    assert skp.main(args + ["--out", str(tmp_path / "fine")]) == 0     # the guard is not a blanket refusal


def test_repro_refuses_an_out_inside_the_configured_library_root(tmp_path):
    cfg, lib = _config(tmp_path)
    write_arm(tmp_path / "pre.json", {"s": arm_row()})
    write_arm(tmp_path / "post.json", {"s": arm_row()})
    args = ["repro", "--pre", str(tmp_path / "pre.json"), "--post", str(tmp_path / "post.json"),
            "--config", str(cfg)]
    assert skp.main(args + ["--out", str(lib / "o")]) == 2
    assert not (lib / "o").exists()
    assert skp.main(args + ["--out", str(tmp_path / "fine")]) == 0


# ---- packets / score / sibvocab (Task 8) -------------------------------------------------

def _frow(slug, name, kind, r1_dec, tagged=True, rp_tagged=True, tag="x"):
    return {"slug": slug, "state": "held", "name": name, "dur": 30.0, "tag": tag, "tagged": tagged,
            "kind": kind, "pos": "interior", "floor": 90.0, "rp_tagged": rp_tagged, "r1_dec": r1_dec}


STRATA_SIZES = {"music": 10, "music-fragment": 5, "spoken": 10, "mixed-with-tuning": 6,
                "untagged-interior": 8, "placeholder-tagged": 3,
                "drop-junk": 8, "drop-nonperf": 5, "drop-edge": 3, "drop-filename": 2}


def _packet_world(tmp_path, extra=0):
    """One show `s1` with 15+ candidates per stratum (names `<stratum>-<k>.mp3`), a cached item
    with those files, and a candidate arm keeping every non-drop one."""
    lib = tmp_path / "lib"
    (lib / "shows" / "s1").mkdir(parents=True)
    (lib / "cache").mkdir()
    (lib / "shows" / "s1" / "show.json").write_text(json.dumps({"identifier": "item1"}))
    (tmp_path / "config.toml").write_text(f'root = "{lib}"\n')
    rows, kept, files = [], [], []
    spec = {"music": ("music", "keep", True, True), "music-fragment": ("music-fragment", "keep", True, True),
            "spoken": ("spoken", "keep", True, True), "mixed-with-tuning": ("mixed-with-tuning", "keep", True, True),
            "untagged-interior": ("untagged", "keep-untagged", False, False),
            "placeholder-tagged": ("music", "keep", False, True),
            "drop-junk": ("tuning/dead-air/noise", "drop-junk", True, True),
            "drop-nonperf": ("non-performance", "drop-nonperf", True, True),
            "drop-edge": ("untagged", "drop-edge", False, False),
            "drop-filename": ("untagged", "drop-filename", False, False)}
    n = 0
    for st, (kind, dec, tagged, rpt) in spec.items():
        for k in range(15 + extra):
            n += 1
            name = f"{st}-{k}.mp3"
            rows.append(_frow("s1", name, kind, dec, tagged, rpt, tag=f"tag {st} {k}"))
            files.append({"name": name, "format": "VBR MP3", "source": "original", "track": str(n),
                          "title": f"tag {st} {k}", "length": "30"})
            if not dec.startswith("drop"):
                kept.append(name)
    files.append({"name": "zzz.mp3", "format": "VBR MP3", "source": "original", "track": "999",
                  "title": "Last", "length": "300"})
    (lib / "cache" / "md_item1.json").write_text(json.dumps(
        {"metadata": {"description": "d" * 4000}, "files": files}))
    ref = tmp_path / "ref"
    ref.mkdir()
    (ref / "r1_files.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    cand = crow([(f, "T", "tags", "1", False) for f in kept + ["zzz.mp3"]],
                short_kept=[True] * len(kept) + [False])
    write_arm(tmp_path / "cand.json", {"s1": cand})
    return ref


def _packets(tmp_path, out, seed=None):
    args = ["packets", "--cand", str(tmp_path / "cand.json"), "--ref-dir", str(tmp_path / "ref"),
            "--config", str(tmp_path / "config.toml"), "--out", str(out)]
    return skp.main(args + (["--seed", str(seed)] if seed is not None else []))


def test_packet_strata_sizes_and_fields(tmp_path):
    _packet_world(tmp_path)
    out = tmp_path / "out"
    assert _packets(tmp_path, out) == 0
    rows = [json.loads(l) for l in (out / "packet.jsonl").read_text().splitlines()]
    from collections import Counter
    assert dict(Counter(r["stratum"] for r in rows)) == STRATA_SIZES
    assert [r["row"] for r in rows] == list(range(1, 61))
    for r in rows:
        assert r["rule_would"] == ("drop" if r["stratum"].startswith("drop") else "keep")
        assert "rule_R_would" not in r
    r = rows[0]
    assert {"class", "stratum", "rule_would", "slug", "state", "item", "url", "file", "dur_sec", "tag",
            "position", "floor_sec", "neighbours_in_play_order", "census_kind", "description"} <= set(r)
    assert r["item"] == "item1" and r["url"] == "https://archive.org/details/item1"
    assert len(r["description"]) == 3000
    nb = r["neighbours_in_play_order"]
    assert 1 <= len(nb) <= 5 and sum(n["this"] for n in nb) == 1
    assert {"file", "dur", "tag", "dropped_today", "this"} <= set(nb[0])
    text = (out / "INSTRUCTIONS.md").read_text()
    for ruling in ("stage banter", "crowd-only", "interview", "between two kept tracks", "Track 9"):
        assert ruling.lower() in text.lower()
    assert "rule_right" in text and "rule_would" in text


def test_packet_membership_comes_from_the_candidate_not_r1_dec(tmp_path):
    lib = tmp_path / "lib"
    (lib / "shows" / "s1").mkdir(parents=True)
    (lib / "cache").mkdir()
    (lib / "shows" / "s1" / "show.json").write_text(json.dumps({"identifier": "item1"}))
    (tmp_path / "config.toml").write_text(f'root = "{lib}"\n')
    rows = [_frow("s1", "A-keep-but-not-in-cand.mp3", "music", "keep"),
            _frow("s1", "B-junk-but-kept.mp3", "music", "drop-junk"),
            _frow("s1", "C-in-show-not-short-kept.mp3", "tuning/dead-air/noise", "drop-junk")]
    ref = tmp_path / "ref"
    ref.mkdir()
    (ref / "r1_files.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    write_arm(tmp_path / "cand.json", {"s1": crow(
        [("B-junk-but-kept.mp3", "T", "tags", "1", False), ("C-in-show-not-short-kept.mp3", "T", "tags", "1", False)],
        short_kept=[True, False])})
    assert _packets(tmp_path, tmp_path / "out") == 0
    got = [json.loads(l) for l in (tmp_path / "out" / "packet.jsonl").read_text().splitlines()]
    assert [(r["file"], r["stratum"], r["rule_would"]) for r in got] == [
        ("B-junk-but-kept.mp3", "music", "keep")]


def test_packets_refuse_candidate_rows_without_valid_short_kept(tmp_path):
    _packet_world(tmp_path)
    arm = json.loads((tmp_path / "cand.json").read_text())
    row = arm["shows"]["s1"]
    del row["short_kept"]
    write_arm(tmp_path / "cand.json", arm["shows"])
    assert _packets(tmp_path, tmp_path / "o1") == 2 and not (tmp_path / "o1").exists()
    row["short_kept"] = [True]                     # length mismatch
    write_arm(tmp_path / "cand.json", arm["shows"])
    assert _packets(tmp_path, tmp_path / "o2") == 2


def test_packet_is_deterministic_for_a_seed(tmp_path):
    _packet_world(tmp_path, extra=10)
    _packets(tmp_path, tmp_path / "a", seed=47)
    _packets(tmp_path, tmp_path / "b", seed=47)
    _packets(tmp_path, tmp_path / "c", seed=48)
    pa = (tmp_path / "a" / "packet.jsonl").read_text()
    assert pa == (tmp_path / "b" / "packet.jsonl").read_text()
    assert pa != (tmp_path / "c" / "packet.jsonl").read_text()


def _answer(row, decision=None, kind=None, right=None):
    decision = decision or row["rule_would"]
    kind = kind or ("song" if row["rule_would"] == "keep" else "tuning")
    return {"row": row["row"], "decision": decision,
            "rule_right": decision == row["rule_would"] if right is None else right,
            "kind": kind, "confidence": "high", "why": "w"}


def _prow(n, stratum, would):
    return {"row": n, "stratum": stratum, "rule_would": would, "slug": "s", "file": f"f{n}.mp3",
            "tag": "t", "dur_sec": 20, "url": "u", "neighbours_in_play_order": []}


def test_score_bar_and_wrong_rows(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text(f'root = "{tmp_path / "lib"}"\n')
    rows = [_prow(i, "music", "keep") for i in range(1, 11)] + [_prow(11, "drop-junk", "drop")]
    (tmp_path / "packet.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    n = [0]

    def run(answers):
        n[0] += 1
        (tmp_path / "ans.jsonl").write_text("\n".join(json.dumps(a) for a in answers) + "\n")
        out = tmp_path / f"o{n[0]}"
        rc = skp.main(["score", "--packet", str(tmp_path / "packet.jsonl"), "--answers",
                       str(tmp_path / "ans.jsonl"), "--config", str(cfg), "--out", str(out)])
        return rc, out

    ok = [_answer(r) for r in rows]
    rc, out = run(ok)
    assert rc == 0
    md = (out / "score.md").read_text()
    assert "right 11" in md and "wrong 0" in md and "PASS" in md
    first = (out / "first10.md").read_text()
    assert "f1.mp3" in first and "f10.mp3" in first and "f11.mp3" not in first
    assert "position" in first and "floor_sec" in first
    assert "grader" not in first and "rule_right" not in first     # blind: no anchoring answers
    ans = (out / "first10-answers.md").read_text()
    assert "f1.mp3" in ans and "song" in ans
    # one wrong row of 11 is 90.9% right: the 90% leg holds, and the wrong row is listed
    one = ok[:3] + [_answer(rows[3], decision="drop", kind="tuning")] + ok[4:]
    rc, out = run(one)
    assert rc == 0
    md = (out / "score.md").read_text()
    assert "wrong 1" in md and "f4.mp3" in md
    # a kept row the grader calls non-performance fails the bar whatever the percentage
    rc, out = run([_answer(rows[0], decision="drop", kind="non-performance")] + ok[1:])
    assert rc == 1 and "FAIL" in (out / "score.md").read_text()
    # a dropped row the grader calls a song fails it too
    rc, out = run(ok[:10] + [_answer(rows[10], decision="keep", kind="song")])
    assert rc == 1
    # two wrong rows of 11 is under 90% right, with no forbidden kind
    rc, out = run([_answer(rows[0], decision="drop", kind="tuning"),
                   _answer(rows[1], decision="drop", kind="crowd")] + ok[2:])
    assert rc == 1
    assert "FAIL" in (out / "score.md").read_text()
    # exactly 90% right passes (9 of 10 on the first ten rows only)
    ten = rows[:10]
    (tmp_path / "packet.jsonl").write_text("\n".join(json.dumps(r) for r in ten) + "\n")
    nine = [_answer(ten[0], decision="drop", kind="tuning")] + [_answer(r) for r in ten[1:]]
    rc, out = run(nine)
    assert rc == 0 and "PASS" in (out / "score.md").read_text()
    # a kept row the grader calls spoken-broadcast, and a dropped fragment, each fail the bar
    rc, _ = run([_answer(ten[0], decision="drop", kind="spoken-broadcast")] + [_answer(r) for r in ten[1:]])
    assert rc == 1
    (tmp_path / "packet.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    rc, _ = run(ok[:10] + [_answer(rows[10], decision="keep", kind="fragment")])
    assert rc == 1
    rc, _ = run(ok[:10] + [_answer(rows[10], decision="keep", kind="segue-or-continuation")])
    assert rc == 1
    # an unanswered row fails
    rc, out = run(ok[:-1])
    assert rc == 1


def test_sibvocab_filters_kept_tags(tmp_path):
    ref = tmp_path / "ref"
    ref.mkdir()
    sibs = [{"id": "A", "drops": [
        {"name": "a1.mp3", "tag": "Tuning", "spam": False, "tagged": True, "jc": None},
        {"name": "a2.mp3", "tag": "tuning up", "spam": False, "tagged": True, "jc": "tuning"},   # junk: not kept
        {"name": "a3.mp3", "tag": "Dark Star", "spam": False, "tagged": True, "jc": None},
        {"name": "a4.mp3", "tag": "Crowd Noise", "spam": False, "tagged": False, "jc": None}]},
        {"id": "B", "drops": [{"name": "b1.mp3", "tag": "Radio DJ intro", "spam": False,
                               "tagged": True, "jc": None},
                              {"name": "b2.mp3", "tag": "Odjinn", "spam": False, "tagged": True, "jc": None}]},
        {"id": "C", "missing": True}]
    (ref / "r1_sibs.json").write_text(json.dumps(sibs))
    (tmp_path / "c.toml").write_text(f'root = "{tmp_path / "lib"}"\n')
    out = tmp_path / "o"
    assert skp.main(["sibvocab", "--ref-dir", str(ref), "--config", str(tmp_path / "c.toml"),
                     "--out", str(out)]) == 0
    text = (out / "sibvocab.txt").read_text()
    assert "A" in text and "a1.mp3" in text and "Tuning" in text and "b1.mp3" in text
    for absent in ("a2.mp3", "a3.mp3", "a4.mp3", "b2.mp3"):
        assert absent not in text


# ---- reuse-check (spec 8 premises 6-8) ----

def _tree_hash(root):
    import hashlib
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(str(p.relative_to(root)).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def _reuse_show(tmp_path, slug, old, new, *, ident="item1", station="paired", voiced=False,
                sizes=None, lengths=None):
    """old/new: source filenames in the library show.json / the candidate row. station: 'paired'
    (manifest + audio for every old file), 'none' (no station dir) or 'foreign' (other item)."""
    from llama.models import Show, Track
    lib, st = tmp_path / "lib", tmp_path / "station"
    d = lib / "shows" / slug
    d.mkdir(parents=True, exist_ok=True)
    (lib / "cache").mkdir(exist_ok=True)
    tracks = [Track(index=i, set="1", title=f"T{f}", filename=f, title_source="tags")
              for i, f in enumerate(old, 1)]
    (d / "show.json").write_text(Show(performance_id=slug, identifier=ident, artist="A", date="2000-01-01",
                                      tracks=tracks).model_dump_json())
    sizes, lengths = sizes or {}, lengths or {}
    names = sorted(set(old) | set(new))
    (lib / "cache" / f"md_{ident}.json").write_text(json.dumps({"files": [
        {"name": n, "size": str(sizes.get(n, 1000)), "length": str(lengths.get(n, 100.0))} for n in names]}))
    if station != "none":
        s = st / slug
        (s / "audio").mkdir(parents=True, exist_ok=True)
        mt = []
        for i, f in enumerate(old, 1):
            (s / "audio" / f"{i:02d} {f}").write_bytes(b"x")
            mt.append({"title": f"T{f}", "filename": f"{i:02d} {f}"})
        (s / "manifest.json").write_text(json.dumps({
            "source": {"identifier": "other" if station == "foreign" else ident}, "tracks": mt,
            "dj_audio": {"presenter": None} if voiced else None}))
    return crow([(f, f"T{f}", "tags", "1", False) for f in new])


def _reuse_run(tmp_path, cand, out, *extra, durations=None, monkeypatch=None):
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path / "lib"}"\ndelivery_path = "{tmp_path / "station"}"\n')
    (tmp_path / "station").mkdir(exist_ok=True)
    write_arm(tmp_path / "cand.json", cand)
    if durations is not None:
        monkeypatch.setattr(skp, "read_duration", lambda p: durations.get(p.name.split(" ", 1)[-1]))
    return skp.main(["reuse-check", "--cand", str(tmp_path / "cand.json"), "--config", str(cfg),
                     "--out", str(out), *extra])


def test_reuse_check_counts_fallbacks_and_times(tmp_path, monkeypatch):
    cand = {"s1": _reuse_show(tmp_path, "s1", ["a.mp3", "b.mp3", "c.mp3"], ["a.mp3", "b.mp3", "c.mp3", "d.mp3"])}
    # a ok, b off by 30 s, c unreadable, d new
    rc = _reuse_run(tmp_path, cand, tmp_path / "out",
                    durations={"a.mp3": 100.0, "b.mp3": 130.0, "c.mp3": None}, monkeypatch=monkeypatch)
    assert rc == 0
    md = (tmp_path / "out" / "reuse_check.md").read_text()
    assert "s1" in md and "paired" in md
    assert "pass 1" in md and "fallback 3" in md
    assert "a.mp3: pass" in md
    assert "b.mp3: fallback (length 130.0s vs metadata 100.0s)" in md
    assert "c.mp3: fallback (length unreadable)" in md
    assert "d.mp3: fallback (not paired)" in md
    assert "wall" in md


def test_reuse_check_never_writes(tmp_path, monkeypatch):
    cand = {"s1": _reuse_show(tmp_path, "s1", ["a.mp3"], ["a.mp3", "b.mp3"])}
    (tmp_path / "lib" / "shows" / "s1" / "package" / "audio").mkdir(parents=True)
    (tmp_path / "lib" / "shows" / "s1" / "package" / "audio" / "x.mp3").write_bytes(b"y")
    before = (_tree_hash(tmp_path / "lib"), _tree_hash(tmp_path / "station"))
    assert _reuse_run(tmp_path, cand, tmp_path / "out", durations={"a.mp3": 100.0}, monkeypatch=monkeypatch) == 0
    assert (_tree_hash(tmp_path / "lib"), _tree_hash(tmp_path / "station")) == before
    assert not (tmp_path / "lib" / "shows" / "s1" / ".audio-aside").exists()


def test_uncovered_bytes_sum(tmp_path, monkeypatch):
    cand = {
        # paired station: only the new file b.mp3 (size 500) is uncovered
        "s1": _reuse_show(tmp_path, "s1", ["a.mp3"], ["a.mp3", "b.mp3"], sizes={"b.mp3": 500}),
        # foreign item station: nothing pairs, every file uncovered (30 + 40)
        "s2": _reuse_show(tmp_path, "s2", ["a.mp3"], ["a.mp3", "b.mp3"], ident="item2", station="foreign",
                          sizes={"a.mp3": 30, "b.mp3": 40}),
        # not delivered: excluded
        "s3": _reuse_show(tmp_path, "s3", ["a.mp3"], ["a.mp3", "b.mp3"], ident="item3", station="none"),
        # voiced: excluded
        "s4": _reuse_show(tmp_path, "s4", ["a.mp3"], ["a.mp3", "b.mp3"], ident="item4", voiced=True),
        # unchanged track list: excluded
        "s5": _reuse_show(tmp_path, "s5", ["a.mp3"], ["a.mp3"], ident="item5"),
    }
    assert _reuse_run(tmp_path, cand, tmp_path / "out", "--sample", "1", durations={"a.mp3": 100.0},
                      monkeypatch=monkeypatch) == 0
    md = (tmp_path / "out" / "reuse_check.md").read_text()
    assert "changed delivered unvoiced shows: 2" in md
    assert "uncovered bytes: 570" in md


def test_reuse_check_refuses_out_over_delivery_path(tmp_path):
    cand = {"s1": _reuse_show(tmp_path, "s1", ["a.mp3"], ["a.mp3", "b.mp3"])}
    assert _reuse_run(tmp_path, cand, tmp_path / "station" / "o") == 2
    assert not (tmp_path / "station" / "o").exists()


def test_reuse_check_refuses_a_missing_delivery_root(tmp_path):
    cand = {"s1": _reuse_show(tmp_path, "s1", ["a.mp3"], ["a.mp3", "b.mp3"])}
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path / "lib"}"\ndelivery_path = "{tmp_path / "unmounted"}"\n')
    write_arm(tmp_path / "cand.json", cand)
    assert skp.main(["reuse-check", "--cand", str(tmp_path / "cand.json"), "--config", str(cfg),
                     "--out", str(tmp_path / "out")]) == 2
    assert not (tmp_path / "out").exists()


def test_reuse_check_refuses_a_missing_config(tmp_path, capsys):
    write_arm(tmp_path / "cand.json", {})
    assert skp.main(["reuse-check", "--cand", str(tmp_path / "cand.json"),
                     "--config", str(tmp_path / "nope.toml"), "--out", str(tmp_path / "out")]) == 2
    assert "no such config" in capsys.readouterr().err


def test_reuse_check_tallies_every_exclusion_class(tmp_path):
    cand = {
        "ok": _reuse_show(tmp_path, "ok", ["a.mp3"], ["a.mp3", "b.mp3"], ident="i1"),
        "unrep": {"outcome": "unreplayable"},
        "gone": _reuse_show(tmp_path, "gone", ["a.mp3"], ["a.mp3", "b.mp3"], ident="i2", station="none"),
        "voiced": _reuse_show(tmp_path, "voiced", ["a.mp3"], ["a.mp3", "b.mp3"], ident="i3", voiced=True),
        "same": _reuse_show(tmp_path, "same", ["a.mp3"], ["a.mp3"], ident="i4"),
        "badman": _reuse_show(tmp_path, "badman", ["a.mp3"], ["a.mp3", "b.mp3"], ident="i5"),
        "nojson": _reuse_show(tmp_path, "nojson", ["a.mp3"], ["a.mp3", "b.mp3"], ident="i6"),
        "miss": _reuse_show(tmp_path, "miss", ["a.mp3"], ["a.mp3", "b.mp3"], ident="i7"),
        "nosize": _reuse_show(tmp_path, "nosize", ["a.mp3"], ["a.mp3", "b.mp3"], ident="i8"),
    }
    (tmp_path / "station" / "badman" / "manifest.json").write_text("{not json")
    (tmp_path / "lib" / "shows" / "nojson" / "show.json").write_text("{not json")
    (tmp_path / "lib" / "cache" / "md_i7.json").unlink()
    (tmp_path / "lib" / "cache" / "md_i8.json").write_text(json.dumps({"files": [{"name": "b.mp3"}]}))
    assert _reuse_run(tmp_path, cand, tmp_path / "out") == 0
    md = (tmp_path / "out" / "reuse_check.md").read_text()
    for line in ("unreplayable candidate row: 1", "no station copy (not delivered): 1",
                 "voiced station copy: 1", "track list unchanged: 1",
                 "station dir present but manifest unreadable: 1", "library show.json unreadable: 1",
                 "changed shows with a metadata cache miss (every size counted as 0): 1",
                 "uncovered files with no readable size (counted as 0): 2"):
        assert line in md, line
    assert "changed delivered unvoiced shows: 3" in md          # ok, miss, nosize


def test_reuse_check_missing_file_and_missing_length_branches(tmp_path, monkeypatch):
    cand = {"s1": _reuse_show(tmp_path, "s1", ["a.mp3", "b.mp3"], ["a.mp3", "b.mp3", "c.mp3"],
                              lengths={"b.mp3": 100.0})}
    (tmp_path / "station" / "s1" / "audio" / "01 a.mp3").unlink()
    md_path = tmp_path / "lib" / "cache" / "md_item1.json"
    md = json.loads(md_path.read_text())
    for f in md["files"]:
        if f["name"] == "b.mp3":
            del f["length"]
    md_path.write_text(json.dumps(md))
    assert _reuse_run(tmp_path, cand, tmp_path / "out", durations={}, monkeypatch=monkeypatch) == 0
    text = (tmp_path / "out" / "reuse_check.md").read_text()
    assert "a.mp3: fallback (station file missing)" in text
    assert "b.mp3: fallback (no metadata length)" in text
    assert "duration-check fallbacks among paired files: 2, metadata size 2000" in text


def test_reuse_check_sample_selection_and_wall_format(tmp_path, monkeypatch):
    import random
    import re
    cand = {}
    for i in range(6):
        cand[f"s{i}"] = _reuse_show(tmp_path, f"s{i}", ["a.mp3"], ["a.mp3", "b.mp3"], ident=f"it{i}")
    assert _reuse_run(tmp_path, cand, tmp_path / "out", "--sample", "2", "--seed", "5",
                      durations={"a.mp3": 100.0}, monkeypatch=monkeypatch) == 0
    text = (tmp_path / "out" / "reuse_check.md").read_text()
    order = sorted(cand)
    random.Random(5).shuffle(order)
    expect = sorted(order[:2])
    got = re.findall(r"^## (s\d)$", text, re.M)
    assert got == expect
    assert len(re.findall(r"; wall \d+\.\d{3}s", text)) == 2
    assert "errs high" in text


def test_reuse_check_plans_each_changed_show_exactly_once(tmp_path, monkeypatch):
    cand = {f"s{i}": _reuse_show(tmp_path, f"s{i}", ["a.mp3"], ["a.mp3", "b.mp3"], ident=f"it{i}")
            for i in range(4)}
    calls = []
    real = skp.audio_reuse.plan_reuse
    monkeypatch.setattr(skp.audio_reuse, "plan_reuse", lambda ws, st: calls.append(ws.dir.name) or real(ws, st))
    assert _reuse_run(tmp_path, cand, tmp_path / "out", "--sample", "4",
                      durations={"a.mp3": 100.0}, monkeypatch=monkeypatch) == 0
    assert sorted(calls) == ["s0", "s1", "s2", "s3"]


def test_reuse_check_refuses_when_the_share_drops_mid_scan(tmp_path, monkeypatch):
    import shutil
    cand = {f"s{i}": _reuse_show(tmp_path, f"s{i}", ["a.mp3"], ["a.mp3", "b.mp3"], ident=f"it{i}")
            for i in range(3)}
    real = skp._station_state
    seen = []

    def flaky(station):
        r = real(station)
        if not seen:
            seen.append(1)
            shutil.rmtree(tmp_path / "station")
        return r
    monkeypatch.setattr(skp, "_station_state", flaky)
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path / "lib"}"\ndelivery_path = "{tmp_path / "station"}"\n')
    write_arm(tmp_path / "cand.json", cand)
    assert skp.main(["reuse-check", "--cand", str(tmp_path / "cand.json"), "--config", str(cfg),
                     "--out", str(tmp_path / "out")]) == 2
    assert not (tmp_path / "out").exists()


# ---- voiced-precheck (spec 5.5, the 37 voiced re-deliveries) ----

PRE_SLUG = "gratefuldead-1977-05-13"


def _pre_world(tmp_path, *, voiced=True, short_kept=(True, True), manifest_tracks=3,
               station_body=None, in_list=True, delivery=True):
    from llama.models import Show, Track
    from llama.workspace import write_artifact
    lib, st = tmp_path / "lib", tmp_path / "station"
    files = ["gd1977-05-13d1t01.mp3", "gd1977-05-13d2t06.mp3", "gd1977-05-13d3t01.mp3"]
    kept = {"gd1977-05-13d2t06.mp3": short_kept[0], "gd1977-05-13d3t01.mp3": short_kept[1]}
    tracks = [Track(index=i + 1, set="1", title=f"T{i + 1}", filename=f, title_source="tags",
                    short_kept=kept.get(f, False)) for i, f in enumerate(files)]
    ws = lib / "shows" / PRE_SLUG
    write_artifact(ws / "show.json", Show(performance_id="GratefulDead/1977-05-13", identifier="gd77",
                                          artist="Grateful Dead", date="1977-05-13", tracks=tracks))
    if manifest_tracks is not None:
        write_artifact(ws / "package" / "manifest.json",
                       {"tracks": [{"index": i + 1, "filename": f"{i + 1:02d} - T.mp3"}
                                   for i in range(manifest_tracks)]})
    (st / PRE_SLUG).mkdir(parents=True)
    if station_body is None:
        station_body = json.dumps({"dj_audio": {"presenter": None} if voiced else None})
    if station_body is not False:
        (st / PRE_SLUG / "manifest.json").write_text(station_body)
    entries = [{"slug": "other-show", "files": [["x.mp3", 10.0, "X", "music"]]}]
    if in_list:
        entries.append({"slug": PRE_SLUG, "files": [["gd1977-05-13d2t06.mp3", 32.0, "Drums", "music"],
                                                    ["gd1977-05-13d3t01.mp3", 60.0, "Drums", "music"]]})
    lst = tmp_path / "voiced-severe-final.json"
    lst.write_text(json.dumps(entries))
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{lib}"\n' + (f'delivery_path = "{st}"\n' if delivery else ""))
    return cfg, lst, lib, st


def _pre(cfg, lst, capsys, slug=PRE_SLUG):
    rc = skp.main(["voiced-precheck", "--list", str(lst), "--config", str(cfg), slug])
    return rc, capsys.readouterr().out


def test_voiced_precheck_passes_and_names_each_failure(tmp_path, capsys):
    cfg, lst, lib, st = _pre_world(tmp_path / "ok")
    before = (_tree_hash(lib), _tree_hash(st), lst.read_bytes())
    rc, out = _pre(cfg, lst, capsys)
    assert rc == 0, out
    assert "FAIL" not in out and f"voiced-precheck {PRE_SLUG}: pass" in out
    assert (_tree_hash(lib), _tree_hash(st), lst.read_bytes()) == before   # read-only

    cases = [
        (dict(in_list=False), [f"{PRE_SLUG} is not in"]),
        (dict(voiced=False), ["destination is not voiced"]),
        (dict(station_body=False), ["destination is not voiced"]),
        (dict(station_body="{not json"),
         [f"refusing to deliver {PRE_SLUG}: cannot read ", "check the station copy by hand"]),
        (dict(delivery=False), ["no delivery_path in the config"]),
        (dict(short_kept=(True, False)), ["gd1977-05-13d3t01.mp3: short_kept is not set"]),
        (dict(manifest_tracks=None), ["package/manifest.json is missing"]),
        (dict(manifest_tracks=2), ["package/manifest.json has 2 tracks, show.json has 3"]),
        (dict(voiced=False, short_kept=(False, False), manifest_tracks=4),
         ["destination is not voiced", "gd1977-05-13d2t06.mp3: short_kept is not set",
          "gd1977-05-13d3t01.mp3: short_kept is not set",
          "package/manifest.json has 4 tracks, show.json has 3"]),
    ]
    for i, (kw, expected) in enumerate(cases):
        cfg, lst, lib, st = _pre_world(tmp_path / f"c{i}", **kw)
        rc, out = _pre(cfg, lst, capsys)
        assert rc == 1, (kw, out)
        fails = [l for l in out.splitlines() if "FAIL" in l]
        for e in expected:
            assert any(e in l for l in fails), (kw, e, out)
        assert f"voiced-precheck {PRE_SLUG}: pass" not in out


def test_voiced_precheck_names_a_listed_file_missing_from_show_json(tmp_path, capsys):
    cfg, lst, lib, st = _pre_world(tmp_path)
    entries = json.loads(lst.read_text())
    entries[-1]["files"].append(["gd1977-05-13d9t09.mp3", 20.0, "Gone", "music"])
    lst.write_text(json.dumps(entries))
    rc, out = _pre(cfg, lst, capsys)
    assert rc == 1
    assert any("gd1977-05-13d9t09.mp3: not in show.json" in l for l in out.splitlines() if "FAIL" in l)


def test_voiced_precheck_unreadable_show_json_fails(tmp_path, capsys):
    cfg, lst, lib, st = _pre_world(tmp_path)
    (lib / "shows" / PRE_SLUG / "show.json").write_text("{not json")
    rc, out = _pre(cfg, lst, capsys)
    assert rc == 1
    assert any("show.json unreadable" in l for l in out.splitlines() if "FAIL" in l)
