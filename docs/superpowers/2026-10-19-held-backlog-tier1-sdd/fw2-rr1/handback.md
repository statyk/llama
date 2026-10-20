VERDICT: APPROVED

Re-review of 9d5884b (scope e7a029e..9d5884b; e7a029e ignored). Read and run only in snapshot `git archive 9d5884b` at /var/folders/yn/jlwxryrj1ds7jpvw931jk1jm0000gn/T//fw2-rr1-snap-7nAgXn (removed at the end); shadowing proven (llama.__file__ inside the snapshot). No worktree files changed, no commits.

## Fix-file compliance (orch-r4/fw2-fix-r1.md, ruling (b))
| Item | Status | Where |
|---|---|---|
| C1: row-`outcome` allowance removed; list form honours `--allow-structure-change` | ADDRESSED ✅ | cli.py:3211-3212 (flag passed to `_reapply_list`), 3253 (signature), 3327 (passed to `reapply_show`) |
| Without the flag: `skipped: structure changed`, retryable true, hint `(re-run with --allow-structure-change after checking)` same as names form | ADDRESSED ✅ | cli.py:3368-3372 |
| Flag never silently ignored in either form | ✅ | names form cli.py:3232; list form above |
| List test rewritten with REAL-shape rows | ADDRESSED ✅ | test_reapply.py:885-906. `_list_file` (test_reapply.py:422-428) writes `{slug, outcome:"clears", briefing, digests}` under `{sha, config_fingerprint, written_at, rows}` = exactly `replay_holds._list_row`/`_list_doc` (scripts/replay_holds.py:688-695), and a structure-list row's outcome is `would_be` (replay_holds.py:758) — "clears" is that shape. Comment cites `_list_row` (no line number; fine). |
| Minor (a)/M-c: two-track dry-run test, one present one missing | ADDRESSED ✅ | test_reapply.py:929-939 |
| Minor (b)/M-d: unreadable/malformed manifest test | ADDRESSED ✅ (no code change needed: today's behaviour already returns True) | test_reapply.py:942-954; catalog.py:157-170, `_tracks` 224-229 |
| Minor (c)/M-b: `first-time downloads` -> `downloads` | ADDRESSED ✅ | cli.py:3380, README.md:267, tests 583/820/840. Plan/spec docs keep the old words (historic record — acceptable). |
| M-a (dry-run prediction vs. skip) | NOT ADDRESSED — not in the fix file; remains a Minor, optional | cli.py:3355-3360 |
| Commit subject verbatim | ✅ | 9d5884b |
| Do-not-retune names in diff | none | |

## Findings
Critical: none. Important: none.
Minor:
- m1 cli.py:3366-3367 comment is now stale: "the operator may add the flag **or move the row to the structure list**" — moving a row to the structure list no longer changes anything (that list also needs the flag). Fix: "the operator may re-run with --allow-structure-change after checking; a re-run without it just skips it again."
- m2 README.md:255-270 never mentions `--allow-structure-change` or how to apply `structure_changed_list.json` (now that the list needs the flag, the operator's G6 path is undocumented there). Fix: add `llama reapply --from-list structure_changed_list.json --allow-structure-change   # after hand-checking each` to the example block.
- m3 (pre-existing M-a, carried) with the flag absent, a dry run of a row whose replay is structure-changed prints `would: x -> structure-changed` and counts its brief/download, though the apply would skip it.
- m4 test_reapply.py:953-954 pins `{"tracks": []}` -> False (no download). Defensible (nothing to fetch), just noting it is pinned behaviour, not a safety choice.

Note on semantics (by ruling, not a defect): the flag now applies to every structure-changed row of whichever list it is given with, including predicted_list; the operator's checking discipline is the only gate.

## Mutation spot-check (MROOT /var/folders/yn/jlwxryrj1ds7jpvw931jk1jm0000gn/T//mut-fw2-rr1-jqZU6W, one copy per mutant, PYTHONPATH shadowing proven per mutant, private PYTHONPYCACHEPREFIX, predictions logged before flips; run over test_reapply.py, 59 tests)
| mutant | predicted test | result |
|---|---|---|
| M2' `_reapply_list` passes `allow_structure_change=False` to reapply_show | test_list_form_skips_structure_changed_rows_unless_the_flag_is_given | CAUGHT by it (only it) — claim confirmed |
| M2'b `reapply()` drops the kwarg to `_reapply_list` (default False) | same | CAUGHT by it (only it) |
| M4 `needs_audio_download` any -> all | test_dry_run_counts_a_purged_delivered_show_as_a_download | CAUGHT by it + test_needs_audio_download_counts_an_unreadable_or_malformed_manifest_as_a_download — claim confirmed |
| M7 list skip `retryable=` -> False | list test | CAUGHT |
| M8 list skip hint suffix dropped | list test | CAUGHT |

## Suite (snapshot, `python -m pytest -q -p no:cacheprovider`)
3793 passed, 1 skipped, 8 deselected, 26 warnings in 136.02s
(matches the implementer's claimed 3793.)
