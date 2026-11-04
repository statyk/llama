// A notes/_lineup.json in the shape site.build_lineup publishes, relative to a
// test's mocked now: occurrences from a day back to eight days on, three a day
// at fixed local times of a zone `offsetHours` from UTC (no daylight saving
// inside the week the tests use).
const HOUR = 3_600_000;
const DAY = 24 * HOUR;

export const DAILY = [
  { block: "early", title: "Early Variety", hour: 5, variety: true },
  { block: "bg", title: "Bluegrass in the Morning", hour: 7, variety: false },
  { block: "late", title: "Late Night", hour: 23, variety: true },
];

const iso = (ms) => new Date(ms).toISOString();

/** Local midnight (as a UTC ms) of the day `days` from nowMs's local day. */
export function localMidnight(nowMs, offsetHours, days = 0) {
  const off = offsetHours * HOUR;
  return Math.floor((nowMs + off) / DAY) * DAY - off + days * DAY;
}

/** The nominal start of `block` on the local day `days` from nowMs's. */
export function nominalStart(nowMs, offsetHours, block, days = 0) {
  const spec = DAILY.find((d) => d.block === block);
  return iso(localMidnight(nowMs, offsetHours, days) + spec.hour * HOUR);
}

/** `titles` maps a block name to a replacement title. */
export function makeLineup(nowMs, offsetHours, titles = {}) {
  const occurrences = [];
  for (let d = -1; d <= 8; d++) {
    DAILY.forEach((spec, i) => {
      const start = localMidnight(nowMs, offsetHours, d) + spec.hour * HOUR;
      const next = DAILY[i + 1] ? localMidnight(nowMs, offsetHours, d) + DAILY[i + 1].hour * HOUR
                                : localMidnight(nowMs, offsetHours, d + 1) + DAILY[0].hour * HOUR;
      occurrences.push({ block: spec.block, nominal_start: iso(start), end: iso(next),
                         title: titles[spec.block] ?? spec.title, variety: spec.variety });
    });
  }
  return { occurrences };
}
