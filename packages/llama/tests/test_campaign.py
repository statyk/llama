"""The per-show campaign record (bulk-apply Task 3)."""
import hashlib
import json
from pathlib import Path

import pytest
from helpers import packaged_gd73, tree_bytes

import llama.cli as cli
import llama.pipeline as pipeline
from llama import campaign
from llama.campaign import (CampaignUnreadable, add_clear, add_mark, after_package,
                            awaiting_fix, last_mark, manifest_sha256, mark_processed,
                            read_record, remove_marks)
from llama.config import load_config
from llama.ledger import Ledger
from llama.replay import input_digests
from llama.stages.package import build_package
from llama.models import Show
from llama.workspace import ShowWorkspace, read_model, write_artifact


def _ws(tmp_path) -> ShowWorkspace:
    return ShowWorkspace(tmp_path / "shows" / "s")


def _mark(ws, at, start="gather", batch="b1"):
    add_mark(ws, reason="r", start_stage=start, batch=batch, at=at)


def test_awaiting_fix_follows_marks_and_processed(tmp_path):
    ws = _ws(tmp_path)
    assert awaiting_fix(read_record(ws)) is False
    _mark(ws, "2026-10-26T10:00:00Z")
    assert awaiting_fix(read_record(ws)) is True
    write_artifact(ws.provenance, {"performance_id": "x"})
    mark_processed(ws, held=True)
    assert awaiting_fix(read_record(ws)) is False
    _mark(ws, "2999-01-01T00:00:00Z", batch="b2")
    assert awaiting_fix(read_record(ws)) is True
    assert last_mark(read_record(ws)).batch == "b2"


def test_remove_marks_and_clear(tmp_path):
    ws = _ws(tmp_path)
    _mark(ws, "2026-10-26T10:00:00Z", batch="a")
    _mark(ws, "2026-10-26T11:00:00Z", batch="b")
    assert remove_marks(ws, "a") == 1 and remove_marks(ws, "zzz") == 0
    add_clear(ws, "equal")
    rec = read_record(ws)
    assert [m.batch for m in rec.marks] == ["b"] and rec.clears[0].outcome == "equal"


def test_mark_processed_writes_digests_and_sha(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    assert mark_processed(ws, held=False) is False and not ws.campaign.exists()
    _mark(ws, "2026-10-26T10:00:00Z")
    assert mark_processed(ws, held=False) is True
    p = read_record(ws).processed
    assert p.manifest_sha256 == hashlib.sha256(
        (ws.package_dir / "manifest.json").read_bytes()).hexdigest()
    assert p.digests == input_digests(ws)
    mark_processed(ws, held=True)
    assert read_record(ws).processed.manifest_sha256 is None


def _redo(cfg, from_stage):
    config = load_config(cfg); ledger = Ledger(config.root / "ledger.jsonl")
    entry = cli._resolve_show(config, ledger, "gratefuldead")
    return cli._redo_show(config, cli.IAClient(), ledger, entry, from_stage)


def test_redo_from_the_recorded_stage_marks_processed(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    _mark(ws, "2026-10-26T10:00:00Z", start="gather")
    _redo(cfg, "brief")
    assert awaiting_fix(read_record(ws)) is True
    _redo(cfg, "gather")
    assert awaiting_fix(read_record(ws)) is False


def test_redo_from_gather_with_a_select_mark_stays_awaiting(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    _mark(ws, "2026-10-26T10:00:00Z", start="select")
    _redo(cfg, "gather")
    assert awaiting_fix(read_record(ws)) is True
    _redo(cfg, "select")
    assert awaiting_fix(read_record(ws)) is False


def test_failing_redo_restores_the_record(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    _mark(ws, "2026-10-26T10:00:00Z")
    before = tree_bytes(ws.dir)
    real = campaign.mark_processed
    def mark_then_fail(*a, **k):
        real(*a, **k)
        raise RuntimeError("boom")
    monkeypatch.setattr(campaign, "mark_processed", mark_then_fail)
    with pytest.raises(RuntimeError):
        _redo(cfg, "gather")
    assert ws.campaign.read_bytes() == before["campaign.json"]
    assert tree_bytes(ws.dir) == before


def test_redo_refuses_an_unreadable_record_before_any_stage(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    ws.campaign.write_text("{not json")
    calls = []
    for name in ("run_select_recording", "run_gather", "run_research", "run_vet_research",
                 "run_brief", "run_package"):
        monkeypatch.setattr(pipeline, name, lambda *a, **k: calls.append(1))
    monkeypatch.setattr(cli, "process_show", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(cli, "make_providers", lambda *a, **k: calls.append(1))
    before = tree_bytes(ws.dir)
    with pytest.raises(CampaignUnreadable, match="cannot read campaign.json"):
        _redo(cfg, "gather")
    assert calls == [] and tree_bytes(ws.dir) == before


def test_package_build_on_processed_show_refreshes_manifest_sha(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    _mark(ws, "2026-10-26T10:00:00Z")
    mark_processed(ws, held=False)
    old = read_record(ws).processed.manifest_sha256
    show = read_model(ws.show, Show)
    show.venue = "Elsewhere"
    write_artifact(ws.show, show)
    from test_pipeline import FakeIA
    build_package(ws, FakeIA(), show, force=True)
    new = read_record(ws).processed.manifest_sha256
    assert new != old and new == manifest_sha256(ws)


def test_unreadable_record_raises(tmp_path):
    ws = _ws(tmp_path)
    ws.dir.mkdir(parents=True)
    for bad in ("{nope", json.dumps({"marks": [{"at": 1}]}), "[]"):
        ws.campaign.write_text(bad)
        with pytest.raises(CampaignUnreadable, match=r"s: cannot read campaign.json \(.*\); check it by hand"):
            read_record(ws)
    ws.campaign.unlink()
    assert read_record(ws) is None


def test_record_is_not_an_input_digest(tmp_path, monkeypatch):
    """Pin: the record and the anchor stay out of the replay digests and the
    stage artifacts a redo drops."""
    from llama.workspace import SHOW_STAGE_ORDER, show_stage_artifacts
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    before = input_digests(ws)
    _mark(ws, "2026-10-26T10:00:00Z")
    assert input_digests(ws) == before
    assert ws.campaign.name == "campaign.json" and ws.reuse_anchor.name == "reuse-anchor.json"
    for stage in SHOW_STAGE_ORDER:
        assert ws.campaign not in show_stage_artifacts(ws, stage)
        assert ws.reuse_anchor not in show_stage_artifacts(ws, stage)


def test_package_build_refuses_an_unreadable_record_before_any_write(tmp_path, monkeypatch):
    """Task 3 review minor: outside a show unit (`get`, `run resume`) a build
    must not write a manifest and then fail on the record."""
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    ws.campaign.write_text("{not json")
    show = read_model(ws.show, Show)
    before = tree_bytes(ws.dir)
    from test_pipeline import FakeIA
    ia = FakeIA()
    downloads = []
    monkeypatch.setattr(ia, "download_file", lambda *a, **k: downloads.append(a))
    with pytest.raises(CampaignUnreadable, match="cannot read campaign.json"):
        build_package(ws, ia, show, force=True)
    assert downloads == [] and tree_bytes(ws.dir) == before
