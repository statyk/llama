# Task 5 handback: station mark writer; deliver over a marked copy; --fixed

Status: DONE_WITH_CONCERNS (the concerns are minor interface notes; see the end)
Commit: f53a3931 feat(station): awaiting_fix writer; deliver replaces a marked copy, --fixed selector

## What was implemented
- `packages/llama/src/llama/station_mark.py` (new): MARK_KEY, COMPARED (verbatim from the brief),
  StationRefused(LlamaError), StationUnreadable(StationRefused) with text
  `<slug>: station copy unreadable: <detail>` (one line); read_station_manifest, mark_of,
  destination_voiced, write_mark, clear_mark, put_back, manifest_differences, emcee_running.
  Rewrite algorithm as pinned: read bytes+dict; add/remove only MARK_KEY (key order kept: an existing
  key keeps its slot, a new one is appended); trailing newline as the original had it;
  `json.dumps(..., indent=2, ensure_ascii=False)`; unique temp `.manifest.json.llama-<hex>.tmp` in the
  same dir, opened `xb`, flushed via `catalog._flush_to_disk`; re-read bytes just before rename, on a
  difference remove temp and raise StationRefused (nothing written); `os.replace`; re-read and require
  every other key equal to the dict read and MARK_KEY == written value (absent for clear). On a mismatch:
  `put_back(expect_sha256=sha(after), data=before)`, which only replaces while the file still holds this
  call's bytes; either way StationRefused. Any exception before/at the rename removes the temp.
  put_back: checks sha first, swaps in with the same pre-rename byte check, verifies after.
  clear_mark on an unmarked copy (absent or null) raises StationRefused
  `<slug>: the station copy is not marked; nothing to clear` (Task 11's string), untouched.
  manifest_differences: COMPARED names in COMPARED order whose canonical JSON text differs
  (`json.dumps(sort_keys=True)`); `tracks.<f>` compares the per-track list; absent == null.
- `packages/llama/src/llama/campaign_gate.py` (new): ps_lines() and tool_processes(), ported from
  rekey's `llama_processes`/`_runs_llama`; scripts/rekey_overrides.py unchanged.
- `cli.py`:
  - `_deliver_one`: `marked = mark_of(dest_manifest) is not None`; after the voiced refusal (and before
    the gate, same reason as the voiced check: no re-download only to be refused), a voiced+marked
    destination with --replace-voiced whose library manifest has `manifest_differences == []` raises
    `_EqualMarkedCopy` with the fixed string `refusing to replace <slug>: the re-processed show equals
    the voiced station copy; keep the voicing with: llama clear-mark <slug>`. Route: `voiced or marked or
    <track list differs>` -> `_replace_destination` (never the overlay for a marked copy).
  - `deliver --fixed` selector; counted in `other_selector`, so `--replace-voiced --fixed` and
    `<name> --fixed` refuse with today's strings. `_deliver_batch(..., fixed=)` filters after
    `apply_selector` and before `split_held` with `_fixed_for_delivery`: not `awaiting_fix`, record read
    and `processed` non-null, station manifest marked. No station dir/manifest -> excluded. An
    unreadable station manifest is KEPT so the existing preflight lists it
    `(refused: destination manifest unreadable)` instead of dropping it silently. `--fixed` with no
    `--dest` and no delivery_path prints `no --dest given and no delivery_path in config`, exit 1.
  - A voiced, marked, processed show in a --fixed batch is refused by today's voiced route (batch text),
    bytes untouched.

## Dry-run list (existing test expectations changed)
None. `git diff` on test_deliver_cmd.py has 0 removed lines; only new tests appended. No other existing
test file touched.

## Tests run
- RED (before implementation):
  `./.venv/bin/python -m pytest -q packages/llama/tests/test_station_mark.py packages/llama/tests/test_campaign_gate.py packages/llama/tests/test_deliver_cmd.py`
  -> 2 collection errors: `ImportError: cannot import name 'station_mark' from 'llama'`,
  `cannot import name 'campaign_gate' from 'llama'`.
  `./.venv/bin/python -m pytest -q packages/llama/tests/test_deliver_cmd.py` -> 7 failed, 60 passed
  (failed: test_marked_destination_is_always_replaced, test_replace_voiced_refuses_an_equal_marked_copy,
  test_replace_voiced_replaces_a_changed_marked_copy [pin; fails only because its setup imports
  station_mark], test_deliver_fixed_selects_marked_and_processed, test_deliver_fixed_combines_with_other_selectors,
  test_deliver_fixed_refuses_replace_voiced_and_a_name, test_deliver_fixed_with_no_marked_copy_delivers_nothing).
  test_unmarked_voiced_destination_keeps_todays_route (pin) passed at RED, as a pin should.
- GREEN: station_mark + campaign_gate -> 19 passed; test_deliver_cmd.py -> 67 passed, then 69 after two
  tests added post-implementation (test_deliver_fixed_lists_an_unreadable_station_copy_as_refused,
  test_deliver_fixed_needs_a_station; not RED-first, they cover the two choices I made beyond the brief).
- Full suite: `./.venv/bin/python -m pytest -q -p no:cacheprovider` -> 6084 passed, 1 skipped,
  8 deselected in 74 s (baseline 6055 + 29 new).
- Mutation check (scratch copy under the session scratchpad, PYTHONPATH-shadowed, `llama.__file__`
  verified inside the copy, predicted test named per mutant): 7/7 CAUGHT by the predicted test —
  M1 drop pre-rename byte check -> test_write_mark_detects_a_concurrent_rewrite; M2 put back
  unconditionally -> test_write_mark_detects_a_rewrite_after_the_rename; M3 skip post-rename verify ->
  same; M4 marked not replaced -> test_marked_destination_is_always_replaced; M5 no equality refusal ->
  test_replace_voiced_refuses_an_equal_marked_copy; M6 --fixed ignores processed ->
  test_deliver_fixed_selects_marked_and_processed; M7 scripts count as emcee -> test_tool_processes_emcee.
  Unmutated copy: 88 passed.

## Files changed
- packages/llama/src/llama/station_mark.py (new)
- packages/llama/src/llama/campaign_gate.py (new)
- packages/llama/src/llama/cli.py
- packages/llama/tests/test_station_mark.py (new, 15 tests)
- packages/llama/tests/test_campaign_gate.py (new, 4 tests)
- packages/llama/tests/test_deliver_cmd.py (10 tests appended)

## Self-review findings
- Strict surface: the writer never goes through `Manifest`; only MARK_KEY changes (asserted: every
  other key equal, `tracks` json-identical, dj_* untouched, write+clear round-trips byte for byte).
- An unreadable/malformed station manifest is refused and never written (missing file, missing dir,
  invalid JSON, JSON list; all four entry points), asserted byte-identical afterwards.
- No temp is ever left behind (asserted after success, pre-rename refusal, post-rename refusal,
  flush failure).
- Residual window (documented in the module docstring): a write landing between the last byte check and
  the rename is overwritten undetected.
- No llama<->emcee import; Global-Constraint constants untouched.

## Concerns / interface notes for the controller
1. `tool_processes` gained an optional keyword `self_script: str | None = None` beyond the brief's
   signature. Needed to re-run rekey's cases exactly (rows 701/703 are `scripts/rekey_overrides.py`
   under other pids, which rekey excludes by its SELF_SCRIPT). Callers using the brief's signature are
   unaffected.
2. The "a `.py` under `scripts/`" rule applies to `tool="llama"` only (`_SCRIPTS_RUN`). For emcee it
   would make any repo script (replay_holds, bulk_apply in another process) block marking as "emcee
   running", and the spec says the emcee check cannot see such scripts anyway. Pinned in the emcee test.
3. `write_mark`/`clear_mark` do NOT call `emcee_running()` themselves; the callers (Task 11 clear-mark,
   Task 15 mark batch) do, per their plan text. Calling it inside would make tests depend on the dev
   machine's process table.
4. `json.dumps(..., indent=2, ensure_ascii=False)`: the brief's "…" left the kwargs open; I chose
   `ensure_ascii=False` so non-ASCII text in a pydantic-written manifest keeps its bytes (the dict is
   equal either way). emcee itself writes with the default ensure_ascii=True.
5. `mark_of` returns `{}` for a non-null, non-object mark (it is still a mark per the contract): callers
   must test `is not None`, never truthiness. Documented in its docstring.
6. `manifest_differences` compares canonical JSON text, so `600` vs `600.0` differ; both sides come from
   the same pydantic model, so this should not arise in practice.
7. The equality refusal sits ahead of the deliver gate (like the voiced check), so a held, voiced, marked,
   equal show is told to `clear-mark`, which itself refuses held shows. Ordering choice; flag if wrong.
