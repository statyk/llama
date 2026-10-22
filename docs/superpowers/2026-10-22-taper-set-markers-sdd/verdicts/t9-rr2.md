ALL ADDRESSED, NO NEW BREAKAGE

# t9-rr2 scoped re-review, cef2675..a9016b5 (77e5322, 95c735a, a9016b5)

Read-only. Taper and gather tests at a9016b5: `./.venv/bin/python -m pytest packages/llama/tests/test_taper.py packages/llama/tests/test_stage_gather.py -q` gave 558 passed. `git diff main -- packages/llama/src/llama/setlist.py` is empty. No protected name (plan lines 15-31) is touched: the code change is confined to `taper._step1_break_before_set_1`, `TaperDecision`'s comment and `decide_taper`'s comment.

Mutants: scratch `git archive a9016b5` copies under ~/.llama-harness/piece2/accept/work/t9-rr2/<id>, run from an empty cwd with PYTHONPATH shadowing (shadowing proved: `llama.taper.__file__` resolved inside each copy) and a per-mutant PYTHONPYCACHEPREFIX. Predictions were logged first in t9-rr2.log.

## Verdicts

1. **llama-db narrowed ruling: ADDRESSED.**
   - taper.py:788-794 takes `h = hits[-1]` over the same window (`tracks[:last + 1]`, last = set 1's placed boundary - 1).
   - The stand-in item goes through the same loop, so it also uses its own latest hit in the window.
   - `B4_AMBIGUOUS` and its reason string are gone from code and spec. A grep finds them only in mutation.md's historical round-3 rows (lines 277, 309), which is correct as a record.
   - The attribution "(llama-db ruling, 2026-10-22, narrowed the same day)" appears in the docstring (taper.py:784-785), the decide_taper comment (taper.py:836-837) and spec §2:351.
   - umphreysmcgee-2004-04-14's spec §1 positive is restored (spec:264).
   - joerussosalmostdead-2017-03-11 is back in `test_annotated_header_real_cases_own`.
   - Mutant U0 (my own: the uniqueness veto restored before `h = hits[-1]`) turned 7 tests red, all predicted: annotated[joerusso-2017], skb real case, repeated_opener[both], stand_in[both], and the umphreys gather test.

2. **Umphreys owned path end to end: ADDRESSED.**
   - `test_umphreys_2004_04_14_taper_owned_identical_to_today` (test_stage_gather.py:3589) is back to the pre-6a117f2 owned assertions verbatim: `taper_owned is True`, labels equal to the oracle, set_breaks [11, 18], trailing encore, review_flags and alignment equal to the oracle, `_was_notes == []`. A comment was added.
   - It goes red under U0, so it now also pins the narrowing end to end on a real fixture.

3. **Spec §2 "Measured declines" wording: ADDRESSED.**
   - Spec:356-360 now reads "Illustrations from the real-case test fixtures, not a population measurement".
   - Its three claims match the tests: skb declines against its latest hit, and umphreys and joerusso-2017 stay owned.

**Extra check: is "before" exact, with h the latest hit? YES.**
- taper.py:795-798 scans `range(min(h, len(today_sets) - 1))`: a change between k and k+1 for k < h. So h-1→h counts and h→h+1 does not.
- Mutant Bm1 (`range(min(h - 1, ...))`) is caught by:
  - `test_step1_break_before_set_1_real_case_declines`, on its constructed "between" step 1: h=8, break at k=7=h-1, so this is the latest-hit boundary;
  - `test_step1_break_just_before_the_hit_declines`;
  - `test_set_1_first_item_with_no_hit_uses_the_next_set_1_item`.
- Mutant Bp1 (`range(min(h + 1, ...))`) is caught by 6 tests, including `test_a_repeat_after_set_1_is_outside_the_window` (h=0, break at h→h+1 must not count) and `test_no_step1_break_before_set_1_stays_owned[2,3]`.

**Extra check: is the stevekimockband-2000-03-31 constructed step 1 a sound pin? YES.**
- The implementer is right that the real step 1 [6,13] breaks before both hits (0-based 6 and 8), so it cannot tell latest from earliest.
- The constructed `["1"]*8 + ["2"]*5 + ["3"]*6` breaks only at k=7, between the hits. It uses the real tape text and track names for placement, and it reaches B4: the asserted reason is `veto: step-1 break before set 1`, not an earlier veto.
- B4 consumes today_sets as a plain input, so a synthetic step 1 is a legitimate way to separate the readings.
- My L1 mutant (`hits[0]`) turned exactly 3 tests red, matching the implementer's re-run: the skb real case, repeated_opener[today0] and stand_in[today0].
- The pin is labelled hypothetical in both the test comment and mutation.md.

## New breakage
None (Critical / Important / Minor: none).

## Deferred minors
- Spec §2:354, "with no step-1 break in that window the taper still owns the structure", states a sufficient condition loosely. The actual condition is "no numbered step-1 break before the latest hit": a step-1 break between the latest hit and set 1's placed boundary is in "that window" yet still owned. The preceding clause and the docstring are exact, so this is only wording. Suggested: "with no step-1 break before that hit".
- The probe table in t9-fix4's handback infers "no step-1 break before the latest hit" for 14 shows from B4 passing at gate8, which the implementer discloses. That is fine as evidence of ownership, not of the reason.
