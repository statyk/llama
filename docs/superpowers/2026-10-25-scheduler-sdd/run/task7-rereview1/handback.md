### Finding Verdicts

1. **Partial line joined by next append: ADDRESSED.** `history.py` `append_aired` now checks the last byte when `f.tell() > 0` and writes `\n` first if it is missing. Test: `test_a_partial_line_left_by_a_crash_is_not_joined_by_the_next_append`. Mutant M7 (guard disabled) turns that test red. Residual, as asked: the fragment stays in the file and is still warned on every `load_aired` (see Out-of-Scope).
2. **`load_aired` admitted rows `recency()` cannot use: ADDRESSED for every field the finding listed.** `AiredRow.from_json` now checks:
   - `start_frame`/`end_frame` are int and not bool;
   - `epoch_id`/`kind`/`slug` are strings;
   - `start`/`end` are non-empty and parse with `grid.iso_to_us`. That check also rejects naive timestamps; I probed this.

   `test_unusable_rows_are_skipped_not_loaded` checks 6 bad shapes, that `recency` does not raise, and that nothing is duplicated. Mutants M10 (no ISO parse) and M11 (bool allowed) both turn it red. One field the finding did not list is still open (`package`): see New Breakage.
3. **Epoch guard: ADDRESSED.** In `service.py` `_append_history`, when `PublishState.epoch_id` is set and is not the station epoch, it raises `TransmitterError`. `_step` turns that into the `history` alert, and nothing is appended. A fresh workspace (no publish.json, so `epoch_id` is None) is not alerted. Test: `test_history_does_not_append_for_another_epochs_publish_state`. Mutant M5 (guard removed) turns it red. Mutant M4 (the `is not None` clause dropped, so a fresh workspace alerts) turns 5 existing service tests red, so the fresh-workspace case is pinned as well.
4. **Service wiring pinned: ADDRESSED.** The implementer did not run these mutants; I did, in a scratch copy, after proving `transmitter.__file__` and `tests_transmitter.__file__` resolve inside it. I named the expected red test before each run:
   - **M1, history moved before `publish_all`.** Predicted `test_history_runs_after_publish_and_sees_the_advanced_last`. That test, and only that test, went red.
   - **M2, `.last` changed to `listed_bound()`.** Predicted `test_history_uses_last_not_the_listed_bound`. Only that test went red.
   - **M3, `ran.add("history")` added.** Predicted `test_history_runs_after_publish...` (the `"history" not in ran` assert) and `test_history_failure_alerts_and_the_tick_completes` (the new caplog assert). Both went red, plus 6 other tick tests (`ValueError: step(s) ['history'] do not belong to observer 'tick'`).
5. **`end instant <= now` boundary: ADDRESSED.** `test_a_row_is_due_exactly_at_its_end_instant` checks both the exact end instant and one microsecond before it. Mutant M6 (`<=` changed to `<`) turns it red.
6. **Indexed `Recency`: ADDRESSED.** It now holds three dicts: by package, by clip slug, and by local `date`, whose values are tuples. The public methods are unchanged; `uses` is replaced by `count`, and nothing in src or in the plan's Tasks 8–10 reads `.uses`.
   - `with_piece` shallow-copies the three dicts. The values are ints or immutable tuples, and `_index` rebinds `by_date[d]` instead of mutating it, so the old index cannot be changed. Mutant M8 (`with_piece` aliasing `self`'s dicts) turns `test_artists_on_uses_the_clock_timezone` red.
   - Dedupe by `(epoch_id, start_frame)` still goes through `seen`, and `count == len(seen)`.
   - The order of `artists_on` results and the artist/year filters match the old code.
7. **Year via `pieces._date_parts`: ADDRESSED.** `recency` uses `_date_parts(d)[0]` and `Piece.year` uses the same function, so the two agree. A non-string date gives no year; `test_meta_with_a_non_string_date_gives_no_year` covers this.
8. **`local_date` takes `datetime.date`: ADDRESSED.** `_check_date` rejects a `datetime` first (it is a subclass of `date`) and then anything that is not a `date`. `artists_on`, `artist_years_on` and `with_piece` all go through it. Mutant M9 (`datetime` accepted) turns `test_a_datetime_for_a_local_date_raises` red.

The scratch suite at c9568c8 has 692 passed, 1 skipped and 1 failure, the expected `test_relay_key_matches_antenna` (antenna/src is absent in the scratch copy). All 11 mutants were caught.

### New Breakage in the Fix Diff

- **Minor: `package` is still not validated, so `recency()` can still raise on a loaded row** (`history.py`, `AiredRow.from_json`). I probed it: a row with `"package": ["x"]` or `{"a": 1}` passes `from_json`, then `recency` raises `TypeError: cannot use 'list' as a dict key` in `_index`, or in `meta_of` if that is a dict lookup. Because `Recency` is built inside the plan step, one such hand-corrupted line would stop planning on every tick. It needs a JSON array or object in `package`, so it is unlikely, but it is the same class as finding 2. Fix: require `package` to be `str | None` in `from_json`, and add the shape to the bad-rows test. An int `package` loads and does no harm.
- **Minor: `Recency` is no longer hashable.** It is a frozen dataclass whose fields are now dicts, so `hash(Recency())` raises `TypeError` (probed). Nothing hashes it today. If Task 9's frozen `SchedulerInput(rec: Recency)` is ever hashed or used as a cache key, that will raise. Either pass `@dataclass(frozen=True, eq=False)` or note it.

### Out-of-Scope Observations

- After finding 1's fix, the crash fragment stays in `aired.jsonl` for good, and `load_aired` logs a "skipped" warning on every call: each tick's history step, and each plan-step `recency` build once Task 11 wires it in. No data is lost and rows stay in order. The noise is permanent until someone edits the file by hand. Possible follow-ups: report it once per process, or have the runbook say how to remove the fragment.
- The epoch guard does not dedupe its own alert. `history` is an ungated event code, so a persistent epoch mismatch re-raises it every tick, and the Dispatcher's repeat window governs how often it is sent. This is the intended design; noted for the runbook.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. Two Minor items are open: `package` type validation in `AiredRow.from_json`, and `Recency` hashability.
