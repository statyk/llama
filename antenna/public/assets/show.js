// The show page's air times, in the listener's zone. All else on the page is static.
import { airTime, notesHref, zoneLabel } from "./timeline.js";

const box = document.getElementById("airtimes");
const line = (text) => Object.assign(document.createElement("div"), { textContent: text });

function airLine({ start, end }) {
  const from = airTime(start);
  const to = airTime(end);
  return `${from.day} ${from.time} to ${to.day === from.day ? "" : `${to.day} `}${to.time}`;
}

async function show() {
  try {
    const res = await fetch(notesHref(box.dataset.slug));
    if (!res.ok) throw new Error(`notes: ${res.status}`);
    const times = ((await res.json()).airtimes || []).map(airLine);
    if (times.length === 0) {
      box.textContent = "Not currently scheduled.";
      return;
    }
    box.replaceChildren(...times.map(line));
    document.getElementById("zone").textContent = zoneLabel();
  } catch {
    box.textContent = "Airtimes unavailable.";
  }
}

show();
