# task10-rereview3 handback

Scope: read-only review of the fix diff e6e56a5..f28dbd0 (evidence.md, test_measure.py). I did not access /Volumes/media/lma-radio/delivered, ran no measurements, made no edits or commits and spawned no subagents. `transmitter.__file__` resolves inside the worktree, and the working tree is clean.

### Finding Verdicts

1. **Unlabelled probe figures: ADDRESSED.**
   - Item 1 now opens with "Committed run (clock c delivered)". Those figures match results-c-delivered.json: funk 91/221, median 21.0, within_7d 230, at `max_shows` 2.
   - It then says "The rest of this item is **reviewer probe, scratch copy**". That label covers the 8 shows of 183 min or more, the top three repeaters and "307 of 351 blocks in the probe (the committed run has 350 blocks)". `miss_by_block["funk-afternoon"]` is [0, 350] in the JSON.
   - Item 6 gives the committed figures first, which match results-a-sym.json: bluegrass 238/307, median 3.0, within_7d 300.
   - Its probe figures are labelled "Reviewer probe, scratch copy (350 days)": the one landing pair, and "295 of the 301 sub-week repeats in the probe (300 in the committed run)".
   - The [0,+15] figures are marked "(committed)" and match results-a.json: bluegrass fill share 0.2016, median 54.5.

2. **Funk wording and the `max_shows = 3` side effect: ADDRESSED.**
   - The text now reads "primarily a library/clock limitation; per the bends note, 30 of the 337 funk gap breaks are the search-miss defect". That is consistent with the bends note at evidence.md line 91.
   - The side effect is added and labelled as a probe: the change shifts dead-evening's start, and Dead airs 406/413 with 441 repeats within 7 days.
   - The "(403 in the committed run)" it compares against matches results-c-delivered.json: dead within_7d 403, aired 403/413.
   - Clock a's funk figures are marked "(committed)" and match results-a.json: 61/221, minimum 48.97.

3. **Naive cache test: ADDRESSED.**
   - `test_naive_scan_cache_refuses_a_mismatch` now adds a `pause_samples=1` case.
   - It also adds a library case: the cache is rewritten with `library="eligible"`, while `naive_filler` hard-codes "delivered".
   - The only `SystemExit` in that path is the key check (naive_filler.py lines 65-70), so each case fails only on its own key.
   - By inspection, a mutant that drops `pause_samples` or `library` from the key would load the cache and fail the test. The fix report says scratch mutants confirmed this.
   - `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_measure.py -q` gives **3 passed**.

4. **Stale cache-key text: ADDRESSED.** evidence.md line 42 now reads "keyed by root, library, pause and extra", which matches the key in both scripts.

### New Breakage in the Fix Diff

None. One cosmetic nit, which does not block:
- Item 6 labels the probe "(350 days)", but the committed run is also 50 weeks, which is 350 days.
- The real difference, per rereview2, is the probe's day horizon against the run's local-calendar weeks (DST). A reader may wonder why 350 days gives 301 where 50 weeks gives 300.
- It could read "(350-day UTC horizon)", but the numbers are correctly attributed as it stands.

### Verdict

**Fix round: all findings addressed, no new Critical/Important breakage.**
