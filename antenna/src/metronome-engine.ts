/** The metronome's sequencing (metronome spec, "Metronome (the DO)"): renew()
 * and alarm() over a port (storage, alarm, R2, clock, logs), so every rule is
 * tested with a fake clock and a fake bucket; metronome.ts binds the port to a
 * Durable Object. State lives in storage, memory is a cache only (the object is
 * evicted between alarms): every call loads the fixed key set and writes back
 * what changed, plus `stalls` on every renew.
 *
 * Spend is the strict surface. The bounds this file enforces, whatever its
 * inputs: at most one PUT per call; at most MAX_DO_PUTS_PER_MINUTE PUTs in a
 * rolling minute, renew's included, the slot reserved (its storage write
 * awaited) before the PUT is issued; each PUT bounded by DO_PUT_TIMEOUT_MS; at
 * most MAX_ALARMS_PER_MINUTE alarm() invocations re-arm per rolling minute; the
 * chain ticks only while the lease's playlist is live; an expired, held,
 * blocked or absent lease never re-arms. */

import { type ClockConfig, MAX_LOOP_MS } from "./clock";
import { gridOf } from "./grid";
import { renderLive } from "./live";
import { ALARM_SLACK_MS, capAllows, currentLease, decideLease, DO_PUT_TIMEOUT_MS, isLive, LATE_LOG_MS, leaseKind,
         MAX_ALARMS_PER_MINUTE, MAX_DO_PUTS_PER_MINUTE, type MetronomeState, type MetronomeStatus, nextStalls,
         nextTarget, type PlayLease, readState, recordTime, stalledFor, stateChanges, type StorageKey, storedLease,
         validateLease } from "./metronome-core";

export interface MetronomePort {
  now(): number;
  /** env.METRONOME is exactly "on". Read on every call: the rollback switch reaches the DO directly. */
  switchOn(): boolean;
  /** The playlist config (configFromEnv), read on every call. */
  config(): ClockConfig;
  /** The stored values of the fixed key set (missing keys absent). */
  load(): Promise<Partial<Record<StorageKey, unknown>>>;
  /** Write these keys; a value of `undefined` deletes the key. */
  save(changes: Partial<Record<StorageKey, unknown>>): Promise<void>;
  getAlarm(): Promise<number | null>;
  setAlarm(atMs: number): Promise<void>;
  deleteAlarm(): Promise<void>;
  /** PUT live.m3u8 (live.ts putLive). */
  putLive(body: string, liveMaxAge: number): Promise<void>;
  /** A timer that resolves `done` after ms; `clear` cancels it. */
  timer(ms: number): { done: Promise<void>; clear(): void };
  /** One structured anomaly line. */
  log(event: string, fields: Record<string, unknown>): void;
}

/** One call's view: what storage holds, and what this call will leave there. */
interface Tx {
  stored: MetronomeState;
  s: MetronomeState;
}

type WriteResult = "put" | "identical" | "null" | "cap" | "failed";

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));
/** An alarm-confirmed tick: a PUT, an identical body, or nothing to build by rule. */
const confirms = (r: WriteResult) => r === "put" || r === "identical" || r === "null";
/** The boundary the last genuine tick built for (its re-armed target less one segment and the slack), or now if
 * later: a duplicate or a renew between an early tick and its boundary rebuilds that tick's playlist, never an
 * older one. With no stored target, or one renew armed, this is now. */
const tickBoundary = (lease: PlayLease, lastTarget: number | null, now: number) =>
  Math.max(now, (lastTarget ?? now) - gridOf(lease.horizon).dMs - ALARM_SLACK_MS);
const copy = (s: MetronomeState): MetronomeState => ({ ...s, putTimes: [...s.putTimes], alarmTimes: [...s.alarmTimes] });

export class MetronomeEngine {
  /** Every write path runs inside this one promise chain (spec "Serialized sections"). */
  private chain: Promise<unknown> = Promise.resolve();
  /** "Logged once" marks, per anomaly: memory only, so an evicted object may log a persisting anomaly again. */
  private readonly marks = new Map<string, string>();

  constructor(private readonly port: MetronomePort) {}

  /** Cron's call, every minute (`null` leaves the lease alone: a health check). */
  renew(lease: unknown): Promise<MetronomeStatus> {
    return this.serial(() => this.renewSteps(lease ?? null));
  }

  /** The alarm chain's tick. Never throws to the runtime: an escaping
   * exception would hand the chain to the platform's 6-retry backoff. */
  async alarm(): Promise<void> {
    try {
      // 1. The rollback switch.
      if (!this.port.switchOn()) {
        await this.port.deleteAlarm();
        return;
      }
      await this.serial(() => this.alarmSteps());
    } catch (e) {
      this.port.log("metronome-alarm-error", { error: msg(e) });
    }
  }

  private serial<T>(fn: () => Promise<T>): Promise<T> {
    const run = this.chain.then(fn, fn);
    this.chain = run.catch(() => undefined);
    return run;
  }

  /** Log `event` when an episode of `key` starts (or its `id` changes); a later call with active=false ends it. */
  private episode(key: string, active: boolean, id: string, event: string, fields: Record<string, unknown>): void {
    if (!active) {
      this.marks.delete(key);
      return;
    }
    if (this.marks.get(key) === id) return;
    this.marks.set(key, id);
    this.port.log(event, fields);
  }

  private async begin(): Promise<Tx> {
    const { state, leaseInvalid } = readState(await this.port.load());
    if (leaseInvalid !== null) {
      // An invalid or unparseable stored lease is deleted on load: no lease.
      this.port.log("metronome-lease-invalid", { reason: leaseInvalid, source: "storage" });
      await this.port.save({ lease: undefined });
    }
    return { stored: copy(state), s: copy(state) };
  }

  /** Write back what changed; `withStalls` writes `stalls` even when unchanged. */
  private async flush(tx: Tx, withStalls = false): Promise<void> {
    const changes = stateChanges(tx.stored, tx.s);
    if (withStalls) changes.stalls = tx.s.stalls;
    if (Object.keys(changes).length > 0) await this.port.save(changes);
    tx.stored = copy(tx.s);
  }

  private async disarm(): Promise<void> {
    if ((await this.port.getAlarm()) !== null) await this.port.deleteAlarm();
  }

  /** The PUT, bounded by DO_PUT_TIMEOUT_MS; never throws. */
  private async boundedPut(body: string, liveMaxAge: number): Promise<"ok" | string> {
    const t = this.port.timer(DO_PUT_TIMEOUT_MS);
    try {
      return await Promise.race([
        this.port.putLive(body, liveMaxAge).then(() => "ok"),
        t.done.then(() => `timed out after ${DO_PUT_TIMEOUT_MS} ms`),
      ]);
    } catch (e) {
      return msg(e);
    } finally {
      t.clear();
    }
  }

  /** Build the playlist for buildAtMs from a play lease and write it, unless
   * the body equals lastBody, the cap is reached or nothing can be built. */
  private async write(tx: Tx, lease: PlayLease, buildAtMs: number, now: number, cfg: ClockConfig,
                      source: "renew" | "alarm"): Promise<WriteResult> {
    const src = { horizon: lease.horizon, fallback: lease.fallback, offair: lease.blocked };
    // The off-air notice is numbered from now + 75 s (offairSequence), the cron
    // loop's max(scheduledTime + loopMs, now) shape: strictly above every live
    // segment either writer has listed, and never decreasing across renews.
    const { body, offairWithoutFallback } = renderLive(src, buildAtMs, now + MAX_LOOP_MS, cfg);
    this.episode("offair-without-fallback", offairWithoutFallback !== null, String(lease.verdictAt),
                 "offair-without-fallback", { reason: offairWithoutFallback, epoch_id: lease.horizon.epoch_id, source });
    if (body === null) {
      // Before the epoch, or no usable fallback for a loop entry: nothing by rule. Once per lease.
      this.episode("null-build", true, String(lease.verdictAt), "metronome-null-build",
                   { verdictAt: lease.verdictAt, at: buildAtMs, source });
      return "null";
    }
    this.episode("null-build", false, "", "", {});
    if (body === tx.s.lastBody) return "identical";
    if (!capAllows(tx.s.putTimes, now, MAX_DO_PUTS_PER_MINUTE)) {
      this.episode("cap", true, "cap", "metronome-cap", { cap: MAX_DO_PUTS_PER_MINUTE, source });
      return "cap";
    }
    this.episode("cap", false, "", "", {});
    // Reserve the slot, its storage write awaited, before the PUT is issued.
    tx.s.putTimes = recordTime(tx.s.putTimes, now, MAX_DO_PUTS_PER_MINUTE);
    await this.flush(tx);
    const r = await this.boundedPut(body, cfg.liveMaxAge);
    if (r !== "ok") {
      // The bytes in R2 are unknown now: the next write is never skipped as identical.
      tx.s.lastBody = null;
      this.episode("put-failed", true, "put-failed", "metronome-put-failed", { error: r, source });
      return "failed";
    }
    this.episode("put-failed", false, "", "", {});
    tx.s.lastBody = body;
    return "put";
  }

  private async alarmSteps(): Promise<void> {
    const now = this.port.now();
    const cfg = this.port.config();
    // 2. Not a current unblocked play lease (none, hold, blocked, expired):
    //    delete any pending alarm and stop. The next renew restarts the chain.
    const tx = await this.begin();
    const s = tx.s;
    const cur = currentLease(s.lease, now);
    this.episode("expired", s.lease !== null && cur === null, String(s.lease?.verdictAt), "metronome-expired",
                 { verdictAt: s.lease?.verdictAt ?? null, source: "alarm" });
    if (cur === null || cur.kind !== "play" || cur.blocked) {
      await this.disarm();
      await this.flush(tx);
      return;
    }
    // 2b. A duplicate or retried delivery: an alarm is still pending, which a
    //     genuine delivery never sees while its handler runs (getAlarm() is null
    //     then, unless setAlarm ran since). Idempotent: build for now, or for the
    //     last tick's boundary if later, and PUT only if the bytes differ; no
    //     re-arm, lastTarget unchanged, not counted. Logged as a duplicate only when
    //     a counted tick ran within the last half segment: a renew that lands while
    //     this delivery is in flight reads getAlarm() as null and arms the next
    //     boundary, so this genuine delivery, a segment after the last counted one,
    //     finds it pending (measured: 13 times in 34 h on verification day).
    const pending = await this.port.getAlarm();
    const lastCounted = s.alarmTimes.length > 0 ? Math.max(...s.alarmTimes) : Number.NEGATIVE_INFINITY;
    const duplicate = pending !== null && now - lastCounted < gridOf(cur.horizon).dMs / 2;
    this.episode("duplicate", duplicate, "duplicate", "metronome-duplicate", { pending, sinceTickMs: now - lastCounted });
    if (pending !== null) {
      const at = tickBoundary(cur, s.lastTarget, now);
      if (confirms(await this.write(tx, cur, at, now, cfg, "alarm"))) s.lastAlarmGoodAt = now;
      await this.flush(tx);
      return;
    }
    // 3. Count the invocation; at the cap, do not re-arm.
    if (!capAllows(s.alarmTimes, now, MAX_ALARMS_PER_MINUTE)) {
      this.episode("alarm-cap", true, "alarm-cap", "metronome-alarm-cap", { cap: MAX_ALARMS_PER_MINUTE });
      await this.flush(tx);
      return;
    }
    this.episode("alarm-cap", false, "", "", {});
    s.alarmTimes = recordTime(s.alarmTimes, now, MAX_ALARMS_PER_MINUTE);
    const prevTarget = s.lastTarget;
    const lateMs = prevTarget === null ? 0 : now - prevTarget;
    this.episode("late", lateMs > LATE_LOG_MS, "late", "metronome-late", { lateMs, target: prevTarget });
    // 4. Re-arm first, only while live, to the first boundary + 25 ms strictly
    //    after max(now, lastTarget): no hot loop when an alarm arrives before
    //    the DO's clock passes its boundary.
    if (isLive(s.lease, now, cfg)) {
      const target = nextTarget(gridOf(cur.horizon), Math.max(now, prevTarget ?? Number.NEGATIVE_INFINITY));
      try {
        await this.port.setAlarm(target);
      } catch (e) {
        this.port.log("metronome-rearm-failed", { error: msg(e), target });
        await this.flush(tx);
        return;
      }
      s.lastTarget = target;
    }
    // 5. Build for the due boundary (an early alarm builds for its own
    //    boundary) and write unless identical, capped and bounded.
    const due = Math.max(now, (prevTarget ?? now) - ALARM_SLACK_MS);
    const r = await this.write(tx, cur, due, now, cfg, "alarm");
    // 6. Alarm-confirmed ticks: a PUT, an identical body, or nothing to build by rule.
    if (confirms(r)) s.lastAlarmGoodAt = now;
    await this.flush(tx);
  }

  private async renewSteps(raw: unknown): Promise<MetronomeStatus> {
    // 1. The rollback switch.
    if (!this.port.switchOn()) {
      await this.port.deleteAlarm();
      return { applied: "off", lease: "none", wrote: null, lastAlarmGoodAt: null, stalledMs: 0, stalls: 0,
               leaseVerdictAt: null };
    }
    const now = this.port.now();
    const cfg = this.port.config();
    // 2. Load (an invalid stored lease is deleted), then the stall count as it
    //    stood. `stalls` is written on every renew, changed or not, so a healthy
    //    DO writes at least one row a minute (the guard's empty-is-not-zero check).
    const tx = await this.begin();
    const s = tx.s;
    const stalledMs = stalledFor(isLive(s.lease, now, cfg), s.lastAlarmGoodAt, s.playSince, now);
    s.stalls = nextStalls(s.stalls, stalledMs);
    // 3. Apply the lease, if given.
    let applied: MetronomeStatus["applied"] = null;
    if (raw !== null) {
      const v = validateLease(raw);
      if (!v.ok) {
        // Stores nothing from it; deletes its stored lease and alarm: idle.
        this.port.log("metronome-lease-invalid", { reason: v.reason, source: "renew" });
        s.lease = null;
        await this.flush(tx, true);
        await this.disarm();
        return { applied: "invalid", lease: "none", wrote: null, lastAlarmGoodAt: s.lastAlarmGoodAt, stalledMs,
                 stalls: s.stalls, leaseVerdictAt: null };
      }
      applied = decideLease(s.lease, v.lease, now);
      this.episode("superseded", applied === "superseded", String(v.lease.verdictAt), "metronome-lease-superseded",
                   { verdictAt: v.lease.verdictAt, currentVerdictAt: s.lease?.verdictAt ?? null });
      if (applied === "accepted") {
        const wasPlay = leaseKind(s.lease, now) === "play";
        s.lease = storedLease(v.lease, now);
        if (leaseKind(s.lease, now) === "play" && !wasPlay) s.playSince = now;
        // Stored before any alarm op: an alarm op that throws must not lose an accepted hold or block.
        await this.flush(tx);
      }
    }
    const cur = currentLease(s.lease, now);
    this.episode("expired", s.lease !== null && cur === null, String(s.lease?.verdictAt), "metronome-expired",
                 { verdictAt: s.lease?.verdictAt ?? null, source: "renew" });
    this.episode("hold", cur?.kind === "hold", "hold", "metronome-hold", { verdictAt: cur?.verdictAt ?? null });
    // 4. Write once now under an unexpired play lease: the live playlist, or the off-air notice.
    //    Never older than the last tick's boundary (an early tick has already built past now).
    let wrote: boolean | null = null;
    if (cur !== null && cur.kind === "play") {
      const r = await this.write(tx, cur, tickBoundary(cur, s.lastTarget, now), now, cfg, "renew");
      wrote = r === "put" ? true : r === "failed" ? false : null;
    }
    // 5. Arm only while live and none is pending; otherwise delete any pending alarm.
    if (cur !== null && cur.kind === "play" && isLive(s.lease, now, cfg)) {
      if ((await this.port.getAlarm()) === null) {
        const target = nextTarget(gridOf(cur.horizon), Math.max(now, s.lastTarget ?? Number.NEGATIVE_INFINITY));
        await this.port.setAlarm(target);
        s.lastTarget = target;
      }
    } else {
      await this.disarm();
    }
    await this.flush(tx, true);
    return { applied, lease: leaseKind(s.lease, now), wrote, lastAlarmGoodAt: s.lastAlarmGoodAt, stalledMs,
             stalls: s.stalls, leaseVerdictAt: currentLease(s.lease, now)?.verdictAt ?? null };
  }
}
