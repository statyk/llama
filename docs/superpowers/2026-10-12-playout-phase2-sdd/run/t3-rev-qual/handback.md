VERDICT: APPROVED

### Findings
#### Critical
None.

#### Important
None.

#### Minor
1. **The 15 s timeout is unpinned** -- `antenna/src/meter.ts:131` (`signal: AbortSignal.timeout(TIMEOUT_MS)`). `fakeFetch` (`test/support.ts` `FetchCall`) records url/method/headers/body but not `init.signal`, so a mutant that drops the signal survives every test. A hung GraphQL POST would hold the invocation (the guard runs first, so it delays everything after it). The brief did not ask for a test. Fix if wanted: record `signal: init?.signal ?? null` in `FetchCall` and assert `f.calls[0].signal` is an `AbortSignal`. Alternatively, use a never-resolving route plus fake timers and assert a rejection.
2. **Most class assignments beyond the measured list are unpinned** -- `meter.ts:28-37`. The "knows every action type" test pins the 12 measured types: moving any of them across classes changes the A/B totals. Moving a pricing-page-only Class A type into `CLASS_B` or `FREE_OPS` (`CopyObject`, `UploadPart`, `CompleteMultipartUpload`, `PutBucketCors`, ...) would under-price silently, and nothing would go red. The account does not use those types today, so the risk is low. A table test of the full pricing-page lists would close it.
3. **A row with no `actionType` is reported as `""`** -- `meter.ts:93`. It prices as Class A, which fails toward the dearer class, so this is correct. But an empty string in `guard.json`'s `evaluation.unknown_action_types` (and in any alert text built from it) is hard for an operator to read. A label such as `"(missing actionType)"` would be clearer.
4. **An empty dataset reads as zero usage** -- `meter.ts:84-86`, `:123`. This is noted honestly in the handback. The main real case is storage `[]` for about 45 min after a period start: storage is under-counted until the first sample lands. The cost is negligible (about 1.4 GB, inside the free tier), and the brief accepts it. Recorded so the whole-branch review knows it is a known behaviour, not an oversight.
5. **`metadataSize ?? 0`** -- `meter.ts:124`. An absent metadataSize counts as 0, while an absent payloadSize throws. The asymmetry is brief-mandated and bounded by metadata bytes (tiny next to payload). Acceptable. A short comment saying why the two differ would stop a later "consistency" edit from going either way blindly.
6. **One test checks five failure modes** -- `meter.test.ts:34-47` (brief-mandated). The first failing `expect` hides the rest. The implementer's added every-field test passes a per-case label as the `expect` message (`expect(() => ..., what)`); the brief's test does not, so a red run names only the first failure.

### ⚠️ Cannot verify from diff
- **Account and API facts.** I could not check from code that the GraphQL schema accepts `limit: 10000` on all three datasets, or that `$account: string!` and the `.000Z` timestamps are accepted. The comment above `USAGE_QUERY` records them as measured on 2026-10-12. That is for Task 17's live check.
- **Whether Workers `requests` matches billable requests** (for example, whether cron invocations are billed) is a pricing/spec question, not a code question. It belongs to the spec seat and Task 2's price table.
- **How the guard (Task 6) consumes a thrown reading** -- recorded as a failed attempt, counting toward blind. This spans tasks. This module's side of that contract is right: every failure path throws.

### Strengths
- **The spend path fails closed throughout.** The following all throw:
  - an HTTP error, a non-JSON body, or GraphQL errors (including partial data alongside errors);
  - an `errors` field that is present but malformed (the implementer's Deviation 1 closes a real gap in the brief's `b.errors.length` check);
  - zero accounts, several accounts, or a non-object account;
  - a missing dataset, or a truncated result (`>=` ROW_LIMIT, fail-closed at exactly the limit);
  - any non-finite, negative or non-numeric count in any field that reaches the `Reading`.
- **Unknown action types price toward the dearer class and are surfaced**, never silently dropped. `FREE_OPS` is checked only after `CLASS_B`, and the three sets do not overlap.
- **The tests verify behaviour, not shape.**
  - Exact class totals.
  - Per-bucket peak summation across two buckets.
  - The window arithmetic (`recentEnd = now - LAG_MS`, a span of exactly `RECENT_MS`).
  - The bearer header, and the `accountTag` filter in the query.
  - An every-field validation test whose cases each carry a label.
  The implementer's reported mutants (sentinel first, predictions named in advance) are a credible check that the new tests can fail.
- No network access: every fetch is injected through `fakeFetch`, which throws on unmatched calls. Committed files contain no account details: the tests use `acct`/`tok`, and the only `@` and hex hits in `git show` are commit metadata.
- The structure is clean and small: `rows`, `count`, `sumRequests` and `r2Counts` each have one job, there is no duplicated logic, and the file follows the brief's layout.

### Checks run
- **Hygiene.** `git show 5a4ebcf | grep -nE '[0-9a-f]{32}|@[a-z]'` matched only the commit hash, the author line and the trailer. No account ID or token appears in the files.
- **Timeout pinned?** I read `test/support.ts` `fakeFetch`/`FetchCall`: `signal` is not recorded, so no test can observe the timeout (Minor 1).
- **Type contract.** In `src/pricing.ts`, `Reading` has `periodToDate`, `recent`, `recentMs` and `unknownActionTypes`. `evaluateSpend` divides by `recentMs` (guarded for values above 0), which matches what `parseUsage` returns (`recentMs: RECENT_MS`).
- **Class-set overlap and precedence.** By reading `meter.ts:28-37` and `:91-99`: no type is in two sets, an unknown type goes to Class A and the report, and a type in `FREE_OPS` is skipped.
- **Error-path coverage.** I traced each throw in `parseUsage`/`readUsage` to a test assertion: errors list, malformed errors, empty accounts, missing storage, non-count values (8 labelled cases), truncation, HTTP 403, and a non-JSON body.
- **Tests not re-run.** The implementer's reported run (7 files, 69 passed, tsc clean) shows no warnings, and nothing I read raised a doubt that a focused run would settle.
