#!/usr/bin/env node
// Upload antenna's static assets to the station's R2 bucket (spec "R2 object
// contract": offair.html and the app assets incl. hls.js). index.html is NOT
// uploaded: the clock writes it (the player page, or the off-air page while the
// station is blocked) from the copies bundled into the Worker (src/pages.ts).
//
// --preview <n> instead uploads an unlisted copy under assets/preview/<n>/ with a
// short cache time and records its keys in .preview-<n>.json; --remove-preview <n>
// deletes those keys. Nothing else in the bucket is touched by either.
// Usage: ANTENNA_BUCKET=<bucket> node scripts/deploy-assets.mjs [--dry-run]
//        [--preview <n> | --remove-preview <n>]
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const bucket = process.env.ANTENNA_BUCKET;
const argv = process.argv.slice(2);
const dryRun = argv.includes("--dry-run");
// Only these flags, and the round name after the two preview flags. Anything
// else stops here: an unknown argument must never fall through to a live upload.
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === "--preview" || a === "--remove-preview") i++;
  else if (a !== "--dry-run") {
    console.error(`unknown argument: ${a}`);
    process.exit(2);
  }
}
if (!bucket) {
  console.error("set ANTENNA_BUCKET to the station's R2 bucket name");
  process.exit(2);
}

// The value after a flag, null when the flag is absent. A round name ends up in R2
// keys and a local filename, so a missing or odd one stops here.
function roundArg(flag) {
  const i = argv.indexOf(flag);
  if (i < 0) return null;
  const round = argv[i + 1] ?? "";
  if (!/^\w[\w-]*$/.test(round)) {
    console.error(`${flag} needs a round name, e.g. ${flag} 1`);
    process.exit(2);
  }
  return round;
}
const preview = roundArg("--preview");
const removePreview = roundArg("--remove-preview");
if (preview !== null && removePreview !== null) {
  console.error("--preview and --remove-preview don't combine");
  process.exit(2);
}

const shq = (a) => (/^[\w@%+=:,./-]+$/.test(a) ? a : `'${a.replace(/'/g, "'\\''")}'`);

const HTML = "text/html; charset=utf-8";
const JS = "text/javascript; charset=utf-8";
const CSS = "text/css; charset=utf-8";
const MANIFEST = "application/manifest+json";
const HOUR = "public, max-age=3600";
const MINUTE = "public, max-age=60";
const TYPES = {
  ".html": HTML,
  ".js": JS,
  ".css": CSS,
  ".woff2": "font/woff2",
  ".png": "image/png",
  ".webmanifest": MANIFEST,
  ".txt": "text/plain; charset=utf-8",
};
const ASSETS = [
  ["offair.html", "public/offair.html", HTML, HOUR],
  ["player.js", "public/player.js", JS, HOUR],
  ["nowplaying.js", "public/nowplaying.js", JS, HOUR],
  ["style.css", "public/style.css", CSS, HOUR],
  ["assets/hls.min.js", "node_modules/hls.js/dist/hls.min.js", JS, HOUR],
];

// Every file under public/assets/, relative to it. The folder may not exist.
function walkAssets() {
  const dir = join(root, "public/assets");
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => relative(dir, join(entry.parentPath, entry.name)))
    .sort();
}

function typeOf(rel) {
  const type = TYPES[extname(rel)];
  if (!type) {
    console.error(`unknown file type: public/assets/${rel}`);
    process.exit(1);
  }
  return type;
}

function liveUploads() {
  const walked = walkAssets().filter((rel) => !rel.startsWith("preview/"));
  return [...ASSETS, ...walked.map((rel) => [`assets/${rel}`, `public/assets/${rel}`, typeOf(rel), HOUR])];
}

function previewUploads(round) {
  const base = `assets/preview/${round}`;
  const generated = mkdtempSync(join(tmpdir(), "antenna-preview-"));
  process.on("exit", () => rmSync(generated, { recursive: true, force: true }));
  const generate = (name, manifest) => {
    const path = join(generated, name);
    writeFileSync(path, `${JSON.stringify(manifest, null, 2)}\n`);
    return path;
  };

  const walked = walkAssets();
  const uploads = [[`${base}/index.html`, "public/index.html", HTML, MINUTE]];
  for (const rel of walked) {
    let file = `public/assets/${rel}`;
    if (rel === "radio.webmanifest") {
      const manifest = JSON.parse(readFileSync(join(root, file), "utf8"));
      file = generate(rel, { ...manifest, start_url: `/${base}/index.html`, scope: `/${base}/` });
    }
    uploads.push([`${base}/assets/${rel}`, file, typeOf(rel), MINUTE]);
  }
  uploads.push([`${base}/assets/hls.min.js`, "node_modules/hls.js/dist/hls.min.js", JS, MINUTE]);
  return uploads;
}

function wrangler(...r2Args) {
  const args = ["wrangler", "r2", "object", ...r2Args];
  if (dryRun) {
    console.log(["npx", ...args].map(shq).join(" "));
    return;
  }
  const r = spawnSync("npx", args, { cwd: root, stdio: "inherit" });
  if (r.error) console.error(`failed to run npx: ${r.error.message}`);
  if (r.status !== 0) process.exit(r.status ?? 1);
}

function upload(uploads) {
  for (const [, file] of uploads) {
    if (!existsSync(resolve(root, file))) {
      console.error(`missing ${file} (run npm install?)`);
      process.exit(1);
    }
  }
  for (const [key, file, type, cache] of uploads) {
    wrangler("put", `${bucket}/${key}`, "--file", resolve(root, file),
             "--content-type", type, "--cache-control", cache, "--remote");
  }
}

const roundList = (round) => join(root, `.preview-${round}.json`);

function uploadPreview(round) {
  const uploads = previewUploads(round);
  if (!dryRun) {
    // Written first, and kept across rounds of the same name, so that a failed
    // upload or a file dropped since the last round leaves no key unremovable.
    const list = roundList(round);
    const earlier = existsSync(list) ? JSON.parse(readFileSync(list, "utf8")) : [];
    const keys = new Set([...earlier, ...uploads.map(([key]) => key)]);
    writeFileSync(list, `${JSON.stringify([...keys], null, 2)}\n`);
  }
  upload(uploads);
}

function deletePreview(round) {
  const list = roundList(round);
  if (!existsSync(list)) {
    console.error(`missing ${relative(join(root, ".."), list)}: no upload recorded for round ${round}`);
    process.exit(1);
  }
  const keys = JSON.parse(readFileSync(list, "utf8"));
  // The list is a file on disk; only keys inside this round's folder may be deleted.
  const prefix = `assets/preview/${round}/`;
  const bad = keys.find((key) => typeof key !== "string" || !key.startsWith(prefix) || key.includes(".."));
  if (bad !== undefined) {
    console.error(`${relative(join(root, ".."), list)} holds a key outside ${prefix}: ${JSON.stringify(bad)}; nothing deleted`);
    process.exit(1);
  }
  for (const key of keys) {
    wrangler("delete", `${bucket}/${key}`, "--remote");
  }
  if (!dryRun) rmSync(list);
}

if (preview !== null) uploadPreview(preview);
else if (removePreview !== null) deletePreview(removePreview);
else upload(liveUploads());
