// Merges a show's struck (dropped) entries into the setlist card's groups. Pure; the
// same algorithm as transmitter's site._setlist_html. Kept entries group exactly as
// notes.groupSets does; a struck entry sits right after the kept entry whose 1-based
// index is its after_track (0: the very start, past the end: the end) and is never
// counted, so a kept item after a struck one in its group carries its kept ordinal.
import { setlistLine } from "./notes.js";
import { tidyTitle } from "./timeline.js";

function validDropped(raw) {
  if (!Array.isArray(raw)) return [];
  return raw.filter((e) => e !== null && typeof e === "object" && !Array.isArray(e)
    && typeof e.title === "string" && e.title !== ""
    && Number.isInteger(e.after_track) && e.after_track >= 0);
}

/** [{ set, items: [{ text, struck, value }] }]; value is a kept ordinal after a struck item, else null. */
export function mergeDropped(setlist, dropped) {
  const kept = Array.isArray(setlist) ? setlist : [];
  const struck = new Map();
  for (const e of validDropped(dropped)) {
    const at = Math.min(e.after_track, kept.length);
    if (!struck.has(at)) struck.set(at, []);
    struck.get(at).push({ text: tidyTitle(e.title), kept: false });
  }
  const groups = [];
  kept.forEach((entry, i) => {
    const index = i + 1;
    const set = entry ? entry.set : undefined;
    let group = groups[groups.length - 1];
    if (!group || group.set !== set) groups.push((group = { set, items: [] }));
    if (index === 1) group.items.push(...(struck.get(0) || []));
    group.items.push({ text: setlistLine({ title: entry && entry.title, segue: entry && entry.segue }), kept: true });
    group.items.push(...(struck.get(index) || []));
  });
  if (kept.length === 0 && struck.has(0)) groups.push({ set: undefined, items: struck.get(0) });
  return groups.map(({ set, items }) => {
    let ordinal = 0;
    let seenStruck = false;
    return {
      set,
      items: items.map((item) => {
        if (!item.kept) {
          seenStruck = true;
          return { text: item.text, struck: true, value: null };
        }
        ordinal += 1;
        return { text: item.text, struck: false, value: seenStruck ? ordinal : null };
      }),
    };
  });
}
