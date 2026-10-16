### Spec Compliance

- ✅ Spec compliant. The diff matches the brief's Step 3 code word for word: `_profile_cell` (cli.py:725-734), the four new `_status_json_row` keys (cli.py:742-746), the `status_cmd` tail rebuilt as one `if/elif` chain that always reaches the stale note (cli.py:858-884), and the replacement docstring (cli.py:824-836). The test file matches Step 1 exactly (packages/emcee/tests/test_status_profiles.py:1-119). Spec §1 (effective profile in the summary, `--profile`, `--list` and `--json`; `delivered_profile` and `profile_source` in JSON; the `(from …)` mark), §3 (`[no assign entry]`, the stale note) and §4 (`tts` in `--json` only) are all covered.
- ⚠️ Cannot verify from the diff: the check of strict surface 3 against the real station is a manual step after this task, and stays with the controller. My code reading (below) found nothing in this diff that could change state.

### Checks run (named risk → what I checked)

- **Strict surface 3: does `status` output or state move for packages with no rules and no moves?** This diff does not touch state or reasons; it only changes how rows are shown. The profile cell `profile_label(s.profile)` (station.py:99-100) prints the same text as the old `s.profile or '(none)'`, because `manifest_profile` already turns `""` into None (station.py:54). Each row's `(from …)` mark needs `profile != delivered_profile`, which cannot happen when `profile_source == "llama"`. The `--list` table, the summary and the stdout of `--json` are therefore unchanged for these packages, apart from the new JSON keys, which only add to each row. With no moves there is no stale note.
- **Stale count taken before filtering:** `_stale_moves(moves, statuses)` runs on the full scan (cli.py:847), before the `--profile`/`--state` filters at cli.py:854-857. A filtered view therefore cannot report false stale moves. Unsupported and error rows still carry `performance_id` (station.py:286, 311), so a broken manifest does not make its move look stale.
- **Does `[no assign entry]` mislabel some other `move_problem`?** No. `move_problem` comes only from `target_problem` (station.py:169-175), whose one message is the no-entry text.
- **Can the `tts` JSON value fail to serialize?** No. `manifest_tts` returns a dict or None (station.py:141-144).
- **Unsupported rows:** `profile_source` is None (station.py:305-311), so they get no `(from …)` mark, which is correct.
- **Focused run:** `test_status_profiles.py` plus `test_status_cmd.py` gave 31 passed with no warnings (I confirmed `emcee` imports from the worktree first).

### Strengths

- Moving the early `return`s into one `if/elif` chain guarantees that every output branch ends with the stale note, including `--json` and "no packages", and the note goes to stderr. `test_status_notes_stale_moves_on_stderr` (test_status_profiles.py:89-101) pins that stdout stays pure JSON.
- The column width is now taken from the rendered cells (`pwidth = max(len(p) for p in profiles)`), so longer marked cells still line up.
- The tests cover the shared-`performance_id` case (test_status_profiles.py:104-119) and check both `status` and `move --list`, which closes Review Focus 5.
- `test_profile_filter_follows_a_move` checks both sides of a move: the package shows under the new profile, and filtering by the old profile gives "no packages match" plus the stderr note.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
- packages/emcee/tests/test_status_profiles.py:4: `from pathlib import Path` is never used. The brief's test code includes it (plan-mandated), but it is lint noise. Remove it.
- No test covers how an `unsupported` or `error` row's profile cell looks under a rule or a move (`profile_source` is None, so no mark appears). The logic is trivial and correct by reading; this is a coverage gap only.

### Assessment

**Task quality:** Approved

**Reasoning:** The change follows the brief exactly and only adds display fields. State computation is untouched, and for packages with no rules or moves the table and summary text are unchanged, so strict surface 3 is not put at risk by this diff. The stale note is computed before filtering and goes to stderr on every output path.
