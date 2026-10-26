### Spec Compliance

**Verdict: mostly compliant, with one placement defect.** The `later` announcement is not confined to the last internal boundary of a block. On realistic clocks it repeats within a block, measured below.

Everything else checks out:
- interfaces;
- gap layout;
- first-piece rules;
- truthfulness;
- the R12 predicate;
- the missing-audio fallbacks;
- `to_row`;
- determinism and live/one-shot agreement.

**How I reviewed it**
- **Pure move (20107c5):** verified by a sorted-line diff of the old `scheduler.py` against the new `scheduler.py` + `_blocksearch.py`. The only differences are the re-export import block, `Sequence`/`rules`/`Recency`/`Piece`/`ClockConfig` imports, two blank lines and docstrings. It is a pure move.
- **`_BlockRun` refactor (2fd11d9):** read against the removed `fill_block` loop. It is faithful: same `block_start`, the same unchanged `prev_artist`, pools built once from the initial ctx, the same convergence bound.
- **Remaining passes:**
  - R12 (`announce.py`, `test_announce`, `test_cli`);
  - Task 8 test gaps (0f05984);
  - the projection (`scheduler.py:186-618`) against the brief and spec "Planning" / "Station IDs and announcements";
  - `test_scheduler.py`.
- **Probes:** read-only scripts against the worktree's code, run from the scratchpad, with nothing mutated:
  - truthfulness and placement over 60 random clocks;
  - live versus one-shot over 25 random clocks;
  - `later` placement over 14 days × 3 realistic clocks × 4 seeds;
  - `fill_block` called directly for one horizon case.

**Named risks**
- **(a) Step function.** Every Interfaces/Algorithm item the brief lists holds:
  - gap layout from `inp.start_frame` (`_add`, `scheduler.py:374-378`);
  - the first piece is the boundary after a show row and a show after an interstitial row (`after_show`, `:346`);
  - `next` before X's first show, except at a run start;
  - station ID least-recently-used first, ties on `tie_rank` (`:438-443`);
  - one-block fallback when only Y fails (`_forms`/`_try_next`, `:448-477`);
  - missing audio: two-block → one-block → ID → nothing;
  - `names` on announcement pieces;
  - `miss` only on each occurrence's first show (`:557`).

  The exception is "`later` only at the last internal boundary of W" (Important 1). The step function is spec-consistent. Live/preview agreement for given lengths is what the spec demands, and phase A then phase B would not have given it with ID clips of differing lengths. Accept.
- **(b) Truthfulness.** X's window is judged with each candidate clip's own length. Y is judged on X's complete projected run (`xrun.complete()[-1].landing`). Degraded X or Y is excluded. Untitled X gets no announcement.
  - The 60-clock probe (4,352 pieces) found **0** announcements whose named occurrence's first projected show was outside its window or degraded.
  - The `later` X-start is an estimate (`last.frames + B`), not the projection. This is an accepted prediction under the spec ("counted under `announcement-broken`").
- **(c) R12.** The one predicate `announce.two_block_ok` is used by `needed()` (`announce.py:92`) and by placement (`scheduler.py:453`).
  - It is a named module constant `TWO_BLOCK_MAX_HOURS = 12`, inclusive at exactly 12 h and pinned at 12 h + 1 µs.
  - "Different block" means a different block name.
  - `needed()` adds "Y titled"; placement adds "Y titled, not degraded, in window". That difference is correct, because degraded depends on the pool and not on the clock.
- **(d) `used`, `rec` and `now_us`.**
  - Persisted rows are never re-added to `rec`: `_row_piece` pieces are not `_add`ed.
  - `used` is bounded live by `now_us`.
  - With `now_us=None` (the measurement), `used` only grows. `_excluded` (`_blocksearch.py:468`) drops it wholesale once a pool is exhausted, so it stays sane but diverges from live (Minor 4).
- **(e) Continuation.** The continuing occurrence is found by exact `(block, nominal_start)` key against the live clock (`:382-396`). A clock edit that changes the name or start falls back to `_entry`. At a run start the named occurrence is used only if the restart lies inside it. Phase-1 rows fall back to `_entry` with `placed=()`.
  - A mid-block `miss=True` matches the spec's definition (a block's actual start is its first show).
  - It will count one miss per cutover or outage, and one at the start of a measurement that does not begin on a block boundary. Task 13 should know this; it is not a defect.
- **(f) Bends.** Per-row bends are deduped per block (`placed_bends`, including persisted rows). So a sum over a block's rows counts each bend once, which is what Task 13's "bends by rule" sums. Fill cause is on fill rows. Caveats are in Minor 3 and Minor 6.
- **(g) `to_row`.** It sets every scheduler field, takes `role` from `PlannedPiece`, and `kind`/`package` from the piece. `announcement_broken` is left at its default for Task 11. The round-trip through `to_json`/`from_json` is pinned.
- **(h) Determinism and timing.**
  - Sets are only membership tests or are re-ordered through `_BEND_ORDER`. Clips are sorted by slug. IDs use `min` with `tie_rank`.
  - **Live versus one-shot:** 25 random clocks with ID clips of 4–40 s and announcement clips of 3–30 s, about 30 h each: every one-shot prefix equals the live rows.
  - **Speed:** 14 days in about 0.4 s on realistic clocks.
  - **Live cost:** confirmed reasonable. A whole horizon is computed for one piece (Minor 7).

### Strengths
- The step-function design is principled. Every decision depends only on laid-out state, and `_run_at` reuses a run only when its own layout agrees with the exact start. That is exactly the continuation-closure property, and it makes live and preview agree by construction. My independent random probe confirmed it.
- The lazy `_BlockRun` keeps `fill_block` unchanged (the Task 8 suite is untouched) and makes per-show re-planning affordable.
- Truthfulness is implemented carefully:
  - each form is judged with its own clip length;
  - Y is judged on X's real projected run;
  - degraded and untitled exclusions are applied;
  - R12 is shared through one predicate.
- The tests are behavioural and sharp:
  - voiced-but-forbidden two-block clips prove R12 in placement;
  - `test_appending_first_pieces_reproduces_one_projection` uses three ID lengths so re-planning is exercised;
  - the `used`/`now_us` test is built so only `used` can explain the result;
  - the bends test is checked against `fill_block`;
  - 17 mutants were reported killed, three of them only after tests were added.
- The `SchedulerInput` and `PlannedPiece` docstrings state the caller contracts (`rec` holds persisted rows; `now_us` semantics) that Task 11 needs.

### Issues

#### Critical
None.

#### Important

**1. `later` is not confined to the last internal boundary; a block can carry two or three `later` announcements.** (`scheduler.py:504-536`, `_try_later` `:479-500`)

*What happens*
- `boundary()` decides `kind == "last"` from the run at `m = s + ID + gap`, using the station ID's length.
- It then places the `later` clip, whose length is different.
- The next `show()` starts at `s + later + gap`. That is not `run.start_of(k)`, so `_run_at` re-plans from the exact start.
- In an open block or a fill block, the bounded search re-composes the remainder for every few seconds of shift, because it prefers landing close to nominal. The re-plan therefore often adds shows.
- The following boundary is then "last" again and places another `later`.

*Measured* (read-only probe; library pool, 4 ID clips of 5–30 s, all announcement clips voiced at 4–20 s, 14 days, 45 occurrences per run):

| Clock | Occurrences with more than one `later`, per seed |
|---|---|
| REPRO_CLOCK | 4, 1, 0, 2 |
| DAYCLOCK | 0, 0, 3, 3 |
| A day/Dead/late clock | 1, 0, 3, 1 |

- That is up to 7% of occurrences, roughly one audible double announcement a week.
- On random clocks I saw `later, show, later, show, later, show` in a single block: "Stay tuned for T1 at …, followed by T2 at …" three times running.
- Seed 30 of my random probe produced `later, show, id, show, later, show`.

*Why it matters*
- The spec says: "At the **last** show boundary inside the block before X … place a `later` … Every other show boundary inside a block gets a station ID."
- Listening experience is part of the stakes.
- The announcements stay truthful (0 untruthful hits), which is why this is Important and not Critical.
- The implementer's Concern 1 calls this "rare". It is not rare.

*Fix*
- (i) Decide `later` with its clip in place. In `_try_later`, take the run from `s + clip.frames + gap` (via `_run_at`, or a fresh `_new_run` you then adopt as `self.run`) and require `step(0).shows` non-empty and `step(1).shows` empty. Otherwise try the next form, then fall back to the ID, whose decision at `m` stands.
- (ii) Allow at most one `later` per occurrence. This is derivable from state, so live and preview still agree: any persisted or projected boundary row with `role == "later"` carrying this occurrence makes later "last" boundaries IDs. It is needed as well as (i), because the boundary after the last show is still decided at the ID length and can re-plan one more show in.
- Add a property-style test over varied ID and clip lengths, like the probe: at most one `later` per occurrence, and every `later` followed by exactly one show of its own occurrence when possible (at least at most one).

#### Minor

**2. The `until_frame` horizon is counted in clock time, not projected frames** (`horizon`, `scheduler.py:568-575`).
- When the plan runs *ahead* of the clock (blocks landing early in tier 2), `project(until_frame=…)` returns a projection that ends before `until_frame`.
- Measured in 5 of 25 random clocks. Seed 18 ended at 20.1 h of a 33.5 h span after playing five occurrences that cover 66 h of clock.
- Every occurrence of the span is still planned, but `schedule --days N` and the measurement's frame coverage fall short.
- Fix: keep extending until a projected piece also reaches `until_frame`, then go `ahead` more.

**3. Fill cause is judged from an estimated `block_start`, and one block's fill rows can carry different causes.**
- `_BlockRun` computes `start − Σ(placed + B)`, but the placed shows were laid out with the actual clip lengths.
- Each re-planned run recomputes `cause`.
- Fix: pass the exact block start, which the projection knows (the first show row's or piece's `start_frame`), to `_BlockRun`, as an optional parameter that defaults to the current formula.

**4. `now_us` makes `used` depend on wall-clock time.**
- The spec says lookahead is "never from `now`, so unchanged inputs give the same choice on every step". With `now_us`, a show row that airs between two steps leaves `used`, so the choice can change between steps, and a preview taken at 10:00 can differ from the live step at 20:00.
- This is inherent in the controller's "persisted-but-unaired" contract, so it is not the implementer's error.
- A frame-anchored alternative avoids it: persisted show rows ending after `start_frame − <lead>`.
- With `now_us=None` (the measurement), `used` never releases a pick until the own pool is exhausted. The measurement's repeat-gap figures therefore describe a stricter regime than live, where a show is released once it airs. Tell Task 13, or pick the frame anchor.

**5. `ahead=0` can return `[]`** when the first piece is the boundary into the next occurrence.
- Task 11's `project(...)[0]` would then raise `IndexError`.
- Fix: clamp `ahead` to ≥ 1, or raise `ValueError`, and document it.

**6. Per-row bends can drop a bend that a re-plan undid.**
- `own = step(k).bends − step(k+1).bends` uses the *old* run's suffix.
- If show k bent rule r, the old suffix also bent r (so r was deferred to a later show), and the block is then re-planned so no later show bends r, then r is never written even though show k bent it.
- It is rare, and `BlockPlan` equality is pinned only in the no-re-plan case. Note it for Task 13's counts.

**7. Live cost.**
- `project` lays out the whole horizon to return one piece. Under `IMPLICIT_CLOCK` that is about 3 days of 24 h open blocks: about 0.3 s here, about 1 s on hugo, twice per appended row.
- Fine against `WatchdogSec=45min`, but an early exit would make the live step nearly free. Options: a `limit=1` keyword, or `ahead=1` in Task 11, which the implementer showed is safe for piece [0].

**8. Out of scope, Task 8 (not this diff).**
- `MAX_FILL = 3` means a long profile block with small `max_shows` cannot be filled. Example: a 17.5 h `max_shows=1` block lands tier 2 at +3 h.
- The projection then plays the following occurrences hours early (each gets ≥ 1 show), racing ahead of the clock.
- Nothing is silent and nothing is cut, but a block would air far from its nominal time.
- Worth a clock-validation warning or a `schedule` note; flagged for the controller only.

**9. Typing nit.**
- `boundary()` returns `PlannedPiece | None | _STOP`, and the `_try_*` helpers return untyped 4-tuples.
- A small `NamedTuple` for the choice and a typed sentinel would make `scheduler.py:504-536` easier to read.
- `scheduler.py` (618 lines after the move) is otherwise well factored.

### Deviations
- **Step function instead of phase A then phase B:** accept. It satisfies every brief interface item except Important 1, which is a fix inside the design, not a reason to revert. It is the only way to get live/preview agreement with clip lengths that vary.
- **Required `SchedulerInput.now_us`:** accept for this task. The Task 11 and Task 13 briefs must be updated to pass it; the plan's `SchedulerInput` signature lacks it. See Minor 4 for the spec tension, which needs a controller decision on now-anchored versus frame-anchored.
- **The caller's `rec` must hold persisted rows and the projection never re-adds them:** accept. It matches `history.recency`.
- **`exclude_profiles` bends once per block:** accept. It follows the controller's "counted once per block" ruling.
- **Mid-block entry records `miss=True`:** accept. It matches the spec's definition of a block's actual start. Task 13 should know it counts cutovers and outages.
- **A fresh start inside the next window starts that block now:** accept. The current block's remainder is shorter than the early wiggle and could not land the next block better, and the spec's "occurrence in progress" call is otherwise kept.
- **`ahead=0` can be empty:** accept with Minor 5.

### Assessment
**Task quality:** Needs fixes

**Reasoning:** The core is sound and well tested:
- the pure move is verified;
- the refactor is faithful;
- the step-function projection gives exact gap layout and agrees live versus one-shot on independent random clocks;
- announcements are truthful (0 violations in about 4,400 probed pieces);
- R12 is shared and pinned.

One spec placement rule fails in a way listeners would hear: `later` is not confined to the last internal boundary, and on realistic clocks up to 7% of occurrences carry repeated `later` announcements. The fix is local:
- decide `later` with its own clip in place;
- allow one `later` per occurrence, derived from the rows;
- add a property test.

The Minors can ride with that fix or be handed to Tasks 11 and 13.
