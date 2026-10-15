**Task quality: Needs fixes.** One assertion pins nothing, and one NaN path on the cap passes when it should trip. Both are small and plan-mandated. The lease and ordering core is otherwise well built, and its tests catch 17 of 20 targeted mutants.

### Strengths
- `antenna/src/metronome-core.ts` is pure: no IO, and every function takes `nowMs`. It is 303 lines with one responsibility. Its only imports are `grid.ts` and `playlist.ts`, so it adds no cycle with `clock.ts`. The `GRID_D` move is clean: `grid.ts:16` defines it and `clock.ts:124` re-exports it.
- Expiry fails closed. `expired` is written negated (`metronome-core.ts:127`), so a NaN, missing or undefined `expiresAt` reads as expired. `storedLease` (`:122`) clamps expiry with the DO's own clock, `min(validUntil, now + 15 min)`. A stored lease with no `expiresAt` loads as NaN, which is expired (`:237`).
- Ordering is right and minimal (`:146-150`). Hold and blocked leases are accepted unconditionally (fail closed). An unblocked play lease is accepted only if its `verdictAt` is strictly newer. A future-dated `verdictAt` is bounded by the DO-clock clamp, and a test pins that.
- Validation is thorough. The play/hold shapes, `d === GRID_D`, integer `first`/`last`, string `epoch`/`epoch_id`, and an epoch that `gridOf` can parse are all checked. A malformed fallback becomes `null` rather than invalidating the lease. There is no existing horizon validator in `src/`, so nothing is duplicated (grep checked).
- The `nextTarget` arithmetic (`:164`) is correct. The result is strictly after `afterMs`, and missed boundaries are skipped.
- Fixed `STORAGE_KEYS` are pinned against `EMPTY_STATE`.
- Mutation check: 20 mutants were each run against `test/metronome-core.test.ts` in a scratch copy with its own `node_modules`, and each outcome was predicted beforehand. All 20 predictions held. CAUGHT (17):
  - `expired` written positively;
  - `>=` ordering;
  - expiry clamp removed;
  - `capAllows <=`;
  - superseded no longer exempts in fallback (b);
  - `d` check dropped;
  - hold not accepted unconditionally;
  - `isLive` ignoring off air;
  - `nextTarget` slack shift removed;
  - `recordTime` without the window;
  - stalls `>` instead of `>=`;
  - `wrote === false` ignored;
  - `stalledFor` ignoring `playSince`;
  - NaN fallback `len` kept;
  - `fallback_version` check dropped;
  - `epoch_id` check dropped;
  - 1 more in the same class.

  SURVIVED: M1, M6 and M13 (below). M14 was an equivalent-mutant baseline.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **`antenna/test/metronome-core.test.ts:199`: the "removed lease" assertion pins nothing (plan-mandated).**
   - What: `expect(stateChanges(before, { ...before, lease: null })).toEqual({ lease: undefined })`. Vitest's `toEqual` ignores properties whose value is `undefined`, so `{}` also passes.
   - Evidence: mutant M1 added `if (k === "lease" && next.lease === null) continue;` before `metronome-core.ts:272`, so a removal is never reported. It survived, 26/26 green.
   - Why it matters: `metronome-core.ts:265-266` makes "a removed lease is `undefined`: the engine deletes the key" the contract Task 4's engine consumes. If that contract silently breaks, a stored lease is left in place after the engine meant to remove it.
   - Fix: use `toStrictEqual({ lease: undefined })`, or assert `Object.keys(changes)` equals `["lease"]` and `changes.lease` is `undefined`.

2. **`antenna/src/metronome-core.ts:171,175`: a NaN `nowMs` opens the cap (plan-mandated; latent).**
   - What: `inWindow` keeps `t` when `nowMs - t < CAP_WINDOW_MS`. With `nowMs = NaN` every comparison is false, the window is empty, and `capAllows` returns `true` whatever the history.
   - Evidence: confirmed in node. `capAllows` over 10 recent timestamps with `nowMs = NaN` and cap 10 returns `true`.
   - Why it matters: this is the spend-bounding function for both DO PUTs and alarms. The global constraint is "NaN or missing values trip, never pass". No NaN source exists today, since `nowMs` is the DO's `Date.now()`, so this is defensive. But it is exactly the rubric's at-least-Important class, and Tasks 4–7 consume this function.
   - Fix: `if (!Number.isFinite(nowMs)) return false;` in `capAllows`, plus a one-line test.

#### Minor (Nice to Have)
1. **`metronome-core.ts:237`: a stored `expiresAt` is not bounded on load.**
   - What: it is checked with `typeof === "number"`, so `Infinity` (from a stored `1e999`, verified to parse as `Infinity` and never expire) or any huge finite value loads as a lease that never expires.
   - Why it matters: today only the engine's own corrupted or buggy write can produce this. But the strict-surface property "spend must not depend on cron being alive" then rests on the writer alone.
   - Fix: on load, use `min(expiresAt, validUntil)` with `finite()`. Better, have `readState` take `nowMs` and treat `expiresAt > nowMs + METRONOME_LEASE_MS` as expired.

2. **`metronome-core.ts:117`: `validateLease` keeps `raw.horizon` by reference, extra fields included, and that is what gets stored.** The hold branch copies its fields, so the two branches are inconsistent. The size of a stored value is then set by whatever the cron side passes, not by construction. `container` and `published_at` are unread elsewhere in `src/` (grep checked), so leaving them unvalidated is fine. Fix: copy the eight known fields.

3. **`metronome-core.ts:301`: `fallbackReason` (c) is written positively.** A malformed `MetronomeStatus` (`stalls` undefined or NaN, say from a version-skewed DO mid-deploy) never trips. Also, `applied: "accepted"` with `lease: "none"` is not a trigger. That combination arises when cron's clock runs more than 15 min behind the DO's, so the lease is accepted already expired. Nothing plays, no stall counts (`wasLive` is false), and cron sees healthy. Both cases are unlikely, and fail-closed here costs cron's loop spend. Consider treating a non-finite `stalls`, or an accepted play lease that comes back `lease: "none"`, as a fallback reason.

4. **Untested boundaries:**
   - M6: `inWindow` at exactly 60 000 ms (`<` vs `<=`) survives. The spec only fixes "just over" and "just under".
   - M13: `readState` accepting negative `stalls` survives (`metronome-core.ts:259`; the code is correct but unpinned).
   - `stalledFor(true, null, null, now)` returns `now`, which is fail-toward-fallback (the implementer flagged this). Task 4 must keep `playSince` set whenever the lease is live.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The fail-closed lease, ordering and expiry are well built, and the tests catch 17 of 20 targeted mutants. The two Important items are each about a one-line fix: a vacuous assertion on the lease-delete contract, and a NaN-passes path on the spend cap. Both come verbatim from the plan.
