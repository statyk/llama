# fixwave-impl handback
Status: DONE
Commits: 2ae8bad "transmitter: pin ahead=1, drop tautological plan_step guard, ping after render-path analyze, comment [interstitials] in config template"; plus a docs commit (see git log -2) "docs: MISS wording is conditional, ..."
Tests: `./.venv/bin/python -m pytest -q packages/transmitter/tests_transmitter` -> 887 passed, 1 skipped (transmitter imported from the worktree).
A: test_scheduler.py `live(..., ahead=2)`, test parametrized [1,2]. Mutant (scratch copy, deleted): scheduler.py project() `last_pos = ahead - 1 if ahead == 1 else ahead` -> test_appending_first_pieces_reproduces_one_projection[1] red (IndexError), [2] green.
B: pipeline.py plan_step guard removed; removed test test_plan_step_guards_the_first_appended_rows_start (pinned "next start" message). The extend-level "gap" LayoutError test kept.
C: pipeline.py render_step pings WATCHDOG=1 right after st.engine.analyze; new test test_render_step_pings_after_its_own_analysis_before_the_encode; updated two test_systemd.py ping counts that encoded the old no-ping behaviour (runner total += len(encoded); render step now 2 pings per encoded show; test renamed). Runbook watchdog paragraph (7.x item 5) gained the render-path re-plan sentence.
D: config.py template `# [interstitials]`; docs 7.5 rollback bullet now "only if you uncommented it".
E: MISS wording conditional in cli.py schedule docstring, CLAUDE.md schedule bullet, docs 7.2 and 7.4 step 3 (added "no MISS with no clock file"); grep finds no other unconditional statements.
F, G: docs 7.3 and 7.4 step 8 edited as briefed.
Concerns: none; two existing systemd tests' counts changed because C adds pings (intended).
