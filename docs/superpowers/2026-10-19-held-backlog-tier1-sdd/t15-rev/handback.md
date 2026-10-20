### Spec Compliance

- ✅ Spec compliant for 4b, 4c, 4d and the orchestrator-added scope. One gap in the Task-16-facing local, listed under Important.
  - 4c: `_valid_ymd` (vet_research.py:41-43) is applied to every branch through the `full`/`noyear` closures (:54-58). The 3-part slash form (:63-65) and the yearless slash form (:78-80) try month-first first and fall back to day-first. The ISO and month-name forms return None when out of range, with no swap, as the spec says ("a slash form"). All brief rows are present, plus `10/11/08` (test_stage_vet.py:445-452). Yearless month-first-wins was already pinned by `normalize_date("3/2") == "--03-02"` (test_stage_vet.py:64).
  - 4b: `own_full = show.date in full` uses the full-date dict only, so a yearless own date does not count (vet_research.py:165). The window is measured from `show.date` (:166-169). `ADJACENT_DAY_WINDOW = 1` has a comment citing "New constants" (:15-17). Adoption reads `mismatched_raw` before the window is applied (:153-162).
  - 4d: the prompt's item 1 reads "on this recording — at this show, on this date" (vet_research.md:10-12). The changed assertion in the existing test_prompts.py:30 is a correct consequence of the wording change, not drift.
  - Orchestrator scope: `vetting.json` is written last, after show.json and notes.json (vet_research.py:234-239). The order is pinned by `test_run_vet_research_writes_vetting_json_last` (test_stage_vet.py:488-496). The top-level `import pytest` is at test_stage_vet.py:4.
  - Do-not-retune grep over the diff: none of the protected names (`is_real_title`, `title_fraction`, `_TRACK_NUM_PREFIX`, `normalize_song`, `DEFAULT_ALIASES`, `GD_SHORTHAND`, `_RECOVER_*`, the tail-guard and junk constants, `_ENUMERATED_*`, `_STRUCTURE_PREFIX`, `_FOOTNOTE_TAIL`) appears in a hunk. `_year` is unchanged.
  - Notes-never-reach-the-LLM: no new note, conflict or flag text is added. 4b only removes entries from `mismatched`.
- ⚠️ Cannot verify from the diff:
  - 4c's acceptance ("of the four stored instances, exactly `ryanadams-2008-11-16` changes") needs a harness run.
  - 4b's 37-flag and 26-clear numbers are for the harness and hand review.
  - `replay.py:26` imports `apply_vet`, so `compute_legs` now sees the window and the new ranges. That is intended. The controller should confirm that Task 19 and 20 expectations were written against the windowed behaviour.

### Strengths

- Equivalence of mutant (c), checked independently: it holds. Adoption requires `len(full) == 1` and `len(mismatched_raw) == 1`, so the single full date is not `show.date`, so `own_full` is False and the windowed set equals the raw set. When `own_full` is True with `len(full) == 1`, `mismatched_raw` is empty either way. No input can tell the mutant apart, so SURVIVED-equivalent is correct.
- `_within_window` fails closed: a calendar-invalid but range-valid date such as `1973-06-31` keeps its flag (vet_research.py:122-126). That is the conservative direction for a guard.
- Mutant (d) was found to be caught only incidentally, and the implementer added a dedicated row instead of accepting that. This matches the "caught only by the predicted test" rule.
- The write-order test records real write calls through a pass-through wrapper rather than mocking the writes away.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
- vet_research.py:170-171: `raw_date_flags` is not what the brief defines it as. The brief says it is "the flags that loop would have produced without the window" (plan line 2272), and Task 16 consumes it as `not date_flags_raw` to mean "no wrong-date or placeholder-date flag fires, read before 4b" (spec :709-710; plan :2356). The local is built only from `mismatched_raw` as `wrong date: {t}`, which goes wrong in three ways:
  - **Yearless flags are missing (the substantive gap).** The flag loop also emits `wrong date: {text}` for each mismatched yearless date (:183-185). A show whose research asserts `1973-06-10` and `June 12` gets a real wrong-date flag, yet `raw_date_flags` is empty, so 4a's "no date flag" leg would pass on it.
  - **Placeholder flags have the wrong text.** On a placeholder show the loop emits `{norm}; item date … looks like a year-only placeholder` (:176-179). The local holds `wrong date: …` instead. The spec says `compare` parses verbatim texts.
  - **Adoption is ignored.** When `adopted is not None` the loop emits nothing, but the local is non-empty.

  The last two are masked today by 4a's `own_full` leg: given `own_full`, adoption is impossible. The yearless omission is not masked.

  The local is also dead code in this commit. Python allows that, but it hands Task 16 a wrong contract under a name that differs from the plan's (`raw_date_flags` here, `date_flags_raw` in plan :2356).

  Fix: move the date-flag loop (:172-185) into one helper, e.g. `_date_flags(mismatched, yearless, show, placeholder, adopted) -> list[str]`. Call it once with `mismatched_raw` for the raw flags and once with the windowed `mismatched` for `flags`. That also removes the duplicated `wrong date:` format string at :171. Add a test now (or make it a precondition in Task 16's brief) that raw flags include a yearless mismatch when the own full date is asserted.

#### Minor (Nice to Have)
- vet_research.md:10-13: the reflow leaves a ragged short line ("entry: split segue chains"). This is cosmetic. Re-wrapping the paragraph would keep the prompt tidy, and only fresh extractions read it.
- test_prompts.py:39-41: `from llama.prompts import load_prompt` is re-imported inside the test, though the module already uses `load_prompt` at top level (:21, :28). The brief mandated it, and it is harmless.
- `test_4b_leaves_placeholder_adoption_unchanged` (test_stage_vet.py:479-482) is brief-mandated but cannot reach the window, since `own_full` is False with one date. It re-tests the existing adoption path. Mutant (c) is equivalent, so no test could distinguish it anyway. The test's name over-promises. Untested interaction: a placeholder show whose research asserts `YYYY-01-01` plus `YYYY-1-12-31` (a New Year's spill). The placeholder-date flag is now suppressed by 4b. That follows the spec's wording, but nothing pins it, and 4b clears are hand-read.
- vet_research.py:41: the `y` parameter of `_valid_ymd` is unused, and `noyear` passes `0` for it (:58). The signature is brief-mandated. Acceptable.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** 4b, 4c, 4d and the write-order change are correct and well pinned, and mutant (c)'s equivalence argument holds. The Task-16 hand-off local `raw_date_flags` leaves out yearless wrong-date flags and mis-renders placeholder and adopted cases. It is not "the flags that loop would have produced", and Task 16's 4a gate would consume it as such. Moving the loop into a helper called twice fixes this and removes the duplicated format string.

Checks run, all by reading only (no tests run):
- Spec "Slice 4" lines 695-775 and "New constants" 975-990.
- Plan lines 2272, 2356, 2395 and 2441, for how Task 16 consumes the local.
- Pre-diff `vet_research.py` lines 180-196: the yearless loop and its flag text.
- `models.py:187`: `date_source` defaults to "item", so the placeholder test really adopts.
- `test_stage_vet.py:40-64`: existing coverage of yearless month-first-wins.
- Grep for other `normalize_date` and `vet_research` importers: only `replay.py` and `pipeline.py`.
