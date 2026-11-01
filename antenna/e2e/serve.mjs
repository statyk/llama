// The smoke tests' site: public/ as static files, plus per-test timeline.json,
// notes/ and a live playlist that loops the fixture segments on the wall clock.
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, sep } from "node:path";
import { fileURLToPath } from "node:url";

const antenna = join(dirname(fileURLToPath(import.meta.url)), "..");
const PUBLIC = join(antenna, "public");
const HLS_JS = join(antenna, "node_modules/hls.js/dist/hls.min.js");

export const SEG_DIR = join(antenna, "e2e/fixtures/seg");
export const SEG_RATE = 48_000;
export const SEG_FRAMES = 96; // exactly 2.048 s at 48 kHz
export const SEG_MS = (SEG_FRAMES * 1024 * 1000) / SEG_RATE;
export const SEG_COUNT = 20;
const WINDOW = 6;

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".woff2": "font/woff2",
  ".png": "image/png",
  ".webmanifest": "application/manifest+json",
  ".txt": "text/plain; charset=utf-8",
  ".aac": "audio/aac",
};

const MODES = new Set(["live", "404", "403", "endlist"]);

function playlist(nowMs, ended) {
  const last = Math.floor(nowMs / SEG_MS);
  const first = last - WINDOW + 1;
  const lines = ["#EXTM3U", "#EXT-X-VERSION:3", `#EXT-X-TARGETDURATION:${Math.ceil(SEG_MS / 1000)}`,
                 `#EXT-X-MEDIA-SEQUENCE:${first}`];
  lines.push(`#EXT-X-PROGRAM-DATE-TIME:${new Date(first * SEG_MS).toISOString()}`);
  for (let n = first; n <= last; n++) lines.push(`#EXTINF:${(SEG_MS / 1000).toFixed(3)},`, `/seg/${n % SEG_COUNT}.aac`);
  if (ended) lines.push("#EXT-X-ENDLIST");
  return `${lines.join("\n")}\n`;
}

/** The file under `root` for a URL path, or null. Never leaves `root`. */
function fileUnder(root, urlPath) {
  const path = join(root, urlPath);
  if (path !== root && !path.startsWith(root + sep)) return null;
  return existsSync(path) && statSync(path).isFile() ? path : null;
}

function staticFile(pathname) {
  if (pathname === "/") return fileUnder(PUBLIC, "index.html");
  if (pathname === "/assets/hls.min.js") return HLS_JS;
  if (pathname.startsWith("/seg/")) return fileUnder(SEG_DIR, pathname.slice("/seg/".length));
  return fileUnder(PUBLIC, pathname);
}

/**
 * startServer({ timeline, notes }) -> { url, setLive(mode), requests, close() }.
 * `timeline` is the /timeline.json body (absent: 404). `notes` maps a slug to its
 * /notes/<slug>.json body (absent: 404). `setLive` picks what /live.m3u8 answers:
 * "live", "404", "403" or "endlist". `requests` lists every request's path and
 * query, in arrival order, and is appended to in place.
 */
export async function startServer({ timeline, notes = {} } = {}) {
  const requests = [];
  let mode = "live";

  const server = createServer((req, res) => {
    requests.push(req.url);
    const send = (status, type, body) => {
      res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
      res.end(body);
    };
    const json = (value) => (value === undefined ? send(404, TYPES[".txt"], "not found")
                                                 : send(200, TYPES[".json"], JSON.stringify(value)));
    let pathname;
    try {
      pathname = decodeURIComponent(new URL(req.url, "http://localhost").pathname);
    } catch {
      return send(400, TYPES[".txt"], "bad path");
    }
    if (pathname === "/timeline.json") return json(timeline);
    if (pathname.startsWith("/notes/") && pathname.endsWith(".json")) {
      const slug = pathname.slice("/notes/".length, -".json".length);
      return json(Object.hasOwn(notes, slug) ? notes[slug] : undefined);
    }
    if (pathname === "/live.m3u8") {
      if (mode === "404" || mode === "403") return send(Number(mode), TYPES[".txt"], mode);
      return send(200, "application/vnd.apple.mpegurl", playlist(Date.now(), mode === "endlist"));
    }
    const file = staticFile(pathname);
    if (!file) return send(404, TYPES[".txt"], "not found");
    res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream", "cache-control": "no-store" });
    createReadStream(file).pipe(res);
  });

  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });

  return {
    url: `http://127.0.0.1:${server.address().port}`,
    requests,
    setLive(next) {
      if (!MODES.has(next)) throw new Error(`unknown live mode: ${next}`);
      mode = next;
    },
    close() {
      server.closeAllConnections();
      return new Promise((resolve) => server.close(resolve));
    },
  };
}
