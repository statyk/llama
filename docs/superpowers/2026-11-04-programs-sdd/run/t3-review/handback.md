### Spec Compliance

- ✅ Spec compliant. Every brief export exists in the new module with the brief's signature: `presentsLine`, `occurrenceKey`, `blockSpan`, `localDateKey`, `comingUpGroups`, `lineupDays`, `onAirKey` (antenna/public/assets/programs.js:12-118). `notes.js` gains `presents: presentsLine(notes)` and imports it from `programs.js` (notes.js:4, notes.js:36). `timeline.js` gains no export, and a test pins its export list (programs.test.ts:154-160). `lineupDays` follows Step 3 exactly: no zone arithmetic, day keys from `nowMs + k*12h` with the first seven distinct kept (programs.js:73-84), occurrences bucketed by `localDateKey(Date.parse(nominal_start))`, unparseable starts dropped, sorted by start, the onAir entry unshifted only when its day key sorts before Today's (programs.js:103-106), labels `Today` then `airTime(...).day`. The exact copy (`LMA RADIO PRESENTS`, and the en dash with a space either side in `7:00a – 9:56a`) matches the global constraints (programs.js:7, :27).
- Extra (harmless, reported in the handback): duplicate occurrence keys in a lineup are shown once (programs.js:91-93), and consecutive headless shows merge into one null-key group (programs.js:52-53). Both are consistent with "no block appears twice" and "Coming up is flat with no headings".
- ⚠️ Cannot verify from the diff: whether the `notes` object that `panelModel` receives carries `program` (Tasks 1-2 own the producer side), and whether `panel.js` and the page render `presents` and lineup text through `textContent` (Task 4). Rollout mix to check in Task 4: a cached old `notes.js` beside a new `panel.js` gives `presents === undefined`, so the renderer should fall back to the house line instead of rendering "undefined".

### Strengths

- The rollout constraint is handled with care: `programs.js` imports only the long-standing `airTime` (programs.js:5), and the export-list test makes any accidental `timeline.js` export fail loudly.
- Malformed data is handled well for the lineup: a null or non-array lineup gives null; null occurrences, non-string keys (so `Date.parse(5)`'s year-2005 trap cannot occur, because `occurrenceKey` gates first) and unparseable starts are skipped (programs.js:88-90).
- The DST test discriminates. I worked through the case by hand: naive 24 h stepping from `2027-03-14T04:30Z` (23:30 EST Mar 13) lands on 00:30 EDT Mar 15 and skips Mar 14, so that mutant would fail. Probe: 00:30 local just after the fall-back hour (`2026-11-01T04:30Z`) and just after spring-forward (`2027-03-14T05:30Z`) both give seven consecutive keys with the correct weekday labels.
- The onAir-lead test pins both directions: the entry is present with the key and absent with null. A separate test shows a today-dated onAir entry is not duplicated (programs.test.ts:136-140).
- The NZ case (programs.test.ts:121-123) pins zone-dependent tab placement: if `localDateKey` ignored `timeZone`, the test would fail.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. antenna/test/programs.test.ts:110-124 — the test named "a block just before midnight Eastern lands on the previous day in Los Angeles" does not check a move to another tab. Its fixture, `2026-11-05T04:30Z`, is 23:30 EST and 20:30 PST, both on Nov 4, so both zones put it under Today. My probe confirmed `NY 1000000 / LA 1000000`. Review Focus 2 names the westward move as pinned in Task 3. The code handles it correctly: the probe at 05:30Z (00:30 EST Nov 5) gives NY `Thu:1` and LA `Today:1`. But no test pins it, and the test title claims otherwise. Fix: use `2026-11-05T05:30:00.000Z` and assert `ny[1].entries.length === 1`, `ny[0].entries.length === 0`, `la[0].entries.length === 1`, and `la[0].entries[0].time === "9:30p"`.
2. antenna/test/programs.test.ts:125-131 — the brief's DST test used `LINEUP_WEEK(now)`, a populated week. The implementation passes `{ occurrences: [] }`, so the DST days check only the keys. Nothing checks that blocks on the spring-forward or fall-back day land on the right tab, or that no block appears twice there. Under Review Focus 2 this is coverage, not correctness: bucketing is per-instant `localDateKey`, so it is correct by construction. Fix: add a few occurrences around the transition hour and assert their tab and uniqueness.
3. antenna/public/assets/programs.js:26-28 and :55 — `blockSpan` throws `RangeError: Invalid time value` (from `airTime`'s `formatToParts(new Date(NaN))`) when a `timeline.blocks` entry has a missing or unparseable `start`, or an `end` that is a non-empty string but cannot be parsed. The exception propagates out of `comingUpGroups`. Probe: `comingUpGroups({blocks:[{block:"b",nominal_start:"x",title:"T"}]}, [{block:"b",nominal_start:"x"}])` throws. The transmitter always writes `start` (Task 2), and an old transmitter has no `blocks` at all, so Review Focus 5 is not breached. Still, the lineup path drops unparseable starts and this path crashes Coming up. Fix: treat a blocks entry whose `start` does not parse as absent (headless), and show the start alone when `end` does not parse.
4. antenna/public/assets/programs.js:50 and :113 — `show.block` and `s.start` throw on a null element in `timeline.shows`. The existing `timeline.js` helpers make the same assumption, so this is consistent and only noted.
5. TDD order (implementer's stated caveat): there was no RED run, and the only RED possible was the missing module. Judged on discrimination instead: the 24 h-stepping mutant (DST test), the zone-ignoring mutant (NZ case), dropping the onAir unshift, and dropping the `dayKey < today` guard (the no-duplicate test) would each turn a test red. The one gap is the westward move (item 1).

### Assessment

**Task quality:** Approved

**Reasoning:** The helpers match the brief's interfaces and Step 3 algorithm exactly and degrade correctly on old or malformed lineup and timeline data. The open items are a mis-named zone test that doesn't pin the westward tab move (the code is correct, per my probe), a thinner DST fixture than the brief's, and a throw on malformed block entries that the transmitter never produces.

Checks run: one node probe (scratchpad, read-only import of programs.js, TZ=America/New_York) covering the westward move, the test fixture's tab placement, fall-back and spring-forward keys at 00:30 local, and `comingUpGroups` with a malformed blocks entry; output is in t3-review.log. One focused read of `airTime` (timeline.js:103-111) to check whether it throws on bad input (named risk: the blockSpan throw). One grep of importers of notes.js and programs.js (named risk: rollout mix; only panel.js imports notes.js). No test suite run.
