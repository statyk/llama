VERDICT: OPEN FINDINGS

The seven findings are addressed as ruled. Item 4's new drop rule adds one regression (Important, below): a "resolved" can be silently lost when a repeat fails just before the condition clears.

### Finding verdicts

1. **ADDRESSED.** Resolution waits out the cooldown: antenna/src/alerts.ts:128-154. The present path is at :110-123.
   - An absent active non-once key on a batch allowed to resolve it (`clearedIn`, :55-57) gets `clearing_since = now` (:138-139). It is held unchanged inside the window (:140-141). It goes inactive with `cleared_at = clearing_since` and sends "resolved" at COOLDOWN_MS or more (:145-152).
   - An incomplete batch copies the entry unchanged (:132-135).
   - A return inside the window strips `clearing_since` and keeps `last_sent_at` (:116-123). The repeat clock is unchanged, as pinned by the flap test (`["alert@0","repeat@360"]`).
   - Once-keys still go inactive at once (:136-137).
   - An inactive entry now means it was absent for at least COOLDOWN_MS, so a return after a delivered "resolved" is a new alert at once (:110). Brief test 1's timing changed as ruled.
   - The failed-"resolved" retry still holds: :331 restores prev's entry (active, `clearing_since` kept). This is pinned by the extended dispatch test and by my probe P3.

   Interactions I checked, with probes in a scratch copy:
   - **Family rules.** A guard key's window starts and completes on `guardComplete` batches that are not complete. A clock key's window does not (guardComplete test; neither-family test).
   - **Spend surface.** tripped-spend/blind are level-triggered from guard.json on every known-outcome invocation (conditions.ts:54-66). Over 59 guard-unknown minutes, tripped-spend kept no `clearing_since`, sent nothing, and stayed active (probe P5). I found no path to a false "resolved" for either key: a "resolved" requires the key to be absent on an allowed batch.
   - **Failed alert, then a flap.** The undelivered alert has `last_sent_at` null, so it is retried at once on return (probe P4).
   - **Failed "resolved", then a return after the window.** This sends a fresh "alert" (probe P3). That is a duplicate, not a loss.
   - **One thing worth knowing:** the window is measured in wall-clock time from the first allowed absence, even across incomplete batches. A key absent at minute 1, unknown from 2 to 39 and absent at 40 resolves at 40 (the test "held" pins this). That "resolved" is true at 40. One could instead read the ruling's "starts or advances only on allowed batches" as counting only time on allowed batches, which would resolve at about 55. The code comment at :133-134 ("neither starts nor runs on") overstates what happens. Minor, and arguably within the ruling; the orchestrator's call.
2. **ADDRESSED.** `validState`, alerts.ts:286-293, keeps only non-null, non-array object entries, and any non-object document reads as {}. The test "drops non-object entries…" covers `{stale:null,n:3,a:[1],s:"x"}`, `[null]`, `null` and `7`. Object entries with wrong field types (`{}`, `{active:true}`) do not throw in planAlerts either (NaN ages, `!e.active`).
3. **ADDRESSED.** `createAlerts`, alerts.ts:295-304 and :339, is a create-only put. When the store refuses outright, it falls back to an unconditional put, the same idiom as guard.ts:141-152. A refused create (false) leaves the racer's state standing, and our sends are re-planned. The test "the first write … create-only; a refused create loses nothing" shows a duplicate, not a loss.
4. **ADDRESSED as specified**, alerts.ts:142-144, but it introduces the regression below.
5. **ADDRESSED.** alerts.ts:222-245 races `binding.send` against a 10 s default timer (channelsFromEnv passes the default) and clears it in `finally`. A timeout throws, so it counts as a channel failure. A late rejection is handled by `race`, so there is no unhandled rejection. Test: "a hung email binding times out…" gives `{sent:0, failed:1}`.
6. **ADDRESSED.** test/alerts.test.ts now uses `ACCT = "acct-5e1d0042"`, in free text with no path, and asserts the guard message contains it and neither the ntfy nor the email text does. I verified it with a mutant: literal-value redaction disabled (threshold 8 changed to 8000), red test predicted. Both the redact unit test and the WafError integration test failed, and nothing else did.
7. **ADDRESSED.** The test sender is `radio@example.org` (test/alerts.test.ts:236, 311, 457), and `lma-radio` no longer appears anywhere in antenna/src or antenna/test.

### New breakage in the fix diff

- **Important: an undelivered *repeat* is treated as a never-delivered alert, so its "resolved" is silently dropped.** alerts.ts:142-144 together with :333.
  - **Cause:** dispatch sets `last_sent_at: null` on any failed alert **or repeat** (:333, deviation 1). Item 4's new rule treats `last_sent_at === null` as "no channel ever delivered this alert" and deletes the entry without sending "resolved".
  - **Effect:** an alert that WAS delivered loses its "resolved" whenever its latest repeat failed on every channel and the condition cleared before a retry succeeded. For example, one ntfy 429 at the 6 h repeat minute with no email configured, then a raise the next minute. The entry is deleted, so no further message comes either.
  - **Reproduced** (probe P1, scratch copy, predicted red): tripped-spend alert delivered at T0; repeat fails at T0+6h; absent from T0+6h+1m; channels healthy. Received `["alert:tripped-spend"]`, expected `[…, "resolved:tripped-spend"]`. The final state is `{}`.
  - **Severity:** this is not a false "resolved" and not a lost trip alert, since the trip alert itself was delivered. It fails toward "the operator believes the station is still blocked", so there is no spend exposure; hence Important rather than Critical. It does break the brief's Failure rule: the "resolved" is never even attempted. This path did not exist before this diff.
  - **Suggested fix:** record delivery explicitly, for example `delivered: boolean`, set on the first accepted send of the episode and preserved across failed repeats, and drop only when it is false. The `kind` cannot discriminate, because a retried failed alert goes out as kind "repeat".
  - **Pin:** a test for the P1 sequence, plus the existing never-delivered tests.

### Out-of-scope observations

- `createAlerts`'s catch-all fallback (:301-303) also catches a *transient* create error and then writes unconditionally. If a racer created alerts.json in that instant, its entries are clobbered. Duplicates follow, and possibly one lost "resolved" for a key only the racer had recorded. This needs a store that throws on the precondition at the same moment a racer creates the file. It is the guard's accepted idiom, so I note it and do not block on it.
- The handback's concern 3 (an alerts.json read failure silences cloud alerts for that minute, with hugo's dead-clock monitor covering it) is unchanged by this diff.

### Checks run

- Read the re-review instructions, constraints, brief, rulings A–F, the implementer handback with fix report, the fix diff, and the current antenna/src/alerts.ts in full. I also read the relevant parts of src/conditions.ts, src/guard.ts (writeGuard idiom, condition sites) and src/bucket.ts (createJson/putJson).
- Did not re-run the suite. The fix report names `cd antenna && npm test && npx tsc --noEmit`: 13 files, 207 tests, tsc clean. Its listed tests match the diff.
- Scratch copy (`git archive HEAD antenna`, node_modules symlinked), run from the scratch directory:
  - Probes P1, P3, P4 and P5 (`npx vitest run test/probe.test.ts`): P1 red as predicted (the regression above); P3, P4 and P5 green.
  - Mutant: literal-value redaction disabled. The predicted 2 tests went red (redact unit and WafError integration); 32 passed.
- Scratch copy removed afterwards. Nothing was written to the live worktree; the only `git status` changes are Task 12's files under packages/transmitter/.
