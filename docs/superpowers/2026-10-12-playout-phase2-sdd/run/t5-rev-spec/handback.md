VERDICT: APPROVED

### Findings
#### Critical
None.

#### Important
None.

#### Minor
1. antenna/test/waf.test.ts:73-104 — Extra (not requested): three tests beyond the brief ("trusts neither an HTTP error nor success: false, even with a result", "resends action_parameters when the rule has them", "gives every API call an abort signal (the 5 s timeout)"). These add tests, not behaviour. Each pins a requirement the brief states in prose ("API failure", "action_parameters if present", "times out after 5 s") but its own tests leave unpinned; the implementer reports a mutant that survived without the first one. The brief's five tests are intact and come first. No action needed; noted only because the spec seat lists extras.

### ⚠️ Cannot verify from diff
- PATCH body completeness against the live Rulesets API (resends action, expression, description, enabled, ref and action_parameters only; fields such as `logging` are not resent). This is plan-mandated and fine for a free-plan `block` custom rule. Only Task 17's live check can confirm that the update keeps the rule whole.
- Review Focus 3's other halves: the `waf-api` alert on a refusal, "a block stays cooperative (ENDLIST + off-air page)" when the WAF fails, and "a WAF failure while blocked ... leaves the decision blocked". These are Task 6/8 (guard.ts, the clock).
- Review Focus 4, "no network call is made with an empty token": waf.ts does not check for an empty token or zoneId (an empty zoneId would call `/zones//...`). The brief assigns that refusal to Task 6 (`"missing secrets fail every evaluation and the WAF reconcile, loudly"`), so Task 6's review must confirm it.
- R14's `waf-corrected` alert (a hand toggle undone) depends on Task 6 reading `changed: true` while the latch state is unchanged. waf.ts supplies `changed` correctly.
- Token permission (Zone → WAF → Edit, zone-scoped): Task 17, live.

### Strengths
- `antenna/src/waf.ts` matches the brief's Step 3 code byte for byte. `diff` of the brief's code block against `git show 8a4d652:antenna/src/waf.ts` is empty.
- The brief's five tests match its Step 1 block verbatim, with the brief's exact names and assertions, including Review Focus 3's named test, "refuses when the rule is missing, ambiguous or not a block rule".
- Every exported interface matches the brief: `API`, `PHASE`, `WafConfig {zoneId, token, description}`, `WafError extends Error`, and `reconcileKillSwitch(fetchFn, cfg, blocked): Promise<{enabled, changed}>`.
- Spend-surface rules in the code:
  - The rule is found by exact description, never by a hard-coded ID.
  - Zero or several matches throw (`found N`), and so does a non-block action (`not "block"`). All three throw before any PATCH; the test asserts GET-only for the non-block case.
  - The PATCH URL names only the matched rule's id, and a test asserts the allowlist rule r1 is untouched (A5, Review Focus 3).
  - An absent `enabled` reads as true, both before the PATCH and when verifying it. A PATCH response that drops the rule or does not reflect the change throws `did not take`.
  - Non-JSON, non-2xx, `success !== true` and a missing `result` each throw `WafError`.
  - Every call carries a 5 s `AbortSignal.timeout`.
  - The guard's budget of one Rulesets GET per invocation and a PATCH only on a state change holds: the matching state returns after the GET alone.
- Only the two files the brief lists were created. No other file changed, and the fixtures carry no account details.

### Checks run
- Missing/misunderstood code: I extracted the brief's waf.ts and waf.test.ts code blocks and diffed them against the committed files at 8a4d652. waf.ts is identical. The test file is the brief's text plus 32 added lines (the three extra tests).
- Files touched as listed: the package stat shows exactly antenna/src/waf.ts and antenna/test/waf.test.ts, both new, matching the brief's "Create" list.
- Spec text: I checked the design spec's "Blocking" paragraph (level-triggered, reads the rule's actual state, Rulesets failure retried next run) and plan amendment A5 (no rules created; exact description; 0 or >1 is an error; non-block is an error). The implementation does all of this. The alerting and retry-next-run parts belong to Task 6.
- Test helper compatibility: test/support.ts's `fakeFetch` records headers through `new Headers(init.headers)`, so the authorization-header assertion is valid. The added signal test wraps `fakeFetch` rather than changing the shared `FetchCall` shape.
- I did not re-run the suite and had no specific doubt that needed a focused run. The implementer reports 102 passing and tsc clean.
