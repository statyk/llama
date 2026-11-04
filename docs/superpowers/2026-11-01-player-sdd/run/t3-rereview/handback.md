### Finding Verdicts

- **Important 1: the `tapeLog` "ignores recent" test asserted nothing and `justAired` had no such test** — ADDRESSED.
  - Fixture: `recent[0]` now has a track file titled "wrong" (antenna/test/timeline.test.ts, diff line 27-28), so a `tapeLog` reading `recent` does add a title.
  - `tapeLog`: exact `toEqual` at `late` = 2030-06-01, past the entry's 2030-01-01 `end` (:141-150). `recent: ["prev-1"]` compared with the same call on `{ shows }` alone (:151-152).
  - `justAired`: new test "justAired ignores recent, whatever its shape" (:171-176), exact `toEqual` on slugs at `late`, for both the object fixture and `recent: ["prev-1"]`. `limit` 10 means a duplicate or added entry is not cut off by the default limit of 6.
  - The slug shape is the real one: site.py:62 builds `recent` as a slug list.
  - Mutant re-run: reported in the fix report (object entries concatenated in `showsOf`, CAUGHT, 4 failed / 15 passed). That mutant skips string entries, and `showsOf` also feeds `comingUp`, so it did not separate the sites or test the slug assertions. I ran per-site mutants to settle that (below).

Check run (read-only on the live tree; scratch copy of `antenna/` at 03e513f7 with its own cloned `node_modules`, `.vite`/`.cache`/`.mf` removed, `npx vitest run test/timeline.test.ts`). Predictions were written to t3-rereview.log before any run. All six matched, including the failing line:

| Mutant | Predicted red | Result | Failing line |
|---|---|---|---|
| control (no change) | none | 19 pass | - |
| M1 `tapeLog` concats object `recent` entries | tapeLog ignores recent, first `toEqual` | 1 failed / 18 passed | :143 |
| M2 `justAired` concats object entries | justAired ignores recent, first expect | 1 failed / 18 passed | :174 |
| M3 `tapeLog` resolves slug entries to shows | tapeLog, `slugsOnly` expect only | 1 failed / 18 passed | :152 |
| M4 `justAired` resolves slug entries | justAired, second expect only | 1 failed / 18 passed | :175 |
| M5 the review's combined mutant: both raw-concat `recent` (null-safe) | those two tests | 2 failed / 17 passed | :143, :174 |

The mutants are null-safe, so none of these failures come from `tapeLog(null, 0)` or `justAired(null, 0)` throwing. M5 is the mutant that passed 18/18 at the previous review.

### New Breakage in the Fix Diff

None. The diff is test-only (antenna/test/timeline.test.ts, +19/-2). timeline.js is unchanged. The fixture change leaves the existing `comingUp` "ignores recent" test intact, because that entry still starts in 2030. Control run 19/19.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
