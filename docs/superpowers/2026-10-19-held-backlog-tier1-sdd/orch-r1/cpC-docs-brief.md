# Docs-only commit: "Recorded at Checkpoint C" block in the plan

File: docs/superpowers/plans/2026-10-19-held-backlog-tier1.md. Find the "## Checkpoint C (operator): slice 1 lists" section. Directly under its **Ask:** paragraph, insert a block in the same style as the existing "**Recorded at Checkpoint B (operator, 2026-10-19):**" block under Checkpoint B (read it first and match its format):

**Recorded at Checkpoint C (operator, 2026-10-19):**
- First measurement (tier1-cp-C = 88f087a): slice 1 cleared 60 held shows but newly held 45 currently-clean delivered/packaged shows, of which only 3 were true conflicts. The rest were false: country name vs code, suburb vs metro, comma-less `City ST`, venue text in the city field, and identical venue names whose cities did not compare.
- Task 13b (operator-approved narrowing):
  - **V:** 1d fires only when the selected recording's venue is NOT `venues_equivalent` to the vote's venue. A blank vote venue counts as not equivalent.
  - **S:** step 1's city check applies only to pairs that 1b newly made equivalent. Pairs equivalent under the pre-slice rule (`structure._venues_equivalent_pre1b`, a frozen copy of the tier1-cp-B2 rule) pass on equivalence alone.
- Task 13c: `replay_holds compare --no-repro-gate`, used for every `-prev`-vs-cand compare.
- Re-measure (tier1-cp-C2 = b6f353a): 54 cleared, 4 newly held:
  - ryanadams-2007-06-06 (true);
  - beneventorusso-2005-08-27, gratefuldead-1978-09-16, smashingpumpkins-1997-06-28 (false; the venue names differ).
  Slice 1 approved as narrowed.
- Documented limitation: V uses the live `venues_equivalent`, so Task 12's loosenings widen V's suppression. `Cornell University` vs `Cornell College` (university strip) and `Capitol` vs `Capital Theatre` (one-edit) count as the same hall. There are 0 such pairs in the library today; the operator chose to leave it.
- Live-library fixes made by the operator at C, outside this branch, with `llama fix --set-venue/--set-city`:
  - gratefuldead-1978-04-15, gratefuldead-1985-06-14, darkstarorchestra-2005-06-07, darkstarorchestra-2005-07-17, darkstarorchestra-2017-06-27, philleshandfriends-1999-10-31;
  - re-delivered with a corrected venue: belafleckandtheflecktones-2006-04-21, guster-2003-07-10, stuallenandmarshotel-2012-11-11, ginblossoms-2003-01-24, belafleckandtheflecktones-2004-04-06;
  - overrides staged: soundtribesector9-2003-06-13, yondermountainstringband-2005-07-16.
  Later checkpoints treat these as expected drift.

Rules: docs only. Change nothing else in the file and nothing in any other file. One commit, message `docs(plan): record Checkpoint C decisions (V+S narrowing, --no-repro-gate, live fixes)`. Docs-only, so no test suite is needed; run `git diff --stat` and confirm exactly 1 file changed.
