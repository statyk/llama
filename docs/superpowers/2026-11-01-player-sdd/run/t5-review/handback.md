### Spec Compliance

- ❌ Issues found:
  - Missing: `panelModel` drops `airtimes` (antenna/public/assets/notes.js:34-43). The spec's panel content includes air times read from the notes' `airtimes`, and Task 10 renders `panelModel` output.
  - Misunderstood: `sessionText`'s album is `whereLine + date` (antenna/public/assets/media.js:14), so it carries the city. The spec says "album: venue and concert date".
- ✅ Everything else checked:
  - Brief's test cases are all present (media.test.ts:7-19, notes.test.ts:5-40).
  - `archiveLink` matches `site.archive_link` (literal prefix; site.py:100-105).
  - The `notes` and `page` fields are not read; `url`, `artist`, `venue`, `city`, `date`, `lineage`, `setlist` and `sections` match `build_notes`' keys (site.py:173-187).
  - Segue rule (notes.js:15) adds a mark only to a title without one.
  - "old" vs empty-`sections` "ready" is right (notes.js:32).
  - No-audio and no-show states give the station name with blank artist and album (media.js:9).
- ⚠️ Cannot verify from diff: `cassette-512.png` doesn't exist yet (Task 6 creates it). Check at Task 6 that it is one square 512 px PNG.

### Strengths

- `sessionText` reuses `nowLine`, so "same text as Now playing" holds by construction, clip labels included.
- The no-audio path clears artist and album too, which is stricter than the brief's title-only test (media.test.ts:16-18).
- Blank handling goes further than the brief asks: `text()` for null, `filter(Boolean)` for album, whitespace title to "?", and a non-array `setlist` is tolerated.
- Tests pin the real rule with `toEqual` on whole objects, and the bad-URL table is complete.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. antenna/public/assets/notes.js:34-43: `panelModel` has no `airtimes`.
   - What's wrong: probe result, keys for `{sections:[], airtimes:["x"], ...}` are `kind, sections, archive, sets, artist, where, date, lineage`.
   - Why it matters: the plan's Task 10 says "Renders `panelModel`" and lists air times among the ready content, consuming `airTime` and `zoneLabel`. The brief's "the show's text fields" doesn't name it, but this binding constraint and the Task 10 note do. Task 10 would have to bypass the model or ship without air times.
   - Fix: add `airtimes: Array.isArray(notes.airtimes) ? notes.airtimes : []` and a test for both a list and a non-list. `site.airtimes` returns `list[dict]` (site.py:67).

2. antenna/public/assets/media.js:14: album includes the city.
   - What's wrong: probe result, `{venue:"Club", city:"Town", date:"2008-11-01"}` gives `"Club, Town, Nov 1 2008"`; with a city, no venue and no date it gives `"Town"`. The spec's text is venue and concert date.
   - Why it matters: the implementer disclosed the choice, and the brief's "Consumes" line lists `whereLine`, but that line is also satisfied by notes.js. No test has a city, so neither reading is pinned.
   - Fix: `[show.venue, concertDate(show.date)].filter(Boolean).join(", ")`, drop the `whereLine` import, and add a case with a city. If the operator prefers the city on the car screen, that is a spec change to rule on, not an implementer default.

#### Minor (Nice to Have)

3. notes.js:40-41: the model carries derived `where` and formatted `date` only, no raw `venue` or `city`, while the plan's Task 10 also lists `whereLine` and `concertDate` as consumed. `whereLine(model)` would silently give "" (`concertDate(model.date)` is harmless). Task 10's implementer should use `model.where` and `model.date` directly; tell them, or adjust that line of the plan.
4. notes.js:24-25: null-entry handling is inconsistent. The comparison uses `entry && entry.set` (null) and the group stores `undefined`, so `groupSets([null,null])` gives two groups (probe). `site.build_notes` filters non-dicts, so this is unreachable from today's publisher, but the guard doesn't do what it appears to.
5. notes.js:25: `set` passes through unnormalized: `{set:null}` gives `set: null`, a missing key gives no `set` at all (probe). "Blank fields are left out, never printed as null" then rests on Task 10. Tell its implementer, or normalize to "" here. No test covers it.
6. media.js:12 via timeline.js `nowLine`: a clip titled only with a parenthetical, such as `"(set 1)"`, gives title "" (probe). Pre-existing in Task 3's helper and likely rare, but the car would then show a blank title rather than the show or station name.
7. media.js:4 (plan-mandated): `ARTWORK`'s root-absolute `/assets/cassette-512.png` points at production, not at `assets/preview/<n>/assets/`, so preview rounds before the first deploy show no artwork. Worth knowing when reading a preview on the phone; production is fine.
8. test/media.test.ts:26: stray space before a comma (`null } , file`).

Named risks checked outside the diff (each one focused):
- Notes key names against `site.build_notes`: match.
- `ARCHIVE_PREFIX` value: identical.
- Task 10's needs in the plan: finding 1 and 3.
- Preview path handling in the plan: finding 7.
- Helper behaviour: one read-only Node probe of the committed modules, in the scratchpad. The suite was not re-run.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The helpers are clean, well tested and correct on links, segues and blank handling, but `panelModel` omits the air times Task 10 must render, and the album adds a city the spec doesn't list. Both are small fixes.
