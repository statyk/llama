// Media Session text for the car and lock screen (pure, unit-tested).
import { concertDate, nowLine, whereLine } from "./timeline.js";

export const ARTWORK = [{ src: "/assets/cassette-512.png", sizes: "512x512", type: "image/png" }];

/** Same title as Now playing. With no audio, or no show on air, the station
 * name alone: no stale artist or album. Blank fields are "", never "null". */
export function sessionText({ np, stationName, audible }) {
  if (!audible || !np || !np.show) return { title: stationName, artist: "", album: "" };
  const show = np.show;
  return {
    title: nowLine(np, stationName),
    artist: show.artist || "",
    album: [whereLine(show), concertDate(show.date)].filter(Boolean).join(", "),
  };
}
