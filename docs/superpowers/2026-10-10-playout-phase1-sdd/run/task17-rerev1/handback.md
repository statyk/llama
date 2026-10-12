Task 17 fix round 1 re-review (0a62d0f..04b6df6)
1 ADDRESSED: player.js:70-73 + nowplaying.js:13-20. Re-probed in headless Chrome (system Chrome, playwright-core run from the scratchpad, nothing written to the worktree) against `git archive 04b6df6`. With an ENDLIST playlist the notice now reads "The station is off the air.", with 1 live.m3u8 fetch.
2 ADDRESSED for the hls.js path: player.js:83-85. After an external audio.pause() the button showed "Play" and live.m3u8 fetches stayed at 1 → 1 over 25 s. New breakage on the native path is below.
3 ADDRESSED: index.html:10 (`data:` icon).
4 ADDRESSED: deploy-assets.mjs:19,44. The dry-run now prints `--content-type 'text/html; charset=utf-8'`.
5 ADDRESSED: deploy-assets.mjs:30-31. index.html is the sixth (last) dry-run line.
6 ADDRESSED: deploy-assets.mjs:48.
7 ADDRESSED: nowplaying.test.ts:52-63 (start-inclusive/end-exclusive boundary, plus the unsorted-files case pinning the `break`). playBlockedNotice is tested at :65-71.
New breakage (Important): the pause→stop handler (player.js:83-85) swallows `ended`, so the off-air notice never shows on the native (Safari/iOS) path.
- At natural end of media, the element fires `pause` and then `ended`, both from the same queued task. stop() calls audio.load(), which cancels the element's pending events, so `ended` → offAir() never runs.
- Prediction named first, then measured in Chrome on a micro page that mirrors stop()'s removeAttribute+load: without the pause→load handler the log is [playing, pause, ended]; with it, [playing, pause] and no `ended`.
- WebKit could not be checked here. Its prepareForLoad also cancels pending media events, so the same outcome is expected.
- Effect: a Safari/iOS listener reaching ENDLIST plays the notice segment, then the player silently resets to "Play" with no notice and stale now-playing text. Spend is unaffected, because stop() still tears everything down.
- Fix: `if (playing && !audio.ended) stop();` (audio.ended is already true when that pause fires).
Out of scope: none.
Verdict: Needs fixes (one line, player.js:84).
