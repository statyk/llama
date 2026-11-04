// The slide-up notes panel: a history entry on the same URL, over the player, so
// the audio keeps playing. Elements are built with createElement and textContent
// only. Every link is built from the encoded slug.
import { panelModel } from "./notes.js";
import { el } from "./page.js";
import { airLine, notesHref, showHref, zoneLabel } from "./timeline.js";

const close = el("button", "more", "Close");
close.type = "button";
const body = el("div");
const bar = el("div", "panel-bar");
bar.append(close);
const panel = el("div", "panel");
panel.setAttribute("role", "dialog");
panel.setAttribute("aria-label", "Show notes");
panel.append(bar, body);
document.body.append(panel);

let generation = 0; // bumped by each open and close, so a late answer is dropped
let closing = false;
let returnTo = null;

const isOpen = () => panel.classList.contains("open");

function newTabLink(className, text, href) {
  const a = el("a", className, text);
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener";
  return a;
}

/** The same wording as site._set_label: digits read "Set N", anything else capitalised. */
function setLabel(value) {
  const text = value == null ? "" : String(value).trim();
  return /^\d+$/.test(text) ? `Set ${text}` : text.charAt(0).toUpperCase() + text.slice(1);
}

function list(tag, lines) {
  const node = el(tag);
  node.append(...lines.map((line) => el("li", null, line)));
  return node;
}

function shareControl(slug) {
  const url = new URL(showHref(slug), location.href).href;
  const note = el("span", "share-note");
  note.setAttribute("role", "status");
  const button = el("button", "more", "Copy link to this show");
  button.type = "button";
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(url);
      note.textContent = "Link copied.";
    } catch {
      note.textContent = url; // no clipboard here: the listener can still select it
    }
  });
  const box = el("div");
  box.append(button, " ", note);
  return box;
}

function ticketView(slug, model) {
  const big = el("section", "bigt");
  const stub = el("div", "bstub");
  const dated = /^(.+) (\d{4})$/.exec(model.date);
  stub.append(dated ? dated[1] : model.date, el("b", "year", dated ? dated[2] : ""), "GEN ADM",
              el("br"), "LMA RADIO");
  const main = el("div", "bmain");
  main.append(el("span", "presents", model.presents ?? "LMA RADIO PRESENTS"), el("h2", null, model.artist || slug));
  if (model.where) main.append(el("div", "w", model.where));
  if (model.archive) main.append(newTabLink("btn", "Hear the full tape on archive.org ↗", model.archive));
  main.append(shareControl(slug));
  big.append(stub, main);
  return big;
}

function setlistCard(sets) {
  const card = el("div", "jcard");
  for (const { set, lines } of sets) {
    const label = sets.length > 1 ? setLabel(set) : "";
    if (label) card.append(el("p", "kick", label));
    card.append(list("ol", lines));
  }
  if (sets.length === 0) card.append(el("p", null, "No setlist."));
  return card;
}

function airBox(airtimes) {
  const box = el("div", "meta");
  box.append(el("b", "label", "On the air"));
  try {
    if (airtimes.length === 0) box.append(el("div", null, "Not currently scheduled."));
    else box.append(...airtimes.map((t) => el("div", null, airLine(t))), el("div", null, zoneLabel()));
  } catch {
    box.append(el("div", null, "Airtimes unavailable."));
  }
  return box;
}

function linerNotes(sections) {
  const liner = el("div", "liner");
  for (const section of sections) {
    if (section.heading) liner.append(el("h3", null, section.heading));
    for (const block of section.blocks || []) {
      if ("p" in block) liner.append(el("p", null, block.p));
      else if ("ul" in block) liner.append(list("ul", block.ul));
    }
  }
  if (!liner.firstChild) liner.append(el("p", null, "No notes yet."));
  return liner;
}

function notesView(slug, model) {
  const left = el("div");
  left.append(el("h2", "kick", "Setlist"), setlistCard(model.sets), airBox(model.airtimes));
  if (model.lineage) {
    const lineage = el("div", "meta");
    lineage.append(el("b", "label", "Taper's lineage"), el("br"), model.lineage);
    left.append(lineage);
  }
  const right = el("div");
  right.append(el("h2", "kick", "Liner notes"), linerNotes(model.sections));
  const cols = el("div", "cols");
  cols.append(left, right);
  return [ticketView(slug, model), cols,
          el("p", "fineprint", "Show notes are AI generated and may contain mistakes.")];
}

const showPageLink = (slug) => [newTabLink(null, "Open the show page", showHref(slug))];

async function load(slug, mine) {
  let nodes;
  try {
    const res = await fetch(notesHref(slug));
    if (!res.ok) throw new Error(`notes: ${res.status}`);
    const model = panelModel(await res.json());
    nodes = model.kind === "ready" ? notesView(slug, model) : showPageLink(slug);
  } catch {
    nodes = showPageLink(slug);
  }
  if (mine === generation) body.replaceChildren(...nodes);
}

export function openPanel(slug) {
  if (isOpen()) {
    history.replaceState({ panel: slug }, "");
  } else {
    returnTo = document.activeElement;
    history.pushState({ panel: slug }, "");
    panel.classList.add("open");
    close.focus({ preventScroll: true });
  }
  panel.scrollTop = 0;
  body.replaceChildren(el("p", null, "Loading…"));
  load(slug, ++generation);
}

/** Back through the panel's entry; popstate does the closing. */
function requestClose() {
  if (closing) return;
  closing = true;
  history.back();
}

close.addEventListener("click", requestClose);

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && isOpen()) requestClose();
});

window.addEventListener("popstate", () => {
  if (!isOpen()) return;
  generation++;
  closing = false;
  panel.classList.remove("open");
  if (returnTo) returnTo.focus();
  returnTo = null;
});
