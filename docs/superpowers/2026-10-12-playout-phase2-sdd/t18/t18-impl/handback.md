# t18-impl handback: playlist hold-back + lookahead (Task 18, amended)

STATUS: DONE. 3 commits on playout-t18 (base 7c93250). All gates green. Nothing pushed or deployed.

## Commits
- faa58e9 feat(antenna): playlist hold-back + lookahead 12 (players start at the wall clock, ~123 s runway)
- 0de54b7 fix(transmitter): dead-clock check dates a lookahead playlist by its own hold-back
- 906222e feat(antenna,docs): hls.js joins and re-syncs at the hold-back; runbook and plan A4 amended

## What changed, by file
- antenna/src/playlist.ts
  - `PlaylistConfig` gains `lookahead?` and `holdBack?` (both default 0).
  - `windowEntries` ends at the target `cur + lookahead`. The grace hold and the fallback switch apply to that target.
  - Live playlists emit `#EXT-X-START:TIME-OFFSET=-<R·d>` and `#EXT-X-SERVER-CONTROL:HOLD-BACK=<R·d>`, 3 decimals, VERSION stays 3:
    - R = min(holdBack, entries − 1);
    - emitted only when R·d >= 3·TARGETDURATION (so R >= 4);
    - never on off-air or ENDLIST-only playlists.
  - New `offairSequence(g, nowMs, seqMs, L) = max(0, indexAt(max(seqMs, nowMs))) + L + 1`.
  - `offairPlaylist`/`endlistOnly` now take the computed sequence number; they have no other callers.
- antenna/src/clock.ts
  - `PLAYLIST_LOOKAHEAD`/`PLAYLIST_HOLD_BACK` in `ClockEnv`, and `MAX_LOOKAHEAD = 16`.
  - `configFromEnv`: lookahead = min(16, floor), holdBack = min(window − 1, floor), defaults 0 (window still defaults to 6).
  - Comment only at the `write` site: it still passes `offairSeqMs: scheduledTime + loopMs`. The rule lives in `playlist.ts`.
  - MAX_PUTS, the d refusal, the 75 s clamp, LIVE_MAX_AGE and the guard order are untouched, and the PUT count is unchanged.
- antenna/wrangler.jsonc: `PLAYLIST_WINDOW "16"`, `PLAYLIST_LOOKAHEAD "12"`, `PLAYLIST_HOLD_BACK "12"`, plus a comment to keep L = R.
- antenna/test/playlist.test.ts
  - New tests: lookahead/hold/fallback, the deployed 16/12 window, the hold-back tags (VERSION 3, placement, start = cur+1), omission at 0/3/undefined and first emission at 4, clamping to window − 1 and to a short early-epoch window, no tags off-air, and the strict off-air invariant for L ∈ {0,3,12,16} × 3 seqMs cases × with and without a fallback.
  - Phase-1 exact numbers bumped by 1 (1000→1001, 1007→1008), and `>=` changed to `>` against the last listed live number.
- antenna/test/clock.test.ts
  - Late invocation (+100 s) and on-time invocation (including the previous minute's invocation) for L ∈ {4, 12, 16 = MAX_LOOKAHEAD}. The notice is strictly above every live body each run PUT, and the on-time off-air run makes exactly 1 PUT.
  - configFromEnv defaults, the lookahead cap and parsing, and the hold-back clamp.
- antenna/test/wrangler-config.test.ts
  - Pins the deployed vars and L = R, and that the hold-back is actually emitted (R·d >= 33).
  - Prune bound: (W − L + grace)·d <= (6 + 3)·d.
- antenna/public/player.js: `new Hls({ liveSyncDuration: 12 * 10.24, maxBufferLength: 130, backBufferLength: 30 })`, with a comment (see the hls.js section).
- packages/transmitter/src/transmitter/deadclock.py: `playlist_hold_back_s(text)`, `playlist_age_s(..., live_hold_back_s=0.0)`, and a monitor field `live_hold_back_s` (see the dead-clock section).
- packages/transmitter/tests_transmitter/test_deadclock.py: a helper for lookahead playlists, and 5 new tests.
- packages/transmitter/src/transmitter/config.py: comment only. The prune floor's derivation now states the (W − L + grace)·d bound.
- docs/playout-setup.md:
  - section 4 step 6 (new): playlist vars, keep L = R, caps and omission;
  - the dead-clock row in the `[alerts]` table;
  - the already-playing-page latency (Safari now drains ~120 s first);
  - a new phase-2 checklist item: "joining on iPhone and Chrome starts near the wall clock (now-playing matches the schedule)".
- docs/superpowers/plans/2026-10-11-playout-phase2.md: A4 and the Task 18 header carry an "Amended 2026-10-12" block (premise error, measurements, as-built values). The original text is kept below it for the record.

## Off-air invariant derivation
- **Live bound.** A live write at time t lists at most `indexAt(t) + L`. `windowEntries`' end is the target `cur + L`, or `h.last` when held, and a hold only happens when target > last. Fallback entries are numbered within the same range.
- **Earlier writes.** `indexAt` is nondecreasing, so every live number written at or before time `now` is at most `indexAt(now) + L`. That covers this invocation, an overlapping one and any earlier one.
- **The rule.** The notice is numbered `indexAt(max(scheduledTime + loopMs, now)) + L + 1`, which is strictly greater than all of those.
- **Why the +1 is needed, even at L = 0** (phase 1 had the same hole). With equality, a player that already holds live segment N reads "notice = N" as a segment it already has. It skips the notice and stops on ENDLIST without it.
- **Why `now` replaces the plan's `startedMs + L·d`.**
  - `startedMs` is taken before the guard. The first write comes after the guard, `index.html` and the input reads, so it can fall in a later segment than `startedMs`.
  - An invocation later than its own loop (lag > 75 s) needs `now` anyway.
  - Taking `max(..., now)` per write keeps the number constant while `now <= scheduledTime + loopMs`, so an on-time invocation still makes 1 PUT. Past that it rises with `now`, so it is monotonic within an invocation.
- **Tests and mutants.** The tests are listed above. In a scratch copy, each of these mutants was caught by the predicted tests: dropping the +1 (10 red), dropping the `now` term (5), dropping the L term (7), the window ignoring L (4), the window-clamp removed (1), the 3·TD threshold removed (1).
- **Does the larger L change the A1 / off-air→live limitation?** No. Returning live drops MEDIA-SEQUENCE from the notice's number to `cur' + L − W + 1`. The drop is about (indexAt(max(S+75, t)) − cur') + W + 1, so L cancels. It is larger in size by +10 (W 16 vs 6) and +1, but not different in kind. Players that stopped on ENDLIST start fresh and are unaffected.

## Dead-clock choice
- **The rule.** hugo dates the live playlist by its newest PROGRAM-DATE-TIME minus the playlist's own hold-back: `#EXT-X-START` negative TIME-OFFSET, else `SERVER-CONTROL` HOLD-BACK, else 0. A missing, malformed or positive offset counts as 0, which is the phase-1 behaviour.
- **The deployment rule L = R** is pinned by antenna's wrangler-config test and documented in the runbook and wrangler.jsonc.
- **Why not a config key.** The playlist is the single source of truth; it is what players obey. A hugo-side `[alerts]` key would be a second copy of a Worker var on another machine, free to drift silently. No config key was added, so `DEFAULT_CONFIG_TOML` and the template test are untouched.
- **If L ≠ R anyway.**
  - R > L over-reads the age, a loud false alarm.
  - R < L under-reads it, so detection is late by (L − R)·d.
- **Off-air.** The off-air playlist carries no tag, so the monitor remembers the last live hold-back and subtracts it from the MEDIA-SEQUENCE age. The notice is numbered L + 1 past the write, so this under-reads by at least d and never false-alarms. After a monitor restart while off-air the remembered value is 0 until a live read, so detection is late by up to L·d.
- **Tests.**
  - A 153.6 s-stale L = 12 playlist alerts on 2 checks; dated by its newest PDT alone it would read 30.7 s and never alert.
  - The off-air case also alerts on 2 checks.
  - Mutants (scratch copy, PYTHONPATH shadowing proven with a sentinel): live ignoring the hold-back (3 red), off-air ignoring the memory (2), no memory (1), no HOLD-BACK fallback (2).

## Prune evidence (no change needed)
- A segment n stays listed while n >= end − W + 1, where end <= cur + L, or h.last during a grace hold of at most `grace` past it. So it is listed at most (W − L + grace)·d after it starts: 16 − 12 + 3 = 7·d = 71.68 s, against phase 1's (6 + 3)·d = 92.16 s.
- prune deletes only segments that started more than `prune_margin_minutes` ago: `packages/transmitter/src/transmitter/publish.py:400-401` (the cutoff and `n_max`).
- The margin's floor is 4 min and the default is 10 min: `config.py:69-71`, `:84`. The floor was derived from 92.16 + 5 + 120 s.
- Players started 12 back fetch from about cur + 1.
- Pinned by the new wrangler-config test ((W − L + grace)·d <= 9·d). The existing `test_prune_margin_floor_covers_the_live_window_and_player_lag` is unchanged.

## hls.js, vendored 1.7.3 (node_modules/hls.js, package.json ^1.7.3)
Verified in `dist/hls.mjs`.
- **EXT-X-START is honoured.** `setStartPosition` uses `details.startTimeOffset` when startPosition is −1 (the default), with a negative offset measured from the edge.
- **`targetLatency`** is HOLD-BACK unless the user sets `liveSyncDuration`/`liveSyncDurationCount`. In that case it is `liveSyncDuration ?? liveSyncDurationCount * targetduration`, where targetduration is TARGETDURATION = 11 s, not 10.24.
  - So `liveSyncDurationCount: 12` (the brief's wording) would mean 132 s.
  - **Deviation:** I used `liveSyncDuration: 122.88` to match the hold-back exactly.
  - Mixing the Count and Duration options throws ("Illegal hls.js config"); confirmed by instantiating hls.js in node with the shipped config.
- **`getMaxBufferLength`** = `maxBufferLength` (default 30) when there is no level bitrate (our media-only playlist), capped by `maxMaxBufferLength` (default 600). I set `maxBufferLength: 130` so the whole ~123 s runway can fill; 120 would stop 2.9 s short.
- **`backBufferLength`** defaults to Infinity. A SourceBuffer quota error goes through `reduceLengthAndFlushBuffer` → `reduceMaxBufferLength`, which lowers `maxMaxBufferLength` and would eat the runway. I set `backBufferLength: 30`.
- **StallWatch (Task 11) is unchanged and still behaves.**
  - hls.js goes off-air on its next playlist reload: the 403 through ERROR, or ENDLIST through LEVEL_LOADED live=false. Buffer size does not matter there.
  - Native Safari only notices on a stall, so on an already-playing page it now plays out ~120 s of buffer first, then the 15 s stall and 2 probes 10 s apart: about 2.5 min. The runbook checklist item was updated to expect that.

## Gates
- `cd antenna && npm test && npx tsc --noEmit`: 235 passed (baseline 217); tsc clean.
- `./.venv/bin/python -m pytest -q`: 2612 passed, 1 skipped, 7 deselected (baseline 2607 + 5 new).
- `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`: 456 passed, 1 skipped.
- `packages/transmitter/scripts/test-in-debian12.sh`: 457 passed (Docker up).
- `.venv`/`.venv311` were created in this worktree (the transmitter and llama imports resolve inside it).

## Deviations from the brief
1. **Option name.** `liveSyncDuration: 122.88` instead of `liveSyncDurationCount: 12` (semantics above). `maxBufferLength` is 130, not 120, and I added `backBufferLength: 30`.
2. **Where the off-air rule lives.** It is in `playlist.offairSequence`, a pure function enforcing the invariant itself, not in clock.ts as `offairSeqMs = max(S + loop, startedMs + L·d)`. The term is `now` (per write) instead of `startedMs + L·d`, plus the +1.
3. **Phase-1 numbers.** The +1 applies at L = 0 too, so the phase-1 off-air numbers shift by one. Existing exact-number tests were updated.
4. **Hold-back clamp.** It is also clamped per playlist to (listed entries − 1), which only differs in the first 15 segments of an epoch, besides the configFromEnv clamp to window − 1.

## Open questions / for the operator
- **Deploy.** player.js is a static asset: it needs `ANTENNA_BUCKET=lma-radio npm run deploy:assets` as well as the Worker deploy (cached max-age 1 h). No deploy was run.
- **Lowering L.** If L is lowered by a deploy while an earlier invocation's live playlist (listing up to cur + old L) is still current, an off-air write right after could number the notice at or below a listed segment. Using MAX_LOOKAHEAD in the off-air rule would close that, at the cost of numbering the notice up to 16 + 1 ahead. I left it on the configured L; your call.
- **Cross-invocation race.** An off-air write computed at t_o, running later than its own loop, can land after an overlapping live write computed in the next segment. The number could then be one short. This needs the two invocations to disagree on blocked; it is the same family as the documented "overlapping cron runs" limitation.
- **Start point.** It is the start of cur + 1 at write time: 0–10 s ahead of the wall clock when written, roughly at it once you allow for the playlist's age when fetched. If you want players never ahead of the schedule, use L = R + 1 (the dead-clock check would then under-read by d, which is safe). Worth checking on the new checklist item.
