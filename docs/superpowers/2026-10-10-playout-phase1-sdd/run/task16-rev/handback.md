# Task 16 review (59feaf2..294be7a)

### Spec Compliance
- ✅ Spec compliant. All three files in the brief have their hunks (clock.ts, index.ts, clock.test.ts). Interfaces match the brief. Write-immediately-then-every-boundary-until-scheduledTime+loopMs is at clock.ts:195-203. The PUT cap is enforced twice, by the loop guard (:197) and the write guard (:188). The identical-bytes skip is at :184-187. The guard seam runs first (:158) and is a no-op (:96). index.ts has a scheduled handler only, with no fetch handler. wrangler.jsonc (read, unchanged): cron `* * * * *`, `workers_dev`/`preview_urls` false, no routes.
- ✅ Ruling 1: clock.ts:171-182 emits one structured console.error per invocation, guarded by the result field, and exposes `offairWithoutFallback`. Tested at clock.test.ts:395-437, including both silent cases.
- ✅ Ruling 2: documented in the runClock docstring at clock.ts:150-155.
- ✅ Ruling 3: no wrangler dry-run, as ruled. Not counted against the implementer.
- ✅ The `usableFallback` extraction (playlist.ts:247-249) is the same expression as the removed line 258. `buildPlaylist` behaviour is unchanged.
- ✅ Extras are limited to the ruling's field and the export. The two extra test imports (`vi`, `afterEach`) are needed for the console spy.

### Strengths
- The off-air-without-fallback reason names both the cause (offair.json vs the staleness rule) and what is missing (fallback_version / index.json / len). The reason string equals the logged field, and a test asserts that (:408).
- Off-air pins its MEDIA-SEQUENCE to `scheduledTime + loopMs` (:170), so the bytes are identical within an invocation. That gives 1 PUT per minute, and the test pins it (:348-356).
- The guard-ordering test captures the bucket log at guard time, so it really proves nothing was read first (:358-368).
- The implementer's two mutation checks (cap, skip) each named their red test in advance.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **The PUT cap comes from untrusted data and unbounded config, not the spec's fixed 10. Plan-mandated: this is the brief's code verbatim.** Locations: clock.ts:124-126 and :165 (`putCap(config, g.dMs)` with `g.dMs` from `state/horizon.json`), and :62 (`LOOP_SECONDS` has no upper bound).
   - The spec says "at most ceil(75/d)+2 = **10** PUTs per invocation", and spend is the strict surface. But `gridOf` (grid.ts) accepts any `d > 0`, and `configFromEnv` accepts any `LOOP_SECONDS >= 0`. Both raise the cap and the loop's frequency together, so the cap does not bound anything.
   - Probe in a scratch copy (git archive, own test file, live tree untouched), counting PUTs per invocation:
     - horizon `d=0.01`: **2501**
     - horizon `d=1`: 76
     - `LOOP_SECONDS=900` with d=10.24: 89 per invocation, while also running 15 minutes. Cron fires every minute, so about 15 invocations overlap.
   - At one invocation per minute, d=0.01 comes to about 108M Class-A ops a month, roughly $480. That is far past the operator's ceiling, and Cloudflare has no spending cap.
   - transmitter writes `d` from `grid.D_US` (publish.py:178), so this needs a corrupted or hand-edited horizon.json or a misconfigured var. It is not normal operation. Still, "a loop that can exceed its PUT cap" is the defect class named in the constraints.
   - Fix:
     - Add a hard ceiling, `const MAX_PUTS = 10; putCap = Math.min(MAX_PUTS, ceil(loopMs/dMs)+2)`.
     - Clamp `loopMs` to at most 75 000 in `configFromEnv`. Alternatively, refuse (write nothing, console.error) a horizon whose `d` is not 10.24.
     - Add a test that seeds `d: 0.01` and asserts `puts <= 10` and that the loop ends by the deadline.

#### Minor (Nice to Have)
1. clock.ts:63: `LIVE_MAX_AGE` accepts 0 (probe: `configFromEnv({LIVE_MAX_AGE:"0"}).liveMaxAge === 0`). That gives `Cache-Control: public, max-age=0` on live.m3u8, which defeats the cache-served listener path (per-listener origin reads). It is config-only, but cheap to clamp to at least 1.
2. clock.test.ts:339-346: the "never exceeds" test checks `putCap(CFG, D) === 10` against the formula. Nothing pins an absolute ceiling against hostile inputs. This is covered by the fix for Important 1.
3. index.ts:215-228: an exception from `runClock` (for example `gridOf` throwing on a malformed `epoch`/`d`) skips the per-invocation `clock` log line. Only the platform's exception record remains, so a lagMs/day verification would see gaps. This fails safe (nothing is written). A try/finally around the log would keep the line.

### Checks run
- Read grid.ts `gridOf` (named risk: is `d` validated beyond > 0?). Answer: no.
- Read publish.py:177-180 (named risk: where horizon `d` comes from). Answer: the constant `grid.D_US`.
- Read wrangler.jsonc (cron, workers_dev/preview_urls false, no routes, vars defaults 6/3/86400/75/5).
- Ran one scratch probe (`test/probe.test.ts` in a git-archive copy) for the numbers above. No mutants. Suite not re-run.

### Assessment
**Task quality:** Needs fixes

**Reasoning:** The clock is correct and well tested at the spec's d=10.24 and default config, and the three rulings are implemented faithfully. But the per-invocation PUT cap is computed from horizon data and an unbounded var instead of being a hard 10. On the strict spend surface that is a cheap fix that should land before Task 17's smoke test.
