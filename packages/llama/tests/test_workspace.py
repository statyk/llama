import json
from pathlib import Path

from llama.models import Criteria, Overrides
from llama.workspace import (
    RunWorkspace, ShowWorkspace, drop_stage_artifacts, read_json, read_model, read_model_list,
    read_overrides, should_run, write_artifact,
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
    assert sws.dir == tmp_path / "shows" / "gratefuldead-1973-06-10"
    assert sws.show.name == "show.json"
    assert sws.package_dir.name == "package"


def test_run_workspace_artists_path(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r")
    assert ws.artists == ws.dir / "artists.json"


def test_drop_stage_artifacts_can_keep_research(tmp_path):
    sws = ShowWorkspace(tmp_path / "s")
    for p in [sws.selection, sws.show, sws.research, sws.vetting]:
        write_artifact(p, "x")
    drop_stage_artifacts(sws, "gather", keep_research=True)
    assert sws.selection.exists()
    assert not sws.show.exists() and not sws.vetting.exists()
    assert sws.research.exists()          # preserved
    drop_stage_artifacts(sws, "research")
    assert not sws.research.exists()      # default still drops it


def test_read_overrides_defaults_when_absent(tmp_path):
    ws = ShowWorkspace(tmp_path / "s")
    ov = read_overrides(ws)
    assert ov.exclude == [] and ov.narration == "full"


def test_stage_order_and_artifacts_include_brief(tmp_path):
    from llama.workspace import SHOW_STAGE_ORDER, ShowWorkspace, show_stage_artifacts
    assert SHOW_STAGE_ORDER == ["select", "gather", "research", "vet",
                                "brief", "package"]
    ws = ShowWorkspace(tmp_path)
    assert show_stage_artifacts(ws, "brief") == [ws.briefing_json, ws.briefing_md]


def test_drop_from_brief_drops_downstream(tmp_path):
    from llama.workspace import ShowWorkspace, drop_stage_artifacts
    ws = ShowWorkspace(tmp_path)
    for p in [ws.vetting, ws.briefing_json, ws.briefing_md]:
        p.write_text("{}")
    (ws.package_dir).mkdir()
    (ws.package_dir / "manifest.json").write_text("{}")
    drop_stage_artifacts(ws, "brief")
    assert ws.vetting.exists()
    for p in [ws.briefing_json, ws.briefing_md, ws.package_dir / "manifest.json"]:
        assert not p.exists()


def test_read_overrides_round_trip(tmp_path):
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(exclude=["a.mp3"], narration="vague"))
    ov = read_overrides(ws)
    assert ov.exclude == ["a.mp3"] and ov.narration == "vague"


def test_overrides_metadata_fields_round_trip(tmp_path):
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(
        venue="X Hall", city="Austin, TX", date="2003-04-19",
        titles={4: "Bertha"}, set_breaks=[9, 17]))
    ov = read_overrides(ws)
    assert ov.venue == "X Hall" and ov.city == "Austin, TX" and ov.date == "2003-04-19"
    assert ov.titles == {4: "Bertha"}          # str JSON key coerced back to int
    assert ov.set_breaks == [9, 17]


def test_overrides_absent_metadata_defaults(tmp_path):
    ov = read_overrides(ShowWorkspace(tmp_path / "s"))
    assert ov.venue is None and ov.city is None and ov.date is None
    assert ov.titles == {} and ov.set_breaks is None
