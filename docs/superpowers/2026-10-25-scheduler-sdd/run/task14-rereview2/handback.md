# Task 14 re-review 2 (fix round 5077763..3a8f30e)

Reviewer: Opus. I worked read-only: no commits, no changes to the tree, and no subagents. Scratch files are in /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-scheduler/6a271170-52a3-49a3-b4db-a9d5cd08acfc/scratchpad/:
- clock-example2.toml, the example extracted from the committed doc;
- occ2.py, the script that loads it and expands it.

I ran them with the worktree venv. `transmitter.__file__` resolves inside the worktree.

### Finding Verdicts

1. **(Important) `clock`/`history` "resolved": FIXED.**
   - The incident runbook headings now say "(event, has "resolved")" for both codes.
   - Section 1's "resolved" column names the level codes plus `clock` and `history`.
   - The event-code bullet names both as the exceptions.
   - Section 3 puts both under "When convenient".
   - In playout-setup.md, 7.1 says each one sends "resolved".
   - All of this matches the code:
     - `Dispatcher._resolve` (alerts.py:318-332) does not check `LEVEL_CODES`.
     - `Station.clock()` resolves `clock` on a valid or absent clock (pipeline.py:166-171). It is called from `extend` (pipeline.py:186), which runs at the plan step of a fill.
     - The `history` step runs on every tick, with `resolves=("history",)` (service.py:348). `_step` resolves on success (service.py:239-242).
   - I grepped every resolve call site in src/transmitter. `clock` and `history` are the only event codes that are resolved, so the remaining "(event, no "resolved")" headings (incident runbook lines 126-203) are correct.

2. **(Important) Example block lengths: FIXED.**
   - The second block is now `late-open`, daily at 23:00.
   - 7.2 has the sentence "A block runs until the next block's start; every hour of the week belongs to some block." This matches `occurrences` (clock.py:341-342).
   - The example's comment now says "A block runs until the next block's start."
   - I re-validated the example: `load_clock` loads 2 blocks. I expanded two weeks with `occurrences`:
     - from 2026-11-02 (EST), `evening-dead` runs 3.0 h on Fri and Sat, and `late-open` runs 24 h, or 21 h on the Thu and Fri nights;
     - from 2026-10-26, the result is the same, plus the expected 25 h on the night clocks fall back (Sat 10-31).
     - Windows are 20/20 for `evening-dead` and 10/30 for `late-open`, as configured.
   - So the fix report's figures are right, and the comments match.

3. **(Minor) `deadheads` → `dead`: FIXED** (playout-setup.md example).

4. **(Minor) `exclude_profiles` comment, probe path and awaiting_fix: FIXED.**
   - The new comment says excluded profiles are left out of open time and of profile blocks' fill, and that the rule bends only when the open pool would be empty. That matches scheduler.py:276-279 (`kept or shows`, `open_bent`) and :75 (fill drawn from the open pool).
   - The probe path is `packages/transmitter/scripts/probe_estimates.py --config <config.toml> --time-one SLUG` in both CLAUDE.md:267 and playout-setup.md:498. The file exists at that path, and `--config` is required (probe_estimates.py:8, and the `required=True` argument).
   - The awaiting_fix reason now points at the probe, and the "station scan shows the reason" claim is gone.

5. **(Minor) 7.4 step 3: FIXED.**
   - The MISS is now placed where the phase-1 plan ends, at the first fill after deploy, not on the block airing at cutover.
   - This matches pipeline.py:318: the append starts from `next_start(rows, ...)`, the end of the plan.
   - The plan end is about a lead ahead: `until_frame` is now + `lead_us` (pipeline.py:121-122), with refill below `low_water_hours`.
   - See New Inaccuracy 1 for a small caveat that predates this fix.

6. **(Minor) ±12 h: FIXED.**
   - 7.2 says "±12 h window".
   - CLAUDE.md:468 says "else a daily 00:00 open block with a ±12 h window".
   - Both match `IMPLICIT_CLOCK` (clock.py:205-209): `wiggle_minutes=720` gives a 720/720 window, days daily. I confirmed this by running `window_minutes`.

### New Inaccuracies in the Fix Diff

No Critical or Important ones. One Minor, which is optional:

1. **(Minor, carried over from before this fix) The cutover MISS is not guaranteed.**
   - The rewritten step 3 still says the MISS always lands. In fact a first show is a MISS only when it falls outside the block's `[lo, hi]` window (scheduler.py:397-398, 618).
   - Under the implicit clock, which step 4 makes the default at cutover, the window is 00:00 ±12 h. So the entry show is a MISS only when the phase-1 plan ends between 12:00 and 24:00 local; an end between 00:00 and 12:00 is in window and records no MISS.
   - With a real clock, the same applies whenever the plan's end falls inside the entered block's window.
   - The wording "records a MISS ... by design" (here, in 7.2 and in CLAUDE.md) predates this round. Saying "may record a MISS" would make it exact. It does not affect air or the operator's actions.

Everything else in the diff checks out against the code.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
