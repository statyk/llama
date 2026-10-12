# Task 16 handback: antenna clock loop and Worker entry

**Status: DONE**

**Commit:** `294be7a` feat(antenna): cron clock writes live.m3u8 at every grid boundary (PUT cap, identical skip, guard seam). Branch playout-phase1, on top of 59feaf2.

**Files:**
- created `antenna/src/clock.ts`: brief's interfaces verbatim, plus `ClockResult.offairWithoutFallback`
- `antenna/src/index.ts`: the scheduled handler, as in the brief
- `antenna/src/playlist.ts`: extracted `usableFallback(inp)`. No behaviour change; `buildPlaylist` now calls it.
- created `antenna/test/clock.test.ts`: the brief's 8 tests plus 3 for ruling 1

**Tests:** `cd antenna && npm test`: 2 files, 24 passed (13 playlist + 11 clock). `npm run typecheck` is clean. Python untouched.

**Rulings:**
1. Off-air without a fallback: `buildPlaylist` still returns null and nothing is written. When the playlist is null, the clock checks `isOffair && usableFallback === null`. If both hold, it sets `result.offairWithoutFallback` to a reason string and emits one `console.error(JSON{event:"offair-without-fallback", reason, epoch_id, fallback_version, scheduled})`. This happens at most once per invocation, guarded by the result field.
   - The reason names the cause: either `state/offair.json has offair: true` or the stale-horizon rule.
   - It also names what is missing: `fallback_version` null, `fallback/<v>/index.json` missing or unreadable, or `len < 1`.
   - Tests cover: offair.json with the index missing (1 log line across 8 attempts, puts 0); staleness with a null `fallback_version`; and silence for off-air-with-fallback and for on-air-without-fallback.
   - The field also appears in the scheduled handler's per-invocation log line, because the handler spreads `...result`.
2. Epoch change: the brief did not handle it. I did not redesign it. The `runClock` docstring now says inputs are read once per invocation, so the epoch cannot change within one. Between invocations, a change of `epoch_id` restarts N at 0 and drops MEDIA-SEQUENCE. That is a deliberate operator re-render event, and players must reload the stream. Task 18's runbook can cite this.
3. No wrangler command was run, and no account IDs or credentials were touched. **Deviation from the brief:** I skipped its Step-4 `npx wrangler deploy --dry-run`, because the ruling prohibits `wrangler deploy` literally. I checked by reading `wrangler.jsonc` instead: it has `triggers.crons ["* * * * *"]`, the BUCKET binding, `workers_dev`/`preview_urls` false, and no routes. The manager can run the dry-run if it wants that check.

**Mutation checks** (scratch copies made with `git archive HEAD antenna | tar -x`, node_modules copied in, run from the scratch dir; predictions were logged before running):
- (a) PUT cap removed (dropped `if (puts >= cap) return` and changed the loop to `while (true)`).
  - Predicted red: "never exceeds ceil(75/d) + 2 PUTs".
  - Result: exactly that test failed (66 vs 10); 23 passed.
- (b) Identical-bytes skip removed.
  - Predicted red: "skips bytes identical…" and "stays silent when off-air has a fallback…" (its `r1.puts == 1` depends on the skip).
  - Result: exactly those two failed (8 vs 1 each); 22 passed.

**Differences from the brief:** `ClockResult` gains `offairWithoutFallback: string | null`; playlist.ts gains the `usableFallback` export; the clock test imports `vi`/`afterEach` for the console spy; the wrangler dry-run was skipped (above). The pure-fallback discontinuity numbering `floor(N/len)+1` is unchanged.

**Concerns (minor, not acted on):**
- A malformed `epoch` or `d` in horizon.json makes `gridOf` throw, so the invocation errors with nothing written. That is inherited from the brief and fails safe, but the error is not structured.
- The skip compares only against this invocation's last write, so the first write of each invocation is always a PUT, as the spec says. Off-air therefore costs 1 PUT per minute.
