# tfw2-rev2: code review of FW2 (1bcccd1..65be006)

### Spec Compliance

- ✅ **Spec compliant.** Items 3-15 and additions A-C are each present, with the test the brief names. I read the diff in full, in one pass.
  - Items 3-5, 15: replay.py:379-392, 412-415, 437-457; test_replay.py:680-800.
  - Item 6: cli.py:35-51, 78, 100-101 (diff lines); test_deliver_cmd.py:483-500.
  - Items 7-9, 11-13: rekey_overrides.py:912, 934-977, 1011, 1024, 1032-1053, 1077-1084; test_rekey_overrides.py:1195-1410.
  - Item 10: short_keep_probe.py:1135-1167; test_short_keep_probe.py:1437-1471.
  - Item 14: test_short_keep_rule.py:827-851.
  - A, B, C: junk.py:127-128, 153-160, 164-187, 238-251, 280-288, 335; test_format_choice_and_derivatives.py:528-565, 588-612, 628-657.
- **The gate only refuses more (operator ruling).** I checked each change against that rule:
  - The consumer `_restored_mentions` (replay.py:426-429, read outside the diff) fires a term when `any(norm.search(n) for n in nts)`. A third copy can therefore only add hits.
  - Item 4 widens `\btoo short\b` to `\btoo{_window(2)}short\b`. With zero window words that is the old pattern, so it is a strict superset; the same holds for `implausibl[ey]`.
  - Item 5's four terms are appended last. No refusing path was removed or narrowed.
  - The re-measure (1014/1014, 901/901, 0 rows losing a term or changing reason) agrees with this reading.
- **The single-name voiced text is unchanged (m-3).** `_VoicedDestination._text("pass")` reproduces the old f-string character for character. The single-name path at cli.py:2727-2732 (outside the diff) still prints `str(exc)`. No source file matches on the message text: a grep for `pass --replace-voiced` finds only cli.py:2557.
- **Migration refusals write nothing (strict surface a).**
  - `_record_gate` raises `_Refused` before any write, both before and under the migration lock.
  - It mirrors `--apply`'s own `_read_record` (rekey_overrides.py:955-976, outside the diff). Apply refuses any record that names another snapshot. So a mixed-snapshot record cannot arise, and the new gate cannot block the true rollback snapshot. Checked because of a named risk: "does the record's `snapshot` get overwritten by a later apply from a newer snapshot?" It cannot.
- **Junk A/B (strict surface c).**
  - `short_keep=False` is untouched: the legacy branch of `filter_files` has no hunk, and `_choose_format`/`_dedupe_derivatives` run only on the `short_keep` path.
  - A grep of the diff's +/- lines for every Global-Constraint name (`SHORT_FRACTION_OF_MEDIAN`, `MIN_MEDIAN_SAMPLE`, `MIN_PLAUSIBLE_SEC`, `_stem`, `_track_number`, `_dedupe_duplicate_listings`, `FORMAT_BY_AUDIO`, `LOSSLESS_TITLE_FORMATS`, `is_filler`/`_FILLER`, `TAUTOLOGICAL_TITLE_SOURCES`, `clean_tag_title`, `is_real_title`, `_TRACK_NUM_PREFIX`, `DURATION_TOLERANCE_S`, `purge_package_audio`) finds nothing.
  - B drops only a copy that shares its `original` with the kept copy, so it is a duplicate by construction. Play order is still decided as if the dropped copies were present (docstring at junk.py:208-215, unchanged).
- **The three changed pre-existing expectations each trace to their item:**
  - `test_repro_treats_equal_unreplayable_as_equal` gains one replayable row per arm, for item 10.
  - `test_sci_ships_the_same_songs_at_either_preference` now asserts 25 at both values and every `SCI_INCLUDE` file shipped, for ruling B.
  - `test_include_re_admits_a_dropped_duplicate` now includes both copies, for B. The one-copy case moved to `test_an_included_copy_wins_the_copy_choice`.
  - Every other test hunk is additions only.
- ⚠️ **Cannot verify from the diff:**
  - The re-measure outputs (`~/.llama-harness/piece4/fw2/gate_{base,fw2}.json`, `include_{base,fw2}.json`) and the 9-mutant table are the implementer's claims. I did not re-run them.
  - Whether `lossless_titles.apply_lossless`'s stem bijection copes with a delivered `X_vbr.mp3` kept by B is outside this diff. It is a pre-existing class, already reachable through an excluded plain copy, and it needs a library include naming a `_vbr` copy, of which the implementer measured none.

### Strengths

- **Each fix takes the refuse-only form the brief asked for.**
  - The third normalised copy (replay.py:391-392) only adds readings, and the fold runs first, so `ʼ` splits. The comment block (replay.py:367-373) states the invariant.
  - New terms are appended, and `test_fw2_the_new_terms_come_last` pins that.
- **Item 6 avoids touching existing tests.** Using an exception subclass keeps `_deliver_one`'s signature, so the four stubbed tests stay untouched. The implementer tried a keyword first and reverted it rather than edit those tests, which is the right call. `batch_text`/`_text` share one template, so the two wordings cannot drift.
- **`_record_gate` matches apply's own record discipline.** Its refusal message names both snapshots and the route, and it runs twice, before and under the lock, like `_uncovered_gate`.
- **The item-13 helper `_stopped_at_s2` tests what matters.** It asserts that nothing is printed after the stop, that S3 is byte-untouched and still migrated, and that the record is not renamed: the stop-and-touch-nothing property, not just a message.
- **The B comment fix (junk.py:153-160) is now true.** It records the sci case that made the old "nothing else needs to change" false.
- **The pins carry their reasons.** Item 15's None-key tests exercise `break_keys` through the new show's short set on both sides, which matches `briefing_reusable` (replay.py:457-470, read to confirm the test reaches the branch it names). Item 8's spy only records calls made inside `_rekey_show`, and it would fail on a positional call that hides the byte arguments.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. **replay.py:379-380: two unfolded look-alikes still glue `not` to `listed`.** `ʻ` (U+02BB) and `ʹ` (U+02B9) are word characters (Lm), and `_APOSTROPHES` does not fold them, so all three copies keep `notʻlisted` as one word.
   - Checked: `_normalised("the reprise is notʻlisted.")[2] == "the reprise is notʻlisted"` and no term fires. The same holds for `ʹ`. `’` and fullwidth `＇` both refuse (log in `tfw2-rev2.log`).
   - This is outside the brief's letter ("every folded look-alike"), and such characters are implausible in LLM English. But on a gate where a false "reusable" is the forbidden outcome, the fix is free: add them to `_APOSTROPHES`, or make the third copy ASCII-alphanumeric only (`[a-z0-9]+`). Splitting more only adds readings.
2. **junk.py:247-251: a pair whose copies are both excluded still counts twice (the implementer's own flagged edge).** Neither copy's original is "held" by a non-avoided copy, so the format is credited twice for a song it ships zero times. That breaks the docstring invariant ("a format listed twice must not win on its doubled time") in that case.
   - It follows the ruling's letter, and it only matters with two or more formats configured.
   - A count-once variant would honour the ruling's "never subtract a non-duplicate exclude": count the first avoided copy per original when no non-avoided copy holds it. The controller should decide whether the ruling meant that.
3. **short_keep_probe.py:1150: two arms that both lack `root` pass the root check (`None == None`).** Arms written by `replay_holds.run` always carry `root` (replay_holds.py:277, 1304), so this reaches only hand-made arms. Refusing a missing `root` on either side would be stricter.
4. **Item 9 (rekey_overrides.py:1077-1084): the warnings are not repeated when `_rename_record` fails.** In that path the error line is last and there is no `next:`, so the omission is consistent. The exit code stays 0 on a listing failure, which the brief's "and/or" allows. Noted only so the choice is explicit.

Test output: the implementer reports the suite as `5442 passed, 1 skipped, 8 deselected` and lists no warnings. I ran no suite. My only command was a read-only probe with `PYTHONDONTWRITEBYTECODE=1`, whose `llama.__file__` resolved inside the worktree.

### Assessment

**Task quality:** Approved

**Reasoning:** Every item is built as briefed, with a test tied to it. Each strict-surface rule holds by construction:
- the gate's new copy and terms are pure supersets, read through an `any()` consumer;
- the single-name voiced text is byte-identical;
- every migration refusal precedes any write;
- `short_keep=False` has no hunk.

The four Minors are optional hardening: two residual glue characters, the both-excluded double count, a both-absent `root`, and the explicit no-repeat-on-rename-failure path.
