Status: DONE_WITH_CONCERNS
Commits: 3efb6668 transmitter + antenna: show pages from sections
Tests: transmitter 947 passed, 1 skipped (macOS); Debian-12 gate 948 passed; antenna npm test 516 passed; typecheck clean; smoke 40 passed.
Concerns: (1) `$artist` placeholder added, not in the brief's list; (2) the template's `<b>` carry a class because the brief's test forbids a bare `<b>`; (3) `$lineage` now holds a fragment; (4) serve.mjs and smoke.pw.mjs changed, outside the brief's file list; (5) set labels are my wording.
Handback: /Users/shawn/projects/llama/.claude/worktrees/player/.superpowers/sdd/player/t9-impl/handback.md

## Implemented
- site.py: `concert_stub` (string parse plus datetime.date for the weekday, own English tables, no strftime; never raises), `where_line`, `render_show_page` from `notes["sections"]` (signature unchanged). One setlist rule matching notes.js `setlistLine` (regex identical to tidyTitle). Setlist grouped by consecutive set, labels only with more than one group. Description: first p or first bullet, whitespace folded, cut at 200, title when no sections. Archive button via `archive_link`, target=_blank rel=noopener. og:image only with site_url. page_url now encodes the slug (global constraint; safe set = encodeURIComponent's). `_text` guards non-string fields so a stray int cannot stop timeline.json, including `_title`, which would have raised on an int date.
- show.html rewritten to show-page.html, on the existing classes: `.top .brand`, `.tag` wrapping the back link, `.bigt .bstub .bmain`, `.presents`, `.cols .jcard .liner .meta .fineprint`, `.kick`. No `$` beyond placeholders, no inline script.
- show.js: reads data-slug, fetches `notesHref`, writes "Sat 12:26a to 1:53a" (the end's day named when it differs) with airTime, and zoneLabel; "Not currently scheduled." and "Airtimes unavailable." carried from the old script. textContent/replaceChildren only.
- radio.css: `.meta b { font-weight: 400; color: var(--oxblood); }`.
- Beyond the brief: serve.mjs gains a `shows` option; smoke.pw.mjs allows /show/ and gains 4 scenarios (zone and day-crossing, none, unreadable, bad time plus hostile slug), because show.js had no other test.

## TDD
RED: ./.venv/bin/pytest packages/transmitter/tests_transmitter/test_site.py -q -> 41 failed, 38 passed.
GREEN: same command -> 79 passed.
Added to the brief's tests: no-notes copy, description bullet/fallback/200 cut, new-tab attributes, setlist rule table, set grouping, no-setlist, blank lineage, null fields, slug encoding, non-string fields, absolute og:image, template look, more concert_stub inputs. The hostile test also checks svg, iframe, script, b, i, u.

## Results
- ./.venv/bin/pytest packages/transmitter/tests_transmitter -q: 947 passed, 1 skipped.
- packages/transmitter/scripts/test-in-debian12.sh: 948 passed in 38.75s.
- cd antenna && npm test: 26 files, 516 passed. npm run typecheck: clean. npm run smoke: 40 passed (36 + 4 new).
- ANTENNA_BUCKET=x node scripts/deploy-assets.mjs --dry-run lists assets/show.js and radio.css.
- player.js, nowplaying.js, style.css and antenna/src/ unchanged from aed6e294.
- Real render screenshots at 1200, 390 and hostile at 320: scrollWidth equals viewport, console clean. /Users/shawn/projects/llama/.claude/worktrees/player/.superpowers/player-smoke/t9-shots/
- After those runs only a docstring in concert_stub changed; test_site.py re-run, 79 passed. The Debian run may have copied the tree before or after it.

## Files
antenna/e2e/serve.mjs, antenna/e2e/smoke.pw.mjs, antenna/public/assets/radio.css, antenna/public/assets/show.js (new), antenna/templates/show.html, packages/transmitter/src/transmitter/site.py, packages/transmitter/tests_transmitter/test_site.py

## Self-review and concerns
1. `$artist` added: the ticket needs the artist alone and `$title` carries the date. Falls back to the slug, as `_title` does.
2. Brief's test requires no literal `<b>` in the page, while `.bstub b` and `.meta b` style that element, so the template uses `<b class="year">` and `<b class="label">`. Neither class has CSS.
3. `$lineage` holds the whole labelled block, or nothing, so a blank lineage leaves the label out. The name is unchanged but it is now HTML, not text.
4. Set labels ("Set 1", "Encore") are my wording: digits get "Set ", others a capital. Task 10's panel gets `set` raw from groupSets and should match. Numbering restarts per set.
5. `.kick` inside `.jcard` keeps its 15px top margin, so the first label sits a little low. Left alone: the CSS scope was one line.
6. The smoke scenarios use the template with placeholders blanked, not site.py output; the real render was checked by screenshot only.
7. The ↗ follows the mockup; the exact copy is a substring of the button text.
8. Air times omit the mockup's month and day: airTime returns weekday and time only.
9. No mutation run was done.
