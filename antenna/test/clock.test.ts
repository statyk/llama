import { createExecutionContext, createScheduledController, env, waitOnExecutionContext } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type BucketLike, type ClockConfig, configFromEnv, MAX_PUTS, putCap, r2Bucket, runClock } from "../src/clock";
import worker from "../src/index";

const E = Date.parse("2026-10-10T12:00:00.000Z");
const D = 10_240;
const CFG: ClockConfig = { window: 6, grace: 3, offairAfterMs: 86_400_000, loopMs: 75_000, liveMaxAge: 5 };

class MemoryBucket implements BucketLike {
  objects = new Map<string, { body: string; contentType?: string; cacheControl?: string }>();
  log: string[] = [];
  async get(key: string) {
    this.log.push(`get ${key}`);
    const o = this.objects.get(key);
    return o ? { text: async () => o.body } : null;
  }
  async put(key: string, value: string, options: { httpMetadata: { contentType: string; cacheControl: string } }) {
    this.log.push(`put ${key}`);
    this.objects.set(key, { body: value, ...options.httpMetadata });
    return null;
  }
  seed(key: string, value: unknown) {
    this.objects.set(key, { body: JSON.stringify(value) });
  }
}

function horizonDoc(epochMs: number, first = 0, last = 1_000_000) {
  const iso = new Date(epochMs).toISOString();
  return { epoch_id: "e1", epoch: iso, d: 10.24, first, last, published_at: iso, container: "adts", fallback_version: "v1" };
}
const FALLBACK = { len: 7, notice: "fallback/v1/notice.aac", d: 10.24 };

function station(bucket: MemoryBucket, offair = false) {
  bucket.seed("state/horizon.json", horizonDoc(E));
  bucket.seed("fallback/v1/index.json", FALLBACK);
  if (offair) bucket.seed("state/offair.json", { offair: true, reason: "test", since: null, until: null });
}

function fakeTime(start: number) {
  let t = start;
  return { now: () => t, sleep: async (ms: number) => { t += ms; } };
}

const playlistPuts = (b: MemoryBucket) => b.log.filter((l) => l === "put live.m3u8").length;

afterEach(() => {
  vi.restoreAllMocks();
});

describe("runClock", () => {
  it("writes immediately, then at every grid boundary until fire + 75 s", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const scheduledTime = E + 50 * D + 300;
    const clock = fakeTime(scheduledTime + 40);
    const r = await runClock({ bucket, ...clock, scheduledTime, config: CFG });
    expect(r.puts).toBe(8); // immediate + boundaries 51..57; 58 starts after fire + 75 s
    expect(playlistPuts(bucket)).toBe(8);
    expect(clock.now()).toBeLessThanOrEqual(scheduledTime + CFG.loopMs);
    expect(bucket.objects.get("live.m3u8")!.body).toContain("seg/e1/57.aac");
  });

  it("never exceeds ceil(75/d) + 2 PUTs, even with a skewed fire time", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const clock = fakeTime(E + 100 * D);
    const r = await runClock({ bucket, ...clock, scheduledTime: E + 100 * D + 600_000, config: CFG });
    expect(putCap(CFG, D)).toBe(10);
    expect(r.puts).toBe(10);
  });

  it("skips bytes identical to the last write (off-air: one PUT per invocation)", async () => {
    const bucket = new MemoryBucket();
    station(bucket, true);
    const scheduledTime = E + 50 * D + 300;
    const r = await runClock({ bucket, ...fakeTime(scheduledTime + 40), scheduledTime, config: CFG });
    expect(r.puts).toBe(1);
    expect(r.skipped).toBe(7);
    expect(bucket.objects.get("live.m3u8")!.body).toContain("#EXT-X-ENDLIST");
  });

  it("runs the guard step before reading anything", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const seen: string[] = [];
    await runClock({
      bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: { ...CFG, loopMs: 0 },
      guard: async () => { seen.push("guard", ...bucket.log); },
    });
    expect(seen).toEqual(["guard"]);
    expect(bucket.log[0]).toBe("get state/horizon.json");
  });

  it("writes nothing without a horizon", async () => {
    const bucket = new MemoryBucket();
    const r = await runClock({ bucket, ...fakeTime(E), scheduledTime: E, config: CFG });
    expect(r.puts).toBe(0);
    expect(bucket.log.every((l) => l.startsWith("get "))).toBe(true);
  });

  it("writes live.m3u8 through the R2 binding with its content type and max-age", async () => {
    await env.BUCKET.put("state/horizon.json", JSON.stringify(horizonDoc(E)));
    await env.BUCKET.put("fallback/v1/index.json", JSON.stringify(FALLBACK));
    await runClock({ bucket: r2Bucket(env.BUCKET), ...fakeTime(E + 10 * D + 40), scheduledTime: E + 10 * D,
                     config: { ...CFG, loopMs: 0 } });
    const obj = await env.BUCKET.get("live.m3u8");
    expect(obj!.httpMetadata!.contentType).toBe("application/vnd.apple.mpegurl");
    expect(obj!.httpMetadata!.cacheControl).toBe("public, max-age=5");
    expect(await obj!.text()).toContain("seg/e1/10.aac");
  });
});

describe("off-air without a usable fallback", () => {
  const offairErrors = (spy: { mock: { calls: unknown[][] } }) =>
    spy.mock.calls
      .map((c) => { try { return JSON.parse(String(c[0])); } catch { return null; } })
      .filter((o) => o?.event === "offair-without-fallback");

  it("writes nothing but reports it loudly, once per invocation (state/offair.json)", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    bucket.seed("state/horizon.json", horizonDoc(E));
    bucket.seed("state/offair.json", { offair: true });
    const scheduledTime = E + 50 * D + 300;
    const r = await runClock({ bucket, ...fakeTime(scheduledTime + 40), scheduledTime, config: CFG });
    expect(r.puts).toBe(0);
    expect(playlistPuts(bucket)).toBe(0);
    expect(r.offairWithoutFallback).toMatch(/state\/offair\.json/);
    expect(r.offairWithoutFallback).toMatch(/fallback\/v1\/index\.json/);
    const logged = offairErrors(spy);
    expect(logged).toHaveLength(1);
    expect(logged[0].reason).toBe(r.offairWithoutFallback);
  });

  it("reports the staleness rule and a null fallback_version", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    bucket.seed("state/horizon.json", { ...horizonDoc(E, 0, 100), fallback_version: null });
    const now = E + 101 * D + CFG.offairAfterMs + 1;
    const r = await runClock({ bucket, ...fakeTime(now), scheduledTime: now, config: CFG });
    expect(r.puts).toBe(0);
    expect(r.offairWithoutFallback).toMatch(/stale/);
    expect(r.offairWithoutFallback).toMatch(/fallback_version/);
    expect(offairErrors(spy)).toHaveLength(1);
  });

  it("stays silent when off-air has a fallback, or the station is on air without one", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const offairOk = new MemoryBucket();
    station(offairOk, true);
    const r1 = await runClock({ bucket: offairOk, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: CFG });
    expect(r1.puts).toBe(1);
    expect(r1.offairWithoutFallback).toBeNull();
    const onAirNoFallback = new MemoryBucket();
    onAirNoFallback.seed("state/horizon.json", horizonDoc(E));
    const r2 = await runClock({ bucket: onAirNoFallback, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D,
                                config: CFG });
    expect(r2.puts).toBeGreaterThan(0);
    expect(r2.offairWithoutFallback).toBeNull();
    expect(offairErrors(spy)).toHaveLength(0);
  });
});

const structuredErrors = (spy: { mock: { calls: unknown[][] } }, event: string) =>
  spy.mock.calls
    .map((c) => { try { return JSON.parse(String(c[0])); } catch { return null; } })
    .filter((o) => o?.event === event);

describe("spend bounds hold regardless of inputs", () => {
  it("caps PUTs at 10 absolutely, whatever d and loopMs say", () => {
    expect(MAX_PUTS).toBe(10);
    for (const [loopMs, dMs] of [[75_000, 10], [900_000, 10_240], [75_000, 1], [10_000_000, 1_000]]) {
      expect(putCap({ ...CFG, loopMs }, dMs)).toBeLessThanOrEqual(10);
    }
  });

  it("refuses a horizon whose d is not 10.24: zero PUTs, one structured error, returns promptly", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    for (const d of [0.01, 1, 10.25, "10.24"]) {
      spy.mockClear();
      const bucket = new MemoryBucket();
      station(bucket);
      bucket.seed("state/horizon.json", { ...horizonDoc(E), d });
      const start = E + 50 * D;
      const clock = fakeTime(start);
      const r = await runClock({ bucket, ...clock, scheduledTime: start, config: CFG });
      expect(r.puts).toBe(0);
      expect(playlistPuts(bucket)).toBe(0);
      expect(clock.now()).toBe(start); // never slept
      expect(r.refused).toMatch(/d/);
      const logged = structuredErrors(spy, "horizon-refused");
      expect(logged).toHaveLength(1);
      expect(logged[0].d).toEqual(d);
    }
  });

  it("clamps LOOP_SECONDS=900 to 75 s: at most 10 PUTs, ends by scheduledTime + 75 s, logged once", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    station(bucket);
    const scheduledTime = E + 50 * D + 300;
    const clock = fakeTime(scheduledTime + 40);
    const r = await runClock({ bucket, ...clock, scheduledTime, config: configFromEnv({ LOOP_SECONDS: "900" }) });
    expect(r.puts).toBeLessThanOrEqual(10);
    expect(r.puts).toBe(8); // same as the 75 s default
    expect(clock.now()).toBeLessThanOrEqual(scheduledTime + 75_000);
    const logged = structuredErrors(spy, "loop-clamped");
    expect(logged).toHaveLength(1);
    expect(logged[0]).toMatchObject({ configuredMs: 900_000, usedMs: 75_000 });
  });

  it("never writes max-age=0: LIVE_MAX_AGE is at least 1", async () => {
    expect(configFromEnv({ LIVE_MAX_AGE: "0" }).liveMaxAge).toBe(1);
    const bucket = new MemoryBucket();
    station(bucket);
    await runClock({ bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D,
                     config: { ...CFG, loopMs: 0, liveMaxAge: 0 } });
    expect(bucket.objects.get("live.m3u8")!.cacheControl).toBe("public, max-age=1");
  });
});

describe("configFromEnv", () => {
  it("parses the vars with defaults", () => {
    expect(configFromEnv({})).toEqual({ window: 6, grace: 3, offairAfterMs: 86_400_000, loopMs: 75_000, liveMaxAge: 5 });
    expect(configFromEnv({ LOOP_SECONDS: "0", PLAYLIST_WINDOW: "8" })).toMatchObject({ loopMs: 0, window: 8 });
    expect(configFromEnv({ GRACE_SEGMENTS: "nonsense" }).grace).toBe(3);
  });
});

describe("scheduled handler", () => {
  it("runs one clock invocation against the bound bucket", async () => {
    const now = Date.now();
    await env.BUCKET.put("state/horizon.json", JSON.stringify(horizonDoc(now - 100 * D)));
    await env.BUCKET.put("fallback/v1/index.json", JSON.stringify(FALLBACK));
    const ctrl = createScheduledController({ scheduledTime: now, cron: "* * * * *" });
    const ctx = createExecutionContext();
    await worker.scheduled!(ctrl, { ...env, LOOP_SECONDS: "0" } as unknown as Env, ctx);
    await waitOnExecutionContext(ctx);
    const body = await (await env.BUCKET.get("live.m3u8"))!.text();
    expect(body).toContain("#EXTM3U");
    expect(body).toContain("seg/e1/");
  });

  it("emits the per-invocation clock line even when runClock throws", async () => {
    const spy = vi.spyOn(console, "log").mockImplementation(() => {});
    await env.BUCKET.put("state/horizon.json", JSON.stringify({ ...horizonDoc(Date.now()), epoch: "nonsense" }));
    const ctrl = createScheduledController({ scheduledTime: Date.now(), cron: "* * * * *" });
    const ctx = createExecutionContext();
    await expect(worker.scheduled!(ctrl, { ...env, LOOP_SECONDS: "0" } as unknown as Env, ctx)).rejects.toThrow(/epoch/);
    await waitOnExecutionContext(ctx);
    const lines = structuredErrors(spy, "clock");
    expect(lines).toHaveLength(1);
    expect(lines[0].error).toMatch(/epoch/);
    expect(lines[0].lagMs).toEqual(expect.any(Number));
  });
});
