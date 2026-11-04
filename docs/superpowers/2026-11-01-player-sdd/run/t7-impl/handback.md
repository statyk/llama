Status: DONE_WITH_CONCERNS
Commit: 28f39ada antenna: render the schedule, tape log and label
Tests: antenna npm test 515 passed (513 + 2 new); npm run smoke 14 passed (twice in a row); npm run typecheck clean.

## Implemented
- antenna/public/assets/page.js: renderAt, setState, refreshTimeline, currentTimeline, ticketLinks (createElement/textContent only). State table per brief; #label-status hidden only in offair; #retry for gaveup/offair/refused. Lists rebuild only when a content key changes. Headings (tape log, coming up, just aired) hide when the list is empty (found via closest("section, .tape-log").querySelector(".kick"); no index.html change). Tape log uses tidyTitle. Coming up shows 6 plus a ".more" "Show all" button (id show-all, created by page.js after #coming-up); just aired 6. #schedule-note: "The schedule isn't available right now." (no timeline) / "Nothing further is scheduled yet." (comingUp empty). Fetch: /timeline.json with no query string, 3 min wait, gate "playing|reconnecting|!document.hidden" applies to force too, failure keeps old timeline and waits 3 min (lastAttempt set at attempt start), in-flight guard.
- app.js: stream URL, one 1 s loop (tick runs once immediately).
- e2e/fixtures/hostile.json: notes-shape document (sections, setlist, slug, artist, venue, city, date, title, lineage, url, page, notes, airtimes) with markup in every field.
- test/asset-bans.test.ts (glob assert timeline.js and page.js found; ban regex). Bite check in a scratch copy (scratchpad/mut): appending innerHTML to page.js failed the test.
- smoke.pw.mjs: after-every-test guard (request allowlist, no console errors except 403/404, no pageerror) plus the 6 brief scenarios, and extras: visible fetch cadence (1 fetch, none at +2 min, second after +3 min), offair hides #label-status (via dynamic import setState, all other states show it, #retry), ticketLinks plain/modified click, Show all.
- Removed an obsolete assertion in the old element test (label "LMA Radio" before timeline loaded; label now fills from the timeline).

## Concerns
1. Mutation not run on the smoke tests (hidden-gate, offair); only the bans test bite was checked, per brief.
2. The "adds no element" check compares total element count against the same page with a benign timeline, plus no img/iframe/svg/script and window.pwned undefined.
3. Hostile slug is on a coming-up ticket (the on-air show is not a ticket).
4. "Show all" is not reset if the list shrinks; once pressed it stays.
5. Headings can only be hidden via DOM lookup since no ids exist; coming-up heading hides along with the zone staying visible.
Files: antenna/public/assets/{page.js,app.js}, antenna/e2e/{smoke.pw.mjs,fixtures/hostile.json}, antenna/test/asset-bans.test.ts.

## Fix round 1
Status: DONE
Commit: see git log (antenna: smoke guard sees every request; pin tidyTitle and failed-fetch wait)
- smoke.pw.mjs: beforeEach records page.on("request") URLs into `seen` (survives server swaps); afterEach fails any URL that is not data:/blob: and whose hostname is not the local host, or whose pathname+search fails ALLOWED.
- hostile.json: track title now ends in "->" so the tidyTitle assertion bites. Mutant (raw e.title in page.js, scratch copy): hostile test red; restored page.js: green.
- New test "a failed fetch waits out the same 3 minutes" (startServer({}), 1 request over 2 min, 2nd after 3). Mutant (lastAttempt set only on success, scratch copy): that test red.
- Tests: `cd antenna && npm test` 515 passed; `npm run smoke` 15 passed; typecheck clean.
