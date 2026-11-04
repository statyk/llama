### Task 7: Page rendering and timeline fetching

**Model hint:** sonnet.

**Files:**
- Create: `antenna/public/assets/page.js`, `antenna/e2e/fixtures/hostile.json`
- Modify: `antenna/public/assets/app.js`, `antenna/e2e/serve.mjs` as needed
- Test: `antenna/test/asset-bans.test.ts`, `antenna/e2e/smoke.pw.mjs`

**Interfaces:**
- Consumes: Task 3's helpers, Task 6's ids and harness.
- Produces: `export function renderAt(atMs)`, `export function refreshTimeline(force)`, `export function currentTimeline()`, `export function setState(name)` and `export function ticketLinks(root, onOpen)`. Consumed by Tasks 8 and 10. `setState`'s names: `playing`, `stopped`, `reconnecting`, `gaveup`, `offair`, `refused`, `unsupported`.
- Produces: `hostile.json`, one document in the notes shape (with `sections` and `setlist`) with markup in every field: artist, venue, city, date, title, lineage, set labels, section headings, paragraphs, bullets, slug. Consumed by Tasks 9 and 10.

- [ ] **Step 1: Write the bans test.** `asset-bans.test.ts` fails if `innerHTML`, `outerHTML`, `insertAdjacentHTML` or `document.write` appears in `public/assets/*.js`. Read the sources with `import.meta.glob("../public/assets/*.js", { query: "?raw", eager: true })`: the Workers pool has no file system, and the single-level glob leaves out `preview/`. Assert that the glob found `timeline.js`, so an empty glob can't pass. Check it bites with a temporary `innerHTML` in `page.js`.

- [ ] **Step 2: Implement `page.js`** with `createElement` and `textContent` only.
  - `renderAt(atMs)` alone writes `#now` and the label, and also updates the tape log and both ticket lists. It rebuilds lists only when their content changed, so a tap isn't lost. `setState(name)` stores the name, shows `#retry` for `gaveup`, `offair` and `refused`, and re-renders. The default is `stopped`.

    | State | Label | `#now` |
    |---|---|---|
    | `playing` | show | `nowLine` |
    | `stopped` | show | `stoppedLine` |
    | `reconnecting` | show | "Reconnecting…" |
    | `gaveup` | show | "Lost the stream." |
    | `refused` | show | "Playback was blocked." |
    | `unsupported` | show | "This browser can't play the stream; open the stream URL in VLC." |
    | `offair` | station name | "The station is off the air." |

    With no show on air the label carries `STATION_NAME`. `#label-status` ("ON THE AIR") is hidden in `offair` and shown otherwise.
  - The tape log renders each entry through `tidyTitle`; `tapeLog` returns titles as stored.
  - A section whose list is empty hides its heading.
  - Fetch `/timeline.json` on load. `refreshTimeline(false)` fetches once the last attempt is 3 minutes old, while the state is `playing` or `reconnecting` or `!document.hidden`. `refreshTimeline(true)` skips the age check but not that condition, so stopped and hidden never fetches. A failed fetch keeps the last timeline and waits out the same 3 minutes.
  - Tickets are `<a class="ticket" data-slug={slug} href={showHref(slug)}>` with the mockup's stub: `airTime` day and time, "GEN ADM"; main: "LMA RADIO PRESENTS", artist, `whereLine`, `concertDate`. Past shows get `.torn`.
  - `ticketLinks(root, onOpen)` adds one delegated click listener on `root`, so rebuilt lists keep working. It leaves modified clicks (`metaKey`, `ctrlKey`, `shiftKey`, `altKey`, non-primary button) to the browser; a plain click prevents the default and calls `onOpen(slug)`.
  - `#schedule-note` says the schedule isn't available when there's no timeline, and that nothing further is scheduled yet when `comingUp` is empty (Review Focus 1).
  - `#zone` shows `zoneLabel()`.
  - "Coming up" shows 6 with a "Show all" button; "Just aired" shows 6.

- [ ] **Step 3: `app.js`.** It imports `page.js` and fills `#stream-url` with the absolute URL of `/live.m3u8`. It owns the page's one once-a-second loop: `renderAt(positionMs({ playing: false, playbackMs: null, nowMs }))` and `refreshTimeline(false)`, so the page renders fully while stopped.

- [ ] **Step 4: Add smoke scenarios.**

```
renders the label, tape log, coming up, just aired and zone line before Play
every ticket link is /show/<encoded slug>.html, even when the fixture's page field is hostile
the hostile fixture through the label, log and tickets: its markup appears as literal text and adds no element
with an empty timeline, the schedule note is shown and the page does not throw
no request leaves the local host (page.on("request"))
stopped and hidden (document.hidden forced by an init script): no timeline.json fetch over 10 mocked minutes (page.clock)
```

  After every test, including those of later tasks:
  - every request is on an allowlist of static paths with no query string: `/`, `/assets/*`, `/timeline.json`, `/live.m3u8`, `/notes/*`, `/seg/*`;
  - the page logged no console errors, except for the expected 404/403s.

- [ ] **Step 5: Run** `cd antenna && npm test && npm run smoke`. Expected: all pass. Fix the code, not the test, unless the test is wrong.

- [ ] **Step 6: Commit.** `antenna: render the schedule, tape log and label`.

---

