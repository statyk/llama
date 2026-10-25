# t19-impl handback: Task 19, `rekey_overrides --apply`

**Status: DONE_WITH_CONCERNS.** The concerns are calls made beyond the brief. All of them lean toward refusing. They are listed below.

**Commit:** `a65daf5 feat(scripts): rekey_overrides --apply`, on top of 73a0f61.

**Files changed:** `scripts/rekey_overrides.py` (+388), `scripts/test_rekey_overrides.py` (+558).

## What was built, against each contract item

### `llama_versions()`
- Runs `which -a llama`. Exit 0 or 1 is fine; any other exit raises OSError. Duplicate paths are removed and PATH order is kept.
- Then runs `<path> --version` for each path (120 s timeout) and returns `(path, stdout.strip())`.
- A binary that fails returns `exit <n>: <output>`; one that cannot be run returns `error: <Type>: <msg>`. `version_ok` refuses both forms.
- `which` finding nothing returns `[]`.

### `version_ok(text)`
- The stripped text must fully match `[0-9]+(\.[0-9]+)+`.
- The comparison is numeric, with the shorter version padded with zeros, so 2.9.0 is below 2.18.0 and 10.0.0 passes.
- These all refuse: `0.1.0`, `0.0.0+unknown`, `2.18.0rc1`, `2.18.0+dirty`, `v2.18.0`, `llama 2.18.0`, multi-line output, a bare `2`, and full-width digits.

### Gates, in order
Each gate refuses with nothing written and before the lock is taken.
1. **Snapshot.** `find_snapshot` must find one, else `no verified snapshot: no rekey-snapshot-* directory holding manifest.json under <root> (runbook step 4)`. If `verify_snapshot` reports problems: `no verified snapshot: <snap>: <problems>`.
2. **Version.** `no llama on PATH`; `llama on PATH below 2.18.0: <path> <out>` for each low binary; or `version check failed: ...`. Each good binary is echoed as `llama on PATH: <path> <out>`.
3. **Process check.** This reuses Task 18's `_process_gate`, which prints `llama processes running:` followed by the indented lines.

### Lock and up-front checks
- `<root>/.rekey.lock` is taken non-blocking; if it is held, the run refuses.
- Under the lock, these refuse with nothing written:
  - `find_snapshot` must still return the same snapshot.
  - `rekey-applied.json` is read (see the calls below).
  - `check_library` runs.
  - Coverage gate: every `library_shows(root)` slug must be among the manifest's slugs. Otherwise the refusal is `not in the snapshot (created after <snap>)`.
  - For each legacy show the snapshot covers, `overrides.json` and `show.json` are compared by sha256 against the manifest entry and against the snapshot copy file. A mismatch refuses as `changed since the snapshot (<file>: sha256 X now, Y in <snap>)`. A missing copy, or a file missing now, also fails.
- Any refusal: every refusal is printed, then `<n> to rekey, <n> refused, <n> already migrated, <n> without positional keys`, then `nothing written`. Exit 1.

### Per legacy show, sorted, under `file_lock(ws.lock)` (`_rekey_show`)
1. **Re-check.**
   - Read the bytes of both files.
   - Compare them with the snapshot as above.
   - Run `check_show(ws, ia, want, overrides_bytes=…, show_bytes=…)` on exactly those bytes. A result of `None` refuses.
2. **Map.** `rekey_raw(json.loads(ov_bytes), [t.filename for t in show.tracks])`. Then a round-trip check (see the calls below).
3. **Write.** `json.dumps(data, indent=2)` goes to `.overrides.json.rekey.tmp` in the show dir (`_write_copy`: O_EXCL plus `_sync_fd`). Then `os.replace`, then `_sync_dir` on the show dir.
4. **Record.** `rekey-applied.json` gets `{"snapshot", "updated_at" (UTC ISO), "shows": [...]}`, written the same durable way. Then `rekeyed: <slug> (T titles, B breaks[, encore])` is printed.
- A refusal at step 1 or 2 prints it and `stopped: <n> legacy show(s) after it not reached`. The summary follows and the exit is 1.
- An exception prints `error: <slug>: <Type>: <msg>` and a re-run hint. The exit is 1. KeyboardInterrupt propagates.

### Refusal routes
Each refusal is printed as these lines:
- `refused: <slug>: <reason> (<detail>)`.
- `  first: run --restore <snap path> with the new binary, then reinstall v2.17.0`, printed only when some show directory's `overrides.json` classifies `filename`.
- `  then: reinstall v2.17.0, repair <slug> with it (route below), then return to step 2 (dry run) and take a NEW snapshot`.
- `  repair: <route>`, with `<show>` replaced by the slug.

### Output and `main`
- Success ends with `<n> rekeyed, <n> refused, <n> already migrated, <n> without positional keys`.
- `main` has a new `--apply`, mutually exclusive with `--snapshot`, which calls `apply(config.root, ia, want, echo=print)`.
- The module docstring has an `--apply` paragraph.

### Carried decisions
- `rekey_raw` is called on the raw JSON, with no copy of its logic.
- The duplicate-key refusal stays in `check_show`, which runs before `rekey_raw`.
- `check_show` gets both byte arguments.
- Coverage uses `library_shows`.
- Lock order is `.rekey.lock` first, then the show lock.
- Tests monkeypatch `llama_versions` and `_ps_lines` in the autouse fixture. `test_llama_versions_reads_every_llama_on_path` exercises the real function against fake `llama` scripts on a tmp PATH.

## Calls beyond the brief (all lean toward refusing)
1. **Coverage gate over every library show.** A show missing from the snapshot refuses even if it has no legacy value. The brief only required a byte comparison for legacy shows. Following the carried decision, the gate runs over every `library_shows(root)` slug. Such a show means something ran between steps 4 and 6, and `--restore` would refuse it later.
2. **New reasons** in `APPLY_REASONS`, kept separate so that `REASONS` stays verbatim from the spec table:
   - `not in the snapshot` and `changed since the snapshot`. Their route is "nothing in the show itself: the NEW snapshot records it as it is now, and the dry run re-checks it".
   - `rekey does not round-trip`. Its route is "a defect in the migration; report it".
3. **Round-trip check before writing.** `resolve_positions(Overrides.model_validate(data), names)` must give exactly the legacy positions, and the key order and every non-positional key must be unchanged. If not, the show is refused and nothing is written for it.
4. **`rekey-applied.json` validation.**
   - An unreadable record refuses.
   - A record naming a snapshot other than the newest refuses. A successful `--restore` renames the record (Task 20), so a mismatch is unexplained.
   - The newest snapshot is re-checked under the lock: a newer one appearing between the gate and the lock refuses.
5. **Interrupted-run reconcile.** This is what lets `test_interrupted_apply_continues` "list all" when the crash falls between the rename and the record.
   - A show is added to the record (`recorded: <slug> (rewritten by an interrupted --apply)`) only when all of these hold:
     - its file is filename-form and not in the record;
     - its snapshot copy is legacy and matches the manifest;
     - its current bytes equal exactly what `--apply` writes from the snapshot's `overrides.json` and `show.json`.
   - Any other filename-form file is neither recorded, refused nor rewritten.
   - The reconcile writes only after the up-front checks pass.
   - Refusing on such files would have printed `--restore` advice on a harmless re-run after a complete apply, and `--restore` discards every later edit.
6. **When a record is written.** It is written only when a show is rewritten or reconciled. A run with nothing to rekey leaves no record.
7. **Gates short-circuit** in order, as with `--snapshot`. The first gate that fails is the only one printed.

## Step-1 tests (`scripts/test_rekey_overrides.py`)
Every refusal test asserts `helpers.tree_bytes(root)` unchanged.

**From the brief:**
- `test_apply_refuses_without_a_snapshot`.
- `test_apply_refuses_a_snapshot_with_a_deleted_or_changed_file`: deleted, changed, and no-manifest cases.
- `test_apply_refuses_a_show_the_snapshot_does_not_cover`: covers a show created after the snapshot, an `overrides.json` re-serialised since, and a `show.json` re-serialised since. The consistent show is not rekeyed and no `--restore` line is printed.
- `test_apply_refuses_a_low_or_dev_or_missing_llama`: `2.17.0`, `0.1.0`, `0.0.0+unknown`, `[]`, and one good plus one low.
- `test_apply_refuses_while_llama_runs`: also covers a failed ps.
- `test_apply_writes_nothing_when_any_show_would_be_refused`: checks the exact then/repair lines and that no `--restore` line is printed.
- `test_apply_rekeys_and_records`: checks the bytes equal `json.dumps(rekey_raw(old, F), indent=2)` and checks the record. A later `library_show` re-gather of each fixture keeps the same titles, sources, sets and breaks on the same files.
- `test_unknown_keys_survive_the_raw_rewrite`: checks the order of keys and values.
- `test_edit_after_the_snapshot_refuses_under_the_lock`: parametrised over `overrides.json` and `show.json`. The first show is rekeyed, the second refused with the `first:` line first, and the third is untouched.
- `test_interrupted_apply_continues`: `_write_record` raises after the first rename. The re-run records, rekeys the rest, and lists all three.
- `test_apply_after_a_restore_starts_a_fresh_record`: Task 20's restore is not built, so `_hand_restore` copies the snapshot back and renames the record to the plan's `rekey-applied.restored-<stamp>.json`. Task 20 should switch the test to the real `--restore`.
- `test_apply_output_and_exit_codes`.
- `test_lock_only_show_dir_is_not_a_show` is extended: `--apply` exits 0, rekeys the show and ignores the husk.

**Added:**
- `test_version_ok`.
- `test_llama_versions_reads_every_llama_on_path`.
- `test_apply_uses_the_newest_snapshot`.
- `test_apply_refuses_a_failed_version_check`.
- `test_a_held_migration_lock_refuses_the_apply`.
- `test_a_check_failing_under_the_lock_refuses_and_stops`: the metadata changes after the up-front pass.
- `test_interrupted_after_the_record_continues`.
- `test_a_record_of_another_snapshot_refuses`: also covers an unreadable record.
- `test_a_rekey_that_does_not_round_trip_is_refused`.
- `test_a_migrated_show_apply_did_not_write_is_not_recorded`.

## RED / GREEN
- **RED.** `./.venv/bin/python -m pytest scripts/test_rekey_overrides.py -q -p no:cacheprovider` gave `28 failed, 53 passed`: `SystemExit: 2` ×21 (argparse does not know `--apply`), and AttributeError for `_rekey_show` ×4, `llama_versions`, `_write_record` and `version_ok`. The first RED attempt errored all 81 tests, because the autouse `setattr` of a missing attribute raised. It was re-run with `raising=False` to get a clean RED, then restored to the default `raising=True`.
- **GREEN.** The same command gave `83 passed`.
- **Full suite.** `./.venv/bin/python -m pytest -q` gave **`5359 passed, 1 skipped, 8 deselected, 26 warnings in 47.09s`**. The baseline was 5330, plus 29 new tests. Exit code 0.
- `llama.__file__` resolves inside the worktree.

## Mutation check
- Run in a scratch copy: `git archive` plus the two changed files, from the scratchpad cwd, with `python -m pytest`, PYTHONPATH shadowing and a bytecode prefix per mutant.
- Shadowing was proven by printing `llama.__file__` and `rekey_overrides.__file__`. Both pointed into the copy.
- The M0 sentinel (`REKEY_MIN_VERSION = "9.0.0"`) turned 22 tests red.
- All 16 mutants were CAUGHT by the test I named before running each one:

| Mutant | Predicted red test |
|---|---|
| M1 lexical version comparison | `test_version_ok` |
| M2 no under-lock comparison | `edit_after…` (both cases) |
| M3 no up-front comparison | `does_not_cover` |
| M4 coverage over `_show_dirs` | `lock_only…` |
| M5 no `check_show` under the lock | `a_check_failing_under_the_lock` |
| M6 no reconcile | `interrupted_apply_continues` |
| M7 record snapshot mismatch ignored | `a_record_of_another_snapshot` |
| M8 no version gate | `low_or_dev…` ×5, `failed_version_check` |
| M9 empty PATH passes | `[none]` |
| M10 `first:` line always printed | `writes_nothing…` |
| M11 no round-trip check | `does_not_round_trip` |
| M12 snapshot verify ignored | `deleted_or_changed`, `newest_snapshot` |
| M13 reconcile any filename show | `migrated_show_apply_did_not_write` |
| M14 no process gate | `while_llama_runs` |
| M15 up-front refusals do not stop | `writes_nothing…` |
| M16 no per-show record | `rekeys_and_records` |

The full lines are in `t19-impl.log`.

## Concerns
- **Byte arguments not pinned.** No test pins that `check_show` under the lock judges the bytes it was given rather than the files. The only way to tell the difference is a write landing between the read and the check, both under the show lock. The code passes both byte arguments, and Task 17's `test_check_show_judges_the_bytes_it_is_given` pins `check_show` itself.
- **Restore test uses a hand stand-in.** `test_apply_after_a_restore_starts_a_fresh_record` relies on `_hand_restore` until Task 20 exists.
- **One gate shown at a time.** Short-circuiting means the operator sees only the first failing gate per run.
- **Live library untouched.** Nothing touched `~/.llama` or the station. Every fixture is under `tmp_path`.
