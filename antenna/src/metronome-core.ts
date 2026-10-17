/** The metronome's pure logic (metronome spec, docs/superpowers/specs/
 * 2026-10-14-antenna-metronome-design.md): the lease, its validation, ordering
 * and expiry, the alarm target, the rolling caps, the stall count, the stored
 * state's fixed key set, and the cron side's fallback decision. No IO and no
 * clock of its own: every function takes `nowMs`. metronome-engine.ts
 * sequences these over storage, alarms and R2; metronome.ts is the Durable
 * Object around the engine. */

import { GRID_D, type Grid, gridOf, type Horizon, indexAt, startMs } from "./grid";
import { type FallbackIndex, isOffair, type PlaylistConfig } from "./playlist";

/** Lease lifetime (Decision 3): a lease the DO accepts plays for at most this long. */
export const METRONOME_LEASE_MS = 15 * 60_000;
/** A renew that finds no alarm-confirmed tick for longer than this counts a stall. */
export const METRONOME_STALE_MS = 30_000;
/** Cron falls back at this many consecutive stalls (trigger c). */
export const STALLS_FALLBACK = 2;
/** At most this many DO playlist PUTs in a rolling CAP_WINDOW_MS, renew's included. */
export const MAX_DO_PUTS_PER_MINUTE = 10;
/** At most this many alarm() invocations in a rolling CAP_WINDOW_MS. */
export const MAX_ALARMS_PER_MINUTE = 12;
export const CAP_WINDOW_MS = 60_000;
/** Each DO R2 PUT is bounded by this (Promise.race, as alerts.ts bounds its sends). */
export const DO_PUT_TIMEOUT_MS = 5_000;
/** Cron's bound on one renew RPC: over two PUT timeouts, plus slack. */
export const RENEW_TIMEOUT_MS = 15_000;
/** Alarms aim this far past a boundary, as the cron loop sleeps to it. */
export const ALARM_SLACK_MS = 25;
/** No computed alarm target is further ahead of now than this (an early tick
 * stores the next boundary's, just over one segment out); a stored one past it
 * is clock skew or corruption and reads as none, or it parks the chain. */
export const MAX_TARGET_AHEAD_MS = 2 * GRID_D * 1000;
/** An alarm later than this past its target logs metronome-late. */
export const LATE_LOG_MS = 2_000;
/** The single instance: cron addresses it as idFromName(METRONOME_NAME). */
export const METRONOME_NAME = "metronome";

export interface PlayLease {
  kind: "play";
  /** When the issuing cron's guard step began (its state reads started): the ordering key. */
  verdictAt: number;
  /** Date.now() at issue + METRONOME_LEASE_MS. Never trusted alone: see storedLease. */
  validUntil: number;
  blocked: boolean;
  horizon: Horizon;
  fallback: FallbackIndex | null;
}

export interface HoldLease {
  kind: "hold";
  verdictAt: number;
  validUntil: number;
}

export type Lease = PlayLease | HoldLease;

/** A validated lease as the DO stores it, with the expiry it computed itself. */
export type StoredLease = Lease & { expiresAt: number };

export type LeaseKind = "play" | "blocked" | "hold" | "none";

/** What renew() returns to cron (the spec's MetronomeStatus). */
export interface MetronomeStatus {
  /** null: renew(null). */
  applied: "accepted" | "superseded" | "invalid" | "off" | null;
  /** The DO's lease after this call; "none" = absent or expired (and always when off). */
  lease: LeaseKind;
  /** This call's write succeeded; false = it failed or timed out; null = no write due
   * (no play lease, identical body, cap, nothing to build). */
  wrote: boolean | null;
  lastAlarmGoodAt: number | null;
  /** As it stood before this call (0 unless the stored lease's playlist was live). */
  stalledMs: number;
  /** Consecutive renews that found stalledMs > METRONOME_STALE_MS; cron falls back at >= 2. */
  stalls: number;
  leaseVerdictAt: number | null;
}

/** What cron calls: the DO's renew over RPC, bounded (metronome.ts metronomeClient). */
export interface MetronomeClient {
  renew(lease: Lease | null): Promise<MetronomeStatus>;
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function horizonProblem(h: unknown): string | null {
  if (!isObj(h)) return "horizon is not an object";
  if (h.d !== GRID_D) return `horizon.d is ${JSON.stringify(h.d)}, not ${GRID_D}`;
  if (typeof h.epoch_id !== "string") return "horizon.epoch_id is not a string";
  if (typeof h.epoch !== "string") return "horizon.epoch is not a string";
  if (!Number.isInteger(h.first) || !Number.isInteger(h.last)) return "horizon.first/last are not integers";
  if (!(h.fallback_version === null || typeof h.fallback_version === "string")) {
    return "horizon.fallback_version is not a string or null";
  }
  try {
    gridOf(h as unknown as Horizon);
  } catch (e) {
    return e instanceof Error ? e.message : String(e);
  }
  return null;
}

/** A fallback index the playlist may use, or null: anything but null or
 * {len: finite number, notice: string} becomes null, which usableFallback
 * already treats as "no usable fallback". A bad fallback never invalidates a lease. */
function fallbackOrNull(f: unknown): FallbackIndex | null {
  return isObj(f) && finite(f.len) && typeof f.notice === "string" ? { len: f.len, notice: f.notice } : null;
}

/** Validate a lease (data from another isolate, or from storage): on apply and on every load. */
export function validateLease(raw: unknown): { ok: true; lease: Lease } | { ok: false; reason: string } {
  if (!isObj(raw)) return { ok: false, reason: "lease is not an object" };
  if (!finite(raw.verdictAt) || !finite(raw.validUntil)) return { ok: false, reason: "verdictAt/validUntil not finite" };
  if (raw.kind === "hold") return { ok: true, lease: { kind: "hold", verdictAt: raw.verdictAt, validUntil: raw.validUntil } };
  if (raw.kind !== "play") return { ok: false, reason: `kind is ${JSON.stringify(raw.kind)}` };
  if (typeof raw.blocked !== "boolean") return { ok: false, reason: "blocked is not a boolean" };
  const problem = horizonProblem(raw.horizon);
  if (problem !== null) return { ok: false, reason: problem };
  return { ok: true, lease: { kind: "play", verdictAt: raw.verdictAt, validUntil: raw.validUntil, blocked: raw.blocked,
                              horizon: raw.horizon as unknown as Horizon, fallback: fallbackOrNull(raw.fallback) } };
}

/** The lease as stored on accept: expiry computed by the DO's own clock, never
 * later than METRONOME_LEASE_MS from now whatever validUntil says. */
export function storedLease(lease: Lease, nowMs: number): StoredLease {
  return { ...lease, expiresAt: Math.min(lease.validUntil, nowMs + METRONOME_LEASE_MS) };
}

/** Written negated, so a NaN or missing expiresAt is expired (pricing.ts overThreshold's idiom). */
export function expired(l: { expiresAt: number }, nowMs: number): boolean {
  return !(nowMs < l.expiresAt);
}

/** The lease if it is present and unexpired, else null. */
export function currentLease(l: StoredLease | null, nowMs: number): StoredLease | null {
  return l !== null && !expired(l, nowMs) ? l : null;
}

export function leaseKind(l: StoredLease | null, nowMs: number): LeaseKind {
  const c = currentLease(l, nowMs);
  if (c === null) return "none";
  if (c.kind === "hold") return "hold";
  return c.blocked ? "blocked" : "play";
}

/** Ordering. A blocked play lease or a hold is accepted unconditionally
 * (blocking is fail-closed); an unblocked play lease only when there is no
 * current lease or its verdictAt is strictly newer than the current one's. */
export function decideLease(current: StoredLease | null, incoming: Lease, nowMs: number): "accepted" | "superseded" {
  if (incoming.kind === "hold" || incoming.blocked) return "accepted";
  const c = currentLease(current, nowMs);
  return c === null || incoming.verdictAt > c.verdictAt ? "accepted" : "superseded";
}

/** The lease's playlist is live: an unexpired unblocked play lease that is not
 * off air at nowMs (a horizon more than offairAfterMs stale is). Only then does
 * the alarm chain tick. */
export function isLive(l: StoredLease | null, nowMs: number, cfg: PlaylistConfig): boolean {
  const c = currentLease(l, nowMs);
  if (c === null || c.kind !== "play" || c.blocked) return false;
  return !isOffair({ nowMs, horizon: c.horizon, fallback: c.fallback, offair: false }, cfg);
}

/** The first boundary + ALARM_SLACK_MS strictly after afterMs. The target comes
 * from the wall clock, never "previous target + d": lateness never accumulates
 * and missed boundaries are skipped, never written in a burst. */
export function nextTarget(g: Grid, afterMs: number): number {
  return startMs(g, indexAt(g, afterMs - ALARM_SLACK_MS) + 1) + ALARM_SLACK_MS;
}

/** The timestamps inside the rolling window ending at nowMs: just over
 * CAP_WINDOW_MS old is outside, just under is inside. */
export function inWindow(times: readonly number[], nowMs: number): number[] {
  return times.filter((t) => nowMs - t < CAP_WINDOW_MS);
}

export function capAllows(times: readonly number[], nowMs: number, cap: number): boolean {
  if (!Number.isFinite(nowMs)) return false; // NaN would empty the window and open the cap
  return inWindow(times, nowMs).length < cap;
}

/** Record nowMs, keeping at most `keep` timestamps (a fixed-size list). */
export function recordTime(times: readonly number[], nowMs: number, keep: number): number[] {
  return [...inWindow(times, nowMs), nowMs].slice(-keep);
}

/** How long the chain has gone without an alarm-confirmed tick, measured from
 * the later of the last one and the moment the current unblocked play lease
 * was first accepted. 0 unless the stored lease's playlist was live. */
export function stalledFor(wasLive: boolean, lastAlarmGoodAt: number | null, playSince: number | null,
                           nowMs: number): number {
  if (!wasLive) return 0;
  return Math.max(0, nowMs - Math.max(lastAlarmGoodAt ?? 0, playSince ?? 0));
}

export function nextStalls(prev: number, stalledMs: number): number {
  return stalledMs > METRONOME_STALE_MS ? prev + 1 : 0;
}

/** The DO's storage: a fixed set of keys that never grows (how stored bytes
 * are bounded; they cannot be metered). A test pins it. */
export const STORAGE_KEYS = ["lease", "playSince", "lastAlarmGoodAt", "lastTarget", "lastBody", "putTimes", "alarmTimes",
                             "stalls"] as const;
export type StorageKey = (typeof STORAGE_KEYS)[number];

export interface MetronomeState {
  lease: StoredLease | null;
  /** When the current unblocked play lease was accepted after no, blocked, hold or expired lease. */
  playSince: number | null;
  /** The last alarm-confirmed tick: only alarm() advances it. */
  lastAlarmGoodAt: number | null;
  /** The last armed alarm time. */
  lastTarget: number | null;
  /** The last successfully written playlist (null after a failed or timed-out PUT). */
  lastBody: string | null;
  /** The last MAX_DO_PUTS_PER_MINUTE PUT times and MAX_ALARMS_PER_MINUTE alarm() times. */
  putTimes: number[];
  alarmTimes: number[];
  stalls: number;
}

export const EMPTY_STATE: MetronomeState = { lease: null, playSince: null, lastAlarmGoodAt: null, lastTarget: null,
                                             lastBody: null, putTimes: [], alarmTimes: [], stalls: 0 };

const numOrNull = (v: unknown) => (finite(v) ? v : null);
const times = (v: unknown, keep: number) => (Array.isArray(v) ? v.filter(finite).slice(-keep) : []);

/** The stored lease: a JSON string written by serializeLease. Anything that
 * does not parse or validate, or whose expiresAt is not a finite number (a
 * stored 1e999 is Infinity and would never expire), is `invalid` (the engine
 * deletes it: no lease). */
export function parseStoredLease(raw: unknown): { lease: StoredLease | null; invalid: string | null } {
  if (raw === undefined || raw === null) return { lease: null, invalid: null };
  if (typeof raw !== "string") return { lease: null, invalid: "stored lease is not a string" };
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { lease: null, invalid: "stored lease is not JSON" };
  }
  const v = validateLease(parsed);
  if (!v.ok) return { lease: null, invalid: `stored lease: ${v.reason}` };
  const expiresAt = isObj(parsed) ? parsed.expiresAt : undefined;
  if (!finite(expiresAt)) return { lease: null, invalid: "stored lease: expiresAt not finite" };
  return { lease: { ...v.lease, expiresAt }, invalid: null };
}

export function serializeLease(l: StoredLease): string {
  return JSON.stringify(l);
}

/** The state from the raw stored values (a missing or malformed value reads as
 * its empty default), plus why the stored lease was invalid, if it was. */
export function readState(raw: Partial<Record<StorageKey, unknown>>): { state: MetronomeState; leaseInvalid: string | null } {
  const { lease, invalid } = parseStoredLease(raw.lease);
  const stalls = raw.stalls;
  return {
    state: {
      lease,
      playSince: numOrNull(raw.playSince),
      lastAlarmGoodAt: numOrNull(raw.lastAlarmGoodAt),
      lastTarget: numOrNull(raw.lastTarget),
      lastBody: typeof raw.lastBody === "string" ? raw.lastBody : null,
      putTimes: times(raw.putTimes, MAX_DO_PUTS_PER_MINUTE),
      alarmTimes: times(raw.alarmTimes, MAX_ALARMS_PER_MINUTE),
      stalls: Number.isInteger(stalls) && (stalls as number) >= 0 ? (stalls as number) : 0,
    },
    leaseInvalid: invalid,
  };
}

/** The stored value of each key of `next` that differs from `prev` (lease as
 * its JSON string; a removed lease is `undefined`: the engine deletes the key). */
export function stateChanges(prev: MetronomeState, next: MetronomeState): Partial<Record<StorageKey, unknown>> {
  const out: Partial<Record<StorageKey, unknown>> = {};
  const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
  for (const k of STORAGE_KEYS) {
    if (same(prev[k], next[k])) continue;
    out[k] = k === "lease" ? (next.lease === null ? undefined : serializeLease(next.lease)) : next[k];
  }
  return out;
}

/** A play lease issued by cron from a known verdict and an accepted horizon. */
export function playLease(verdictAt: number, issuedAt: number, blocked: boolean, horizon: Horizon,
                          fallback: FallbackIndex | null): PlayLease {
  return { kind: "play", verdictAt, validUntil: issuedAt + METRONOME_LEASE_MS, blocked, horizon, fallback };
}

/** A hold: a known blocked verdict whose inputs are unusable, or a refused horizon. */
export function holdLease(verdictAt: number, issuedAt: number): HoldLease {
  return { kind: "hold", verdictAt, validUntil: issuedAt + METRONOME_LEASE_MS };
}

/** Why cron must fall back (run its loop where the lease table allows, and
 * raise metronome-down), or null when the DO is healthy:
 * (a) renew threw or timed out;
 * (b) cron sent a play lease (blocked or not), it was not superseded, and it
 *     was not accepted or its write failed, or the DO's lease is not what it
 *     was told ("play", or "blocked" for a blocked one: say, accepted already expired);
 * (c) STALLS_FALLBACK consecutive renews found the chain stalled. Written
 *     negated: a stall count that is not a non-negative integer trips too. */
export function fallbackReason(sent: Lease | null,
                               r: { status: MetronomeStatus } | { error: string }): string | null {
  if ("error" in r) return `renew failed: ${r.error}`;
  const s = r.status;
  if (sent?.kind === "play" && s.applied !== "superseded"
      && (s.applied !== "accepted" || s.wrote === false || s.lease !== (sent.blocked ? "blocked" : "play"))) {
    const kind = sent.blocked ? "blocked play" : "play";
    return `renew answered applied=${s.applied}, wrote=${s.wrote}, lease=${s.lease} to a ${kind} lease`;
  }
  if (!(Number.isInteger(s.stalls) && s.stalls >= 0 && s.stalls < STALLS_FALLBACK)) {
    return `alarm chain stalled on ${s.stalls} consecutive renews (${s.stalledMs} ms)`;
  }
  return null;
}
