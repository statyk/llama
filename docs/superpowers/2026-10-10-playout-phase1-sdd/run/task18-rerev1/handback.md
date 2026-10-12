### Scoped re-review: Task 18 fix round 1 (c34be9b..1e97973, docs/playout-setup.md only)

**Verdict: all six findings ADDRESSED, no new breakage, Task quality: Approved.**

**Important 1: ADDRESSED.** The re-epoch procedure was missing the fallback re-render. It is now in at `docs/playout-setup.md` §3 step 7: re-run `transmitter fallback render …` in the new workspace before the first publish. The step also explains why: `<root>/fallback.json` is per-workspace, and without it the horizon carries `fallback_version: null`, the off-air lever does nothing, and the start-delay window is dead air. It also says to copy `config.toml` when `TRANSMITTER_ROOT` moves.
- Checked the new facts against the code at 1e97973:
  - `fallback_path = root / "fallback.json"` is at `workspace.py:101-102`.
  - The horizon takes the version from the local workspace (`publish.py:315,371`).
  - A `null` version makes both off-air paths write nothing (`playlist.ts:76,81`).
  - The config is read from `default_root()/config.toml` (`config.py:106`).
- "Before the first publish" is the right point. In a fresh workspace `fallback render` defers, and the first publish batch then carries the version (`fallback.py:114-115`).

**Minor findings: all ADDRESSED.**
1. **`monthly_budget_usd`.** §2 step 9 now calls it "your monthly ceiling, phase 2's `monthly_budget_usd`" and says it is not a transmitter config key and must not go in `config.toml`. Accurate: there is no such field at `config.py:28-102`.
2. **Orphaned `seg/<old epoch_id>/` objects.** §3 step 7 now says to delete them by hand, via the dashboard or an R2 lifecycle rule. The reason it gives is correct: prune deletes only what the local `publish.json` records, about 1.4 GB at a 24 h lead.
3. **Env file for `fallback render`.** §3 step 4 now loads it with `set -a; . <env file>; set +a`. That works because the env file is plain `KEY=value` lines (§1 step 3).
4. **`npm ci` before `npx wrangler`.** It is now first in §1 step 1, so the pinned wrangler is used for login and bucket create. §4 step 1 points back to it.
5. **Workspace vs config path.**
   - §3 step 7 now reads "workspace (`root` in config; default `~/.transmitter` or `$TRANSMITTER_ROOT`)", which matches `config.py:97`.
   - §3 step 3 now reads "always `$TRANSMITTER_ROOT/config.toml` when that is set, else `~/.transmitter/config.toml`". That matches `config.py:106`, apart from nit 1 below.

**New breakage in the fix diff:** none. The diff touches only `docs/playout-setup.md` (+18/−9). Every new code fact was re-checked as listed above. Nothing in the diff opens a cost path: the lifecycle-rule and dashboard deletes are free R2 operations, and the fallback re-render costs a handful of immutable PUTs.

**Nits (non-blocking):**
1. §3 step 3 says "always", but `--config` overrides the path on every command (`cli.py:41,57`). The runbook never passes `--config`, so the practical effect is nil.
2. The fix left several lines unwrapped and much longer than the doc's ~90-column wrap: §1 step 1, §2 step 9 and §3 step 7. They render fine as markdown; this is cosmetic only.

**Out-of-scope observations:** none new.

**Task quality:** Approved
