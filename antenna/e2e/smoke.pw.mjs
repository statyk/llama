import { expect, test } from "@playwright/test";
import { makeTimeline } from "./fixtures/timeline.mjs";
import { startServer } from "./serve.mjs";

let site;

test.beforeEach(async () => {
  site = await startServer({ timeline: makeTimeline(Date.now()) });
});
test.afterEach(async () => {
  await site.close();
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

test("the page's elements are all there for the behaviour to bind to", async ({ page }) => {
  await page.goto(site.url);
  for (const id of ["label-artist", "label-where", "label-date", "hubs", "play", "stop", "now", "retry",
                    "tape-log", "coming-up", "just-aired", "zone", "schedule-note", "stream-url", "audio"]) {
    await expect(page.locator(`#${id}`)).toHaveCount(1);
  }
  await expect(page.locator("#label-artist")).toHaveText("LMA Radio");
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
