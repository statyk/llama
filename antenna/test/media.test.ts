import { describe, expect, it } from "vitest";
import { ARTWORK, sessionText } from "../public/assets/media.js";

const np = { show: { artist: "Band", venue: "Club", date: "2008-11-01" }, file: { kind: "track", title: "Song>" } };

describe("sessionText", () => {
  it("is the now-playing title, the band, and venue plus concert date", () => {
    expect(sessionText({ np, stationName: "LMA Radio", audible: true }))
      .toEqual({ title: "Song >", artist: "Band", album: "Club, Nov 1 2008" });
  });
  it("is the station name with no show on air", () => {
    expect(sessionText({ np: null, stationName: "LMA Radio", audible: true }))
      .toEqual({ title: "LMA Radio", artist: "", album: "" });
  });
  it("leaves no stale song, artist or album when nothing is audible", () => {
    expect(sessionText({ np, stationName: "LMA Radio", audible: false }))
      .toEqual({ title: "LMA Radio", artist: "", album: "" });
  });
  it("shows the show name between songs", () => {
    expect(sessionText({ np: { show: np.show, file: null }, stationName: "LMA Radio", audible: true }).title).toBe("Band");
  });
  it("leaves blank fields out, never printing null", () => {
    const r = sessionText({ np: { show: { artist: "Band", venue: null, date: null }, file: null }, stationName: "S", audible: true });
    expect(r).toEqual({ title: "Band", artist: "Band", album: "" });
    expect(JSON.stringify(r)).not.toContain("null");
    expect(sessionText({ np: { show: { venue: "Club", date: null } , file: null }, stationName: "S", audible: true }).album).toBe("Club");
  });
  it("exports the artwork", () => {
    expect(ARTWORK).toEqual([{ src: "/assets/cassette-512.png", sizes: "512x512", type: "image/png" }]);
  });
});
