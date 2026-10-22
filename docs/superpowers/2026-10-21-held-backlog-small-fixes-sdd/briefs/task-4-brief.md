### Task 4: Slice C core, `llama/show_unit.py`

**Files:**
- Create: `packages/llama/src/llama/show_unit.py`
- Modify: `packages/llama/tests/helpers.py` (add `tree_bytes`)
- Test: `packages/llama/tests/test_show_unit.py`

**Interfaces:**
- Consumes: `locks.file_lock`, `workspace.ShowWorkspace`, `workspace.atomic_write_bytes`, `errors.LlamaError`.
- Produces (Tasks 5-8 rely on these exact names):
  - `TXN_DIR = ".txn"`
  - `@dataclass(frozen=True) class ShowView: provenance: bool; overrides: bytes | None; show: bytes | None` (equality is the re-resolve check). The name avoids `cli.ShowState`, which already exists.
  - `capture_view(show_ws: ShowWorkspace) -> ShowView` (`provenance.json` exists; `overrides.json` and `show.json` bytes, or None)
  - `class ShowChanged(LlamaError)`
  - `take_snapshot(show_ws) -> None`, `restore_snapshot(show_ws) -> None`, `discard_snapshot(show_ws) -> None`
  - `@contextmanager show_unit(show_ws: ShowWorkspace, expect: ShowView | None) -> Iterator[None]` (`None`: a caller that showed no content, i.e. redo; the view is read under the lock and the check always passes)
  - tests: `helpers.tree_bytes(d: Path) -> dict[str, bytes]`, which maps each file's posix path relative to `d` to its bytes, for every file under `d` except the top-level `.lock`

Behaviour (spec C1 steps 2-5, C2):
- `show_unit`:
  1. Takes `file_lock(show_ws.lock)` (blocking) for the whole context.
  2. Computes `now = capture_view(show_ws)`; a `None` `expect` becomes `now`. If `now != expect`, it raises `ShowChanged`: when `expect.provenance and not now.provenance`, the text is `f"{slug}: the show was removed; nothing changed"`; otherwise it is `f"{slug}: changed by another command; run it again"` (`slug = show_ws.dir.name`). Nothing is written.
  3. Calls `discard_snapshot` (a leftover is deleted, never restored), then `take_snapshot`. If `take_snapshot` raises, it discards and re-raises.
  4. Yields.
  5. On any `BaseException` it calls `restore_snapshot`, then `discard_snapshot`, then re-raises. If `restore_snapshot` itself raises, that error propagates with the original exception chained (its `__context__`) and `.txn/` is left in place (spec C2's documented limitation: the next unit deletes it without restoring). On normal exit it calls `discard_snapshot`.
- `take_snapshot` copies every file under the show dir, except the top-level `.lock`, everything under `.txn/` and everything under `package/audio/`, to `.txn/files/<relpath>`. It writes `.txn/index.json` = `{"audio": sorted file names directly in package/audio/}`.
- `restore_snapshot`, in this order:
  - (a) Unlink every file outside `package/audio/`, `.lock` and `.txn/` that is not in the snapshot.
  - (b) `atomic_write_bytes` every snapshot file back to its path.
  - (c) Unlink every file in `package/audio/` not on the `audio` list.
- Directories are not restored. An empty directory a failed unit created (`package/`, `package/audio/`) stays; nothing checks for a directory's existence, and C2's guarantee covers files.
- Existing audio is never copied or rewritten. A retag that a failed package stage made in place stays, as the spec's limitation documents.

- [ ] **Step 1: Write the failing tests** (`test_show_unit.py`)

Imports: `import pytest`, `import llama.show_unit as show_unit_mod`, `from helpers import tree_bytes`, `from llama.errors import LlamaError`, `from llama.locks import Locked, file_lock`, `from llama.show_unit import ShowChanged, capture_view, show_unit`, `from llama.workspace import ShowWorkspace, atomic_write_bytes, write_artifact`.

Fixture `_show(tmp_path)`: a `ShowWorkspace(tmp_path / "shows" / "s")` with `provenance.json`, `overrides.json`, `show.json`, `reviews.json`, `package/manifest.json` and `package/audio/a.mp3` (bytes `b"A"`), written with `write_artifact`/`atomic_write_bytes`.

```python
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

def test_a_unit_with_no_expected_view_reads_the_show_under_the_lock(tmp_path):   # redo's form
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
    assert ws.research.read_text() == "half" and not (ws.dir / ".txn").exists()   # deleted, not restored

def test_files_outside_the_known_artifacts_are_restored_and_new_ones_removed(tmp_path):   # Review Focus 1
    ws = _show(tmp_path); (ws.dir / "llm-failure.txt").write_text("old"); (ws.dir / "notes.json.1.tmp").write_text("t")
    before = tree_bytes(ws.dir)
    def body():
        (ws.dir / "llm-failure.txt").write_text("new"); (ws.dir / "stray.tmp").write_text("s")
    _fail_inside(ws, LlamaError("x"), body)
    assert tree_bytes(ws.dir) == before

def test_existing_audio_is_never_snapshotted_or_rewritten(tmp_path):
    ws = _show(tmp_path)
    _fail_inside(ws, LlamaError("x"), lambda: (ws.package_dir / "audio" / "a.mp3").write_bytes(b"RETAGGED"))
    assert (ws.package_dir / "audio" / "a.mp3").read_bytes() == b"RETAGGED"   # outside the guarantee
    assert not (ws.dir / ".txn" / "files" / "package" / "audio").exists()

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
```

- [ ] **Step 2: Run them and see them fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_show_unit.py -q`
Expected: FAIL with `ModuleNotFoundError: llama.show_unit`.

- [ ] **Step 3: Implement `show_unit.py` and `helpers.tree_bytes` as specified above**

Give the module docstring the three documented limitations from spec C2: audio retagged in place, the `.lock`-only husk left by a racing `rm`, and SIGKILL (or a failed restore) leaving a stale `.txn/`, which the next unit deletes and `llama redo <show> --from gather` repairs. Add a fourth: the unit protects `entry.ws`, while `process_show` writes to `show_ws(prov.performance_id)`, so a show directory whose name is not `slugify(performance_id)` (renamed by hand) is outside the guarantee, as today.

- [ ] **Step 4: Run the file's tests, then the full suite**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_show_unit.py -q`, then `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/show_unit.py packages/llama/tests/test_show_unit.py packages/llama/tests/helpers.py
git commit -m "feat(show_unit): snapshot-and-restore unit under the show lock (slice C core)"
```

---

