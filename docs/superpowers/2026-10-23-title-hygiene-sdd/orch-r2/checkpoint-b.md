# CHECKPOINT B: title hygiene (piece 3), orch-r2 (session 3400e369), 2026-10-23

The branch is held-backlog-title-hygiene at **174995e**, with a clean tree apart from the untracked draft `acceptance.md`. Tasks 0-20 are complete and review-clean. Task 21 is at Step 7. Task 22 has not started.

Suite at 174995e: `./.venv/bin/python -m pytest -q -p no:cacheprovider` gives 4762 passed, 1 skipped, 8 deselected. The orchestrator re-ran it, with `llama.__file__` inside the worktree.

## Evidence (paths and sha256)

| item | path | sha256 |
|---|---|---|
| Final whole-branch review (**Fable** seat) | .superpowers/sdd/title-hygiene/final-rev/handback.md (21047 B) | 19d7a6fe2cb612c572edb2587c3d2399bfc13bdcbb2c2c022c7e65c3edac34d4 |
| Acceptance report (draft, uncommitted) | docs/superpowers/2026-10-22-title-hygiene-evidence/acceptance.md | 601ee5fec7585343f79e69de4374f3bba866c583cc6be23eb7c77522a751186e |
| Opus pre-screen | .superpowers/sdd/title-hygiene/cpb-prescreen/handback.md | 3226550dec5fe2ff277ac317dfecf389f615d6ecf6f25734837c7590a03724b6 |
| Pre-screen adjusted rows | ~/.llama-harness/piece3/accept/handcheck/prescreen/adjusted.jsonl | ecf3844414e6821a17c0360967009b9c4cc46cb6bafe3753fb00e529e439020f |
| Pre-screen tally | ~/.llama-harness/piece3/accept/handcheck/prescreen/tally.json | d14284571932c365cd36db8711ed87e0f5c85d5678029f102dc4785bb8aeed00 |
| Checker row files (12) | ~/.llama-harness/piece3/accept/handcheck/rows.sha256 | (per-file list) |
| Arms, compares, parity, packets | ~/.llama-harness/piece3/accept/ | arm shas in acceptance.md |

## Fable verdict: Ready to merge? **With fixes**

The reviewer's reasoning:
- Architecture, protected-name discipline, the wiring (one copy of the prelude and title block), and Q2 with the replay relaxation are sound and pinned.
- The hand check found zero shifted shows.
- But darkstarorchestra-2014-07-31 shows C2 clearing a hold while shipping a wrong, duplicated title with no flag.
- And the acceptance record and Task 22 are not yet in the branch.

Findings:
- **Critical C-1: C2 on a wholesale-shifted MP3 tag set** (lossless_titles.py:141-149, 199-205).
  - C2 corrects only the positions its reference confirms. On darkstarorchestra-2014-07-31, #3's reference is `?`, so #3 keeps the shifted MP3 tag "Duprees Diamond Blues", which duplicates #4. The hold is cleared and nothing flags it.
  - The spec's ±1 skip looks only at lossless tags. The mirror signature, delivered tags agreeing with the reference at ±1, appears on 4 shows: darkstarorchestra-2014-07-31, lettuce-2002-07-13, tedeschitrucksband-2019-02-15 and tedeschitrucksband-2020-01-15. lettuce #10 and #16 (unreplaced edges) were not hand-checked.
  - Fix options (operator ruling: strict surface):
    - **preferred:** when 2 or more delivered tags show the ±1 shift signature, keep C2's confirmed replacements and demote every other unconfirmed delivered real tag to blank (it becomes `unresolved`, so the hold, D or the gated S decides), with one note;
    - **conservative:** skip C for that show (DSO stays held, and the 18 right corrections are forfeited).
  - Either way, add a verbatim DSO fixture and re-measure.
- **Important I-1: needs-LLM rows lose their cascade record** (replay.py:544, the plan's Task 17 contract). 6 of the 14 as-is added holds print as `unattributed`. Fix: record the cascade regardless of needs-LLM (a plan deviation), then regenerate holds_delta.
- **Important I-2: written justification for added holds.** acceptance.md must carry the strict-surface (d) justification table for the added holds (14 as-is, 15 fresh) and the good-shows-held count, and be committed.
- **Important I-3: Task 22 not yet done.** The CLAUDE.md bullet and SDD record are expected; this is the plan's next task.
- **Minor M-1 to M-7:**
  - M-1: check 1 passes a lone `Encore`, `Set Break` or `Intermission` as a title (a spec amendment to the header shape);
  - M-2: gated check 2 cannot see override neighbours;
  - M-3: reader (i) unescapes twice;
  - M-4: stale `"restart"` comment;
  - M-5: Q1 chosen-note wording on the ablation path;
  - M-6: slice 5 leaves `()` debris;
  - M-7: lettuce #10 and #16 unchecked.
- **Triage of deferred minors, fix-before-merge:**
  - Task 10's `()` debris (= M-6);
  - Task 16's `_sibling_transfer` docstring sweep;
  - Task 18: the `..._off_when_slice5_disabled` test should use `ALL_SLICES - {"slice5"}`;
  - Task 19: the compare summary's `disabled slices` line prints only the cand arm's set;
  - Task 20: delete or fold the tautological floor test, and add a resolution line to mutation.md.
  - Everything else: defer.

## Acceptance (pre-screened hand check, 157 shows, 900 tracks filled or replaced)

| path | filled or replaced | wrong | cant-tell |
|---|---|---|---|
| C1 | 86 | 0 | 0 |
| C2 | 91 | 0 | 2 (2.2% if both wrong) |
| D | 341 | 0 | 0 |
| slice 4 | 22 | 0 | 0 |
| S | 2 | 0 | 0 |
| slice 5 | 355 | 0 | 0 |
| pooled | 900 | 0 | 2 |

- **Shifted shows: 0.** That includes the gate's untagged hand check, where every shifted, some-wrong or cant-tell show is held in the candidate.
- **The bar's blind spot (Fable).** The per-path bar cannot see C-1's class, because the wrong title is one that no path touched. The whole-show hand-check rule is what caught it.
- **Slice-1 good-S holds.** 3 under the strict reading: lotus-2010-06-10, umphreysmcgee-2005-11-12 and steepcanyonrangers-2004-05-21. The last two also have shifted tape tags that the hold stops. Counting only shows with no other silent defect gives 1. The bar is at most 2.
- **Q1 declines, reported apart:** darkstarorchestra-2004-04-24, darkstarorchestra-2015-07-11 (today shifted), philleshandfriends-2007-10-20 (today shifted from #10), gratefuldead-1989-07-19.
- **Holds (fresh-get):** 41 cleared (5 held now, 34 would-hold on a fresh get, 2 currently shipped) and 15 added (10 delivered, 4 packaged, 1 voiced). As-is: 7 cleared, 14 added.
- **Parity:** 3983/3983.
- **Slice 5:** 0 flag, set or segue changes; 27 shows and 422 tracks stripped; 7 delivered shows would need a fresh brief.
- **Mutation (Task 20):** 29 mutants, 27 caught. The 2 survivors are now pinned (174995e). Approved by an Opus review.

## Decisions for the operator

1. **C-1** (Critical, strict surface): take the preferred fix (demote unconfirmed delivered tags on a shifted set), the conservative fix (skip C on the show), or another rule. The re-measure follows either way.
2. **The two C2 conflicts:** greenskybluegrass-2012-09-25 #9 and johnkadlecik-2017-10-31 #9. In each, the same taper's description and FLAC tag disagree with the MP3 tag and a second taper. Accept them as cant-tell? If both are wrong, C2 is at 2.2%, over the 2% bar.
3. **The slice-1 good-S count:** 3 strict, or 1. Is the bar met?
4. **I-1:** may the harness record the cascade on needs-LLM rows? It deviates from the plan's Task 17 contract and is needed to attribute every added hold.
5. **Cosmetic constant changes** (each currently right-partial; a "no" is a documented limitation):
   - D cleaning: a leading `--> `, trailing `^` and `$` with padding, and a duration glued after `)`;
   - slice 5: decline a strip that leaves `()` (Fable says fix before merge);
   - an artist prefix, ` H2`, and `Encore- ` (slice 5 does not strip these; `E: ` is kept by spec design);
   - M-1: lone encore or set-break forms as a check-1 header shape.
6. **Abbreviations replacing fuller titles:** MRG via C2, O via slice 4. Accept as a limitation?
7. **Reader gaps that cost holds:** a bare trailing `N` line treated as a disc label (lotus-2010-06-10), and a disc header carrying a duration (railroadearth-2007-01-28). Accept as limitations?

## Proposed next steps after the rulings (orchestrator)

- ONE fix wave: C-1 as ruled, with the DSO fixture; I-1; the five fix-before-merge minors; any cosmetic rulings. Then a scoped Opus re-review.
- A re-measure (Task 21 Steps 1-5, arms plus the C2 hand check including the unreplaced edges).
- Then commit acceptance.md with the (d) justification table, and do Task 22 (CLAUDE.md bullet naming P3, P4, (g) `07-8th Wonder`, deadandcompany-2016-07-15 piece-5 class, plus the rulings above; SDD record copying all three ledgers, the Checkpoint A rulings and the key verdicts).
- Finish menu.
