"""moves.json: strict load, lock, write, record, clear (spec section 3;
strict surface 2: a recorded move is never silently lost)."""

import fcntl
import json
import os
from pathlib import Path

import pytest

import emcee.moves as moves_mod
from emcee.errors import EmceeError
from emcee.moves import (clear_move, load_moves, moves_path, read_moves_data, record_move,
                         write_moves)

STAMP = "2026-10-16T20:14:03Z"


def _write(root: Path, data) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "moves.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return path


def _lock_is_held(root: Path) -> bool:
    fd = os.open(root / "moves.json.lock", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


# --- loading --------------------------------------------------------------


def test_missing_file_is_no_moves(tmp_path):
    moves = load_moves(tmp_path)
    assert (moves.exists, moves.entries, moves.path) == (False, {}, tmp_path / "moves.json")
    assert moves_path(tmp_path) == tmp_path / "moves.json"


def test_loads_a_valid_file(tmp_path):
    _write(tmp_path, {"A/1": {"profile": "southern", "package": "a-1", "moved_at": STAMP},
                      "B/2": {"profile": None}})
    moves = load_moves(tmp_path)
    assert moves.exists
    assert moves.get("A/1")["profile"] == "southern"
    assert moves.get("B/2")["profile"] is None
    assert moves.get("C/3") is None and moves.get(None) is None and moves.get(42) is None


@pytest.mark.parametrize("content, why", [
    ('{"A/1": {"profile": "sou', "invalid JSON"),
    ('["A/1"]', "not a JSON object"),
    ('{"A/1": "southern"}', "is not an object"),
    ('{"A/1": {"package": "a"}}', 'has no "profile"'),
    ('{"A/1": {"profile": 7}}', "non-empty string or null"),
    ('{"A/1": {"profile": ""}}', "non-empty string or null"),   # Review Focus 2
])
def test_a_malformed_file_is_a_hard_error_naming_it(tmp_path, content, why):
    path = _write(tmp_path, content)
    with pytest.raises(EmceeError) as exc:
        load_moves(tmp_path)
    assert str(path) in str(exc.value)
    assert why in str(exc.value)


def test_an_unreadable_file_is_a_hard_error(tmp_path):
    (tmp_path / "moves.json").mkdir()
    with pytest.raises(EmceeError, match="moves.json"):
        load_moves(tmp_path)


def test_a_non_utf8_file_is_a_hard_error(tmp_path):
    (tmp_path / "moves.json").write_bytes(b"\xff\xfe{")
    with pytest.raises(EmceeError, match="moves.json"):
        load_moves(tmp_path)


def test_read_moves_data_is_empty_for_a_missing_file_and_strict_otherwise(tmp_path):
    assert read_moves_data(tmp_path) == {}
    _write(tmp_path, "{broken")
    with pytest.raises(EmceeError):
        read_moves_data(tmp_path)


# --- the missing-file guard -----------------------------------------------


def test_require_present_passes_when_the_file_exists_or_nothing_was_move_voiced(tmp_path):
    load_moves(tmp_path).require_present([])            # missing, nothing move-voiced
    _write(tmp_path, {})
    load_moves(tmp_path).require_present([("a", "A/1", "southern")])   # present


def test_require_present_fails_naming_the_path_the_count_and_both_ways_out(tmp_path):
    moves = load_moves(tmp_path)
    with pytest.raises(EmceeError) as exc:
        moves.require_present([("a", "A/1", "southern"), ("b", None, None)])
    message = str(exc.value)
    details = "\n".join(exc.value.details)
    assert str(tmp_path / "moves.json") in message
    assert "2 package(s)" in message
    assert "a: performance_id A/1, voiced as southern" in details
    assert "b: performance_id (none), voiced as (none)" in details
    assert "rebuild" in details
    assert "write {}" in details


# --- writing --------------------------------------------------------------


def test_write_moves_fsyncs_sorts_and_leaves_no_temp(tmp_path, monkeypatch):
    synced: list[int] = []
    real_fsync = os.fsync
    monkeypatch.setattr("emcee.workspace.os.fsync", lambda fd: (synced.append(fd), real_fsync(fd))[1])
    root = tmp_path / "home"

    write_moves(root, {"B/2": {"profile": None}, "A/1": {"profile": "x"}})

    path = root / "moves.json"
    assert synced
    assert json.loads(path.read_text()) == {"A/1": {"profile": "x"}, "B/2": {"profile": None}}
    assert path.read_text().index('"A/1"') < path.read_text().index('"B/2"')
    assert path.read_text().endswith("\n")
    assert sorted(p.name for p in root.iterdir()) == ["moves.json"]


# --- record ---------------------------------------------------------------


def test_record_creates_the_file_and_the_entry(tmp_path):
    assert record_move(tmp_path, "A/1", "southern", "a-1", moved_at=STAMP) is True
    assert json.loads((tmp_path / "moves.json").read_text()) == {
        "A/1": {"profile": "southern", "package": "a-1", "moved_at": STAMP}}


def test_record_of_a_null_profile(tmp_path):
    record_move(tmp_path, "A/1", None, "a-1", moved_at=STAMP)
    assert json.loads((tmp_path / "moves.json").read_text())["A/1"]["profile"] is None


def test_the_identical_move_is_unchanged_and_not_rewritten(tmp_path):
    record_move(tmp_path, "A/1", "southern", "a-1", moved_at=STAMP)
    before = (tmp_path / "moves.json").read_bytes()
    assert record_move(tmp_path, "A/1", "southern", "a-1", moved_at="2027-01-01T00:00:00Z") is False
    assert (tmp_path / "moves.json").read_bytes() == before


def test_record_keeps_unknown_keys_everywhere(tmp_path):
    _write(tmp_path, {"B/2": {"profile": "funk", "note": "keep me"},
                      "A/1": {"profile": "funk", "extra": 1}})
    record_move(tmp_path, "A/1", "southern", "a-1", moved_at=STAMP)
    data = json.loads((tmp_path / "moves.json").read_text())
    assert data["B/2"] == {"profile": "funk", "note": "keep me"}
    assert data["A/1"] == {"profile": "southern", "extra": 1, "package": "a-1", "moved_at": STAMP}


def test_record_never_overwrites_a_malformed_file(tmp_path):
    path = _write(tmp_path, "{broken")
    with pytest.raises(EmceeError):
        record_move(tmp_path, "A/1", "southern", "a-1", moved_at=STAMP)
    assert path.read_text() == "{broken"


def _spy_lock(monkeypatch) -> list[tuple[str, bool]]:
    seen: list[tuple[str, bool]] = []
    real_read, real_write = moves_mod.read_moves_data, moves_mod.write_moves

    def read(root):
        seen.append(("read", _lock_is_held(root)))
        return real_read(root)

    def write(root, data):
        seen.append(("write", _lock_is_held(root)))
        return real_write(root, data)

    monkeypatch.setattr(moves_mod, "read_moves_data", read)
    monkeypatch.setattr(moves_mod, "write_moves", write)
    return seen


def test_record_holds_the_lock_around_load_modify_write(tmp_path, monkeypatch):
    seen = _spy_lock(monkeypatch)
    record_move(tmp_path, "A/1", "southern", "a-1", moved_at=STAMP)
    assert seen == [("read", True), ("write", True)]
    assert _lock_is_held(tmp_path) is False


# --- clear ----------------------------------------------------------------


def _no_live():
    raise AssertionError("the live package must not be resolved when a recorded entry matches")


def test_clear_by_performance_id_or_recorded_package_name(tmp_path):
    _write(tmp_path, {"A/1": {"profile": "s", "package": "a-1"},
                      "B/2": {"profile": "s", "package": "b-2"}})
    assert clear_move(tmp_path, "A/1", _no_live) == "A/1"
    assert clear_move(tmp_path, "b-2", _no_live) == "B/2"
    assert (tmp_path / "moves.json").exists()
    assert json.loads((tmp_path / "moves.json").read_text()) == {}   # last clear leaves {}


def test_clear_falls_back_to_the_live_package(tmp_path):
    _write(tmp_path, {"A/1": {"profile": "s", "package": "renamed-since"}})
    assert clear_move(tmp_path, "a-1", lambda: "A/1") == "A/1"


def test_ambiguous_recorded_matches_are_refused_listing_their_ids(tmp_path):
    path = _write(tmp_path, {"Old/abc": {"profile": "s", "package": "abc"},
                             "New/abc": {"profile": "s", "package": "abc"}})
    before = path.read_bytes()
    with pytest.raises(EmceeError) as exc:
        clear_move(tmp_path, "abc", _no_live)
    assert exc.value.details == ["New/abc", "Old/abc"]
    assert path.read_bytes() == before


def test_clearing_something_never_recorded_writes_nothing(tmp_path):
    with pytest.raises(EmceeError, match="no move is recorded"):
        clear_move(tmp_path, "a-1", lambda: "A/1")
    assert not (tmp_path / "moves.json").exists()


def test_clear_holds_the_lock_around_load_modify_write(tmp_path, monkeypatch):
    _write(tmp_path, {"A/1": {"profile": "s", "package": "a-1"}})
    seen = _spy_lock(monkeypatch)
    clear_move(tmp_path, "A/1", _no_live)
    assert seen == [("read", True), ("write", True)]
