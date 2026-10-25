# Round-2 decisions (apply exactly)

## A. REPLACE the mutable tail with an append-only plan (circuit-breaker: the frontier/truncate mechanism drew Important findings in two rounds)
A1. Replace the whole "The frontier" bullet, the "Clock edits" paragraph, the Persistence bullet and every trace of "truncate", "re-plans everything after them", "R = max(listed_bound...)", "frozen rows" as a computed set, and "every plan step re-plans the unfrozen tail" with this rule:
  - **The plan is append-only, as in phase 1.** The scheduler never changes or removes a row of `plan.jsonl`. Each plan step runs the scheduler from the end of the persisted plan (its lookahead is recomputed in memory every step and never persisted) and appends the next row(s). Every persisted row is therefore final; there is no frontier to compute.
  - The only existing paths that drop persisted rows stay exactly as phase 1 has them, owned by render/publish, not the scheduler: the render-time re-validation skip (`replan_from`: a piece that fails before its first segment is encoded is dropped with every row after it, and the plan is re-extended from that row's own start frame and `run_start` flag), and recovery after an outage longer than the lead (`cut_for_recovery` at `listed_bound`, which deletes the unpublished files first). The scheduler is just the extender those paths call.
  - **Clock edits** reach air after the persisted plan has aired: about one lead plus at most one show. `transmitter schedule` shows the new clock's effect at once; `status` shows the persisted plan, which is what will actually air.
  - Lookahead is anchored to the frame line (block occurrences counted from the end of the persisted plan), never to `now`, so unchanged inputs give the same choice on every step.
A2. Stakes "frozen prefix" bullet: say the scheduler only appends; a persisted row never changes except by phase 1's two existing paths (above).
A3. **Plan lock.** One non-waiting flock (the `publish_lock` pattern, e.g. `plan.lock`) around `plan_step` + `render_step`: the service holds it for its plan/render steps; the `plan` and `render` CLI commands take it and refuse when held. `schedule` and `status` take no lock. (This closes a phase-1 race too: two appenders reading the same plan could each append a different row at the same start while render uses the other.)
A4. Gap layout: the rule "every non-`run_start` row starts at the previous row's end + `gap_frames`" is asserted on each **appended** row only (phase 1's `next_start` already does this); existing rows are checked only for non-overlap, as today, so a `show_gap_seconds` change never fails a step.
A5. Correct the code claims: phase 1's `render_step` does drop and re-extend persisted rows (the skip path); `replan_from` restarts at the skipped row's own start frame and `run_start` flag.
A6. Scenario check (record briefly in the spec's Testing list as required tests): a clock edit mid-fill; a manual `plan`/`render` while the service renders (refused by the lock); the skip path dropping an interstitial row and a show row; recovery with a guard stop longer than the lead; a `show_gap_seconds` change; a phase-1 prefix; a crash between append and render.

## B. Exact timing (O2-4, F minor) — simplify
B1. Replace the two-pass bullets with: a plan step appends at most `max_new` rows (the service's pacing stands). For the next row: run the scheduler on best-known lengths; analyse that row's piece; run the scheduler once more with the exact count; append run 2's pick if its piece is analysed, otherwise run 1's analysed pick (accepting a possible miss). A step always appends at least one row while the plan is short of `until_frame`. Written rows always carry exact counts. Remove "(those up to `until_frame`)".
B2. Estimate inputs: the scan carries what estimates need (each entry's size, the manifest's `total_duration_sec`, the voiced profile). A clip's length comes from its size and its own MP3 bitrate (read from its first frame header), not an assumed 64 kbps: unchunked, unbedded clips ship the provider's MP3. Unvoiced packages (for `--library delivered`) are keyed by the manifest's mtime and size and get the flat 4-minute clip allowance. `schedule` keeps estimates in memory and writes nothing.
B3. Render-step re-plan cap: greater than the interstitial pool size plus the rows in the lead.

## C. Announcements (O2-6, F minor)
C1. `later` goes on the **last** show boundary inside the block before X; every other internal boundary gets a station ID.
C2. A block's actual start (for its window and `miss`) is the start of its first show; the `next` clip before it belongs to the boundary.
C3. Truthfulness at placement is judged on the scheduler's in-memory lookahead, which must reach every block the announcement names.
C4. An announcement row records the block occurrence(s) it names; whether the promise held is judged when each named block's first show row is appended, and a broken one is logged `announcement-broken` and recorded in history.
C5. Missing audio: for the two-block form, fall back to the one-block form's clip if present, then to a station ID.
C6. Time phrasing: `[announce] time_format` in the clock file (default the builder picks, e.g. "11", "11:30"); ids hash the rendered text, so only operator edits (templates, titles, format) change ids, never a code default.

## D. Removals (O2-7, O2-10)
D1. Interstitials are NOT written to `timeline.json` (remove `kind: "interstitial"` entries, the notes/page/`recent` exclusion text, and the timeline touch points that existed only for them). The player's no-show text becomes the station name instead of "We'll be back shortly." (a small `antenna/public/nowplaying.js` change), which also covers the existing 2 s gaps; the builder checks the off-air path still shows its own text.
D2. Defer `anchors` to phase 4: remove the timeline `anchors` filling (leave `"anchors": []` as today). Rows carry `block` already, so phase 4 can build it.

## E. Clock file (O2-9, S r1)
E1. transmitter keeps a copy of the last clock that loaded in its workspace. An invalid `clock.toml` alerts and planning continues with that copy (render's skip path uses the same copy); with no valid copy ever, the implicit open block. Replace "fails the step ... plan untouched".

## F. Rollback (O2-5)
F1. The tolerant reader keeps unknown keys through a read-write round-trip (they survive a rollback and roll-forward). Interstitial rows keep string `slug`/`dir`/`key` (e.g. the clip's name, the folder name, its file-set key). The runbook's rollback step also removes `[interstitials]` from config.toml (the strict config of an older build rejects it).

## G. Measurement (F minor)
G1. Clock (a) is the naive script's five anchors (07:00 dead, 12:00 bluegrass, 19:00 dead daily, Sat 22:30 funk, Sun 15:00 dead-family) written in the new clock format; add "anchors read from the clock (a) file" to the script's named edits.

## H. Calls list
H1. Update: remove the frontier call; add append-only plan + plan lock; last-valid clock copy; interstitials out of the timeline; anchors deferred; time_format in the clock.

## Rejected
- Running a plan step every tick for status freshness: moot under append-only (status shows what will air).
