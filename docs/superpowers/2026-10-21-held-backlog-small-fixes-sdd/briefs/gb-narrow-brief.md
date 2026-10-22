# Slice B narrowing wave — brief (owner ruling 2026-10-21)

Context: slice B's venue tie-break (`gather.venue_tie_break`, packages/llama/src/llama/stages/gather.py:955, called at ~gather.py:1407) ships the selected recording's own stripped venue on a tied grouping vote. The Task 9 measurement found ~38 of 234 ties where the two strings are DIFFERENT NAMES (e.g. "9:30 Club" -> "Nightclub", "Mad City Music Exchange" -> "Luther's Blues"), where the selected string was no better on average. The owner has ruled to NARROW the rule. Scope is exactly the items below.

## 1. Code (failing-first)
- New condition: the tie-break applies ONLY when the selected recording's stripped venue string and the vote's venue string are `venues_equivalent` (packages/llama/src/llama/structure.py:356 — spelling and phrasing of one name). Use that function as is; do not change it.
- Every existing condition stays exactly as it is: the tie counted raw (as `grouping._make_candidate` counts), count > 0, the city gate (`cities_compatible` or blank city), the three arms it applies in (no event, unflagged 1a, step 1 when the selected string passes step 1's full test), and no tie-break under an operator venue override (`tie = ... if overrides.venue is None else None`, commit 12af7eb).
- Where the check goes is your call (inside `venue_tie_break` is the natural place, so every caller gets it); keep the function's contract (returns None when the tie-break does not apply).
- Tests, beside the existing slice B tie-break tests (grep -n "tie_break\|tie-break" packages/llama/tests/test_stage_gather.py and any unit tests of venue_tie_break):
  - NEW, failing first (show RED on the current HEAD before editing source): a non-equivalent tie — e.g. "9:30 Club" vs "Nightclub", same city — ships the VOTE unchanged (venue and city).
  - KEEP (or add if missing) an equivalent-tie test that ships the selected spelling (e.g. two spellings of one name).
  - Existing tie-break tests whose two strings are NOT `venues_equivalent` will now change outcome. That is expected under this ruling: for each such test, decide whether it should become a non-equivalent "ships the vote" pin or be re-shaped to an equivalent pair so it keeps testing what it was written for (the city gate, the arms, the override). List every test you changed and why in your report. Do not weaken any assertion that is not about the narrowed condition.
- Mutant (mandate 5 — scratch copy only, `git archive HEAD | tar -x -C <scratch>`, run from the scratch dir with PYTHONPATH shadowing and `<worktree>/.venv/bin/python -m pytest`, after proving `llama.__file__` resolves inside the scratch tree): remove (or invert) the new `venues_equivalent` condition. BEFORE flipping it, write in your log the test you predict goes red (name it first). Then run and record: CAUGHT only if the predicted test is red. Report prediction, command, result.

## 2. Docs (same wave)
- Spec, docs/superpowers/specs/2026-10-21-held-backlog-small-fixes-design.md, slice B's rule: add one sentence saying the tie-break applies only when the two strings are `venues_equivalent`, with the reason: measured 2026-10-21, about 38 of 234 ties were different names, where the selected string was no better on average ("9:30 Club" -> "Nightclub").
- CLAUDE.md's "**Venue tie-break**" bullet (~line 627): add the equivalence limit and that an operator venue override suppresses the tie-break.
- CLAUDE.md:62 (triage): the text says the `changed by another command` path "re-resolves, re-captures and re-prints the show"; the code captures the view first, then re-resolves (cli.py ~1837 then ~1842). Fix the step order to match the code.

## 3. Re-measure (after the code is committed and the suite is green; tree must be CLEAN — a -dirty identity is useless)
- The owner keeps the library quiet. Re-run the CANDIDATE arm only, with this worktree's interpreter, in the background:
  `cd /Users/shawn/projects/llama/.claude/worktrees/held-backlog-small-fixes && ./.venv/bin/python scripts/replay_holds.py run --all --out ~/.llama-harness/small-fixes/cand-2.json`
  (the earlier cand.json stays as it is). ~3 min last time.
- Then compare against the EXISTING base arm, gate skipped, into a NEW dir:
  `./.venv/bin/python scripts/replay_holds.py compare ~/.llama-harness/small-fixes/base.json ~/.llama-harness/small-fixes/cand-2.json --out ~/.llama-harness/small-fixes/cmp-norepro-2 --no-repro-gate; echo "exit $?"`
- If compare exits 2 (arms differ): re-run the BASE arm too, from the base worktree with ITS interpreter: `cd /Users/shawn/projects/llama/.claude/worktrees/held-backlog-small-fixes-base && ./.venv/bin/python scripts/replay_holds.py run --all --out ~/.llama-harness/small-fixes/base-2.json`, then compare base-2.json vs cand-2.json into cmp-norepro-2 (`--no-repro-gate`). Report what made the arms differ.
- Stop rules: any added or removed venue/city flag (`venue mismatch:` prefix or `recordings of this date disagree on city`) on any show is a DEFECT — stop and report. Any newly held show is a failed acceptance — report prominently.
- Report: venue_changes.txt total; how many rows are now NON-equivalent under `structure.venues_equivalent` (compute it with a short read-only script over the rows' two venue strings; expect 0); city changes; DELIVERED; flags CHANGED; and the summary.txt text. Measurement only: predicted_list.json is not for apply.
- ~/.llama is READ-ONLY. Never deliver/rm/fix/redo/reapply/get/triage.

## Binding
- Global constraints: .superpowers/sdd/2026-10-21-held-backlog-small-fixes/global-constraints.md. `normalize_song`, `DEFAULT_ALIASES`, `venues_equivalent` and every do-not-retune constant stay byte-identical.
- Commit code+tests, then docs (or one commit), each with the test command in the message and the trailer from global-constraints.md. Full suite before the last commit: `./.venv/bin/python -m pytest -q` (was 4046 passed, 1 skipped, 8 deselected).
