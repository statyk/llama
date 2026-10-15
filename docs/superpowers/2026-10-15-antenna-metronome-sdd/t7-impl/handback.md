# t7-impl handback: Task 7, cron's lease table, the fallback decision, metronome-down

**Status:** DONE_WITH_CONCERNS (one concern, below; nothing blocking)
**Commit:** b54e6e2 feat(antenna): cron renews the metronome on every path and falls back only when it looks dead (on b737d8b)

## What I implemented
Applied the brief's edits verbatim, with each `old` anchor checked to occur exactly once:
- src/alerts.ts: added `metronome-down` to CLOCK_KEYS.
- src/clock.ts, all 14 edits: `ClockDeps.metronome?`, `ClockResult.metronome`, `MetronomeLine`, the `renew` closure (it calls fallbackReason, logs a `metronome-down` event and pushes the condition), renew(null) on guard unknown/crashed, `unusable()` (hold if blocked, else null) on read-threw / horizon-missing / gridOf-threw, renew(hold) on refused, `noteOffairWithoutFallback` hoisted out of `write` and raised before the lease, and the play renew (healthy ⇒ complete=true, return; otherwise the legacy loop).
- src/index.ts: `metronome: env.METRONOME === "on" ? metronomeClient(env.METRONOME_DO) : undefined`.
- test/alerts.test.ts: the brief's one-line change. test/clock-metronome.test.ts: the brief's file, with one adaptation (below).

## Test adaptation (required by carry-t7's trigger (b) lease check)
test/clock-metronome.test.ts:180-186 ("offair-without-fallback is raised by cron from its own inputs even though the DO writes"):
- old: `metronome: fakeMetronome().client`
- new: `metronome: fakeMetronome(() => healthy({ lease: "blocked" })).client`, plus a comment and one added assertion `expect(out.keys).not.toContain("metronome-down")`.
- Why: the test sends a blocked play lease (guardSays(true, true)). The default fake answers `lease: "play"`, and the revised trigger (b) correctly reads that as a mismatch (`s.lease !== "blocked"`). The fallback loop then ran and made 1 cron PUT, so `playlistPuts(bucket)` was 1, not 0. A healthy DO answers a blocked lease with lease "blocked". The added assertion proves the fake now really reads as healthy. This is the only test that changed; no reason-string assertions needed adapting.

## Tests
- RED: `cd antenna && npx vitest run test/clock-metronome.test.ts test/alerts.test.ts` gave 21 failed: the alerts key-set test (8 vs 9 keys), plus 20 new tests failing as the brief predicts (`m.sent` was `[]`, `r.metronome` undefined, `metronome-down` absent, 8 cron PUTs where 0 were expected). Two new tests passed before the change, and that was expected: they assert behaviour that already exists (the cron off-air PUT on "a blocked lease the DO did not write", and an incomplete batch on guard unknown).
- GREEN, focused: 63 passed (63). The first GREEN run failed only the test adapted above.
- Full: `cd antenna && npm test && npm test && npm run typecheck` gave `Tests  371 passed (371)` both times, tsc silent, exit 0. That is the expected 371 (349 + 22). Every pre-existing clock test passes unchanged.
- `npx wrangler deploy --dry-run --outdir <scratchpad>/antenna-dryrun`: Total Upload 85.01 KiB / gzip 23.38 KiB; `env.METRONOME_DO (Metronome)` and `env.METRONOME ("off")` listed; `--dry-run: exiting now.`
- Log: $D/t7-impl/t7-impl.log

## Report-only checks
1. **renew exactly once per path, with the table's argument.** Guard unknown or crashed: renew(null), then return. Read threw: renew(unusable()), then throw. Horizon missing: renew(unusable()). Refused: renew(hold) whatever the verdict. gridOf threw: renew(unusable()). Accepted: renew(play{blocked, horizon, fallback}), then either return complete or run the loop (a later throw from the loop, such as a failed PUT, does not renew again). An index.html failure does not return, so it falls through to the paths above. With `deps.metronome` absent, `renew` returns null without calling anything, and the `if (deps.metronome && …)` guard skips the lease branch: the loop is exactly as before (all old clock tests pass unchanged). The only code between the guard and the play renew that could throw outside a renew'd catch is the lead arithmetic and `offairWithoutFallback(src, …)` (pure; renderLive already ran the same isOffair logic on the same inputs before this change). A throw there would reach the catch with zero renews. I see no way for it to throw.
2. **metronome-down on every trigger.** It is raised inside `renew`, so every fallbackReason trigger raises it whatever the path: guard unknown with renew throwing (tested), an unanswered hold on a refused horizon (tested), and renew(null)/hold answering stalls ≥ 2. The loop runs only on the play path.
3. **Trigger (a) with the guard still running.** The guard step always runs first; renew comes only after it. A throw, timeout or missing binding (metronomeClient throws "the METRONOME_DO binding is missing") is caught inside `renew` as trigger (a), and the play path then runs the full loop (tested: 8 PUTs, the off-mode count).
4. **The Task 5 corner (three renews in one 10.24 s segment).** The wiring adds exactly one renew per invocation and never more, and a healthy invocation returns right after its renew, so a healthy metronome causes no overlap. Three renews inside one segment need three invocations firing within 10.24 s. Fire time ≥ scheduled time and schedules are 60 s apart, so the first fire would need a lag of about 110 s or more, plus a blocked/hold-then-play verdict flip in between. The wiring cannot produce that by itself. It is not provably impossible under extreme cron lag (lags > 75 s were seen on 10-13), but it is far outside what was measured.

## Self-review / concerns
- **CONCERN, strict-surface adjacent: "renew never throws" fails for a non-object reply.** `metronomeClient` returns the stub's reply without validating it. If a skewed or broken DO ever answered `undefined`/`null`, `fallbackReason` would throw a TypeError on `s.applied` inside `renew`. On the play path that throw escapes `renew` before the fallback loop, so the invocation ends in `clock-failed` + ClockError, with no `metronome-down` and no fallback write. That fails closed on spend (nothing is written), but the station is left without the fallback, and the `renew` doc comment's "Never throws" is wrong in that case. Any object reply, `{}` included, is handled: it trips (b) or (c). I left it alone: it lives in metronome-core's `fallbackReason` (or the client), outside this task's file list and the brief's verbatim code. Suggested fix, if wanted: in `renew`, treat a non-object `status` as `{ error: "renew returned a non-object" }`, or validate in `metronomeClient`.
- Otherwise the diff matches the brief verbatim. Names are clear, the test output is clean (every console.error/log in the new tests is mocked), and nothing beyond scope was added.

## Files changed
- /Users/shawn/projects/llama/.claude/worktrees/antenna-metronome/antenna/src/clock.ts
- /Users/shawn/projects/llama/.claude/worktrees/antenna-metronome/antenna/src/index.ts
- /Users/shawn/projects/llama/.claude/worktrees/antenna-metronome/antenna/src/alerts.ts
- /Users/shawn/projects/llama/.claude/worktrees/antenna-metronome/antenna/test/alerts.test.ts
- /Users/shawn/projects/llama/.claude/worktrees/antenna-metronome/antenna/test/clock-metronome.test.ts (new)

## Fix round 1 (code-quality Important: `renew` could throw)
**Commit:** 0b59b70 fix(antenna): renew never throws: a non-object reply or an unprintable rejection is trigger (a)

**Changes (src/clock.ts, inside `renew` only):**
- The reply is read as `unknown`. Any reply where `typeof status !== "object" || status === null` becomes `{ error: "renew returned a non-object" }`, so it is trigger (a).
- The rejection's message is stringified inside its own `try`, falling back to `"unprintable rejection"`. `String(Object.create(null))` throws "Cannot convert object to primitive value", checked with node.
- `renew` can no longer throw, so its "Never throws" doc comment is now true. The play path falls back and raises `metronome-down`, `result.metronome` is always set, and `clock-inputs` is no longer hidden on the read-threw and gridOf paths.

**Covering test:** one new `it` in test/clock-metronome.test.ts, in the fallback describe: "a non-object reply or an unprintable rejection is trigger (a): renew never throws, the loop runs".
- It loops over two answers: `() => undefined as unknown as MetronomeStatus` and `() => { throw Object.create(null); }`.
- For each it expects no throw, `puts` 8, `metronome-down` raised, and `r.metronome` matching `{ sent: "play", status: null, error: <string>, fallback: <string> }`.

**RED (on 0b59b70's parent, b54e6e2 code):** `npx vitest run test/clock-metronome.test.ts -t "non-object reply"` gave 1 failed: `expected ClockError: Cannot read properties of und… to be null`, with cause TypeError. That is the undefined arm. The loop stops at the first failure, so the `Object.create(null)` arm was not separately shown RED. Its pre-fix throw is established by the node check above: `String()` ran in the old catch with no guard.

**GREEN:** `cd antenna && npm test && npm run typecheck` gave `Tests  372 passed (372)` and tsc clean, exit 0. That matches the expected 372.
