### Task 3: GraphQL usage meter

**Model hint:** opus (spend path)

**Files:**
- Create: `antenna/src/meter.ts`, `antenna/test/meter.test.ts`
- Modify: `antenna/test/support.ts` (append `usageResponse`)

**Interfaces:**
- Consumes: `Period` (Task 1); `OpCounts`, `Reading` (Task 2); `fakeFetch`, `json` (Task 1).
- Produces:
  - `GRAPHQL_URL`, `RECENT_MS` (3 h), `LAG_MS` (5 min), `ROW_LIMIT` (10,000), `CLASS_A`, `CLASS_B`, `FREE_OPS` (Sets of R2 `actionType` strings), `USAGE_QUERY`.
  - `interface MeterCredentials { accountId; token }`, `usageVariables(accountId, period, nowMs)`.
  - `parseUsage(body: unknown): Reading` (throws on GraphQL errors, no account, a missing dataset, a non-count value, or a truncated result).
  - `readUsage(fetchFn, creds, period, nowMs): Promise<Reading>` (POST with a bearer token and a 15 s timeout; throws on HTTP errors or a non-JSON body).
  - `test/support.ts`: `usageResponse({ workers?, workersRecent?, ops?, opsRecent?, buckets? })`, a canned account-scoped response.

Notes for the implementer:

- This reads **account-scoped** datasets (all Workers and all buckets): the spec's account is dedicated to the station, so the meters mean what they say.
- Sampled estimates are fine.
- Storage is the sum over buckets of each bucket's peak in the period. A `max` with no `bucketName` dimension would return one bucket's peak, not the account's.
- One query covers the whole period to date. That is valid: each dataset accepts up to 32 days per query within the last 90 days, and a billing period is at most 31 days (measured 2026-10-12, amendment A5). The comment above `USAGE_QUERY` says so.
- The three Sets cover every `actionType` this account reported over 3 days (measured 2026-10-12, A5). One in none of them is priced as Class A and reported in `guard.json` (`evaluation.unknown_action_types`); Task 17's checklist confirms the list stays empty.

- [ ] **Step 1: Write the failing test**

Append to `antenna/test/support.ts`:

```ts
/** A canned account-scoped response, shaped as the API returns it. */
export function usageResponse(o: { workers?: number; workersRecent?: number; ops?: Record<string, number>;
                                   opsRecent?: Record<string, number>; buckets?: [number, number][] } = {}) {
  const ops = (m: Record<string, number>) =>
    Object.entries(m).map(([actionType, requests]) => ({ sum: { requests }, dimensions: { actionType } }));
  return {
    data: { viewer: { accounts: [{
      workersToDate: [{ sum: { requests: o.workers ?? 40_000 } }],
      workersRecent: [{ sum: { requests: o.workersRecent ?? 180 } }],
      r2ToDate: ops(o.ops ?? { PutObject: 200_000, GetObject: 300_000, DeleteObject: 80_000 }),
      r2Recent: ops(o.opsRecent ?? { PutObject: 3_000, GetObject: 4_000 }),
      storage: (o.buckets ?? [[1.4e9, 2e6]]).map(([payloadSize, metadataSize], i) =>
        ({ max: { payloadSize, metadataSize }, dimensions: { bucketName: `b${i}` } })),
    }] } },
    errors: null,
  };
}
```

`antenna/test/meter.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { GRAPHQL_URL, LAG_MS, parseUsage, readUsage, RECENT_MS, ROW_LIMIT, usageVariables } from "../src/meter";
import { fakeFetch, json, usageResponse } from "./support";

const PERIOD = { startMs: Date.parse("2026-10-11T00:00:00Z"), endMs: Date.parse("2026-11-11T00:00:00Z") };
const NOW = Date.parse("2026-10-20T12:00:00Z");

describe("parseUsage", () => {
  it("sums Workers requests, classes R2 operations and sums per-bucket peak storage", () => {
    const r = parseUsage(usageResponse({ ops: { PutObject: 10, ListObjects: 1, GetObject: 5, HeadObject: 2, DeleteObject: 99 },
                                         buckets: [[1e9, 1e6], [2e9, 0]] }));
    expect(r.periodToDate).toEqual({ workersRequests: 40_000, r2ClassA: 11, r2ClassB: 7 });
    expect(r.recent).toEqual({ workersRequests: 180, r2ClassA: 3_000, r2ClassB: 4_000 });
    expect(r.recentMs).toBe(RECENT_MS);
    expect(r.storageBytes).toBe(3e9 + 1e6);
    expect(r.unknownActionTypes).toEqual([]);
  });

  it("prices an unknown action type as Class A and reports it", () => {
    const r = parseUsage(usageResponse({ ops: { PutObject: 1, SomethingNew: 7 } }));
    expect(r.periodToDate.r2ClassA).toBe(8);
    expect(r.unknownActionTypes).toEqual(["SomethingNew"]);
  });

  it("knows every action type the account reported (measured 2026-10-12)", () => {
    const seen = ["DeleteObject", "GetBucketCors", "GetBucketLifecycleConfiguration", "GetBucketNotificationConfiguration",
                  "GetBucketSippyConfiguration", "GetObject", "HeadBucket", "ListBuckets", "ListMultipartUploads",
                  "ListObjects", "PutBucket", "PutObject"];
    const r = parseUsage(usageResponse({ ops: Object.fromEntries(seen.map((a) => [a, 1])) }));
    expect(r.unknownActionTypes).toEqual([]);
    expect(r.periodToDate).toMatchObject({ r2ClassA: 5, r2ClassB: 6 }); // DeleteObject is free
  });

  it("throws on GraphQL errors, a missing account, a missing dataset, a bad count or a truncated result", () => {
    expect(() => parseUsage({ data: null, errors: [{ message: "not authorized" }] })).toThrow(/not authorized/);
    expect(() => parseUsage({ data: { viewer: { accounts: [] } }, errors: null })).toThrow(/CF_ACCOUNT_ID/);
    const noStorage = usageResponse();
    delete (noStorage.data.viewer.accounts[0] as Record<string, unknown>).storage;
    expect(() => parseUsage(noStorage)).toThrow(/storage missing/);
    const bad = usageResponse();
    bad.data.viewer.accounts[0].workersToDate = [{ sum: { requests: "lots" as unknown as number } }];
    expect(() => parseUsage(bad)).toThrow(/not a count/);
    const truncated = usageResponse();
    truncated.data.viewer.accounts[0].r2ToDate = Array.from({ length: ROW_LIMIT },
      () => ({ sum: { requests: 1 }, dimensions: { actionType: "GetObject" } }));
    expect(() => parseUsage(truncated)).toThrow(/truncated/);
  });
});

describe("readUsage", () => {
  it("POSTs the account-scoped query with the bearer token and the windows", async () => {
    const f = fakeFetch({ [`POST ${GRAPHQL_URL}`]: () => json(usageResponse()) });
    const r = await readUsage(f.fetch, { accountId: "acct", token: "tok" }, PERIOD, NOW);
    expect(r.periodToDate.r2ClassA).toBe(200_000);
    expect(f.calls).toHaveLength(1);
    expect(f.calls[0].headers.authorization).toBe("Bearer tok");
    const sent = JSON.parse(f.calls[0].body!);
    expect(sent.variables).toEqual(usageVariables("acct", PERIOD, NOW));
    expect(sent.variables.start).toBe("2026-10-11T00:00:00.000Z");
    expect(Date.parse(sent.variables.recentEnd)).toBe(NOW - LAG_MS);
    expect(Date.parse(sent.variables.recentEnd) - Date.parse(sent.variables.recentStart)).toBe(RECENT_MS);
    expect(sent.query).toContain("accountTag: $account");
  });

  it("throws on an HTTP error or a non-JSON body", async () => {
    const e403 = fakeFetch({ "POST ": () => new Response("forbidden", { status: 403 }) });
    await expect(readUsage(e403.fetch, { accountId: "a", token: "t" }, PERIOD, NOW)).rejects.toThrow(/HTTP 403/);
    const html = fakeFetch({ "POST ": () => new Response("<html>", { status: 200 }) });
    await expect(readUsage(html.fetch, { accountId: "a", token: "t" }, PERIOD, NOW)).rejects.toThrow(/not JSON/);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/meter.test.ts`
Expected: FAIL. `../src/meter` cannot be resolved.

- [ ] **Step 3: Implement**

`antenna/src/meter.ts`:

```ts
/** Usage read from Cloudflare's GraphQL Analytics API, account-scoped (all
 * Workers and buckets), with an Account Analytics: Read token. The adaptive
 * datasets are sampled estimates; operations lag ~1-2 min and storage ~45 min
 * (measured 2026-10-11), so the recent window ends LAG_MS before now. Any
 * failure -- HTTP, GraphQL errors, a missing account, a truncated result --
 * throws: the guard counts it as a failed reading. */

import type { Period } from "./period";
import type { OpCounts, Reading } from "./pricing";

export const GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql";
export const RECENT_MS = 3 * 3_600_000;
export const LAG_MS = 5 * 60_000;
export const ROW_LIMIT = 10_000;
const TIMEOUT_MS = 15_000;

/** R2 operation classes (R2 pricing page). Free operations are not billed; an
 * actionType in no list is priced as Class A, the dearer class, and reported.
 * Every actionType this account reported over 3 days is listed (measured
 * 2026-10-12). */
export const CLASS_A = new Set([
  "ListBuckets", "PutBucket", "ListObjects", "PutObject", "CopyObject", "CompleteMultipartUpload",
  "CreateMultipartUpload", "LifecycleStorageTierTransition", "ListMultipartUploads", "UploadPart",
  "UploadPartCopy", "ListParts", "PutBucketEncryption", "PutBucketCors", "PutBucketLifecycleConfiguration",
]);
export const CLASS_B = new Set([
  "HeadBucket", "HeadObject", "GetObject", "UsageSummary", "GetBucketEncryption", "GetBucketLocation",
  "GetBucketCors", "GetBucketLifecycleConfiguration", "GetBucketNotificationConfiguration", "GetBucketSippyConfiguration",
]);
export const FREE_OPS = new Set(["DeleteObject", "DeleteBucket", "AbortMultipartUpload"]);

/** One query covers the whole period to date. Each dataset accepts a range of up
 * to 32 days (maxDuration 2,764,800 s) within the last 90 days (notOlderThan
 * 7,776,000 s), and a billing period is at most 31 days. Measured for this
 * account 2026-10-12, when this exact query (`.000Z` timestamps, `$account:
 * string!`) succeeded over 31- and 32-day ranges. */
export const USAGE_QUERY = `query StationUsage($account: string!, $start: Time!, $now: Time!, $recentStart: Time!, $recentEnd: Time!) {
  viewer {
    accounts(filter: { accountTag: $account }) {
      workersToDate: workersInvocationsAdaptive(limit: ${ROW_LIMIT}, filter: { datetime_geq: $start, datetime_leq: $now }) { sum { requests } }
      workersRecent: workersInvocationsAdaptive(limit: ${ROW_LIMIT}, filter: { datetime_geq: $recentStart, datetime_leq: $recentEnd }) { sum { requests } }
      r2ToDate: r2OperationsAdaptiveGroups(limit: ${ROW_LIMIT}, filter: { datetime_geq: $start, datetime_leq: $now }) { sum { requests } dimensions { actionType } }
      r2Recent: r2OperationsAdaptiveGroups(limit: ${ROW_LIMIT}, filter: { datetime_geq: $recentStart, datetime_leq: $recentEnd }) { sum { requests } dimensions { actionType } }
      storage: r2StorageAdaptiveGroups(limit: ${ROW_LIMIT}, filter: { datetime_geq: $start, datetime_leq: $now }) { max { payloadSize metadataSize } dimensions { bucketName } }
    }
  }
}`;

export interface MeterCredentials {
  accountId: string;
  token: string;
}

export function usageVariables(accountId: string, period: Period, nowMs: number) {
  const iso = (ms: number) => new Date(ms).toISOString();
  const recentEnd = nowMs - LAG_MS;
  return { account: accountId, start: iso(period.startMs), now: iso(nowMs),
           recentStart: iso(recentEnd - RECENT_MS), recentEnd: iso(recentEnd) };
}

type Rows = { sum?: { requests?: unknown }; max?: Record<string, unknown>; dimensions?: Record<string, unknown> }[];

function rows(acct: Record<string, unknown>, name: string): Rows {
  const r = acct[name];
  if (!Array.isArray(r)) throw new Error(`analytics: ${name} missing from the response`);
  if (r.length >= ROW_LIMIT) throw new Error(`analytics: ${name} returned ${r.length} rows (truncated)`);
  return r as Rows;
}

function count(v: unknown, what: string): number {
  if (typeof v !== "number" || !Number.isFinite(v) || v < 0) throw new Error(`analytics: ${what} is not a count: ${JSON.stringify(v)}`);
  return v;
}

function sumRequests(rs: Rows, what: string): number {
  return rs.reduce((t, r) => t + count(r.sum?.requests, what), 0);
}

function r2Counts(rs: Rows, unknown: Set<string>): Pick<OpCounts, "r2ClassA" | "r2ClassB"> {
  let r2ClassA = 0;
  let r2ClassB = 0;
  for (const r of rs) {
    const action = String(r.dimensions?.actionType ?? "");
    const n = count(r.sum?.requests, `r2 ${action} requests`);
    if (CLASS_B.has(action)) r2ClassB += n;
    else if (FREE_OPS.has(action)) continue;
    else {
      if (!CLASS_A.has(action)) unknown.add(action);
      r2ClassA += n;
    }
  }
  return { r2ClassA, r2ClassB };
}

/** Parse a GraphQL response body into a Reading (throws on anything unexpected). */
export function parseUsage(body: unknown): Reading {
  const b = body as { data?: { viewer?: { accounts?: unknown[] } }; errors?: { message?: string }[] | null };
  if (b?.errors && b.errors.length > 0) {
    throw new Error(`analytics: ${b.errors.map((e) => e?.message ?? "error").join("; ")}`);
  }
  const accounts = b?.data?.viewer?.accounts;
  if (!Array.isArray(accounts) || accounts.length !== 1) {
    throw new Error("analytics: no account in the response (check CF_ACCOUNT_ID and the token's account scope)");
  }
  const acct = accounts[0] as Record<string, unknown>;
  const unknown = new Set<string>();
  const periodToDate = { workersRequests: sumRequests(rows(acct, "workersToDate"), "workers requests"),
                         ...r2Counts(rows(acct, "r2ToDate"), unknown) };
  const recent = { workersRequests: sumRequests(rows(acct, "workersRecent"), "workers requests"),
                   ...r2Counts(rows(acct, "r2Recent"), unknown) };
  const storageBytes = rows(acct, "storage").reduce(
    (t, r) => t + count(r.max?.payloadSize, "payloadSize") + count(r.max?.metadataSize ?? 0, "metadataSize"), 0);
  return { periodToDate, recent, recentMs: RECENT_MS, storageBytes, unknownActionTypes: [...unknown].sort() };
}

export async function readUsage(fetchFn: typeof fetch, creds: MeterCredentials, period: Period,
                                nowMs: number): Promise<Reading> {
  const res = await fetchFn(GRAPHQL_URL, {
    method: "POST",
    headers: { authorization: `Bearer ${creds.token}`, "content-type": "application/json" },
    body: JSON.stringify({ query: USAGE_QUERY, variables: usageVariables(creds.accountId, period, nowMs) }),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`analytics: HTTP ${res.status}: ${text.slice(0, 200)}`);
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    throw new Error(`analytics: response is not JSON: ${text.slice(0, 200)}`);
  }
  return parseUsage(body);
}
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npx vitest run && npx tsc --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/meter.ts antenna/test/meter.test.ts antenna/test/support.ts
git commit -m "feat(antenna): account-scoped GraphQL usage meter (Workers requests, R2 classes, storage)"
```

---

