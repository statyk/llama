### Finding Verdicts

- **320 px test put the long band on one coming-up ticket only; the cassette label never carried it** — ADDRESSED. antenna/e2e/smoke.pw.mjs:767 passes `onAir: { artist: LONG }` (consumed at e2e/fixtures/timeline.mjs:32,45). :768 maps every show to LONG. :774 waits on `#label-artist` toHaveText(LONG) before the first scrollWidth assertion at :775. page.js:130 sets that label from the on-air show's artist, so the wait is real. The fix report's mutant (`white-space: nowrap` on `.hand.h1`, red at :775) names the line the diff puts that assertion on; I did not re-run it.
- **Spec extra: `mobile-web-app-capable` removed from index.html and pages.ts regenerated** — ADDRESSED. Removed at antenna/public/index.html (diff line 63). grep finds zero bare `mobile-web-app-capable` in src/pages.ts. Across public, src, test, e2e and scripts only the brief-required `apple-mobile-web-app-capable` remains (index.html:12, plus the existing public/assets/preview/probe.html:6). The pages.ts diff has no other change to PLAYER_PAGE, and OFFAIR_PAGE is context only. `git status` is clean, so pages.ts matches the generator output.

### New Breakage in the Fix Diff

None blocking.
- Minor (cosmetic, no action needed): antenna/e2e/smoke.pw.mjs:767 `onAir: { artist: LONG }` is redundant, because :768 overwrites every show's artist. No behaviour effect.

### Checks Run

- Read the fix diff, makeTimeline (e2e/fixtures/timeline.mjs), the `#label-artist` wiring (page.js:130) and the `.hand` CSS.
- Fix report names covering tests: npm test 518 passed, npm run smoke 56 passed. It shows counts only, not raw output. I did not re-run either; the diff is consistent with them.
- One slip: I ran `node scripts/build-pages.mjs --help`, which may have re-run the generator. No file changed: `git status` was clean after it and again at the end of this review.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
