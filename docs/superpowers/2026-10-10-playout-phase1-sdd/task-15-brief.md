### Task 15: antenna scaffold and the playlist builder

**Model hint:** opus

**Files:**
- Create: `antenna/package.json` (+ `package-lock.json` from npm), `antenna/tsconfig.json`, `antenna/wrangler.jsonc`, `antenna/vitest.config.ts`, `antenna/worker-configuration.d.ts` (generated)
- Create: `antenna/src/grid.ts`, `antenna/src/playlist.ts`, `antenna/src/index.ts` (placeholder; Task 16 fills it)
- Create: `antenna/test/playlist.test.ts`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: the `state/horizon.json` and `fallback/<v>/index.json` documents transmitter writes (Tasks 11, 13): `{epoch_id, epoch, d, first, last, published_at, container, fallback_version}` and `{len, notice, d}`.
- Produces (`src/grid.ts`): `interface Horizon`; `interface Grid { epochMs; dMs }`; `gridOf(h) -> Grid`; `indexAt(g, nowMs)`; `startMs(g, n)`; `isoAt(g, n)`.
- Produces (`src/playlist.ts`): `interface FallbackIndex { len; notice }`; `interface PlaylistConfig { window; grace; offairAfterMs }`; `interface PlaylistInputs { nowMs; horizon; fallback; offair; offairSeqMs? }`; `type Entry`; `isOffair(inputs, cfg)`; `windowEntries(cur, horizon, cfg)`; `offairPlaylist(fallback, g, seqMs)` (`EXT-X-MEDIA-SEQUENCE = indexAt(g, seqMs)`; the clock passes `scheduledTime + loopMs`, so it is constant within an invocation and never decreases); `buildPlaylist(inputs, cfg) -> string | null` (null = nothing safe to list; the caller writes nothing).

- [ ] **Step 1: Scaffold the project**

```bash
mkdir -p antenna/src antenna/test && cd antenna
cat > package.json <<'JSON'
{
  "name": "antenna",
  "private": true,
  "type": "module",
  "engines": { "node": ">=22" },
  "scripts": {
    "test": "vitest run",
    "typecheck": "tsc --noEmit",
    "types": "wrangler types",
    "deploy": "wrangler deploy",
    "deploy:assets": "node scripts/deploy-assets.mjs"
  }
}
JSON
npm install --save-dev wrangler@4 vitest@5 @cloudflare/vitest-plugin@1 typescript@5
```

(`@cloudflare/vitest-plugin` is the current name of `@cloudflare/vitest-pool-workers`, which npm now marks deprecated; it supports vitest `^4.1 || ^5`.)

`antenna/wrangler.jsonc`:

```jsonc
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "antenna",
  "main": "src/index.ts",
  "compatibility_date": "2026-10-01",
  // Cron-only: no routes, no fetch handler, and no public URL. A routeless
  // Worker otherwise gets a public, billed *.workers.dev URL that the zone's
  // WAF kill switch cannot reach (spec "Architecture").
  "workers_dev": false,
  "preview_urls": false,
  "triggers": { "crons": ["* * * * *"] },
  // The bucket name must match transmitter's [publish] bucket.
  "r2_buckets": [{ "binding": "BUCKET", "bucket_name": "llama-radio" }],
  "vars": {
    "PLAYLIST_WINDOW": "6",
    "GRACE_SEGMENTS": "3",
    "OFFAIR_AFTER_SECONDS": "86400",
    "LOOP_SECONDS": "75",
    "LIVE_MAX_AGE": "5"
  },
  // One log line per invocation (~1,440/day) stays inside the free allowance.
  "observability": { "enabled": true }
}
```

`antenna/vitest.config.ts`:

```ts
import { cloudflareTest } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [cloudflareTest({ wrangler: { configPath: "./wrangler.jsonc" } })],
});
```

(If the installed plugin's export differs, `node_modules/@cloudflare/vitest-plugin/dist/pool/index.d.mts` declares it; version 1.4.0 exports `cloudflareTest(options) => Vite.Plugin` with `options.wrangler.configPath`.)

`antenna/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "es2022",
    "module": "es2022",
    "moduleResolution": "bundler",
    "lib": ["es2022"],
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "allowJs": true,
    "checkJs": false,
    "types": ["@cloudflare/vitest-plugin/types"]
  },
  "include": ["src", "test", "public", "worker-configuration.d.ts"]
}
```

`antenna/src/index.ts` (placeholder so wrangler and the test pool have a `main`):

```ts
export default {
  async scheduled(): Promise<void> {},
} satisfies ExportedHandler<Env>;
```

```bash
npx wrangler types            # writes worker-configuration.d.ts (Env with BUCKET + vars)
cd ..
```

Append to `.gitignore`:

```
antenna/node_modules/
antenna/.wrangler/
```

- [ ] **Step 2: Write the failing tests**

`antenna/test/playlist.test.ts`:

```ts
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
    expect(es[2].disc).toBe(Math.floor(101 / 7));
  });

  it("treats N < horizon.first as absent", () => {
    const pl = buildPlaylist({ nowMs: at(102), horizon: horizon(100, 200), fallback: FB, offair: false }, CFG)!;
    expect(entries(pl).map((e) => e.uri)).toEqual([...loop([97, 98, 99]), ...live([100, 101, 102])]);
  });

  it("an empty horizon (first = last + 1) lists fallback", () => {
    for (const cur of [150, 152, 160]) {
      const pl = buildPlaylist({ nowMs: at(cur), horizon: horizon(151, 150), fallback: FB, offair: false }, CFG)!;
      const es = entries(pl);
      expect(es).toHaveLength(6);
      expect(es.every((e) => e.uri.startsWith("fallback/v1/"))).toBe(true);
    }
  });

  it("numbers every fallback segment floor(N/len), consistently across successive playlists", () => {
    const seen = new Map<number, number>();
    for (let cur = 1000; cur <= 1016; cur++) {
      const pl = buildPlaylist({ nowMs: at(cur), horizon: horizon(0, 10), fallback: FB, offair: false }, CFG)!;
      const ms = mediaSequence(pl);
      const es = entries(pl);
      es.forEach((e, i) => {
        const n = ms + i;
        expect(e.uri).toBe(`fallback/v1/${n % 7}.aac`);
        expect(e.disc).toBe(Math.floor(n / 7));
        if (seen.has(n)) expect(seen.get(n)).toBe(e.disc);
        seen.set(n, e.disc);
      });
      const tags = pl.split("\n").filter((l) => l === "#EXT-X-DISCONTINUITY").length;
      expect(tags).toBe(es.filter((_, i) => (ms + i) % 7 === 0).length);
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
    expect(buildPlaylist({ nowMs: at(1000), horizon: horizon(0, 5000), fallback: null, offair: true }, CFG)).toBeNull();
    expect(buildPlaylist({ nowMs: at(50), horizon: horizon(0, 100), fallback: null, offair: false }, CFG)).not.toBeNull();
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
```

- [ ] **Step 3: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/playlist.test.ts`
Expected: FAIL — cannot resolve `../src/playlist`.

- [ ] **Step 4: Implement `grid.ts` and `playlist.ts`**

`antenna/src/grid.ts`:

```ts
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
```

`antenna/src/playlist.ts`:

```ts
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
```

- [ ] **Step 5: Run the tests and the type check**

Run: `cd antenna && npx vitest run && npx tsc --noEmit`
Expected: PASS, no type errors.

- [ ] **Step 6: Commit**

```bash
git add .gitignore antenna
git commit -m "feat(antenna): Worker scaffold and the wall-clock playlist builder"
```

---

