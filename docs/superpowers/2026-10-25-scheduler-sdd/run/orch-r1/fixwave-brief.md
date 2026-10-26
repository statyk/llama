# Final fix wave — scheduler branch (playout-scheduler)

Worktree: /Users/shawn/projects/llama/.claude/worktrees/scheduler (branch playout-scheduler, BASE 00afe1f). Python 3.11 compatibility is a hard constraint for packages/transmitter.
Source of the findings: the final whole-branch review, /Users/shawn/projects/llama/.claude/worktrees/scheduler/.superpowers/sdd/scheduler/final-review-r2/handback.md ("Minor" section, items 1-6) and the name-docs review, /Users/shawn/projects/llama/.claude/worktrees/scheduler/.superpowers/sdd/scheduler/name-docs-review/handback.md ("Minor" 1-3). Read both Minor sections first; they are short.

Fix every item below. Each is small. Commit in coherent steps (code+tests separate from docs is fine).

## Code + tests
A. (r2 Minor 1) `ahead=1` is unpinned. In packages/transmitter/tests_transmitter/test_scheduler.py, give the `live()` helper an `ahead` parameter (default unchanged) and run `test_appending_first_pieces_reproduces_one_projection` for both ahead=1 and ahead=2 (parametrize). It must pass for both without any production change. Prove it can fail: in a SCRATCH copy only (mandate 5), mutate the piece-[0] path so ahead=1 differs and show the new case goes red; record the mutant and the red test name in your handback.
B. (r2 Minor 3) pipeline.py `plan_step`: the "internal-bug guard" right after `start, run_start = next_start(rows, st.gap_frames), False` is tautological (`next_start` is defined as last end + gap, planner.py). Ruling: DROP the guard (the real guard is `extend`'s expected-start check). If a test pins that LayoutError message, remove that test case too and say so.
C. (r2 Minor 4) pipeline.py `render_step`: after the direct `st.engine.analyze(piece.show)` call (the cold analysis on the render path), send a watchdog ping the same way this function already does after `encode_show` (`if notify is not None: notify("WATCHDOG=1")`). Add a test that a render step which analyzes pings at least once more than before (or that the ping follows analyze before encode), following how existing tests observe `notify`. Also add one sentence to the runbook's watchdog paragraph (docs/playout-setup.md; find it by grepping WatchdogSec/watchdog) noting that a render-path re-plan calls extend with no max_new, so with an estimate-heavy library one render step can analyse many never-aired picks (worst case ~40-55 min) under the plan lock; the watchdog is fed per analysis, so the service survives, but publish waits that long.
D. (r2 Minor 6) config.py `DEFAULT_CONFIG_TOML`: comment out the `[interstitials]` table header (`# [interstitials]`) so a config made by `config init` on this build is accepted by builds before 684d323. Keep the explanatory comments. Check tests that parse the template (e.g. config init round-trip) still pass, and adjust docs/playout-setup.md 7.5 if its "remove `[interstitials]`" advice now needs to say "only if you uncommented it" (keep it accurate).
Not in scope: r2 Minor 5 (double stat) — ruled out, leave interstitials.py alone.

## Docs only
E. (r2 Minor 2 / Task 14 deferred minor) Change the unconditional "records a MISS" wording to conditional: "may record a MISS (only with a clock file, and only when the plan's end lands outside that block's window)" — or equivalent exact wording — at: packages/transmitter/src/transmitter/cli.py `schedule` docstring (~line 253), docs/playout-setup.md ~line 497 (7.2 "Reading schedule / status") and ~line 576 (7.4 step 3, "The MISS therefore lands..."), and CLAUDE.md ~line 262 (schedule bullet). Grep for any other unconditional statement of it (`records a MISS`, `records MISS`, `MISS therefore`) and fix those too. If the cli.py docstring is shown by --help, keep the line short.
F. (name-docs Minor 1) docs/playout-setup.md 7.3 (~line 558): "The show pages and alerts take it from `station_name`" -> "The show pages and hugo's alerts take it from `station_name`; antenna's emails from the Worker's `STATION_NAME` (7.4 step 8)".
G. (name-docs Minors 2-3) docs/playout-setup.md 7.4 step 8 (the station_name = "LMA Radio" step): say "do this before step 1's restart, or restart again after"; say the `wrangler.jsonc` `STATION_NAME` edit must be committed (like METRONOME, an uncommitted var reverts at the next deploy from a clean checkout); note the next publish pass re-PUTs `notes/` and `show/` pages for every show in the site window (digest change, a handful of PUTs); and that pages of shows outside that window (aired more than a day ago) are never re-rendered and keep "llama radio".
Do NOT edit any file under docs/superpowers/specs/ or the plan.

## Verification (state exact commands and counts in the handback)
- `cd /Users/shawn/projects/llama/.claude/worktrees/scheduler && ./.venv/bin/python -m pytest -q packages/transmitter/tests_transmitter` — must be green. First confirm `./.venv/bin/python -c "import transmitter; print(transmitter.__file__)"` resolves inside this worktree.
- Do not run the Debian-12 docker script or antenna tests; the orchestrator runs all gates afterwards.
- Never touch hugo, R2, Cloudflare (no ssh, no wrangler, no publish).

## Handback
Status (DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT), commits (sha + subject), per item A-G what changed (file:line), the mutant for A with its red test, test command + result line, concerns.
