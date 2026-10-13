VERDICT: OPEN FINDINGS (one Minor, a one-word wording fix in F6; everything else ADDRESSED, no new breakage)

# t18-rerev1: re-review of fix round 1 (906222e..80e2223, one commit 80e2223)

## Per item

- **F1 ADDRESSED.** docs/playout-setup.md:220-224. The "~100 s late does not stall" claim is gone, and no other copy of it exists in docs/ or antenna/. The new text matches brief.md: 45/60 s freezes play through, 75/90 s freezes give 1-3 s drops that heal, also with the screen locked. The lag mapping (freeze ~ lag - 15 s, so 60 s ~ 75 s late and 75-90 s ~ 90-105 s late) is consistent with the brief.
- **F2 ADDRESSED.** Plan line 70.
  - (a) The single-tag runs are VERSION 3 (START 120 s, HOLD-BACK 116 s) and the both-tags run is VERSION 6 (113 s). This matches brief.md.
  - (b) The on-time failure reason is present, worded as the fix brief dictated. See the nuance under Informational.
  - (c) The ~2.5 min Safari latency is stated, superseding Review Focus 5 / A2's ~45 s; spend is unaffected. This is consistent with player.js: native Safari reaches the probe path only after its buffer plays out. hls.js still detects at the playlist reload (LEVEL_LOADED live===false at player.js:72-74, or the ERROR path). setup.md:466 agrees.
  - (d) The freeze measurements are included.
- **F3 ADDRESSED.** The constructor at antenna/public/player.js:71 is `new window.Hls({ maxBufferLength: 130, backBufferLength: 30 })`, and the comment says maxBufferLength must exceed PLAYLIST_HOLD_BACK × 10.24 = 122.88 s. Source-verified against antenna/node_modules/hls.js/dist/hls.mjs. The package is 1.7.3, the lock pins 1.7.3, and deploy-assets.mjs:31 ships dist/hls.min.js from it.
  - HOLD-BACK is parsed from SERVER-CONTROL unconditionally, with no VERSION or low-latency gate (hls.mjs:9417).
  - `get targetLatency` (hls.mjs:34966-34989): `targetLatency = lowLatencyMode ? partHoldBack || holdBack : holdBack` (34983). The config fallback applies only if `_targetLatencyUpdated || userConfig.liveSyncDuration || userConfig.liveSyncDurationCount || targetLatency === 0`. The fallback is `liveSyncDuration ?? liveSyncDurationCount(default 3, hls.mjs:38149) * targetduration` (34984-34985).
  - Measured in node, by constructing Hls and stubbing latestLevelDetails:
    - the constructor succeeds; userConfig is exactly {maxBufferLength:130, backBufferLength:30}, liveSyncDuration is undefined, startPosition is -1;
    - targetLatency with HOLD-BACK 122.88 is **122.88**;
    - with no tag and TARGETDURATION 11 it is **33** (3 target durations);
    - contrast: a user liveSyncDuration overrides HOLD-BACK (old ctor + HOLD-BACK 40 → 122.88), which confirms the removal was needed for "one source of truth".
  - EXT-X-START also applies. The default `startPosition: -1` (hls.mjs:38101) leads to setStartPosition (11693-11725), which uses the media playlist's `startTimeOffset` (parsed at 9374/9633-9635, finite only). For a negative offset that gives `sliding + offset + details.edge`, clamped to the window. So the join point comes from EXT-X-START, and later re-syncs come from HOLD-BACK (liveSyncPosition). Both are 122.88.
  - Since base 7c93250, the player.js diff is only the Hls constructor plus its comment (git diff 7c93250..80e2223 -- antenna/public/player.js). The off-air (LEVEL_LOADED/ERROR/ended/error/pause), StallWatch and probe paths are untouched.
- **F4 ADDRESSED.**
  - The comment at config.py:103-105 now describes hold-back dating.
  - The deadclock.py:76-79 docstring adds the on-time off-air under-read and the restart caveat. I checked the arithmetic. The off-air body is constant within an on-time invocation (one PUT at S+lag; identical bytes are skipped), and seq = indexAt(S+75)+L+1. So the read is T - start(indexAt(S+75)) - d against a true age of T - (S+lag), an under-read of 75 + d - frac - lag. That is 75-85 s for lag≈0, so "~85 s" is the upper end. After a restart, live_hold_back_s=0 adds L·d, so "more after a hugo restart" is correct.
- **F5 ADDRESSED; all three new asserts discriminate.** Mutants ran in the scratch copy, with PYTHONPATH shadowing proven by a planted sentinel: `transmitter.deadclock.__file__` resolved to the scratch path and SENTINEL_T18 == "scratch". Runs used PYTHONDONTWRITEBYTECODE=1, -p no:cacheprovider and __pycache__ cleared per mutant, over the full tests_transmitter suite. Each mutant's red test was predicted in advance and matched:
  - M1, abs() on the offset (`offset != 0 → abs(offset)`): predicted red test_a_malformed_or_positive_offset_is_ignored, at the positive-START assert. Got 1 failed / 456 passed, at test_deadclock.py:66: `assert 122.88 == 40.96`. Before F5(a) gave HOLD-BACK a different magnitude, this mutant would have survived.
  - M2, SERVER-CONTROL wins (START no longer returns early; SERVER-CONTROL returns): predicted red test_start_wins_over_server_control_when_both_differ. Got 1 failed / 456 passed, at :78 (-81.92 vs 0.0).
  - M3, the isfinite check dropped: predicted red the same malformed test at the -inf assert. Got 1 failed / 456 passed, at :69: `assert inf == 40.96`.
  - (c) covers both fall-through outcomes for -inf: to HOLD-BACK 40.96 (:69), and to the newest segment when HOLD-BACK is also malformed (:71).
- **F6 PARTIAL (Minor).**
  - Step 6 (setup.md:224-233) has everything F6 asked for: the VLC/no-tag case (~92 s ahead, ~31 s runway), keeping HOLD_BACK = LOOKAHEAD, and the R>L / R<L directions. I checked the directions against the code: age = now - newestPDT + R·d, so R>L reads older (false alerts) and R<L reads younger (late detection). The "do not lower the lookahead casually" warning and its reason are also there.
  - **Line 356 does not carry the requested wording.** The brief asked for "It is dated by its newest segment's start minus its own hold-back". The commit has "**Its age is dated by** its newest segment's start minus its own hold-back". An age is not "dated by" a start time, so the sentence still conflates the two. Fix: replace "Its age is dated by" with "It is dated by" (setup.md:356). A one-word edit; no re-review needed beyond a glance.
- **F7 ADDRESSED.** antenna/src/clock.ts:37-42 uses `windowSegments`; the returned field is still `window`, so the API is unchanged. No other bare `window` binding is left in clock.ts. tsc is clean.
- **F8 ADDRESSED; the test discriminates.** It is antenna/test/playlist.test.ts:290-294; the expected value is 0+2+1 = 3, and unclamped it would be -5+3 = -2, as the comment says. I ran a scratch mutant that drops `Math.max(0, …)` in offairSequence (playlist.ts:80). Predicted red: "numbers an off-air playlist built before the epoch from 0, never negative". Got exactly that one test failing: 1 failed / 235 passed. The scratch baseline was 236/236. So no pre-existing test pinned the clamp, and this one does.

## Account identifiers
None. The added lines of the fix diff contain no 32-hex IDs, email addresses, token, key or secret strings.

## New breakage introduced by the fix diff
- Critical: none.
- Important: none.
- Minor: none beyond the F6 wording above.

## Informational (not blocking; dictated by the fix brief or pre-existing)
1. **F2(b) precision.** Under the realizable cron lags, the decisive on-time failure of the plan's rule is EQUALITY. A live write at the invocation's own start t lists indexAt(t)+L, and the plan's rule gives indexAt(t + L·d) = indexAt(t)+L for L=12, where the second term always dominates S+75. That equality is why the `+1` is needed. The doc's "live write just before S+75" argument holds under the code's stated invariant (a constant seq covering writes up to seqMs), but it is the stronger of the two framings.
2. **deadclock.py:75 (pre-existing text, not this round)** says the off-air read "under-reads by at least one segment". In fact the under-read is 75 + d - frac - lag for lag ≤ 75, and d - frac when the now-term dominates, which is less than one segment. "Never false-alarms" is still true. Suggest "by up to …" or "always under-reads" if it is touched again.
3. **test_deadclock.py:64-65.** The comment "newest segment 112 starts at now - 40.96 s + age" is garbled. The assert is right: now = start(112), so age = 40.96.
4. **setup.md:229-230.** "~3 target durations … ~31 s runway" mixes units. 3 × TARGETDURATION = 33 s (hls.js's fallback, measured above), while 31 s ≈ 3·d. The size of the error is about 2 s.
5. **Unmeasured combination.** The shipped combination (both tags at VERSION 3) was not itself one of the measured iPhone runs. The docs do not claim it was. This round adds a VERSION-6 caveat to the plan, but playlist.ts:23 says "iOS honours both at VERSION 3", which is accurate per tag. The phase-2 checklist item at setup.md:467 is the place this gets confirmed live.

## Gates (re-run by me in the live worktree at 80e2223; worktree left clean)
- `cd antenna && npm test` → Test Files 14 passed (14), Tests **236 passed (236)**. `npx tsc --noEmit` → exit 0.
- `PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider` → **457 passed, 1 skipped**.
- The same suite with `./.venv311/bin/python` → **457 passed, 1 skipped**.
- Not re-run by me: the full `./.venv/bin/python -m pytest -q` suite and test-in-debian12.sh. They were not in my re-run list.

Scratch: /private/tmp/claude-501/t18-rerev1-scratch (git archive 80e2223, node_modules symlinked). Mutants were restored after each run. Log: $D/t18-rerev1/t18-rerev1.log.
