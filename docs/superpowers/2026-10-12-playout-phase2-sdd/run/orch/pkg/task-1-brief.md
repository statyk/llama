### Task 1: antenna storage seam, test support, billing period

**Model hint:** sonnet

**Files:**
- Create: `antenna/src/bucket.ts`, `antenna/src/period.ts`
- Create: `antenna/test/support.ts`, `antenna/test/bucket.test.ts`, `antenna/test/period.test.ts`
- Modify: `antenna/src/clock.ts` (the bucket types move to `bucket.ts`), `antenna/test/clock.test.ts` (uses `test/support.ts`)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `bucket.ts`: `interface StoredObject { text(); etag? }`, `interface ObjectInfo { etag; customMetadata? }`, `interface PutOptions { httpMetadata: {contentType, cacheControl}; customMetadata?; onlyIf?: { etagMatches } }`, `interface BucketLike { get; head; put }` (put resolves to `null` when `onlyIf` fails), `r2Bucket(b: R2Bucket): BucketLike`, `type JsonRead<T> = {kind:"absent"} | {kind:"ok"; value; etag?} | {kind:"corrupt"; error; etag?}`, `readJsonDoc<T>(bucket, key): Promise<JsonRead<T>>` (a read error propagates), `STATE_HTTP = { contentType: "application/json", cacheControl: "no-store" }`, `putJson(bucket, key, value, etag?): Promise<boolean>` (false = precondition failed).
  - `period.ts`: `interface Period { startMs; endMs }`, `billingPeriod(nowMs, day): Period` (throws for a day outside 1..31).
  - `test/support.ts`: `class MemoryBucket implements BucketLike` (`objects`, `log` of `"get k"`/`"head k"`/`"put k"`, `failGets`, `failPuts`, `seed(key, value)`, `json(key)`, `puts(key?)`), `fakeTime(start) -> { now, sleep }`, `interface FetchCall`, `type Route`, `fakeFetch(routes) -> { fetch, calls }` (routes keyed by the prefix of `"METHOD url"`; unmatched calls throw), `json(value, status?) -> Response`.
  - `clock.ts` re-exports `BucketLike`, `StoredObject`, `r2Bucket` from `bucket.ts`, so existing imports keep working.

- [ ] **Step 1: Write the failing tests**

`antenna/test/support.ts` (shared by every later antenna test):

```ts
import type { BucketLike, ObjectInfo, PutOptions } from "../src/bucket";

export interface MemoryObject {
  body: string;
  etag: string;
  contentType?: string;
  cacheControl?: string;
  customMetadata?: Record<string, string>;
}

/** In-memory BucketLike with etags and conditional puts. `log` records every
 * call ("get k", "head k", "put k"); `failGets`/`failPuts` make calls throw. */
export class MemoryBucket implements BucketLike {
  objects = new Map<string, MemoryObject>();
  log: string[] = [];
  failGets = new Set<string>();
  failPuts = new Set<string>();
  private n = 0;

  async get(key: string) {
    this.log.push(`get ${key}`);
    if (this.failGets.has(key)) throw new Error(`injected get failure: ${key}`);
    const o = this.objects.get(key);
    return o ? { text: async () => o.body, etag: o.etag } : null;
  }

  async head(key: string): Promise<ObjectInfo | null> {
    this.log.push(`head ${key}`);
    if (this.failGets.has(key)) throw new Error(`injected head failure: ${key}`);
    const o = this.objects.get(key);
    return o ? { etag: o.etag, customMetadata: o.customMetadata } : null;
  }

  async put(key: string, value: string, options: PutOptions) {
    this.log.push(`put ${key}`);
    if (this.failPuts.has(key)) throw new Error(`injected put failure: ${key}`);
    const cur = this.objects.get(key);
    if (options.onlyIf && cur?.etag !== options.onlyIf.etagMatches) return null;
    const etag = `etag-${++this.n}`;
    this.objects.set(key, { body: value, etag, ...options.httpMetadata, customMetadata: options.customMetadata });
    return { etag };
  }

  seed(key: string, value: unknown) {
    this.objects.set(key, { body: typeof value === "string" ? value : JSON.stringify(value), etag: `seed-${++this.n}` });
  }

  json(key: string): any {
    return JSON.parse(this.objects.get(key)!.body);
  }

  puts(key?: string): number {
    return this.log.filter((l) => (key ? l === `put ${key}` : l.startsWith("put "))).length;
  }
}

export function fakeTime(start: number) {
  let t = start;
  return { now: () => t, sleep: async (ms: number) => { t += ms; } };
}

export interface FetchCall {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string | null;
}

export type Route = (call: FetchCall) => Response | Promise<Response>;

/** A fetch stand-in: each call goes to the first route whose prefix matches
 * `METHOD url`; an unmatched call throws (no test may reach the network). */
export function fakeFetch(routes: Record<string, Route>) {
  const calls: FetchCall[] = [];
  const fn = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    const headers: Record<string, string> = {};
    new Headers(init?.headers).forEach((v, k) => { headers[k] = v; });
    const call = { url, method, headers, body: typeof init?.body === "string" ? init.body : null };
    calls.push(call);
    for (const [prefix, route] of Object.entries(routes)) {
      if (`${method} ${url}`.startsWith(prefix)) return route(call);
    }
    throw new Error(`unexpected fetch: ${method} ${url}`);
  };
  return { fetch: fn as typeof fetch, calls };
}

export const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } });
```

`antenna/test/bucket.test.ts`:

```ts
import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { putJson, r2Bucket, readJsonDoc } from "../src/bucket";
import { MemoryBucket } from "./support";

describe("readJsonDoc / putJson", () => {
  it("distinguishes absent, parsed and corrupt objects", async () => {
    const b = new MemoryBucket();
    expect(await readJsonDoc(b, "k")).toEqual({ kind: "absent" });
    b.seed("k", { a: 1 });
    expect(await readJsonDoc(b, "k")).toMatchObject({ kind: "ok", value: { a: 1 } });
    b.seed("k", "{nope");
    expect(await readJsonDoc(b, "k")).toMatchObject({ kind: "corrupt" });
  });

  it("propagates a read error rather than calling it absent", async () => {
    const b = new MemoryBucket();
    b.failGets.add("k");
    await expect(readJsonDoc(b, "k")).rejects.toThrow(/injected/);
  });

  it("a conditional put over a stale etag writes nothing and reports it", async () => {
    const b = new MemoryBucket();
    expect(await putJson(b, "k", { v: 1 })).toBe(true);
    const first = await readJsonDoc(b, "k");
    expect(await putJson(b, "k", { v: 2 }, first.kind === "ok" ? first.etag : undefined)).toBe(true);
    expect(await putJson(b, "k", { v: 3 }, first.kind === "ok" ? first.etag : undefined)).toBe(false);
    expect(b.json("k")).toEqual({ v: 2 });
    expect(b.objects.get("k")!.cacheControl).toBe("no-store");
  });

  it("the R2 binding honours the same contract (etag, conditional put, head metadata)", async () => {
    const b = r2Bucket(env.BUCKET);
    expect(await putJson(b, "state/test.json", { v: 1 })).toBe(true);
    const r = await readJsonDoc(b, "state/test.json");
    expect(r.kind).toBe("ok");
    const etag = r.kind === "ok" ? r.etag : undefined;
    expect(typeof etag).toBe("string");
    expect(await putJson(b, "state/test.json", { v: 2 }, etag)).toBe(true);
    expect(await putJson(b, "state/test.json", { v: 3 }, etag)).toBe(false);
    expect(await (await env.BUCKET.get("state/test.json"))!.json()).toEqual({ v: 2 });
    await b.put("h", "x", { httpMetadata: { contentType: "text/plain", cacheControl: "no-store" }, customMetadata: { a: "1" } });
    expect((await b.head("h"))!.customMetadata).toEqual({ a: "1" });
    expect(await b.head("missing")).toBeNull();
  });
});
```

`antenna/test/period.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { billingPeriod } from "../src/period";

const iso = (ms: number) => new Date(ms).toISOString();
const at = (s: string) => Date.parse(s);

describe("billingPeriod", () => {
  it("runs from the anniversary day at 00:00 UTC to the next", () => {
    const p = billingPeriod(at("2026-10-20T15:00:00Z"), 11);
    expect(iso(p.startMs)).toBe("2026-10-11T00:00:00.000Z");
    expect(iso(p.endMs)).toBe("2026-11-11T00:00:00.000Z");
  });

  it("before the anniversary in a month belongs to the previous period", () => {
    const p = billingPeriod(at("2026-10-10T23:59:59Z"), 11);
    expect(iso(p.startMs)).toBe("2026-09-11T00:00:00.000Z");
    expect(iso(p.endMs)).toBe("2026-10-11T00:00:00.000Z");
  });

  it("the anniversary instant itself starts the new period", () => {
    const p = billingPeriod(at("2026-10-11T00:00:00Z"), 11);
    expect(iso(p.startMs)).toBe("2026-10-11T00:00:00.000Z");
  });

  it("crosses the year", () => {
    const p = billingPeriod(at("2027-01-05T00:00:00Z"), 11);
    expect(iso(p.startMs)).toBe("2026-12-11T00:00:00.000Z");
    expect(iso(p.endMs)).toBe("2027-01-11T00:00:00.000Z");
  });

  it("clamps day 31 to the last day of shorter months", () => {
    const p = billingPeriod(at("2027-02-15T00:00:00Z"), 31);
    expect(iso(p.startMs)).toBe("2027-01-31T00:00:00.000Z");
    expect(iso(p.endMs)).toBe("2027-02-28T00:00:00.000Z");
    expect(iso(billingPeriod(at("2027-03-01T00:00:00Z"), 31).startMs)).toBe("2027-02-28T00:00:00.000Z");
  });

  it("refuses a day outside 1..31", () => {
    for (const d of [0, 32, 1.5, Number.NaN]) expect(() => billingPeriod(Date.now(), d)).toThrow(/1\.\.31/);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/bucket.test.ts test/period.test.ts`
Expected: FAIL. The imports `../src/bucket` and `../src/period` cannot be resolved.

- [ ] **Step 3: Implement**

`antenna/src/bucket.ts`:

```ts
/** The R2 surface the clock and the guard use, narrowed so tests can supply an
 * in-memory bucket. Conditional puts are how two overlapping invocations avoid
 * overwriting each other's guard state (spec "Cost guard"). */

export interface StoredObject {
  text(): Promise<string>;
  etag?: string;
}

export interface ObjectInfo {
  etag: string;
  customMetadata?: Record<string, string>;
}

export interface PutOptions {
  httpMetadata: { contentType: string; cacheControl: string };
  customMetadata?: Record<string, string>;
  /** Write only if the stored object still has this etag. */
  onlyIf?: { etagMatches: string };
}

export interface BucketLike {
  get(key: string): Promise<StoredObject | null>;
  head(key: string): Promise<ObjectInfo | null>;
  /** Resolves to null when an onlyIf precondition failed (nothing was written). */
  put(key: string, value: string, options: PutOptions): Promise<unknown>;
}

export function r2Bucket(b: R2Bucket): BucketLike {
  return {
    get: (key) => b.get(key),
    head: (key) => b.head(key),
    put: (key, value, options) => b.put(key, value, options),
  };
}

export type JsonRead<T> =
  | { kind: "absent" }
  | { kind: "ok"; value: T; etag?: string }
  | { kind: "corrupt"; error: string; etag?: string };

/** Read and parse a JSON object. A read error (R2 unreachable) propagates: the
 * caller decides; unparseable bytes are reported as "corrupt", never as absent. */
export async function readJsonDoc<T = unknown>(bucket: BucketLike, key: string): Promise<JsonRead<T>> {
  const obj = await bucket.get(key);
  if (obj === null) return { kind: "absent" };
  const text = await obj.text();
  try {
    return { kind: "ok", value: JSON.parse(text) as T, etag: obj.etag };
  } catch (e) {
    return { kind: "corrupt", error: e instanceof Error ? e.message : String(e), etag: obj.etag };
  }
}

export const STATE_HTTP = { contentType: "application/json", cacheControl: "no-store" };

/** PUT a state document; with `etag`, only over that version. False = precondition failed. */
export async function putJson(bucket: BucketLike, key: string, value: unknown, etag?: string): Promise<boolean> {
  const result = await bucket.put(key, JSON.stringify(value) + "\n", {
    httpMetadata: STATE_HTTP,
    ...(etag ? { onlyIf: { etagMatches: etag } } : {}),
  });
  return result !== null;
}
```

`antenna/src/period.ts`:

```ts
/** Cloudflare billing periods are anniversary-based (UTC), not calendar months
 * (spec "Platform facts"). The anniversary day comes from the Billing page. */

export interface Period {
  startMs: number;
  endMs: number;
}

/** Midnight UTC on `day` of the month; a month without that day uses its last day. */
function anniversary(year: number, month: number, day: number): number {
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return Date.UTC(year, month, Math.min(day, lastDay));
}

export function billingPeriod(nowMs: number, day: number): Period {
  if (!Number.isInteger(day) || day < 1 || day > 31) {
    throw new Error(`billing anniversary day must be an integer 1..31, not ${day}`);
  }
  const now = new Date(nowMs);
  let year = now.getUTCFullYear();
  let month = now.getUTCMonth();
  let startMs = anniversary(year, month, day);
  if (startMs > nowMs) {
    month -= 1;
    if (month < 0) {
      month = 11;
      year -= 1;
    }
    startMs = anniversary(year, month, day);
  }
  const endMs = month === 11 ? anniversary(year + 1, 0, day) : anniversary(year, month + 1, day);
  return { startMs, endMs };
}
```

In `antenna/src/clock.ts`, replace the head of the file, from the first import through the closing brace of `r2Bucket`:

```ts
import { type Horizon, gridOf, indexAt, startMs } from "./grid";
import { buildPlaylist, type FallbackIndex, isOffair, type PlaylistConfig, usableFallback } from "./playlist";

export interface StoredObject {
  text(): Promise<string>;
}

export interface BucketLike {
  get(key: string): Promise<StoredObject | null>;
  put(key: string, value: string, options: { httpMetadata: { contentType: string; cacheControl: string } }): Promise<unknown>;
}

export function r2Bucket(b: R2Bucket): BucketLike {
  return {
    get: (key) => b.get(key),
    put: (key, value, options) => b.put(key, value, options),
  };
}
```

with:

```ts
import type { BucketLike } from "./bucket";
import { type Horizon, gridOf, indexAt, startMs } from "./grid";
import { buildPlaylist, type FallbackIndex, isOffair, type PlaylistConfig, usableFallback } from "./playlist";

export { type BucketLike, r2Bucket, type StoredObject } from "./bucket";
```

In `antenna/test/clock.test.ts`, make three edits:

1. Delete the local `class MemoryBucket implements BucketLike { … }` and the local `function fakeTime(start: number) { … }`.
2. Change the clock import line to `import { type ClockConfig, configFromEnv, MAX_PUTS, putCap, r2Bucket, runClock } from "../src/clock";`.
3. Add `import { fakeTime, MemoryBucket } from "./support";` after `import worker from "../src/index";`.

Nothing else in that file changes in this task.

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npx vitest run && npx tsc --noEmit`
Expected: PASS (5 files: the three existing ones plus `bucket` and `period`); no type errors. `bucket.test.ts`'s last test also proves that the R2 binding in the Workers runtime honours `onlyIf: { etagMatches }`, returning `null` for a stale etag.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/bucket.ts antenna/src/period.ts antenna/src/clock.ts antenna/test/support.ts antenna/test/bucket.test.ts antenna/test/period.test.ts antenna/test/clock.test.ts
git commit -m "feat(antenna): storage seam with etags and conditional puts; billing period; shared test support"
```

---

