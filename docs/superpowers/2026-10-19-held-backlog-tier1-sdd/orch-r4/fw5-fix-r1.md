Fix round 1 for fw5 (from the orchestrator). The Opus review (verdict file /Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1/.superpowers/sdd/tier1/fw5-rev/handback.md — read it) found I1 Important: the rule as built splits 694 library titles and adds 306 single-word fragments to the guard's known set, while it clears the same single flagged song as a much narrower gate. Ruling: adopt the reviewer's G2b gate.

1. In `song_comma_components` (brief.py ~139-140) replace the `< 2` check with, verbatim:
   `if len(parts) < 2 or not all(_BRIEF_PAREN.search(_BRIEF_TRAILING.sub("", p)) for p in parts):`
   `    return []`
   Update the docstring: split only when EVERY top-level comma part ends in its own parenthetical (the merged-tease shape, e.g. `Stay With Me (tease), Girl Named Sandoz (tease)`); a comma inside a single song title (`Lawyers, Guns and Money`, `Talk To Me Devil, Again`) never splits; a merged title with any un-annotated part stays a hold (fails safe).
2. New test: `Talk To Me Devil, Again` and `Lawyers, Guns and Money (Warren Zevon)` → `song_comma_components` returns `[]`, and a briefing mention of `Again` on a show with the first title is still flagged unknown.
3. Mutant M5: drop the `all(...)` clause → predicted: the new test. Recipe as before.
4. Re-run the full suite; append the fix report to fw5-impl/handback.md and touch `$D/fw5-impl/done-r1` (NOT `done`). Commit `fix(brief): split comma titles only when every part is annotated (fw5 review I1)`.
Check `$D/TAKEN_OVER` and `$D/taken-over/fw5-impl` before committing. Another implementer may have committed since your last commit — that is expected; do not touch its files.
