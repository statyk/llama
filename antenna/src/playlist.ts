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
}

export interface PlaylistInputs {
  nowMs: number;
  horizon: Horizon;
  fallback: FallbackIndex | null;
  offair: boolean; // state/offair.json {offair: true}
  offairSeqMs?: number; // the off-air MEDIA-SEQUENCE is indexAt(offairSeqMs); default nowMs
}

export type Entry = { n: number; kind: "live" | "fallback" };

export function isOffair(inp: PlaylistInputs, cfg: PlaylistConfig): boolean {
  if (inp.offair) return true;
  const g = gridOf(inp.horizon);
  return inp.nowMs > startMs(g, inp.horizon.last + 1) + cfg.offairAfterMs;
}

/** The listed indices. While 0 < cur - last <= grace the window holds at
 * horizon.last; segments outside [first, last] are absent and play the loop. */
export function windowEntries(cur: number, h: Horizon, cfg: PlaylistConfig): Entry[] {
  const behind = cur - h.last;
  const end = behind > 0 && behind <= cfg.grace ? h.last : cur;
  const start = Math.max(0, end - cfg.window + 1);
  const out: Entry[] = [];
  for (let n = start; n <= end; n++) out.push({ n, kind: n >= h.first && n <= h.last ? "live" : "fallback" });
  return out;
}

const extinf = (dMs: number) => `#EXTINF:${(dMs / 1000).toFixed(3)},`;
const lines = (xs: string[]) => xs.join("\n") + "\n";

/** The notice + ENDLIST. EXT-X-MEDIA-SEQUENCE must never decrease across
 * playlist reloads (RFC 8216), so it is indexAt(seqMs): at or past every live
 * sequence listed for the same clock time, and constant within one invocation
 * when the clock passes scheduledTime + loopMs. */
export function offairPlaylist(fb: FallbackIndex, g: Grid, seqMs: number): string {
  return lines([
    "#EXTM3U",
    "#EXT-X-VERSION:3",
    `#EXT-X-TARGETDURATION:${Math.ceil(g.dMs / 1000)}`,
    `#EXT-X-MEDIA-SEQUENCE:${Math.max(0, indexAt(g, seqMs))}`,
    "#EXT-X-DISCONTINUITY",
    extinf(g.dMs),
    fb.notice,
    "#EXT-X-ENDLIST",
  ]);
}

/** The live playlist, or null when nothing can be listed safely (before the
 * epoch, or a fallback/notice is needed and none is published). A null means
 * "write nothing": players stall on a stale playlist rather than fetch a
 * segment that does not exist. */
export function buildPlaylist(inp: PlaylistInputs, cfg: PlaylistConfig): string | null {
  const h = inp.horizon;
  const g = gridOf(h);
  const fb = inp.fallback !== null && h.fallback_version !== null && inp.fallback.len >= 1 ? inp.fallback : null;
  if (isOffair(inp, cfg)) return fb ? offairPlaylist(fb, g, inp.offairSeqMs ?? inp.nowMs) : null;
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
  // number floor(N/len) (= floor(N/len) during pure fallback). A pure-live
  // window restarts at 0: a live<->fallback transition may cost a listener one
  // reload or glitch (spec-accepted).
  let discSeq = 0;
  const fi = entries.findIndex((e) => e.kind === "fallback");
  if (fi >= 0) {
    const tagsThrough = tagged.slice(0, fi + 1).filter(Boolean).length;
    discSeq = Math.max(0, Math.floor(entries[fi].n / len) - tagsThrough);
  }
  const out = [
    "#EXTM3U",
    "#EXT-X-VERSION:3",
    `#EXT-X-TARGETDURATION:${Math.ceil(g.dMs / 1000)}`,
    `#EXT-X-MEDIA-SEQUENCE:${entries[0].n}`,
    `#EXT-X-DISCONTINUITY-SEQUENCE:${discSeq}`,
  ];
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
