# final-review: antenna-metronome, 04849bf..a35208b (13 commits, 32 files, +2862/-86)

Reviewer: Fable (spec review mode). Read-only on the worktree; every run was in a scratch copy
(`git archive a35208b antenna`, node_modules symlinked) under the scratchpad. Checks run: the
whole diff and every new source and test file read; the suite once in the scratch copy
(372 passed, 20 files, 5.9 s); `npm run typecheck` clean there with the proposed tests added;
two deliberate mutants (both survive the committed tests, both caught by the pins below); one
real-delivery alarm test (1 passed, 3.2 s). The live worktree is untouched (`git status` clean).

## Strengths

- The spend bounds are where the spec put them and they are real: one `write()` per `renew`/`alarm`
  (engine.ts:147-182, called once per path); the PUT slot is reserved and flushed to storage
  before the PUT is issued (engine.ts:169-171, pinned by renew.test:295); `capAllows` fails closed on
  a non-finite clock (core.ts:174-177); the alarm cap is checked before the re-arm (engine.ts:213-219);
  expiry is negated (`!(now < expiresAt)`), computed on the DO's clock and never extended by
  `renew(null)` or a superseded lease (renew.test:190-226); a non-finite stored `expiresAt` is an
  invalid lease, deleted on load (core.ts:229-243). The chain cannot run without cron: an expired,
  held, blocked or absent lease disarms and never re-arms (alarm.test:142-200).
- `alarm()` never throws (engine.ts:78-89; alarm.test:273), and a re-arm failure is its own catch, so
  the platform's 6-retry backoff is never entered.
- The hot-loop guard is right: `nextTarget(g, max(now, lastTarget))` is strictly after both, and
  `tickBoundary = max(now, lastTarget - D - 25 ms)` makes a duplicate or a renew between an early
  tick and its boundary rebuild that tick's bytes, so MEDIA-SEQUENCE never goes backwards
  (alarm.test:54-121).
- Cron's side fails closed everywhere: every early-return path renews with the lease-table argument
  (clock.ts:287-335, clock-metronome.test:74-155); `renew` itself never throws (a non-object reply and
  an unprintable rejection are both trigger (a)); `fallbackReason` (b) now also fires on an accepted
  lease the DO is not doing (`lease` not what it was told), and (c) is negated so a NaN or missing
  `stalls` trips (core.ts:300-313, core.test:232-278).
- The guard's three DO meters are priced, projected and stored (every `METERS` entry finite,
  pinned), and "empty is not zero" runs only while the switch is on, exactly `"on"` (guard.test:258-287).
- The engine/port split is a good design: the DO is a 90-line binding, and the engine's rules were
  testable with a fake clock and a gated bucket, including interleaving (alarm.test:291-309).
- The docs are honest: section 9 carries rollout, rollback, the dead-cron consequence and the
  rollback-not-ride-it-out rule for a persisting `metronome-down` (queue item 7: present).

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

**I-1. No committed evidence that a genuine workerd delivery sees `getAlarm() === null`
(queue item 1, REQUIRED).** `antenna/test/metronome.test.ts:61-77` ("the alarm ticks and re-arms")
uses `runDurableObjectAlarm`, which deletes the alarm before calling `alarm()`
(`node_modules/@cloudflare/vitest-plugin/dist/worker/lib/cloudflare/test-internal.mjs:121-126`), so the
null that the comment at lines 68-69 credits to the runtime is supplied by the helper. Spec reading 9
makes duplicate detection rest on this premise: if a genuine delivery ever saw its own alarm as
pending, every tick would take the duplicate branch (engine.ts:204-211), never re-arm, and the chain
would stall until cron falls back at `stalls >= 2`, every minute, forever. Fix: add the real-delivery
test below (verified in the scratch copy: 1 passed, 3.2 s, typecheck clean) and reword the comment.

**I-2. A PUT-capped alarm write confirming the tick is unpinned (queue item 2).** Spec: "A cap-skipped
write does not [advance `lastAlarmGoodAt`]". Mutant `confirms = ... || r === "cap"`
(engine.ts:55) survives the committed suite (65/65 in the three engine/DO files). With it, a chain
whose every PUT is capped would look healthy to cron: `stalledMs` stays 0, trigger (c) never fires,
and a frozen playlist goes unreported. Fix: one assertion inside the existing test
"the PUT cap holds across alarms and renews" (alarm.test:250-263) — verified: passes on the original,
fails on the mutant.

**I-3. The duplicate path's write-when-bytes-differ is unpinned (queue item 3).** Mutant: replace
`if (confirms(await this.write(tx, cur, at, now, cfg, "alarm"))) s.lastAlarmGoodAt = now;`
(engine.ts:208) with `s.lastAlarmGoodAt = now;` — survives. That path is the recovery after a handler
that re-armed and then failed its PUT (`lastBody` null): the at-least-once retry is what lands the
playlist. Without a pin, a refactor to "duplicates never write" would pass green and lose that
recovery (one boundary's playlist missing until the next tick). Fix: one new `it` (below) — verified:
passes on the original, fails on the mutant.

### Minor (Nice to Have)

**M-1 (queue item 5, MUST-FIX as docs).** A DO PUT that passes its 5 s bound is counted failed, but
R2 `put` cannot be aborted (engine.ts:131-143; metronome.ts:42), so it may still land, even after a
later successful PUT, leaving an older MEDIA-SEQUENCE on `live.m3u8` until the next tick (≤ ~10 s).
A reasonable operator reading section 9's known limitations would expect to find it; it is not there.
Spend is unaffected (the slot was reserved before the PUT). Fix: one sentence in
`docs/playout-setup.md` section 9 "Known limitations" (text below).

**M-2 (queue item 6, no action).** A throw in renew's step 5 (`setAlarm` at engine.ts:301, or `disarm()`
at :305) still skips the final `flush(tx, true)`. After the "flush the accepted lease before any alarm
op" fix (engine.ts:282-283) what is lost is only: `stalls` (recomputed next renew from the stale stored
value, so trigger (c) can arrive one renew late), `lastTarget` (the alarm was not armed anyway, or the
next tick recomputes from `max(now, stale)`), and `lastBody` after a successful PUT (one extra
identical PUT next time, inside the cap). The rejection itself is trigger (a), so cron falls back that
minute. Not worth code; the test at renew.test:170-188 pins the half that matters.

**M-3 (queue item 4, OK-TO-DEFER).** `clock.ts` `failedInputs` and the `index-write` condition still
build their message with `e instanceof Error ? e.message : String(e)`; `String(Object.create(null))`
throws. Both catch values come from `readInputs`/`gridOf`/`reconcileIndex`, which throw `Error`s, so
it is practically unreachable; if it did fire, the outer `clock-failed` catch (same idiom) would rethrow
the TypeError, `finally` still flushes alerts, and nothing is PUT. A shared non-throwing
`describeError` is the right cleanup; defer.

**M-4 (new, OK-TO-DEFER).** A stored `lastTarget` far in the future parks the chain with no self-heal:
renew sees the far alarm pending and never re-arms (engine.ts:299), and after a rollback-and-return
`nextTarget(max(now, lastTarget))` re-arms to the same far time. Reachable only through DO clock skew or
storage corruption (every computed target is ≤ now + D + 25 ms); cron falls back at `stalls >= 2` and
alerts, so continuity holds. A one-line bound on load (a `lastTarget` more than D + 25 ms past `now`
reads as null) would make it self-healing. Defer.

**M-5 (new, no action).** `playSince` is not reset when an unblocked play lease returns to live from
the stale-horizon off-air state (engine.ts:279-281: `wasPlay` is true for an off-air play lease), so
the first `stalledMs` after revival measures from the last off-air tick rather than the revival. Effect:
none in practice (a renew ≥ 30 s after the revival counts a stall either way, and the chain's own first
tick arrives within 10 s). Noted.

**M-6 (CLAUDE.md, OK-TO-DEFER).** `CLAUDE.md:300` "**The metronome**" paragraph has no blank line
before it, so it renders as a continuation of the playout paragraph; the surrounding antenna text is
already one long paragraph. Cosmetic.

## Rulings reviewed (digest items 1-10)

Agree with all ten. Two notes:

- Ruling 8 (trigger (b) generalized to `s.lease !== (sent.blocked ? "blocked" : "play")`): correct and
  strictly fail-closed; the only new fallback is a >15-min clock skew between cron and the DO, where
  cron writing is the right answer.
- Ruling 9 (`tickBoundary`): the right option. The alternative (refuse a lower MEDIA-SEQUENCE than
  `lastBody`) would indeed freeze a legitimate return-to-live after a block. I checked the bound:
  `lastTarget` is at most one segment + slack ahead of `now`, so the write is never more than one
  early-delivery margin ahead, as ruled.

Also agree with the accepted departures (the "lease=" reason string; the rewritten expiresAt test;
the blocked-lease fake reply at clock-metronome.test:180-191).

## Declined to judge

- Two overlapping renews within one minute over a single silent chain break count stalls 1 and 2 and
  trigger one fallback minute plus a `metronome-down` alert — spec-mandated ("so overlapping renews
  all see a dead chain"; test list "two overlapping renews over a dead chain both count"); bounded by
  cron's MAX_PUTS.
- A DO analytics dataset outage longer than 6 h while `METRONOME` is `"on"` trips the station blind
  (readings fail on "empty is not zero") where before it would not — spec-decided ("never price a
  meter at zero for want of data").
- An unknown verdict or unreadable inputs now let the previous lease play on for up to 15 min
  (behaviour change) and a dead cron is detected ~17-18 min in — both spec-accepted (Decisions 3-4).
- `putLive` floors `max-age` at 1 s — duplicates `runClock`'s pre-existing normalization; no behaviour
  change in off mode.
- The alarm cap could be bypassed if `port.save` threw after `recordTime` and before the flush — but
  that same throw stops the PUT, and targets stay grid-bounded (≤ ~6/min); needs a storage failure.
- The scheduled-handler tests run the guard with no secrets and still get a known verdict — pre-existing
  guard behaviour, not this branch's.
- Task 9 (probe teardown, deploy, flip-on, verification day) — not in this branch by design.

## Minor triage (every `minor (deferred)` line of final-review-minors.md)

- T1 live.test substring asserts (last segment / MEDIA-SEQUENCE not line-anchored): OK-TO-DEFER — plan-mandated text; live.test:21 asserts the exact `#EXT-X-MEDIA-SEQUENCE:73` token.
- T1 `offairWithoutFallback` "has len < 1" branch untested: OK-TO-DEFER — pre-existing gap, pure string.
- T1 live.ts doc comment forward-references metronome-engine.ts: OK-TO-DEFER — now true.
- T1 RED step skipped (process): OK-TO-DEFER — process; the mutants above show where tests bite.
- T2 guard's empty-is-not-zero relies on every renew writing ≥1 row: OK-TO-DEFER — pinned at renew.test:255-265 (`["save stalls"]`, incl. expired and invalid paths) and renew.test:72.
- T2 long metronome-down blind-trips ~6-9 h in; runbook must say roll back: RESOLVED — section 9 Rollback says it (queue item 7).
- T2 latch.ts fractional Set rebuilt per `stored()` call: OK-TO-DEFER — plan-verbatim, 15-min cadence.
- T3 parseStoredLease accepts Infinity/far-future expiresAt: RESOLVED by the core fix (non-finite ⇒ invalid, core.test:197-206); a far-future *finite* value is bounded by `storedLease`'s `min(validUntil, now + 15 min)` at every accept, and only storage corruption could plant one.
- T3 validateLease keeps `raw.horizon` by reference (extra fields persist): OK-TO-DEFER — bounded by what cron sends (transmitter's horizon.json, operator-written); ~1 KB.
- T3 fallbackOrNull requires finite len: OK-TO-DEFER — stricter than spec, fail-closed.
- T3 stored expiresAt not bounded on load: same as above, RESOLVED/OK.
- T3 fallbackReason (c) positive / accepted+none not a trigger: RESOLVED (negated; (b) generalized; core.test:263-278).
- T3 untested boundaries (inWindow at exactly 60000; readState negative stalls; stalledFor(true,null,null)): OK-TO-DEFER — `<` at 60000 is pinned by the 59_999/60_001 pair; negative stalls read as 0 by construction; playSince is set at every live acceptance (renew.test:31, :202).
- T3 recordTime with NaN now empties history: OK-TO-DEFER — every call site checks `capAllows` first with the same clock (engine.ts:164-170, :213-219).
- T4 max(now,lastTarget) unpinned in renew: OK-TO-DEFER — alarm.test:69-81 pins it on the early-tick renew.
- T4 recordTime keep value unpinned (putTimes ≤ 10): OK-TO-DEFER — core.test:150-156 pins the list size at 12; the engine passes the constants.
- T4 cap-skipped renew write then chain re-arms — not asserted: OK-TO-DEFER — alarm.test:250-263 asserts `alarmAt` not null after the capped tick.
- T4 timed-out PUT may land after a later PUT: MUST-FIX (docs line, M-1).
- T4 invariant 3/4 pins in T5: OK-TO-DEFER — covered as above.
- T4 alarm-op failure skips lease persist: RESOLVED (flush before alarm ops; renew.test:170-188).
- T4 "logged once" test asserts 1..3 range: OK-TO-DEFER — `episode()` dedup is exercised by alarm.test:104 (`toHaveLength(1)`) and renew.test:167.
- T4 LATE_LOG_MS/MAX_ALARMS_PER_MINUTE/confirms unused until T5: RESOLVED (used).
- T4 timed-out PUT known-limitations line: MUST-FIX (M-1).
- T4 renew(undefined) maps to null: OK-TO-DEFER — the DO forwards the argument unchanged; cron never sends undefined.
- T5 hold/blocked renew disarms, play renew arms from stale future lastTarget skipping one boundary (3 renews in one segment): OK-TO-DEFER — one skipped boundary (≤ 10 s), needs three renews inside one segment.
- T5 stored putTimes/alarmTimes length unpinned at engine level; alarm-cap window edge: OK-TO-DEFER — core.test pins both; alarm.test:239-248 pins the alarm cap edge (59_999/60_001).
- T5 capped write confirming tick unpinned: MUST-FIX (I-2).
- T5 duplicate path write-when-bytes-differ unpinned: MUST-FIX (I-3).
- T5 step-2 "delete pending alarm" unpinned (deliverDuplicate in must-not-tick cases): OK-TO-DEFER — alarm.test:181-200 delivers a still-pending alarm under hold/blocked and asserts `alarmAt` null.
- T6 "alarm ticks and re-arms" credits getAlarm-null to workerd: MUST-FIX (I-1).
- T6 real timer port's 5 s bound untested at DO level: OK-TO-DEFER — engine-level pinned; a DO-level test costs 5 s wall time.
- T6 save() put then delete as two awaited ops: OK-TO-DEFER — needs an isolate death between two storage ops inside one event; worst case both writers write for ≤ 15 min.
- T6 ~7 s real alarm a possible flake under load: OK-TO-DEFER — watch; `reset()` clears it.
- T7 non-object DO reply makes renew throw: RESOLVED (0b59b70; clock-metronome.test:226-238).
- T7 two tests feed the default `lease:"play"` fake to a blocked lease: OK-TO-DEFER — clock-metronome.test:168 and :186 now reply `blocked`; the remaining ones take the fallback path with assertions that still hold.
- T7 clock.ts:246 sent-label duplicates fallbackReason's mapping: OK-TO-DEFER — cosmetic.
- T7 switch-off path raises offair-without-fallback from deps.now() before the loop: OK-TO-DEFER — ms-level; the loop's first write is immediate.
- T7 test gaps (non-Error rejection at runClock level; timeout after accept; stalls≥2 on null/hold): OK-TO-DEFER — the first is now covered (`Object.create(null)` rejection); (c) on `null` is pinned at core.test:260.
- T7 unguarded String(e) in failedInputs/index-write: OK-TO-DEFER (M-3).
- T8 CLAUDE.md "at most" vs "≤": OK-TO-DEFER — meaning identical.
- T8 CLAUDE.md missing blank line: OK-TO-DEFER (M-6).

## Recommendations

- Put the real-delivery test in `test/metronome.test.ts` (same `afterEach` reset) rather than a new
  file, so the DO files stay the ones that reset storage.
- On the verification day, grep the tail for `metronome-duplicate` lines: production workerd is the
  only runtime that can confirm reading 9 beyond local workerd, and that line is the symptom.
- Consider M-4 (a `lastTarget` sanity bound on load) in a follow-up; it is the one state the object
  cannot recover from on its own.

## Fix-wave list (one implementer; `cd antenna && npm test && npm run typecheck` from the worktree after)

Expected count after: **374** (372 + the real-delivery `it` + the duplicate-after-failed-PUT `it`;
item 2 is an assertion inside an existing test). The brief's "+1 ⇒ 373" counted item 1 alone.

1. **`antenna/test/metronome.test.ts`** — add a helper beside `pendingAlarm` (line 33):
   ```ts
   const alarmTimes = () => runInDurableObject(stub(), (_o: Metronome, state) => state.storage.get<number[]>("alarmTimes"));
   ```
   and add this `it` inside `describe("the Metronome Durable Object")`, after "the alarm ticks and re-arms":
   ```ts
   it("a genuine delivery (the runtime's own, not runDurableObjectAlarm) sees no pending alarm: counted, re-armed later, never a duplicate", async () => {
     const logs = vi.spyOn(console, "error").mockImplementation(() => {});
     const seen: (number | null)[] = [];
     await runInDurableObject(stub(), (o: Metronome, state) => {
       const self = o as unknown as { env: AntennaEnv };
       self.env = { ...self.env, METRONOME: "on" };
       // The engine's port calls this same storage object: record what getAlarm() answers inside alarm().
       const real = state.storage.getAlarm.bind(state.storage);
       vi.spyOn(state.storage, "getAlarm").mockImplementation(async () => { const v = await real(); seen.push(v); return v; });
     });
     const now = Date.now();
     const epoch = new Date(now - 100 * D - (D - 600)).toISOString(); // 600 ms before boundary 101
     const lease: Lease = { kind: "play", verdictAt: now, validUntil: now + METRONOME_LEASE_MS, blocked: false,
                            horizon: { epoch_id: "e1", epoch, d: 10.24, first: 0, last: 1_000_000, published_at: epoch,
                                       container: "adts", fallback_version: "v1" },
                            fallback: { len: 7, notice: "fallback/v1/notice.aac" } };
     expect((await stub().renew(lease)).applied).toBe("accepted");
     const armed = await pendingAlarm();
     expect(armed).toBeGreaterThan(now);
     expect(armed).toBeLessThan(now + 1_000);
     seen.length = 0;
     // alarmTimes is recorded only on the genuine path (a duplicate is not counted).
     await vi.waitFor(async () => expect((await alarmTimes())?.length ?? 0).toBeGreaterThanOrEqual(1),
                      { timeout: 5_000, interval: 50 });
     expect(seen).toEqual([null]); // the one getAlarm() inside alarm() answered null
     expect(await pendingAlarm()).toBeGreaterThan(armed!);
     expect(logs.mock.calls.flat().join("\n")).not.toContain("metronome-duplicate");
   });
   ```
   (Verified in a scratch copy as written: 1 passed, 3.2 s; `tsc --noEmit` clean. The test's own
   `afterEach` already does `vi.restoreAllMocks()` and `reset()`.)
   Then replace the comment at lines 68-69 ("The handler saw no pending alarm (getAlarm() is null
   while it runs), so it ticked as a genuine delivery and re-armed later, not as a duplicate.") with:
   `// runDurableObjectAlarm deletes the alarm before calling alarm(), so this pins only the engine's
   // genuine-delivery branch (re-arm, not duplicate); the next test lets the runtime deliver the alarm itself.`

2. **`antenna/test/metronome-alarm.test.ts`**, test "the PUT cap holds across alarms and renews, and the
   chain still re-arms over it" (lines 250-263): after `expect(port.alarmAt).not.toBeNull();` add
   ```ts
   expect(port.store.get("lastAlarmGoodAt") ?? null).toBeNull(); // a cap-skipped write is not a confirmed tick
   ```
   (Verified: passes on the original; fails on mutant `confirms = ... || r === "cap"`.)

3. **`antenna/test/metronome-alarm.test.ts`**, inside `describe("alarm: the tick")`, before
   "duplicates after a completed tick", add:
   ```ts
   it("a duplicate after a tick whose PUT failed writes the differing bytes (lastBody is null) and confirms the tick", async () => {
     const { port, engine } = await playing();
     port.bucket.failPuts.add("live.m3u8");
     await deliver(port, engine, target(1001) + 3); // re-armed, then its PUT failed: lastBody null, tick unconfirmed
     expect(port.store.get("lastBody")).toBeNull();
     expect(port.store.get("lastAlarmGoodAt") ?? null).toBeNull();
     port.bucket.failPuts.delete("live.m3u8");
     const puts = port.puts();
     await deliverDuplicate(port, engine, target(1001) + 9); // at-least-once: the retry finds the re-armed alarm pending
     expect(port.puts()).toBe(puts + 1);
     expect(port.body()).toContain("seg/e1/1013.aac");
     expect(port.store.get("lastAlarmGoodAt")).toBe(target(1001) + 9);
     expect(port.alarmAt).toBe(target(1002));
     expect(port.store.get("lastTarget")).toBe(target(1002));
   });
   ```
   (Verified: passes on the original; fails on the mutant that confirms without writing.)

4. **`docs/playout-setup.md`**, section 9 "**Known limitations.**" paragraph: append
   `An R2 PUT the object has waited 5 s for is counted as failed (`metronome-put-failed`, `lastBody`
   cleared, the next tick retries), but R2's `put` cannot be aborted, so it may still land, even after a
   later successful PUT: the playlist can then show an older MEDIA-SEQUENCE until the next tick (≤ ~10 s).
   The slot was counted against the PUT cap before it was issued, so this costs no extra spend.`

5. Commit as one fix commit on `antenna-metronome` (test command in the message), attribution lines per
   the session reminder. No source change is needed; nothing else in the fix wave.

## Assessment

**Ready to merge? With fixes** (the four items above; all test/docs, no source change). The code
meets the spec's Stakes: every DO meter is priced or bounded by construction, no unknown verdict is
ever treated as unblocked, the chain cannot run without cron past 15 min, and the PUT/alarm caps hold
under the mutants I tried. The gaps are evidentiary — the one premise the duplicate rule rests on had
no committed test, and two spec-named rules survived mutation — and a docs omission a reasonable
operator would want.
