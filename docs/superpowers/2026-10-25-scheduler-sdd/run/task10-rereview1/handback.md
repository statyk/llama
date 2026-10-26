# task10-rereview1: re-review of the Task 10 fix round (9260dbd..d5c84c6), plus the funk diagnosis

Status: DONE. Review only: no commits and no edits to the live tree. Probes ran in scratch copies (`git archive d5c84c6`) under
`/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-scheduler/6a271170-52a3-49a3-b4db-a9d5cd08acfc/scratchpad/rr3/`
(`src` = d5c84c6 as committed, `fix` = the prototype below, `probes/` = scripts). In each copy I checked that `transmitter.__file__` resolved inside it.
**Share access:** I did not scan `/Volumes/media/lma-radio/delivered` at any point in this review, before or after the controller's instruction. Every probe read the existing pickles (`f1/del.pkl`, `f1/elig.pkl`) or the committed JSON. The one `load_pool` call that names the share root returned from the cache before reaching any scan. My baseline harness gives exactly the committed clock-c figures (funk 91/221, median 21.0, 230 within 7 d), so the probes agree with the evidence.

## Finding Verdicts

1. **(Important) Dead misdiagnosis, per-profile figures, re-run on fixed code: ADDRESSED.** evidence.md now attributes the repeats to the Task 8 ranking defect fixed at 9260dbd and to the 17 doubled packages. It gives the before-fix line: 39/413, which I confirmed against the 9260dbd results-a.json. The Dead columns are per-profile (`repeat_gap_days_by_profile.dead`), and every clock was re-run. I spot-checked all nine runs against the JSON and they match: aired/pool, gap min/median, within-7 d (a 403/982, a-ex17 0, a-sym 320, b 4, b-ex17 4, c 403, c-ex17 0, c-elig 290, c-elig-ex17 177), the fill splits, own-profile share, the bends and the per-block fill shares. I also checked the causal claim by probe. On clock a, 402 of the 405 Dead repeats under 7 days are in dead-pm and are doubled packages (13 slugs; 1974-09-11 alone has 163). On clock c, all 404 are in dead-evening and all are doubled.
   - Floor line: it gives both figures with their denominators (0/1150 = 0.0% against (15+17)/1100 = 2.9%), and both match results-a.json and results-naive.json.
   - The excl-17 runs do exclude the 17: `excluded_slugs` is 17 with pool 2769 on a, b and c, and 1 with pool 223 on eligible.
2. **(Minor) UTC weeks: ADDRESSED.** `week_of` now uses local-date 7-day spans, giving 1150, 2100 and 1050 starts with 50 weeks each.
3. **(Minor) scan cache not keyed: ADDRESSED.** The cache is now a pickle `{root, library, pool}`. I checked by probe that a mismatched library or root is refused with SystemExit. Residual gaps (Minor, new): `naive_filler.load_shows` unwraps the dict without checking the key, and the key does not include `extra` or `pause_samples`, which both change lengths.
4. **(Minor) no per-profile repeat gaps: ADDRESSED.** The script now writes `repeat_gap_days_by_profile` (repeats, min, p10, median, max, within_7d) and `distinct_aired_by_profile`.
5. **(Minor) smoke test checks only keys: ADDRESSED, weakly.** It asserts the per-profile gap keys and `0 < dead aired <= pool`. That is a real per-profile figure, but it would not catch a wrong gap value.

Operator additions:
- excl-17 variants of every clock: present.
- dead-am / 12-hour-block table: present.
- ±15 symmetric variant of clock a: present.
- "Before the fix" line: present.

## New Breakage in the Fix Diff

1. **(Important) The bends label is new in this diff and is false as measured.** evidence.md says "Bends by rule (a bend is counted only when a rule-keeping option existed)". The code counts a bend only when a rule-keeping option was *offered* by the bounded search (`_Tier.kept`, `_blocksearch.py:119-129`, `bends()` :152-154). The spec ("What counts as a bend") says *existed*.
   - Measured with an exhaustive enumeration of all in-window singles and pairs, the gap was broken while a gap-keeping (mostly fully clean) option existed but was never offered, and no bend was recorded:
     - clock a dead-family: 35 of 35 gap-breaking first calls;
     - clock c funk-afternoon: 30 of 337.
   - So "c delivered full: bends none" and "a full: {'era': 3}" understate passed-over rules.
   - Smallest correction: relabel ("counted only when the bounded search offered a rule-keeping option") and note the undercount. The underlying search miss is under the funk diagnosis below.
2. (Minor) The "Dead blocks" table rows are inconsistent:
   - "b full | overnight-tribute" and "b excl-17 | dead-evening" name different blocks for the two halves of the pair (all b blocks are 0% anyway);
   - there is no dead-am row for a ±15 and no dead-morning row for c.
3. (Minor) The doubled-packages paragraph reads "the only own shows and pairs that fill the 300-minute dead-am block alone or a 12-hour two-show block". It is true only of single-show dead-am landings, as the later bullet ("fresh pairs land it") shows. It should be reworded.

Nothing else is broken. `_gaps_by_profile` and `fill_share_by_block` are correct, and `--exclude-slugs` filters before `measure`.

## Funk diagnosis

**Root cause: a library/clock limitation, working as the spec's compromise order says.** A search-bound defect explains a small minority of the funk repeats; it is the same defect as new-breakage item 1.

- Clock c's funk-afternoon block runs 14:00 to 20:00 (360 min). Its window is ±15, so own options must land between 345 and 375 min. `max_shows` defaults to 2 for a profile block (`clock.py:294-297`).
- Funk lengths (del.pkl): 221 shows, median 123 min, longest 216. No single show lands.
- Of the 24,310 pairs, 315 land (by arithmetic from block start). Every landing pair contains one of the 8 shows of 183 min or more:
  - newmastersounds-2008-01-18 (216.3; in 76 landing pairs);
  - robertrandolph…-2004-07-25 (214.4; 75);
  - bluestraveler-1991-01-05 (204.0; 52);
  - themotet-2011-10-29 (197.7; 40);
  - then 191.6, 189.3, 185.7, 183.5.
- The block runs 7 times a week, but the 45-day gap lets those 8 shows cover only about 8 of every ~45 blocks. Most blocks therefore cannot land without a gap break.
- Exhaustive probe over 351 blocks: in 337 the chosen option breaks the gap. In 307 of those **no in-window option keeps the gap**, so tier 0 (own landing) beats fill as the spec's compromise order requires ("a block filled from its own profile always beats one that keeps a rotation rule by using fill"). No bend is recorded, correctly under the spec, because nothing kept the rule.
- The sub-week repeats are almost all three long shows: newmastersounds-2008-01-18 (88), robertrandolph…-2004-07-25 (71), bluestraveler-1991-01-05 (68).
- Candidate checks:
  - (1) Dominant-artist adjacency is ruled out. Adjacency is 0 in the chosen options, and 296 of the 315 landing pairs are two different artists.
  - (3) The `used` window and recency are not the cause. Only 5-6 shows are excluded, and recency only picks among options that all break the gap.
  - (4) No doubled funk packages appear in the repeats.

**Concrete block, structural case: 2026-11-10 14:00 local (19:00Z), clock c, full library.**
- Chosen (tier 0): karldensonstinyuniverse-2001-03-08 (143.5 min, never aired, score 1.000) + newmastersounds-2008-01-18 (216.3 min, last aired 7.0 d before, score 0.140). Violations (adj, gap, day, era) = (0, 1, 0, 0), value -0.864, landing -0.1 min (window -15..+15).
- Exhaustive alternatives: 606 in-window options, **0 gap-keeping**. Histogram: (0,1,0,0) 506, (0,2,0,0) 62, (1,1,1,0) 24, …
- Deciding rule: the compromise order (tier 0 over fill), then lexicographic violations, then value. No fresh option lands.

**Concrete block, search-miss case: 2026-12-24 14:00 local (19:00Z), clock c.** Here a fresh, rule-keeping option did land and was never seen.
- Chosen: jjgreyandmofro-2007-08-17 (140.6 min, never aired) + newmastersounds-2008-01-18 (216.3 min, last 4.0 d, score 0.080). Violations (0, 1, 0, 0), value -1.025, landing -3.1 min, tier 0.
- Exhaustive best: radiators-2000-12-15 (172.2 min, last 45.0 d, score 0.900) + georgeporterjr-2018-10-05 (172.9 min, last 47.0 d, score 0.900). Violations (0, 0, 0, 0), value -0.695, landing -14.8 min, tier 0. This option wins on every key, but **it was never offered**.
- Deciding code: `_Search.firsts` (`_blocksearch.py:326-337`). It takes the top `PAIR_FIRSTS` = 32 first members by score among those that pass `_feasible_first`, and `_feasible_first` (:317-324) checks only that some pool length completes the window. Never-aired shows all score 1.0 and tie on sha256 rank, so the 32 firsts are arbitrary fresh short shows (ranks 27 and 91 here). Their only landing partners are the recently aired long shows. The clean pair's members rank 163 and 164.
- The same miss on clock a dead-family, 2026-12-06 15:00 local (20:00Z):
  - chosen: furthur-2013-09-22 (173.9 min) + philleshandfriends-1994-09-24 (66.0 min, last 28 d), (0, 1, 0, 0), value -0.451;
  - unseen: melvinseals-2003-01-25 (115.7) + ratdog-2003-09-06 (126.3), both never aired, (0, 0, 0, 0), value -0.083 (ranks 177/182).
  - This miss causes all 35 of that block's gap breaks, including the weekly (min 7 d) dead-family repeat in results-a.json.

**Verdict: library/clock limitation (primary) plus a minor defect.**
- **Clock-side lever, measured:** clock c with `max_shows = 3` on funk-afternoon only gives funk **221/221 aired, gap min 45.0, median 60.0, 0 repeats within 7 d** (was 91/221, 1.01, 21.0, 230). It adds no misses and no fill. Dead is 406/413 with 441 repeats within 7 d (was 403/413 and 403), because the funk landing shifts dead-evening's start.
- **Defect:** `_blocksearch.py:326-337`. First-member selection ignores whether a rule-keeping partner exists, which also makes the bend tally undercount.
  - Smallest prototyped fix, in the `fix` scratch copy: `firsts(window=True)` puts first members that have an in-range partner not hit by the gap rule ahead of the others, still by score, still capped at 32.
  - It passed 187 scheduler/rules/measure/clock tests. I selected them with `-k`, so this was not the full suite; `test_relay` cannot run in an archive without `antenna/src`.
  - It removes every missed gap-keeping option on clock c funk.
  - Measured effect is small and mixed:

    | run | before | with prototype |
    |---|---|---|
    | clock c funk: aired | 91 | 93 |
    | clock c funk: median gap (d) | 21.0 | 17.0 |
    | clock c funk: within 7 d | 230 | 226 |
    | clock a dead-family: gap min (d) | 7.0 | 34.8 |
    | clock a dead-family: within 7 d | 1 | 0 |
    | clock a dead-family: distinct aired | 43 | 30 |
    | clock a Dead: distinct aired | 384 | 363 |
    | clock a Dead: within 7 d | 403 | 422 |

  - **Not recommended as a drop-in fix.** It is a Task 8 search-design question for the controller/operator. The safe change now is the evidence relabel (new-breakage item 1).

**Other profiles with the same pattern:**
- **clock a ±15, bluegrass: the same structural pattern, and worse than funk.** evidence.md lists 238/307 aired with median gap 3.0 d but does not comment on it.
  - The Mon-Sat 12:00-19:00 block (420 min, landing 405-435) has exactly one landing pair in the library: leftoversalmon-2000-01-28 + yondermountainstringband-2014-02-16.
  - Those two shows account for 295 of the 301 bluegrass repeats under 7 days.
  - With the asymmetric [0,+15] window no pair lands, so the block falls to fill (20% fill share) and bluegrass keeps a 54.5-day median.
  - The ±15 window "fixes" landing and destroys rotation. This should be called out in "Anything surprising" next to funk.
- **clock c eligible, funk (45/89, median 12):** structural. 347 gap breaks, 0 with a gap-keeping option.
- **clock a dead-family (43/225, min 7):** the search-miss defect above.
- **clock a bluegrass (min 2.0, 10 within 7 d):** structural and small.
- **clock b:** no non-Dead profile has a minimum gap under 45 d.

## Out-of-Scope Observations

- **The live tree is dirty, and not from me.** After d5c84c6 was committed, something re-ran `scratchpad/f1/run.sh` into the worktree: 8 tracked `results-*.json` files are modified and `results-c-delivered-ex17.json` is untracked. I diffed them: only `project_seconds` differs, and the untracked file equals the committed `results-c-ex17.json` apart from timing. Good news for reproducibility. But the controller should restore the 8 files (or commit them deliberately) and drop the duplicate. `run.sh` is not committed, and its output names do not match the committed names.
- The spec says the gap rule is "not applied within that pool" when "the pool's eligible airtime is shorter than the gap". Funk on clock c is that case in effect: only ~8 shows can land the window. The implementation still counts gap, which is harmless here because gap ranks below adjacency. The spec clause is unimplemented for length-constrained subsets, and probably should be.
- The spec Intent asks for diversity. Under the compromise order a single landing pair can air almost daily (a ±15 bluegrass). The operator may want a rule about when repeated gap breaks should yield to fill. That is a design question, not a Task 10 defect.

## Verdict

**Fix round: findings remain open (one).** Findings 1-5 and the operator additions are addressed, and the numbers match the JSON.
- One new Important issue, introduced in this diff: the bends label in evidence.md states "existed" where the code counts "offered", and an exhaustive probe found 35 + 30 uncounted passed-over gap-keeping options.
- Recommended evidence edits:
  - relabel the bends;
  - add the a ±15 bluegrass concentration and the funk root cause (structural: 8 long shows carry every landing pair; `max_shows = 3` measured as clearing it);
  - tidy the Dead-blocks table rows.
- The search-miss defect (`_blocksearch.py:326-337`) goes to the controller as a Task 8 follow-up, not a Task 10 blocker.
