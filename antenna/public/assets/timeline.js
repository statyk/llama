// Pure timeline helpers for the player (unit-tested, no DOM). Shares nothing
// with the frozen root files. Concert dates are strings, never Date.
//
// Timeline contract: shows[] sorted by start; shows[].files[] sorted by start.
// `recent`, `page` and `notes` are deliberately never read here.

export const STATION_NAME = "LMA Radio";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Playback position as a wall-clock ms: the stream's program-date-time when
 * playing and known, else the current time. */
export function positionMs({ playing, playbackMs, nowMs }) {
  return playing && playbackMs != null ? playbackMs : nowMs;
}

function showsOf(timeline) {
  return timeline && Array.isArray(timeline.shows) ? timeline.shows : [];
}

/** Same contract as nowplaying.findNowPlaying. */
export function findShow(timeline, atMs) {
  for (const show of showsOf(timeline)) {
    if (atMs >= Date.parse(show.start) && atMs < Date.parse(show.end)) {
      let file = null;
      for (const f of show.files || []) {
        if (Date.parse(f.start) <= atMs) file = f;
        else break;
      }
      return { show, file };
    }
  }
  return null;
}

/** A trailing segue mark reads "Title >". */
export function tidyTitle(s) {
  const t = String(s == null ? "" : s).trim();
  return t.replace(/\s*-*>\s*$/, " >");
}

/** "DJ intro (set 1)" -> "DJ intro". */
export function clipLabel(s) {
  return String(s == null ? "" : s).replace(/\s*\([^)]*\)\s*$/, "").trim();
}

export function nowLine(np, stationName) {
  if (!np || !np.show) return stationName;
  const f = np.file;
  if (f && f.title) return f.kind === "clip" ? clipLabel(f.title) : tidyTitle(f.title);
  return np.show.artist || stationName;
}

export function stoppedLine(np, stationName) {
  if (np && np.show && np.show.artist) return "Press Play to listen.";
  return stationName;
}

/** Every track (no clips) of the show on air, first to last, each marked
 * "played", "now" (the last track started by atMs) or "next". Before the first
 * track starts none is "now". Never reaches into another show. */
export function tapeLog(timeline, atMs) {
  const np = findShow(timeline, atMs);
  if (!np) return [];
  const files = (np.show.files || []).filter((f) => f.kind === "track");
  let now = -1;
  files.forEach((f, i) => {
    if (Date.parse(f.start) <= atMs) now = i;
  });
  return files.map((f, i) => ({
    title: f.title, start: f.start, state: i < now ? "played" : i === now ? "now" : "next",
  }));
}

/** Shows that have not started yet, soonest first. */
export function comingUp(timeline, atMs) {
  return showsOf(timeline)
    .filter((s) => Date.parse(s.start) > atMs)
    .sort((a, b) => Date.parse(a.start) - Date.parse(b.start));
}

/** Shows that have ended, newest first. */
export function justAired(timeline, atMs, limit = 6) {
  return showsOf(timeline)
    .filter((s) => Date.parse(s.end) <= atMs)
    .sort((a, b) => Date.parse(b.start) - Date.parse(a.start))
    .slice(0, limit);
}

/** "2008-11-01" -> "Nov 1 2008"; anything else comes back as stored. */
export function concertDate(s) {
  if (s == null) return "";
  const str = String(s);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(str);
  if (!m) return str;
  const mo = Number(m[2]);
  const d = Number(m[3]);
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return str;
  return `${MONTHS[mo - 1]} ${d} ${m[1]}`;
}

/** { day: "Sun", time: "1:53a" } in the given zone (default: the runtime's). */
export function airTime(iso, timeZone) {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone, weekday: "short", hour: "numeric", minute: "2-digit", hour12: true,
  });
  const p = {};
  for (const part of fmt.formatToParts(new Date(Date.parse(iso)))) p[part.type] = part.value;
  const suffix = String(p.dayPeriod || "").charAt(0).toLowerCase();
  return { day: p.weekday, time: `${p.hour}:${p.minute}${suffix}` };
}

/** "Sat 12:26a to 1:53a", naming the end's day only when it differs. */
export function airLine({ start, end }) {
  const from = airTime(start);
  const to = airTime(end);
  return `${from.day} ${from.time} to ${to.day === from.day ? "" : `${to.day} `}${to.time}`;
}

export function zoneLabel(timeZone) {
  let name;
  try {
    const fmt = new Intl.DateTimeFormat("en-US", { timeZone, timeZoneName: "longGeneric" });
    const part = fmt.formatToParts(new Date()).find((x) => x.type === "timeZoneName");
    name = part ? part.value : fmt.resolvedOptions().timeZone;
  } catch {
    // Older Safari throws a RangeError for "longGeneric": name the zone by its id.
    name = new Intl.DateTimeFormat("en-US", { timeZone }).resolvedOptions().timeZone;
  }
  return `Times shown in ${name}`;
}

export function whereLine(show) {
  return [show && show.venue, show && show.city].filter(Boolean).join(", ");
}

export function showHref(slug) {
  return `/show/${encodeURIComponent(slug)}.html`;
}

export function notesHref(slug) {
  return `/notes/${encodeURIComponent(slug)}.json`;
}
