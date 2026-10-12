import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { r2Bucket } from "../src/bucket";
import { INDEX_KEY, reconcileIndex, sha256Hex } from "../src/indexpage";
import { OFFAIR_PAGE, PLAYER_PAGE } from "../src/pages";
import { MemoryBucket } from "./support";

describe("reconcileIndex", () => {
  it("writes the player page when not blocked and the off-air page when blocked, each once", async () => {
    const bucket = new MemoryBucket();
    expect(await reconcileIndex(bucket, false)).toBe("written");
    expect(bucket.objects.get(INDEX_KEY)!.body).toBe(PLAYER_PAGE);
    expect(await reconcileIndex(bucket, false)).toBe("unchanged");
    expect(await reconcileIndex(bucket, true)).toBe("written");
    expect(bucket.objects.get(INDEX_KEY)!.body).toBe(OFFAIR_PAGE);
    expect(bucket.objects.get(INDEX_KEY)!.customMetadata).toEqual({ sha256: await sha256Hex(OFFAIR_PAGE), page: "offair" });
    expect(await reconcileIndex(bucket, true)).toBe("unchanged");
    expect(bucket.puts(INDEX_KEY)).toBe(2);
  });

  it("corrects a hand-uploaded index.html (no metadata) at once", async () => {
    const bucket = new MemoryBucket();
    bucket.seed(INDEX_KEY, "<html>old</html>");
    expect(await reconcileIndex(bucket, false)).toBe("written");
  });

  it("the off-air page has no player scripts (the kill switch would block them)", () => {
    expect(OFFAIR_PAGE).toContain("The station is off the air.");
    expect(OFFAIR_PAGE).not.toContain("player.js");
    expect(PLAYER_PAGE).toContain("player.js");
  });

  it("writes through the R2 binding with its content type, max-age and metadata", async () => {
    await reconcileIndex(r2Bucket(env.BUCKET), true);
    const obj = await env.BUCKET.get(INDEX_KEY);
    expect(obj!.httpMetadata!.contentType).toBe("text/html; charset=utf-8");
    expect(obj!.httpMetadata!.cacheControl).toBe("public, max-age=60");
    expect(obj!.customMetadata!.page).toBe("offair");
    expect(await obj!.text()).toBe(OFFAIR_PAGE);
    expect(await reconcileIndex(r2Bucket(env.BUCKET), true)).toBe("unchanged");
  });
});
