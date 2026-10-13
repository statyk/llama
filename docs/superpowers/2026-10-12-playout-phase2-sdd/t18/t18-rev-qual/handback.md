VERDICT: APPROVED

# t18-rev-qual: code-quality review of 7c93250..906222e (playout-t18)

No Critical or Important findings. The off-air numbering, the window/grace/fallback changes, the tag emission and clamping, the config caps and the dead-clock re-dating are correct. 20 of 24 targeted mutants were caught, and each was caught by the test I named in advance. The 4 survivors are 1 equivalent mutant and 3 minor test gaps (listed below). The Minor items are optional polish.

## Gates (run in the worktree, read-only)
- `cd antenna && npm test && npx tsc --noEmit`: 14 files, **235 passed**; tsc exit 0.
- `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`: **456 passed, 1 skipped**. `transmitter.__file__` resolves inside the worktree.
- `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider` (Python 3.11.15): **456 passed, 1 skipped**.
- I did not run the Debian-12 script.
- The vendored hls.js is **1.7.3**. I instantiated it in node with `{liveSyncDuration: 122.88, maxBufferLength: 130, backBufferLength: 30}`:
  - the constructor does not throw (the config validation at hls.mjs:38438/38444 allows liveSyncDuration without liveMaxLatencyDuration);
  - the resolved config is liveSyncDuration 122.88, liveMaxLatencyDurationCount Infinity (so it never seeks forward), maxMaxBufferLength 600, liveBackBufferLength null.

## Mutation results
Scratch copy: `git archive 906222e` into /private/tmp/claude-501/t18-rev-qual-scratch, with node_modules symlinked. Python ran via `python -m pytest`, `PYTHONPATH` set to the scratch src and `PYTHONDONTWRITEBYTECODE=1`; a planted sentinel confirmed the import came from the scratch copy. I named the expected red test before each flip.

| # | Mutant | Predicted red | Result |
|---|---|---|---|
| M1 | offairSequence drops `+ 1` | playlist "numbers the off-air notice above every…", clock late/on-time | CAUGHT (as predicted, plus the two 1001 asserts) |
| M2 | `indexAt(seqMs)` only, no `now` term | playlist 1020 assert, clock late | CAUGHT |
| M3 | drops `+ lookahead` | clock L=4/12/16, playlist "above every" | CAUGHT |
| M4 | grace hold keyed on `cur`, not the target | playlist "lookahead lists … holding at last" | CAUGHT |
| M5 | emission threshold 3 TD → 4 TD | playlist "emits nothing … below 3 TD" (holdBack 4 emits) | CAUGHT |
| M6 | no `entries.length - 1` clamp | playlist "never offsets past the listed window" | CAUGHT |
| M7 | START only, no SERVER-CONTROL | playlist "both tags" | CAUGHT |
| M8 | `toFixed(2)` | hold-back tests | CAUGHT |
| M9 | VERSION 3 → 6 | "at VERSION 3" | CAUGHT |
| M10 | lookahead uncapped | configFromEnv "capped at 16" | CAUGHT |
| M11 | holdBack not clamped to window − 1 | configFromEnv "clamped" | CAUGHT |
| M12 | clock passes no offairSeqMs | clock on-time `toHaveLength(1)` | CAUGHT (plus the 3 phase-1 off-air clock tests) |
| M13 | window end at target + 1 | window tests | CAUGHT (by the off-air clock tests and the hold-back tests) |
| M14 | `holdBack > 0` → `>= 0` | predicted SURVIVE (equivalent: 0·d < 33 s) | SURVIVED (equivalent) |
| M15 | offairSequence drops `Math.max(0, …)` | predicted SURVIVE (no pre-epoch off-air test) | SURVIVED |
| P1 | live age drops `+ hold-back` | lookahead-age test, dead-clock-with-lookahead | CAUGHT |
| P2 | off-air age drops `+ live_hold_back_s` | off-air subtracts test, monitor off-air test | CAUGHT |
| P3 | monitor never remembers the hold-back | monitor off-air test | CAUGHT |
| P4 | monitor remembers on every 200 (off-air resets to 0) | monitor off-air test | CAUGHT |
| P5 | ignores START | lookahead-age (server_control=False case) | CAUGHT |
| P6 | ignores SERVER-CONTROL | lookahead-age (start_tag=False case) | CAUGHT |
| P7 | `abs(offset)`: a positive TIME-OFFSET is accepted | predicted SURVIVE | SURVIVED (see Minor 1) |
| P8 | `_attribute` drops the `isfinite` check | predicted SURVIVE | SURVIVED (see Minor 1) |
| P9 | SERVER-CONTROL wins over START | predicted SURVIVE (same values) | SURVIVED (see Minor 1) |

## Edge cases checked
- **Off-air invariant.**
  - The derivation in `playlist.ts:62-81` holds: windowEntries' end is at most `cur + L`, and `indexAt` is nondecreasing.
  - Overlapping earlier invocations are covered. Their loop writes land at a boundary `next ≤ T_prev + 75 s` (plus the 25 ms slack). That is below the new invocation's `seqMs = T + 75 s`.
  - Within one invocation the number cannot step: loop writes happen at `next + 25 ms` with `next ≤ deadline = seqMs`, so `indexAt(max(seqMs, now))` stays constant. Only a write that starts already past its deadline numbers from `now`.
  - The phase-1 rule of one off-air PUT per invocation still holds; the existing "blocked: one PUT" test stays green.
  - Residual, outside the documented scope ("writes at or before nowMs"), and negligible:
    - Scenario: an older invocation read `offair=false` milliseconds before the flip, and its first write lands after the newer off-air write.
    - For the numbers to collide, that write must also cross a segment boundary, and the newer invocation must be more than 75 s late.
    - This is the same last-writer-wins race phase 1 already has.
- **L changed between deploys.**
  - The on-time margin `indexAt(T + 75) − indexAt(t_prev)` is about 7 segments, so lowering L by up to about 7 in one deploy is safe even mid-overlap.
  - On hugo, a live read re-learns the hold-back from the playlist itself, so only an off-air read within a minute of a deploy can use a stale remembered value.
- **Early epoch.** At L = 12, any `cur ≥ 0` lists at least 13 entries, so the hold-back is never clamped. The clamp boundary (13 entries, offset 12) is tested exactly.
- **Horizon end.**
  - The grace hold and the fallback switch are keyed on the target, and that is tested.
  - Every live-kind entry is ≤ `h.last`, so the existence of listed segments does not depend on the lead.
  - In the grace hold, hugo over-reads the age by `(target − last)·d ≤ 30.72 s`. This is not a regression: phase 1 over-read by `(cur − last)·d` in the same state.
- **Prune.** The `(W − L + grace)·d = 7·d ≤ 9·d` reasoning is correct for both the non-hold and the hold case.
- **Malformed playlists on hugo.**
  - Empty, non-numeric, NaN or inf values give None, which is treated as no hold-back.
  - A positive TIME-OFFSET falls through to HOLD-BACK.
  - A malformed PROGRAM-DATE-TIME still reads as stale, as before.
- **player.js / Task 11.**
  - `hlsErrorNotice` acts on any 403 (fatal or not), and `LEVEL_LOADED` with `live === false` still calls `offAir` at once.
  - Live playlist reloads do not depend on buffer depth, so a 130 s buffer does not delay hls.js's off-air detection.
  - StallWatch is driven by playback position only and is unaffected.
  - The runbook's revised wording (Chrome at the next reload, Safari up to about 2.5 min) matches the code.
- **Strict config / Python 3.11.**
  - No new config key: hugo reads the hold-back from the playlist, so `extra="forbid"` models and the TOML template are untouched.
  - The only `config.py` change is a comment.
  - `float | None` is fine on 3.11, and the 3.11 suite is green.
- **Off-air→live (A1, informational).** Raising L and W widens the backwards MEDIA-SEQUENCE jump. Off-air→live goes from about `indexAt(T + 75) − cur + W` ≈ 7 + 6 = 13 segments to about 7 + 16 = 23 segments (~235 s). The limitation is the same, just longer.

## Critical
None.

## Important
None.

## Minor
1. **The positive-offset test cannot tell "ignored" from "abs()"** (`packages/transmitter/tests_transmitter/test_deadclock.py:63-64`).
   - The positive TIME-OFFSET in that test has the same magnitude as the HOLD-BACK it falls back to (122.880), so P7 (`abs(offset)`) and P9 (SERVER-CONTROL wins over START) both survive.
   - P8 (no `isfinite`) also survives: no test feeds `-inf` or `nan`.
   - Real-world risk is low, since the antenna writes these tags itself. But the test's name says it pins "ignored", and it does not.
   - Fix:
     - In the positive case, also change `HOLD-BACK=122.880` to a different value (e.g. `HOLD-BACK=40.960`) and assert the age that follows from it.
     - Add one assert with START and SERVER-CONTROL set to different values to pin which tag wins.
     - Add `TIME-OFFSET=-inf` to the malformed case.
2. **`player.js:69` hard-codes `12 * 10.24`, a second source of truth for `PLAYLIST_HOLD_BACK`.**
   - If an operator changes `PLAYLIST_HOLD_BACK`/`PLAYLIST_LOOKAHEAD`, hls.js still joins at the playlist's EXT-X-START but re-syncs at 122.88 s.
   - hls.js 1.7.3 already uses the playlist's `HOLD-BACK` as its target latency when the user config sets neither `liveSyncDuration` nor `liveSyncDurationCount` (hls.mjs:34978-34986; HOLD-BACK is parsed at hls.mjs:9417). With no tag it falls back to the default `liveSyncDurationCount` of 3, the same as the old explicit setting.
   - Fix: drop `liveSyncDuration` and let the playlist drive it, with a comment saying so. Or keep it and add a comment that it must track `PLAYLIST_HOLD_BACK`.
   - Either way the deployed behaviour is correct today.
3. **Players that ignore EXT-X-START/HOLD-BACK now play about 92 s ahead of the schedule.**
   - Players such as VLC, or any client honouring neither tag, still start about 3 target durations behind the listed end, which is now about `cur + 9`.
   - Every segment exists (lead ~24 h), so this is not a correctness bug. But "now playing" from such a client no longer matches the wall clock, and its runway stays at ~31 s.
   - The runbook's new checklist item covers only iPhone and Chrome.
   - Fix: one sentence in `docs/playout-setup.md` section 4 step 6 (or the A4 amendment) noting this for VLC/tag-blind clients.
4. **The deployment rule hold-back = lookahead is pinned only for the committed vars, not enforced in `configFromEnv`** (`antenna/src/clock.ts:37-42`).
   - A `wrangler deploy --var PLAYLIST_HOLD_BACK:15`, with L still 12, makes hugo over-read the age by 3·d = 30.7 s and can raise false `dead-clock` alerts. The failure is noisy rather than silent, and spend is unaffected.
   - Fix: a sentence in the runbook that `--var` overrides must keep the two equal. Or clamp `holdBack ≤ lookahead` with a log line. Optional.
5. **Doc wording** (`docs/playout-setup.md:348`). "Its age is its newest segment's start minus its own hold-back" describes the playlist's *date*, not its age. Suggest: "It is dated by its newest segment's start minus its own hold-back (…), i.e. the start of the segment airing when it was written".
6. **Nits.**
   - `clock.ts:37`: the local `const window` shadows a well-known global name. `k` or `windowSegments` would read better; tsc is fine either way.
   - Mutant M15 survives because no test covers off-air before the epoch (the `Math.max(0, …)` in `offairSequence`). This gap predates the task; one assert would close it.
   - `wrangler-config.test.ts:631` hard-codes `(6 + 3)` from transmitter's `_LIVE_WINDOW_SEGMENTS`/`_LIVE_GRACE_SEGMENTS`. The comment names the source, which is acceptable across languages, but a lowered transmitter constant would not trip this test.
   - `deadclock.py`'s off-air docstring says it "under-reads by at least one segment". For an on-time invocation it is about 75 s plus one segment (seqMs = scheduledTime + 75 s). That is accurate as a lower bound, but the size of the delay is worth knowing: a dead clock while off-air alerts roughly 85 s later than `dead_clock_seconds` (~208 s more after a hugo restart, documented).

## Clarity / idiom
- Comment density and naming match the surrounding code.
- The `offairSequence` docstring is a clear, correct derivation, and extracting it into one function shared by `offairPlaylist`/`endlistOnly` removes duplication.
- The `?? 0` defaults for the optional `lookahead`/`holdBack` (three sites) are the price of keeping the existing test `CFG` objects valid, and are acceptable.
- No dead code.

Files reviewed: /Users/shawn/projects/llama/.claude/worktrees/playout-t18/antenna/src/playlist.ts, antenna/src/clock.ts, antenna/public/player.js, antenna/wrangler.jsonc, antenna/test/{playlist,clock,wrangler-config}.test.ts, packages/transmitter/src/transmitter/{deadclock,config}.py, packages/transmitter/tests_transmitter/test_deadclock.py, docs/playout-setup.md, docs/superpowers/plans/2026-10-11-playout-phase2.md.
Mutation log: /Users/shawn/projects/llama/.claude/worktrees/playout-t18/.superpowers/sdd/t18/t18-rev-qual/t18-rev-qual.log
