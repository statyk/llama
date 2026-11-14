import { describe, expect, it } from "vitest";
import { mergeDropped } from "../public/assets/dropped.js";
import { groupSets } from "../public/assets/notes.js";

const kept = (set: string, title: string, segue = false) => ({ set, title, segue });
const SETLIST = [kept("1", "A"), kept("1", "B"), kept("2", "C"), kept("2", "D")];
const flat = (groups: any[]) =>
  groups.map((g) => ({ set: g.set, items: g.items.map((i: any) => [i.text, i.struck, i.value]) }));

describe("mergeDropped", () => {
  it("strikes inline and does not count it", () => {
    const out = mergeDropped(SETLIST, [{ title: "Junk", set: "1", after_track: 1 }]);
    expect(flat(out)).toEqual([
      { set: "1", items: [["A", false, null], ["Junk", true, null], ["B", false, 2]] },
      { set: "2", items: [["C", false, null], ["D", false, null]] },
    ]);
  });
  it("puts after_track 0 at the start of the first group", () => {
    const out = mergeDropped(SETLIST, [{ title: "Intro", set: "1", after_track: 0 }]);
    expect(flat(out)[0]).toEqual({ set: "1", items: [["Intro", true, null], ["A", false, 1], ["B", false, 2]] });
  });
  it("keeps a struck entry at a set boundary in the earlier group", () => {
    const out = mergeDropped(SETLIST, [{ title: "Gap", set: "2", after_track: 2 }]);
    expect(flat(out)[0].items).toEqual([["A", false, null], ["B", false, null], ["Gap", true, null]]);
    expect(flat(out)[1].items).toEqual([["C", false, null], ["D", false, null]]);
  });
  it("appends a tail entry to the last group", () => {
    const out = mergeDropped(SETLIST, [{ title: "Tail", set: "2", after_track: 4 }]);
    expect(flat(out)[1].items).toEqual([["C", false, null], ["D", false, null], ["Tail", true, null]]);
  });
  it("clamps beyond the kept count, keeping input order with entries at the kept count", () => {
    const out = mergeDropped([kept("1", "A"), kept("1", "B")], [
      { title: "Late", set: "1", after_track: 99 },
      { title: "Last", set: "1", after_track: 2 },
    ]);
    expect(flat(out)).toEqual([{ set: "1", items: [["A", false, null], ["B", false, null],
                                                    ["Late", true, null], ["Last", true, null]] }]);
  });
  it("keeps input order at one position and numbers by kept ordinal", () => {
    const out = mergeDropped(SETLIST, [{ title: "X", set: "1", after_track: 1 }, { title: "Y", set: "1", after_track: 1 }]);
    expect(flat(out)[0].items).toEqual([["A", false, null], ["X", true, null], ["Y", true, null], ["B", false, 2]]);
  });
  it("forms one group from only struck entries", () => {
    const out = mergeDropped([], [{ title: "X", set: "1", after_track: 0 }, { title: "Y", set: "1", after_track: 5 }]);
    expect(flat(out)).toEqual([{ set: undefined, items: [["X", true, null], ["Y", true, null]] }]);
  });
  it("renders segue marks on kept text and tidies struck titles", () => {
    const out = mergeDropped([kept("1", "A", true), kept("1", "B")], [{ title: "  Junk  ", set: "1", after_track: 1 }]);
    expect(out[0].items.map((i: any) => i.text)).toEqual(["A >", "Junk", "B"]);
  });
  it("ignores a damaged dropped value", () => {
    const base = flat(mergeDropped(SETLIST, undefined));
    expect(flat(mergeDropped(SETLIST, "x"))).toEqual(base);
    expect(flat(mergeDropped(SETLIST, { title: "T", after_track: 1 }))).toEqual(base);
    const bad = [null, 3, "s", [], { title: "", after_track: 1 }, { title: 5, after_track: 1 },
                 { title: "T", after_track: "3" }, { title: "T", after_track: 1.5 }, { title: "T", after_track: -1 },
                 { title: "T", after_track: true }, { title: "T" }];
    expect(flat(mergeDropped(SETLIST, bad))).toEqual(base);
    expect(flat(mergeDropped(SETLIST, [...bad, { title: "Ok", after_track: 1 }]))[0].items[1]).toEqual(["Ok", true, null]);
  });
  it("equals groupSets without dropped", () => {
    const want = groupSets(SETLIST).map((g: any) => ({
      set: g.set, items: g.lines.map((text: string) => ({ text, struck: false, value: null })) }));
    for (const dropped of [undefined, null, []]) expect(mergeDropped(SETLIST, dropped)).toEqual(want);
    expect(mergeDropped([], undefined)).toEqual([]);
  });
});
