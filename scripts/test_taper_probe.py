"""scripts/taper_probe.py: in-scope set, gate counts, form counts, out/root refusal.
Tmp dirs only; nothing reads ~/.llama."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import taper_probe as tp
from llama import taper

DESC = "Set 1:\nAlpha\nBravo\nSet 2:\nCharlie\nDelta\nEncore:\nEcho"
TITLES = ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]


def _bundle(path: Path, slug: str, ident: str, titles=TITLES):
    sj = {"identifier": ident, "artist": "Test Band"}
    rows = "\n".join(f"{i} | 1 | {t} | tags | True | 300 | f{i}.mp3"
                     for i, t in enumerate(titles, 1))
    path.joinpath(f"{slug}.md").write_text(
        "# x\n\n## show.json (what llama would ship)\n"
        f"{json.dumps(sj, indent=2)}\n\ntracks (n | set | title | title_source | matched | "
        f"dur s | file):\n{rows}\n\n## vetting.json\n")


@pytest.fixture
def world(tmp_path):
    root, bundles, ev = tmp_path / "root", tmp_path / "bundles", tmp_path / "ev"
    (root / "cache").mkdir(parents=True)
    bundles.mkdir()
    ev.mkdir()
    base = {"taper_explicit": "yes", "primary": "desc-set-header", "marker_quote": "Set 2:"}
    classified = [
        dict(base, slug="a-owned-match"),
        dict(base, slug="b-unplaced"),
        dict(base, slug="c-owned-renum"),
        dict(base, slug="d-owned-notarget"),
        dict(base, slug="e-partial", taper_explicit="partial"),
        dict(base, slug="f-bare-digit", marker_quote="1: | 2:"),
        dict(base, slug="g-filename", primary="filename-set"),
    ]
    (ev / "classified.jsonl").write_text("".join(json.dumps(r) + "\n" for r in classified))
    s1 = [
        {"slug": "a-owned-match", "t_breaks": [2], "t_enc": 4, "renum": False},
        {"slug": "b-unplaced", "t_breaks": [2], "t_enc": 4, "renum": False},
        {"slug": "c-owned-renum", "t_breaks": [2], "t_enc": 4, "renum": True},
        {"slug": "d-owned-notarget", "t_breaks": None, "t_enc": None, "renum": False},
    ]
    (ev / "sort1.json").write_text(json.dumps(s1))
    for slug in ("a-owned-match", "c-owned-renum", "d-owned-notarget"):
        _bundle(bundles, slug, "id-" + slug)
        (root / "cache" / f"md_id-{slug}.json").write_text(
            json.dumps({"metadata": {"description": DESC}}))
    _bundle(bundles, "b-unplaced", "id-b", titles=["Zed", "Yak", "Xi", "Wow", "Vim"])
    (root / "cache" / "md_id-b.json").write_text(json.dumps({"metadata": {"description": DESC}}))
    return root, bundles, ev, tmp_path / "out"


def test_in_scope_set_is_fixed_before_the_reader_runs(world, monkeypatch):
    root, bundles, ev, _ = world
    rows = tp.read_jsonl(ev / "classified.jsonl")
    expect = {"a-owned-match", "b-unplaced", "c-owned-renum", "d-owned-notarget"}
    assert {r["slug"] for r in rows if tp.in_scope(r)} == expect

    def boom(*a, **k):
        raise AssertionError("reader called")
    monkeypatch.setattr(taper, "decide_taper", boom)
    assert {r["slug"] for r in rows if tp.in_scope(r)} == expect


def test_gate_counts_owned_and_target_matches(world):
    root, bundles, ev, out = world
    rows = tp.gate_rows(root, bundles, ev)
    scoped = {r["slug"]: r for r in rows if r["in_scope"]}
    assert len(scoped) == 4
    assert scoped["a-owned-match"]["status"] == "owned"
    assert scoped["a-owned-match"]["match"] == "match"
    assert scoped["b-unplaced"]["status"].startswith("unplaced")
    text = tp.gate_summary(rows)
    assert "ownership ratio (owned / in-scope): 3/4 = 0.750" in text
    assert "target match rate (exact, owned with target, not renum): 1/1 = 1.000" in text
    assert "owned renum rows (not graded): 1" in text
    assert "owned rows with no target (not graded): 1" in text
    assert "## owned renum rows (1)\n  c-owned-renum" in text
    assert "## owned rows with no target (1)\n  d-owned-notarget" in text
    assert "e-partial" not in text.split("in-scope rows (all)")[1]


def test_target_labels_and_tiers():
    assert tp.target_labels(5, [2], 4) == ["1", "1", "2", "2", "encore"]
    assert tp.breaks_of(["1", "1", "2", "encore"]) == ([2], 3)
    from llama.models import Track
    tr = [Track(index=i, set="1", title=t, filename="f", title_source="tags")
          for i, t in enumerate(["A", "B", "Tuning", "C", "D"], 1)]
    assert tp.tier(["1", "1", "1", "2", "2"], ["1", "2", "2", "2", "2"], tr) == "songs moved"
    assert tp.tier(["1"] * 5, ["1", "1", "1", "2", "2"], tr) == "sets split"
    assert tp.tier(["1", "1", "1", "2", "2"], ["1"] * 5, tr) == "sets merged"
    assert tp.tier(["1", "1", "1", "2", "encore"], ["1", "1", "1", "2", "2"], tr) == "encore folded"
    assert tp.tier(["1", "1", "1", "2", "2"], ["1", "1", "2", "2", "2"], tr) == "filler only"
    assert tp.tier(["1", "1", "1", "3", "3"], ["1", "1", "1", "2", "2"], tr) == "labels renamed"


def test_encore_changes_are_never_renames_and_merges_are_flagged():
    from llama.models import Track
    tr = [Track(index=i, set="1", title=t, filename="f", title_source="tags")
          for i, t in enumerate(["A", "B", "C", "D", "E", "F"], 1)]
    # encore folded into set 2 (same runs shape would otherwise read as a rename)
    stored = ["1", "1", "2", "2", "encore", "encore"]
    assert tp.tier(stored, ["1", "1", "2", "2", "2", "2"], tr) == "encore folded"
    # stored set 3 becomes the taper's encore
    stored = ["1", "1", "2", "2", "3", "3"]
    assert tp.tier(stored, ["1", "1", "2", "2", "encore", "encore"], tr) == "encore added"
    # a merge hiding inside an encore tier (3 sets -> 2, encore folded) is flagged
    stored = ["1", "1", "2", "2", "3", "encore"]
    new = ["1", "1", "1", "2", "2", "2"]
    assert tp.tier(stored, new, tr) == "encore folded"
    assert tp.sets_merged(stored, new, tr)
    assert not tp.sets_merged(new, stored, tr)


def test_forms_counts_matches_per_form(tmp_path):
    root = tmp_path / "root"
    (root / "cache").mkdir(parents=True)
    (root / "cache" / "md_x.json").write_text(json.dumps(
        {"metadata": {"creator": "Grateful Dead", "description": "Set 2: Alpha\nENC: Bravo"}}))
    n, lines, files, hits, _ = tp.forms_scan(root)
    assert n == 1
    assert lines["set header: Set N/one/I"] == 1
    assert lines["encore header: ENC"] == 1
    summ, samples = tp.forms_outputs(root)
    assert "Set 2:" in samples and "ENC:" in samples


def test_r4_switch_off_restores():
    before = taper._ENCORE_LIKE_END
    with tp.r4_disabled():
        assert not taper._encore_like("Traffic Jam E")
    assert taper._ENCORE_LIKE_END is before
    assert taper._encore_like("Traffic Jam E")


def test_probe_refuses_out_inside_library(world, capsys):
    root, bundles, ev, _ = world
    rc = tp.main(["gate", "--root", str(root), "--bundles", str(bundles),
                  "--evidence", str(ev), "--out", str(root / "shows" / "x")])
    assert rc == 2
    assert not (root / "shows").exists()


def test_forms_counts_the_checkpoint_a_forms_and_rules(tmp_path):
    root = tmp_path / "root"
    (root / "cache").mkdir(parents=True)
    desc = ("Set I Disc 1: 74:16\nAlpha\nDisk 2: Set 2\nBravo\nSET THREE (50:28)\nCharlie\n"
            "Set 3 & Encore: Delta\nEncore: none\n9E.Echo\n")
    (root / "cache" / "md_x.json").write_text(json.dumps({"metadata": {"description": desc}}))
    _, lines, _, _, _ = tp.forms_scan(root)
    assert lines["set header: Set M + Disc N (set first, ruling c)"] == 1
    assert lines["set header: Disc N + Set M (disc first)"] == 1
    assert lines["rule: header + (duration|time) (ruling b)"] == 1
    assert lines["rule: set-and-encore header held before the inline split"] == 1
    assert lines["void input: encore none / no encore / n/a"] == 1
    assert lines["veto Checkpoint A gap: Encor / 9E. / E Title / E~ / -e-"] == 1
    # the held set-and-encore line is no inline split: only its rest could be
    assert lines["inline-split marker (mid-line Set/E/Encore)"] == 0


def _gate_dir(path: Path, gate: list[dict], lib: list[dict]) -> Path:
    path.mkdir(parents=True)
    tp._write_jsonl(path / "gate_rows.jsonl", gate)
    tp._write_jsonl(path / "library_rows.jsonl", lib)
    return path


def test_delta_lists_newly_owned_and_newly_not_owned(tmp_path):
    old = _gate_dir(tmp_path / "old", [
        {"slug": "g1", "in_scope": True, "status": "not-asserted(one set)", "reason": "one set"},
        {"slug": "g2", "in_scope": True, "status": "owned", "reason": None},
        {"slug": "g3", "in_scope": False, "status": "owned", "reason": None},
    ], [
        {"slug": "l1", "status": "owned", "reason": None, "taper": ["1", "2"], "tier": None},
        {"slug": "l2", "status": "unplaced(x)", "reason": "unplaced: x"},
    ])
    new = _gate_dir(tmp_path / "new", [
        {"slug": "g1", "in_scope": True, "status": "owned", "reason": None, "match": "match"},
        {"slug": "g2", "in_scope": True, "status": "not-asserted(veto: today's encore)",
         "reason": "veto: today's encore"},
        {"slug": "g3", "in_scope": False, "status": "owned", "reason": None},
    ], [
        {"slug": "l1", "status": "owned", "reason": None, "taper": ["1", "1"],
         "tier": "sets merged"},
        {"slug": "l2", "status": "owned", "reason": None, "taper": ["1", "2"],
         "tier": "sets split"},
    ])
    text = tp.delta_summary(old, new)
    assert "in-scope rows: old 2, new 2, identical set: True" in text
    scope = text.split("## gate rows, in scope")[1].split("## gate rows, all")[0]
    assert "newly owned 1, newly not owned 1" in scope
    assert "  g1 match=match  (was: one set)" in scope
    assert "  g2  (veto: today's encore)" in scope
    lib = text.split("## library")[1]
    assert "newly owned 1, newly not owned 0, owned in both with different labels 1" in lib
    assert "  l2 [sets split]  (was: unplaced: x)" in lib
    assert "  l1  [None] -> [sets merged]" in lib
    out = tmp_path / "out"
    assert tp.main(["delta", "--old", str(old), "--new", str(new), "--out", str(out),
                    "--root", str(tmp_path / "root"), "--bundles", str(tmp_path / "b")]) == 0
    assert (out / "delta_summary.txt").read_text() == text


# --- score ---

def _score_world(tmp_path, rows, s1, arm_shows, stripped=True):
    ev = tmp_path / "ev"
    ev.mkdir()
    (ev / "classified.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (ev / "sort1.json").write_text(json.dumps(s1))
    arm = tmp_path / "arm.json"
    arm.write_text(json.dumps({"structure_overrides_stripped": stripped, "root": str(tmp_path / "lib"),
                               "shows": arm_shows}))
    return ev, arm


def _arm_row(sets, owned=True, filler=None, **kw):
    return dict({"taper_owned": owned, "sets": sets, "filler": filler or [False] * len(sets),
                 "taper_reason": None, "outcome": "clean", "gather_flags": [],
                 "unreplayable": None}, **kw)


def test_score_counts_matches_against_adjudicator_targets(tmp_path, capsys):
    base = {"taper_explicit": "yes", "primary": "desc-set-header", "marker_quote": "Set 2:"}
    rows = [dict(base, slug="hit"), dict(base, slug="miss"), dict(base, slug="fill"),
            dict(base, slug="declined"), dict(base, slug="fname", primary="filename-set")]
    s1 = [{"slug": s, "t_breaks": [2], "t_enc": 4, "renum": False}
          for s in ("hit", "miss", "fill", "declined", "fname")]
    target = ["1", "1", "2", "2", "encore"]
    ev, arm = _score_world(tmp_path, rows, s1, {
        "hit": _arm_row(target),
        "miss": _arm_row(["1", "2", "2", "2", "encore"]),
        # differs from the target only on a filler track
        "fill": _arm_row(["1", "1", "1", "2", "encore"], filler=[False, False, True, False, False]),
        "declined": _arm_row(["1"] * 5, owned=False, taper_reason="veto: encore-like text"),
        "fname": _arm_row(target)})
    out = tmp_path / "out"
    assert tp.main(["score", "--arm", str(arm), "--evidence", str(ev), "--out", str(out),
                    "--root", str(tmp_path / "lib"), "--bundles", str(tmp_path / "b")]) == 0
    text = (out / "score_summary.txt").read_text()
    assert "yes/partial excluding filename/track-tag: 4" in text
    assert "graded (owned, with a target; renumbered rows only when the adjudicator's fix is applied): 3" in text
    assert "match (exact, song level): 1" in text
    assert "filler-only differences (own class, not matches, not misses): 1" in text
    assert "IN SCOPE (yes, worded form, 3 desc primaries; the gate's definition): 4 rows: match 1, " \
           "filler-only 1, miss 1 (of 3 graded); declined 1" in text
    assert "  of which yes: 4 rows" in text and "  of which partial: 0 rows" in text
    assert "misses: 1" in text and "declined (not taper-owned, computed as today): 1" in text
    assert "## misses (1)\n  miss  [desc-set-header] owned ([1], 4) target [[2], 4]" in text
    assert "## out of scope (filename / track-tag rows) (1)\n  fname" in text
    got = {r["slug"]: r["class"] for r in tp.read_jsonl(out / "score_rows.jsonl")}
    assert got["hit"] == "match" and got["fill"] == "filler-only" and got["miss"] == "miss"
    assert got["declined"] == "declined"
    assert "match (exact" in capsys.readouterr().out


def test_score_refuses_an_unstripped_arm_and_scores_the_known_disagreements(tmp_path, capsys):
    ev, arm = _score_world(tmp_path, [], [], {}, stripped=False)
    assert tp.main(["score", "--arm", str(arm), "--evidence", str(ev), "--out", str(tmp_path / "o"),
                    "--root", str(tmp_path / "lib"), "--bundles", str(tmp_path / "b")]) == 2
    assert "--strip-structure-overrides" in capsys.readouterr().err

    base = {"taper_explicit": "partial", "primary": "desc-set-header", "marker_quote": "Set 2:"}
    slugs = list(tp.EXPECTED_DISAGREEMENTS)
    rows = [dict(base, slug=s) for s in slugs]
    s1 = [{"slug": s, "t_breaks": [2], "t_enc": 4, "renum": False} for s in slugs]
    two = ["1", "1", "2", "2", "2"]
    shows = {s: _arm_row(two) for s in slugs}
    shows["thedead-2009-04-29"] = _arm_row(["1", "1", "2", "2", "encore"])      # encore ships: wrong
    shows["darkstarorchestra-2007-05-08"] = _arm_row(two, owned=False, taper_reason="unplaced")
    shows["gratefuldead-1970-05-15-spans"] = _arm_row(
        two, outcome="still-held", gather_flags=["tape spans 2 events"])
    shows["gratefuldead-1981-12-31"] = _arm_row(["1", "1", "2", "2", "encore"])   # equals target
    shows["stevekimockband-2003-03-11"] = _arm_row(two)       # owned, no encore label: expected
    shows["ekoostikhookah-2009-12-31"] = _arm_row(two, owned=False, taper_reason="one set")
    shows["deadandcompany-2018-06-16"] = _arm_row(two, owned=False, taper_reason="one set")
    (tmp_path / "w").mkdir()
    ev, arm = _score_world(tmp_path / "w", rows, s1, shows)
    rows_out = {r["slug"]: r for r in tp.score_rows(json.loads(arm.read_text()), ev)}
    verdict = {s: r["verdict"] for s, r in rows_out.items()}
    assert verdict["thedead-2009-04-29"] == "UNEXPECTED"
    assert {s: v for s, v in verdict.items() if v != "UNEXPECTED"} == {
        s: "as expected" for s in slugs if s != "thedead-2009-04-29"}
    assert all(r["class"] == "known disagreement" for r in rows_out.values())
    assert rows_out["derektrucksband-2005-01-09"]["detail"].startswith("owned, no encore label")
    assert rows_out["gratefuldead-1981-12-31"]["detail"].startswith("owned; the shipped structure happens")
    assert rows_out["deadandcompany-2018-06-16"]["detail"].startswith("declined")
    # not-asserted: owned is a reader defect; no-encore: an encore label ships is wrong
    shows["ekoostikhookah-2009-12-31"] = _arm_row(["1", "1", "1", "1", "encore"])
    shows["deadandcompany-2018-06-16"] = _arm_row(two)
    shows["stevekimockband-2003-03-11"] = _arm_row(["1", "1", "2", "2", "encore"])
    v = {r["slug"]: r["verdict"] for r in tp.score_rows({"shows": shows}, ev)}
    assert v["ekoostikhookah-2009-12-31"] == v["deadandcompany-2018-06-16"] == "UNEXPECTED"
    assert v["stevekimockband-2003-03-11"] == "UNEXPECTED"
    # a spans row that is not held is flagged
    shows["gratefuldead-1970-05-15-spans"] = _arm_row(two)
    bad = tp.score_rows({"shows": shows}, ev)
    assert {r["slug"]: r["verdict"] for r in bad}["gratefuldead-1970-05-15-spans"] == "UNEXPECTED"
    text = tp.score_summary(bad)
    assert "thedead-2009-04-29: UNEXPECTED" in text and "expectation:" in text


def test_score_grades_a_renumbered_row_only_when_the_adjudicators_fix_was_stripped(tmp_path):
    base = {"taper_explicit": "yes", "primary": "desc-set-header", "marker_quote": "Set 2:"}
    rows = [dict(base, slug=s) for s in ("applied", "other-fix", "no-fix", "enc-differs")]
    s1 = [{"slug": s, "t_breaks": [2], "t_enc": 4, "renum": True} for s in
          ("applied", "other-fix", "no-fix", "enc-differs")]
    target = ["1", "1", "2", "2", "encore"]
    ev, arm = _score_world(tmp_path, rows, s1, {
        "applied": _arm_row(target, stripped={"set_breaks": [2], "encore_after": 4}),
        "other-fix": _arm_row(target, stripped={"set_breaks": [3], "encore_after": 4}),
        "no-fix": _arm_row(target, stripped={}),
        "enc-differs": _arm_row(target, stripped={"set_breaks": [2]})})
    got = {r["slug"]: r["class"] for r in tp.score_rows(json.loads(arm.read_text()), ev)}
    assert got["applied"] == "match"
    assert got["other-fix"] == got["no-fix"] == got["enc-differs"] == \
        "owned, renumbered target (not graded)"
