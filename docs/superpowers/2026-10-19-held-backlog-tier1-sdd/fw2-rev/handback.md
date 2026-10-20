VERDICT: CHANGES REQUIRED

Reviewed 1089b76..00b0c6e (c106103, 00b0c6e) in snapshot /var/folders/yn/jlwxryrj1ds7jpvw931jk1jm0000gn/T//fw2-rev-snap-41gGMM (git archive 00b0c6e; shadowing proven: llama.__file__ inside the snapshot). No worktree files changed, no commits.

## Spec compliance (fw2-brief.md)
| Item | Status | Where |
|---|---|---|
| 1. `reapply_show(allow_structure_change=False)`; structure-changed + not dry-run + not allowed -> `skipped: structure changed`, nothing written; added to outcome comment | ✅ | reapply.py:53-54, 70-71, 108-110 (gate after the dry-run return, before the fresh brief and every write) |
| 1a. CLI `--allow-structure-change`, verbatim help | ✅ | cli.py:3195-3198, 3230 |
| 1b. list form allowed when `row["outcome"] == "structure-changed"` | ✅ as written, ❌ in effect (Critical C1) | cli.py:3326-3328 |
| 1. predicted row now structure-changed skipped; recorded `retryable: true`; re-run skips again | ✅ | cli.py:3367-3370 |
| 1. names form prints `... -> skipped: structure changed (re-run with --allow-structure-change after checking)`, exit 0 | ✅ | cli.py:3235-3238 |
| 2. catch-all arm `FAILED slug: Type: msg`, progress outcome consistent; typed arms + names form unchanged | ✅ | cli.py:3288-3295, 3352 |
| 3. dry-run download when no manifest OR any manifest track missing; reuses an existing helper | ✅ | catalog.py:157-170 (`needs_audio_download`, reuses `_tracks`), cli.py:3359 |
| Tests listed in the brief | ✅ (the list-form one is tautological, see C1) | test_reapply.py:844-937 |
| classify / compute_legs / write order untouched; no general row-vs-classify check | ✅ | |
| Do-not-retune names (Global Constraints) | none in the diff | |
| Commit subjects verbatim | ✅ | |

## Findings

### Critical
**C1 — the list-form allowance can never fire on a real structure_changed_list; every structure-list row would be skipped forever.** cli.py:3328 allows only `row.get("outcome") == "structure-changed"`, but the harness writes structure-list rows with `outcome = would_be` (scripts/replay_holds.py:758 `_list_row(s, r, r.get("would_be"))`), and the plan's Contracts fix that shape: rows carry `"outcome": "clears|needs-brief"` (plan lines 109-114; would_be per line 89). Measured on the real harness output: every `structure_changed_list.json` under ~/.llama-harness (cmp-D-held, cmp-F2-slice-all, cmp-G2-all, cmp-G2-slice-held, cmp-fw6-all) has 0 rows with outcome `structure-changed` (e.g. cmp-fw6-all: 11 rows, all `needs-brief`). So `llama reapply --from-list structure_changed_list.json` — the plan's G6 path for checked structure changes — now prints `skipped: structure changed` for every row, and `--allow-structure-change` is silently ignored with `--from-list`, so there is no list-form way to apply them. Direction is safe (nothing is written), but item 1(b) is dead on contract-conforming input. The defect is in the brief (it names the discriminator verbatim); the implementer followed it. The test (test_reapply.py:887-889) hand-edits a row to `"structure-changed"`, a shape the harness never produces, so it passes over the bug (test data not where the thing decides). M2 is "caught" only by that tautological row.
Fix (orchestrator's call, one of):
 (a) the harness stamps structure-list rows, e.g. `{"...", "outcome": would_be, "structure_changed": true}` (an additive Contracts field), and reapply allows on `row.get("structure_changed") is True`; the test builds its rows through `replay_holds._list_row`/the compare writer, not by hand. Existing lists are refused anyway after any commit (sha must equal `code_identity()`), so no on-disk list needs migrating.
 (b) honour `--allow-structure-change` in the list form (pass it into `_reapply_list`; the operator gives it only for the structure list), and drop the row-outcome test.
Either way also refuse (or honour) `--allow-structure-change` combined with `--from-list`; today it is accepted and ignored.

### Important
None beyond C1.

### Minor
- M-a (cli.py:3355-3360): dry-run of a predicted row whose replay is now structure-changed prints `would: x -> structure-changed` and counts it as a fresh brief/download, while the apply will skip it. Compliant (brief says "not a dry run"), but the dry run no longer predicts the apply; consider printing `would: x -> skipped: structure changed` when not allowed (pass the allowance into the dry-run branch).
- M-b (cli.py:3375): summary still says "first-time downloads", now that it also counts re-downloads of purged delivered shows. Rename to "downloads".
- M-c (test_reapply.py:922-937): the purged-audio test uses one track, so `any`->`all` in `needs_audio_download` survives (M4 below). Add a two-track manifest with one file present.
- M-d: no direct test of `needs_audio_download`'s unreadable-manifest / missing-`filename` arms (both return True); cheap to add.

## Mutation spot-check (scratch copies under /var/folders/yn/jlwxryrj1ds7jpvw931jk1jm0000gn/T//mut-fw2-rev-SMRRkP, PYTHONPATH shadowing proven per mutant, private PYTHONPYCACHEPREFIX, predictions logged before flips; run over test_reapply.py, unmutated baseline 52 passed)
| mutant | predicted test | result |
|---|---|---|
| M1 reapply.py gate `and not allow_structure_change` -> `and False` | test_structure_changed_is_skipped_unless_allowed_and_writes_nothing | CAUGHT by it + test_cli_names_form_structure_changed_needs_the_flag + test_list_structure_row_... (claim confirmed) |
| M2 cli.py list allowance -> `True` | test_list_structure_row_applies_but_a_predicted_row_that_turned_structure_changed_is_skipped | CAUGHT (claim confirmed; but see C1: catches only against a hand-made row shape) |
| M3 (extra) skipped row `retryable=` -> `False` | same list test | CAUGHT |
| M4 (extra) `needs_audio_download` `any` -> `all` | predicted SURVIVE | SURVIVED (M-c) |
| M5 (extra) `needs_audio_download` returns False once a manifest exists | test_dry_run_counts_a_purged_delivered_show_as_a_download | CAUGHT |

## Suite (snapshot, `python -m pytest -q -p no:cacheprovider`)
3786 passed, 1 skipped, 8 deselected, 26 warnings in 147.79s
