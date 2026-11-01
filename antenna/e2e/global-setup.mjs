// Generates the audio the fixture stream plays: real AAC, cut into segments by
// counting ADTS frames, as the transmitter cuts its own. *.aac is gitignored.
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SEG_COUNT, SEG_DIR, SEG_FRAMES, SEG_MS, SEG_RATE } from "./serve.mjs";

const SECONDS = (SEG_COUNT * SEG_MS) / 1000 + 1;

function encode(path) {
  const r = spawnSync("ffmpeg", [
    "-hide_banner", "-loglevel", "error", "-y",
    "-f", "lavfi", "-i", `sine=frequency=330:sample_rate=${SEG_RATE}:duration=${SECONDS}`,
    "-ac", "2", "-c:a", "aac", "-b:a", "96k", "-f", "adts", path,
  ], { encoding: "utf8" });
  if (r.error?.code === "ENOENT") throw new Error("the smoke tests need ffmpeg on PATH: it was not found");
  if (r.error) throw r.error;
  if (r.status !== 0) throw new Error(`ffmpeg failed: ${r.stderr}`);
}

/** Byte offset of every ADTS frame. */
function frameOffsets(adts) {
  const offsets = [];
  for (let at = 0; at + 7 <= adts.length; ) {
    if (adts[at] !== 0xff || (adts[at + 1] & 0xf0) !== 0xf0) throw new Error(`no ADTS sync at byte ${at}`);
    offsets.push(at);
    at += ((adts[at + 3] & 0x03) << 11) | (adts[at + 4] << 3) | (adts[at + 5] >> 5);
  }
  return offsets;
}

export default function globalSetup() {
  const scratch = mkdtempSync(join(tmpdir(), "antenna-smoke-"));
  try {
    const path = join(scratch, "tone.aac");
    encode(path);
    const adts = readFileSync(path);
    const offsets = frameOffsets(adts);
    if (offsets.length < SEG_COUNT * SEG_FRAMES) throw new Error(`ffmpeg gave ${offsets.length} frames`);
    rmSync(SEG_DIR, { recursive: true, force: true });
    mkdirSync(SEG_DIR, { recursive: true });
    for (let i = 0; i < SEG_COUNT; i++) {
      const end = offsets[(i + 1) * SEG_FRAMES] ?? adts.length;
      writeFileSync(join(SEG_DIR, `${i}.aac`), adts.subarray(offsets[i * SEG_FRAMES], end));
    }
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}
