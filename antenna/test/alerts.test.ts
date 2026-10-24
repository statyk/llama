import { afterEach, describe, expect, it, vi } from "vitest";
import { type AlertEntry, type AlertEnv, ALERTS_KEY, type AlertState, alertSink, CLOCK_KEYS, channelsFromEnv,
         COOLDOWN_MS, dispatchAlerts, emailChannel, GATE, GATED_KEYS, keyFamily, type Outgoing, planAlerts, rawEmail,
         redact, RELAY_KEY, RELAY_RING, type RelayMessage, relayDocProblem, relaySink, secretsFromEnv }
  from "../src/alerts";
import type { PutOptions } from "../src/bucket";
import type { AlertBatch } from "../src/clock";
import type { AlertCondition } from "../src/conditions";
import { guardConfigFromEnv, type GuardEnv, guardStep } from "../src/guard";
import { GRAPHQL_URL } from "../src/meter";
import { API } from "../src/waf";
import { type FetchCall, fakeFetch, json, MemoryBucket, usageResponse } from "./support";

const T0 = Date.parse("2026-10-20T12:00:00Z");
const H = 3_600_000;
const REPEAT = 6 * H;
const cond = (key: string, resolvable = true): AlertCondition =>
  ({ key, priority: "high", resolvable, title: `${key} title`, message: `${key} message` });

afterEach(() => {
  vi.restoreAllMocks();
});

describe("planAlerts", () => {
  it("sends a new condition once, repeats it every REPEAT, and resolves it when it clears", () => {
    let s: AlertState = {};
    let r = planAlerts(s, [cond("offair-corrupt")], T0, REPEAT);
    expect(r.send.map((o) => o.kind)).toEqual(["alert"]);
    s = r.next;
    r = planAlerts(s, [cond("offair-corrupt")], T0 + H, REPEAT);
    expect(r.send).toEqual([]);
    s = r.next;
    r = planAlerts(s, [cond("offair-corrupt")], T0 + REPEAT, REPEAT);
    expect(r.send.map((o) => o.kind)).toEqual(["repeat"]);
    s = r.next;
    // Ruled (fix round 1, option a): "resolved" only once absent for COOLDOWN_MS.
    r = planAlerts(s, [], T0 + REPEAT + H, REPEAT);
    expect(r.send).toEqual([]);
    expect(r.next["offair-corrupt"]).toMatchObject({ active: true, clearing_since: new Date(T0 + REPEAT + H).toISOString() });
    r = planAlerts(r.next, [], T0 + REPEAT + H + COOLDOWN_MS, REPEAT);
    expect(r.send.map((o) => [o.kind, o.key])).toEqual([["resolved", "offair-corrupt"]]);
    expect(r.next["offair-corrupt"].active).toBe(false);
  });

  it("does not resolve a non-resolvable condition aloud", () => {
    const s = planAlerts({}, [cond("budget-50", false)], T0, REPEAT).next;
    expect(planAlerts(s, [], T0 + H, REPEAT).send).toEqual([]);
  });

  it("a condition that returns within the cooldown is continuing, not new", () => {
    let s = planAlerts({}, [cond("offair-corrupt")], T0, REPEAT).next;
    s = planAlerts(s, [], T0 + 60_000, REPEAT).next;
    const back = planAlerts(s, [cond("offair-corrupt")], T0 + 120_000, REPEAT);
    expect(back.send).toEqual([]);
    expect(back.next["offair-corrupt"].active).toBe(true);
    s = planAlerts(back.next, [], T0 + 180_000, REPEAT).next;
    expect(planAlerts(s, [cond("offair-corrupt")], T0 + 180_000 + COOLDOWN_MS, REPEAT).send.map((o) => o.kind)).toEqual(["alert"]);
  });

  it("sends a once condition when it first appears, never repeats it, and not again when it returns", () => {
    const once = (key: string): AlertCondition => ({ ...cond(key, false), once: true });
    let r = planAlerts({}, [once("budget-50:2026-10-11:15")], T0, REPEAT);
    expect(r.send.map((o) => o.kind)).toEqual(["alert"]);
    r = planAlerts(r.next, [once("budget-50:2026-10-11:15")], T0 + REPEAT, REPEAT);
    expect(r.send).toEqual([]);
    r = planAlerts(r.next, [], T0 + REPEAT + H, REPEAT); // the projection dipped under 50%
    expect(r.send).toEqual([]);
    r = planAlerts(r.next, [once("budget-50:2026-10-11:15")], T0 + 2 * REPEAT, REPEAT);
    expect(r.send).toEqual([]);
    // The next billing period is a new key.
    r = planAlerts(r.next, [once("budget-50:2026-11-11:15")], T0 + 3 * REPEAT, REPEAT);
    expect(r.send.map((o) => o.key)).toEqual(["budget-50:2026-11-11:15"]);
  });

  it("forgets inactive entries after a week", () => {
    let s = planAlerts({}, [cond("x")], T0, REPEAT).next;
    s = planAlerts(s, [], T0 + H, REPEAT).next;
    expect(planAlerts(s, [], T0 + 8 * 24 * H, REPEAT).next).toEqual({});
  });
});

describe("planAlerts: resolution waits out the cooldown (ruled, fix round 1)", () => {
  const MIN = 60_000;
  /** Run planAlerts minute by minute; `present(m)` says whether the key is computed at minute m. */
  const run = (key: string, minutes: number, present: (m: number) => boolean,
               batch: (m: number) => AlertBatch = () => ({ complete: true, guardComplete: true })) => {
    let s: AlertState = {};
    const sends: string[] = [];
    for (let m = 0; m <= minutes; m++) {
      const r = planAlerts(s, present(m) ? [cond(key)] : [], T0 + m * MIN, REPEAT, batch(m));
      for (const o of r.send) sends.push(`${o.kind}@${m}`);
      s = r.next;
    }
    return { sends, s };
  };

  it("a flap inside the window sends no resolved and no new alert; the next repeat goes out on schedule", () => {
    // The reviewer's probe: present at 0, absent at 1-4, present from 5 on (plus two more short flaps).
    const absent = new Set([1, 2, 3, 4, 40, 200, 201]);
    const { sends } = run("lead-low", 6 * 60 + 2, (m) => !absent.has(m));
    expect(sends).toEqual(["alert@0", "repeat@360"]);
  });

  it("a key absent for COOLDOWN_MS sends resolved exactly once", () => {
    const { sends, s } = run("lead-low", 120, (m) => m === 0);
    expect(sends).toEqual(["alert@0", `resolved@${1 + COOLDOWN_MS / MIN}`]);
    expect(s["lead-low"]).toMatchObject({ active: false, cleared_at: new Date(T0 + MIN).toISOString() });
    expect(s["lead-low"].clearing_since).toBeUndefined();
  });

  it("after a delivered resolved, a return is a new alert at once", () => {
    const { sends } = run("lead-low", 30, (m) => m === 0 || m === 17);
    expect(sends).toEqual(["alert@0", "resolved@16", "alert@17"]);
  });

  it("on incomplete batches the clearing window neither starts nor runs on", () => {
    // Absent from minute 1; batches 1-29 incomplete (clock-family key), complete from 30.
    const { sends } = run("lead-low", 60, (m) => m === 0, (m) => ({ complete: m >= 30, guardComplete: true }));
    expect(sends).toEqual(["alert@0", `resolved@${30 + COOLDOWN_MS / MIN}`]);
    // Clearing already started, then incomplete batches: held, resolved only once complete again.
    const held = run("lead-low", 60, (m) => m === 0, (m) => ({ complete: m === 1 || m >= 40, guardComplete: false }));
    expect(held.sends).toEqual(["alert@0", "resolved@40"]);
  });

  it("once-conditions are unaffected: no clearing window", () => {
    const c: AlertCondition = { ...cond("budget-50:2026-10-11:15", false), once: true };
    const s = planAlerts({}, [c], T0, REPEAT).next;
    const r = planAlerts(s, [], T0 + MIN, REPEAT);
    expect(r.next[c.key]).toMatchObject({ active: false, cleared_at: new Date(T0 + MIN).toISOString() });
    expect(r.next[c.key].clearing_since).toBeUndefined();
  });

  it("an alert no channel ever delivered gets no resolved when it clears: the entry is dropped", () => {
    const s: AlertState = { "waf-api": { active: true, resolvable: true, title: "t", first_at: new Date(T0).toISOString(),
                                         last_sent_at: null, cleared_at: null } };
    const r1 = planAlerts(s, [], T0 + MIN, REPEAT);
    const r2 = planAlerts(r1.next, [], T0 + MIN + COOLDOWN_MS, REPEAT);
    expect([...r1.send, ...r2.send]).toEqual([]);
    expect(r2.next).toEqual({});
  });
});

describe("planAlerts on an incomplete batch (AlertBatch)", () => {
  const INCOMPLETE: AlertBatch = { complete: false, guardComplete: false };
  const GUARD_ONLY: AlertBatch = { complete: false, guardComplete: true };

  it("resolves nothing that is absent, and starts no cooldown for it, while still sending what is present", () => {
    let s = planAlerts({}, [cond("tripped-spend"), cond("lead-low")], T0, REPEAT).next;
    // One minute while tripped where only a guard-family key is computed (an ungated one: offair-corrupt).
    const r = planAlerts(s, [cond("offair-corrupt")], T0 + 60_000, REPEAT, INCOMPLETE);
    expect(r.send.map((o) => [o.kind, o.key])).toEqual([["alert", "offair-corrupt"]]);
    expect(r.next["tripped-spend"]).toEqual(s["tripped-spend"]);
    expect(r.next["lead-low"]).toEqual(s["lead-low"]);
    s = r.next;
    // Back to normal 20 minutes later (past the cooldown): continuing, not new;
    // offair-corrupt starts clearing on the complete batch, and resolves aloud
    // once absent for COOLDOWN_MS.
    const back = planAlerts(s, [cond("tripped-spend"), cond("lead-low")], T0 + 21 * 60_000, REPEAT);
    expect(back.send).toEqual([]);
    const later = planAlerts(back.next, [cond("tripped-spend"), cond("lead-low")], T0 + 21 * 60_000 + COOLDOWN_MS, REPEAT);
    expect(later.send.map((o) => [o.kind, o.key])).toEqual([["resolved", "offair-corrupt"]]);
  });

  it("still repeats a present condition on an incomplete batch", () => {
    const s = planAlerts({}, [cond("tripped-spend")], T0, REPEAT).next;
    expect(planAlerts(s, [cond("tripped-spend")], T0 + REPEAT, REPEAT, INCOMPLETE).send.map((o) => o.kind))
      .toEqual(["repeat"]);
  });

  it("guardComplete: guard-family keys resolve, clock-family keys do not", () => {
    const s = planAlerts({}, [cond("offair-corrupt"), cond("lead-low"), cond("offair-without-fallback"), cond("tripped-blind")],
                         T0, REPEAT).next;
    let r = planAlerts(s, [cond("horizon-refused")], T0 + 60_000, REPEAT, GUARD_ONLY);
    expect(r.send.map((o) => [o.kind, o.key])).toEqual([["alert", "horizon-refused"]]);
    expect(r.next["offair-corrupt"].clearing_since).toBe(new Date(T0 + 60_000).toISOString());
    r = planAlerts(r.next, [cond("horizon-refused")], T0 + 60_000 + COOLDOWN_MS, REPEAT, GUARD_ONLY);
    expect(r.send.map((o) => [o.kind, o.key]).sort()).toEqual([["resolved", "offair-corrupt"], ["resolved", "tripped-blind"]]);
    expect(r.next["lead-low"]).toEqual(s["lead-low"]);
    expect(r.next["offair-without-fallback"]).toEqual(s["offair-without-fallback"]);
  });

  it("a key in neither family is treated as clock-family: resolved only on a complete batch", () => {
    const s = planAlerts({}, [cond("something-new")], T0, REPEAT).next;
    let r = planAlerts(s, [], T0 + 60_000, REPEAT, GUARD_ONLY);
    expect(r.send).toEqual([]);
    expect(r.next).toEqual(s); // not even clearing
    r = planAlerts(r.next, [], T0 + 60_000 + COOLDOWN_MS, REPEAT, GUARD_ONLY);
    expect(r.next).toEqual(s);
    r = planAlerts(r.next, [], T0 + 2 * COOLDOWN_MS, REPEAT);
    expect(r.send).toEqual([]);
    expect(planAlerts(r.next, [], T0 + 3 * COOLDOWN_MS, REPEAT).send.map((o) => o.kind)).toEqual(["resolved"]);
  });

  it("classifies every key the guard and the clock raise", () => {
    for (const k of ["tripped-spend", "tripped-blind", "budget-50:2026-10-11:15", "budget-80:2026-10-11:40",
                     "guard-reading-failing", "guard-unknown", "offair-corrupt", "guard-state-corrupt", "waf-api",
                     "waf-corrected", "budget-file-invalid", "guard-write", "budget-unreadable"]) {
      expect([k, keyFamily(k)]).toEqual([k, "guard"]);
    }
    const clock = ["guard-crashed", "index-write", "horizon-missing", "horizon-refused", "lead-low",
                   "offair-without-fallback", "clock-inputs", "clock-failed", "metronome-down"];
    expect([...CLOCK_KEYS].sort()).toEqual([...clock].sort());
    for (const k of clock) expect([k, keyFamily(k)]).toEqual([k, "clock"]);
    expect(keyFamily("budget-x")).toBe("clock");
    // B. only two raise sites bypass the gate
    const sources = import.meta.glob("../src/*.ts", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
    const sites = Object.entries(sources).flatMap(([f, s]) => (s.match(/immediate:\s*true/g) ?? []).map(() => f));
    expect(sites.sort()).toEqual(["../src/clock.ts", "../src/guard.ts"]);
    for (const k of GATED_KEYS) expect(CLOCK_KEYS.has(k) || keyFamily(k) === "guard").toBe(true);
  });
});

describe("the 3-consecutive gate", () => {
  const at = (n: number) => T0 + n * 60_000;
  const iso = (ms: number) => new Date(ms).toISOString();
  const imm = (key: string): AlertCondition => ({ ...cond(key), immediate: true });
  const DONE: AlertBatch = { complete: true, guardComplete: true };
  const NONE: AlertBatch = { complete: false, guardComplete: false };
  const broken = { name: "x", send: async () => { throw new Error("down"); } };
  /** A still-active entry whose clearing window has elapsed. No streak: the
   * first allowed absence that started the clearing stripped it. */
  const live: AlertEntry = { active: true, resolvable: true, title: "t", first_at: iso(T0 - H), last_sent_at: iso(T0 - H),
                             delivered: true, cleared_at: null, clearing_since: iso(T0 - COOLDOWN_MS - 60_000) };

  it("A. GATED_KEYS is exactly the approved list", () => {
    expect(GATE).toBe(3);
    expect([...GATED_KEYS].sort()).toEqual(["budget-unreadable", "clock-failed", "clock-inputs", "guard-crashed",
      "guard-unknown", "guard-write", "horizon-missing", "index-write", "metronome-down", "waf-api"]);
  });

  it("C. a gated key sends only on its 3rd consecutive presence; the first message says so", () => {
    let r = planAlerts({}, [cond("waf-api")], at(0), REPEAT);
    expect(r.send).toEqual([]);
    expect(r.next["waf-api"]).toMatchObject({ active: false, pending: true, streak: 1 });
    r = planAlerts(r.next, [cond("waf-api")], at(1), REPEAT);
    expect(r.send).toEqual([]);
    expect(r.next["waf-api"]).toMatchObject({ active: false, pending: true, streak: 2 });
    r = planAlerts(r.next, [cond("waf-api")], at(2), REPEAT);
    expect(r.send.map((o) => o.kind)).toEqual(["alert"]);
    expect(r.send[0].message).toMatch(/3 consecutive/);
    expect(r.next["waf-api"]).toMatchObject({ active: true, streak: 3 });
    expect(r.next["waf-api"].pending).toBeUndefined();
  });

  it("D. an absence on a batch that could clear it drops a pending-only entry", () => {
    let s = planAlerts({}, [cond("waf-api")], at(0), REPEAT).next;
    s = planAlerts(s, [], at(1), REPEAT, DONE).next;
    expect(s).not.toHaveProperty("waf-api");
    expect(planAlerts(s, [cond("waf-api")], at(2), REPEAT).next["waf-api"].streak).toBe(1);
  });

  it("E. an incomplete batch over a pending entry leaves it unchanged; guardComplete resets a guard-family one", () => {
    const s = planAlerts({}, [cond("clock-inputs"), cond("guard-write")], at(0), REPEAT).next;
    const r = planAlerts(s, [], at(1), REPEAT, NONE);
    expect(r.next).toEqual(s);
    const g = planAlerts(s, [], at(1), REPEAT, { complete: false, guardComplete: true });
    expect(g.next["clock-inputs"]).toEqual(s["clock-inputs"]);
    expect(g.next).not.toHaveProperty("guard-write");
    // the incomplete minute neither advanced nor reset: two more presences reach GATE
    const t = planAlerts(r.next, [cond("clock-inputs")], at(2), REPEAT).next;
    expect(planAlerts(t, [cond("clock-inputs")], at(3), REPEAT).send.map((o) => o.kind)).toEqual(["alert"]);
  });

  it("G. pending over a kept inactive entry keeps its history; a reset keeps it as before", () => {
    const old: AlertEntry = { active: false, resolvable: true, title: "t", first_at: iso(T0 - H), last_sent_at: iso(T0 - H),
                              delivered: true, cleared_at: iso(T0 - 30 * 60_000) };
    const r = planAlerts({ "waf-api": old }, [cond("waf-api")], at(0), REPEAT);
    expect(r.send).toEqual([]);
    expect(r.next["waf-api"]).toEqual({ ...old, streak: 1 });
    expect(planAlerts(r.next, [], at(1), REPEAT, DONE).next["waf-api"]).toEqual(old);
  });

  it("H. pending over a still-active entry whose clearing elapsed: it stays, may resolve, or is replaced at GATE", () => {
    const r = planAlerts({ "waf-api": live }, [cond("waf-api")], at(0), REPEAT);
    expect(r.send).toEqual([]);
    expect(r.next["waf-api"]).toEqual({ ...live, streak: 1 });
    const gone = planAlerts(r.next, [], at(1), REPEAT, DONE);
    expect(gone.send.map((o) => [o.kind, o.key])).toEqual([["resolved", "waf-api"]]);
    const s = planAlerts(r.next, [cond("waf-api")], at(1), REPEAT).next;
    const back = planAlerts(s, [cond("waf-api")], at(2), REPEAT);
    expect(back.send.map((o) => o.kind)).toEqual(["alert"]);
    expect(back.next["waf-api"].first_at).toBe(iso(at(2)));
  });

  it("I. a single blip inside an active episode never sends a repeat", () => {
    let s = [0, 1, 2].reduce((st, n) => planAlerts(st, [cond("waf-api")], at(n), REPEAT).next, {} as AlertState);
    s = planAlerts(s, [], at(2) + REPEAT, REPEAT, DONE).next;          // a clean minute: streak reset, clearing starts
    let r = planAlerts(s, [cond("waf-api")], at(3) + REPEAT, REPEAT);    // back inside the window, repeat due
    expect(r.send).toEqual([]);
    expect(r.next["waf-api"].active).toBe(true);
    r = planAlerts(r.next, [cond("waf-api")], at(4) + REPEAT, REPEAT);
    r = planAlerts(r.next, [cond("waf-api")], at(5) + REPEAT, REPEAT);
    expect(r.send.map((o) => o.kind)).toEqual(["repeat"]);
  });

  it("J. an immediate condition sends at once, advances the streak, and its repeat is not gated", () => {
    let r = planAlerts({}, [imm("metronome-down")], at(0), REPEAT);
    expect(r.send.map((o) => o.kind)).toEqual(["alert"]);
    expect(r.send[0].message).not.toMatch(/consecutive/);
    expect(r.next["metronome-down"]).toMatchObject({ active: true, streak: 1 });
    r = planAlerts(r.next, [imm("metronome-down")], at(0) + REPEAT, REPEAT);   // streak 2 < GATE, repeat due
    expect(r.send.map((o) => o.kind)).toEqual(["repeat"]);
  });

  it("K. ungated keys send at their first presence and store no streak (strict surfaces)", () => {
    for (const c of [cond("tripped-spend"), cond("tripped-blind"), cond("guard-state-corrupt"), cond("offair-corrupt"),
                     cond("horizon-refused"), cond("lead-low"), cond("guard-reading-failing"),
                     cond("offair-without-fallback"), cond("waf-corrected", false),
                     { ...cond("budget-file-invalid", false), once: true },
                     { ...cond("budget-50:2026-10-11:15", false), once: true },
                     { ...cond("budget-80:2026-10-11:15", false), once: true }]) {
      const r = planAlerts({}, [c], T0, REPEAT);
      expect([c.key, r.send.map((o) => o.kind)]).toEqual([c.key, ["alert"]]);
      expect([c.key, "streak" in r.next[c.key]]).toEqual([c.key, false]);
    }
  });

  it("L. the stored streak stops at GATE: a steady active episode writes alerts.json no more", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    for (let n = 0; n < 6; n++) await dispatchAlerts(bucket, [], [cond("waf-api")], at(n), REPEAT);
    expect(bucket.puts(ALERTS_KEY)).toBe(3);
  });

  it("M. an entry from before the gate continues; its due repeat waits for GATE presences", () => {
    const legacy: AlertEntry = { active: true, resolvable: true, title: "t", first_at: iso(T0 - REPEAT),
                                 last_sent_at: iso(T0 - REPEAT), delivered: true, cleared_at: null }; // old Worker: no streak
    let r = planAlerts({ "waf-api": legacy }, [cond("waf-api")], at(0), REPEAT);
    expect(r.send).toEqual([]);
    expect(r.next["waf-api"]).toMatchObject({ active: true, first_at: legacy.first_at, streak: 1 });
    r = planAlerts(r.next, [cond("waf-api")], at(1), REPEAT);
    r = planAlerts(r.next, [cond("waf-api")], at(2), REPEAT);
    expect(r.send.map((o) => o.kind)).toEqual(["repeat"]);
  });

  it("Q. a failed \"resolved\" restores the entry without its streak, so the clean minute's reset holds", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    bucket.seed(ALERTS_KEY, { "waf-api": live });
    expect(await dispatchAlerts(bucket, [], [cond("waf-api")], at(0), REPEAT)).toEqual({ sent: 0, failed: 0 }); // held
    expect(bucket.json(ALERTS_KEY)["waf-api"]).toEqual({ ...live, streak: 1 });
    expect(await dispatchAlerts(bucket, [broken], [], at(1), REPEAT, DONE)).toEqual({ sent: 0, failed: 1 });
    expect(bucket.json(ALERTS_KEY)["waf-api"]).toEqual(live);
    await dispatchAlerts(bucket, [], [cond("waf-api")], at(2), REPEAT);
    expect(bucket.json(ALERTS_KEY)["waf-api"].streak).toBe(1);
  });

  it("R. an undelivered immediate first alert is resent at once by a non-immediate presence, never re-gated", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const got: Outgoing[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(o); } };
    const relay = relaySink(bucket, [], () => "stream-1");
    bucket.failPuts.add(RELAY_KEY); // both the email and the relay fail at minute 0
    expect(await dispatchAlerts(bucket, [broken], [imm("metronome-down")], at(0), REPEAT, DONE, relay))
      .toEqual({ sent: 0, failed: 1 });
    expect(bucket.json(ALERTS_KEY)["metronome-down"]).toMatchObject({ active: true, last_sent_at: null, delivered: false });
    bucket.failPuts.delete(RELAY_KEY);
    expect(await dispatchAlerts(bucket, [ok], [cond("metronome-down")], at(1), REPEAT, DONE, relay))
      .toEqual({ sent: 1, failed: 0 });
    expect(got.map((o) => [o.kind, o.key])).toEqual([["repeat", "metronome-down"]]);
    expect(got[0].message).not.toMatch(/consecutive/); // the episode began immediate
    expect(bucket.json(ALERTS_KEY)["metronome-down"]).toMatchObject({ active: true, streak: 2, delivered: true });
  });

  it("S. a gated first alert whose send fails at GATE is retried the next minute with the gate note", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const got: Outgoing[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(o); } };
    await dispatchAlerts(bucket, [broken], [cond("waf-api")], at(0), REPEAT);
    await dispatchAlerts(bucket, [broken], [cond("waf-api")], at(1), REPEAT);
    expect(await dispatchAlerts(bucket, [broken], [cond("waf-api")], at(2), REPEAT)).toEqual({ sent: 0, failed: 1 });
    expect(await dispatchAlerts(bucket, [ok], [cond("waf-api")], at(3), REPEAT)).toEqual({ sent: 1, failed: 0 });
    expect(got.map((o) => [o.kind, o.key])).toEqual([["repeat", "waf-api"]]);
    expect(got[0].message).toMatch(/3 consecutive/);
  });

  it("T. a stored streak is read defensively: capped at GATE, anything else not a positive integer reads as 0", () => {
    const old: AlertEntry = { active: false, resolvable: true, title: "t", first_at: iso(T0 - H), last_sent_at: iso(T0 - H),
                              delivered: true, cleared_at: iso(T0 - 30 * 60_000) };
    const big = planAlerts({ "waf-api": { ...old, streak: 99 } }, [cond("waf-api")], at(0), REPEAT);
    expect(big.send.map((o) => o.kind)).toEqual(["alert"]);
    expect(big.next["waf-api"].streak).toBe(GATE);
    for (const bad of ["x", 1.5, 0, -1] as unknown[]) {
      const r = planAlerts({ "waf-api": { ...old, streak: bad as number } }, [cond("waf-api")], at(0), REPEAT);
      expect([bad, r.send]).toEqual([bad, []]);
      expect([bad, r.next["waf-api"].streak]).toEqual([bad, 1]);
    }
  });

  describe("U. a failed gated alert that replaced a still-active episode is resent at once, never re-gated (Q4)", () => {
    const relayed = (bucket: MemoryBucket) => relaySink(bucket, [], () => "stream-1");
    /** Test H's path: pending over `live` reaches GATE and the new episode's alert fails on email and relay. */
    const failAtGate = async () => {
      vi.spyOn(console, "error").mockImplementation(() => {});
      const bucket = new MemoryBucket();
      bucket.seed(ALERTS_KEY, { "waf-api": live });
      bucket.failPuts.add(RELAY_KEY);
      const relay = relayed(bucket);
      await dispatchAlerts(bucket, [broken], [cond("waf-api")], at(0), REPEAT, DONE, relay);
      await dispatchAlerts(bucket, [broken], [cond("waf-api")], at(1), REPEAT, DONE, relay);
      expect(await dispatchAlerts(bucket, [broken], [cond("waf-api")], at(2), REPEAT, DONE, relay))
        .toEqual({ sent: 0, failed: 1 });
      // The old episode was delivered: its "resolved" must not be lost, so `delivered` stays.
      expect(bucket.json(ALERTS_KEY)["waf-api"]).toMatchObject({ active: true, first_at: iso(at(2)), last_sent_at: null,
                                                                delivered: true });
      bucket.failPuts.delete(RELAY_KEY);
      const got: Outgoing[] = [];
      const ok = { name: "ok", send: async (o: Outgoing) => { got.push(o); } };
      return { bucket, got, ok, relay };
    };

    it("the next minute's presence resends it with the gate note", async () => {
      const { bucket, got, ok, relay } = await failAtGate();
      expect(await dispatchAlerts(bucket, [ok], [cond("waf-api")], at(3), REPEAT, DONE, relay))
        .toEqual({ sent: 1, failed: 0 });
      expect(got.map((o) => [o.kind, o.key])).toEqual([["repeat", "waf-api"]]);
      expect(got[0].message).toMatch(/3 consecutive/);
      // Delivered now: a later failed repeat waits for the gate again after a clean minute.
      const later = at(3) + REPEAT;
      bucket.failPuts.add(RELAY_KEY);
      expect(await dispatchAlerts(bucket, [broken], [cond("waf-api")], later, REPEAT, DONE, relay))
        .toEqual({ sent: 0, failed: 1 });
      bucket.failPuts.delete(RELAY_KEY);
      await dispatchAlerts(bucket, [ok], [], later + 60_000, REPEAT, DONE, relay);
      expect(await dispatchAlerts(bucket, [ok], [cond("waf-api")], later + 120_000, REPEAT, DONE, relay))
        .toEqual({ sent: 0, failed: 0 });
      expect(got).toHaveLength(1);
    });

    it("after a clean minute between, the next presence still sends at once", async () => {
      const { bucket, got, ok, relay } = await failAtGate();
      expect(await dispatchAlerts(bucket, [ok], [], at(3), REPEAT, DONE, relay)).toEqual({ sent: 0, failed: 0 });
      expect(await dispatchAlerts(bucket, [ok], [cond("waf-api")], at(4), REPEAT, DONE, relay))
        .toEqual({ sent: 1, failed: 0 });
      expect(got.map((o) => [o.kind, o.key])).toEqual([["repeat", "waf-api"]]);
    });

    it("the old episode's resolved still goes out when the key clears before any resend", async () => {
      const { bucket, got, ok, relay } = await failAtGate();
      await dispatchAlerts(bucket, [ok], [], at(3), REPEAT, DONE, relay);
      await dispatchAlerts(bucket, [ok], [], at(3) + COOLDOWN_MS, REPEAT, DONE, relay);
      expect(got.map((o) => [o.kind, o.key])).toEqual([["resolved", "waf-api"]]);
    });
  });
});

describe("resolved wording", () => {
  it("guard-state-corrupt's resolution does not imply the spend trip it caused has cleared", () => {
    const c: AlertCondition = { key: "guard-state-corrupt", priority: "urgent", resolvable: true,
                                title: "state/guard.json unreadable", message: "m" };
    let s = planAlerts({}, [c], T0, REPEAT).next;
    s = planAlerts(s, [], T0 + 60_000, REPEAT).next;
    const [o] = planAlerts(s, [], T0 + 60_000 + COOLDOWN_MS, REPEAT).send;
    expect(o.kind).toBe("resolved");
    expect(o.message).toMatch(/reads cleanly again/);
    expect(o.message).toMatch(/spend trip it caused stays until a raise or a new (billing )?period/);
  });
});

describe("channels", () => {
  const o: Outgoing = { key: "tripped-spend", kind: "alert", priority: "urgent", title: "Station blocked: spend", message: "m" };

  it("channelsFromEnv builds email only; ntfy is gone", () => {
    class FakeMessage {
      constructor(public from: string, public to: string, public raw: string) {}
    }
    const fullEmailEnv: AlertEnv = { ALERT_EMAIL: { send: async () => undefined }, ALERT_EMAIL_FROM: "a@x",
                                     ALERT_EMAIL_TO: "b@y" };
    expect(channelsFromEnv({ ...fullEmailEnv, NTFY_URL: "https://n/t" } as AlertEnv, () => T0, FakeMessage as never)
      .map((c) => c.name)).toEqual(["email"]);
    expect(channelsFromEnv({ NTFY_URL: "https://n/t", NTFY_TOKEN: "tk" } as AlertEnv, () => T0)).toEqual([]);
  });

  it("email: a send_email message from the configured sender to the configured recipient", async () => {
    const sent: { from: string; to: string; raw: string }[] = [];
    class FakeMessage {
      constructor(public from: string, public to: string, public raw: string) {}
    }
    const ch = emailChannel({ send: async (m) => { sent.push(m as unknown as FakeMessage); } }, "radio@example.org",
                            "ops@example.net", "llama radio", () => T0, FakeMessage as never);
    await ch.send(o);
    expect(sent[0]).toMatchObject({ from: "radio@example.org", to: "ops@example.net" });
    expect(sent[0].raw).toContain("Subject: llama radio: Station blocked: spend\r\n");
  });

  it("rawEmail: headers, an encoded non-ASCII subject, a base64 body", () => {
    const raw = rawEmail("a@example.org", "b@example.net", "Spend — 80%", "héllo", T0, "id1");
    expect(raw).toContain("From: a@example.org\r\nTo: b@example.net\r\n");
    expect(raw).toMatch(/Subject: =\?UTF-8\?B\?[A-Za-z0-9+/=]+\?=\r\n/);
    expect(raw).toContain("Message-ID: <id1@example.org>\r\n");
    expect(raw).toContain("Content-Transfer-Encoding: base64\r\n\r\n");
    const body = raw.split("\r\n\r\n")[1].replace(/\r\n/g, "");
    expect(new TextDecoder().decode(Uint8Array.from(atob(body), (c) => c.charCodeAt(0)))).toBe("héllo");
  });

  it("channelsFromEnv: only what is fully configured", () => {
    expect(channelsFromEnv({}, () => T0)).toEqual([]);
    const binding = { send: async () => undefined };
    expect(channelsFromEnv({ ALERT_EMAIL: binding, ALERT_EMAIL_FROM: "a@x" }, () => T0)).toEqual([]);
    expect(channelsFromEnv({ ALERT_EMAIL: binding, ALERT_EMAIL_FROM: "a@x", ALERT_EMAIL_TO: "b@y" }, () => T0)
      .map((c) => c.name)).toEqual(["email"]);
  });

  it("secretsFromEnv: the four CF_* values that are set", () => {
    expect(secretsFromEnv({})).toEqual([]);
    expect(secretsFromEnv({ CF_ACCOUNT_ID: "a1", CF_ZONE_ID: "z1", CF_ANALYTICS_TOKEN: "t1", CF_WAF_TOKEN: "w1",
                            STATION_NAME: "s" })).toEqual(["a1", "z1", "t1", "w1"]);
  });
});

describe("redaction of account details from off-account text", () => {
  const decodeEmail = (raw: string) => {
    const [head, body] = raw.split("\r\n\r\n");
    const b = body.replace(/\r\n/g, "");
    return head + "\n" + new TextDecoder().decode(Uint8Array.from(atob(b), (c) => c.charCodeAt(0)));
  };

  it("redact: Rulesets/accounts paths, bare 32-hex ids and the configured values", () => {
    const hex = "0123456789abcdef0123456789abcdef";
    expect(redact(`GET /zones/zz9/rulesets/phases/http_request_firewall_custom/entrypoint: HTTP 403`))
      .toBe("GET /zones/<id>/rulesets/phases/http_request_firewall_custom/entrypoint: HTTP 403");
    expect(redact(`PATCH /zones/zz9/rulesets/rs7/rules/r3: HTTP 500`)).toBe("PATCH /zones/<id>/rulesets/<id>/rules/<id>: HTTP 500");
    expect(redact(`/accounts/a1b2/x and zone ${hex}.`)).toBe("/accounts/<id>/x and zone <id>.");
    expect(redact("account acct-secret-77 is wrong", ["acct-secret-77"])).toBe("account <id> is wrong");
    expect(redact("short ids are left alone: ab", ["ab"])).toBe("short ids are left alone: ab");
  });

  it("a WafError carrying the zone, ruleset and rule ids reaches neither the relay nor email", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const ZONE = "zone-7f3a9c41";
    const RS = "ruleset-4b2e81d0";
    const RULE = "rule-91c0ffee";
    const HEXZ = "fedcba9876543210fedcba9876543210";
    const ACCT = "acct-5e1d0042"; // configured, so redacted as a literal value
    const env: GuardEnv = { MONTHLY_BUDGET_USD: "15", BILLING_ANNIVERSARY_DAY: "11", CF_ACCOUNT_ID: ACCT,
                            CF_ZONE_ID: ZONE, CF_ANALYTICS_TOKEN: "an-tok", CF_WAF_TOKEN: "waf-tok" };
    const cloud = fakeFetch({
      [`POST ${GRAPHQL_URL}`]: () => json(usageResponse()),
      [`GET ${API}/zones/${ZONE}/rulesets/phases/`]: () =>
        json({ success: true, result: { id: RS, rules: [{ id: RULE, action: "block", description: "station: kill switch",
                                                          expression: "x", enabled: true }] } }),
      [`PATCH ${API}/zones/${ZONE}/rulesets/${RS}/rules/${RULE}`]: (_c: FetchCall) =>
        json({ success: false, errors: [{ code: 10000, message: `account ${ACCT} zone ${HEXZ}: not authorized` }] }, 403),
    });
    const bucket = new MemoryBucket();
    const out = await guardStep({ bucket, now: () => T0, fetch: cloud.fetch, config: guardConfigFromEnv(env) });
    const waf = out.conditions.find((c) => c.key === "waf-api")!;
    expect(waf.message).toContain(RS); // the guard's own text (and the console) keep the detail
    expect(waf.message).toContain(ACCT);

    const raws: string[] = [];
    const binding = { send: async (m: unknown) => { raws.push((m as { raw: string }).raw); } };
    class FakeMessage {
      constructor(public from: string, public to: string, public raw: string) {}
    }
    const channels = channelsFromEnv({ ...env, ALERT_EMAIL: binding, ALERT_EMAIL_FROM: "radio@example.org",
                                       ALERT_EMAIL_TO: "ops@example.net" }, () => T0, FakeMessage as never);
    const relay = relaySink(bucket, secretsFromEnv(env));
    // waf-api is gated: the first two minutes send nothing, the third sends (redaction on the gated path).
    expect(await dispatchAlerts(bucket, channels, [waf], T0, REPEAT, undefined, relay)).toEqual({ sent: 0, failed: 0 });
    expect(await dispatchAlerts(bucket, channels, [waf], T0 + 60_000, REPEAT, undefined, relay))
      .toEqual({ sent: 0, failed: 0 });
    expect(bucket.objects.has(RELAY_KEY)).toBe(false);
    expect(raws).toHaveLength(0);
    expect(await dispatchAlerts(bucket, channels, [waf], T0 + 120_000, REPEAT, undefined, relay))
      .toEqual({ sent: 1, failed: 0 });
    expect(raws).toHaveLength(1);
    const relayText = bucket.objects.get(RELAY_KEY)!.body;
    const emailText = decodeEmail(raws[0]);
    expect(relayText).toMatch(/Kill switch not reconciled/);
    expect(emailText).toMatch(/Kill switch not reconciled/);
    for (const text of [relayText, emailText]) {
      for (const id of [ZONE, RS, RULE, HEXZ, ACCT]) expect([id, text.includes(id)]).toEqual([id, false]);
    }
  });
});

describe("dispatchAlerts", () => {
  it("sends to every channel, records the send, and does not resend the next minute", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const got: string[] = [];
    const ch = (name: string) => ({ name, send: async (o: Outgoing) => { got.push(`${name}:${o.key}`); } });
    expect(await dispatchAlerts(bucket, [ch("a"), ch("b")], [cond("lead-low")], T0, REPEAT)).toEqual({ sent: 1, failed: 0 });
    expect(got).toEqual(["a:lead-low", "b:lead-low"]);
    expect(bucket.json(ALERTS_KEY)["lead-low"].active).toBe(true);
    await dispatchAlerts(bucket, [ch("a")], [cond("lead-low")], T0 + 60_000, REPEAT);
    expect(got).toHaveLength(2);
  });

  it("one working channel is enough; when every channel fails the next invocation retries", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const broken = { name: "x", send: async () => { throw new Error("down"); } };
    const got: string[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(o.key); } };
    expect(await dispatchAlerts(bucket, [broken], [cond("offair-corrupt")], T0, REPEAT)).toEqual({ sent: 0, failed: 1 });
    expect(await dispatchAlerts(bucket, [broken, ok], [cond("offair-corrupt")], T0 + 60_000, REPEAT)).toEqual({ sent: 1, failed: 0 });
    expect(got).toEqual(["offair-corrupt"]);
  });

  it("a once alert no channel accepted is sent at the next invocation", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const broken = { name: "x", send: async () => { throw new Error("down"); } };
    const got: string[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(o.key); } };
    const c: AlertCondition = { ...cond("budget-80:2026-10-11:15", false), once: true };
    expect(await dispatchAlerts(bucket, [broken], [c], T0, REPEAT)).toEqual({ sent: 0, failed: 1 });
    expect(await dispatchAlerts(bucket, [ok], [c], T0 + 60_000, REPEAT)).toEqual({ sent: 1, failed: 0 });
    expect(got).toEqual(["budget-80:2026-10-11:15"]);
  });

  it("a failed alert for a condition back after the cooldown is retried the next minute, not a repeat period later", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const broken = { name: "x", send: async () => { throw new Error("down"); } };
    const got: string[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(`${o.kind}:${o.key}`); } };
    await dispatchAlerts(bucket, [ok], [cond("offair-corrupt")], T0, REPEAT);
    await dispatchAlerts(bucket, [ok], [], T0 + H, REPEAT); // clearing
    await dispatchAlerts(bucket, [ok], [], T0 + H + COOLDOWN_MS, REPEAT); // resolved
    const back = T0 + H + 2 * COOLDOWN_MS;
    expect(await dispatchAlerts(bucket, [broken], [cond("offair-corrupt")], back, REPEAT)).toEqual({ sent: 0, failed: 1 });
    expect(await dispatchAlerts(bucket, [ok], [cond("offair-corrupt")], back + 60_000, REPEAT)).toEqual({ sent: 1, failed: 0 });
    expect(got).toHaveLength(3);
    expect(got[2]).toMatch(/:offair-corrupt$/);
  });

  it("a resolved notice no channel accepted is retried the next minute", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const broken = { name: "x", send: async () => { throw new Error("down"); } };
    const got: string[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(`${o.kind}:${o.key}`); } };
    await dispatchAlerts(bucket, [ok], [cond("offair-corrupt")], T0, REPEAT);
    expect(await dispatchAlerts(bucket, [broken], [], T0 + H, REPEAT)).toEqual({ sent: 0, failed: 0 }); // clearing
    expect(await dispatchAlerts(bucket, [broken], [], T0 + H + COOLDOWN_MS, REPEAT)).toEqual({ sent: 0, failed: 1 });
    expect(bucket.json(ALERTS_KEY)["offair-corrupt"]).toMatchObject({ active: true, clearing_since: new Date(T0 + H).toISOString() });
    expect(await dispatchAlerts(bucket, [ok], [], T0 + H + COOLDOWN_MS + 60_000, REPEAT)).toEqual({ sent: 1, failed: 0 });
    expect(got).toEqual(["alert:offair-corrupt", "resolved:offair-corrupt"]);
    expect(bucket.json(ALERTS_KEY)["offair-corrupt"].active).toBe(false);
  });

  it("an undelivered alert that clears is dropped, never resolved, through dispatch", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const broken = { name: "x", send: async () => { throw new Error("down"); } };
    const got: string[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(`${o.kind}:${o.key}`); } };
    expect(await dispatchAlerts(bucket, [broken], [cond("offair-corrupt")], T0, REPEAT)).toEqual({ sent: 0, failed: 1 });
    await dispatchAlerts(bucket, [ok], [], T0 + 60_000, REPEAT);
    expect(await dispatchAlerts(bucket, [ok], [], T0 + 60_000 + COOLDOWN_MS, REPEAT)).toEqual({ sent: 0, failed: 0 });
    expect(got).toEqual([]);
    expect(bucket.json(ALERTS_KEY)).toEqual({});
  });

  it("a failed repeat of a delivered alert keeps it delivered: its resolved still goes out (P1)", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const broken = { name: "x", send: async () => { throw new Error("down"); } };
    const got: string[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(`${o.kind}:${o.key}`); } };
    await dispatchAlerts(bucket, [ok], [cond("tripped-spend")], T0, REPEAT);
    expect(await dispatchAlerts(bucket, [broken], [cond("tripped-spend")], T0 + REPEAT, REPEAT)).toEqual({ sent: 0, failed: 1 });
    expect(bucket.json(ALERTS_KEY)["tripped-spend"]).toMatchObject({ last_sent_at: null, delivered: true });
    await dispatchAlerts(bucket, [ok], [], T0 + REPEAT + 60_000, REPEAT);
    await dispatchAlerts(bucket, [ok], [], T0 + REPEAT + 60_000 + COOLDOWN_MS, REPEAT);
    expect(got).toEqual(["alert:tripped-spend", "resolved:tripped-spend"]);
    expect(bucket.json(ALERTS_KEY)["tripped-spend"].active).toBe(false);
  });

  it("an alert whose first send and retry both failed is still undelivered: dropped on clear, no resolved", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const broken = { name: "x", send: async () => { throw new Error("down"); } };
    const got: string[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(`${o.kind}:${o.key}`); } };
    await dispatchAlerts(bucket, [broken], [cond("offair-corrupt")], T0, REPEAT);
    expect(await dispatchAlerts(bucket, [broken], [cond("offair-corrupt")], T0 + 60_000, REPEAT)).toEqual({ sent: 0, failed: 1 });
    expect(bucket.json(ALERTS_KEY)["offair-corrupt"]).toMatchObject({ last_sent_at: null, delivered: false });
    await dispatchAlerts(bucket, [ok], [], T0 + 120_000, REPEAT);
    await dispatchAlerts(bucket, [ok], [], T0 + 120_000 + COOLDOWN_MS, REPEAT);
    expect(got).toEqual([]);
    expect(bucket.json(ALERTS_KEY)).toEqual({});
  });

  describe("a failed fresh alert over a still-active delivered episode keeps it delivered", () => {
    const M = 60_000;
    const setup = () => {
      vi.spyOn(console, "error").mockImplementation(() => {});
      const got: string[] = [];
      return {
        bucket: new MemoryBucket(), got,
        broken: { name: "x", send: async () => { throw new Error("down"); } },
        ok: { name: "ok", send: async (o: Outgoing) => { got.push(`${o.kind}:${o.key}`); } },
      };
    };

    it("P6: after a failed resolved, a failed return, then a re-clear: resolved still goes out", async () => {
      const { bucket, got, broken, ok } = setup();
      await dispatchAlerts(bucket, [ok], [cond("tripped-spend")], T0, REPEAT);
      await dispatchAlerts(bucket, [broken], [], T0 + M, REPEAT); // clearing
      expect(await dispatchAlerts(bucket, [broken], [], T0 + 16 * M, REPEAT)).toEqual({ sent: 0, failed: 1 }); // resolved fails
      expect(await dispatchAlerts(bucket, [broken], [cond("tripped-spend")], T0 + 17 * M, REPEAT))
        .toEqual({ sent: 0, failed: 1 }); // the fresh alert fails
      expect(bucket.json(ALERTS_KEY)["tripped-spend"]).toMatchObject({ active: true, delivered: true, last_sent_at: null });
      await dispatchAlerts(bucket, [broken], [], T0 + 18 * M, REPEAT); // clearing again
      await dispatchAlerts(bucket, [ok], [], T0 + 33 * M, REPEAT);
      expect(got).toEqual(["alert:tripped-spend", "resolved:tripped-spend"]);
      expect(bucket.json(ALERTS_KEY)["tripped-spend"].active).toBe(false);
    });

    it("P7: a window elapsed across incomplete batches, a failed return, then a re-clear: resolved still goes out", async () => {
      const { bucket, got, broken, ok } = setup();
      await dispatchAlerts(bucket, [ok], [cond("tripped-spend")], T0, REPEAT);
      await dispatchAlerts(bucket, [ok], [], T0 + M, REPEAT); // clearing, on a complete batch
      for (let m = 2; m <= 20; m++) {
        await dispatchAlerts(bucket, [ok], [], T0 + m * M, REPEAT, { complete: false, guardComplete: false });
      }
      expect(got).toEqual(["alert:tripped-spend"]);
      expect(await dispatchAlerts(bucket, [broken], [cond("tripped-spend")], T0 + 21 * M, REPEAT))
        .toEqual({ sent: 0, failed: 1 }); // the fresh alert fails
      for (let m = 22; m <= 37; m++) await dispatchAlerts(bucket, [ok], [], T0 + m * M, REPEAT);
      expect(got).toEqual(["alert:tripped-spend", "resolved:tripped-spend"]);
    });

    it("a failed return after a DELIVERED resolved still starts an undelivered episode", async () => {
      const { bucket, got, broken, ok } = setup();
      await dispatchAlerts(bucket, [ok], [cond("offair-corrupt")], T0, REPEAT);
      await dispatchAlerts(bucket, [ok], [], T0 + M, REPEAT);
      await dispatchAlerts(bucket, [ok], [], T0 + 16 * M, REPEAT); // resolved, delivered
      await dispatchAlerts(bucket, [broken], [cond("offair-corrupt")], T0 + 17 * M, REPEAT); // new episode fails
      expect(bucket.json(ALERTS_KEY)["offair-corrupt"]).toMatchObject({ active: true, delivered: false });
      await dispatchAlerts(bucket, [ok], [], T0 + 18 * M, REPEAT);
      await dispatchAlerts(bucket, [ok], [], T0 + 33 * M, REPEAT);
      expect(got).toEqual(["alert:offair-corrupt", "resolved:offair-corrupt"]); // no resolved for the undelivered episode
    });

    it("P10: a failed re-alert over an active never-delivered episode stays undelivered: dropped on re-clear, no resolved", async () => {
      const { bucket, got, broken, ok } = setup();
      await dispatchAlerts(bucket, [broken], [cond("tripped-spend")], T0, REPEAT);
      await dispatchAlerts(bucket, [ok], [], T0 + M, REPEAT); // clearing, on a complete batch
      for (let m = 2; m <= 20; m++) {
        await dispatchAlerts(bucket, [ok], [], T0 + m * M, REPEAT, { complete: false, guardComplete: false });
      }
      expect(await dispatchAlerts(bucket, [broken], [cond("tripped-spend")], T0 + 21 * M, REPEAT))
        .toEqual({ sent: 0, failed: 1 });
      expect(bucket.json(ALERTS_KEY)["tripped-spend"]).toMatchObject({ active: true, delivered: false, last_sent_at: null });
      for (let m = 22; m <= 37; m++) await dispatchAlerts(bucket, [ok], [], T0 + m * M, REPEAT);
      expect(got).toEqual([]);
      expect(bucket.json(ALERTS_KEY)).toEqual({});
    });
  });

  it("an older entry without `delivered` counts as delivered when a send was recorded", () => {
    const legacy: AlertState = { "waf-api": { active: true, resolvable: true, title: "t", first_at: new Date(T0).toISOString(),
                                              last_sent_at: new Date(T0).toISOString(), cleared_at: null } };
    const r1 = planAlerts(legacy, [], T0 + 60_000, REPEAT);
    expect(planAlerts(r1.next, [], T0 + 60_000 + COOLDOWN_MS, REPEAT).send.map((o) => o.kind)).toEqual(["resolved"]);
  });

  it("drops non-object entries from alerts.json instead of wedging every alert", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    for (const stored of [{ stale: null, n: 3, a: [1], s: "x" }, [null], null, 7]) {
      const bucket = new MemoryBucket();
      bucket.seed(ALERTS_KEY, JSON.stringify(stored));
      const got: string[] = [];
      const ok = { name: "ok", send: async (o: Outgoing) => { got.push(o.key); } };
      expect(await dispatchAlerts(bucket, [ok], [cond("tripped-spend")], T0, REPEAT)).toEqual({ sent: 1, failed: 0 });
      expect(got).toEqual(["tripped-spend"]);
      expect(Object.keys(bucket.json(ALERTS_KEY))).toEqual(["tripped-spend"]);
    }
  });

  it("the first write of alerts.json is create-only; a refused create loses nothing and does not throw", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const opts: unknown[] = [];
    const put = bucket.put.bind(bucket);
    bucket.put = async (k, v, o) => { if (k === ALERTS_KEY) opts.push(o.onlyIf); return put(k, v, o); };
    await dispatchAlerts(bucket, [], [cond("x")], T0, REPEAT);
    await dispatchAlerts(bucket, [], [cond("x"), cond("y")], T0 + 60_000, REPEAT);
    expect(opts[0]).toEqual({ etagDoesNotMatch: "*" });
    expect(opts[1]).toEqual({ etagMatches: expect.any(String) });

    // An overlapping invocation creates alerts.json between our read and our write.
    class Racing extends MemoryBucket {
      raced = false;
      override async get(key: string) {
        if (key === ALERTS_KEY && !this.raced) {
          this.raced = true;
          this.seed(ALERTS_KEY, { theirs: { active: true, resolvable: true, title: "t", first_at: new Date(T0).toISOString(),
                                            last_sent_at: new Date(T0).toISOString(), cleared_at: null } });
          return null;
        }
        return super.get(key);
      }
    }
    const racing = new Racing();
    const got: string[] = [];
    const ok = { name: "ok", send: async (o: Outgoing) => { got.push(o.key); } };
    expect(await dispatchAlerts(racing, [ok], [cond("ours")], T0, REPEAT)).toEqual({ sent: 1, failed: 0 });
    expect(Object.keys(racing.json(ALERTS_KEY))).toEqual(["theirs"]); // theirs stands
    // Our send is not recorded, so the next invocation re-plans it: a duplicate, never a loss.
    await dispatchAlerts(racing, [ok], [cond("ours"), cond("theirs")], T0 + 60_000, REPEAT);
    expect(got).toEqual(["ours", "ours"]);
  });

  it("a hung email binding times out and counts as a channel failure", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    class FakeMessage {
      constructor(public from: string, public to: string, public raw: string) {}
    }
    const hung = { send: () => new Promise<unknown>(() => {}) };
    const ch = emailChannel(hung, "radio@example.org", "ops@example.net", "s", () => T0, FakeMessage as never, [], 5);
    await expect(ch.send({ key: "k", kind: "alert", priority: "high", title: "t", message: "m" })).rejects.toThrow(/timed out/);
    expect(await dispatchAlerts(new MemoryBucket(), [ch], [cond("offair-corrupt")], T0, REPEAT)).toEqual({ sent: 0, failed: 1 });
  });

  it("writes alerts.json only when the state changed", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    await dispatchAlerts(bucket, [], [], T0, REPEAT);
    expect(bucket.puts(ALERTS_KEY)).toBe(0);
    await dispatchAlerts(bucket, [], [cond("x")], T0, REPEAT);
    await dispatchAlerts(bucket, [], [cond("x")], T0 + 60_000, REPEAT);
    expect(bucket.puts(ALERTS_KEY)).toBe(1);
  });

  it("alertSink passes the batch through: an incomplete batch resolves nothing", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const sink = alertSink(bucket, {}, () => T0);
    const ring = () => bucket.json(RELAY_KEY).ring.map((m: RelayMessage) => [m.kind, m.title]);
    await sink([cond("tripped-spend"), cond("lead-low")], T0, { complete: true, guardComplete: true });
    await sink([cond("offair-corrupt")], T0 + 60_000, { complete: false, guardComplete: false });
    expect(ring()).toEqual([["alert", "tripped-spend title"], ["alert", "lead-low title"], ["alert", "offair-corrupt title"]]);
    await sink([cond("tripped-spend")], T0 + 120_000, { complete: false, guardComplete: true });
    expect(ring()).toHaveLength(3); // offair-corrupt is clearing
    await sink([cond("tripped-spend")], T0 + 120_000 + COOLDOWN_MS, { complete: false, guardComplete: true });
    expect(ring().slice(3)).toEqual([["resolved", "offair-corrupt title"]]);
    expect(bucket.json(ALERTS_KEY)["lead-low"].active).toBe(true);
  });
});

describe("the relay", () => {
  const fixed = () => "stream-1";
  const broken = { name: "email", send: async () => { throw new Error("down"); } };
  const okEmail = (got: string[] = []) => ({ name: "email", send: async (o: Outgoing) => { got.push(o.key); } });
  const errors = (spy: { mock: { calls: unknown[][] } }) =>
    spy.mock.calls.map((c) => { try { return JSON.parse(String(c[0])); } catch { return null; } }).filter(Boolean);
  /** Record the `onlyIf` of every relay PUT. */
  const recordOnlyIf = (bucket: MemoryBucket) => {
    const opts: unknown[] = [];
    const put = bucket.put.bind(bucket);
    bucket.put = async (k: string, v: string, o: PutOptions) => {
      if (k === RELAY_KEY) opts.push(o.onlyIf);
      return put(k, v, o);
    };
    return opts;
  };

  it("one write per invocation carrying every message, after the emails", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const putsAtSend: number[] = [];
    const email = { name: "email", send: async () => { putsAtSend.push(bucket.puts(RELAY_KEY)); } };
    await dispatchAlerts(bucket, [email], [cond("tripped-spend"), cond("lead-low")], T0, REPEAT, undefined,
                         relaySink(bucket, [], fixed));
    expect(putsAtSend).toEqual([0, 0]);
    expect(bucket.puts(RELAY_KEY)).toBe(1);
    const doc = bucket.json(RELAY_KEY);
    expect(doc.stream).toBe("stream-1");
    expect(doc.ring.map((m: RelayMessage) => [m.seq, m.key, m.kind, m.priority])).toEqual(
      [[1, "tripped-spend", "alert", "high"], [2, "lead-low", "alert", "high"]]);
    expect(doc.ring[0].at).toBe(new Date(T0).toISOString());
    expect(doc.ring[0]).toEqual({ seq: 1, at: new Date(T0).toISOString(), key: "tripped-spend", kind: "alert",
                                  priority: "high", title: "tripped-spend title", message: "tripped-spend message" });
    expect(relayDocProblem(doc)).toBeNull();
  });

  it("an invocation that sends nothing neither reads nor writes the relay", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const relay = relaySink(bucket, [], fixed);
    await dispatchAlerts(bucket, [okEmail()], [cond("tripped-spend")], T0, REPEAT, undefined, relay);
    bucket.log = [];
    await dispatchAlerts(bucket, [okEmail()], [cond("tripped-spend")], T0 + 60_000, REPEAT, undefined, relay); // continuing
    await dispatchAlerts(bucket, [okEmail()], [cond("waf-api")], T0 + 120_000, REPEAT, undefined, relay);      // held
    expect(bucket.log.filter((l) => l.endsWith(RELAY_KEY))).toEqual([]);
  });

  it("seq increases across invocations and the ring keeps the last 50", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    let n = 0;
    const relay = relaySink(bucket, [], () => `stream-${++n}`);
    for (let i = 1; i <= 60; i++) {
      const c: AlertCondition = { ...cond(`budget-50:k${i}`, false), once: true };
      expect(await dispatchAlerts(bucket, [], [c], T0 + i * 60_000, REPEAT, undefined, relay)).toEqual({ sent: 1, failed: 0 });
    }
    const doc = bucket.json(RELAY_KEY);
    expect(RELAY_RING).toBe(50);
    expect(doc.ring).toHaveLength(50);
    expect(doc.ring.map((m: RelayMessage) => m.seq)).toEqual(Array.from({ length: 50 }, (_, i) => i + 11));
    expect(doc.ring[49].key).toBe("budget-50:k60");
    expect(doc.stream).toBe("stream-1");
    expect(bucket.puts(RELAY_KEY)).toBe(60);
  });

  it("title and message are redacted before they are written", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const c: AlertCondition = { key: "offair-corrupt", priority: "urgent", resolvable: true,
                                title: "PATCH /zones/zz9/rulesets/rs7 failed for acct-secret-77",
                                message: "GET /zones/zz9/rulesets/rs7/rules/r3: account acct-secret-77 refused" };
    await dispatchAlerts(bucket, [], [c], T0, REPEAT, undefined, relaySink(bucket, ["acct-secret-77"], fixed));
    const text = bucket.objects.get(RELAY_KEY)!.body;
    expect(text).toContain("/zones/<id>/rulesets/<id>");
    for (const id of ["zz9", "rs7", "r3", "acct-secret-77"]) expect([id, text.includes(id)]).toEqual([id, false]);
  });

  it("the first write is create-only; a store that refuses the precondition gets an unconditional put", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const opts = recordOnlyIf(bucket);
    const relay = relaySink(bucket, [], fixed);
    await dispatchAlerts(bucket, [], [cond("tripped-spend")], T0, REPEAT, undefined, relay);
    await dispatchAlerts(bucket, [], [cond("tripped-spend"), cond("lead-low")], T0 + 60_000, REPEAT, undefined, relay);
    expect(opts).toEqual([{ etagDoesNotMatch: "*" }, { etagMatches: expect.any(String) }]);
    expect(bucket.json(RELAY_KEY).ring.map((m: RelayMessage) => [m.seq, m.key])).toEqual(
      [[1, "tripped-spend"], [2, "lead-low"]]);

    const refusing = new MemoryBucket();
    const put = refusing.put.bind(refusing);
    refusing.put = async (k: string, v: string, o: PutOptions) => {
      if (k === RELAY_KEY && o.onlyIf && "etagDoesNotMatch" in o.onlyIf) throw new Error("precondition not supported");
      return put(k, v, o);
    };
    expect(await dispatchAlerts(refusing, [], [cond("tripped-spend")], T0, REPEAT, undefined, relaySink(refusing, [], fixed)))
      .toEqual({ sent: 1, failed: 0 });
    expect(refusing.json(RELAY_KEY).ring.map((m: RelayMessage) => m.key)).toEqual(["tripped-spend"]);
  });

  it("a lost race re-reads and retries once, then fails: at most 2 PUTs, logged", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    bucket.seed(RELAY_KEY, { stream: "s", ring: [] });
    const put = bucket.put.bind(bucket);
    bucket.put = async (k: string, v: string, o: PutOptions) => (k === RELAY_KEY ? (bucket.log.push(`put ${k}`), null)
                                                                                 : put(k, v, o));
    expect(await relaySink(bucket, [], fixed)([{ key: "k", kind: "alert", priority: "high", title: "t", message: "m" }], T0))
      .toBe(false);
    expect(bucket.puts(RELAY_KEY)).toBe(2);
    expect(errors(spy)).toContainEqual(expect.objectContaining({ event: "alert-relay-failed" }));

    // Losing only the first race: the racer's messages stand and ours follow them.
    const racing = new MemoryBucket();
    const msg = (seq: number, key: string) => ({ seq, at: new Date(T0).toISOString(), key, kind: "alert",
                                                 priority: "high", title: key, message: key });
    racing.seed(RELAY_KEY, { stream: "s", ring: [msg(1, "racer-a")] });
    const rput = racing.put.bind(racing);
    let raced = false;
    racing.put = async (k: string, v: string, o: PutOptions) => {
      if (k === RELAY_KEY && !raced) {
        raced = true;
        racing.seed(RELAY_KEY, { stream: "s", ring: [msg(1, "racer-a"), msg(2, "racer-b")] }); // new etag
      }
      return rput(k, v, o);
    };
    expect(await relaySink(racing, [], fixed)([{ key: "ours", kind: "alert", priority: "high", title: "t", message: "m" }],
                                              T0)).toBe(true);
    expect(racing.puts(RELAY_KEY)).toBe(2);
    const doc = racing.json(RELAY_KEY);
    expect(doc.stream).toBe("s");
    expect(doc.ring.map((m: RelayMessage) => [m.seq, m.key])).toEqual([[1, "racer-a"], [2, "racer-b"], [3, "ours"]]);
  });

  for (const [what, body] of [["unparseable", "{nope"], ["not an object", [1, 2]],
                              ["stream not a string", { stream: 5, ring: [] }],
                              ["ring not an array", { stream: "s", ring: {} }],
                              ["a non-integer seq", { stream: "s", ring: [{ seq: 1.5 }] }],
                              ["a boolean seq", { stream: "s", ring: [{ seq: true }] }],
                              ["a null ring entry", { stream: "s", ring: [null] }],
                              ["a non-object ring entry", { stream: "s", ring: [1] }]] as const) {
    it(`a corrupt object (${what}) is overwritten conditionally on its etag with a fresh stream, logged`, async () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
      const bucket = new MemoryBucket();
      bucket.seed(RELAY_KEY, body);
      const seeded = bucket.objects.get(RELAY_KEY)!.etag;
      if (typeof body !== "string") expect(relayDocProblem(body)).not.toBeNull();
      const opts = recordOnlyIf(bucket);
      expect(await dispatchAlerts(bucket, [], [cond("tripped-spend")], T0, REPEAT, undefined, relaySink(bucket, [], fixed)))
        .toEqual({ sent: 1, failed: 0 });
      expect(opts).toEqual([{ etagMatches: seeded }]);
      const doc = bucket.json(RELAY_KEY);
      expect(doc.stream).toBe("stream-1");
      expect(doc.ring.map((m: RelayMessage) => m.seq)).toEqual([1]);
      expect(errors(spy)).toContainEqual(expect.objectContaining({ event: "alert-relay-corrupt" }));
    });
  }

  it("relayDocProblem accepts a well-formed document, an empty ring included", () => {
    expect(relayDocProblem({ stream: "s", ring: [] })).toBeNull();
    expect(relayDocProblem({ stream: "s", ring: [{ seq: 3, extra: "x" }] })).toBeNull();
    expect(relayDocProblem(null)).not.toBeNull();
    expect(relayDocProblem("s")).not.toBeNull();
  });

  it("a hung relay write times out and never delays the email of a spend alert", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const put = bucket.put.bind(bucket);                        // R2 binding with no timeout of its own:
    bucket.put = (k, v, o) => (k === RELAY_KEY ? new Promise(() => {}) : put(k, v, o));   // hang the relay only
    const got: string[] = [];
    const email = { name: "email", send: async (o: Outgoing) => { got.push(o.key); } };
    const r = await dispatchAlerts(bucket, [email], [cond("tripped-spend")], T0, REPEAT, undefined,
                                   relaySink(bucket, [], fixed, 5));
    expect(got).toEqual(["tripped-spend"]);
    expect(r).toEqual({ sent: 1, failed: 0 });
    expect(errors(spy)).toContainEqual(expect.objectContaining({ event: "alert-relay-failed",
                                                                 error: expect.stringMatching(/timed out/) }));
  });

  it("delivered = email OR relay", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    // email fails, relay ok: delivered, not resent the next minute
    let bucket = new MemoryBucket();
    let relay = relaySink(bucket, [], fixed);
    const got: string[] = [];
    expect(await dispatchAlerts(bucket, [broken], [cond("offair-corrupt")], T0, REPEAT, undefined, relay))
      .toEqual({ sent: 1, failed: 0 });
    expect(await dispatchAlerts(bucket, [okEmail(got)], [cond("offair-corrupt")], T0 + 60_000, REPEAT, undefined, relay))
      .toEqual({ sent: 0, failed: 0 });
    expect(got).toEqual([]);
    // email ok, relay put throws: delivered
    bucket = new MemoryBucket();
    bucket.failPuts.add(RELAY_KEY);
    relay = relaySink(bucket, [], fixed);
    expect(await dispatchAlerts(bucket, [okEmail()], [cond("offair-corrupt")], T0, REPEAT, undefined, relay))
      .toEqual({ sent: 1, failed: 0 });
    // both fail: not delivered, sent again the next minute
    bucket = new MemoryBucket();
    bucket.failPuts.add(RELAY_KEY);
    relay = relaySink(bucket, [], fixed);
    expect(await dispatchAlerts(bucket, [broken], [cond("offair-corrupt")], T0, REPEAT, undefined, relay))
      .toEqual({ sent: 0, failed: 1 });
    expect(await dispatchAlerts(bucket, [okEmail(got)], [cond("offair-corrupt")], T0 + 60_000, REPEAT, undefined, relay))
      .toEqual({ sent: 1, failed: 0 });
    expect(got).toEqual(["offair-corrupt"]);
  });

  it("a gated alert whose email and relay both failed is retried the next minute, not re-gated", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    const relay = relaySink(bucket, [], fixed);
    bucket.failPuts.add(RELAY_KEY);
    for (const m of [0, 1]) {
      expect(await dispatchAlerts(bucket, [broken], [cond("waf-api")], T0 + m * 60_000, REPEAT, undefined, relay))
        .toEqual({ sent: 0, failed: 0 });
    }
    expect(await dispatchAlerts(bucket, [broken], [cond("waf-api")], T0 + 120_000, REPEAT, undefined, relay))
      .toEqual({ sent: 0, failed: 1 });
    bucket.failPuts.delete(RELAY_KEY);
    const got: Outgoing[] = [];
    const email = { name: "email", send: async (o: Outgoing) => { got.push(o); } };
    expect(await dispatchAlerts(bucket, [email], [cond("waf-api")], T0 + 180_000, REPEAT, undefined, relay))
      .toEqual({ sent: 1, failed: 0 });
    expect(got.map((o) => o.key)).toEqual(["waf-api"]);
    expect(got[0].message).toMatch(/3 consecutive/);
    expect(bucket.json(RELAY_KEY).ring[0].message).toMatch(/3 consecutive/);
  });
});
