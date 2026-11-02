import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { makeTimeline } from "./fixtures/timeline.mjs";
import { startServer } from "./serve.mjs";

const fixture = (name) => JSON.parse(readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8"));
const HOSTILE = fixture("hostile");
const NOTES = { full: fixture("notes-full"), old: fixture("notes-old"), empty: fixture("notes-empty") };
const ALLOWED = /^\/(assets\/[^?#]*|timeline\.json|live\.m3u8|notes\/[^?#]*|seg\/[^?#]*|show\/[^?#]*)?$/;
const SHOW_TEMPLATE = readFileSync(new URL("../templates/show.html", import.meta.url), "utf8");
const EXPECTED_STATUS = /Failed to load resource: (the server responded with a status of (403|404)|net::ERR_(EMPTY_RESPONSE|CONNECTION_RESET|FAILED))/;

let site;
let seen;
let consoleErrors;
let pageErrors;

test.beforeEach(async ({ context, page }) => {
  site = await startServer({ timeline: makeTimeline(Date.now()) });
  seen = [];
  consoleErrors = [];
  pageErrors = [];
  context.on("request", (r) => seen.push(r.url()));
  page.on("console", (m) => { if (m.type() === "error" && !EXPECTED_STATUS.test(m.text())) consoleErrors.push(m.text()); });
  page.on("pageerror", (e) => pageErrors.push(String(e)));
});
// After every test: only static paths with no query string, and a quiet console.
test.afterEach(async () => {
  const local = new URL(site.url).hostname;
  await site.close();
  // Every request the page made, to any host, across any server the test swapped in.
  const stray = seen.filter((u) => {
    if (u.startsWith("data:") || u.startsWith("blob:")) return false;
    const url = new URL(u);
    return url.hostname !== local || !ALLOWED.test(url.pathname + url.search) || (u.includes("?") && !url.search);
  });
  expect(stray).toEqual([]);
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});

/** A timeline whose shows keep their slugs but take the hostile document's text. */
function hostileTimeline() {
  const t = makeTimeline(Date.now());
  t.shows = t.shows.map((s, i) => ({
    ...s,
    slug: i === 3 ? HOSTILE.slug : s.slug,
    artist: HOSTILE.artist, venue: HOSTILE.venue, city: HOSTILE.city, date: HOSTILE.date,
    page: HOSTILE.page, notes: HOSTILE.notes,
    files: s.files.map((f) => (f.kind === "track" ? { ...f, title: HOSTILE.title } : f)),
  }));
  return t;
}

/** The show template with its slug filled and every other placeholder blank. */
function showPage(slug) {
  const attr = slug.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll('"', "&quot;");
  return SHOW_TEMPLATE.replaceAll("$slug", attr).replace(/\$\w+/g, "");
}

async function openShowPage(page, notes, slug = "x") {
  await site.close();
  site = await startServer({ shows: { [slug]: showPage(slug) }, notes: notes ? { [slug]: notes } : {} });
  await page.goto(`${site.url}/show/${encodeURIComponent(slug)}.html`);
}

test.describe("show page air times", () => {
  test.use({ timezoneId: "America/New_York" });

  test("are written in the listener's zone, naming the end's day when it differs", async ({ page }) => {
    await openShowPage(page, { airtimes: [
      { start: "2026-10-31T04:26:00Z", end: "2026-10-31T05:53:00Z" },
      { start: "2026-11-01T03:30:00Z", end: "2026-11-01T04:30:00Z" },
    ] });
    await expect(page.locator("#airtimes > div")).toHaveText(["Sat 12:26a to 1:53a", "Sat 11:30p to Sun 12:30a"]);
    await expect(page.locator("#zone")).toHaveText("Times shown in Eastern Time");
  });

  test("say so when the show has none", async ({ page }) => {
    await openShowPage(page, { airtimes: [] });
    await expect(page.locator("#airtimes")).toHaveText("Not currently scheduled.");
    await expect(page.locator("#zone")).toBeEmpty();
  });

  test("say so when the notes can't be read", async ({ page }) => {
    await openShowPage(page, null);
    await expect(page.locator("#airtimes")).toHaveText("Airtimes unavailable.");
  });

  test("say so on a bad time, and the hostile slug fetches its own notes as text", async ({ page }) => {
    await openShowPage(page, { airtimes: [{ start: "<img src=x onerror=\"window.pwned=1\">", end: "x" }] }, HOSTILE.slug);
    await expect(page.locator("#airtimes")).toHaveText("Airtimes unavailable.");
    expect(site.requests).toContain(`/notes/${encodeURIComponent(HOSTILE.slug)}.json`);
    expect(await page.evaluate(() => window.pwned)).toBeUndefined();
  });
});

test("the page loads, shows the header line and every asset request succeeds", async ({ page }) => {
  const bad = [];
  page.on("response", (r) => { if (!r.ok()) bad.push(`${r.status()} ${r.url()}`); });
  page.on("requestfailed", (r) => bad.push(`failed ${r.url()}`));

  await page.goto(site.url, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);

  await expect(page.getByRole("heading", { name: "LMA Radio" })).toBeVisible();
  await expect(page.getByText("Live concert tapes from the Live Music Archive, around the clock.")).toBeVisible();
  await expect(page.locator("#play")).toHaveText("Play");
  await expect(page.locator("#stop")).toHaveText("Stop");
  expect(bad).toEqual([]);
  for (const path of ["/assets/radio.css", "/assets/app.js", "/assets/hls.min.js",
                      "/assets/fonts/caveat-latin-700-normal.woff2",
                      "/assets/fonts/special-elite-latin-400-normal.woff2",
                      "/assets/fonts/libre-baskerville-latin-700-normal.woff2"]) {
    expect(site.requests).toContain(path);
  }
});

test("the footer's archive.org link opens in a new tab so the music keeps playing", async ({ page }) => {
  await page.goto(site.url);
  const link = page.locator("footer a[href='https://archive.org/details/etree']");
  await expect(link).toHaveAttribute("target", "_blank");
  await expect(link).toHaveAttribute("rel", /noopener/);
});

test("an engine that throws on longGeneric still renders the page and Play still turns the hubs", async ({ page }) => {
  await page.addInitScript(() => {
    const Real = Intl.DateTimeFormat;
    Intl.DateTimeFormat = function (loc, opts) {
      if (opts && opts.timeZoneName === "longGeneric") throw new RangeError("longGeneric");
      return new Real(loc, opts);
    };
    Intl.DateTimeFormat.prototype = Real.prototype;
  });
  await page.goto(site.url);
  await expect(page.locator("#zone")).toHaveText(/^Times shown in .+/);
  await expect(page.locator("#label-artist")).toHaveText("On Air Band");
  await page.locator("#play").click();
  await expect(page.locator("#hubs")).toHaveClass(/turning/);
});

test("the page's elements are all there for the behaviour to bind to", async ({ page }) => {
  await page.goto(site.url);
  for (const id of ["label-artist", "label-where", "label-date", "hubs", "play", "stop", "now", "now-notes", "retry",
                    "tape-log", "coming-up", "just-aired", "zone", "schedule-note", "stream-url", "audio"]) {
    await expect(page.locator(`#${id}`)).toHaveCount(1);
  }
  await expect(page.locator("#retry")).toBeHidden();
});

test("the hubs spin only under .turning, and never with reduced motion", async ({ page }) => {
  const spinning = () => page.locator(".hub").first().evaluate((el) => getComputedStyle(el).animationName);
  await page.goto(site.url);
  expect(await spinning()).toBe("none");
  await page.evaluate(() => document.getElementById("hubs").classList.add("turning"));
  expect(await spinning()).toBe("spin");
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(await spinning()).toBe("none");
});

test("the fixture stream really plays, and setLive changes what /live.m3u8 answers", async ({ page }) => {
  await page.goto(site.url, { waitUntil: "networkidle" });
  await page.evaluate(() => {
    document.getElementById("play").addEventListener("click", () => {
      const audio = document.getElementById("audio");
      const hls = new window.Hls();
      hls.loadSource("/live.m3u8");
      hls.attachMedia(audio);
      audio.play();
    });
  });
  await page.click("#play");
  // A live stream starts part-way along its timeline, so position alone proves nothing.
  const position = () => page.locator("#audio").evaluate((a) => a.currentTime);
  await expect.poll(position, { timeout: 15_000 }).toBeGreaterThan(0);
  const started = await position();
  await expect.poll(position, { timeout: 15_000 }).toBeGreaterThan(started + 1);
  expect(await page.locator("#audio").evaluate((a) => a.paused)).toBe(false);
  expect(site.requests.some((r) => /^\/seg\/\d+\.aac$/.test(r))).toBe(true);

  const answer = (path) => fetch(site.url + path).then(async (r) => ({ status: r.status, text: await r.text() }));
  expect((await answer("/live.m3u8")).text).toContain("#EXT-X-PROGRAM-DATE-TIME:");
  expect((await answer("/live.m3u8")).text).not.toContain("#EXT-X-ENDLIST");
  site.setLive("endlist");
  expect((await answer("/live.m3u8")).text).toContain("#EXT-X-ENDLIST");
  site.setLive("404");
  expect((await answer("/live.m3u8")).status).toBe(404);
  site.setLive("403");
  expect((await answer("/live.m3u8")).status).toBe(403);
  site.setLive("live");
  expect((await answer("/live.m3u8")).status).toBe(200);
  expect(() => site.setLive("nonsense")).toThrow();
});

test("renders the label, tape log, coming up, just aired and zone line before Play", async ({ page }) => {
  await page.goto(site.url);
  await expect(page.locator("#label-artist")).toHaveText("On Air Band");
  await expect(page.locator("#label-where")).toHaveText("The Club, Chattanooga, TN");
  await expect(page.locator("#label-date")).toHaveText("Nov 1 2008");
  await expect(page.locator("#now")).toHaveText("On Air Band is on the air. Press Play.");
  await expect(page.locator("#tape-log li").first().locator("span")).toHaveText("Song 3");
  await expect(page.locator("#tape-log li").first().locator("time")).toHaveText(/^\d{1,2}:\d{2}[ap]$/);
  await expect(page.locator("#coming-up .ticket")).toHaveCount(3);
  await expect(page.locator("#just-aired .ticket.torn")).toHaveCount(2);
  await expect(page.locator("#coming-up .ticket").first().locator(".artist")).toHaveText("Next Band");
  await expect(page.locator("#coming-up .ticket").first().locator(".adm")).toHaveText("GEN ADM");
  await expect(page.locator("#coming-up .ticket").first().locator(".presents")).toHaveText("LMA RADIO PRESENTS");
  await expect(page.locator("#coming-up .ticket").first().locator(".where")).toHaveText("Coliseum, Richmond, VA");
  await expect(page.locator("#zone")).toHaveText(/^Times shown in .+/);
  await expect(page.locator("#schedule-note")).toBeHidden();
  await expect(page.locator("#stream-url")).toHaveText(`${site.url}/live.m3u8`);
  await expect(page.getByRole("heading", { name: "Tape log" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Just aired" })).toBeVisible();
});

test("every ticket link is /show/<encoded slug>.html, even when the fixture's page field is hostile", async ({ page }) => {
  await site.close();
  site = await startServer({ timeline: hostileTimeline() });
  await page.goto(site.url);
  const tickets = page.locator(".ticket");
  await expect(tickets).toHaveCount(5);
  const found = await tickets.evaluateAll((as) => as.map((a) => [a.dataset.slug, a.getAttribute("href")]));
  expect(found.length).toBe(5);
  for (const [slug, href] of found) expect(href).toBe(`/show/${encodeURIComponent(slug)}.html`);
  expect(found.map(([slug]) => slug)).toContain(HOSTILE.slug);
});

test("the hostile fixture through the label, log and tickets: its markup appears as literal text and adds no element", async ({ page }) => {
  const count = async () => page.evaluate(() => document.querySelectorAll("*").length);
  await page.goto(site.url);
  await expect(page.locator("#tape-log li")).not.toHaveCount(0);
  const benign = await count();

  await site.close();
  site = await startServer({ timeline: hostileTimeline() });
  await page.goto(site.url);
  await expect(page.locator("#label-artist")).toHaveText(HOSTILE.artist);
  await expect(page.locator("#label-where")).toHaveText(`${HOSTILE.venue}, ${HOSTILE.city}`);
  await expect(page.locator("#label-date")).toHaveText(HOSTILE.date);
  const tidy = HOSTILE.title.trim().replace(/\s*-*>\s*$/, " >");
  await expect(page.locator("#tape-log li span").first()).toHaveText(tidy);
  await expect(page.locator("#coming-up .ticket .artist").first()).toHaveText(HOSTILE.artist);
  await expect(page.locator("#coming-up .ticket .where").first()).toHaveText(`${HOSTILE.venue}, ${HOSTILE.city}`);
  await expect(page.locator("#coming-up .ticket .sr").first()).toHaveText(HOSTILE.date);
  expect(await count()).toBe(benign);
  expect(await page.locator("img, iframe, svg, main script, h1[onclick]").count()).toBe(0);
  expect(await page.evaluate(() => window.pwned)).toBeUndefined();
});

test("with an empty timeline, the schedule note is shown and the page does not throw", async ({ page }) => {
  await site.close();
  site = await startServer({ timeline: makeTimeline(Date.now(), { shows: [], recent: [] }) });
  await page.goto(site.url);
  await expect(page.locator("#schedule-note")).toHaveText("Nothing further is scheduled yet.");
  await expect(page.locator("#coming-up .ticket")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Tape log" })).toBeHidden();
  await expect(page.getByRole("heading", { name: "Just aired" })).toBeHidden();
  await expect(page.getByRole("heading", { name: "Coming up" })).toBeHidden();
  await expect(page.locator("#label-artist")).toHaveText("LMA Radio");

  await site.close();
  site = await startServer({});
  await page.goto(site.url);
  await expect(page.locator("#schedule-note")).toHaveText("The schedule isn't available right now.");
  await expect(page.locator("#now")).toHaveText("LMA Radio");
});

test("no request leaves the local host", async ({ page }) => {
  const outside = [];
  page.on("request", (r) => { if (!r.url().startsWith(site.url + "/") && !r.url().startsWith("data:")) outside.push(r.url()); });
  await page.goto(site.url, { waitUntil: "networkidle" });
  expect(outside).toEqual([]);
});

test("stopped and hidden (document.hidden forced): no timeline.json fetch over 10 mocked minutes", async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(document, "hidden", { get: () => true, configurable: true }));
  await page.clock.install({ time: Date.now() });
  await page.goto(site.url);
  await page.clock.runFor(10 * 60_000);
  expect(site.requests.filter((r) => r.startsWith("/timeline.json"))).toEqual([]);
});

test("visible: one fetch on load, the next only once 3 minutes have passed", async ({ page }) => {
  const fetches = () => site.requests.filter((r) => r.startsWith("/timeline.json")).length;
  await page.clock.install({ time: Date.now() });
  await page.goto(site.url);
  await expect.poll(fetches).toBe(1);
  await page.clock.runFor(2 * 60_000);
  expect(fetches()).toBe(1);
  await page.clock.runFor(61_000);
  await expect.poll(fetches).toBe(2);
});

test("a failed fetch waits out the same 3 minutes", async ({ page }) => {
  await site.close();
  site = await startServer({}); // /timeline.json answers 404
  const fetches = () => site.requests.filter((r) => r.startsWith("/timeline.json")).length;
  await page.clock.install({ time: Date.now() });
  await page.goto(site.url);
  await expect.poll(fetches).toBe(1);
  await page.clock.runFor(2 * 60_000);
  expect(fetches()).toBe(1);
  await page.clock.runFor(61_000);
  await expect.poll(fetches).toBe(2);
});

test("ON THE AIR is hidden in the offair state only", async ({ page }) => {
  await page.goto(site.url);
  const status = page.locator("#label-status");
  await expect(status).toBeVisible();
  for (const name of ["playing", "stopped", "reconnecting", "gaveup", "refused", "unsupported"]) {
    await page.evaluate(async (n) => (await import("/assets/page.js")).setState(n), name);
    await expect(status).toBeVisible();
  }
  await page.evaluate(async () => (await import("/assets/page.js")).setState("offair"));
  await expect(status).toBeHidden();
  await expect(page.locator("#now")).toHaveText("The station is off the air.");
  await expect(page.locator("#retry")).toBeVisible();
  await page.evaluate(async () => (await import("/assets/page.js")).setState("stopped"));
  await expect(status).toBeVisible();
  await expect(page.locator("#retry")).toBeHidden();
});

test("ticketLinks: a plain click opens in-page, a modified click is left to the browser", async ({ page }) => {
  await page.goto(site.url);
  await page.evaluate(async () => {
    const { ticketLinks } = await import("/assets/page.js");
    window.opened = [];
    ticketLinks(document.body, (slug) => window.opened.push(slug));
  });
  const ticket = page.locator("#just-aired .ticket").first();
  await ticket.click();
  expect(await page.evaluate(() => window.opened)).toEqual(["fixture-aired-1"]);
  expect(new URL(page.url()).pathname).toBe("/");
  await ticket.click({ modifiers: ["Shift"], trial: true });
  await page.evaluate(() => document.body.addEventListener("click", (e) => e.preventDefault(), { once: true }));
  await ticket.click({ modifiers: ["Shift"] });
  expect(await page.evaluate(() => window.opened)).toEqual(["fixture-aired-1"]);
});

test("Show all reveals the rest of coming up", async ({ page }) => {
  const t = makeTimeline(Date.now());
  const extra = Array.from({ length: 5 }, (_, i) => ({
    ...t.shows[5], slug: `more-${i}`, start: new Date(Date.parse(t.shows[5].end) + (i + 1) * 90 * 60_000).toISOString(),
    end: new Date(Date.parse(t.shows[5].end) + (i + 2) * 90 * 60_000).toISOString(),
  }));
  t.shows = [...t.shows, ...extra];
  await site.close();
  site = await startServer({ timeline: t });
  await page.goto(site.url);
  await expect(page.locator("#coming-up .ticket")).toHaveCount(6);
  await page.getByRole("button", { name: "Show all" }).click();
  await expect(page.locator("#coming-up .ticket")).toHaveCount(8);
  await expect(page.getByRole("button", { name: "Show all" })).toBeHidden();
});

// ---- The player, on the real HLS fixture ----

const liveRequests = () => site.requests.filter((r) => r === "/live.m3u8").length;
const timelineRequests = () => site.requests.filter((r) => r === "/timeline.json").length;
const position = (page) => page.locator("#audio").evaluate((a) => a.currentTime);
const audioSrc = (page) => page.locator("#audio").evaluate((a) => a.src);

/** Mocked time in one-second steps, so real fetches land between the page's ticks. */
async function advance(page, ms) {
  for (let t = 0; t < ms; t += 1000) {
    await page.clock.runFor(1000);
    await new Promise((resolve) => setTimeout(resolve, 3));
  }
}

/** Steps mocked time until `done()`, for at most `ms`; returns the mocked ms it took. */
async function advanceUntil(page, ms, done) {
  for (let t = 0; t < ms; t += 1000) {
    if (await done()) return t;
    await advance(page, 1000);
  }
  throw new Error(`not done after ${ms} ms of mocked time`);
}

/** Stops the page's clock, so nothing runs but what a test steps or an answer triggers. */
async function holdClock(page) {
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 100));
}

async function playToAudio(page) {
  await page.click("#play");
  await expect.poll(() => position(page), { timeout: 15_000 }).toBeGreaterThan(0);
  const started = await position(page);
  await expect.poll(() => position(page), { timeout: 15_000 }).toBeGreaterThan(started + 0.5);
}

/** Records the probes: the page's fetches of /live.m3u8. hls.js loads it by XHR. */
function countProbes(context) {
  const probes = [];
  context.on("request", (r) => { if (r.resourceType() === "fetch" && r.url().endsWith("/live.m3u8")) probes.push(r); });
  return probes;
}

/** Every render throws from here on; ticket clicks, which also use closest, are spared. */
async function breakRendering(page) {
  await page.evaluate(() => {
    const real = Element.prototype.closest;
    Element.prototype.closest = function (selector) {
      if (selector.startsWith("section")) throw new Error("planted render error");
      return real.call(this, selector);
    };
  });
}

test("a lasting render error leaves the loop's player tick running", async ({ page }) => {
  await page.goto(site.url);
  await playToAudio(page);
  await expect(page.locator("#hubs")).toHaveClass(/turning/);
  await breakRendering(page);
  await page.locator("#audio").evaluate((a) => { a.playbackRate = 0; });
  await expect(page.locator("#hubs")).not.toHaveClass(/turning/);
});

test("a lasting render error does not block Play", async ({ page }) => {
  await page.goto(site.url);
  await breakRendering(page);
  await playToAudio(page);
  await expect(page.locator("#hubs")).toHaveClass(/turning/);
});

test("Play gives audio (currentTime advances) and #hubs gets turning", async ({ page }) => {
  await page.goto(site.url);
  await expect(page.locator("#hubs")).not.toHaveClass(/turning/);
  await playToAudio(page);
  await expect(page.locator("#hubs")).toHaveClass(/turning/);
  await expect(page.locator("#now")).toHaveText("Song 3");
  expect(site.requests.some((r) => /^\/seg\/\d+\.aac$/.test(r))).toBe(true);
});

test("Now playing follows the playback position, not the wall clock", async ({ page }) => {
  await site.close();
  site = await startServer({ timeline: makeTimeline(Date.now()), pdtOffsetMs: -9 * 60_000 }); // Song 2's time
  await page.goto(site.url);
  await expect(page.locator("#tape-log li span").first()).toHaveText("Song 3");
  await playToAudio(page);
  await expect(page.locator("#now")).toHaveText("Song 2");
});

test("Stop silences the audio, stops the hubs and shows the stopped line", async ({ page }) => {
  await page.goto(site.url);
  await playToAudio(page);
  await expect(page.locator("#hubs")).toHaveClass(/turning/);
  await page.click("#stop");
  await expect(page.locator("#hubs")).not.toHaveClass(/turning/);
  await expect(page.locator("#now")).toHaveText("On Air Band is on the air. Press Play.");
  expect(await page.locator("#audio").evaluate((a) => a.paused && !a.hasAttribute("src"))).toBe(true);
  const segments = site.requests.length;
  await page.waitForTimeout(2500);
  expect(site.requests.length).toBe(segments);
  await expect(page.locator("#now")).toHaveText("On Air Band is on the air. Press Play.");
});

test("a stall, then recovery to playing with no key pressed", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto(site.url);
  await playToAudio(page);
  site.setLive("404");
  await expect(page.locator("#now")).toHaveText("Reconnecting…", { timeout: 60_000 });
  await expect(page.locator("#hubs")).not.toHaveClass(/turning/);
  site.setLive("live");
  await expect(page.locator("#now")).toHaveText("Song 3", { timeout: 60_000 });
  await expect(page.locator("#hubs")).toHaveClass(/turning/);
});

test("navigator.mediaSession.metadata.title is the song", async ({ page }) => {
  const metadata = () => page.evaluate(() => {
    const { title, artist, album, artwork } = navigator.mediaSession.metadata;
    return { title, artist, album, art: artwork.map((a) => new URL(a.src).pathname), state: navigator.mediaSession.playbackState };
  });
  await page.goto(site.url);
  await playToAudio(page);
  await expect.poll(metadata).toEqual({
    title: "Song 3", artist: "On Air Band", album: "The Club, Nov 1 2008",
    art: ["/assets/cassette-512.png"], state: "playing",
  });
  // Set only when the text changes.
  await page.evaluate(() => { window.held = navigator.mediaSession.metadata; });
  await page.waitForTimeout(2500);
  expect(await page.evaluate(() => window.held === navigator.mediaSession.metadata)).toBe(true);

  await page.click("#stop");
  await expect.poll(metadata).toEqual({ title: "LMA Radio", artist: "", album: "", art: ["/assets/cassette-512.png"], state: "paused" });
});

test('/live.m3u8 answering 404 shows "Reconnecting…", then a switch to 403 reaches the off-air notice', async ({ page }) => {
  await page.clock.install({ time: Date.now() });
  site.setLive("404");
  await page.goto(site.url);
  await page.click("#play");
  await advanceUntil(page, 30_000, async () => (await page.locator("#now").textContent()) === "Reconnecting…");
  site.setLive("403");
  await advanceUntil(page, 90_000, async () => (await page.locator("#now").textContent()) === "The station is off the air.");
  await expect(page.locator("#retry")).toBeVisible();
  await expect(page.locator("#label-artist")).toHaveText("LMA Radio");
  expect(await page.locator("#audio").evaluate((a) => a.paused && !a.hasAttribute("src"))).toBe(true);
});

test("Stop during a retry delay: no further /live.m3u8 request after a further 40 s of mocked time", async ({ page }) => {
  await page.clock.install({ time: Date.now() });
  site.setLive("404");
  await page.goto(site.url);
  await page.click("#play");
  await advance(page, 16_000); // the failure has counted; the delay runs at least 4 s
  await page.click("#stop");
  const before = liveRequests();
  await advance(page, 40_000);
  expect(liveRequests()).toBe(before);
  expect(await page.locator("#audio").evaluate((a) => a.paused && !a.hasAttribute("src"))).toBe(true);
  await expect(page.locator("#now")).toHaveText("On Air Band is on the air. Press Play.");
});

test("Stop during a probe: its answer never restarts the audio", async ({ context, page }) => {
  const probes = countProbes(context);
  await page.clock.install({ time: Date.now() });
  site.setLive("404");
  let release;
  const held = new Promise((resolve) => { release = resolve; });
  await page.route("**/live.m3u8", async (route) => {
    if (route.request().resourceType() === "fetch") await held;
    await route.fallback();
  });
  await page.goto(site.url);
  await page.click("#play");
  await advanceUntil(page, 30_000, async () => probes.length === 1);
  await page.click("#stop");
  release();
  await advance(page, 40_000);
  expect(probes.length).toBe(1);
  expect(await page.locator("#audio").evaluate((a) => a.paused && !a.hasAttribute("src"))).toBe(true);
  await expect(page.locator("#now")).toHaveText("On Air Band is on the air. Press Play.");
});

test("/live.m3u8 unreachable during a stall: probes only, the src is untouched, then reachable gives a restart within one probe interval", async ({ context, page }) => {
  test.setTimeout(60_000);
  const probes = countProbes(context);
  await page.clock.install({ time: Date.now() });
  await page.goto(site.url);
  await playToAudio(page);
  site.setLive("drop");
  // The real buffer runs out in real time; the stall is then mocked.
  await expect.poll(() => page.locator("#audio").evaluate((a) => {
    const held = a.buffered.length ? a.buffered.end(a.buffered.length - 1) - a.currentTime : 0;
    return held < 0.5;
  }), { timeout: 30_000 }).toBe(true);
  const src = await audioSrc(page);
  expect(src).toMatch(/^blob:/);
  const segments = site.requests.filter((r) => r.startsWith("/seg/")).length;

  await advance(page, 90_000);
  expect(probes.length).toBeGreaterThanOrEqual(4);
  expect(probes.length).toBeLessThanOrEqual(6);
  await expect(page.locator("#now")).toHaveText("Reconnecting…");
  expect(await audioSrc(page)).toBe(src);
  expect(await page.locator("#audio").evaluate((a) => a.paused)).toBe(false);
  expect(site.requests.filter((r) => r.startsWith("/seg/")).length).toBe(segments);

  // An iPhone gave `playing` with the position frozen: it proves nothing.
  await page.locator("#audio").evaluate((a) => a.dispatchEvent(new Event("playing")));
  await advance(page, 2000);
  await expect(page.locator("#now")).toHaveText("Reconnecting…");
  await expect(page.locator("#hubs")).not.toHaveClass(/turning/);

  site.setLive("live");
  await advanceUntil(page, 16_000, async () => (await audioSrc(page)) !== src);
  await expect.poll(() => position(page), { timeout: 15_000 }).toBeGreaterThan(0);
  await advanceUntil(page, 30_000, async () => (await page.locator("#now").textContent()) === "Song 3");
  await expect(page.locator("#hubs")).toHaveClass(/turning/);
});

test("the stream reachable again, one probe failing does not end recovery: the next probe's answer restarts at once", async ({ context, page }) => {
  const probes = countProbes(context);
  await page.clock.install({ time: Date.now() });
  site.setLive("drop");
  await page.goto(site.url);
  await page.click("#play");
  await holdClock(page);
  await advanceUntil(page, 45_000, async () => probes.length === 2); // both unreachable
  const src = await audioSrc(page);

  site.setLive("live");
  let seen = 0;
  let release;
  const held = new Promise((resolve) => { release = resolve; });
  await page.route("**/live.m3u8", async (route) => {
    if (route.request().resourceType() !== "fetch") return route.fallback();
    seen += 1;
    if (seen === 1) return route.abort();
    await held;
    return route.fallback();
  });
  await advanceUntil(page, 16_000, async () => seen === 1);
  await advance(page, 5000);
  expect(await audioSrc(page)).toBe(src); // that failure restarted nothing
  await expect(page.locator("#now")).toHaveText("Reconnecting…");
  await advanceUntil(page, 16_000, async () => seen === 2);
  release();
  // The clock is held, so no tick can do this: the verdict itself restarts.
  await expect.poll(() => audioSrc(page)).not.toBe(src);
});

test('a 10-minute silence shows "Lost the stream." and Try again', async ({ page }) => {
  test.setTimeout(60_000);
  await page.clock.install({ time: Date.now() });
  site.setLive("drop");
  await page.goto(site.url);
  await page.click("#play");
  await advance(page, 9 * 60_000);
  await expect(page.locator("#now")).toHaveText("Reconnecting…");
  await advanceUntil(page, 62_000, async () => (await page.locator("#now").textContent()) === "Lost the stream.");
  await expect(page.locator("#retry")).toBeVisible();
  expect(await page.locator("#audio").evaluate((a) => a.paused && !a.hasAttribute("src"))).toBe(true);
  const before = liveRequests();
  await advance(page, 60_000);
  expect(liveRequests()).toBe(before);
  await expect(page.locator("#now")).toHaveText("Lost the stream.");

  site.setLive("live");
  await page.click("#retry");
  await expect(page.locator("#retry")).toBeHidden();
  await expect.poll(() => position(page), { timeout: 15_000 }).toBeGreaterThan(0);
  await advanceUntil(page, 30_000, async () => (await page.locator("#hubs").getAttribute("class")).includes("turning"));
});

test("over 10 mocked minutes of 404: at most 60 /live.m3u8 requests and at most 4 /timeline.json requests", async ({ page }) => {
  test.setTimeout(60_000);
  await page.clock.install({ time: Date.now() });
  site.setLive("404");
  await page.goto(site.url);
  await page.click("#play");
  await advance(page, 10 * 60_000);
  await expect(page.locator("#now")).toHaveText("Lost the stream.");
  expect(liveRequests()).toBeGreaterThan(10);
  expect(liveRequests()).toBeLessThanOrEqual(60);
  expect(timelineRequests()).toBeLessThanOrEqual(4);
});

test("Media Session: play, pause and stop only; play after a hidden Stop fetches the timeline, the force alone does not", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(document, "hidden", { get: () => true, configurable: true });
    window.actions = {};
    const session = navigator.mediaSession;
    session.setActionHandler = (name, handler) => { window.actions[name] = handler; };
  });
  await page.clock.install({ time: Date.now() });
  await page.goto(site.url);
  await holdClock(page); // no tick: only the handler itself can fetch
  expect((await page.evaluate(() => Object.keys(window.actions))).sort()).toEqual(["pause", "play", "stop"]);

  await page.evaluate(async () => (await import("/assets/page.js")).refreshTimeline(true));
  await page.waitForTimeout(300);
  expect(timelineRequests()).toBe(0);

  await page.evaluate(() => window.actions.play());
  await expect.poll(timelineRequests).toBe(1);
  await page.evaluate(() => window.actions.pause());
  await expect(page.locator("#hubs")).not.toHaveClass(/turning/);
  expect(await page.locator("#audio").evaluate((a) => !a.hasAttribute("src"))).toBe(true);
});

test("a pause from the phone is a Stop, and it stays stopped", async ({ page }) => {
  await page.goto(site.url);
  await playToAudio(page);
  await expect(page.locator("#hubs")).toHaveClass(/turning/); // past the join: no stall under way
  await page.locator("#audio").evaluate((a) => a.pause());
  await expect(page.locator("#now")).toHaveText("On Air Band is on the air. Press Play.");
  const before = site.requests.length;
  await page.waitForTimeout(2500);
  expect(site.requests.length).toBe(before);
  expect(await page.locator("#audio").evaluate((a) => a.paused && !a.hasAttribute("src"))).toBe(true);
});

test("a playlist that ends goes straight to the off-air notice", async ({ page }) => {
  site.setLive("endlist");
  await page.goto(site.url);
  await page.click("#play");
  await expect(page.locator("#now")).toHaveText("The station is off the air.");
  await expect(page.locator("#retry")).toBeVisible();
  await page.click("#stop");
  await expect(page.locator("#now")).toHaveText("The station is off the air.");
  await expect(page.locator("#retry")).toBeVisible();
});

test("a refused play() shows the notice; any other rejection is left to the stall path", async ({ page }) => {
  await page.goto(site.url);
  await page.evaluate(() => {
    window.rejection = "AbortError";
    HTMLMediaElement.prototype.play = () => Promise.reject(new DOMException("no", window.rejection));
  });
  await page.click("#play");
  await page.waitForTimeout(300);
  await expect(page.locator("#retry")).toBeHidden();
  await page.evaluate(() => { window.rejection = "NotAllowedError"; });
  await page.click("#play");
  await expect(page.locator("#now")).toHaveText("Playback was blocked.");
  await expect(page.locator("#retry")).toBeVisible();
});

test("Play during a dropout, key or Media Session: a probe goes out, the src is untouched and the audio carries on", async ({ context, page }) => {
  const probes = countProbes(context);
  await page.addInitScript(() => {
    window.actions = {};
    navigator.mediaSession.setActionHandler = (name, handler) => { window.actions[name] = handler; };
  });
  await page.goto(site.url);
  await playToAudio(page);
  await expect(page.locator("#hubs")).toHaveClass(/turning/);
  const src = await audioSrc(page);
  site.setLive("drop");

  const failed = page.waitForEvent("requestfailed", (r) => r.resourceType() === "fetch");
  await page.click("#play");
  await failed; // that question is over, so the next press asks again
  expect(probes.length).toBe(1);
  await page.evaluate(() => window.actions.play());
  await expect.poll(() => probes.length).toBe(2);
  await page.waitForTimeout(300);
  expect(await audioSrc(page)).toBe(src);
  const held = await position(page);
  await expect.poll(() => position(page)).toBeGreaterThan(held);
  await expect(page.locator("#hubs")).toHaveClass(/turning/);
});

test("Play during a stall, once /live.m3u8 answers: rejoins at once, not at the next probe", async ({ context, page }) => {
  const probes = countProbes(context);
  await page.clock.install({ time: Date.now() });
  site.setLive("drop");
  await page.goto(site.url);
  await page.click("#play");
  await holdClock(page);
  await advanceUntil(page, 30_000, async () => probes.length === 1);
  const src = await audioSrc(page);
  site.setLive("live");
  await page.click("#play");
  // The clock is held: no tick and no probe interval can do this.
  await expect.poll(() => audioSrc(page)).not.toBe(src);
  await expect(page.locator("#now")).toHaveText("Song 3");
});

test("Play with an off-air answer still rejoins, and the hubs stop until the position advances", async ({ page }) => {
  await page.clock.install({ time: Date.now() });
  await page.goto(site.url);
  await playToAudio(page);
  await expect(page.locator("#hubs")).toHaveClass(/turning/);
  const src = await audioSrc(page);
  await page.route("**/live.m3u8", (route) => (route.request().resourceType() === "fetch"
    ? route.fulfill({ status: 403, body: "403" }) : route.fallback()));
  await holdClock(page);
  await page.click("#play");
  await expect.poll(() => audioSrc(page)).not.toBe(src);
  await expect(page.locator("#hubs")).not.toHaveClass(/turning/);
});

test("Stop during Play's question stays stopped, and a second press adds nothing", async ({ context, page }) => {
  const probes = countProbes(context);
  await page.goto(site.url);
  await playToAudio(page);
  let release;
  const held = new Promise((resolve) => { release = resolve; });
  await page.route("**/live.m3u8", async (route) => {
    if (route.request().resourceType() === "fetch") await held;
    await route.fallback();
  });
  await page.click("#play");
  await page.click("#play");
  await expect.poll(() => probes.length).toBe(1);
  await page.waitForTimeout(300);
  expect(probes.length).toBe(1);
  await page.click("#stop");
  const before = liveRequests();
  release();
  await page.waitForTimeout(1500);
  expect(liveRequests()).toBe(before + 1); // the answered question, and nothing after it
  expect(await page.locator("#audio").evaluate((a) => a.paused && !a.hasAttribute("src"))).toBe(true);
  await expect(page.locator("#now")).toHaveText("On Air Band is on the air. Press Play.");
});

test("a play() that never settles (home-screen app, hidden): no notice, no hubs, Reconnecting, and only a moving position gives playing", async ({ page }) => {
  await page.addInitScript(() => {
    window.realPlay = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = () => new Promise(() => {});
  });
  await page.clock.install({ time: Date.now() });
  await page.goto(site.url);
  await page.click("#play");
  const hubs = page.locator("#hubs");
  await advanceUntil(page, 30_000, async () => {
    expect(await hubs.getAttribute("class")).not.toContain("turning");
    return (await page.locator("#now").textContent()) === "Reconnecting…";
  });
  await expect(page.locator("#retry")).toBeHidden();
  // Measured: iOS itself fired `pause` on a stuck play(). One second on, the
  // teardown's hold is over and the first sample after the restart is a baseline,
  // so no stall reads yet: only `joining` keeps this pause from being a Stop.
  await advance(page, 1000);
  await page.locator("#audio").evaluate((a) => a.dispatchEvent(new Event("pause")));
  await advance(page, 1000);
  await expect(page.locator("#now")).toHaveText("Reconnecting…");
  expect(await audioSrc(page)).toMatch(/^blob:/);
  await advance(page, 40_000);
  await expect(page.locator("#now")).toHaveText("Reconnecting…");
  await expect(hubs).not.toHaveClass(/turning/);

  await page.locator("#audio").evaluate((a) => window.realPlay.call(a));
  await advanceUntil(page, 40_000, async () => (await page.locator("#now").textContent()) === "Song 3");
  await expect(hubs).toHaveClass(/turning/);
});

test.describe("the on-air notes link", () => {
  const SLUG = "fixture-on-air";
  const link = (page) => page.locator("#now-notes");

  test("carries the on-air show, stays while stopped, and is left alone between changes", async ({ page }) => {
    await page.goto(site.url);
    await expect(link(page)).toBeVisible();
    await expect(link(page)).toHaveText("Show notes");
    await expect(link(page)).toHaveAttribute("data-slug", SLUG);
    await expect(link(page)).toHaveAttribute("href", `/show/${SLUG}.html`);
    await expect(link(page).locator("xpath=ancestor::*[contains(@class,'playing')]")).toHaveCount(1);
    await page.evaluate(() => {
      window.linkWrites = 0;
      new MutationObserver((m) => { window.linkWrites += m.length; })
        .observe(document.getElementById("now-notes"), { attributes: true });
    });
    await page.waitForTimeout(2500);
    expect(await page.evaluate(() => window.linkWrites)).toBe(0);
  });

  test("its link is built from the encoded slug", async ({ page }) => {
    await site.close();
    site = await startServer({ timeline: makeTimeline(Date.now(), { onAir: { slug: HOSTILE.slug } }) });
    await page.goto(site.url);
    await expect(link(page)).toHaveAttribute("data-slug", HOSTILE.slug);
    await expect(link(page)).toHaveAttribute("href", `/show/${encodeURIComponent(HOSTILE.slug)}.html`);
  });

  test("a click opens the panel on that show and the audio keeps advancing", async ({ page }) => {
    await site.close();
    site = await startServer({ timeline: makeTimeline(Date.now()), notes: { [SLUG]: { ...NOTES.full, artist: "On Air Band" } } });
    await page.goto(site.url);
    await playToAudio(page);
    const before = page.url();
    await link(page).click();
    await expect(page.locator(".panel .bmain h2")).toHaveText("On Air Band");
    expect(page.url()).toBe(before);
    expect(await page.evaluate(() => history.state)).toEqual({ panel: SLUG });
    const held = await position(page);
    await expect.poll(() => position(page), { timeout: 15_000 }).toBeGreaterThan(held + 0.5);
    expect(await page.locator("#audio").evaluate((a) => a.paused)).toBe(false);
    await expect(page.locator("#hubs")).toHaveClass(/turning/);
    await page.keyboard.press("Escape");
    await expect(page.locator(".panel")).toBeHidden();
    await expect(link(page)).toBeFocused();
  });

  test("a modified click is left to the browser", async ({ page }) => {
    await page.goto(site.url);
    await page.evaluate(() => document.body.addEventListener("click", (e) => e.preventDefault(), { once: true }));
    await link(page).click({ modifiers: ["Shift"] });
    await page.waitForTimeout(200);
    await expect(page.locator(".panel")).toBeHidden();
    expect(await page.evaluate(() => history.state)).toBeNull();
  });

  test("is hidden with nothing on air", async ({ page }) => {
    await site.close();
    site = await startServer({ timeline: makeTimeline(Date.now(), { shows: [], recent: [] }) });
    await page.goto(site.url);
    await expect(page.locator("#schedule-note")).toHaveText("Nothing further is scheduled yet.");
    await expect(link(page)).toBeHidden();
    await expect(link(page)).not.toHaveAttribute("href", /./);
  });

  test("is hidden off the air, and back when the state clears", async ({ page }) => {
    await page.goto(site.url);
    await expect(link(page)).toBeVisible();
    await page.evaluate(async () => (await import("/assets/page.js")).setState("offair"));
    await expect(link(page)).toBeHidden();
    await page.evaluate(async () => (await import("/assets/page.js")).setState("stopped"));
    await expect(link(page)).toBeVisible();
    await expect(link(page)).toHaveAttribute("data-slug", SLUG);
  });

  test("follows when the on-air show changes", async ({ page }) => {
    await page.clock.install({ time: Date.now() });
    await page.goto(site.url);
    await expect(link(page)).toHaveAttribute("data-slug", SLUG);
    await page.clock.fastForward(75 * 60_000); // the fixture's show ends 70 minutes on
    await expect(link(page)).toHaveAttribute("data-slug", "fixture-next-1");
    await expect(link(page)).toHaveAttribute("href", "/show/fixture-next-1.html");
  });
});

test("at 320 px with a very long band name, main and panel do not scroll sideways", async ({ page }) => {
  const SLUG = "fixture-next-1";
  const LONG = "...And You Will Know Us By the Trail of Dead";
  const timeline = makeTimeline(Date.now(), { onAir: { artist: LONG } });
  timeline.shows = timeline.shows.map((s) => ({ ...s, artist: LONG }));
  await site.close();
  site = await startServer({ timeline, notes: { [SLUG]: { ...NOTES.full, artist: LONG } } });
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto(site.url);
  await expect(page.locator(".ticket").first()).toBeVisible();
  await expect(page.locator("#label-artist")).toHaveText(LONG);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  await page.locator(`.ticket[data-slug="${SLUG}"]`).first().click();
  await expect(page.locator(".panel .bmain h2")).toHaveText(LONG);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  expect(await page.evaluate(() => {
    const p = document.querySelector(".panel");
    return p.scrollWidth - p.clientWidth;
  })).toBeLessThanOrEqual(0);
});

test.describe("notes panel", () => {
  const SLUG = "fixture-next-1";
  const OTHER = "fixture-next-2";
  const panel = (page) => page.locator(".panel");
  const ticketFor = (page, slug) => page.locator(`.ticket[data-slug="${slug}"]`).first();

  async function openSite(page, notes, timeline = makeTimeline(Date.now())) {
    await site.close();
    site = await startServer({ timeline, notes });
    await page.goto(site.url);
    await expect(page.locator(".ticket").first()).toBeVisible();
  }

  /** A same-origin page behind the player, so a back past the player is visible in the URL. */
  async function openSiteBehindAnotherPage(page, notes) {
    await site.close();
    site = await startServer({ timeline: makeTimeline(Date.now()), notes });
    await page.goto(`${site.url}/timeline.json`);
    await page.goto(site.url);
    await expect(page.locator(".ticket").first()).toBeVisible();
  }

  test("a tap on a ticket opens the panel, leaves the URL unchanged, and adds no navigation", async ({ page }) => {
    await openSite(page, { [SLUG]: NOTES.full });
    const before = page.url();
    const documents = site.requests.filter((r) => r === "/").length;
    await expect(panel(page)).toBeHidden();

    await ticketFor(page, SLUG).click();
    await expect(panel(page)).toBeVisible();
    await expect(panel(page).locator(".bmain h2")).toHaveText("Next Band");
    expect(page.url()).toBe(before);
    expect(site.requests.filter((r) => r === "/").length).toBe(documents);
    expect(await page.evaluate(() => performance.getEntriesByType("navigation").length)).toBe(1);
    expect(await page.evaluate(() => history.state)).toEqual({ panel: SLUG });
  });

  test("shows a loading state at once, before the notes arrive", async ({ page }) => {
    let release;
    const held = new Promise((resolve) => { release = resolve; });
    await page.route(`**/notes/${SLUG}.json`, async (route) => { await held; await route.continue(); });
    await openSite(page, { [SLUG]: NOTES.full });
    await ticketFor(page, SLUG).click();
    await expect(panel(page)).toBeVisible();
    await expect(panel(page)).toContainText("Loading…");
    await expect(panel(page).locator(".bmain")).toHaveCount(0);
    release();
    await expect(panel(page).locator(".bmain h2")).toHaveText("Next Band");
    await expect(panel(page)).not.toContainText("Loading…");
  });

  test("the ready notes: ticket, setlist, liner notes, air times, lineage, disclaimer, archive and share", async ({ page }) => {
    await page.addInitScript(() => {
      window.copied = [];
      Object.defineProperty(navigator, "clipboard", {
        value: { writeText: async (text) => { window.copied.push(text); } },
      });
    });
    await openSite(page, { [SLUG]: NOTES.full });
    await ticketFor(page, SLUG).click();
    const p = panel(page);
    await expect(p.locator(".bstub")).toContainText("Nov 1");
    await expect(p.locator(".bstub .year")).toHaveText("1985");
    await expect(p.locator(".bstub")).toContainText("GEN ADM");
    await expect(p.locator(".bmain .presents")).toHaveText("LMA RADIO PRESENTS");
    await expect(p.locator(".bmain .w")).toHaveText("Coliseum, Richmond, VA");
    await expect(p.locator(".jcard .kick")).toHaveText(["Set 1", "Encore"]);
    await expect(p.locator(".jcard ol li")).toHaveText(["Opener >", "Second Song", "Closer >", "Last One"]);
    await expect(p.locator(".liner h3")).toHaveText("Set one");
    await expect(p.locator(".liner p")).toHaveText("A paragraph of liner notes.");
    await expect(p.locator(".liner ul li")).toHaveText(["First bullet", "Second bullet"]);
    await expect(p.locator(".meta").first()).toContainText("Times shown in");
    await expect(p.locator(".meta").nth(1)).toContainText("SBD > Cassette > DAT");
    await expect(p.locator(".fineprint")).toHaveText("Show notes are AI generated and may contain mistakes.");

    const archive = p.getByRole("link", { name: /Hear the full tape on archive\.org/ });
    await expect(archive).toHaveAttribute("href", NOTES.full.url);
    await expect(archive).toHaveAttribute("target", "_blank");
    await expect(archive).toHaveAttribute("rel", "noopener");
    await expect(p.locator('a[href="/"], a[href="./"]')).toHaveCount(0);
    await expect(p.locator("a")).toHaveCount(1);

    await p.getByRole("button", { name: "Copy link to this show" }).click();
    expect(await page.evaluate(() => window.copied)).toEqual([`${site.url}/show/${SLUG}.html`]);
    await expect(p.locator(".share-note")).toHaveText("Link copied.");
  });

  test("a share that can't reach the clipboard prints the link instead", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "clipboard", { value: { writeText: () => Promise.reject(new Error("denied")) } });
    });
    await openSite(page, { [SLUG]: NOTES.full });
    await ticketFor(page, SLUG).click();
    await panel(page).getByRole("button", { name: "Copy link to this show" }).click();
    await expect(panel(page).locator(".share-note")).toHaveText(`${site.url}/show/${SLUG}.html`);
  });

  test("sets are labelled only with more than one group, and a null set prints nothing", async ({ page }) => {
    await openSite(page, {
      [SLUG]: { ...NOTES.full, setlist: [{ set: null, title: "Alone" }, { title: "Absent" }] },
      [OTHER]: { ...NOTES.full, setlist: [{ set: "1", title: "Only set" }] },
    });
    await ticketFor(page, SLUG).click();
    await expect(panel(page).locator(".jcard ol li")).toHaveText(["Alone", "Absent"]);
    await expect(panel(page).locator(".jcard")).not.toContainText("null");
    await expect(panel(page).locator(".jcard")).not.toContainText("undefined");
    await expect(panel(page).locator(".jcard .kick")).toHaveCount(0);
    await ticketFor(page, OTHER).evaluate((a) => a.click());
    await expect(panel(page).locator(".jcard ol li")).toHaveText("Only set");
    await expect(panel(page).locator(".jcard .kick")).toHaveCount(0);
  });

  test("the back action closes the panel; the close control closes it; a second back leaves nothing stale", async ({ page }) => {
    await openSiteBehindAnotherPage(page, { [SLUG]: NOTES.full, [OTHER]: NOTES.full });
    const home = page.url();

    await ticketFor(page, SLUG).click();
    await expect(panel(page)).toBeVisible();
    await page.goBack();
    await expect(panel(page)).toBeHidden();
    expect(page.url()).toBe(home);

    await ticketFor(page, SLUG).click();
    await expect(panel(page)).toBeVisible();
    await panel(page).getByRole("button", { name: "Close" }).click();
    await expect(panel(page)).toBeHidden();
    expect(page.url()).toBe(home);

    // A second ticket while open replaces the entry, so one back still closes.
    await ticketFor(page, SLUG).click();
    await expect(panel(page).locator(".bmain h2")).toBeVisible();
    await ticketFor(page, OTHER).evaluate((a) => a.click());
    await page.goBack();
    await expect(panel(page)).toBeHidden();
    expect(page.url()).toBe(home);

    await page.goBack();
    await expect(page).toHaveURL(`${site.url}/timeline.json`);
  });

  test("Escape closes, a second close while one is pending is ignored, and focus goes in and back", async ({ page }) => {
    await openSiteBehindAnotherPage(page, { [SLUG]: NOTES.full });
    const home = page.url();
    const inPanel = () => page.evaluate(() => document.querySelector(".panel").contains(document.activeElement));
    const ticket = ticketFor(page, SLUG);

    await ticket.click();
    await expect(panel(page)).toBeVisible();
    expect(await inPanel()).toBe(true);
    await page.keyboard.press("Escape");
    await expect(panel(page)).toBeHidden();
    await expect(ticket).toBeFocused();

    await ticket.click();
    await expect(panel(page)).toBeVisible();
    await panel(page).getByRole("button", { name: "Close" }).evaluate((b) => { b.click(); b.click(); });
    await expect(panel(page)).toBeHidden();
    await expect(ticket).toBeFocused();
    await page.waitForTimeout(200);
    expect(page.url()).toBe(home);
  });

  test("a reload with the panel open does not reopen it, and the stale entry stays on the player", async ({ page }) => {
    await openSiteBehindAnotherPage(page, { [SLUG]: NOTES.full });
    const home = page.url();
    await ticketFor(page, SLUG).click();
    await expect(panel(page)).toBeVisible();
    await page.reload();
    await expect(page.locator(".ticket").first()).toBeVisible();
    await expect(panel(page)).toBeHidden();
    await page.goBack();
    await expect(panel(page)).toBeHidden();
    expect(page.url()).toBe(home);
  });

  test("two fast taps show only the second show's notes", async ({ page }) => {
    let release;
    const held = new Promise((resolve) => { release = resolve; });
    const firstBody = page.waitForResponse(`**/notes/${SLUG}.json`);
    await page.route(`**/notes/${SLUG}.json`, async (route) => { await held; await route.continue(); });
    await openSite(page, {
      [SLUG]: { ...NOTES.full, artist: "First Band" },
      [OTHER]: { ...NOTES.full, artist: "Second Band" },
    });
    await ticketFor(page, SLUG).click();
    await ticketFor(page, OTHER).evaluate((a) => a.click());
    await expect(panel(page).locator(".bmain h2")).toHaveText("Second Band");
    release();
    await (await firstBody).finished();
    await page.waitForTimeout(100);
    await expect(panel(page).locator(".bmain h2")).toHaveText("Second Band");
    await expect(panel(page)).not.toContainText("First Band");
  });

  test("notes arriving after the close leave the closed panel alone", async ({ page }) => {
    let release;
    const held = new Promise((resolve) => { release = resolve; });
    const late = page.waitForResponse(`**/notes/${SLUG}.json`);
    await page.route(`**/notes/${SLUG}.json`, async (route) => { await held; await route.continue(); });
    await openSite(page, { [SLUG]: NOTES.full });
    await ticketFor(page, SLUG).click();
    await page.goBack();
    await expect(panel(page)).toBeHidden();
    release();
    await (await late).finished();
    await page.waitForTimeout(100);
    await expect(panel(page)).toBeHidden();
    await expect(panel(page).locator(".bmain")).toHaveCount(0);
  });

  for (const [name, notes] of [["without sections", { [SLUG]: NOTES.old }], ["that fail to load", {}]]) {
    test(`notes ${name} show "Open the show page" with target=_blank`, async ({ page }) => {
      await openSite(page, notes);
      await ticketFor(page, SLUG).click();
      const link = panel(page).getByRole("link", { name: "Open the show page" });
      await expect(link).toHaveAttribute("href", `/show/${SLUG}.html`);
      await expect(link).toHaveAttribute("target", "_blank");
      await expect(panel(page).locator(".bmain")).toHaveCount(0);
    });
  }

  test('a ticket on empty sections reads "No notes yet."', async ({ page }) => {
    await openSite(page, { [SLUG]: NOTES.empty });
    await ticketFor(page, SLUG).click();
    const p = panel(page);
    await expect(p.locator(".liner")).toHaveText("No notes yet.");
    await expect(p.locator(".bmain h2")).toHaveText("Next Band");
    await expect(p.getByRole("link")).toHaveCount(0);
    await expect(p.locator(".bmain .w")).toHaveCount(0);
    await expect(p).toContainText("Not currently scheduled.");
    await expect(p).not.toContainText("null");
    await expect(p.locator(".meta")).toHaveCount(1);
  });

  test("a bad air time reads as unavailable and leaves the rest of the notes", async ({ page }) => {
    await openSite(page, { [SLUG]: { ...NOTES.full, airtimes: [{ start: "x", end: "x" }] } });
    await ticketFor(page, SLUG).click();
    await expect(panel(page)).toContainText("Airtimes unavailable.");
    await expect(panel(page).locator(".bmain h2")).toHaveText("Next Band");
  });

  test("the hostile fixture through the panel: its markup appears as literal text and adds no element", async ({ page }) => {
    const count = () => page.evaluate(() => document.querySelectorAll(".panel *").length);
    const setlist = [...HOSTILE.setlist, { set: "<i>Encore</i>", title: HOSTILE.title, segue: false }];
    await openSite(page, { [SLUG]: { ...NOTES.full, url: HOSTILE.url, airtimes: [] } });
    await ticketFor(page, SLUG).click();
    await expect(panel(page).locator(".bmain h2")).toBeVisible();
    const benign = await count();

    await openSite(page, { [HOSTILE.slug]: { ...HOSTILE, setlist } }, hostileTimeline());
    await page.locator("#coming-up .ticket").first().click();
    const p = panel(page);
    await expect(p.locator(".bmain h2")).toHaveText(HOSTILE.artist);
    await expect(p.locator(".bmain .w")).toHaveText(`${HOSTILE.venue}, ${HOSTILE.city}`);
    await expect(p.locator(".bstub")).toContainText(HOSTILE.date);
    await expect(p.locator(".jcard .kick")).toHaveText(["<b>Set 1</b>", "<i>Encore</i>"]);
    const tidy = (title) => title.trim().replace(/\s*-*>\s*$/, " >");
    await expect(p.locator(".jcard ol li")).toHaveText([
      `${HOSTILE.setlist[0].title} >`, HOSTILE.setlist[1].title, tidy(HOSTILE.setlist[2].title), tidy(HOSTILE.title),
    ]);
    await expect(p.locator(".liner h3")).toHaveText(HOSTILE.sections[0].heading);
    await expect(p.locator(".liner p")).toHaveText(HOSTILE.sections[0].blocks[0].p);
    await expect(p.locator(".liner ul li")).toHaveText(HOSTILE.sections[0].blocks[1].ul);
    await expect(p).toContainText(HOSTILE.lineage);
    expect(await count()).toBe(benign);
    await expect(p.locator("img, iframe, svg, script, [onclick], u, i, a")).toHaveCount(0);
    expect(await page.evaluate(() => window.pwned)).toBeUndefined();
  });
});
