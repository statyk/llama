### Task 5: Pure Media Session and notes helpers

**Model hint:** sonnet.

**Files:**
- Create: `antenna/public/assets/media.js`, `antenna/public/assets/notes.js`
- Test: `antenna/test/media.test.ts`, `antenna/test/notes.test.ts`

**Interfaces:**
- Consumes: `timeline.js` `nowLine`, `tidyTitle`, `concertDate`, `whereLine`.
- Produces:
  - `media.js`: `sessionText({ np, stationName, audible }) -> { title, artist, album }`; `ARTWORK = [{ src: "/assets/cassette-512.png", sizes: "512x512", type: "image/png" }]`
  - `notes.js`: `panelModel(notes) -> { kind: "ready" | "old", ...}`; `archiveLink(url) -> string | null`, the same rule as `site.archive_link`; `setlistLine({ title, segue }) -> string`; `groupSets(setlist) -> [{ set, lines }]`

- [ ] **Step 1: Write failing tests.**

```ts
// media
expect(sessionText({ np: { show: { artist: "Band", venue: "Club", date: "2008-11-01" }, file: { kind: "track", title: "Song>" } },
                     stationName: "LMA Radio", audible: true }))
  .toEqual({ title: "Song >", artist: "Band", album: "Club, Nov 1 2008" });
expect(sessionText({ np: null, stationName: "LMA Radio", audible: true }))
  .toEqual({ title: "LMA Radio", artist: "", album: "" });
// any state with no audio: station name, no stale song
expect(sessionText({ np: { show: { artist: "Band" }, file: { kind: "track", title: "Song" } },
                     stationName: "LMA Radio", audible: false }).title).toBe("LMA Radio");

// notes
expect(panelModel({ slug: "s" }).kind).toBe("old");
expect(panelModel(null).kind).toBe("old");
expect(panelModel({ sections: "x" }).kind).toBe("old");
expect(panelModel({ sections: [] }).kind).toBe("ready");
expect(panelModel({ sections: [], url: "javascript:alert(1)" }).archive).toBe(null);
expect(panelModel({ sections: [], url: "http://archive.org/details/x" }).archive).toBe(null);
expect(archiveLink("https://archive.org/details/x")).toBe("https://archive.org/details/x");
for (const bad of ["http://archive.org/details/x", "https://archive.org.evil.test/x", "javascript:alert(1)", "", null, 42]) {
  expect(archiveLink(bad)).toBe(null);
}
expect(setlistLine({ title: "Song", segue: true })).toBe("Song >");
expect(setlistLine({ title: "Song>", segue: true })).toBe("Song >");
expect(setlistLine({ title: "Song ->", segue: false })).toBe("Song >");
expect(setlistLine({ title: null, segue: false })).toBe("?");
expect(groupSets([{ set: "1", title: "A" }, { set: "1", title: "B" }, { set: "encore", title: "C" }]).length).toBe(2);
```

- [ ] **Step 2: Run** `cd antenna && npx vitest run test/media.test.ts test/notes.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement.** `panelModel` returns `kind: "ready"` only when `sections` is an array, with `sections`, `archive: archiveLink(notes.url)`, `sets: groupSets(notes.setlist || [])`, and the show's text fields.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit.** `antenna: pure Media Session text and notes helpers`.

---

