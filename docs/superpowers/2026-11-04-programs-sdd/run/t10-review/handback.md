### Spec Compliance

- ✅ Spec compliant. `diff emcee/station_lock.py llama/station_lock.py` shows only the differences the implementer listed. The algorithm lines (acquire, release, `_critical`/`_deferred`/`_unblock`/`_exiting`, `_exit_on_signal` releasing and then calling `os._exit(128+signum)`, and handler install and restore) are byte-identical to the four-round-reviewed emcee reference. R6 and t5b are therefore carried unchanged.
- ⚠️ Cannot verify from this diff: whether every llama caller (deliver, clear-mark, bulk_apply steps) goes through `for_package`. That wiring belongs to later tasks. At HEAD, `grep station_lock|for_package` over packages/llama/src and scripts matches only the module itself.

Checks run:
- `LOCK_NAME`/`MAGIC` are the same in both modules: llama station_lock.py:47-48, emcee :46-47.
- `tool: llama`, llama station_lock.py:137. This is the only change in the holder body.
- `LlamaError` replaces `EmceeError` at :45, :55, :94, :101 and :153. The create error keeps the `cannot create the station lock at {path}: {_reason}` text.
- StationLocked, llama station_lock.py:55-67: the message is the header `the station is locked by another writer ({path}):`, then each holder line indented two spaces, then `  check it with: emcee lock show; remove it with: emcee lock clear (only if that writer is gone)`. `_CLEAR_HINT` (:51-52) is verbatim, and `.path`/`.holder` are set. `details` is `[]`, so llama's CLI boundary (cli.py:2005, `error: {exc}`, then details) prints the same content emcee prints from details. Empty holder: `"".splitlines()` is `[]`, which gives header plus hint and stays correct. This is the brief's 3-part message ("three lines" means header, holder block, hint), and the test pins it exactly (test_station_lock.py:70-75, including `exc.details == []`).
- `for_package`, llama station_lock.py:320-324: `station_lock(Path(out).absolute().parent, ...)`. Named risk: llama and emcee might derive different folders, for example absolute() on one side and resolve() on the other, which would give two lock files behind a symlinked share path. Checked: emcee's callers all use `.absolute().parent` (emcee cli.py:775, :900), so the derivation matches. The relative case is tested at test_station_lock.py:518-523: chdir, `Path("gd73-06-10")`, `held.path.is_absolute()`, equal to `tmp_path.absolute()/LOCK_NAME`.
- Return annotation: `AbstractContextManager[Held]` instead of the brief's `ContextManager[Held]`. These are equivalent and the deprecation-free choice is fine.
- Tests mirror emcee name for name. The test diff contains only import, FOREIGN, command-string, error-class and comment substitutions, the reworked refusal assertion, and the two added tests (:510, :526). The subprocess window script and both thread modes (`sys.argv[3:] == ["thread"]`, :311) carry over unchanged and import `llama.station_lock` (:159, :306, :446). FOREIGN is now an emcee holder, which makes the refusal test genuinely cross-tool (`"tool: emcee" in text`, :532).
- No emcee imports: `grep import emcee` over packages/llama/src matches nothing. The `emcee` mentions in station_lock.py are only in strings, comments and docs.
- The reworded comments are accurate. The `bulk_apply` per-show step and "all through `for_package`" (:17-20) match the spec's "Who acquires" section. "llama's status heartbeat" (:203, test :311) is real: status.py:126 starts a daemon `heartbeat:` thread.
- The unused `read_lock` is kept (:90-101). It is dead in llama's src but exercised by the mirrored tests. Keeping the modules diffable name for name is worth more here than YAGNI on a strict, twinned surface. I accept it.

### Strengths
- The implementer produced the module by mechanical substitution from the reviewed emcee module, so it inherits every reviewed fix, and the 72-line diff is easy to audit completely.
- The one deliberate departure in shape (message vs `details`) has a stated reason in the docstring: batch callers that report `str(exc)` alone still name the holder and both emcee commands. The exact-shape test pins it.
- The `for_package` test covers both the absolute and the relative `out` case, and it checks that the lock is not placed inside the package directory (:514).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. packages/llama/tests: llama has no `test_no_emcee_imports` guard, while emcee (packages/emcee/tests/test_no_llama_imports.py) and transmitter do. The global constraint "llama never imports emcee" is enforced in only one direction. This task adds the first llama module that is a deliberate twin of an emcee module, so the temptation to import is now highest. The gap existed before this task and is outside the brief, so it does not block. Recommend a follow-up, about 25 lines: copy emcee's file with `llama`/`emcee` swapped, checking both src and tests (FORBIDDEN `^\s*(?:from|import)\s+emcee\b` plus the `import_module` form).
2. llama station_lock.py:55-67: the refusal is now multi-line inside `str(exc)`. A future batch caller that writes the error into a single-line record (a ledger row or a JSON field) will contain embedded newlines. That is intended, but worth knowing when Tasks 11+ wire batch listings.

### Assessment

**Task quality:** Approved

**Reasoning:** The module is the reviewed emcee algorithm with only contract-required substitutions. `for_package` derives the folder exactly as emcee's callers do, and the refusal message is pinned verbatim, with the holder and both emcee commands. The only gap is a pre-existing missing llama-side import guard, which is recommended as a cheap follow-up.

Tests: not re-run. Reading the code raised no doubt that the implementer's reported run (52 passed, warning-free) does not already answer.
