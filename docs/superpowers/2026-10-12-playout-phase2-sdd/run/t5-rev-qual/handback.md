VERDICT: APPROVED

### Findings
#### Critical
None.

#### Important
None.

#### Minor
1. `antenna/src/waf.ts:50` (`env.result === undefined`). A body of `{"success":true,"result":null}`, or a literal `null` body (`JSON.parse("null")` makes `env` itself null), passes or crashes the envelope check. The result is a `TypeError` ("Cannot read properties of null") from `ruleset.rules`/`after.rules`/`env.success`, not a `WafError`. It still fails closed, because it throws before any PATCH and the docstring already warns of non-WafError throws. But the message is uninformative, and any caller that branches on `instanceof WafError` would misclassify it. Fix: guard `env` being a non-null object, and use `env.result == null`.
2. `antenna/test/waf.test.ts:91-104`, the "abort signal" test. It checks that a live `AbortSignal` is present, not that the timeout is 5 s. A mutant `TIMEOUT_MS = 500_000` (or `AbortSignal.timeout(Infinity)`-like) survives. That matters because amendment A4's whole reason for the bound is the per-minute cron. Fix: `vi.spyOn(AbortSignal, "timeout")` and assert it was called with 5000 for each call.
3. `antenna/src/waf.ts:84-88`. Verification checks only `enabled` on the PATCH result. If the API ever dropped or altered another field (the "update replaces the rule" risk the implementer flags: `logging` and similar fields not resent), the reconcile would report success on a rule whose `expression`/`action` changed. Cheap hardening: also require the returned rule's `action === "block"` and `expression === rule.expression`. This is the live-check concern deferred to Task 17. Not required by the brief.
4. `antenna/test/waf.test.ts:53-55`. The found-0 and found-2 cases don't assert that no PATCH was issued (only the non-block case does). The current code can't reach the PATCH there, so this is only a regression net: add `expect(calls.map(c=>c.method)).toEqual(["GET"])` for each.

### ⚠️ Cannot verify from diff
- A timeout or network failure surfaces as a `DOMException`/`TypeError`, not a `WafError` (documented in the docstring). Task 6's caller must catch every throw from `reconcileKillSwitch` as `waf-api` and leave the decision blocked (Review Focus 3/4). That is Task 6's job to verify.
- Empty `zoneId`/`token` produces a real call (`/zones//...`, `Bearer `). Review Focus 4's "no network call is made with an empty token" is assigned to Task 6's pre-check, so it is not verifiable here.
- WafError messages embed the request path, and so the zone ID. Per plan lines 1184/1974 they are persisted to `state/guard.json` `waf.error` and sent in alerts. `docs/playout-setup.md:98` confirms that `state/` is not on the WAF allowlist, so the zone ID is not exposed to listeners. Nothing in the committed code contains a real ID. No action needed, provided that allowlist never adds `/state/`.
- Overlapping invocations with opposite `blocked` decisions: last PATCH wins, and the next minute re-reconciles (level-triggered). The trip-is-never-lost guarantee belongs to Task 6's latch, not this module.
- The Rulesets PATCH preserving rule position, and accepting `ref` alongside the full definition: live behaviour, Task 17.

### Strengths
- Fail-closed ordering is right. Find-exactly-one by description, then refuse a non-`block` action, then the idempotent no-op on match, all happen before any write. The PATCH URL carries only the matched rule's id, so no other rule can be touched. The test asserts that the allowlist rule r1 is unchanged.
- The envelope check refuses `!res.ok`, `success !== true` and missing `result` independently. The implementer found by mutation that the brief's fixtures left both the `res.ok` and `success` checks unpinned, and added "trusts neither…" to pin them. That is a real gap closed, not padding.
- The `api()` fake models the replace semantics (`{id, ...body}`), so the post-PATCH verification actually depends on the body sent. In "missing enabled field", sending the wrong `enabled` would fail the verify step, so that test pins the direction as well as the call.
- Absent `enabled` is read as true (`!== false`), matching the API's omission.
- Every fetch is injected via `fakeFetch` (throws on unmatched). No network access, and the fixtures use only placeholders (`zone1`, `rs1`, `waf-token`, host `h`). The repo hygiene is clean.
- The code matches the brief verbatim. The three added tests sit in the planned test file, and `support.ts` is unchanged.

### Checks run
- Brief vs implementation: compared `waf.ts` in the diff to brief Step 3 line by line. Identical.
- Can't-reach-PATCH on refusal (Review Focus 3): traced `killSwitch()`, which throws before `update` is built for found≠1 and for non-block. The non-block test asserts GET-only.
- Envelope edge cases: reasoned through `result: null` and a `null` body (Minor 1). Both throw before any write, so fail-closed holds.
- Timeout pin: reasoned that a changed `TIMEOUT_MS` still yields an unaborted `AbortSignal`, so the signal test cannot see it (Minor 2). No mutant run; the conclusion follows directly from the assertion.
- Zone-ID exposure via error messages: grepped the plan (`waf: {enabled, error}` persisted in guard.json) and `docs/playout-setup.md:98` (`state/` not allowlisted, so blocked). Not listener-visible.
- Test-output noise: grepped `t5-impl.log` for warn/error. The only hits are the expected RED run (`Cannot find module '../src/waf'`) and the implementer's deliberate mutant runs. There are no warnings in the green runs.
- Suite not re-run, per the instructions. No doubt arose that an existing run didn't answer.
