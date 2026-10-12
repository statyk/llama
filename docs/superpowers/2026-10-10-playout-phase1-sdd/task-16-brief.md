### Task 16: antenna clock loop and the Worker entry

**Model hint:** opus

**Files:**
- Create: `antenna/src/clock.ts`
- Modify: `antenna/src/index.ts`
- Create: `antenna/test/clock.test.ts`

**Interfaces:**
- Consumes: Task 15's `gridOf/indexAt/startMs`, `buildPlaylist`, `FallbackIndex`, `PlaylistConfig`, `Horizon`.
- Produces: `interface StoredObject { text() }`; `interface BucketLike { get(key); put(key, value: string, { httpMetadata: { contentType, cacheControl } }) }`; `r2Bucket(b: R2Bucket) -> BucketLike`; `interface ClockConfig extends PlaylistConfig { loopMs; liveMaxAge }`; `interface ClockEnv` (string vars); `configFromEnv(env) -> ClockConfig`; `interface ClockDeps { bucket; now; sleep; scheduledTime; config; guard? }`; `guardStep(deps)` (**phase-2 seam, a no-op**); `readInputs(bucket) -> { horizon, fallback, offair }`; `putCap(cfg, dMs) -> number`; `runClock(deps) -> { puts, skipped }`; `LIVE_KEY = "live.m3u8"`.

- [ ] **Step 1: Write the failing tests**

`antenna/test/clock.test.ts`:

```ts
import { createExecutionContext, createScheduledController, env, waitOnExecutionContext } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { type BucketLike, type ClockConfig, configFromEnv, putCap, r2Bucket, runClock } from "../src/clock";
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
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/clock.test.ts`
Expected: FAIL — cannot resolve `../src/clock`.

- [ ] **Step 3: Implement `clock.ts` and the Worker entry**

`antenna/src/clock.ts`:

```ts
import { type Horizon, gridOf, indexAt, startMs } from "./grid";
import { buildPlaylist, type FallbackIndex, type PlaylistConfig } from "./playlist";

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

export interface ClockConfig extends PlaylistConfig {
  loopMs: number;
  liveMaxAge: number;
}

export interface ClockEnv {
  PLAYLIST_WINDOW?: string;
  GRACE_SEGMENTS?: string;
  OFFAIR_AFTER_SECONDS?: string;
  LOOP_SECONDS?: string;
  LIVE_MAX_AGE?: string;
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
    liveMaxAge: Math.floor(num(env.LIVE_MAX_AGE, 5)),
  };
}

export interface ClockDeps {
  bucket: BucketLike;
  now: () => number;
  sleep: (ms: number) => Promise<void>;
  scheduledTime: number;
  config: ClockConfig;
  guard?: (deps: ClockDeps) => Promise<void>;
}

export interface ClockResult {
  puts: number;
  skipped: number;
}

export const LIVE_KEY = "live.m3u8";
const BOUNDARY_SLACK_MS = 25;

/**
 * Phase-2 seam. The cost guard runs here, first in every invocation and in
 * its own try/finally: it evaluates usage when state/guard.json is >= 15 min
 * old, applies the blind rule, and reconciles the blocked state (tripped OR
 * offair: ENDLIST playlist, off-air index.html, WAF kill switch) before any
 * playlist work. Phase 1 honours only a hand-written state/offair.json, which
 * readInputs reads; this is deliberately a no-op.
 */
export async function guardStep(_deps: ClockDeps): Promise<void> {}

export interface ClockInputs {
  horizon: Horizon | null;
  fallback: FallbackIndex | null;
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

/** state/ is read once per invocation, via the binding (never through the cache). */
export async function readInputs(bucket: BucketLike): Promise<ClockInputs> {
  const horizon = await readJson<Horizon>(bucket, "state/horizon.json");
  const offairDoc = await readJson<{ offair?: unknown }>(bucket, "state/offair.json");
  const fallback = horizon?.fallback_version
    ? await readJson<FallbackIndex>(bucket, `fallback/${horizon.fallback_version}/index.json`)
    : null;
  return { horizon, fallback, offair: offairDoc?.offair === true };
}

export function putCap(cfg: ClockConfig, dMs: number): number {
  return Math.ceil(cfg.loopMs / dMs) + 2;
}

/**
 * One cron invocation: write the current playlist immediately, then rewrite it
 * at every grid boundary E + N*d until scheduledTime + loopMs. Only CPU time is
 * billed, so the waiting is free. Overlapping invocations are harmless: the
 * playlist is a pure function of the clock and the inputs.
 */
export async function runClock(deps: ClockDeps): Promise<ClockResult> {
  await (deps.guard ?? guardStep)(deps);
  const { bucket, config } = deps;
  const inputs = await readInputs(bucket);
  const result: ClockResult = { puts: 0, skipped: 0 };
  const horizon = inputs.horizon;
  if (horizon === null) return result;
  const g = gridOf(horizon);
  const cap = putCap(config, g.dMs);
  let lastBody: string | null = null;
  const write = async (force: boolean) => {
    const body = buildPlaylist({ nowMs: deps.now(), horizon, fallback: inputs.fallback, offair: inputs.offair,
                                 offairSeqMs: deps.scheduledTime + config.loopMs }, config);
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
}
```

`antenna/src/index.ts` (replaces the placeholder):

```ts
import { configFromEnv, r2Bucket, runClock } from "./clock";

export default {
  async scheduled(controller, env, _ctx): Promise<void> {
    const started = Date.now();
    const result = await runClock({
      bucket: r2Bucket(env.BUCKET),
      now: () => Date.now(),
      sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
      scheduledTime: controller.scheduledTime,
      config: configFromEnv(env),
    });
    // One line per invocation; the phase-1 verification compares scheduled vs
    // actual fire times (lagMs) over a day from these.
    console.log(JSON.stringify({ event: "clock", scheduled: controller.scheduledTime, started,
                                 lagMs: started - controller.scheduledTime, ...result }));
  },
} satisfies ExportedHandler<Env>;
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npx vitest run && npx tsc --noEmit`
Expected: PASS, no type errors.

Run: `cd antenna && npx wrangler deploy --dry-run --outdir .wrangler/dry-run`
Expected: bundles successfully and lists the `BUCKET` binding; no routes. (The dry run does not print triggers: check that `antenna/wrangler.jsonc` has `"triggers": { "crons": ["* * * * *"] }`.)

- [ ] **Step 5: Commit**

```bash
git add antenna
git commit -m "feat(antenna): cron clock writes live.m3u8 at every grid boundary (PUT cap, identical skip, guard seam)"
```

---

