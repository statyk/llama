import { createExecutionContext, createScheduledController, env, waitOnExecutionContext } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type ClockConfig, configFromEnv, MAX_PUTS, putCap, r2Bucket, runClock } from "../src/clock";
import type { AlertCondition } from "../src/conditions";
import type { AntennaEnv } from "../src/env";
import type { GuardOutcome } from "../src/guard";
import worker from "../src/index";
import { INDEX_KEY } from "../src/indexpage";
import { OFFAIR_PAGE, PLAYER_PAGE } from "../src/pages";
import { fakeTime, MemoryBucket } from "./support";

const E = Date.parse("2026-10-10T12:00:00.000Z");
const D = 10_240;
const CFG: ClockConfig = { window: 6, grace: 3, offairAfterMs: 86_400_000, loopMs: 75_000, liveMaxAge: 5,
                           leadFloorMs: 16 * 3_600_000 };

/** A guard stand-in with a fixed verdict (guard.ts has its own tests). */
const guardSays = (blocked: boolean | null, tripped = false, conditions: AlertCondition[] = []) =>
  async (): Promise<GuardOutcome> => ({ blocked, tripped: blocked === null ? null : tripped,
                                        offair: blocked === null ? null : blocked && !tripped, doc: null, conditions });
const onAir = guardSays(false);

function horizonDoc(epochMs: number, first = 0, last = 1_000_000) {
  const iso = new Date(epochMs).toISOString();
  return { epoch_id: "e1", epoch: iso, d: 10.24, first, last, published_at: iso, container: "adts", fallback_version: "v1" };
}
const FALLBACK = { len: 7, notice: "fallback/v1/notice.aac", d: 10.24 };

function station(bucket: MemoryBucket) {
  bucket.seed("state/horizon.json", horizonDoc(E));
  bucket.seed("fallback/v1/index.json", FALLBACK);
}

const playlistPuts = (b: MemoryBucket) => b.puts("live.m3u8");
const structured = (spy: { mock: { calls: unknown[][] } }, event: string) =>
  spy.mock.calls
    .map((c) => { try { return JSON.parse(String(c[0])); } catch { return null; } })
    .filter((o) => o?.event === event);

afterEach(() => {
  vi.restoreAllMocks();
});

describe("runClock", () => {
  it("writes immediately, then at every grid boundary until fire + 75 s", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const scheduledTime = E + 50 * D + 300;
    const clock = fakeTime(scheduledTime + 40);
    const r = await runClock({ bucket, ...clock, scheduledTime, config: CFG, guard: onAir });
    expect(r.puts).toBe(8); // immediate + boundaries 51..57; 58 starts after fire + 75 s
    expect(playlistPuts(bucket)).toBe(8);
    expect(clock.now()).toBeLessThanOrEqual(scheduledTime + CFG.loopMs);
    expect(bucket.objects.get("live.m3u8")!.body).toContain("seg/e1/57.aac");
  });

  it("never exceeds ceil(75/d) + 2 PUTs, even with a skewed fire time", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const clock = fakeTime(E + 100 * D);
    const r = await runClock({ bucket, ...clock, scheduledTime: E + 100 * D + 600_000, config: CFG, guard: onAir });
    expect(putCap(CFG, D)).toBe(10);
    expect(r.puts).toBe(10);
  });

  it("blocked: the off-air playlist, one PUT per invocation (identical bytes skipped)", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const scheduledTime = E + 50 * D + 300;
    const r = await runClock({ bucket, ...fakeTime(scheduledTime + 40), scheduledTime, config: CFG, guard: guardSays(true) });
    expect(r.puts).toBe(1);
    expect(r.skipped).toBe(7);
    expect(bucket.objects.get("live.m3u8")!.body).toContain("#EXT-X-ENDLIST");
  });

  it("runs the guard before reading or writing anything", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const seen: string[] = [];
    await runClock({ bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: { ...CFG, loopMs: 0 },
                     guard: async () => { seen.push("guard", ...bucket.log); return onAir(); } });
    expect(seen).toEqual(["guard"]);
    expect(bucket.log.slice(0, 2)).toEqual([`head ${INDEX_KEY}`, `put ${INDEX_KEY}`]);
  });

  it("records how long the guard took (guardMs, on the clock line)", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const clock = fakeTime(E + 10 * D);
    const r = await runClock({ bucket, ...clock, scheduledTime: E + 10 * D, config: { ...CFG, loopMs: 0 },
                               guard: async () => { await clock.sleep(1_234); return onAir(); } });
    expect(r.guardMs).toBe(1_234);
  });

  it("writes nothing at all when the guard cannot tell whether the station is blocked", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    station(bucket);
    const r = await runClock({ bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: CFG, guard: guardSays(null) });
    expect(r).toMatchObject({ puts: 0, blocked: null, index: "skipped" });
    expect(bucket.puts()).toBe(0);
  });

  it("a guard that throws is treated as unknown: nothing written, an urgent alert", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    station(bucket);
    const sent: AlertCondition[] = [];
    const r = await runClock({ bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: CFG,
                               guard: async () => { throw new Error("kaboom"); },
                               alerts: async (cs) => { sent.push(...cs); } });
    expect(r.puts).toBe(0);
    expect(bucket.puts()).toBe(0);
    expect(sent.map((c) => c.key)).toEqual(["guard-crashed"]);
  });

  it("index.html follows the blocked state", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const run = (guard: () => Promise<GuardOutcome>) =>
      runClock({ bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: { ...CFG, loopMs: 0 }, guard });
    expect((await run(onAir)).index).toBe("written");
    expect(bucket.objects.get(INDEX_KEY)!.body).toBe(PLAYER_PAGE);
    expect((await run(onAir)).index).toBe("unchanged");
    expect((await run(guardSays(true, true))).index).toBe("written");
    expect(bucket.objects.get(INDEX_KEY)!.body).toBe(OFFAIR_PAGE);
  });

  it("a failed index.html write still writes the playlist, and alerts", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    bucket.failPuts.add(INDEX_KEY);
    const sent: string[] = [];
    const r = await runClock({ bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: { ...CFG, loopMs: 0 },
                               guard: onAir, alerts: async (cs) => { sent.push(...cs.map((c) => c.key)); } });
    expect(r.index).toBe("failed");
    expect(r.puts).toBe(1);
    expect(sent).toEqual(["index-write"]);
  });

  it("a failed index.html HEAD while blocked still writes the off-air playlist, and alerts", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    bucket.failGets.add(INDEX_KEY); // fails the HEAD reconcileIndex makes
    const sent: string[] = [];
    const r = await runClock({ bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: { ...CFG, loopMs: 0 },
                               guard: guardSays(true, true), alerts: async (cs) => { sent.push(...cs.map((c) => c.key)); } });
    expect(r).toMatchObject({ index: "failed", blocked: true, puts: 1 });
    expect(bucket.puts(INDEX_KEY)).toBe(0);
    expect(bucket.objects.get("live.m3u8")!.body).toContain("#EXT-X-ENDLIST");
    expect(sent).toEqual(["index-write"]);
  });

  it("writes no playlist without a horizon, and says so", async () => {
    const bucket = new MemoryBucket();
    const r = await runClock({ bucket, ...fakeTime(E), scheduledTime: E, config: CFG, guard: onAir });
    expect(r.puts).toBe(0);
    expect(playlistPuts(bucket)).toBe(0);
    expect(r.alerts).toEqual(["horizon-missing"]);
  });

  it("alerts when the published lead is below the floor, except while tripped (publishing stops then)", async () => {
    const bucket = new MemoryBucket();
    bucket.seed("state/horizon.json", horizonDoc(E, 0, 1000));
    bucket.seed("fallback/v1/index.json", FALLBACK);
    const now = E + 1001 * D - 3_600_000; // the lead is 1 h
    const r = await runClock({ bucket, ...fakeTime(now), scheduledTime: now, config: { ...CFG, loopMs: 0 }, guard: onAir });
    expect(r.alerts).toContain("lead-low");
    const t = await runClock({ bucket, ...fakeTime(now), scheduledTime: now, config: { ...CFG, loopMs: 0 },
                               guard: guardSays(true, true) });
    expect(t.alerts).not.toContain("lead-low");
  });

  it("passes the guard's conditions to the alert sink once, after the last playlist write", async () => {
    const bucket = new MemoryBucket();
    station(bucket);
    const order: string[] = [];
    const cond: AlertCondition = { key: "budget-50", priority: "default", resolvable: false, title: "t", message: "m" };
    const realPut = bucket.put.bind(bucket);
    bucket.put = async (k, v, o) => { order.push(`put ${k}`); return realPut(k, v, o); };
    await runClock({ bucket, ...fakeTime(E + 10 * D + 40), scheduledTime: E + 10 * D, config: CFG,
                     guard: guardSays(false, false, [cond]),
                     alerts: async (cs) => { order.push(`alerts ${cs.map((c) => c.key).join()}`); } });
    expect(order.filter((o) => o.startsWith("alerts"))).toEqual(["alerts budget-50"]);
    expect(order.filter((o) => o === "put live.m3u8").length).toBeGreaterThan(1);
    expect(order.at(-1)).toBe("alerts budget-50"); // after every boundary write
  });

  it("writes live.m3u8 through the R2 binding with its content type and max-age", async () => {
    await env.BUCKET.put("state/horizon.json", JSON.stringify(horizonDoc(E)));
    await env.BUCKET.put("fallback/v1/index.json", JSON.stringify(FALLBACK));
    await runClock({ bucket: r2Bucket(env.BUCKET), ...fakeTime(E + 10 * D + 40), scheduledTime: E + 10 * D,
                     config: { ...CFG, loopMs: 0 }, guard: onAir });
    const obj = await env.BUCKET.get("live.m3u8");
    expect(obj!.httpMetadata!.contentType).toBe("application/vnd.apple.mpegurl");
    expect(obj!.httpMetadata!.cacheControl).toBe("public, max-age=5");
    expect(await obj!.text()).toContain("seg/e1/10.aac");
  });
});

describe("off-air without a usable fallback", () => {
  const uriLines = (body: string) => body.split("\n").filter((l) => l !== "" && !l.startsWith("#"));

  it("writes the ENDLIST-only playlist once and reports it loudly, once per invocation", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    bucket.seed("state/horizon.json", horizonDoc(E));
    const scheduledTime = E + 50 * D + 300;
    const r = await runClock({ bucket, ...fakeTime(scheduledTime + 40), scheduledTime, config: CFG, guard: guardSays(true) });
    expect(r.puts).toBe(1);
    expect(playlistPuts(bucket)).toBe(1);
    expect(r.skipped).toBeGreaterThan(0);
    const body = bucket.objects.get("live.m3u8")!.body;
    expect(uriLines(body)).toEqual([]);
    expect(body.trimEnd().endsWith("#EXT-X-ENDLIST")).toBe(true);
    expect(r.offairWithoutFallback).toMatch(/blocked/);
    expect(r.offairWithoutFallback).toMatch(/ENDLIST-only/);
    expect(r.offairWithoutFallback).toMatch(/fallback\/v1\/index\.json/);
    const logged = structured(spy, "offair-without-fallback");
    expect(logged).toHaveLength(1);
    expect(logged[0].reason).toBe(r.offairWithoutFallback);
    expect(r.alerts).toContain("offair-without-fallback");
  });

  it("reports the staleness rule and a null fallback_version", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    bucket.seed("state/horizon.json", { ...horizonDoc(E, 0, 100), fallback_version: null });
    const now = E + 101 * D + CFG.offairAfterMs + 1;
    const r = await runClock({ bucket, ...fakeTime(now), scheduledTime: now, config: CFG, guard: onAir });
    expect(r.puts).toBe(1);
    expect(uriLines(bucket.objects.get("live.m3u8")!.body)).toEqual([]);
    expect(r.offairWithoutFallback).toMatch(/stale/);
    expect(r.offairWithoutFallback).toMatch(/fallback_version/);
    expect(structured(spy, "offair-without-fallback")).toHaveLength(1);
  });

  it("stays silent when off-air has a fallback, or the station is on air without one", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const offairOk = new MemoryBucket();
    station(offairOk);
    const r1 = await runClock({ bucket: offairOk, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D, config: CFG,
                                guard: guardSays(true) });
    expect(r1.puts).toBe(1);
    expect(r1.offairWithoutFallback).toBeNull();
    const onAirNoFallback = new MemoryBucket();
    onAirNoFallback.seed("state/horizon.json", horizonDoc(E));
    const r2 = await runClock({ bucket: onAirNoFallback, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D,
                                config: CFG, guard: onAir });
    expect(r2.puts).toBeGreaterThan(0);
    expect(r2.offairWithoutFallback).toBeNull();
    expect(structured(spy, "offair-without-fallback")).toHaveLength(0);
  });
});

describe("spend bounds hold regardless of inputs", () => {
  it("caps PUTs at 10 absolutely, whatever d and loopMs say", () => {
    expect(MAX_PUTS).toBe(10);
    for (const [loopMs, dMs] of [[75_000, 10], [900_000, 10_240], [75_000, 1], [10_000_000, 1_000]]) {
      expect(putCap({ ...CFG, loopMs }, dMs)).toBeLessThanOrEqual(10);
    }
  });

  it("refuses a horizon whose d is not 10.24: zero playlist PUTs, one structured error, an alert, returns promptly", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    for (const d of [0.01, 1, 10.25, "10.24"]) {
      spy.mockClear();
      const bucket = new MemoryBucket();
      station(bucket);
      bucket.seed("state/horizon.json", { ...horizonDoc(E), d });
      const start = E + 50 * D;
      const clock = fakeTime(start);
      const r = await runClock({ bucket, ...clock, scheduledTime: start, config: CFG, guard: onAir });
      expect(r.puts).toBe(0);
      expect(playlistPuts(bucket)).toBe(0);
      expect(clock.now()).toBe(start); // never slept
      expect(r.refused).toMatch(/d/);
      expect(r.alerts).toContain("horizon-refused");
      const logged = structured(spy, "horizon-refused");
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
    const r = await runClock({ bucket, ...clock, scheduledTime, config: configFromEnv({ LOOP_SECONDS: "900" }), guard: onAir });
    expect(r.puts).toBeLessThanOrEqual(10);
    expect(r.puts).toBe(8); // same as the 75 s default
    expect(clock.now()).toBeLessThanOrEqual(scheduledTime + 75_000);
    const logged = structured(spy, "loop-clamped");
    expect(logged).toHaveLength(1);
    expect(logged[0]).toMatchObject({ configuredMs: 900_000, usedMs: 75_000 });
  });

  it("never writes max-age=0: LIVE_MAX_AGE is at least 1", async () => {
    expect(configFromEnv({ LIVE_MAX_AGE: "0" }).liveMaxAge).toBe(1);
    const bucket = new MemoryBucket();
    station(bucket);
    await runClock({ bucket, ...fakeTime(E + 10 * D), scheduledTime: E + 10 * D,
                     config: { ...CFG, loopMs: 0, liveMaxAge: 0 }, guard: onAir });
    expect(bucket.objects.get("live.m3u8")!.cacheControl).toBe("public, max-age=1");
  });
});

describe("configFromEnv", () => {
  it("parses the vars with defaults", () => {
    expect(configFromEnv({})).toEqual({ window: 6, grace: 3, offairAfterMs: 86_400_000, loopMs: 75_000, liveMaxAge: 5,
                                        leadFloorMs: 16 * 3_600_000 });
    expect(configFromEnv({ LOOP_SECONDS: "0", PLAYLIST_WINDOW: "8" })).toMatchObject({ loopMs: 0, window: 8 });
    expect(configFromEnv({ GRACE_SEGMENTS: "nonsense" }).grace).toBe(3);
    expect(configFromEnv({ LEAD_FLOOR_HOURS: "6" }).leadFloorMs).toBe(6 * 3_600_000);
  });
});

describe("scheduled handler", () => {
  // env carries the wrangler vars but no secrets: the guard cannot read usage
  // or reach the WAF (no network in tests), records that, and is not blocked
  // (blind trips only after BLIND_AFTER_SECONDS).
  it("runs the guard then one clock invocation against the bound bucket", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    const now = Date.now();
    await env.BUCKET.put("state/horizon.json", JSON.stringify(horizonDoc(now - 100 * D)));
    await env.BUCKET.put("fallback/v1/index.json", JSON.stringify(FALLBACK));
    const ctrl = createScheduledController({ scheduledTime: now, cron: "* * * * *" });
    const ctx = createExecutionContext();
    await worker.scheduled!(ctrl, { ...env, LOOP_SECONDS: "0" } as unknown as AntennaEnv, ctx);
    await waitOnExecutionContext(ctx);
    const body = await (await env.BUCKET.get("live.m3u8"))!.text();
    expect(body).toContain("#EXTM3U");
    expect(body).toContain("seg/e1/");
    const guard = await (await env.BUCKET.get("state/guard.json"))!.json<{ tripped: boolean; last_error: string }>();
    expect(guard.tripped).toBe(false);
    expect(guard.last_error).toMatch(/CF_ACCOUNT_ID/);
    expect((await env.BUCKET.head("index.html"))!.customMetadata!.page).toBe("player");
    expect(structured(log, "clock")[0].guardMs).toEqual(expect.any(Number));
  });

  it("emits the per-invocation clock line even when runClock throws", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const spy = vi.spyOn(console, "log").mockImplementation(() => {});
    await env.BUCKET.put("state/horizon.json", JSON.stringify({ ...horizonDoc(Date.now()), epoch: "nonsense" }));
    const ctrl = createScheduledController({ scheduledTime: Date.now(), cron: "* * * * *" });
    const ctx = createExecutionContext();
    await expect(worker.scheduled!(ctrl, { ...env, LOOP_SECONDS: "0" } as unknown as AntennaEnv, ctx)).rejects.toThrow(/epoch/);
    await waitOnExecutionContext(ctx);
    const lines = structured(spy, "clock");
    expect(lines).toHaveLength(1);
    expect(lines[0].error).toMatch(/epoch/);
    expect(lines[0].lagMs).toEqual(expect.any(Number));
  });
});
