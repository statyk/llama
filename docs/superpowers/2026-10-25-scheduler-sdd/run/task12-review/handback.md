# Task 12 review (e157449..6e0e282): spec compliance and quality

### Spec Compliance
- Spec "Timeline" (design.md:526-530) asks for the station name instead of "We'll be back shortly." when no show covers the instant, and for the off-air path to keep its own text. Both hold.
- `nowPlayingText(np, timelineLoaded, stationName = "llama radio")` matches the brief's interface exactly. Loaded with no show, it returns `stationName`. Not loaded, it returns "Tuning in…". The show branch is unchanged.
- player.js:161 passes `document.title`, as the brief asks.
- **Off-air claim: verified.** `nowPlayingText` is called only at player.js:161. Every off-air or blocked path goes through `offAir(text)` (player.js:43), which sets its own notice text and clears now-playing to "". The callers are:
  - LEVEL_LOADED with live=false (73);
  - `hlsErrorNotice` (76-77);
  - unsupported browser (82);
  - `playBlockedNotice` (86-87);
  - the `ended` and `error` events (92, 94);
  - the stall probe's `classifyProbe` verdict (147).
  
  After `offAir`, `playing` is false, so the 1 s tick returns at line 152 and never overwrites the notice. offair.html loads no script.
- **`document.title` risk: none found.** No code in antenna/public or antenna/src sets `document.title`, so it cannot echo the previous show between shows. It is the static `<title>llama radio</title>` from index.html:6. A blocked-station swap of index.html to OFFAIR_PAGE affects only fresh loads, and that page has no player.js.
- **pages.ts freshness: fine.** scripts/build-pages.mjs generates src/pages.ts from public/index.html and public/offair.html only. The commit changes neither, so pages.ts correctly did not change. I re-ran `node scripts/build-pages.mjs --check`: it passes silently.
- **Tests cover both branches:** loaded/null with the default, explicit and custom names ("KXYZ" shows the parameter is really used), and not-loaded with and without the name. I re-ran `npx vitest run test/nowplaying.test.ts`: 17 passed. I did not repeat the implementer's full-suite run; their report says 426 passed.

### Strengths
- The diff is minimal and confined to the brief's files and lines. No unrelated churn.
- The default parameter keeps any caller that omits the third argument working. It also makes cache skew between player.js and nowplaying.js (both max-age=3600) harmless in either direction: the worst case is the old "We'll be back shortly." for up to an hour.
- The "KXYZ" assertion rules out a hard-coded return that would have passed the brief's two literal assertions.
- Timeline text still goes to the DOM only through `textContent`.

### Issues
#### Critical
None.
#### Important
None.
#### Minor
1. The test title at antenna/test/nowplaying.test.ts:45 still reads "formats show and file, or says the station will be back". The second half is now stale; something like "or shows the station name" would fit. Cosmetic only.
2. `document.title` is an implicit coupling. If someone later sets the tab title per show (a common player feature), the gap text would start echoing the last show. A comment at player.js:161, or a `const STATION_NAME = document.title` captured once at load, would guard against that. Not a defect today.
3. An empty `<title>` would give empty now-playing text, because the default applies only to `undefined`. `stationName || "llama radio"` would cover it. This is hypothetical.
4. The name is inconsistent across the project. The player uses "llama radio", matching `[antenna] station_name` in docs/playout-setup.md:361. The spec's station-ID example (design.md:103) says "LMA Radio". This is outside this task's scope. It is worth a check before the IDs and the player text go live together, so listeners do not hear one name and read another.

### Assessment
**Task quality:** Approved
**Reasoning:** The change implements the spec's Timeline item exactly as the brief specifies. Off-air text cannot reach `nowPlayingText` or be overwritten by the tick. `document.title` is never mutated. pages.ts is correctly unaffected, and the freshness check and focused tests pass. The remaining items are cosmetic or future-proofing.
