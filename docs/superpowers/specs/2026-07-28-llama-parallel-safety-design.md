# llama parallel-safety design

**Status:** approved (brainstorm), ready for implementation planning
**Date:** 2026-07-28

## Problem

`llama` was built as a single-operator, one-run-at-a-time tool over a shared
on-disk workspace (`~/.llama/`). Many stages are slow (network fetches, LLM
research/synthesis, TTS), so running several jobs concurrently would be a real
convenience. But the workspace has **no cross-process coordination of any
kind** — no `fcntl`/`flock`/`filelock`/lockfiles/`O_EXCL` anywhere in `src/`.
Every write is either a fixed-name temp-then-rename or a plain append, and
several shared files are read-modify-write with a wide TOCTOU window. Running
two `llama` processes in parallel today can:

- **Lose or duplicate `ledger.jsonl` rows.** `record` scans the whole file for
  duplicates and *then* appends (not atomic together); `remove`/`remove_status`
  read → filter → rewrite the whole file, so any append that lands between a
  remove's snapshot and its rename is silently dropped.
  (`src/llama/ledger.py:25-49`.)
- **Corrupt caches and sidecars.** `write_artifact` and every cache/ledger/TTS
  writer use a *fixed* temp name (`<path>.tmp`, `.jsonl.tmp`, `.part`), so two
  processes writing the same target interleave into one temp file before the
  rename. (`src/llama/workspace.py:17-23`, `ia_client.py:77-79`,
  `setlistfm.py:93-95`, `stages/package.py:232-234`.)
- **Collapse two runs into one run directory.** `unique_run_name` only *reads*
  whether `runs/<name>/` exists; two same-day identical invocations both
  compute the same name before either creates the dir.
  (`src/llama/workspace.py:107-116`.)
- **Interleave two runs into one `shows/<slug>/` dir.** Show dirs are global,
  keyed only by performance id (not namespaced by run), guarded only by
  `exists()`/`should_run` checks — themselves TOCTOU — while `--force`/
  `drop_stage_artifacts` actively unlinks artifacts another run may be
  mid-read on. (`src/llama/workspace.py:80-104`, `pipeline.py:70-132`.)

## Goal & scope

Make `llama` safe to run as **a few concurrent processes on one machine against
a local `~/.llama/`** (SSD/APFS; no network filesystem). Concurrency of the
*slow* stages is the point, so the design must not serialize independent work —
only genuine same-resource collisions may block.

**Contention semantics (decided during brainstorming):**

- When two runs land on the **same performance** (same `shows/<slug>/`), the
  first to acquire the show lock builds it; others **wait and reuse** the
  completed show (recording their own per-run ledger row), never duplicating
  the expensive work. This preserves the "library reused across runs" model.
- A waiting run **defers** locked shows: it try-locks each show, builds its own
  *unique* shows first, then comes back and blocks on the deferred (shared)
  ones — so it never idles behind another run.

**Out of scope:** network/NFS-shared workspaces, multi-machine coordination, a
daemon/job-queue architecture, and any change to pipeline stage logic beyond
adding locks and unique temp names.

## Approach (chosen)

**Fine-grained `fcntl.flock` advisory locks at two scopes, plus atomic-write
hygiene.** Rejected alternatives: a single global workspace lock (trivially
correct but fully serializes — defeats the purpose) and a daemon + job queue
(the "real" concurrency architecture, but massive scope for a few jobs on one
Mac — YAGNI).

### 1. The locking primitive — `src/llama/locks.py` (new)

A small module wrapping `fcntl.flock` on a dedicated **sidecar** file (never
renamed or deleted while held):

```python
class Locked(Exception):
    """Raised by a non-blocking acquire when another process holds the lock."""

@contextmanager
def file_lock(path: Path, *, blocking: bool = True):
    """Advisory exclusive lock on a .lock sidecar. Auto-released on close/crash.
    Non-blocking mode raises Locked if another process holds it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError:
            raise Locked(path)          # only reachable in non-blocking mode
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
```

Two lock **scopes**, using stable sidecar paths:

- **Ledger lock** — `~/.llama/ledger.jsonl.lock` (one global lock, held for
  milliseconds around each ledger read-modify-write).
- **Per-show lock** — `~/.llama/shows/<slug>/.lock` (held for the whole build,
  possibly minutes; the lock a waiting run blocks on).

Committed design properties:

- **Auto-release.** `flock` is tied to the open fd, so a crashed or killed
  process drops its lock immediately. The `.lock` files linger on disk but hold
  nothing. **No stale-lock reaping, no timeouts, no PID files.**
- **Deadlock-free by lock ordering.** A show build holds the *show* lock and
  only ever grabs the *ledger* lock briefly at the very end (`ledger.record`),
  then releases it. The ledger lock never nests a show lock. A single
  consistent order (show ⊃ ledger, never the reverse) means no cycle is
  possible.
- **Advisory — writers-only opt-in.** Locks work only because *every writer*
  takes them. **Readers deliberately take no lock**: every file they read is
  written via atomic rename, so a reader always sees a whole old-or-new file
  and never blocks behind a long build. Read-only commands (`show`, `status`,
  `pipeline`) and winnow's ledger dedup scan stay lock-free.
- **Sidecars survive dir wipes.** The show `.lock` sidecar must survive
  `drop_stage_artifacts`/`rm` deleting the dir's *contents*: the holder keeps
  its fd and the inode persists until close (safe on POSIX). Lock sidecars are
  gitignored (they live under `~/.llama/`, already outside the repo, but the
  pattern is noted for any test fixtures).

Platform note: `fcntl` is POSIX-only. `llama` ships macOS/Linux binaries; the
Windows build path is not a supported concurrency target and is out of scope
for this design. The module may guard the import so a Windows run degrades to
no-op locking (single-process behavior unchanged) rather than failing to
import — decided at implementation time.

### 2. Ledger — `src/llama/ledger.py`

Wrap each mutator's read-modify-write in the ledger lock, re-reading *inside*
the lock so check-then-act is atomic:

```python
def record(self, entry):
    with file_lock(self._lock_path):        # ~/.llama/ledger.jsonl.lock
        for e in self._entries_unlocked():  # re-read under lock
            if (e.performance_id, e.status, e.run) == key(entry):
                return
        with self.path.open("a") as f:
            f.write(entry.model_dump_json() + "\n")
```

The same wrapper covers `remove` and `remove_status`: the entire read → filter
→ rewrite runs under the lock, so an append can no longer be lost between a
remove's snapshot and its rename, and two removes can't clobber each other.
Readers (`entries`, `played_ids`, `rejected_ids`, `latest_dispositions`, and
winnow's dedup) stay lock-free. The rewrite paths also drop the shared fixed
`.jsonl.tmp` name in favor of a unique temp (see §4).

### 3. Run-name atomic claim — `src/llama/workspace.py`

Replace the `exists()`-check in `unique_run_name` with a claim that atomically
creates the run directory:

```python
def claim_run_dir(root, base):
    runs = root / "runs"
    for name in [base, *(f"{base}-{n}" for n in itertools.count(2))]:
        try:
            (runs / name).mkdir(parents=True, exist_ok=False)  # atomic claim
            return name
        except FileExistsError:
            continue
```

`mkdir(exist_ok=False)` is the atomic primitive — the loser gets
`FileExistsError` and bumps to the next suffix, so two same-day identical
invocations get distinct names and distinct dirs. Callers at `cli.py:344` and
`cli.py:375` switch from `unique_run_name` to `claim_run_dir`; the run dir now
exists a beat earlier, which is harmless since the run immediately writes into
it. `unique_run_name` is removed and its existing unit test
(`tests/test_sessions.py:18`, `test_unique_run_name`) is rewritten against
`claim_run_dir` — since `claim_run_dir` creates each dir itself, three
successive calls with the same base yield `x`, `x-2`, `x-3` without the test's
manual `mkdir` between calls.

### 4. Atomic-write hygiene — unique temp names

Give every temp-then-rename writer a **unique** temp name (via
`tempfile.mkstemp` in the target directory) so two processes writing the same
target never interleave into one temp file:

```python
def write_artifact(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)          # atomic; last-writer-wins, never torn
    except BaseException:
        os.unlink(tmp)                 # don't leak temps on failure
        raise
```

Same unique-temp treatment for:

- caches — `ia_client.py:77-79`, `setlistfm.py:93-95`, `artist_index.py:111`
  (the last already goes through `write_artifact`, so it inherits the fix);
- ledger rewrites — `ledger.py:37,46`;
- TTS clips — `stages/package.py:232-234` (the `.part` temp).

`profiles.py:33` and `presenters.py:41` switch from in-place `write_text` to
`write_artifact` so they become atomic too. For content-hash-keyed caches,
last-writer-wins is correct because both writers produce identical bytes — the
goal is to kill the *interleaving*, not to order the writers.

### 5. Per-show lock — the mutator boundary

**Rule:** any command that writes into or deletes a `shows/<slug>/` dir
acquires that show's lock; readers don't. Concretely:

- `process_show` (`pipeline.py`) — the whole body, from the
  `drop_stage_artifacts`/provenance write through the final `ledger.record`,
  runs under the show lock. This one change also closes the
  `--force`/`drop_stage_artifacts` mid-flight-deletion race: a concurrent
  build/redo of the same show can't enter until the lock frees.
- `fix`, `redo`, `voice` (all funnel through `process_show` / redo-from-stage),
  `deliver` (writes its delivery marker + records the ledger), and
  `rm`/`catalog.remove_show` (deletes the dir) each acquire the target show's
  lock before touching it.
- Read-only `show`, `status`, `pipeline` take no lock.

### 6. The defer-locked runner loop — `src/llama/cli.py`

The `for entry in chosen` loop (`cli.py:292`) changes from a straight pass into
two passes so a run never idles behind another run's build:

```python
deferred = []
for entry in chosen:
    try:
        with file_lock(show_lock_path(ws, entry.candidate.performance_id),
                       blocking=False):
            _process(entry)                    # existing try/except accounting
    except Locked:
        deferred.append(entry)                 # another run is building it
# second pass: block on the ones we skipped, then reuse-or-build
for entry in deferred:
    with file_lock(show_lock_path(ws, entry.candidate.performance_id),
                   blocking=True):
        _process(entry)
```

`_process(entry)` is the existing body: the `process_show(...)` call plus its
`try/except (TaskFailed, LLMError, IAError, SpeechError)` accounting
(`packaged`/`held`/`failed`) and the `pkg`/needs-review echo — unchanged.

**Reuse falls out for free.** When the deferred pass finally acquires a show
another run just finished, `process_show`'s existing `should_run`/`exists()`
stage guards see the artifacts present and skip straight through gather →
package to this run's own `ledger.record` — no duplicated LLM/network/TTS work.
A `Locked` exception can only arise on the *first* (non-blocking) pass; the
second pass blocks, so `Locked` is never confused with a stage failure.

**Force edge case:** a run invoked with an explicit `--force`/`--from <stage>`
still *rebuilds* on the deferred pass (force bypasses the `should_run` guards) —
correct, since the user explicitly asked to redo, and now safe because it holds
the show lock throughout.

## Error handling

- **Lock acquisition failure** other than contention (e.g. `OSError` opening the
  sidecar) propagates as a normal error — it means the workspace is
  unwritable, which is already fatal.
- **Non-blocking contention** on the first runner pass is caught as `Locked`
  and handled by deferral; it is never surfaced as a failure.
- **Process death mid-build** releases the show lock automatically (flock
  semantics); the partially-built show dir is left with whatever atomic-renamed
  artifacts completed, exactly as a crash leaves it today — the next run
  reuses/continues via the normal `should_run` guards.
- **Temp-file leaks** on write failure are cleaned up in the `write_artifact`
  except-branch rather than accumulating.

## Testing strategy

Cross-*process* safety must be exercised with real separate processes (threads
sharing an fd share the flock and prove nothing). All tests offline (no network,
no real LLM — `fake` backend).

**`tests/test_locks.py` (primitive):**
- Acquire/release round-trip; sidecar file created.
- Non-blocking acquire raises `Locked` when the lock is already held (held in a
  forked child, released via a shared barrier).
- **Auto-release on death:** fork a child that acquires then `os._exit()`s
  without releasing; the parent then acquires non-blocking and succeeds.

**`tests/test_concurrency.py` (`os.fork`/`multiprocessing` over a `tmp_path`
workspace, shared start barrier):**
- **Ledger no-loss/no-dup:** N children each `record` a distinct row (and some
  the *same* row); assert the final `ledger.jsonl` has exactly the expected
  unique rows. A record-vs-remove race variant asserts the appended row
  survives.
- **Run-name claim:** N children call `claim_run_dir` with the same base
  simultaneously; assert N distinct names and N distinct dirs.
- **Same-show single-build:** two children run the pipeline (fake backend) on
  the same performance; a build-counter marker (a file a stage appends to)
  asserts the expensive stages ran **once**, and both children recorded their
  own per-run ledger row.
- **Different-show parallelism (liveness):** two children on *different* shows
  both complete without either blocking — guards against an over-broad lock.

**`tests/test_atomic_write.py`:** two processes writing the same target via
`write_artifact` yield a file equal to exactly one input (never a byte-mix), and
no `.tmp` files are left behind.

These join the existing offline `pytest -q` suite. The fork-based tests are kept
lean; if any prove flaky on CI they get an opt-in marker, but the goal is to
keep them in the default run since they are the actual guarantee.

## Files touched

- **new:** `src/llama/locks.py`, `tests/test_locks.py`,
  `tests/test_concurrency.py`, `tests/test_atomic_write.py`
- **test update:** `tests/test_sessions.py` (`test_unique_run_name` rewritten
  against `claim_run_dir`)
- **modified:** `src/llama/ledger.py` (lock + unique temp),
  `src/llama/workspace.py` (`claim_run_dir`, `write_artifact` unique temp,
  show-lock path helper), `src/llama/pipeline.py` (wrap `process_show` in show
  lock), `src/llama/cli.py` (defer-locked runner loop; show lock in
  `fix`/`redo`/`voice`/`deliver`/`rm`; `claim_run_dir` callers),
  `src/llama/ia_client.py`, `src/llama/setlistfm.py`,
  `src/llama/stages/package.py` (unique temps), `src/llama/profiles.py`,
  `src/llama/presenters.py` (atomic writes via `write_artifact`),
  `src/llama/catalog.py` (`remove_show` under show lock).

No new dependencies (`fcntl`, `tempfile`, `os` are stdlib).
