#!/usr/bin/env node
// Renders favicon-32.png and favicon-16.png from public/assets/favicon.svg, on a
// transparent background. Run by hand when the SVG changes (needs Chrome); not part of any build.
// Usage: node scripts/make-favicon.mjs
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const assets = join(dirname(fileURLToPath(import.meta.url)), "../public/assets");
const svg = readFileSync(join(assets, "favicon.svg"), "utf8");

const browser = await chromium.launch({ channel: "chrome" });
try {
  for (const size of [32, 16]) {
    const page = await browser.newPage({ viewport: { width: size, height: size } });
    await page.setContent(
      `<!doctype html><style>html,body{margin:0;background:transparent}svg{display:block;width:${size}px;height:${size}px}</style>${svg}`);
    await page.screenshot({ path: join(assets, `favicon-${size}.png`), omitBackground: true });
    await page.close();
    console.log(`wrote public/assets/favicon-${size}.png`);
  }
} finally {
  await browser.close();
}
