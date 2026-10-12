import { describe, expect, it } from "vitest";
import { billingPeriod } from "../src/period";

const iso = (ms: number) => new Date(ms).toISOString();
const at = (s: string) => Date.parse(s);

describe("billingPeriod", () => {
  it("runs from the anniversary day at 00:00 UTC to the next", () => {
    const p = billingPeriod(at("2026-10-20T15:00:00Z"), 11);
    expect(iso(p.startMs)).toBe("2026-10-11T00:00:00.000Z");
    expect(iso(p.endMs)).toBe("2026-11-11T00:00:00.000Z");
  });

  it("before the anniversary in a month belongs to the previous period", () => {
    const p = billingPeriod(at("2026-10-10T23:59:59Z"), 11);
    expect(iso(p.startMs)).toBe("2026-09-11T00:00:00.000Z");
    expect(iso(p.endMs)).toBe("2026-10-11T00:00:00.000Z");
  });

  it("the anniversary instant itself starts the new period", () => {
    const p = billingPeriod(at("2026-10-11T00:00:00Z"), 11);
    expect(iso(p.startMs)).toBe("2026-10-11T00:00:00.000Z");
  });

  it("crosses the year", () => {
    const p = billingPeriod(at("2027-01-05T00:00:00Z"), 11);
    expect(iso(p.startMs)).toBe("2026-12-11T00:00:00.000Z");
    expect(iso(p.endMs)).toBe("2027-01-11T00:00:00.000Z");
  });

  it("clamps day 31 to the last day of shorter months", () => {
    const p = billingPeriod(at("2027-02-15T00:00:00Z"), 31);
    expect(iso(p.startMs)).toBe("2027-01-31T00:00:00.000Z");
    expect(iso(p.endMs)).toBe("2027-02-28T00:00:00.000Z");
    expect(iso(billingPeriod(at("2027-03-01T00:00:00Z"), 31).startMs)).toBe("2027-02-28T00:00:00.000Z");
  });

  it("refuses a day outside 1..31", () => {
    for (const d of [0, 32, 1.5, Number.NaN]) expect(() => billingPeriod(Date.now(), d)).toThrow(/1\.\.31/);
  });
});
