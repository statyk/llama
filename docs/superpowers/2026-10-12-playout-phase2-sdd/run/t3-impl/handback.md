# t3-impl handback — Task 3: GraphQL usage meter

Status: DONE
Commit: 5a4ebcf feat(antenna): account-scoped GraphQL usage meter (Workers requests, R2 classes, storage)
Tests: `cd antenna && npm test && npx tsc --noEmit` -> 7 files, 69 passed (61 before + 8 new); tsc clean.

## Implemented
- `antenna/src/meter.ts` (new): GRAPHQL_URL, RECENT_MS (3 h), LAG_MS (5 min), ROW_LIMIT (10,000), CLASS_A/CLASS_B/FREE_OPS,
  USAGE_QUERY (with the A5 32-day/90-day comment), MeterCredentials, usageVariables, parseUsage, readUsage
  (POST, bearer token, 15 s AbortSignal.timeout; throws on HTTP error / non-JSON). Brief code verbatim except the deviations below.
- `antenna/test/meter.test.ts` (new): the brief's 6 tests verbatim + 2 added (below).
- `antenna/test/support.ts`: appended `usageResponse` verbatim.

## Deviations from the brief
1. **Malformed `errors` field fails the reading.** Brief: `if (b?.errors && b.errors.length > 0)` — a present but
   non-list `errors` (e.g. an object) has no `.length`, so it was ignored and a reading accepted. Now any `errors`
   that is not null/absent and not an empty list throws (message from `.message`, else JSON). Test: "treats a
   malformed (non-list) errors field as a failed reading, not as no errors" (also asserts `errors: []` is accepted).
2. **Null-safe row access** (`r?.sum`, `r?.max`, `r?.dimensions`) and the account check also requires
   `accounts[0]` to be a non-null object, so a null row/account gives a clear analytics error (not-a-count /
   CF_ACCOUNT_ID) instead of a bare TypeError. Both threw before; this only improves the message.
3. **Added test** "rejects a missing, negative or non-finite value in every field that reaches the Reading":
   covers workersToDate (-1), workersRecent (Infinity), r2ToDate (NaN), r2Recent (missing sum), payloadSize
   (-5, missing), metadataSize (NaN), and a missing `max`. The brief's `count()` already validated every field
   (each op count and both storage components), so no code change was needed for the mandate; the test pins it.

## TDD evidence
- RED: `cd antenna && npx vitest run test/meter.test.ts` -> FAIL "Cannot find module '../src/meter'" (no tests).
- GREEN: same command -> 6 passed (brief tests), then 8 passed with the added tests.
- Full: `npm test && npx tsc --noEmit` -> Test Files 7 passed, Tests 69 passed; TSC-CLEAN.

## Mutation check (scratch copy via tar, node_modules symlinked; predictions named before running; all matched)
- sentinel (drop HeadObject from CLASS_B) -> "sums Workers requests..." fails (proves the copy is what runs).
- M1 brief's errors check restored -> only the malformed-errors test fails.
- M2 drop `v < 0`, M3 drop `Number.isFinite`, M4 metadataSize unchecked -> each fails the every-field test.
- M5 truncation `>=` -> `>` -> "throws on GraphQL errors, ... truncated result" fails.

## Self-review / concerns
- `metadataSize ?? 0` (brief design, kept): an absent/null metadataSize counts 0. A non-null bad value is
  rejected. Under-count bounded by metadata bytes (tiny vs payload); flagging only for the reviewer's call.
- An EMPTY dataset array reads as zero usage (e.g. storage `[]` during the ~45 min storage lag at a period start,
  or a dataset that silently returns nothing). Indistinguishable from genuine zero at this layer; the brief
  accepts it. Not a malformed response, so not rejected.
- A row with no actionType is priced Class A and reported as `""` in unknownActionTypes (fails toward dearer).
- No network, no account details in committed files; the test uses "acct"/"tok" placeholders.
