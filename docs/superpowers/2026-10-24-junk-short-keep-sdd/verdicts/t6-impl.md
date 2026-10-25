# Task 6 handback

Status: DONE. Commits: b04041c (replay record), c34c99d (harness re-key + compare gates), and the probes commit (HEAD).
Suite: `./.venv/bin/python -m pytest -q` -> 4949 passed, 1 skipped, 8 deselected.

## Implemented
- replay.py: ShowReplay gains filenames, short_kept, segues, breaks, flags (defaulted); replay_show fills them from gathered.show / legs.flags.
- replay_holds.py: `run --rekey-overrides` (shadow always; legacy file re-keyed via override_keys.rekey_raw using show.json filenames, then strip; failure copies unchanged and records rekey_error; row `rekeyed`; arm header `overrides_rekeyed`). `_shadow` keeps its 2-tuple; new `_shadow_full` adds meta. Re-key not in compute_legs. Digests remain the real file's.
- compare: `_gates` refuses (exit 2, names the shows, per arm) any unreplayable row containing "overrides.json unreadable" or the legacy/mixed/dangling texts; no apply lists when either arm is rekeyed (summary line updated).
- taper_probe: `_fix_applied` translates filename values via row filenames, else root/shows/<slug>/show.json; ints as is. title_hygiene_probe: row gains `stripped_positions` (1-based).

## TDD
RED first for each batch (AttributeError on record; unknown flag / no refusal for harness; filename test failures), then GREEN. Tests: test_record_carries_filenames_short_kept_and_flags; test_rekey_shadow_maps_legacy_and_leaves_the_library_alone; test_rekey_then_strip; test_rekey_failure_is_recorded_not_raised; test_rekey_leaves_filename_and_empty_overrides_alone; test_unflagged_run_has_no_rekey_stamp; test_compare_accepts_rekeyed_candidate_and_writes_no_apply_lists; test_compare_refuses_an_arm_with_overrides_validation_unreplayable (4 texts, both arm positions); test_taper_probe_translates_filename_breaks; test_title_hygiene_probe_reads_filename_titles.

## Existing tests changed
- test_replay.py::test_show_replay_to_dict_has_the_contract_keys_plus_date: key-list pin extended with the 5 new fields (brief Interfaces).
- Synthetic int-valued arm rows in test_taper_probe untouched (still pass).

## Decisions
- Refusal lives in `_gates` (before any write), matched by substring, so the "LlamaError: <slug>: ..." prefix and 200-char truncation do not matter.
- Mixed files are not re-keyed (classify != legacy); replay then yields the mixed refusal, which compare rejects.
- A rekey run always uses the shadow path, so every row has a `stripped` key (possibly `{}`) and `rekeyed`.
- title_hygiene_probe's existing `stripped` is left as recorded; the positions are an added key.

## Files
packages/llama/src/llama/replay.py, scripts/replay_holds.py, scripts/taper_probe.py, scripts/title_hygiene_probe.py, packages/llama/tests/test_replay.py, scripts/test_replay_holds.py, scripts/test_taper_probe.py, scripts/test_title_hygiene_probe.py.

## Self-review / concerns
No mutation run done. A rekey-failed legacy show surfaces as unreplayable (legacy refusal), so a compare of such an arm refuses by design. No constants from Global Constraints touched.
