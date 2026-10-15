/** state/horizon.json as transmitter writes it (spec "R2 object contract"). */
export interface Horizon {
  epoch_id: string;
  epoch: string; // ISO-8601 UTC
  d: number; // seconds; 10.24
  first: number;
  last: number; // highest N with every segment first..last present; last < first = empty
  published_at: string;
  container: string;
  fallback_version: string | null;
}

/** The grid constant transmitter always writes: 441 * 1024 / 44100 s. A
 * horizon with any other d is refused (the clock's spend bounds) and is never
 * part of a metronome lease. */
export const GRID_D = 10.24;

export interface Grid {
  epochMs: number;
  dMs: number;
}

export function gridOf(h: Horizon): Grid {
  const epochMs = Date.parse(h.epoch);
  if (!Number.isFinite(epochMs)) throw new Error(`horizon.epoch is not a timestamp: ${h.epoch}`);
  const dMs = Math.round(h.d * 1000);
  if (!(dMs > 0)) throw new Error(`horizon.d is not a positive duration: ${h.d}`);
  return { epochMs, dMs };
}

/** Segment airing at nowMs (floor; negative before the epoch). */
export function indexAt(g: Grid, nowMs: number): number {
  return Math.floor((nowMs - g.epochMs) / g.dMs);
}

export function startMs(g: Grid, n: number): number {
  return g.epochMs + n * g.dMs;
}

export function isoAt(g: Grid, n: number): string {
  return new Date(startMs(g, n)).toISOString();
}
