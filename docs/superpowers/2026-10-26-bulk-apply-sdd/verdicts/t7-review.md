# T7 review: emcee honours `awaiting_fix` (BASE 003a5404..HEAD 402d138c)

### Spec Compliance

- ✅ Spec compliant. Every interface in the brief is present and matches the spec's emcee clause and the Contracts' "emcee:" fixed strings:
  - `station.AWAITING = "awaiting-fix"` (station.py:24).
  - `awaiting_fix_reason(manifest: object)` (station.py:28-46) is transmitter's function line for line (transmitter/station.py:129-145): whitespace collapse, 200-char cut with `…`, plain line for any non-null malformed value. It also returns None for a non-dict manifest, as the brief's `object` signature requires. It never raises.
  - `PackageStatus.awaiting_fix` (station.py:71).
  - `package_status` returns AWAITING before `assess`, with `reasons=[line]` and `**identity(...)` kept (station.py:327-330).
  - `_STATUS_STATES` and the `--state` help are updated.
  - The JSON row carries `"awaiting_fix"`.
  - The summary has an `awaiting fix` column, per profile and in the total, not counted in `other`.
  - `run` prints `skip <slug>: awaiting fix from llama` and does not set `failed` (cli.py:510-512).
  - `_process_one` re-reads the manifest and raises the exact refusal, with the malformed variant, before `resolve_voicing`, preflight and any spend (cli.py:262-268).
- `rewrite_manifest` needed no change (raw dict). It is pinned by `test_rewrite_manifest_preserves_awaiting_fix`.
- The emcee-never-imports-llama rule holds. The 21 "from llama" hits in the diff are the fixed string, and the one "transmitter" hit is a docstring.
- Every test named in the brief exists. `test_malformed_mark_is_awaiting_fix_without_raising`'s voice half was split out as `test_voice_refuses_a_malformed_mark`, which is fine.
- Dry-run list checked against the diff: exactly one existing expectation moved (`test_status_summary_rows_counts_labels_and_order`). It is under the "awaiting fix column" clause, and the edit adds the column and nothing else.
- ⚠️ Cannot verify from diff:
  - CLAUDE.md does not yet mention emcee's `awaiting-fix` state. That is deliberate: it belongs to Task 18 (plan line 568). The controller should confirm it lands there.
  - The implementer's RED evidence is partial (`-x`). The mutation checks below stand in for it.

### Strengths
- The port is faithful. `MAX_REASON_CHARS` and its truncation match transmitter, and the shape test covers string, list, number, bool, `{}`, an empty reason, a non-str reason, whitespace collapse and the 500-char cut (test_station.py).
- The guard sits in `_process_one`, which `run` and `voice` share, ahead of every config resolution. Spend, preflight and manifest writes are all checked with byte-equality and spend stubs (test_voice_cmd.py, test_run_cmd.py).
- `test_process_one_rereads_the_manifest` reads first with the same `Package`, then marks, then calls. It would catch a cached manifest.
- The mark wins over a structurally broken manifest: `identity` is total, and AWAITING returns before `assess` can raise.

### Issues

#### Critical
None.

#### Important
None.

#### Minor
1. cli.py:506-512: the `move_problem` check runs before the AWAITING skip. A marked package whose recorded move targets an unassigned profile therefore prints `error: <slug>: …` and exits 1, not `skip <slug>: awaiting fix from llama`.
   - It is consistent with how a ready package is treated, and marking does not change the exit status (that package already errored before it was marked).
   - But the brief says a marked package "does not count as a failure", and neither order is pinned by a test.
   - Fix: decide which order is wanted and add one test for it.
2. cli.py:263-268: the refusal is rebuilt by `removeprefix("awaiting fix from llama: ")` on the status line. That couples it to `awaiting_fix_reason`'s output text.
   - Mutant d2 shows it is pinned.
   - A small helper returning the cleaned reason, or both strings, would be sturdier.
3. cli.py:254: the `_process_one` docstring's "Order (strict surface)" list does not name the awaiting-fix refusal as its new first step.
4. test_run_cmd.py:791: `_forbid_spend` duplicates `helpers.forbid_spend` (helpers.py:232), which patches the same two attributes. Reuse the helper.
5. test_status_cmd.py:770-772: the identity test asserts only `is not None` for `voiced_by`, `tts` and `tts_now`. A row filled with wrong values would pass. Assert the expected values instead: `"house"`, the recorded tts dict, and the `tts_now` dict.
6. cli.py:628-637: `voice --fresh` validates its stems before `_process_one`. On a marked package, `voice --fresh X` therefore refuses with "has no DJ audio to re-roll" or "no clip …", not the awaiting refusal. No spend happens either way. This is cosmetic.

### Checks run
- Untouched-names grep over the diff: SHORT_FRACTION_OF_MEDIAN, MIN_PLAUSIBLE_SEC, MIN_MEDIAN_SAMPLE, DURATION_TOLERANCE_S, audio_reuse, purge_package_audio, STOP_AFTER_LLM_FAILURES, load_list, briefing_reusable, AGREEMENT_FLOOR, WRITTEN_DURATION*, SHORT_CORE_LETTERS, SHORT_TAG_WINDOW, STEM_SUBSTRING_MIN, _ENTRY_LEADER and `import llama` all had 0 hits. The diff touches only `packages/emcee`.
- Named risk: other `process_package` callers that would bypass the guard. I grepped `packages/emcee/src`. The only caller is `_process_one` (cli.py:292), which both `run` (cli.py:554) and `voice` (cli.py:642) reach.
- Named risk: `Package.manifest()` caching would defeat the re-read. package_io.py:44-54 reads the file on every call.

### Mutation results
- Scratch copy: `git archive 402d138c packages/emcee packages/herder` was extracted to `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-bulk-apply/829c3eab-317d-4890-b354-066008e43de7/scratchpad/t7-mut/`, with one copy per mutant.
- Each run started from an empty cwd, with `PYTHONPATH=<mutant>/packages/{emcee,herder}/src`, `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider`. Each run asserted that `emcee.__file__` resolved inside its mutant tree.
- Baseline on the unmutated scratch copy, over the 5 test files: 132 passed.

| Mutant | Flip | Predicted to fail | Result |
|---|---|---|---|
| (a) | `package_status` early return disabled | test_station::test_marked_package_is_awaiting_fix | CAUGHT. 6 failed: that test, malformed, json-identity, summary, state-filter and run-skip |
| (b) | `run`'s AWAITING skip disabled | test_run_cmd::test_run_skips_a_marked_package_and_spends_nothing | CAUGHT. 1 failed, as predicted |
| (c) | `_process_one` guard disabled (`held = None`) | test_process_one_rereads_the_manifest, test_voice_refuses_a_marked_package_before_preflight, test_voice_refuses_a_malformed_mark | CAUGHT. Exactly those 3 failed |
| (d1) | malformed branch of `awaiting_fix_reason` returns None | test_malformed_mark_is_awaiting_fix_without_raising, test_awaiting_fix_reason_shapes, test_voice_refuses_a_malformed_mark | CAUGHT. Exactly those 3 failed |
| (d2) | malformed refusal always gets `(detail)` | test_voice_refuses_a_malformed_mark | CAUGHT. Exactly that 1 failed |

The commands and output are logged in `.superpowers/sdd/bulk-apply/t7-review/t7-review.log`.

### Assessment

**Task quality:** Approved

**Reasoning:** The implementation is minimal and correct. It mirrors transmitter exactly, guards the shared `_process_one` before any spend, and every load-bearing branch is pinned: all five mutants were caught by the predicted tests. The remaining items are ordering and test-tightness minors.
