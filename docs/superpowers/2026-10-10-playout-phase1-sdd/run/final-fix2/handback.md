# final-fix2 handback (playout-phase1, 9fdc47a -> f8b0177)

## Commits
- d27cec8 feat(antenna): off-air without a usable fallback writes an ENDLIST-only playlist
- 94618a7 fix(transmitter): prune never rewrites the horizon without a recorded fallback
- 451b93d docs(playout): off-air without a fallback is ENDLIST-only; prune's fallback gate
- f8b0177 docs(playout): as-built amendments to the spec; plan Task 9 as-built note

## Per ruling
- **A (ENDLIST-only):** `playlist.ts` adds `endlistOnly(g, seqMs)`: header, MEDIA-SEQUENCE by the same `max(0, indexAt(seqMs))` rule as `offairPlaylist`, `#EXT-X-ENDLIST`, no URI lines. `buildPlaylist` returns it when off-air and `usableFallback` is null. The non-off-air null-fallback path is unchanged and still returns null. In `clock.ts`, the `offair-without-fallback` structured error is still logged once per invocation, now worded "written as an ENDLIST-only playlist (no notice), so players stop". The body goes through the normal write path, so MAX_PUTS and the identical-bytes skip still apply: 1 PUT per invocation. For the player I added a pure helper `hlsErrorNotice(data)` in `nowplaying.js`: 403 or `levelEmptyError` returns the off-air text, fatal returns "unavailable", anything else returns null. `player.js` uses it. I checked hls.js source: an empty level fires a non-fatal LEVEL_EMPTY_ERROR and no LEVEL_LOADED. Tests: the flipped playlist test covers three no-fallback causes plus the staleness rule, no URI lines, no DISCONTINUITY, sequence constant and >= live. In the clock tests: puts=1, skipped>0, body has no URI lines, error logged once. New player test: `hlsErrorNotice` in `nowplaying.test.ts`.
- **B (N1 prune gate):** `prune` loads the fallback version after the batching check and before the horizon PUT and any delete. If it is None, it sets `stopped="no-fallback"`, sets `error=NO_FALLBACK` and returns. The horizon rewrite then reuses that version. How it surfaces: `publish_all` -> `_report_stop` -> `ALERT prune: stopped: no-fallback: no fallback rendered …`, and `transmitter publish` exits 1 because `pruned.error` is set. This matches publish's gate, which also surfaces through `error`. I replaced the "inert" wording in `publish.py`'s docstring, NO_FALLBACK, a comment and a test comment, because after A off-air is no longer inert. Confirmed: there are exactly 3 horizon writers (`publish.py:339`, `publish.py:404`, `fallback.py:123`) and all are gated, so "every horizon names a fallback" now holds. CLAUDE.md and runbook §3 step 4 / §4 step 4 are reworded to match.
- **C (O3):** I added a blockquote as-built note under plan Task 9's `render_step` interface line. It says an unchanged on-air row is re-encoded, and `LayoutError` is raised only when the package changed, is no longer eligible, its planned frame count changed, or the encode failed. A frame mismatch on re-encode raises `FrameCountDrift`.
- **D (spec):** five italic "(As built, 2026-10-10: …)" amendments, each checked against the code:
  - the 4-minute prune margin floor, with its derivation; below it is a ConfigError;
  - `min(MAX_PUTS=10, ceil(loopMs/d)+2)`, d≠10.24 refused, LOOP_SECONDS clamped to 75 s;
  - segment N carries discontinuity floor(N/len)+1, with the RFC 6.2.2 reason;
  - native aac is ~128 kbps ABR-like, which nothing depends on;
  - off-air with no fallback writes ENDLIST-only, and a non-off-air window needing a missing fallback is still not written. A Publisher bullet adds that transmitter never publishes or prunes a horizon without a recorded fallback.

## Verification (at f8b0177, teed into final-fix2.log)
- `./.venv/bin/python -c "import transmitter; print(transmitter.__file__)"` resolves inside the worktree.
- `./.venv/bin/python -m pytest -q -p no:cacheprovider`: 2455 passed, 7 deselected.
- `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider`: 306 passed.
- `cd antenna && npm test`: 41 passed. `npm run typecheck` (tsc --noEmit) is clean.
- No ffmpeg code was touched, so the Debian-12 gate was not run.

## Mutation (scratch copy via `git archive | tar -x`; run from the copy; transmitter shadowed with PYTHONPATH and proven by a planted `SENTINEL_COPY`; PYTHONDONTWRITEBYTECODE=1; antenna node_modules symlinked)
- B, prune gate made `if False:`. Predicted `test_prune_never_rewrites_the_horizon_without_a_recorded_fallback`. Observed exactly that one red (`assert None == 'no-fallback'`), 305 others passed.
- A, `buildPlaylist` off-air branch reverted to `: null`. Predicted the playlist ENDLIST-only test plus 2 clock off-air tests. Observed exactly those 3 red.
- A2, `levelEmptyError` clause dropped. Predicted the `hlsErrorNotice` ENDLIST test. Observed exactly that one red.
- After restoring, all suites in the copy were green again. The scratch copy has been deleted.

## Deviations
- The prune test is in `tests_transmitter/test_prune.py`, where every other prune test lives, not `test_publish.py`. I added one `test_service.py` test for the alert line.
- The prune gate sits after the "fewer than prune_min_segments prunable" early return. It therefore fires only when a prune would actually PUT or delete, which avoids a second alert every tick next to publish's. It is still before the horizon PUT and every delete.
- `prune` sets `error=NO_FALLBACK` as well as `stopped`, so the CLI exits 1 and the alert names the fix.
- The player handling is a tested helper rather than a bare one-liner.

## Open questions
None blocking. The web player shows "The station is off the air." on the ENDLIST-only playlist. VLC just stops. This needs a hand check on the Phase-1 checklist if the operator wants it, and is not added to the checklist.
