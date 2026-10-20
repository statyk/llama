# fw1 impl report: DONE
Commit 0c916da `fix(cli): --untitled clears a pre-existing encore and returns a status`.
Changes (cli.py): _untitled_resolution passes clear_encore=True; returns (Literal["declined","held","packaged"], Path|None); both call sites (triage [u], fix --untitled) use the status; _overrides_snapshot removed (no other users). Printed texts unchanged.
Tests: test_fix.py: base test asserts encore_after is None; new seeded-encore test (also runs real compute_gather over the written overrides -> single set "1"); zero-track refusal (exit 1, "0 of 0 resolved"); fix decline (exit 0, "declined; nothing written", overrides bytes identical, no redo). test_triage.py: [u] decline asserts prompt shown twice, no packaged/held line.
Suite: 3772 passed, 1 skipped, 8 deselected.
Mutation (rsync copy, PYTHONPATH shadowing proved, private pycache):
- M1 drop clear_encore=True -> predicted test_fix::test_untitled_clears_a_pre_existing_encore_so_the_tape_is_one_set -> caught by exactly that test (only failure)
- M2 decline returns "held" -> predicted (b) and (c) -> caught by test_fix::test_untitled_declined_says_so_exits_zero_and_leaves_overrides_alone and test_triage::test_triage_u_declined_writes_nothing_and_returns_to_the_prompt
No deviations or concerns.
