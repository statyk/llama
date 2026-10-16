### Spec Compliance

- ✅ Spec compliant. `packages/emcee/src/emcee/moves.py` and `packages/emcee/tests/test_moves.py` are byte-identical to the brief's Step 1/Step 3 blocks (checked by extracting the brief's code blocks and `diff`ing: no output). The `helpers.py` hunk matches the brief's `no_moves`/`moves_of` plus the `from emcee.moves import Moves` import (helpers.py:11, :167-180). All three listed files are touched. Against spec §3: the store is keyed by performance_id with `package`/`moved_at` (moves.py:163-175); writes hold a flock on `moves.json.lock` around load-modify-write (moves.py:167, :186); entries are edited in place so unknown keys survive (moves.py:172-173); unique temp + fsync + replace (moves.py:147-153); `--clear` matches recorded entries first, by exact id or recorded package, refuses ambiguity listing the ids, and leaves `{}` behind (moves.py:186-197); strict loading names the file (moves.py:41-74); `require_present` names the path, the count and both ways out (moves.py:96-112). No llama import.
- ⚠️ Cannot verify from diff: (a) spec §3's "exact name, then unique substring" resolution for `--clear` lives in the `live_performance_id` callable a later task supplies; (b) the "every command loads moves first" and "`move` scans for move-voiced packages before writing" ordering are the callers' job (Tasks 4-6). The controller should check both when those tasks land.

### Strengths

- Strictness is complete and tested at every layer: invalid JSON, a non-object top level, a non-object entry, a missing `profile`, a non-string profile and an empty-string profile (test_moves.py:58-71); IsADirectoryError and non-UTF-8 (test_moves.py:74-83). Every message asserts that the path is named.
- The lock tests check real flock state through a second fd (`_lock_is_held`), not a mock, and check it at both read and write time (test_moves.py:26-36, :176-201, :233-237).
- `record_move` never overwrites a malformed file (test_moves.py:169-173), and clearing an unrecorded move writes nothing, not even an empty file (test_moves.py:226-229). These are the strict-surface-2 cases that matter.
- `clear_move` uses `_no_live`, which raises if called, to prove a recorded match never touches the live package (test_moves.py:204-205).
- The test count matches the claim: 25 tests (19 functions plus 6 parametrized cases).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
- **plan-mandated** — moves.py:142-160 `write_moves` re-implements the unique-temp + `os.replace` + unlink-on-failure block of `emcee.workspace.atomic_write_bytes` (workspace.py:21-33) almost verbatim. The only additions are `flush()` and `fsync()`. The repo states this pattern must not be duplicated: workspace.py's module docstring, and package_io.py:86-88 ("the unique-temp + os.replace pattern must not be duplicated"). Named risk checked: an existing atomic-write helper, found via grep for `mkstemp|os.replace|fsync` in `packages/emcee/src/emcee/`. Fix: give `atomic_write_bytes` a keyword `fsync: bool = False` (flush + `os.fsync` before the replace). Then `write_moves` becomes `atomic_write_bytes(moves_path(root), payload, fsync=True)`. `test_write_moves_fsyncs_...` would need its monkeypatch target moved to `emcee.workspace.os.fsync`. The brief mandated this code, so this is the human's call.

#### Minor (Nice to Have)
- moves.py:142-144: the docstring promises "old file or the new one" after a crash. That holds for tearing. Without an fsync of the parent directory after `os.replace`, the rename itself can be lost on power failure, so the old file reappears. Acceptable for this file; only worth fixing if durability, and not just atomicity, is the intent.
- moves.py:168-170: an identical-profile `record_move` returns False without refreshing the informational `package` name when the package was renamed since. This matches spec ("unchanged"), but `--list` will then show the stale name. Note only.
- test_moves.py:169-173 and :240-245: nothing checks that the lock is released when the body raises (malformed file, ambiguous clear), or after `clear_move`. Only `record_move`'s success path asserts the lock is released (test_moves.py:202). The `finally` in moves.py:133-138 is right, but it is unpinned.
- Implementer report: RED was "not separately captured". There is no failing-run evidence for TDD. The module was new, so the claimed ModuleNotFoundError is very likely, but it is not evidenced.

### Assessment

**Task quality:** Approved

**Reasoning:** The implementation is exactly what the brief specified. It is correct on every strict-surface-2 path, and the tests verify real file and flock behavior. The one Important item duplicates an existing atomic-write helper at the plan's direction; whether to fold it into `atomic_write_bytes(fsync=True)` is the human's decision and does not block this task.
