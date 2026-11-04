### Task 3: Pure timeline helpers

**Model hint:** sonnet.

**Files:**
- Create: `antenna/public/assets/timeline.js`
- Test: `antenna/test/timeline.test.ts`

**Interfaces:**
- Produces (all exported from `timeline.js`, consumed by Tasks 5, 7, 8, 9, 10):
  - `STATION_NAME = "LMA Radio"`
  - `positionMs({ playing, playbackMs, nowMs }) -> number`
  - `findShow(timeline, atMs) -> { show, file } | null`, the same contract as `nowplaying.findNowPlaying`
  - `nowLine(np, stationName) -> string`
  - `stoppedLine(np, stationName) -> string`
  - `tapeLog(timeline, atMs, limit = 8) -> [{ title, start }]`, `start` the file's ISO string, usable by `airTime`
  - `comingUp(timeline, atMs) -> show[]`, soonest first
  - `justAired(timeline, atMs, limit = 6) -> show[]`, newest first
  - `tidyTitle(s) -> string`, `clipLabel(s) -> string`
  - `concertDate(s) -> string`
  - `airTime(iso, timeZone?) -> { day, time }`
  - `zoneLabel(timeZone?) -> string`
  - `whereLine(show) -> string`
  - `showHref(slug) -> string`, `notesHref(slug) -> string`

- [ ] **Step 1: Write the failing tests.** Use a canned timeline with a clip, tracks and a neighbouring show, built like `antenna/test/nowplaying.test.ts`. They include:

```ts
expect(positionMs({ playing: true, playbackMs: 5, nowMs: 9 })).toBe(5);
expect(positionMs({ playing: true, playbackMs: null, nowMs: 9 })).toBe(9);
expect(positionMs({ playing: false, playbackMs: 5, nowMs: 9 })).toBe(9);

expect(tidyTitle("Magic Foot>")).toBe("Magic Foot >");
expect(tidyTitle("Space ->")).toBe("Space >");
expect(tidyTitle("Song")).toBe("Song");
expect(clipLabel("DJ intro (set 1)")).toBe("DJ intro");
expect(clipLabel("DJ outro")).toBe("DJ outro");

expect(concertDate("2008-11-01")).toBe("Nov 1 2008");
expect(concertDate("1977-05-00")).toBe("1977-05-00");
expect(concertDate("1977")).toBe("1977");
expect(concertDate(null)).toBe("");

expect(airTime("2026-11-01T05:53:00Z", "America/New_York")).toEqual({ day: "Sun", time: "1:53a" }); // EDT
expect(airTime("2026-11-01T06:53:00Z", "America/New_York")).toEqual({ day: "Sun", time: "1:53a" }); // EST, same label
expect(airTime("2026-11-01T07:30:00Z", "America/Los_Angeles")).toEqual({ day: "Sun", time: "12:30a" });
expect(airTime("2026-11-01T06:30:00Z", "America/Los_Angeles")).toEqual({ day: "Sat", time: "11:30p" });
expect(zoneLabel("America/New_York")).toBe("Times shown in Eastern Time");
expect(zoneLabel("Europe/Helsinki")).toMatch(/^Times shown in /);

expect(nowLine(null, "LMA Radio")).toBe("LMA Radio");
// a clip gives clipLabel; a track gives tidyTitle; a show with no file gives its artist
expect(nowLine({ show: { artist: "Band" }, file: null }, "LMA Radio")).toBe("Band");
expect(nowLine({ show: { artist: null }, file: null }, "LMA Radio")).toBe("LMA Radio");

expect(stoppedLine({ show: { artist: "Band" }, file: null }, "LMA Radio")).toBe("Band is on the air. Press Play.");
expect(stoppedLine(null, "LMA Radio")).toBe("LMA Radio");
expect(stoppedLine({ show: { artist: null }, file: null }, "LMA Radio")).toBe("LMA Radio");

expect(whereLine({ venue: "Club", city: null })).toBe("Club");
expect(whereLine({ venue: null, city: null })).toBe("");
expect(showHref("a b/c")).toBe("/show/a%20b%2Fc.html");
expect(notesHref("a b/c")).toBe("/notes/a%20b%2Fc.json");
```

  Named tests also cover:
  - `tapeLog` leaves out clips, runs newest first, excludes tracks after `atMs`, and continues into the previous show when the current one has fewer than `limit` tracks;
  - `tapeLog` entries carry `start` as the ISO string, and `airTime(entry.start, ...)` formats it;
  - `tapeLog` and `comingUp` ignore `recent` (fixture with a wrong `recent`);
  - `airTime` and `zoneLabel` don't depend on the runtime's default locale (a spy on `Intl.DateTimeFormat` sees `en-US` on every call);
  - `comingUp` at a time past the last show returns `[]`, and with `timeline: null` returns `[]` (Review Focus 1);
  - a show with `files: []` and null fields passes through every helper without throwing or producing "null" (Review Focus 4);
  - no helper reads `show.page` or `show.notes` (fixture sets them to `"javascript:x"`, output never contains it).

- [ ] **Step 2: Run** `cd antenna && npx vitest run test/timeline.test.ts`. Expected: FAIL, module not found.

- [ ] **Step 3: Implement** using `Intl.DateTimeFormat` with a fixed `en-US` locale, `hour12: true` and `formatToParts`, for both `airTime` and `zoneLabel`. `time` is lower-case, no space, single-letter suffix (`1:53a`). `zoneLabel` uses `timeZoneName: "longGeneric"`, with the time zone's `resolvedOptions().timeZone` as the fallback. `concertDate` matches `^\d{4}-(\d{2})-(\d{2})$` with month 01-12 and day 01-31, else returns the string as stored. Month names come from a literal array, never `Date`.

- [ ] **Step 4: Run** the same command. Expected: PASS. If `longGeneric` isn't available in the Workers test runtime, inject the formatter rather than loosening the assertion.

- [ ] **Step 5: Commit.** `antenna: pure timeline helpers for the new player`.

---

