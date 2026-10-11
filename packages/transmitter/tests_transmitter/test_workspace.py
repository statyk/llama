import os

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


def test_atomic_write_fsyncs_the_temp_file_before_the_rename(tmp_path, monkeypatch):
    """A power loss after the rename must not leave a zero-length file: the
    data is on disk before the new name points at it."""
    calls = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):
        calls.append(("fsync", os.fstat(fd).st_size))
        real_fsync(fd)

    def replace(src, dst):
        calls.append(("replace", os.path.basename(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    atomic_write_bytes(tmp_path / "s.json", b"12345")
    assert calls == [("fsync", 5), ("replace", "s.json")]


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


def test_epoch_creation_is_serialised_against_a_concurrent_creator(tmp_path):
    """Two processes starting together must agree on one epoch: creation runs
    under an exclusive lock and re-reads epoch.json once it holds it."""
    import fcntl
    import threading

    ws = Workspace(tmp_path)
    now = grid.iso_to_us("2026-10-10T12:00:00Z")
    ws.root.mkdir(parents=True, exist_ok=True)
    fd = os.open(ws.epoch_lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)                          # the other process is mid-create
    result = []
    t = threading.Thread(target=lambda: result.append(load_or_create_epoch(ws, now + 5 * 10**6)),
                         daemon=True)
    try:
        t.start()
        t.join(timeout=0.5)
        assert t.is_alive()                                 # waits for the lock
        write_json(ws.epoch_path, {"epoch_id": "e20261010T120000Z", "epoch": "2026-10-10T12:00:00.000Z",
                                   "d": 10.24})
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    t.join(timeout=5)
    assert result == [Epoch("e20261010T120000Z", now)]     # theirs, not a second epoch
