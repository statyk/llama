# t8-rr1: Task 8 fix round 1 re-review (76c1830..c7625c9)

### Finding Verdicts

- **(Important 1) No test separated candidate membership from `r1_dec`; M1/M2 survived.** ADDRESSED.
  - The new test is `test_packet_membership_comes_from_the_candidate_not_r1_dec` (`scripts/test_short_keep_probe.py:476-492`).
  - The code now derives membership from `set(c["filenames"])` plus `short_kept is True` (`scripts/short_keep_probe.py:437-440`).
  - I ran the mutants myself, because the implementer had not:
    - **M1** (`kept = not e["r1_dec"].startswith("drop")`): predicted to fail the new test. **Killed**: only that test fails, 36 others pass.
    - **M2** (the `continue` replaced by `pass`): predicted to fail the new test. **Killed**: only that test fails.
    - **Variant M1b** (`kept = in_show`, which ignores `short_kept`): predicted to survive. **Survived**, 37 passed. See Minor 1 below.
- **(Important 2) INSTRUCTIONS gave the operator an invented "tuning chatter" direction.** ADDRESSED.
  - `scripts/short_keep_probe.py:349-350` now reads "...stage announcements; a mixed tag such as `tuning/banter` is kept."
  - `tuning/banter` is spec 2.3's own example (`docs/superpowers/specs/2026-10-23-junk-short-keep-design.md:171`).
  - `grep chatter scripts/short_keep_probe.py` finds nothing.
- **(Minor 2) packets must refuse (exit 2) bad candidate rows, and test membership against `set(filenames)`.** ADDRESSED.
  - The refusal covers a replayable row with no `filenames` or `short_kept` list, or with lengths that differ (`:425-430`). It fires before anything is written.
  - Membership is `e["name"] in set(c["filenames"])` (`:437`).
  - The new test is `test_packets_refuse_candidate_rows_without_valid_short_kept` (`test:495-504`). It covers a missing `short_kept` (exit 2, out dir not created) and a length mismatch (exit 2).
  - Mutants:
    - **M3** (`if bad:` changed to `if False:`): predicted to fail that test. **Killed** (KeyError).
    - **M3b** (the length clause deleted): predicted to fail that test. **Killed** (KeyError on the mismatch case).
  - The policy matches `arms`' existing refusal of replayable rows that lack the fields (`:296-300`).
  - `replay.py:560-561` always sets `filenames` and `short_kept` together, so real arms cannot trip the refusal by accident.
- **(Minor 5) Test the exact 90% boundary, plus a kept spoken-broadcast row and a dropped segue/fragment row.** ADDRESSED.
  - The new cases are in `test_score_bar_and_wrong_rows` (`test:573-586`).
  - Mutants, each killed at the assertion I predicted:
    - **M5** (`>=` changed to `>`): dies at `:578`, the 9-of-10 PASS case.
    - **M7** (`spoken-broadcast` removed from `BAD_KEPT`): dies at `:581`. The case scores exactly 90%, so only the forbidden-kind leg can fail it.
    - **M8** (`fragment` removed from `BAD_DROPPED`): dies at `:584`.
    - **M9** (`segue-or-continuation` removed from `BAD_DROPPED`): dies at `:586`.
- **(Minor 7) first10.md blind, with position and floor_sec; answers in a separate first10-answers.md.** ADDRESSED.
  - `first10.md` no longer prints a grader line, and it now prints `floor_sec` and `position` (`:514-520`).
  - `first10-answers.md` is written separately (`:522-527`).
  - The test asserts both files (`test:552-555`).
  - **M10** (a grader line put back in `first10.md`): predicted to fail at `:553`. **Killed** there.

**Mutation rig:**
- Each mutant ran in a fresh copy of `git archive c7625c9`, under the scratchpad, deleted after its run.
- Each run used `.venv/bin/python -m pytest -p no:cacheprovider scripts/test_short_keep_probe.py` from the copy, with `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPATH` pointing at the copy's `scripts`, `packages/llama/src` and `packages/herder/src`.
- A planted sentinel (`raise RuntimeError('SENTINEL-RR1')` in the copy's probe) gave a collection error naming SENTINEL-RR1. So the copy is the code under test.
- The unmutated copy passed 37 of 37.
- Predictions and results are logged in `$D/t8-rr1/t8-rr1.log`.

### New Breakage in the Fix Diff

- **Minor 1:** the new membership test's row C (in the show, `short_kept` false) has kind `tuning/dead-air/noise` (`scripts/test_short_keep_probe.py:483`). That kind cannot fall in any kept stratum, so "never drawn" is checked only on the dropped path.
  - That is why M1b (`kept = in_show`) survives.
  - The gap is real: under M1b, an operator-re-admitted short music file would be graded as the rule's keep.
  - **Fix:** give C kind `"music"`. Measured: with that one-word change the unmutated suite passes 37 of 37, and M1b is killed at `test:491`.
- **Minor 2:** `scripts/short_keep_probe.py:513` still has `a = answers.get(r["row"]) or {}` in the `first10.md` loop, now unused. Cosmetic; the implementer noted it too.

Nothing else found:
- The refusal runs after `_guard_out` and before any write.
- `is True` is right for JSON-loaded or `bool()`-built values.
- The per-row `set()`/`dict()` rebuild costs nothing at 3,547 rows.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. There are two Minors: row C's kind should be `music` so M1b dies, and the unused `a =` line.
