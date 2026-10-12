import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { createJson, putJson, r2Bucket, readJsonDoc } from "../src/bucket";
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

  it("a corrupt read carries the stored etag, so a conditional overwrite of it is possible", async () => {
    const b = new MemoryBucket();
    b.seed("k", "{nope");
    const etag = b.objects.get("k")!.etag;
    const r = await readJsonDoc(b, "k");
    expect(r).toEqual({ kind: "corrupt", error: expect.any(String), etag });
    expect(await putJson(b, "k", { fixed: true }, etag)).toBe(true);
    expect(b.json("k")).toEqual({ fixed: true });
  });

  it("createJson writes only when the key is absent", async () => {
    const b = new MemoryBucket();
    expect(await createJson(b, "k", { v: 1 })).toBe(true);
    expect(await createJson(b, "k", { v: 2 })).toBe(false);
    expect(b.json("k")).toEqual({ v: 1 });
    expect(b.objects.get("k")!.cacheControl).toBe("no-store");
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
    // Create-only (etagDoesNotMatch "*"): refused over an existing key, honoured on an absent one.
    expect(await createJson(b, "state/test.json", { v: 4 })).toBe(false);
    expect(await (await env.BUCKET.get("state/test.json"))!.json()).toEqual({ v: 2 });
    expect(await createJson(b, "state/new.json", { v: 1 })).toBe(true);
    expect(await createJson(b, "state/new.json", { v: 2 })).toBe(false);
    expect(await (await env.BUCKET.get("state/new.json"))!.json()).toEqual({ v: 1 });
    await b.put("h", "x", { httpMetadata: { contentType: "text/plain", cacheControl: "no-store" }, customMetadata: { a: "1" } });
    expect((await b.head("h"))!.customMetadata).toEqual({ a: "1" });
    expect(await b.head("missing")).toBeNull();
  });
});
