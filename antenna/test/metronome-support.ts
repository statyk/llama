import type { ClockConfig } from "../src/clock";
import { putLive } from "../src/live";
import { type Lease, METRONOME_LEASE_MS } from "../src/metronome-core";
import { MetronomeEngine, type MetronomePort } from "../src/metronome-engine";
import { MemoryBucket } from "./support";

export const E = Date.parse("2026-10-10T12:00:00.000Z");
export const D = 10_240;
/** The deployed playlist config (wrangler.jsonc). */
export const CFG: ClockConfig = { window: 16, lookahead: 12, holdBack: 12, grace: 3, offairAfterMs: 86_400_000,
                                  loopMs: 75_000, liveMaxAge: 5, leadFloorMs: 16 * 3_600_000 };
export const HORIZON = { epoch_id: "e1", epoch: new Date(E).toISOString(), d: 10.24, first: 0, last: 1_000_000,
                         published_at: new Date(E).toISOString(), container: "adts", fallback_version: "v1" };
export const FALLBACK = { len: 7, notice: "fallback/v1/notice.aac" };

/** A lease as cron issues it at nowMs (verdictAt = nowMs unless given). */
export function lease(nowMs: number, o: { blocked?: boolean; hold?: boolean; verdictAt?: number;
                                          horizon?: Record<string, unknown>; fallback?: unknown } = {}): Lease {
  const verdictAt = o.verdictAt ?? nowMs;
  if (o.hold) return { kind: "hold", verdictAt, validUntil: nowMs + METRONOME_LEASE_MS };
  return { kind: "play", verdictAt, validUntil: nowMs + METRONOME_LEASE_MS, blocked: o.blocked ?? false,
           horizon: { ...HORIZON, ...o.horizon }, fallback: (o.fallback === undefined ? FALLBACK : o.fallback) } as Lease;
}

/** An in-memory MetronomePort: a settable clock, a Map for storage, one alarm
 * slot, a MemoryBucket, timers that fire only when asked, and an optional gate
 * that holds every PUT until released. */
export class FakePort implements MetronomePort {
  t: number;
  on = true;
  cfg: ClockConfig = CFG;
  store = new Map<string, unknown>();
  alarmAt: number | null = null;
  bucket = new MemoryBucket();
  logs: Record<string, unknown>[] = [];
  /** Every storage, alarm and PUT operation in order: "save k1,k2", "setAlarm t", "deleteAlarm", "put". */
  ops: string[] = [];
  failSetAlarm = false;
  failLoad = false;
  private gate: Promise<void> | null = null;
  private fires: (() => void)[] = [];

  constructor(t: number) {
    this.t = t;
  }

  now() { return this.t; }
  switchOn() { return this.on; }
  config() { return this.cfg; }
  async load() {
    if (this.failLoad) throw new Error("injected load failure");
    return Object.fromEntries(this.store);
  }
  async save(changes: Record<string, unknown>) {
    this.ops.push(`save ${Object.keys(changes).sort().join(",")}`);
    for (const [k, v] of Object.entries(changes)) {
      if (v === undefined) this.store.delete(k);
      else this.store.set(k, structuredClone(v));
    }
  }
  async getAlarm() { return this.alarmAt; }
  async setAlarm(t: number) {
    if (this.failSetAlarm) throw new Error("injected setAlarm failure");
    this.ops.push(`setAlarm ${t}`);
    this.alarmAt = t;
  }
  async deleteAlarm() {
    this.ops.push("deleteAlarm");
    this.alarmAt = null;
  }
  async putLive(body: string, liveMaxAge: number) {
    this.ops.push("put");
    if (this.gate) await this.gate;
    await putLive(this.bucket, body, liveMaxAge);
  }
  timer(_ms: number) {
    let fire!: () => void;
    const done = new Promise<void>((r) => { fire = r; });
    this.fires.push(fire);
    return { done, clear: () => {} };
  }
  log(event: string, fields: Record<string, unknown>) {
    this.logs.push({ event, ...fields });
  }

  /** Hold every PUT until the returned function is called. */
  holdPuts(): () => void {
    let release!: () => void;
    this.gate = new Promise<void>((r) => { release = r; });
    return () => { this.gate = null; release(); };
  }
  /** Fire every pending timer (a PUT timeout). */
  fireTimers() {
    for (const f of this.fires.splice(0)) f();
  }
  events(name: string) {
    return this.logs.filter((l) => l.event === name);
  }
  puts() {
    return this.bucket.puts("live.m3u8");
  }
  body() {
    return this.bucket.objects.get("live.m3u8")?.body ?? null;
  }
}

export function engineAt(t: number) {
  const port = new FakePort(t);
  return { port, engine: new MetronomeEngine(port) };
}

/** Let queued microtasks run (for interleaving tests). */
export const settle = () => new Promise<void>((r) => setTimeout(r, 0));

export const seqOf = (body: string) => Number(/#EXT-X-MEDIA-SEQUENCE:(\d+)/.exec(body)![1]);
export const lastListed = (body: string) =>
  seqOf(body) + body.split("\n").filter((l) => l !== "" && !l.startsWith("#")).length - 1;
