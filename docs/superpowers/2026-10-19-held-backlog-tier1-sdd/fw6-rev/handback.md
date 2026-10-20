VERDICT: CHANGES REQUIRED

(Test-only changes, about 4 lines. The production code is correct and matches the brief; the problem is that two note-path guards are untested, and one of those tests is a test the brief required.)

Reviewed 0c916da..3c75471 (one commit, 3c75471) in a read-only snapshot taken with git archive 3c75471. The snapshot's shadowing was proven: llama.__file__ resolved under the snapshot.

## Spec compliance
| # | Brief item | Status | Where |
|---|---|---|---|
| 1 | `_JOINED_NUM_PREFIX = re.compile(r"^\d{1,3}[-_](?=[^\d\s])")` verbatim; `_TRACK_NUM_PREFIX`, `_GLUED_NUM_PREFIX` and `_ENUMERATED_*` byte-identical | ✅ | titles.py:207 (comment :197-206). Diff grep: no do-not-retune name is redefined, only referenced |
| 1 | Comment covers what it strips, why it is separate, the fw6 citation, and the bound/lookahead | ✅ (wording as the brief dictated; see Minor m1) | titles.py:197-206 |
| 2 | Its own vote, same shape as 2c, over `voters` (gate_basis), `count=1`, run after the spaced and glued passes, no footnote tail | ✅ | titles.py:249-254. An unconditional `sub` on a non-matching `^` pattern is a no-op, so this is equivalent to 2c's conditional form |
| 3 | Scope is tag titles only; override, setlist and sibling-align text untouched | ✅ in code / ❌ in the report's claim | See "Extra checks": sibling-align DONOR tags do pass through clean_tag_titles |
| 4 | Gather note text verbatim, only when `tag_source == "tags"`, only for a changed title that matches the predicate, never for an override | ✅ code | gather.py:1141-1144 |
| 4 | replay_holds family `("2d", "stripped joined track number:")` | ✅ | replay_holds.py:177. No test pins NOTE_GROUPS, so there was none to update |
| T | Tests: hyphen tape (incl. `22-I Know You Rider` and unnumbered `Bertha`), underscore tape, digit remainder named as a false negative (`04-200 More Miles` rather than `01-200`, which is fine), numeric titles on a passing vote (1922/2001/4-20/24-7 Spyz/1-800-Suicide), 2-of-10, M80/7-Up | ✅ | test_titles.py:638-677 |
| T | Gather: one note per stripped title, verbatim; nothing under format recovery | ✅ first part / ⚠️ second part is vacuous (I1) | test_stage_gather.py:2667-2697 |
| M | M1-M5 table | ✅ claimed; I re-ran M1 and M5 and confirmed both | below |
| C | Cache census | ✅ in the impl handback (8 items, 23 closest calls, all banter/applause rows) | |

## Findings

### Important
**I1. The required "nothing under format recovery" test is vacuous, and the `tag_source == "tags"` guard is unpinned.** (test_stage_gather.py:2690-2697; guard at gather.py:1134)
- `_rre_joined(drop_mp3_titles=True)` deletes the mp3 titles, so `raw = clean_tag_title(None) == ""`. `_JOINED_NUM_PREFIX.match("")` is then None, and no note can fire whether or not the guard is there.
- Mutant M8 (`if tag_source == "tags":` -> `if True:`) passes all 295 tests in test_titles.py and test_stage_gather.py.
- What would go wrong: if the guard is lost, every recovered show whose mp3 carries junk `NN-x` tags gets false "stripped joined track number" notes. Those land in notes.json and in the harness's 2d family. The same exposure already exists, untested, for 2c.
- Fix (verified): in `_rre_joined(drop_mp3_titles=True)`, set the mp3 title to `t[:2] + "-x"` instead of deleting it. Recovery still fires because the mp3 title_fraction is 0. Then assert the first track's `title_source == "sibling-format"`, title `Pig In A Pen`, and no joined notes. I ran exactly this probe: it PASSES on 3c75471 and FAILS on M8 (`assert not True`).

**I2. The note's predicate clause is unpinned.** (gather.py:1141, `and _JOINED_NUM_PREFIX.match(raw)`)
- Mutant M7 (drop that clause) passes all 295 tests.
- What would go wrong: on every glued (2c) tape, each glued strip would also emit a bogus "stripped joined track number" note. The harness would then double-count families.
- Fix (verified): add `assert not any(n.startswith("stripped joined track number:") for n in res.notes)` to `test_2c_strips_railroad_earths_glued_numbers_and_notes_each`. This mirrors the reverse assertion the implementer already added to test_2d. With it, M7 fails that test and the real code passes.

### Minor
- **m1 (comment over-credits the `\d{1,3}` bound).** titles.py:203-205.
  - For `1922` and `2001`, what keeps them out of reach is the mandatory `[-_]`, not the bound. The bound only matters for a title like `2001-A Space Odyssey`.
  - Unlisted mutant M6 (`\d{1,3}` -> `\d+`) SURVIVES the suite. The brief dictated this wording, and the project's own rule is "do not credit a guard with work it does not do".
  - Fix: add a row such as `2001-A Space Odyssey` to the odd list in `test_joined_strip_never_touches_numeric_titles_when_the_vote_passes` (this pins the bound), and/or reword the comment to say the separator excludes the bare years and the bound excludes `NNNN-Title`.
- **m2 (unrecorded destructive mode).** On a tape where the vote PASSES, `7-Up`, `3-D` and `8-Ball` become `Up`, `D` and `Ball`. This is the analogue of the accepted `100 Years` gap.
  - The census found no such title across 13,339 items, so this is documentation-level only. I recommend recording it as an operator-ruled gap, or pinning it by test as `100 Years` is. Do not tune the rule.
- **m3 (the report's scope claim is inaccurate; the brief's own parenthetical is too).** "sibling-align text does not pass through clean_tag_titles" is false for DONOR tags: gather.py:208 (`load_donor_tapes`, `DonorTape.titles=clean_tag_titles(kept)`) and correspondence.py:310. The effect is acceptable; see the extra checks below.
- **m4.** ryanadams-2017-05-06, named in the brief's motivation, is unchanged. Its shipped titles show 18 of 25 in the joined form (0.72 < 0.8), so the vote fails as designed. It is delivered and clean, so no action is needed.

## Extra checks (orchestrator)

**select_recording.py:69: CANNOT change which recording is picked. Acceptable.**
- That call site uses only `title_fraction(clean_tag_titles(kept))`, and `title_fraction` is exactly invariant under this strip:
  - The strip removes only digits and `[-_]`, neither of which is an ASCII letter, so `is_real_title`'s letter count is unchanged.
  - The `[0-9]{4}` fullmatch holds neither before (the raw title contains `-` or `_`) nor after (the lookahead guarantees the remainder starts with a non-digit).
- The same proof covers `_recover_format_titles`' trigger (gather.py:339) and `fetch_siblings` (gather.py:1165): neither can move.

**Donor paths (gather.py:208 sibling-align donors; correspondence.py:310 `sibling_item_durations` for `--suggest-titles`): titles from the 8 affected items now arrive stripped. Acceptable, no gate needed.**
- For sibling-align, a donor would previously have proposed `01-Hell In A Bucket`. Its fuzzy norm, `01 hell in a bucket`, also disagrees with the target's anchors. It now proposes the clean title.
- For suggest-titles, a donor whose titles were joined-numbered could not resolve canonical items before and now can. That changes the DP's duration costs, but only for a proposal an operator confirms.
- This is the same reach 2c already has, it is in the direction of correctness, and the harness shows 0 sibling-align title changes across 3,468 shows.

**Harness `~/.llama-harness/cmp-fw6-all/`: `compare` exited 2** ("arms differ: joerussosalmostdead-2022-04-30: digests differ"), so no report files were written.
- The cause is that joerusso's provenance.json changed in the live library between the two arms. fw6 did not cause it.
- I diffed `fw6-base-all.json` against `fw6-cand-all.json` directly instead (read-only). The show sets are identical (3,468), and only 5 shows changed, all through the new strip:
  - **darkstarorchestra-2012-05-19** (held): 21 titles stripped, 21 notes. Outcome stays needs-brief -> needs-brief. It is NOT newly cleared: it still needs a fresh briefing, as the diagnosis predicted.
  - **mountaingoats-2012-06-27** (held): 27 titles stripped. Stays needs-llm.
  - **mountaingoats-2017-06-02** (delivered): 45 titles stripped, plus a structure change. The base arm's proposed set_breaks [12,15,23] become [11,15,23] (stored: [10,15,23]), and set_changes drops track 12.
    - Track 11 is `John Doesn't Plan The Solo Set` (banter) and track 12 is `Xolo`, so the candidate's break after 11 looks more plausible.
    - Hand-check before any action. It is delivered, so reapply never touches it.
  - **mountaingoats-2019-05-08** (delivered): 31 titles stripped. clean -> clean-changed, briefing reuse -> fresh.
  - **theblacklillies-2014-04-20** (packaged): 13 titles stripped. clean -> clean-changed, briefing reuse -> fresh.
- Newly cleared: NONE. Newly held: none.
- Every changed shipped title is a `NN-`/`NN_` prefix removal. All are listed in the arms; there are 137 in total (21+27+45+31+13), and the closest calls are the mountaingoats banter/applause rows, which were never song titles.
- Selection changes: none (the selected_venue/city fields are identical, and the invariance proof above covers it).

## Mutation spot-check
I wrote each prediction to the log before flipping the mutant. Each mutant had a fresh rsync copy of the snapshot, PYTHONPATH shadowing (proven per mutant: llama.__file__ resolved under the copy) and a private PYTHONPYCACHEPREFIX. Every run covered test_titles.py and test_stage_gather.py.

| mutant | predicted test | caught by / SURVIVED |
|---|---|---|
| M1 lookahead `(?=\S)` | test_joined_strip_never_touches_numeric_titles_when_the_vote_passes | caught by the predicted test, and also by test_joined_strip_leaves_a_digit_remainder_alone_a_known_false_negative |
| M5 lookahead `(?=[A-Z][a-z])` | test_joined_strip_removes_hyphen_numbers_and_leaves_unnumbered_titles | caught by the predicted test |
| M6 (unlisted) `\d{1,3}` -> `\d+` | SURVIVED (predicted) | SURVIVED (m1) |
| M7 (unlisted) note condition drops `_JOINED_NUM_PREFIX.match(raw)` | SURVIVED (predicted) | SURVIVED (I2). With the proposed 2c assertion, it is caught by test_2c_strips_railroad_earths_glued_numbers_and_notes_each |
| M8 (unlisted) `tag_source == "tags"` -> `True` | SURVIVED (predicted; recovery test vacuous) | SURVIVED (I1). With the proposed probe fixture (mp3 tags `NN-x`), the recovery test fails on M8 and passes on 3c75471 |

## Suite
Snapshot of 3c75471 with the worktree interpreter and PYTHONPATH shadowing: `3780 passed, 1 skipped, 8 deselected, 26 warnings in 87.64s`. This matches the implementer's count (3762 + 18).
