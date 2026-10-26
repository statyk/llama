### Finding Verdicts

Scope and method: read-only review of d5c84c6..e6e56a5. I did not access `/Volumes/media/lma-radio/delivered`, ran no measurements, made no edits and spawned no subagents. Every figure was checked against the committed `results-*.json` (with `./.venv/bin/python -c`; `transmitter.__file__` resolves inside the worktree) or against task10-rereview1's handback and its probe scripts. The working tree is clean at e6e56a5; the dirty results files that rereview1 reported are gone.

1. **Bends label and undercount: ADDRESSED.**
   - The label now reads "a rule-keeping option was **offered by the bounded search**".
   - A new note, "Bends are undercounted", gives the probe figures exactly as rereview1 reported them: dead-family 35 of 35 gap-breaking first calls, and c funk 30 of 337. It labels them "the review's exhaustive probes (scratch copies, not committed runs)".
   - It names the cause (`_blocksearch.py` first-show selection ignores whether a rule-keeping partner exists) and calls it a Task 8 follow-up.
   - The figures it cites match the JSON: dead-family 43/225 aired with a 7.0-day minimum (results-a.json), and c delivered full bends `{}`.

2. **Funk root cause: ADDRESSED, with a minor labelling gap (see New Breakage 1).**
   - These match rereview1: 14:00-20:00 (360 min), `max_shows` 2, the 8 shows of 183 min or more, the top three repeaters, and 307 of 351 blocks with no gap-keeping option.
   - The `max_shows = 3` results (221/221, minimum 45 d, median 60 d, none within 7 d, no misses, no fill) are labelled "Reviewer probe figures (scratch copy, not a committed run)".
   - These match results-c-delivered.json: 91/221, median 21.0, 230 repeats within 7 d. Clock a's funk figures (61/221, minimum 48.97) also match.

3. **±15 bluegrass concentration and the operator question: ADDRESSED in substance, with one number mismatch (see New Breakage 1).**
   - The one landing pair and the Mon-Sat 12:00-19:00 block are right: in clock-a-sym.toml the bluegrass block ends at dead-pm Mon-Sat and at dead-family on Sunday.
   - These match the JSON: 238/307 aired and median 3.0 (results-a-sym.json); 20% fill (results-a.json bluegrass fill share 0.2016) and the 54.5-day median.
   - The operator design question is present.

4. **Dead-blocks table and the "only own shows" sentence: ADDRESSED.**
   - All 18 rows match `fill_share_by_block` / `own_profile_share_by_block`:
     - a excl-17 dead-pm: 0.4092 / 0.5908;
     - c delivered excl-17 dead-evening: 0.4648 / 0.5352;
     - c eligible full dead-evening: 0.2679 / 0.7321;
     - c eligible excl-17 dead-evening: 0.4205 / 0.5795;
     - every other Dead row is 0.0 / 1.0.
   - The b overnight-tribute line (0% fill in both runs) matches.
   - Every full/excl-17 pair now names the same blocks.
   - The doubled-packages sentence now limits "only" to single-show dead-am landings and notes that fresh pairs also land dead-am.

5. **Scan-cache key: ADDRESSED.**
   - `naive_filler.load_shows` now checks `{root, library: "delivered", pause_samples, extra}` and raises SystemExit on a mismatch.
   - `measure_scheduler.load_pool` checks and writes the same four keys.
   - Both scripts default pause to 0.75 s (`PAUSE_SECONDS = 0.75`), so a cache written by `measure_scheduler` is readable by `naive_filler`.
   - `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_measure.py -q` gives 3 passed. The measure test covers library, pause, extra and root mismatches. The naive test covers root and extra only (see New Breakage 3).

### New Breakage in the Fix Diff

1. **(Minor) Some probe figures in evidence.md are unlabelled, and one disagrees with the committed JSON.**
   - "Anything surprising" item 6 says the pair accounts for "295 of the 301 bluegrass repeats under 7 days" and that "only one pair lands it". Both are reviewer-probe figures, but nothing in the item says so.
   - The committed results-a-sym.json gives bluegrass `within_7d` = **300**, not 301. The probe (`rr3/probes/rows.py`) ran over a 350-day horizon rather than the measured 50 local-calendar weeks, hence the difference of one.
   - In item 1, "only the 8 funk shows of 183 min or longer", the top three repeaters and "307 of 351 blocks" are also probe-derived. 351 is the probe's horizon; the committed run has 350 blocks. They appear before the bold probe label, which reads as covering only the `max_shows = 3` figures.
   - Smallest fix:
     - mark those sentences "(reviewer probe, scratch copy)";
     - give the committed count, for example "295 of the 301 sub-week repeats in the probe (300 in the committed run)".
   - The figures do not change any conclusion, but the brief asks that probe figures be labelled.
2. **(Minor) The wording slightly overstates the funk conclusion and leaves out the side effect of the `max_shows = 3` lever.**
   - "A library/clock limitation, not a defect" conflicts with the bends note two sections earlier, which puts 30 of the 337 funk gap breaks down to the search-miss defect. Rereview1's verdict was "library/clock limitation (primary) plus a minor defect".
   - The probe also found that `max_shows = 3` moves the start of dead-evening, which puts Dead at 406/413 with **441** repeats within 7 d (403 before).
   - Without that, an operator could read the lever as free.
   - Suggest "primarily a library/clock limitation", and add the Dead side effect to the probe sentence.
3. **(Minor) The test does not pin all of naive_filler's key.** `test_naive_scan_cache_refuses_a_mismatch` exercises only root and extra mismatches, so removing `pause_samples` or `library` from naive_filler's key would still pass. One more `pytest.raises` with `pause_samples=1` closes this.
4. **(Minor, stale text left by the fix)** "What was run" (evidence.md line 43) still says the scan cache is "keyed by root and library". It is now keyed by root, library, pause and extra.

Nothing Critical or Important.

### Out-of-Scope Observations

- `naive_filler.load_shows` now calls `aacenc.extra_frames()` (ffmpeg) before it reads the cache. Before this change, a cached run needed no ffmpeg. This only matters if the script is re-run on a machine without ffmpeg; the `--extra`-style parameter exists but the CLI does not expose it.
- As the fix handback says, the existing scratch pickles do not have the new keys, so they will be refused on any re-run (by design).

### Verdict

**Fix round: all findings addressed, no new Critical/Important breakage.** Findings 1-5 are all addressed, and every committed-JSON figure the fix adds matches.

Four Minor items remain:
- probe labelling in "Anything surprising" items 1 and 6, including 301 against the committed 300;
- the funk "not a defect" wording and the missing Dead side effect of `max_shows = 3`;
- the naive test's missing pause/library cases;
- the stale "keyed by root and library" line.

Fixing the first two is advisable before the operator reads the doc, but they do not block it.
