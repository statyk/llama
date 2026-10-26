# Task 14 re-review (fix round 36282ce..5077763)

Reviewer: Opus. Read-only. I made no commits and no tree changes, and spawned no subagents. Scratch files: `clock-example.toml` (extracted from the doc) and `clock-alt.toml`, both in /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-scheduler/6a271170-52a3-49a3-b4db-a9d5cd08acfc/scratchpad/.

### Finding Verdicts

**Important**
1. **CLAUDE.md phase contradiction: FIXED.**
   - Line 274 now reads "phases 1-3".
   - Lines 461-462 now read "phases 1–3 built; the full player is phase 4".
   - No other "phases 1-2" remains in CLAUDE.md, playout-setup.md or the incident runbook.
2. **`clock`/`history` alert codes: PARTLY FIXED.**
   - Both codes are now in 7.1's event list and its sent-at-once list. That is correct: neither is in `LEVEL_CODES` or `GATED_CODES` (alerts.py:53,59).
   - The cloud "clock" family is disambiguated in both places.
   - Both codes have incident-runbook entries.
   - The entries' resolve semantics are wrong, though. See New Inaccuracy 1.
3. **Clock reference: PARTLY FIXED.**
   - The example loads under `load_clock` (2 blocks). I extracted it from the committed doc and ran it with the worktree venv; `transmitter.__file__` resolves inside the worktree.
   - Keys and defaults match clock.py: `timezone` and at least one `[[block]]` required (165-181), `wiggle_minutes` 15 (167), the four template defaults (19-22), `time_format` (81), zones (71-73), `[rotation]` 45 / 3.0 (161-162), `max_shows` default (293-297), and wiggle vs early/late exclusivity (146-149).
   - "First time, write `draft.toml` from the example" is now in place.
   - However, the example does not give 2–3 h blocks, and its "Blocks of 2-3 h" comment is false. See New Inaccuracy 2.
   - The placeholder profile is not marked as one. See New Inaccuracy 3.
4. **Phase-3 cutover checklist: FIXED.**
   - The new 7.4 includes `ANTENNA_BUCKET=<bucket> npm run deploy:assets`. The script exists (antenna/package.json:14).
   - 6e0e282 touches exactly `nowplaying.js` and `player.js`.
   - "We'll be back shortly." is the pre-change text (main:antenna/public/nowplaying.js:52).
   - One wording nit is in Minor A below.

**Minor (all addressed)**
- Library reason: fixed. `reason_key` strips the reason (report.py:269-274), and `--time-one` prints it (probe_estimates.py:37-44). The path is wrong; see Minor B.
- Invalid-clock status lines: fixed. They match service.py:452-459, and `problem` begins "invalid clock at" (clock.py:216,220).
- Fill sentence: fixed (report.py:25).
- Plan lock: fixed. Plan and render run only `if self.filling`, each inside `plan_lock` (service.py:329-341).
- Voicing loop and `--no-bed` note: fixed (emcee cli.py:663).
- `[station] quiet_minutes`: fixed (config.py:26-28).
- Section order, numbering and title: fixed. The order is now 7.1-7.5, and the title reads "phases 1 to 3". The external "section 7.1" references still resolve.
- `announcements --clock FILE`: fixed in both files (cli.py:292).
- Fragment removal "with the service stopped": fixed.
- Implicit daily 00:00 open block: fixed in 7.2 (clock.py:205-209). Two nits:
  - "a 12 h window" is ±12 h, i.e. 24 h.
  - CLAUDE.md's Scheduler paragraph still says "else one all-week open block". This line was not in the diff.

### New Inaccuracies in the Fix Diff

1. **Important: `clock` and `history` DO send "resolved". The headings say they don't.**
   - docs/playout-incident-runbook.md:230 and :236 head both entries "(event, no "resolved")".
   - `alerts.resolve` → `Dispatcher._resolve` (alerts.py:318-332) does not check `LEVEL_CODES`. For any code whose entry is `active` and was sent, it sends `"<station>: resolved: <code>"` / `"<code> has cleared."` and marks the entry inactive.
   - `clock` is resolved by `Station.clock()` on every valid or absent clock (pipeline.py:166-171; pinned at tests_transmitter/test_pipeline.py:896). That happens at the next plan step of a fill.
   - `history` is resolved by the history step on every successful tick (`_step("history", ..., resolves=("history",))`, service.py:348; `_step` resolves on success, service.py:239-242). So a "resolved: history" arrives within about a minute of the fix.
   - These two are the only event codes anything resolves, so section 1 of the incident runbook is now wrong for them too. Its table says "resolved" message: "**level codes only**". Its event-code bullet ("It never sends 'resolved'") does not list them, and the urgency table (section 3) has neither code.
   - The fix report's concern has the direction backwards. The body text "first fires, and later clears, at the next fill" is right; the heading is what is wrong.
   - Fix:
     - head both entries "(event, has "resolved")";
     - say `history` resolves on the next successful tick;
     - add both codes to section 1's "resolved" column, e.g. "level codes, plus the event codes `clock` and `history`";
     - put both in the urgency table. Suggested: `history` and `clock` under "when convenient", since air is unaffected.
   - 7.1 could also say they are resolved as well as aging out.

2. **Important: the example clock's blocks are 6, 18 and 24 h, not "2-3 h", and the runbook never says how long a block runs.**
   - The code: a block runs from its start to the next block's start (`occurrences`, clock.py:341-352; spec lines 86 and 181). Nothing in 7.2 says so.
   - I expanded the example over a week (America/New_York):
     - `afternoon-open` is 24 h Sun-Thu and 6 h Fri/Sat;
     - `evening-dead` (Fri/Sat 20:00, `max_shows = 2`) runs 18 h, until 14:00 the next day, and 19 h across the DST change.
   - So the comment at playout-setup.md:529 ("Blocks of 2-3 h") is false for the example it annotates. An operator copying it gets an overnight-into-afternoon "Dead Evening": two shows, then hours of fill labelled "longer than max_shows" (or misses), every Friday and Saturday.
   - `schedule --clock` would show it, so air is not at risk. But this is the template the first clock is written from, and the brief asked for 2–3 h blocks.
   - Fix (verified):
     - change the second block to an open block starting at the profile block's end, e.g. `name = "late-open"`, `start = "23:00"`, `days = "daily"`; with that, `evening-dead` is exactly 3.0 h and the open block, whose `max_shows` is unbounded, carries the rest;
     - add one sentence to 7.2: "A block runs until the next block's start; every hour of the week belongs to some block."

3. **Minor: the placeholder profile is not marked.**
   - `profiles = ["deadheads"]  # llama profile names` (playout-setup.md:535) reads as a real name.
   - It is not one of the delivered profiles (dead, funk, bluegrass, americana, indie, jam, southern, livetronica, dead-family, dead-tribute, country).
   - Copied as is, the block's own pool is empty, so every occurrence is `degraded` (scheduler.py:298-299) and plays from the open pool.
   - Fix: use the real `dead`, or mark it `# a llama profile name, e.g. "dead"`.

4. **Minor: the `[open] exclude_profiles` comment is too strong, and the probe script path is wrong.**
   - The comment says "Profiles that never air in an open block". The exclusion is a rule that bends last: when every eligible show is excluded, the open pool falls back to all shows (scheduler.py:276-279, `open_bent`). It also removes those profiles from profile blocks' fill, since fill is drawn from the open pool (scheduler.py:75). Suggested: "kept out of open blocks and fill (bent only when nothing else is eligible)".
   - Separately, `scripts/probe_estimates.py --time-one SLUG` (playout-setup.md:497, new; CLAUDE.md:267, pre-existing) is not at that path. The file is `packages/transmitter/scripts/probe_estimates.py`, and the doc omits that it takes `--config` (its usage line 8).
   - Also, "the station scan shows the reason" has no operator-visible surface other than that probe. The reasons are computed in station.py:170-231 and surfaced only by the probe.

5. **Minor A: 7.4 step 3, "The block in progress at cutover records a MISS".** The scheduler appends from the end of the persisted phase-1 plan, about a lead (~20-24 h) ahead. So the MISS lands on the block that contains the plan's end, at the first fill after deploy, not on the block airing at cutover. Suggested: "The block the scheduler first enters mid-way (where the phase-1 plan ends, about a day ahead) records a MISS on its first show; that is by design."

Checked and correct:
- 7.4 steps 1, 2, 4, 5, 6. Backfill happens on the first append (history.py:131-152); the history step runs every tick (service.py:348).
- The new cloud-family wording.
- The incident `history` entry's causes. These are `TransmitterError` on an epoch mismatch (service.py:264-270) or any other exception, via `_step`'s generic arm (service.py:257-258).
- `on_this_day` in a block's `prefer` overrides `[rotation]` (rules.py:77-82).
- The `--clock` export rationale: ids hash the rendered text.

### Verdict

**Fix round:** Findings remain open.
- Important 2: the new `clock`/`history` entries say no "resolved" is sent, but `alerts.resolve` sends one for both; section 1's table and the urgency table need the two codes.
- Important 3: the clock example's "Blocks of 2-3 h" is false (6/18/24 h), and the runbook never says a block runs until the next block's start.

Important 1 and 4 and all Minor findings are addressed. The new Minor items 3-5 are optional. All fixes are doc-only.
