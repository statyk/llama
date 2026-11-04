### Finding Verdicts

- **Important 1: `panelModel` has no `airtimes`** — ADDRESSED. antenna/public/assets/notes.js:43 is exactly the required `airtimes: Array.isArray(notes.airtimes) ? notes.airtimes : []`, on the `kind: "ready"` return. The key matches what the publisher writes (packages/transmitter/src/transmitter/site.py:186). antenna/test/notes.test.ts ("panelModel air times") covers a list, a non-list string and an absent key.
- **Important 2: album includes the city** — ADDRESSED. antenna/public/assets/media.js:15 (diff line 34) is exactly `[show.venue, concertDate(show.date)].filter(Boolean).join(", ")`, matching docs/superpowers/specs/2026-11-01-player-design.md:158 "album: venue and concert date". The `whereLine` import is gone (media.js:2). antenna/test/media.test.ts "keeps the city out of the album" covers a city with venue and date, and a city alone. `concertDate(undefined)` returns "" (timeline.js:93), so the city-alone case gives "".

Fix report check: the Fix round 1 section of t5-impl/handback.md names the covering tests and shows output (15 passed in the focused run; 460 passed in `npm test`; tsc clean). Its claims agree with the diff. Tests were not re-run, per the rubric.

### New Breakage in the Fix Diff

None. `whereLine` stays imported in notes.js:3 and is still used at notes.js:40. The "leaves blank fields out" case still holds with the new album expression.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
