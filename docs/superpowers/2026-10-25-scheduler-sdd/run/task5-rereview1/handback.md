# task5-rereview1: re-review of the task 5 fix round (684d323..0afcb9a)

### Finding Verdicts

1. **ADDRESSED.** `test_announcements_live_clock_writes_no_last_good_copy` (packages/transmitter/tests_transmitter/test_cli.py:295) runs without `--clock`, with the clock at `<TRANSMITTER_ROOT>/clock.toml`. It asserts the listing and that `clock.last-good.toml` does not exist. `test_announcements_invalid_live_clock_notes_and_writes_no_copy` (:304) checks the `note:` path. Mutation (scratch): `save=False`→`save=True` at cli.py:280 is killed by the predicted test (`assert not True` at test_cli.py:301). Removing the `note: {lc.problem}` echo is killed by the invalid-clock test as predicted.
2. **ADDRESSED.** The `InterstitialsConfig.dir` field_validator (config.py:123-129) rejects a relative path. That fails `load_config` with a ConfigError matching "absolute" (test_config.py:108) and is also checked at model level (test_interstitials.py:92). `test_template_parses_to_the_defaults` stays green, since the template example is absolute and commented out. Mutation: disabling the validator turns both new tests red.
3. **ADDRESSED (by the "or report what was done" branch, not the one-stat ask).** `scan` now does two stats per clip (interstitials.py:53-56), down from three. The first stat covers `S_ISREG`, the size-0 check and quiet. `station.file_set_key_and_sizes` then stats again for the key and sizes. The implementer reported this. The meta `sizes` now comes from the same stat as the key, so the two are consistent. A residual race exists and is Minor; see Out-of-Scope.
4. **ADDRESSED.** All four new tests kill their mutants in a scratch copy. Each expected red test was named before its run.
   - Changing the per-file `continue` to `break`: `test_oserror_on_one_file_skips_only_that_file` goes red (`[] == ['id-b']`).
   - Narrowing `except OSError` to `except ValueError`, so the skip is gone: the same test goes red (OSError propagates).
   - Removing the `S_ISREG` check: `test_a_directory_named_like_a_clip_is_skipped` goes red (`['id-x','id-y']`).
   - Removing the `x.nominal_us >= until` bound: `test_needed_excludes_occurrences_at_or_after_the_span_end` goes red.
   - Changing `>=` to `>`: the same test also goes red, so float→int rounding of `until` does not mask the boundary.
   - `test_announcements_bad_clock_file_exits_1` is present (test_cli.py:313) and green.
5. **ADDRESSED.** cli.py:286-288 prints exactly one stderr `note: no interstitials folder (...)` when the folder is None or not a directory. `scan()` is unchanged and stays quiet. Mutation: replacing the condition with `False` turns `test_announcements_notes_a_missing_interstitials_folder` red.

Constraint check: the diff does not touch announcement texts, `ann_id` or `needed()` (announce.py has no source change; only a test was added).

Mutation method: `git archive 0afcb9a packages/transmitter antenna/templates` into a scratchpad copy, run from an empty cwd. Command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<scratch>/packages/transmitter/src:<scratch>/packages/transmitter .venv/bin/python -B -m pytest -p no:cacheprovider`. Before any run, `transmitter.__file__` and `tests_transmitter.__file__` were shown to resolve inside the scratch copy. Each mutant was applied to the pristine file and restored afterwards. Scratch baseline: 662 passed, 1 skipped, 1 failed. The failure is `test_relay_key_matches_antenna`, which reads `antenna/src/alerts.ts`; that file is not in the archive, so the failure belongs to the scratch copy, not the code.

### New Breakage in the Fix Diff

None at Critical or Important level. Minor:
- test_cli.py:309: the invalid-live-clock assertion `"note: " in output and "clock" in output` is loose. It kills the mutant today only because the folder note's text (and the truncated pytest tmp path) happen not to contain "clock". A tighter pin would be `"note: invalid clock" in output` or the clock path. It is not wrong today.
- The not-a-directory branch of finding 5 (station root set, folder missing) runs in the other live-clock tests, but no test asserts it. A mutant reducing the condition to `if folder is None:` would likely survive. I did not run that mutant.

### Out-of-Scope Observations

- The two-stat `scan` has a small window: the quiet, size and regular-file check comes from stat 1, while the key and sizes come from stat 2. A file rewritten between the two could be keyed on a newer, not-yet-quiet mtime or size. The effect is self-healing, because the key changes again on the next scan, and transmitter still only reads the folder. Minor; this follows the shape the implementer reported.
- `dir = "~/..."` is now rejected as relative because it is not expanded. That is consistent with the ruling; mentioned for awareness.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
