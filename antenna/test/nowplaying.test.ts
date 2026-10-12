import { describe, expect, it } from "vitest";
import { classifyProbe, findNowPlaying, hlsErrorNotice, playBlockedNotice, nowPlayingText, prefersNativeHls,
         StallWatch } from "../public/nowplaying.js";

const TIMELINE = {
  shows: [
    {
      slug: "cracker-2005-11-01", start: "2026-10-10T12:00:00.000Z", end: "2026-10-10T13:40:00.000Z",
      artist: "Cracker", date: "2005-11-01", venue: "Knickerbockers", city: "Lincoln, NE USA",
      files: [
        { kind: "clip", title: "DJ intro (set 1)", start: "2026-10-10T12:00:00.023Z" },
        { kind: "track", title: "One Fine Day", start: "2026-10-10T12:03:00.000Z" },
        { kind: "track", title: "Guarded By Monkeys", start: "2026-10-10T12:10:39.000Z" },
      ],
    },
  ],
};
const t = (iso: string) => Date.parse(iso);

describe("prefersNativeHls", () => {
  it("uses native HLS on Apple WebKit only", () => {
    expect(prefersNativeHls({ vendor: "Apple Computer, Inc." }, true)).toBe(true); // Safari, any iOS browser
    expect(prefersNativeHls({ vendor: "Google Inc." }, true)).toBe(false); // Chrome's native HLS: use hls.js
    expect(prefersNativeHls({ vendor: "" }, false)).toBe(false); // Firefox
    expect(prefersNativeHls({ vendor: "Apple Computer, Inc." }, false)).toBe(false);
  });
});

describe("findNowPlaying", () => {
  it("finds the show and the latest file that has started", () => {
    const np = findNowPlaying(TIMELINE, t("2026-10-10T12:05:00Z"))!;
    expect(np.show.slug).toBe("cracker-2005-11-01");
    expect(np.file!.title).toBe("One Fine Day");
  });
  it("has a show but no file before the first file starts (encoder priming)", () => {
    expect(findNowPlaying(TIMELINE, t("2026-10-10T12:00:00.010Z"))!.file).toBeNull();
  });
  it("returns null in a gap, in the fallback loop, or without a timeline", () => {
    expect(findNowPlaying(TIMELINE, t("2026-10-10T14:00:00Z"))).toBeNull();
    expect(findNowPlaying(null, t("2026-10-10T12:05:00Z"))).toBeNull();
  });
});

describe("nowPlayingText", () => {
  it("formats show and file, or says the station will be back", () => {
    const np = findNowPlaying(TIMELINE, t("2026-10-10T12:05:00Z"));
    expect(nowPlayingText(np, true)).toBe("Cracker — 2005-11-01, Knickerbockers, Lincoln, NE USA · One Fine Day");
    expect(nowPlayingText(null, true)).toBe("We'll be back shortly.");
    expect(nowPlayingText(null, false)).toBe("Tuning in…");
  });
});

describe("show-boundary edges and file ordering", () => {
  it("includes start, excludes end", () => {
    expect(findNowPlaying(TIMELINE, t("2026-10-10T12:00:00.000Z"))).not.toBeNull();
    expect(findNowPlaying(TIMELINE, t("2026-10-10T13:40:00.000Z"))).toBeNull();
    expect(findNowPlaying(TIMELINE, t("2026-10-10T13:39:59.999Z"))!.file!.title).toBe("Guarded By Monkeys");
  });
  it("assumes files sorted by start: a started file after a not-yet-started one is not found (break)", () => {
    const unsorted = { shows: [{ ...TIMELINE.shows[0], files: [
      { kind: "track", title: "B", start: "2026-10-10T12:10:00.000Z" },
      { kind: "track", title: "A", start: "2026-10-10T12:03:00.000Z" } ] }] };
    expect(findNowPlaying(unsorted, t("2026-10-10T12:05:00Z"))!.file).toBeNull();
  });
});

describe("playBlockedNotice", () => {
  it("only NotAllowedError while playing is a blocked notice; AbortError is ignored", () => {
    expect(playBlockedNotice({ name: "NotAllowedError" }, true)).toMatch(/blocked/);
    expect(playBlockedNotice({ name: "AbortError" }, true)).toBeNull();
    expect(playBlockedNotice({ name: "NotAllowedError" }, false)).toBeNull();
  });
});

describe("hlsErrorNotice", () => {
  it("treats the clock's ENDLIST-only playlist (levelEmptyError, non-fatal) as off-air", () => {
    expect(hlsErrorNotice({ details: "levelEmptyError", fatal: false })).toBe("The station is off the air.");
  });
  it("treats a 403 as off-air and other fatal errors as unavailable", () => {
    expect(hlsErrorNotice({ details: "levelLoadError", fatal: false, response: { code: 403 } }))
      .toBe("The station is off the air.");
    expect(hlsErrorNotice({ details: "fragLoadError", fatal: true, response: { code: 500 } }))
      .toBe("The stream is unavailable right now.");
  });
  it("lets hls.js recover from any other non-fatal error", () => {
    expect(hlsErrorNotice({ details: "fragLoadError", fatal: false, response: { code: 404 } })).toBeNull();
    expect(hlsErrorNotice({ details: "bufferStalledError", fatal: false })).toBeNull();
  });
});

describe("hlsErrorNotice: the 403 can arrive on networkDetails", () => {
  it("treats networkDetails.status 403 as off-air", () => {
    expect(hlsErrorNotice({ fatal: false, networkDetails: { status: 403 } })).toBe("The station is off the air.");
  });
});

describe("classifyProbe", () => {
  it("only a 403 or an ENDLIST playlist is off-air", () => {
    expect(classifyProbe(403, "")).toBe("offair");
    expect(classifyProbe(200, "#EXTM3U\n#EXT-X-ENDLIST\n")).toBe("offair");
    for (const [s, b] of [[0, ""], [200, "#EXTM3U\nseg/e1/1.aac\n"], [503, ""], [429, ""], [404, ""]] as const) {
      expect(classifyProbe(s, b)).toBe("unknown");
    }
  });
});

describe("StallWatch", () => {
  const playFor = (w: StallWatch, fromS: number, fromMs: number, seconds: number) => {
    for (let i = 0; i <= seconds; i++) expect(w.tick(fromS + i, fromMs + i * 1000)).toBe(false);
  };

  it("never probes while playback advances", () => {
    const w = new StallWatch();
    w.reset(0);
    playFor(w, 0, 0, 120);
  });

  it("probes after 15 s without progress, at most every 10 s, one at a time", () => {
    const w = new StallWatch();
    w.reset(0);
    playFor(w, 0, 0, 10); // position 10 at t=10 s
    const probes: number[] = [];
    for (let t = 11_000; t <= 60_000; t += 1000) {
      if (w.tick(10, t)) {
        probes.push(t);
        expect(w.tick(10, t + 500)).toBe(false); // still probing
        w.verdict("unknown");
      }
    }
    expect(probes).toEqual([25_000, 35_000, 45_000, 55_000]);
  });

  it("goes off-air on two consecutive off-air verdicts (the kill switch mid-play)", () => {
    const w = new StallWatch();
    w.reset(0);
    playFor(w, 0, 0, 10);
    expect(w.tick(10, 25_000)).toBe(true);
    expect(w.verdict("offair")).toBe(false);
    expect(w.tick(10, 35_000)).toBe(true);
    expect(w.verdict("offair")).toBe(true);
  });

  it("a blip: network errors while stalled, then progress resumes -- never off-air", () => {
    const w = new StallWatch();
    w.reset(0);
    playFor(w, 0, 0, 10);
    expect(w.tick(10, 25_000)).toBe(true);
    expect(w.verdict("offair")).toBe(false); // one stray 403 is not enough...
    expect(w.tick(10, 35_000)).toBe(true);
    expect(w.verdict("unknown")).toBe(false); // ...and a non-verdict resets the count
    expect(w.tick(10, 45_000)).toBe(true);
    expect(w.verdict("offair")).toBe(false);
    expect(w.tick(11, 46_000)).toBe(false); // playing again
    expect(w.stalled(47_000)).toBe(false);
  });
});
