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
