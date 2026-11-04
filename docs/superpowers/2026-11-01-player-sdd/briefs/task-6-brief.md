### Task 6: Look and smoke harness

**Model hint:** opus (visual judgement against the mockups).

**Files:**
- Create: `antenna/public/assets/radio.css`, `antenna/public/assets/fonts/*`, `antenna/public/assets/app.js` (a stub), `antenna/scripts/make-art.mjs`, `antenna/public/assets/cassette-512.png`, `cassette-og.png`, `icon-180.png`, `icon-192.png`, `antenna/playwright.config.mjs`, `antenna/e2e/serve.mjs`, `antenna/e2e/fixtures/timeline.mjs`, `antenna/e2e/smoke.pw.mjs`
- Modify: `antenna/public/index.html`, then `npm run pages`; `antenna/package.json`, `antenna/package-lock.json`
- Test: `antenna/test/indexpage.test.ts`

**Interfaces:**
- Produces, consumed by Tasks 7 to 11, the page's element ids: `#label-artist`, `#label-where`, `#label-date`, `#hubs` (the class `turning` makes them spin), `#play`, `#stop`, `#now`, `#retry`, `#tape-log`, `#coming-up`, `#just-aired`, `#zone`, `#schedule-note`, `#stream-url`, `#audio`. CSS classes `.ticket`, `.ticket.torn`, `.panel`, `.panel.open`.
- Produces the smoke harness: `npm run smoke`; `serve.mjs` exports `startServer({ timeline, notes }) -> { url, setLive(mode), requests, close() }`, with `mode` one of `live`, `404`, `403`, `endlist` and `requests` the paths served; `fixtures/timeline.mjs` exports `makeTimeline(nowMs, overrides?)`.

- [ ] **Step 1: Fonts.** Default choice: Caveat 700 for the label, Special Elite for typed text, Libre Baskerville 700 for ticket names, all openly licensed. Copy the Latin `woff2` files into `assets/fonts/`, with their licences as `*.txt`, from `@fontsource/*` packages installed temporarily (not left in `package.json`). `font-display: swap`. Check accented names (Béla) render.

- [ ] **Step 2: Static page.** Rewrite `index.html`, in the order of the spec's "The main page", with hard-coded sample content removed before commit: the header line, cassette (CSS or SVG), Play and Stop keys, Now playing, the sections, footer with the credit, "Non-commercial; no ads" and the stream URL. It loads only `assets/hls.min.js` (deferred) and `<script type="module" src="assets/app.js">`; `app.js` is a stub until Task 7. Asset references are relative; `og:image` is the absolute `https://listen.lma-radio.com/assets/cassette-og.png`. `og:title` is "LMA Radio", `og:description` the header line. Keep `<link rel="icon" href="data:,">`. In `indexpage.test.ts`, change `expect(PLAYER_PAGE).toContain("player.js")` to `"assets/app.js"`.

- [ ] **Step 3: `radio.css`.** Port the mockups' look. Phone is one column; at about 800 px and up, layout B. Hubs spin only under `.turning`, and never under `prefers-reduced-motion`. Ticket perforation, notches and texture stay. Long names wrap on the label and truncate on tickets with an ellipsis. Include safe-area padding (`env(safe-area-inset-*)`) and the panel's closed state.

- [ ] **Step 4: Smoke harness.**
  - Add `@playwright/test` as a dev dependency, script `"smoke": "playwright test"`. `testMatch: "e2e/*.pw.mjs"`, so Vitest doesn't collect it (it matches `*.test` and `*.spec` only). Use `channel: "chrome"`, because bundled Chromium normally can't play AAC. Run `tsc --noEmit` to confirm `e2e/` isn't picked up.
  - `serve.mjs` is a small Node static server over `public/` and the fixtures. It maps `/assets/hls.min.js` to `node_modules/hls.js/dist/hls.min.js`, and serves `timeline.json`, `notes/` and `/live.m3u8` per test.
  - A Playwright global setup generates a short AAC HLS fixture with ffmpeg at test start, as `e2e/fixtures/seg/*.aac` (`*.aac` is gitignored, so no audio is committed). In `live` mode `/live.m3u8` loops those segments as a sliding live playlist with `EXT-X-PROGRAM-DATE-TIME`, so a browser really plays. `timeline.json` is generated at test start, with times relative to now.
  - First test: the page loads, shows the header line and every asset request succeeds.

- [ ] **Step 5: Art.** `make-art.mjs` opens a page holding only the cassette in Playwright and writes the four PNGs: 512 square, 1200×630, 180 and 192 square. Commit the PNGs. Run it by hand; it isn't part of any build.

- [ ] **Step 6: Verify.** `npm run pages && npm test && npm run smoke` is green. `git diff --exit-code main -- antenna/public/player.js antenna/public/nowplaying.js antenna/public/style.css` is empty. Screenshot at 390 and 1200 px and compare with the mockups.

- [ ] **Step 7: Commit.** `antenna: the cassette page, tickets, fonts, art and the smoke harness`.

---

