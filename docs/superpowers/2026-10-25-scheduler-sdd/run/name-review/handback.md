# name-review: 3a8f30e..579f619 (station on-air name "LMA Radio")

### Spec Compliance

Compliant with the operator ruling and with R27 as R27 is written.

- **Exact capitalisation.** All 9 changed occurrences read `LMA Radio`: index.html (title, og:title, h1), offair.html (title `Off the air · LMA Radio`, h1), the nowplaying.js default, the matching strings in src/pages.ts, and the runbook. None is in another case.
- **The between-shows path.** player.js:161 passes `document.title` as `stationName`. index.html's `<title>` is now `LMA Radio`, so between shows the player shows "LMA Radio". The nowplaying.js default (used only when no name is passed) agrees.
- **pages.ts is fresh.** `node scripts/build-pages.mjs --check` exits 0. `npm test` runs that check first (package.json:9). The diff of pages.ts touches only the five name strings.
- **Test.** `npx vitest run test/nowplaying.test.ts` passes 17/17. The test still covers the default name (`nowPlayingText(null, true)` returns "LMA Radio"), an explicit name, a custom name (`KXYZ`), and the not-loaded branch ("Tuning in…") with and without a name. Renaming the test to "...shows the station name between shows" is accurate.
- **Runbook (docs/playout-setup.md:558).** The note now reads: *The station's on-air name is "LMA Radio" (exact capitalisation): use it in the station IDs; the player shows it between shows (its page title).* This is accurate, and it removes the old "pick one".
- **Scope.** The diff touches exactly the R27 files: 6 files, +13/−13. Alert surfaces are unchanged: wrangler.jsonc `STATION_NAME`, alerts.ts:363, the transmitter config/alerts defaults, and playout-setup.md:361. No `docs/superpowers/` file changed, so the spec is untouched. The spec already says "LMA Radio" (spec:103), so it does not contradict the ruling.
- **Remaining "llama radio" (`git grep`).** No occurrence remains in antenna/public, the player path or src/pages.ts. The ones left in tracked code are:
  - alerts.ts:363, wrangler.jsonc:44, worker-configuration.d.ts:19 and the alerts tests (alert subjects);
  - transmitter config.py:117/231 and alerts.py:193;
  - the transmitter tests;
  - historical plan and brief docs.

### Issues

#### Critical
None.

#### Important
1. **R27's premise is incomplete: `[antenna] station_name` is not alert-only. It is also listener-visible on the per-show pages, which will still say "llama radio".** This is not an implementer defect: R27 told them to leave it alone. It is an escalation for the controller and operator.
   - publish.py:263–264 passes `cfg.antenna.station_name` into `site.render_show_page`.
   - antenna/templates/show.html puts `$station` in three places: `<title>$title · $station</title>`, `<meta property="og:site_name" content="$station">` and the back link `<a href="../">← $station</a>`.
   - These pages are published to R2 at `show/<slug>.html`, are publicly served (the WAF rule at playout-setup.md:94 allows `/show/`), and carry Open Graph tags for sharing.
   - The default (config.py:117) and the seeded `config init` value (config.py:231) are both `"llama radio"`. Unless hugo's config.toml already overrides it, every show page will show "llama radio" while the player shows "LMA Radio".
   - The implementer's line "No other listener-facing occurrences" is therefore inaccurate. Their grep did not reach the `$station` template variable.
   - playout-setup.md:361 has the same gap, which predates this change. It describes `station_name` as "the station name in alert subjects and in the titles of relayed pushes" and does not mention the show pages.
   - Two ways to resolve it:
     - (a) The operator rules that show pages are in scope. Then change the transmitter default and seed to "LMA Radio". That moves alert subjects and relayed push titles too, so keep `STATION_NAME` identical per playout-setup.md:373 and update the alert tests.
     - (b) Leave the code as it is. Set `station_name = "LMA Radio"` in hugo's config.toml at cutover, and correct row 361 to name the show pages.
   - Either way, the runbook should not keep describing this knob as alert-only.

#### Minor
1. docs/superpowers/plans/2026-10-25-scheduler.md:832–838 still shows `"llama radio"` in Task 12's test sketch. It is a historical plan, not the spec, so leaving it is consistent with the ruling. It is noted only so nobody reads it as current.
2. The runbook note does not say that alert subjects (`STATION_NAME` / `[antenna] station_name`) deliberately stay "llama radio". A half-sentence would stop an operator "fixing" one and not the other, which would break the "keep the two identical" rule at :373. This is optional, and moot if Important #1 is resolved by (a).

### Assessment

The change is correct, minimal, consistently capitalised and fresh (pages check exits 0, nowplaying test 17/17). It does what the ruling and R27 asked, with no scope creep and the spec untouched. Important #1 does not require a code change in this commit. It needs a scope decision upstream: R27 classed `station_name` as alert-only, but it also brands the public show pages.

**Task quality:** Approved
