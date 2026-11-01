import { describe, expect, it, vi } from "vitest";
import { airTime, clipLabel, comingUp, concertDate, findShow, justAired, nowLine, notesHref, positionMs,
         showHref, stoppedLine, tapeLog, tidyTitle, whereLine, zoneLabel, STATION_NAME } from "../public/assets/timeline.js";

const t = (iso: string) => Date.parse(iso);
const BAD = "javascript:x";
const TIMELINE = {
  shows: [
    {
      slug: "prev-1", start: "2026-10-10T10:00:00.000Z", end: "2026-10-10T12:00:00.000Z",
      artist: "Prev", date: "2000-01-02", venue: "Hall", city: "Town", page: BAD, notes: BAD,
      files: [
        { kind: "clip", title: "DJ intro", start: "2026-10-10T10:00:00.000Z" },
        { kind: "track", title: "P1", start: "2026-10-10T10:01:00.000Z" },
        { kind: "track", title: "P2", start: "2026-10-10T10:30:00.000Z" },
        { kind: "track", title: "P3", start: "2026-10-10T11:00:00.000Z" },
      ],
    },
    {
      slug: "cur-1", start: "2026-10-10T12:00:00.000Z", end: "2026-10-10T13:40:00.000Z",
      artist: "Cracker", date: "2005-11-01", venue: "Knickerbockers", city: "Lincoln, NE USA", page: BAD, notes: BAD,
      files: [
        { kind: "clip", title: "DJ intro (set 1)", start: "2026-10-10T12:00:00.023Z" },
        { kind: "track", title: "One Fine Day", start: "2026-10-10T12:03:00.000Z" },
        { kind: "track", title: "Magic Foot>", start: "2026-10-10T12:10:00.000Z" },
        { kind: "track", title: "Later", start: "2026-10-10T13:00:00.000Z" },
      ],
    },
    { slug: "next-1", start: "2026-10-10T13:40:00.000Z", end: "2026-10-10T15:00:00.000Z", artist: "Next", date: "1977-05-00",
      venue: null, city: null, files: [] },
    { slug: "next-2", start: "2026-10-10T15:00:00.000Z", end: "2026-10-10T16:00:00.000Z", artist: null, date: null,
      venue: null, city: null, files: [] },
  ],
  recent: [{ slug: "wrong", start: "2030-01-01T00:00:00Z", end: "2030-01-01T01:00:00Z",
             files: [{ kind: "track", title: "wrong", start: "2030-01-01T00:10:00Z" }] }],
};

describe("positionMs", () => {
  it("uses playback time only while playing and known", () => {
    expect(positionMs({ playing: true, playbackMs: 5, nowMs: 9 })).toBe(5);
    expect(positionMs({ playing: true, playbackMs: null, nowMs: 9 })).toBe(9);
    expect(positionMs({ playing: false, playbackMs: 5, nowMs: 9 })).toBe(9);
  });
});

describe("findShow", () => {
  it("finds show and latest started file; null in gaps or without a timeline", () => {
    const np = findShow(TIMELINE, t("2026-10-10T12:05:00Z"))!;
    expect(np.show.slug).toBe("cur-1");
    expect(np.file!.title).toBe("One Fine Day");
    expect(findShow(TIMELINE, t("2026-10-10T12:00:00.010Z"))!.file).toBeNull();
    expect(findShow(TIMELINE, t("2026-10-10T13:40:00.000Z"))!.show.slug).toBe("next-1");
    expect(findShow(TIMELINE, t("2026-10-10T20:00:00Z"))).toBeNull();
    expect(findShow(null, 0)).toBeNull();
  });
});

describe("titles", () => {
  it("tidies segues and clip labels", () => {
    expect(tidyTitle("Magic Foot>")).toBe("Magic Foot >");
    expect(tidyTitle("Space ->")).toBe("Space >");
    expect(tidyTitle("Song")).toBe("Song");
    expect(clipLabel("DJ intro (set 1)")).toBe("DJ intro");
    expect(clipLabel("DJ outro")).toBe("DJ outro");
  });
});

describe("concertDate", () => {
  it("formats without Date and passes odd values through", () => {
    expect(concertDate("2008-11-01")).toBe("Nov 1 2008");
    expect(concertDate("1977-05-00")).toBe("1977-05-00");
    expect(concertDate("1977")).toBe("1977");
    expect(concertDate(null)).toBe("");
  });
});

describe("airTime and zoneLabel", () => {
  it("formats in the zone, across the DST change", () => {
    expect(airTime("2026-11-01T05:53:00Z", "America/New_York")).toEqual({ day: "Sun", time: "1:53a" });
    expect(airTime("2026-11-01T06:53:00Z", "America/New_York")).toEqual({ day: "Sun", time: "1:53a" });
    expect(airTime("2026-11-01T07:30:00Z", "America/Los_Angeles")).toEqual({ day: "Sun", time: "12:30a" });
    expect(airTime("2026-11-01T06:30:00Z", "America/Los_Angeles")).toEqual({ day: "Sat", time: "11:30p" });
    expect(zoneLabel("America/New_York")).toBe("Times shown in Eastern Time");
    expect(zoneLabel("Europe/Helsinki")).toMatch(/^Times shown in /);
  });
  it("falls back to the zone id when the engine throws on longGeneric", () => {
    const real = Intl.DateTimeFormat;
    const spy = vi.spyOn(Intl, "DateTimeFormat").mockImplementation(function (this: unknown, loc?: any, opts?: any) {
      if (opts && opts.timeZoneName === "longGeneric") throw new RangeError("Value longGeneric out of range");
      return new real(loc, opts);
    } as any);
    try {
      expect(zoneLabel("Europe/Helsinki")).toBe("Times shown in Europe/Helsinki");
    } finally {
      spy.mockRestore();
    }
  });
  it("does not depend on the runtime default locale", () => {
    const real = Intl.DateTimeFormat;
    const seen: unknown[] = [];
    const spy = vi.spyOn(Intl, "DateTimeFormat").mockImplementation(function (this: unknown, loc?: any, opts?: any) {
      seen.push(loc);
      return new real(loc, opts);
    } as any);
    try {
      airTime("2026-11-01T05:53:00Z", "America/New_York");
      zoneLabel("America/New_York");
    } finally {
      spy.mockRestore();
    }
    expect(seen.length).toBeGreaterThan(0);
    expect(seen.every((l) => l === "en-US")).toBe(true);
  });
});

describe("lines", () => {
  it("nowLine", () => {
    expect(nowLine(null, STATION_NAME)).toBe("LMA Radio");
    expect(nowLine(findShow(TIMELINE, t("2026-10-10T12:00:30Z")), "LMA Radio")).toBe("DJ intro");
    expect(nowLine(findShow(TIMELINE, t("2026-10-10T12:11:00Z")), "LMA Radio")).toBe("Magic Foot >");
    expect(nowLine({ show: { artist: "Band" }, file: null }, "LMA Radio")).toBe("Band");
    expect(nowLine({ show: { artist: null }, file: null }, "LMA Radio")).toBe("LMA Radio");
  });
  it("stoppedLine", () => {
    expect(stoppedLine({ show: { artist: "Band" }, file: null }, "LMA Radio")).toBe("Band is on the air. Press Play.");
    expect(stoppedLine(null, "LMA Radio")).toBe("LMA Radio");
    expect(stoppedLine({ show: { artist: null }, file: null }, "LMA Radio")).toBe("LMA Radio");
  });
  it("whereLine and hrefs", () => {
    expect(whereLine({ venue: "Club", city: null })).toBe("Club");
    expect(whereLine({ venue: "Club", city: "Town" })).toBe("Club, Town");
    expect(whereLine({ venue: null, city: null })).toBe("");
    expect(showHref("a b/c")).toBe("/show/a%20b%2Fc.html");
    expect(notesHref("a b/c")).toBe("/notes/a%20b%2Fc.json");
  });
});

describe("tapeLog", () => {
  it("leaves out clips, runs newest first, excludes future tracks", () => {
    const log = tapeLog(TIMELINE, t("2026-10-10T12:11:00Z"), 3);
    expect(log.map((e) => e.title)).toEqual(["Magic Foot>", "One Fine Day", "P3"]);
  });
  it("continues into the previous show and honours the limit", () => {
    const all = tapeLog(TIMELINE, t("2026-10-10T12:11:00Z"));
    expect(all.map((e) => e.title)).toEqual(["Magic Foot>", "One Fine Day", "P3", "P2", "P1"]);
    expect(tapeLog(TIMELINE, t("2026-10-10T12:11:00Z"), 2)).toHaveLength(2);
  });
  it("carries ISO starts that airTime formats", () => {
    const [e] = tapeLog(TIMELINE, t("2026-10-10T12:11:00Z"));
    expect(e.start).toBe("2026-10-10T12:10:00.000Z");
    expect(airTime(e.start, "UTC")).toEqual({ day: "Sat", time: "12:10p" });
  });
  it("ignores recent and tolerates a missing timeline", () => {
    const late = t("2030-06-01T00:00:00Z");
    expect(tapeLog(TIMELINE, late)).toEqual([
      { title: "Later", start: "2026-10-10T13:00:00.000Z" },
      { title: "Magic Foot>", start: "2026-10-10T12:10:00.000Z" },
      { title: "One Fine Day", start: "2026-10-10T12:03:00.000Z" },
      { title: "P3", start: "2026-10-10T11:00:00.000Z" },
      { title: "P2", start: "2026-10-10T10:30:00.000Z" },
      { title: "P1", start: "2026-10-10T10:01:00.000Z" },
    ]);
    const slugsOnly = { ...TIMELINE, recent: ["prev-1"] };
    expect(tapeLog(slugsOnly, late)).toEqual(tapeLog({ shows: TIMELINE.shows }, late));
    expect(tapeLog(null, 0)).toEqual([]);
  });
});

describe("comingUp and justAired", () => {
  it("lists upcoming soonest first and ignores recent", () => {
    expect(comingUp(TIMELINE, t("2026-10-10T12:11:00Z")).map((s: any) => s.slug)).toEqual(["next-1", "next-2"]);
  });
  it("returns [] past the last show or without a timeline", () => {
    expect(comingUp(TIMELINE, t("2026-10-11T00:00:00Z"))).toEqual([]);
    expect(comingUp(null, 0)).toEqual([]);
    expect(justAired(null, 0)).toEqual([]);
  });
  it("justAired is newest first and limited", () => {
    const at = t("2026-10-10T15:30:00Z");
    expect(justAired(TIMELINE, at).map((s: any) => s.slug)).toEqual(["next-1", "cur-1", "prev-1"]);
    expect(justAired(TIMELINE, at, 1)).toHaveLength(1);
  });
  it("justAired ignores recent, whatever its shape", () => {
    const late = t("2030-06-01T00:00:00Z");
    const want = ["next-2", "next-1", "cur-1", "prev-1"];
    expect(justAired(TIMELINE, late, 10).map((s: any) => s.slug)).toEqual(want);
    expect(justAired({ ...TIMELINE, recent: ["prev-1"] }, late, 10).map((s: any) => s.slug)).toEqual(want);
  });
});

describe("robustness", () => {
  const empty = { slug: "e", start: "2026-10-10T10:00:00Z", end: "2026-10-10T11:00:00Z", artist: null, date: null,
                  venue: null, city: null, files: [] };
  it("empty shows pass every helper without 'null'", () => {
    const tl = { shows: [empty] };
    const at = t("2026-10-10T10:30:00Z");
    const np = findShow(tl, at);
    const out = [nowLine(np, "S"), stoppedLine(np, "S"), whereLine(empty), concertDate(empty.date),
                 JSON.stringify(tapeLog(tl, at)), JSON.stringify(comingUp(tl, at)),
                 JSON.stringify(justAired(tl, t("2026-10-10T12:00:00Z")).map((s: any) => s.slug))];
    for (const s of out) expect(s).not.toMatch(/null|undefined/);
  });
  it("never reads page or notes", () => {
    const at = t("2026-10-10T12:11:00Z");
    const out = JSON.stringify([nowLine(findShow(TIMELINE, at), "S"), tapeLog(TIMELINE, at),
      comingUp(TIMELINE, at).map((s: any) => s.slug), justAired(TIMELINE, at).map((s: any) => s.slug),
      whereLine(TIMELINE.shows[1]), showHref("cur-1"), notesHref("cur-1")]);
    expect(out).not.toContain(BAD);
  });
});
