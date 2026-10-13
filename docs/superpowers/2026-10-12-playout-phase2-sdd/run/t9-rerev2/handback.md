VERDICT: OPEN FINDINGS

Both findings are addressed. One path on the spend surface still loses a "resolved". By the dispatch's rule that a lost message is Critical, it is listed as Critical below. Its direction is fail-safe (details there). The defect predates fix 2: it has existed since fix 1, but it sits on the line that fix 2 added.

### Finding verdicts

1. **ADDRESSED.**
   - Delivery is now recorded explicitly as `AlertEntry.delivered` (antenna/src/alerts.ts:71-73).
   - Older entries without the field read as delivered iff `last_sent_at` is non-null, as ruled: `wasDelivered`, :94.
   - planAlerts plans `delivered: true` on a new alert (:120) and on a repeat (:124).
   - On a failed send, dispatch sets `last_sent_at: null`. It sets `delivered` to `false` for kind "alert" and to `wasDelivered(prev)` for kind "repeat" (:341-347).
   - A failed "resolved" restores the prev entry, so `delivered` is preserved (:339).
   - The clear-time drop now keys on `!wasDelivered(e)` (:150), no longer on the null.
   - P1 is pinned by test/alerts.test.ts:404-417, "a failed repeat of a delivered alert keeps it delivered… (P1)".
   - I confirmed the pin with mutants (expected red named first, only the P1 test):
     - G1, the drop rule reverted to `last_sent_at === null`: P1 test red, 36 passed.
     - G2, a failed send always sets `delivered: false`: P1 test red, 36 passed.
   - The never-delivered drop is also pinned, through a retry sent as kind "repeat" (:419-432), and so is the legacy fallback (:434-439).
   - Repeated failures cause no write churn: the key order is preserved, so `next` serializes equal to `prev`.

2. **ADDRESSED.** The comment at alerts.ts:139-142 now says what the code does:
   - an incomplete batch neither starts nor resets the clearing window;
   - the elapsed time is wall-clock from the first allowed absence;
   - the window may complete on the next allowed batch.

   The code at :138-143 matches: it copies the entry through unchanged.

### New breakage in the fix diff

- **Critical (per the dispatch's rule; fails safe, no spend exposure): a re-alert that fails over a still-unresolved delivered episode is marked undelivered, so a re-clear silently drops the "resolved".** The cause is alerts.ts:345-346, `delivered: o.kind === "alert" ? false : …`, together with :116 and :150.
  - **Mechanism.**
    - The "new alert" branch at :116 also fires for an entry that is still **active**: one with `clearing_since` aged at least COOLDOWN_MS when the key returns.
    - That happens after a failed "resolved", which restores the active clearing entry, or after the clearing window elapsed across guard-unknown batches.
    - The previous episode's "alert" was delivered and its "resolved" never was, so as far as the operator knows the condition is still active.
    - If the fresh "alert" then fails on every channel, dispatch stamps `delivered: false`.
    - If the condition clears again before a retry succeeds, :150 deletes the entry and sends nothing.
    - The operator's last message is the old "alert"; the truth is "cleared"; no "resolved" ever comes.
  - **Reproduced** in a `git archive 24bb50b` scratch copy, run from the scratch dir. Both probes were predicted red and both went red with `got == ["alert:tripped-spend"]` and final state `{}`.
    - **P6 (failed resolved retry):** tripped-spend alert delivered at T0. Absent from +1m, channels down. "resolved" fails at +16m. Present at +17m, and the fresh alert fails (stored `{active:true, delivered:false, last_sent_at:null}`). Absent from +18m. Channels healthy at +33m: the entry is dropped and nothing is sent.
    - **P7 (incomplete batches):** alert delivered at T0. Absent at +1m on a complete batch. `{complete:false, guardComplete:false}` from +2m to +20m. Present at +21m, and the fresh alert fails. Absent from +22m with healthy channels: dropped at +37m, nothing sent.
    - The same probes are red at 9664254 (fix 1), so this predates fix 2. Fix 2 still made the explicit `delivered` decision at this line, and the dispatch named "a failed resolved retry" as a path to check.
  - **Severity, for the orchestrator.** The lost message is a "resolved", not an "alert". It fails toward "the operator believes the station is still blocked", the same direction as the P1 finding that round 1 rated Important. It never yields a false "resolved" and never hides a trip. Reaching it needs every channel down across a resolve, a return and a re-clear (for example, an ntfy outage of 30 minutes or more with no email configured, while a raise or re-trip flaps). The dispatch classes any lost message as Critical, so I have listed it as Critical.
  - **Suggested fix (one line, validated).** A failed "alert" inherits delivery from a prev episode that is still active:
    `delivered: o.kind === "alert" && !prev[o.key]?.active ? false : wasDelivered(prev[o.key])`.
    - An inactive prev (a delivered "resolved") or no prev still starts the new episode undelivered.
    - An active prev that was itself never delivered still yields false.
    - In the scratch copy with this change, P6 and P7 go green and all 37 alerts tests stay green (41 of 41).
    - Pin it with P6 and P7 as regression tests.

### Paths checked and found sound (spend surface: tripped-spend and tripped-blind share this code path)

- **A failed alert retried as kind "repeat", then delivered.** The repeat plans `delivered: true` and is kept on success. Probe P8 was predicted green and passed: `["repeat:tripped-spend","resolved:tripped-spend"]`. If the retry fails, `wasDelivered(prev)` is false, so the entry stays undelivered (test :419-432).
- **A failed "resolved" retry, followed by a successful retry.** :339 restores prev (active, `clearing_since` and `delivered` kept), and the next allowed batch resends "resolved". The existing dispatch test covers this; probe P9 passed. A return after a failed "resolved" whose new alert is delivered is a duplicate "alert", not a loss. The undelivered variant is the Critical above.
- **A return after a delivered "resolved".** The inactive entry takes the new-alert branch (:116). Its planned `delivered: true` is corrected to `false` on failure, so the new episode is undelivered until sent. P9 asserts `{active:true, delivered:false, last_sent_at:null}`, then a "repeat" retry is delivered. Persisted state only ever holds the dispatch-corrected value, because the write follows the sends (:350-355).
- **Once-keys.** The once branch (:110-115, :144-145) runs before any `delivered` logic. A failed once alert is still deleted and resent as new (:340). Once-keys are not resolvable, so no "resolved" can be lost or falsified. They are not spend-trip keys in any case.
- **Incomplete-batch copy-through.** :143 copies the entry verbatim, `delivered` included, and the present-key branches spread `notClearing(e)`, which keeps it. A false "resolved" still needs the key absent on an allowed batch (`clearedIn`, :55-57), and the diff leaves that unchanged.
- **No channel configured.** `delivered` is always true, so the log line counts as the delivery. This is unchanged and consistent with the brief.

### Out-of-scope observations

- Legacy entries in fix-1 format written after a failed *repeat* (`last_sent_at: null`, no `delivered`) would read as undelivered. That matches the ruled fallback. No such state exists anywhere: Task 9 has not been deployed, and phase 1 had no alerts.json.
- With the suggested fix, a re-cleared episode's "resolved" would read "active since <the new first_at>" rather than the first episode's. This is cosmetic.

### Checks run

- **Read:** the rereview instructions, constraints, brief, rulings A–F, the implementer handback (fix 1 and fix 2 sections), the round-1 re-review, the fix-2 diff, and the current antenna/src/alerts.ts (planAlerts :100-164, dispatch :292-366).
- **Suite:** not re-run. The fix-2 report names `cd antenna && npm test && npx tsc --noEmit`: 13 files, 210 tests, tsc clean. The named tests match the diff.
- **Scratch copy** `git archive 24bb50b antenna`, node_modules symlinked, run from the scratch dir:
  - probes P6 and P7: predicted red, red;
  - probes P8 and P9: predicted green, green;
  - mutants G1 and G2: predicted "only the P1 test red", matched;
  - the candidate fix: probes plus alerts.test.ts at 41 of 41.
- **Scratch copy** `git archive 9664254`: P6 and P7 red, which confirms the defect predates fix 2.
- **Cleanup:** scratch copies removed. The live worktree is untouched (`git status` clean, HEAD 24bb50b). No commits.
