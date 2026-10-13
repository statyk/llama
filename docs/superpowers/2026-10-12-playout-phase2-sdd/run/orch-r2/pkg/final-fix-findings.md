# Final-review fix wave — the complete findings list (orchestrator rulings applied)

Source: the final whole-branch review (Fable), $D/final-review/handback.md (pinned). It contains the exact probe
test text for F1 and F3 — use it. Base: 01186ea.

## Must fix (MUST-FIX items and the reviewer's "fix before merge")
F1 (MUST-FIX 1, antenna). Commit the reviewer's probe as a test in antenna/test/guard.test.ts: with
`failGets(BUDGET_KEY)`, a step at T0 and a step at T0 + 6 h + 1 min → blocked/tripped, reason "blind". Prove it:
in a scratch copy, mutant A (`if (!budgetReadFailed) doc = applyBlindRule(...)` at guard.ts ~282) must turn it
red, and it must be green on HEAD.

F2 (MUST-FIX 2, antenna/public/player.js ~125). Guard `AbortSignal.timeout`:
`const signal = typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function" ? AbortSignal.timeout(8000) : undefined;`
and pass it in the fetch init only when defined. Rebuild generated pages if the build check requires it
(`npm test` runs `node scripts/build-pages.mjs --check`); player.js is not inlined into pages unless the check says so.

F3 (MUST-FIX 3, antenna). Commit the reviewer's P10 probe as the fourth test of the alerts.test.ts describe at
~:434 (a failed re-alert over an active NEVER-delivered episode stays delivered:false and sends no "resolved" on
re-clear). Prove it: mutant M1' (`delivered: o.kind === "alert" ? !!prev[o.key]?.active : wasDelivered(prev[o.key])`
at alerts.ts ~348) must turn it red; green on HEAD.

F4 (M6). tests_transmitter/test_systemd.py ~45: "far in the past" → "far in the future" (helpers.E is 2096).

F5 (M3 = N1). docs/playout-setup.md: a raise must exceed BOTH the projected figure and actual ÷ 0.9 (trip = actual ≥ 90%
OR projected ≥ 100%) — in the spend checklist item step 2 AND section 7's "Raise above the *projected* figure".

F6 (M4 = N2). docs/playout-setup.md spend item: the 50% alert at $7 is expected; the 80% one only if
max(actual, projected) ≥ $5.60 — do not make its absence a failure.

F7 (M5 = N3). docs/playout-setup.md 6.1 step 3: paste the Google App Password without spaces (sourcing the env
file in bash otherwise errors).

## Folded by ruling (small, outward-facing)
F8 (M1, transmitter). service.py: the monitor step is named "dead-clock", so an exception inside
DeadClockMonitor.check fires the LEVEL code `dead-clock` with a traceback ("the clock is dead" — wrong). Rename the
step "dead-clock-check" (an event code: re-sent at most every repeat_hours, drops off); keep `dead-clock` raised and
resolved only by the monitor. Test: a monitor whose check raises alerts "dead-clock-check", not "dead-clock". Add
`dead-clock-check` to the runbook's hugo event-code list (7.1).

F9 (M2, transmitter). publish.py ~155-159: hugo's guard cache reads a corrupt/non-bool offair.json as on-air while
the Worker (guard.ts ~231-238) reads it as off-air → a noise unexpected-403 dead-clock alert after 17 checks. Mirror
the Worker: absent → False, a boolean → that value, anything else present → True. Do not change what blocks
publishing (offair never stopped publishing; only `tripped` does) — confirm guard_blocks_publishing is unaffected
and its tests unchanged. Test the three cases.

F10 (M7, transmitter). alerts.py ~104: ntfy Title predicate `str.isascii()` instead of latin-1; non-ASCII titles
RFC 2047-encoded with `Header(...).encode(maxlinelen=0)` (no obs-fold). Test "café" and a long non-ASCII title.

F11 (M8, antenna — comment only). guard.ts mergeLostRace (~123-132): a comment that a loser which merely carried
prev's spend trip forward re-imposes it over a winner that cleared it with a raise — fail-closed, self-heals at the
merged document's next evaluation (≤ 15 min). No code change.

F12 (T17 N4, docs). Broken-Worker "way back": "redeploy with the committed wrangler.jsonc (its output ends with
`schedule: * * * * *`)".

## Not in this wave (deferred, with the reviewer's reasons in its triage table): everything else in final-triage.md.

## Rules
- Spend surface is strict: F1/F3 are tests only — the antenna src must not change except F2 (player.js) and F11 (a
  comment). F9 must not change guard_blocks_publishing.
- antenna: `cd antenna && npm test && npx tsc --noEmit`. transmitter: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`,
  `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`, then `docker info` and the Debian-12 gate
  `packages/transmitter/scripts/test-in-debian12.sh` (background, teed, polled ≤ 270 s; STOP and report BLOCKED if docker fails).
- Docs: re-run the brief's Task 17 Step 2 email grep (`grep -nE "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}" docs/playout-setup.md | grep -v "example\.\(com\|org\|net\)\|alerts@lma-radio\.com"` → no output).
- Red first for every new test (record it); mutants only in a scratch copy; commit incrementally by explicit paths
  with the test command in each message.
