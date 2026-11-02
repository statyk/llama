// The player page's rendering: the label, the tape log, the tickets and the
// timeline fetch. Elements are built with createElement and textContent only;
// nothing here parses markup. Every link is built from the encoded slug.
import {
  STATION_NAME, airTime, comingUp, concertDate, findShow, justAired, nowLine, showHref,
  stoppedLine, tapeLog, tidyTitle, whereLine, zoneLabel,
} from "./timeline.js";

export const STATES = ["playing", "stopped", "reconnecting", "gaveup", "offair", "refused", "unsupported"];
const REFETCH_MS = 3 * 60_000;
const SHOWN = 6;
const LOG_WINDOW = 5; // rows of the tape log shown while collapsed
const LONG_NAME = 26; // characters past which the artist drops a size, then another
const LONGER_NAME = 34;
const FIXED_NOW = {
  reconnecting: "Reconnecting…",
  gaveup: "Lost the stream.",
  refused: "Playback was blocked.",
  unsupported: "This browser can't play the stream; open the stream URL in VLC.",
  offair: "The station is off the air.",
};

let state = "stopped";
let timeline = null;
let lastAttempt = null; // ms of the last fetch attempt
let lastAtMs = null;
let inFlight = false;
let showAll = false;
let logExpanded = false;
let logSlug = null; // the show the tape log is for; a change collapses it
const built = new Map(); // element id -> key of what it currently shows

const $ = (id) => document.getElementById(id);

function setText(id, text) {
  const el = $(id);
  if (el && el.textContent !== text) el.textContent = text;
}

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

/** The heading of the section holding `list`, hidden while the list is empty. */
function setHeadingHidden(list, hidden) {
  const section = list.closest("section, .tape-log");
  const heading = section && section.querySelector(".kick");
  if (heading) heading.hidden = hidden;
}

/** Replace `list`'s children with `rows` unless `key` says nothing changed. */
function rebuild(list, key, rows) {
  if (built.get(list.id) === key) return;
  built.set(list.id, key);
  list.replaceChildren(...rows());
}

function ticket(show, torn) {
  const when = airTime(show.start);
  const a = el("a", torn ? "ticket torn" : "ticket");
  a.dataset.slug = show.slug;
  a.href = showHref(show.slug);
  const stub = el("span", "stub");
  stub.append(el("span", "day", when.day), el("b", "time", when.time), el("span", "adm", "GEN ADM"));
  const main = el("span", "main");
  main.append(
    el("span", "presents", "LMA RADIO PRESENTS"),
    el("b", "artist", show.artist || ""),
    el("span", "where", whereLine(show)),
    el("span", "sr", concertDate(show.date)),
  );
  a.append(stub, main);
  return a;
}

function renderTickets(list, shows, torn) {
  const key = JSON.stringify([torn, shows.map((s) => [s.slug, s.start, s.artist, s.venue, s.city, s.date])]);
  rebuild(list, key, () => shows.map((s) => ticket(s, torn)));
  setHeadingHidden(list, shows.length === 0);
}

/** First index of the collapsed window: the now row with two before and two
 * after, slid to keep `size` rows when the tape has that many. No now: the first. */
function windowStart(entries, size) {
  const now = entries.findIndex((e) => e.state === "now");
  return Math.max(0, Math.min(now < 0 ? 0 : now - 2, entries.length - size));
}

function logToggle(list) {
  let more = $("tape-log-more");
  if (!more) {
    more = el("button", "more", "");
    more.id = "tape-log-more";
    more.type = "button";
    more.addEventListener("click", () => {
      logExpanded = !logExpanded;
      if (lastAtMs != null) renderLog(lastAtMs, onAirShow(lastAtMs));
    });
    list.after(more);
  }
  return more;
}

/** The show the page presents at atMs: none off air or with nothing on air. */
function onAirShow(atMs) {
  const np = findShow(timeline, atMs);
  return state !== "offair" && np ? np.show : null;
}

function renderLog(atMs, show) {
  const list = $("tape-log");
  if (!list) return;
  list.tabIndex = -1; // focus lands here when the button hides under the keyboard
  const slug = show ? show.slug : null;
  if (slug !== logSlug) {
    logSlug = slug;
    logExpanded = false;
  }
  const entries = show ? tapeLog(timeline, atMs) : [];
  const key = JSON.stringify(entries);
  rebuild(list, key, () => entries.map((e) => {
    const li = el("li", e.state);
    if (e.state === "now") li.setAttribute("aria-current", "true");
    const time = el("time", null, airTime(e.start).time);
    time.dateTime = e.start;
    li.append(el("span", null, tidyTitle(e.title)), time);
    return li;
  }));
  // Collapsing only toggles a class on the rows, so a toggle or a tick never rebuilds them.
  const collapsible = entries.length > LOG_WINDOW;
  const lo = windowStart(entries, LOG_WINDOW);
  Array.from(list.children).forEach((li, i) => {
    li.classList.toggle("off", collapsible && !logExpanded && (i < lo || i >= lo + LOG_WINDOW));
  });
  const more = logToggle(list);
  const hadFocus = more.hidden === false && document.activeElement === more;
  more.hidden = !collapsible;
  if (hadFocus && more.hidden) {
    list.focus();
  }
  const label = logExpanded ? "Show fewer" : `Show all ${entries.length} songs`;
  if (more.textContent !== label) more.textContent = label;
  const expanded = String(logExpanded);
  if (more.getAttribute("aria-expanded") !== expanded) more.setAttribute("aria-expanded", expanded);
  setHeadingHidden(list, entries.length === 0);
}

function renderSchedule(atMs) {
  const coming = comingUp(timeline, atMs);
  const list = $("coming-up");
  if (list) {
    renderTickets(list, showAll ? coming : coming.slice(0, SHOWN), false);
    let more = $("show-all");
    if (!more) {
      more = el("button", "more", "Show all");
      more.id = "show-all";
      more.type = "button";
      more.addEventListener("click", () => {
        showAll = true;
        if (lastAtMs != null) renderAt(lastAtMs);
      });
      list.after(more);
    }
    more.hidden = showAll || coming.length <= SHOWN;
  }
  const justList = $("just-aired");
  if (justList) renderTickets(justList, justAired(timeline, atMs, SHOWN), true);
  const note = $("schedule-note");
  if (note) {
    const text = !timeline ? "The schedule isn't available right now."
      : coming.length === 0 ? "Nothing further is scheduled yet." : "";
    note.textContent = text;
    note.hidden = text === "";
  }
}

/** The on-air show's notes link, touched only when the slug changes and hidden with none. */
function renderNotesLink(show) {
  const link = $("now-notes");
  const slug = (show && show.slug) || null;
  if (!link || built.get(link.id) === slug) return;
  built.set(link.id, slug);
  link.hidden = !slug;
  if (slug) {
    link.dataset.slug = slug;
    link.href = showHref(slug);
  } else {
    delete link.dataset.slug;
    link.removeAttribute("href");
  }
}

/** The show in full under Now playing: artist, venue and city, date. Hidden with no show on air. */
function renderNowShow(show) {
  const line = $("now-show");
  if (!line) return;
  const text = show
    ? [show.artist, whereLine(show), concertDate(show.date)].filter(Boolean).join(" \u00b7 ")
    : "";
  if (built.get(line.id) !== text) {
    built.set(line.id, text);
    line.textContent = text;
  }
  line.hidden = text === "";
}

/** The artist line, stepping the size down by name length; one line, whatever the name. */
function renderArtist(name) {
  const line = $("label-artist");
  if (!line || built.get(line.id) === name) return;
  built.set(line.id, name);
  line.textContent = name;
  line.title = name;
  line.classList.toggle("long", name.length > LONG_NAME && name.length <= LONGER_NAME);
  line.classList.toggle("longer", name.length > LONGER_NAME);
}

/** Alone writes #now and the label; also updates the tape log and both ticket lists. */
export function renderAt(atMs) {
  lastAtMs = atMs;
  const np = findShow(timeline, atMs);
  const offair = state === "offair";
  const show = onAirShow(atMs);
  renderArtist(show && show.artist ? show.artist : STATION_NAME);
  setText("label-where", show ? whereLine(show) : "");
  setText("label-date", show ? concertDate(show.date) : "");
  const status = $("label-status");
  if (status) status.hidden = offair;
  let now = FIXED_NOW[state];
  if (now == null) now = state === "playing" ? nowLine(np, STATION_NAME) : stoppedLine(np, STATION_NAME);
  setText("now", now);
  renderNowShow(show);
  renderNotesLink(show);
  setText("zone", zoneLabel());
  renderLog(atMs, show);
  renderSchedule(atMs);
}

export function setState(name) {
  if (!STATES.includes(name)) throw new Error(`unknown state: ${name}`);
  state = name;
  const retry = $("retry");
  if (retry) retry.hidden = !["gaveup", "offair", "refused"].includes(name);
  // A render error must never block Play or recovery, which call this first.
  try {
    renderAt(lastAtMs == null ? Date.now() : lastAtMs);
  } catch {
    // The next tick tries again.
  }
}

export function currentTimeline() {
  return timeline;
}

/** Fetch /timeline.json once the last attempt is 3 minutes old (or at once with
 * `force`), but never while stopped and hidden. A failure keeps the old timeline. */
export async function refreshTimeline(force) {
  const live = state === "playing" || state === "reconnecting" || !document.hidden;
  if (!live || inFlight) return;
  const now = Date.now();
  if (!force && lastAttempt != null && now - lastAttempt < REFETCH_MS) return;
  lastAttempt = now;
  inFlight = true;
  try {
    const res = await fetch("/timeline.json");
    if (!res.ok) throw new Error(`timeline ${res.status}`);
    const doc = await res.json();
    if (doc && Array.isArray(doc.shows)) timeline = doc;
  } catch {
    // keep the last timeline; the next attempt waits out the same 3 minutes
  } finally {
    inFlight = false;
  }
  if (lastAtMs != null) renderAt(lastAtMs);
}

/** One delegated click listener for the tickets and the on-air notes link: a plain
 * click calls onOpen(slug); modified clicks are left to the browser. */
export function ticketLinks(root, onOpen) {
  root.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target instanceof Element ? e.target.closest("a.ticket, a#now-notes") : null;
    if (!a || !root.contains(a) || !a.dataset.slug) return;
    e.preventDefault();
    onOpen(a.dataset.slug);
  });
}
