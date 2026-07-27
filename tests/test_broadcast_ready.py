import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.catalog import (CatalogEntry, broadcast_readiness, iter_shows,
                           select_shows)
from llama.ledger import Ledger
from llama.workspace import ShowWorkspace, write_artifact

from helpers import build_ready

runner = CliRunner()


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


def _cfg(tmp_path: Path) -> str:
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    return str(tmp_path / "config.toml")


def test_status_marks_broadcast_ready(tmp_path: Path):
    build_ready(tmp_path, "gratefuldead-1973-06-10")
    r = runner.invoke(cli.app, ["status", "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "broadcast-ready" in r.output


def test_status_broadcast_ready_filter_excludes_unready(tmp_path: Path):
    build_ready(tmp_path, "ready-1973-06-10")
    build_ready(tmp_path, "silent-1973-06-11", voiced=False)   # unvoiced -> not ready
    r = runner.invoke(cli.app, ["status", "--broadcast-ready", "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "ready-1973-06-10" in r.output
    assert "silent-1973-06-11" not in r.output


def test_status_json_includes_broadcast_ready(tmp_path: Path):
    build_ready(tmp_path, "gratefuldead-1973-06-10")
    r = runner.invoke(cli.app, ["status", "--json", "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    obj = next(o for o in json.loads(r.output) if o["slug"] == "gratefuldead-1973-06-10")
    assert obj["broadcast_ready"] is True


def test_show_detail_ready_line(tmp_path: Path):
    build_ready(tmp_path, "gratefuldead-1973-06-10")
    r = runner.invoke(cli.app, ["show", "gratefuldead", "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "broadcast-ready: yes" in r.output


def test_show_detail_not_ready_lists_reasons(tmp_path: Path):
    build_ready(tmp_path, "silent-1973-06-11", voiced=False, broadcast_m3u=False)
    r = runner.invoke(cli.app, ["show", "silent", "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "broadcast-ready: no" in r.output
    assert "no DJ audio (unvoiced)" in r.output
    assert "no broadcast.m3u" in r.output


def test_show_list_broadcast_ready_selector(tmp_path: Path):
    build_ready(tmp_path, "ready-1973-06-10")
    build_ready(tmp_path, "silent-1973-06-11", voiced=False)
    r = runner.invoke(cli.app, ["show", "--broadcast-ready", "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "ready-1973-06-10" in r.output
    assert "silent-1973-06-11" not in r.output


def test_batch_select_broadcast_ready_filters(tmp_path: Path):
    build_ready(tmp_path, "ready-1973-06-10")
    build_ready(tmp_path, "silent-1973-06-11", voiced=False)
    _cfg(tmp_path)   # writes config.toml; _setup needs a Path, not the str
    config, _, ledger = cli._setup(tmp_path / "config.toml")
    entries = cli._batch_select(config, ledger, broadcast_ready=True)
    assert {e.slug for e in entries} == {"ready-1973-06-10"}


def test_deliver_broadcast_ready_selector(tmp_path: Path, monkeypatch):
    build_ready(tmp_path, "ready-1973-06-10")
    build_ready(tmp_path, "silent-1973-06-11", voiced=False)
    picked = []
    monkeypatch.setattr(cli, "_deliver_one",
                        lambda config, ledger, e, dest, force: picked.append(e.slug))
    r = runner.invoke(cli.app, ["deliver", "--broadcast-ready", "--yes",
                                "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    assert picked == ["ready-1973-06-10"]


def test_redo_broadcast_ready_selector(tmp_path: Path, monkeypatch):
    build_ready(tmp_path, "ready-1973-06-10")
    build_ready(tmp_path, "silent-1973-06-11", voiced=False)
    picked = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda config, ia, ledger, e, stage, **kw: picked.append(e.slug))
    r = runner.invoke(cli.app, ["redo", "--from", "package", "--broadcast-ready",
                                "--yes", "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    assert picked == ["ready-1973-06-10"]
