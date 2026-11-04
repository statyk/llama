// Pure helpers for programs, block groups and the weekly lineup (unit-tested,
// no DOM). Kept apart from timeline.js so a cached old timeline.js beside a new
// page.js never fails to load for a missing export; this file only imports
// timeline.js's long-standing airTime.
import { airTime } from "./timeline.js";

const HOUSE_LINE = "LMA RADIO PRESENTS";
const DAYS = 7;
const HALF_DAY_MS = 12 * 3_600_000;

/** The program name when it is a non-blank string, else the house line. */
export function presentsLine(x) {
  const p = x && typeof x.program === "string" ? x.program.trim() : "";
  return p || HOUSE_LINE;
}

const nonEmpty = (v) => typeof v === "string" && v !== "";

/** Occurrence identity: the (block, nominal_start) pair, or null. */
export function occurrenceKey(block, nominalStart) {
  return nonEmpty(block) && nonEmpty(nominalStart) ? `${block}\u0000${nominalStart}` : null;
}

/** "7:00a – 9:56a", or "7:00a" when the end is unknown. */
export function blockSpan(entry, timeZone) {
  const from = airTime(entry.start, timeZone).time;
  return nonEmpty(entry.end) ? `${from} – ${airTime(entry.end, timeZone).time}` : from;
}

/** "YYYY-MM-DD" of the instant in the zone (default: the runtime's). */
export function localDateKey(ms, timeZone) {
  const fmt = new Intl.DateTimeFormat("en-US", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" });
  const p = {};
  for (const part of fmt.formatToParts(new Date(ms))) p[part.type] = part.value;
  return `${p.year}-${p.month}-${p.day}`;
}

/** Consecutive shows of one known occurrence share a group (with its title and
 * span); everything else falls into headless groups (null key, title, span). */
export function comingUpGroups(timeline, shows) {
  const blocks = timeline && Array.isArray(timeline.blocks) ? timeline.blocks : [];
  const byKey = new Map();
  for (const b of blocks) {
    const k = b && occurrenceKey(b.block, b.nominal_start);
    if (k && !byKey.has(k)) byKey.set(k, b);
  }
  const groups = [];
  for (const show of Array.isArray(shows) ? shows : []) {
    const k = occurrenceKey(show.block, show.nominal_start);
    const entry = k ? byKey.get(k) : null;
    const key = entry ? k : null;
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.shows.push(show);
    else groups.push({
      key, title: entry ? entry.title : null, span: entry ? blockSpan(entry) : null, shows: [show],
    });
  }
  return groups;
}

/** Seven listener-local days from today, each with its lineup entries; null for
 * a missing or malformed lineup. No zone arithmetic: day keys come from
 * formatting nowMs + k * 12 h, which cannot skip a day (a day lasts >= 23 h).
 * @param {any} lineup
 * @param {number} nowMs
 * @param {string} [timeZone]
 * @param {string | null} [onAir] an occurrence key from onAirKey
 * @returns {Array<{key: string, label: string, entries: Array<{key: string, title: string, time: string, variety: boolean}>}> | null} */
export function lineupDays(lineup, nowMs, timeZone, onAir = null) {
  if (!lineup || !Array.isArray(lineup.occurrences)) return null;
  /** @type {Array<{key: string, label: string, entries: Array<{key: string, title: string, time: string, variety: boolean}>}>} */
  const days = [];
  const seen = new Set();
  for (let k = 0; days.length < DAYS && k < DAYS * 4; k++) {
    const at = nowMs + k * HALF_DAY_MS;
    const key = localDateKey(at, timeZone);
    if (seen.has(key)) continue;
    seen.add(key);
    days.push({
      key,
      label: days.length === 0 ? "Today" : airTime(new Date(at).toISOString(), timeZone).day,
      entries: [],
    });
  }
  const byDay = new Map(days.map((d) => [d.key, d]));
  /** @type {Array<{ms: number, dayKey: string, entry: {key: string, title: string, time: string, variety: boolean}}>} */
  const items = [];
  const placed = new Set();
  for (const o of lineup.occurrences) {
    const ms = o ? Date.parse(o.nominal_start) : NaN;
    const key = o ? occurrenceKey(o.block, o.nominal_start) : null;
    if (!Number.isFinite(ms) || !key || placed.has(key)) continue;
    placed.add(key);
    items.push({
      ms, dayKey: localDateKey(ms, timeZone),
      entry: { key, title: o.title, time: airTime(o.nominal_start, timeZone).time, variety: Boolean(o.variety) },
    });
  }
  items.sort((a, b) => a.ms - b.ms);
  for (const it of items) {
    const day = byDay.get(it.dayKey);
    if (day) day.entries.push(it.entry);
  }
  if (onAir) {
    const it = items.find((x) => x.entry.key === onAir);
    if (it && it.dayKey < days[0].key) days[0].entries.unshift(it.entry);
  }
  return days;
}

/** The on-air show's occurrence key, or null (legacy show, nothing on air). */
export function onAirKey(timeline, atMs) {
  const shows = timeline && Array.isArray(timeline.shows) ? timeline.shows : [];
  for (const s of shows) {
    if (atMs >= Date.parse(s.start) && atMs < Date.parse(s.end)) return occurrenceKey(s.block, s.nominal_start);
  }
  return null;
}
