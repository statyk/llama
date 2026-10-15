# Plan review decisions (Opus + Fable), apply all

P1. Every `renew` persists at least one row (fixes the false blind trip). `renewSteps` writes `stalls`
    on every call (the spec's renew step "update stalls"), even when its value is unchanged, so a
    healthy DO always writes ≥ 1 row per minute and "empty is not zero" for `doRowsWritten` holds.
    Fix the `assertMetronomeMetered` docstring premise to say this. Remove/adjust "Spec reading 4"
    ("keys written only when they change") so it carves out `stalls` on renew. Add a Task 4 test:
    `renew(null)` against an expired (and against an absent) lease still calls `save` with `stalls`.

P2. Duplicate alarm deliveries are idempotent again (spec: "A duplicate or retried alarm rebuilds
    the same bytes and skips the PUT"). In `alarmSteps`, after the lease check: if the port reports a
    pending alarm (`getAlarm() !== null`; a genuine delivery has none pending while its handler runs),
    treat the invocation as a duplicate: build for `now`, write only if the bytes differ (normally
    identical → confirmed tick), do NOT re-arm and do NOT change `lastTarget`. Remove "Spec reading 9"
    and Review Focus 5's "at most one boundary early" claim and replace with the idempotent behaviour.
    Tests (Task 5): k = 3 duplicates after a completed tick → no extra PUT, `lastTarget` unchanged,
    the pending alarm unchanged; a duplicate followed by a renew in the same segment → no
    backwards MEDIA-SEQUENCE and no extra PUT. Extend `FakePort` with a `deliver` variant that leaves
    `alarmAt` set. Add to Task 9's checks: the verification day confirms on the real runtime that a
    duplicate sees a pending alarm (count `metronome-duplicate` log lines if you add one, once per
    episode), and record that this getAlarm semantics is from the docs (do-facts) and the test double.
    Keep the alarm-invocation cap test meaningful under the new rule (it must still exercise 12+
    genuine-looking deliveries).

P3. Pin the 15-minute bound under renew(null)/superseded (Task 4 test): `renew(play)` at T;
    `renew(null)` at T+5 min and T+10 min; a superseded unblocked play lease at T+12 min; at T+15 min
    `renew(null)` reports `lease: "none"`, no PUT, no pending alarm, and a delivered alarm writes
    nothing and does not re-arm.

P4. Task 0 step 3: commit the plan only if the worktree's copy differs from `main`'s
    (`git diff --quiet main -- <plan path> || git commit ...`); otherwise skip.

P5. Review Focus 4 and Task 8's section 9 "Rollback": add that a persistent `metronome-down` while
    `METRONOME` is "on" (DO absent or broken) also fails every guard reading (`doRequests` = 0) and
    trips the station blind after 6 h — roll back with `--var METRONOME:off` rather than ride it out.

P6. Task 9 step 1(b) and section 9: run the pre-deploy query check from the MAIN checkout's
    `antenna/` (the worktree has no gitignored `.env`); the variables are `CLOUDFLARE_ACCOUNT_ID` and
    `CLOUDFLARE_ANALYTICS_TOKEN` (not `CF_ANALYTICS_TOKEN`). Section 9 step 3: the post-flip guard
    failure lasts "until the next evaluation (≤ ~20 min)", not "up to 5 minutes".

P7. Every commit step uses `git -C <worktree root> add …` / `git -C <worktree root> commit …` (or states
    it runs from the worktree root), consistent with `cd antenna && npm test` in the run steps.

P8. Reword the "Verified while writing this plan" bullet: the code was verified at its FINAL state in a
    scratch copy (Tasks 4 and 5 were verified together; some tests were added at the end); per-task
    counts are expected values — an implementer reports any per-task difference rather than assuming
    it is theirs. If you re-run per-task boundaries in a fresh scratch copy and they hold, say so.

P9. Task 9 verification: add an independent `live.m3u8` poller for the verification day (from the Mac,
    `curl` every ~5 s of `https://listen.lma-radio.com/live.m3u8`, logging fetch time, MEDIA-SEQUENCE
    and the last PROGRAM-DATE-TIME to a file under `~/lma-radio-ops/`), give the exact script, and make
    the "no freeze > 45 s" criterion use it (DO logs remain diagnostic only, since anomaly lines are
    once per episode).

P10. Trims: the new cron-only config test keeps only the `triggers` assertion (the others already
    exist); declare `METRONOME?: string` once (in `ClockEnv`) and give `guardConfigFromEnv` the
    narrowest type that reaches it; remove the other declarations.

Method: apply each change to the plan text AND to the scratch copy at
/private/tmp/claude-501/-Users-shawn-projects-llama/b91f8d99-bd38-4c3d-b31c-e41370b13e93/scratchpad/ant
(it is a scratch git repo; commit there as you like), then run `npm test` and `npm run typecheck` there
and make sure every code block in the plan matches the scratch copy and every expected test count in
the plan matches what the suite reports.
