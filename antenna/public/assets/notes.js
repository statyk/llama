// The notes panel's model (pure, unit-tested). Same link rule as
// transmitter.site.archive_link: a literal https://archive.org/ prefix.
import { concertDate, tidyTitle, whereLine } from "./timeline.js";
import { presentsLine } from "./programs.js";

const ARCHIVE_PREFIX = "https://archive.org/";

export function archiveLink(url) {
  return typeof url === "string" && url.startsWith(ARCHIVE_PREFIX) ? url : null;
}

/** "Song" + segue -> "Song >"; a title that already ends in a mark is tidied. */
export function setlistLine({ title, segue }) {
  if (title == null || String(title).trim() === "") return "?";
  const t = tidyTitle(title);
  return segue && !t.endsWith(">") ? `${t} >` : t;
}

/** Consecutive entries with the same set label, in order. */
export function groupSets(setlist) {
  const groups = [];
  for (const entry of Array.isArray(setlist) ? setlist : []) {
    const last = groups[groups.length - 1];
    const line = setlistLine({ title: entry && entry.title, segue: entry && entry.segue });
    if (last && last.set === (entry && entry.set)) last.lines.push(line);
    else groups.push({ set: entry ? entry.set : undefined, lines: [line] });
  }
  return groups;
}

/** "ready" only for notes with a sections array; anything else is "old". */
export function panelModel(notes) {
  if (!notes || !Array.isArray(notes.sections)) return { kind: "old" };
  const text = (v) => (v == null ? "" : String(v));
  return {
    kind: "ready",
    presents: presentsLine(notes),
    sections: notes.sections,
    archive: archiveLink(notes.url),
    sets: groupSets(notes.setlist || []),
    artist: text(notes.artist),
    where: whereLine(notes),
    date: concertDate(notes.date),
    lineage: text(notes.lineage),
    airtimes: Array.isArray(notes.airtimes) ? notes.airtimes : [],
  };
}
