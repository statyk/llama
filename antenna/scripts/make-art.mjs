#!/usr/bin/env node
// Renders the committed pictures from the page's own cassette, alone on the paper.
// Run by hand when the cassette changes (needs Chrome); not part of any build.
// Usage: node scripts/make-art.mjs
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import { startServer } from "../e2e/serve.mjs";

const assets = join(dirname(fileURLToPath(import.meta.url)), "../public/assets");
const CASSETTE_WIDTH = 330; // CSS px, the size the design is drawn at

// [file, width, height, cassette width in the picture]
const PICTURES = [
  ["cassette-512.png", 512, 512, 464],
  ["cassette-og.png", 1200, 630, 820],
  ["icon-180.png", 180, 180, 164],
  ["icon-192.png", 192, 192, 176],
];

const site = await startServer();
const browser = await chromium.launch({ channel: "chrome" });
try {
  for (const [file, width, height, cassette] of PICTURES) {
    const page = await browser.newPage({ viewport: { width, height } });
    await page.goto(site.url, { waitUntil: "load" });
    await page.evaluate(({ designWidth, zoom }) => {
      const cass = document.querySelector(".cass");
      cass.style.width = `${designWidth}px`;
      cass.style.alignSelf = "center";
      cass.style.zoom = String(zoom);
      document.body.replaceChildren(cass);
      document.body.style.cssText = "height:100vh;display:flex;align-items:center;justify-content:center";
      return document.fonts.ready;
    }, { designWidth: CASSETTE_WIDTH, zoom: cassette / CASSETTE_WIDTH });
    await page.screenshot({ path: join(assets, file) });
    await page.close();
    console.log(`wrote public/assets/${file}`);
  }
} finally {
  await browser.close();
  await site.close();
}
