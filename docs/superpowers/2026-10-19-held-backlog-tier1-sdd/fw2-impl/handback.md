# fw2 handback: DONE
Commits: c106103 (names-form structure-changed needs --allow-structure-change), 00b0c6e (failure lines name exception type; dry-run counts purged audio).
Tests: full suite 3786 passed, 1 skipped, 8 deselected (commit 1 alone: 3784).
Changes: reapply_show(allow_structure_change=False) returns "skipped: structure changed" (nothing written, after the dry-run return); CLI --allow-structure-change; list form allows only rows with row["outcome"]=="structure-changed"; skipped row recorded retryable=True. Catch-all arm prints/records "Type: msg". New catalog.needs_audio_download(ws) (reuses _tracks) used for the dry-run download count.
Mutants:
- M1 ignore allow flag (always allow) -> test_cli_names_form_structure_changed_needs_the_flag / test_structure_changed_is_skipped_unless_allowed_and_writes_nothing -> CAUGHT by both (plus the list-form test)
- M2 allow every list row -> test_list_structure_row_applies_but_a_predicted_row_that_turned_structure_changed_is_skipped -> CAUGHT (only that test)
Deviations: structure-changed tests force the outcome by wrapping reapply_mod.classify (no fixture yields a real structure change). Names form has no catch-all arm, so item 2 changed only the list form; updated existing test's "FAILED held-3: mutagen says no" to include RuntimeError. classify/compute_legs/write order untouched.

# Fix round 1: DONE
Commit: see `git log` ("fix(reapply): list form honours --allow-structure-change (fw2 review C1)"). Suite 3793 passed, 1 skipped, 8 deselected.
- Removed the row["outcome"] allowance; _reapply_list takes allow_structure_change from the CLI flag; list skip line carries the hint; skip stays retryable.
- List test rewritten with real-shape rows (_list_file = scripts/replay_holds.py _list_row shape: slug/outcome/briefing/digests, outcome clears): skipped without flag, applied with it.
- Dry-run test now two tracks, one present one missing; new test pins needs_audio_download: unreadable JSON, missing filename, non-list tracks all count as a download (that is today's behaviour, no code change).
- Wording "first-time downloads" -> "downloads" in cli.py, README.md, tests (plan doc left as historic).
Mutants: M2' (list form ignores flag) -> test_list_form_skips_structure_changed_rows_unless_the_flag_is_given -> CAUGHT (only it). M4 (any->all) -> test_dry_run_counts_a_purged_delivered_show_as_a_download -> CAUGHT (plus the malformed-manifest test).
