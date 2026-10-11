import { describe, expect, it } from "vitest";
import type { Horizon } from "../src/grid";
import { buildPlaylist, type FallbackIndex, type PlaylistConfig } from "../src/playlist";

const E = Date.parse("2026-10-10T12:00:00.000Z");
const D = 10_240;
const CFG: PlaylistConfig = { window: 6, grace: 3, offairAfterMs: 24 * 3600 * 1000 };
const FB: FallbackIndex = { len: 7, notice: "fallback/v1/notice.aac" };

function horizon(first: number, last: number, extra: Partial<Horizon> = {}): Horizon {
  const iso = new Date(E).toISOString();
  return { epoch_id: "e1", epoch: iso, d: 10.24, first, last, published_at: iso,
           container: "adts", fallback_version: "v1", ...extra };
}

const at = (n: number) => E + n * D + 1; // just after segment n starts

function entries(pl: string): { uri: string; disc: number; pdt: string }[] {
  const lines = pl.trim().split("\n");
  const seqLine = lines.find((l) => l.startsWith("#EXT-X-DISCONTINUITY-SEQUENCE:"));
  let disc = seqLine ? Number(seqLine.split(":")[1]) : 0;
  let pdt = "";
  const out: { uri: string; disc: number; pdt: string }[] = [];
  for (const l of lines) {
    if (l === "#EXT-X-DISCONTINUITY") disc++;
    else if (l.startsWith("#EXT-X-PROGRAM-DATE-TIME:")) pdt = l.slice("#EXT-X-PROGRAM-DATE-TIME:".length);
    else if (!l.startsWith("#")) out.push({ uri: l, disc, pdt });
  }
  return out;
}

const mediaSequence = (pl: string) => Number(/#EXT-X-MEDIA-SEQUENCE:(\d+)/.exec(pl)![1]);
const live = (ns: number[]) => ns.map((n) => `seg/e1/${n}.aac`);
const loop = (ns: number[]) => ns.map((n) => `fallback/v1/${n % 7}.aac`);

describe("buildPlaylist", () => {
  it("lists the last six live segments ending at the current index", () => {
    const pl = buildPlaylist({ nowMs: at(1000), horizon: horizon(0, 5000), fallback: FB, offair: false }, CFG)!;
    const es = entries(pl);
    expect(es.map((e) => e.uri)).toEqual(live([995, 996, 997, 998, 999, 1000]));
    expect(mediaSequence(pl)).toBe(995);
    expect(es[0].pdt).toBe(new Date(E + 995 * D).toISOString());
    expect(pl).toContain("#EXT-X-TARGETDURATION:11\n");
    expect(pl).toContain("#EXTINF:10.240,\n");
    expect(pl).not.toContain("#EXT-X-DISCONTINUITY\n");
    expect(pl).not.toContain("ENDLIST");
  });

  it("holds at horizon.last for up to three segments (a publish retry is not an outage)", () => {
    for (const behind of [1, 2, 3]) {
      const pl = buildPlaylist({ nowMs: at(100 + behind), horizon: horizon(0, 100), fallback: FB, offair: false }, CFG)!;
      expect(entries(pl).at(-1)!.uri).toBe("seg/e1/100.aac");
      expect(mediaSequence(pl)).toBe(95);
    }
  });

  it("switches to the fallback loop beyond grace, with a discontinuity at the switch", () => {
    const pl = buildPlaylist({ nowMs: at(104), horizon: horizon(0, 100), fallback: FB, offair: false }, CFG)!;
    const es = entries(pl);
    expect(es.map((e) => e.uri)).toEqual([...live([99, 100]), ...loop([101, 102, 103, 104])]);
    const lines = pl.split("\n");
    expect(lines[lines.indexOf("fallback/v1/3.aac") - 3]).toBe("#EXT-X-DISCONTINUITY");
    expect(es[2].disc).toBe(Math.floor(101 / 7) + 1);
  });

  it("treats N < horizon.first as absent", () => {
    const pl = buildPlaylist({ nowMs: at(102), horizon: horizon(100, 200), fallback: FB, offair: false }, CFG)!;
    expect(entries(pl).map((e) => e.uri)).toEqual([...loop([97, 98, 99]), ...live([100, 101, 102])]);
    // A discontinuity at the fallback->live switch too: fallback segment k carries timestamp k*d.
    const lines = pl.split("\n");
    expect(lines[lines.indexOf("seg/e1/100.aac") - 3]).toBe("#EXT-X-DISCONTINUITY");
  });

  it("an empty horizon (first = last + 1) lists fallback", () => {
    for (const cur of [150, 152, 160]) {
      const pl = buildPlaylist({ nowMs: at(cur), horizon: horizon(151, 150), fallback: FB, offair: false }, CFG)!;
      const es = entries(pl);
      expect(es).toHaveLength(6);
      expect(es.every((e) => e.uri.startsWith("fallback/v1/"))).toBe(true);
    }
  });

  it("numbers every fallback segment floor(N/len) + 1, consistently across successive playlists", () => {
    const seen = new Map<number, number>();
    for (let cur = 1000; cur <= 1016; cur++) {
      const pl = buildPlaylist({ nowMs: at(cur), horizon: horizon(0, 10), fallback: FB, offair: false }, CFG)!;
      const ms = mediaSequence(pl);
      const es = entries(pl);
      es.forEach((e, i) => {
        const n = ms + i;
        expect(e.uri).toBe(`fallback/v1/${n % 7}.aac`);
        expect(e.disc).toBe(Math.floor(n / 7) + 1);
        if (seen.has(n)) expect(seen.get(n)).toBe(e.disc);
        seen.set(n, e.disc);
      });
      const tags = pl.split("\n").filter((l) => l === "#EXT-X-DISCONTINUITY").length;
      expect(tags).toBe(es.filter((_, i) => (ms + i) % 7 === 0).length);
    }
  });

  it("never renumbers a segment's discontinuity across reloads early in an epoch (RFC 8216 6.2.2)", () => {
    // Pure fallback from the epoch (empty horizon), and a live->fallback
    // dropout inside the first len segments: the floor(N/len) - tags clamp
    // used to renumber both.
    const cases: { name: string; h: Horizon; fb: FallbackIndex }[] = [
      { name: "empty, len 7", h: horizon(0, -1), fb: FB },
      { name: "empty, len 3", h: horizon(0, -1), fb: { len: 3, notice: "fallback/v1/notice.aac" } },
      { name: "dropout at 20, len 50", h: horizon(0, 19), fb: { len: 50, notice: "fallback/v1/notice.aac" } },
      { name: "dropout at 2, len 3", h: horizon(0, 1), fb: { len: 3, notice: "fallback/v1/notice.aac" } },
    ];
    for (const { name, h, fb } of cases) {
      const seen = new Map<string, number>();
      for (let cur = 0; cur <= 3 * fb.len + 10; cur++) {
        const pl = buildPlaylist({ nowMs: at(cur), horizon: h, fallback: fb, offair: false }, CFG);
        if (pl === null) continue; // the grace hold over an empty horizon at the epoch: nothing written
        for (const e of entries(pl)) {
          if (seen.has(e.uri + e.pdt)) expect(e.disc, `${name}: ${e.uri} @ cur=${cur}`).toBe(seen.get(e.uri + e.pdt));
          seen.set(e.uri + e.pdt, e.disc);
        }
      }
    }
  });

  it("goes off-air with the notice and ENDLIST when state/offair.json says so", () => {
    const pl = buildPlaylist({ nowMs: at(1000), horizon: horizon(0, 5000), fallback: FB, offair: true }, CFG)!;
    expect(entries(pl).map((e) => e.uri)).toEqual(["fallback/v1/notice.aac"]);
    expect(pl.trimEnd().endsWith("#EXT-X-ENDLIST")).toBe(true);
    expect(mediaSequence(pl)).toBe(1000);
  });

  it("numbers the off-air playlist from offairSeqMs: constant within an invocation, never below live", () => {
    const seqMs = at(1000) + 75_000; // what the clock passes: scheduledTime + loopMs
    const off = (nowMs: number) =>
      buildPlaylist({ nowMs, horizon: horizon(0, 5000), fallback: FB, offair: true, offairSeqMs: seqMs }, CFG)!;
    expect(off(at(1001))).toBe(off(at(1000))); // identical bytes: the clock's skip makes it one PUT
    expect(mediaSequence(off(at(1000)))).toBe(1007);
    for (const cur of [10, 1000, 4999]) {
      const nowMs = at(cur);
      const livePl = buildPlaylist({ nowMs, horizon: horizon(0, 5000), fallback: FB, offair: false }, CFG)!;
      for (const offairSeqMs of [undefined, nowMs + 75_000]) {
        const offPl = buildPlaylist({ nowMs, horizon: horizon(0, 5000), fallback: FB, offair: true, offairSeqMs }, CFG)!;
        expect(mediaSequence(offPl)).toBeGreaterThanOrEqual(mediaSequence(livePl));
      }
    }
  });

  it("goes off-air offair_after past the end of the published horizon", () => {
    const end = E + 101 * D;
    const inputs = { horizon: horizon(0, 100), fallback: FB, offair: false };
    expect(buildPlaylist({ ...inputs, nowMs: end + CFG.offairAfterMs }, CFG)).not.toContain("ENDLIST");
    expect(buildPlaylist({ ...inputs, nowMs: end + CFG.offairAfterMs + 1 }, CFG)).toContain("#EXT-X-ENDLIST");
  });

  it("returns null rather than list a segment that does not exist", () => {
    expect(buildPlaylist({ nowMs: at(104), horizon: horizon(0, 100), fallback: null, offair: false }, CFG)).toBeNull();
    expect(buildPlaylist({ nowMs: at(104), horizon: horizon(0, 100, { fallback_version: null }), fallback: FB, offair: false }, CFG)).toBeNull();
    expect(buildPlaylist({ nowMs: at(50), horizon: horizon(0, 100), fallback: null, offair: false }, CFG)).not.toBeNull();
  });

  it("goes off-air with an ENDLIST-only playlist (no notice, no URI lines) when no fallback is usable", () => {
    const cases = [
      { horizon: horizon(0, 5000), fallback: null, offair: true }, // index.json missing
      { horizon: horizon(0, 5000, { fallback_version: null }), fallback: FB, offair: true }, // never recorded
      { horizon: horizon(0, 5000), fallback: { ...FB, len: 0 }, offair: true }, // empty loop
    ];
    for (const inp of cases) {
      const pl = buildPlaylist({ ...inp, nowMs: at(1000) }, CFG)!;
      expect(pl).not.toBeNull();
      expect(entries(pl)).toEqual([]);
      expect(pl.split("\n").filter((l) => l !== "" && !l.startsWith("#"))).toEqual([]);
      expect(pl).not.toContain("#EXT-X-DISCONTINUITY");
      expect(pl.trimEnd().endsWith("#EXT-X-ENDLIST")).toBe(true);
      expect(mediaSequence(pl)).toBe(1000);
    }
    // Same MEDIA-SEQUENCE rule as the notice playlist: constant within an
    // invocation (offairSeqMs), never below the live sequence.
    const seqMs = at(1000) + 75_000;
    const a = buildPlaylist({ ...cases[0], nowMs: at(1000), offairSeqMs: seqMs }, CFG)!;
    const b = buildPlaylist({ ...cases[0], nowMs: at(1005), offairSeqMs: seqMs }, CFG)!;
    expect(a).toBe(b);
    const livePl = buildPlaylist({ ...cases[0], fallback: FB, offair: false, nowMs: at(1000) }, CFG)!;
    expect(mediaSequence(a)).toBeGreaterThanOrEqual(mediaSequence(livePl));
    // The staleness rule takes the same branch.
    const end = E + 101 * D;
    const stale = buildPlaylist({ horizon: horizon(0, 100), fallback: null, offair: false,
                                  nowMs: end + CFG.offairAfterMs + 1 }, CFG)!;
    expect(entries(stale)).toEqual([]);
    expect(stale.trimEnd().endsWith("#EXT-X-ENDLIST")).toBe(true);
  });

  it("returns null before the epoch", () => {
    expect(buildPlaylist({ nowMs: E - 1, horizon: horizon(0, 10), fallback: FB, offair: false }, CFG)).toBeNull();
  });

  it("namespaces live keys by epoch", () => {
    const pl = buildPlaylist({ nowMs: at(10), horizon: horizon(0, 100, { epoch_id: "e2" }), fallback: FB, offair: false }, CFG)!;
    expect(pl).toContain("seg/e2/10.aac");
    expect(mediaSequence(pl)).toBe(5);
  });
});
