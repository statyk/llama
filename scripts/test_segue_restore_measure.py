"""Tests for scripts/segue_restore_measure.py: the pure parts, offline."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "llama" / "tests"))

import segue_restore_measure as m
from llama.models import Track
from llama.stages import gather


def _t(i, fn, title, set_="1", segue=False):
    return Track(index=i, set=set_, title=title, filename=fn, duration_sec=100.0,
                 segue=segue, title_source="tags")


def test_stub_answers_every_index_by_filename():
    stored = [_t(1, "a.mp3", "Alpha", "1", True), _t(2, "b.mp3", "Beta", "2", False)]
    stub = m.StubAligner(stored)
    prompt = ("Audio tracks:\n1 | a.mp3 | Alpha | 100.0\n2 | b.mp3 | Beta | 200\n"
              "3 | new.mp3 | Gamma | ?\n\nCanonical setlist:\n[set 1] Alpha >\n[set 2] Beta\n")
    out = json.loads(stub.complete(prompt))["tracks"]
    assert [r["index"] for r in out] == [1, 2, 3]
    assert out[0] == {"index": 1, "set": "1", "segue": True, "matched_title": "Alpha"}
    assert out[1]["set"] == "2" and out[1]["segue"] is False
    # a filename missing from the stored show: previous track's set, no segue
    assert out[2] == {"index": 3, "set": "2", "segue": False, "matched_title": "Gamma"}


def test_stub_missing_first_filename_defaults_set_1():
    stub = m.StubAligner([])
    out = json.loads(stub.complete("1 | x.mp3 | X | 5\n"))["tracks"]
    assert out == [{"index": 1, "set": "1", "segue": False, "matched_title": "X"}]


def test_info_form():
    assert m.info_form(">") == ">"
    assert m.info_form(" -> ") == "->"
    assert m.info_form("x) (>") == ") (>"
    assert m.info_form("> X reprise") == "other"
    assert m.info_form("with jam >") == "other"
    assert m.info_form(None) == "other"


def test_recorder_records_a_b_and_donor_said_no():
    calls = []

    def real(tracks, segues, *, donor, **kw):
        # the donor suppresses track 1; without it track 1 is also added
        adds = [(0, "setlist.fm")] + ([] if donor else [(1, "setlist.fm")])
        out = list(segues)
        for k, _ in adds:
            out[k] = True
        return out, adds

    rec = m.Recorder(real)
    tracks = [_t(1, "a", "A"), _t(2, "b", "B"), _t(3, "c", "C")]
    result = rec(tracks, [False, False, False], donor="DONOR", shipped_sets=["1"] * 3)
    assert result == ([True, False, False], [(0, "setlist.fm")])
    (row,) = rec.calls
    assert row["a"] == [False, False, False]
    assert row["b"] == [True, False, False]
    assert row["adds"] == [(0, "setlist.fm")]
    assert row["skips"] == [(1, "setlist.fm")]
    assert row["titles"] == ["A", "B", "C"]
    assert calls == []


def test_recorder_installs_over_gather(monkeypatch):
    rec = m.Recorder(gather.restore_segues)
    monkeypatch.setattr(gather, "restore_segues", rec)
    assert gather.restore_segues is rec


RAW = {"sets": {"set": [{"song": [
    {"name": "Jam", "info": ">"}, {"name": "Tape Thing", "tape": True},
    {"name": "Drums"}, {"name": "Jam", "info": "x) (>"}]}]}}


def test_infos_for_tracks_first_unused_match():
    out = m.infos_for_tracks(["Jam", "Drums", "Jam", "Nope"], RAW)
    assert out == [">", "", "x) (>", None]


def test_infos_for_tracks_no_raw():
    assert m.infos_for_tracks(["Jam"], None) == [None]


def test_stratified_sample_seeded_and_deterministic():
    rows = [{"slug": f"s{i}", "track": i, "form": "ab"[i % 2 if i < 40 else 0]}
            for i in range(60)]
    a = m.stratified_sample(rows, 10, seed=1, key=lambda r: r["form"])
    b = m.stratified_sample(list(reversed(rows)), 10, seed=1, key=lambda r: r["form"])
    c = m.stratified_sample(rows, 10, seed=2, key=lambda r: r["form"])
    assert a == b and a != c and len(a) == 10
    assert {r["form"] for r in a} == {"a", "b"}
    assert sum(r["form"] == "b" for r in a) == 5      # round-robin across strata


def test_stratified_sample_short_population():
    rows = [{"slug": "s", "track": 1, "form": ">"}]
    assert m.stratified_sample(rows, 20, seed=1, key=lambda r: r["form"]) == rows


def test_library_runs_offline_and_writes_only_under_out(tmp_path):
    from fixture_library import build_library
    root = tmp_path / "lib"
    build_library(root)
    before = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
    out = tmp_path / "out"
    real = gather.restore_segues
    rc = m.main(["--config", str(root / "config.toml"), "library", "--out", str(out)])
    assert rc == 0
    assert gather.restore_segues is real      # the recorder is uninstalled
    data = json.loads((out / "library.json").read_text())
    assert data["scanned"] + data["skipped_llm"] + len(data["errors"]) == 2
    assert sorted(str(p.relative_to(root)) for p in root.rglob("*")) == before
    assert not (out / "scratch").exists()


def test_out_overlapping_library_is_refused(tmp_path):
    from fixture_library import build_library
    root = tmp_path / "lib"
    build_library(root)
    assert m.main(["--config", str(root / "config.toml"), "library",
                   "--out", str(root / "shows" / "x")]) == 2
