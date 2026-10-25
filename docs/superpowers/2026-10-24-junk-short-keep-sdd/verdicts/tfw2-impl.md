# tfw2-impl: FW2 (final review fix-wave items 3-15, additions A-C)

Branch held-backlog-junk-filter, worktree /Users/shawn/projects/llama/.claude/worktrees/junk-filter, base 1bcccd1, HEAD 65be006. `llama.__file__` resolves inside the worktree. Log: `$D/tfw2-impl/tfw2-impl.log` (every RED/GREEN run, the suite runs, the gate re-measure, the library measure and the mutants are teed there).

**Status: DONE.** All items built. None BLOCKED or NEEDS_CONTEXT.

## Commits (5, each with the full suite green at that state)

| commit | items | full suite |
|---|---|---|
| 8482a9f fix(replay): the briefing-reuse gate refuses more | 3, 4, 5, 15 | 5425 passed, 1 skipped, 8 deselected |
| 5704966 fix(deliver): batch wording for the voiced refusal | 6 | 5426 passed |
| e08c4dd fix(rekey): restore refuses another snapshot; flush the root; pins | 7, 8, 9, 11, 12, 13 | 5434 passed |
| b57a790 fix(probe): repro never passes on nothing; junk rule pins | 10, 14 | 5439 passed |
| 65be006 fix(junk): an excluded duplicate counts once; an included copy wins | A, B, C | **5442 passed, 1 skipped, 8 deselected** |

I took each group's diff into a scratchpad patch and re-applied the groups one at a time, so each commit's state is the state that suite run tested. The command was `./.venv/bin/python -m pytest -q -p no:cacheprovider`, in the background, with rc files in `$D/tfw2-impl/`. The baseline was 5394; the 48 new tests make 5442.

## Items

### 3. (must) 15b N1: apostrophe glue, including `’` (m-2)
- **Change:** `replay._normalised` now returns a third copy, `" ".join(_TOKEN_SPLIT.findall(folded))`. Here `_TOKEN_SPLIT = \w+`, so every apostrophe is a separator in that copy. The fold runs first, because `ʼ` is a word character until it is folded. Every normalised term already fires on any copy, so this only adds readings. The comment block above `_NEG` is updated to say so.
- **Tests:** `test_replay.py::test_fw2_absence_wording_refuses`, 9 cases:
  - glued forms that now refuse: `not‘listed’`, `not’listed`, ``not`listed` ``, `not´listed`, `notʼlisted`, `not′listed`, `not‘included`;
  - forms that refused before and still do: `isn´t listed`, `isn't listed`.
- **RED:** 7 failed on 1bcccd1, exactly the glued forms; the two `isn…t` cases passed.
- **GREEN:** passes.

### 4. (must) `too` / `implausibl[ey]` with up to 2 words before `short`
- **Change:** the normalised patterns are now `\btoo{_window(2)}short\b` and `\bimplausibl[ey]{_window(2)}short\b`. The raw patterns are unchanged, and the names and positions are kept.
- **Tests:** in the same parametrized test: "too very short", "too, frankly, short", "implausibly, very short", "implausible and short".
- **RED:** 4 failed. **GREEN:** passes.

### 5. (must) the measured vocabulary
Four terms, appended last so no earlier first hit moves. Each comment carries the t15b-rr5 corpus count:

| term | pattern | t15b-rr5 count |
|---|---|---|
| `lacks` | raw `\black(?:s\|ed\|ing)?\b` | 57 spans / 50 rows; 6 / 6 with a data subject |
| `not recorded` | `_NEG` + window 3 + `recorded` | 10 spans / 9 rows |
| `cut from the recording` | `cuts?` + window 2 + `from\|off\|out` + window 3 + tape/recording/data/listing/list/file/show | 5 rows |
| `lists no` | data subject (data, tape, recording, list, listing, tracklist, setlist, track, file, page, description, notes, fm) + window 2 + `list(s\|ed)\|contain(s\|ed)` + window 1 + `no` | 100 spans / 96 rows with a data subject, excluding "flags" |

Tests:
- `test_fw2_measured_vocabulary_refuses` (9 short sentences, exact first-hit reason).
- `test_fw2_corpus_sentences_fire_their_term`: the verbatim corpus sentences, slug in each id. These are belafleckandtheflecktones-1995-08-25, brotherspast-2006-11-17, hayescarll-2006-01-21, greenskybluegrass-2010-03-26 and billystrings-2017-08-29. The test asserts the term is among `_restored_mentions`' hits. The full corpus sentences open with "first two songs", which `track count` takes first.
- `test_fw2_the_new_terms_come_last`.

**RED:** all 15 failed. **GREEN:** passes.

### 6. (must) Task 16 Minor 6: batch wording
- **Change:** the voiced refusal is now `cli._VoicedDestination(LlamaError)`. Its `str()` is the single-name text, byte-identical. `_deliver_batch` catches it ahead of `LlamaError` and prints `batch_text()` instead: `... re-delivering would un-voice it (re-deliver it by name with --replace-voiced to replace it with a fresh, unvoiced copy)`.
- **Why not a parameter:** I first added an `in_batch=` keyword to `_deliver_one`. Four existing tests stub `_deliver_one` with a fixed signature, so they failed. I reverted that rather than edit those tests (see the log, "GREEN items 6, 10": 4 failed, then the exception form: 196 passed). `_deliver_one`'s signature is unchanged.
- **Test:** `test_deliver_cmd.py::test_batch_voiced_refusal_names_the_single_name_route`. It asserts the batch wording, no `(pass --replace-voiced`, and the voiced copy untouched. The single-name test `test_redeliver_over_voiced_is_refused_and_changes_nothing` is unchanged and passes.
- **RED:** failed. **GREEN:** passes.

### 7. (must, **pin**) `first: run --restore` on the up-front path after an interrupted run
- **Test:** `test_rekey_overrides.py::test_first_restore_line_on_the_up_front_refusal_after_an_interrupted_run`.
  - `_write_record` is made to fail, so S1 is rewritten and left unrecorded.
  - `_drop_first_file` then makes S2 and S3 refuse up front.
  - The re-run shows each refusal block with `FIRST`, then `THEN`. The last line is `nothing written`, there is no `recorded:` line, and `tree_bytes(root)` is unchanged.
- **RED:** none; it passed on 1bcccd1 (pin).

### 8. (must, **pin**) `check_show`'s byte arguments under the lock
- **Test:** `test_check_show_under_the_lock_judges_the_bytes_read_there`. It spies on `rk.check_show` only while inside `_rekey_show`. Calls go to S1, S2 and S3, and each gets non-None `overrides_bytes` and `show_bytes` equal to the files' bytes. Passes on 1bcccd1 (pin).

### 9. (must) a listing failure in `--restore` repeated before `next:`
- **Change:**
  - `_print_not_reverted` now returns its listing-failure warnings. These cover the reapply and runs listings (`_created_since`) and the station listing.
  - `_restore_locked` echoes them again after the record rename and just before `next:`.
  - The exit code stays 0, since the restore itself succeeded. The repetition is the chosen form of "and/or".
- **Test:** `test_restore_repeats_a_listing_failure_before_next`. The `delivery_path` is a file and `runs/` is chmod 0. Each warning appears exactly twice, and the last three lines are `[runs warning, station warning, NEXT]`.
- **RED:** failed (count 1). **GREEN:** passes.

### 10. T7, `repro`
- **Change:** `short_keep_probe.repro` refuses with exit 1 when either arm has no replayable row, or when the arms' top-level `root` differ (an arm without a key counts as None). It compares nothing.
- **Deliberate choice:** `repro.md` is still written, holding only `refused: ...` lines, so a stale passing report from an earlier run cannot outlive the refusal. The module docstring is updated.
- **Tests:**
  - `test_repro_refuses_two_empty_arms`;
  - `test_repro_refuses_an_arm_with_no_replayable_row`;
  - `test_repro_refuses_arms_from_different_roots`: different roots refuse, one root missing refuses, equal roots pass.
- **RED:** 3 failed (rc 0). **GREEN:** passes.

### 11. T18: `_sync_dir(root)` after the snapshot manifest rename
- **Change:** one line after `_sync_dir(snap)` in `_take_snapshot`.
- **Test:** `test_snapshot_flushes_the_root_after_its_manifest`. The spy records whether `<snap>/manifest.json` exists at each `_sync_dir(root)` call; the last call must see it.
- **RED:** failed (no root sync at all). **GREEN:** passes.

### 12. T20: restore against the wrong snapshot
- **Change:** a new `_record_gate(root, snap)`, run in `restore`'s pre-lock gates and again under the migration lock. When `rekey-applied.json` exists and its `snapshot` is not `snap.name`, it refuses with "refusing to restore: … records the shows as rewritten from snapshot X, not Y; restore from <root>/X (nothing written)". With no record (none taken, or renamed by a restore) there is no check. The module and `restore` docstrings are updated.
- **Beyond the letter:** an unreadable record (bad JSON, or no string `snapshot`) also refuses, writing nothing. On surface (a) that is the conservative reading.
- **Test:** `test_restore_refuses_a_snapshot_the_applied_record_does_not_name`.
  - Two snapshots, apply from the newer, restore with the older: rc 1, the line names both, no `restored:` line, `tree_bytes(root)` byte-identical.
  - An unreadable record is likewise refused with nothing written.
  - Restoring from the named snapshot then succeeds.
- **RED:** failed. **GREEN:** passes.

### 13. T20: restore's untested branches (all **pins**, each passed on 1bcccd1)
Each test asserts the stop line, `stopped: 1 show(s) after it not reached`, and that nothing is printed after it. It also asserts that S3 is byte-untouched and still migrated, that the record is not renamed, and that no restored-record file exists.
- `test_restore_stops_at_a_directory_where_the_snapshot_holds_a_file`: S2's `show.json` is replaced by a directory, and its contents survive.
- `test_restore_stops_at_a_link_on_the_way_to_a_copy`: S2's snapshotted `extra/` subdirectory is replaced by a symlink out of the show dir. `_check_inside` refuses, nothing is written through the link, and the outside directory is unchanged.
- `test_restore_stops_at_a_record_rename_collision`: `_restore_record_name` is pinned, and that file already exists. Every show is restored. The last line is the `error: renaming …` stop, with no `next:` and no `renamed:` line, and both files are unchanged.

### 14. T10 pins (`test_short_keep_rule.py`, both **pins**)
- `test_a_one_second_tagged_file_is_kept`: with `short_keep=False` the 1 s file's reasons are exactly `["implausibly short"]`. With the rule it is kept, `excluded == []` and `short_kept` names it.
- `test_a_call_sign_wrap_up_drops_as_non_performance`: `short_tag_is_junk("KBFH Wrap-Up")` is True, and through `filter_files` the file stays excluded with `["implausibly short"]`.

### 15. T11 pins (`test_replay.py`)
- `test_reuse_refuses_when_a_non_short_filename_differs` returns `"tracks differ"`.
- `test_a_none_break_key_on_both_sides_reuses` (pin): a break after a short-kept first track keys None on both sides, and the briefing is reused.
- `test_a_none_break_key_against_a_real_one_forces_a_brief` (pin): a break keyed None against one keyed `a.mp3`, both ways round, gives `broadcast fields changed: set_breaks`.
- All passed on 1bcccd1, as pins. The "tracks differ" test kills the mutant the review named. That was not separately mutated here.

### A. N-1: an excluded duplicate double-counted in the format choice
- **Change:**
  - `_kept_running_time(kept, avoid)` leaves out an avoided (operator-excluded) derivative whose `original` a non-avoided kept derivative also carries. Every other excluded file still counts, per the ruling.
  - `_choose_format` passes `avoid`, and its docstring says so.
- **Tests (`test_format_choice_and_derivatives.py`):**
  - `test_an_excluded_duplicate_copy_does_not_double_its_formats_time`. A `Flac` derivative format has one doubled pair and the `24bit Flac` originals sit beside it, with `want=("24bit Flac", "Flac")`. With either copy excluded the choice is the same as with no exclude (`24bit Flac`, a tie broken by order). Before the fix, `Flac` won on 2400 s against 2100 s.
  - `test_an_excluded_single_copy_still_counts_toward_its_format` (pin): a non-duplicate exclude does not move the format.
- **RED:** 1 failed. **GREEN:** passes.

### B. N-2: an included copy wins the copy choice
- **Change:**
  - `_derivative_preference(f, prefer)` now has a first key, `name not in prefer`.
  - `_dedupe_derivatives(kept, avoid, prefer)`, `_choose_format(..., prefer)`, and `filter_files` pass `readmit` (`overrides.include`) through.
  - When both copies are included, one still drops and `include` re-admits it. So "no exclusion reason is refused" still holds.
  - The `PREFER_VBR_DERIVATIVE` comment is corrected. The flip is one line because excluded copies never win and included copies always win. It also records the sci case it used to break.
- **Tests:**
  - `test_sci_ships_the_same_songs_at_either_preference` now asserts 25 origins, **each once**, at both values, with every `SCI_INCLUDE` file shipped.
  - New `test_an_included_copy_wins_the_copy_choice`, at both preference values.
  - `test_include_re_admits_a_dropped_duplicate` now includes both copies.
- **RED:** 2 failed (the sci test gave 30 against 25 at `True`; the one-copy include left both copies kept). **GREEN:** passes.
- `short_keep=False` is untouched: the legacy arm never calls `_choose_format`, and the v2.17.0 oracle tests pass.

### C. m-1: the two comment lines
- FW1's docstrings already covered both rules. I added one line at the decision in `_choose_format` ("The rule (I-1): the greatest kept running time wins; never 'first non-empty'"). I added another at `back = tagged_keep + untagged_keep` in `_apply_short_rule`, saying both derivatives may come back there and filter_files keeps one (`_dedupe_derivatives`, I-2).

## Changed pre-existing expectations (every one, tied to its item)
1. `scripts/test_short_keep_probe.py::test_repro_treats_equal_unreplayable_as_equal`: each arm gains one replayable row `"r"`. An all-unreplayable arm is now refused by item 10. The equal-unreplayable and differing-unreplayable assertions are otherwise unchanged.
2. `packages/llama/tests/test_format_choice_and_derivatives.py::test_sci_ships_the_same_songs_at_either_preference`: `len(origins) == 25` is now asserted at both preference values (it was only at False), and the docstring's "five ship twice" is gone. This is ruling B, pinned as instructed.
3. `packages/llama/tests/test_format_choice_and_derivatives.py::test_include_re_admits_a_dropped_duplicate`: it now includes BOTH copies. Under B, an include of only `x1t03_vbr.mp3` makes that copy the kept one, so nothing is dropped and nothing is re-admitted; the song ships once. The one-copy case moved to the new `test_an_included_copy_wins_the_copy_choice`.

No other existing test was edited. The single-name voiced-refusal tests are untouched (m-3).

## Gate re-measure (read-only, `~/.llama-harness/piece4/ckb/15a/dump.jsonl`; output `~/.llama-harness/piece4/fw2/gate_{base,fw2}.json`)
- 1bcccd1, in a scratch `git archive` with shadowing proven by `llama.__file__`: refused **1014/1014**, and **901/901** of the reuse arm; reusable 0 and 0.
- FW2 HEAD: refused **1014/1014** and **901/901**; reusable **0** and **0**.
- Row by row, base to FW2: 0 rows lose a term, 0 reasons change, 0 newly reusable.
- New terms' row counts (of 1014 / of 901):

  | term | 1014 | 901 |
  |---|---|---|
  | `lacks` | 50 | 43 |
  | `not recorded` | 17 | 13 |
  | `cut from the recording` | 6 | 5 |
  | `lists no` | 49 | 39 |

  `too short` and `implausibly short` are unchanged, at 55/46 and 788/711.
- Timing: the new patterns and the third copy are linear, about 0.4 s per 1.7 M characters for the worst generator.

## Library measure for A/B (read-only)
- What ran: `final_kept` over the 179 library shows with a non-empty include or exclude, on mp3, at 1bcccd1 and at FW2. Output is in `~/.llama-harness/piece4/fw2/include_{base,fw2}.json`.
- Result: **0 shows change** their final kept list, format or order source.

## Mutation check (scratch `git archive HEAD` per mutant, PYTHONPATH shadow proven, PYTHONDONTWRITEBYTECODE)
9 mutants, each predicted first. Each failed exactly its predicted tests and nothing else:

| mutant | what it breaks | failed |
|---|---|---|
| M1 | no third copy | 7 glued-quote cases |
| M9 | `too` window 0 | 2 cases |
| M2 | `_record_gate` a no-op | item 12 test |
| M5 | no repeat | item 9 test |
| M8 | no root sync | item 11 test |
| M6 | no root check in repro | item 10 roots test |
| M7 | batch wording | item 6 test |
| M3 | running time ignores `avoid` | A test |
| M4 | `prefer` ignored | B tests (2) |

## Concerns
- **One stray write, removed.** My first Write of this report used the main checkout's path (`/Users/shawn/projects/llama/.superpowers/sdd/junk-short-keep/tfw2-impl/handback.md.tmp-unused`, contents "unused"). I removed it, and the two directories it created, at once. `git -C /Users/shawn/projects/llama status` is clean.
- **`lists no` reaches about half 15b's data-subject count.** It is 49 rows, against 15b's 96. 15b's count took any verb before `no` ("has no", "records no set break"), while the brief names `lists/contains` only. A wider verb set would refuse more and is safe; that is the controller's call.
- **The new terms over-refuse, as the stakes accept.** `lacks` is a plain word, so it also refuses "lacking in top end". `not recorded` uses a 3-word window and fires on 17 rows, against 15b's 9.
- **Item 12 goes beyond the letter.** It also refuses an unreadable `rekey-applied.json`. Nothing is written, but a hand-corrupted record now blocks `--restore` until it is repaired.
- **Item 9 keeps exit 0.** The warnings are repeated; there is no distinct exit code.
- **Addition A, followed verbatim, has one latent edge.** When both copies of a pair are excluded, neither shares an original with a non-avoided copy, so both still count (doubled). The song is not shipped at all, and the ruling says not to subtract other excludes. This only matters with two or more formats configured; the library is mp3.
- **Addition B has a narrow behaviour change.** An `include` naming a stale (C-1 class) or `_vbr` copy now ships that copy alone, where it shipped beside the other copy before. Measured: no library show has such an include.
- **Item 10 writes `repro.md` on a refusal**, holding only `refused:` lines, so a stale passing report is overwritten.
- **CLAUDE.md's deliver paragraph** ("a batch confirmation marks or counts the voiced destinations") is still Task 23's, and was not touched here.
