import { describe, expect, it } from "vitest";
import { LIVE_KEY, offairWithoutFallback, putLive, renderLive } from "../src/live";
import { MemoryBucket } from "./support";

const E = Date.parse("2026-10-10T12:00:00.000Z");
const D = 10_240;
const CFG = { window: 6, grace: 3, offairAfterMs: 86_400_000, lookahead: 12, holdBack: 5 };
const H = { epoch_id: "e1", epoch: new Date(E).toISOString(), d: 10.24, first: 0, last: 1_000_000,
            published_at: new Date(E).toISOString(), container: "adts", fallback_version: "v1" };
const FB = { len: 7, notice: "fallback/v1/notice.aac" };

describe("renderLive", () => {
  it("builds the live playlist on air, with no off-air reason", () => {
    const r = renderLive({ horizon: H, fallback: FB, offair: false }, E + 50 * D, E + 50 * D, CFG);
    expect(r.body).toContain("seg/e1/62.aac"); // 50 + lookahead 12
    expect(r.offairWithoutFallback).toBeNull();
  });

  it("numbers the off-air notice from offairSeqMs (offairSequence)", () => {
    const r = renderLive({ horizon: H, fallback: FB, offair: true }, E + 50 * D, E + 60 * D, CFG);
    expect(r.body).toContain("#EXT-X-MEDIA-SEQUENCE:73"); // indexAt(60 d) + 12 + 1
    expect(r.body).toContain("fallback/v1/notice.aac");
  });

  it("is null before the epoch, and says why off air has no notice", () => {
    expect(renderLive({ horizon: H, fallback: FB, offair: false }, E - 1, E - 1, CFG).body).toBeNull();
    const r = renderLive({ horizon: H, fallback: null, offair: true }, E + 10 * D, E + 10 * D, CFG);
    expect(r.body).toContain("#EXT-X-ENDLIST");
    expect(r.offairWithoutFallback).toMatch(/blocked.*fallback\/v1\/index\.json is missing/);
    expect(offairWithoutFallback({ horizon: H, fallback: FB, offair: true }, E, CFG)).toBeNull();
  });
});

describe("putLive", () => {
  it("writes live.m3u8 with its content type and a max-age of at least 1 s", async () => {
    const b = new MemoryBucket();
    await putLive(b, "#EXTM3U\n", 5);
    expect(b.objects.get(LIVE_KEY)).toMatchObject({ body: "#EXTM3U\n", contentType: "application/vnd.apple.mpegurl",
                                                    cacheControl: "public, max-age=5" });
    await putLive(b, "#EXTM3U\n", 0);
    expect(b.objects.get(LIVE_KEY)!.cacheControl).toBe("public, max-age=1");
  });
});
