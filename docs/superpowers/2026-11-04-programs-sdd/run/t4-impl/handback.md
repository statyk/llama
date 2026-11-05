# t4-impl handback: Task 4, antenna page (program on tickets, block headings, weekly lineup)

Status: DONE_WITH_CONCERNS (minor; see Concerns)
Commit: 13b380aa antenna: program on tickets, block headings and the weekly lineup

## What was implemented
- `e2e/fixtures/old-index.html`: `git show main:antenna/public/index.html`, taken before index.html was edited (cmp-identical to the then-current file).
- `public/index.html`: `#coming-up` loses `class="tickets"`; new `<section id="lineup" class="schedule lineup" hidden>` after Just aired, with `h2.kick` "The weekly lineup", `#lineup-days.days[role=tablist]` and `ol#lineup-list.lineup-list`. `src/pages.ts` regenerated with `npm run pages`.
- `public/assets/page.js`:
  - `ticket()` uses `presentsLine(show)`; the shared `ticketKey` adds `s.program` (Coming up and Just aired).
  - `renderComingUp`: applies SHOWN first, then `comingUpGroups`; one `div.block-group` per group, with `div.block-head` (`span.block-title`, `span.block-span`) only for keyed groups, then its own `div.tickets`. Its rebuild key covers each group's key, title, span and ticket keys. If `#coming-up` has the `.tickets` class (the old index.html), it renders flat tickets via `renderTickets`.
  - `refreshLineup(now)`, called from `refreshTimeline` after its gate (so it runs with the first timeline refresh and is never fetched while stopped and hidden), refetches once its last attempt is 30 min old. It has its own in-flight flag. A failure keeps the old lineup. It does nothing when `#lineup` is missing (old index.html: no fetch). It reads the body as text even on an error status (see Findings).
  - `renderLineup(atMs)`: returns at once without `#lineup`. It calls `lineupDays(lineup, atMs, undefined, onAir)` with `onAir = onAirKey(timeline, atMs)` (null in the offair state, see Concerns), and hides the section on null. It keeps the selected day in memory and resets it to Today when today's key changes. Tabs are `button[role=tab][aria-controls=lineup-list]`, and selection flips only `aria-selected`/`tabIndex`, so the tabs are rebuilt only when the days change. Roving tabindex plus ArrowLeft/Right/Home/End (wrapping). Entries are `li` (`.variety` when variety) holding `span.at` (time) and `span.t` (title). `li.on-air[aria-current=true]` is set only in Today. textContent only.
- `public/assets/panel.js`: `model.presents ?? "LMA RADIO PRESENTS"`.
- `public/assets/radio.css`: `.block-head` uses the `.kick` look (11px, .16em, uppercase, oxblood) with a dotted rule beneath, and `.block-span` right-aligned (margin-left:auto, so it stays right when it wraps). Also `.block-group + .block-group` spacing, the `.days` tab buttons (`.more`-like; selected is oxblood with label text), and `.lineup-list` rows in the tape-log style. `.variety .t` is italic with `font-synthesis: style`, because Special Elite has no italic face and body sets `font-synthesis: none`, so italics would not render without it. `li.on-air` is oxblood, bold, with the tape log's triangle marker. `.ticket .presents` is single-line with an ellipsis (the ticket's height is fixed), while the panel's presents wraps. Desktop: `.lineup-list` max-width 620px. Only palette variables are used.
- `e2e/serve.mjs`: `index` option (a file path served at `/`).
- `e2e/fixtures/timeline.mjs`: `assignBlocks(timeline, specs)` sets `block`/`nominal_start`/`program` on runs of shows and builds `blocks` (with `start`/`end` overrides, `end: null` to omit).
- `e2e/fixtures/lineup.mjs`: `makeLineup(nowMs, offsetHours, titles)` (3 blocks a day at 5:00 variety, 7:00, 23:00 variety; day -1..8), `nominalStart`, `localMidnight`.
- `antenna/CLAUDE.md` player bullet: `programs` added to the pure modules; the new-module rule; old-index tolerance; program on tickets (fallback, show.html `$presents`, panel); Coming up grouping; lineup source, 30-min refetch, hidden when missing.

## Tests
- vitest: `the player page has a hidden weekly lineup section after Just aired` (verbatim from the brief).
- smoke (24 new): every scenario in the brief's list, plus:
  - keyboard tab navigation
  - offair: nothing is marked on air
  - the chosen tab resets to Today at midnight
  - unparsable, `{"occurrences": 5}` and `null` lineup bodies
  - a failed refetch keeps the lineup
  - Europe/London: the clock's 11:00p block moves to the next morning's tab (Review Focus 2, a zone other than the clock's)
- Existing tests touched:
  - "the page loads ... every asset request succeeds" now serves a lineup, because it asserts every response is ok.
  - "elements are all there" now lists `lineup`, `lineup-days` and `lineup-list`.

## TDD evidence
- RED: `npm run pages && npx vitest run test/indexpage.test.ts` gave 1 failed / 6 passed (the regex found no `id="lineup"`). `npx playwright test --grep "programs and block|weekly lineup|old index.html|block title with markup|60-character"` gave 20 failed. Each failure was a missing element or the old text, for example `#coming-up .block-title` not found, presents "LMA RADIO PRESENTS" where "Gravel & Steel" was expected, and no tabs. All were expected, since nothing was implemented yet.
- GREEN:
  - `cd antenna && npm run pages && npm test`: 27 files, 545 passed (baseline 544 + 1).
  - `npm run typecheck`: clean.
  - `npm run smoke`: 129 passed (3.7m).
  - The 3 tests added after that run started (keyboard, offair, day change) pass separately: 3 passed.
  - After the final CSS tweak (block-head rule), `--grep "programs and block|60-character"` gives 8 passed.
- Frozen files: `git diff --stat main -- antenna/public/player.js antenna/public/nowplaying.js antenna/public/style.css` is empty. `antenna/src/` changes only `pages.ts`, via `npm run pages`.

## Mutation check (scratch `git worktree` in the scratchpad, run from an empty cwd, removed afterwards)
The unmutated copy's baseline passed first. Each mutant failed exactly its predicted test:
- M1, program dropped from the ticket key: "program title change rebuilds the ticket".
- M2, highlight in every tab: "highlighted in Today's tab only".
- M3, old-index flat branch removed: "new assets with the old index.html".
- M4, offair suppression removed: "off the air nothing ... marked on air".
- M5, no reset to Today: "goes back to Today".
- M6, `res.json()` without draining the 404 body: "no request leaves the local host" (networkidle timeout).

## Findings
- An unread 404 body from `fetch` keeps Chrome's request open, so `waitUntil: "networkidle"` never settled. The first full smoke run had 4 failures from this. `refreshLineup` now reads `res.text()` before checking `ok`. `refreshTimeline` has the same unread-404 pattern for timeline.json, but it was left alone (unchanged, out of scope).
- Routed (`page.route`) answers never reach the fake server, so those tests count the page's own requests.
- 320 px: main page and panel `scrollWidth <= 320` with a 60-character program (words) and a 60-character unbroken block title, in Coming up and in the lineup.

## Concerns / judgement calls for review
1. In the offair state `renderLineup` passes a null on-air key. The brief says to pass `onAirKey(timeline, atMs)`, but the rest of the page shows nothing on air when off air (`onAirShow`), so the lineup now does the same. This is pinned by a test, and it is a one-line revert if unwanted.
2. On a ticket, a long program ends in an ellipsis on one line (like `.artist`), not wrapped, because the ticket's height is fixed and a wrapped line would collide with the date row. The full text is still the element's textContent. In the panel it wraps.
3. A lineup day with no entries shows an empty list, with no copy added (the brief gives none).
4. A block on air whose nominal start falls on tomorrow's local date (for example a block that starts early just before midnight) is not highlighted anywhere, per "Today only".
5. The `.ticket .presents` program is shown in its own case. The house line is literal uppercase text, and there is no CSS uppercase.
