// A timeline.json with times relative to now, in the shape site.build_timeline
// publishes: a show on air, two aired, three to come.
const MINUTE = 60_000;
const SHOW_MINUTES = 90;
const TRACK_MINUTES = 8;

const SHOWS = [
  { slug: "fixture-aired-2", artist: "The Second Aired Band", date: "1985-03-07", venue: "Old Hall", city: "San Francisco, CA" },
  { slug: "fixture-aired-1", artist: "Aired Band", date: "1973-05-26", venue: "Stadium", city: null },
  { slug: "fixture-on-air", artist: "On Air Band", date: "2008-11-01", venue: "The Club", city: "Chattanooga, TN" },
  { slug: "fixture-next-1", artist: "Next Band", date: "1985-11-01", venue: "Coliseum", city: "Richmond, VA" },
  { slug: "fixture-next-2", artist: "Later Band", date: "2009-03-07", venue: "Theater", city: "Glenside, PA" },
  { slug: "fixture-next-3", artist: "Last Band", date: "2007-07-30", venue: "Big Room", city: "Boise, ID" },
];
const ON_AIR = 2;
const STARTED_MINUTES_AGO = 20;

const iso = (ms) => new Date(ms).toISOString();

function files(startMs) {
  const out = [{ kind: "clip", title: "DJ intro (set 1)", start: iso(startMs) }];
  for (let i = 0; i * TRACK_MINUTES + 2 < SHOW_MINUTES - 2; i++) {
    out.push({ kind: "track", title: `Song ${i + 1}`, start: iso(startMs + (2 + i * TRACK_MINUTES) * MINUTE) });
  }
  out.push({ kind: "clip", title: "DJ outro", start: iso(startMs + (SHOW_MINUTES - 2) * MINUTE) });
  return out;
}

/** The timeline at nowMs. `overrides.onAir` merges into the show on air; every
 * other key replaces that key of the document. */
export function makeTimeline(nowMs, overrides = {}) {
  const { onAir = {}, ...doc } = overrides;
  const firstStart = nowMs - STARTED_MINUTES_AGO * MINUTE - ON_AIR * SHOW_MINUTES * MINUTE;
  const shows = SHOWS.map((show, i) => {
    const start = firstStart + i * SHOW_MINUTES * MINUTE;
    const built = {
      ...show,
      start: iso(start),
      end: iso(start + SHOW_MINUTES * MINUTE),
      profile: "fixture",
      notes: `notes/${show.slug}.json`,
      page: `show/${show.slug}.html`,
      files: files(start),
    };
    return i === ON_AIR ? { ...built, ...onAir } : built;
  });
  const recent = shows.slice(0, ON_AIR).reverse().map((s) => s.slug);
  return { generated_at: iso(nowMs), epoch_id: "fixture", shows, recent, anchors: [], ...doc };
}

/** Puts runs of shows under block occurrences, in place, and lists them in `blocks`.
 * Each spec is { block, title, from, to } (show indices, `to` exclusive), plus
 * optional `program` (given to each of its shows), `start`/`end` (the published
 * span; `end: null` leaves it out) and `nominal` (default: the first show's start). */
export function assignBlocks(timeline, specs) {
  timeline.blocks = specs.map((spec) => {
    const nominal = spec.nominal ?? timeline.shows[spec.from].start;
    for (let i = spec.from; i < spec.to; i++) {
      Object.assign(timeline.shows[i], { block: spec.block, nominal_start: nominal },
                    spec.program === undefined ? {} : { program: spec.program });
    }
    const entry = { block: spec.block, nominal_start: nominal, title: spec.title,
                    start: spec.start ?? timeline.shows[spec.from].start };
    const end = spec.end === undefined ? timeline.shows[spec.to - 1].end : spec.end;
    return end === null ? entry : { ...entry, end };
  });
  return timeline;
}
