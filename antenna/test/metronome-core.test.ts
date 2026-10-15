import { describe, expect, it } from "vitest";
import { gridOf } from "../src/grid";
import { ALARM_SLACK_MS, capAllows, currentLease, decideLease, EMPTY_STATE, expired, fallbackReason, holdLease,
         inWindow, isLive, type Lease, leaseKind, METRONOME_LEASE_MS, type MetronomeStatus, nextStalls, nextTarget,
         parseStoredLease, playLease, readState, recordTime, serializeLease, stalledFor, stateChanges, STORAGE_KEYS,
         storedLease, validateLease } from "../src/metronome-core";

const E = Date.parse("2026-10-10T12:00:00.000Z");
const D = 10_240;
const T = E + 1_000 * D; // a moment well inside the epoch
const CFG = { window: 16, grace: 3, offairAfterMs: 86_400_000, lookahead: 12, holdBack: 12 };
const H = { epoch_id: "e1", epoch: new Date(E).toISOString(), d: 10.24, first: 0, last: 1_000_000,
            published_at: new Date(E).toISOString(), container: "adts", fallback_version: "v1" };
const FB = { len: 7, notice: "fallback/v1/notice.aac" };
const play = (verdictAt: number, blocked = false, over: Record<string, unknown> = {}) =>
  ({ kind: "play", verdictAt, validUntil: verdictAt + METRONOME_LEASE_MS, blocked, horizon: H, fallback: FB, ...over });
const status = (s: Partial<MetronomeStatus>): MetronomeStatus =>
  ({ applied: "accepted", lease: "play", wrote: true, lastAlarmGoodAt: T, stalledMs: 0, stalls: 0, leaseVerdictAt: T, ...s });

describe("validateLease", () => {
  it("accepts a well-formed play or hold lease", () => {
    expect(validateLease(play(T))).toEqual({ ok: true, lease: play(T) });
    expect(validateLease({ kind: "hold", verdictAt: T, validUntil: T + 1, extra: 1 }))
      .toEqual({ ok: true, lease: { kind: "hold", verdictAt: T, validUntil: T + 1 } });
  });

  it("rejects every invalid shape", () => {
    const bad: [string, unknown][] = [
      ["null", null], ["array", []], ["string", "play"],
      ["kind", play(T, false, { kind: "go" })],
      ["blocked missing", play(T, false, { blocked: undefined })],
      ["blocked string", play(T, false, { blocked: "false" })],
      ["verdictAt NaN", play(T, false, { verdictAt: Number.NaN })],
      ["verdictAt missing", { kind: "hold", validUntil: T }],
      ["validUntil Infinity", play(T, false, { validUntil: Number.POSITIVE_INFINITY })],
      ["horizon missing", play(T, false, { horizon: undefined })],
      ["d 10.25", play(T, false, { horizon: { ...H, d: 10.25 } })],
      ["d string", play(T, false, { horizon: { ...H, d: "10.24" } })],
      ["epoch unparseable", play(T, false, { horizon: { ...H, epoch: "nonsense" } })],
      ["epoch number", play(T, false, { horizon: { ...H, epoch: E } })],
      ["first float", play(T, false, { horizon: { ...H, first: 0.5 } })],
      ["last string", play(T, false, { horizon: { ...H, last: "9" } })],
      ["epoch_id number", play(T, false, { horizon: { ...H, epoch_id: 7 } })],
      ["fallback_version number", play(T, false, { horizon: { ...H, fallback_version: 1 } })],
    ];
    for (const [what, raw] of bad) expect([what, validateLease(raw).ok]).toEqual([what, false]);
  });

  it("a malformed fallback becomes null, never an invalid lease", () => {
    for (const fallback of [{ len: "7", notice: "n" }, { len: 7 }, "x", [], { len: Number.NaN, notice: "n" }]) {
      const v = validateLease(play(T, false, { fallback }));
      expect(v.ok && v.lease.kind === "play" && v.lease.fallback).toBeNull();
    }
    const v = validateLease(play(T, false, { fallback: null }));
    expect(v.ok && v.lease.kind === "play" && v.lease.fallback).toBeNull();
  });
});

describe("expiry", () => {
  it("expiresAt = min(validUntil, now + 15 min): a far-future validUntil still expires at 15 min", () => {
    expect(storedLease({ kind: "hold", verdictAt: T, validUntil: T + 60_000 }, T).expiresAt).toBe(T + 60_000);
    expect(storedLease({ kind: "hold", verdictAt: T, validUntil: T + 86_400_000 }, T).expiresAt).toBe(T + METRONOME_LEASE_MS);
  });

  it("is written negated: NaN or missing is expired", () => {
    expect(expired({ expiresAt: T + 1 }, T)).toBe(false);
    expect(expired({ expiresAt: T }, T)).toBe(true);
    expect(expired({ expiresAt: Number.NaN }, T)).toBe(true);
    expect(expired({} as { expiresAt: number }, T)).toBe(true);
    expect(currentLease({ ...(play(T) as Lease), expiresAt: Number.NaN }, T)).toBeNull();
  });

  it("names the lease kind, none when expired", () => {
    const s = (l: Record<string, unknown>) => storedLease(l as unknown as Lease, T);
    expect(leaseKind(s(play(T)), T)).toBe("play");
    expect(leaseKind(s(play(T, true)), T)).toBe("blocked");
    expect(leaseKind(s({ kind: "hold", verdictAt: T, validUntil: T + 1 }), T)).toBe("hold");
    expect(leaseKind(s(play(T)), T + METRONOME_LEASE_MS)).toBe("none");
    expect(leaseKind(null, T)).toBe("none");
  });
});

describe("decideLease (ordering)", () => {
  const cur = storedLease(play(T) as Lease, T);
  it("supersedes an unblocked play lease whose verdictAt is not strictly newer, equal included", () => {
    expect(decideLease(cur, play(T - 1) as Lease, T)).toBe("superseded");
    expect(decideLease(cur, play(T) as Lease, T)).toBe("superseded");
    expect(decideLease(cur, play(T + 1) as Lease, T)).toBe("accepted");
  });

  it("accepts blocked play and hold whatever their verdictAt (blocking is fail-closed)", () => {
    expect(decideLease(cur, play(T - 60_000, true) as Lease, T)).toBe("accepted");
    expect(decideLease(cur, holdLease(T - 60_000, T), T)).toBe("accepted");
  });

  it("a future-dated verdictAt (a cron clock running ahead) never keeps a blocked lease out", () => {
    const ahead = storedLease(play(T + 3_600_000) as Lease, T); // an hour ahead
    expect(decideLease(ahead, play(T + 60_000) as Lease, T)).toBe("superseded");
    expect(decideLease(ahead, play(T + 60_000, true) as Lease, T)).toBe("accepted");
    expect(decideLease(ahead, holdLease(T + 60_000, T), T)).toBe("accepted");
    expect(storedLease(play(T + 3_600_000) as Lease, T).expiresAt).toBe(T + METRONOME_LEASE_MS); // the DO's clock
  });

  it("an older unblocked lease cannot supersede a newer blocked one, but is accepted with no current lease", () => {
    const blocked = storedLease(play(T, true) as Lease, T);
    expect(decideLease(blocked, play(T - 1) as Lease, T)).toBe("superseded");
    expect(decideLease(null, play(T - 1) as Lease, T)).toBe("accepted");
    expect(decideLease(cur, play(T - 1) as Lease, T + METRONOME_LEASE_MS)).toBe("accepted"); // current expired
  });
});

describe("isLive", () => {
  it("only an unexpired unblocked play lease that is not off air", () => {
    const s = (l: Record<string, unknown>) => storedLease(l as unknown as Lease, T);
    expect(isLive(s(play(T)), T, CFG)).toBe(true);
    expect(isLive(s(play(T, true)), T, CFG)).toBe(false);
    expect(isLive(s({ kind: "hold", verdictAt: T, validUntil: T + 1 }), T, CFG)).toBe(false);
    expect(isLive(s(play(T)), T + METRONOME_LEASE_MS, CFG)).toBe(false);
    // a horizon more than offairAfterMs stale is off air
    const late = E + 11 * D + CFG.offairAfterMs + 1;
    const stale = storedLease(play(late, false, { horizon: { ...H, last: 10 } }) as unknown as Lease, late);
    expect(isLive(stale, late, CFG)).toBe(false);
    expect(isLive(stale, late - 2, CFG)).toBe(true);
  });
});

describe("nextTarget", () => {
  const g = gridOf(H);
  it("is the first boundary + 25 ms strictly after the given time", () => {
    expect(nextTarget(g, E + 5 * D)).toBe(E + 5 * D + ALARM_SLACK_MS);
    expect(nextTarget(g, E + 5 * D + 24)).toBe(E + 5 * D + ALARM_SLACK_MS);
    expect(nextTarget(g, E + 5 * D + 25)).toBe(E + 6 * D + ALARM_SLACK_MS); // strictly after
    expect(nextTarget(g, E + 5 * D + 9_000)).toBe(E + 6 * D + ALARM_SLACK_MS);
  });

  it("skips missed boundaries instead of bursting", () => {
    expect(nextTarget(g, E + 50 * D + 100)).toBe(E + 51 * D + ALARM_SLACK_MS);
  });
});

describe("rolling windows", () => {
  it("just over 60 s after the oldest timestamp is allowed, just under is not", () => {
    const ts = Array.from({ length: 10 }, (_, i) => T + i * 1_000);
    expect(capAllows(ts, T + 59_999, 10)).toBe(false);
    expect(capAllows(ts, T + 60_001, 10)).toBe(true);
    expect(capAllows([], Number.NaN, 10)).toBe(false); // a NaN clock trips, never opens the cap
    expect(inWindow(ts, T + 60_001)).toHaveLength(9);
  });

  it("records into a fixed-size list", () => {
    let ts: number[] = [];
    for (let i = 0; i < 30; i++) ts = recordTime(ts, T + i, 12);
    expect(ts).toHaveLength(12);
    expect(ts.at(-1)).toBe(T + 29);
    expect(recordTime([T - 120_000], T, 12)).toEqual([T]); // old entries drop out
  });
});

describe("stalls", () => {
  it("measures from the later of the last alarm tick and playSince, and only while live", () => {
    expect(stalledFor(true, T - 40_000, T - 10_000, T)).toBe(10_000);
    expect(stalledFor(true, T - 5_000, T - 90_000, T)).toBe(5_000);
    expect(stalledFor(true, null, T - 45_000, T)).toBe(45_000);
    expect(stalledFor(false, T - 600_000, null, T)).toBe(0);
  });

  it("counts consecutive stalls over 30 s and resets otherwise", () => {
    expect(nextStalls(0, 30_001)).toBe(1);
    expect(nextStalls(1, 31_000)).toBe(2);
    expect(nextStalls(2, 30_000)).toBe(0);
  });
});

describe("stored state", () => {
  it("round-trips a lease and reads anything else as empty defaults", () => {
    const l = storedLease(play(T) as Lease, T);
    const { state, leaseInvalid } = readState({ lease: serializeLease(l), stalls: 2, putTimes: [1, "x", 3],
                                                lastBody: "#EXTM3U\n", lastTarget: Number.NaN });
    expect(leaseInvalid).toBeNull();
    expect(state).toEqual({ ...EMPTY_STATE, lease: l, stalls: 2, putTimes: [1, 3], lastBody: "#EXTM3U\n" });
  });

  it("an unparseable or invalid stored lease is invalid (no lease)", () => {
    expect(parseStoredLease("{nope").invalid).toMatch(/not JSON/);
    expect(parseStoredLease(42).invalid).toMatch(/not a string/);
    expect(parseStoredLease(JSON.stringify({ ...play(T), horizon: { ...H, d: 1 }, expiresAt: T })).invalid).toMatch(/d/);
    expect(parseStoredLease(undefined)).toEqual({ lease: null, invalid: null });
  });

  it("a stored lease whose finite expiresAt has passed loads, as expired", () => {
    const { lease, invalid } = parseStoredLease(JSON.stringify({ ...play(T), expiresAt: T }));
    expect(invalid).toBeNull();
    expect(lease).not.toBeNull();
    expect(currentLease(lease, T)).toBeNull();
  });

  it("a stored lease whose expiresAt is not a finite number is invalid (no lease)", () => {
    const raw = JSON.stringify(play(T));
    const withExpiry = (e: string) => `${raw.slice(0, -1)},"expiresAt":${e}}`;
    // 1e999 parses to Infinity (it would never expire); null and "x" are not numbers; raw has none.
    for (const stored of [withExpiry("1e999"), withExpiry("-1e999"), withExpiry("null"), withExpiry('"x"'), raw]) {
      const { state, leaseInvalid } = readState({ lease: stored });
      expect(leaseInvalid).toMatch(/expiresAt/);
      expect(state.lease).toBeNull();
    }
  });

  it("writes only the keys that changed, a removed lease as undefined", () => {
    const l = storedLease(play(T) as Lease, T);
    const before = { ...EMPTY_STATE, lease: l, stalls: 1 };
    expect(stateChanges(before, { ...before, stalls: 0, lastBody: "b" })).toEqual({ stalls: 0, lastBody: "b" });
    expect(stateChanges(before, { ...before, lease: null })).toStrictEqual({ lease: undefined });
    expect(Object.keys(stateChanges(EMPTY_STATE, { ...before, lastTarget: 1 })).sort()).toEqual(["lastTarget", "lease", "stalls"]);
  });

  it("the key set is fixed", () => {
    expect([...STORAGE_KEYS].sort()).toEqual(["alarmTimes", "lastAlarmGoodAt", "lastBody", "lastTarget", "lease",
                                              "playSince", "putTimes", "stalls"]);
    expect(Object.keys(EMPTY_STATE).sort()).toEqual([...STORAGE_KEYS].sort());
  });
});

describe("lease builders", () => {
  it("issue a lease valid for 15 min from issue, ordered by verdictAt", () => {
    expect(playLease(T - 3_000, T, true, H, FB)).toEqual({ kind: "play", verdictAt: T - 3_000,
                                                          validUntil: T + METRONOME_LEASE_MS, blocked: true,
                                                          horizon: H, fallback: FB });
    expect(holdLease(T - 3_000, T)).toEqual({ kind: "hold", verdictAt: T - 3_000, validUntil: T + METRONOME_LEASE_MS });
  });
});

describe("fallbackReason (cron's triggers)", () => {
  const p = playLease(T, T, false, H, FB);
  const b = playLease(T, T, true, H, FB);
  const hold = holdLease(T, T);
  it("(a) renew threw or timed out", () => {
    expect(fallbackReason(p, { error: "renew timed out after 15000 ms" })).toMatch(/renew failed: renew timed out/);
    expect(fallbackReason(null, { error: "boom" })).toMatch(/boom/);
  });

  it("(b) a play lease not accepted, or its write failed, unless superseded", () => {
    for (const lease of [p, b]) {
      expect(fallbackReason(lease, { status: status({}) })).toBeNull();
      expect(fallbackReason(lease, { status: status({ wrote: null }) })).toBeNull(); // cap, identical, nothing to build
      expect(fallbackReason(lease, { status: status({ wrote: false }) })).toMatch(/wrote=false/);
      expect(fallbackReason(lease, { status: status({ applied: "invalid", wrote: null }) })).toMatch(/invalid/);
      expect(fallbackReason(lease, { status: status({ applied: "off", wrote: null }) })).toMatch(/off/);
      expect(fallbackReason(lease, { status: status({ applied: "superseded", wrote: false }) })).toBeNull();
    }
    // (b) is about play leases only.
    expect(fallbackReason(hold, { status: status({ applied: "off", wrote: null }) })).toBeNull();
    expect(fallbackReason(null, { status: status({ applied: null, wrote: false }) })).toBeNull();
  });

  it("(c) two consecutive stalls; a single stall is not a trigger", () => {
    expect(fallbackReason(p, { status: status({ stalls: 1, stalledMs: 40_000 }) })).toBeNull();
    expect(fallbackReason(p, { status: status({ stalls: 2, stalledMs: 40_000 }) })).toMatch(/stalled on 2/);
    expect(fallbackReason(null, { status: status({ applied: null, stalls: 3 }) })).toMatch(/stalled/);
  });

  it("(c) fails closed: a stall count that is not a non-negative integer trips", () => {
    for (const stalls of [Number.NaN, undefined, 1.5, -1]) {
      expect(fallbackReason(p, { status: status({ stalls: stalls as number }) })).toMatch(/stalled/);
    }
    expect(fallbackReason(p, { status: status({ stalls: 0 }) })).toBeNull();
    expect(fallbackReason(p, { status: status({ stalls: 1 }) })).toBeNull();
  });

  it("(b) an accepted unblocked play lease the DO is not playing (accepted already expired)", () => {
    expect(fallbackReason(p, { status: status({ applied: "accepted", lease: "none" }) }))
      .toMatch(/applied=accepted, wrote=true, lease=none to a play lease/);
    expect(fallbackReason(p, { status: status({ applied: "accepted", lease: "play" }) })).toBeNull();
  });
});
