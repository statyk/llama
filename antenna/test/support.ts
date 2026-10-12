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
