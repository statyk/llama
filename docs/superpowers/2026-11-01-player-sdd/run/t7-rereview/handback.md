### Finding Verdicts

- **1. Important: the after-every-test allowlist read the fixture server's own log, so other hosts were invisible and server swaps lost the list** — ADDRESSED. `antenna/e2e/smoke.pw.mjs:59` records `page.on("request")` into `seen`, reset per test at :56, so it is independent of `site`. :30-34 fails a URL on another hostname or one failing `ALLOWED`. Red checks, run in scratch copies with the prediction logged first (`t7-rereview.log`):
  - Mutant: third-host fetch of an ALLOWED path planted in `app.js`. Predicted and actual red: "the page's elements are all there", at `expect(stray)` :34.
  - Mutant: `fetch("/timeline.json?v=1")` in `page.js`. Predicted and actual red: same test, same line.
  - Added test, stray `/stray-first?x=1` on the first server, then a server swap: red under the new guard (`stray` names the URL), green under the 28f39ada guard. This is the control for the swap half.
  - Added test, third-host fetch: `stray` names it under the new guard; empty under the old guard. The old guard went red only through the DNS failure's console error, so a resolving host would have passed.
  - Also caught by `stray`: third-host `img`, `sendBeacon`, iframe, blob-worker fetch, an off-allowlist local path. Iframe and worker fetch were fully green under the old guard.
  - Two gaps remain; see Minors below. Neither is the finding's stated defect.
- **2. Tape log tidyTitle unpinned** — ADDRESSED. `antenna/e2e/fixtures/hostile.json:7` ends in `->`; `smoke.pw.mjs:171-172` expects ` >`. Mutant `e.title` raw at `page.js:89`: red at :172, as predicted. No other test reads the title's ending.
- **3. "A failed fetch waits out the same 3 minutes" unpinned** — ADDRESSED. New test at `smoke.pw.mjs:225-236`; `startServer({})` really answers 404 (`serve.mjs`, `json(undefined)`).
  - Mutant `lastAttempt` set only on success: red at :233, as predicted, with "visible:" green.
  - Mutant failure wait of 2 min: red 5 of 5 at :233, so the race I doubted at that immediate read did not appear.
  - Mutant failure wait of 2.5 min: green 2 of 2. The test brackets the wait between 2:00 and 3:01, the same shape as the "visible:" test. Accepted; see Minors.

### New Breakage in the Fix Diff

- **Minor, `smoke.pw.mjs:59`:** `page.on("request")` does not see a popup or new tab, and the old server log did. Planted `window.open("/planted-pop?x=1")`: red under the 28f39ada guard, green under the new one. A third-host `window.open` is green under both. `ticketLinks` deliberately leaves modified clicks to the browser, so new tabs are a real path. Fix: take `context` in `beforeEach` and use `context.on("request")`.
- **Minor, `smoke.pw.mjs:32`:** `url.search` is empty for a bare trailing `?`, so `fetch("/timeline.json?")` is green under the new guard and red under the old. Small regression against "no query string". Fix: also fail when `u` contains `?` with an empty `search`.
- **Minor, pre-existing rather than a regression:** a WebSocket never reaches `stray`, under either guard. Only the console error of a failed connection reddens it, so a third-party socket that connects would pass. `page.on("websocket")` would close it. The brief names only `page.on("request")`.
- **Minor, test bound:** the 2.5 min mutant survives (finding 3). A tighter upper-side check would need a read just before 3:00. Not worth a round by itself.
- Fix report: names the tests and gives counts (515, 15), not raw output. I did not re-run the suites, per the rubric. Its two mutants reproduced as claimed.

### Out-of-Scope Observations

- `smoke.pw.mjs:199-204` "no request leaves the local host" is now a strict subset of the guard. It is a brief-listed scenario, so keep it.
- Scratch copies were left at `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-player/189f1567-d332-428c-81ac-df162d1a7df0/scratchpad/t7rr`. The live worktree was not modified; `git status` was clean after the runs.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. Open: none. Three Minors for the ledger, of which the popup gap and the bare `?` are small regressions, each with a one-line fix.
