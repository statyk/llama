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
        assert r["gate0"] is True, (r["slug"], r["gate0_diff"])
        assert r["gate0_as_is"] is True, (r["slug"], r["gate0_as_is_diff"])
    # Not vacuous: D fills on the numbered show, sibling-align ran on gd74, S on gd73.
    by = {r["slug"]: r for r in rows}
    assert "sibling-align" in {t["source"] for t in by[GD74]["today"]}
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
