import { describe, expect, it } from "vitest";
import { archiveLink, groupSets, panelModel, setlistLine } from "../public/assets/notes.js";

describe("panelModel", () => {
  it("is old unless sections is an array", () => {
    expect(panelModel({ slug: "s" }).kind).toBe("old");
    expect(panelModel(null).kind).toBe("old");
    expect(panelModel({ sections: "x" }).kind).toBe("old");
    expect(panelModel({ sections: [] }).kind).toBe("ready");
  });
  it("drops links that are not https archive.org", () => {
    expect(panelModel({ sections: [], url: "javascript:alert(1)" }).archive).toBe(null);
    expect(panelModel({ sections: [], url: "http://archive.org/details/x" }).archive).toBe(null);
    expect(panelModel({ sections: [], url: "https://archive.org/details/x" }).archive).toBe("https://archive.org/details/x");
  });
  it("carries sections, sets and show text", () => {
    const m = panelModel({ sections: [{ heading: "h" }], artist: "Band", venue: "Club", city: "Town", date: "2008-11-01",
                           lineage: null, setlist: [{ set: "1", title: "A", segue: true }] });
    expect(m).toMatchObject({ kind: "ready", artist: "Band", where: "Club, Town", date: "Nov 1 2008", lineage: "",
                              sections: [{ heading: "h" }], sets: [{ set: "1", lines: ["A >"] }] });
  });
});

describe("archiveLink", () => {
  it("accepts only the literal https archive.org prefix", () => {
    expect(archiveLink("https://archive.org/details/x")).toBe("https://archive.org/details/x");
    for (const bad of ["http://archive.org/details/x", "https://archive.org.evil.test/x", "javascript:alert(1)", "", null, 42]) {
      expect(archiveLink(bad)).toBe(null);
    }
  });
});

describe("setlistLine", () => {
  it("normalises segue marks", () => {
    expect(setlistLine({ title: "Song", segue: true })).toBe("Song >");
    expect(setlistLine({ title: "Song>", segue: true })).toBe("Song >");
    expect(setlistLine({ title: "Song ->", segue: false })).toBe("Song >");
    expect(setlistLine({ title: "Song", segue: false })).toBe("Song");
    expect(setlistLine({ title: null, segue: false })).toBe("?");
  });
});

describe("groupSets", () => {
  it("groups consecutive entries by set", () => {
    const g = groupSets([{ set: "1", title: "A" }, { set: "1", title: "B" }, { set: "encore", title: "C" }]);
    expect(g).toEqual([{ set: "1", lines: ["A", "B"] }, { set: "encore", lines: ["C"] }]);
  });
  it("tolerates a missing setlist", () => {
    expect(groupSets(undefined as any)).toEqual([]);
  });
});
