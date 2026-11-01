import { describe, expect, it } from "vitest";
import * as frozen from "../public/nowplaying.js";
import { Recovery, classifyProbe, immediateOffair, pauseMeansStop, playBlockedNotice,
         prefersNativeHls } from "../public/assets/recovery.js";

type Options = Partial<{
  stallMs: number; nativeStallMs: number; joinMs: number; minDelayMs: number; maxDelayMs: number;
  resetAfterMs: number; giveUpMs: number; probeEveryMs: number; verdictFreshMs: number;
  advanceSlackS: number; verdictsNeeded: number; random: () => number;
}>;

/** random 0.5 means no jitter: 0.8 + 0.4 * 0.5 = 1. */
const hls = (options: Options = {}) => new Recovery({ native: false, random: () => 0.5, ...options });
const native = (options: Options = {}) => new Recovery({ native: true, random: () => 0.5, ...options });

/** From a fresh hls.js session to a performed first restart at 21 s. */
function firstRestart(r: Recovery): number {
  r.begin(0);
  r.tick(1, 1000);
  expect(r.tick(1, 16000)).toBe("none");
  expect(r.tick(1, 21000)).toBe("probe");
  r.verdict("reachable");
  expect(r.tick(1, 21000)).toBe("restart");
  r.restarted(21000);
  return 21000;
}

/** Plays a real advance every second, `seconds` times, from baseline `pos` at
 * `from`. Returns the last sample's time and position. */
function play(r: Recovery, from: number, seconds: number, pos = 100) {
  expect(r.tick(pos, from)).toBe("none");
  let t = from;
  for (let i = 1; i <= seconds; i++) {
    t = from + i * 1000;
    expect(r.tick(pos + i, t)).toBe("none");
  }
  return { t, pos: pos + seconds };
}

/** Ticks a frozen position every 500 ms until `want`; the time it came back. */
function tickUntil(r: Recovery, pos: number, from: number, want: string, limitMs = 120_000): number {
  for (let t = from; t <= from + limitMs; t += 500) {
    const result = r.tick(pos, t);
    if (result === want) return t;
    expect(result).toBe("none");
  }
  throw new Error(`no ${want} within ${limitMs} ms of ${from}`);
}

/** Runs out the stall from the last advance, then returns the delay that
 * followed it: the failure's tick to the first probe. */
function delayAfterStall(r: Recovery, pos: number, lastAdvance: number): number {
  const failedAt = lastAdvance + 15000;
  expect(r.tick(pos, failedAt)).toBe("none");
  return tickUntil(r, pos, failedAt, "probe") - failedAt;
}

/** Ticks every second, answering each probe `unreachable`. */
function offline(r: Recovery, from: number, to: number, pos = 1) {
  const results: string[] = [];
  const probes: number[] = [];
  for (let t = from; t <= to; t += 1000) {
    const result = r.tick(pos, t);
    results.push(result);
    if (result === "probe") {
      probes.push(t);
      expect(r.verdict("unreachable")).toBe(false);
      expect(r.tick(pos, t)).toBe("none");
    }
  }
  return { results, probes };
}

describe("Recovery: what counts as a failure", () => {
  it("a position that keeps advancing never acts, even after a fatal hls.js error", () => {
    const r = hls();
    const fatal = { fatal: true, details: "manifestLoadError" };
    r.begin(0);
    expect(immediateOffair(fatal)).toBe(false);
    for (let s = 1; s <= 120; s++) expect(r.tick(s, s * 1000)).toBe("none");
    expect(r.advancing).toBe(true);
    expect(r.stalled).toBe(false);
  });

  it("a stall on hls.js waits the delay, probes, and restarts only after a reachable verdict", () => {
    const r = new Recovery({ native: false, random: () => 0.5 });
    r.begin(0);
    r.tick(1, 1000);
    expect(r.tick(1, 16000)).toBe("none");
    expect(r.tick(1, 20999)).toBe("none");
    expect(r.tick(1, 21000)).toBe("probe");
    expect(r.tick(1, 21000)).toBe("none");
    expect(r.verdict("reachable")).toBe(false);
    expect(r.tick(1, 21000)).toBe("restart");
  });

  it("native waits nativeStallMs before anything", () => {
    const r = native();
    r.begin(0);
    r.tick(1, 1000);
    expect(r.tick(1, 16000)).toBe("none");
    expect(r.tick(1, 21000)).toBe("none");
    expect(r.tick(1, 31000)).toBe("none");
    expect(r.tick(1, 35999)).toBe("none");
    expect(r.tick(1, 36000)).toBe("probe");
  });

  it("a native error counts as a failure at once", () => {
    const r = native();
    r.begin(0);
    r.tick(1, 1000);
    r.tick(2, 2000);
    r.failed(3000);
    expect(r.tick(2, 7999)).toBe("none");
    expect(r.tick(2, 8000)).toBe("probe");
  });

  it("an advance cancels a failure: iOS recovers short stalls by itself", () => {
    const r = hls();
    r.begin(0);
    r.tick(1, 1000);
    expect(r.tick(1, 16000)).toBe("none");
    expect(r.tick(1.5, 17000)).toBe("none");
    expect(r.advancing).toBe(true);
    for (let s = 1; s <= 10; s++) expect(r.tick(1.5 + s, 17000 + s * 1000)).toBe("none");
  });

  it("a verdict from an earlier failure does not carry into the next one", () => {
    const r = hls({ stallMs: 1000, probeEveryMs: 5000 });
    r.begin(0);
    r.tick(1, 500);
    expect(r.tick(1, 1000)).toBe("none");
    expect(r.tick(1, 6000)).toBe("probe");
    r.verdict("reachable");
    expect(r.tick(2, 7000)).toBe("none");
    expect(r.advancing).toBe(true);
    expect(r.tick(2, 8000)).toBe("none");
    expect(r.tick(2, 13000)).toBe("probe");
  });

  it("noteWaiting alone never starts a probe", () => {
    const r = hls();
    r.begin(0);
    for (let s = 1; s <= 60; s++) {
      r.noteWaiting();
      expect(r.tick(s, s * 1000)).toBe("none");
    }
    r.noteWaiting();
    expect(r.tick(60, 61000)).toBe("none");
  });

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
});

describe("Recovery: the network", () => {
  it("offline for 8 minutes: only probes about every 15 s, never a restart", () => {
    const r = hls();
    r.begin(0);
    const { results, probes } = offline(r, 1000, 480_000);
    expect(results.filter((x) => x !== "none" && x !== "probe")).toEqual([]);
    expect(probes[0]).toBe(20000);
    expect(probes).toHaveLength(31);
    for (let i = 1; i < probes.length; i++) expect(probes[i] - probes[i - 1]).toBe(15000);
  });

  it("the network returning gives a restart within one probe interval", () => {
    const r = hls();
    r.begin(0);
    const { probes } = offline(r, 1000, 480_000);
    const due = probes[probes.length - 1] + 15000;
    expect(due - 480_000).toBeLessThanOrEqual(15000);
    expect(r.tick(1, due - 1000)).toBe("none");
    expect(r.tick(1, due)).toBe("probe");
    r.verdict("reachable");
    expect(r.tick(1, due)).toBe("restart");
  });

  it("unreachable leaves the delay alone: the restart after an outage backs off once", () => {
    const r = hls();
    r.begin(0);
    const { probes } = offline(r, 1000, 120_000);
    const due = probes[probes.length - 1] + 15000;
    expect(r.tick(1, due)).toBe("probe");
    r.verdict("reachable");
    expect(r.tick(1, due)).toBe("restart");
    r.restarted(due);
    r.tick(1, due + 1000);
    expect(r.tick(1, due + 25000)).toBe("none");
    expect(tickUntil(r, 1, due + 25000, "probe")).toBe(due + 35000);
  });

  it("a reachable verdict goes stale: an old one gets a new probe, not a restart", () => {
    const r = hls();
    r.begin(0);
    r.tick(1, 1000);
    r.tick(1, 16000);
    expect(r.tick(1, 21000)).toBe("probe");
    r.verdict("reachable");
    expect(r.tick(1, 31000)).toBe("none");
    expect(r.tick(1, 36000)).toBe("probe");
    r.verdict("reachable");
    expect(r.tick(1, 45999)).toBe("restart");
  });

  it("a reachable verdict exactly verdictFreshMs old is stale", () => {
    const r = hls({ probeEveryMs: 5000 });
    r.begin(0);
    r.tick(1, 1000);
    r.tick(1, 16000);
    expect(r.tick(1, 21000)).toBe("probe");
    r.verdict("reachable");
    expect(r.tick(1, 31000)).toBe("probe");
  });

  it("no restart until a probe has answered", () => {
    const r = hls();
    r.begin(0);
    r.tick(1, 1000);
    r.tick(1, 16000);
    expect(r.tick(1, 21000)).toBe("probe");
    for (let t = 22000; t <= 60000; t += 1000) expect(r.tick(1, t)).toBe("none");
  });

  it("at most one probe at a time, spaced probeEveryMs", () => {
    const r = hls();
    r.begin(0);
    r.tick(1, 1000);
    r.tick(1, 16000);
    expect(r.tick(1, 21000)).toBe("probe");
    expect(r.tick(1, 36000)).toBe("none");
    r.verdict("unreachable");
    expect(r.tick(1, 36000)).toBe("probe");
    r.verdict("unreachable");
    expect(r.tick(1, 50999)).toBe("none");
    expect(r.tick(1, 51000)).toBe("probe");
  });

  it("a hung probe does not block recovery", () => {
    const r = hls();
    r.begin(0);
    r.tick(1, 1000);
    r.tick(1, 16000);
    expect(r.tick(1, 21000)).toBe("probe");
    expect(r.tick(1, 29000)).toBe("none");
    r.verdict("unreachable");
    expect(r.tick(1, 36000)).toBe("probe");
    r.verdict("reachable");
    expect(r.tick(1, 36000)).toBe("restart");
  });

  it("no restart while one is outstanding", () => {
    const r = hls();
    r.begin(0);
    r.tick(1, 1000);
    r.tick(1, 16000);
    r.tick(1, 21000);
    r.verdict("reachable");
    expect(r.tick(1, 21000)).toBe("restart");
    expect(r.tick(1, 21000)).toBe("none");
    expect(r.tick(1, 22000)).toBe("none");
    expect(r.tick(1, 60000)).toBe("none");
    r.restarted(60000);
    expect(r.tick(1, 61000)).toBe("none");
  });
});

describe("Recovery: delays", () => {
  it("delays between restarts run 5, 10, 20, 30, 30 s", () => {
    const r = hls();
    r.begin(0);
    r.tick(1, 1000);
    let failedAt = 16000;
    expect(r.tick(1, failedAt)).toBe("none");
    const delays = [];
    for (let i = 0; i < 5; i++) {
      const probeAt = tickUntil(r, 1, failedAt, "probe");
      delays.push(probeAt - failedAt);
      r.verdict("reachable");
      expect(r.tick(1, probeAt)).toBe("restart");
      r.restarted(probeAt);
      r.tick(1, probeAt + 1000);
      failedAt = probeAt + 25000;
      expect(r.tick(1, failedAt)).toBe("none");
    }
    expect(delays).toEqual([5000, 10000, 20000, 30000, 30000]);
  });

  it.each([
    [0, 4000],
    [1, 6000],
  ])("jitter: random %d makes the first delay %d ms", (random, want) => {
    const r = hls({ random: () => random });
    r.begin(0);
    r.tick(1, 1000);
    r.tick(1, 16000);
    expect(r.tick(1, 16000 + want - 1)).toBe("none");
    expect(r.tick(1, 16000 + want)).toBe("probe");
  });

  it("the delay does not reset on brief progress", () => {
    const r = hls();
    const first = firstRestart(r);
    const a = play(r, first + 1000, 30);
    expect(delayAfterStall(r, a.pos, a.t)).toBe(10000);
    r.verdict("reachable");
    const probeAt = a.t + 25000;
    expect(r.tick(a.pos, probeAt)).toBe("restart");
    r.restarted(probeAt);
    const b = play(r, probeAt + 1000, 30);
    expect(delayAfterStall(r, b.pos, b.t)).toBe(20000);
  });

  it("the delay resets after 60 s of advancing playback", () => {
    const r = hls();
    const first = firstRestart(r);
    const a = play(r, first + 1000, 61);
    expect(delayAfterStall(r, a.pos, a.t)).toBe(5000);
  });

  it("60 s of playback with a stall in the middle is not 60 s of advancing", () => {
    const r = hls();
    const first = firstRestart(r);
    const a = play(r, first + 1000, 40);
    expect(r.tick(a.pos, a.t + 1000)).toBe("none");
    const b = play(r, a.t + 2000, 40, a.pos);
    expect(delayAfterStall(r, b.pos, b.t)).toBe(10000);
  });

  it("a retry gets joinMs to start before it counts as a failure", () => {
    for (const r of [hls(), native()]) {
      const restartAt = 21000;
      r.begin(0);
      r.failed(16000);
      expect(r.tick(1, restartAt)).toBe("probe");
      r.verdict("reachable");
      expect(r.tick(1, restartAt)).toBe("restart");
      r.restarted(restartAt);
      for (let t = restartAt + 1000; t < restartAt + 25000; t += 1000) expect(r.tick(1, t)).toBe("none");
      expect(r.tick(1, restartAt + 25000)).toBe("none");
      expect(r.tick(1, restartAt + 34999)).toBe("none");
      expect(r.tick(1, restartAt + 35000)).toBe("probe");
    }
  });

  it("a real advance ends the join: from then on it's the ordinary stall rule", () => {
    const r = hls();
    const restartAt = firstRestart(r);
    r.tick(0, restartAt + 1000);
    r.tick(1, restartAt + 2000);
    r.failed(restartAt + 5000);
    expect(r.tick(1, restartAt + 14999)).toBe("none");
    expect(r.tick(1, restartAt + 15000)).toBe("probe");
  });

  it("repeated failed() during a delay or join neither shortens the delay nor queues a second restart", () => {
    const r = native();
    r.begin(0);
    r.tick(1, 1000);
    r.tick(2, 2000);
    r.failed(3000);
    r.failed(4000);
    r.failed(7000);
    expect(r.tick(2, 7999)).toBe("none");
    expect(r.tick(2, 8000)).toBe("probe");
    r.failed(8000);
    r.verdict("reachable");
    expect(r.tick(2, 8000)).toBe("restart");
    r.failed(8000);
    expect(r.tick(2, 8000)).toBe("none");
    r.restarted(8000);
    r.failed(9000);
    r.failed(20000);
    r.tick(2, 9000);
    expect(r.tick(2, 32999)).toBe("none");
    expect(r.tick(2, 33000)).toBe("none");
    expect(r.tick(2, 42999)).toBe("none");
    expect(r.tick(2, 43000)).toBe("probe");
  });

  it("fast stream failure cannot loop faster than minDelayMs", () => {
    const r = hls({ joinMs: 0, probeEveryMs: 1, random: () => 0 });
    r.begin(0);
    const restarts: number[] = [];
    for (let t = 0; t <= 300_000; t += 100) {
      r.failed(t);
      const result = r.tick(1, t);
      if (result === "probe") {
        r.verdict("reachable");
        expect(r.tick(1, t)).toBe("restart");
        r.restarted(t);
        restarts.push(t);
      }
    }
    expect(restarts.length).toBeGreaterThan(5);
    for (let i = 1; i < restarts.length; i++) {
      expect(restarts[i] - restarts[i - 1]).toBeGreaterThanOrEqual(5000);
    }
  });
});

describe("Recovery: giving up", () => {
  it("gives up at 10 minutes without audio, counted from the last advancing playback", () => {
    const r = hls();
    r.begin(0);
    const { t, pos } = play(r, 1000, 99, 1);
    expect(t).toBe(100_000);
    const { results } = offline(r, t + 1000, 699_000, pos);
    expect(results).not.toContain("giveup");
    expect(r.tick(pos, 699_999)).not.toBe("giveup");
    expect(r.mayPlay(699_999)).toBe(true);
    expect(r.tick(pos, 700_000)).toBe("giveup");
    expect(r.mayPlay(700_000)).toBe(false);
  });

  it("a retry doesn't move the give-up time", () => {
    const r = hls();
    r.begin(0);
    const { results, probes } = offline(r, 1000, 570_000);
    expect(results).not.toContain("giveup");
    const due = probes[probes.length - 1] + 15000;
    expect(r.tick(1, due)).toBe("probe");
    r.verdict("reachable");
    expect(r.tick(1, due)).toBe("restart");
    r.restarted(due);
    expect(r.mayPlay(599_999)).toBe(true);
    expect(r.tick(0, 599_000)).toBe("none");
    expect(r.tick(41, 599_500)).toBe("none");
    expect(r.tick(41, 600_000)).toBe("giveup");
  });

  it("the give-up check wins over a pending restart", () => {
    const r = hls({ verdictFreshMs: 20000 });
    r.begin(0);
    const { probes } = offline(r, 1000, 589_000);
    const due = probes[probes.length - 1] + 15000;
    expect(due).toBeLessThan(600_000);
    expect(r.tick(1, due)).toBe("probe");
    r.verdict("reachable");
    expect(r.tick(1, 600_000)).toBe("giveup");
  });

  it("the give-up check beats a restart that was asked for and not yet performed", () => {
    const r = hls();
    r.begin(0);
    r.tick(1, 1000);
    r.tick(1, 16000);
    r.tick(1, 21000);
    r.verdict("reachable");
    expect(r.tick(1, 21000)).toBe("restart");
    expect(r.tick(1, 600_000)).toBe("giveup");
  });

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
    expect(r.advancing).toBe(true);
    expect(r.mayPlay(3_600_000)).toBe(true);
  });

  it("begin starts a new session: the listener's Try again after a give-up", () => {
    const r = hls();
    r.begin(0);
    r.tick(1, 1000);
    expect(r.tick(1, 600_000)).toBe("giveup");
    r.begin(700_000);
    expect(r.mayPlay(700_000)).toBe(true);
    expect(r.tick(1, 701_000)).toBe("none");
    expect(r.tick(1, 715_000)).toBe("none");
    expect(tickUntil(r, 1, 715_000, "probe")).toBe(720_000);
  });
});

describe("Recovery: off-air", () => {
  it("two off-air verdicts reach off-air across a retry and other verdicts between them", () => {
    const r = hls();
    const restartAt = firstRestart(r);
    r.tick(1, restartAt + 1000);
    expect(r.tick(1, restartAt + 25000)).toBe("none");
    const probe1 = restartAt + 35000;
    expect(r.tick(1, probe1)).toBe("probe");
    expect(r.verdict("offair")).toBe(false);
    expect(r.tick(1, probe1 + 15000)).toBe("probe");
    expect(r.verdict("unreachable")).toBe(false);
    expect(r.tick(1, probe1 + 30000)).toBe("probe");
    expect(r.verdict("offair")).toBe(true);
  });

  it("verdictsNeeded off-air verdicts survive a reachable one and a restart between them", () => {
    const r = hls();
    r.begin(0);
    r.tick(1, 1000);
    r.tick(1, 16000);
    expect(r.tick(1, 21000)).toBe("probe");
    expect(r.verdict("offair")).toBe(false);
    expect(r.tick(1, 36000)).toBe("probe");
    expect(r.verdict("reachable")).toBe(false);
    expect(r.tick(1, 36000)).toBe("restart");
    r.restarted(36000);
    r.tick(1, 37000);
    r.tick(1, 61000);
    expect(r.tick(1, 71000)).toBe("probe");
    expect(r.verdict("offair")).toBe(true);
  });

  it("an off-air verdict alone never restarts", () => {
    const r = hls();
    r.begin(0);
    r.tick(1, 1000);
    r.tick(1, 16000);
    expect(r.tick(1, 21000)).toBe("probe");
    expect(r.verdict("offair")).toBe(false);
    expect(r.tick(1, 21000)).toBe("none");
    expect(r.tick(1, 36000)).toBe("probe");
  });

  it("the first sample after a retry is a baseline, not progress", () => {
    const r = hls();
    r.begin(0);
    r.tick(300, 1000);
    r.tick(300, 16000);
    expect(r.tick(300, 21000)).toBe("probe");
    r.verdict("offair");
    expect(r.tick(300, 36000)).toBe("probe");
    r.verdict("reachable");
    expect(r.tick(300, 36000)).toBe("restart");
    r.restarted(36000);
    expect(r.tick(2, 37000)).toBe("none");
    expect(r.advancing).toBe(false);
    expect(r.stalled).toBe(false);
    expect(r.tick(2, 61000)).toBe("none");
    expect(r.tick(2, 70999)).toBe("none");
    expect(r.tick(2, 71000)).toBe("probe");
    expect(r.verdict("offair")).toBe(true);
  });

  it("a higher first sample after a retry is a baseline too", () => {
    const r = hls();
    r.begin(0);
    r.tick(300, 1000);
    r.tick(300, 16000);
    expect(r.tick(300, 21000)).toBe("probe");
    r.verdict("offair");
    expect(r.tick(300, 36000)).toBe("probe");
    r.verdict("reachable");
    expect(r.tick(300, 36000)).toBe("restart");
    r.restarted(36000);
    expect(r.tick(310, 37000)).toBe("none");
    expect(r.advancing).toBe(false);
    expect(r.tick(310, 61000)).toBe("none");
    expect(r.tick(310, 70999)).toBe("none");
    expect(r.tick(310, 71000)).toBe("probe");
    expect(r.verdict("offair")).toBe(true);
  });

  it("a jump after a restart is not progress", () => {
    const r = hls();
    r.begin(0);
    r.tick(300, 1000);
    r.tick(300, 16000);
    expect(r.tick(300, 21000)).toBe("probe");
    r.verdict("offair");
    expect(r.tick(300, 36000)).toBe("probe");
    r.verdict("reachable");
    expect(r.tick(300, 36000)).toBe("restart");
    r.restarted(36000);
    expect(r.tick(0, 37000)).toBe("none");
    expect(r.advancing).toBe(false);
    expect(r.tick(41, 38000)).toBe("none");
    expect(r.advancing).toBe(false);
    for (let t = 39000; t <= 60000; t += 1000) {
      expect(r.tick(41, t)).toBe("none");
      expect(r.advancing).toBe(false);
    }
    expect(r.stalled).toBe(true);
    expect(r.tick(41, 61000)).toBe("none");
    expect(r.tick(41, 70999)).toBe("none");
    expect(r.tick(41, 71000)).toBe("probe");
    expect(r.verdict("offair")).toBe(true);
  });

  it("a rise of exactly wall clock plus advanceSlackS advances; anything above it is a jump", () => {
    const r = hls();
    r.begin(0);
    r.tick(10, 1000);
    r.tick(13, 2000);
    expect(r.advancing).toBe(true);
    r.tick(16.01, 3000);
    expect(r.advancing).toBe(false);
    r.tick(16.5, 4000);
    expect(r.advancing).toBe(true);
  });

  it("no rise is no advance", () => {
    const r = hls();
    r.begin(0);
    r.tick(10, 1000);
    r.tick(10, 2000);
    expect(r.advancing).toBe(false);
    r.tick(5, 3000);
    expect(r.advancing).toBe(false);
    expect(r.stalled).toBe(true);
  });

  it("real progress resets the verdict count", () => {
    const r = hls();
    r.begin(0);
    r.tick(1, 1000);
    r.tick(1, 16000);
    expect(r.tick(1, 21000)).toBe("probe");
    expect(r.verdict("offair")).toBe(false);
    const { t, pos } = play(r, 22000, 3, 1);
    expect(r.tick(pos, t + 15000)).toBe("none");
    const probeAt = tickUntil(r, pos, t + 15000, "probe");
    expect(r.verdict("offair")).toBe(false);
    expect(r.tick(pos, probeAt + 15000)).toBe("probe");
    expect(r.verdict("offair")).toBe(true);
  });
});

describe("pauseMeansStop", () => {
  it("pauseMeansStop", () => {
    expect(pauseMeansStop({ selfTeardown: true, stalled: false, ended: false })).toBe(false);
    expect(pauseMeansStop({ selfTeardown: false, stalled: true, ended: false })).toBe(false);
    expect(pauseMeansStop({ selfTeardown: false, stalled: false, ended: true })).toBe(false);
    expect(pauseMeansStop({ selfTeardown: false, stalled: false, ended: false })).toBe(true);
  });
});

describe("helpers", () => {
  it.each([
    [{ response: { code: 403 } }, true],
    [{ networkDetails: { status: 403 } }, true],
    [{ details: "levelEmptyError" }, true],
    [{ fatal: true, details: "manifestLoadError" }, false],
  ])("immediateOffair %j", (data, want) => {
    expect(immediateOffair(data)).toBe(want);
  });

  it("immediateOffair copes with no data", () => {
    expect(immediateOffair(undefined)).toBe(false);
  });

  it("playBlockedNotice has the new text and still ignores an AbortError", () => {
    expect(playBlockedNotice({ name: "NotAllowedError" }, true)).toBe("Playback was blocked.");
    expect(playBlockedNotice({ name: "AbortError" }, true)).toBe(null);
    expect(playBlockedNotice({ name: "NotAllowedError" }, false)).toBe(null);
  });

  it("prefersNativeHls and classifyProbe are the frozen file's, unchanged", () => {
    expect(prefersNativeHls.toString()).toBe(frozen.prefersNativeHls.toString());
    expect(classifyProbe.toString()).toBe(frozen.classifyProbe.toString());
    expect(prefersNativeHls({ vendor: "Apple Computer, Inc." }, true)).toBe(true);
    expect(prefersNativeHls({ vendor: "Google Inc." }, true)).toBe(false);
    expect(classifyProbe(403, "")).toBe("offair");
    expect(classifyProbe(200, "#EXT-X-ENDLIST")).toBe("offair");
    expect(classifyProbe(200, "#EXTM3U")).toBe("unknown");
    expect(classifyProbe(0, "")).toBe("unknown");
  });
});
