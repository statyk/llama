import pytest

from transmitter import grid
from transmitter.errors import ConfigError
from transmitter.workspace import (Epoch, Workspace, atomic_write_bytes, load_epoch,
                                   load_or_create_epoch, read_json, write_json)


def test_atomic_write_leaves_no_temp(tmp_path):
    target = tmp_path / "a" / "b.bin"
    atomic_write_bytes(target, b"one")
    atomic_write_bytes(target, b"two")
    assert target.read_bytes() == b"two"
    assert [p.name for p in target.parent.iterdir()] == ["b.bin"]


def test_json_round_trip_and_default(tmp_path):
    write_json(tmp_path / "x.json", {"a": 1})
    assert read_json(tmp_path / "x.json") == {"a": 1}
    assert read_json(tmp_path / "missing.json", {"d": 0}) == {"d": 0}


def test_workspace_paths(tmp_path):
    ws = Workspace(tmp_path)
    assert ws.plan_path == tmp_path / "plan.jsonl"
    assert ws.seg_dir("e1") == tmp_path / "render" / "seg" / "e1"
    assert ws.shows_dir == tmp_path / "render" / "shows"


def test_epoch_is_created_once_on_a_whole_second(tmp_path):
    ws = Workspace(tmp_path)
    now = grid.iso_to_us("2026-10-10T12:00:00Z") + 123_456
    e = load_or_create_epoch(ws, now)
    assert e.epoch_us == now - 123_456
    assert e.epoch_id == "e20261010T120000Z"
    assert e.iso == "2026-10-10T12:00:00.000Z"
    assert load_or_create_epoch(ws, now + 10**9) == e
    assert read_json(ws.epoch_path)["d"] == 10.24


def test_epoch_index_math():
    e = Epoch("x", 1_000_000)
    assert e.start_us(2) == 1_000_000 + 2 * grid.D_US
    assert e.index_at(e.start_us(2) + 5) == 2


def test_an_edited_d_is_refused(tmp_path):
    ws = Workspace(tmp_path)
    write_json(ws.epoch_path, {"epoch_id": "x", "epoch": "2026-10-10T12:00:00.000Z", "d": 6.0})
    with pytest.raises(ConfigError, match="epoch change"):
        load_epoch(ws)
