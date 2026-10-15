### Spec Compliance
- ✅ Spec compliant. All four brief-listed files carry their hunks; nothing outside them changed.
- Check run: I extracted the brief's Step 1 and Step 4 code blocks and diffed them against `git show fb30bd5:` of `antenna/test/metronome-core.test.ts` and `antenna/src/metronome-core.ts`. Both are byte-identical (TEST-SAME, CORE-SAME).
- Check run: `GRID_D` is defined once, at `grid.ts:16`, just before `interface Grid`, with the brief's comment. `clock.ts:3` imports it and `clock.ts:124` does `export { GRID_D }`. The `d` refusal at `clock.ts:267` still resolves. `metronome-core.ts` imports `grid` and `playlist` only, never `clock`.
- Constants match the brief and the global constraints exactly: 900_000 / 30_000 / 2 / 10 / 12 / 60_000 / 5_000 / 15_000 / 25 / 2_000 / "metronome".
- Produced interfaces exist with the brief's shapes: `PlayLease`, `HoldLease`, `Lease`, `StoredLease`, `LeaseKind`, `MetronomeClient`, `MetronomeState`, `STORAGE_KEYS`/`StorageKey`, and all 24 listed functions plus `EMPTY_STATE`. `MetronomeStatus` matches the spec's interface field for field (`metronome-core.ts:151-165` against spec lines 263-273).
- Spec "The lease":
  - Validation (`metronome-core.ts:175-210`) covers every listed check: kind, finite `verdictAt`/`validUntil`, boolean `blocked`, `gridOf` passes, `d === GRID_D`, integer `first`/`last`, string `epoch_id`, string-or-null `fallback_version`. A malformed fallback becomes null.
  - Ordering (`:238-242`): blocked play and hold are accepted unconditionally; an unblocked play needs no current lease or a strictly greater `verdictAt`.
  - Expiry (`:214-221`): stored `expiresAt = min(validUntil, now + 15 min)`, and the check is negated.
- Spec "Metronome (the DO)":
  - The 8-key set matches the spec's bullet list.
  - `isLive` (`:247-251`) is an unexpired unblocked play with `!isOffair`. Checked: `playlist.ts:39-43` `isOffair` is the flag or the 24 h stale test, so passing `offair: false` leaves only the stale test, as the spec defines live.
  - `stalledMs` and `stalls` follow spec renew step 2.
  - `nextTarget` (`:256-258`): checked against `grid.ts:32-38`, where `indexAt` is `Math.floor`. `startMs(indexAt(t-25)+1)+25` is the first boundary+25 strictly after t, including before the epoch.
- Spec "Spend bounds": the rolling window is `now - t < 60_000`, `capAllows` is `< cap`, and `recordTime` and `readState` truncate to the last 10 PUTs and the last 12 alarms.
- Spec "Fallback (new)": `fallbackReason` (`:386-395`) implements (a), (b) and (c) exactly as spec lines 115-120 word them, superseded exemption included.
- Test count: 26 `it` blocks (3+3+4+1+2+2+2+5+1+3), which matches the plan's 252+26=278.

- ⚠️ Cannot verify from diff (spans Tasks 4-7):
  - Callers must pass `max(now, lastTarget)` to `nextTarget`.
  - The engine must keep `playSince` set whenever the lease is live. Otherwise `stalledFor(true, null, null, now)` returns `now`, a spurious stall (`metronome-core.ts:281`, the `?? 0`).
  - `recordTime`'s `keep` must equal the cap at each call site.
  - The cap slot must be reserved before the PUT.
  - `lastBody` must be nulled on a PUT timeout.
  - `offairSeqMs = now + 75 s` and `METRONOME === "on"` are later tasks.
  - The engine must delete an invalid stored lease (`readState.leaseInvalid`) and must call `validateLease` before `decideLease`.

### Issues
#### Critical (Must Fix)
None.
#### Important (Should Fix)
None.
#### Minor (Nice to Have)
- `metronome-core.ts:329`: `parseStoredLease` accepts any `typeof number` `expiresAt`, including `Infinity` (`JSON.parse` turns `1e999` into `Infinity`) or a far-future finite value. Such a lease would never expire on the DO's own clock. Only storage corruption can reach this, because `storedLease` always computes a finite value no later than now + 15 min. But this is the strict surface, and the spec's own idiom (`finite`, as used at `:202`) would close it.
- `metronome-core.ts:209`: `validateLease` keeps `raw.horizon` by reference, so `published_at`/`container` go unchecked and any extra fields persist into the stored `lease` value. The spec's validation list does not require more, and the playlist does not read those fields (grep of `playlist.ts`/`live.ts`: no hits). The stored value's size is still bounded only by what cron sends, unlike hold and fallback, which are rebuilt from validated fields.
- `metronome-core.ts:196`: `fallbackOrNull` requires a finite `len`, which is stricter than the spec's `len: number`. That is consistent with fail-closed, so it is noted, not a defect.

### Verdict
**Spec compliance:** Pass
