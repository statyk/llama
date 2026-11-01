import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "e2e/*.pw.mjs",
  globalSetup: "./e2e/global-setup.mjs",
  outputDir: "../.superpowers/player-smoke",
  reporter: "list",
  workers: 1,
  timeout: 30_000,
  // System Chrome: bundled Chromium normally can't play AAC.
  use: { channel: "chrome" },
});
