# t3-review handback: Task 3 (campaign record and "processed"), 16cf2b3d..79049ca6

### Spec Compliance

- ✅ Spec compliant. Every interface in the brief is present with the stated signature:
  - campaign.py: CAMPAIGN_FILE, CampaignUnreadable(LlamaError), the four models, read_record, awaiting_fix, last_mark, add_mark, remove_marks, mark_processed, after_package, add_clear, manifest_sha256.
  - workspace.py:82-83 `campaign`/`reuse_anchor`. Neither path is in `show_stage_artifacts` or `input_digests` (replay.py:91-110 unchanged; pinned by test_record_is_not_an_input_digest).
  - replay.py:236-278 VISIBLE_FIELDS, visible_changes, row_visible_changes, row_label_only.
  - cli.py:2790 reads the record before plan_reuse, drop_stage_artifacts, make_providers and process_show.
  - cli.py:2814-2817 calls mark_processed when SHOW_STAGE_ORDER.index(from) <= index(last mark start), with held=pkg is None.
  - package.py:140 calls after_package after the manifest write.
  - Writes go through atomic_write_bytes and then catalog._flush_to_disk (campaign.py:77-81). mark_processed imports input_digests inside the function.
  - The CampaignUnreadable text matches the fixed string `<slug>: cannot read campaign.json (<error>); check it by hand` (campaign.py:58-61; the test regex asserts it).
- Contract checks:
  - "Awaiting fix" = marks non-empty and (processed null or processed.at < last mark's at). Implemented at campaign.py:96-106 with parsed datetimes. An unparseable `at` counts as awaiting, the safe direction.
  - Start stage = last mark's (last_mark).
  - The spec's "fix --clear-* re-gathering a re-selection's old recording stays awaiting" holds through the stage comparison: gather (index 1) > select (index 0). Tested by test_redo_from_gather_with_a_select_mark_stays_awaiting.
  - Every fix, triage and untitled caller goes through `_redo_show_locked` (cli.py:1966/1971, 2162, 3559) inside a show_unit. A failed unit therefore restores campaign.json (tested byte-identical).
  - The untitled path (gather redo held → processed with sha None, then brief redo → build_package → after_package fills the sha) works as the spec's "any package build on a processed show refreshes that sha" requires.
- ⚠️ Cannot verify from this diff:
  - (a) Task 9's reapply wiring of mark_processed. Today's reapply.py:191 already calls build_package, so after_package now fires on reapply's packaging, before reapply's own show.json commit. That is harmless (a held show still fails the clear), but Task 9's reviewer should confirm the ordering.
  - (b) Task 4 must treat CampaignUnreadable as awaiting (Review Focus 5).
  - (c) Task 12 must keep its outcome guard before row_visible_changes (see Minor 2).

### Strengths

- The unreadable-record refusal comes first and is pinned well. test_redo_refuses_an_unreadable_record_before_any_stage stubs every stage, process_show and make_providers, asserts zero calls and an unchanged tree, and checks the fixed string.
- The stage-comparison boundaries are each covered by a test:
  - a mark from `gather` with a redo from `brief` stays awaiting;
  - from `gather` it is processed;
  - a `select` mark with a redo from `gather` stays awaiting;
  - a redo from `select` is processed.
  So `<` vs `<=` and an inverted comparison would both fail.
- The failing-redo test injects the failure after the real mark_processed write. It proves the unit restores campaign.json byte-identical, not merely that nothing was written.
- row_visible_changes is checked against visible_changes on real `shipped_diff` rows. The cases cover a swap, a relabel, an unchanged show, a mixed title/venue/break change and a count change. This is the parity the later marking tasks rely on.
- Global Constraints grep: none of the Untouched names appear in the diff's +/- lines. Checked DURATION_TOLERANCE_S, the junk constants and rule, purge_package_audio, STOP_AFTER_LLM_FAILURES, load_list, briefing_reusable, the piece-3 constants, audio_reuse pairing, Manifest, emcee and file_lock. No new lock and no Manifest field.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. **campaign.py:40:** `manifest_sha256: str | None = None`, but the brief's interface and the Contracts list it as a required key. A record missing the key validates and reads as a held outcome rather than refusing as malformed. Harmless today, since only this code writes it. Drop the default to match the contract.

2. **replay.py:258-261:** ShowReplay.filenames defaults to `[]`, not None (replay.py:729). So on a needs-llm or unreplayable row, row_visible_changes returns `["files"]` and row_label_only returns False. Probed on `ShowReplay(outcome="needs-llm")`: the output was `['files'] False`.
   - Plan Task 12 (plan line 519) guards this by outcome before computing visible changes, and Task 14's kind order puts needs-llm first.
   - Unguarded, it would re-mark a processed show from a needs-LLM row, which the spec forbids.
   - Suggestion: state the precondition in the docstring, or return [] for non-replayed outcomes.
   - Conversely, a row missing the key entirely (an old-arm row) reads as "no file change", which hides a same-count swap. That is acceptable only because arms must match the pin's sha.

3. **package.py:140 with package.py:147:** after_package can raise CampaignUnreadable after the manifest is written.
   - Inside a show_unit (redo/fix/triage) the unit restores everything.
   - On a non-unit path (get / run resume through process_show), the manifest stays and run_package's flag write is skipped. The next resume sees `built=False`, so package-stage flags (e.g. duration mismatch) are never recorded.
   - The trigger is narrow: a corrupt campaign.json plus a run-path package build. Task 4's deliver refusal on an unreadable record backstops it.
   - Fix: read the record at the top of build_package's build branch, so an unreadable record refuses before any download or write.

4. **Test gap, cli.py:2817:** no test asserts `processed.manifest_sha256` after a redo, so `held=pkg is None` is not pinned. A `held=False` mutant would survive. It only differs on a package-stage hold, where the manifest exists. Add a redo assertion that the sha equals the new manifest's sha, and is None for a package-stage hold.

5. **Spec note on VISIBLE_FIELDS (replay.py:236):** the spec's marking rule lists `source.identifier` among manifest-visible fields, but the plan-fixed tuple omits it. Re-selections are marked by their own rule, so this is a plan/spec wording gap, not an implementation defect. Recorded for the controller.

6. **campaign.py:77-81:** the file is F_FULLFSYNC'd after the rename, but the directory entry is not fsynced. This is the mechanism the brief mandates; recorded only against the spec's "made durable".

### Checks run
- `./.venv/bin/python -m pytest packages/llama/tests/test_campaign.py packages/llama/tests/test_replay.py -q` → 316 passed. llama.__file__ resolves inside the worktree.
- Probe of row_visible_changes on a needs-llm ShowReplay row (Minor 2).
- Call-site check: every `_redo_show_locked` caller is inside a show_unit (cli.py:1960, 2160, 2769, 3493).
- Reapply's build_package call site (reapply.py:191) for the after_package ordering (⚠️ a).
- build_package's short-circuit (package.py:54): after_package is not reached when an existing manifest is reused.

### Assessment

**Task quality:** Approved

**Reasoning:** Every brief interface and contract clause is met. The stage-comparison and unreadable-record behaviour are tested at their boundaries. The remaining items are a contract-default nit, a precondition on the row helper that the plan's callers already guard, a narrow non-unit failure ordering, and one unpinned argument.
