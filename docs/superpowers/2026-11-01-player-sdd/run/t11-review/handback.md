### Spec Compliance

- ❌ Issues found: two, neither a behaviour defect.
  - Partly met: `antenna/e2e/smoke.pw.mjs:764-782`. "On main" is exercised on tickets only: the long band never reaches the cassette label, so that surface can overflow with the test green (mutant M3).
  - Extra: `antenna/public/index.html:13`, `mobile-web-app-capable`. See Minor 1.
- Otherwise compliant, checked against the brief and spec lines 142-151, 310-330:
  - Off-air page: inline styles, system fonts, no script, no `assets/`, no `style.css`, refresh 300, link to `/` (`antenna/public/offair.html:6,9-18,24`). Frozen files are not in the diff. `antenna/src/` changes only in generated `pages.ts`.
  - `theme-color` and manifest colours equal `--paper` (#e9dfc8). All off-air colours are existing palette variables.
  - Icons, measured with sips: 180, 192 and 512 square, no alpha. iOS has no transparency to fill black.
  - No service worker. The kill-switch rule is untouched.
- ⚠️ Cannot verify from here, for the Task 12 home-screen check:
  - Spec line 325 wants the page's colours in the status area. `apple-mobile-web-app-status-bar-style` `default` (`index.html:15`) relies on iOS using `theme-color` there. `black-translucent` would be wrong on cream, so the choice is reasonable but unmeasured: Test 8 and D5 ran the probe page, never this `index.html`.
  - In the preview app, `/show/...` links are outside the preview scope `/assets/preview/<n>/`, so they will show browser chrome. That is preview-only. Live scope is `/`.

### Strengths

- The third assertion (`smoke.pw.mjs:778-781`) is what catches panel overflow. M2 shows the document check is blind to the fixed panel, so the implementer went past the brief's wording usefully.
- `viewport-fit=cover` has the safe-area padding it needs: `radio.css:59-60,305-306` already carry it. `offair.html` has no env() padding but needs none: its content is centred inside 24 px.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. `antenna/e2e/smoke.pw.mjs:767-768`: the 320 px test puts the long band on `fixture-next-1` only, so the cassette label, its largest appearance at 32 px, is never tested.
   - Why it matters: this test exists to pin the long band at 320 px now that every surface exists. M3 breaks exactly that surface and the test stays green. Today's code is fine: V0 below passes.
   - Fix: also put the band on the show on air, `makeTimeline(Date.now(), { onAir: { artist: LONG } })`, keep the map for `SLUG`, and wait for `#label-artist` to show LONG before the first assertion. The just-aired torn tickets are covered if every show takes the name, as V0 did.
   - Severity is a judgement: literally the band is "on main" via tickets, but I would not sign off a guard with this hole when it is a one-line fix.

#### Minor (Nice to Have)

1. `antenna/public/index.html:13`, `mobile-web-app-capable`: drop it.
   - The brief lists only the Apple tags, and spec line 323 is scoped to the iPhone.
   - The manifest's `display: standalone` already covers Chrome.
   - Measured (M4): removing the tag changes nothing in system Chrome. No console message appears with or without it, so the usual reason for it, silencing Chrome's deprecation notice, was not observed here. DevTools' Issues panel was not checked.
   - It is harmless, so it does not block.
2. `antenna/public/offair.html:24`, "Check whether we're back": acceptable. It is not listed copy, so no exact-copy rule is broken, and it says what the link does in a window with no reload button. The spec's word for this same retry on the same off-air state is "Try again" (spec line 138). I would use that for one vocabulary, but this is the operator's taste. Do not block on it.
3. `antenna/public/assets/radio.webmanifest`: nothing tests it. A typo'd icon name or bad JSON passes both suites and surfaces only on the phone (or as a `JSON.parse` crash at `--preview`). One smoke step could fetch the manifest and assert each icon returns 200; `serve.mjs:26` already serves the type. The player-page test also pins no `apple-mobile-web-app-*` or `theme-color` tag, as the brief's own test does not.

### Checks run

- Scratch copy of 8b53cfc8 (`git archive`, cloned `node_modules`), predictions written to the log before any mutant ran, run with `node .../cli.js test -g "at 320 px"`. Added one scratch-only variant test, long band on every show including on air. A failing run names the scratch path, so the scratch tree was the one served.
- V0, unmutated: both tests green, scrollWidth 320, clientWidth 320, so hidden scrollbars do not leave a 15 px blind spot.
- M1, delete `min-width: 0` from `.main` (`radio.css:249`). Predicted red at :774. Result: red at :774, received 490. CAUGHT as predicted.
- M2, `white-space: nowrap` on `.bmain h2` (`radio.css:354`). Predicted to pass :774 and :777 and go red at :781. Result: red at :781, received 427. CAUGHT as predicted.
- M3, `white-space: nowrap` on `.hand.h1` (`radio.css:118`). Predicted the existing test stays green and the variant goes red. Result: existing test green; variant red, scrollWidth 523. SURVIVED as predicted; the variant's red proves the mutant was served.
- The overflow test can fail on tickets and on the panel, and cannot fail on the cassette label.
- Manifest vs `--preview` in `antenna/scripts/deploy-assets.mjs`, by reading: they agree.
  - `:109-111` matches the exact name `walkAssets` yields, spreads all fields and overrides `start_url` to `/assets/preview/<n>/index.html` and `scope` to `/assets/preview/<n>/`. The page is uploaded at that same `index.html` (`:107`), so it is in scope, as spec line 355 asks.
  - The page's relative `assets/radio.webmanifest` resolves to the uploaded `<base>/assets/radio.webmanifest`. The manifest's relative icon paths resolve beside it, and both icons are uploaded by the walk.
  - The live path: `liveUploads` sends `assets/radio.webmanifest` as `application/manifest+json`.
  - A `--dry-run --preview 99` in scratch confirmed those keys and wrote no `.preview-99.json`.
- Named risk, the station allowlist: `/assets/` is already allowed (`docs/playout-setup.md:93`). During a block the manifest and icons 403, which only matters at install time. The off-air page references neither.
- Not re-run: the full suites (the implementer's 518 and 56 stand).

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The page, off-air page and manifest are right, and the manifest agrees with `--preview`. The 320 px test is proven for tickets and panel but has a surviving hole on the cassette label, a one-line fixture change.
