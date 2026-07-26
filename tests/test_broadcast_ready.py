import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.catalog import (CatalogEntry, broadcast_readiness, iter_shows,
                           select_shows)
from llama.ledger import Ledger
from llama.models import Show, Track
from llama.workspace import ShowWorkspace, write_artifact

runner = CliRunner()


def build_ready(root: Path, slug: str = "gratefuldead-1973-06-10", *,
                needs_review: bool = False, voiced: bool = True,
                broadcast_m3u: bool = True, drop_audio: bool = False,
                script: bool = True) -> ShowWorkspace:
    """A fully broadcast-ready show, with knobs to break one condition at a time."""
    ws = ShowWorkspace(root / "shows" / slug)
    write_artifact(ws.show, Show(
        performance_id="GratefulDead/1973-06-10", identifier="gd73",
        artist="Grateful Dead", date="1973-06-10",
        tracks=[Track(index=1, set="1", title="Morning Dew", filename="a.mp3",
                      title_source="tags")],
        needs_review=needs_review,
        review_flags=["held for a reason"] if needs_review else []))
    if script:
        write_artifact(ws.dj_notes_json, {"set_intros": {"1": "a"}, "outro": "o"})
    manifest = {"schema_version": 2,
                "tracks": [{"index": 1, "set": "1", "title": "Morning Dew",
                            "filename": "01 - Morning Dew.mp3"}]}
    if voiced:
        manifest["dj_audio"] = {"set_intros": {"1": "dj-audio/set1-intro.mp3"},
                                "outro": "dj-audio/99-outro.mp3"}
    write_artifact(ws.package_dir / "manifest.json", manifest)
    if not drop_audio:
        write_artifact(ws.package_dir / "audio" / "01 - Morning Dew.mp3", "x")
    if broadcast_m3u:
        write_artifact(ws.package_dir / "broadcast.m3u", "#EXTM3U\n")
    return ws


def test_fully_ready_show(tmp_path: Path):
    ws = build_ready(tmp_path)
    assert broadcast_readiness(ws) == (True, [])


def test_not_packaged(tmp_path: Path):
    ws = ShowWorkspace(tmp_path / "shows" / "bare")
    write_artifact(ws.selection, {})            # a show dir with no manifest
    assert broadcast_readiness(ws) == (False, ["not packaged"])


def test_each_condition_breaks_readiness(tmp_path: Path):
    cases = [
        ("held", dict(needs_review=True), "held for review"),
        ("noscript", dict(script=False), "no DJ script"),
        ("unvoiced", dict(voiced=False), "no DJ audio (unvoiced)"),
        ("nom3u", dict(broadcast_m3u=False), "no broadcast.m3u"),
        ("noaudio", dict(drop_audio=True), "1 of 1 audio files missing"),
    ]
    for slug, kw, reason in cases:
        ws = build_ready(tmp_path / slug, "gratefuldead-1973-06-10", **kw)
        ready, reasons = broadcast_readiness(ws)
        assert ready is False, slug
        assert reasons == [reason], (slug, reasons)


def test_iter_shows_populates_broadcast_ready(tmp_path: Path):
    build_ready(tmp_path, "ready-show")
    build_ready(tmp_path, "silent-show", voiced=False)   # unvoiced -> not ready
    entries = {e.slug: e for e in iter_shows(tmp_path, Ledger(tmp_path / "l.jsonl"))}
    assert entries["ready-show"].broadcast_ready is True
    assert entries["silent-show"].broadcast_ready is False


def test_select_shows_broadcast_ready_filter():
    def e(slug, ready):
        return CatalogEntry(slug=slug, ws=ShowWorkspace(Path("/x")),
                            state="packaged", broadcast_ready=ready)
    es = [e("a", True), e("b", False)]
    assert {x.slug for x in select_shows(es, broadcast_ready=True)} == {"a"}
    assert {x.slug for x in select_shows(es)} == {"a", "b"}   # default: no filter
