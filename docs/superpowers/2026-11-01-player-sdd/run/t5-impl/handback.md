Status: DONE
Commit: see git log (antenna: pure Media Session text and notes helpers)
Tests: npm test 24 files / 458 tests passed; typecheck (tsc --noEmit) clean.
TDD: RED with modules absent: "Test Files 2 failed (2) ... Cannot find module '../public/assets/notes.js'". GREEN: "Test Files 2 passed (2) Tests 13 passed (13)".
Files: antenna/public/assets/media.js, notes.js; antenna/test/media.test.ts, notes.test.ts.
Decisions: album = whereLine(show) (venue, city) + concertDate, so a show with a city gives "Club, Town, Nov 1 2008"; brief's example has no city. No audio or no show: artist and album "". panelModel also carries artist, where, date, lineage (text, "" when null).
Concerns: none beyond the album/city choice.

## Fix round 1 (commit 1fa89c84)
- notes.js: panelModel now carries `airtimes` (array kept, anything else -> []); tests for list, string, absent.
- media.js: album is `[show.venue, concertDate(show.date)]`; whereLine import dropped; tests with a city (with venue+date, and city alone -> "").
- Tests: `npx vitest run test/media.test.ts test/notes.test.ts`: Test Files 2 passed (2), Tests 15 passed (15). `npm test && npm run typecheck`: Test Files 24 passed (24), Tests 460 passed (460), tsc clean.
