import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { configFromEnv, GRID_D } from "../src/clock";
import wranglerText from "../wrangler.jsonc?raw";

/** wrangler.jsonc uses whole-line // comments only. */
const config = (() => {
  try {
    return JSON.parse(wranglerText.split("\n").filter((l) => !l.trim().startsWith("//")).join("\n"));
  } catch (e) {
    throw new Error(`wrangler.jsonc: only whole-line // comments and no trailing commas are supported by this test (${e})`);
  }
})();

describe("wrangler.jsonc (this repo is public)", () => {
  it("carries no account details and no email address", () => {
    expect(config).not.toHaveProperty("account_id");
    expect(wranglerText).not.toMatch(/"(account_id|zone_id)"\s*:/); // any depth, incl. env.* and routes[]
    expect(wranglerText).not.toMatch(/\b[0-9a-f]{32}\b/i); // Cloudflare account and zone IDs are 32 hex
    expect(config).not.toHaveProperty("routes"); // cron-only (spec "Architecture")
    expect(wranglerText).not.toMatch(/@[a-z0-9-]+\.[a-z]/i);
    expect(config.workers_dev).toBe(false);
    expect(config.preview_urls).toBe(false);
  });

  it("binds send_email unrestricted: the destination is the ALERT_EMAIL_TO secret", () => {
    expect(config.send_email).toEqual([{ name: "ALERT_EMAIL" }]);
    const bound = (env as unknown as { ALERT_EMAIL?: { send?: unknown } }).ALERT_EMAIL;
    expect(typeof bound?.send).toBe("function");
  });
});

describe("wrangler.jsonc: the metronome (metronome spec)", () => {
  it("binds one SQLite-backed Durable Object class, Metronome, created by migration v1", () => {
    expect(config.durable_objects).toEqual({ bindings: [{ name: "METRONOME_DO", class_name: "Metronome" }] });
    expect(config.migrations).toEqual([{ tag: "v1", new_sqlite_classes: ["Metronome"] }]);
    expect(config).not.toHaveProperty("exports"); // mutually exclusive with migrations
    const ns = (env as unknown as { METRONOME_DO?: { idFromName?: unknown } }).METRONOME_DO;
    expect(typeof ns?.idFromName).toBe("function");
  });

  it("carries the switch as exactly \"on\" or \"off\" (a typo would silently mean off)", () => {
    expect(["on", "off"]).toContain(config.vars.METRONOME);
  });

  it("is still driven by one cron trigger, every minute", () => {
    expect(config.triggers).toEqual({ crons: ["* * * * *"] });
  });
});

describe("wrangler.jsonc playlist vars (amendment A4, amended 2026-10-12)", () => {
  const cfg = configFromEnv(config.vars);

  it("lists 16 segments, 12 past the one airing, and starts players 12 before the listed end", () => {
    expect(config.vars).toMatchObject({ PLAYLIST_WINDOW: "16", PLAYLIST_LOOKAHEAD: "12", PLAYLIST_HOLD_BACK: "12" });
    expect(cfg).toMatchObject({ window: 16, lookahead: 12, holdBack: 12 });
  });

  it("keeps the deployment rule hold-back = lookahead (hugo's dead-clock check dates the playlist by it)", () => {
    expect(cfg.holdBack).toBe(cfg.lookahead);
    // ... and the hold-back is actually emitted: >= 3 target durations.
    expect(cfg.holdBack! * GRID_D).toBeGreaterThanOrEqual(3 * Math.ceil(GRID_D));
  });

  it("lists no segment longer after it starts than transmitter's prune floor allows for", () => {
    // A segment n stays listed while n >= end - window + 1, and the end is at
    // most cur + lookahead, or horizon.last while held for up to `grace` past
    // it: so at most (window - lookahead + grace) * d after it starts.
    // transmitter's PRUNE_MARGIN_FLOOR_MINUTES (config.py) is derived from
    // (6 + 3) * d of listing; the deployed window must not exceed that.
    expect((cfg.window - cfg.lookahead! + cfg.grace) * GRID_D).toBeLessThanOrEqual((6 + 3) * GRID_D);
  });
});
