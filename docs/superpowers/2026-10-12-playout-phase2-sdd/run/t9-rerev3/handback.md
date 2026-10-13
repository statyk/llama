VERDICT: ALL ADDRESSED

### Finding verdicts

1. **ADDRESSED.** Evidence: antenna/src/alerts.ts:348-349.
   - The failed-send branch now sets
     `delivered: o.kind === "alert" && !prev[o.key]?.active ? false : wasDelivered(prev[o.key])`.
   - The three required cases hold:
     - **Absent or inactive prev:** starts undelivered (`false`).
     - **Active, delivered prev:** inherits `true`.
     - **Active prev that was never delivered:** `wasDelivered` gives `false`.
   - **P6** is pinned at test/alerts.test.ts:446-459. It includes a mid-sequence assertion on the stored `{active:true, delivered:true, last_sent_at:null}`.
   - **P7** is pinned at :461-473. It uses `{complete:false, guardComplete:false}`, which is right for a guard-family key.
   - **The control** (a delivered "resolved", then a failed return) is at :475-485.
   - The report's RED/GREEN and mutant claims (H1 makes only P6 and P7 red; H2 makes only the control red) are consistent with the diff.
   - Only the never-delivered active case lacks a test (see Minor below).

### New breakage in the fix diff

**No Critical or Important issues.** I checked the line against the whole delivered/clearing state machine (spend surface: tripped-spend and tripped-blind):

- **Where it can fire.** A kind "alert" with an active prev comes only from planAlerts' new-alert branch, via an active entry whose `clearing_since` has aged at least COOLDOWN_MS (:116). Once-keys only send when there is no prev, and a failed once alert is deleted before this line runs (:340). So the change touches nothing else.
- **No false "resolved".** A "resolved" still needs the key absent on an allowed batch for COOLDOWN_MS (:144-163), and the diff leaves that unchanged.
  - P13: the re-alert fails over an active delivered episode, then the condition stays present with healthy channels. Got `["alert","repeat"]`, the entry stays active, and no "resolved" is sent while present.
- **An active never-delivered prev never becomes "delivered".**
  - P10: the alert is never delivered; the clearing window ages across incomplete batches; the re-alert fails. Stored `delivered:false`. The re-clear with healthy channels drops the entry, `got == []`.
- **No duplicate "resolved".** The inherited entry is built without `clearing_since` and with `last_sent_at: null`, so the next present batch retries it as a "repeat" (Infinity >= repeatMs). Clearing then resolves the merged episode exactly once.
  - P11 (repeat retry succeeds): `["alert","repeat","resolved"]`.
  - P12 (repeat retries keep failing while present, `delivered` stays true, then clear): `["alert","resolved"]`.
- **Failed repeats after the inheritance.** A failed repeat takes `wasDelivered(prev)`, where prev is now the inherited `true`. It stays true across repeated failures, so it neither drops nor fabricates.

**Minor (test gap, not breakage):** test/alerts.test.ts does not pin the "an active prev that was never delivered stays false" arm.
- Mutant M1 forces a failed alert over any active prev to `delivered: true`. Expected red: P10 only. Result: all 40 committed alerts tests stayed green; only my P10 went red (1 failed, 43 passed).
- Under M1, a never-delivered tripped-spend episode would get a "resolved" for an alert the operator never received.
- The committed code is correct here. Only the pin is missing.
- Suggest adding P10 as a fourth test in the new describe block:
  1. A broken-channel alert at T0, then absent on a complete batch at +1m.
  2. Incomplete batches from +2m to +20m.
  3. The re-alert fails at +21m. Assert `delivered:false`.
  4. Absent with healthy channels from +22m to +37m. Assert `got == []` and the state is `{}`.

### Out-of-scope observations

- `prev[o.key]?.active` is a truthiness test on hand-editable JSON (validState only checks object shape). A hand edit like `"active": "no"` would read as active. Every other branch of planAlerts has the same exposure, so this is not new, and the fallback is the conservative side.
- HEAD moved to 6f52067 (Task 13, transmitter only). It does not touch antenna/ (`git diff --stat 7f30c7b HEAD -- antenna` is empty).

### Checks run

- **Read:** rereview-common.md, constraints.md, the task-9 brief (rules plus test head), rulings A–F, the fix-3 section of the implementer handback, the t9-rerev2 handback (P6/P7), the fix-3 diff, and the current alerts.ts planAlerts (:100-164) and dispatchAlerts (:315-357).
- **Suite:** not re-run. The fix-3 report names `cd antenna && npm test && npx tsc --noEmit` (13 files, 213 tests, tsc clean), and the named tests match the diff.
- **Scratch copy** (`git archive 7f30c7b antenna`, node_modules symlinked, run from the scratch dir):
  - Probes P10–P13 were predicted green. Result: alerts.test.ts plus the probes, 44/44 green.
  - Mutant M1 was predicted "only P10 red". It matched: 1 failed, 43 passed, and every committed test stayed green.
- **Cleanup:** scratch removed. Live worktree untouched (`git status --short antenna` empty). No commits, no stash.
