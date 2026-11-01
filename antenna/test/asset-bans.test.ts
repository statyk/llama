import { describe, expect, it } from "vitest";

const sources = import.meta.glob("../public/assets/*.js", { query: "?raw", eager: true, import: "default" }) as Record<string, string>;

describe("player assets", () => {
  it("found the module sources (an empty glob must not pass)", () => {
    const names = Object.keys(sources).map((p) => p.split("/").pop());
    expect(names).toContain("timeline.js");
    expect(names).toContain("page.js");
  });

  it("never parse markup", () => {
    const banned = /innerHTML|outerHTML|insertAdjacentHTML|document\s*\.\s*write/;
    for (const [path, text] of Object.entries(sources)) {
      expect(banned.test(text), path).toBe(false);
    }
  });
});
