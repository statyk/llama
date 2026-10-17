import { describe, expect, it } from "vitest";
import { ALARM_SLACK_MS, holdLease, METRONOME_LEASE_MS, STORAGE_KEYS } from "../src/metronome-core";
import { CFG, D, deliver, deliverDuplicate, E, engineAt, lease, seqOf, settle } from "./metronome-support";

const T = E + 1_000 * D + 3_000; // 3 s into segment 1000
const target = (n: number) => E + n * D + ALARM_SLACK_MS;

/** A DO that accepted an unblocked play lease at T: alarm pending at boundary 1001. */
async function playing() {
  const r = engineAt(T);
  await r.engine.renew(lease(T));
  return r;
}

describe("alarm: the tick", () => {
  it("re-arms first to the next boundary, then writes, then confirms the tick", async () => {
    const { port, engine } = await playing();
    expect(port.alarmAt).toBe(target(1001));
    port.ops.length = 0;
    await deliver(port, engine);
    expect(port.alarmAt).toBe(target(1002));
    expect(port.ops.indexOf(`setAlarm ${target(1002)}`)).toBeLessThan(port.ops.indexOf("put"));
    expect(port.body()).toContain("seg/e1/1013.aac");
    expect(port.store.get("lastTarget")).toBe(target(1002));
    expect(port.store.get("lastAlarmGoodAt")).toBe(target(1001));
    expect(port.puts()).toBe(2);
  });

  it("runs on the grid: one PUT per boundary, no drift", async () => {
    const { port, engine } = await playing();
    for (let n = 1001; n <= 1010; n++) {
      expect(port.alarmAt).toBe(target(n));
      await deliver(port, engine, target(n) + 7); // a few ms late, every time
    }
    expect(port.puts()).toBe(11);
    expect(port.alarmAt).toBe(target(1011));
  });

  it("a late alarm skips missed boundaries rather than bursting", async () => {
    const { port, engine } = await playing();
    await deliver(port, engine, target(1001) + 25_000); // 2 boundaries missed
    expect(port.alarmAt).toBe(target(1004));
    expect(port.puts()).toBe(2);
    expect(port.events("metronome-late")).toEqual([expect.objectContaining({ lateMs: 25_000 })]);
  });

  it("an alarm delivered before the DO's clock passes its boundary builds for that boundary and moves on", async () => {
    const { port, engine } = await playing();
    await deliver(port, engine, target(1001) - 40); // 15 ms before boundary 1001 starts
    expect(port.body()).toContain("seg/e1/1013.aac"); // boundary 1001's playlist, not 1000's
    expect(port.alarmAt).toBe(target(1002)); // never the same target again: no hot loop
  });

  it("an early tick, then a duplicate still before its boundary: the same bytes, no PUT, no re-arm", async () => {
    const { port, engine } = await playing();
    await deliver(port, engine, target(1001) - 40); // early: builds for boundary 1001
    const puts = port.puts();
    const body = port.body()!;
    port.ops.length = 0;
    await deliverDuplicate(port, engine, target(1001) - 35); // still 10 ms before boundary 1001
    expect(port.puts()).toBe(puts);
    expect(port.body()).toBe(body);
    expect(seqOf(port.body()!)).toBe(seqOf(body));
    expect(port.alarmAt).toBe(target(1002));
    expect(port.store.get("lastTarget")).toBe(target(1002));
    expect(port.ops.filter((o) => o.startsWith("setAlarm") || o === "deleteAlarm")).toEqual([]);
  });

  it("an early tick, then a renew still before its boundary: the same body, no PUT, MEDIA-SEQUENCE never goes backwards", async () => {
    const { port, engine } = await playing();
    await deliver(port, engine, target(1001) - 40); // early: builds for boundary 1001
    const puts = port.puts();
    const body = port.body()!;
    port.t = target(1001) - 35; // still 10 ms before boundary 1001
    const st = await engine.renew(lease(port.t));
    expect(st).toMatchObject({ applied: "accepted", wrote: null });
    expect(port.puts()).toBe(puts);
    expect(seqOf(port.body()!)).toBeGreaterThanOrEqual(seqOf(body));
    expect(port.body()).toBe(body);
    expect(port.alarmAt).toBe(target(1002));
  });

  it("a second delivery for the same boundary rebuilds identical bytes: no PUT, still a confirmed tick", async () => {
    const { port, engine } = await playing();
    await deliver(port, engine, target(1001) + 3);
    const puts = port.puts();
    port.store.set("lastTarget", target(1001)); // the same boundary again (at-least-once delivery)
    await deliver(port, engine, target(1001) + 9);
    expect(port.puts()).toBe(puts);
    expect(port.store.get("lastAlarmGoodAt")).toBe(target(1001) + 9);
  });

  it("a duplicate after a tick whose PUT failed writes the differing bytes (lastBody is null) and confirms the tick", async () => {
    const { port, engine } = await playing();
    port.bucket.failPuts.add("live.m3u8");
    await deliver(port, engine, target(1001) + 3); // re-armed, then its PUT failed: lastBody null, tick unconfirmed
    expect(port.store.get("lastBody")).toBeNull();
    expect(port.store.get("lastAlarmGoodAt") ?? null).toBeNull();
    port.bucket.failPuts.delete("live.m3u8");
    const puts = port.puts();
    await deliverDuplicate(port, engine, target(1001) + 9); // at-least-once: the retry finds the re-armed alarm pending
    expect(port.puts()).toBe(puts + 1);
    expect(port.body()).toContain("seg/e1/1013.aac");
    expect(port.store.get("lastAlarmGoodAt")).toBe(target(1001) + 9);
    expect(port.alarmAt).toBe(target(1002));
    expect(port.store.get("lastTarget")).toBe(target(1002));
  });

  it("duplicates after a completed tick (an alarm still pending): no PUT, no re-arm, lastTarget unchanged", async () => {
    const { port, engine } = await playing();
    await deliver(port, engine, target(1001) + 3);
    const puts = port.puts();
    port.ops.length = 0;
    for (const dt of [5, 9, 2_000]) await deliverDuplicate(port, engine, target(1001) + dt);
    expect(port.puts()).toBe(puts);
    expect(port.ops.filter((o) => o !== "save lastAlarmGoodAt")).toEqual([]);
    expect(port.alarmAt).toBe(target(1002));
    expect(port.store.get("lastTarget")).toBe(target(1002));
    expect(port.store.get("lastAlarmGoodAt")).toBe(target(1001) + 2_000); // identical bytes: a confirmed tick
    expect(port.events("metronome-duplicate")).toHaveLength(1);
  });

  it("a renew while the boundary's alarm is in flight arms the next one: the same path, not logged as a duplicate", async () => {
    // Measured on the real runtime (verification day, 13 times in 34 h): getAlarm() reads null once the
    // runtime has taken the alarm, so a renew a few ms before the boundary arms the next one, and the
    // in-flight handler then finds it pending.
    const { port, engine } = await playing();
    await deliver(port, engine, target(1001) + 3);
    port.t = target(1002) - 20;
    port.alarmAt = null; // the runtime has taken boundary 1002's alarm; its handler has not run yet
    await engine.renew(lease(port.t));
    expect(port.alarmAt).toBe(target(1003));
    port.ops.length = 0;
    await deliverDuplicate(port, engine, target(1002)); // the in-flight delivery runs with target(1003) pending
    expect(port.events("metronome-duplicate")).toEqual([]);
    expect(port.ops.filter((o) => o.startsWith("setAlarm") || o === "deleteAlarm")).toEqual([]);
    expect(port.alarmAt).toBe(target(1003));
    expect(port.body()).toContain("seg/e1/1014.aac"); // boundary 1002's playlist
    expect(port.store.get("lastAlarmGoodAt")).toBe(target(1002));
    await deliver(port, engine); // the chain carries on at boundary 1003
    expect(port.alarmAt).toBe(target(1004));
    expect(port.body()).toContain("seg/e1/1015.aac");
    expect(port.events("metronome-duplicate")).toEqual([]);
  });

  it("a redelivery inside the last half segment is still a duplicate; one a full segment after the counted tick is the renew race", async () => {
    const { port, engine } = await playing();
    await deliver(port, engine, target(1001) + 3);
    await deliverDuplicate(port, engine, target(1001) + D / 2 - 1);
    expect(port.events("metronome-duplicate")).toHaveLength(1);
    const r = await playing();
    await deliver(r.port, r.engine, target(1001) + 3);
    await deliverDuplicate(r.port, r.engine, target(1001) + D / 2 + 3);
    expect(r.port.events("metronome-duplicate")).toEqual([]);
  });

  it("a duplicate, then a renew in the same segment: no extra PUT, MEDIA-SEQUENCE never goes backwards", async () => {
    const { port, engine } = await playing();
    await deliver(port, engine, target(1001) + 3);
    const puts = port.puts();
    const seqs = [seqOf(port.body()!)];
    await deliverDuplicate(port, engine, target(1001) + 5);
    seqs.push(seqOf(port.body()!));
    port.t = target(1001) + 4_000; // still segment 1001
    expect((await engine.renew(lease(port.t))).wrote).toBeNull();
    seqs.push(seqOf(port.body()!));
    expect(port.puts()).toBe(puts);
    expect([...seqs].sort((a, b) => a - b)).toEqual(seqs);
    await deliver(port, engine); // boundary 1002, on time
    expect(seqOf(port.body()!)).toBeGreaterThan(seqs[2]);
  });
});

describe("alarm: an epoch change", () => {
  it("the next renew writes the new epoch at once, and the next alarm re-aims to the new grid", async () => {
    const { port, engine } = await playing();
    await deliver(port, engine);
    const E2 = E + 1_001 * D + 4_000; // a re-render: a new epoch 4 s after boundary 1001
    port.t = E2 + 100 * D + 1_000;
    const newEpoch = { epoch_id: "e2", epoch: new Date(E2).toISOString() };
    const st = await engine.renew(lease(port.t, { horizon: newEpoch }));
    expect(st).toMatchObject({ applied: "accepted", wrote: true });
    expect(port.body()).toContain("seg/e2/112.aac"); // 100 + lookahead 12 on the new grid
    // The pending alarm is long past: deliver it now; it re-arms on the new grid.
    await deliver(port, engine, port.t + 10);
    expect(port.alarmAt).toBe(E2 + 101 * D + ALARM_SLACK_MS);
    await deliver(port, engine);
    expect(port.alarmAt).toBe(E2 + 102 * D + ALARM_SLACK_MS);
  });
});

describe("alarm: when it must not tick", () => {
  it("switch off: deletes the alarm, writes nothing", async () => {
    const { port, engine } = await playing();
    port.on = false;
    port.alarmAt = target(1001); // pending
    await engine.alarm();
    expect(port.alarmAt).toBeNull();
    expect(port.puts()).toBe(1);
  });

  for (const [what, setup] of [
    ["no lease", async (e: Awaited<ReturnType<typeof playing>>) => { e.port.store.delete("lease"); }],
    ["a hold", async (e: Awaited<ReturnType<typeof playing>>) => { await e.engine.renew(holdLease(T + 1, T + 1)); }],
    ["a blocked lease", async (e: Awaited<ReturnType<typeof playing>>) => {
      await e.engine.renew(lease(T + 1, { blocked: true, verdictAt: T + 1 }));
    }],
    ["an expired lease", async (e: Awaited<ReturnType<typeof playing>>) => { e.port.t = T + METRONOME_LEASE_MS; }],
    ["a lease renewed only by renew(null) and a superseded lease", async (e: Awaited<ReturnType<typeof playing>>) => {
      for (const min of [5, 10]) {
        e.port.t = T + min * 60_000;
        await e.engine.renew(null);
      }
      e.port.t = T + 12 * 60_000;
      await e.engine.renew(lease(e.port.t, { verdictAt: T }));
      e.port.t = T + METRONOME_LEASE_MS;
    }],
    ["an unparseable stored lease", async (e: Awaited<ReturnType<typeof playing>>) => { e.port.store.set("lease", "{"); }],
  ] as const) {
    it(`${what}: an alarm delivered anyway writes nothing and does not re-arm`, async () => {
      const p = await playing();
      await setup(p);
      const puts = p.port.puts();
      p.port.alarmAt = null;
      await p.engine.alarm();
      expect(p.port.puts()).toBe(puts);
      expect(p.port.alarmAt).toBeNull();
    });
  }

  it("a renew that stored a hold or a block, then threw on its alarm op: the still-pending alarm writes nothing and does not re-arm", async () => {
    for (const next of [holdLease(T + 1_000, T + 1_000), lease(T + 1_000, { blocked: true, verdictAt: T + 1_000 })]) {
      const { port, engine } = await playing();
      expect(port.alarmAt).toBe(target(1001)); // the play lease's alarm, pending
      port.t = T + 1_000;
      port.failDeleteAlarm = true;
      await expect(engine.renew(next)).rejects.toThrow(/deleteAlarm/);
      expect(JSON.parse(port.store.get("lease") as string)).toMatchObject({ kind: next.kind, verdictAt: T + 1_000 });
      expect(port.alarmAt).toBe(target(1001)); // the delete failed: still pending
      const puts = port.puts();
      const body = port.body();
      port.ops.length = 0;
      await deliver(port, engine);
      expect(port.puts()).toBe(puts);
      expect(port.body()).toBe(body);
      expect(port.alarmAt).toBeNull();
      expect(port.ops.filter((o) => o.startsWith("setAlarm") || o === "put")).toEqual([]);
      expect(port.events("metronome-alarm-error")).toEqual([]); // the step-2 return, not a caught exception
    }
  });

  it("a horizon over 24 h stale under an unblocked lease: the off-air body once, no re-arm, no stall", async () => {
    const late = E + 11 * D + CFG.offairAfterMs + 1;
    const { port, engine } = engineAt(late - 20_000);
    await engine.renew(lease(late - 20_000, { horizon: { last: 10 } })); // still live, 20 s before the cut-over
    await deliver(port, engine, late);
    expect(port.body()).toContain("#EXT-X-ENDLIST");
    expect(port.alarmAt).toBeNull();
    port.t = late + 60_000;
    const st = await engine.renew(lease(port.t, { horizon: { last: 10 } }));
    expect(st).toMatchObject({ stalls: 0, stalledMs: 0 });
    expect(port.alarmAt).toBeNull();
  });

  it("a null build (before the epoch) is a confirmed tick, logged once per lease", async () => {
    const before = E - 5 * D;
    const { port, engine } = engineAt(before);
    await engine.renew(lease(before));
    expect(port.puts()).toBe(0);
    await deliver(port, engine);
    await deliver(port, engine);
    expect(port.puts()).toBe(0);
    expect(port.store.get("lastAlarmGoodAt")).toBe(port.t);
    expect(port.events("metronome-null-build")).toHaveLength(1);
    expect(port.alarmAt).not.toBeNull();
  });

  it("a fallback loop entry with no usable fallback is a null build too", async () => {
    const { port, engine } = engineAt(T);
    // the horizon ended 5 segments ago (past grace): the window needs loop entries
    await engine.renew(lease(T, { horizon: { last: 995 }, fallback: null }));
    await deliver(port, engine);
    expect(port.puts()).toBe(0);
    expect(port.store.get("lastAlarmGoodAt")).toBe(port.t);
  });
});

describe("alarm: caps and failures", () => {
  it("the 13th alarm() in 60 s does not re-arm and logs metronome-alarm-cap; just over 60 s later it does", async () => {
    const { port, engine } = await playing();
    for (let i = 0; i < 12; i++) await deliver(port, engine, T + 1_000 + i * 100);
    expect(port.alarmAt).not.toBeNull();
    await deliver(port, engine, T + 1_000 + 59_999); // 13th, just under 60 s after the first
    expect(port.alarmAt).toBeNull();
    expect(port.events("metronome-alarm-cap")).toHaveLength(1);
    await deliver(port, engine, T + 1_000 + 60_001); // just over: the oldest left the window
    expect(port.alarmAt).not.toBeNull();
  });

  it("the PUT cap holds across alarms and renews, and the chain still re-arms over it", async () => {
    const { port, engine } = await playing();
    // a flapping verdict between ticks: 10 PUTs within the minute
    for (let i = 1; i <= 9; i++) {
      port.t = T + i * 1_000;
      await engine.renew(lease(port.t, { blocked: i % 2 === 1, verdictAt: T + i }));
    }
    expect(port.puts()).toBe(10);
    await engine.renew(lease(T + 9_500, { verdictAt: T + 10 })); // back on air
    await deliver(port, engine, target(1001) + 30_000);
    expect(port.puts()).toBe(10);
    expect(port.events("metronome-cap").length).toBeGreaterThanOrEqual(1);
    expect(port.alarmAt).not.toBeNull();
    expect(port.store.get("lastAlarmGoodAt") ?? null).toBeNull(); // a cap-skipped write is not a confirmed tick
  });

  it("a failed re-arm logs metronome-rearm-failed and returns without writing", async () => {
    const { port, engine } = await playing();
    port.failSetAlarm = true;
    await deliver(port, engine);
    expect(port.events("metronome-rearm-failed")).toHaveLength(1);
    expect(port.puts()).toBe(1);
  });

  it("an exception anywhere in alarm() never propagates", async () => {
    const { port, engine } = await playing();
    port.failLoad = true;
    await expect(deliver(port, engine)).resolves.toBeUndefined();
    expect(port.events("metronome-alarm-error")).toEqual([expect.objectContaining({ error: "injected load failure" })]);
  });

  it("a failed PUT leaves the chain armed, the tick unconfirmed and lastBody cleared", async () => {
    const { port, engine } = await playing();
    port.bucket.failPuts.add("live.m3u8");
    await deliver(port, engine);
    expect(port.alarmAt).toBe(target(1002));
    expect(port.store.get("lastAlarmGoodAt") ?? null).toBeNull();
    expect(port.store.get("lastBody")).toBeNull();
    expect(port.events("metronome-put-failed")).toHaveLength(1);
  });
});

describe("alarm and renew interleaved", () => {
  it("a renew during an alarm's slow PUT waits for it: the cap and lastBody stay consistent", async () => {
    const { port, engine } = await playing();
    const release = port.holdPuts();
    port.alarmAt = null;
    port.t = target(1001);
    const tick = engine.alarm();
    await settle();
    const renewed = engine.renew(lease(port.t, { verdictAt: port.t }));
    await settle();
    expect(port.ops.filter((o) => o === "put")).toHaveLength(2); // the first renew and the alarm: the new renew waits
    release();
    const [, st] = await Promise.all([tick, renewed]);
    expect(st.wrote).toBeNull(); // the same moment, the same body: skipped against the alarm's lastBody
    expect(port.puts()).toBe(2);
    expect((port.store.get("putTimes") as number[]).length).toBe(2);
    expect(port.store.get("lastBody")).toBe(port.body());
  });
});

describe("storage", () => {
  it("the stored keys are always within the fixed set, and a full cycle uses exactly it", async () => {
    const { port, engine } = await playing();
    const within = () => { for (const k of port.store.keys()) expect(STORAGE_KEYS as readonly string[]).toContain(k); };
    for (let i = 0; i < 20; i++) {
      await deliver(port, engine);
      within();
    }
    port.alarmAt = null; // a silent chain break: the next renew counts a stall
    port.t += 40_000;
    await engine.renew(lease(port.t));
    await deliver(port, engine);
    await engine.renew(lease(port.t + 1, { verdictAt: port.t + 1 }));
    within();
    expect([...port.store.keys()].sort()).toEqual([...STORAGE_KEYS].sort());
  });
});
