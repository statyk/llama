# fw7b-rev — combined spec-compliance + code-quality review (READ-ONLY)

You review commits c255ca7..cd9a0b6 on branch held-backlog-tier1 (worktree /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1). You change NO files in the worktree and make NO commits. **Another implementer may be committing in the worktree while you work: never read source or run tests in the live worktree.** First take a snapshot: `S=$(mktemp -d "$TMPDIR/fw7b-rev-snap-XXXXXX"); git -C /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1 archive cd9a0b6 | tar -x -C "$S"`, echo $S into your log, and read/run everything there, using the worktree's interpreter with PYTHONPATH shadowing (`cd "$S" && PYTHONPATH="$S/packages/llama/src:$S/packages/herder/src" PYTHONPYCACHEPREFIX="$S/.pyc" /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.venv/bin/python -m pytest -q -p no:cacheprovider`; prove the shadowing once with `-c 'import llama; print(llama.__file__)'`). Mutants go in further copies of $S. Remove only your own $S at the end.

- The implementer's requirements: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/orch-r4/fw7b-brief.md (this is the spec you check compliance against).
- The diff: /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/orch-r4/fw7b-rev-c255ca7..cd9a0b6.diff (also `git -C /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1 diff c255ca7..cd9a0b6`). The implementer's report is in the matching `/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/<impl-task>/handback.md` — read it AFTER forming your own view of the diff, and treat its claims as claims to verify, not facts.
- Binding project constraints: the plan's "Global Constraints" (docs/superpowers/plans/2026-10-19-held-backlog-tier1.md lines 24-43) and the project CLAUDE.md. The data is the operator's live library: briefing_guard and title/structure code are the STRICT surface — a change that silently loosens a guard (fewer holds) is Critical/Important unless the brief asked for exactly that loosening.

## Check
1. **Spec compliance**: every required item of the brief is done, nothing extra was changed, verbatim values are verbatim. List each brief item ✅/❌ with file:line.
2. **Code quality**: correctness, edge cases, idiom matching the surrounding code, comment density, test quality (do the tests test behaviour and would they fail on the bug?). Grep the diff for every do-not-retune name in Global Constraints — none may move.
3. **Mutation spot-check**: re-run at least ONE of the implementer's claimed mutants yourself per the plan's recipe (predicted test written before the flip; PYTHONPATH shadowing proven; private PYTHONPYCACHEPREFIX) and confirm the claimed catch. Name any mutant the brief should have listed and didn't, and run it if cheap.
4. Run the full suite once in your snapshot (command above) and report the exact count line.

## Verdict format (handback.md)
First line: `VERDICT: APPROVED` or `VERDICT: CHANGES REQUIRED`. Then: spec table; findings as Critical / Important / Minor, each with file:line, the failure scenario, and a concrete fix; mutation spot-check table; suite line. Be concise.

## Extra checks (orchestrator)
- The implementer moved mid-file imports in 22 test modules with an ast script. Check that no moved import was deliberately placed mid-file (after `pytest.importorskip`, a `sys.path`/env tweak, a `monkeypatch`-dependent module state, or a circular-import workaround), and that no test now imports a different object than before. Spot-check at least 5 modules.
- 0fead4d changes behaviour (dry-run skip of a structure-changed show without the flag) in both cli.py and reapply.py — review it as code, not docs.
- Docs: every new CLAUDE.md/README sentence must be true of the code at cd9a0b6 (check each against the code; list any false one as Important).
