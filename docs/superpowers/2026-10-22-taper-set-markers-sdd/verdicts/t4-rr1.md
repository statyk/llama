# t4-rr1: re-review of Task 4, fix round 1 (19b0ad2..f4c7a84)

**Fix round: all findings are addressed, and the fix adds no Critical or Important breakage.** Status: DONE. I made no commits and no repo edits; the worktree is clean.

### Finding Verdicts
- **Important 1: three of the four conditions on the owned-show low-confidence flag (gather.py:1352) were untested; mutants M1, M2 and M3 survived.** ADDRESSED.
  - Three tests were added: `packages/llama/tests/test_stage_gather.py:3390` (a), `:3398` (b) and `:3409` (c).
  - Each asserts that reader coverage is `approx(2/7)`, below the 0.8 threshold, and that the flag is absent (`_assert_weak_reader_no_flag`, :3383).
  - Production code is unchanged. The diff touches only the test file, with 41 added lines.

  **Check 1: I re-ran the mutants myself in scratch copies.** Each copy was `git archive f4c7a84 pytest.ini packages/llama`, run from the copy's own cwd under `PYTHONPATH=<copy>/src` and `-p no:cacheprovider`, with `PYTHONDONTWRITEBYTECODE=1`. For every copy, `llama.stages.gather.__file__` printed that copy's own path. Each mutant's diff against HEAD was checked and is exactly one line. Predictions were logged before the runs, and every result matched its prediction:

  | Mutant | Change | Result | Killed by |
  |---|---|---|---|
  | M1 | drop `canonical.items and` | 1 failed, 3 passed | only (a) `test_owned_low_confidence_needs_canonical_items` |
  | M2 | drop `anchored is None and` | 1 failed, 3 passed | only (b) `..._needs_no_anchoring` |
  | M3 | drop `result.coverage < threshold` | 1 failed, 3 passed | only (c) `..._needs_weak_step_one` |

  In every case the failure was the flag-absent assertion.

  **Check 2: a probe copy shows each test removes exactly one condition.** The probe printed all four inputs just before the `if` at gather.py:1352:

  | Test | Canonical items | Anchored | Step-1 coverage | Reader coverage | Threshold |
  |---|---|---|---|---|---|
  | (a) | 0 | False | 0.0 | 0.2857 | 0.8 |
  | (b) | 7 | **True** | 0.0 | 0.2857 | 0.8 |
  | (c) | 7 | False | **1.0** | 0.2857 | 0.8 |

  **Check 3: what the tests actually assert, versus what they assume.**
  - **(b) anchoring is asserted.** The test asserts `step1_alignment == "jerrybase"`. In gather.py:1310-1316, `alignment = "jerrybase"` is set only when `anchored is not None`, and :1331 copies it into `step1_alignment`. So anchoring is pinned by assertion.
  - **(c) step-1 coverage ≥ threshold is not asserted directly.** The test asserts only `step1_alignment == "deterministic"`, meaning not anchored. It is still self-guarding:
    - If step-1 coverage fell below the threshold, all four conditions would hold: canonical items come from the setlist.fm fixture, anchoring is absent (asserted), and the reader is weak (asserted).
    - The flag would then fire, and the test would fail instead of passing vacuously.
    - The only unasserted link is that canonical items are non-empty, and that comes from `_FakeSetlistFM(TP_SONGS)`. This is a Minor point, recorded below.
  - **(a) "no canonical items" is likewise not asserted directly.** The test asserts `taper.source == "notes"`. If canonical items appeared, the flag would fire, because jerrybase is off by default and step-1 coverage on the weak markers is low. So this one is self-guarding too.
  - **Live worktree.** `llama.__file__` resolves inside the worktree, and `pytest -k owned_low_confidence` gives 4 passed.

### New Breakage in the Fix Diff
No Critical or Important breakage. One Minor:
- **Minor: (b) is the only test whose pin could go vacuous without failing.** test_stage_gather.py:3398 does not assert that step-1 coverage is below the threshold.
  - If `_MISMATCHED_SLFM` ever started matching the tape, (b) would keep passing but would no longer pin M2.
  - The risk is small, since the fixture's names are "Zulu …".
  - Fix: an explicit precondition, e.g. `align(res.show.tracks, <canonical>).coverage < 0.8`, or the `_oracle` run's coverage. That would also turn the (a) and (c) preconditions from entailed into asserted.

### Out-of-Scope Observations
None.

### Verdict
**Fix round:** all findings are addressed, and the fix adds no Critical or Important breakage. Nothing is left open; the one Minor above is deferred to the final review.

Evidence log: `$D/t4-rr1/t4-rr1.log`.
Scratch copies:
- `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/0443a042-e8ee-4093-a603-2fbd14e62179/scratchpad/t4-rr1/P`
- `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/0443a042-e8ee-4093-a603-2fbd14e62179/scratchpad/t4-rr1/M1`
- `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/0443a042-e8ee-4093-a603-2fbd14e62179/scratchpad/t4-rr1/M2`
- `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/0443a042-e8ee-4093-a603-2fbd14e62179/scratchpad/t4-rr1/M3`
