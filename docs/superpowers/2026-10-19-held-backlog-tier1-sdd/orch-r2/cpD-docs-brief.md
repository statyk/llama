# Docs-only commit: "Recorded at Checkpoint D" block in the plan

File: docs/superpowers/plans/2026-10-19-held-backlog-tier1.md. Find the "## Checkpoint D (operator): the stored-briefing re-check" section. Directly under its **Ask:** paragraph (the one ending "On approval, the approved rows go to `$H/approved-D.txt`."), insert a block in the same style as the existing "**Recorded at Checkpoint C (operator, 2026-10-19):**" block under Checkpoint C (read it first and match its format: a bold heading line, then bullets):

**Recorded at Checkpoint D (operator, 2026-10-19):**
- Measured at tier1-cp-D = b9ae699 (slice 3 alone; Task 15 was implemented after the measurement so it could not reach the cand arm), with PREV = tier1-cp-C2. Slice 3 changed 34 stored briefing-guard verdicts (3a 11, 3b 15, 3c 8) and moved 27 held shows to `clears`, each shipping its stored briefing by reuse. Zero clean briefings newly fire (base 0, cand 0). Suppressed set-count/ordinal matches: 21, not the prototype's ~68 (the Task 14 fix round clips 3c's negation windows at clause punctuation and briefing-field boundaries).
- Slice 3 approved as measured; approved rows in `$H/approved-D.txt`.
- Five reused briefings REJECTED: smashingpumpkins-1996-04-27, wacobrothers-2005-12-22, warrenzevon-1988-11-30, thewaybacks-2006-04-29, deadandcompany-2015-11-20. Their prose asserts encore or segue detail the guard does not check, and show.json does not support it. They stay held, are listed in `$H/rejected-D.txt`, and **Checkpoint G drops them from `predicted_list.json`** before any apply. The operator re-briefs them after the merge.
- furthur-2011-02-12's suppressed match ("had expected a spacier second set", classed as negation) is accepted as harmless: the show has two sets.
- moe-2002-06-22 stays held. Its briefing's "two sets and an encore" is right; show.json labels the `E:` encore tracks set 3. The operator fixes the structure after the run.
- For slice 6: 9 of the 27 reused stored `briefing.md` files still carry an empty `## Encore` heading, so reapply's re-render of `briefing.md` from the normalised briefing (spec 3a) is load-bearing for them.

Rules: docs only. Change nothing else in the file and nothing in any other file. One commit, message `docs(plan): record Checkpoint D decisions (slice 3 approved, 5 reuses rejected)`, ending with the two trailer lines from common.md (use your own model name in Co-Authored-By). Docs-only, so no test suite is needed; run `git diff --stat HEAD~1` after committing and confirm exactly 1 file changed.
