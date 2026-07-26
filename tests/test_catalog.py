from pathlib import Path

import pytest

from llama.catalog import (CatalogError, derive_state, derive_voiced,
                           iter_shows, resolve_run, resolve_show,
                           select_shows)
from llama.ledger import Ledger
from llama.models import Candidate, Overrides, Provenance, RecordingSummary, Show, Track
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
        write_artifact(ws.dj_notes_json, {"set_intros": {"1": "a"}, "outro": "o"})
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


def test_derive_voiced_states(tmp_path):
    pre = build(tmp_path / "a", "a", stages={"select"})
    assert derive_voiced(pre) is None
    silent = build(tmp_path / "b", "b",
                   stages={"select", "gather", "research", "vet", "synthesize", "package"})
    assert derive_voiced(silent) is False
    voiced = ShowWorkspace(tmp_path / "c" / "shows" / "c")
    write_artifact(voiced.package_dir / "manifest.json",
                   {"schema_version": 2, "dj_audio": {"set_intros": {"1": "x"}, "outro": "o"}})
    assert derive_voiced(voiced) is True


def test_iter_shows_populates_voiced_and_overrides(tmp_path):
    ws = build(tmp_path, "s", stages={"select", "gather"})
    write_artifact(ws.overrides, Overrides(exclude=["a.mp3"], narration="vague"))
    (entry,) = iter_shows(tmp_path, Ledger(tmp_path / "ledger.jsonl"))
    assert entry.voiced is None
    assert entry.overrides.exclude == ["a.mp3"] and entry.overrides.narration == "vague"


def test_select_shows_filters():
    from llama.catalog import CatalogEntry
    from llama.workspace import ShowWorkspace
    def e(slug, state, voiced=None, artist="Grateful Dead"):
        return CatalogEntry(slug=slug, ws=ShowWorkspace(Path("/x")), state=state,
                            voiced=voiced, artist=artist)
    es = [e("a", "held"), e("b", "packaged", voiced=False),
          e("c", "packaged", voiced=True), e("d", "delivered", artist="Phish")]
    assert {x.slug for x in select_shows(es, states={"held"})} == {"a"}
    assert {x.slug for x in select_shows(es, states={"held", "packaged"})} == {"a", "b", "c"}
    assert {x.slug for x in select_shows(es, voiced=False)} == {"b"}
    assert {x.slug for x in select_shows(es, artist="phish")} == {"d"}
    assert {x.slug for x in select_shows(es, states={"packaged"}, voiced=True)} == {"c"}


def test_resolve_run(tmp_path: Path):
    (tmp_path / "runs" / "2026-07-16-countryish").mkdir(parents=True)
    (tmp_path / "runs" / "2026-07-16-dead").mkdir(parents=True)
    assert resolve_run(tmp_path, "countryish") == "2026-07-16-countryish"
    assert resolve_run(tmp_path, "2026-07-16-dead") == "2026-07-16-dead"
    with pytest.raises(CatalogError):
        resolve_run(tmp_path, "2026-07-16")
    with pytest.raises(CatalogError):
        resolve_run(tmp_path, "nope")
