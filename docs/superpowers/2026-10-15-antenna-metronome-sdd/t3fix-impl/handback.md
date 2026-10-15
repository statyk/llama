# t3fix-impl handback — core fix round (items 1-4)

**Status:** DONE_WITH_CONCERNS (concerns are two small deviations from the brief's literal text, both explained below; no behaviour concern)

Commit: `2dfda92` fix(antenna): metronome core fails closed on stored expiry, stall count and an accepted lease not playing (one commit, all four items; on top of aeef49d)

## What was implemented
1. `parseStoredLease` (antenna/src/metronome-core.ts): after validateLease passes, `expiresAt` must be `finite(...)`; otherwise it returns `{ lease: null, invalid: "stored lease: expiresAt not finite" }`. Infinity (stored `1e999`), -Infinity, null, a string, or a missing value are all invalid, so `readState().leaseInvalid` is set. I checked the engine path and left it unchanged: `MetronomeEngine.begin()` already logs `metronome-lease-invalid` (source storage) and saves `{lease: undefined}` whenever `leaseInvalid !== null`. `storedLease` is unchanged.
2. `fallbackReason` (c) is now written negated: `!(Number.isInteger(s.stalls) && s.stalls >= 0 && s.stalls < STALLS_FALLBACK)`. The reason string is unchanged.
3. `fallbackReason` (b) has a new disjunct `(!sent.blocked && s.lease !== "play")` under the existing `sent.kind === "play" && applied !== "superseded"` guard, so `superseded` stays exempt. The doc comment for (b)/(c) is updated.
4. antenna/test/metronome-renew.test.ts, in the existing test "an invalid lease is applied invalid: ..." (line 64): `port.ops.length = 0` before the invalid renew, then `expect(port.ops).toContain("save lease,stalls")`. No new `it`.

## Deviations from the brief (please check)
- **The (b) reason string gained a `lease=` field.** It is now `renew answered applied=${applied}, wrote=${wrote}, lease=${lease} to a [blocked ]play lease`. Without it, the new case reads "applied=accepted, wrote=true to a play lease", which looks healthy in a metronome-down alert. The format (same key=value list, same trigger) is otherwise kept. Existing tests (/wrote=false/, /invalid/, /off/, renew-test /wrote=false/) still match. If the literal old string is required, drop `, lease=${s.lease}` and loosen the new test's regex.
- **One existing test pinned the opposite of item 1.** It was "a stored lease whose expiresAt is missing loads as expired" (it asserted `lease` not null). I re-pointed it instead of deleting it, so the `it` count holds: it is now "a stored lease whose finite expiresAt has passed loads, as expired" (a valid, finite, past expiresAt loads with invalid=null and is expired). That keeps the valid-but-expired load path pinned. The missing case is covered by the new item-1 test.
- **Item 4 is not on an empty store.** No existing invalid-lease test uses an empty store, so I used the line-64 test as the brief allows. There the invalid-branch flush also deletes the lease, so the correct op is `"save lease,stalls"`, not a bare `"save stalls"`. The mutant `flush(tx)` gives `"save lease"` and is caught (evidence below).

## TDD evidence
RED, items 1-3 (new tests added, source unchanged): `npx vitest run test/metronome-core.test.ts test/metronome-renew.test.ts`
```
× a stored lease whose expiresAt is not a finite number is invalid (no lease)
× (c) fails closed: a stall count that is not a non-negative integer trips
× (b) an accepted unblocked play lease the DO is not playing (accepted already expired)
Tests  3 failed | 52 passed (55)
```
All three failed with `TypeError: .toMatch() expects to receive a string, but got object`, meaning the old code returned null (no invalid reason, no trigger). That is the fail-open being fixed.

GREEN, items 1-3: same command, `Tests  55 passed (55)`.

RED, item 4 (mutant `flush(tx, true)` -> `flush(tx)` in the invalid branch). I ran it in a scratch copy (tar of antenna/ minus node_modules, node_modules symlinked), from the copy's own cwd: `npx vitest run test/metronome-renew.test.ts`
```
× an invalid lease is applied invalid: logged, the stored lease and the alarm deleted, nothing written
AssertionError: expected [ 'save lease', 'deleteAlarm' ] to include 'save lease,stalls'
Tests  1 failed | 25 passed (26)
```
GREEN, item 4: the live worktree passes (full suite below).

## Full verification (after the final formatting tidy, which changes no behaviour)
- `cd antenna && npm test`: `Test Files 17 passed (17)`, `Tests 307 passed (307)` (expected 307)
- `cd antenna && npm run typecheck`: `tsc --noEmit`, clean
- `grep -rn fallbackReason src` returns only metronome-core.ts itself. Nothing in src calls it yet; its users are test/metronome-core.test.ts and test/metronome-renew.test.ts, and both pass. test/clock*.test.ts pass in the full run.

## Files changed
- antenna/src/metronome-core.ts
- antenna/test/metronome-core.test.ts
- antenna/test/metronome-renew.test.ts

## Self-review
- The changes are minimal and in the named module. No engine change was needed for item 1.
- Formatting: the (c) return was split onto its own block and the (b) template uses a `kind` local, to stay within the file's ~120-column style (amended into the same commit before reporting).

## Concerns / for the controller
- Item 3 covers unblocked play leases only, as the brief specifies. A *blocked* play lease accepted already expired (lease "none" rather than "blocked") still gives no (b) trigger. Under the lease table that may be intended (the expired DO lease is idle and writes nothing), but Task 7's author may want to confirm.
- The two deviations above: the reason-string field and the re-pointed existing test.
