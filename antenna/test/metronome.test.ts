import { env, evictDurableObject, listDurableObjectIds, reset, runDurableObjectAlarm,
         runInDurableObject } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AntennaEnv } from "../src/env";
import { type Lease, METRONOME_LEASE_MS, METRONOME_NAME, STORAGE_KEYS } from "../src/metronome-core";
import { type Metronome, metronomeClient } from "../src/metronome";

const D = 10_240;
const e = env as unknown as AntennaEnv;
const stub = () => e.METRONOME_DO.get(e.METRONOME_DO.idFromName(METRONOME_NAME));

/** The test env carries wrangler.jsonc's committed METRONOME, which the
 * rollout flips; tests never rely on it and set this instance's env
 * explicitly, as a deploy of the var would. Lasts until the object is evicted
 * or reset. */
const setSwitch = (value: string) =>
  runInDurableObject(stub(), (o: Metronome) => {
    const self = o as unknown as { env: AntennaEnv };
    self.env = { ...self.env, METRONOME: value };
  });

/** A play lease 3 s into a segment, so the alarm it arms is ~7 s away: the
 * runtime fires real alarms on time, and one 25 ms away would race the test. */
function playLease(nowMs: number): Lease {
  const epoch = new Date(nowMs - 100 * D - 3_000).toISOString();
  return { kind: "play", verdictAt: nowMs, validUntil: nowMs + METRONOME_LEASE_MS, blocked: false,
           horizon: { epoch_id: "e1", epoch, d: 10.24, first: 0, last: 1_000_000, published_at: epoch, container: "adts",
                      fallback_version: "v1" },
           fallback: { len: 7, notice: "fallback/v1/notice.aac" } };
}

const storedKeys = () =>
  runInDurableObject(stub(), async (_o: Metronome, state) => [...(await state.storage.list()).keys()].sort());
const pendingAlarm = () => runInDurableObject(stub(), (_o: Metronome, state) => state.storage.getAlarm());
const alarmTimes = () => runInDurableObject(stub(), (_o: Metronome, state) => state.storage.get<number[]>("alarmTimes"));

afterEach(async () => {
  vi.restoreAllMocks();
  await reset(); // storage, alarms, R2 and instances: DO storage is not isolated per test otherwise
});

describe("the Metronome Durable Object", () => {
  it("off: renew answers off, arms nothing, stores nothing", async () => {
    await setSwitch("off");
    const st = await stub().renew(playLease(Date.now()));
    expect(st.applied).toBe("off");
    expect(await pendingAlarm()).toBeNull();
    expect(await storedKeys()).toEqual([]);
    expect(await e.BUCKET.get("live.m3u8")).toBeNull();
  });

  it("on: renew writes live.m3u8 through the R2 binding, stores within the fixed key set and arms the alarm", async () => {
    await setSwitch("on");
    const st = await stub().renew(playLease(Date.now()));
    expect(st).toMatchObject({ applied: "accepted", lease: "play", wrote: true });
    const obj = await e.BUCKET.get("live.m3u8");
    expect(obj!.httpMetadata).toMatchObject({ contentType: "application/vnd.apple.mpegurl",
                                              cacheControl: "public, max-age=5" });
    expect(await obj!.text()).toContain("seg/e1/");
    expect(await pendingAlarm()).toEqual(expect.any(Number));
    for (const k of await storedKeys()) expect(STORAGE_KEYS as readonly string[]).toContain(k);
  });

  it("the alarm ticks and re-arms; a full cycle stores exactly the fixed key set", async () => {
    const logs = vi.spyOn(console, "error").mockImplementation(() => {});
    await setSwitch("on");
    const s = stub();
    await s.renew(playLease(Date.now()));
    const armed = await pendingAlarm();
    expect(await runDurableObjectAlarm(s)).toBe(true);
    // runDurableObjectAlarm deletes the alarm before calling alarm(), so this pins only the engine's
    // genuine-delivery branch (re-arm, not duplicate); the next test lets the runtime deliver the alarm itself.
    expect(await pendingAlarm()).toBeGreaterThan(armed!);
    expect(logs.mock.calls.flat().join("\n")).not.toContain("metronome-duplicate");
    // A stall (no alarm-confirmed tick for > 30 s): the next renew counts it.
    await runInDurableObject(s, (_o: Metronome, state) => state.storage.put("lastAlarmGoodAt", Date.now() - 60_000));
    await runInDurableObject(s, (_o: Metronome, state) => state.storage.put("playSince", Date.now() - 60_000));
    expect((await s.renew(null)).stalls).toBe(1);
    expect(await storedKeys()).toEqual([...STORAGE_KEYS].sort());
  });

  it("a genuine delivery (the runtime's own, not runDurableObjectAlarm) sees no pending alarm: counted, re-armed later, never a duplicate", async () => {
    const logs = vi.spyOn(console, "error").mockImplementation(() => {});
    const seen: (number | null)[] = [];
    await runInDurableObject(stub(), (o: Metronome, state) => {
      const self = o as unknown as { env: AntennaEnv };
      self.env = { ...self.env, METRONOME: "on" };
      // The engine's port calls this same storage object: record what getAlarm() answers inside alarm().
      const real = state.storage.getAlarm.bind(state.storage);
      vi.spyOn(state.storage, "getAlarm").mockImplementation(async () => { const v = await real(); seen.push(v); return v; });
    });
    const now = Date.now();
    const epoch = new Date(now - 100 * D - (D - 600)).toISOString(); // 600 ms before boundary 101
    const lease: Lease = { kind: "play", verdictAt: now, validUntil: now + METRONOME_LEASE_MS, blocked: false,
                           horizon: { epoch_id: "e1", epoch, d: 10.24, first: 0, last: 1_000_000, published_at: epoch,
                                      container: "adts", fallback_version: "v1" },
                           fallback: { len: 7, notice: "fallback/v1/notice.aac" } };
    expect((await stub().renew(lease)).applied).toBe("accepted");
    const armed = await pendingAlarm();
    expect(armed).toBeGreaterThan(now);
    expect(armed).toBeLessThan(now + 1_000);
    seen.length = 0;
    // alarmTimes is recorded only on the genuine path (a duplicate is not counted).
    await vi.waitFor(async () => expect((await alarmTimes())?.length ?? 0).toBeGreaterThanOrEqual(1),
                     { timeout: 5_000, interval: 50 });
    expect(seen).toEqual([null]); // the one getAlarm() inside alarm() answered null
    expect(await pendingAlarm()).toBeGreaterThan(armed!);
    expect(logs.mock.calls.flat().join("\n")).not.toContain("metronome-duplicate");
  }, 10_000); // over waitFor's 5 s, so a slow delivery fails with waitFor's message, not the test timeout

  it("state lives in storage: after eviction (as at a deploy) the lease and the pending alarm are still there", async () => {
    await setSwitch("on");
    await stub().renew(playLease(Date.now()));
    const armed = await pendingAlarm();
    await evictDurableObject(stub());
    expect(await pendingAlarm()).toBe(armed);
    await setSwitch("on"); // the override was memory only
    expect((await stub().renew(null)).lease).toBe("play");
    expect(await runDurableObjectAlarm(stub())).toBe(true);
    expect(await pendingAlarm()).toEqual(expect.any(Number)); // the chain goes on
  });

  it("switched off with an alarm pending: the alarm writes nothing and is not re-armed", async () => {
    await setSwitch("on");
    const s = stub();
    await s.renew(playLease(Date.now()));
    await e.BUCKET.delete("live.m3u8");
    await setSwitch("off");
    expect(await runDurableObjectAlarm(s)).toBe(true);
    expect(await pendingAlarm()).toBeNull();
    expect(await e.BUCKET.get("live.m3u8")).toBeNull();
  });

  it("only the exact string \"on\" enables it", async () => {
    for (const v of ["On", "on ", "1", "true", ""]) {
      await setSwitch(v);
      expect((await stub().renew(playLease(Date.now()))).applied).toBe("off");
    }
  });
});

describe("metronomeClient", () => {
  it("addresses the single instance by its fixed name", async () => {
    await setSwitch("on");
    const client = metronomeClient(e.METRONOME_DO);
    await client.renew(playLease(Date.now()));
    await client.renew(null);
    const ids = await listDurableObjectIds(e.METRONOME_DO);
    expect(ids).toHaveLength(1);
    expect(ids[0].equals(e.METRONOME_DO.idFromName("metronome"))).toBe(true);
  });

  it("asks idFromName for \"metronome\" and nothing else", async () => {
    const names: string[] = [];
    const ns = { idFromName: (n: string) => { names.push(n); return {} as DurableObjectId; },
                 get: () => ({ renew: async () => ({ applied: null }) }) };
    await metronomeClient(ns).renew(null);
    expect(names).toEqual(["metronome"]);
  });

  it("a missing binding rejects inside renew (cron's trigger a), never at construction", async () => {
    const client = metronomeClient(undefined);
    await expect(client.renew(null)).rejects.toThrow(/METRONOME_DO binding is missing/);
  });

  it("a renew that does not answer within the timeout rejects", async () => {
    const ns = { idFromName: () => ({}) as DurableObjectId, get: () => ({ renew: () => new Promise(() => {}) }) };
    await expect(metronomeClient(ns, 20).renew(null)).rejects.toThrow(/renew timed out after 20 ms/);
  });
});
