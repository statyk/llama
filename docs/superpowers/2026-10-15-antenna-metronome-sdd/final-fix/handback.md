# final-fix handback — antenna metronome final-review fix wave

**Status:** DONE
**Commit:** 76ef024 test(antenna): pin a genuine alarm delivery, the capped write and the duplicate retry; docs: the unabortable PUT
(on antenna-metronome, parent a35208b; nothing pushed, no branch switch, no deploy, no wrangler, no R2)

## What I implemented (all verbatim from final-review/handback.md "Fix-wave list"; zero adaptations)
1. I-1 — antenna/test/metronome.test.ts: `alarmTimes` helper at :34 (beside `pendingAlarm`); new `it` at :80
   "a genuine delivery (the runtime's own, not runDurableObjectAlarm) sees no pending alarm: counted, re-armed later,
   never a duplicate", after "the alarm ticks and re-arms"; the old :68-69 comment replaced with the reviewer's
   wording (runDurableObjectAlarm deletes the alarm first; the next test lets the runtime deliver).
2. I-2 — antenna/test/metronome-alarm.test.ts:279, inside "the PUT cap holds across alarms and renews, and the chain
   still re-arms over it": `expect(port.store.get("lastAlarmGoodAt") ?? null).toBeNull();`.
3. I-3 — antenna/test/metronome-alarm.test.ts:93, new `it` "a duplicate after a tick whose PUT failed writes the
   differing bytes (lastBody is null) and confirms the tick", inside describe("alarm: the tick"), before
   "duplicates after a completed tick".
4. M-1 — docs/playout-setup.md section 9 "Known limitations." paragraph: the reviewer's sentence appended
   (timed-out R2 PUT may still land; older MEDIA-SEQUENCE until next tick, <= ~10 s; no extra spend).
5. M-6 ruling — CLAUDE.md: one blank line inserted before the line starting `**The metronome**` (was :300, now :301).
   Nothing else in CLAUDE.md changed (diff: +1 line).
No antenna/src change.

## Tests (live worktree)
- `cd antenna && npm test` -> `Test Files  20 passed (20)` / `Tests  374 passed (374)` (expected 374: matches)
- `cd antenna && npm run typecheck` -> rc=0
- Item 1 flake check, `npx vitest run test/metronome.test.ts`, six runs, all pass (11/11 each):
  - plain runs 1-3: file Duration 2.37 s, 2.41 s, 2.45 s
  - verbose runs 1-3 (per-test time of the new test): 666 ms, 657 ms, 672 ms (file 2.50 s, 2.26 s, 2.87 s)
  (Faster than the reviewer's 3.2 s because the lease sits 600 ms before boundary 101, so the real alarm fires
  ~625 ms after the renew.) The test is non-vacuous by construction: `seen` must equal exactly `[null]`, so an
  unwired spy (`[]`) or a duplicate-path delivery (`[<number>]`) fails it.

## TDD / mutation evidence (scratch copies only, mandate 5)
Scratch root: /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-antenna-metronome/aab0ffd0-1c39-4c05-9566-1b4fa5339bb1/scratchpad/final-fix/{base,sentinel,i2,i3}
Each built by `git -C <worktree> archive HEAD antenna | tar -x` (HEAD = 76ef024, so the new tests are in it),
node_modules symlinked from the worktree's antenna/, run as `npx vitest run test/metronome-alarm.test.ts`
from `<copy>/antenna` as cwd. `diff -r base/antenna/src <copy>/antenna/src` shows exactly one changed line per mutant.
Predictions were written to the log before any mutant ran.

- base (unmutated): 29/29 passed (as predicted).
- sentinel (engine.ts:55 `const confirms = (_r: WriteResult) => false;`) — predicted red incl. "re-arms first to the
  next boundary, then writes, then confirms the tick". Actual: 7 failed | 22 passed, that test among them
  (`expected undefined to be 1791643850265`). Proves the scratch run imports scratch src.
- I-2 mutant (engine.ts:55 `... || r === "null" || r === "cap"`) — predicted red: exactly "alarm: caps and failures >
  the PUT cap holds across alarms and renews, and the chain still re-arms over it", at the new assertion.
  Actual: 1 failed | 28 passed, that test, `AssertionError: expected 1791643880265 to be null` (the new
  lastAlarmGoodAt check). Whole suite on this mutant: `Tests 1 failed | 373 passed (374)`, same single test.
- I-3 mutant (engine.ts:208 `if (confirms(await this.write(...))) s.lastAlarmGoodAt = now;` -> `s.lastAlarmGoodAt = now;`)
  — predicted red: exactly "alarm: the tick > a duplicate after a tick whose PUT failed writes ... and confirms the tick",
  at `expect(port.puts()).toBe(puts + 1)`. Actual: 1 failed | 28 passed, that test, `expected 2 to be 3`.
  Whole suite on this mutant: `Tests 1 failed | 373 passed (374)`, same single test.
All three predictions matched exactly. The whole-suite runs show each mutant is caught by the new check alone,
consistent with the reviewer's finding that both survive the committed (pre-fix) tests.

## Files changed
- antenna/test/metronome.test.ts
- antenna/test/metronome-alarm.test.ts
- docs/playout-setup.md
- CLAUDE.md

## Self-review
Diff is the reviewer's text verbatim; placement as specified; no stray edits; worktree clean after commit.
Full test output was pristine apart from vitest's usual transform-cache tip.

## Concerns
None. (Item 1 is a real-time alarm test; six runs were 657-672 ms with no flake, and its waitFor allows 5 s.)

Log: .superpowers/sdd/metronome/final-fix/final-fix.log
