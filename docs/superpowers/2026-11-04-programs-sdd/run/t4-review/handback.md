### Spec Compliance

- ✅ Spec compliant. Every file the brief lists has its hunk: index.html, page.js, panel.js, radio.css, pages.ts (regenerated), timeline.mjs, serve.mjs (`index` option), lineup.mjs (new), old-index.html (new), smoke.pw.mjs, indexpage.test.ts, CLAUDE.md. All 15 brief smoke scenarios are present (smoke.pw.mjs, the "Programs, block headings and the weekly lineup" block) and so is the vitest test, verbatim (indexpage.test.ts:+546).
- Exact copy: `The weekly lineup` (index.html:+507), `LMA RADIO PRESENTS` fallback (panel.js:+328, `presentsLine`), span `7:00a – 9:56a` and start-only `2:10p`, both asserted in the smoke tests. Tab labels `Today`/`Thu` asserted.
- Frozen files: none of player.js, nowplaying.js, style.css is in the diff stat. `antenna/src/` changes only pages.ts, and that matches index.html.
- Check run: `cmp <(git show main:antenna/public/index.html) antenna/e2e/fixtures/old-index.html` gives identical. The fixture really is main's page.
- Text goes in only through `el(...)`/textContent: page.js:+97, +213 (block and lineup titles are `String()`-coerced, null becomes ""). The hostile smoke test asserts the same element count as a benign run, and no `pwned`.
- Mixed versions: `renderComingUp` falls back to flat tickets on `.tickets` (page.js:+87). `renderLineup` and `refreshLineup` no-op without `#lineup` (page.js:+176, +280; the old-index test asserts 0 lineup requests). The panel uses `??` (panel.js:+328).
- Implementer concern 1 (null on-air key off air, page.js:+177): **accepted.** The spec's Decision is "the block on air now is highlighted". Off air nothing is on air, and the page's other surfaces (label status, now line) already say so. The brief's literal wording didn't consider the off-air state. A side effect: while off air, the before-midnight carry-over entry also drops out of Today, because lineupDays only prepends it given a key. That is consistent with nothing being on air. It is pinned by "off the air nothing in the lineup is marked on air".
- Concern 2 (ticket program ellipsized, not wrapped): **accepted as a builder styling call**, flagged for Shawn below. `.ticket` has a fixed height on every viewport (radio.css:309 `height: 92px`, :563 `84px`), so wrapping would collide with the `.sr` date row. It matches the existing `.artist` treatment. Review Focus 1's binding part (literal text, no sideways scroll at 320 px) holds: the 320 px test asserts scrollWidth on both the page and the panel.
- Concern 3 (empty day shows an empty list, no copy): accepted. The exact-copy constraint gives no string for it, and adding copy would be an Extra.
- Concern 4 (an on-air block whose nominal start falls on tomorrow's date isn't highlighted): accepted. It follows "Today only" plus the helper's carry-over rule, which only pulls back an *earlier* day's entry (programs.js:105). This is a rare edge.
- Concern 5: no issue.
- ⚠️ Cannot verify from the diff: that the transmitter's `_lineup.json` shape (`occurrences[].block/nominal_start/title/variety`) matches what lineup.mjs fakes. That is Task 2's object. The controller should cross-check the fixture against `site.build_lineup` in the whole-branch review.

### Strengths

- The old/new page detection keys on the one structural difference the brief named (`.tickets` on `#coming-up`), and the old-index test serves main's real file and plays audio through it.
- Tabs are rebuilt only when the days change. Selection only flips `aria-selected`/`tabIndex` (page.js:+198-203), so focus survives a click and arrow-key navigation, and the roving tabindex is tested.
- `refreshLineup` reads the body before checking `ok` (page.js:+286). That is a real, measured fix for Chrome holding a 404 open against `networkidle`, and mutant M6 pins it.
- The tests discriminate well: same block name with another day's nominal start (no highlight), a group cut by SHOWN continuing under its heading, block-head transform and colour compared to the live `.kick`, Europe/London zone shift, and day-change reset. The implementer's six mutants each had a predicted red test.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. **For Shawn's eye (visible design call):** a long program name is cut to one line with an ellipsis on tickets (radio.css:+378). At 320 px roughly 30 characters fit, so the 60-character test title shows about half. Real titles ("One More from the Archive", 25 characters) fit. The full title is in the panel and on show.html. The alternative, a taller ticket, changes the existing look. Surface it in the run report rather than fixing it.
2. page.js:+187-196 / index.html:+508-509: the tab pattern is incomplete. `#lineup-list` has no `role="tabpanel"` (with `aria-labelledby` the selected tab), and the tablist has no accessible name (e.g. `aria-labelledby` pointing at the section's h2). The tabs' `aria-controls` points at an element with no panel role. Fix: add `role="tabpanel"` to the `<ol>`, plus an id on the h2 and `aria-labelledby` on the tablist. Note that index.html deploys separately, so the attributes could equally be set from page.js.
3. page.js:+178: `lineupDays` runs on every once-a-second `renderAt`. Each call constructs a fresh `Intl.DateTimeFormat` per day probe and per occurrence (`localDateKey`, programs.js:31; about 60 or more constructions plus `airTime` per tick). On a phone this is wasted work every second, for output that changes only per minute or per fetch. Fix: memoize `days` on `(lineup, timeline on-air key, floor(atMs/60_000))` in page.js, or cache the formatter in programs.js. The latter would be a Task 3 change and needs a new-module-rule check.
4. radio.css:+403-416: `.block-head` restates `.kick`'s font-size, letter-spacing, transform and colour by value rather than sharing a selector (`.kick, .block-head { … }`). If `.kick` changes, the two drift apart. The smoke test compares only transform and colour.
5. page.js:+281 / +259: the lineup refetch is driven from inside `refreshTimeline`'s 3-minute gate, so the effective cadence is 30-33 minutes, and a `force` refresh never forces the lineup. That is acceptable against the brief ("once the last attempt is 30 minutes old"). The CLAUDE.md wording "refetched every 30 minutes with the timeline" is accurate enough.

### Assessment

**Task quality:** Approved

**Reasoning:** Every brief requirement and scenario is implemented and tested with discriminating assertions. The four judgement calls are sound against the spec's Decisions. The text-only, frozen-file and mixed-version constraints hold, and the old-index fixture is byte-identical to main's page. What remains is accessibility polish, per-tick efficiency and one visible styling choice for Shawn to confirm.
