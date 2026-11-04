Status: DONE_WITH_CONCERNS
Commits: 85792e10 antenna: the slide-up notes panel
Tests: npm test 516 passed (26 files); tsc clean; npm run smoke 55 passed (40 + 15 new).
Concerns: (1) three files outside the brief's list changed, small (page.js, show.js + timeline.js, radio.css); (2) the panel stub reads "Nov 1 / 1985", the show page "SAT NOV 1 / 1985"; (3) copy for the share control and its notes is mine.
Handback: /Users/shawn/projects/llama/.claude/worktrees/player/.superpowers/sdd/player/t10-impl/handback.md

## Implemented
- `antenna/public/assets/panel.js` (new): `openPanel(slug)`. The `.panel` element is created at module load, so the slide-up transition has a closed state to start from.
  - Open: `pushState({ panel: slug }, "")`, or `replaceState` if already open. Loading state at once ("Loading…"), then the fetch through a generation counter, bumped by each open and by each close, so a late answer is dropped after a second tap and after a close.
  - Close: the Close button and Escape call `history.back()`, ignored while one is pending; `popstate` does the closing. Nothing opens on load.
  - Focus goes to Close on open and back to the previously focused element on close. On iPhone Safari a tapped link takes no focus, so there the return is a no-op.
  - Render: `"old"`, a failed fetch, or any exception while building the view gives a new-tab "Open the show page" (`target=_blank rel=noopener`). `"ready"` follows show.html: `.bigt .bstub .bmain`, `.cols`, `.jcard`, `.meta`, `.liner`, `.fineprint`. Archive button only with `archive`. "No notes yet." on empty sections; "No setlist." as on the show page. Set labels use site.py's wording, only with more than one group; null or absent set prints nothing. Air times as on the show page: "Not currently scheduled." with none, "Airtimes unavailable." on a bad time (the rest of the notes stay). Blank where and lineage are left out. A blank artist falls back to the slug, as in site.py.
  - Share: button "Copy link to this show" copies the absolute `showHref(slug)` and says "Link copied."; if the clipboard refuses, it prints the URL for selecting.
  - No link back to the station. textContent only; the asset ban test covers panel.js.
- `app.js`: `ticketLinks(document, openPanel)`.
- Fixtures: `e2e/fixtures/notes-{full,old,empty}.json`.

## Beyond the brief's file list (please rule)
- `page.js`: `el` is now exported (one word), so panel.js has no second copy.
- `show.js` to `timeline.js`: `airLine` moved unchanged and exported, since show.js cannot be imported (it runs on load) and a second copy of the format could drift. The show page smoke tests still cover it.
- `radio.css`: two lines, `.panel-bar` sticky row and `.panel-bar .more`, for the Close control. Close uses the existing `.more`. The sticky behaviour was not exercised: the sample notes didn't overflow.

## Tests
Smoke, 15 new under "notes panel": the six brief scenarios (the failed-fetch case as a seventh sibling of "without sections") plus: loading state before the answer; the full ready content, archive and share; share with a refusing clipboard; set labels and null set; Escape, double close and focus; reload with the panel open and its stale entry; notes arriving after a close; a bad air time.
The history test puts a same-origin page behind the player, so a back past the player shows in the URL: after back, Close, and a second ticket while open (replaceState), one more back lands on that page.

RED: `npx playwright test -g "notes panel"` before panel.js: 15 failed.
GREEN: same command: 15 passed. One failure on the way was my expectation: tidyTitle rewrites a trailing `>` on the hostile `</script>` title, which is the correct behaviour, so the test now applies the rule.
Final, at 85792e10's content: `cd antenna && npm test`: 26 files, 516 passed. `npm run typecheck`: clean. `npm run smoke`: 55 passed (3.1m).
Frozen files: `git diff 6cc6dae0 -- public/player.js public/nowplaying.js public/style.css`: empty. `deploy-assets --dry-run` lists assets/panel.js. Nothing deployed.

Mutants, in a scratch `git archive` copy with the failing test predicted first; baseline there 15 passed:
- generation check removed: two fast taps, and notes after a close, failed (both predicted).
- pushState in place of replaceState while open: the history test failed.
- closing guard removed: the Escape/double close test failed.
- null check removed from setLabel: the set label test failed.

## Files
Created: antenna/public/assets/panel.js, antenna/e2e/fixtures/notes-full.json, notes-old.json, notes-empty.json.
Modified: antenna/public/assets/app.js, page.js, show.js, timeline.js, radio.css, antenna/e2e/smoke.pw.mjs.
Screenshots, phone and desktop: /Users/shawn/projects/llama/.claude/worktrees/player/.superpowers/t10-shots/panel-390.png, panel-1200.png (the throwaway script that took them is not committed).

## Self-review
Read the diff. Removed one unneeded background override on Close. Considered and left out: a guard for a tap during a pending close (the popstate closes either way, same result); a fallback when the focused ticket was rebuilt while open (focus on a detached element is a no-op; rebuilds happen at show boundaries).

## Concerns
1. The three changes outside the file list, above.
2. Stub date: panelModel gives "Nov 1 1985" with no weekday, so the panel splits off the year and shows "Nov 1", unlike the show page's "SAT NOV 1". A weekday would need the raw date in the model or a change to notes.js.
3. Not in the plan's exact copy, chosen by me: "Copy link to this show", "Link copied.", "Close", "Loading…".
4. The panel is non-modal (no focus trap, page stays live), because the spec says the page's controls keep working. On a phone it covers them, as designed.
5. A forward press after a back lands on the old panel entry without opening it, by design ("nothing opens"); a ticket tapped there leaves one extra entry, on the same URL, so it only costs one extra back.
