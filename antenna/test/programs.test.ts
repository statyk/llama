import { describe, expect, it } from "vitest";
import { blockSpan, comingUpGroups, lineupDays, localDateKey, occurrenceKey, onAirKey, presentsLine }
  from "../public/assets/programs.js";

const t = (iso: string) => Date.parse(iso);
const NY = "America/New_York";
const BG = ["Bluegrass in the Morning", "2026-11-04T12:00:00.000Z"];
const MD = ["Mid-morning Dead", "2026-11-04T14:56:00.000Z"];
const sh = (slug: string, start: string, end: string, block?: string, nominal?: string) =>
  ({ slug, start, end, ...(block ? { block, nominal_start: nominal } : {}) });
const TL_BLOCKS = {
  shows: [
    sh("bg-1", "2026-11-04T12:00:00.000Z", "2026-11-04T13:30:00.000Z", "bg", BG[1]),
    sh("bg-2", "2026-11-04T13:30:00.000Z", "2026-11-04T14:56:00.000Z", "bg", BG[1]),
    sh("dead-1", "2026-11-04T14:56:00.000Z", "2026-11-04T16:00:00.000Z", "dead", MD[1]),
    sh("legacy-1", "2026-11-04T16:00:00.000Z", "2026-11-04T17:00:00.000Z"),
  ],
  blocks: [
    { block: "bg", nominal_start: BG[1], title: BG[0], start: BG[1], end: "2026-11-04T14:56:00.000Z" },
    { block: "dead", nominal_start: MD[1], title: MD[0], start: MD[1] },
  ],
};
const TIMELINE = { shows: [sh("a", "2026-10-10T12:00:00.000Z", "2026-10-10T13:00:00.000Z"),
                           sh("b", "2026-10-10T13:00:00.000Z", "2026-10-10T14:00:00.000Z")] };
const occ = (block: string, nominal_start: string, title = block, variety = false) =>
  ({ block, nominal_start, end: nominal_start, title, variety });
const LATE = occ("late", "2026-11-05T04:00:00.000Z", "Late Night"); // 23:00 EST Nov 4
const LATE_KEY = occurrenceKey("late", "2026-11-05T04:00:00.000Z");
const LINEUP = {
  occurrences: [
    occ("bg", "2026-11-04T12:00:00.000Z", "Bluegrass in the Morning"),
    LATE,
    occ("dead", "2026-11-04T14:56:00.000Z", "Mid-morning Dead", true),
    occ("bg", "2026-11-05T12:00:00.000Z", "Bluegrass in the Morning"),
    occ("bg", "2026-11-10T12:00:00.000Z", "Bluegrass in the Morning"),
    occ("bg", "2026-11-11T12:00:00.000Z", "Bluegrass in the Morning"), // day 8: out
    occ("old", "2026-11-03T12:00:00.000Z", "Yesterday"),
    { block: "bad", nominal_start: "nope", title: "x" },
  ],
};

describe("presentsLine", () => {
  it("the program, else the house line", () => {
    expect(presentsLine({ program: " Gravel & Steel " })).toBe("Gravel & Steel");
    for (const v of [undefined, null, "", "  ", 7]) expect(presentsLine({ program: v })).toBe("LMA RADIO PRESENTS");
    expect(presentsLine(null)).toBe("LMA RADIO PRESENTS");
  });
});

describe("occurrenceKey", () => {
  it("joins the pair, null unless both are non-empty strings", () => {
    expect(occurrenceKey("a", "b")).toBe("a\u0000b");
    for (const [a, b] of [["", "b"], ["a", ""], [null, "b"], ["a", undefined], [1, "b"]]) {
      expect(occurrenceKey(a as any, b as any)).toBeNull();
    }
  });
});

describe("comingUpGroups", () => {
  it("consecutive shows of one occurrence share a heading; others get none", () => {
    const g = comingUpGroups(TL_BLOCKS, TL_BLOCKS.shows);
    expect(g.map((x) => [x.title, x.shows.map((s) => s.slug)])).toEqual([
      ["Bluegrass in the Morning", ["bg-1", "bg-2"]], ["Mid-morning Dead", ["dead-1"]], [null, ["legacy-1"]],
    ]);
    expect(g[2]).toMatchObject({ key: null, span: null });
    expect(g[0].key).toBe(occurrenceKey("bg", BG[1]));
    expect(typeof g[0].span).toBe("string");
  });
  it("a keyed show with no blocks entry is headless", () => {
    const tl = { shows: TL_BLOCKS.shows, blocks: [TL_BLOCKS.blocks[0]] };
    expect(comingUpGroups(tl, tl.shows).map((x) => x.title)).toEqual(["Bluegrass in the Morning", null]);
  });
  it("an old timeline with no blocks is one headless group", () => {
    expect(comingUpGroups(TIMELINE, TIMELINE.shows)).toEqual([{ key: null, title: null, span: null, shows: TIMELINE.shows }]);
  });
  it("tolerates missing input", () => {
    expect(comingUpGroups(null, undefined as any)).toEqual([]);
  });
});

describe("blockSpan", () => {
  it("start – end, or the start alone", () => {
    expect(blockSpan({ start: "2026-11-04T12:00:00.000Z", end: "2026-11-04T14:56:00.000Z" }, NY)).toBe("7:00a – 9:56a");
    expect(blockSpan({ start: "2026-11-04T12:00:00.000Z" }, NY)).toBe("7:00a");
  });
});

describe("localDateKey", () => {
  it("formats the date in the zone", () => {
    expect(localDateKey(t("2026-11-05T04:30:00Z"), NY)).toBe("2026-11-04");
    expect(localDateKey(t("2026-11-05T04:30:00Z"), "America/Los_Angeles")).toBe("2026-11-04");
    expect(localDateKey(t("2026-11-05T04:30:00Z"), "UTC")).toBe("2026-11-05");
  });
});

describe("lineupDays", () => {
  it("seven tabs from today, Today first, grouped by listener-local date", () => {
    const days = lineupDays(LINEUP, t("2026-11-04T15:00:00Z"), NY)!;
    expect(days.map((d) => d.label)).toEqual(["Today", "Thu", "Fri", "Sat", "Sun", "Mon", "Tue"]);
    expect(days[0].entries[0]).toMatchObject({ title: "Bluegrass in the Morning", time: "7:00a", variety: false }); // earlier today kept
    expect(days[0].entries.map((e) => e.title)).toEqual(["Bluegrass in the Morning", "Mid-morning Dead", "Late Night"]);
    expect(days[0].entries[1].variety).toBe(true);
    expect(days[1].entries.length).toBe(1);
    const all = days.flatMap((d) => d.entries.map((e) => e.key));
    expect(new Set(all).size).toBe(all.length);
    expect(all).not.toContain(occurrenceKey("old", "2026-11-03T12:00:00.000Z"));
    expect(all).not.toContain(occurrenceKey("bg", "2026-11-11T12:00:00.000Z"));
  });
  it("a block just before midnight Eastern lands on the previous day in Los Angeles", () => {
    const lu = { occurrences: [occ("n", "2026-11-05T04:30:00.000Z", "Night")] }; // 23:30 EST, 20:30 PST Nov 4
    const now = t("2026-11-04T15:00:00Z");
    const ny = lineupDays(lu, now, NY)!;
    const la = lineupDays(lu, now, "America/Los_Angeles")!;
    expect(ny[0].entries.length).toBe(1);
    expect(la[0].entries[0].time).toBe("8:30p");
    const tokyo = lineupDays(lu, now, "Asia/Tokyo")!; // now is 00:00 Nov 5 JST; the block is 13:30 Nov 5
    expect(tokyo[0].entries.length).toBe(1);
    const nz = lineupDays(lu, t("2026-11-04T05:00:00Z"), "Pacific/Auckland")!; // today = Nov 4; block is 17:30 Nov 5 NZDT
    expect(nz[0].entries.length).toBe(0);
    expect(nz[1].entries.length).toBe(1);
  });
  it("no tab skipped or repeated across spring-forward and fall-back", () => {
    for (const now of ["2027-03-13T04:30:00Z", "2027-03-14T04:30:00Z", "2026-10-31T03:30:00Z", "2026-11-01T03:30:00Z"]) {
      const keys = lineupDays({ occurrences: [] }, t(now), NY)!.map((d) => d.key);
      expect(keys.length).toBe(7);
      keys.slice(1).forEach((k, i) => expect(Date.parse(k) - Date.parse(keys[i])).toBe(86_400_000));
    }
  });
  it("the block on air since before midnight leads Today's tab", () => {
    const now = t("2026-11-05T05:30:00Z"); // 00:30 EST
    const days = lineupDays(LINEUP, now, NY, LATE_KEY)!;
    expect(days[0].entries[0].key).toBe(LATE_KEY);
    expect(lineupDays(LINEUP, now, NY, null)![0].entries.map((e) => e.key)).not.toContain(LATE_KEY);
  });
  it("an onAir key already on today's date is not duplicated", () => {
    const key = occurrenceKey("bg", "2026-11-04T12:00:00.000Z");
    const e = lineupDays(LINEUP, t("2026-11-04T15:00:00Z"), NY, key)![0].entries.map((x) => x.key);
    expect(e.filter((k) => k === key).length).toBe(1);
  });
  it("missing or malformed lineups give null", () => {
    for (const v of [null, {}, { occurrences: "x" }]) expect(lineupDays(v, 0)).toBeNull();
  });
});

describe("onAirKey", () => {
  it("the on-air show's occurrence, null for a legacy show or nothing on air", () => {
    expect(onAirKey(TL_BLOCKS, t("2026-11-04T13:00:00Z"))).toBe(occurrenceKey("bg", BG[1]));
    expect(onAirKey(TL_BLOCKS, t("2026-11-04T16:30:00Z"))).toBeNull();
    expect(onAirKey(TL_BLOCKS, t("2026-11-04T20:00:00Z"))).toBeNull();
    expect(onAirKey(null, 0)).toBeNull();
  });
});

describe("timeline.js exports", () => {
  it("are unchanged", async () => {
    expect(Object.keys(await import("../public/assets/timeline.js")).sort()).toEqual([
      "STATION_NAME", "positionMs", "findShow", "tidyTitle", "clipLabel", "nowLine", "stoppedLine", "tapeLog", "comingUp",
      "justAired", "concertDate", "airTime", "airLine", "zoneLabel", "whereLine", "showHref", "notesHref"].sort());
  });
});
