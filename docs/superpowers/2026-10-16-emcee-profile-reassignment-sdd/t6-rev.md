### Spec Compliance

- ✅ Spec compliant. `cli.py` matches the brief's Step 3 verbatim (diff lines 85-205); `_COMMAND_ORDER` gains `move` after `status` (cli.py diff:63; boundary test diff:234); `test_move_cmd.py` is the brief's Step 1 file verbatim. Spec §3 checked item by item:
  - Addressing via `_resolve_package` (diff:171, 161); every form requires a station root (brief decision), resolved via `_resolve_station_root` (diff:152).
  - Strict surface 2: `_load_station` (cli.py:216-224, unchanged, Task 4) loads moves first (malformed = EmceeError naming the file), then scans, then runs `require_present`. `move_cmd` calls it for every form before any write or read (diff:153). Tests pin record/`--list`/`--clear` for both the missing-file guard (test diff:470-487, which also asserts both ways out are named and no file is created) and a bad file (truncated and wrong-shape × 3 forms, diff:493-508).
  - Refusals exit 1 with the file unchanged: unassigned target, no `performance_id`, unsupported, unreadable. Each runs with the file present and absent (diff:438-457).
  - A move to the delivered profile needs no assign entry, by name (diff:364-369) or `--delivered`, including a `null` delivered profile (diff:372-377).
  - Output states are verbatim from the global constraints, the "missing audio replaces the next-run claim" rule included (diff:197-205; tests diff:343-361). The state comes from the profile check, not full readiness (diff:333-340).
  - `--clear` matches recorded entries first, refuses ambiguity with the ids, and leaves `{}` behind (moves.py `clear_move`; tests diff:514-557).
  - `--list` prints the `missing` and `[no assign entry]` markers (diff:89-114, 563-581).
  - A move survives `--replace-voiced` re-delivery (diff:587-598).
  - The lock is held around both the read and the write (diff:390-413).
- ⚠️ Cannot verify from diff: nothing material. `assess`/`Assessment` fields (`voiced`, `profile_reason`, `missing_tracks`, `effective`) and `PackageStatus.delivered_profile` come from Tasks 3-5. The passing tests the implementer reports exercise them, but their semantics were reviewed with those tasks, not here.

### Strengths

- The guard ordering is right and pinned. `_load_station` runs before `record_move`/`clear_move` on every form, so recording a new move can never create a fresh `moves.json` that silences the missing-file check (spec §3's stated reason). The "file-absent" refusal parametrization (test diff:438) also proves that a refused move does not create the file as a side effect.
- `clear_move` (moves.py) calls `live_performance_id` only when no recorded entry matches, and only inside the lock. A failing live lookup raises before `write_moves`, so `--clear` on a missing file with no match never creates the file.
- The lock test checks the lock really is held at the read and at the write, using a non-blocking probe flock. It does not use a mock.
- The "missing audio" test runs as three cases and asserts that `next emcee run` is absent, which pins the replacement rule rather than only the presence of the new text.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. **The writer can produce a `moves.json` its own strict reader rejects, and reports it as a success with exit 0** (cli.py diff:179-192; moves.py `record_move`).
   - Risk checked: whether the record path can produce a file that `_validated` rejects. I checked it with a scratch probe (temp `EMCEE_ROOT`, nothing in the worktree touched): with config `[assign.profiles.""]`, `emcee move ttb ""` passes `target_problem` and writes `"profile": ""`. The post-write `assess(... load_moves(...))` then raises the malformed-file error, which the broad `except Exception` turns into `moved: ttb  funk ->  (state unknown: …malformed…)` with exit 0. Every later `run`/`voice`/`status`/`move` then hard-fails until the file is hand-edited.
   - Reachable only through a quoted empty TOML table key, so it is very unlikely, and nothing is lost (it is a loud failure, not a silent one). But it is a writer/reader schema mismatch on strict surface 2.
   - Cheapest fix: `record_move` runs `_validated(data, path)` (or checks `profile is None or (isinstance(profile, str) and profile)`) before `write_moves`. Alternatively, `Assign` forbids empty profile names.
2. **In `--list`, a stale exemption move is marked `[no assign entry]`** (cli.py diff:106-108).
   - For a `missing` package the delivered profile is unknown, so the row approximates `target_problem` with `target not in config.assign.profiles`. A recorded `--delivered` exemption to an unassigned delivered profile (e.g. `funk`) whose package is gone shows `southern`-style `funk (from ?)  missing  [no assign entry]`, although that move would be valid once its package returns.
   - This is also a partial re-implementation of `target_problem`'s logic.
   - Untested: no test covers a `missing` row with an unassigned target.
   - Consider suppressing the marker on `missing` rows, since use-time validation cannot be evaluated without a package.
3. **`unchanged` does not refresh the informational `package` name** (moves.py `record_move`). If the package directory was renamed, the identical move returns False and `--list` keeps the old name. This is cosmetic, because resolution uses the key only (spec §3).
4. **`except Exception` around the post-write `assess`** (cli.py diff:187-192) catches programming errors as well as `EmceeError`/`OSError`. Exit 0 is defensible, because the write has already happened and the error is printed via `_typed_error`. Narrowing it to `(EmceeError, OSError)` would make a real bug surface as a traceback.
5. **The usage-error test checks only the exit code** (test diff:460-464). It does not assert that `moves.json` is absent afterwards. The code exits before `load_config`, so there is no risk today.

### Assessment

**Task quality:** Approved

**Reasoning:**
- The implementation is the brief's code verbatim and meets spec §3 in full.
- Strict surface 2 is enforced before every write or read on all three forms, and tests pin the missing-file guard and the bad-file refusal for each form.
- The one writer/reader mismatch (empty-string profile key) is a contrived-config edge with a loud failure, recorded as Minor with a one-line fix.
