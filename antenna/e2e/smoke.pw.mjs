import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { makeTimeline } from "./fixtures/timeline.mjs";
import { startServer } from "./serve.mjs";

const HOSTILE = JSON.parse(readFileSync(new URL("./fixtures/hostile.json", import.meta.url), "utf8"));
const ALLOWED = /^\/(assets\/[^?#]*|timeline\.json|live\.m3u8|notes\/[^?#]*|seg\/[^?#]*)?$/;
const EXPECTED_STATUS = /Failed to load resource: the server responded with a status of (403|404)/;

let site;
let seen;
let consoleErrors;
let pageErrors;

test.beforeEach(async ({ page }) => {
  site = await startServer({ timeline: makeTimeline(Date.now()) });
  seen = [];
  consoleErrors = [];
  pageErrors = [];
  page.on("request", (r) => seen.push(r.url()));
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
    return url.hostname !== local || !ALLOWED.test(url.pathname + url.search);
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

test("the page's elements are all there for the behaviour to bind to", async ({ page }) => {
  await page.goto(site.url);
  for (const id of ["label-artist", "label-where", "label-date", "hubs", "play", "stop", "now", "retry",
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
