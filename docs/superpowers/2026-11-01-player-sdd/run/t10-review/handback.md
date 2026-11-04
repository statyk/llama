### Spec Compliance

- ✅ Spec compliant. Every item in the brief is in the diff:
  - Loading state first, then fetch through a generation counter (panel.js:133-143, 146-158).
  - pushState, or replaceState while open (panel.js:146-155).
  - popstate closes, Close and Escape go through `history.back()`, and a pending close is ignored (panel.js:161-180).
  - Nothing opens on load: popstate returns when not open (panel.js:174).
  - "old" or a failed fetch gives the target=_blank link (panel.js:131-141). Ready content is at panel.js:64-129.
  - Archive button only when `model.archive` is set (panel.js:73). Share control copies the absolute URL (panel.js:46).
  - No station link. Focus goes in and back. The app.js wiring is at app.js:13.
  - All six brief scenarios are in smoke.pw.mjs, 15 new tests in total (count matches the report).
  - No diff touches public/player.js, nowplaying.js, style.css or antenna/src/.
  - panel.js line numbers are the file's own at 85792e10.
- ⚠️ Not verifiable by me: the suite results (rubric: not re-run), and real iPhone/home-screen behaviour of `history.back()` and focus return. That belongs to the operator's preview.

**Rulings on the implementer's questions**

- page.js `export el`: accept. It is one word and avoids a second copy. Named risk: an import loop, since plan line 72 lists no panel -> page edge. Checked: page.js imports only timeline.js (page.js:4-7), and `ticketLinks` takes a callback, so there is no loop. The plan's import line is out of date, nothing worse.
- show.js to timeline.js `airLine`: accept. The move is verbatim (diff lines 668-672 vs 699-704), and show.js cannot be imported because it runs on load. timeline.js is the right home, as it holds `airTime` and `zoneLabel`.
- radio.css two lines: accept. Close needs a row and the plan gave it none. Sticky was unexercised by the implementer; I exercised it (Check below).
- Copy "Copy link to this show", "Link copied.", "Close", "Loading…": accept. None conflicts with the exact-copy list. The spec says only "close control" and "a way to share". "Loading…" matches show.html's own text, as does "No setlist." "Airtimes unavailable." and "Not currently scheduled." match show.js.
- Stub date "Nov 1 / 1985" vs show page "SAT NOV 1 / 1985": not a spec breach. The spec requires "the concert date on its stub", and the plan says panelModel has "already formatted" `date`. One show gets two wordings, so it is a Minor (below) for the operator's preview, not a fix now.
- Non-modal panel: correct. Spec line 247: "the page's hubs and controls keep working". A focus trap or `aria-modal` would make the page's controls unreachable by keyboard. `role="dialog"` without `aria-modal` is the honest markup. Note the panel covers the keys on phone and on 1200 px alike (panel-1200.png), which the spec allows ("slides up over the player"). Operator judges it at preview.
- Forward onto a stale entry: correct. Spec line 251 and the brief say nothing opens. Worst case is one extra back on the same URL.

### Strengths

- `closing` cannot stick: it is set only while open, and the same-document popstate that follows always clears it.
- The generation is bumped on close as well as open, so a late answer cannot fill a closed panel. Tested at smoke.pw.mjs "notes arriving after the close".
- `load` builds nodes inside the try, so malformed `sections` (a non-object block, a non-array `ul`) falls back to the show-page link rather than a stuck "Loading…".
- The hostile test compares element count against a benign render of the same shape, which is much stronger than a substring check. It also pins `.kick`, set labels and a non-archive URL.
- The history test puts a real page behind the player, so a back past the player is visible.
- Blank date cannot print "null": `concertDate` returns "" and panelModel's `text` covers the rest. Pinned by notes-empty.
- The report says mutants were predicted first and run in a scratch copy (reported, not re-run by me).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. panel.js:67. The stub drops the weekday and re-parses a formatted string with a regex. It reads "Nov 1", the show page "SAT NOV 1", so one show has two stubs. The plan-given `date` is the cause. If the operator wants them equal, add a pure `concertStub` next to `concertDate` from the string, without `Date`, and drop the regex. Wait for the preview.
2. radio.css:320 (`.panel-bar`). The bar is transparent and sticks at the panel's padding edge, so scrolled text passes beside and behind Close and shows in a clipped 14 px strip above it. Measured below. Close stays opaque, readable and on screen, so this is cosmetic. Fix if the operator notices: give the bar `background: var(--paper)` and pull it to the panel's top edge.
3. timeline.js:115 `airLine` is now an exported function in a unit-tested pure module, but has no unit test (`grep airLine antenna/test/*.ts` finds nothing). Its day-differs branch deserves two lines in timeline.test.ts.
4. panel.js:178. If the page rebuilt the ticket while the panel was open, `returnTo` is detached and focus falls to body. This is rare (show boundary or the list toggle) and affects keyboard users only. A re-lookup by `a.ticket[data-slug]` would fix it; not worth doing now. The implementer disclosed it.

### Checks run

- Named risk: the sticky bar was never exercised. Ran a throwaway script from the scratchpad: Chrome channel, notes with 8 long sections, panel.scrollTop = 500, at 390, 1200 and 320 px. The bar stayed in view at panel top + 14-16 px, background transparent. Screenshot looked at: /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-player/189f1567-d332-428c-81ac-df162d1a7df0/scratchpad/t10/sticky-390.png. Output is in t10-review.log.
- Named risk: the clipboard-refused URL overflowing the 222 px ticket body. Same script, refusing clipboard: panel scrollWidth equals clientWidth at all three widths, note width 146 px at 320 (a URL wraps). A longer slug is Task 11's 320 px scope, and `overflow-wrap: anywhere` on body (radio.css:52) inherits to `.share-note`.
- Named risk: an import loop from the new panel -> page edge. page.js imports only timeline.js (page.js:4-7), so no loop.
- Named risk: `stub.append(null)` printing "null". Read notes.js:31-45 and timeline.js:92-101: `date` is always a string.
- Named risk: panel.js escaping the ban on innerHTML. antenna/test/asset-bans.test.ts:3 globs `../public/assets/*.js`, so it covers panel.js.
- Read screenshots panel-390.png and panel-1200.png: layout follows show.html's order; the gap above "SET 1" is `.kick`'s margin.
- The probe served the worktree's files read-only from a scratchpad script. I changed nothing in the worktree outside t10-review/, and did not re-run the suite.

### Assessment

**Task quality:** Approved

**Reasoning:** The panel matches the brief and the spec on history, generation, focus, textContent and fallback, and the tests cover the races (the mutant results are the implementer's report). The three out-of-list changes and the chosen copy are justified, and what remains is four Minors, the stub wording and the sticky bar being the operator's preview to judge.
