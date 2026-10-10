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

const shq = (a) => (/^[\w@%+=:,./-]+$/.test(a) ? a : `'${a.replace(/'/g, "'\\''")}'`);

const HTML = "text/html; charset=utf-8";
const JS = "text/javascript; charset=utf-8";
const CSS = "text/css; charset=utf-8";
const HOUR = "public, max-age=3600";
const ASSETS = [
  ["offair.html", "public/offair.html", HTML, HOUR],
  ["player.js", "public/player.js", JS, HOUR],
  ["nowplaying.js", "public/nowplaying.js", JS, HOUR],
  ["style.css", "public/style.css", CSS, HOUR],
  ["assets/hls.min.js", "node_modules/hls.js/dist/hls.min.js", JS, HOUR],
  // last: short TTL, and it references everything above
  ["index.html", "public/index.html", HTML, "public, max-age=60"],
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
    console.log(["npx", ...args].map(shq).join(" "));
    continue;
  }
  const r = spawnSync("npx", args, { cwd: root, stdio: "inherit" });
  if (r.error) console.error(`failed to run npx: ${r.error.message}`);
  if (r.status !== 0) process.exit(r.status ?? 1);
}
