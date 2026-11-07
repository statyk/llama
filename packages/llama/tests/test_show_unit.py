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


# --- audio set aside by a re-packaging unit (spec 5.4) ------------------------

from pathlib import Path  # noqa: E402

from helpers import (  # noqa: E402
    ReuseIA,
    audio_files,
    packaged_reuse_show,
    patch_fake_durations,
    reuse_show,
)
from llama.audio_reuse import ASIDE_DIR, plan_reuse  # noqa: E402
from llama.stages.package import build_package  # noqa: E402
from llama.workspace import drop_stage_artifacts  # noqa: E402

_OLD = (("A", "a.mp3", 300.0), ("Jam", "j1.mp3", 600.0), ("Jam", "j2.mp3", 602.0))


def _repackaging_body(ws):
    """A re-gather inserting a short file before track 2, then packaging."""
    plan = plan_reuse(ws, None)
    new = reuse_show(_OLD[0], ("Crowd", "s.mp3", 20.0, True), _OLD[1], _OLD[2])
    drop_stage_artifacts(ws, "package")
    write_artifact(ws.show, new)
    build_package(ws, ReuseIA({t.filename: t.duration_sec for t in new.tracks}), new, reuse=plan)
    assert (ws.dir / ASIDE_DIR).is_dir()


def test_failed_unit_puts_aside_audio_back_under_old_names(tmp_path, monkeypatch):
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*_OLD))
    before = tree_bytes(ws.dir)
    assert sorted(audio_files(ws)) == ["01 - A.mp3", "02 - Jam.mp3", "03 - Jam.mp3"]
    _fail_inside(ws, LlamaError("after package"), lambda: _repackaging_body(ws))
    assert tree_bytes(ws.dir) == before               # old names, old bytes, old manifest
    assert not (ws.dir / ASIDE_DIR).exists()


def test_failed_unit_mid_set_aside_puts_back_what_was_moved(tmp_path, monkeypatch):
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*_OLD))
    before = tree_bytes(ws.dir)
    import llama.audio_reuse as audio_reuse
    real, moved = audio_reuse.os.replace, []
    def flaky(src, dst, *a, **k):
        if Path(dst).parent.name == ASIDE_DIR:      # only set_aside's moves
            if len(moved) == 2:
                raise KeyboardInterrupt
            moved.append(src)
        return real(src, dst, *a, **k)
    monkeypatch.setattr(audio_reuse.os, "replace", flaky)
    _fail_inside(ws, KeyboardInterrupt(), lambda: _repackaging_body(ws))
    assert len(moved) == 2
    monkeypatch.undo()
    assert tree_bytes(ws.dir) == before and not (ws.dir / ASIDE_DIR).exists()


def test_successful_unit_deletes_the_aside(tmp_path, monkeypatch):
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*_OLD))
    with show_unit(ws, capture_view(ws)):
        _repackaging_body(ws)
    assert not (ws.dir / ASIDE_DIR).exists() and not (ws.dir / ".txn").exists()
    assert sorted(audio_files(ws)) == ["01 - A.mp3", "02 - Crowd.mp3", "03 - Jam.mp3",
                                       "04 - Jam.mp3"]


@pytest.mark.parametrize("fails", [False, True])
def test_leftover_aside_is_deleted_at_unit_entry(tmp_path, fails):
    ws = _show(tmp_path)
    atomic_write_bytes(ws.dir / ASIDE_DIR / "stale.mp3", b"STALE")
    before = tree_bytes(ws.dir)
    del before[f"{ASIDE_DIR}/stale.mp3"]
    seen = []
    def body():
        seen.append((ws.dir / ASIDE_DIR).exists())
    if fails:
        _fail_inside(ws, LlamaError("x"), body)        # a stale aside is never put back
    else:
        with show_unit(ws, capture_view(ws)):
            body()
    assert seen == [False]
    assert tree_bytes(ws.dir) == before and not (ws.dir / ASIDE_DIR).exists()


def test_a_leftover_aside_that_cannot_be_removed_refuses_before_anything_is_written(tmp_path, monkeypatch):
    ws = _show(tmp_path)
    atomic_write_bytes(ws.dir / ASIDE_DIR / "stale.mp3", b"STALE")
    monkeypatch.setattr(show_unit_mod.shutil, "rmtree", lambda *a, **k: None)
    ran = []
    with pytest.raises(LlamaError, match="leftover audio aside"):
        with show_unit(ws, capture_view(ws)):
            ran.append(1)
    assert not ran and not (ws.dir / ".txn" / "index.json").exists()


def test_two_repackagings_in_one_unit_restore_the_original_audio(tmp_path, monkeypatch):
    # Review (Important 1): a second set_aside in one unit must never move the
    # first pass's files over the pre-unit originals in the aside.
    patch_fake_durations(monkeypatch)
    ws = packaged_reuse_show(tmp_path, reuse_show(*_OLD))
    before = tree_bytes(ws.dir)
    def two_passes():
        _repackaging_body(ws)                              # inserts Crowd before track 2
        plan = plan_reuse(ws, None)
        back = reuse_show(*_OLD)                           # and a second pass drops it again
        drop_stage_artifacts(ws, "package")
        write_artifact(ws.show, back)
        build_package(ws, ReuseIA({t.filename: t.duration_sec for t in back.tracks}), back,
                      reuse=plan)
    with pytest.raises(LlamaError):
        with show_unit(ws, capture_view(ws)):
            two_passes()
            raise LlamaError("after package")
    assert tree_bytes(ws.dir) == before                    # 03 - Jam.mp3 is j2's audio again
    assert not (ws.dir / ASIDE_DIR).exists()


# --- directories a failed unit created (Task R1) ------------------------------

import json  # noqa: E402
import os  # noqa: E402


def _paths(d):
    """Every directory AND file under `d` (posix, relative), except the top-level `.lock`."""
    out = set()
    for dirpath, dirnames, filenames in os.walk(d):
        rel = Path(dirpath).relative_to(d)
        out.update((rel / n).as_posix() for n in dirnames + filenames)
    out.discard(".lock")
    return out


def _bare_show(tmp_path):
    """A show with no `package/` at all (as a held show is before packaging)."""
    ws = ShowWorkspace(tmp_path / "shows" / "s")
    write_artifact(ws.provenance, {"performance_id": "x/1"})
    write_artifact(ws.show, {"title": "t"})
    return ws


def _package_it(ws):
    write_artifact(ws.package_dir / "manifest.json", {"v": 3})
    atomic_write_bytes(ws.package_dir / "audio" / "01 - A.mp3", b"A")


def test_a_failed_unit_removes_the_directories_it_created(tmp_path):
    ws = _bare_show(tmp_path); before = _paths(ws.dir)
    assert not ws.package_dir.exists()
    _fail_inside(ws, LlamaError("after package"), lambda: _package_it(ws))
    assert _paths(ws.dir) == before
    assert not ws.package_dir.exists() and not (ws.dir / ".txn").exists()


def test_a_pre_existing_empty_package_audio_survives_a_failed_unit(tmp_path):
    ws = _bare_show(tmp_path); (ws.package_dir / "audio").mkdir(parents=True)
    before = _paths(ws.dir)
    _fail_inside(ws, LlamaError("x"), lambda: _package_it(ws))
    assert _paths(ws.dir) == before
    assert (ws.package_dir / "audio").is_dir() and not any((ws.package_dir / "audio").iterdir())


def test_a_pre_existing_empty_directory_elsewhere_survives_a_failed_unit(tmp_path):
    ws = _show(tmp_path); (ws.dir / "research").mkdir()
    before = _paths(ws.dir)
    _fail_inside(ws, LlamaError("x"), lambda: write_artifact(ws.dir / "research" / "n.json", {}))
    assert _paths(ws.dir) == before and (ws.dir / "research").is_dir()


def test_a_created_directory_left_non_empty_by_the_restore_survives(tmp_path):
    # Anything under package/audio/ that is not a direct audio file is untracked by
    # the snapshot, so the restore leaves it; its created parents are not empty and
    # must stay (rmdir only, never rmtree). A created empty sibling still goes.
    ws = _bare_show(tmp_path)
    def body():
        atomic_write_bytes(ws.package_dir / "audio" / "sub" / "x.mp3", b"X")
        (ws.dir / "extra").mkdir()
    _fail_inside(ws, LlamaError("x"), body)
    assert (ws.package_dir / "audio" / "sub" / "x.mp3").read_bytes() == b"X"
    assert not (ws.dir / "extra").exists()


def test_an_rmdir_error_neither_masks_the_original_nor_stops_the_removal(tmp_path, monkeypatch):
    ws = _bare_show(tmp_path); before = _paths(ws.dir)
    real, refused = os.rmdir, []
    def flaky(path, *a, **k):
        if Path(path).name == "extra":
            refused.append(path)
            raise PermissionError("no")
        return real(path, *a, **k)
    monkeypatch.setattr(show_unit_mod.os, "rmdir", flaky)
    def body():
        _package_it(ws); (ws.dir / "extra").mkdir()
    with pytest.raises(LlamaError, match="the original"):
        with show_unit(ws, capture_view(ws)):
            body()
            raise LlamaError("the original")
    monkeypatch.undo()
    assert refused                                           # the guarded rmdir did run
    assert _paths(ws.dir) == before | {"extra"} and not (ws.dir / ".txn").exists()


def test_a_successful_unit_keeps_the_directories_it_created(tmp_path):
    ws = _bare_show(tmp_path)
    with show_unit(ws, capture_view(ws)):
        (ws.package_dir / "audio").mkdir(parents=True); (ws.dir / "extra").mkdir()
    assert (ws.package_dir / "audio").is_dir() and (ws.dir / "extra").is_dir()


def test_keyboard_interrupt_removes_the_directories_the_unit_created(tmp_path):
    ws = _bare_show(tmp_path); before = _paths(ws.dir)
    _fail_inside(ws, KeyboardInterrupt(), lambda: _package_it(ws))
    assert _paths(ws.dir) == before


def test_a_restore_without_a_recorded_directory_set_removes_no_directory(tmp_path, monkeypatch):
    # Defensive only: a leftover .txn/ is deleted at entry, never restored, so an
    # index without "dirs" is not reachable through show_unit.
    ws = _bare_show(tmp_path)
    real = show_unit_mod.take_snapshot
    def old_index(show_ws):
        real(show_ws)
        idx = show_ws.dir / ".txn" / "index.json"
        idx.write_text(json.dumps({"audio": json.loads(idx.read_text())["audio"]}))
    monkeypatch.setattr(show_unit_mod, "take_snapshot", old_index)
    _fail_inside(ws, LlamaError("x"), lambda: (ws.dir / "extra").mkdir())
    assert (ws.dir / "extra").is_dir()


# --- the snapshot refuses on an unreadable subtree (Task R1b) ------------------

import stat  # noqa: E402

_root_only = pytest.mark.skipif(os.geteuid() == 0, reason="root reads a chmod 0o000 directory")


def _show_with_private_dir(tmp_path):
    """A show holding `private/` with a file and an empty sub-subdirectory."""
    ws = _show(tmp_path)
    write_artifact(ws.dir / "private" / "notes.json", {"n": 1})
    (ws.dir / "private" / "empty").mkdir()
    return ws, ws.dir / "private"


def _before(ws):
    return _paths(ws.dir), tree_bytes(ws.dir)


def _assert_refused_unchanged(ws, private, before, body_ran):
    private.chmod(stat.S_IRWXU)
    assert not body_ran and not (ws.dir / ".txn").exists()
    assert _before(ws) == before


@_root_only
def test_an_unreadable_subtree_refuses_the_unit_before_the_body(tmp_path):
    ws, private = _show_with_private_dir(tmp_path); before = _before(ws)
    body_ran = []
    private.chmod(0o000)
    try:
        with pytest.raises(LlamaError, match=r"^s: cannot snapshot .*private") as ei:
            with show_unit(ws, capture_view(ws)):
                body_ran.append(True)
        assert isinstance(ei.value.__cause__, OSError)
    finally:
        private.chmod(stat.S_IRWXU)
    _assert_refused_unchanged(ws, private, before, body_ran)


@_root_only
def test_the_directory_walk_alone_refuses_an_unreadable_subtree(tmp_path, monkeypatch):
    # The subtree is readable again by the time the file walk runs, so only a
    # strict directory walk can refuse.
    ws, private = _show_with_private_dir(tmp_path); before = _before(ws)
    real = show_unit_mod._tracked_files
    def readable_again(show_ws, *a, **k):
        private.chmod(stat.S_IRWXU)
        return real(show_ws, *a, **k)
    monkeypatch.setattr(show_unit_mod, "_tracked_files", readable_again)
    body_ran = []
    private.chmod(0o000)
    try:
        with pytest.raises(LlamaError, match=r"^s: cannot snapshot .*private"):
            with show_unit(ws, capture_view(ws)):
                body_ran.append(True)
    finally:
        private.chmod(stat.S_IRWXU)
    _assert_refused_unchanged(ws, private, before, body_ran)


@_root_only
def test_the_file_walk_alone_refuses_an_unreadable_subtree(tmp_path, monkeypatch):
    # The subtree turns unreadable only after the directory walk, so only a
    # strict file walk can refuse (and the files it already saved are discarded).
    ws, private = _show_with_private_dir(tmp_path); before = _before(ws)
    real = show_unit_mod._dirs
    def unreadable_after(show_ws, *a, **k):
        out = real(show_ws, *a, **k)
        private.chmod(0o000)
        return out
    monkeypatch.setattr(show_unit_mod, "_dirs", unreadable_after)
    body_ran = []
    try:
        with pytest.raises(LlamaError, match=r"^s: cannot snapshot .*private"):
            with show_unit(ws, capture_view(ws)):
                body_ran.append(True)
    finally:
        private.chmod(stat.S_IRWXU)
    _assert_refused_unchanged(ws, private, before, body_ran)


@_root_only
def test_an_unreadable_subtree_at_restore_neither_raises_nor_masks_the_original(tmp_path):
    # Write+search but no read: the restore cannot list `private/` (so it unlinks
    # and removes nothing there) but still puts its saved file back by name.
    ws, private = _show_with_private_dir(tmp_path); before = _before(ws)
    def body():
        write_artifact(private / "notes.json", {"n": 2})
        write_artifact(ws.show, {"changed": True})
        private.chmod(0o300)
    try:
        _fail_inside(ws, RuntimeError("the original"), body)
    finally:
        private.chmod(stat.S_IRWXU)
    assert not (ws.dir / ".txn").exists()
    assert _before(ws) == before


# --- an unreadable FILE refuses the same way (Task R1c) -------------------------

@_root_only
def test_an_unreadable_file_refuses_the_unit_before_the_body(tmp_path):
    # `private/` stays listable; only its file cannot be read.
    ws, private = _show_with_private_dir(tmp_path); before = _before(ws)
    secret = private / "notes.json"
    body_ran = []
    secret.chmod(0o000)
    try:
        with pytest.raises(LlamaError, match=r"^s: cannot snapshot .*private/notes\.json") as ei:
            with show_unit(ws, capture_view(ws)):
                body_ran.append(True)
        assert isinstance(ei.value.__cause__, OSError)
    finally:
        secret.chmod(stat.S_IRUSR | stat.S_IWUSR)
    _assert_refused_unchanged(ws, private, before, body_ran)


@_root_only
def test_an_unlistable_audio_dir_is_refused_by_the_directory_walk(tmp_path):
    # The strict directory walk descends into package/audio/, so it refuses first.
    ws = _show(tmp_path); before = _before(ws)
    audio = ws.package_dir / "audio"
    body_ran = []
    audio.chmod(0o300)
    try:
        with pytest.raises(LlamaError, match=r"^s: cannot snapshot .*package/audio") as ei:
            with show_unit(ws, capture_view(ws)):
                body_ran.append(True)
        assert isinstance(ei.value.__cause__, OSError)
    finally:
        audio.chmod(stat.S_IRWXU)
    _assert_refused_unchanged(ws, audio, before, body_ran)


@_root_only
def test_the_audio_listing_alone_refuses_an_unlistable_audio_dir(tmp_path, monkeypatch):
    # package/audio/ turns unlistable only after both walks (a race), so only the
    # snapshot's audio listing can refuse.
    ws = _show(tmp_path); before = _before(ws)
    audio = ws.package_dir / "audio"
    real = show_unit_mod._tracked_files
    def unlistable_after(show_ws, *a, **k):
        yield from real(show_ws, *a, **k)
        audio.chmod(0o300)
    monkeypatch.setattr(show_unit_mod, "_tracked_files", unlistable_after)
    body_ran = []
    try:
        with pytest.raises(LlamaError, match=r"^s: cannot snapshot .*package/audio") as ei:
            with show_unit(ws, capture_view(ws)):
                body_ran.append(True)
        assert isinstance(ei.value.__cause__, OSError)
    finally:
        audio.chmod(stat.S_IRWXU)
    _assert_refused_unchanged(ws, audio, before, body_ran)
