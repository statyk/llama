### Spec Compliance

- ✅ Spec compliant. The diff is one new file, `docs/playout-setup.md` (200 lines). I extracted the brief's markdown block and diffed it against the committed doc. Every line of the brief is present verbatim. The only differences are additions at :87-96, :99-102, :113-123, :128-133 and :140-149, and they match the six orchestrator rulings plus the implementer's listed code-wins corrections. Nothing was dropped and nothing unrequested was added.
- Ruling 1 (`wrangler deploy --dry-run` first): present at :128-130. The flag is a real wrangler flag. I did not run it.
- Ruling 2 (off-air needs a published fallback, otherwise `offair-without-fallback` and the WAF kill switch is the only hard stop): present at :140-145, and correct against `antenna/src/clock.ts:180-191`, `antenna/src/playlist.ts:64-66` and `playlist.ts:76`. The "usable" conditions in the doc are exactly the code's: `fallback_version` null, `index.json` missing or unreadable, or `len < 1`.
- Ruling 3 (a re-epoch restarts MEDIA-SEQUENCE and players reload): present at :122-123, and it matches the `clock.ts:144-150` docstring. The re-epoch *procedure* the implementer added around it is incomplete (Important 1).
- Ruling 4 (`prune_margin_minutes` floor of 4): present at :93-96. The code fact is right: `config.py:69-71,84` sets `ge=PRUNE_MARGIN_FLOOR_MINUTES` = ceil((9·10.24 + 5 + 120)/60) = 4, default 10. `load_config` turns a ValidationError into a ConfigError (`config.py:115-116`), so the value is refused, not floored, as the doc says. The doc's rationale also matches the code comment at `config.py:57-64`.
- Ruling 5 (show template): present at :91-92. It matches `service.py:44-53`: an unset `[antenna] dir` or an unreadable file raises a ConfigError.
- Ruling 6 (clock spend bounds): present at :146-149. All three bounds match the code:
  - `MAX_PUTS = 10` (`clock.ts:79`), applied through `putCap` at `clock.ts:118-120`.
  - A `d` other than 10.24 is refused and logged as `horizon-refused` (`clock.ts:167-172`). transmitter writes `d = grid.D_US/1e6` = 10.24 (`publish.py:176`), so a normal horizon passes the strict equality.
  - `MAX_LOOP_MS = 75_000`, with the `loop-clamped` log at `clock.ts:156-162`.

### Checks run (one per claim, at c34be9b)
- Bucket name `llama-radio` = `antenna/wrangler.jsonc` `r2_buckets[0].bucket_name`. `workers_dev:false`, `preview_urls:false`, cron `* * * * *`, no routes: all in wrangler.jsonc. `src/index.ts` exports only `scheduled`, so there is no fetch handler.
- `npm ci` / `npm test` / `npm run deploy:assets` match the `antenna/package.json` scripts (`test` = vitest run, `deploy:assets` = `node scripts/deploy-assets.mjs`).
- `ANTENNA_BUCKET` and `--dry-run` behave as stated: `scripts/deploy-assets.mjs:12-17` reads them, and `:44-46` prints `npx wrangler r2 object put …` without running it. The script resolves paths from its own location, so cwd is not a factor.
- The off-air `wrangler r2 object put … --content-type application/json --remote` uses the same form deploy-assets uses. The clock reads `state/offair.json` and treats only `offair === true` as off-air (`clock.ts:111,115`), so `"offair": false` or deleting the object both restore service, as the doc says.
- WAF allowlist versus everything actually published or referenced:
  - deploy-assets writes `offair.html`, `player.js`, `nowplaying.js`, `style.css`, `assets/hls.min.js` and `index.html`.
  - `public/index.html` references `style.css`, `assets/hls.min.js`, `player.js`, and a favicon `data:,` URL (no request).
  - `templates/show.html` references `../style.css` and notes URLs.
  - transmitter writes `seg/`, `fallback/`, `notes/`, `show/`, `timeline.json` and `live.m3u8`.
  - All of these are allowlisted. Nothing needed is blocked, and `state/` stays blocked.
- Clock log line `{"event":"clock","lagMs":…}` matches `src/index.ts:23-24`, which logs it on every invocation, including when the clock throws.
- Player 403 handling ("stop, show off-air notice, manual retry"): `public/player.js:39,61,89`.
- `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`: read at `r2.py:17-20`; missing keys raise a ConfigError.
- `$TRANSMITTER_ROOT/config.toml`: `config.py:17-19,106`. Unknown keys are errors: `_StrictModel extra="forbid"`, `config.py:22-25`.
- Config keys `[station] root`, `[publish] account_id`/`bucket`, `[antenna] dir`/`site_url` all exist (`config.py:28-93`). `monthly_budget_usd` does not.
- `transmitter` console script: `pyproject.toml:19-20`. Dependencies are typer, pydantic, numpy and boto3, so a standalone `pip install -e packages/transmitter` resolves without herder.
- `transmitter fallback render <loop> --notice <file>`: `cli.py:123-143`. The output strings "horizon updated" and "horizon deferred (the next publish batch carries the version)" are correct. Their conditions (no local horizon yet, or the high-water rule) match `fallback.py:114-123`.
- `transmitter status` lines (epoch, plan, on air, published lead, fallback): `service.py:201-227`.
- The epoch is created by `open_station`, through `load_or_create_epoch` (`service.py:39-42`, `workspace.py:138-160`), and all five commands the doc names call `open_station`: `cli.py:69,80,92,112,133`. `status` does not create an epoch (`service.py:203-205`), so leaving it off the list is correct. `epoch.json` lives at `cfg.root/epoch.json` (`workspace.py:82`, `service.py:40`). The refusal message `published state belongs to epoch …` matches `publish.py:188-191`.
- `ALERT` lines: `alerts.py:10-11` calls `log.error("ALERT %s: …")`, and logging goes to stderr via `cli.py:147`, so journald captures it.
- Not run: no wrangler commands, no network calls, no test suite (docs-only diff). The implementer reports 2438 passed.

### Implementer's three concerns: verdicts
1. **`/embed.html` in the WAF allowlist with no asset: harmless, keep it.** The spec plans `embed.html` for phase 4 (spec :192, :372, :557). Until then a request returns an R2 404, which the edge caches (3 minutes) and the rate-limit rule bounds. No spend or continuity effect.
2. **`monthly_budget_usd` is not a config key at HEAD: confirmed, Minor** (Minor 1). It is a spec/phase-2 concept (spec :428, :478). The doc uses it only as a formula term, so the phase-1 operator has no value to plug in.
3. **The `.station-root` refusal claim: confirmed accurate.** `plan_step` calls `st.scan_now`, then `station.scan` (`pipeline.py:125`, `station.py:205-208`), then `require_root`. That raises `StationRootError` ("has no .station-root marker -- refusing …", `station.py:49-63`) before the plan is touched.

### Strengths
- The brief is reproduced exactly; every addition is a ruling or a correction tied to code.
- Every code fact in the additions checked out against source: config path, strict keys, template path, the prune floor being refused rather than raised, the fallback-render output strings, the off-air-without-fallback conditions, and all three clock spend bounds with their log event names.
- The off-air note (:140-145) states the lever's failure mode honestly and points at the kill switch as the real hard stop. That is the most spend-relevant fact in the doc.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **`docs/playout-setup.md:120-121`: the re-epoch procedure leaves out re-running `transmitter fallback render`. Following it as written makes the off-air lever inert and leaves dead air at the new epoch's start.**
   - **Cause:** the fallback version is per-workspace. `save_fallback_version` and `load_fallback_version` read and write `<root>/fallback.json` (`state.py:46-52`, `workspace.py:101-102`). Every horizon a publish writes takes the version from the local workspace (`publish.py:315,371`, `horizon_doc(..., load_fallback_version(p.ws))`). A "fresh workspace" therefore publishes `state/horizon.json` with `"fallback_version": null`.
   - **Effect, from `clock.ts`/`playlist.ts`:**
     - The `state/offair.json` lever writes nothing (`offair-without-fallback`), and so does the automatic stale-horizon off-air.
     - The start-delay window before the new epoch's first segment needs fallback entries. `buildPlaylist` returns null there (`playlist.ts:81`), so players sit on the stale old-epoch playlist and get dead air.
   - **Why it matters:** this is the strict surface. A doc-described control silently stops working after a doc-described procedure, and the only remaining stop is the WAF kill switch.
   - **Fix:** add "then run `transmitter fallback render …` (section 3 step 4) in the new workspace before the first publish; the fallback version is recorded per workspace." The same section could note that a `TRANSMITTER_ROOT` move also needs `config.toml` copied over, because the config is read from `$TRANSMITTER_ROOT/config.toml` (`config.py:106`).

#### Minor (Nice to Have)
1. **`docs/playout-setup.md:77-79`: `monthly_budget_usd` reads like a config key, but it is a phase-2 spec value with no home at HEAD.** Rephrase as "your monthly ceiling (phase 2's `monthly_budget_usd`) − $5". :90 says unknown keys are errors, so an operator who adds this "key" to `config.toml` gets a load error.
2. **`docs/playout-setup.md:120-121`: a deliberate re-epoch orphans the old epoch's segments, about 1.4 GB at a 24 h lead.** Prune deletes only the runs recorded in the local `publish.json` and never lists the bucket, so a fresh workspace never deletes `seg/<old epoch_id>/`. The cost is small (inside R2's 10 GB free storage for a few re-epochs) but it is an unbounded leak on the spend surface. Add "delete `seg/<old epoch_id>/` by hand (dashboard or an R2 lifecycle rule) once listeners have moved."
3. **`docs/playout-setup.md:97-98` (brief text): `fallback render` needs the R2 keys, but the doc loads the env file only at step 5 (:103).** `fallback render` calls `open_publisher`, which calls `make_client` (`cli.py:134`, `r2.py:17-20`), and that raises "set R2_ACCESS_KEY_ID …" without them. The failure is loud and harmless. Suggested fix: "with the env file loaded (`set -a; . <env file>; set +a`)" at step 4.
4. **`docs/playout-setup.md:25` (brief text): `npx wrangler login` / `r2 bucket create` run before `npm ci` (:127).** At that point npx fetches an unpinned wrangler instead of the lockfile's. Running `npm ci` first in section 1 fixes it.
5. **`docs/playout-setup.md:115`: "(`~/.transmitter` or `$TRANSMITTER_ROOT`, i.e. the config's top-level `root`)" blurs two things.** The workspace is `cfg.root`, which only defaults to that directory and can be overridden. The config file itself is always read from `$TRANSMITTER_ROOT` or `~/.transmitter`. Suggested wording: "the workspace (`root` in config, default `~/.transmitter` or `$TRANSMITTER_ROOT`)".

### Assessment

**Task quality:** Needs fixes

**Reasoning:** Every command, flag, key, env var, path, log event and R2 key in the doc checked out against the code at c34be9b, and all six rulings landed accurately. The one blocking gap is the implementer-added re-epoch procedure: it omits the per-workspace fallback re-render, which leaves the off-air lever inert. That is a one-sentence fix.
