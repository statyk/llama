import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
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
