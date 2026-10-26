### Finding Verdicts

1. **(Important) `later` confined to the last boundary, once per occurrence: ADDRESSED.**
   - (i) `scheduler.py:524` `_try_later` now judges each form with its own clip in place. The run is taken from `s + clip + gap`, and `step(k).shows` must be non-empty while `step(k+1).shows` is empty. On failure it restores the run decided at `m`.
   - `boundary` (`scheduler.py:579-580`) always falls back to `_Choice(id_clip, "id", ...)` when no announcement qualifies. A boundary with an ID available therefore never ends up with neither a `later` nor an ID. This holds for each failure path: missing clip, block not one show from its end, X out of window, and Y failing on every form.
   - (ii) `later_done` is derived from the rows (`:383`, matched on the occurrence key). The projection sets it on placing a `later`, and `_enter` resets it.
   - Live and preview cannot disagree on (ii). A persisted `later` row carries the block it plays in, which is the same key the one-shot projection checks. Mutant m3 (drop the key match from the row-derived `later_done`) went red on exactly `test_appending_first_pieces_reproduces_one_projection`, as I predicted.
   - Probes on head:
     - `p7` (3 clocks × 4 seeds × 14 days): 0 occurrences with more than one `later`, and 0 whose `later` is not followed by exactly one show.
     - `p1`, 800 random clocks: 0 non-tail `later-not-last` cases, against **79** at base c981d23.
   - Residual, accepted as prediction: if a re-plan after the `later`'s show adds another show (the real ID is shorter than the estimate B), the `later` stops being the last boundary. The next boundary gets an ID because of (ii). I never observed this in 800 seeds.
2. **(R14) frame-anchored `used`: ADDRESSED.**
   - `now_us` is gone, and `used_at` (`:447`) is half-open `[F-W, F)` over persisted and projected show starts.
   - The run-reuse check (`:475`) compares `used ∪ placed`, which is exactly what `_excluded` depends on, so reuse stays equivalent to a fresh run.
   - Mutant m1 (`bisect_right` at the lower bound) went red on exactly `test_used_window_is_half_open_on_the_frame_line`, as I predicted.
   - Live vs one-shot:
     - `p4`, 40 clocks × 30 h: 0 mismatches.
     - A 72 h variant, 25 clocks, so the window slides for two days: 0 mismatches.
   - The `later` Y-judgment run adds the last show through `extra_used`, which equals what the real X run sees at `x_start`.
3. **(Minor) horizon by projected frames: ADDRESSED.**
   - It terminates on any pool. Each loop iteration appends at least one piece with positive frames, because `show` always places one or raises `PlanError`. `_STOP` cannot fire while `last_pos == sys.maxsize`.
   - The cost is proportional to the occurrences needed to cover `until_frame` in frames. It is bounded, but it grows on clocks whose blocks land very early.
   - Test gap (Minor): mutant m2 removed the `max(clock_pos, ...)` at `:687`. I predicted it would survive, and the scheduler, rules and block tests all stayed green. The "never before the clock horizon" clause is unpinned; it only matters when the frame line runs ahead of the clock.
4. **(Minor) exact block start: ADDRESSED.**
   - `_BlockRun(block_start=...)` is passed only for the current occurrence with shows placed (`:465`). Otherwise the estimate equals the first show's exact start.
   - `_fill_cause` depends only on `own_all` and `block_start`, so the block gets one cause. `fill_block` is unchanged.
5. **(Minor) `ahead < 1`: ADDRESSED** (`:671`, test present).
6. **(Minor) typing: ADDRESSED.** The `_Choice` NamedTuple is at `:338` and `_STOP: Final = _Stop()` at `:335`. The return types are annotated, and the string forward reference is fine on 3.11.
7. **(Operator ruling / R16) gap-0 recency: ADDRESSED.**
   - `rules.py:59` uses `GAP0_RECENCY_HORIZON_DAYS = 365` and float days. Never-aired shows stay at 1.0.
   - The gap rule is still off at 0: `gap_hit`, `viol` and `violations` are untouched, so bend accounting is unchanged.
   - There is no per-pool path that passes `gap_days=0` for a gap > 0 clock, so gap > 0 behaviour is unchanged.
   - `_blocksearch` treats a time-varying recency term exactly as it already does for gap > 0, so I see no Task 8 ordering hazard.
   - Mutant m4 (horizon replaced by 1e-9, i.e. a flat 0.9) went red, as I predicted, on `test_gap_zero_disables_the_gap_rule_without_dividing`. I ran it with `-x`. The implementer's RED run shows the other two gap-0 tests.

### New Breakage in the Fix Diff

- **(Minor) The sliding `used` window is a new mid-block re-plan cause that the runs do not predict, so two-block Y predictions break slightly more often.**
  - Each `_BlockRun` freezes `used` at its creation start. When a show leaves the 24 h window partway through a block, `_run_at` rebuilds the run correctly, as a live step would, but the block's shape can change after an announcement was judged on the old prediction.
  - `p1`, 800 random clocks, untruthful `next`/`later` named blocks:
    - base: 5 seeds, 8 lines
    - head: 7 seeds, 10 lines
  - I traced seed 195. b2 was re-planned at its boundary after p3 because `r0` left the window, the block ended one show early, and the announced Y (b3) started 18.8 min before its window.
  - This is inside the spec's accepted limitation ("a prediction ... counted under `announcement-broken`"), so it does not block.
  - Suggested fix: at creation, give each run step its `used` from the window at that step's start. The shows before the run's start are fixed then, and its own picks are in `placed`. The `used` half of the reuse check would then always pass when the start matches. That removes both this re-plan source and most of the extra cost below.
- **Cost (not blocking).** Implicit clock, live loop appending `project(...)[0]` with the default horizon, measured sequentially:
  - per call: median 0.50 s at base, 0.61 s at head (+22%, not 2×; max 0.79 → 0.82)
  - with `until_frame = start + 48 h`: 0.98 → 1.13 s (the base number is inflated by a concurrent run)
  - At hugo's roughly 3× and two calls per appended row, that is about 3.7 s per row. A 48 h initial fill is a few minutes, well under `WatchdogSec=45min`. Profile clocks are unaffected, per the implementer.

### Out-of-Scope Observations

- **The `later` predicts X's start with the boundary estimate B** (gap + typical ID + gap). The real boundary into X is usually a `next` clip of a different length. Seed 711: a `later` named b0+b1 with b0 `max_shows=1`, and Y (b1, wiggle 5) landed 8.6 min late. This class predates the fix (the old code used the same estimate). It could be tightened by predicting with X's `next` clip length.
- `test_relay.py::test_relay_key_matches_antenna` fails only in my scratch copy, because it reads `antenna/src`, which `git archive ... antenna/templates` does not extract. The rest of the suite: 796 passed, 1 skipped. Environmental, not caused by the fix.
- The implementer noted a Task 8 behaviour: a tier-0 `()` ends the block after the first fill lands. I did not examine it.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. Two Minor items remain, neither blocking:
- the unpinned `max(clock_pos, ...)` (mutant m2 survived);
- the sliding window as a small new source of broken two-block predictions, with the per-step frame-window `used` suggested as the remedy, which would also recover the +22% live cost.
