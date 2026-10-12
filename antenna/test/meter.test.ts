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

  it("rejects a missing, negative or non-finite value in every field that reaches the Reading", () => {
    type Acct = Record<string, { sum?: { requests: unknown }; max?: Record<string, unknown> }[]>;
    const cases: [string, (a: Acct) => void][] = [
      ["workersToDate", (a) => { a.workersToDate[0].sum!.requests = -1; }],
      ["workersRecent", (a) => { a.workersRecent[0].sum!.requests = Infinity; }],
      ["r2ToDate", (a) => { a.r2ToDate[0].sum!.requests = NaN; }],
      ["r2Recent", (a) => { delete a.r2Recent[0].sum; }],
      ["storage payloadSize", (a) => { a.storage[0].max!.payloadSize = -5; }],
      ["storage payloadSize missing", (a) => { delete a.storage[0].max!.payloadSize; }],
      ["storage metadataSize", (a) => { a.storage[0].max!.metadataSize = NaN; }],
      ["storage max missing", (a) => { delete a.storage[0].max; }],
    ];
    for (const [what, mutate] of cases) {
      const r = usageResponse();
      mutate(r.data.viewer.accounts[0] as unknown as Acct);
      expect(() => parseUsage(r), what).toThrow(/not a count/);
    }
  });

  it("treats a malformed (non-list) errors field as a failed reading, not as no errors", () => {
    const r = { ...usageResponse(), errors: { message: "rate limited" } };
    expect(() => parseUsage(r)).toThrow(/rate limited/);
    expect(() => parseUsage({ ...usageResponse(), errors: [] })).not.toThrow();
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
