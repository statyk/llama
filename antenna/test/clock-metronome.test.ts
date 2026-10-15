import { createExecutionContext, createScheduledController, env, reset, runInDurableObject,
         waitOnExecutionContext } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type AlertBatch, type ClockConfig, runClock } from "../src/clock";
import type { AlertCondition } from "../src/conditions";
import type { AntennaEnv } from "../src/env";
import type { GuardOutcome } from "../src/guard";
import worker from "../src/index";
import type { Metronome } from "../src/metronome";
import { type Lease, METRONOME_LEASE_MS, METRONOME_NAME, type MetronomeClient,
         type MetronomeStatus } from "../src/metronome-core";
import { fakeTime, MemoryBucket } from "./support";

const E = Date.parse("2026-10-10T12:00:00.000Z");
const D = 10_240;
const CFG: ClockConfig = { window: 6, grace: 3, offairAfterMs: 86_400_000, loopMs: 75_000, liveMaxAge: 5,
                           leadFloorMs: 16 * 3_600_000 };
const AT = E + 50 * D + 300;

const guardSays = (blocked: boolean | null, tripped = false) =>
  async (): Promise<GuardOutcome> => ({ blocked, tripped: blocked === null ? null : tripped,
                                        offair: blocked === null ? null : blocked && !tripped, doc: null, conditions: [] });

function horizonDoc(epochMs: number) {
  const iso = new Date(epochMs).toISOString();
  return { epoch_id: "e1", epoch: iso, d: 10.24, first: 0, last: 1_000_000, published_at: iso, container: "adts",
           fallback_version: "v1" };
}
const FALLBACK = { len: 7, notice: "fallback/v1/notice.aac" };

function station(bucket = new MemoryBucket()) {
  bucket.seed("state/horizon.json", horizonDoc(E));
  bucket.seed("fallback/v1/index.json", FALLBACK);
  return bucket;
}

const healthy = (s: Partial<MetronomeStatus> = {}): MetronomeStatus =>
  ({ applied: "accepted", lease: "play", wrote: true, lastAlarmGoodAt: AT, stalledMs: 0, stalls: 0, leaseVerdictAt: AT,
     ...s });

/** A metronome stand-in: records every lease it is sent and answers `answer(lease)`. */
function fakeMetronome(answer: (l: Lease | null) => MetronomeStatus | Promise<MetronomeStatus> =
                         (l) => healthy({ applied: l === null ? null : "accepted" })) {
  const sent: (Lease | null)[] = [];
  const client: MetronomeClient = { renew: async (l) => { sent.push(l); return answer(l); } };
  return { client, sent };
}

type Run = { r: Awaited<ReturnType<typeof runClock>> | null; error: unknown; batch: AlertBatch | null; keys: string[];
             bucket: MemoryBucket; clock: ReturnType<typeof fakeTime> };

async function run(o: { guard?: () => Promise<GuardOutcome>; bucket?: MemoryBucket; metronome?: MetronomeClient;
                        at?: number }): Promise<Run> {
  const bucket = o.bucket ?? station();
  const at = o.at ?? AT;
  const clock = fakeTime(at + 40);
  const out: Run = { r: null, error: null, batch: null, keys: [], bucket, clock };
  try {
    out.r = await runClock({ bucket, ...clock, scheduledTime: at, config: CFG, guard: o.guard ?? guardSays(false),
                             metronome: o.metronome,
                             alerts: async (cs: AlertCondition[], _n, b) => { out.keys = cs.map((c) => c.key); out.batch = b; } });
  } catch (e) {
    out.error = e;
  }
  return out;
}

const playlistPuts = (b: MemoryBucket) => b.puts("live.m3u8");

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the lease table: what cron passes to renew, by its own outcome", () => {
  it("guard unknown or crashed: renew(null), and the fallback never writes", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    for (const guard of [guardSays(null), async (): Promise<GuardOutcome> => { throw new Error("x"); }]) {
      const m = fakeMetronome(() => { throw new Error("dead"); }); // even with the DO dead
      const out = await run({ guard, metronome: m.client });
      expect(m.sent).toEqual([null]);
      expect(playlistPuts(out.bucket)).toBe(0);
      expect(out.keys).toContain("metronome-down");
    }
  });

  it("verdict known unblocked, inputs unusable (read threw, missing, unreadable, bad epoch): renew(null), no cron PUT", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const threw = station();
    threw.failGets.add("state/horizon.json");
    const missing = new MemoryBucket();
    const corrupt = new MemoryBucket();
    corrupt.seed("state/horizon.json", "{not json");
    const badEpoch = station();
    badEpoch.seed("state/horizon.json", { ...horizonDoc(E), epoch: "nonsense" });
    for (const bucket of [threw, missing, corrupt, badEpoch]) {
      const m = fakeMetronome(() => { throw new Error("dead"); });
      await run({ bucket, metronome: m.client });
      expect(m.sent).toEqual([null]);
      expect(playlistPuts(bucket)).toBe(0);
    }
  });

  it("verdict known blocked, inputs unusable: renew(hold), no cron PUT", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const threw = station();
    threw.failGets.add("state/horizon.json");
    const missing = new MemoryBucket();
    const badEpoch = station();
    badEpoch.seed("state/horizon.json", { ...horizonDoc(E), epoch: "nonsense" });
    for (const bucket of [threw, missing, badEpoch]) {
      const m = fakeMetronome(() => { throw new Error("dead"); });
      await run({ bucket, guard: guardSays(true, true), metronome: m.client });
      expect(m.sent).toEqual([{ kind: "hold", verdictAt: AT + 40, validUntil: AT + 40 + METRONOME_LEASE_MS }]);
      expect(playlistPuts(bucket)).toBe(0);
    }
  });

  it("horizon refused: renew(hold) blocked or not, no cron PUT", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    for (const guard of [guardSays(false), guardSays(true, true)]) {
      const bucket = station();
      bucket.seed("state/horizon.json", { ...horizonDoc(E), d: 1 });
      const m = fakeMetronome(() => { throw new Error("dead"); });
      await run({ bucket, guard, metronome: m.client });
      expect(m.sent.map((l) => l?.kind)).toEqual(["hold"]);
      expect(playlistPuts(bucket)).toBe(0);
    }
  });

  it("verdict known, horizon accepted: a play lease with the verdict, horizon and fallback, ordered by the guard's start", async () => {
    for (const blocked of [false, true]) {
      const m = fakeMetronome();
      const clock = fakeTime(AT + 40);
      await runClock({ bucket: station(), ...clock, scheduledTime: AT, config: CFG, metronome: m.client,
                       guard: async () => { await clock.sleep(2_000); return guardSays(blocked, blocked)(); } });
      expect(m.sent).toEqual([{ kind: "play", verdictAt: AT + 40, validUntil: AT + 2_040 + METRONOME_LEASE_MS,
                                blocked, horizon: horizonDoc(E), fallback: FALLBACK }]);
    }
  });

  it("renews exactly once per invocation, on every path", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const refused = station();
    refused.seed("state/horizon.json", { ...horizonDoc(E), d: 1 });
    const threw = station();
    threw.failGets.add("state/horizon.json");
    const cases = [{ guard: guardSays(null) }, { bucket: new MemoryBucket() }, { bucket: refused }, { bucket: threw },
                   {}, { guard: guardSays(true, true) }];
    for (const c of cases) {
      const m = fakeMetronome();
      await run({ ...c, metronome: m.client });
      expect(m.sent).toHaveLength(1);
    }
  });
});

describe("a healthy metronome", () => {
  it("cron writes no playlist, the batch is complete, the clock line carries the status", async () => {
    const m = fakeMetronome();
    const out = await run({ metronome: m.client });
    expect(playlistPuts(out.bucket)).toBe(0);
    expect(out.batch).toEqual({ complete: true, guardComplete: true });
    expect(out.r!.metronome).toEqual({ sent: "play", status: healthy(), error: null, fallback: null });
    expect(out.keys).not.toContain("metronome-down");
  });

  it("a blocked lease that the DO wrote: no cron PUT either", async () => {
    const m = fakeMetronome(() => healthy({ lease: "blocked" }));
    const out = await run({ guard: guardSays(true, true), metronome: m.client });
    expect(m.sent[0]).toMatchObject({ kind: "play", blocked: true });
    expect(playlistPuts(out.bucket)).toBe(0);
  });

  it("guard unknown with a healthy renew(null) stays incomplete: no guard-family key resolves", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const out = await run({ guard: guardSays(null), metronome: fakeMetronome().client });
    expect(out.batch).toEqual({ complete: false, guardComplete: false });
  });

  it("offair-without-fallback is raised by cron from its own inputs even though the DO writes", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    bucket.seed("state/horizon.json", horizonDoc(E)); // no fallback index
    // A healthy DO answers a blocked play lease with lease "blocked" (fallbackReason (b) checks it).
    const out = await run({ bucket, guard: guardSays(true, true),
                            metronome: fakeMetronome(() => healthy({ lease: "blocked" })).client });
    expect(out.keys).toContain("offair-without-fallback");
    expect(out.keys).not.toContain("metronome-down");
    expect(out.r!.offairWithoutFallback).toMatch(/ENDLIST-only/);
    expect(playlistPuts(bucket)).toBe(0);
  });

  it("a single stall: no fallback, no alert, stalledMs on the clock line", async () => {
    const out = await run({ metronome: fakeMetronome(() => healthy({ stalls: 1, stalledMs: 41_000 })).client });
    expect(playlistPuts(out.bucket)).toBe(0);
    expect(out.keys).not.toContain("metronome-down");
    expect(out.r!.metronome!.status!.stalledMs).toBe(41_000);
  });

  it("superseded: no fallback (the DO keeps a newer lease)", async () => {
    const out = await run({ metronome: fakeMetronome(() => healthy({ applied: "superseded", wrote: null })).client });
    expect(playlistPuts(out.bucket)).toBe(0);
    expect(out.keys).not.toContain("metronome-down");
  });
});

describe("the fallback: cron's own loop, and metronome-down", () => {
  const triggers: [string, () => MetronomeStatus | Promise<MetronomeStatus>][] = [
    ["(a) renew throws", () => { throw new Error("RPC failed"); }],
    ["(b) invalid", () => healthy({ applied: "invalid", lease: "none", wrote: null })],
    ["(b) off (version skew)", () => healthy({ applied: "off", lease: "none", wrote: null })],
    ["(b) wrote false", () => healthy({ wrote: false })],
    ["(c) stalls >= 2", () => healthy({ stalls: 2, stalledMs: 70_000 })],
  ];
  for (const [what, answer] of triggers) {
    it(`${what}: the legacy loop runs (as many PUTs as today), metronome-down is raised, the batch is complete`, async () => {
      vi.spyOn(console, "error").mockImplementation(() => {});
      const out = await run({ metronome: fakeMetronome(answer).client });
      expect(out.r!.puts).toBe(8); // immediate + boundaries 51..57, exactly the off-mode count
      expect(out.keys).toContain("metronome-down");
      expect(out.r!.metronome!.fallback).toEqual(expect.any(String));
      expect(out.batch).toEqual({ complete: true, guardComplete: true });
    });
  }

  it("a blocked lease the DO did not write: cron writes the off-air playlist", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const out = await run({ guard: guardSays(true, true),
                            metronome: fakeMetronome(() => healthy({ lease: "blocked", wrote: false })).client });
    expect(playlistPuts(out.bucket)).toBe(1);
    expect(out.bucket.objects.get("live.m3u8")!.body).toContain("#EXT-X-ENDLIST");
  });

  it("a hold the DO did not answer: metronome-down, but the fallback never writes", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = station();
    bucket.seed("state/horizon.json", { ...horizonDoc(E), d: 1 });
    const out = await run({ bucket, metronome: fakeMetronome(() => { throw new Error("dead"); }).client });
    expect(out.keys).toEqual(expect.arrayContaining(["horizon-refused", "metronome-down"]));
    expect(playlistPuts(bucket)).toBe(0);
  });
});

describe("scheduled handler with the metronome", () => {
  const noSecrets = (metronome: string) =>
    ({ ...env, METRONOME: metronome, LOOP_SECONDS: "0", CF_ACCOUNT_ID: undefined, CF_ZONE_ID: undefined,
       CF_ANALYTICS_TOKEN: undefined, CF_WAF_TOKEN: undefined, NTFY_URL: undefined, NTFY_TOKEN: undefined,
       ALERT_EMAIL: undefined, ALERT_EMAIL_FROM: undefined, ALERT_EMAIL_TO: undefined }) as unknown as AntennaEnv;
  const e = env as unknown as AntennaEnv;
  const clockLine = (spy: { mock: { calls: unknown[][] } }) =>
    spy.mock.calls.map((c) => { try { return JSON.parse(String(c[0])); } catch { return null; } })
      .find((o) => o?.event === "clock");
  const seed = async () => {
    // 3 s into a segment, so the DO's first alarm is ~7 s away and cannot race the test.
    await e.BUCKET.put("state/horizon.json", JSON.stringify(horizonDoc(Date.now() - 100 * D - 3_000)));
    await e.BUCKET.put("fallback/v1/index.json", JSON.stringify(FALLBACK));
  };
  const fire = async (environment: AntennaEnv) => {
    const ctx = createExecutionContext();
    await worker.scheduled!(createScheduledController({ scheduledTime: Date.now(), cron: "* * * * *" }), environment, ctx);
    await waitOnExecutionContext(ctx);
  };

  afterEach(async () => {
    await reset();
  });

  it("METRONOME on, the DO on too: the DO writes live.m3u8, cron does not, the clock line has the status", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in tests"));
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    await seed();
    await runInDurableObject(e.METRONOME_DO.get(e.METRONOME_DO.idFromName(METRONOME_NAME)), (o: Metronome) => {
      const self = o as unknown as { env: AntennaEnv };
      self.env = { ...self.env, METRONOME: "on" };
    });
    await fire(noSecrets("on"));
    const line = clockLine(log);
    expect(line.puts).toBe(0);
    expect(line.metronome).toMatchObject({ sent: "play", status: { applied: "accepted", wrote: true }, fallback: null });
    expect(await (await e.BUCKET.get("live.m3u8"))!.text()).toContain("seg/e1/");
  });

  it("METRONOME on for cron but off in the DO (version skew): cron falls back and raises metronome-down", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in tests"));
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    await seed();
    await fire(noSecrets("on"));
    const line = clockLine(log);
    expect(line.metronome).toMatchObject({ status: { applied: "off" }, fallback: expect.stringMatching(/applied=off/) });
    expect(line.puts).toBe(1);
    expect(line.alerts).toContain("metronome-down");
  });

  it("METRONOME off (as committed): cron's loop exactly as before, no renew", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in tests"));
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    await seed();
    await fire(noSecrets(String(e.METRONOME)));
    const line = clockLine(log);
    expect(line.metronome).toBeNull();
    expect(line.puts).toBe(1);
  });
});
