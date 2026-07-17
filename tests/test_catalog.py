import json
from pathlib import Path

import pytest

from llama.catalog import (CatalogError, derive_state, iter_shows, legacy_show_dirs,
                           resolve_run, resolve_show, stage_depth)
from llama.ledger import Ledger
from llama.models import Candidate, LedgerEntry, Provenance, RecordingSummary, Show, Track
from llama.workspace import ShowWorkspace, write_artifact


def make_show(needs_review=False):
    return Show(
        performance_id="GratefulDead/1973-06-10", identifier="gd73",
        artist="Grateful Dead", date="1973-06-10",
        tracks=[Track(index=1, set="1", title="Morning Dew", filename="a.mp3",
                      title_source="tags")],
        needs_review=needs_review,
        review_flags=["research asserts wrong date: x"] if needs_review else [],
    )


def build(root: Path, slug: str, *, stages: set[str], needs_review=False,
          pid="GratefulDead/1973-06-10", run="r1"):
    ws = ShowWorkspace(root / "shows" / slug)
    write_artifact(ws.provenance, Provenance(
        performance_id=pid, run=run, dossier="great",
        candidate=Candidate(performance_id=pid, collection="GratefulDead",
                            date="1973-06-10",
                            recordings=[RecordingSummary(identifier="gd73")]),
        processed_at="2026-07-17T00:00:00+00:00"))
    if "select" in stages:
        write_artifact(ws.selection, {"identifier": "gd73"})
    if "gather" in stages:
        write_artifact(ws.show, make_show(needs_review))
    if "research" in stages:
        write_artifact(ws.research, "## Reputation\nfine")
    if "vet" in stages:
        write_artifact(ws.vetting, {"vetting": {"asserted_songs": [],
                                                "asserted_dates": [],
                                                "context": ""}, "flags": []})
    if "synthesize" in stages:
        write_artifact(ws.dj_notes_json, {"intro": "i", "set_intros": {},
                                          "outro": "o"})
    if "package" in stages:
        write_artifact(ws.package_dir / "manifest.json", {"schema_version": 2})
    return ws


def test_derive_state_matrix(tmp_path: Path):
    cases = [
        ({"select"}, "selected"),
        ({"select", "gather"}, "gathered"),
        ({"select", "gather", "research"}, "researched"),
        ({"select", "gather", "research", "vet"}, "vetted"),
        ({"select", "gather", "research", "vet", "synthesize"}, "scripted"),
        ({"select", "gather", "research", "vet", "synthesize", "package"}, "packaged"),
    ]
    for i, (stages, expected) in enumerate(cases):
        ws = build(tmp_path / str(i), f"s{i}", stages=stages)
        state, flags = derive_state(ws, delivered=set())
        assert state == expected and flags == []


def test_held_beats_everything(tmp_path: Path):
    ws = build(tmp_path, "s", stages={"select", "gather", "research", "vet",
                                      "synthesize", "package"}, needs_review=True)
    state, flags = derive_state(ws, delivered={"GratefulDead/1973-06-10"})
    assert state == "held"
    assert flags == ["research asserts wrong date: x"]


def test_delivered_beats_packaged(tmp_path: Path):
    ws = build(tmp_path, "s", stages={"select", "gather", "research", "vet",
                                      "synthesize", "package"})
    state, _ = derive_state(ws, delivered={"GratefulDead/1973-06-10"})
    assert state == "delivered"


def test_stage_depth(tmp_path: Path):
    ws = build(tmp_path, "s", stages={"select", "gather"})
    assert stage_depth(ws) == 2
    assert stage_depth(ShowWorkspace(tmp_path / "shows" / "empty")) == 0


def test_iter_shows_and_resolve(tmp_path: Path):
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    build(tmp_path, "mekons-1989-12-02", stages={"select", "gather"},
          pid="mekons/1989-12-02")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    entries = iter_shows(tmp_path, ledger)
    assert [e.slug for e in entries] == ["gratefuldead-1973-06-10", "mekons-1989-12-02"]
    assert entries[0].artist == "Grateful Dead"
    assert entries[0].provenance.run == "r1"

    assert resolve_show(tmp_path, ledger, "mekons-1989-12-02").slug == "mekons-1989-12-02"
    assert resolve_show(tmp_path, ledger, "mek").slug == "mekons-1989-12-02"
    with pytest.raises(CatalogError) as exc:
        resolve_show(tmp_path, ledger, "19")   # substring of both
    assert set(exc.value.matches) == {"gratefuldead-1973-06-10", "mekons-1989-12-02"}
    with pytest.raises(CatalogError) as exc:
        resolve_show(tmp_path, ledger, "nomatch")
    assert exc.value.matches == []


def test_resolve_show_accepts_existing_path(tmp_path: Path):
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    ledger = Ledger(tmp_path / "ledger.jsonl")
    assert resolve_show(tmp_path, ledger, str(ws.dir)).slug == "gratefuldead-1973-06-10"


def test_resolve_run(tmp_path: Path):
    (tmp_path / "runs" / "2026-07-16-countryish").mkdir(parents=True)
    (tmp_path / "runs" / "2026-07-16-dead").mkdir(parents=True)
    assert resolve_run(tmp_path, "countryish") == "2026-07-16-countryish"
    assert resolve_run(tmp_path, "2026-07-16-dead") == "2026-07-16-dead"
    with pytest.raises(CatalogError):
        resolve_run(tmp_path, "2026-07-16")
    with pytest.raises(CatalogError):
        resolve_run(tmp_path, "nope")


def test_legacy_show_dirs(tmp_path: Path):
    legacy = tmp_path / "runs" / "r1" / "shows" / "old-show"
    legacy.mkdir(parents=True)
    assert legacy_show_dirs(tmp_path) == [legacy]
    assert legacy_show_dirs(tmp_path / "elsewhere") == []
