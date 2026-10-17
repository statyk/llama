import { describe, expect, it } from "vitest";
import { describeError } from "../src/errors";

describe("describeError", () => {
  it("is an Error's message, or the value as a string", () => {
    expect(describeError(new Error("boom"))).toBe("boom");
    expect(describeError("plain")).toBe("plain");
    expect(describeError(42)).toBe("42");
    expect(describeError(undefined)).toBe("undefined");
  });

  it("never throws, whatever was thrown", () => {
    // String() throws on each of these.
    const noProto = Object.create(null);
    const badToString = { toString() { throw new Error("no"); } };
    const badMessage = Object.defineProperty(new Error("x"), "message", { get() { throw new Error("no"); } });
    for (const v of [noProto, badToString, badMessage, Symbol.for("s")]) {
      expect(typeof describeError(v)).toBe("string");
    }
    expect(describeError(Symbol.for("s"))).toBe("Symbol(s)");
    expect(describeError(noProto)).toBe("[object Object]");
    expect(describeError(badMessage)).toBe("[object Error]");
  });
});
