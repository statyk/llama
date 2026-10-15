# t6-review: Task 6 (the Metronome DO, binding, migration v1, switch), 72858f6..b737d8b

**Spec compliance: Pass. Task quality: Approved** (no Critical or Important findings; 4 Minor).

## SPEC SEAT

### Spec Compliance
- ✅ Spec compliant. All six listed files carry their hunks, and the code matches the brief verbatim: `antenna/src/metronome.ts` (Steps 3), `src/env.ts` (Step 4), `src/index.ts` re-export only, no wiring (Step 5), `wrangler.jsonc` three edits (Step 6), `test/metronome.test.ts` and the three `wrangler-config.test.ts` cases (Step 1), inserted before the A4 describe as instructed.
- Produced interfaces exist with the stated shapes: `class Metronome extends DurableObject<AntennaEnv>` with `renew(lease: Lease | null): Promise<MetronomeStatus>` and `alarm(): Promise<void>` (metronome.ts:16-59); `MetronomeNamespace` (metronome.ts:62-65); `metronomeClient(ns | undefined, timeoutMs = RENEW_TIMEOUT_MS)` (metronome.ts:71); `AntennaEnv.METRONOME_DO: DurableObjectNamespace<Metronome>` (env.ts:10-11); `export { Metronome }` (index.ts:7).
- Constants: `METRONOME_NAME` used by the client (metronome.ts:77); renew bound is `RENEW_TIMEOUT_MS` = 15_000 (metronome-core.ts:26); the PUT bound is the engine's `DO_PUT_TIMEOUT_MS` = 5_000 (metronome-core.ts:24), raced against the DO's `timer` port in `boundedPut` (metronome-engine.ts:131-143). Switch is `this.env.METRONOME === "on"` exactly (metronome.ts:25).
- Migration form `migrations` + `new_sqlite_classes`, tag `v1`, no `exports` (wrangler.jsonc, durable_objects/migrations lines); `"METRONOME": "off"`; observability comment updated.
- Report-only check 2: the DO's `renew` (metronome.ts:53-55) forwards the argument unchanged; nothing in the DO or client gives `undefined` a meaning. ✅
- Report-only check 3: `wrangler.jsonc` carries no account ID, zone ID, token value or address (grep for `account_id|zone_id|@domain|"token":` hits only the pre-existing comment naming the secret NAMES, line 32). I re-ran `npx wrangler deploy --dry-run --outdir <scratchpad>` from a scratch copy (git archive of b737d8b): binding table lists `env.METRONOME_DO (Metronome)  Durable Object` and `env.METRONOME ("off")`, then `--dry-run: exiting now.`; no line matching warn/migration/export/error.
- ⚠️ Cannot verify from diff: `docs/playout-setup.md section 4 step 7` (cited in the wrangler.jsonc switch comment) does not exist yet in this diff; presumably a later docs task writes it. Cron's use of `metronomeClient` and the trigger (a) handling are Task 7.

### Issues
#### Critical (Must Fix)
None.
#### Important (Should Fix)
None.
#### Minor (Nice to Have)
- See quality-seat Minor 1 (the workerd-delivery test's premise is supplied by the test helper). It is the brief's own test, implemented verbatim, so it is not a spec deviation.

### Verdict
**Spec compliance:** Pass

## QUALITY SEAT

### Strengths
- The DO is a pure binding: every rule stays in the engine; metronome.ts is 90 lines with one responsibility.
- `this.env` is read inside each closure on every call (`switchOn`, `config`, `putLive`; metronome.ts:25-26, 42). Mutant check: capturing the switch at construction (`const on = env.METRONOME === "on"`) or reading the constructor's `env` parameter is caught, because `setSwitch` replaces `this.env` after construction and the "on: renew writes" test then fails on `applied: "accepted"`. Mutant `!== "off"` is caught by the exact-string test ("On", "on ", "1", "true", "").
- Client: the `ns === undefined` throw sits inside the async `renew` (metronome.ts:76), so a missing binding rejects in renew, never at construction. Mutant: move the check to `metronomeClient`'s body, which makes it throw synchronously, so "a missing binding rejects inside renew" fails. Timeout: race + `finally clearTimeout`; Promise.race attaches handlers, so a late rejection of the abandoned stub promise is not unhandled. Removing the race is caught by the 20 ms test.
- Focus 1 (deploy with an alarm pending): the eviction test asserts the pending alarm time is unchanged (`toBe(armed)`), the lease still reads `play` from storage after eviction, and the chain re-arms after a post-eviction alarm. Adequate.
- Focus 4 (missing binding): covered as above; the error message matches `/METRONOME_DO binding is missing/`.
- Switched off with an alarm pending: the alarm deletes itself and writes nothing (test asserts no alarm and no `live.m3u8`), so the rollback stops spend without cron.
- Storage stays within `STORAGE_KEYS` (asserted both as a subset after one renew and as exactly the 8 keys after a full cycle).

### Focus 5 / spec reading 9: genuine workerd delivery vs duplicate (check I ran)
- The brief's test does NOT show it. `runDurableObjectAlarm` (node_modules/@cloudflare/vitest-plugin/dist/worker/lib/cloudflare/test-internal.mjs:121-126) is `if (getAlarm() === null) return false; await deleteAlarm(); await instance.alarm?.();`. The helper deletes the alarm before calling the handler, so the "getAlarm() is null while it runs" premise in the test comment (metronome.test.ts, "the alarm ticks and re-arms" test) is supplied by the helper. It is not workerd's delivery semantics. What the test does pin is the engine's branch under that premise. Mutant `pending !== null` becomes `pending === null` (metronome-engine.ts:204-206): no re-arm, so `toBeGreaterThan(armed)` fails. It is caught.
- What it would need: let the runtime deliver the alarm, with no `runDurableObjectAlarm`. I ran exactly that as a scratch probe (a git-archive copy of b737d8b outside the repo, with node_modules symlinked and vitest run from the scratch cwd). The probe arms a lease whose next boundary is ~0.74 s away and instruments the scratch `alarm()` to record `ctx.storage.getAlarm()` on entry. It `vi.waitFor`s until stored `alarmTimes` has ≥1 entry, which a duplicate never adds, then asserts the recorded value is `null`, the re-armed alarm is later than the armed one, and no `metronome-duplicate` log line appeared. **Result: 1 passed (2.28 s).** So local workerd's genuine delivery sees `getAlarm() === null`, is counted and re-arms. This is local workerd, not production; the production claim still rests on Cloudflare's documented semantics (an alarm is not "set" once its handler has started, unless setAlarm ran since).
- Verdict: the behaviour is right, but the committed evidence is indirect. It is adequate only together with this probe. See Minor 1.

### The 5 s PUT bound and the timer port
- `timer` (metronome.ts:43-47) assigns `id` synchronously inside the executor, so `clear()` always cancels; `done` never settles after clear, which `boundedPut` tolerates (it has already returned). The R2 PUT is not aborted on timeout (R2 `put` takes no signal). The bound limits the wait, not the operation, so a PUT that times out may still land. That is acceptable because the engine counts the PUT before issuing it (metronome-engine.ts:11 contract), and the extra spend from a late landing is bounded by that same count.
- No DO-level test exercises the real timer port's timeout. A mutant `timer` whose `done` never resolves (ms ignored) passes every test in this diff, because only the engine's FakePort tests hit the timeout branch. See Minor 2.

### Issues
#### Critical (Must Fix)
None.
#### Important (Should Fix)
None.
#### Minor (Nice to Have)
1. antenna/test/metronome.test.ts ("the alarm ticks and re-arms" test, comment lines "The handler saw no pending alarm (getAlarm() is null while it runs)..."). The comment credits the null to the runtime, but `runDurableObjectAlarm` deletes the alarm before invoking `alarm()`, so the test is tautological about spec reading 9. Why it matters: the duplicate rule makes a genuine delivery that sees a pending alarm stop re-arming, which stalls the chain until cron falls back at `stalls >= 2`. A regression in workerd or in the helper would go unseen. Fix: reword the comment to say the helper clears the alarm, and add one real-delivery test like the probe above. It costs about 1 s, with the boundary set 0.5-1 s out and `vi.waitFor` on `alarmTimes.length >= 1` plus no `metronome-duplicate` log. The brief forbade extra tests for the implementer, so this is for the orchestrator or the plan to decide.
2. antenna/src/metronome.ts:43-47. The real `timer` port's bound is untested at the DO level (mutant: `done` never resolves, which nothing catches). Fix (optional): a unit test of the exported port pieces, or a DO test with a stubbed `BUCKET.put` that never settles, asserting renew returns within ~5 s with `wrote: false`. That test would be slow, so it may not be worth it. Noted only.
3. antenna/src/metronome.ts:29-38. `save` does `await storage.put(puts)` and then `await storage.delete(deletes)`: two awaited operations, where the engine treats one save as one change set. On the SQLite backend both should land in the same implicit transaction or output-gate flush, so this is probably fine. Issuing both without the intermediate `await` (or using `storage.transaction`) would make the atomicity explicit rather than incidental. Low risk, since a crash between the two needs an isolate death mid-event.
4. antenna/test/metronome.test.ts: the `playLease` arms an alarm ~7 s out, and real alarms fire, so under heavy suite load a slow test could see the runtime deliver mid-test (the brief's own comment acknowledges this). The implementer ran the suite twice green. Noted as a flake vector to watch, not a defect.

### Assessment
**Task quality:** Approved
**Reasoning:** A thin, verbatim binding whose key rules (switch read per call, missing binding rejecting inside renew, fixed-name addressing, renew timeout, eviction preserving lease and alarm, off-with-alarm-pending writing nothing) each have a test that a plausible mutant fails. My scratch probe confirms that a genuine local workerd delivery is not taken for a duplicate, closing the one evidence gap the committed tests leave open.

Checks run: read the brief, carry, constraints, implementer claims and the diff; read the engine port, `boundedPut` and the duplicate branch (metronome-engine.ts:24-43, 125-143, 190-215); read the `runDurableObjectAlarm` source; ran a scratch-copy real-alarm probe (1 passed); ran a scratch-copy `wrangler deploy --dry-run` (bindings as expected, no warnings); grepped `wrangler.jsonc` for secrets. No suite run and no change to the live worktree.
