### Task 11: Off-air page, home screen, link previews

**Model hint:** sonnet.

**Files:**
- Modify: `antenna/public/offair.html`, `antenna/public/index.html`, then `npm run pages`
- Create: `antenna/public/assets/radio.webmanifest`
- Test: `antenna/test/indexpage.test.ts`, `antenna/e2e/smoke.pw.mjs`

**Interfaces:**
- Consumes: Task 1's `--preview`, which rewrites the manifest's `start_url` and `scope`; decision D5.

If D5 said the app doesn't match Safari, stop here until the operator has ruled.

- [ ] **Step 1: Write failing tests** in `indexpage.test.ts`:

```ts
it("the off-air page stands alone while /assets/ is blocked", () => {
  expect(OFFAIR_PAGE).not.toMatch(/<script|assets\/|style\.css/);
  expect(OFFAIR_PAGE).toContain('http-equiv="refresh" content="300"');
  expect(OFFAIR_PAGE).toContain('href="/"');
});
it("the player page previews the station, not a show", () => {
  expect(PLAYER_PAGE).toContain("https://listen.lma-radio.com/assets/cassette-og.png");
  expect(PLAYER_PAGE).toContain("Live concert tapes from the Live Music Archive, around the clock.");
  expect(PLAYER_PAGE).toContain('rel="manifest"');
  expect(PLAYER_PAGE).toContain("apple-touch-icon");
  expect(PLAYER_PAGE).toContain("viewport-fit=cover");
  expect(PLAYER_PAGE).not.toContain("serviceWorker");
});
```

  In `smoke.pw.mjs`, now that every surface exists:

```
at 320 px wide with the band ...And You Will Know Us By the Trail of Dead, document.scrollWidth <= 320 on main and panel
```

- [ ] **Step 2: Run** `cd antenna && npm run pages && npx vitest run test/indexpage.test.ts`. Expected: FAIL.

- [ ] **Step 3: Implement.** `offair.html`: the cream-paper look with inline CSS and system fonts, the notice, a link to `/`, the refresh tag. Manifest: name "LMA Radio", `display: standalone`, `start_url: "/"`, `scope: "/"`, palette colours, the 192 and 512 icons. `index.html`: `<link rel="manifest" href="assets/radio.webmanifest">`, `apple-touch-icon`, `apple-mobile-web-app-capable`, `apple-mobile-web-app-title`, `apple-mobile-web-app-status-bar-style`, `theme-color`, `viewport-fit=cover`. No service worker.

- [ ] **Step 4: Run** `npm run pages && npm test && npm run typecheck && npm run smoke`. Expected: all green.

- [ ] **Step 5: Commit.** `antenna: off-air page, home-screen app, fixed link preview`.

---

