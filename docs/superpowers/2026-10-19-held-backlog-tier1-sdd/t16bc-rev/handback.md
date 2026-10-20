### Spec Compliance

- ✅ Spec compliant (16b and 16c), with the slash-form deviation judged in the implementation's favour (below).
  - `normalize_date` output is unchanged: `_parse_date(text, False)` keeps `ok == _valid_ymd` and the original `noyear` (vet_research.py:55-95, 98-103); Task 15's day-0 rejection is re-pinned (test_stage_vet.py `test_normalize_date_still_rejects_day_zero`).
  - `day_unknown_date` shares the four regex branches instead of copying them (vet_research.py:106-109). Year-less forms return None through `noyear`'s `day_zero` guard (vet_research.py:68-71), and month 0/13 return None through `ok` (vet_research.py:62-63).
  - `grounding_flags` builds `day_unknown` with the first surface text per normalised value (vet_research.py:246-250). I checked that `["1991-09-00", "September 0, 1991", "9/0/91"]` on a 1991-09-01 show gives exactly one flag, `wrong date: 1991-09-00`.
  - `_date_flags` emits the day-unknown flags after the full-date flags and before the yearless ones, only when `not placeholder`, and still returns `[]` once a date is adopted (vet_research.py:156-177). Both call sites pass the set in, so the flags reach both `date_flags_raw` (vet_research.py:271-272) and the windowed flags (vet_research.py:284). The 4b window filters only `mismatched_raw`, so it cannot drop them.
  - Placeholder shows are unaffected: `full`, `mismatched_raw`, `yearless` and adoption never read `day_unknown` (vet_research.py:239-258).
  - No new constant, note or flag text. No do-not-retune constant is in the diff (checked the four files' hunks: `_valid_ymd`, `_TRACK_NUM_PREFIX`, the junk and tail constants etc. are untouched).
  - 16c: replay_holds.py:507-510 reads `v["vetting"]["asserted_dates"]` with dict/dict/list guards and keeps `(vetting.json unavailable)` for the fallback. Nothing else in compare changed.
- The brief's tests are all present (test_stage_vet.py, Task 16b block): parametrised `day_unknown_date`, the billycorgan shape, a day-00 in another month, a day-00 next to the show date, surface text and ordering, placeholder ignores the day-00, placeholder adoption unchanged, and the 4a gate declining. 16c's test is at scripts/test_replay_holds.py:726-743.
- Deviation ruling ("0/5/08"): **the implementation is right.**
  - The brief's interface also says "Reuse normalize_date's parsing". `normalize_date`'s slash rule (spec 4c) is month-first with a day-first fallback.
  - With that fallback, `0/5/08` reads as 2008-05-00. That matches `5/0/08` and `0/9/91` → 1991-09-00 (I checked both). It is the only sensible reading of the string.
  - Reading the slash form strictly month-first would make `day_unknown_date` the one reader in the module that ignores the 4c fallback.
  - The two readers stay disjoint: a string is either a valid date or a day-00 date, never both, so no text can raise two flags.
  - Strict-surface cost: it can add a hold only on a specific show, for an LLM asserting a D/M/Y day-0 string. That is the operator's stated intent ("day unknown must still flag"), not a loosening.
  - The brief's own list marked its None examples as "pick so that the month-0 and year-less cases are pinned". The implementer pinned month-0-either-way with `0/0/91` and the year-less slash form with `0/5`. The controller should record the brief's "(month-first)" wording as superseded in the ledger.
- ⚠️ Cannot verify from the diff: that billycorgan-1991-09-01 stays held and littlefeat-1970-01-01 stays unflagged on the real library. That needs a harness replay of those two slugs. The unit tests mirror their shapes only.

### Strengths
- A clean factoring: one `_parse_date` with a single `day_zero` switch, rather than a second copy of the regexes. The day-0 and normal readers can't drift apart.
- Day-unknown flags reach `date_flags_raw` because they go through `_date_flags`. No separate code path, so the 4a gate gets them automatically. Mutant (b) shows this is pinned (`test_16b_day00_makes_the_right_show_gate_decline`).
- The tests check exact flag lists, not just `any(...)`. `test_16b_day00_flag_uses_the_surface_text_and_orders_before_yearless` pins the surface text and the ordering in one assertion.
- The 16c test uses the real nested `VettingResult` shape and asserts inside the slice-4b section only, rather than anywhere in the file.
- The mutation table covers all four mutants the brief listed. Each was caught by the predicted test, with shadowing proven.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
- vet_research.py:157: `day_unknown: dict[str, str] | None = None`. The default is never used: both call sites (vet_research.py:271-272, :284) pass it (checked by grep). A future caller that forgets the argument would quietly drop the day-00 flags, which are holds on a strict surface. Make it a required positional and drop `or {}` at :172.
- test_stage_vet.py (Task 16b block): nothing pins the de-dup "first surface text per normalised value". A mutant that emits one flag per asserted text instead of per normalised value would survive. Add `["1991-09-01", "1991-09-00", "September 0, 1991"]` → exactly `["research asserts wrong date: 1991-09-00"]`.
- test_stage_vet.py parametrised list: the `0/5/08` → `2008-05-00` reading the ruling above rests on is not pinned. Add `("0/5/08", "2008-05-00")` so the day-first fallback is a tested decision, not an accident.
- vet_research.py:239-250: `vetting.asserted_dates` is walked twice. These could be folded into one loop. Cosmetic.
- scripts/test_replay_holds.py:728-731: `lose_flag` only wraps `_clear_it`, so pass `_clear_it` directly. The arguments are passed positionally to `_two_arms(tmp_path, mutate_cand, mutate_base)`, which forces the reader to check the signature to see which arm loses the flag. Keyword arguments would make it plain.

### Assessment

**Task quality:** Approved

**Reasoning:** Both changes do what the Checkpoint E decision asks. The day-00 path shares the date parser, reaches both the raw and the windowed flags, and never touches placeholder adoption, and mutation shows all four required behaviours are pinned. What remains is optional hardening: a required parameter and two extra test cases.
