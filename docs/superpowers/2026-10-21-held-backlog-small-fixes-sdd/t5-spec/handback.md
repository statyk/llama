### Spec Compliance (SPEC role) — ✅ Spec compliant
⚠️ Cannot verify from diff (cross-task): CLAUDE.md's new pointer "(one unit: see `llama fix` below)" (CLAUDE.md:65) refers to unit text that does not exist yet. Task 6's plan step adds the "One unit (2026-10-21)" paragraph to the `llama fix` entry, so it resolves there. Note that the `llama fix` entry sits *above* the `redo` entry on the same line, not below. That wording is plan-mandated and trivial.

### Strengths
- `_redo_show` / `_redo_show_locked` match the brief's interfaces exactly (cli.py:2458-2511). `_redo_show` is `with show_unit(entry.ws, None): return _redo_show_locked(...)`. `_redo_show_locked` takes no lock and re-reads `provenance.json` under the caller's lock via `read_model(show_ws.provenance, Provenance)`, not `entry.provenance`. It raises `ShowChanged("<slug>: the show was removed; nothing changed")` only when `entry.provenance` was set, and otherwise today's `LlamaError` with byte-identical text. Apart from that check it touches only `entry.ws` and `entry.slug`. The positional shape `(config, ia, ledger, e, stage, **kw)` is preserved. The refusal string matches the global-constraints fixed string. `process_show` is unchanged and still lock-free.
- Named risk (a), lock discipline. Check: grepped every `_redo_show`/`file_lock(` site in cli.py.
  - `_redo_show` is called at 1818/1823 (`_untitled_resolution`), 1940 (triage), 3188 (fix), 3262 (`_redo_batch`) and 3356 (single redo). None of these callers holds the show lock, so each takes it exactly once, inside `show_unit`. Before this change `_redo_show` took `file_lock` itself, so the caller contract did not change.
  - `_redo_show_locked` has no production caller other than `_redo_show`.
  - The other show-lock sites, 686 (`_execute` deferred pass) and 2316 (`_deliver_one`), never reach `_redo_show`.
  - No double lock and no unlocked pipeline run. The pin test `test_redo_runs_the_pipeline_inside_the_show_lock` confirms the pipeline runs under the lock.
  - Spec note: fix/triage still write overrides outside the lock, and `--untitled` still runs as two units. That is Tasks 6/7 scope per the plan (plan lines 722-1015), not a gap in Task 5.
- Named risk (b), `_execute._process` (cli.py:581-598). The `RateLimited` arm stays above the broadened `(TaskFailed, HerderError, LlamaError)`. `IAError` subclasses `LlamaError` (the implementer says so; I did not re-check it). `sessions.classify_failure` (sessions.py:29-44) still tests `IADownloadError`→download and `IAError`→archive before falling through to `other`, so the archive/download kinds and the sweep's re-spend set are unchanged. `Locked` and `RunMissing` are plain `Exception`, not `LlamaError` (locks.py:11,43), so the wider catch does not swallow the deferral path or run-level aborts.
- Named risk (c), batch redo. `_redo_batch` (cli.py:3260-3266) calls `_redo_show` per show, so each show gets its own unit. `ShowChanged`/`LlamaError` are caught into `FAILED <slug>: <msg>`, and the command exits 0. `test_redo_batch_restores_a_failed_show_and_continues` asserts exit 0, `FAILED aready: boom`, that `bready` was processed, and that `aready`'s tree is byte-identical after a half-write.
- Every C5 item in Task 5's slice has a test that asserts what the brief says, word-for-word with the brief:
  - failed `redo --from brief` restores every file;
  - an `IAError` on purged audio removes the new audio and restores the manifest;
  - `KeyboardInterrupt` after the drop restores and re-raises, with no `.txn`;
  - a show removed while the redo waited refuses with the fixed string and leaves the `.lock`-only husk;
  - a leftover `.txn` is deleted;
  - a run whose show refuses its overrides records `("a", "other")`, continues to `b` and ends `incomplete`;
  - pin: `reapply` on refused overrides writes nothing.
- The brief's listed imports were added. `helpers.packaged_gd73` matches its interface: config with `[jerrybase] enabled = false`, `make_providers`/`IAClient` patched, `test_pipeline` imported inside the function, returns `(cfg, ws)`.
- Both CLAUDE.md sentences are present verbatim as the brief specifies.
- A single `redo` exits 1 with the error, as C2 requires. `main_cli` (cli.py:4091-4108) prints `error: <msg>` and exits 1 for `LlamaError`/`HerderError`, and `IAError`/`ShowChanged` are `LlamaError`s. The new single-redo tests assert exit 1 and the exception type.
- The implementer reports RED 7 failed / 2 passed, matching the brief's prediction (5 failing redo-cmd tests + batch + pace = 7, plus 2 pins). Reasoning per test agrees: on c9d770c, `_redo_show_locked` does not exist, no `.txn` is discarded, and a `LlamaError` aborts `_execute`. GREEN: 4014 passed, 1 skipped, 8 deselected.

### Issues
#### Critical
None.
#### Important
None.
#### Minor
1. Spec C1's step order is (3) refuse a removed show, then (4) delete the leftover, then (5) snapshot. For redo, the removed/no-provenance check now runs inside the unit, after `_discard_leftover` and `take_snapshot` (show_unit.py:149-153 → cli.py:2482-2486). Net effect on a refusal is only that a stale `.txn/` gets deleted, plus the `.lock` husk the spec already documents. The restore leaves every other file byte-identical. This is plan-mandated: the brief puts the check in `_redo_show_locked` with `expect=None`. It is harmless and needs no fix. A one-line note in `_redo_show`'s docstring would record the order if wanted.
2. `test_a_leftover_txn_is_deleted_not_restored_by_the_next_redo` (test_redo_cmd.py) cannot tell "deleted" from "restored". A successful redo never restores, and `take_snapshot` would overwrite the stale `files/show.json` even without `_discard_leftover`. It only proves the `.txn` is gone after success. This is plan-mandated test text. Task 4's own `show_unit` tests and Task 8's mutation run are where the "not restored" half is actually pinned. Confirm Task 8 names a red test for removing `_discard_leftover`.

### Assessment
**Task quality:** Approved.
**Reasoning:** The diff implements the brief's `_redo_show`/`_redo_show_locked` split and the `_execute` catch exactly, with every C5 test in this slice present and correct. All three named risks check out: single lock at every call site, `RateLimited` still first with archive/download classification intact, and batch per-show units with exit 0. The two minor notes are both plan-mandated and harmless.
