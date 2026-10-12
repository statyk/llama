VERDICT: Approved

Review of 9fdc47a..f8b0177 (4 commits), playout-phase1. No Critical or Important findings. All four rulings (A-D) are implemented as ruled, and nothing outside their scope changed behaviour.

## Findings (all Minor, optional)
1. Minor: `transmitter publish` exiting non-zero on a prune `no-fallback` stop is not pinned by any test. The exit is correct today, via `pruned.error` (packages/transmitter/src/transmitter/cli.py:97). But mutant MB3 drops the `pruned.error or` and still leaves the whole suite green. Fix: add a test_cli.py case that monkeypatches `service.publish_all` to return `PruneReport(stopped="no-fallback", error=NO_FALLBACK)` and asserts exit_code == 1 with "prune: no-fallback" on stderr.
2. Minor: alerts are doubled when fallback.json is lost. In steady state, `publish_batch` raises `ALERT publish: …no fallback rendered…` (publish.py:285) and prune raises `ALERT prune: stopped: no-fallback…` (publish.py:392). Both fire every tick: 2 ERROR log lines a minute in phase 1, and 2 distinct dedupe keys in phase 2. This is not a spend issue and not a storm beyond publish's existing per-pass alert. Fix (optional): in `service.publish_all` (service.py:148-149), log prune's no-fallback at WARNING when a publish report in the same pass already carries `NO_FALLBACK`.
3. Minor: the "player page shows its off-air notice" claim is only verified for hls.js (docs/playout-setup.md, section 4 step 4). On native HLS (Safari), a zero-segment ENDLIST playlist at start probably fires `error`, which shows "The stream is unavailable right now." (player.js:77-79). Mid-stream it should play out and fire `ended`, which shows "off the air". Either way the player stops and polls nothing more, so there is no spend or loop risk. Fix: reword to "players stop (hls.js shows the off-air notice; native players may show 'unavailable')", or verify on Safari.
4. Minor: the spec's as-built note says "storage comes in under the estimate below" (spec:301-302), but no measurement in the repo backs it. aacenc.py:4-8 says only that silence encodes small. Fix: "at or under", or cite the measurement.
5. Informational, no action: the ENDLIST-only playlist shares two RFC 8216 deviations with the approved notice playlist. (a) It removes segments below 3×TARGETDURATION and jumps MEDIA-SEQUENCE (§6.2.1/6.2.2 strictly constrain live-playlist edits). (b) It omits DISCONTINUITY-SEQUENCE. A zero-segment Media Playlist is not itself invalid. hls.js 1.7.3 parses it with no parsing error: I ran the vendored M3U8Parser on the exact body and got frags=0, live=false, playlistParsingError=null.

## What I checked
- A (playlist.ts:67-75, 92-95; clock.ts:176-202). Off-air with no usable fallback now gives `endlistOnly`: header, MEDIA-SEQUENCE = max(0, indexAt(offairSeqMs)) (the same expression as offairPlaylist:54), ENDLIST, and no URIs. It goes through the unchanged write path: identical-bytes skip (:192), `puts >= cap` (:196), cap = min(MAX_PUTS=10, …) (:118-120). The body is constant within an invocation, so it costs 1 PUT per invocation (~44k Class A/month, below the on-air rate). Off-air is read once per invocation and the stale rule is monotone in now, so within an invocation the sequence cannot fall below a live sequence already written. When on air, a null fallback still gives null, with no log and no write (playlist.ts:100; offairWithoutFallback returns null when !isOffair, clock.ts:125). The loud log is still logged once per invocation (:183-189). No new listener-billed path: live.m3u8 is the same object with the same cache headers.
- hls.js 1.7.3 (the vendored copy is the one deployed: scripts/deploy-assets.mjs:30). An empty media playlist reaches `handlePlaylistLoaded`. That function fires ERROR with details=levelEmptyError, fatal:false, and returns before LEVEL_LOADED (playlist-loader.ts:758-776). This holds for the manifest path too (:346-350). error-controller.ts:167-188 escalates a non-live empty level to fatal, but the details string is unchanged, so `hlsErrorNotice` returns "off the air" either way (nowplaying.js:26-31). `offAir` then calls `hls.destroy()`, which stops all polling (player.js:27-44). A live window always has ≥1 entry (playlist.ts:33-40), so a levelEmptyError never comes from an on-air playlist and the off-air notice cannot show by mistake.
- B (publish.py:392-400). The gate is after the guard, high-water and batching checks, and before both the horizon PUT (:404) and every delete (:425). It costs no PUT budget (the test asserts puts_path absent). There are 3 writers of state/horizon.json, by grep of HORIZON_KEY/horizon_doc: publish_batch (:339, gated at :283-292), prune (:404, gated), and fallback.upload_fallback (fallback.py:123, writes its own `build.version`). The only delete is prune's. So every horizon names a fallback, as the docs claim.
- C: the plan Task 9 note matches pipeline.py:239-284. The re-encode happens only when the key is the same, the show is eligible and the planned frame count is the same. FrameCountDrift is raised on an encode mismatch. Otherwise LayoutError is raised when on air.
- D: every amendment matches the code. Prune floor: config.py:57-71,84 ((6+3)·10.24+5+120 s → 4 min, ge=floor). Spend bounds: clock.ts:77-79,156-172. Discontinuity sequence floor(N/len)+1: playlist.ts:106-121. Native aac: aacenc.py:4-8,23-29. ENDLIST-only: as above.
- CLAUDE.md, runbook and docstrings: the ALERT text matches `_report_stop` (service.py:122-123). The "publish, prune and fallback render are its only writers" claim checked out by grep.

## Mutants (scratch copy; shadowing proven by planted sentinels: a py module attr and a failing vitest file; PYTHONDONTWRITEBYTECODE=1). Every prediction held:
- MA1 off-air no-fallback → null: red on playlist "goes off-air with an ENDLIST-only…" plus 2 clock off-air tests (3).
- MA2 endlistOnly fed nowMs instead of seqMs: red on the same 3.
- MA3 drop the levelEmptyError clause: red on nowplaying "treats the clock's ENDLIST-only playlist…" (1).
- MA4 disable the identical-bytes skip: red on 4 clock tests, including "writes the ENDLIST-only playlist once".
- MA5 log only when body===null (old placement): red on 2 clock off-air tests.
- MB1 remove the prune gate: red on test_prune_never_rewrites_the_horizon_without_a_recorded_fallback.
- MB2 gate without error text: red on the same test.
- MB3 CLI ignores pruned.error: GREEN (Finding 1).

## Runs
- `./.venv/bin/python -m pytest -q -p no:cacheprovider`: 2455 passed, 7 deselected.
- `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider`: 306 passed.
- `cd antenna && npm test`: 41 passed (3 files). `npm run typecheck`: clean.
- The worktree is clean. Nothing was committed or edited.
