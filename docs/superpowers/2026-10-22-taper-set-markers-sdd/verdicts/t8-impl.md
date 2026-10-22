# t8-impl handback: Task 8, the mutation run plus the R14 killing tests

**Status: DONE**

## Commits
1. **c26fd59** `test(gather): pin the Task 4/5 survivors the mutation run needs killed` (Step A, test only). It adds these tests to `packages/llama/tests/test_stage_gather.py`:
   - `test_set_count_note_excludes_the_taper_encore` (Task 5 M5, required). Through gather: TP_DESC, i.e. 2 numbered sets plus an encore, against jerrybase Charlie/1, Echo/2, Foxtrot/3. Expects the note `structure has 2 sets but jerrybase shows 3 (taper's markers)` and no count flag.
   - `test_closer_agreement_uses_fuzzy_song_matching` (Task 5 M6, required). A helper-level test with 3 params: case, `&`/`and`, and a dropped subtitle. The flag stays hard. Each case first asserts that `_CLOSER_FLAG` parses the flag, so `kept` is a real verdict (this also addresses t5-rev minor 5's tautology concern for the new tests).
   - `test_closer_maps_to_the_taper_set_of_the_same_number` (Task 5 M2).
   - `test_duplicate_closer_flags_consume_sets_in_order` (Task 5 M3).
   - `test_filler_only_label_difference_keeps_step_one_alignment` (Task 4 M4). It patches `llama.taper.decide_taper` to an owned decision that differs from step 1 only on the filler track `Tuning`. Expected: `alignment` stays `deterministic` and there is no "was" note.
   - Before this commit, each test was checked in a scratch copy: it fails on its mutant and passes on HEAD.
2. **6bddf0d** `docs: taper-markers mutation record`. Adds `docs/superpowers/2026-10-22-taper-set-markers-sdd/mutation.md`.

## Instrument proof
- **Scratch copy:** `git archive c26fd59` is unpacked into the scratch dir, and every mutant gets a fresh copytree under `m/<id>`.
- **How tests run:** from an empty scratch cwd, as `<wt>/.venv/bin/python -m pytest -q -p no:cacheprovider`, with:
  - `PYTHONPATH=<copy>/packages/llama/src:<copy>/packages/herder/src`;
  - a fresh `PYTHONPYCACHEPREFIX` per mutant;
  - a 600 s timeout.
- **Import check:** for every run, the runner asserts that `llama`, `llama.taper`, `llama.stages.gather`, `llama.replay` and `herder` resolve inside that copy.
- **One-line check:** the runner asserts each mutant's old text occurs exactly once, and that the diff is a single hunk of one `-` line and one `+` line.
- **Sentinels**, run on the 6 relevant files (760 tests):

| sentinel | planted at | red |
|---|---|---|
| S0 | unmutated copy | 0 / 760 |
| S1 | `raise` at the top of `decide_taper` | 396 |
| S2 | `raise` in `demote_jerrybase_flags` | 15, all gather |
| S3 | `raise` in `compute_legs` | 107: reapply, replay, replay_holds |

- Every mutant's passed + failed count totals 760. So no mutant aborted the session or hung.

## Mutant table
Full table with diffs and observed sets: `docs/superpowers/2026-10-22-taper-set-markers-sdd/mutation.md`.

| id | mutation | file:line | observed red | verdict |
|---|---|---|---|---|
| a | non-filler track between accepted | taper.py:715 | 3: predicted, +2 undeclared, same rule | CAUGHT-AS-PREDICTED |
| b | non-unique match accepted | taper.py:684 | 2: predicted, +1 undeclared | CAUGHT-AS-PREDICTED |
| c1 | repeated-title check, a side | taper.py:703 | 2: predicted, +1 undeclared | CAUGHT-AS-PREDICTED |
| c2 | repeated-title check, b side | taper.py:705 | 2: predicted, +1 undeclared | CAUGHT-AS-PREDICTED |
| d | skip accepted mid-sequence | taper.py:541 | 2: synthetic skip case, +1 undeclared | CAUGHT-AS-PREDICTED |
| d2 | (extra) skip accepted at the first header | taper.py:532 | 2: predicted, +1 undeclared | CAUGHT-AS-PREDICTED |
| e | numbered marker after the encore ignored | taper.py:514 | 3: predicted, +1 undeclared | CAUGHT-AS-PREDICTED |
| f | cross-check removed | taper.py:591 | exactly the predicted 3 | CAUGHT-AS-PREDICTED |
| g | encore-like veto removed | taper.py:772 | exactly the predicted 11 | CAUGHT-AS-PREDICTED |
| h | track-title veto removed | taper.py:770 | exactly the predicted 3 | CAUGHT-AS-PREDICTED |
| i | relaxation keyed on `not needs_llm` | replay.py:331 | 5: predicted 3, +2 declared | CAUGHT-AS-PREDICTED |
| j1 | relaxation removed | replay.py:331 | 2: predicted, +1 declared | CAUGHT-AS-PREDICTED |
| j2 | relaxation unconditional | replay.py:331 | 6: predicted 5, +1 declared | CAUGHT-AS-PREDICTED |
| k | text agreement ignored | gather.py:124 | exactly the predicted 5 | CAUGHT-AS-PREDICTED |
| l | `E.` recognised | taper.py:223 | 5: predicted 4, +1 declared | CAUGHT-AS-PREDICTED |
| m | bare `1:` recognised | taper.py:165 | 17: predicted 15, +2 declared | CAUGHT-AS-PREDICTED |
| n | anchoring applied after the taper | gather.py:1400 | 4: predicted, +3 declared | CAUGHT-AS-PREDICTED |
| o | `(?!\w)` dropped from the set token | taper.py:165 | exactly `test_set_like_negatives[Set In Stone]` | CAUGHT-AS-PREDICTED |
| p | merged-across-boundary rule removed | taper.py:712 | exactly predicted | CAUGHT-AS-PREDICTED |
| q | set-like veto removed | taper.py:774 | exactly the predicted 21 | CAUGHT-AS-PREDICTED |
| r | bare-`Set` rule removed | taper.py:557 | exactly the predicted 6 | CAUGHT-AS-PREDICTED |
| s | con't exemption dropped | taper.py:562 | exactly the predicted 4 | CAUGHT-AS-PREDICTED |
| t | M5, encore counted | gather.py:105 | exactly the new test | CAUGHT-AS-PREDICTED |
| u | M6, raw `==` | gather.py:122 | exactly the new 3 | CAUGHT-AS-PREDICTED |
| v | M2, any set's last song | gather.py:121 | exactly the predicted 2 | CAUGHT-AS-PREDICTED |
| w | M3, no in-order consumption | gather.py:115 | exactly the new test | CAUGHT-AS-PREDICTED |
| x | T4 M4, `if True` | gather.py:1405 | exactly the new test | CAUGHT-AS-PREDICTED |
| y1 | `canonical.items` dropped | gather.py:1397 | exactly predicted | CAUGHT-AS-PREDICTED |
| y2 | `anchored is None` dropped | gather.py:1397 | exactly predicted | CAUGHT-AS-PREDICTED |
| y3 | `result.coverage < threshold` dropped | gather.py:1397 | exactly predicted | CAUGHT-AS-PREDICTED |

**Survivors: 0. Hangs: 0. Surprise catches: 0.** No predicted test stayed green, and no red failed for an unrelated reason.

## The undeclared extra reds
Seven mutants turned extra tests red that I had not declared beforehand: a, b, c1, c2, d, d2 and e. I re-ran each and read its assertion. Each is another test pinning the same rule:
- **(a):** `test_every_boundary_must_place` and `test_real_case_declines` now place across a non-filler track.
- **(b):** `test_real_case_declines`. The ambiguous `NFA` match now passes the uniqueness check and declines later, for another reason.
- **(c1):** gather `test_not_owned_is_exactly_today`. Charlie is listed on both sides, so the show is now owned. The test's `reason.startswith` hits `None`, which gives an `AttributeError`. That is the only non-`AssertionError` red, and it is still this rule's behaviour.
- **(c2):** `test_comma_part_counts_for_the_other_side_check`.
- **(d):** `test_decide_taper_reports_source_and_reader_reason`. The reason is now `unplaced:` instead of `void:`.
- **(d2):** `test_leading_block_is_set_one_only_before_set_two`.
- **(e):** `test_set_and_encore_disc_line_asserts_nothing`. The reason is now `one set`.

I scored these as CAUGHT-AS-PREDICTED and listed them, because the predicted test was red for the predicted reason. If you count any unpredicted extra red as a surprise, these seven are the ones to look at. Each one adds a pin; none is a wrong-reason catch.

## Deviations from the brief (decided before flipping)
- **Missing test name.** The brief names `test_unrecognised_forms_are_not_markers` for (l), (m) and (o), and that test does not exist. My predictions named the real pins instead:
  - (l): `test_title_lookalikes_are_not_markers[E.*]`;
  - (m): the `n_colon` and `dso_bare_digit` tests;
  - (o): `test_set_like_negatives[Set In Stone]`.
- **(d)'s test name.** The brief names `test_void_rules`. The skipped-set case is in `test_void_rules_synthetic` (the same name family).
- **(c) split in two.** (c) became c1 and c2, one per side of the repeated-title check, so that each mutant stays one line. Both are caught.
- **(d2) added.** It covers the first-header half of the set-number rule, and it is caught.
- **M2 rewritten as one line.** The reviewer's M2 was multi-line. My (v) is a one-line equivalent: `songs` becomes the per-set last songs, sorted so that a match comes last. The effect is "agrees if any set's last song matches the closer".

## Observation for Task 9 / the orchestrator
**(o)**, the word boundary on the `Set 1-3/I-III` token:
- In the header regexes it is redundant. Every header shape needs `:`, a dash, decoration, an annotation, `cont`, a disc label or the line end straight after the token. So `Set Intro` cannot read as set 1 even without `(?!\w)`.
- I predicted `test_set_intro_is_not_set_one_and_set_iv_voids` would stay GREEN, and it did.
- The boundary is load-bearing only in `_SET_LIKE`, which reuses `_SET_TOKEN`. There, `[Set In Stone]` kills it.
- So Measurement 6's "forms' word boundaries" is pinned, but through the set-like veto. The brief's framing ("Set Intro reads as set 1") is not the failure this boundary prevents.
- No action is needed. This is recorded in mutation.md.

## Suite
`./.venv/bin/python -m pytest -q` from the worktree, run after Step A and again before the Step C commit: **4434 passed, 1 skipped, 8 deselected**. `llama.__file__` is in the worktree. `git diff main -- packages/llama/src/llama/setlist.py` is empty.

## Evidence
- **Scratch dir:** `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/0443a042-e8ee-4093-a603-2fbd14e62179/scratchpad/t8-impl/`. It holds:
  - `runner.py`, `gen.py`, `mutants.json` (the predictions), `sentinels.json`;
  - `results.jsonl` and `sentinels.jsonl`;
  - `score.py` and `inspect_m.py`;
  - `base/` (the archive).
- **Log:** `$D/t8-impl/t8-impl.log`. It holds the predictions (written before the run), every mutant's line, the scoring, and the exception sweep.

## Concerns
None blocking. The seven undeclared extra reds are listed above for the orchestrator to judge.
