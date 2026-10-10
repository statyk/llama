import { describe, expect, it } from "vitest";
import { findNowPlaying, playBlockedNotice, nowPlayingText, prefersNativeHls } from "../public/nowplaying.js";

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
