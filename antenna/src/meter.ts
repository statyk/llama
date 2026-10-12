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
  return rs.reduce((t, r) => t + count(r?.sum?.requests, what), 0);
}

function r2Counts(rs: Rows, unknown: Set<string>): Pick<OpCounts, "r2ClassA" | "r2ClassB"> {
  let r2ClassA = 0;
  let r2ClassB = 0;
  for (const r of rs) {
    const action = String(r?.dimensions?.actionType ?? "");
    const n = count(r?.sum?.requests, `r2 ${action} requests`);
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
  const b = body as { data?: { viewer?: { accounts?: unknown[] } }; errors?: unknown };
  // GraphQL reports errors as a list; anything else that is present (a non-empty
  // list, or a malformed non-list) is a failed reading, never ignored.
  if (b?.errors != null && !(Array.isArray(b.errors) && b.errors.length === 0)) {
    const errs = Array.isArray(b.errors) ? b.errors : [b.errors];
    throw new Error(`analytics: ${errs.map((e) => (e as { message?: string })?.message ?? JSON.stringify(e)).join("; ")}`);
  }
  const accounts = b?.data?.viewer?.accounts;
  if (!Array.isArray(accounts) || accounts.length !== 1 || typeof accounts[0] !== "object" || accounts[0] === null) {
    throw new Error("analytics: no account in the response (check CF_ACCOUNT_ID and the token's account scope)");
  }
  const acct = accounts[0] as Record<string, unknown>;
  const unknown = new Set<string>();
  const periodToDate = { workersRequests: sumRequests(rows(acct, "workersToDate"), "workers requests"),
                         ...r2Counts(rows(acct, "r2ToDate"), unknown) };
  const recent = { workersRequests: sumRequests(rows(acct, "workersRecent"), "workers requests"),
                   ...r2Counts(rows(acct, "r2Recent"), unknown) };
  const storageBytes = rows(acct, "storage").reduce(
    (t, r) => t + count(r?.max?.payloadSize, "payloadSize") + count(r?.max?.metadataSize ?? 0, "metadataSize"), 0);
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
