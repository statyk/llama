### Finding Verdicts

- **Important 1: a native `error` on an element that was playing was swallowed** — ADDRESSED. `recovery.js:115` sets `lastPos = null` after the guard, so the next `sample` takes the baseline branch (`recovery.js:178-186`) and cannot reach `advance`/`clearAttempt`. Test `recovery.test.ts` "a native error survives the position rising between the last sample and the error": position 2 -> failed(2700) -> tick(2.7, 3000), advancing false, none at 7699, probe at 7700. The implementer's scratch run shows it red without the fix at both the `advancing` and the 7700 assertions. "An element still playing never acts" is pinned by "an element still playing after an error recovers on its second sample": the second sample advances, `clearAttempt` runs, 40 s of "none".

Checks, from the diff, reading recovery.js at 671d2f14, and a node script importing it from the scratchpad (output in t4-rereview.log):
- Fix report names the covering tests and shows output: 53 focused, 513 full, tsc clean. Not re-run, per the rubric.
- Guard ordering is right: an ignored `failed` (delay or join) leaves `lastPos` alone, so repeated errors cannot starve the advance. Sequence failed, baseline, ignored failed, advance still clears.
- Baseline with a non-null `lastSampleMs` is safe: `rise` is 0, so `jump` is false.
- `lastAudioMs`, `offairCount`, `restarts` are untouched by the baseline. Give-up and the verdict count are unchanged.
- Throttled case: failed(2500), first tick at 62 s on a playing element returns "probe" (baseline, delay already out). The verdict's follow-up tick sees a rise, advances and returns "none". So a wasted probe at worst, the element is not touched, and Task 8 shows `reconnecting` for one sample. Not a defect.

### Implementer's flagged side effect

- **60 s delay reset restarts on an error: does not matter.** Measured with one prior restart, error at 30.5 s, element still playing: `restarts` is 1 at 62 s and 0 at 93 s. It costs only a later reset, so a longer delay (capped at 30 s), on an element that survived an `error` while `restarts > 0`. A really dead element goes through `restarted`, which clears the run anyway. The spec's "resets only after about 60 s of advancing playback" still holds.
- **`stalled` false on the baseline sample: small, real, see Minor below.** `advancing` false for that sample is harmless: `#hubs` drops `turning` for about 1 s, only on an element that kept playing through an error.

### New Breakage in the Fix Diff

- **Minor, `recovery.js:115` with `:183-185`: the error's baseline clears `frozen` during a stall under way.** Before the fix `stalled` stayed true here. Measured: frozen at 2 from 3 s, `stalled` true, failed(4500), tick(2, 5000): `stalled` false, `pauseMeansStop` true, then true again at 6 s. A `pause` landing in that one sample is taken as the phone's Stop, and recovery ends instead of continuing. It needs all of: a stall with no `waiting` since the last advance (`waiting` survives the baseline, measured true), a native `error`, and a `pause` within about 1 s. The probe log shows real dropouts firing `waiting` and no `pause` or `error` (docs/superpowers/2026-11-01-player-probe.md:15-16, D1), so this is not a reachable path on the evidence. The window also grows from one sample to two for a flat position after an error. Non-blocking. If it is wanted closed, one line: `this.waiting = true` beside `:115`; the next advance clears it, and `stalled` has only the `pauseMeansStop` reader. Otherwise ledger it with concern 3.
- **Minor, `recovery.js:110-111`: wording.** "An element still playing gets cancelled by the sample after it" says the element is cancelled; it is the failure.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. Two Minors to ledger, neither blocking.
