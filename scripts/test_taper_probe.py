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
    assert tp.tier(["1"] * 5, ["1", "1", "1", "2", "2"], tr) == "sets merged or split"
    assert tp.tier(["1", "1", "1", "2", "encore"], ["1", "1", "1", "2", "2"], tr) == "encore folded"
    assert tp.tier(["1", "1", "1", "2", "2"], ["1", "1", "2", "2", "2"], tr) == "filler only"
    assert tp.tier(["1", "1", "1", "3", "3"], ["1", "1", "1", "2", "2"], tr) == "labels renamed"


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
