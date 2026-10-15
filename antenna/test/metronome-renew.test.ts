import { describe, expect, it } from "vitest";
import { ALARM_SLACK_MS, fallbackReason, holdLease, METRONOME_LEASE_MS, STORAGE_KEYS } from "../src/metronome-core";
import { CFG, D, E, engineAt, HORIZON, lastListed, lease, seqOf, settle } from "./metronome-support";

const T = E + 1_000 * D + 3_000; // 3 s into segment 1000

describe("renew: the switch", () => {
  it("off: deletes the alarm, writes and stores nothing, answers applied off", async () => {
    const { port, engine } = engineAt(T);
    port.on = false;
    port.alarmAt = T + 5_000;
    const st = await engine.renew(lease(T));
    expect(st).toEqual({ applied: "off", lease: "none", wrote: null, lastAlarmGoodAt: null, stalledMs: 0, stalls: 0,
                         leaseVerdictAt: null });
    expect(port.alarmAt).toBeNull();
    expect(port.puts()).toBe(0);
    expect(port.store.size).toBe(0);
  });
});

describe("renew: a play lease", () => {
  it("accepts, writes the live playlist at once, arms the next boundary, records playSince", async () => {
    const { port, engine } = engineAt(T);
    const st = await engine.renew(lease(T));
    expect(st).toMatchObject({ applied: "accepted", lease: "play", wrote: true, stalledMs: 0, stalls: 0,
                               leaseVerdictAt: T, lastAlarmGoodAt: null });
    expect(port.puts()).toBe(1);
    expect(port.body()).toContain("seg/e1/1012.aac"); // 1000 + lookahead 12
    expect(port.alarmAt).toBe(E + 1_001 * D + ALARM_SLACK_MS);
    expect(port.store.get("lastTarget")).toBe(port.alarmAt);
    expect(port.store.get("playSince")).toBe(T);
    expect(port.store.get("lastBody")).toBe(port.body());
    for (const k of port.store.keys()) expect(STORAGE_KEYS as readonly string[]).toContain(k);
  });

  it("renew(null) leaves the lease untouched and still writes from a current play lease", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    port.t = T + 2 * D;
    const st = await engine.renew(null);
    expect(st).toMatchObject({ applied: null, lease: "play", wrote: true, leaseVerdictAt: T });
    expect(port.puts()).toBe(2);
  });

  it("an identical body is not written again (wrote null), and is not a failure", async () => {
    const { port, engine } = engineAt(T);
    const l = lease(T);
    await engine.renew(l);
    const st = await engine.renew(lease(T + 1, { verdictAt: T + 1 }));
    expect(st).toMatchObject({ applied: "accepted", wrote: null });
    expect(port.puts()).toBe(1);
    expect(fallbackReason(l, { status: st })).toBeNull();
  });

  it("does not re-arm when an alarm is already pending", async () => {
    const { port, engine } = engineAt(T);
    port.alarmAt = T + 999;
    await engine.renew(lease(T));
    expect(port.alarmAt).toBe(T + 999);
  });
});

describe("renew: validation", () => {
  it("an invalid lease is applied invalid: logged, the stored lease and the alarm deleted, nothing written", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    expect(port.alarmAt).not.toBeNull();
    port.t = T + 1_000;
    port.ops.length = 0;
    const st = await engine.renew(lease(T + 1_000, { horizon: { d: 10.25 } }));
    expect(st).toMatchObject({ applied: "invalid", lease: "none", wrote: null, leaseVerdictAt: null });
    expect(port.ops).toContain("save lease,stalls"); // stalls saved even unchanged (0 -> 0): every renew writes a row
    expect(port.store.has("lease")).toBe(false);
    expect(port.alarmAt).toBeNull();
    expect(port.puts()).toBe(1);
    expect(port.events("metronome-lease-invalid")).toEqual([expect.objectContaining({ source: "renew" })]);
  });

  it("an unparseable stored lease is deleted on load: no write, no re-arm", async () => {
    const { port, engine } = engineAt(T);
    port.store.set("lease", "{not json");
    port.alarmAt = T + 5_000;
    const st = await engine.renew(null);
    expect(st).toMatchObject({ applied: null, lease: "none", wrote: null });
    expect(port.store.has("lease")).toBe(false);
    expect(port.alarmAt).toBeNull();
    expect(port.puts()).toBe(0);
    expect(port.events("metronome-lease-invalid")).toEqual([expect.objectContaining({ source: "storage" })]);
  });

  it("a stored lease that no longer validates (say, after a deploy) is deleted, and the fresh one is accepted", async () => {
    const { port, engine } = engineAt(T);
    port.store.set("lease", JSON.stringify({ ...lease(T - 60_000), horizon: { ...HORIZON, d: 1 }, expiresAt: T + 1 }));
    const st = await engine.renew(lease(T));
    expect(st).toMatchObject({ applied: "accepted", lease: "play", wrote: true });
  });

  it("a malformed fallback plays as no usable fallback, not an invalid lease", async () => {
    const { port, engine } = engineAt(T);
    const st = await engine.renew(lease(T, { fallback: { len: "7" } }));
    expect(st.applied).toBe("accepted");
    expect(port.body()).toContain("seg/e1/1012.aac"); // on air inside the horizon: no loop entry needed
  });
});

describe("renew: ordering", () => {
  it("an older or equal unblocked play lease is superseded (logged once), the newer one stays", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    for (const v of [T - 1, T, T - 2]) {
      const st = await engine.renew(lease(T, { verdictAt: v }));
      expect(st).toMatchObject({ applied: "superseded", lease: "play", leaseVerdictAt: T });
    }
    expect(port.events("metronome-lease-superseded").length).toBeGreaterThanOrEqual(1);
    expect(port.events("metronome-lease-superseded").length).toBeLessThanOrEqual(3);
  });

  it("a lagging older blocked lease is accepted (fail-closed) until a newer unblocked one", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    expect((await engine.renew(lease(T, { verdictAt: T - 60_000, blocked: true }))).lease).toBe("blocked");
    // older than the blocked lease now current: superseded, the DO stays blocked
    expect((await engine.renew(lease(T, { verdictAt: T - 90_000 }))).applied).toBe("superseded");
    expect((await engine.renew(lease(T, { verdictAt: T + 60_000 }))).lease).toBe("play");
    expect(port.alarmAt).not.toBeNull();
  });
});

describe("renew: blocked, hold, expiry", () => {
  it("blocked: writes the off-air notice, leaves no alarm pending", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    const st = await engine.renew(lease(T + 1, { verdictAt: T + 1, blocked: true }));
    expect(st).toMatchObject({ applied: "accepted", lease: "blocked", wrote: true });
    expect(port.body()).toContain("fallback/v1/notice.aac");
    expect(port.body()).toContain("#EXT-X-ENDLIST");
    expect(port.alarmAt).toBeNull();
  });

  it("the notice is numbered above every live segment listed and never decreases across renews", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    const live = port.body()!;
    const seqs: number[] = [];
    for (let i = 1; i <= 4; i++) {
      port.t = T + i * 60_000;
      await engine.renew(lease(port.t, { blocked: true }));
      seqs.push(seqOf(port.body()!));
    }
    expect(seqs[0]).toBeGreaterThan(lastListed(live));
    // indexAt(now + 75 s) + lookahead + 1, above indexAt(now) + lookahead
    expect(seqs[0]).toBeGreaterThan(Math.floor((T + 60_000 - E) / D) + CFG.lookahead!);
    expect([...seqs].sort((a, b) => a - b)).toEqual(seqs);
    expect(port.puts()).toBe(5); // about one PUT per minute while blocked, as today
  });

  it("hold: no PUT, no pending alarm, logged once", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    for (const dt of [1, 2]) {
      port.t = T + dt * 60_000;
      const st = await engine.renew(holdLease(port.t, port.t));
      expect(st).toMatchObject({ applied: "accepted", lease: "hold", wrote: null });
    }
    expect(port.puts()).toBe(1);
    expect(port.alarmAt).toBeNull();
    expect(port.events("metronome-hold")).toHaveLength(1);
  });

  it("expiry: past 15 min the DO writes nothing and disarms; a new lease restarts it", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T, { verdictAt: T }));
    port.t = T + METRONOME_LEASE_MS;
    const st = await engine.renew(null);
    expect(st).toMatchObject({ applied: null, lease: "none", wrote: null, stalledMs: 0 });
    expect(port.alarmAt).toBeNull();
    expect(port.puts()).toBe(1);
    expect(port.events("metronome-expired")).toHaveLength(1);
    const again = await engine.renew(lease(port.t));
    expect(again).toMatchObject({ applied: "accepted", lease: "play", wrote: true });
    expect(port.alarmAt).not.toBeNull();
    expect(port.store.get("playSince")).toBe(port.t);
  });

  it("renew(null) and a superseded lease never extend it: 15 min after acceptance nothing is written or armed", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    for (const min of [5, 10]) {
      port.t = T + min * 60_000;
      expect((await engine.renew(null)).lease).toBe("play");
    }
    port.t = T + 12 * 60_000;
    expect((await engine.renew(lease(port.t, { verdictAt: T }))).applied).toBe("superseded");
    port.t = T + METRONOME_LEASE_MS;
    const puts = port.puts();
    expect(await engine.renew(null)).toMatchObject({ lease: "none", wrote: null });
    expect(port.puts()).toBe(puts);
    expect(port.alarmAt).toBeNull();
  });

  it("a far-future validUntil still expires 15 min after acceptance", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew({ ...lease(T), validUntil: T + 86_400_000 });
    port.t = T + METRONOME_LEASE_MS;
    expect((await engine.renew(null)).lease).toBe("none");
  });
});

describe("renew: stalls", () => {
  it("renew's own write never confirms a tick: two renews over a dead chain count 1 then 2", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    port.alarmAt = null; // the chain broke silently
    port.t = T + 40_000;
    const one = await engine.renew(lease(port.t));
    expect(one).toMatchObject({ stalls: 1, stalledMs: 40_000, wrote: true });
    expect(one.lastAlarmGoodAt).toBeNull();
    expect(fallbackReason(lease(port.t), { status: one })).toBeNull(); // a single stall: no fallback
    // ... that renew re-armed, but the alarm never comes either:
    port.alarmAt = null;
    port.t = T + 80_000;
    const two = await engine.renew(lease(port.t));
    expect(two).toMatchObject({ stalls: 2, stalledMs: 80_000 });
    expect(fallbackReason(lease(port.t), { status: two })).toMatch(/stalled on 2/);
  });

  it("counts from playSince when the play lease is newer than the last alarm tick", async () => {
    const { port, engine } = engineAt(T);
    port.store.set("lastAlarmGoodAt", T - 600_000);
    await engine.renew(lease(T)); // first play lease: playSince = T
    port.t = T + 20_000;
    expect((await engine.renew(null)).stalledMs).toBe(20_000);
  });

  it("every renew writes stalls, unchanged or not, so a healthy DO writes a row every minute", async () => {
    const absent = engineAt(T);
    await absent.engine.renew(null);
    expect(absent.port.ops).toEqual(["save stalls"]);
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    port.t = T + METRONOME_LEASE_MS; // expired
    port.ops.length = 0;
    await engine.renew(null);
    expect(port.ops).toEqual(["deleteAlarm", "save stalls"]);
  });

  it("is 0, and resets the count, when the stored lease was not live", async () => {
    const { port, engine } = engineAt(T);
    port.store.set("stalls", 5);
    const st = await engine.renew(holdLease(T, T));
    expect(st).toMatchObject({ stalledMs: 0, stalls: 0 });
  });
});

describe("renew: the PUT cap and the PUT timeout", () => {
  it("the 11th write in 60 s is skipped and logged; a cap-skipped write is wrote null, not a failure", async () => {
    const { port, engine } = engineAt(T);
    // A flapping verdict: blocked and unblocked leases alternate, so every body differs.
    const flap = (i: number) => lease(T + i * 1_000, { blocked: i % 2 === 0, verdictAt: T + i });
    const statuses = [];
    for (let i = 0; i < 11; i++) {
      port.t = T + i * 1_000;
      statuses.push(await engine.renew(flap(i)));
    }
    expect(port.puts()).toBe(10);
    expect(statuses[10]).toMatchObject({ applied: "accepted", wrote: null });
    expect(fallbackReason(flap(10), { status: statuses[10] })).toBeNull();
    expect(port.events("metronome-cap")).toHaveLength(1);
    port.t = T + 59_999; // just under 60 s after the oldest: still capped
    expect((await engine.renew(flap(11))).wrote).toBeNull();
    port.t = T + 60_001; // just over
    expect((await engine.renew(flap(12))).wrote).toBe(true);
  });

  it("reserves the cap slot in storage before the PUT is issued", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    const put = port.ops.indexOf("put");
    expect(port.ops.slice(0, put).some((o) => o.startsWith("save ") && o.includes("putTimes"))).toBe(true);
  });

  it("a PUT that does not settle within 5 s is a failed write and clears lastBody; the next identical body is written", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    expect(port.store.get("lastBody")).toEqual(expect.any(String));
    port.t = T + 2 * D;
    const release = port.holdPuts();
    const pending = engine.renew(null);
    await settle();
    port.fireTimers();
    const st = await pending;
    expect(st).toMatchObject({ wrote: false });
    expect(port.store.get("lastBody")).toBeNull();
    expect(port.events("metronome-put-failed")).toEqual([expect.objectContaining({ error: "timed out after 5000 ms" })]);
    expect(fallbackReason(lease(T), { status: st })).toMatch(/wrote=false/);
    release();
    await settle();
    const before = port.puts();
    expect((await engine.renew(null)).wrote).toBe(true); // same moment, same body: not skipped
    expect(port.puts()).toBe(before + 1);
  });

  it("a PUT that throws is a failed write", async () => {
    const { port, engine } = engineAt(T);
    port.bucket.failPuts.add("live.m3u8");
    expect((await engine.renew(lease(T))).wrote).toBe(false);
  });
});

describe("renew: serialization", () => {
  it("overlapping renews run one after the other: one PUT, consistent cap and lastBody", async () => {
    const { port, engine } = engineAt(T);
    const release = port.holdPuts();
    const a = engine.renew(lease(T));
    const b = engine.renew(lease(T, { verdictAt: T + 1 }));
    await settle();
    expect(port.ops.filter((o) => o === "put")).toHaveLength(1); // b has not started
    release();
    const [sa, sb] = await Promise.all([a, b]);
    expect(sa.wrote).toBe(true);
    expect(sb.wrote).toBeNull(); // identical body
    expect(port.puts()).toBe(1);
    expect(port.store.get("putTimes")).toEqual([T]);
    expect(port.store.get("lastBody")).toBe(port.body());
  });
});
