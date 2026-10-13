import { type Grid, type Horizon, gridOf, indexAt, isoAt, startMs } from "./grid";

/** fallback/<version>/index.json. */
export interface FallbackIndex {
  len: number;
  notice: string; // full key of the off-air notice segment
}

export interface PlaylistConfig {
  window: number; // k: segments listed
  grace: number; // segments the clock waits at horizon.last before falling back
  offairAfterMs: number;
  /** Segments listed past the one airing now (amendment A4, amended
   * 2026-10-12). A lookahead adds no runway by itself -- it moves the listed
   * end and a player's start point together -- but with holdBack equal to it,
   * players start at the wall clock with holdBack * d of listed runway against
   * a late cron fire. Every listed segment exists: the published lead is
   * ~24 h. The grace hold and the fallback switch apply to cur + lookahead.
   * Default 0. */
  lookahead?: number;
  /** Where players start, in segments before the listed end: emitted on every
   * live playlist as EXT-X-START:TIME-OFFSET and EXT-X-SERVER-CONTROL:HOLD-BACK
   * (iOS honours both at VERSION 3, measured 2026-10-12). Deployment rule:
   * holdBack = lookahead, which hugo's dead-clock check relies on (it dates the
   * playlist by its newest PROGRAM-DATE-TIME minus this offset). Default 0. */
  holdBack?: number;
}

export interface PlaylistInputs {
  nowMs: number;
  horizon: Horizon;
  fallback: FallbackIndex | null;
  offair: boolean; // state/offair.json {offair: true}
  offairSeqMs?: number; // the clock's scheduledTime + loopMs; default nowMs (see offairSequence)
}

export type Entry = { n: number; kind: "live" | "fallback" };

export function isOffair(inp: PlaylistInputs, cfg: PlaylistConfig): boolean {
  if (inp.offair) return true;
  const g = gridOf(inp.horizon);
  return inp.nowMs > startMs(g, inp.horizon.last + 1) + cfg.offairAfterMs;
}

/** The listed indices, ending at the target cur + lookahead. While
 * 0 < target - last <= grace the window holds at horizon.last; segments
 * outside [first, last] are absent and play the loop. The end never exceeds
 * cur + lookahead (offairSequence relies on it). */
export function windowEntries(cur: number, h: Horizon, cfg: PlaylistConfig): Entry[] {
  const target = cur + (cfg.lookahead ?? 0);
  const behind = target - h.last;
  const end = behind > 0 && behind <= cfg.grace ? h.last : target;
  const start = Math.max(0, end - cfg.window + 1);
  const out: Entry[] = [];
  for (let n = start; n <= end; n++) out.push({ n, kind: n >= h.first && n <= h.last ? "live" : "fallback" });
  return out;
}

const extinf = (dMs: number) => `#EXTINF:${(dMs / 1000).toFixed(3)},`;
const lines = (xs: string[]) => xs.join("\n") + "\n";

/** The off-air MEDIA-SEQUENCE (the notice's number), for a write at nowMs.
 *
 * Invariant: strictly greater than every live segment number any write at or
 * before nowMs -- this invocation's, an overlapping one's or an earlier one's
 * -- could have listed. A live write at t lists at most indexAt(t) + lookahead
 * (windowEntries never ends past its target), and indexAt is nondecreasing,
 * so every such number is at most indexAt(nowMs) + lookahead. Numbering from
 * max(seqMs, nowMs) and adding lookahead + 1 is therefore strictly above all
 * of them. The + 1 is load-bearing: a notice numbered EQUAL to a live segment
 * a player already holds is, to that player, the segment it already has
 * (RFC 8216: a media sequence number names one segment), so it skips the
 * notice and stops on ENDLIST without it.
 *
 * seqMs is the clock's scheduledTime + loopMs, so the number is constant
 * within an invocation (one PUT: identical bytes are skipped) while
 * nowMs <= seqMs; past it (an invocation running later than its own loop) it
 * follows nowMs, so it never decreases within an invocation either. */
export function offairSequence(g: Grid, nowMs: number, seqMs: number, lookahead: number): number {
  return Math.max(0, indexAt(g, Math.max(seqMs, nowMs))) + lookahead + 1;
}

/** The notice + ENDLIST, numbered `seq` (offairSequence). EXT-X-MEDIA-SEQUENCE
 * must never decrease across playlist reloads (RFC 8216). */
export function offairPlaylist(fb: FallbackIndex, g: Grid, seq: number): string {
  return lines([
    "#EXTM3U",
    "#EXT-X-VERSION:3",
    `#EXT-X-TARGETDURATION:${Math.ceil(g.dMs / 1000)}`,
    `#EXT-X-MEDIA-SEQUENCE:${seq}`,
    "#EXT-X-DISCONTINUITY",
    extinf(g.dMs),
    fb.notice,
    "#EXT-X-ENDLIST",
  ]);
}

/** Off-air with no usable fallback (ruling, 2026-10-10): a zero-segment
 * playlist, header + MEDIA-SEQUENCE + ENDLIST and no URI lines, so players stop
 * instead of stalling on a stale playlist. It lists nothing, so it can never
 * name a segment that does not exist. Same MEDIA-SEQUENCE rule as
 * offairPlaylist (offairSequence). */
export function endlistOnly(g: Grid, seq: number): string {
  return lines([
    "#EXTM3U",
    "#EXT-X-VERSION:3",
    `#EXT-X-TARGETDURATION:${Math.ceil(g.dMs / 1000)}`,
    `#EXT-X-MEDIA-SEQUENCE:${seq}`,
    "#EXT-X-ENDLIST",
  ]);
}

/** The fallback the playlist may list, or null when none is published:
 * horizon.fallback_version unset, its index.json missing/unreadable, or len < 1. */
export function usableFallback(inp: Pick<PlaylistInputs, "horizon" | "fallback">): FallbackIndex | null {
  return inp.fallback !== null && inp.horizon.fallback_version !== null && inp.fallback.len >= 1 ? inp.fallback : null;
}

/** The live playlist, or null when nothing can be listed safely (before the
 * epoch, or a fallback loop entry is needed and none is published). A null
 * means "write nothing": players stall on a stale playlist rather than fetch a
 * segment that does not exist. Off-air never returns null: without a usable
 * fallback it is the ENDLIST-only playlist (no notice). */
export function buildPlaylist(inp: PlaylistInputs, cfg: PlaylistConfig): string | null {
  const h = inp.horizon;
  const g = gridOf(h);
  const fb = usableFallback(inp);
  if (isOffair(inp, cfg)) {
    const seq = offairSequence(g, inp.nowMs, inp.offairSeqMs ?? inp.nowMs, cfg.lookahead ?? 0);
    return fb ? offairPlaylist(fb, g, seq) : endlistOnly(g, seq);
  }
  const cur = indexAt(g, inp.nowMs);
  if (cur < 0) return null;
  const entries = windowEntries(cur, h, cfg);
  if (entries.length === 0) return null;
  if (fb === null && entries.some((e) => e.kind === "fallback")) return null;
  const len = fb ? fb.len : 1;
  // A discontinuity before segment 0 of every loop iteration and at every switch.
  const tagged = entries.map(
    (e, i) => (e.kind === "fallback" && e.n % len === 0) || (i > 0 && entries[i - 1].kind !== e.kind),
  );
  // Choose the sequence so fallback segment N always carries discontinuity
  // number floor(N/len) + 1. The +1 (a deliberate deviation from the spec's
  // floor(N/len)) is what makes this hold at the start of an epoch: the first
  // fallback entry carries at most one tag, so the sequence is
  // floor(n/len) + 1 - tagsThrough >= 0 and never needs clamping. The old
  // clamp at 0 renumbered segments between reloads whenever n < len (RFC 8216
  // 6.2.2: the sequence must rise as tags leave the window, so every remaining
  // segment keeps its number). A pure-live window restarts at 0: a
  // live<->fallback transition may cost a listener one reload or glitch
  // (spec-accepted).
  let discSeq = 0;
  const fi = entries.findIndex((e) => e.kind === "fallback");
  if (fi >= 0) {
    const tagsThrough = tagged.slice(0, fi + 1).filter(Boolean).length;
    discSeq = Math.floor(entries[fi].n / len) + 1 - tagsThrough;
  }
  const targetS = Math.ceil(g.dMs / 1000);
  const out = [
    "#EXTM3U",
    "#EXT-X-VERSION:3",
    `#EXT-X-TARGETDURATION:${targetS}`,
    `#EXT-X-MEDIA-SEQUENCE:${entries[0].n}`,
    `#EXT-X-DISCONTINUITY-SEQUENCE:${discSeq}`,
  ];
  // Where players start: holdBack segments before the listed end, never past
  // the listed window (RFC 8216bis: |TIME-OFFSET| SHOULD NOT exceed the
  // playlist's duration), and only at >= 3 target durations (HOLD-BACK MUST be,
  // and a start offset SHOULD NOT lie within 3 target durations of the end).
  const holdBack = Math.min(cfg.holdBack ?? 0, entries.length - 1);
  if (holdBack > 0 && holdBack * g.dMs >= 3 * targetS * 1000) {
    const s = ((holdBack * g.dMs) / 1000).toFixed(3);
    out.push(`#EXT-X-START:TIME-OFFSET=-${s}`, `#EXT-X-SERVER-CONTROL:HOLD-BACK=${s}`);
  }
  entries.forEach((e, i) => {
    if (tagged[i]) out.push("#EXT-X-DISCONTINUITY");
    out.push(
      `#EXT-X-PROGRAM-DATE-TIME:${isoAt(g, e.n)}`,
      extinf(g.dMs),
      e.kind === "live" ? `seg/${h.epoch_id}/${e.n}.aac` : `fallback/${h.fallback_version}/${e.n % len}.aac`,
    );
  });
  return lines(out);
}
