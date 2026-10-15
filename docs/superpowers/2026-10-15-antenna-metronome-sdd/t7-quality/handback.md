# t7-quality: code-quality review of Task 7 (b737d8b..b54e6e2)

**Task quality: Needs fixes.** There is one Important finding: `renew`'s "Never throws" guarantee is false on the spend-decision path. The fix is two lines, all inside `clock.ts`.

### Strengths
- The lease table is enforced by one place. `renew` (clock.ts:244-262) is the only route to the DO, `fallbackReason` and `metronome-down`. Each early return or throw calls it once, just before it leaves (clock.ts:281, 308, 316, 325, 332, 358). With the switch off it is a no-op (`if (!deps.metronome) return null`).
- The play gate `deps.metronome && (await renew(...)) === null` (clock.ts:358) fails closed. With the metronome off, the loop runs. With it on, any trigger runs the loop. Only an explicit null reason skips the loop.
- The rollback switch compares against the exact string (index.ts:28: `env.METRONOME === "on"`).
- The off-air-without-fallback raise was hoisted into a once-only `noteOffairWithoutFallback` (clock.ts:346-355). That removes the duplicate block it would otherwise have needed, and lets cron raise the alert from its own inputs even when the DO writes.
- `complete = true` on the healthy path comes after every condition is computed: guard, index, lead-low, offair-without-fallback. So a healthy minute truly clears `metronome-down`.
- The test adaptation (clock-metronome.test.ts:186-188) is correct and minimal. It also adds a `not.toContain("metronome-down")` assertion, which proves the fake reads as healthy.
- Mutants checked by reading, each with the test that catches it:
  - drop `deps.metronome &&` at :358: off mode would return without writing; the handler "METRONOME off" test (`puts 1`) and every pre-existing clock test catch it.
  - `unusable()` always null: caught by the blocked-inputs test (expects a hold).
  - refused passes `unusable()`: caught by the unblocked-refused case (expects `["hold"]`).
  - `verdictAt = deps.now()` instead of `startedMs`: caught by the guard-sleeps-2 s test.
  - drop the gridOf-catch renew: caught, because `badEpoch` reaches `gridOf` (grid.ts:25 throws) and expects `[null]`/hold.
  - truthy check instead of `=== "on"` in index.ts: caught by the off handler test (`metronome` null).
  - drop `complete = true` on the healthy path: caught by the batch assertion.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
- **clock.ts:242, 253: `renew` can throw, although its doc comment and every call site assume it cannot.**
  - **The cause:** `fallbackReason` (metronome-core.ts:303-309) reads `s.applied`/`s.stalls` on the reply without checking it, and runs outside renew's `try`.
  - **What triggers it:** a reply that is `undefined` or `null` makes `renew` throw a TypeError. That happens on every lease kind: on a play lease at `s.applied`, on null or hold at `s.stalls`. Also, `String(e)` at :251 throws for a rejection value like `Object.create(null)`.
  - **Consequences:**
    - (1) On the play path, a broken DO, the exact case the fallback exists for, gets no fallback loop and no `metronome-down`. The run ends in `clock-failed`.
    - (2) `result.metronome` is never assigned, so the clock line shows `metronome: null`, which is how "switch off" looks. The operator's main diagnostic misreports the switch.
    - (3) On the read-threw and gridOf paths (:308, :332), the throw replaces `throw failedInputs(e)`. So `clock-inputs` and the real input error are hidden behind `clock-failed` and a TypeError.
  - **Severity:** it fails closed on spend (nothing is written) and it is alerted (urgent `clock-failed`). Today's engine always returns an object (metronome-engine.ts:250, 272, 308), so reaching it needs a DO regression or an RPC oddity. I still rate it Important: it is a false contract on the strict surface, and the failure costs continuity exactly when the DO is broken.
  - **Fix:** in `renew`, after the await, treat `typeof status !== "object" || status === null` as `r = { error: "renew returned a non-object" }` (trigger (a)). Or wrap the reason computation in the same try, so that any throw becomes trigger (a) and "Never throws" holds by construction. Add one test: `fakeMetronome(() => undefined as unknown as MetronomeStatus)` on the play path, expecting `puts 8`, `metronome-down`, and `r.metronome.fallback` set.

#### Minor (Nice to Have)
- **clock.ts:246:** the `sent` label repeats the `blocked ? "blocked" : "play"` mapping in `fallbackReason` (metronome-core.ts:305-306). If one changes without the other, the clock line and the trigger disagree. This is a small duplicate; one shared helper would remove it.
- **clock.ts:355:** with the switch off, `offair-without-fallback` is now raised before the loop, from a `deps.now()` read just before the first write, not from that write's own render. The result is the same within milliseconds and once per invocation. This is a small departure from "off ⇒ exactly as before", harmless as built.
- **Test gaps (coverage only):**
  - no `runClock`-level test of a non-`Error` rejection (the `String(e)` arm);
  - no test that renew timing out after the DO already accepted gives two bounded writers;
  - no test of `metronome-down` with stalls ≥ 2 on a renew(null) or hold path (loud, and the loop must not write).

### Checks run
- Read the diff once. Focused checks, each for a named risk:
  - **Does the reply ever come back as a non-object?** Read `fallbackReason` (metronome-core.ts:300-313), `metronomeClient` (metronome.ts:72-90) and the engine's `renewSteps` return sites (metronome-engine.ts:250, 272, 308): every return is an object; the client does not validate.
  - **Is the gridOf-catch renew covered?** It is: grid.ts:23-29 shows `badEpoch` throws in `gridOf`.
  - **Is the play gate safe with the switch off?** Read clock.ts:355-404: the loop and the catch are unchanged.
- No tests run: none were needed, because the non-object throw follows directly from metronome-core.ts:303-309.
