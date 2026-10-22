# t9-run handback: BLOCKED (compare exit 3, baseline drift). Nothing applied.

Status: BLOCKED. Stopped at Step 3 per rule (exit 3 = harness drift; no --no-repro-gate, arms not re-run).

## Preconditions
- $W HEAD 36473d8, git status --porcelain empty; llama.__file__ under $W.
- Full suite: ./.venv/bin/python -m pytest -q -> 4041 passed, 1 skipped, 8 deselected (matches predecessor).
- Base worktree B=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-small-fixes-base (sibling dir ...held-backlog-small-fixes-base) at BASE_SHA 6ba3be2245a9274bd1651a98afb2c0dab54925eb; its .venv llama.__file__ resolves under B.

## Commands and exit codes
- base arm: (cd B && ./.venv/bin/python scripts/replay_holds.py run --all --out ~/.llama-harness/small-fixes/base.json) -> exit 0 (base.rc)
- cand arm: (cd W && ./.venv/bin/python scripts/replay_holds.py run --all --out ~/.llama-harness/small-fixes/cand.json) -> exit 0 (cand.rc)  [ran concurrently]
- compare: (cd W && ./.venv/bin/python scripts/replay_holds.py compare base.json cand.json --out ~/.llama-harness/small-fixes/cmp) -> exit 3
  Output: "baseline reproduces 134/147 held shows that are not needs-LLM (< 99%)"
  Only file written in cmp/: drift.txt (198 lines), sha256 0a20d5bb631909c147b88257edb9315724d52b2941ddba0d4ba3d812dbca2504

## N per arm
Both replayed 3983 shows.
- base: clean=2950, clean-changed=5, needs-brief=4, needs-llm=697, newly-held=184, still-held=142, still-held-package=1
- cand: clean=2788, clean-changed=168, needs-brief=5, needs-llm=697, newly-held=183, still-held=141, still-held-package=1
(Note: cand has 168 clean-changed vs 5 in base: likely the venue tie-break effect, unreviewed because compare gated out.)

## Drift analysis (cmp/drift.txt)
Header: "base shows whose stored core flags are not reproduced". The sampled rows are overwhelmingly [packaged]/[delivered] shows with stored flags [] whose base replay produces flags (e.g. low-confidence setlist, research asserts unknown song, jerrybase set closer not at a set break, venue mismatch), plus a few [held] rows where the stored flags are a superset of the replay. This pattern is consistent with the stored library state having been produced by overruled/reapplied/operator-fixed shows (flags cleared via fix --overrule or similar) and library changes since the base-code baseline (the backlog work of 2026-10-20/21), rather than a defect of this branch: the drift is in the BASE arm, which is v2.14.0 code. The 134/147 = 91% reproduction is below the 99% gate. I did not diagnose further or use --no-repro-gate.
Decision needed from owner/orchestrator: whether to (a) accept running compare with --no-repro-gate (explicitly forbidden to me), or (b) have the harness gate scoped to held shows that were not overruled, or (c) other. The arm JSONs are intact at ~/.llama-harness/small-fixes/{base,cand}.json, so compare can be re-run in seconds with a different decision.

## Not produced
No Step 4 numbers (venue_changes.txt, flags.txt, packaged_exposure.txt, predicted_list.json), as compare exits before writing them.

## State
Nothing applied; ~/.llama untouched (read-only). Base worktree left in place. No commits, no repo changes.
