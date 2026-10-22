import pytest

import llama.show_unit as show_unit_mod
from helpers import tree_bytes
from llama.errors import LlamaError
from llama.locks import Locked, file_lock
from llama.show_unit import ShowChanged, capture_view, show_unit
from llama.workspace import ShowWorkspace, atomic_write_bytes, write_artifact


def _show(tmp_path):
    ws = ShowWorkspace(tmp_path / "shows" / "s")
    write_artifact(ws.provenance, {"performance_id": "x/1"})
    write_artifact(ws.overrides, {"venue": "V"})
    write_artifact(ws.show, {"title": "t"})
    write_artifact(ws.reviews, {"r": 1})
    write_artifact(ws.package_dir / "manifest.json", {"v": 3})
    atomic_write_bytes(ws.package_dir / "audio" / "a.mp3", b"A")
    return ws


def _fail_inside(ws, exc, body):
    view = capture_view(ws)
    with pytest.raises(type(exc)):
        with show_unit(ws, view):
            body()
            raise exc


def test_a_failed_unit_restores_every_file_byte_identical(tmp_path):
    ws = _show(tmp_path); before = tree_bytes(ws.dir)
    def body():
        write_artifact(ws.show, {"changed": True}); ws.reviews.unlink()
        write_artifact(ws.research, "new"); write_artifact(ws.package_dir / "manifest.json", {"v": 9})
        atomic_write_bytes(ws.package_dir / "audio" / "new.mp3", b"N")
    _fail_inside(ws, LlamaError("refused"), body)
    assert tree_bytes(ws.dir) == before
    assert not (ws.dir / ".txn").exists() and ws.lock.exists()


def test_keyboard_interrupt_restores_and_re_raises(tmp_path):
    ws = _show(tmp_path); before = tree_bytes(ws.dir)
    _fail_inside(ws, KeyboardInterrupt(), lambda: ws.show.unlink())
    assert tree_bytes(ws.dir) == before


def test_a_successful_unit_keeps_its_writes_and_removes_the_snapshot(tmp_path):
    ws = _show(tmp_path)
    with show_unit(ws, capture_view(ws)):
        write_artifact(ws.research, "kept")
    assert ws.research.read_text() == "kept" and not (ws.dir / ".txn").exists()


def test_a_unit_with_no_expected_view_reads_the_show_under_the_lock(tmp_path):
    ws = _show(tmp_path); write_artifact(ws.overrides, {"other": "command"})
    with show_unit(ws, None):
        write_artifact(ws.research, "kept")
    assert ws.research.read_text() == "kept"


def test_a_failed_restore_propagates_chained_and_the_next_unit_deletes_the_txn(tmp_path, monkeypatch):
    ws = _show(tmp_path)
    def broken(show_ws):
        raise OSError("disk full")
    monkeypatch.setattr(show_unit_mod, "restore_snapshot", broken)
    with pytest.raises(OSError) as info:
        with show_unit(ws, capture_view(ws)):
            write_artifact(ws.research, "half")
            raise LlamaError("boom")
    assert isinstance(info.value.__context__, LlamaError) and (ws.dir / ".txn").exists()
    monkeypatch.undo()
    with show_unit(ws, capture_view(ws)):
        pass
    assert ws.research.read_text() == "half" and not (ws.dir / ".txn").exists()


def test_files_outside_the_known_artifacts_are_restored_and_new_ones_removed(tmp_path):
    ws = _show(tmp_path); (ws.dir / "llm-failure.txt").write_text("old"); (ws.dir / "notes.json.1.tmp").write_text("t")
    before = tree_bytes(ws.dir)
    def body():
        (ws.dir / "llm-failure.txt").write_text("new"); (ws.dir / "stray.tmp").write_text("s")
    _fail_inside(ws, LlamaError("x"), body)
    assert tree_bytes(ws.dir) == before


def test_existing_audio_is_never_snapshotted_or_rewritten(tmp_path):
    ws = _show(tmp_path)
    def body():
        (ws.package_dir / "audio" / "a.mp3").write_bytes(b"RETAGGED")
        assert not (ws.dir / ".txn" / "files" / "package" / "audio").exists()
    _fail_inside(ws, LlamaError("x"), body)
    assert (ws.package_dir / "audio" / "a.mp3").read_bytes() == b"RETAGGED"


def test_a_leftover_snapshot_is_deleted_not_restored(tmp_path):
    ws = _show(tmp_path); current = ws.show.read_bytes()
    atomic_write_bytes(ws.dir / ".txn" / "files" / "show.json", b"STALE")
    with show_unit(ws, capture_view(ws)):
        pass
    assert ws.show.read_bytes() == current and not (ws.dir / ".txn").exists()


@pytest.mark.parametrize("change", ["overrides", "show"])
def test_a_changed_show_refuses_and_changes_nothing(tmp_path, change):
    ws = _show(tmp_path); view = capture_view(ws)
    write_artifact(getattr(ws, change), {"other": "command"}); before = tree_bytes(ws.dir)
    with pytest.raises(ShowChanged, match="s: changed by another command; run it again"):
        with show_unit(ws, view):
            raise AssertionError("the body must not run")
    assert tree_bytes(ws.dir) == before


def test_a_removed_show_refuses_with_the_removed_message(tmp_path):
    ws = _show(tmp_path); view = capture_view(ws); ws.provenance.unlink()
    with pytest.raises(ShowChanged, match="s: the show was removed; nothing changed"):
        with show_unit(ws, view):
            pass


def test_the_lock_is_held_inside_the_unit_and_released_after(tmp_path):
    ws = _show(tmp_path)
    with show_unit(ws, capture_view(ws)):
        with pytest.raises(Locked):
            with file_lock(ws.lock, blocking=False):
                pass
    with file_lock(ws.lock, blocking=False):
        pass


def test_the_lock_file_is_never_touched_by_a_failed_unit(tmp_path):
    ws = _show(tmp_path); ws.lock.touch(); ino = ws.lock.stat().st_ino
    _fail_inside(ws, LlamaError("x"), lambda: write_artifact(ws.research, "n"))
    assert ws.lock.stat().st_ino == ino


def test_a_leftover_snapshot_file_is_not_resurrected_by_a_failed_unit(tmp_path):
    ws = _show(tmp_path); before = tree_bytes(ws.dir)
    atomic_write_bytes(ws.dir / ".txn" / "files" / "ghost.json", b"G")
    _fail_inside(ws, LlamaError("x"), lambda: None)
    assert tree_bytes(ws.dir) == before


def test_a_leftover_that_cannot_be_removed_refuses_before_anything_is_written(tmp_path, monkeypatch):
    ws = _show(tmp_path)
    atomic_write_bytes(ws.dir / ".txn" / "files" / "ghost.json", b"G")
    monkeypatch.setattr(show_unit_mod.shutil, "rmtree", lambda *a, **k: None)
    ran = []
    with pytest.raises(LlamaError, match="leftover snapshot"):
        with show_unit(ws, capture_view(ws)):
            ran.append(1)
    assert not ran and not (ws.dir / ".txn" / "index.json").exists()


@pytest.mark.parametrize("exc", [KeyboardInterrupt, OSError])
def test_a_failing_take_snapshot_discards_and_re_raises(tmp_path, monkeypatch, exc):
    ws = _show(tmp_path); before = tree_bytes(ws.dir)
    real = show_unit_mod.atomic_write_bytes; calls = []
    def flaky(path, data):
        calls.append(path)
        if len(calls) == 2:
            raise exc("mid-snapshot")
        real(path, data)
    monkeypatch.setattr(show_unit_mod, "atomic_write_bytes", flaky)
    ran = []
    with pytest.raises(exc):
        with show_unit(ws, capture_view(ws)):
            ran.append(1)
    assert not ran and not (ws.dir / ".txn").exists()
    monkeypatch.undo()
    assert tree_bytes(ws.dir) == before
