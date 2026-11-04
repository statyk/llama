### Spec Compliance

- ❌ Issues found (one):
  - **Misunderstood/vacuous named test:** the brief requires "`tapeLog` and `comingUp` ignore `recent`". The `tapeLog` half is present but cannot fail: antenna/test/timeline.test.ts:141 (diff line 295). `comingUp` is genuinely pinned (test:148). Details under Important.
- All 16 interface exports are present with the specified signatures (timeline.js:7-131). All inline assertions from brief Step 1 are present verbatim. `nowplaying.js` is untouched (the diff stat shows only 2 new files). Only `timeline.js` and `timeline.test.ts` were created, as listed; no extras.
- Global constraints that hold:
  - Hrefs are built only from the encoded slug (timeline.js:125-131); `page`, `notes` and `recent` are never read.
  - `concertDate` uses a literal month array and no `Date` (timeline.js:9, 92-101).
  - Day `00` and partial dates print as stored; `null` gives "" (probe and test:69-72).
  - Times are in the listener's zone, fixed to `en-US` via `formatToParts` (timeline.js:104-119).
- ⚠️ Cannot verify from diff (later tasks):
  - **Task 7 must call `tidyTitle` on each tape-log entry.** Spec line 264 requires " >" in the tape log, but `tapeLog` returns the raw title (the test pins `"Magic Foot>"`, test:128), and the plan never says who tidies it: Task 7 line 521 only says "updates the tape log"; the only `tidyTitle` consumer listed is Task 5's (plan:428). A plain render would ship `Magic Foot>`.
  - **Task 8's `player.playbackMs()` must return a finite number or null.** `positionMs` guards only null, so `playbackMs: NaN` returns NaN (probe), and `findShow` then gives null and the label falls back to the station name. The old `player.js:110` checks `Number.isFinite`; keep that when porting.
  - Task 7's zone line and ticket stubs call `zoneLabel`/`airTime` during rendering. See Minor 1 and Minor 2 for the throwing paths.

### Strengths

- **Review Focus 1 and 4:** `showsOf` funnels every list through a null-safe gate (timeline.js:17-19). A null timeline or one past its last show gives `[]`/null. Shows with unparseable dates drop out of `findShow`, `tapeLog`, `comingUp` and `justAired` because NaN comparisons are false, so `airTime` is unreachable with a bad date from these lists.
- **State boundaries partition cleanly:** a show with `start == atMs` is current, not coming up (`findShow` is `>=`, `comingUp` is `>`). A show with `end == atMs` is just aired, not current (`<` against `<=`).
- **No input mutation:** `tapeLog` sorts a filtered copy (timeline.js:63-64), and `comingUp`/`justAired` do likewise.
- **Review Focus 2 passes:** DST-fold, cross-midnight, Pacific zone, midnight (`12:05a`) and noon (`12:05p`) all correct, by test and probe.
- **Locale spy test is real:** it asserts non-empty and every call `en-US` (test:85-100).
- **Writer checked (risk: fixture and code disagree with real `timeline.json`):** packages/transmitter/src/transmitter/site.py:36,53-60 and pieces.py:181. Only `kind` values `clip` and `track` exist; track titles fall back to the filename, so never null; `slug` is always a string; interstitial rows are not in `shows`; `shows[]` keeps the last 24 h, so `tapeLog`/`justAired` have data. `tapeLog`'s `kind === "track"` filter is safe.
- **`findShow` compared to `findNowPlaying`:** same contract and same logic (risk: contract drift).

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. **antenna/test/timeline.test.ts:141 and :34 (fixture `recent`), :157-159: the "ignores recent" test for `tapeLog` asserts nothing, and `justAired` has no such test.**
   - The fixture's `recent` entry has no `files`, so a `tapeLog` reading `recent` adds no titles, and `not.toContain("wrong")` can never fail.
   - `justAired` is only tested at 15:30, before the fixture's 2030 `end`, so a `recent` entry is filtered out either way.
   - Measured in a scratch copy: a combined mutant making both `tapeLog` and `justAired` concat `timeline.recent` passes 18/18 (predicted survive). Control mutant on `comingUp` is caught by 2 tests (predicted caught), proving the scratch code ran.
   - This matters because the spec's headline rule is that just-aired and the tape log never come from `recent`, and the brief names this test.
   - The fixture's shape is also wrong: the real `recent` is a list of slugs (site.py:62), so also cover that shape.
   - **Fix:** give the `recent` object a `files: [{kind:"track", title:"wrong", start:...}]`, and assert `tapeLog` and `justAired` with exact `toEqual` at a time past that entry's `end`. Add a case with `recent: ["prev-1"]` (real shape) where the expected list excludes or reorders nothing because of it. Check by re-running the mutant above.

#### Minor (Nice to Have)

1. **timeline.js:114-119: the brief's `resolvedOptions().timeZone` fallback is effectively dead.**
   - An engine without `longGeneric` (Safari < 15.4, by my knowledge, not tested) throws `RangeError` from the constructor, before the fallback runs, and that would take down the render. Engines with it always return the part. No test covers the fallback.
   - **Fix:** wrap the formatter in try/catch and fall back to `new Intl.DateTimeFormat("en-US", { timeZone }).resolvedOptions().timeZone`.
   - Related: `UTC` renders "Times shown in GMT+00:00" and `Etc/GMT+5` "GMT-05:00" (measured in node; ICU may differ in browsers). That isn't "in words", but it is only reachable on a device set to UTC. All 12 geographic zones probed gave words. Not worth more than noting.
2. **timeline.js:109 (`airTime(null, ...)` throws `RangeError`).** The brief says helpers handle null fields, and the robustness test (test:165-173) never calls `airTime`, `tidyTitle`, `clipLabel`, `showHref` or `notesHref`, despite "every helper". Unreachable through the list helpers, but a direct `airTime(show.start)` on an unvalidated show would throw, including from Task 9/10's notes data if a field is null. **Fix:** return `{ day: "", time: "" }` on an invalid date and extend the test.
3. **timeline.js:126 (`showHref(null)` gives `/show/null.html`).** Unreachable with today's writer (slug is required), and no validation is requested. Note it for Task 7's `hostile.json`.
4. **timeline.js:50 (`nowLine`).** A clip titled only with a parenthetical gives "" instead of falling through to the artist (probe). Not seen in the writer's data. `f.kind === "clip" ? clipLabel(...) || artist` would close it.
5. **timeline.js:39 (`tidyTitle`).** `"A>>"` gives `"A> >"` and a bare `">"` gives `" >"`. Cosmetic; the spec names only `>` and `->`.
6. **timeline.js:22-34: `findShow` repeats the loop of `nowplaying.js:36-49` verbatim.**
   - The rubric lists verbatim duplication as a defect, so it is flagged. I rate it Minor because the source is frozen and the plan's own pattern for this file set is to copy from it (plan:312-313), so there is no drift path.
   - The brief does not explicitly mandate a copy, only "the same contract". If the operator prefers, `timeline.js` could import from `../nowplaying.js`, but that ties the new page to the rollback file.
7. **Process: brief Step 2 (run the tests, expect FAIL) was skipped.** The implementer's report admits no RED run was captured. The tests are behavioural, so nothing is lost beyond the finding above, which a RED-then-mutate habit is meant to surface. The reported 444-test run is stated as a count with no output in the report. I did not re-run the full suite; I ran test/timeline.test.ts only against the mutants above, never against unmodified code.
8. **timeline.js:71 (`if (out.length >= limit) break`)** is nearly redundant with the inner return. Harmless.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The implementation is correct against the brief and Review Focus 1, 2 and 4; I found no behavioural bug reachable with real `timeline.json` data. The named `recent` test for `tapeLog` is vacuous and `justAired` has none, a mutant proves the spec's headline rule is unpinned, and the fix is a small test-only change.

Checks run: 1 mutant pair plus 1 control in a scratch `git archive` copy (vitest on test/timeline.test.ts only); a node probe of edge inputs against timeline.js; a node probe of `longGeneric` across 14 zones; a read of site.py/pieces.py/player.js:106-113/nowplaying.js:35-50 and of the plan's Task 7. No test was re-run in the live worktree and nothing there was changed apart from this report directory.
