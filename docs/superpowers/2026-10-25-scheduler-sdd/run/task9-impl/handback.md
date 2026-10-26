# Task 9 handback: the projection (occurrences, interstitials, announcements)

Status: DONE_WITH_CONCERNS (the concerns are design notes for Tasks 11 and 13; nothing is broken)

## Commits (branch playout-scheduler, on top of 392dfde)
- b32f700 R12: `announce.TWO_BLOCK_MAX_HOURS = 12` + `announce.two_block_ok(x, y)`, used by `needed()`
- 20107c5 pure move: the block search internals moved to `transmitter/_blocksearch.py`; `scheduler.py` re-exports what the tests use
- 0f05984 Task 8 test gaps (a) and (b), each mutation-checked
- 2fd11d9 `fill_block` now pulls its runs from a lazy `_BlockRun`. Behaviour is unchanged and the suite stays green.
- da80197 the projection: `SchedulerInput`, `PlannedPiece`, `project`, `to_row`, plus `test_scheduler.py`
- c981d23 import order and one comment

Every commit was green under `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`. The final run: **787 passed, 1 skipped** (21.8 s).

## What was built
- **`SchedulerInput`** is `frozen=True, eq=False` and is never hashed. It has the fields the brief lists, plus a **required `now_us: int | None`** (Decision 4).
- **`PlannedPiece`** is frozen and has the fields from the brief plus `end_frame`. Its docstring states the per-row bends rule.
- **`project(inp, *, until_frame=None, ahead=2)`**:
  - It is pure. It returns every piece whose occurrence is between the continuing one and position L. L is `ahead` past the continuing occurrence, or, with `until_frame`, `ahead` past the occurrence in progress at `until_frame`.
  - A boundary piece counts as the occurrence of the show that follows it.
  - Every piece is laid out exactly. The first piece starts at `start_frame` with `run_start` as given; each later piece starts at the previous end + `gap_frames`.
- **`to_row(pp, seq)`** sets `kind`, `package` and every scheduler field. `role` comes from `PlannedPiece`.
- `PlanError("no eligible packages to plan")` is raised only when the pool holds no show.

## Decisions
1. **How the projection is structured (deviation from the brief's phase A then phase B).** I did not fill whole blocks with an estimated boundary and then lay the clips out afterwards. The projection is a step function over the pieces laid out so far:
   - **Each show** is the first show of a `fill_block` run started from that show's *exact* start.
   - **Each boundary** is decided by a run started where the next show would begin after the actual next station ID (or after one gap when there is no ID pool).
   - **The boundary estimate** (gap + typical ID + gap, or one gap with no ID pool) is used only for the later shows inside a run and for predicted landings.

   Why: ID clips differ in length. A block filled from estimated positions disagrees with the live step, which continues from exact persisted starts and so would choose different shows. Errors would also add up across blocks. Because every decision depends only on the laid-out state, appending piece [0] and projecting again reproduces the rest by construction.

   Cost stays linear because runs are lazy: about 2–3 searches per show plus one complete run per titled-block judgment. A run is reused only when its own layout agrees with the exact start, so reuse matches the continuation-closure property.
2. **Lazy `_BlockRun`** (`scheduler.py`). `fill_block` pulls every run. It has `step(i)`, `start_of(i)`, `complete()`, `is_fill(i)`, `cause` and `degraded`. All existing `fill_block` tests pass unchanged.
3. **Pure move** of the search into `_blocksearch.py` (580 lines). I checked by sorted-line diff that no code line changed. `scheduler.fill_block`, `BlockPlan`, `_Tier`, `_Ctx` and `_sequence_violations` all still import from `scheduler`.
4. **`now_us` was added to `SchedulerInput` as a required field.** A persisted show row counts as unaired when its end is after `now_us`; `None` counts every persisted show row as unaired.
   - It is required so Task 11 cannot forget it. `plan.jsonl` is never trimmed, so "every persisted row" would grow without bound and would block preferred, already-aired shows.
   - Task 11 and `schedule` pass `now`. The measurement (empty plan) and the tests pass `None`.
5. **How `used` and `rec` are built:**
   - **`used`** = persisted unaired show slugs ∪ every show the projection has picked. That includes the current occurrence's placed shows, which is equivalent because `_excluded` treats `placed ∪ used` the same either way.
   - **`rec`**: the caller's `rec` must already contain every persisted row (Task 11 builds it with `history.recency(aired, rows, ...)`), and the projection **never re-adds a persisted row**, so counts stay sane.
   - Each projected piece (shows and clips) is added once, with `with_piece`, at its exact start and its local date in the clock's time zone.
   - `test_appending_first_pieces_reproduces_one_projection` mirrors this: the live loop adds each appended piece to `rec` once.
6. **Per-row bends:**
   - A show row carries the rules its own run bent that the run continuing after it does not (`step_k.bends − step_{k+1}.bends`), minus any rule already written on an earlier show row of the same occurrence (persisted rows included).
   - So each rule a block bends sits on exactly one of its show rows: the show that bent it. A sum over a block's rows counts each bend once, and their union is `BlockPlan.bends` (pinned against `fill_block` in `test_block_bends_match_the_block_plan_and_sit_on_the_show_that_bent_them`).
   - **`exclude_profiles`** is written **once per block**, on the block's first show drawn from the bent open pool. The brief said every such show; I followed the controller's "count each bend once" rule. Bend order is `rules.RULES` then `exclude_profiles`.
7. **Fill cause on rows:** a fill show (its run is tier 1 with `fill_from == 0`) carries that run's `cause`.
8. **Choosing the continuing occurrence:**
   - **Normal case:** the occurrence named by the last row's `(block, nominal_start)` when the clock still yields it. `placed` is that occurrence's persisted show rows. Pieces come from the pool, using the row's `frames`; a show missing from the pool gets a stand-in. Placed own rows (`fill is None`, not degraded) stay in the own pool even if their profile moved.
   - **At a run start:** that occurrence is used only if the restart falls inside it. Otherwise the occurrence in progress at `start_frame` is used.
   - **Fallback** (phase-1 rows, a fresh run, an edited clock): the occurrence in progress at `start_frame`, with `placed=()`. Extra rule I added: if `start_frame` already lies in the *next* occurrence's window, that next block starts now, on time.
9. **`miss`** is set on each occurrence's first show only: the start is outside `[lo, hi]`. Entering mid-block (phase-1 cutover, a fresh run after an outage) therefore records `miss=True` on that block's first show. I kept this so the rule depends only on the rows, which is what makes live and one-shot agree.
10. **Announcement candidates:**
    - Two-block first, but only when `two_block_ok(X, Y)` holds and Y is titled and not degraded. Then the one-block form.
    - Each candidate is judged on X's window with its own clip length.
    - For the two-block form, Y must land in its window by X's projected run, started from X's start with this clip in place.
    - A missing clip moves to the next candidate, then to a station ID, then to nothing.
    - X untitled or degraded means no announcement.
    - `later`: X's start is predicted as clip + the block's last show + the boundary estimate. Y is judged with that last show added to `rec` and `used`.
11. **Horizon:** judgments look past L as needed (lazily), so the first piece does not depend on `ahead` as long as `ahead ≥ 1`. With `ahead=0`, a first piece that is the boundary into the next occurrence falls beyond the horizon, and the result is empty.
12. **When the ID pool changes between steps (empty ↔ non-empty):** the layout of appended rows stays exact by construction, because each piece starts at the previous end + gap (+ clip + gap). The boundary estimate only changes predictions and the `block_start` that `fill_block` uses to judge the fill cause.

## The R12 change and its tests
- `TWO_BLOCK_MAX_HOURS = 12`; `two_block_ok` requires: `y` is not None, a different block name, and `y.nominal − x.nominal ≤ 12 h`.
- `needed()` uses two-block forms only when it holds and Y is titled.
- New tests:
  - the predicate itself: exactly 12 h passes; 12 h + 1 µs, the same block and `None` fail;
  - a daily block that follows itself needs only its 2 one-block clips;
  - 12 h 1 min versus 11 h 59 min.
- The existing `test_needed_skips_untitled_blocks...` now also asserts D gets one-block forms only.
- `test_cli`'s daily-block export changed: 4 clips became 2, and "exported 3" became "exported 1".
- Placement uses the same predicate. `test_next_announcement...` and `test_titled_open_block...` now include a *voiced* two-block clip that R12 forbids, and assert it is not used. Mutant M1 confirmed this pins it.

## Test results and TDD evidence (log: `task9-impl.log`)
- **R12:** RED was an ImportError on `TWO_BLOCK_MAX_HOURS`. GREEN: 32 passed (targeted), then 751 passed, 1 skipped (full suite).
- **Projection:** RED was an ImportError on `PlannedPiece`. The first GREEN attempt had one test bug (`shows_of` was filtering by block name, not by occurrence) and was fixed. The `used` test was redesigned around a previous occurrence: within one occurrence `placed` already excludes the show, and over three days `used` runs out of alternatives.
- **Final:** 787 passed, 1 skipped. `test_scheduler.py` has 34 test functions (35 cases): the brief's 24 plus 10 more:
  - two variants of the `later` rule;
  - fresh start inside the next window;
  - run start after an outage;
  - `used` versus `now_us`;
  - the boundary estimate (median ID);
  - `to_row` round-trip;
  - fill cause on rows;
  - two bends tests.
- **Mutation checks** (scratch copy shadowed through `PYTHONPATH`, `-B`, `transmitter.__file__` verified inside the copy; the red test was predicted before each run). There were 17 mutants and all were killed, M1, M2 and M15 only after I added tests:
  - M1 placement ignores `two_block_ok` → survived at first, because the clip was missing anyway → I voiced it in the tests → killed;
  - M2 `later` at every internal boundary → survived at first, because X's window rejected it → added the wide-window test → killed;
  - M3 ID rotation reversed → killed;
  - M4 persisted rows left out of `used` → killed;
  - M5 a run reused whatever its start → `test_appending...` red;
  - M6 / M7 the Y / X window checks on `next` → killed;
  - M8 bends not deduplicated → killed;
  - M9 no next-window entry → killed;
  - M10 `miss` on every show → killed;
  - M11 the 12 h bound exclusive → killed;
  - M12 horizon ignores `until_frame` → killed;
  - M13 row bends = the whole run's bends → killed;
  - M14 run start continues the named occurrence → killed;
  - M15 `later` without the Y check → survived at first → added `test_later_falls_back...` → killed;
  - M16 fill cause left off rows → killed;
  - M17 no `next` at all → killed.
- **Task 8 gap mutants:**
  - (a) "longest" leaving out the placed shows → red: `test_fill_cause_is_judged_on_the_whole_own_pool_from_the_block_start`;
  - (b) `block_start` without the boundary term → red: `test_block_start_counts_the_boundary_after_each_placed_show`.
- **Live versus one-shot stress (outside the suite):**
  - Clocks: the reproduction clock, `IMPLICIT_CLOCK`, and a clock-a-like busy clock with `exclude_profiles`.
  - 3 days each; 0–5 ID clips of random lengths, 80% of the announcement clips present, random history and start.
  - **13 runs, 0 mismatches.**

## Timing
- `test_project_over_a_3000_piece_pool_is_fast` (current + 2, three titled blocks): **0.21 s** against a 2 s bound.
- The implicit clock over 7 days of the fixture: 1.17 s.
- A live step (one `project` call, current + 2) on the 300-show fixture:
  - about 0.3 s with `IMPLICIT_CLOCK`, where each occurrence is a 24 h open block;
  - about 20–30 ms with profile-block clocks.

## Files changed
- `packages/transmitter/src/transmitter/announce.py`
- `packages/transmitter/src/transmitter/_blocksearch.py` (new; moved code)
- `packages/transmitter/src/transmitter/scheduler.py`
- `packages/transmitter/tests_transmitter/test_announce.py`
- `packages/transmitter/tests_transmitter/test_cli.py`
- `packages/transmitter/tests_transmitter/test_scheduler_block.py`
- `packages/transmitter/tests_transmitter/test_scheduler.py` (new)

## Self-review
- I read the diff. The import order is fixed. Python 3.11: every changed file compiles under 3.11.15. The suite was not run under 3.11; the Debian-12 script is the gate for that.
- No IO, and no hashing of `SchedulerInput`, `Recency` or `Occurrence`. Occurrences are keyed on `occ.key` everywhere (`_Occs.index`, comparisons).
- `fill_block`'s behaviour is unchanged, as the full Task 8 suite shows.

## Concerns (for the controller and Tasks 11 and 13)
1. **A `later` clip that is not the typical ID length triggers a re-plan.** The block is re-planned from the exact start after the clip. In rare cases that changes the remaining show count (0 or 2), so the `later` is not followed by exactly the block's last show. Live and one-shot agree on this, but the "last internal boundary" claim can be off by one. A plain ID boundary is decided at the actual ID length, so only the `later` case has this.
2. **The fill cause is judged from an estimated block start.** `fill_block` computes its `block_start` from `start − Σ(placed + boundary estimate)`. After clips of non-typical length this is off by seconds, which can affect only the structural / pool-short label. An exact block start would need a new `fill_block` parameter.
3. **A mid-block entry records `miss=True`** (Decision 9). Task 13's `status` and the measurement might want to set aside the first block after a cutover or outage.
4. **Live cost under `IMPLICIT_CLOCK`.** About 0.3 s per `project` call on this Mac; hugo is probably around 3× slower, and Task 11 calls it twice per row. Task 11 could pass `ahead=1`: piece [0] does not depend on `ahead ≥ 1`.
5. **Pre-existing, Task 8 / rules:** with `concert_gap_days = 0`, `rules.recency_term` gives every aired show a flat 0.9. Least-recently-aired ordering is then lost and `tie_rank` decides, so once `used` releases a show the same few shows recur. The spec says least recently aired first still applies. I did not change this (operator ruling 2: do not change Task 8's behaviour).
6. **For Task 11:** pass `now_us`, build `rec` from `history.recency(aired, rows + appended, …)` exactly once per row, and never pass a `rec` that already contains projected pieces.
