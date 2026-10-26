### Task 12: Player

**Files:**
- Modify: `antenna/public/nowplaying.js:51-57`, `antenna/public/player.js:161`
- Test: `antenna/test/nowplaying.test.ts`

**Interfaces:**
- `nowPlayingText(np, timelineLoaded, stationName = "llama radio")`: no show → `stationName` when loaded (was "We'll be back shortly."), "Tuning in…" otherwise. `player.js` passes `document.title`. The off-air path (`hlsErrorNotice`, `classifyProbe`, offair page) is unchanged; verify by reading `player.js` that off-air sets its own text rather than calling `nowPlayingText`. (Interstitial rows are already kept out of the timeline by Task 1.)

- [ ] **Step 1: Failing tests**

```ts
expect(nowPlayingText(null, true, "llama radio")).toBe("llama radio");
expect(nowPlayingText(null, false, "llama radio")).toBe("Tuning in…");
```

- [ ] **Step 2: Run to verify failure** — `cd antenna && npm ci && npm test` (`npm ci` first: a fresh worktree has no `node_modules`). Expected: FAIL.
- [ ] **Step 3: Implement**; run `cd antenna && npm run pages` if `npm test`'s freshness check says `src/pages.ts` is stale.
- [ ] **Step 4: Run the antenna suite** — `cd antenna && npm test`. Expected: all PASS.
- [ ] **Step 5: Commit**

```bash
git add antenna/public antenna/src/pages.ts antenna/test/nowplaying.test.ts
git commit -m "antenna: the player shows the station name between shows"
```

---

