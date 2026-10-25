# Task 1 review (t1-rev): c7dac0c..fdd7f1d

### Spec Compliance
- ✅ Spec compliant on every itemised requirement, with one ❌ in behaviour that the spec text only half covers (Important 1 below: the interior test reads pre-dedupe listings).
- ✅ Normative port (spec 2.3). Checked by script: every non-blank line of the spec's code block appears verbatim in `packages/llama/src/llama/junk.py`, except the three `def` lines. Those differ only by the brief's type annotations (`junk.py:139,144,154`). All nine regexes are character-identical.
- ✅ `basename_without_extension` is exactly the global-constraints form (`junk.py:133-136`).
- ✅ `short_verdict` order is spam, then tagged junk/keep, then untagged filename/keep/edge (`junk.py:167-182`), as the brief's interface says.
- ✅ The tripwire drop records `SPAM_REASON` (`junk.py:250`). A junk, filename-junk or edge drop keeps `["implausibly short"]`. Only entries whose reasons are exactly `["implausibly short"]` are re-decided (`junk.py:204`, spec 2.1).
- ✅ The tag fallback reads the original's title for derivatives (`junk.py:207`). Pinned both ways by `test_short_keep_rule.py::test_tag_falls_back_to_the_original_title` (Review Focus 1).
- ✅ Play order is taken over kept + tagged-kept + untagged candidates, by track tag when complete and unique, else by name. Only kept and tagged-kept files count as neighbours (`junk.py:220-236`).
- ✅ `ordering["short_kept"]` is present in both ordering dicts, sorted, and intersected with the final `kept` after dedupe and readmit (`junk.py:453,460,467`). Review Focus 2 is pinned by `test_short_kept_names_survive_dedupe_only`.
- ✅ `orig_tracks` is moved above the format loop with the identical expression (`junk.py:405`). The format loop, the dedupe call and the readmit block are otherwise untouched.
- ✅ Global constraints, untouched names: I grepped the diff's `-` lines in `junk.py`. They are only the `_keep_and_exclude`/`filter_files` signatures, the return statements, the fallback/chosen tuples, the moved `orig_tracks` line and the two ordering dicts. None of the following is modified: `SHORT_FRACTION_OF_MEDIAN`, `MIN_MEDIAN_SAMPLE`, `MIN_PLAUSIBLE_SEC`, `_stem`, `_track_number`, the two-pass floor, the convention/provenance/`missing duration` arms, `_dedupe_duplicate_listings`, `FORMAT_BY_AUDIO`, `LOSSLESS_TITLE_FORMATS`, and readmit's position. The other modules on the list are not in the diff.
- ✅ Spec 2.5, every caller gets the rule. `grep -rn short_keep packages scripts` finds only the definition and the new tests. No caller passes `False`.
- ✅ Changed contracts, call sites checked:
  - `_keep_and_exclude` (3-tuple) has one caller (`junk.py:412`).
  - Every `filter_files` caller in `src/` and `scripts/` unpacks 3 items and is unaffected by the new keyword.
  - gather copies `ordering` keys selectively (`stages/gather.py:1112,2037-2038`), so the new key cannot leak into a persisted model.
- ✅ Fixtures:
  - The vendored `junk_v2_17_0.py` body equals `git show e37f670:packages/llama/src/llama/junk.py` (I ran a diff; it was empty).
  - The corpus is 3,547 rows, sha256 `4ed4fb94…59e10`, and equals the field projection of `~/.llama-harness/piece45/spec/r1/r1_files.jsonl` row for row (checked by script).
- ✅ Step 5's dry-run list is what the rule now keeps in the fixtures. I re-ran it: dso `Announcements`, furthur `tmp`, gd70/gd74-miller `Introduction` (mp3 and flac), windsor `Weather Report Suite Part I >`, rre's two Banter files (mp3 and flac). gd73 is unchanged and has no duplicate listings. This matches the brief's expected list exactly.
- ✅ Every existing-test update names its spec clause, and none follows a mis-pointed override:
  - `test_override_path_leaves_matched_unmeasured` re-points `encore_after` 26→27 with the mandated comment (`test_stage_gather.py:206-208`).
  - The input-shape restorations (`_gd74_blank_ia`, `_furthur_without_short_tuning`, the probe library) remove the newly kept file only where the test's subject is the old shape. The captured tapes stay covered by the updated gather tests and the `furthur` cascade case.
- ⚠️ Cannot verify from the diff: whether the census `pos` that `test_deny_vocabulary_corpus` replays matches the filter's own interior derivation on real items. The test docstring says so honestly. Task 9 is the gate.

### Strengths
- **Normative port.** The regexes and functions were extracted from the spec by script and checked by bytecode. My line-by-line check found no deviation.
- **Implementer decisions I verified as correct:**
  - `follow-me-now.mp3` needs the dominant stem, or the convention arm also fires and the tripwire never sees it.
  - `http://` cannot fire on a stem, because the basename is cut at the last `/`. It is tested on a tag instead.
  - The original is looked up only for a derivative, consistent with `_track_number`.
- **The `short_keep=False` pin is strong.** It compares names, the full excluded dicts and the ordering against the vendored e37f670 filter, plus object identity, over every fixture × mp3/flac. `test_short_keep_true_changes_some_fixture` keeps it from passing vacuously.
- **The tests catch the mutants that matter.** U2 in `test_untagged_interior_kept_edge_dropped` is Task 21 mutant (e). `test_interior_ignores_spam_and_filename_junk_neighbours` covers neighbour-set leakage. The implementer reports six caught mutants in a shadowed scratch copy.
- **Warnings did not grow.** The full suite reports 26 warnings, the same as the Task 0 baseline in `orch/ledger.md:35`. The new file runs clean (I ran it: `54 passed in 0.35s`).

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **`junk.py:220-236`: the interior test runs over pre-dedupe listings, so an untagged short file at a tape edge is kept on a duplicate-listed item (strict surface (c), ruling 4).**
   - **Cause.** `_apply_short_rule` builds the play-order pool from `_keep_and_exclude`'s `kept`, which still holds both copies of a doubled item. One example is the ymsb2005 donor shape, where every track is listed at top level and again under `<identifier>/`.
   - **Why it fails.** Duplicate track numbers force filename order. The `<identifier>/` block then sorts as one contiguous block apart from the top-level block, so:
     - the top-level copy of an untagged short FIRST track has the whole other block before it, and reads as interior;
     - the prefixed copy of an untagged short LAST track has the whole top-level block after it, and reads as interior.
   - **Result.** `_dedupe_duplicate_listings` then keeps the surviving copy, so an edge file ruling 4 says must drop is admitted and named in `short_kept`.
   - **Check I ran** (read-only, live venv, `llama.__file__` inside the worktree). A 7-track tape whose untagged t01 is 30 s:
     - single listing: t01 is excluded with `implausibly short`;
     - the same tape doubled under `ymsb2005-12-31.x/`: `ordering["short_kept"] == ['ymsb2005-12-31d1t01.mp3']`, and t01 now plays last.
   - **Fixture coverage.** No fixture has duplicate listings (I surveyed every fixture in mp3 and flac). So nothing in the suite or the corpus test can see this, and Task 9 sees it only if a library item has the shape.
   - **Fix.** Derive the interior positions over the pool collapsed on dedupe's key (basename, rounded duration), e.g. by mapping each candidate to its key's position. Add a doubled-listing test next to `test_short_kept_names_survive_dedupe_only`.
   - **Spec wording.** Spec 2.5 puts the rule inside `_keep_and_exclude`, which runs before dedupe, while 2.4 says the order is "derived the way `filter_files` derives it", which is post-dedupe. The fix is local, but the orchestrator may want to record the reading.

#### Minor (Nice to Have)
1. **`test_stage_gather.py` (`_furthur_without_short_tuning`, added near :2405) and `test_title_cascade.py:126`:** the same helper is defined twice.
   - `test_title_cascade.py` already imports from `test_stage_gather` (`_rre`, :106).
   - Fix: import the helper instead of copying it.
2. **`test_short_keep_rule.py::test_floor_unchanged_by_kept_short_files` is close to tautological.**
   - The floor's median is over `non_duration`, the other arms only, so a file's tag can never reach it, wherever the rule sits.
   - No plausible mutant of this diff turns this pin red.
   - It is mandated by the brief, so keep it. Its value is documentary.
3. **`junk.py:210-213`: `interior=False` is used as a sentinel.** It is passed so that "edge" means "untagged, not filename junk", and the spam check then runs a second time for each untagged file (:233).
   - Correct and commented, but indirect.
   - A small `_short_class()` returning spam/junk/tagged/filename/untagged would read more plainly.
4. **`junk.py:177`: `own_title or original_title`.** A whitespace-only own title is truthy, cleans to empty, and does not fall back to the original's title.
   - This is as measured (the implementer cites the r1 scripts), and spec 2.2's "else" is ambiguous.
   - Worth one test or a comment so the behaviour is deliberate rather than incidental.
5. **Implementer concern 1 (format choice): confirmed real, narrow, and spec-mandated.**
   - A format whose kept set consists only of tagged short files can now win `filter_files`' first-non-empty preference.
   - That needs fewer than `MIN_MEDIAN_SAMPLE` clean durations, all under 90 s.
   - An untagged-only one cannot win, because with no base, nothing is interior.
   - Follows from spec 2.5. No action unless the orchestrator wants a pin.
6. **Implementer concern 2 (spec-level, not a Task 1 defect).**
   - On captured furthur, the mp3's placeholder own tag `tmp` makes the file tagged-kept, while its FLAC original's `Tuning Up` would have been junk.
   - D then titles it `Tuning Up`, and it ships as a track.
   - This is literal spec 2.2 (the own title wins), and Task 2's junk note fires on it as a note, not a hold.
   - Worth the orchestrator confirming that the note-only outcome is intended for this class.
7. **Implementer concern 3: interim coverage 27/28 on gd74 windsor** (`test_stage_gather.py:177-181,190-201`). This is expected until Task 2's coverage clause. Task 2's dry run must restore 1.0 and check `conflicts`.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The port is exact, the contracts are intact, and the tests are strong. But on a strict surface the interior test admits untagged short edge files on duplicate-listed items, which contradicts ruling 4 (reproduced above). The fix is local and needs one regression test.
