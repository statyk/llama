# Issues found in round 1, and how the spec now handles each

1. "Render frontier"/"frozen" undefined; files alone miss published (deleted) segments; re-plan could start early -> Planning "The frontier": R = max(listed_bound, highest local segment file); frozen = overlaps <= R; truncate and re-plan every step; first new row at last-frozen.end + gap.
2. Clock-edit latency described as phase 1's property -> "Clock edits" paragraph: new behaviour, reaches air once the frozen prefix has aired.
3. Gap rule unenforced (estimate->exact could leave silence) -> "Gap layout": start = prev.end + gap for every non-run_start row, interstitials included, asserted on write.
4. Estimate/exact handshake undefined; rows with estimates would loop in render -> "Exact timing": estimates from total_duration_sec + clip sizes; one exact re-pass; written rows always exact (write stops before an unanalysed piece); max_new pacing; clips always exact.
5. Announcement lock cascades through the lookahead and adds a row state -> lock REMOVED; "A promise kept where possible"; scheduler's own objective keeps it; broken = logged + history.
6. "Stay tuned for X at 11" would air as X starts -> `next` (at X's start, names X without time) and `later` (inside the block before) templates; selection and fallback rules.
7. Second block's profile not covered -> accepted limitation, counted announcement-broken.
8. Rotation rules could beat Goal 2 (single-artist Dead pool prefers fill over pairing) -> compromise order outranks every rotation rule; rules impossible in a pool not applied; bend counted only when a keeping option existed in the tier; concert gap vs pool airtime.
9. Soft-launch 80/20 wrong -> 60/34 by voiced airtime.
10. Compromise step 1 circular; structural fill reported as compromise -> Goals 3 reworded; fill reported by cause (pool short vs longer than max_shows).
11. Empty open pool -> PlanError -> exclude_profiles bends last; PlanError only when nothing eligible.
12. Removing [planner] seed breaks strict config -> seed kept, tie-break shuffle_rank(seed, slug).
13. Rollback to old reader wedges plan/render/publish -> tolerant PlanRow.from_json shipped and deployed first; runbook rollback target; never truncate plan.jsonl.
14. Miss/bend facts not persisted -> rows carry kind, block, nominal_start, miss, bends.
15. Interstitials hit package-shaped code (re-validation by slug -> infinite re-plan loop with watchdog fed) -> touch points listed; interstitials re-validate against the folder; failing clip removed for the call; hard cap on re-plans per render_step.
16. Interstitial timeline entries -> notes/page PUTs and recent pollution -> kind interstitial excluded from notes/page loop and recent; player shows station name (small antenna change).
17. Interstitials folder location -> default <station root>/interstitials/, invisible to all three scanners (cited); export into it when hugo's mount is writable.
18. aired.jsonl gated on wall clock, no idempotency -> appended only for published rows; identity (epoch, start_frame); backfill same rule.
19. Invalid clock.toml behaviour unstated -> clock read every plan step; invalid fails the step with an alert, plan untouched; schedule --clock to check; status "no clock: open all week".
20. status running the scheduler -> status reads persisted rows only.
21. DST zero-length block -> dropped, tested.
22. Baseline script cannot produce the comparison -> named edits, committed beside the evidence doc; scheduler run over >=50 weeks.

## Removed by the revision
- The announcement lock (committed blocks persisted past the lead).
- The `one`/`two` templates.
- "80/20".
