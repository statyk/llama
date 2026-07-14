import json
from pathlib import Path

from llama.models import Criteria
from llama.workspace import (
    RunWorkspace, read_json, read_model, read_model_list, should_run, write_artifact,
)


def test_atomic_model_roundtrip(tmp_path: Path):
    p = tmp_path / "deep" / "criteria.json"
    c = Criteria(query="test")
    write_artifact(p, c)
    assert read_model(p, Criteria) == c
    assert not list(tmp_path.rglob("*.tmp"))


def test_model_list_and_plain_data(tmp_path: Path):
    p = tmp_path / "list.json"
    write_artifact(p, [Criteria(query="a"), Criteria(query="b")])
    assert [c.query for c in read_model_list(p, Criteria)] == ["a", "b"]
    write_artifact(tmp_path / "raw.json", {"k": [1, 2]})
    assert read_json(tmp_path / "raw.json") == {"k": [1, 2]}
    write_artifact(tmp_path / "notes.md", "# hello")
    assert (tmp_path / "notes.md").read_text() == "# hello"


def test_should_run(tmp_path: Path):
    p = tmp_path / "x.json"
    assert should_run(p, force=False)
    p.write_text("{}")
    assert not should_run(p, force=False)
    assert should_run(p, force=True)


def test_workspace_layout(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "2026-07-14-china-rider")
    assert ws.criteria == tmp_path / "runs" / "2026-07-14-china-rider" / "criteria.json"
    assert ws.candidates.name == "candidates.json"
    assert ws.shortlist.name == "shortlist.json"
    sws = ws.show_ws("GratefulDead/1973-06-10")
    assert sws.dir == ws.dir / "shows" / "gratefuldead-1973-06-10"
    assert sws.show.name == "show.json"
    assert sws.package_dir.name == "package"
    assert sws.dj_notes_md.name == "dj-notes.md"


def test_run_workspace_artists_path(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r")
    assert ws.artists == ws.dir / "artists.json"
