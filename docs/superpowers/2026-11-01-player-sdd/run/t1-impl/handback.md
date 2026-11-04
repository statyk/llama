Status: DONE_WITH_CONCERNS
Commit: see the final reply (antenna: asset walker, preview rounds and the early iPhone probe)
Tests: antenna npm test 426 passed (21 files); tsc clean; dry-runs correct; stubbed-npx runs; probe exercised in Chromium.

## Implemented
- antenna/scripts/deploy-assets.mjs: walker over public/assets/ (preview/ left out of the live upload; a missing folder is fine), TYPES table, unknown extension exits 1 naming the file before any upload, --preview <n>, --remove-preview <n>.
- .gitignore: antenna/.preview-*.json.
- antenna/public/assets/preview/probe.html, probe.js. R3's static apple-mobile-web-app-capable meta is in. No hls.js.

## Beyond the brief's letter (all small, say if unwanted)
- The key list is written BEFORE uploading and unions with an existing list of the same round, so a failed upload or a file dropped between rounds leaves nothing unremovable.
- All file checks run before the first upload (the old script checked mid-loop).
- --remove-preview honours --dry-run and keeps the list on a failed delete.
- A round name must match ^\w[\w-]*$; missing/odd exits 2, as does combining --preview with --remove-preview.
- probe.webmanifest has a name field.
- Stop also ends the retry loop. Otherwise audio returns up to 30 s after pressing Stop.
- Metadata is not updated while stopped or paused (tick lines still run, title="(not updated)"): a real player wouldn't, and tests 5-6 ask what survives that state.
- popstate, the archive link tap and a timeupdate tick line are logged, because rows 1 and 8 need them.
- Media Session artist/album read "artist field"/"album field", so row 7 shows which fields the car displays.

## Log format
tick <source> n=<k> [LATE] [STALL] gap= played= stuck= ct= buf= paused= rs= ns= net= vis= title=
LATE: gap over 7.5 s (the timer slept). STALL: the page wants audio and it advanced 2 s+ less than the wall clock across the tick. stuck: seconds since currentTime last rose, kept across retry restarts. "wants audio" is the page's intent, so a stall where iOS pauses the element still flags.

## Tests
- Step 3 dry-runs: five old keys, nothing under preview/, max-age=3600. --preview 1 --dry-run: five keys under assets/preview/1/, max-age=60; no list written.
- --remove-preview nosuch: "missing antenna/.preview-nosuch.json: no upload recorded for round nosuch", exit 1.
- Scratch tree + stub npx on PATH, nothing reached the network: live upload 5 puts; --preview 2 writes the list and the generated manifest has the right start_url/scope; remove --dry-run keeps the list; failing delete exit 7 keeps it; remove runs 5 deletes and drops it; failed upload leaves a list; temp dir cleaned.
- Walker: nested fonts/a.woff2, all seven types correct, radio.webmanifest rewritten in preview ("start_url": "/assets/preview/4/index.html", "scope": "/assets/preview/4/"), unknown .bin exits 1 with zero npx calls and no list, .bin under preview/ ignored live and refused in preview, no public/assets: 5 keys live, exit 0.
- Probe in Playwright Chromium (a WAV standing in for the stream, scratch server, URL shape as production): Start, ended, retry loop 2 cycles at gap=30.0s, Pause only, pushState + back (popstate), Stop, reload survival, Copy via writeText ("Copied 97 lines"), fallback with writeText rejected (box stays, whole text selected, message shown), execCommand fallback, media session handlers called directly (pause/stop log only, play restarts). Manifest link fetched from /assets/preview/1/probe.webmanifest. 390x844 layout checked by screenshot. 30 min of ticks ran with no fault.
- NOT tested: anything on iOS, native HLS, real offline, real Media Session UI. Clipboard on iOS is by recipe (select + setSelectionRange on a readonly textarea, inside the tap).

## Self-review
Caught and fixed: my first refactor dropped "wrangler" from the command (npx r2 ...), seen in the first dry-run output. Diff re-read; nothing else. player.js, nowplaying.js, style.css, src/ unchanged (0 diff lines).

## Concerns
1. Media Session pause and stop handlers log ONLY, as the brief says. Registering them replaces iOS's default, so lock-screen or car Pause may do nothing audible during the test, and Bluetooth off may leave audio on the phone speaker. Kept deliberately: an element `pause` after a handler line is then iOS's own doing, which is the cleaner evidence for D1/D2. The operator must be told. To change it, one line in probe.js.
2. A home-screen app has its own localStorage on iOS, so Safari and home-screen logs are separate: Copy from each.
3. docs/superpowers/2026-11-01-player-probe.md is NOT created: it holds Step 6 instructions and Step 7 results, out of my scope. Operator instructions still need writing; the table below can seed them.
4. A stray .DS_Store under public/assets/ would exit 1 as unknown type, per the brief's rule. Clear, not silent.
5. Today's public/index.html loads style.css and player.js relatively, so assets/preview/<n>/index.html is broken until later tasks move them. The probe is unaffected.
6. The log has no Clear button (not in the brief); it rolls at 6000 lines, about 4 hours. Copy after each test.
7. A 30-minute hang in this run was my test's clipboard.readText in Playwright, not the page.

## Step 6 table: the lines that answer each row
1. timers/timeupdate while locked: `visibilitychange ... vis=hidden`, then `tick interval` and `tick timeupdate` lines with vis=hidden; gap near 5 s = running, LATE = slept. Title: read the lock screen; its clock in the title compares against the tick lines' title="#N source HH:MM:SS".
2. event order: `offline`, then `event waiting/stalled/pause/error/ended/suspend` in order. buf= shows the runway draining. Stall confirmed by `STALL` and growing stuck= (or, if timers froze, one LATE STALL line on thaw with played far below gap). pause: `event pause` with no `button` line before it. Recovery alone: `online`, then `event playing` and played= back near gap, no button or action line between.
3. `retry N: gap=...` then `retry N: play() resolved` or `play() REJECTED <name>`; after `online`, success = resolved, `event playing`, ct rising. Absent retry lines while locked = timers frozen.
4. tick lines through the outage with stuck= passing 600 = limit enforceable; if none, one LATE line on thaw with the true gap.
5. `button Stop`, `teardown`, then `media session action play` = reached the page (absence = did not), then `media session play: play() resolved|REJECTED`.
6. `button Pause only`, `event pause`, then the same lines as 5.
7. What the car shows: operator's eyes; title/"artist field"/"album field" name which fields it uses. Bluetooth off: `media session action pause|stop` and/or `event pause`, in order, with no button line.
8. `standalone=true` on the load lines proves the launch mode; tests 1, 2, 5 read as above. Back swipe: `button pushState`, then `popstate` with paused= and ct= showing audio survived. Archive: `link archive.org`, then `visibilitychange`/`pagehide`, ticks with played near gap = audio survived.
