### Scoped re-review: Task 19 fix round 1 (3194983..3a3e034, CLAUDE.md only)

All seven in-scope findings are addressed, and the fix diff introduces no new breakage.

**Spec compliance:** ✅ Every in-scope finding is ADDRESSED. The orchestrator's rulings are respected: Minor 5's move to Architecture was not done, and Minor 6 is deferred to the final review.

| Finding | Verdict | Evidence |
|---|---|---|
| I1: off-air-without-fallback | ADDRESSED | Taken out of the spend list. The spend sentence now ends at `loop-clamped` (CLAUDE.md ~238-241). A separate "Separately, the off-air lever is INERT without a published fallback" sentence covers both `state/offair.json` and a horizon more than 24 h stale, and states the consequences: nothing written, `offair-without-fallback` logged, players keep the last playlist, WAF kill switch is the only hard stop, plus the runbook pointer. |
| I2: PublishLocked condition | ADDRESSED | Now reads "`run` holds it only during its once-a-minute publish/prune step". A manual publish "normally succeeds (serialized, spending PUTs from the same budget)" and exits 1 only on overlap. |
| M1: framing | ADDRESSED | Project status gains a sentence saying transmitter is "not a released/signed binary" and antenna is a Worker. "What this is" opening gains a parenthetical pointing to the playout paragraph. |
| M2: COPY-of-tree list | ADDRESSED | `transmitter` added to the console-script list. |
| M3: antenna steps | ADDRESSED | Now `cd antenna && npm ci && npm test`, and `npx wrangler deploy (run --dry-run first; see the runbook)`. |
| M4: hysteresis | ADDRESSED | Now "plan/render once the lead drops below `low_water_hours`, and keep filling until it is back at `lead_hours`". |
| M5: re-wrap | ADDRESSED (re-wrap part) | The long line at old :233 is re-wrapped. See Minor 2 below for a new long line. |

**New code facts in the fix diff, each checked once:**
- "24 h stale": playlist.ts:25-29 `isOffair` returns true when `offair`, or when `nowMs > start(last+1) + offairAfterMs`. clock.ts:42 defaults `offairAfterMs` to `OFFAIR_AFTER_SECONDS` 86400, and wrangler.jsonc sets `"86400"` ✓. playlist.ts:76 returns null (nothing written) when off-air and `fb` is null, in both causes ✓.
- "spending PUTs from the same budget": `PutBudget` is file-backed at `ws.puts_path` (service.py:76, publish.py:64-75), so a manual publish and `run` against the same workspace share one daily budget ✓.
- "`run` holds it only during its once-a-minute publish/prune step": the lock is taken only inside `publish_batch`/`prune` (publish.py:244, :347), which `Runner.tick` reaches via `publish_all` every 60 s tick (service.py:202, `tick_s=60.0`) ✓.
- `low_water_hours` / `lead_hours` are real config names (config.py:44, :52) ✓. Filling stops at `lead >= lead_us - D_US`, within one segment of `lead_hours` (service.py:183-185), so "back at `lead_hours`" is accurate ✓.
- `release.yml` has no transmitter reference (checked last round) ✓. The transmitter paragraph is still the last paragraph before "## Architecture", so "described at the end of this section" is true ✓.
- Fix-round evidence: `task19-fix1.log` shows antenna 37/37 passed. The fix report states pytest 2438 passed. A docs-only diff cannot change either.

**New issues:**
- Critical: none.
- Important: none.
- Minor 1: "What this is" now reads "...all the way to air (the playout side, `transmitter` + `antenna/`, is described at the end of this section). They ship as separate signed binaries". "They" still means llama and emcee, but the parenthetical sits between the subject and the claim, so a reader could take "They" to include transmitter. Project status contradicts that reading explicitly, so this is cosmetic. Optional fix: put the parenthetical after the "signed binaries" sentence.
- Minor 2: that same edited line runs past the paragraph's wrap width (~95 columns). This is the same cosmetic class as the old Minor 5.

**Strengths:** The I1 rewrite is better than the suggested text: it puts "INERT" up front and keeps the spend bounds as a clean list of true spend controls. The I2 rewrite adds the shared-budget fact, which is the spend-relevant part of a manual publish, and that fact is correct.

**Task quality:** Approved

**Reasoning:** Both Important findings and Minors 1-5 (within the ruled scope) are fixed. Every new code fact the fix asserts (stale-horizon 24 h rule, file-backed shared PUT budget, lock held only during the publish/prune step, hysteresis bounds) matches the code at 3a3e034. What remains is two cosmetic nits.
