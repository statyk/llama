VERDICT: ALL ADDRESSED

### Finding verdicts

1. **(Important) Blip test did not pin progress resetting offairCount: ADDRESSED.** antenna/test/nowplaying.test.ts:155-156 adds `tick(11, 61_000)` -> true (the stall is re-established: 61 000 - 46 000 = 15 000 >= stallMs, and 61 000 - 45 000 = 16 000 >= probeEveryMs) and then `verdict("offair")` -> false. With the mutant, offairCount is still 1 from the 45 000 verdict, so this becomes 2 and returns true. I re-ran the mutant independently in a scratch copy (`git archive HEAD antenna`), removing only `this.offairCount = 0;` from tick()'s progress branch (nowplaying.js:97). Predicted red test: "StallWatch > a blip ...". Result: baseline 17/17 passed; mutant 1 failed | 16 passed, exactly that test, failing at test/nowplaying.test.ts:156:33 ("expected true to be false"), the new assertion. This matches the implementer's claim.

2. **(Minor) Session counter in probe(): ADDRESSED, and correct.** player.js: `let session = 0`, `++session` in start() (beside watch.reset), `const gen = session` at probe entry, and a return when `gen !== session` both after the response arrives (before reading the body) and before the verdict. Why it is correct: a stale probe never calls watch.verdict, so it can neither add to nor reset the new session's offairCount, and it cannot clear the new session's `probing` flag. The new session does not depend on the stale probe clearing `probing`, because start() -> watch.reset() already sets probing = false. One-in-flight now holds per session. Across a Stop/Play boundary, at most one stale fetch can overlap the new session's probe, and the 8 s timeout bounds it. That costs nothing: the probe is an edge cache hit or a WAF 403. Stop without Play is still covered by `!playing`.

3. **(Minor) AbortSignal.timeout(8000): ADDRESSED, and correct.** player.js:125. An abort before the response leaves status 0, so classifyProbe returns "unknown". The signal also covers `res.text()`. An abort during the body read throws into the same catch with status already 200 and body "", and classifyProbe(200, "") is also "unknown". A 403 never reads a body. Neither path can produce a false "offair". Cadence: the verdict lands within 8 s, so `probing` clears before the next 10 s slot. Mid-play detection stays at about 15 s stall + 2 probes 10 s apart, inside the ~45 s target. The same pattern is already used in src/meter.ts, src/waf.ts and src/alerts.ts.

4. **(Minor) 124-character hlsErrorNotice line: ADDRESSED.** nowplaying.js now wraps the `const code = ... ||` expression over two lines. Nothing changed semantically (the `||` operand order is the same). `awk 'length > 120'` over nowplaying.js, player.js and nowplaying.test.ts prints nothing.

### New breakage in the fix diff

- **Minor (non-blocking), player.js:125:** `AbortSignal.timeout` exists only from Safari/iOS 16, Chrome 103 and Firefox 100. On an older browser (for example iOS 15 WebKit, where every iOS browser uses native HLS) the call throws a TypeError. It throws inside the `try`, so the catch turns every probe into "unknown". Nothing breaks visibly and nothing bills, but on those browsers mid-play kill-switch detection silently never fires. That brings back the phase-1 "page goes silent" behaviour this task exists to fix. No spend or stakes surface is involved. The audience is small in 2026. An optional one-line hardening: `signal: typeof AbortSignal.timeout === "function" ? AbortSignal.timeout(8000) : undefined`. This is the operator's call and does not block the task.

### Out-of-scope observations

- None. HEAD (733439f) has no drift from b19dccf on the Task 11 paths. Uncommitted Task 9 files were ignored as instructed.

### Checks run

- Read the re-review instructions, the constraints, the brief, the handback with the fix report, and the fix diff.
- `git diff --stat b19dccf HEAD -- antenna/public antenna/test/nowplaying.test.ts`: empty (no drift).
- `awk 'length > 120'` over the three Task 11 files: no output.
- Scratch copy (scratchpad, `git archive HEAD antenna | tar -x`, node_modules symlinked, run from the scratch dir): `npx vitest run test/nowplaying.test.ts` gave 17/17 on the baseline and 1 failed / 16 passed on the progress-reset mutant (the predicted test, failing at line 156). The scratch copy was deleted afterwards.
- The full suite was not re-run, per the instructions. The fix report names `cd antenna && npm test && npx tsc --noEmit` with 13 files, 197 tests passed and tsc clean. It also states that items 2 and 3 are browser-only and not unit-tested; I judged those by reading the code.
