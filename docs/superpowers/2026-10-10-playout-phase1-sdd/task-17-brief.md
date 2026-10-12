### Task 17: Static player page and the asset deploy script

**Model hint:** sonnet

**Files:**
- Create: `antenna/public/index.html`, `antenna/public/player.js`, `antenna/public/nowplaying.js`, `antenna/public/style.css`, `antenna/public/offair.html`
- Create: `antenna/scripts/deploy-assets.mjs`
- Create: `antenna/test/nowplaying.test.ts`
- Modify: `antenna/package.json` (adds `hls.js` via npm)

**Interfaces:**
- Consumes: `live.m3u8` (Task 16), `timeline.json` shape from Task 10 (`shows[].{start,end,artist,date,venue,city,files[].{title,start}}`).
- Produces (`public/nowplaying.js`, ES module): `prefersNativeHls(nav, canPlayNative) -> boolean` (Apple WebKit = vendor starts with "Apple", and native HLS reported — covers Safari and every iOS browser; Chrome with native HLS still gets hls.js); `findNowPlaying(timeline, atMs) -> {show, file} | null`; `nowPlayingText(np, timelineLoaded) -> string`.
- Produces: R2 keys `index.html` (max-age 60), `offair.html`, `player.js`, `nowplaying.js`, `style.css`, `assets/hls.min.js` (max-age 3600), uploaded by `ANTENNA_BUCKET=<bucket> npm run deploy:assets`.

- [ ] **Step 1: Install hls.js and write the failing tests**

```bash
cd antenna && npm install hls.js@1 && cd ..
```

`antenna/test/nowplaying.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { findNowPlaying, nowPlayingText, prefersNativeHls } from "../public/nowplaying.js";

const TIMELINE = {
  shows: [
    {
      slug: "cracker-2005-11-01", start: "2026-10-10T12:00:00.000Z", end: "2026-10-10T13:40:00.000Z",
      artist: "Cracker", date: "2005-11-01", venue: "Knickerbockers", city: "Lincoln, NE USA",
      files: [
        { kind: "clip", title: "DJ intro (set 1)", start: "2026-10-10T12:00:00.023Z" },
        { kind: "track", title: "One Fine Day", start: "2026-10-10T12:03:00.000Z" },
        { kind: "track", title: "Guarded By Monkeys", start: "2026-10-10T12:10:39.000Z" },
      ],
    },
  ],
};
const t = (iso: string) => Date.parse(iso);

describe("prefersNativeHls", () => {
  it("uses native HLS on Apple WebKit only", () => {
    expect(prefersNativeHls({ vendor: "Apple Computer, Inc." }, true)).toBe(true); // Safari, any iOS browser
    expect(prefersNativeHls({ vendor: "Google Inc." }, true)).toBe(false); // Chrome's native HLS: use hls.js
    expect(prefersNativeHls({ vendor: "" }, false)).toBe(false); // Firefox
    expect(prefersNativeHls({ vendor: "Apple Computer, Inc." }, false)).toBe(false);
  });
});

describe("findNowPlaying", () => {
  it("finds the show and the latest file that has started", () => {
    const np = findNowPlaying(TIMELINE, t("2026-10-10T12:05:00Z"))!;
    expect(np.show.slug).toBe("cracker-2005-11-01");
    expect(np.file!.title).toBe("One Fine Day");
  });
  it("has a show but no file before the first file starts (encoder priming)", () => {
    expect(findNowPlaying(TIMELINE, t("2026-10-10T12:00:00.010Z"))!.file).toBeNull();
  });
  it("returns null in a gap, in the fallback loop, or without a timeline", () => {
    expect(findNowPlaying(TIMELINE, t("2026-10-10T14:00:00Z"))).toBeNull();
    expect(findNowPlaying(null, t("2026-10-10T12:05:00Z"))).toBeNull();
  });
});

describe("nowPlayingText", () => {
  it("formats show and file, or says the station will be back", () => {
    const np = findNowPlaying(TIMELINE, t("2026-10-10T12:05:00Z"));
    expect(nowPlayingText(np, true)).toBe("Cracker — 2005-11-01, Knickerbockers, Lincoln, NE USA · One Fine Day");
    expect(nowPlayingText(null, true)).toBe("We'll be back shortly.");
    expect(nowPlayingText(null, false)).toBe("Tuning in…");
  });
});
```

Run: `cd antenna && npx vitest run test/nowplaying.test.ts`
Expected: FAIL — cannot resolve `../public/nowplaying.js`.

- [ ] **Step 2: Implement the page**

`antenna/public/nowplaying.js`:

```js
// Pure helpers for the player (unit-tested). The player computes now-playing
// client-side: program-date-time of the playback position, looked up in
// timeline.json -- no request stream bills per listener.

/** Native HLS on Apple WebKit (Safari and every iOS browser -- all WebKit);
 * hls.js everywhere else, including Chrome whose native HLS is buggy. Detected
 * by vendor, not canPlayType alone (also true on Chrome). */
export function prefersNativeHls(nav, canPlayNative) {
  const vendor = typeof nav.vendor === "string" ? nav.vendor : "";
  return Boolean(canPlayNative) && vendor.startsWith("Apple");
}

export function findNowPlaying(timeline, atMs) {
  if (!timeline || !Array.isArray(timeline.shows)) return null;
  for (const show of timeline.shows) {
    if (atMs >= Date.parse(show.start) && atMs < Date.parse(show.end)) {
      let file = null;
      for (const f of show.files || []) {
        if (Date.parse(f.start) <= atMs) file = f;
        else break;
      }
      return { show, file };
    }
  }
  return null;
}

export function nowPlayingText(np, timelineLoaded) {
  if (!np) return timelineLoaded ? "We'll be back shortly." : "Tuning in…";
  const s = np.show;
  const where = [s.venue, s.city].filter(Boolean).join(", ");
  const head = [s.artist, [s.date, where].filter(Boolean).join(", ")].filter(Boolean).join(" — ");
  return np.file ? `${head} · ${np.file.title}` : head;
}
```

`antenna/public/player.js`:

```js
import { findNowPlaying, nowPlayingText, prefersNativeHls } from "./nowplaying.js";

const STREAM = "live.m3u8";
const TIMELINE = "timeline.json";
const TIMELINE_REFRESH_MS = 3 * 60 * 1000;

const audio = document.getElementById("audio");
const playButton = document.getElementById("play");
const nowPlaying = document.getElementById("now-playing");
const notice = document.getElementById("notice");
const noticeText = document.getElementById("notice-text");
const retryButton = document.getElementById("retry");
document.getElementById("stream-url").textContent = new URL(STREAM, location.href).href;

let hls = null;
let playing = false;
let timeline = null;
let timelineFetchedAt = 0;

const useNative = () => prefersNativeHls(navigator, audio.canPlayType("application/vnd.apple.mpegurl") !== "");

function showNotice(text) {
  noticeText.textContent = text;
  notice.hidden = false;
}

function stop() {
  playing = false;
  if (hls) {
    hls.destroy();
    hls = null;
  }
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  playButton.textContent = "Play";
}

// Off-air (ENDLIST) or blocked (403): stop, show the notice, never auto-reconnect.
function offAir(text) {
  stop();
  showNotice(text);
  nowPlaying.textContent = "";
}

// Radio semantics: every start joins the live edge (pause = stop).
function start() {
  stop();
  notice.hidden = true;
  playing = true;
  playButton.textContent = "Stop";
  if (useNative()) {
    audio.src = STREAM;
  } else if (window.Hls && window.Hls.isSupported()) {
    hls = new window.Hls({ liveSyncDurationCount: 3 });
    hls.on(window.Hls.Events.LEVEL_LOADED, (_event, data) => {
      if (data.details && data.details.live === false) offAir("The station is off the air.");
    });
    hls.on(window.Hls.Events.ERROR, (_event, data) => {
      const code = data.response && data.response.code;
      if (code === 403) offAir("The station is off the air.");
      else if (data.fatal) offAir("The stream is unavailable right now.");
    });
    hls.loadSource(STREAM);
    hls.attachMedia(audio);
  } else {
    offAir("This browser cannot play the stream here; open the stream URL in VLC.");
    return;
  }
  audio.play().catch(() => offAir("Playback was blocked; press Try again."));
  refreshTimeline(true);
}

audio.addEventListener("ended", () => offAir("The station is off the air."));
audio.addEventListener("error", () => {
  if (playing) offAir("The stream is unavailable right now.");
});
playButton.addEventListener("click", () => (playing ? stop() : start()));
retryButton.addEventListener("click", start);

function playbackDateMs() {
  if (hls && hls.playingDate) return hls.playingDate.getTime();
  if (typeof audio.getStartDate === "function") {
    const startMs = audio.getStartDate().getTime();
    if (Number.isFinite(startMs)) return startMs + audio.currentTime * 1000;
  }
  return null;
}

// Fetched only while playing, at most every few minutes, never while hidden.
async function refreshTimeline(force) {
  if (!playing || document.hidden) return;
  if (!force && Date.now() - timelineFetchedAt < TIMELINE_REFRESH_MS) return;
  timelineFetchedAt = Date.now();
  try {
    const res = await fetch(TIMELINE);
    if (res.ok) timeline = await res.json();
  } catch {
    // keep the last timeline
  }
}

setInterval(() => {
  if (!playing) return;
  refreshTimeline(false);
  const at = playbackDateMs();
  if (at !== null) nowPlaying.textContent = nowPlayingText(findNowPlaying(timeline, at), timeline !== null);
}, 1000);
```

`antenna/public/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>llama radio</title>
<meta property="og:type" content="website">
<meta property="og:title" content="llama radio">
<meta property="og:description" content="Live concert recordings from the Live Music Archive, around the clock.">
<link rel="stylesheet" href="style.css">
<script src="assets/hls.min.js" defer></script>
<script type="module" src="player.js"></script>
</head>
<body>
<main class="player">
  <h1>llama radio</h1>
  <p id="now-playing" class="now-playing">Press play to tune in.</p>
  <p><button id="play" type="button">Play</button></p>
  <audio id="audio" preload="none"></audio>
  <div id="notice" class="notice" hidden>
    <p id="notice-text">The station is off the air.</p>
    <p><button id="retry" type="button">Try again</button></p>
  </div>
  <p class="stream">Stream URL (VLC, apps): <code id="stream-url"></code></p>
  <p class="credit">Recordings from the <a href="https://archive.org/details/etree">Live Music Archive</a>.
     Non-commercial; no ads.</p>
</main>
</body>
</html>
```

`antenna/public/offair.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Off the air · llama radio</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<main class="player">
  <h1>llama radio</h1>
  <p class="notice">The station is off the air.</p>
  <p class="credit">Recordings from the <a href="https://archive.org/details/etree">Live Music Archive</a>.</p>
</main>
</body>
</html>
```

`antenna/public/style.css`:

```css
body { font: 17px/1.5 system-ui, sans-serif; margin: 0; background: #faf8f4; color: #222; }
main { max-width: 40rem; margin: 3rem auto; padding: 0 1.25rem; }
h1 { font-size: 1.8rem; margin-bottom: .5rem; }
button { font-size: 1.1rem; padding: .5rem 1.4rem; border-radius: .4rem; border: 1px solid #444; background: #fff; cursor: pointer; }
.now-playing { min-height: 1.5em; font-weight: 600; }
.notice { background: #fff3cd; border: 1px solid #e0c36b; padding: .25rem 1rem; border-radius: .4rem; }
.stream code { word-break: break-all; }
.credit, .lineage, .set { color: #666; font-size: .9rem; }
```

`antenna/scripts/deploy-assets.mjs`:

```js
#!/usr/bin/env node
// Upload antenna's static assets to the station's R2 bucket (spec "R2 object
// contract": index.html, offair.html and the app assets incl. hls.js are written
// by the antenna deploy script; index.html is static in phase 1).
// Usage: ANTENNA_BUCKET=<bucket> node scripts/deploy-assets.mjs [--dry-run]
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const bucket = process.env.ANTENNA_BUCKET;
const dryRun = process.argv.includes("--dry-run");
if (!bucket) {
  console.error("set ANTENNA_BUCKET to the station's R2 bucket name");
  process.exit(2);
}

const HTML = "text/html; charset=utf-8";
const JS = "text/javascript; charset=utf-8";
const CSS = "text/css; charset=utf-8";
const HOUR = "public, max-age=3600";
const ASSETS = [
  ["index.html", "public/index.html", HTML, "public, max-age=60"],
  ["offair.html", "public/offair.html", HTML, HOUR],
  ["player.js", "public/player.js", JS, HOUR],
  ["nowplaying.js", "public/nowplaying.js", JS, HOUR],
  ["style.css", "public/style.css", CSS, HOUR],
  ["assets/hls.min.js", "node_modules/hls.js/dist/hls.min.js", JS, HOUR],
];

for (const [key, file, type, cache] of ASSETS) {
  const path = join(root, file);
  if (!existsSync(path)) {
    console.error(`missing ${file} (run npm install?)`);
    process.exit(1);
  }
  const args = ["wrangler", "r2", "object", "put", `${bucket}/${key}`, "--file", path,
                "--content-type", type, "--cache-control", cache, "--remote"];
  if (dryRun) {
    console.log(["npx", ...args].join(" "));
    continue;
  }
  const r = spawnSync("npx", args, { cwd: root, stdio: "inherit" });
  if (r.status !== 0) process.exit(r.status ?? 1);
}
```

- [ ] **Step 3: Run the tests, the type check and a dry run**

Run: `cd antenna && npx vitest run && npx tsc --noEmit`
Expected: PASS.

Run: `cd antenna && ANTENNA_BUCKET=llama-radio node scripts/deploy-assets.mjs --dry-run`
Expected: six `npx wrangler r2 object put llama-radio/<key> … --remote` lines, one per asset.

- [ ] **Step 4: Manual smoke check (local)**

Serve the spike output from Task 2 alongside the page to check the wiring in a browser: copy `antenna/public/*` and `antenna/node_modules/hls.js/dist/hls.min.js` (as `assets/hls.min.js`) into the spike directory, add `live.m3u8` from `python -m transmitter.spike serve`, open `http://localhost:8000/index.html`, press Play: audio plays in Chrome (hls.js) and Safari (native); the stream URL shows; playback stops and the notice appears when the live playlist reaches ENDLIST. (The phase-4 Playwright smoke test against a local R2 emulation replaces this.)

- [ ] **Step 5: Commit**

```bash
git add antenna
git commit -m "feat(antenna): minimal static player (native HLS on Apple, hls.js elsewhere) and asset deploy script"
```

---

