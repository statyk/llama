VERDICT: APPROVED

# t18-rev-spec: spec-compliance review of Task 18 (amended), range 7c93250..906222e

Every brief requirement is met. The four deviations are justified; one of them (the off-air rule) is required, not optional. I found no Critical or Important issues. The minors are doc accuracy, one duplicated constant, and items the operator should acknowledge.

## Verified independently (not taken from the handback)

- **Gates, re-run by me in the worktree:**
  - `cd antenna && npm test && npx tsc --noEmit`: 235 passed, tsc clean.
  - `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`: 456 passed, 1 skipped.
  - `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q` (3.11.15): 456 passed, 1 skipped.
  - Both venvs resolve `transmitter` inside the worktree.
  - Not re-run: the Debian-12 docker gate and the full llama suite (the Python change is confined to transmitter).
- **Scratch mutants** (`git archive 906222e` into /private/tmp/claude-501/t18-rev-spec-scratch; Python shadowing proven with a planted sentinel):
  - **The plan's original off-air rule, even with a +1:** `indexAt(max(seqMs, now + L·d)) + 1`. Caught: 3 red, the on-time clock tests at L = 4, 12 and 16.
  - **Per-playlist hold-back clamp removed.** Caught: 1 red.
  - **Grace hold keyed on `cur` instead of the target.** Caught: 1 red.
  - **Live dead-clock age ignoring the hold-back.** Caught: 3 red, matching the handback.
- **Commits:** all three carry both trailer lines. No account ID, zone ID, token, key or address appears in any added line. `CLAUDE.md` is untouched.

## Off-air MEDIA-SEQUENCE invariant

The code is `playlist.ts:79-81`: `offairSequence = max(0, indexAt(max(seqMs, nowMs))) + L + 1`. It is called at `playlist.ts:129` with `seqMs = scheduledTime + loopMs` (`clock.ts:311-312`).

- **Live upper bound.** `windowEntries` (`playlist.ts:49-57`) ends at `target = cur + L`, or at `h.last` only when `h.last < target`. A live write at time t therefore lists at most `indexAt(t) + L`. Fallback entries stay inside the same range. This holds in all three cases:
  - normal;
  - held at `horizon.last`: `end = h.last < target`;
  - past grace: fallback entries up to `target`.
- **Earlier writes, for every L in 0..16.** `indexAt` is nondecreasing. Every live number written at or before `nowMs` is therefore at most `indexAt(nowMs) + L`. The notice is at least `indexAt(nowMs) + L + 1`, so it is strictly above. This covers:
  - this invocation's writes;
  - an earlier invocation's writes;
  - an overlapping invocation's writes computed before this one;
  - a late invocation, via the `now` term.

  `playlist.test.ts` pins it for L ∈ {0, 3, 12, 16} × cur ∈ {0, 5, 1000, 4990} × three `seqMs` values × with and without a fallback. At cur = 4990, L = 12 exercises the held-at-last case and L = 16 the past-grace fallback case. `clock.test.ts` pins the late (+100 s) and on-time cases, including the previous minute's run, at L = 4, 12 and 16.
- **Why the plan's rule had to go.** It was wrong for an on-time invocation, not only a late one. With `max(indexAt(S+75), indexAt(startedMs) + L)`, a live write at S+75−ε lists `indexAt(S+75) + L`, which is above both terms for any L ≥ 1. My mutant M1 shows this (red at L = 4). Taking L outside the max is therefore required, and the deviation is justified. The handback's "why" list never states this, its strongest reason (Minor 5).
- **Monotonic within one invocation.** The number is constant while `now <= S + loop`, and follows `now` afterwards. `inputs.offair` is fixed per invocation and stale-horizon off-air is monotone in `now`, so the playlist can go live → off-air within an invocation but never back. Pinned at `playlist.test.ts` (`off(at(1000) + 200_000) === 1020`).
- **On-time PUT count.** Unchanged: one off-air PUT per on-time invocation (pinned: `offs` has length 1). A late invocation breaks out of the loop after its first write. The only path to a second off-air PUT is a `sleep` that overshoots past a whole boundary beyond the deadline. That is negligible in Workers, and it stays bounded by the cap.
- **The +1 at L = 0.** It is safe. The off-air MEDIA-SEQUENCE has two consumers:
  - players, for whom it is a label;
  - hugo's dead-clock check, which now under-reads by one more segment. That direction is safe: it can delay an alert, never raise a false one.

  The phase-1 exact-number tests were updated (1000→1001, 1007→1008). The +1 also closes a real phase-1 hole (notice = last live number ⇒ the player skips the notice).
- **Disclosed residual races, all acceptable.**
  - A late off-air PUT can land after a live write that an overlapping invocation computed later than it. That needs a PUT to span a segment boundary.
  - Lowering L by a deploy while off-air.
- **A1 / off-air→live.** The handback's conclusion is correct: L cancels out of the drop, so the larger L does not change the limitation. Its formula is off by one, though: the drop is `X − cur' + W`, not `+ W + 1` (Minor 6).

## Hold-back tags (`playlist.ts:158-174`)

- **Format.** Exact: `#EXT-X-START:TIME-OFFSET=-122.880` and `#EXT-X-SERVER-CONTROL:HOLD-BACK=122.880`, 3 decimals, `#EXT-X-VERSION:3` kept. Both tags come before the first segment (pinned).
- **Live only.** They are only in the live branch. The off-air and ENDLIST-only playlists carry neither (pinned).
- **Threshold.** `holdBack·dMs >= 3·ceil(dMs/1000)·1000`, i.e. 3·11 = 33 s. R = 3 (30.72 s) emits nothing and R = 4 (40.96 s) is the first emitted (pinned).
- **Clamping.**
  - `configFromEnv` clamps to `window − 1` (`clock.ts:42`), as the brief requires.
  - Per playlist, it also clamps to `entries − 1` (deviation 4). This is harmless: with L = R it is never active, because `end ≥ L` gives at least R + 1 entries.
- **Config.** `MAX_LOOKAHEAD = 16` and the backward-compatible defaults (lookahead 0, holdBack 0, window 6) are in `clock.ts:33-48`. `wrangler.jsonc` has 16/12/12. All are pinned in `clock.test.ts` and `wrangler-config.test.ts`, including L = R and R·d ≥ 33.

## Dead-clock check on hugo (`deadclock.py:51-92`, `:122-134`)

- **Live staleness when L = R.** Age is `(now − newest PDT) + R·d = now − start(cur at write)`, the same as phase 1. A held-at-last playlist over-reads by at most grace·d, also the same as phase 1. The "~3 min" dead-clock checklist item still holds.
- **Off-air.** The monitor remembers the last live hold-back. The monitor object persists across ticks: it is built once by `service.open_monitor` and lives in `Runner`, so the memory is real. The age under-reads, never over-reads: by at most `(S + 75 − t_write) + d`, about 85 s, against phase 1's about 75 s. So there is no false alarm, and detection is up to one segment later than in phase 1.
- **Cases the handback discloses:**
  - a monitor restarted while off-air starts with 0 memory (late by up to L·d);
  - L ≠ R;
  - a malformed or positive offset counts as 0 (the phase-1 behaviour).
- **Python 3.11.** Uses only `float | None`, `math.isfinite` and `str.partition`.
- **Choosing the playlist's own tag over a config key** is justified: the playlist is the single source of truth, and a hugo-side key could drift. The brief explicitly allowed it once L = R is documented, which it is (runbook §4 step 6, `wrangler.jsonc` comment, test). No config key was added, so `DEFAULT_CONFIG_TOML` and its test rightly stay unchanged.

## Prune

Prune is safe as is, and the handback's evidence checks out.

- `publish.py:400-401`: the cutoff is `now − prune_margin_minutes`.
- The margin's floor is 4 min (`config.py:66-84`), and the default is 10 min.
- A segment is now listed for at most (16 − 12 + 3)·d = 71.68 s after it starts, against the floor's 9·d = 92.16 s. Pinned at `wrangler-config.test.ts`.

## Spend bounds

All unchanged:

- `MAX_PUTS = 10`, `GRID_D`;
- the 75 s clamp, the `LIVE_MAX_AGE >= 1` floor;
- guard first, then `reconcileIndex`, then inputs;
- `putCap`.

The only `clock.ts` changes are config parsing and a comment. Live PUTs per invocation are unchanged. A player's segment-GET count per listen is unchanged; each segment is just fetched ~2 min earlier, cache-served.

## hls.js, vendored 1.7.3 (`antenna/node_modules/hls.js/package.json`, served by `scripts/deploy-assets.mjs:31`)

Each claim below is checked against `dist/hls.mjs`:

- **EXT-X-START.** It is honoured when `startPosition = -1`: `edge + offset`, clamped to the playlist (`hls.mjs:11693-11713`).
- **`targetLatency`.** It is HOLD-BACK unless the user sets `liveSyncDuration` or `liveSyncDurationCount`. Then it is `liveSyncDuration ?? liveSyncDurationCount * targetduration`, where `targetduration` is 11 (`:34979-34986`). So `liveSyncDurationCount: 12` would mean 132 s, and the deviation to `liveSyncDuration: 122.88` is correct.
- **Mixing Count and Duration options throws** (`:38438`). The shipped config mixes nothing, and since `liveMaxLatencyDuration` is unset, nothing throws.
- **Buffer length.** `getMaxBufferLength` returns `min(maxBufferLength, maxMaxBufferLength = 600)` when there is no bitrate (`:11304-11315`). 130 (rather than 120) is needed for the 122.88 s runway.
- **Back buffer.** The `backBufferLength` default is Infinity (`:38120`), and `reduceMaxBufferLength` shrinks `maxMaxBufferLength` on a quota error (`:11333`). Setting 30 is reasonable.
- **StallWatch.** The code path is unchanged (`player.js:69-76`; `nowplaying.js` untouched).

## Docs

- **Plan.** The A4 amendment and the Task 18 header both carry "Amended 2026-10-12" blocks, with the original text kept.
- **Runbook.**
  - §4 step 6 is added.
  - The dead-clock row in the alerts table is updated.
  - The already-playing-page latency is updated.
  - The brief's checklist item is present (`docs/playout-setup.md:459`).

## Critical

None.

## Important

None.

## Minor

1. **The runbook overstates the runway** (`docs/playout-setup.md:221`): "a cron fire up to ~100 s late … does not stall them".
   - **Scenario.** The brief's own iPhone measurements contradict it. A late fire freezes the playlist for about lag − 15 s, so a 100 s lag is an ~85 s freeze. Measured, 75 s and 90 s freezes caused a 1–3 s drop that healed itself. Safari also starts 113–120 s behind the listed end, not 122.88 s. The operator would expect no drop where one is measured.
   - **Fix.** Say "freezes up to ~60 s (lag up to ~75 s) play through; longer ones, up to the measured max lag of 117 s, cause a 1–3 s drop on iOS that heals itself."
2. **The A4 amendment conflates VERSION** (`docs/superpowers/plans/2026-10-11-playout-phase2.md:70`): "… and/or … HOLD-BACK at VERSION 3 started playback 113–120 s behind".
   - **Scenario.** Per the brief, the 113 s both-tags figure was measured at VERSION 6. The single-tag runs (116 s and 120 s) are the VERSION-3 evidence. A future reader could cite this text as proof that both tags were measured at VERSION 3.
   - **Fix.** "EXT-X-START alone 120 s, HOLD-BACK alone 116 s, both (at VERSION 6) 113 s; iOS honoured each at VERSION 3."
3. **The kill-switch latency on an already-playing Safari page grows from about 45 s to about 2.5 min.**
   - **Scenario.** This is inherent to the hold-back, which is the operator's chosen design. The handback and the runbook checklist disclose it, but the plan's Review Focus 5 and A2 still say "within about 45 s". Spend is unaffected: the playout is from the local buffer, and the 403s are not billed.
   - **Fix.** The operator acknowledges it, and Task 19's A2 note records it.
4. **`player.js:69` hardcodes `liveSyncDuration: 12 * 10.24`**, which duplicates `PLAYLIST_HOLD_BACK`.
   - **Scenario.** A later change to the var without a `deploy:assets` makes hls.js re-sync at a different latency than it joins at.
   - **Fix (optional).** Per `hls.mjs:34983-34985`, leaving `liveSync*` unset makes hls.js use the playlist's HOLD-BACK, which is single-sourced and falls back to 3·TD with no tag. The brief asked for an explicit value, so the current form is compliant; at least name the coupling in the runbook's §4 step 6.
5. **The handback never states the decisive reason the plan's off-air rule was replaced.**
   - **Scenario.** The plan's rule also fails for on-time invocations: live writes up to S+75 list `indexAt(S+75) + L`, which is above `max(indexAt(S+75), indexAt(startedMs) + L)`. The handback's reasons (pre-guard `startedMs`, lateness) are true but secondary. The record should carry the main one for Task 19.
   - **Fix.** One sentence in the A4 amendment or the Task 19 brief.
6. **The handback's A1 formula is off by one.** The off-air→live drop is `X − cur' + W` with `X = indexAt(max(S+75, t))`, not `+ W + 1`. Its comparison with phase 1 ("+10 and +1") is right. Nothing in code.
7. **One stale comment.** `config.py:103` still says "the public live.m3u8's newest segment older than this". It is now that segment minus the hold-back; the template text at `:225` is already generic.
8. **Off-air→off-air numbering can now dip by a segment across invocations.** It happens when an invocation runs more than about 135 s late and the next one is on time (the measured max lag is 117 s, plus guard time). This is harmless: such a player has already stopped on ENDLIST and does not reload. Hugo's age only under-reads. Recorded for completeness; no fix needed.
9. **For Task 19.** The spec's playlist rules (`docs/superpowers/specs/2026-10-09-playout-design.md:408-428`, "ending at the current index", and the off-air numbering) are now out of date. Task 19 owns the spec amendments; this is a hand-off, not a T18 defect.

## Open questions from the handback

My view on each:

- **Using MAX_LOOKAHEAD in the off-air rule** would close the "lowering L by a deploy" hole. The cost: the off-air dead-clock check under-reads by a further (16 − L)·d, about 41 s at L = 12. Leaving it on the configured L is defensible; it is the operator's call.
- **The cross-invocation race** is the same family as phase 1's overlapping-runs note. Accept it.
- **The start point** is +0 to 10 s ahead of the wall clock at the moment of the write. The new checklist item will measure it. L = R + 1 is a fine follow-up if that is wanted.
