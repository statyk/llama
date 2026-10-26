### Spec Compliance

**Compliant, with no missing or extra scope and nothing misread.** I checked each point against the brief, the spec ("Rotation history") and the controller's additions:

- `aired_rows_due` (history.py:87-94):
  - The bound is `(pub_last + 1) * SEGMENT_FRAMES`, compared with `PlanRow.end_frame`. That property returns `cut_frame` when the row was cut (layout.py:54-56), so a cut end counts.
  - `pub_last is None` gives `[]`.
  - The end instant is `epoch_us + frame_to_us(end_frame)`. At a segment boundary this equals `Epoch.start_us(n)`, which is exactly `n * D_US`.
- The service passes `PublishState.last` (service.py:259). That is what the spec names ("the end of segment `PublishState.last`"). It does not pass `high_water`/`listed_bound`, and must not: those can run ahead of confirmed PUTs.
- `append_aired`:
  - Identity is `(epoch_id, start_frame)`, read back from the file.
  - It writes with `open("a")`, then flush and fsync.
  - With no file, the first call is the backfill, under the same rule.
  - A phase-1 row comes out as `kind="show", package=slug`.
- `load_aired` skips any bad line with a warning and never raises. `from_json` ignores unknown keys. `bends` lists become tuples of strings.
- The row records everything the spec asks for: kind, package, block, start/end, miss and bends. The "which set" field belongs to future set pieces and is correctly absent.
- `Recency`:
  - It is the union of aired rows and persisted plan rows, deduped by identity. Aired rows from another epoch keep their own ISO `start`, which is correct: they cannot be converted through the current epoch.
  - `last_aired_us` covers shows and keys on `package or slug`. `last_used_us` covers clips by slug.
  - `artists_on`/`artist_years_on` use the clock timezone.
  - `with_piece` returns a new frozen index and leaves the old one alone (the test checks both).
  - It reads the right attributes of the Task-6 `Piece`: `kind`, `slug`, `package`, `artist`, `year`.
- Service wiring (service.py:332-337):
  - The history step runs after `publish_all` inside its own `_step("history", …, resolves=("history",))`.
  - It is not added to `ran` and not declared in `STEP_CODES`/`OBSERVER_STEPS`, so it is an ungated event code. That matches the global constraints.
  - It never stops the tick.
  - It does not run on the fail-closed early return when `publish.json` is unreadable, which is correct.
- The `_step` docstring and the except-arm comment now name `PlanLocked` (service.py:226-249).
- The systemd test's watchdog count going from 5 to 6 is correct: `_step` pings in `finally` for every step, so the history step adds exactly one ping per tick. It hides nothing, because the count still pins the plan-analysis pings separately.
- ⚠️ Whether `Recency` scales to Task 8's actual call pattern is something the diff cannot show (see Minor 4).

### Strengths

- The module is small, pure where it can be, and cleanly separated from the IO. `aired_rows_due` is testable without a workspace.
- Identity-based dedupe plus `open("a")` and fsync gives real idempotency across restarts. The cut-end test asserts both halves: the recorded end, and that the uncut end would not have been due.
- The timezone test uses a real boundary case: 02:00Z counts on the previous local day in New York.
- Persisted-state permissiveness (unknown keys, phase-1 rows) is tested.
- The service failure test injects a real exception and checks that the alert becomes active.
- Mutation check: moving `history` into `ran` is caught by the existing gate test `test_a_successful_step_resolves_its_level_codes`, so the "not in `ran`" invariant is pinned, though not by the new test.
- Touched test files run clean: 81 passed, 1 skipped, no noise.

### Issues

#### Critical
None.

#### Important

1. **A crash mid-append leaves a partial line that the next append joins onto. The bad line then stays in the file for good and is warned about every minute.** history.py:126-130.
   - **What I saw.** Probe: one good row, then a simulated crash leaving `{"epoch_id": "e", "start_fr` with no newline, then `append_aired`. The first new row was written onto the end of the partial line, producing one corrupt line, so that row was lost for that tick. The next tick re-appended it (identity not found), so the file now reads frames `[0, 882, 441]`, out of order.
   - **Why it matters.** The data does heal through identity. But the file is append-only, so the corrupt line is never removed. `append_aired` calls `load_aired` on every tick once anything has aired, so a single SIGKILL or power loss on hugo produces a warning every minute forever, plus out-of-order rows for the phase-4 "recently played" reader. This was a named risk for persisted, append-only state, and the fix is two lines.
   - **Fix.** Before writing, if the file exists, is non-empty and does not end in `\n`, write a `\n` first. Optionally, record "partial last line" once per load instead of on every read. Add a test: partial line, then append, then the new row loads.

2. **`load_aired` accepts rows that `recency()` cannot use. One such row would make Task 8's plan step raise on every tick.** history.py:55-62 and 198.
   - **What I saw.** `from_json` checks only that the required keys exist. Probes:
     - A row without `start` (it defaults to `""`) loads cleanly, then `recency()` raises `ValueError: Invalid isoformat string: ''` at `grid.iso_to_us(a.start)`.
     - A row with `"start_frame": "0"` loads, its identity `("e", "0")` never matches the int identity, and `append_aired` appends the row a second time (it returned 1).
   - **Why it matters.** "Permissive on read, a corrupt line is skipped, never raises" is meant to keep one bad row from breaking consumers. Here the bad row gets past the loader and breaks the consumer instead. Task 8 runs `recency` inside the plan step, so one malformed row (from a hand edit or a foreign writer) would stop planning, and the lead would drain toward the fallback. `planner._parse_row` already sets the precedent for this kind of type check.
   - **Fix.** In `from_json`:
     - require `start_frame`/`end_frame` to be ints and not bools, like `planner._INT_FIELDS`;
     - require `epoch_id`, `kind` and `slug` to be strings;
     - require `start` to be a non-empty string that `grid.iso_to_us` accepts.

     `load_aired` then skips a failing row with its existing warning. Add a test that loads such a row and calls `recency` successfully on the rest.

#### Minor

1. **`append_aired` does not check the epoch.** service.py:257-259, history.py:117. It never compares `PublishState.epoch_id` with `st.epoch.epoch_id`. `publish.py:222` refuses in that case. If `publish.json` were left over from another epoch after an operator re-epoch, the history step would append current-epoch plan rows as aired, based on the old epoch's `last`, in the same tick that publish alerts. Those rows are permanent in an append-only file. The scenario needs an operator mistake, but the guard is one line: skip, or alert `history`, unless `state.epoch_id == epoch.epoch_id`.

2. **The new service tests do not pin what they claim.** test_service.py:878-909. Mutants run in scratch copies:
   - Moving the history step *before* `publish_all` gives 65 passed. Expected red: `test_tick_appends_aired_rows_after_publishing`. It stayed green.
   - Passing `listed_bound()` instead of `.last` gives 72 passed, so nothing distinguishes `last` from `high_water`.
   - Putting `history` into `ran` passes `test_history_failure_alerts_and_the_tick_completes`. Its comment "end_observation does not raise" asserts nothing, because `alerts.end_observation` swallows the error. Only the pre-existing gate test catches it.

   Fixes:
   - assert that `"alert end_observation failed"` is not in `caplog`;
   - add a direct `_append_history` test with `last < high_water`;
   - check placement, for example with a fake `publish_all` that advances `last` and a check that this tick's history used it.

3. **The `<=` boundary at end == now is unpinned.** history.py:94. Mutating it to `<` gives 72 passed. Add one test case at `now_us == end instant`.

4. **`Recency` does linear scans that Task 8 will call in a nested loop.** history.py:160-182. Every `last_aired_us`/`artists_on` call scans all uses. The uses (aired rows plus all plan rows) grow without bound, and scoring calls `last_aired_us` for every candidate in every slot. After a year that is thousands of uses × hundreds of candidates × tens of slots in each plan step on hugo. Indexing by package and by local date when building (`with_piece` copying small dicts) keeps the interface unchanged. Better to do it now than to discover it in Task 8.

5. **`_year_of` duplicates `pieces._date_parts` and disagrees with it.** history.py:139-143. It accepts `"1977"` or `"1977-xx"` where `Piece.year` returns `None`, so `with_piece` and `recency` can disagree on the same show's era. It also raises `TypeError` on a non-string date from `meta_of` (probe: `int date raised TypeError`). Reuse `pieces._date_parts(d)[0]`.

6. **Smaller points:**
   - Aired rows contribute `start_us` at millisecond precision (from ISO), while plan rows and `with_piece` contribute microseconds. This is harmless at day scale.
   - `append_aired` re-reads both whole files and rebuilds an `AiredRow` for every past row on every tick. That is O(history) per minute; fine for now, but worth noting.
   - The ISO-string `local_date` key works for the `datetime.date` Task 8 will pass (via `str()`), but a `datetime` would silently match nothing. Consider typing the parameter as `date` only, or normalising with `.isoformat()` on a `date`.
   - In the reworded comment in the systemd test (test_systemd.py:46), the ", plus" clause now reads awkwardly.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The implementation matches the spec and the brief throughout: published-and-past rule, cut ends, identity, backfill, permissive read, the ungated `history` step outside `ran`, and `PublishState.last`. The structure is clean. Two robustness gaps in the persisted-state path, both demonstrated by probes, should be fixed before Task 8 builds on this:

- A partial line from a crash poisons the next append and leaves a warning every minute forever.
- The loader admits malformed-but-JSON rows that make `recency()` raise, which in Task 8's plan step would stop planning.

Both are small fixes, each with a test. The Minor items, especially the epoch guard and the test-pinning gaps, should go in the same fix round.
