### Task 10: Notes panel

**Model hint:** opus.

**Files:**
- Create: `antenna/public/assets/panel.js`, `antenna/e2e/fixtures/notes-*.json`
- Modify: `antenna/public/assets/app.js`
- Test: `antenna/e2e/smoke.pw.mjs`

**Interfaces:**
- Consumes: Task 2's `sections`; Task 3's `notesHref`, `showHref`, `airTime`, `zoneLabel`; Task 5's `panelModel` (which has already formatted `where` and `date`, and carries `airtimes`), `setlistLine`, `groupSets`; Task 7's `ticketLinks` and `hostile.json`.
- Produces: `export function openPanel(slug)`.

- [ ] **Step 1: `panel.js`.** `openPanel(slug)`:
  - Shows the panel at once with a loading state, then fetches `notesHref(slug)` through a generation counter, so a second tap's panel never shows the first's notes (Review Focus 5).
  - `history.pushState({ panel: slug }, "")` on the same URL; if the panel is already open, `replaceState` instead of a second `pushState`. `popstate` closes; the close control calls `history.back()`, and a close while one is pending is ignored. Nothing opens the panel on load.
  - Renders `panelModel`: `"old"` or a failed fetch shows a `target="_blank"` link "Open the show page" to `showHref(slug)`. `"ready"` shows the ticket, setlist, liner notes ("No notes yet." when empty), air times, lineage, the disclaimer, the archive button only when `archive` is set (`target="_blank" rel="noopener"`), and a share control copying the absolute `showHref(slug)`.
  - No link back to the station. `textContent` only. Focus moves into the panel and back on close; Escape closes.

- [ ] **Step 2: `app.js`.** Import `panel.js` and call `ticketLinks(document, openPanel)`.

- [ ] **Step 3: Add smoke scenarios.**

```
a tap on a ticket opens the panel, leaves the URL unchanged, and adds no navigation
the back action closes the panel; the close control closes it; a second back leaves nothing stale
two fast taps show only the second show's notes (first response delayed; the second tap is delivered by evaluate on the ticket link)
notes without sections show "Open the show page" with target=_blank
a ticket on empty sections reads "No notes yet."
the hostile fixture through the panel: its markup appears as literal text and adds no element
```

- [ ] **Step 4: Run** `cd antenna && npm test && npm run smoke`. Expected: all pass.

- [ ] **Step 5: Commit.** `antenna: the slide-up notes panel`.

---

