### Spec Compliance

- ❌ Issues found: one requirement partly met. Everything else in the brief is implemented as written.
  - **Partial (Step 4, "after every test"):** the allowlist guard only sees requests that reach the fixture server. See Important 1. `antenna/e2e/smoke.pw.mjs:23-25`.
- Requirements met, checked against the diff:
  - State table, copy and `#retry`: `page.js` `FIXED_NOW`, `renderAt`, `setState`. All strings match the global constraints exactly, including the "…" character.
  - `#label-status` is hidden in `offair` only (`renderAt`). Pinned: mutant M2 is red on "ON THE AIR is hidden in the offair state only".
  - Tape log goes through `tidyTitle` (`page.js:89`).
  - An empty list hides its heading. `setHeadingHidden` resolves correctly for all three lists against `index.html`: `.tape-log` for the log, and each `section.schedule` for the ticket lists.
  - Ticket markup equals the t6 handback's "Markup Task 7 must use", including `.sr` for the concert date. The tape log row is `<li><span/><time/></li>`.
  - `ticketLinks` is one delegated listener and leaves all modified and non-primary clicks to the browser.
  - The fetch gate applies to `force` too (`page.js:158-160`). `lastAttempt` is set at attempt start, so a failure waits 3 minutes.
  - Coming up 6 + Show all; just aired 6. `comingUp` is uncapped, so everything published is reachable.
  - Note text, `#zone`, and `#stream-url` as an absolute URL are done. `#stream-url` is a `<code>`, so no href is needed.
  - `hostile.json` has markup in every listed field, and its section/block/setlist shape matches `site.py:109-186`.
  - Asset ban test: single-level glob, asserts `timeline.js` was found.
- Global constraints:
  - `page.js` never reads `page` or `notes`. Every link comes from `showHref`.
  - No file under `src/` is touched, and neither are the frozen files.
  - URLs are root-absolute.
- Removed assertion (`#label-artist` "LMA Radio" in the old element test): legitimate. Once the timeline renders, that test's fixture legitimately shows "On Air Band", and the empty-timeline test now pins the station-name label. No coverage lost.
- Extras (`e2e` beyond the brief's six scenarios, `export STATES`): the tests are in scope. The `STATES` export has no consumer outside the module (harmless; see Minor 6).
- ⚠️ Cannot verify from diff: no real iPhone/Safari render of these lists. That belongs to later tasks.

### Strengths

- `rebuild`'s content keys and the delegated `ticketLinks` are simple and correct. Rebuilt lists keep working with no re-binding.
- `refreshTimeline` matches the brief exactly: the `inFlight` guard, attempt-start stamping, and the shape check that keeps the last good timeline.
- `renderAt` is the single writer of `#now` and the label. `setState` only adds `#retry`.
- The hostile tests compare element counts against a benign render rather than only grepping, and they drive a hostile slug through a real ticket.
- The afterEach regex correctly refuses query strings, including on `/`.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. `antenna/e2e/smoke.pw.mjs:23-25`: the "after every test" allowlist reads `site.requests`, which is the fixture server's own log.
   - **What's wrong:** a request to any other host never reaches that server, so the guard cannot see the one thing the global constraint "No third-party request" forbids. The only off-origin check is the dedicated test at :190, which loads the page and presses nothing.
   - **Why it matters:** the brief makes this guard apply to "every test, including those of later tasks". Play (hls), the notes panel and show pages will all run under a guard blind to third-party requests. Confirmed by reading: `ALLOWED` is only ever applied to server-seen paths.
   - **Second gap:** tests that swap the server (:140, :157, :174, :184, :258) discard the first server's request list, so those requests are never checked. `site` is reassigned and only the last server is read at :23.
   - **Fix:**
     - In `beforeEach`, record `page.on("request", r => seen.push(r.url()))`.
     - In `afterEach`, fail any URL that is not `data:`/`blob:` and whose hostname isn't the local host, and test `pathname + search` of the rest against `ALLOWED`.
     - The `blob:` exemption will be needed for hls.js in Task 8.
     - This also replaces the request half of the server-log approach for swapped servers.

#### Minor (Nice to Have)

Each "unpinned" item below is correct code with no test holding it. Mutants were run in a scratch copy on the whole smoke suite; predictions were logged first and all held. Baseline: 14 passed.

1. `antenna/e2e/smoke.pw.mjs:162` and `antenna/e2e/fixtures/hostile.json:7`: the tape log's `tidyTitle` is unpinned.
   - Mutant M3 (`e.title` raw at `page.js:89`) survives: 14 passed.
   - The hostile title already ends in " >", so `tidy` equals the raw title, and the fixture's benign titles have no segue mark. The `const tidy` line looks like a pin but isn't.
   - Fix: end the hostile track title in `->` (or `-->`). That is a one-character fixture change, and `tidy` then bites.
2. `page.js:51`: "rebuilds lists only when their content changed" is unpinned.
   - Mutant M4 (key check deleted, so every list is replaced every second) survives.
   - Fix: hold a ticket's element handle across two ticks and assert it is still connected.
3. `page.js:158-160`: `refreshTimeline(true)` is unexercised.
   - Mutant M5 (force bypasses the stopped-and-hidden gate) survives.
   - Task 8's lock-screen handler relies on this, so pin it there or here by calling the exported function with `document.hidden` forced.
4. `page.js:162`: "a failed fetch waits out the same 3 minutes" is unpinned.
   - Mutant M6 (`lastAttempt` set only on success, so a failing page refetches every second) survives.
   - This is the one that would matter on the spend side during an outage.
   - Fix: extend the visible-cadence test with `startServer({})` and assert one request across 2 mocked minutes.
5. `antenna/e2e/smoke.pw.mjs:8,18`: the console exemption is by status text alone, so any unexpected 404 or 403 passes, not only the "expected" ones. For later tasks, consider checking `m.location().url` against `/timeline.json`, `/live.m3u8`, `/notes/`.
6. Small items:
   - `antenna/e2e/smoke.pw.mjs:244`: the `trial: true` click does nothing; delete it.
   - The same test covers Shift only; Ctrl, Meta and Alt are unexercised.
   - `export const STATES` isn't in the interface; drop the `export`.
7. `page.js:165`: `fetch` has no timeout, and `inFlight` blocks every later attempt until it settles, so a stalled connection pauses refreshes for as long as the browser holds it. `signal: AbortSignal.timeout(...)` closes that. Low stakes: browsers do bound it.

Risks checked and cleared:
- Stale timeline from the HTTP cache: the spec declares `max-age=30` (spec:115), so a plain `fetch` is right.
- `hls.min.js` tripping the ban glob: it isn't in `public/assets/` (deploy and `serve.mjs` map it from `node_modules`).
- Shadowed `[hidden]` rules: `radio.css:43` is `display:none !important`.
- Hidden-gate and offair mutants M1, M2: both red on exactly the predicted test, answering implementer concern 1.

Test evidence: the handback reports vitest 515, smoke 14 (twice) and typecheck clean, with no noise. I did not re-run vitest.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** `page.js` and `app.js` implement the brief correctly, and I found no behavioural defect. The "after every test" request guard cannot see third-party requests, and later tasks depend on it for that exact constraint. Fix it before Task 8, and take Minor 1 and 4 with it since they are cheap.
