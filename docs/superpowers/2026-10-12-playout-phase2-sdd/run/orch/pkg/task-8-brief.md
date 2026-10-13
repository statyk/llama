### Task 8: Clock integration and Worker wiring

**Model hint:** opus (spend + blocking path)

**Files:**
- Modify: `antenna/src/clock.ts` (replace the whole file), `antenna/src/index.ts` (replace), `antenna/wrangler.jsonc` (replace)
- Create: `antenna/src/env.ts`
- Modify: `antenna/test/clock.test.ts` (replace the whole file)

**Interfaces:**
- Consumes:
  - `GuardOutcome`, `guardStep`, `guardConfigFromEnv`, `GuardEnv` (Task 6);
  - `AlertCondition` (Task 6);
  - `reconcileIndex`, `INDEX_KEY` (Task 7);
  - `PLAYER_PAGE`, `OFFAIR_PAGE` (Task 7);
  - the bucket seam (Task 1).
- Produces:
  - `ClockConfig.leadFloorMs` (var `LEAD_FLOOR_HOURS`, default 16).
  - `ClockDeps.guard: () => Promise<GuardOutcome>` (**required**) and `ClockDeps.alerts?: (conditions, nowMs) => Promise<void>` (default `logAlerts`).
  - `ClockResult` gains `blocked: boolean | null`, `guardMs: number | null` (how long the guard took; logged on the clock line), `index: "written" | "unchanged" | "failed" | "skipped"` and `alerts: string[]` (the condition keys).
  - `readInputs(bucket, blocked)`; `offair.json` is no longer read here, because the guard reads it.
  - `logAlerts(conditions, nowMs)`.
  - `src/env.ts`: `interface AntennaEnv extends ClockEnv, GuardEnv { BUCKET: R2Bucket }`.
  - New clock condition keys: `guard-crashed`, `index-write`, `horizon-missing`, `horizon-refused`, `lead-low` and `offair-without-fallback`.

The phase-1 `guardStep` seam disappears: the real guard is passed in by `index.ts`. Behaviour summary:

- The guard runs first.
- An unknown outcome (null), or a guard that throws, writes nothing at all.
- `index.html` follows `blocked`.
- The playlist is the off-air playlist while blocked.
- The lead-floor condition is suppressed while tripped.
- Alerts are flushed once, after the invocation's last playlist write (or at an early return), never before the guard. A slow alert channel therefore never delays a boundary write.
- The guard's duration is recorded as `guardMs` and logged on the per-invocation clock line: amendment A4's trigger adds it to the cron lag.

All phase-1 spend bounds and their tests are kept. The existing tests are adapted: they now pass a guard stand-in.

- [ ] **Step 1: Write the failing tests**

Replace `antenna/test/clock.test.ts` with:

```ts
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/clock.test.ts`
Expected: FAIL. `../src/env` cannot be resolved, and `leadFloorMs`, `guard` and `alerts` are unknown to the current clock.

- [ ] **Step 3: Implement**

Replace `antenna/src/clock.ts` with:

```ts
import type { BucketLike } from "./bucket";
import type { AlertCondition } from "./conditions";
import { type Horizon, gridOf, indexAt, startMs } from "./grid";
import type { GuardOutcome } from "./guard";
import { reconcileIndex } from "./indexpage";
import { buildPlaylist, type FallbackIndex, isOffair, type PlaylistConfig, usableFallback } from "./playlist";

export { type BucketLike, r2Bucket, type StoredObject } from "./bucket";

export interface ClockConfig extends PlaylistConfig {
  loopMs: number;
  liveMaxAge: number;
  /** Alert when the published lead (end of horizon.last - now) is below this. */
  leadFloorMs: number;
}

export interface ClockEnv {
  PLAYLIST_WINDOW?: string;
  GRACE_SEGMENTS?: string;
  OFFAIR_AFTER_SECONDS?: string;
  LOOP_SECONDS?: string;
  LIVE_MAX_AGE?: string;
  LEAD_FLOOR_HOURS?: string;
}

function num(v: string | undefined, fallback: number): number {
  const x = v === undefined ? Number.NaN : Number(v);
  return Number.isFinite(x) && x >= 0 ? x : fallback;
}

export function configFromEnv(env: ClockEnv): ClockConfig {
  return {
    window: Math.max(1, Math.floor(num(env.PLAYLIST_WINDOW, 6))),
    grace: Math.floor(num(env.GRACE_SEGMENTS, 3)),
    offairAfterMs: num(env.OFFAIR_AFTER_SECONDS, 86_400) * 1000,
    loopMs: num(env.LOOP_SECONDS, 75) * 1000,
    liveMaxAge: Math.max(1, Math.floor(num(env.LIVE_MAX_AGE, 5))),
    leadFloorMs: num(env.LEAD_FLOOR_HOURS, 16) * 3_600_000,
  };
}

export interface ClockDeps {
  bucket: BucketLike;
  now: () => number;
  sleep: (ms: number) => Promise<void>;
  scheduledTime: number;
  config: ClockConfig;
  /** The cost guard step (guard.ts), run first; it decides blocked. */
  guard: () => Promise<GuardOutcome>;
  /** Where this invocation's alert conditions go (alerts.ts); default: logged. */
  alerts?: (conditions: AlertCondition[], nowMs: number) => Promise<void>;
}

export interface ClockResult {
  puts: number;
  skipped: number;
  /** Set when off-air was in force but no usable fallback/notice exists, so
   * the ENDLIST-only playlist (no notice) was written instead (also logged
   * once per invocation as a structured console.error). */
  offairWithoutFallback: string | null;
  /** Set when the horizon was refused (d is not the grid constant); nothing written. */
  refused: string | null;
  /** The guard's verdict: null = unknown, nothing written this invocation. */
  blocked: boolean | null;
  /** How long the guard step took. Logged on the clock line: amendment A4's
   * trigger adds it to the cron lag. */
  guardMs: number | null;
  index: "written" | "unchanged" | "failed" | "skipped";
  /** Keys of the alert conditions raised this invocation. */
  alerts: string[];
}

export const LIVE_KEY = "live.m3u8";

// Spend is the strict surface (Cloudflare has no spending cap), so the PUT
// bound is absolute and never derived from inputs alone: d comes from
// state/horizon.json and loopMs from a wrangler var, and either could
// otherwise turn the cap into thousands of Class-A writes per invocation.
/** The grid constant transmitter always writes: 441 * 1024 / 44100 s. */
export const GRID_D = 10.24;
/** The spec's run length: write until scheduledTime + 75 s, never longer. */
export const MAX_LOOP_MS = 75_000;
/** ceil(75 / 10.24) + 2: the per-invocation PUT ceiling, whatever the inputs. */
export const MAX_PUTS = 10;
const BOUNDARY_SLACK_MS = 25;

export interface ClockInputs {
  horizon: Horizon | null;
  fallback: FallbackIndex | null;
  /** Blocked (tripped OR offair), from the guard: the off-air playlist. */
  offair: boolean;
}

async function readJson<T>(bucket: BucketLike, key: string): Promise<T | null> {
  const obj = await bucket.get(key);
  if (obj === null) return null;
  try {
    return JSON.parse(await obj.text()) as T;
  } catch {
    return null;
  }
}

/** The horizon and its fallback, read once per invocation via the binding
 * (never through the cache). The blocked state comes from the guard. */
export async function readInputs(bucket: BucketLike, blocked: boolean): Promise<ClockInputs> {
  const horizon = await readJson<Horizon>(bucket, "state/horizon.json");
  const fallback = horizon?.fallback_version
    ? await readJson<FallbackIndex>(bucket, `fallback/${horizon.fallback_version}/index.json`)
    : null;
  return { horizon, fallback, offair: blocked };
}

/** Default alert sink until alerts.ts dispatches: one structured line each. */
export async function logAlerts(conditions: AlertCondition[], _nowMs: number): Promise<void> {
  for (const c of conditions) console.error(JSON.stringify({ event: "alert", key: c.key, title: c.title, message: c.message }));
}

export function putCap(cfg: ClockConfig, dMs: number): number {
  return Math.min(MAX_PUTS, Math.ceil(cfg.loopMs / dMs) + 2);
}

/** Why off-air is in force at nowMs and no usable fallback exists, or null. */
function offairWithoutFallback(inputs: ClockInputs, horizon: Horizon, nowMs: number, cfg: ClockConfig): string | null {
  const inp = { nowMs, horizon, fallback: inputs.fallback, offair: inputs.offair };
  if (!isOffair(inp, cfg) || usableFallback(inp) !== null) return null;
  const cause = inputs.offair
    ? "the station is blocked (tripped or state/offair.json)"
    : `horizon is stale (now is more than ${cfg.offairAfterMs / 1000} s past the end of segment ${horizon.last})`;
  const missing =
    horizon.fallback_version === null || horizon.fallback_version === ""
      ? "horizon.fallback_version is null"
      : inputs.fallback === null
        ? `fallback/${horizon.fallback_version}/index.json is missing or unreadable`
        : `fallback/${horizon.fallback_version}/index.json has len < 1`;
  return `off-air (${cause}) but no usable fallback (${missing}): live.m3u8 written as an ENDLIST-only playlist (no notice), so players stop`;
}

/**
 * One cron invocation. First the cost guard (guard.ts): it decides blocked =
 * tripped OR offair and reconciles the kill switch; when it cannot tell, the
 * invocation writes nothing at all. Then index.html follows the blocked state,
 * and the playlist is written immediately and at every grid boundary
 * E + N*d until scheduledTime + loopMs (the off-air playlist while blocked).
 * Alerts go out after the last playlist write, so a slow channel never delays
 * a boundary write. Only CPU time is billed, so the waiting is free.
 * Overlapping invocations are harmless: the playlist is a pure function of the
 * clock and the inputs.
 *
 * Epoch change: inputs are read once per invocation, so an epoch never changes
 * inside one. When state/horizon.json's epoch_id changes between invocations,
 * segment numbering restarts (N from 0 at the new epoch E) and
 * EXT-X-MEDIA-SEQUENCE drops. That is deliberate, not a defect: a new epoch is
 * an operator re-render event (transmitter re-renders and republishes under
 * seg/<new epoch_id>/), and players must reload the stream to follow it.
 */
export async function runClock(deps: ClockDeps): Promise<ClockResult> {
  const { bucket } = deps;
  const config: ClockConfig = {
    ...deps.config,
    loopMs: Math.min(deps.config.loopMs, MAX_LOOP_MS),
    liveMaxAge: Math.max(1, Math.floor(deps.config.liveMaxAge)),
  };
  if (config.loopMs !== deps.config.loopMs) {
    console.error(JSON.stringify({ event: "loop-clamped", configuredMs: deps.config.loopMs, usedMs: config.loopMs,
                                   scheduled: deps.scheduledTime }));
  }
  const result: ClockResult = { puts: 0, skipped: 0, offairWithoutFallback: null, refused: null, blocked: null,
                                guardMs: null, index: "skipped", alerts: [] };
  const conditions: AlertCondition[] = [];
  let flushed = false;
  const flush = async () => {
    if (flushed) return;
    flushed = true;
    result.alerts = conditions.map((c) => c.key);
    try {
      await (deps.alerts ?? logAlerts)(conditions, deps.now());
    } catch (e) {
      console.error(JSON.stringify({ event: "alert-dispatch-failed", error: e instanceof Error ? e.message : String(e) }));
    }
  };
  try {
    // 1. The guard, first: it decides blocked and reconciles the kill switch.
    const startedMs = deps.now();
    let outcome: GuardOutcome;
    try {
      outcome = await deps.guard();
    } catch (e) {
      outcome = { blocked: null, tripped: null, offair: null, doc: null, conditions: [{
        key: "guard-crashed", priority: "urgent", resolvable: true, title: "Cost guard crashed",
        message: `The guard step threw (${e instanceof Error ? e.message : String(e)}); the clock wrote nothing.` }] };
    }
    result.guardMs = deps.now() - startedMs;
    conditions.push(...outcome.conditions);
    result.blocked = outcome.blocked;
    if (outcome.blocked === null) {
      // Unknown: change nothing (players stall on a stale playlist, toward zero cost).
      console.error(JSON.stringify({ event: "guard-unknown", scheduled: deps.scheduledTime }));
      return result;
    }
    const blocked = outcome.blocked;
    // 2. index.html follows the blocked state.
    try {
      result.index = await reconcileIndex(bucket, blocked);
    } catch (e) {
      result.index = "failed";
      conditions.push({ key: "index-write", priority: "high", resolvable: true, title: "index.html not reconciled",
                        message: `Writing index.html (${blocked ? "off-air" : "player"} page) failed: ${e instanceof Error ? e.message : String(e)}` });
    }
    // 3. The playlist.
    const inputs = await readInputs(bucket, blocked);
    const horizon = inputs.horizon;
    if (horizon === null) {
      conditions.push({ key: "horizon-missing", priority: "default", resolvable: true, title: "No horizon published",
                        message: "state/horizon.json is absent: nothing is on air yet (transmitter has not published)." });
      return result;
    }
    if (horizon.d !== GRID_D) {
      result.refused = `state/horizon.json d is ${JSON.stringify(horizon.d)}, not the grid constant ${GRID_D}: live.m3u8 not written`;
      console.error(JSON.stringify({ event: "horizon-refused", reason: result.refused, d: horizon.d,
                                     epoch_id: horizon.epoch_id, scheduled: deps.scheduledTime }));
      conditions.push({ key: "horizon-refused", priority: "urgent", resolvable: true, title: "Horizon refused",
                        message: result.refused });
      return result;
    }
    const g = gridOf(horizon);
    const leadMs = startMs(g, horizon.last + 1) - deps.now();
    // While tripped, transmitter stops publishing by design: the lead drains then.
    if (!outcome.tripped && leadMs < config.leadFloorMs) {
      conditions.push({ key: "lead-low", priority: "high", resolvable: true, title: "Published lead below floor",
                        message: `The published lead is ${(leadMs / 3_600_000).toFixed(1)} h (floor ` +
                                 `${(config.leadFloorMs / 3_600_000).toFixed(1)} h): is transmitter on hugo publishing?` });
    }
    const cap = putCap(config, g.dMs);
    let lastBody: string | null = null;
    const write = async (force: boolean) => {
      const nowMs = deps.now();
      const body = buildPlaylist({ nowMs, horizon, fallback: inputs.fallback, offair: inputs.offair,
                                   offairSeqMs: deps.scheduledTime + config.loopMs }, config);
      // Ruling: off-air without a usable fallback writes the ENDLIST-only
      // playlist through the normal path below (cap and identical-bytes skip
      // apply), but stays loud: the notice is missing. Once per invocation.
      if (result.offairWithoutFallback === null) {
        const reason = offairWithoutFallback(inputs, horizon, nowMs, config);
        if (reason !== null) {
          result.offairWithoutFallback = reason;
          console.error(JSON.stringify({ event: "offair-without-fallback", reason, epoch_id: horizon.epoch_id,
                                         fallback_version: horizon.fallback_version, scheduled: deps.scheduledTime }));
          conditions.push({ key: "offair-without-fallback", priority: "high", resolvable: true,
                            title: "Off-air without a notice", message: reason });
        }
      }
      if (body === null) return;
      if (!force && body === lastBody) {
        result.skipped++;
        return;
      }
      if (result.puts >= cap) return;
      await bucket.put(LIVE_KEY, body, {
        httpMetadata: { contentType: "application/vnd.apple.mpegurl", cacheControl: `public, max-age=${config.liveMaxAge}` },
      });
      result.puts++;
      lastBody = body;
    };
    await write(true);
    const deadline = deps.scheduledTime + config.loopMs;
    while (result.puts < cap) {
      const now = deps.now();
      const next = startMs(g, indexAt(g, now) + 1);
      if (next > deadline) break;
      await deps.sleep(next - now + BOUNDARY_SLACK_MS);
      await write(false);
    }
    return result;
  } finally {
    await flush(); // after the last playlist write (or an early return), never before the guard
  }
}
```

`antenna/src/env.ts`:

```ts
import type { ClockEnv } from "./clock";
import type { GuardEnv } from "./guard";

/** Everything the Worker reads from its environment: wrangler vars, Worker
 * secrets (account details and tokens, never in the repo) and bindings. */
export interface AntennaEnv extends ClockEnv, GuardEnv {
  BUCKET: R2Bucket;
}
```

Replace `antenna/src/index.ts` with:

```ts
import { r2Bucket } from "./bucket";
import { type ClockResult, configFromEnv, runClock } from "./clock";
import type { AntennaEnv } from "./env";
import { guardConfigFromEnv, guardStep } from "./guard";

export default {
  async scheduled(controller, env, _ctx): Promise<void> {
    const started = Date.now();
    const bucket = r2Bucket(env.BUCKET);
    const now = () => Date.now();
    const fetchFn: typeof fetch = (input, init) => fetch(input, init);
    let result: ClockResult | undefined;
    let error: string | undefined;
    try {
      result = await runClock({
        bucket,
        now,
        sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
        scheduledTime: controller.scheduledTime,
        config: configFromEnv(env),
        guard: () => guardStep({ bucket, now, fetch: fetchFn, config: guardConfigFromEnv(env) }),
      });
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      throw e; // still a failed invocation in observability
    } finally {
      // One line per invocation, ALWAYS (including when runClock throws); the
      // phase-1 verification compares scheduled vs actual fire times (lagMs).
      console.log(JSON.stringify({ event: "clock", scheduled: controller.scheduledTime, started,
                                   lagMs: started - controller.scheduledTime, ...result, ...(error ? { error } : {}) }));
    }
  },
} satisfies ExportedHandler<AntennaEnv>;
```

Replace `antenna/wrangler.jsonc` with (no account details: the account comes from `CLOUDFLARE_ACCOUNT_ID` in the git-ignored `antenna/.env`, and secrets are set with `wrangler secret put` in Task 17; `BILLING_ANNIVERSARY_DAY` is a plain var, ruling R12):

```jsonc
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "antenna",
  "main": "src/index.ts",
  "compatibility_date": "2026-10-01",
  // Cron-only: no routes, no fetch handler, and no public URL. A routeless
  // Worker otherwise gets a public, billed *.workers.dev URL that the zone's
  // WAF kill switch cannot reach (spec "Architecture").
  "workers_dev": false,
  "preview_urls": false,
  "triggers": { "crons": ["* * * * *"] },
  // The bucket name must match transmitter's [publish] bucket.
  "r2_buckets": [{ "binding": "BUCKET", "bucket_name": "lma-radio" }],
  "vars": {
    "PLAYLIST_WINDOW": "6",
    "GRACE_SEGMENTS": "3",
    "OFFAIR_AFTER_SECONDS": "86400",
    "LOOP_SECONDS": "75",
    "LIVE_MAX_AGE": "5",
    "LEAD_FLOOR_HOURS": "16",
    // The cost guard (spec "Cost guard"). MONTHLY_BUDGET_USD includes the $5
    // Workers Paid base; the billing period starts on BILLING_ANNIVERSARY_DAY
    // at 00:00 UTC. Account details are Worker secrets, never here:
    // CF_ACCOUNT_ID, CF_ZONE_ID, CF_ANALYTICS_TOKEN, CF_WAF_TOKEN
    // (see docs/playout-setup.md).
    "MONTHLY_BUDGET_USD": "15",
    "BILLING_ANNIVERSARY_DAY": "11",
    "GUARD_EVAL_SECONDS": "900",
    "BLIND_AFTER_SECONDS": "21600",
    "KILL_SWITCH_DESCRIPTION": "station: kill switch"
  },
  // One log line per invocation (~1,440/day) stays inside the free allowance.
  "observability": { "enabled": true }
}
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npm test && npx tsc --noEmit`
Expected: PASS; no type errors. The `scheduled handler` test runs the **real** guard against the bound bucket with the wrangler vars and no secrets. It records the missing secrets in `state/guard.json` and makes no network call (both `meterProblems` and `wafProblems` short-circuit before any fetch). It is not blocked and writes the player `index.html`.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/clock.ts antenna/src/env.ts antenna/src/index.ts antenna/wrangler.jsonc antenna/test/clock.test.ts
git commit -m "feat(antenna): the clock runs the cost guard first; blocked drives index.html and the off-air playlist"
```

- [ ] **Step 6: Review gate (orchestrator).** The spend-critical path is complete. Report to the parent and list:
- each dispatch since the last report, with its model;
- the review verdicts for Tasks 1–8;
- any ruling taken.

Then continue with Task 9.

---
