# evid-impl handback
Status: DONE. Commit: see `git log -1` (docs: held-backlog Tier 1 evidence ...). Files: docs/superpowers/2026-10-19-held-backlog-tier1-evidence.md (147 lines), CLAUDE.md (evidence pointer added in the Tier 1 bullet; no pre-existing placeholder found).
Tests: ./.venv/bin/python -m pytest -q -p no:cacheprovider -> 3803 passed, 1 skipped, 8 deselected (llama.__file__ inside worktree).
Mutations: none (docs only).
Untraceable numbers: none. Discrepancies noted in doc: G1 PREV was cp-F2 not cp-F; plan C item 4 calls 1d a note, Contracts say flag.
Concerns: G1 summary.txt prints "newly cleared: 112" vs predicted_list 155 rows; I cited 155 only and did not interpret 112. Weekly meter 3%->4% after wave 1, 3%->5% overall (doc uses overall). B first-measurement counts and A/E/F counts come from ledgers; C/D/E/F decisions from plan Recorded blocks.

## Fix round 1
Applied I1-I4, m1, m2, m3, m5 and the CLAUDE.md m4 rewrap (wording unchanged) to the evidence doc; commit "docs: evidence doc fact-check fixes". Suite: 3803 passed, 1 skipped, 8 deselected. No untraceable numbers.
