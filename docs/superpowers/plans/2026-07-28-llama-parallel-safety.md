# llama parallel-safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `llama` safe to run as a few concurrent processes on one machine against a local `~/.llama/`, without serializing the slow (network/LLM/TTS) stages.

**Architecture:** Advisory `fcntl.flock` locks at two scopes — a short global **ledger lock** and a long **per-show lock** — plus atomic-write hygiene (unique temp names via a shared helper) and an atomic run-name claim. Same-performance collisions serialize (first builds, others wait and reuse); independent shows run fully in parallel. Design and rationale: `docs/superpowers/specs/2026-07-28-llama-parallel-safety-design.md`.

**Tech Stack:** Python 3.11+, stdlib only (`fcntl`, `tempfile`, `os`, `multiprocessing`), pytest. No new dependencies.

## Global Constraints

- **POSIX-only feature.** `fcntl` is POSIX; the concurrency target is macOS/Linux with a local FS. `locks.py` guards the `fcntl` import so a non-POSIX platform degrades to no-op locking (single-process behavior unchanged) rather than failing to import.
- **No new dependencies.** `fcntl`, `tempfile`, `os`, `multiprocessing` are stdlib.
- **Readers never lock.** Only writers/mutators take locks. Every file a reader reads is written via atomic rename, so readers see a whole old-or-new file. `show`, `status`, `pipeline`, and winnow's ledger dedup scan stay lock-free.
- **Lock ordering (deadlock-free):** show ⊃ ledger, never the reverse. A show build holds the show lock and only briefly takes the ledger lock at the end (`ledger.record`).
- **No same-process double-lock.** `flock` on two distinct fds of the same file blocks *within one process*. Therefore `process_show` itself never acquires the show lock — **its caller** does (the runner loop, `_redo_show`, `_deliver_one`, `catalog.remove_show`). Never nest two acquisitions of the same lock path in one process.
- **Tests are offline** (`fake` backend, no network) and use the `fork` multiprocessing context for real cross-process guarantees.
- Run `pytest -q` from an activated `.venv` (`source .venv/bin/activate`).

---

### Task 1: Lock primitive — `locks.py`

**Files:**
- Create: `src/llama/locks.py`
- Test: `tests/test_locks.py`

**Interfaces:**
- Produces:
  - `class Locked(Exception)` — raised by a non-blocking acquire when another process holds the lock.
  - `file_lock(path: Path, *, blocking: bool = True)` — context manager taking an advisory exclusive lock on the sidecar file `path`. Blocking by default; `blocking=False` raises `Locked(path)` if held. Auto-released on context exit and on process death.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_locks.py
import multiprocessing as mp
import os
import time
from pathlib import Path

import pytest

from llama.locks import Locked, file_lock

CTX = mp.get_context("fork")


def test_acquire_release_creates_sidecar(tmp_path: Path):
    lock = tmp_path / "x.lock"
    with file_lock(lock):
        assert lock.exists()
    # released; re-acquirable in-process
    with file_lock(lock, blocking=False):
        pass


def _hold_until(lock_path, started, release):
    with file_lock(Path(lock_path)):
        started.set()
        release.wait(5)


def test_nonblocking_raises_when_held(tmp_path: Path):
    lock = tmp_path / "x.lock"
    started, release = CTX.Event(), CTX.Event()
    p = CTX.Process(target=_hold_until, args=(str(lock), started, release))
    p.start()
    try:
        assert started.wait(5)
        with pytest.raises(Locked):
            with file_lock(lock, blocking=False):
                pass
    finally:
        release.set()
        p.join(5)


def _acquire_then_die(lock_path, started):
    fd_ctx = file_lock(Path(lock_path))
    fd_ctx.__enter__()
    started.set()
    os._exit(0)  # die without releasing


def test_lock_auto_released_on_process_death(tmp_path: Path):
    lock = tmp_path / "x.lock"
    started = CTX.Event()
    p = CTX.Process(target=_acquire_then_die, args=(str(lock), started))
    p.start()
    assert started.wait(5)
    p.join(5)
    # OS released the dead process's flock; we can take it non-blocking.
    with file_lock(lock, blocking=False):
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_locks.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llama.locks'`.

- [ ] **Step 3: Write the implementation**

```python
# src/llama/locks.py
import os
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None


class Locked(Exception):
    """A non-blocking acquire found the lock held by another process."""


@contextmanager
def file_lock(path: Path, *, blocking: bool = True):
    """Advisory exclusive lock on the sidecar file `path`.

    Auto-released when the context exits and when the process dies (flock is
    tied to the open fd). Non-blocking mode raises Locked if held elsewhere.
    On non-POSIX platforms this is a no-op (single-process behavior).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None:  # pragma: no cover - non-POSIX fallback
        yield
        return
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError as exc:
            raise Locked(path) from exc
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_locks.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/llama/locks.py tests/test_locks.py
git commit -m "feat: add fcntl file-lock primitive with auto-release"
```

---

### Task 2: Atomic-write hygiene — shared helper + all writers

**Files:**
- Modify: `src/llama/workspace.py` (add `atomic_write_text`/`atomic_write_bytes`; `write_artifact` delegates)
- Modify: `src/llama/ia_client.py:72-80` (cache write)
- Modify: `src/llama/setlistfm.py:93-95` (cache write)
- Modify: `src/llama/stages/package.py:232-234` (TTS `.part` clip)
- Modify: `src/llama/profiles.py:33` (TOML write)
- Modify: `src/llama/presenters.py` (TOML write — the `path.write_text(...)` save site)
- Test: `tests/test_atomic_write.py`

**Interfaces:**
- Produces:
  - `atomic_write_text(path: Path, text: str) -> None` — write `text` to `path` atomically via a **unique** temp file (`tempfile.mkstemp` in `path.parent`) + `os.replace`. Cleans up the temp on failure.
  - `atomic_write_bytes(path: Path, data: bytes) -> None` — same for bytes.
  - `write_artifact(path, data)` — unchanged signature; now delegates its final write to `atomic_write_text`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_atomic_write.py
import multiprocessing as mp
from pathlib import Path

from llama.workspace import atomic_write_text

CTX = mp.get_context("fork")


def _writer(path, text, start):
    start.wait(5)
    atomic_write_text(Path(path), text)


def test_concurrent_writes_never_interleave(tmp_path: Path):
    target = tmp_path / "out.json"
    a, b = "A" * 20000, "B" * 20000
    start = CTX.Event()
    procs = [CTX.Process(target=_writer, args=(str(target), t, start)) for t in (a, b)]
    for p in procs:
        p.start()
    start.set()
    for p in procs:
        p.join(5)
    # File equals exactly one writer's content — never a byte-mix.
    assert target.read_text() in (a, b)
    # No temp files left behind.
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_text_roundtrip(tmp_path: Path):
    target = tmp_path / "sub" / "x.txt"
    atomic_write_text(target, "hello")
    assert target.read_text() == "hello"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_atomic_write.py -q`
Expected: FAIL — `ImportError: cannot import name 'atomic_write_text'`.

- [ ] **Step 3: Add the helpers to `workspace.py` and delegate `write_artifact`**

Add `import os` and `import tempfile` at the top of `src/llama/workspace.py` (keep existing imports). Then add:

```python
def atomic_write_text(path: Path, text: str) -> None:
    """Atomic write via a unique temp file + rename. Concurrent writers to the
    same target never interleave (each gets its own temp); last rename wins."""
    atomic_write_bytes(path, text.encode())


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
```

Change `write_artifact` to delegate its final write:

```python
def write_artifact(path: Path, data) -> None:
    """Atomic write (unique temp + rename): a failed stage never leaves a partial artifact."""
    text = data if isinstance(data, str) else json.dumps(_to_jsonable(data), indent=2)
    atomic_write_text(path, text)
```

- [ ] **Step 4: Convert the remaining writers to the unique-temp helper**

`src/llama/ia_client.py` `_cached` (replace the fixed-temp block):

```python
    def _cached(self, key: str, fetch) -> dict | list:
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text())
        data = fetch()
        atomic_write_text(path, json.dumps(data))
        return data
```

Add `from llama.workspace import atomic_write_text` to `ia_client.py` imports.

`src/llama/setlistfm.py` (replace the `tmp = path.with_suffix(".tmp")` block at 93-95):

```python
                atomic_write_text(path, json.dumps(data))
```

Add `from llama.workspace import atomic_write_text` to `setlistfm.py` imports.

`src/llama/stages/package.py` (replace the `.part` block at 232-234):

```python
            atomic_write_bytes(dest, data)
```

Update the `package.py` import line that currently pulls from `llama.workspace` to also import `atomic_write_bytes`.

`src/llama/profiles.py` `save_profile` (line 33):

```python
    atomic_write_text(path, tomli_w.dumps(profile.model_dump(mode="json", exclude_none=True)))
```

Add `from llama.workspace import atomic_write_text` to `profiles.py` imports (and drop the now-unused `path.parent.mkdir(...)` line above it — `atomic_write_text` makes the parent).

`src/llama/presenters.py` — at the presenter-save site (the `path.write_text(tomli_w.dumps(...))` call), replace with `atomic_write_text(path, tomli_w.dumps(...))` and add the same import; drop its redundant `mkdir` if present.

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: PASS — new atomic-write tests pass and no existing test regresses (cache/profile/presenter round-trips still work; the on-disk cache format is unchanged).

- [ ] **Step 6: Commit**

```bash
git add src/llama/workspace.py src/llama/ia_client.py src/llama/setlistfm.py \
        src/llama/stages/package.py src/llama/profiles.py src/llama/presenters.py \
        tests/test_atomic_write.py
git commit -m "feat: unique temp names for all atomic writes (no cross-process interleave)"
```

---

### Task 3: Ledger locking + atomic rewrite

**Files:**
- Modify: `src/llama/ledger.py`
- Test: `tests/test_ledger_concurrency.py`

**Interfaces:**
- Consumes: `llama.locks.file_lock`, `llama.workspace.atomic_write_text`.
- Produces: `Ledger.record`/`remove`/`remove_status` unchanged signatures, now serialized by a per-ledger lock at `<ledger.jsonl>.lock` with the read re-done inside the lock.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ledger_concurrency.py
import multiprocessing as mp
from pathlib import Path

from llama.ledger import Ledger
from llama.models import LedgerEntry

CTX = mp.get_context("fork")


def _entry(pid, run):
    return LedgerEntry(performance_id=pid, artist="A", date="1973-06-10",
                       venue="V", status="selected", run=run,
                       recorded_at="2026-07-28T00:00:00Z")


def _record(path, pid, run, start):
    start.wait(5)
    Ledger(Path(path)).record(_entry(pid, run))


def test_concurrent_record_no_loss_no_dup(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    start = CTX.Event()
    # 8 distinct rows + 4 duplicate attempts of one existing row.
    specs = [(f"p{i}", "r") for i in range(8)] + [("p0", "r")] * 4
    procs = [CTX.Process(target=_record, args=(str(path), pid, run, start))
             for pid, run in specs]
    for p in procs:
        p.start()
    start.set()
    for p in procs:
        p.join(5)
    entries = Ledger(path).entries()
    keys = {(e.performance_id, e.status, e.run) for e in entries}
    assert len(keys) == 8              # no losses
    assert len(entries) == 8           # no duplicates despite the 4 dup attempts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ledger_concurrency.py -q`
Expected: FAIL — without the lock, concurrent `record` produces duplicate `p0` rows and/or fewer than 8 unique keys (flaky-toward-failure). (If it happens to pass by luck, the lock still makes it deterministic.)

- [ ] **Step 3: Add locking to `ledger.py`**

Add imports and a lock-path property, and wrap each mutator:

```python
from llama.locks import file_lock
from llama.workspace import atomic_write_text


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        self._lock = path.with_name(path.name + ".lock")

    # ... entries()/played_ids()/rejected_ids()/latest_dispositions() unchanged (lock-free reads) ...

    def record(self, entry: LedgerEntry) -> None:
        """Append-once, serialized across processes."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(self._lock):
            for e in self.entries():            # re-read under the lock
                if (e.performance_id, e.status, e.run) == (entry.performance_id, entry.status, entry.run):
                    return
            with self.path.open("a") as f:
                f.write(entry.model_dump_json() + "\n")

    def remove(self, performance_id: str) -> int:
        with file_lock(self._lock):
            before = self.entries()
            kept = [e for e in before if e.performance_id != performance_id]
            atomic_write_text(self.path, "".join(e.model_dump_json() + "\n" for e in kept))
            return len(before) - len(kept)

    def remove_status(self, performance_id: str, status: str) -> int:
        """Remove only rows matching both performance_id and status."""
        with file_lock(self._lock):
            before = self.entries()
            kept = [e for e in before if not (e.performance_id == performance_id and e.status == status)]
            atomic_write_text(self.path, "".join(e.model_dump_json() + "\n" for e in kept))
            return len(before) - len(kept)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ledger_concurrency.py tests/ -q -k "ledger"`
Expected: PASS. Then `pytest -q` — no regressions.

- [ ] **Step 5: Commit**

```bash
git add src/llama/ledger.py tests/test_ledger_concurrency.py
git commit -m "feat: serialize ledger mutations with a file lock (no lost/dup rows)"
```

---

### Task 4: Atomic run-name claim

**Files:**
- Modify: `src/llama/workspace.py` (replace `unique_run_name` with `claim_run_dir`)
- Modify: `src/llama/cli.py:46,344,375` (import + callers)
- Modify: `tests/test_sessions.py:11,18-23` (rewrite the test)
- Test: add a concurrency case to `tests/test_sessions.py`

**Interfaces:**
- Produces: `claim_run_dir(root: Path, base: str) -> str` — atomically creates `runs/<name>/` (trying `base`, `base-2`, `base-3`, …) and returns the claimed name. Two concurrent callers with the same base get distinct names.
- Removes: `unique_run_name`.

- [ ] **Step 1: Rewrite the unit test and add the race test**

```python
# tests/test_sessions.py — replace the unique_run_name import and test
import multiprocessing as mp
from llama.workspace import RunWorkspace, claim_run_dir, write_artifact

CTX = mp.get_context("fork")


def test_claim_run_dir_suffixes(tmp_path: Path):
    # Each call creates the dir itself, so successive calls auto-suffix.
    assert claim_run_dir(tmp_path, "2026-07-27-x") == "2026-07-27-x"
    assert claim_run_dir(tmp_path, "2026-07-27-x") == "2026-07-27-x-2"
    assert claim_run_dir(tmp_path, "2026-07-27-x") == "2026-07-27-x-3"


def _claim(root, base, out):
    out.put(claim_run_dir(Path(root), base))


def test_claim_run_dir_race_distinct_names(tmp_path: Path):
    out = CTX.Queue()
    procs = [CTX.Process(target=_claim, args=(str(tmp_path), "2026-07-28-q", out))
             for _ in range(6)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(5)
    names = sorted(out.get() for _ in procs)
    assert len(set(names)) == 6                                   # all distinct
    assert len(list((tmp_path / "runs").iterdir())) == 6          # 6 dirs claimed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sessions.py -q`
Expected: FAIL — `ImportError: cannot import name 'claim_run_dir'`.

- [ ] **Step 3: Replace `unique_run_name` with `claim_run_dir`**

In `src/llama/workspace.py`, add `import itertools` at the top and replace the `unique_run_name` function with:

```python
def claim_run_dir(root: Path, base: str) -> str:
    """Atomically claim a run name by creating its dir. `base`, else `base-2`,
    `base-3`, ... — two concurrent callers can never win the same name."""
    runs = root / "runs"
    for name in itertools.chain([base], (f"{base}-{n}" for n in itertools.count(2))):
        try:
            (runs / name).mkdir(parents=True, exist_ok=False)
            return name
        except FileExistsError:
            continue
```

- [ ] **Step 4: Update the callers in `cli.py`**

Line 46 import: replace `unique_run_name` with `claim_run_dir`.

Line 344 (the `run_name = name or unique_run_name(...)` site):

```python
    run_name = name or claim_run_dir(config.root,
                                     <same base expression as before>)
```

Line 375 (the `RunWorkspace(config.root, unique_run_name(...))` site):

```python
    ws = RunWorkspace(config.root, claim_run_dir(config.root,
                                                 <same base expression as before>))
```

Keep the two base expressions exactly as they are today. Note: when the caller passes an explicit `name` (line 344), the run dir is NOT pre-created by `claim_run_dir`; that path is unchanged and `RunWorkspace` creates the dir on first write as before.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sessions.py -q`
Expected: PASS. Then `pytest -q` — no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/llama/workspace.py src/llama/cli.py tests/test_sessions.py
git commit -m "feat: atomic run-name claim (no two runs collapse into one dir)"
```

---

### Task 5: Per-show lock on the single-show mutators

**Files:**
- Modify: `src/llama/workspace.py` (`ShowWorkspace.lock` attribute)
- Modify: `src/llama/cli.py` (`_redo_show` at 1239, `_deliver_one` at 1121)
- Modify: `src/llama/catalog.py` (`remove_show` at ~285)
- Test: `tests/test_show_lock.py`

**Interfaces:**
- Consumes: `llama.locks.file_lock`.
- Produces: `ShowWorkspace.lock: Path` — the per-show sidecar `<show dir>/.lock`. Every single-show mutator (`_redo_show`, `_deliver_one`, `catalog.remove_show`) acquires it (blocking) around its body. `process_show` stays lock-free (its caller holds the lock — see Global Constraints).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_show_lock.py
from pathlib import Path

from llama.workspace import ShowWorkspace, RunWorkspace


def test_show_workspace_exposes_lock_path(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "run-1")
    show = ws.show_ws("gd1973-06-10")
    assert show.lock == show.dir / ".lock"
```

(The cross-process reuse guarantee is exercised end-to-end in Task 6; this task just wires the lock path and the mutator acquisitions, which are verified by the full suite still passing.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_show_lock.py -q`
Expected: FAIL — `AttributeError: 'ShowWorkspace' object has no attribute 'lock'`.

- [ ] **Step 3: Add the lock path**

In `src/llama/workspace.py`, in `ShowWorkspace.__init__`, add:

```python
        self.lock = dir / ".lock"
```

- [ ] **Step 4: Acquire the show lock in each single-show mutator**

Add `from llama.locks import file_lock` to `cli.py` and `catalog.py` imports.

In `cli.py` `_redo_show` (1239) — wrap the `process_show(...)` call (currently returned at ~1272):

```python
    show_ws = ws.show_ws(entry.candidate.performance_id)
    with file_lock(show_ws.lock):
        return process_show(ws, ia, ledger, entry, make_providers(config), ...)  # unchanged args
```

(Use whatever `ws`/`show_ws` handle the function already has; the point is to hold `show_ws.lock` around the existing `process_show` call and its return.)

In `cli.py` `_deliver_one` (1121) — wrap the function body that writes the delivery output and records the ledger:

```python
    show_ws = <resolve ShowWorkspace for entry, as the function already does>
    with file_lock(show_ws.lock):
        ... existing body (copy/verify + ledger.record) ...
        return <existing return>
```

In `catalog.py` `remove_show` — wrap the body that deletes/moves the show dir:

```python
    show_ws = <the ShowWorkspace / show dir this function already computes>
    with file_lock(show_ws.lock):
        ... existing removal body ...
```

If `remove_show` deletes the directory, that's fine while holding the lock: the holder keeps its fd, and the sidecar's inode persists until the context exits (POSIX). Do not special-case deleting the `.lock` file.

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: PASS — no regressions (single-process behavior is unchanged; the locks are uncontended).

- [ ] **Step 6: Commit**

```bash
git add src/llama/workspace.py src/llama/cli.py src/llama/catalog.py tests/test_show_lock.py
git commit -m "feat: per-show lock on redo/deliver/remove mutators"
```

---

### Task 6: Defer-locked runner loop (the get/run path)

**Files:**
- Modify: `src/llama/cli.py:292-316` (the `for entry in chosen` loop)
- Test: `tests/test_concurrency.py`

**Interfaces:**
- Consumes: `llama.locks.file_lock`, `Locked`, `ShowWorkspace.lock`.
- Produces: the runner loop becomes two passes — first pass try-locks each show (non-blocking) and **defers** any show already locked by another run; second pass blocks on the deferred shows, then reuses-or-builds. `process_show` is called with the show lock held; it remains lock-free itself.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_concurrency.py
import multiprocessing as mp
from pathlib import Path

from llama.locks import Locked, file_lock
from llama.workspace import RunWorkspace

CTX = mp.get_context("fork")


def _build_once_marker(show_ws):
    """Simulate a show build guarded by the per-show lock: append to a shared
    counter file only if the 'show' isn't already built."""
    with file_lock(show_ws.lock):
        if not show_ws.show.exists():
            with (show_ws.dir.parent / "build_count.txt").open("a") as f:
                f.write("x")
            show_ws.show.write_text("{}")  # mark built


def _run(root, start):
    start.wait(5)
    ws = RunWorkspace(Path(root), "r")
    _build_once_marker(ws.show_ws("gd1973-06-10"))


def test_same_show_built_once_across_processes(tmp_path: Path):
    (tmp_path / "shows").mkdir(parents=True)
    start = CTX.Event()
    procs = [CTX.Process(target=_run, args=(str(tmp_path), start)) for _ in range(4)]
    for p in procs:
        p.start()
    start.set()
    for p in procs:
        p.join(5)
    # The expensive build ran exactly once despite 4 concurrent runners.
    assert (tmp_path / "shows" / "build_count.txt").read_text() == "x"


def test_defer_loop_skips_locked_then_blocks():
    """The runner-loop two-pass logic: locked shows are deferred, not failed."""
    from llama.cli import _partition_by_lock  # helper extracted in Step 3
    # a fake entry whose show lock is held returns as 'deferred', not raised.
    # (See Step 3 for the exact helper contract.)
```

> Note for the implementer: keep `test_same_show_built_once_across_processes` as the load-bearing assertion. The second test is a light unit check of the extracted helper; write it against the real `_partition_by_lock` signature you create in Step 3 (or delete it if you inline the loop instead of extracting a helper — the cross-process test is the guarantee that matters).

- [ ] **Step 2: Run test to verify it fails / drives the design**

Run: `pytest tests/test_concurrency.py::test_same_show_built_once_across_processes -q`
Expected: PASS already for the *marker* helper (it uses `file_lock` directly), confirming the lock semantics. This test locks in the guarantee that Task 6's loop must preserve; run it before and after the loop change.

- [ ] **Step 3: Rewrite the runner loop as two passes**

In `src/llama/cli.py`, add `from llama.locks import Locked, file_lock` (if not already imported by Task 5). Replace the single `for entry in chosen:` loop body (292-316) so the per-entry work is factored into a local and wrapped in the show lock:

```python
    setlistfm = make_client(config)
    packaged = held = failed = 0

    def _process(entry):
        nonlocal packaged, held, failed
        try:
            pkg = process_show(ws, ia, ledger, entry, providers, ws.name, config.audio_format,
                               force=force, script=script, voice=voice, speech=speech,
                               chunk=config.tts.chunk,
                               bed=resolve_bed(config, presenter),
                               presenter=presenter, title=title,
                               setlistfm=setlistfm,
                               structure_cfg=config.structure, selection_cfg=config.selection,
                               jerrybase_enabled=config.jerrybase.enabled,
                               force_stage=force_stage)
        except (TaskFailed, LLMError, IAError, SpeechError) as exc:
            if isinstance(exc, TaskFailed) and exc.raw_output:
                failure_path = ws.show_ws(entry.candidate.performance_id).dir / "llm-failure.txt"
                failure_path.parent.mkdir(parents=True, exist_ok=True)
                failure_path.write_text(exc.raw_output)
            typer.echo(f"FAILED {entry.candidate.performance_id}: {exc}", err=True)
            failed += 1
            return
        if pkg:
            typer.echo(f"packaged: {pkg}")
            packaged += 1
        else:
            typer.echo(f"needs-review, skipped: {entry.candidate.performance_id}")
            held += 1

    try:
        deferred = []
        for entry in chosen:
            lock_path = ws.show_ws(entry.candidate.performance_id).lock
            try:
                with file_lock(lock_path, blocking=False):
                    _process(entry)
            except Locked:
                deferred.append(entry)                 # another run is building it
        for entry in deferred:                          # come back and wait
            with file_lock(ws.show_ws(entry.candidate.performance_id).lock):
                _process(entry)
    finally:
        if speech is not None:
            speech.close()
```

Keep the summary/echo block after the `finally` exactly as it is today.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_concurrency.py -q`
Expected: PASS. Then `pytest -q` — the full suite (single-process `get`/`run` behavior is unchanged because the locks are uncontended and deferral never triggers).

- [ ] **Step 5: Commit**

```bash
git add src/llama/cli.py tests/test_concurrency.py
git commit -m "feat: defer-locked two-pass runner loop (wait+reuse on same-show contention)"
```

---

### Task 7: Documentation

**Files:**
- Modify: `CLAUDE.md` (architecture note on concurrency)
- Modify: `README.md` (a short "running multiple jobs at once" note, if the README has an operations/workflow section)

**Interfaces:** none (docs only).

- [ ] **Step 1: Add a concurrency note to `CLAUDE.md`**

Under the Architecture section, add a bullet:

> - **Parallel-safe workspace:** multiple `llama` processes may run concurrently against one local `~/.llama/`. Coordination is advisory `fcntl.flock` (`src/llama/locks.py`) at two scopes — a short **ledger lock** (`ledger.jsonl.lock`) around every ledger mutation, and a long **per-show lock** (`shows/<slug>/.lock`) around `process_show` and every single-show mutator (`redo`/`fix`/`voice`/`deliver`/`rm`). Locks auto-release on process death (no stale-lock reaping). Same-performance runs serialize (first builds, others wait and reuse); independent shows run fully in parallel. Readers (`show`/`status`/winnow dedup) never lock. All atomic writes use unique temp names. POSIX-only; non-POSIX degrades to no-op locking.

- [ ] **Step 2: Add an operator note to `README.md`**

In the workflow/operations section, add a short paragraph:

> **Running several jobs at once.** `llama` is safe to run as multiple concurrent processes against the same `~/.llama/` on one machine — kick off several `llama get`/profile runs (or a cron fan-out) in parallel. If two runs pick the same performance, one builds it and the others wait and reuse the result rather than duplicating the work; runs never idle behind each other on shows they don't share. (Local filesystem only — a network/NFS-shared workspace is not supported.)

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: note parallel-safe concurrent llama runs"
```

---

## Self-Review

**Spec coverage:**
- locks.py primitive (spec §1) → Task 1. ✓
- Ledger locking + atomic rewrite (spec §2) → Task 3. ✓
- Run-name atomic claim (spec §3) → Task 4. ✓
- Atomic-write hygiene / unique temps (spec §4) → Task 2 (+ ledger rewrite in Task 3). ✓
- Per-show lock + mutator boundary (spec §5) → Task 5 (single-show mutators) + Task 6 (runner loop). ✓
- Defer-locked runner loop (spec §6) → Task 6. ✓
- Error handling (spec) → `Locked` handled in Task 6; lock/temp cleanup in Tasks 1–2. ✓
- Testing strategy (spec) → test files across Tasks 1–6; the fork-context, offline, cross-process guarantees are all present. ✓
- Docs → Task 7. ✓

**Placeholder scan:** the only intentional `<same base expression>` / `<resolve ShowWorkspace…>` markers are "keep the existing code here" anchors, not missing content — the surrounding structure and the lock wrapper are fully specified. No TBD/TODO.

**Type consistency:** `file_lock(path, *, blocking)` / `Locked` (Task 1) used identically in Tasks 3, 5, 6. `atomic_write_text`/`atomic_write_bytes` (Task 2) used in Tasks 2, 3. `claim_run_dir` (Task 4) matches its callers. `ShowWorkspace.lock` (Task 5) used in Task 6. Consistent.
