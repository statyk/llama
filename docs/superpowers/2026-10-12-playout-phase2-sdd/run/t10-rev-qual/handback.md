VERDICT: NEEDS FIXES

### Findings

#### Critical
None.

#### Important
1. **antenna/test/wrangler-config.test.ts:10-11: the "no account details" test does not catch a zone ID at all, and catches an account ID only as a top-level key (plan-mandated).** The test is the brief's code verbatim. Its title promises that wrangler.jsonc "carries no account details", and the plan says it "keeps wrangler.jsonc free of account details and addresses". It has exactly two checks: `config` has no top-level `account_id`, and the text matches no `@x.y` pattern. I mutated a scratch copy to check. Each of these mutants left the suite green (2 passed):
   - M2: `"routes": [{ "pattern": "x.example/*", "zone_id": "<32 hex>" }]`. The zone ID gets through, and so do routes on a Worker that must stay cron-only.
   - M3: `"env": { "production": { "account_id": "<32 hex>" } }`. This is a nested account_id, a common wrangler shape.
   - M4: a 32-hex account ID as a var value (`"CF_ACCOUNT_ID": "<32 hex>"`), the obvious mistake when someone "simplifies" a secret into a var.

   The repo is public, and this is the one guard against that leak, so a test that claims the constraint without pinning it is Important. Fix (verified in the scratch copy: M0 still passes and M2, M3 and M4 each go red). Add to the first `it`:
   ```ts
   expect(wranglerText).not.toMatch(/"(account_id|zone_id)"\s*:/);   // any depth, incl. env.* and routes[]
   expect(wranglerText).not.toMatch(/\b[0-9a-f]{32}\b/i);            // Cloudflare account and zone IDs are 32 hex
   expect(config).not.toHaveProperty("routes");                      // cron-only (spec "Architecture")
   ```
   The current file contains no 32-hex string, so this adds no false positive.

#### Minor
1. **antenna/tsconfig.json:13: `vite/client` widens types project-wide (plan-mandated).** It adds ambient declarations to `src/` as well as `test/`: `*?raw`, `*?url`, `*.css`, `*.svg` modules and `import.meta.env`. Worker code that imported `./x?raw` would then pass `tsc` but fail in wrangler's esbuild bundle. Only a deploy or a dry run would show that, and implementers run neither. Two narrower options:
   - a one-line `declare module "*?raw" { const s: string; export default s; }` under `test/`;
   - a test-only tsconfig.

   The brief chose `vite/client` on purpose, so this is a note, not a fix request.
2. **antenna/package.json: `vite/client` resolves from a dependency of a dependency.** Vite comes in only through vitest's dependencies (hoisted to `node_modules/vite` today). If npm ever stops hoisting it, `tsc --noEmit` breaks. Listing `vite` in devDependencies would make the dependency explicit.
3. **antenna/test/wrangler-config.test.ts:6: the JSONC parse is fragile.** Stripping whole-line comments means one later inline `// comment` or trailing comma (both legal JSONC) makes `JSON.parse` throw at module load. This fails in the safe direction: the file goes red loudly. But the cause is an unrelated edit, and the error message ("Unexpected token") does not say why. The doc comment does state the limitation. Optional fix: strip comments and trailing commas more robustly, or catch the parse error and rethrow it with a hint.

### ⚠️ Cannot verify from diff
- **docs/playout-setup.md:195 is now stale.** It still says `deploy:assets` uploads the "player page". The plan rewrites that step in a later task (plan line ~6211). Confirm it lands there.
- **First-deploy ordering.** `index.html` now comes from the clock, which writes it within a minute of the Worker deploying. The player page references `player.js`, `style.css` and `assets/hls.min.js`, which `deploy:assets` uploads. If the Worker deploys before the assets on a fresh bucket, the page briefly points at missing assets. The live bucket already holds the phase-1 assets, so this is harmless here, but the runbook order (Task 17) should keep assets uploaded before or alongside the deploy.

### Strengths
- **The `deploy-assets.mjs` edit is minimal and correct.** Only the `index.html` entry and its now-meaningless "last" comment go. The header now says who owns `index.html`. The clock's `INDEX_HTTP` keeps the same `public, max-age=60` the removed entry used, so the cache behaviour is unchanged.
- **The phase-1 `index.html` already in R2 gets taken over.** It has no `sha256` customMetadata. `reconcileIndex` (src/indexpage.ts) compares `info?.customMetadata?.sha256` and rewrites on a mismatch or when it is absent, so the clock takes over within a minute.
- **The binding is correct as committed.** It names no destination and no address, and the wrangler.jsonc comments say why.
- **`worker-configuration.d.ts` matches the config.** It was regenerated so `Env` carries `ALERT_EMAIL: SendEmail`.
- **The second test checks the binding is live.** It asserts that the vitest pool actually binds `ALERT_EMAIL` (`send` is a function), not only that the config text contains it.

### Checks run
- **Risk: with ALERT_EMAIL now bound in the vitest pool, can a test reach a real email path?** Answer: no. I checked:
  - `grep "scheduled!(\|fetch!("` over test/: the only two Worker-handler invocations are clock.test.ts:480 and :500, and both pass `noSecrets()`. `noSecrets()` (clock.test.ts:465-468) sets `ALERT_EMAIL`, `ALERT_EMAIL_FROM` and `ALERT_EMAIL_TO` (and NTFY_*, CF_*) to `undefined`.
  - The other `cloudflare:test` users (bucket.test.ts, indexpage.test.ts) touch only `env.BUCKET`.
  - alerts.test.ts:310 spreads a local `GuardEnv` (line 288), not the pool env, and injects a fake binding and a fake `EmailMessage`.
  - There is a second, independent guard. `channelsFromEnv` (src/alerts.ts:280) builds an email channel only when the binding AND both `ALERT_EMAIL_FROM` and `ALERT_EMAIL_TO` are non-empty, and neither is bound in the pool: no `.dev.vars` or `.env` exists in antenna/, and none is tracked.
  - On top of that, Miniflare's local send_email binding does not deliver mail.
- **Risk: does the wrangler-config test fail if an account ID, zone ID or address is added?** I ran mutants in a scratch copy (`git archive HEAD antenna | tar -x`, node_modules symlinked, run from the scratch dir), with `npx vitest run test/wrangler-config.test.ts`. I wrote the predicted result down before each run. Every result matched its prediction:
  - M0 baseline: 2 passed. This also shows the scratch config is the one under test, since M1 and M5 go red there.
  - M1 top-level `account_id`: red, "carries no account details...". Predicted red.
  - M2 `routes[].zone_id`: GREEN. Predicted survive.
  - M3 `env.production.account_id`: GREEN. Predicted survive.
  - M4 32-hex var value: GREEN. Predicted survive.
  - M5 `// send to ops@example.net` comment: red. Predicted red.
  - Hardened test (the three lines above): M0 2 passed; M2 red on the `account_id|zone_id` key check; M3 red on the same; M4 red on the 32-hex check.

  Output is teed to `$D/t10-rev-qual/t10-rev-qual.log`. The scratch copy has been deleted, and the live worktree is untouched (`git status` is clean).
- **Risk: does the clock take over the stale phase-1 `index.html`?** I read `src/indexpage.ts` `reconcileIndex`: it rewrites when the `sha256` metadata is absent or differs.
- **Risk: does `vite/client` resolve?** `node_modules/vite/client.d.ts` exists. Vite reaches the lockfile only as a peer or dependency of the vitest packages.
- No wrangler command and no `--dry-run` was run. I read `deploy-assets.mjs` in full; it has no remaining `index.html` reference except the header comment.
