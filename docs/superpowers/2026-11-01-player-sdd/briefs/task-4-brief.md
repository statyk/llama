### Task 4: Pure recovery decisions

**Model hint:** opus.

**Files:**
- Create: `antenna/public/assets/recovery.js`
- Test: `antenna/test/recovery.test.ts`

**Interfaces:**
- Produces (consumed by Task 8):
  - `prefersNativeHls(nav, canPlayNative)`, `classifyProbe(status, body)`: copied from `nowplaying.js` unchanged.
  - `playBlockedNotice(err, stillPlaying)`: copied from `nowplaying.js`, with its text changed to "Playback was blocked."
  - `immediateOffair(data) -> boolean`: true for a 403 or `levelEmptyError`, as `hlsErrorNotice` tests.
  - `class Recovery` with injected time and randomness:
    - `constructor({ native, stallMs=15000, nativeStallMs=30000, joinMs=25000, minDelayMs=5000, maxDelayMs=30000, resetAfterMs=60000, giveUpMs=600000, probeEveryMs=15000, verdictFreshMs=10000, advanceSlackS=2, verdictsNeeded=2, random=Math.random })`
    - `begin(nowMs)`: the listener pressed Play
    - `tick(positionS, nowMs) -> "none" | "probe" | "restart" | "giveup"`
    - `failed(nowMs)`: a native `error` event; the failure counts at once
    - `noteWaiting()`: a `waiting` event arrived (never `stalled`: a healthy iPhone fires it every 11 s)
    - `verdict("offair" | "reachable" | "unreachable") -> boolean`: true means go off-air. `reachable` is an HTTP response that isn't off-air; `unreachable` is a rejected or timed-out fetch.
    - `restarted(nowMs)`: a restart was just performed
    - `mayPlay(nowMs) -> boolean`: the wall-clock check before any `play()`
    - `get stalled -> boolean`: the last sample didn't advance, or `noteWaiting` was called since the last advance
    - `get advancing -> boolean`: the last sample was a real advance. A rise above the wall-clock time since the previous sample plus `advanceSlackS` is a jump, not an advance, and re-baselines.
  - `pauseMeansStop({ selfTeardown, stalled, ended }) -> boolean`

- [ ] **Step 1: Write the failing tests,** each driving `tick` with a fake clock:

```ts
it("a position that keeps advancing never acts, even after a fatal hls.js error", ...);
it("a stall on hls.js waits the delay, probes, and restarts only after a reachable verdict", () => {
  const r = new Recovery({ native: false, random: () => 0.5 });
  r.begin(0);
  r.tick(1, 1000);
  expect(r.tick(1, 16000)).toBe("none");    // the failure; the delay runs to 21 s
  expect(r.tick(1, 21000)).toBe("probe");
  r.verdict("reachable");
  expect(r.tick(1, 21000)).toBe("restart");
});
it("offline for 8 minutes: only probes about every 15 s, never a restart", () => {
  // begin, stall; every "probe" answered verdict("unreachable"), ticking each second to 480 s.
  // Every result is "none" or "probe", probes at least probeEveryMs apart, none is "restart".
});
it("the network returning gives a restart within one probe interval", () => {
  // after the above, the next due "probe" answered verdict("reachable"): the next tick is "restart".
});
it("a reachable verdict goes stale: an old one gets a new probe, not a restart", () => {
  // verdict("reachable"), then the next tick comes more than verdictFreshMs later: "probe".
});
it("native waits nativeStallMs before anything", ...);       // 16 s none, 31 s failure, 36 s probe
it("a native error counts as a failure at once", ...);
it("delays between restarts run 5, 10, 20, 30, 30 s", ...);  // random 0.5 means no jitter; every probe reachable
it("the delay does not reset on brief progress", ...);       // 30 s of playback, then fail: delay still grows
it("the delay resets after 60 s of advancing playback", ...);
it("a retry gets joinMs to start before it counts as a failure", ...);
it("gives up at 10 minutes without audio, counted from the last advancing playback", ...);
it("frozen timers: the first tick after an hour gives up, not restarts", () => {
  const r = new Recovery({ native: true });
  r.begin(0);
  r.tick(5, 1000);
  expect(r.tick(5, 3_600_000)).toBe("giveup");
  expect(r.mayPlay(3_600_000)).toBe(false);
});
it("tick samples first: an advance after a long gap is not a give-up", () => {
  const r = new Recovery({ native: true });
  r.begin(0);
  r.tick(5, 1000);
  expect(r.tick(900, 3_600_000)).not.toBe("giveup");
});
it("two off-air verdicts reach off-air across a retry and other verdicts between them", () => {
  // probe, verdict reachable; restart; restarted(); probe, verdict offair; probe, verdict unreachable; probe, verdict offair -> true
});
it("an off-air verdict alone never restarts", ...);          // first offair: next tick is not "restart"
it("the first sample after a retry is a baseline, not progress", () => {
  // currentTime falls from 300 to 2 after a restart; offair count survives; no reset of the delay
});
it("a higher first sample after a retry is a baseline too", ...); // 300 to 310: same outcome
it("a jump after a restart is not progress", () => {
  // restarted(); baseline 0; 41 one second later: advancing false, delay and verdict count kept.
  // A position frozen at 41 with playing and a resolved play() stays a failure: nothing but samples counts.
});
it("real progress resets the verdict count", ...);
it("stalled: a sample that didn't advance, or noteWaiting since the last advance", () => {
  const r = new Recovery({ native: false });
  r.begin(0);
  r.tick(1, 1000);
  r.tick(2, 2000);
  expect(r.stalled).toBe(false);
  r.noteWaiting();
  expect(r.stalled).toBe(true);
  r.tick(3, 3000);
  expect(r.stalled).toBe(false);
  r.tick(3, 4000);
  expect(r.stalled).toBe(true);
});
it("repeated failed() during a delay or join neither shortens the delay nor queues a second restart", ...);
it("at most one probe at a time, spaced probeEveryMs", ...);
it("no restart until a probe has answered", ...);            // no verdict yet: "none"
it("noteWaiting alone never starts a probe", ...);           // position advancing: "none"
it("no restart while one is outstanding", ...);              // restart without restarted(): "none"
it("a hung probe does not block recovery", ...);             // Task 8 enforces the time limit; verdict("unreachable") is called on timeout
it("fast stream failure cannot loop faster than minDelayMs", ...); // Global spend rule
it("pauseMeansStop", () => {
  expect(pauseMeansStop({ selfTeardown: true, stalled: false, ended: false })).toBe(false);
  expect(pauseMeansStop({ selfTeardown: false, stalled: true, ended: false })).toBe(false);
  expect(pauseMeansStop({ selfTeardown: false, stalled: false, ended: true })).toBe(false);
  expect(pauseMeansStop({ selfTeardown: false, stalled: false, ended: false })).toBe(true);
});
it.each([
  [{ response: { code: 403 } }, true],
  [{ networkDetails: { status: 403 } }, true],
  [{ details: "levelEmptyError" }, true],
  [{ fatal: true, details: "manifestLoadError" }, false],
])("immediateOffair %j", (data, want) => {
  expect(immediateOffair(data)).toBe(want);
});
it("playBlockedNotice has the new text and still ignores an AbortError", () => {
  expect(playBlockedNotice({ name: "NotAllowedError" }, true)).toBe("Playback was blocked.");
  expect(playBlockedNotice({ name: "AbortError" }, true)).toBe(null);
});
```

  D1: `pause` does not fire in a dropout, and a Bluetooth disconnect is a `pause` with no stall, so the rule stands.

- [ ] **Step 2: Run** `cd antenna && npx vitest run test/recovery.test.ts`. Expected: FAIL.

- [ ] **Step 3: Implement.** Jitter is `delay * (0.8 + 0.4 * random())`. `lastAudioMs` is the time of the last advancing sample. The first position after `restarted`, higher or lower, sets the baseline without counting as progress. A failure starts the delay; when it runs out `tick` returns `"probe"`, and again every `probeEveryMs` until an answer allows more. `"restart"` needs a `reachable` verdict younger than `verdictFreshMs` and the delay run out: nothing else restarts. `unreachable` changes nothing but the time of the next probe; it never counts towards off-air or the delay. `tick` samples the position first, so an advance updates `lastAudioMs`, then returns `"giveup"` whenever `nowMs - lastAudioMs >= giveUpMs`; `mayPlay` applies the same test. `failed` is ignored while a delay or join is running. `pauseMeansStop` is false when `ended`.

- [ ] **Step 4: Run** the same command. Expected: PASS.

- [ ] **Step 5: Commit.** `antenna: recovery decisions as a pure tested module`.

---

