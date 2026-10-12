### Spec Compliance

- ✅ Spec compliant. All three brief edits are present: the Setup line matches the brief verbatim (CLAUDE.md:15); the transmitter and antenna Commands bullets are appended after the emcee bullet (CLAUDE.md:130-145); the transmitter/antenna paragraph is appended to "What this is" after the emcee/LLM-tier paragraphs (CLAUDE.md:207-238). All five orchestrator-ruled additions are present: the high-water mark, the antenna spend bounds, the held-horizon alert, PublishLocked, and the Python 3.11 gate. Two departures from the brief text are both justified by the code: `--once` was added (cli.py `run(... once ...)`), and "(needs docker)" was added (test-in-debian12.sh `exec docker run ... debian:12`).
- ⚠️ Cannot verify from the diff: the antenna "37 passed" claim has no captured output file. pytest evidence exists at `$D/task19-impl/pytest.out` (2438 passed, 7 deselected, rc 0).

### Checks run (one per claim, against 3194983)

- `--once` runs one tick: cli.py `run` passes `max_ticks=1 if once` ✓. The subcommands `plan|render|publish|status`, `fallback render <loop> [--notice]` and `config init` all exist in cli.py ✓.
- "plan/render below the low-water lead, publish + prune every minute": service.py Runner.tick (filling starts when lead < `low_water_hours`, plan max_new=1 and render run while filling, `publish_all` runs every tick, `tick_s=60`) ✓. Filling actually continues until the lead is back at `lead_hours`. That is brief wording, see Minor 4.
- `TRANSMITTER_ROOT`: config.py:18 ✓. `R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`: r2.py:17-20 ✓.
- `packages/transmitter/tests_transmitter/` is a package (`__init__.py` present) ✓. The root pyproject `testpaths` includes it, so the untouched "Test: `pytest -q`" line stays true ✓.
- The `test-in-debian12.sh` path, Python 3.11 + ffmpeg 5.1, and Docker requirement match the script ✓. `python -m transmitter.spike build|serve <dir>` matches spike.py:8-9 and 200-213 ✓.
- antenna: package.json has `test: vitest run`, `deploy:assets`, and devDependency `@cloudflare/vitest-plugin` ✓. vitest.config.ts uses `cloudflareTest` (Workers runtime) ✓. `ANTENNA_BUCKET` is read in scripts/deploy-assets.mjs:12 ✓. `docs/playout-setup.md` exists ✓.
- Dist `llama-transmitter`, CLI `transmitter`: packages/transmitter/pyproject.toml ✓. `test_no_llama_or_emcee_imports.py` exists ✓. "over NFS on hugo" matches the spec (lines 115 and 136) ✓.
- Grid facts (frames [441N, 441N+441), frame 0 at the epoch, native `aac`, ADTS, cut by counting frames) match layout.py:2-7 and aacenc.py:1 and :29 ✓.
- High-water mark:
  - The `publish.json` filename is workspace.py:89-90 ✓.
  - The `high_water` field is in state.PublishState ✓.
  - It is persisted before the horizon PUT (publish.py:310-312, before :314) ✓.
  - plan_step re-plans nothing at or below `listed_bound()` (pipeline.py:131-143) ✓.
  - Held batch: `report.held`, with the error text "horizon held: ..." (publish.py:291-298) ✓.
  - fallback defers its horizon rewrite: fallback.py:116-121 returns False, and cli.py prints "horizon deferred (the next publish batch carries the version)" ✓.
  - prune also never rewrites below the mark: it stops with "high-water" (publish.py:356-360). The text does not say so, but nothing contradicts it ✓.
- HeldTracker: `HELD_ALERT_AFTER = 3`, `alerts.alert("horizon-held", ...)`, one observe per `publish_all` (service.py:84-99, :145-146) ✓. It fires once, at exactly 3 (`==`), which fits "after" ✓.
- PublishLocked:
  - `publish_lock` uses `LOCK_EX | LOCK_NB` and raises PublishLocked (publish.py:141-152) ✓.
  - It is used by publish_batch (:244), prune (:347) and upload_fallback (fallback.py:104) ✓.
  - PublishLocked subclasses TransmitterError, so main_cli prints `error: {e}` and exits 1 ✓.
  - Runner._step logs a warning and continues (service.py:169-171) ✓.
  - The "while `run` is up" wording is wrong, see Important 2.
- antenna clock:
  - `MAX_PUTS = 10`, and `putCap = min(MAX_PUTS, ...)` (clock.ts:79, :119) ✓.
  - `d !== GRID_D` (10.24) → `horizon-refused`, return before any put (clock.ts:166-171) ✓.
  - `loopMs = min(configured, MAX_LOOP_MS = 75000)` with a `loop-clamped` log (clock.ts:155-162) ✓.
  - No usable fallback while off-air → body null → nothing written, plus an `offair-without-fallback` log (clock.ts:173-190) ✓.
  - "docs/playout-setup.md section 4 step 4" is the right place (playout-setup.md:143-154) ✓. The framing is wrong, see Important 1.
- No routes, `workers_dev = false`: wrangler.jsonc ✓. No fetch handler: index.ts has `scheduled` only ✓. live.m3u8 is rewritten at each grid boundary until `scheduledTime + loopMs` (clock.ts:204-212) ✓.
- Spec path `docs/superpowers/specs/2026-10-09-playout-design.md` exists ✓.

### Strengths

- Every constant and log/alert event name in the added text matches the code exactly: `MAX_PUTS = 10`, `HELD_ALERT_AFTER = 3`, `horizon-refused`, `loop-clamped`, `offair-without-fallback`, `horizon-held`, `PublishLocked`, `publish.publish_lock`, `state.PublishState`, `publish.json`, `high_water`.
- The implementer corrected the brief from the code (`--once`, needs docker) instead of copying it.
- The high-water explanation states the reason (a crash between the horizon PUT and the local save), not just the rule. That is the right level for a future agent tempted to "simplify" it.
- It names `antenna/src/clock.ts` as the place where the bounds live, and points to the runbook step.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. **The off-air-without-fallback case is listed as a spend bound, which reverses its safety meaning** (CLAUDE.md:229-233).
   - The sentence reads "Its clock bounds its own spend ...: MAX_PUTS ..., d refused, LOOP clamped, and an off-air flag with no published fallback writes nothing."
   - Writing nothing here is not a spend control. It means the **off-air lever does nothing**: players keep the last `live.m3u8` they got (no `#EXT-X-ENDLIST`), and the WAF kill switch becomes the only hard stop (playout-setup.md:149-154). The runbook keeps this separate (step 4) from the spend bounds (step 5); this paragraph merges them.
   - Next to "bounds its own spend", a future agent can read "off-air with no fallback = nothing written = cheap and safe". That is the wrong conclusion on the strict surface: Cloudflare has no spending cap, and this is the operator's stop lever.
   - The text is also narrower than the code. clock.ts:126-135 does the same thing for **stale-horizon** off-air (now > E + (last+1)·d + 24 h), which is the case after transmitter has been dead for a day.
   - The runbook pointer softens this, but CLAUDE.md is what agents read first.
   - Fix (one clause): move it out of the spend list. For example: "Off-air (the `state/offair.json` flag, or a horizon more than 24 h stale) only takes effect once a fallback has been published: without one the clock writes nothing and logs `offair-without-fallback`, players keep the last playlist, and the WAF kill switch is the only hard stop (`docs/playout-setup.md` §4 step 4)."

2. **The PublishLocked condition is stated wrongly: "while `run` is up" should be "while `run` holds the lock"** (CLAUDE.md:223-226).
   - `run` takes `publish_lock` only inside each tick's `publish_batch`/`prune` calls (service.py:202 → publish.py:244, :347). The lock is released between ticks.
   - So a manual `transmitter publish` while the service is running normally **succeeds**: it is serialized against the service and spends from the same PUT budget. It exits 1 only if it overlaps the service's publish/prune step.
   - The brief's constraint and the publish.py:9-11 docstring both say "while `run` holds the lock".
   - A future agent reading the current text may either stop the service to publish by hand (needless), or treat a manual publish as a guaranteed no-op while `run` is up. It is not a no-op: it uploads and spends.
   - The task brief names lock statements as defects that matter, so this is Important. The fix is the four-word swap above, optionally adding "(during its once-a-minute publish/prune step)".

#### Minor (Nice to Have)

1. **The untouched framing is now contradicted** (CLAUDE.md:149-152). "Two Python CLIs — `llama` and `emcee` — that together carry ... recording all the way to air. They ship as separate signed binaries" was true before. The repo now holds a third Python CLI and a Worker, and transmitter is what actually puts audio on air. transmitter is not a signed binary: `.github/workflows/release.yml` has no transmitter reference. The "Project status" section (CLAUDE.md:5-11) describes only the llama pipeline. Suggest one sentence in each, e.g. "...plus `transmitter` (playout, not a released binary) and `antenna/` (a Cloudflare Worker), phase 1". The brief did not ask for this, so it is Minor and needs an orchestrator ruling.
2. **The COPY-of-tree warning lists `pytest`, `pip`, `llama` and `emcee`** (CLAUDE.md:21). `transmitter` now has the same absolute-shebang hazard. Add it to the list.
3. **The antenna bullet omits two steps** (CLAUDE.md:142-145). It does not mention `npm ci` before `npm test`; commit 1e97973 fixed this exact omission in the runbook, at playout-setup.md:136. It also gives a bare `npx wrangler deploy`, while the runbook says to run `npx wrangler deploy --dry-run` first because the deploy "was never executed during development" (playout-setup.md:137-139). Suggest `cd antenna && npm ci && npm test` and "(`--dry-run` first; see the runbook)".
4. **"plan/render below the low-water lead" is only half the hysteresis** (CLAUDE.md:130-131). Filling starts below `low_water_hours` and continues until the lead is back at `lead_hours` (service.py:176-185). This is brief wording, so it is cosmetic.
5. **Formatting:** CLAUDE.md:233 runs well past the paragraph's wrap width (the sentence ends mid-line with "transmitter must stay Python"). Also, the "What this is" paragraph has grown to about 32 lines of operational detail (lock behaviour, alert constants). Under the house style this would sit better under "Architecture", but the orchestrator ruled "no new sections", so this is noted only.
6. **Process:**
   - The implementer left `pytest.out`/`pytest.rc` in `$D/task19-impl/`, against mandate 2 ("nothing else may be written"). They flagged it themselves.
   - Their pytest run shows 26 warnings, all in llama tests (test_atomic_write, test_concurrency, test_ledger_concurrency, test_locks, test_sessions). A docs-only diff did not add them, so they are pre-existing and not this task's, but they are noise in the suite output.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** Every command, path, constant and event name I checked matches the code at 3194983. Two statements need a clause each before agents act on them: the paragraph lists off-air-without-fallback as a spend bound when it actually means the off-air lever is inert, and it says PublishLocked fires "while `run` is up" when the code refuses only while `run` holds the lock. Both are one-line fixes; no code changes are needed.
