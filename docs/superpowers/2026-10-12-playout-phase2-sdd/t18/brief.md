# Task 18 (amended): playlist hold-back + lookahead

Worktree: `/Users/shawn/projects/llama/.claude/worktrees/playout-t18`, branch `playout-t18`, base `7c93250`
(main, with phase 2 merged). Read `CLAUDE.md` (playout section), the phase-2 plan
`docs/superpowers/plans/2026-10-11-playout-phase2.md` (its Stakes, Global Constraints, amendment A4 and
Task 18), and the spec's Stakes section (`docs/superpowers/specs/2026-10-09-playout-design.md`). This
brief **replaces** the plan's Task 18 Steps 1–5. The plan's version (lookahead 3, cap 4) rests on a wrong
premise; the amended design follows.

## Why the plan's version is wrong, and what was measured (operator, 2026-10-12)

- **Cron lag.** A 13.6 h `wrangler tail` capture (846 invocations) gave a median of 15 s, a p99 of 77 s
  and a max of 117 s. Every daytime fire at :00/:30 lagged more than 25 s. Details:
  `docs/superpowers/2026-10-11-playout-phase1-verification.md`, cron row.
  - A late fire leaves `live.m3u8` unchanged for about lag − 15 s.
  - Players sit about 3 target durations behind the **listed end**. They stall once that gap exceeds
    their distance to the listed end (~31 s).
  - The operator heard two dropouts on iOS around 10:00 EDT.
- **The premise error.** A lookahead alone adds NO runway. Lookahead shifts the listed end and the
  player's start point together, so a player still starts 3 behind the listed end. The plan's A4
  arithmetic, "lookahead 3 → ~64 s runway", was wrong. **Runway comes only from where players start
  relative to the listed end.**
- **iOS behaviour, measured on a real iPhone.** The test server played the station's real segments with
  a Mac-side playlist that could freeze. Results:
  - **No tag:** players start 22 s behind; a 45 s freeze stalls.
  - **`#EXT-X-START:TIME-OFFSET=-122.880`:** start 120 s behind; Safari buffers the whole ~120 s.
  - **`#EXT-X-SERVER-CONTROL:HOLD-BACK=122.880` alone:** start 116 s behind.
  - **Both tags (VERSION 6):** start 113 s behind.
  - **Freezes with a tag:** 45 s and 60 s freezes play through and the buffer refills. 75 s and 90 s
    freezes cause a 1–3 s drop that auto-heals, also with the screen locked.
  - All iOS browsers use WebKit, so this covers Chrome and Firefox on iPhone.
  - Desktop and Android go through hls.js (`antenna/public/player.js`).

## The design

The playlist config gains two values:

- **`holdBack` (R segments):** where players should start, R segments before the listed end. It is
  emitted on every **live** playlist as both:
  - `#EXT-X-START:TIME-OFFSET=-<R·d seconds, 3 decimals>`;
  - `#EXT-X-SERVER-CONTROL:HOLD-BACK=<same>`.

  Keep `#EXT-X-VERSION:3` (iOS honoured both tags at version 3). Emit nothing when R = 0. RFC 8216bis
  requires HOLD-BACK to be at least 3 × TARGETDURATION, and the START offset should not lie within
  3 target durations of the end, so emit them only when `R·d >= 3·TARGETDURATION`.
- **`lookahead` (L segments):** list L segments past the one airing, so players that start R behind the
  listed end sit at the wall clock when L = R.
  - Every listed segment exists: the lead is ~24 h, and the lead floor alerts at 16 h.
  - The grace hold and the fallback switch apply to `target = cur + L` (the plan's Step 3 `windowEntries`
    change is still right).
- **Config:**
  - `wrangler.jsonc` vars: `PLAYLIST_WINDOW "16"`, `PLAYLIST_LOOKAHEAD "12"`, `PLAYLIST_HOLD_BACK "12"`.
  - `configFromEnv` defaults stay backward-compatible (lookahead 0, holdBack 0, window 6).
  - `MAX_LOOKAHEAD = 16`.
  - Clamp `holdBack` to at most `window − 1`. The offset must lie inside the listed window; RFC: |offset|
    SHOULD NOT exceed the playlist duration.
  - Pin all of these with tests.
- **Off-air MEDIA-SEQUENCE invariant: get this exactly right; it is the subtle part.**
  - The off-air playlist's MEDIA-SEQUENCE (the notice segment's number) must never number the notice at
    or below a live segment number a player may already have seen. Live windows now list up to
    `cur + L`.
  - The plan's Step 3 rule is `offairSeqMs = max(scheduledTime + loopMs, startedMs + L·d)`.
  - Derive, and pin with tests, that the notice's number is **strictly greater than every live segment
    number any earlier write (this invocation or an overlapping or earlier one) could have listed**. Use
    the plan's late-invocation test, and add an on-time-invocation case and a cap case (L = 16).
  - If the rule needs a `+1` or a different term, fix it and say why in the handback.
  - Keep MEDIA-SEQUENCE monotonic within an invocation, as phase 1 does.
  - Do NOT try to fix the off-air→live direction: that is the documented VLC limitation (amendment A1),
    out of scope. Do say in the handback whether the larger L changes that limitation.
- **hugo's dead-clock check (`packages/transmitter/src/transmitter/deadclock.py`).** It dates
  `live.m3u8` by its newest segment's PROGRAM-DATE-TIME. With L = 12 that segment starts ~123 s in the
  **future**, so a dead clock would go unnoticed for an extra ~2 minutes.
  - Fix it so the check measures staleness correctly regardless of L. For example, date the playlist by
    its newest PDT minus the lookahead. The lookahead can come from a new `[alerts]` or `[publish]`
    config key; or, more robustly, from the `#EXT-X-START`/`HOLD-BACK` offset in the playlist itself,
    if L = R is documented as the deployment rule. Choose, justify in the handback, and test.
  - The config is strict (`extra="forbid"`). A new key needs the model, `DEFAULT_CONFIG_TOML`, the
    runbook, and `test_template_parses_to_the_defaults`.
  - Python 3.11: run the transmitter suite on both `.venv` and `.venv311`, and the Debian-12 gate if
    Docker is up. Create `.venv`/`.venv311` in this worktree first, per `CLAUDE.md`/plan Task 0, if they
    are missing.
- **Prune.** Confirm, and pin if not already pinned, that hugo's prune never deletes a segment the new
  window can list. The oldest listed is `cur + L − W + 1` = `cur − 3` for L = 12, W = 16. Players
  started 12 back fetch from about `cur`. If prune is safe as is, say so with file:line evidence; do not
  change it needlessly.
- **hls.js (`antenna/public/player.js`, currently `new window.Hls({ liveSyncDurationCount: 3 })`).**
  hls.js honours EXT-X-START (source-verified by research), but make it explicit and robust:
  - `liveSyncDurationCount: 12` (matching the hold-back; comment why);
  - `maxBufferLength` large enough to actually fill the runway (e.g. 120). Check hls.js's
    `maxMaxBufferLength` and back-buffer defaults so it is honoured.

  Check the vendored hls.js version's option names and semantics before relying on them. Make sure the
  mid-play kill-switch StallWatch (Task 11) still behaves. `player.js` has no tests; keep changes
  minimal and explained.
- **Docs.**
  - Revise the plan's amendment A4 and the Task 18 header in the plan to record the corrected premise,
    the measurements above and the as-built values. Keep it short; mark it "amended 2026-10-12".
  - Update `docs/playout-setup.md` wherever playlist vars or the dead-clock check are described, and add
    a phase-2 checklist item: "joining on iPhone and Chrome starts near the wall clock (now-playing
    matches the schedule)".
  - Do not touch `CLAUDE.md`; that is Task 19.

## Constraints (verbatim from the plan's Global Constraints where they apply)

- The clock's spend bounds stay intact: `MAX_PUTS = 10`, the d ≠ 10.24 refusal, the 75 s loop clamp,
  `LIVE_MAX_AGE` ≥ 1. The PUT count must not change.
- The guard runs first. No test may reach the network.
- **This repo is public.** No account ID, zone ID, token, key or email address may be committed.
- No `wrangler deploy`, no `secret put`, no `deploy:assets`, no `--dry-run` of any kind, and no call to
  the real account, R2, ntfy or SMTP.
- **TDD:** failing tests first, then the implementation.
- **Gates** (state the exact commands in the handback):
  - `cd antenna && npm test && npx tsc --noEmit`;
  - `./.venv/bin/python -m pytest -q`;
  - `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`;
  - `packages/transmitter/scripts/test-in-debian12.sh`.
- Commit incrementally with clear messages, each ending with these two lines:

```
Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018J1bSvV862ZY6Y1VhXqoSL
```

## Handback

Write the handback per mandate 1. It must cover:
- what changed, file by file;
- the off-air invariant derivation (one paragraph);
- the dead-clock choice;
- prune evidence;
- hls.js option names verified, with the version;
- gate commands with their counts;
- commits;
- deviations from this brief;
- open questions.
