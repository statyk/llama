# SDD ledger — plan: docs/superpowers/plans/2026-09-02-sibling-title-transfer.md

Spec: docs/superpowers/specs/2026-09-02-sibling-title-transfer-design.md (read).
Worktree: /Users/shawn/projects/llama/.worktrees/sibling-transfer, branch sibling-transfer.
Baseline verified by orchestrator 2026-09-02 09:17 EDT: `./.venv/bin/pytest -q` -> 1557 passed, 7 deselected. HEAD 98d752a.

## Pre-flight conflict scan

### Cross-task rows (tasks sharing a file or an interface)

| A | B | A produces | B consumes | Finding |
|---|---|---|---|---|
| T1 | T5 | `junk.filter_files` dedupe | gather donor loading calls `filter_files` | Consistent; T1-before-T5 order is load-bearing and the plan states it. No conflict. |
| T2 | T3 | `titles.is_real_title` numeric widening | siblings hygiene uses `is_real_title` | Consistent; order holds. |
| T2 | T5 | `titles.py` (is_real_title), `test_titles.py` | `titles.py` (remove sibling rung), `test_titles.py` | Same files, disjoint regions, strictly sequential dispatch. No conflict. |
| T3 | T4 | `siblings.py`, `test_siblings.py` created | extended | Consistent. |
| T4 | T5 | `rate_alignment`/`cplus_filter`, `structure.loosely_same_title` | gather transfer pass | Consistent. |
| T5 | T6 | donor-loading helper (implicit) | T6 requires "factor the donor-loading helper so the two share it" | **CONFLICT (minor):** T5's brief does not instruct factoring; T6's does. Ruling below. |
| T5 | T6 | `models.py` title_source comment | `models.py` ProposalRow fields | Disjoint regions, sequential. No conflict. |
| T3/T4 | T5 | `siblings.py` purity constraint | gather does all I/O | Consistent with Global Constraints. |
| all | T7 | shipped functions | measurement through shipped code only | Consistent. |

### Per-task self-consistency rows

| Task | Tests spec'd vs code spec'd | Files created vs later touched | Finding |
|---|---|---|---|
| T1 | dedupe tests match the (basename, round(dur)) key + swap rule | `scripts/dedupe_sweep.py` created, never re-touched | agrees |
| T2 | `is_real_title` cases match the widening; pinned enumerated-gate tests named | census script created, never re-touched | agrees; carries a named STOP/escalation gate |
| T3 | 8 content tests match the stated DP ops and per-row declines | `siblings.py` created, extended by T4 | agrees |
| T4 | comparator + band + C+ tests match the stated interfaces | `structure.py` comparator-only edit | agrees; `cplus_filter` gates auto band only — pinned as invariant 1 |
| T5 | 6 tests match the transfer pass; mutation A needs an independence test that may not exist yet — Step 1 says write it | gather/titles/models edits | agrees |
| T6 | 6 CliRunner tests match the sibling arm; renderer never calls `cplus_filter` | cli/models edits | agrees |
| T7 | gates are content comparisons with expected values | evidence doc created | agrees; Opus, ship gate |

### Rulings made before execution

Ruling: The donor-loading helper is factored out in **Task 6**, not Task 5 — T5 writes `_sibling_transfer` with its donor loading inline-but-extractable, T6 extracts the shared helper and both call it. Why: T5's brief does not mandate the seam and inventing one early risks a shape T6 cannot use; T6's brief explicitly owns it. Cost if wrong: one extra refactor commit inside T6.

Ruling: The evidence doc's placeholder filename `docs/superpowers/2026-09-XX-sibling-transfer-evidence.md` resolves to **`docs/superpowers/2026-09-02-sibling-transfer-evidence.md`**. Why: the plan uses a date placeholder; house convention is the authoring date. Cost if wrong: a filename edit plus the `siblings.py` citation comments that name it.

Ruling: Base-commit discrepancy — plan's Global Constraints say base `main` @ `44038ae`; the worktree branches from `98d752a`, which is `44038ae` plus the docs commit that added the plan and spec themselves. Treated as the same code base. Baseline re-measured and matches the plan's stated 1557/7. Cost if wrong: none; verified by measurement.

Ruling: `models.TitleProposal.evidence_source` already carries `"sibling-duration"` (Phase B's canonical duration DP). Task 6's new value is `"sibling-align"` and is **distinct** — the existing value is not renamed or reused. Why: the plan names `"sibling-align"` explicitly and Phase B's value is a different arm. Cost if wrong: a confusing two-value namespace; noted for the Task 6 reviewer to check the rendering distinguishes them.

## Progress

Task 1: implementer DONE (Sonnet). Commits f943909 (junk dedupe + tests), 852e47d (scripts/dedupe_sweep.py).
  Suite `./.venv/bin/pytest -q` -> 1560 passed, 7 deselected (baseline 1557 + 3 new).
  Sweep: 968 items / 1936 item-format pairs, exactly one changed item (ymsb2005-12-31.flac16, 56->28 both formats), 24 hand-checked pairs, added=[] everywhere.
  Note: implementer ran its own mutation IN-WORKTREE and reverted, contrary to the global constraint that mutations run on an outside copy. Tree is clean; treated as unverified and re-run by the spec reviewer on a proper copy.
Task 1: review dispatched — spec-compliance (Opus, t1-rev-spec) and code-quality (Opus, t1-rev-qual), concurrently, each on its own out-of-worktree copy.
Task 1: spec review SPEC (Opus) — all 18 brief requirements met. Verdict: /private/tmp/.../sdd-phasec/t1-rev-spec/report.md
  Findings: 1 Important (R6 play-order-on-deduped-list is UNPINNED — mutation M5, moving the dedupe after the ordering block, broke nothing across all 1560 tests, yet it is a real behaviour change: on the real ymsb item order_source degrades track-tags -> filename). 2 Minor (swap can leave `kept` out of name order, 0/968 corpus incidence; no-length-key files keyed on basename alone, as the brief specified).
  Mutations M1-M4 all RED with named tests and verbatim assertion lines; M5 GREEN = the finding.
  *** PROCESS CORRECTION, applies to every later reviewer ***
  `./.venv/bin/pytest` is a console script with an ABSOLUTE SHEBANG at the worktree interpreter. Run from an out-of-worktree copy it silently tests THE WORKTREE, not the copy — a planted sentinel showed 22 passing that should have been red. The correct invocation from a copy is `./.venv/bin/python -m pytest`. This is exactly the "a check that returns nothing and a check that never looked are indistinguishable" hazard, and it would have voided every mutation result in this phase. Correction pushed live to the in-flight code-quality reviewer; folded into all subsequent reviewer dispatches.
  Ruling: the R6 Important finding enters the fix loop (one test asserting order_source == "track-tags" on a dup-with-tags fixture). Why: it is the plan's own stated requirement ("play-order derivation runs on the deduped list") and it is currently a shape-free claim — precisely the four-hollow-pins failure this phase was told not to repeat. Cost if wrong: one small test.
Task 1: quality review CHANGES REQUESTED (Opus). Verdict: /private/tmp/.../sdd-phasec/t1-rev-qual/report.md
  1 Important (BOTH placement invariants unpinned: dedupe-after-ordering green AND dedupe-before-_keep_and_exclude green; two validated killer tests supplied in the report). 7 Minor.
  Confirms independently: all three new tests are binding (each killed by a named source edit); the sweep's "exactly one item" is NOT a script artifact — replicated straight from raw cache metadata, old code taken from git at f943909^.
  Convergence note: both reviewers reached the placement gap independently and neither saw the other's findings or the ledger.
Task 1: fix round 1/5 dispatched — resumed the original implementer (Sonnet, context intact). Scope: the 2 Important placement pins + 2 house-style minors (docstring, sweep provenance comment).
  Ruling: the two house-style minors are folded into the fix round rather than deferred, against the skill's "minors never enter the loop". Why: the file is open anyway, and provenance-in-a-comment is a standing convention of this codebase (junk.py's existing measured constants all carry it) that the final review would otherwise re-raise. Cost if wrong: two trivial lines of diff in a round that was happening regardless.
  Deferred minors (pointed at the final whole-branch review, NOT fixed): redundant `order` list; (basename, round(secs)) key vs titles.py's different-dirs-are-different-tracks note (0/968 corpus incidence); test name overstates "byte-identical" at test_junk.py:240; sweep script's n_pairs counts absent formats so "1936 pairs" is 2x968 by construction.
Coordinator follow-up (2026-09-02 09:39): two items.
  (1) Retrospective audit of Phase B's mutation evidence for the shebang defect — dispatched read-only to phb-audit (Sonnet), scoped to the preserved verdicts dir, explicitly barred from touching the worktree while the fix round writes there. Rubric: SOUND only via `-m pytest` (S1), `PYTHONPATH=<copy>` (S2, valid here because PYTHONPATH precedes .pth entries and this project's editable installs are plain-path .pth), or an empirical shadow proof (S3); in-worktree mutate-and-restore classified IN-PLACE (different hazard, not this one); bare console script from a copy = UNVERIFIED. Instructed that UNVERIFIED means the evidence does not support the conclusion either way — never "refuted", never "probably fine". Inventory only; the owner decides what gets re-verified.
  (2) The invocation rule goes into the plan's Global Constraints (durable) rather than only dispatch text. DEFERRED until the fix round commits — the implementer is currently sole writer in the worktree and a concurrent commit from me is the two-writer clobber the protocol exists to prevent. Queued as the next worktree write.

## Shared-state hazards: the instrument shares state with the thing it measures

Two mechanisms, one lesson. Both found on 2026-09-02 during Task 1; both now in the plan's Global Constraints so a later phase inherits them, because dispatch text dies with the run.

**(a) The shebang trap.** `<worktree>/.venv/bin/pytest` is a console script with an ABSOLUTE SHEBANG at the worktree's interpreter. Run from a copied tree it silently tests THE WORKTREE, so a mutation applied to the copy has no effect and the tests stay green. Found by the Task 1 spec reviewer's planted sentinel: 22 tests passed that should have been red. Correct form from a copy is `./.venv/bin/python -m pytest`; `PYTHONPATH=<copy>` also works (it precedes the plain-path `.pth` entries these editable installs use).

**(b) The shared-`.pth` trap.** Repointing the worktree venv's `_editable_impl_*.pth` at a scratch copy DOES achieve shadowing — destructively. Those pointers are shared global state: the orchestrator, the implementer and every concurrent reviewer import through them, so redirecting them redirects EVERYONE. It leaves no trace in `git status`, so the usual clean-tree check is structurally blind to it. Found by the Task 1 fix-round implementer, which discovered `_editable_impl_llama_radio.pth` and `..._herder.pth` aimed at a reviewer's scratch dir and repaired them before re-verifying. Standing rule: a child may NEVER modify the worktree venv's `.pth` files; shadowing is per-process (`PYTHONPATH`, or the copy's own interpreter), never by editing installed pointers.

Reusable guard, cheap enough to run at the start of every dispatch and before trusting any suite count:
  ./.venv/bin/python -c "import llama,herder,emcee,pathlib; wt=pathlib.Path('<worktree>').resolve(); print('PTH-GUARD:', 'OK' if all(wt in pathlib.Path(m.__file__).resolve().parents for m in (llama,herder,emcee)) else 'CORRUPT')"
Verified OK at 2026-09-02 09:44 EDT.

### Suite-count provenance (re-measured vs restated)
- 1557 / 7 deselected @ 98d752a — RE-MEASURED by orchestrator 09:17, before any child existed. Sound.
- 1560 / 7 @ 852e47d — RESTATED, not re-measured. Taken by the implementer ~09:25; the reviewers that corrupted the pointers were not dispatched until 09:27, so it falls OUTSIDE the corruption window. Independently corroborated by arithmetic: 1562 - 2 = 1560, and `git show 115f0f8 -- test_junk.py` adds exactly 2 test functions (test_dedupe_runs_before_play_order_derivation, test_dedupe_runs_after_junk_filtering).
- 1562 / 7 @ 115f0f8 — RE-MEASURED by orchestrator 09:43, after verifying all three `.pth` files point into the worktree and that llama/herder/emcee resolve there. Sound.

### Credit where it belongs
The fix-round implementer found the corrupted pointers, disclosed them in its commit message, and repaired them before re-verifying — against its own interest, since it could have silently fixed the pointer and let its green result stand unexamined. That disclosure is why the rest of its report is worth believing, and it goes in the Task 1 record as a strength, not a footnote.

### CORRECTION to hazard (b): the root cause is pip, not a deliberate repoint

My earlier entry said a reviewer "repointed the .pth files to shadow its copy". That is WRONG and the correction matters, because the true mechanism is not a choice anyone made.

`.venv/bin/pip` carries the SAME absolute shebang as `.venv/bin/pytest` — verified 2026-09-02: `.venv/bin/pytest`, `.venv/bin/pip` and `.venv/bin/llama` all begin `#!/Users/shawn/.../sibling-transfer/.venv/bin/python3.14`. So the Task 1 code-quality reviewer, doing the ordinary and sensible thing of running `./.venv/bin/pip install -e ... --no-deps` from its COPY to make the copy importable, silently reinstalled into the WORKTREE's venv and repointed the worktree's herder/llama `.pth` at its scratch tree. For ~15 minutes the worktree interpreter imported from that copy.

The generalization, which is the durable lesson: **in a copied tree NO console script under `.venv/bin/` is safe — every one of them is a shebang back into the original venv, and `pip` is the destructive member of the family because it writes.** `python -m <tool>` is the only form that follows the copy. This subsumes hazard (a): the pytest case is one instance of a general rule, not a quirk.

Second-order point worth keeping: the reviewer's *own* results were never invalid — it achieved real shadowing, just by accident and at the worktree's expense. The damage was entirely to OTHER agents. A method can be sound for its user and still poison everyone else, so "were my numbers right?" is the wrong question to ask about shared state.

Also of note: the reviewer's `sed` repair attempt was refused by the permission classifier and it did NOT work around it — it reported instead. That is the correct behaviour and the reason the corruption surfaced as a finding rather than a silent fix.

### Queued worktree actions (deliberately NOT done while children are live)
1. `./.venv/bin/pip install -e packages/herder -e packages/llama --no-deps` from the WORKTREE ROOT, to clear metadata residue: `llama_radio-0.1.0.dist-info/direct_url.json` and `llama_herder-0.1.0.dist-info/direct_url.json` still record the reviewer's scratch dir as install origin. `.pth` files themselves are correct; this is a latent landmine for the next reinstall, not a live fault. Deferred because a reinstall momentarily rewrites the very pointers a live re-reviewer imports through — doing it now would be the same class of mistake I am recording.
2. Generalize the plan constraint from `pytest` to all `.venv/bin/` console scripts, naming `pip` explicitly as the destructive one.
3. Add the one-line warning to the project CLAUDE.md beside its existing worktree/venv note, where every future session reads it.
  Ruling: item 3 goes in even though CLAUDE.md is outside this plan's file list. Why: the plan is read by the next phase, but CLAUDE.md is read by every session in this repo, and this defect cost two agents' worth of confusion in one morning. Cost if wrong: three lines of doc on a feature branch, trivially revertible.
Task 1: fix round 1/5 (4 addressed, 0 open; commits 852e47d..115f0f8). Re-review verdict APPROVED (Opus). Verdict: /private/tmp/.../sdd-phasec/t1-rerev/report.md
  Both mutants independently killed on a copy shadowed by PYTHONPATH + `python -m pytest`, worktree .pth untouched, shadowing proven twice (constant sentinel AND a behavioural one). Each mutation failed ONLY its own new test (1 failed / 1561 passed), so neither new test re-asserts existing coverage.
  Reviewer nuance recorded, no action: finding 2's test pins the placement via junk-provenance displacement rather than the median-perturbation pathway the finding named. It kills the stated mutation, which is what ADDRESSED requires; a median case would be an ADDITIONAL test on a >=5-file tape. Logged as a deferred minor for the final review rather than a fix round.
  Disputed provenance, SETTLED BY ARTIFACT: the re-reviewer asserted the corrupted pointers were the fix agent's own copy venv, not the worktree's. That is wrong. At 09:44 I read the worktree's own site-packages and found `llama_radio-0.1.0.dist-info/direct_url.json` and `llama_herder-.../direct_url.json` recording `workc/t1-rev-qual/packages/{llama,herder}` as install origin — objective proof that a `pip install -e` naming the CODE-QUALITY reviewer's copy wrote into the WORKTREE's site-packages. The quality reviewer's own account matches. Ruling: the quality reviewer's pip-from-copy is the established cause; the re-reviewer's provenance claim is a factual error that does not touch its verdict (it verified the diff, not the venv's history).
Task 1: complete (commits 98d752a..115f0f8, review clean after 1 fix round).
  Suite RE-MEASURED by orchestrator after venv normalization: 1562 passed, 7 deselected (`./.venv/bin/pytest -q`), PTH-GUARD OK, all three direct_url.json now record worktree paths.
Task 2: implementer DONE (Sonnet). Commit 77478b9 (scripts/numeric_title_census.py new, titles.py widened, test_titles.py +6).
  Suite RE-MEASURED by orchestrator: 1568 passed, 7 deselected (was 1562, +6). PTH-GUARD OK. Tree clean.
  Census verdict: ZERO qualifying items -> global scope, no STOP. Over 2,095 iacache items (2,064 with kept files): exactly 2 pure-4-digit tag titles total, 1 each on 2 different items, no item with >=2, neither equal to its item's own metadata.year. Both hand-checked as real songs (Mike Watt covering The Clash "1977"; the Stooges' "1970"), not date stamps.
  Acceptance mutation self-run: reverting the widening failed test_is_real_title_accepted_a_year_like_numeric_title (exact required name: test_is_real_title_accepts_a_year_like_numeric_title) with `assert False is True`; to be independently re-run by the spec reviewer.
  Deferred by implementer, judgement referred to reviewers: a stale docstring comment in test_correspondence.py still describes the OLD is_real_title("1922") behaviour. Assertions unaffected. Out of Task 2's file scope.
Task 2: review dispatched — spec-compliance (Opus, t2-rev-spec) and code-quality (Opus, t2-rev-qual), concurrently, out-of-worktree copies, PYTHONPATH shadowing only (pip explicitly forbidden after this morning's incident).
  Orchestrator's own review steer, given to BOTH reviewers because it is the highest-risk thing here: "2 hits across 2,095 items" is exactly the shape an extraction failure takes. A census that never looked and a census that looked and found little produce identical output. Both told to establish the census CAN return non-empty (known-positive case, real field names, right corpus) before crediting the number. Also flagged: the census walks `iacache` (2,095 items) while Task 1's sweep walked ~/.llama/cache/md_*.json (968) - reviewers to confirm the population is the one the brief asked for.
Coordinator ruling (2026-09-02 ~10:05) on the corpus discrepancy — SETTLED, do not reconcile:
  `iacache` (~2,095) is a DECADE-STRATIFIED SAMPLE, the corpus behind the existing LOSSLESS_TITLE_FORMATS measurement ("sole lossless source for 209 of 2,095 items"), which already carries the caveat that it is NOT a rate over shows llama would select.
  `~/.llama/cache/md_*.json` (~968) is the WORKING CACHE — what llama actually fetched. docs/2026-08-07-lma-census.md records it must NOT be used for archive-wide figures; ~40% high from selection bias.
  Task 1 asked "does this change anything llama has actually gathered" -> working cache. Task 2 asks "how common is year-junk in the wild" -> stratified sample. Both correct for their own question. Pushed live to both in-flight reviewers, redirecting them from "reconcile the counts" to "confirm the framing".
  Converted into a REQUIREMENT rather than a note: the census write-up AND the constant's comment must NAME the corpus and carry the stratified-sample caveat. An unlabelled "2 of 2,095" reads as an archive-wide rate to the next person — precisely the error the census doc exists to prevent. Both reviewers told to file its absence as Important, on the grounds that provenance-free numbers in constant comments are how this codebase's do-not-retune discipline decays.

TASK 2 FIX ROUND IS NOW CERTAIN regardless of reviewer verdicts. Scope fixed in advance so findings can be batched into ONE dispatch (per the skill: one fix dispatch with the complete list, never one fixer per finding):
  (a) Cross-check the same census over the 968-item working cache. Owner's rationale: if year-junk is absent in BOTH the general population and the one production actually touches, the global-scope decision is supported on two independent bases, which is a stronger claim than either alone. A disagreement between them is itself a finding.
  (b) Corpus naming + stratified-sample caveat in the comment and the write-up (above).
  (c) Fix the stale test_correspondence.py docstring that describes the OLD is_real_title("1922") behaviour.
  Ruling on (c), overriding my earlier deferral: it ships in this phase, not later. Why — the comment documents the exact opposite of behaviour THIS task deliberately changes, it is one line, and this project has already been bitten twice by exactly this class (the misattributed `forced` comment; the stale line-number citation). Deferring a stale comment written by the change that staled it is how the next reader gets misled. Cost if wrong: one line of diff in a round that is happening anyway.
Task 2: spec review SPEC (Opus) + quality review CHANGES REQUESTED (Opus). Verdicts: .../t2-rev-spec/report.md, .../t2-rev-qual/report.md
  THREE findings reached independently by both reviewers, neither seeing the other's work: the self-invalidating `crosses` arm, the missing stratified-sample caveat, and the undisclosed production stale reference.
  Census validity — MY MAIN CONCERN, ANSWERED. The "2 of 2,095" is a real reading, not a silent zero. Spec reviewer proved the instrument can return non-empty THREE ways: schema check (1,962/2,095 items carry audio `title`), a planted synthetic positive control run through the COMMITTED script (found both items, tripped the >=2 STOP condition, correctly matched a planted date stamp against metadata.year), and an independent regex oracle sharing no code with the census. The oracle is what found the missing third item.
  Instrument defects found (code and ruling both stand): (F1) census breaks on first non-empty format, hiding `turkuaz2018-01-18`'s flac-only `1662` — the purest sibling-format recovery case, mp3 fraction 0.000 < _RECOVER_BELOW and flac 0.923 > _RECOVER_SIBLING_ABOVE, so recovery fires and the title reaches the tag rung. True figures 3/3/3, not 2/2/2. (F2) the `crosses` arm calls the live is_real_title, so the committed script cannot reproduce the committed report. (F4) undisclosed stale site in PRODUCTION source, correspondence.py:105-110.
Task 2: fix round 1/5 dispatched — original implementer resumed (Sonnet), ONE batched dispatch carrying all 7 items + the nit.

RULING on the `structure._hygienic` exposure — analysed, NOT escalated as a scope question, because it is not one:
  The quality reviewer measured that global scope also opens `_hygienic` (structure.py:1104), the pipeline's only SILENT adopter: 181 pure-4-digit canonical items of 48,031, 163 absorbed by _date_norms, 18 newly passing — including `2448` (a flac2448 lineage string), `2026` on a 2025 show, `2020` on a 1994 show. Real junk, and the plan's STOP gate never looked at this rung.
  But the plan's two options are: GLOBAL = widen `is_real_title` itself; HYGIENE-ONLY = "only the sibling/setlist-gap adoption check accepts it, the tag rung unchanged". The adoption check IS `_hygienic`. So hygiene-only deliberately opens `_hygienic` too — the 18-item exposure is IDENTICAL under both options and cannot be avoided by re-scoping. The only thing scope changes is whether the TAG rung also opens, and the tag-rung effect is exactly 3 items, all hand-checked real songs (`1977`, `1970`, `1662`), with zero gate flips at _RECOVER_BELOW/_RECOVER_SIBLING_ABOVE.
  Ruling: global stands. It gains 3 correct titles at the tag rung at no additional `_hygienic` cost, so it strictly dominates hygiene-only. What the exposure DOES require is to be written down as a sized, accepted risk rather than left implied — that is in the fix round. Cost if wrong: the 18 `_hygienic` items would need a separate narrowing, which is a follow-up change either way and is not made cheaper by choosing hygiene-only now.

## CARRIED OBLIGATIONS FOR TASK 7 — owner requirements, must reach Task 7's dispatch
Source: coordinator ruling 2026-09-02, confirming global scope and adding precision requirements on the `_hygienic` exposure.

Confirmed: GLOBAL SCOPE STANDS. The owner reads the plan's hygiene-only option the same way — both options open the same 18 `_hygienic` items, so scope decides only whether the tag rung also opens, where the effect is 3 hand-checked real songs with zero gate flips. Same downside, strictly more upside.

The distinction that must not be lost: **"passes `_hygienic`" is NOT "gets adopted".** 18 items clearing a predicate is an UPPER BOUND on exposure, not the exposure. A title only ships if the rung fires, the run is count-forced between anchors, and nothing upstream already resolved it. The true figure could be 18, or 2, or 0. A risk note claiming "18 junk titles now pass" when the real number is 1 is as misleading as one that understates it.

  T7-OBLIGATION-1 (folded into Task 2's fix round, ALREADY DISPATCHED): enumerate all 18 with the mechanism for each, not a bare count — a list survives, a count decays into folklore. Plus: state which number is measured and which is a bound IN THE SAME SENTENCE.
  T7-OBLIGATION-2 (Task 7): MEASURE pass-vs-adopt. Of the 18, how many actually alter a shipped track title in a real re-gather? That is the number the risk note should lead with, with 18 as the population it was drawn from. Size it with Task 7's re-gather harness; do not guess earlier.
  T7-OBLIGATION-3 (Task 7): if ANY of the 18 do adopt, they are a NAMED REGRESSION CLASS in the evidence doc, not a ledger line. Rationale, which is the sharpest framing of this whole phase's purpose: `_hygienic` is the pipeline's ONLY silent adopter — the one surface where a wrong title ships with no flag and no operator ever sees it. A silent adopter taking `2448` as a song title is worse than anything the operator path can do wrong.

  PENDING WORKTREE ACTION (deferred while the fix-round implementer is sole writer): add obligations 2 and 3 to the plan's Task 7 acceptance criteria and REGENERATE task-7-brief.md, so they reach the Task 7 implementer through its requirements file rather than only through dispatch prose. Dispatch text dies with the run; this is the same durability argument that moved the venv rules into the plan and CLAUDE.md.

## Standing methodology bar for the rest of Phase C (owner, 2026-09-02)
Prove an instrument THREE independent ways before crediting its numbers, as the Task 2 spec reviewer did: (1) a schema check, (2) a planted synthetic positive control run through the COMMITTED script, (3) an independent oracle sharing no code with the instrument. It earned its cost immediately — the oracle found `turkuaz2018-01-18`'s flac-only `1662` precisely BECAUSE it did not share the census's first-non-empty-format assumption. The durable lesson: prefer REDUNDANT instruments over merely careful ones. A careful instrument still cannot see its own blind spot; a second instrument built on different assumptions can. This bar now applies to Tasks 3-7, above all Task 7's blind arm and controls.
Task 2: fix round 1/5 committed 076a990 (all 7 findings + the nit + the late owner requirement). Suite RE-MEASURED by orchestrator: 1567 passed, 7 deselected. PTH-GUARD OK, tree clean.
  Count RECONCILED, not restated: 1568 -> 1567 is a net -1 from the negative parametrize going 5 cases -> 4. Removed "d1t02" (covered by test_is_real_title above), "12" (subsumed by "01" -- both only constrain the lower bound) and "3"; added "19770101" (a yyyymmdd date stamp, the exact junk class) and "12345" (minimal one-over). 3 removed, 2 added, -1. Verified by diffing the parametrize lists at both commits rather than trusting the arithmetic.
  Corrected census: 3 items / 3 titles / 3 distinct values, third being turkuaz2018-01-18's flac-only `1662`. `crosses` arm now uses frozen local old/new predicates so the script reproduces against the post-change tree.
  Owner's cross-population check DELIVERED and it found something: the ~968-item WORKING CACHE carries 1 further occurrence -- "1922", on a sibling recording of trampledbyturtles-2007-07-20. Also below the STOP threshold, so BOTH corpora independently support global scope despite differing raw counts. That is the two-independent-bases result the owner wanted, and note the title it found is the very one the spec's composition note is about.
  Late owner requirement DELIVERED: the 18 `_hygienic` items are ENUMERATED in the constant's comment, explicitly labelled an UPPER BOUND on exposure and not a measured shipped-title count, with Task 7 named as where the pass-vs-adopt figure gets measured. Implementer independently re-derived the population rather than copying the review: it reports 181 of 48,031 and **162** absorbed by _date_norms where the reviewer said 163 -- a one-item discrepancy it surfaced rather than silently adopting either number. Flagged to the re-reviewer to adjudicate.
  Upper bound now pinned: _YEAR_LIKE_NUMERIC uses fullmatch on r"\d{4}" (was an unanchored-in-effect r"^\d{4}$"); the \d{4,} mutation is verified red on test_is_real_title_still_rejects_non_year_numeric_residue[19770101] and [12345].
  Both stale sites corrected, production docstring first (correspondence.py) then test_correspondence.py.
  Minor coverage note for the re-reviewer: dropping "3" removes the only single-digit negative case. "01" still covers sub-4-length rejection, so this is almost certainly harmless, but it was not among the findings and should be confirmed rather than assumed.
  PENDING WORKTREE ACTION CLEARED: commit 06d526e adds Task 7's Step 6 (the enumerated `_hygienic` exposure, pass-vs-adopt measurement, and the named-regression-class requirement) plus the three-independent-instruments bar to Task 7's acceptance criteria, and task-7-brief.md was REGENERATED so the Task 7 implementer receives both through its requirements file rather than dispatch prose.
Task 2: scoped re-review dispatched (Opus, t2-rerev), scope 77478b9..076a990.

## Owner ruling: the `"3"` coverage gap, and the mechanical lesson behind it (2026-09-02)
Owner read the source directly and split the question I had left open:
  `d1t02` — FINE, no action. Retained at test_titles.py:98 in test_is_real_title's parametrize, with an explicit cross-reference comment at line 138 saying it is covered there and not repeated. Relocating a case WITH a source-level cross-reference is the right way to do it.
  `"3"` — GENUINELY UNCOVERED. The retained parametrize at lines 96-99 is ("Deal",True),("Jam",True),("Here Comes Sunshine",True),("d1t02",False),("",False),("A B",False) — no single-digit case anywhere. So my "01 surely covers it" was not merely unverified; it is now the ONLY thing standing behind single-digit rejection, and nothing pins it.
  Severity, stated precisely: behaviour did NOT change (`"3"` still fails the letter-count rule and is not four digits). This is lost PINNING, not lost correctness. But lost pinning is the exact class this phase exists to be strict about. One-line restoration, folded into whatever round the re-review opens; no dedicated dispatch.

STANDING PROCESS RULE, adopted — this is the second coverage-shrink to slip through inside a FIX round, i.e. a round whose entire purpose was closing hollow pins:
  **A fix round that reduces the suite count must account for the delta CASE-BY-CASE in its report** — not merely leave it reconcilable by whoever goes looking. Both the owner and I reconciled 1568->1567 independently; that is redundancy working, but it should not have needed two of us, and neither of us was the party who knew why each case was dropped.
  Not a criticism of the implementer: it documented the `d1t02` relocation properly in the source and its `"12"`-is-subsumed-by-`"01"` argument is sound. The defect is that a net count change was reported as a number rather than as a per-case ledger.
  PENDING WORKTREE ACTION (deferred while the re-reviewer is live): add this rule to the plan's Global Constraints, beside the "acceptance is never a shape test" bullet. Same durability argument as the venv rules and the Task 7 obligations — a rule that lives only in a ledger does not reach Tasks 3-7's implementers.
Task 2: scoped re-review (Opus) — ALL SEVEN findings ADDRESSED, no new Critical/Important breakage. Verdict: /private/tmp/.../sdd-phasec/t2-rerev/report.md
  Verified by independent instruments, not by reading the diff: an oracle with ZERO llama imports (raw JSON walk) reproduced 3/3/3 and confirmed turkuaz2018-01-18's 14 mp3 files carry 0 titles so `1662` is flac-only; the `crosses` arm re-run on the post-change tree prints 3, not the zeros the old arm forced; the cross-population hit reproduced exactly (tbt2007-07-20.391.flac16).
  Finding 4 anchoring is genuine and BETTER than asked: `x1977`, `1977x`, `' 1977'`, `'1977 '` and `'1977\n'` all False — fullmatch also closed a trailing-newline hole that `^\d{4}$` actually had.
  162-vs-163 ADJUDICATED, and it was never a disagreement: entry-vs-item granularity. 181 entries - 19 entries = 162; 181 - 18 DISTINCT ITEMS = 163. minutemen1984-07-14 carries two values and is the boundary. The comment commits to 162, which is correct.
  The `"3"` gap CONFIRMED BY MUTATION, not by reading: compiling r"\d{4}|\d" — accepting EVERY single digit as a real title — passes the entire 1567-test suite. Nothing pins single-digit rejection. This is the strongest possible form of the owner's finding and vindicates asking for it to be proven rather than presumed.
Task 2: fix round 2/5 dispatched (original implementer resumed, Sonnet) — 3 one-line Minors: restore "3"; drop the unsupported metadata-approximation attribution (162 holds under two different date-source approximations, so the attribution claims a sensitivity that isn't there); fix titles.py:115-118 calling the exposure "not real songs" while the same block establishes 1977 and 1662 ARE real songs.
  Deferred, PRE-EXISTING, not to be fixed here: `\d` matches Unicode digits, so is_real_title("١٩٧٧") is True. Equally true of the old ^\d{4}$; not introduced by this task. -> final whole-branch review.
  Plan constraint 48d6d61 landed: a fix round that reduces the suite count must account for the delta CASE-BY-CASE in its report. Applied to round 2's own report as its first test.

## Three findings recorded in their durable form (owner direction, 2026-09-02)

**(1) The `"3"` result is an INSTRUMENT finding, not a restored test case.** Recording it as "restored a parametrize case" would badly understate it and mislead whoever inherits this. The correct statement: the re-reviewer compiled `r"\d{4}|\d"` — a predicate accepting EVERY SINGLE DIGIT as a real title — and the **entire 1567-test suite passed**. So single-digit rejection was never pinned by anything, INCLUDING BEFORE this task touched the predicate. The dropped `"3"` case did not create the hole; it was the only thing that had ever been near it, and it was itself never load-bearing (it passed for the letter-count reason, not the digit-length reason). The restoration is a one-liner; the fact it uncovered is that a whole class of junk-title rejection was resting on nothing. Same lesson as the phase's other instrument findings: reading cannot see this, only mutation can.

**(2) Unicode-digit deferral — ENDORSED by the owner, with the fix shape recorded so the final review does not re-derive it.**
  Defect: `\d` matches Unicode digits, so `is_real_title("١٩٧٧")` is True. PRE-EXISTING — equally true of the old `^\d{4}$` — and genuinely rare, so it stays out of round 2.
  Likely fix when the final review picks it up: **one character class, `[0-9]{4}` rather than `\d{4}`.** In-repo precedent for being explicit about ASCII in this exact area: `titles._TRACK_NUM_PREFIX`'s `\d{1,3}` bound is load-bearing and documented as such, and the rest of `is_real_title` already demands ASCII letters — so an ASCII digit class is the CONSISTENT reading, not a new policy.
  Standing instruction to the final review: if it needs more than the character class plus a test, that is a finding and it stays DEFERRED rather than expanding a final-review round.

**(3) Name the unit whenever a count is committed to a comment.** The 162-vs-163 episode was not a disagreement: 181 entries - 19 entries = 162; 181 - 18 DISTINCT ITEMS = 163, with `minutemen1984-07-14` the boundary case carrying two values. Two agents measured the same population correctly and reported different numbers because neither had stated the unit. A bare "162" in a comment invites exactly this. Rule: a committed count names its unit (entries / distinct items / shows / files), not just its population and date.
  PENDING WORKTREE ACTION (deferred while the round-2 implementer is sole writer): add this to the plan's Global Constraints beside the citation-style requirement.

**(4) The `fullmatch` change closed a live bug, not just an unpinned bound.** `$` matches before a final newline in Python, so the old `^\d{4}$` accepted `'1977\n'`. That is a classic and it was live in shipped code. Record as a real gain: the fix for an UNPINNED bound also closed an ACTUAL hole nobody had reported.

## PACING CHECKPOINT 2026-09-02 10:30 EDT — Phase C does not fit this window
Meter: 5h 50%, 7d 9%. burn5=39.2%/hr, binding=5h, headroom=77min. 5h resets 14:09.
Projection: at 39.2%/hr the 5h window exhausts ~11:47, ~2h20m BEFORE its own reset. Tasks 1-2 cost 50 points (including the Phase B audit and three fix rounds). Tasks 3-7 remain and are larger; Task 7 is the Opus measurement gate. Room for ~1 more task before the owner's 70% stop band, not 5.
Reported to owner with three options; my recommendation (c) then (a):
  (a) one Opus reviewer per task for 3-7, land Task 3 (+maybe 4), hand back at 70%.
  (b) keep two reviewers, land Task 3 only.
  (c) stop after Task 2 closes, checkpoint, resume Tasks 3-7 in a fresh window at 14:09 with full headroom.
Reasoning for (c): Tasks 3 and 4 are the DP and the C+ guards — the technical core carrying all four spec invariants. Beginning them at 50% with a wall at 11:47 risks a mid-task kill, and a half-done Task 3 is exactly the "compiles, passes, and is wrong" state the delegation guidance warns about; the standing remedy is revert-and-redispatch, so a kill there wastes the whole task rather than part of it.

  RULING (overrulable by the owner, and surfaced to them because it materially changes burn): I have been over-provisioning review. I dispatched TWO Opus reviewers per task (separate spec-compliance and code-quality agents); the superpowers skill's own design is ONE task reviewer emitting BOTH verdicts, and its task-reviewer-prompt.md explicitly covers both halves. The user's rule fixes the MODEL (Opus, always) and that review happens, not the agent count. Switching to one reviewer per task roughly halves review cost for Tasks 3-7.
  Cost if wrong: loses independent convergence, which has demonstrably paid — Task 1's two reviewers hit the same hollow-pin finding blind, and Task 2 had three findings reached twice independently. That is also the single most expensive thing this run does. Recorded as a genuine trade, not a free saving.

## RULING OVERTURNED — reviewer count stays at TWO. My authority reasoning was wrong.
Owner-side decision 2026-09-02 10:31 (independently confirmed meter: 51%, 39.3%/hr, wall ~11:46, reset 14:10).

I argued that consolidating to one Opus task-reviewer was justified because "the superpowers skill's own design is one reviewer emitting both verdicts". That premise is true about the skill and IRRELEVANT as authority. **`~/.claude/CLAUDE.md` names implementer, spec-compliance reviewer and code-quality reviewer as three DISTINCT roles and requires both reviewers on Opus, and the user's file outranks the skill's shape.** I reached for the skill because it agreed with the answer I wanted on cost, which is motivated reading of a precedence order I already knew — the same file opens by stating it outranks harness defaults. Recorded as MY error, not a close call: a cost pressure produced a authority argument, rather than an authority question producing an answer.
Second, independent reason the consolidation was wrong on the merits: the evidence was running AGAINST it in the same breath I proposed it. Two reviewers independently hit the same hollow-pin finding on Task 1; three findings were reached twice on Task 2; the census oracle found `1662` precisely BECAUSE it did not share the census's assumptions. Cutting the second reviewer on entry to Tasks 3-4 — where the four spec invariants live and are subtlest — optimises the wrong variable at the worst moment.
Standing: TWO Opus reviewers per task for Tasks 3-7. If pacing later makes the cost genuinely binding, that is a question for the USER, not a call the orchestrator or the coordinator makes silently. The trade has been relayed upward.

## DECISION: option (c) — stop after Task 2, resume Tasks 3-7 in a fresh window after the 14:10 reset.
Task 2: fix round 2/5 (3 addressed, 0 open; commit e1c0be9). Scoped re-review APPROVED (Opus). Verdict: /private/tmp/.../sdd-phasec/t2-rerev2/report.md
  Finding 1 verified BY MUTATION, not by reading: mutating _YEAR_LIKE_NUMERIC to re.compile(r"\d{4}|\d") turns test_is_real_title_still_rejects_non_year_numeric_residue[3] RED --
    assert is_real_title(cleaned) is False / E AssertionError: assert True is False / + where True = is_real_title('3')
  1 failed of 57, the SOLE failure, which also proves it is the only single-digit case exercising the predicate. Mutation reverted; copy byte-identical after.
  Suite delta itemised per the new constraint: 1567 -> 1568, +1 attributed to the restored "3" alone, plus a retroactive case-by-case for the round-0 -> round-1 -1.
Task 2: complete (commits fd0f92d..e1c0be9, review clean after 2 fix rounds).
  Suite RE-MEASURED by orchestrator at checkpoint: 1568 passed, 7 deselected (`./.venv/bin/pytest -q`), PTH-GUARD OK, tree clean at e1c0be9.

## ============ CHECKPOINT: SESSION PAUSED 2026-09-02 ~10:35 EDT ============
Reason: 5h rate-limit window. Meter 50-51%, burn ~39%/hr, projected wall ~11:46 vs reset 14:10 — burning to the wall would discard ~2h20m of window and buy at most one task. Owner chose option (c): stop after Task 2, resume Tasks 3-7 in a fresh window.

STATE OF THE BRANCH: `sibling-transfer` @ e1c0be9 (+ the checkpoint commits below). Tree clean. Suite 1568 passed, 7 deselected. Nothing pushed, nothing merged, no tags, worktree intact.

TASKS COMPLETE: 1 (filter_files duplicate-listing dedupe) and 2 (numeric-title census + is_real_title global widening). Both reviewed by two Opus reviewers and re-reviewed after fix rounds.

### WHERE TASK 3 PICKS UP — no context re-derivation needed
Next action: dispatch the Task 3 implementer. Nothing is in flight; no task is half-done.
  Brief (already generated, current): .superpowers/sdd/2026-09-02-sibling-title-transfer/task-3-brief.md
  BASE for its review package: e1c0be9 (or whatever HEAD is after the checkpoint commits — re-read it, do not assume).
  Task 3 creates packages/llama/src/llama/siblings.py + tests/test_siblings.py: the duration DP (`align_durations`, `propose_rows`), `DonorTape`/`SiblingRow`, whole-tape preconditions, per-row declines. PURE — no I/O, no LLM, no imports from stages/.
  Its two named acceptance mutations: (i) replace the DP call with positional transfer `titles[i] = donor.titles[i]` — the A2-shaped test must fail; (ii) set MIN_EXCLUSION_PENALTY = 0 — the near-ambiguous test must adopt and fail. A mutation that breaks nothing is a finding against the tests.
  Model call OWED to the owner with justification, not asserted: the plan sizes Tasks 3-4 as "well-specified ports of measured prototypes -> Sonnet, with the mutations as the reviewer's teeth"; the owner's expectation is Opus for both. Argue the departure explicitly rather than silently agreeing.
  Reviewers: TWO Opus per task (spec-compliance + code-quality), per the overturned-ruling entry above. Not negotiable at orchestrator level.

### CARRY-INS THAT MUST NOT BE LOST (all now in committed files, not just here)
  - Plan Global Constraints now carry: the console-script/venv hazards, the fix-round-shrink itemisation rule, and the count-unit-naming rule.
  - CLAUDE.md carries the copied-tree console-script warning.
  - Task 7's acceptance in the plan carries Step 6 (the enumerated `_hygienic` exposure, pass-vs-adopt measurement, named-regression-class requirement) and the three-independent-instruments bar. task-7-brief.md was regenerated to match.
  - Deferred minors for the FINAL whole-branch review: Task 1's seven (redundant `order` list; cross-dir key vs titles._stem_no_ext; test name overstates "byte-identical" at test_junk.py:240; sweep n_pairs counts absent formats; and the median-perturbation test that would strictly add to finding 2's pathway), plus Task 2's Unicode-digit gap (`\d` matches Unicode digits, so is_real_title("١٩٧٧") is True — PRE-EXISTING, likely fix is `[0-9]{4}`, and if it needs more than the character class plus a test it STAYS deferred).

## ============ SESSION RESUMED 2026-09-02 14:13 EDT ============
Fresh 5h window: meter 2%, resets 19:10, burn unconstrained. Owner gave the go for Tasks 3-7.
Verified before dispatching, not restated: BASE RE-READ as 0548092 (not assumed from the checkpoint), tree clean, PTH-GUARD OK, baseline RE-MEASURED 1568 passed / 7 deselected.
Reviewer count: TWO Opus reviewers per task, unchanged. If pacing binds again it is a boundary escalation, not an orchestrator-level consolidation.

Task 3: dispatched, implementer on **OPUS** (departing from the plan's Sonnet sizing; argument recorded below and given to the owner).
  Case for the plan's Sonnet sizing: DP ops and cost function fully specified; dataclass shapes and signatures given verbatim; 8 test cases enumerated with expected strings; a measured prototype exists and may be read.
  Case for Opus, which I took:
   (1) It is NOT transcription. This phase's own rule is that shipped code is written FRESH against the spec and not copied from the scratch prototype — so it is a guided reimplementation of a subtle DP from prose, which is explicitly not the cheapest tier.
   (2) DECISIVE: Task 3 fixes the DATA MODEL that Tasks 4, 5 and 6 all consume. Task 4's C+ guard brackets fill runs USING `donor_span`, so a wrong span convention (half-open vs inclusive; what a merged pairing's span means) propagates straight into the guard whose whole purpose is preventing silent adoption — and propagates invisibly.
   (3) The failure mode is silent-and-plausible: a DP with an off-by-one in the merge window still emits perfectly plausible titles, just wrong ones. That is the class this phase has caught only by mutation, never by reading.
   (4) These row semantics seed Task 7's ship-gate numbers, so an error here silently invalidates the measurements rather than failing loudly.
   (5) Cost is not binding — fresh window at 2%.
  Where I would have taken Sonnet: if the prototype were copied verbatim, or if Task 3's output were consumed only by its own tests. Neither holds.
  Steered explicitly on the span convention: told to document it in the dataclass docstring and pin it with a test, since that is the interface Task 4 inherits.
Task 3: implementer DONE_WITH_CONCERNS (Opus). Commit ce80541 (siblings.py 304 lines + test_siblings.py 322 lines, +626, nothing else touched).
  Suite RE-MEASURED by orchestrator: 1587 passed, 7 deselected (baseline 1568, +19 new, none removed or rewritten). PTH-GUARD OK, tree clean.
  Both named mutations verified by the implementer on out-of-worktree copies with `python -m pytest` + PYTHONPATH and pycache purged:
    positional transfer -> test_a2_deleted_donor_head_track_declines_the_orphan_and_keeps_the_rest RED at test_siblings.py:147, `assert got[1].verdict == "decline"` / `AssertionError: assert 'adopt' == 'decline'` (7 failed, 12 passed)
    MIN_EXCLUSION_PENALTY = 0.0 -> test_near_ambiguous_pairing_declines_on_weak_evidence RED at :194, same assertion line (1 failed, 18 passed) — NOT hollow, no rewrite needed
  Span convention chosen and documented: `track` 1-based (matching Track.track); `donor_span` HALF-OPEN over 0-BASED donor indices, deliberately the same shape anchor_spans/gap_span return so Task 4 reuses them unconverted. Split rows share one span, docstring says "do not sum them".
Task 3: review dispatched — spec-compliance (Opus, t3-rev-spec) and code-quality (Opus, t3-rev-qual), concurrently, out-of-worktree copies, PYTHONPATH shadowing only.
  Both told to probe the SPAN CONVENTION specifically — whether it is PINNED by a test or merely documented — by mutating it to inclusive or 1-based and seeing if anything goes red. That is the interface Task 4 inherits and the one place being right by accident looks identical to being right on purpose.
  Three implementer concerns handed to BOTH reviewers for INDEPENDENT adjudication, with my own view withheld so as not to pre-judge:
    (a) penalty_sec = inf ("forced") is unreachable; branch kept, meaning pinned by a different test. Dead code or defensible?
    (b) The brief's near-ambiguous sketch DOES NOT WORK as written — two adjacent 300s songs yield ~600s penalty, not the sub-60 the test needs. Implementer substituted a short-adjacent-fragment fixture (25s donor track, 10s drift, penalty 20). Reviewers to verify the substitute genuinely exercises the sub-60 path rather than assuming it.
    (c) propose_rows re-solves the DP per matched op — fine at tape scale, but Task 5 fans it over every donor of every show.
  Also filed by the implementer for Task 7, not blocking: a target-side skip is structurally rare because skipping and absorbing cost the same under L1, so `no sibling track` only appears where absorption is illegal (2:2 barred, or MAX_MERGE); elsewhere the DP reports a merge and declines those rows, so one deleted donor track can cost TWO rows. It deliberately did NOT add a skip-preferring tie-break because that would invalidate the spec's measurements — restraint I want the reviewers to confirm rather than praise.

## Owner responses on Task 3 (2026-09-02 ~14:35) — one confirmation, one endorsement, one instruction

**(1) Tie-break restraint CONFIRMED CORRECT, with the reason stated.** Declining a skip-preferring tie-break because it would invalidate the spec's measurements is right because every number in the spec — the 0.80 knee, the marginal-error bands, the 28/28 six-show result — was measured against a DP with these exact cost semantics. A tie-break changing which of two EQUAL-COST solutions wins changes the population those numbers describe, SILENTLY, and nothing in the suite would notice. Ship the measured behaviour, file the improvement.
  T7-OBLIGATION-4 (new): file it with a DECISION CRITERION, not as an observation. Task 7 must answer, with numbers: how often does a target-side skip actually arise in the corpus, and when it does, how many rows does the two-row cost affect? "Structurally rare, and it cost N rows across the blind arm" is a finding a future phase can act on. **"Structurally rare" alone decays into folklore — the same failure the unit-naming rule exists to prevent.**

**(2) Span-convention attack endorsed as the highest-value thing this review round does.** Standing: if mutating the span to inclusive or 1-based turns NOTHING red, that is a finding against the tests REGARDLESS of how correct the implementation is. Already in both reviewers' dispatches.

**(3) INSTRUCTION — fix the plan, not just the test.** The brief's near-ambiguous sketch (two adjacent 300 s songs) is arithmetically impossible: it yields ~600 s penalty, not the sub-60 the test needs. Once the reviewers confirm the substituted fixture genuinely exercises the sub-60 path, CORRECT THE SKETCH IN THE PLAN FILE AND COMMIT IT, with a one-line note that the original numbers were arithmetically impossible. Otherwise the next reader of Task 3's brief rebuilds the wrong fixture and the working one survives only in a scratchpad report. **A plan defect discovered is a plan defect fixed** — the same durability argument that has moved five rules into files this run.

  QUEUED WORKTREE ACTION, one commit, deferred until the two reviewers land: (a) correct the near-ambiguous sketch in the plan's Task 3 + regenerate task-3-brief.md; (b) add T7-OBLIGATION-4 to the plan's Task 7 Step 6 + regenerate task-7-brief.md. Both touch the same file, and (a) is gated on reviewer confirmation by the owner's own construction, so they batch into one commit rather than writing under live children.

**Owner rulings deferred to the reviewers, recorded so I do not re-decide them:** the unreachable `penalty_sec = inf` branch is the Phase B **N1 class** — a defensive branch whose docstring claims a pin that does not exist; the resolution is either pin it or say plainly it is unreachable and why it is kept. The per-op DP re-solve is a real cost question, but Task 5 is where its fan-out becomes measurable, so a reviewer's call plus a Task 5 note is the proportionate response.
Task 3: spec review SPEC PASS (Opus); code-quality CHANGES REQUESTED (Opus), 4 Important + Minors.
  SPAN CONVENTION IS PINNED — confirmed independently by BOTH: inclusive (j0,j1-1) -> 3 red; 1-based (j0+1,j1+1) -> 3 red; a 0-based `track` also reds them. The round's highest-risk item, and it held.
  Both named mutations reproduced independently. Mutation 2 fails EXACTLY ONE test of 1587, so precisely one test leans on MIN_EXCLUSION_PENALTY — no accidental over-coupling.
  Concern 2 VINDICATED NUMERICALLY: the brief's sketch measures 600 s on every row and adopts them all — it can never reach the sub-60 path. Substitute measures 20 s. -> plan corrected in e251feb per the owner's "a plan defect discovered is a plan defect fixed".

  RULING on a genuine reviewer DISAGREEMENT (settled by reading both sources myself, as with the .pth provenance dispute):
  Spec reviewer: "hygiene composed from imported predicates, nothing reimplemented." Quality reviewer: "_hygienic_title is a VERBATIM copy of structure._hygienic:1095-1107, comment included."
  BOTH ARE RIGHT ABOUT DIFFERENT THINGS. The four PREDICATES are genuinely imported (spec reviewer correct). The COMPOSITION — the entire return expression plus the aliases comment — is duplicated (quality reviewer correct). My dispatch said "import the predicates, do not reimplement or copy THEM", which the implementer satisfied literally; the duplicated composition is the defect the wording did not reach.
  Decisive evidence that the guard does not work: the spec reviewer added an arm to structure._hygienic (`not t.endswith("!")`) and ALL 19 TESTS STAYED GREEN. The equality table cannot detect the drift it exists to catch.
  Ruling: PROMOTE to a public `structure.hygienic_title`, import it in both places, delete the duplicate and the equality table. This touches structure.py, OUTSIDE Task 3's stated file list — allowed by my ruling, because Task 4 opens that file anyway and leaving it means Tasks 4-6 build on two definitions that can silently diverge. Cost if wrong: a small structure.py diff lands one task earlier than planned.
  Note the spec reviewer's counterpoint, which the promotion answers rather than overrides: the real justification for not importing `_hygienic` was that it is PRIVATE to structure — so making it public is the fix, not a workaround.

  REAL BUG found (not a pin gap): siblings.py:252's `all(d > 0 ...)` raises TypeError on None, and None is exactly how models.Track.duration_sec: float | None expresses "missing". Verified by me by reading; verified as a crash by the reviewer. Task 5 feeds Track durations, so this would fire in production. This is the first genuine runtime defect the phase has caught, as opposed to an unpinned invariant.
Task 3: fix round 1/5 dispatched — original implementer resumed (OPUS). Scope: the 4 Importants + MAX_MERGE-unpinned-from-below (flagged independently by BOTH reviewers, so not a nit) + dead-branch documentation consistency.
  Deferred to the final whole-branch review: redundant is_real_title at :290, bare assert at :220, rows.sort, rstrip(">"), and the per-op DP re-solve (correctly deferred — measured 0.064 s at 40x40, 1.77 s at 120x120 per donor; Task 5 is where fan-out makes it measurable).
  Flagged to the implementer as a question rather than a finding: A2/A3 sit EXACTLY on match_fraction == 0.80. A fixture balanced precisely on a threshold is fragile; confirm deliberate or move off the boundary.

## Owner: both-directions rule, and two notes (2026-09-02 ~14:45)
**(1) structure.py scope expansion ENDORSED.** Promoting `hygienic_title` to public is the dispatch-time invariant ("reuse structure's definitions rather than writing a second one") applied literally. Two definitions of hygiene that can diverge silently is the same hazard class as two definitions of an anchor.
  Owner kept the framing worth keeping: both reviewers were right about different things, and the gap was in MY DISPATCH WORDING — "import the predicates, do not copy them" was satisfied to the letter while the defect sat one level up at the composition. **A specification satisfied to the letter can leave the hazard it was written to prevent fully intact.** That is the more useful lesson than either finding.

**(2) NEW PLAN CONSTRAINT, committed 7e3b7cf: every numeric bound gets a mutation in BOTH directions, outcome recorded either way.** Third instance of one-sided pinning in this phase: MAX_MERGE 3->2 broke nothing (1 and 4 did); \d{4} -> \d{4,} passed the whole suite, admitting 19770101 into the most-trusted rung; single-digit rejection was pinned by nothing at all. Cause is STRUCTURAL not careless — a suite naturally pins the direction that breaks the happy path and leaves the other side free, so a constant tested one way looks pinned and is half-loose. A bound that breaks nothing in one direction is a FINDING AGAINST THE TESTS, not a shrug. Pushed live to the in-flight fix round as well.

**(3) The None crash's PIN must use a real `None`,** not a sentinel resembling one (0, -1, nan, or a stand-in object) — those pass while leaving the production path, a genuine None arriving from a Track, still crashing. Pushed live to the implementer.

### SELF-INFLICTED MONITORING ARTIFACT — recorded because it is the same class as the flag-placement rule
My watcher for the fix round waited on `HEAD != e251feb`. I then committed 7e3b7cf (the plan constraint) MYSELF while the child was in flight, which advanced HEAD and fired the watcher — reporting my own commit as if it were the child's fix. **The manager's own hand contaminated the liveness signal it was reading**, exactly the failure the `$D/taken-over/<task>` outside-the-measured-directory rule exists to prevent, one layer over.
  Mitigation used: path-scoped `git commit <pathspec>` so my commit could not sweep up anything the child had staged (a plain `git commit` commits the whole INDEX and would have). Retry loop for index.lock contention; committed first attempt.
  Durable lesson: **a liveness watcher keyed on shared mutable state (HEAD) is invalid the moment the watcher's owner can also mutate it.** Key the watch on something only the child writes — its sentinel, or its own report mtime. Re-armed accordingly.
Task 3: fix round 1/5 committed 4b07645 — all six findings addressed. Suite RE-MEASURED by orchestrator: 1590 passed, 7 deselected. PTH-GUARD OK, tree clean.
  Suite delta ITEMISED per the plan constraint: 1587 -> 1590 = +4 new, -1 removed (the equality table, deleted together with the duplicated composition it pinned).
  Finding 4 promotion verified COMPLETE by me independently: `grep -rn "_hygienic\b" packages/llama/{src,tests}` returns ZERO hits — no stragglers, no alias left behind. The diff correctly reached beyond siblings.py into structure.py, titles.py, correspondence.py, test_structure.py and test_titles.py (call sites + prose references), which is wider than Task 3's stated file list and is exactly what my scope ruling authorised.
  Implementer reports the drift class is now closed: mutating the single definition turns a siblings test AND a structure test red, where before a structure-side change left siblings green. That is the property the equality table was supposed to provide and demonstrably did not.
  Both-directions rule applied on its first outing, to all four ordered constants: MAX_MERGE 1/2/4/5, MIN_EXCLUSION_PENALTY 0/600, MIN_MATCH_FRACTION 0.0/1.0, SKIP_COST_MULT 0.5/2.0 — each direction turning at least one named test red.
  A2/A3 fixtures each gained a sixth pair, moving them off match_fraction == 0.80 exactly, reason stated inline. That was raised as a question, not a finding, and was acted on anyway.
Task 3: scoped re-review dispatched (Opus, t3-rerev), scope ce80541..4b07645, told explicitly that only 4b07645 is the fix and the two docs commits are mine and out of scope.
  Steered hardest at finding 3's pin (must be a REAL None, not 0/-1/nan/a look-alike, and must DECLINE rather than merely not-raise) and at spot-checking at least two both-direction constant claims INCLUDING a downward one — downward being the direction that has silently passed three times this phase.
Task 3: scoped re-review APPROVED (Opus) — all six ADDRESSED, every one verified BY MUTATION rather than by reading. Verdict: /private/tmp/.../sdd-phasec/t3-rerev/report.md
  Finding 3's pin is REAL: literal `None` on each side (not 0/nan/stand-in), asserts diag["decline"] == "missing per-track durations" rather than merely not-raising, and reverting `_all_present` reproduces the original TypeError verbatim. The old 0.0 case stays pinned separately.
  Finding 4 verified structurally, not by claim: exactly ONE definition at structure.py:1095, zero `_hygienic` refs, two call sites; dropping the metadata clause reddens BOTH a siblings test and a structure test. AST comparison confirms titles.py and correspondence.py changes are comment-only and structure.py is identical modulo the rename — i.e. the promotion moved no behaviour.
  Finding 5: the re-reviewer ran all four ordered constants BOTH directions rather than spot-checking two as instructed — 10 mutations, all red. The downward MAX_MERGE 3->2 fails ONLY the new 1:3 fixture, which is exactly the finding closing.
  Finding 6: it checked the CLAIM rather than the comment — fuzzed 4,000 random tapes x every legal pairing `forbid`, 0 INF. That is the three-independent-instruments habit applied unprompted to a dead-code assertion.
  Suite delta independently confirmed: 1509 -> 1512 test defs (net +3, matching 1587 -> 1590); the 4 additions map one-to-one onto findings 1/2/3/5; the single removal is confirmed to be the equality table and the only removal in the tree. Nothing weakened — A2/A3 gained asserts (10->12, 9->11) and every replaced assertion is stronger. A2/A3 now measure 0.8333 vs the old A2's exact 0.80.
Task 3: complete (commits ce80541..4b07645, review clean after 1 fix round).
  Suite RE-MEASURED by orchestrator: 1590 passed, 7 deselected. PTH-GUARD OK, tree clean.
  Deferred to the final whole-branch review: `bool` is admitted by the new isinstance duration guard (True > 0 is True); two hygiene clauses lack a siblings-side fixture; plus Task 3's earlier deferrals (redundant is_real_title at :290, bare assert at :220, rows.sort, rstrip(">"), per-op DP re-solve).
Task 4: dispatched, implementer on **OPUS**. Argued on its own terms rather than inheriting Task 3's ruling.
  Case for the plan's Sonnet sizing: interfaces given verbatim (loosely_same_title, Disagreement, GuardResult, rate_alignment, cplus_filter); tests enumerated; constants stated.
  Case for Opus, which I took:
   (1) DECISIVE: Task 4's whole job is REUSE — calling the real structure.anchor_spans/unresolved_runs/gap_span so the leading-edge exception and the absent trailing branch are INHERITED rather than restated. Task 3 demonstrated the precise failure mode one hour earlier: "import the predicates, do not copy them" was satisfied to the letter while the COMPOSITION was duplicated one level up, and the equality table meant to catch drift was proven inert. The same mistake here is a SECOND ANCHOR DEFINITION inside the guard whose only purpose is preventing silent adoption. Deciding what "reuse" means is judgment, not transcription.
   (2) The localised-shift fixture must synthesise a case where the RATIO IS DELIBERATELY BLIND (8/10 agreement -> band still `auto`) while C+ adopts zero interior titles. Building a fixture that genuinely reproduces that shape, rather than one that merely returns the right verdict, requires understanding why the ratio cannot see it.
   (3) Count-forcing here is explicitly WEAKER than adopt_gap_titles' and self-referential (donor span endpoints come from the alignment under test), justified by measurement and NOT by the setlist-gap argument — a subtlety a cheaper model would likely paper over with the familiar argument.
   (4) Evidence from this phase: an Opus implementer on Task 3 still shipped 4 Important findings including a real crash. Task 4 is harder.
  Told explicitly, carrying Task 3's lesson forward: reuse means CALLING THE REAL FUNCTION, not reproducing its logic faithfully — a specification satisfied to the letter can leave the hazard it was written to prevent fully intact.
Task 4: implementer COMPLETE (Opus). Commits 491088b (comparator + bands + C+, 27 tests) and 8c78eb3 (split a compound assertion so each mutation names the title it would ship).
  Suite RE-MEASURED by orchestrator: 1617 passed, 7 deselected (baseline 1590, +27, none removed). PTH-GUARD OK, tree clean.
  All three named mutations verified by the implementer on out-of-worktree copies:
    A one-sided bracketing -> 4 failed, incl. test_a_tail_run_never_adopts_automatically (`assert "Charlie" not in _adopted(out).values()`) and test_the_localised_shift_adopts_zero_interior_titles_under_cplus (`assert "Hotel" not in adopted.values()`)
    B count-forcing deleted -> 2 failed, incl. the localised-shift asserting `"Kilo > Xray" not in adopted.values()` — so the fixture DOES reproduce count-forcing catching that case's last wrong title, which the plan warned would otherwise mean the fixture was wrong
    C MIN_ANCHORS=1 -> test_a_single_agreeing_anchor_routes_to_the_operator_not_auto
  Both-directions applied to FOUR constants: AUTO 0.85/0.65, FLOOR 0.75/0.10, MIN_ANCHORS 3/1, LOOSE_TITLE_RATIO 0.85/0.75 — each killed by a BEHAVIOURAL test, not a value pin.
  Invariants verified structurally by the implementer: cplus_filter has NO caller outside tests (cli/correspondence/stages: none) -> invariant 1; C+ calls the real unresolved_runs/gap_span -> invariant 3; loosely_same_title called only by the two guard functions.
  Count-forcing deliberately NOT factored into a shared helper, on invariant-2 grounds. Handed to the quality reviewer to judge whether that is restraint or duplication wearing an invariant's clothes.

  PLAN AMBIGUITY CONFIRMED BY ME at plan:168 — the band definition answers one case twice. "`operator` >= 0.50 OR < 2 anchors; `declined` < 0.50": a case with agreement 0.3 and exactly 1 anchor satisfies BOTH clauses. The implementer routed it to `operator` and flagged the double answer rather than picking silently.
  Not escalated as BLOCKED — it is resolvable and the choice is defensible: the operator band is a DISPLAY path where a human reviews, so routing there is conservative, while `declined` HIDES the case, which cuts against invariant 1's whole purpose. Handed to BOTH reviewers to adjudicate independently against the SPEC (not the plan) before I rule.
Task 4: review dispatched — spec-compliance (Opus, t4-rev-spec) and code-quality (Opus, t4-rev-qual), concurrently.
  Both told to attack invariant 3 hardest, carrying Task 3's lesson explicitly: a specification satisfied to the letter can leave the hazard intact, so verify C+ CALLS the real gap_span rather than reproducing its logic — a second anchor definition inside this guard would be invisible.
  Spec reviewer additionally: spot-check >=2 both-direction claims INCLUDING a downward one. Quality reviewer additionally: judge the implementer's five Task 5 concerns, and whether the localised-shift fixture is genuine rather than right-by-construction.

## Band-overlap ambiguity: MY ARITHMETIC WAS WRONG, and the implementation already anticipated the fix
Owner correction 2026-09-02 ~15:20.

**My error:** I described the overlapping case as "agreement 0.3 with exactly 1 anchor". That is ARITHMETICALLY IMPOSSIBLE. Agreement is agreeing-anchors / total-anchors, so with exactly 1 anchor the ratio can only be 0.0 or 1.0. I invented an example to illustrate an overlap I had correctly spotted, and the example could not occur. Recorded as my error: a real defect described with a fabricated instance is still a fabricated instance, and had a reviewer taken my example as the case to test, it would have tested nothing.

**The genuine overlap is exactly two cases:**
  - 1 anchor that DISAGREES -> ratio 0.0, satisfying `< 0.50` (declined) AND `< 2 anchors` (operator).
  - 0 anchors -> ratio is 0/0, UNDEFINED.

**Checked the 0-anchor case myself (read-only): it is handled EXPLICITLY, not accidentally.** `rate_alignment` returns `GuardResult(None, 0, [], "no-anchors")` BEFORE the division, so there is no ZeroDivisionError and no coercion to 0.0 landing in `declined` by accident; `agreement` is `None`, matching the declared interface (`agreement: float | None  # None = no anchors`). This was the owner's independent-finding candidate and it is clean.

**The implementation already expresses the correction as a PRECEDENCE rule, and documents it.** `if n_anchors < MIN_ANCHORS: band = "operator"` is evaluated BEFORE the ratio clauses, and the docstring says: "Band order is deliberate: fewer than MIN_ANCHORS anchors routes to the operator whatever the ratio says, including below FLOOR. The bands were measured over pairs with >= 2 anchors; over one anchor the ratio is not the measured statistic at all, so it may neither license adoption nor justify throwing the proposal away."
  So the defect is in the PLAN'S WORDING ONLY — it states a disjunction where the design is a precedence. The code is right and reasoned.

**Why operator is right for the lone-disagreeing-anchor case, in the spec's own terms** (given to both reviewers as INPUT, explicitly not as my ruling): MIN_ANCHORS exists because the ratio is TOO NOISY TO BE A MEASUREMENT below 2, not because a low value means a bad alignment. And the sweep measured **24.1% of disagreeing anchors are TAPE-wrong** — sibling and canonical agreeing against the target's own tag — about as common as sibling-wrong. So one disagreeing anchor is near-zero evidence: roughly one time in four the anchor itself is what is wrong. Declining on that hides a case the operator band exists to show, cutting against invariant 1.

  QUEUED PLAN CORRECTION (pending reviewer adjudication, then one commit): restate plan:168's band table as a PRECEDENCE RULE — the anchor-count clause is evaluated first, because below MIN_ANCHORS the ratio is not a measurement and the ratio clauses do not apply — and note that the overlap is exactly the 1-anchor-disagreeing and 0-anchor cases. Same treatment as Task 3's impossible near-ambiguous sketch: a plan defect found is a plan defect fixed, in the plan.
  I withheld from both reviewers what I found in the code, so they check rather than confirm me.

**Owner's assessment of mutation B, recorded because it is the phase's high-water mark:** deleting count-forcing turning the localised-shift test red on the specific wrong title is the single most important result in this phase so far — it is the case that killed the trailing-anchor shape in the sweep, and the fixture demonstrably REPRODUCES it rather than approximating it. Also ratified as a standard: "each constant killed by a BEHAVIOURAL test rather than a value pin" — a value pin would satisfy the both-directions rule while testing nothing.
Task 4: spec review SPEC PASS (Opus). Verdict: /private/tmp/.../sdd-phasec/t4-rev-spec/report.md
  ALL FOUR INVARIANTS YES, each verified by reading the calls rather than trusting comments. The decisive check on invariant 3: **no `lo == 0` / `hi + 1` / left-right logic exists ANYWHERE in siblings.py** — C+ calls the real unresolved_runs and the real gap_span(anchors, lo, hi, len(tracks)), and mutation A proves the reuse load-bearing. Also noted correctly: anchor_spans is INAPPLICABLE here (item-title binding vs DP duration pairing); only its span SHAPE is reused. That is a distinction I had not drawn and it is right.
  Invariant 1 is pinned by a test named for the hazard: test_cplus_applied_to_the_display_would_blind_the_operator.
  All three named mutations reproduced independently; "nothing broke nothing". Spot-checks: SIX, exceeding the two required, THREE of them downward. Every death is a band/title assertion, not a value pin. Reproduces the implementer's table exactly.
  Suite: +27 test defs, 0 removed; the only deletions in the entire 2-commit package are two replaced import lines. structure.py is comparator-only.

  BAND ADJUDICATION — SETTLED, and it moves the defect entirely off the code. The SPEC is UNAMBIGUOUS: "under it, operator path regardless of agreement". Only the PLAN is ambiguous. The anchor-count clause is a PRECEDENCE, not a tiebreak. The overlap is exactly ONE case (1 disagreeing anchor, ratio 0.0) — the reviewer independently confirmed my 0.3-with-1-anchor example was arithmetically impossible.
  Merits, adding a reason I did not have: `declined`'s 68-99% marginal-error basis was MEASURED OVER >=2 ANCHORS AND DOES NOT EXIST AT 1. So declining a lone-anchor case applies a threshold whose justification is absent for that population. Plus 24.1% tape-wrong, plus: since NEITHER band adopts, `operator` costs a minute of attention while `declined` silently discards a possibly-correct alignment for exactly the barely-tagged population this phase serves.
  0-anchor independently verified as explicit-before-the-division, matching my own read.

  3 Minor findings, none blocking:
   M1: the "agreeing anchor" predicate is composed INLINE TWICE (rate_alignment:420, cplus_filter:490) rather than in one helper. Nothing is logically duplicated TODAY, but it is the same SHAPE as the Task-3 drift — a future change to what "agreement" means in layer 1 would not propagate to layer 2. One three-line helper closes it. Given that this phase has now been bitten by exactly this twice, I intend to fold it in rather than defer.
   M2: all four constants cite docs/superpowers/2026-09-02-sibling-transfer-evidence.md, which does not exist yet; the plan's FILE TABLE still says 2026-09-XX-. The citation is correct per my earlier ruling; the PLAN's table is the stale half. -> plan fix, mine.
   M3 -> **T7-OBLIGATION-5**: `_anchor_row` additionally requires `bool(row.proposed)`, so a tagged track paired with an UNTITLED donor is neither an agreeing nor a disagreeing anchor. The reviewer agrees with the narrowing (counting it as a disagreement would let an untitled donor drag a correct alignment below FLOOR — a failure mode with no upside) and it is pinned by test_an_unpaired_tagged_track_is_not_an_anchor. But it IS a real deviation from the spec's literal denominator, and **Task 7's measurement scorer MUST adopt the same rule or its agreement numbers will not reconcile with the shipped guard.** Task 7 blocker, not a Task 4 one.

## Owner endorsements + one general lesson (2026-09-02 ~15:25)

**M1: FOLD THE HELPER IN, do not defer.** Owner: the evidence is behind it — this phase has been bitten TWICE by "not logically duplicated today" (Task 3's hygiene composition, and the equality table that was supposed to catch it and was inert). A three-line helper now costs less than a third instance, and **the argument for deferring is always the same one that was wrong the previous two times.** Goes into Task 4's fix round.

**M3 landed in Task 7's BRIEF, not the ledger — commit 0e218e2, task-7-brief.md regenerated (29 lines).** Owner's statement of the failure it prevents, which is sharper than mine: if Task 7's scorer computes agreement over a different denominator than `_anchor_row` uses, **the gate certifies a guard that is NOT THE SHIPPED GUARD** — the numbers would be internally consistent, reconcile against nothing, and read as a pass. Same class as measuring the wrong tree, ONE LEVEL UP: the instrument is fine, it is merely pointed at a slightly different object than the one shipping.
  Acceptance is now a RECONCILIATION CHECK: for at least one real pair, the scorer's agreement must equal the shipped guard's, obtained by CALLING `siblings.rate_alignment` rather than reimplementing it. Note the shape — this is the three-independent-instruments bar's complement: redundancy catches an instrument that is wrong, reconciliation catches an instrument that is right about the wrong object.
  Also fixed in the same commit: the file table's `2026-09-XX` placeholder now reads `2026-09-02-sibling-transfer-evidence.md`, the path four do-not-retune constants already cite, with a note that Task 7 must create it there or those citations dangle.

**GENERAL LESSON, owner-stated, wider than this phase: A THRESHOLD IS ONLY VALID OVER THE POPULATION IT WAS MEASURED ON.**
  Derived from the reviewer's band argument, which is a sharper form of the noise argument: not "the ratio is unreliable below 2 anchors" but "**the number that justifies the band was never measured there**". `declined`'s 68-99% marginal-error basis was measured over >=2 anchors and DOES NOT EXIST at 1, so declining a lone-anchor case applies a threshold whose justification is absent for that population.
  This generalises to every threshold this project inherits from a sweep — the tail-guard constants, AUTO/FLOOR, MIN_MATCH_FRACTION, the junk duration floor. Applying one outside its measured population is not a conservative choice; it is an unjustified one wearing conservatism's clothes.
  To be preserved VERBATIM in the pending plan correction to the band table.

**Correction recorded against me: my invariant-3 framing was TOO BROAD.** I told both reviewers to reuse "`anchor_spans` / `unresolved_runs` / `gap_span`". The spec reviewer pushed back: `anchor_spans` is genuinely INAPPLICABLE here — it binds item titles, while the DP pairs durations — and only its span SHAPE is reused. **An invariant stated too broadly invites either false findings or a shrug, and both are expensive**: a compliant implementer would have been driven to force an unusable call, and a lax one would have discounted the whole invariant. The reviewer pushing back rather than complying is what caught it.

### PENDING, deliberately not done while the quality reviewer is live
The band-precedence correction sits INSIDE Task 4's section of the plan, and regenerating `task-4-brief.md` while the quality reviewer is reading it would hand it inconsistent requirements mid-review. Held until its sentinel lands, then one commit: restate the band table as an ordered evaluation (reviewer's supplied wording), carry the "measured over >=2 anchors and does not exist at 1" reason verbatim, note the overlap is exactly the 1-anchor-disagreeing and 0-anchor cases, and regenerate task-4-brief.md.
Task 4: quality review CHANGES REQUESTED (Opus), 4 Important + 3 Minor. Verdict: /private/tmp/.../sdd-phasec/t4-rev-qual/report.md
  **SOURCE IS CLEAN — every finding is TEST-SIDE.** Reuse independently confirmed the hard way: deleting `gap_span`'s LEADING BRANCH in structure.py kills the sibling test plus two pre-existing ones. That is stronger than checking the call site — it proves the sibling behaviour is downstream of structure's real logic. No copied composition, unlike Task 3.
  Sound and no action: comparator symmetric (0 asymmetric pairs in 200k, including the autojunk range), no O(n^2) risk (MAX_TITLE_LEN=80), constants follow provenance style, purity intact, no scope creep, zero test deletions, both commit messages state the test command.
  The un-shared count-forcing clause RATIFIED as right restraint: the two justifications are genuinely different (canonical vs self-referential span), and a shared helper would invite the wrong inference. I had flagged it as possible "duplication wearing an invariant's clothes"; the reviewer's reasoning is better than my suspicion.
  All five Task-5 concerns judged REAL. #1 most dangerous (gather MUST intersect with the unresolved set or it overwrites tape tags). #4 upgraded to crash-adjacent.

  ### MY REPORT TO THE OWNER WAS OVERSTATED — CORRECTING IT
  I called mutation B "the phase's high-water mark: the fixture demonstrably REPRODUCES count-forcing catching that case's last wrong title rather than approximating it." Finding 4 shows that is wrong as stated. The fixture is **genuine machinery, wrong mechanism**: built through the real DP from real durations, `agreement == AUTO`, `band == "auto"` over 10 anchors, zero interior adoption, and A and B each kill it naming a different title — so it passes the brief's acceptance wording. But **the ops are 1:1 throughout: the shift is in the TAPE'S TAGS, not the donor span.** The two interior titles C+ blocks are CORRECT; only track 11's merge is wrong. **The spec's case is the INVERSE — the alignment slides and the ratio ships 7 wrong titles.**
  So the regression pin for the class C+ exists for does not currently reproduce that class. Consequence if left: a future refactor could break C+ for the real donor-span-slide case with every test green.
  Both reviewers were right about different things AGAIN — the spec reviewer checked the fixture against the ACCEPTANCE CRITERIA (passes), the quality reviewer checked it against the REAL-WORLD CLASS (does not). Third instance this phase of two correct reviewers appearing to conflict. The durable lesson: **"does it satisfy the acceptance wording" and "does it reproduce the phenomenon" are different questions, and only the second one is what a regression pin is for.**
  Fix: keep the fixture, correct its docstring to say what it actually reproduces, ADD a true donor-span-slide counterpart. If one cannot be built through the real DP, the implementer must say so and explain rather than hand-assembling rows to fake it — that would itself be a finding worth having.

  Finding 2 is the phase's SECOND crash-adjacent defect: `_anchor_row`'s unpinned `bool(row.proposed)` clause is the only thing preventing `AttributeError: 'NoneType' object has no attribute 'replace'` from `fuzzy_norm_title(None)` on an untitled-donor row that `propose_rows` emits ON ITS OWN. Deleting the clause: 1215 passed, 0 failed.
  Finding 1: the band PRECEDENCE — the thing the owner and I just spent two rounds settling — is itself UNPINNED. Reordering the ladder so `declined` outranks the anchor-count clause leaves the entire suite green, because the only separating case is a DISAGREEING single anchor and no test builds one. Settling a question and pinning it are different acts.
Task 4: plan corrected 453deff — band table restated as an ordered evaluation with the overlap named exactly, the reviewer's "measured over >=2 anchors and does not exist at 1" argument verbatim, and the general lesson. task-4-brief.md regenerated (48 lines). Done in the clean window between the reviewers finishing and the fix round dispatching.
Task 4: fix round 1/5 dispatched — original implementer resumed (Opus). Scope: the 4 test-side Importants + the inline-twice helper.

## PATTERN, not incident: a proxy satisfied is not the thing itself (owner, 2026-09-02)
Two instances now, across two phases, and the pairing is what makes it a pattern:
  - **Phase B:** the M3 gate **passed on SHAPE** while **13 of 22 titles were wrong**.
  - **Phase C, Task 4:** the localised-shift fixture **passed the acceptance wording** while reproducing a *tag* shift rather than the *donor-span* shift it is the regression pin for.
In both, the acceptance criterion was met exactly and the phenomenon was absent. **An acceptance criterion is a PROXY, and a proxy satisfied is not the thing itself.** For a regression pin specifically: "does it satisfy the acceptance wording" and "does it reproduce the phenomenon" are different questions, and only the second is what the pin is for.
My own error here was treating a passed acceptance as a reproduced phenomenon and reporting it upward as the phase's strongest result. The owner had amplified that claim further; correcting it downstream cost less than it would have at ratification, which is the argument for reporting corrections against one's own prior claims promptly rather than at the next natural boundary.

## Owner refinements to Task 4's fix round (pushed live, scope unchanged)
  (a) Finding 1's new pin must BUILD the separating case — a **disagreeing single anchor** — not assert the ladder's order structurally. A structural test (checking clause order, or that MIN_ANCHORS is consulted first) would PASS under the very reordering it exists to catch. Owner's framing, which is the durable half: **settling a question and pinning it are different acts, and the gap between them is invisible precisely because the discussion feels like the work.** Two rounds were spent settling this precedence and neither of us noticed nothing pinned it.
  (b) Finding 2's `bool(row.proposed)` clause now carries DOUBLE DUTY — it prevents AttributeError from fuzzy_norm_title(None) AND defines the anchor denominator Task 7's scorer must mirror. **Pin the two separately.** One test asserting both would let either half rot: a later change could preserve no-crash while altering the denominator, and the single test would stay green.
  (c) Finding 4's failure mode is itself EVIDENCE. -> T7 Step 9, committed 1170b7d, task-7-brief.md regenerated (31 lines).

## T7-OBLIGATION-6 (Step 9): is the donor-span slide real, or a synthesis artifact?
  C+ exists PRIMARILY to catch a localised donor-span slide with high anchor agreement. **The sweep observed that case exactly ONCE, at agreement exactly 0.80, in the SYNTHESISED prefix-mask population.** That is thin ground for the guard's headline justification, and Task 4's fixture reproducing the wrong mechanism sharpens the question rather than answering it.
  Task 7's blind arm settles it. Report count and population separately, SYNTH vs REAL, never pooled. **Both answers are valuable and neither is a failure:** if the class is real, Task 4's fixture must be corrected to reproduce it; if it is synthesis-only, **count-forcing's justification must be restated in honest terms** — the guard may still be worth keeping as cheap insurance, but the spec must say that rather than implying a measured frequency it does not have.
  Same family as the standing lesson: a threshold or a guard is only justified over the population its evidence was drawn from.
Task 4: fix round 1/5 committed f149111 — all five findings addressed. Suite RE-MEASURED by orchestrator: 1622 passed, 7 deselected (was 1617; +5 added, 3 renamed, 0 removed). PTH-GUARD OK, tree clean.
  ALL FOUR review findings were TEST-SIDE; the single source change is one `_anchor_agrees` helper so layer 1 (ratio) and layer 2 (bracketing) cannot drift on what agreement means.
  The implementer BUILT the true donor-span slide rather than reporting it impossible: tags all correct, agreement 1.0, three wrong interior titles as adopt rows, declined by count-forcing ALONE. Old fixture renamed `_tape_tag_shift` with an honest docstring rather than deleted.
  Finding 2 pinned TWICE on purpose (crash guard / anchor denominator), and the implementer built mutant H2 specifically to PROVE the two are separable — dropping the clause while making the comparison None-safe, so only the denominator test dies. That is the two-test requirement DEMONSTRATED rather than asserted, and it is the standard for the rest of the phase.
Task 4: scoped re-review dispatched (Opus, t4-rerev), scope 8c78eb3..f149111, told only f149111 is the fix and the three docs commits are mine.
  Steered hardest at the NEW donor-span fixture: do not accept it on its docstring, dump the rows, verify the ops are genuinely offset, the tags genuinely all correct, the three interior titles genuinely wrong, and the decline attributable to count-forcing ALONE — because its predecessor was mislabeled in exactly this way and passed the acceptance wording while doing it.

## THE PHASE'S MOST CONCEPTUALLY IMPORTANT FINDING — carried into Step 9 as prior evidence (commit fab1be7)
Owner's judgement, and it was at risk of dying in a fix-round report.
  **Forcing a donor-span slide through an L1 duration cost requires the two tapes' songs to differ by MINUTES.** The credible real-world mechanism — several adjacent near-equal-length songs with one missing from the target — was tried FIRST and **never reaches C+ at all**: penalties collapse to 2-18 s against MIN_EXCLUSION_PENALTY = 60, so layer 3 declines those rows before the guard is consulted.
  The generalising sentence: **the ambiguity that lets an alignment slide is the same quantity the penalty measures.** Two of the three routes into this class are self-limiting.
  Why it matters beyond the fixture: it is a MECHANISTIC argument that C+'s primary case may be largely unreachable in production, and it arrived INDEPENDENTLY of the sweep's single synthetic observation at agreement 0.80. **Step 9 now has two converging inputs from different instruments** — a far stronger prior than either alone, and another vindication of the redundancy argument this phase keeps validating.
  **One reading is FORBIDDEN and is written into the plan as such: this is not license to remove C+.** An unreachable-in-this-corpus class is not an impossible one, and the corpus is 89 shows. If the blind arm finds the class synthesis-only, C+ becomes **insurance rather than measured necessity and the spec must say so IN THOSE WORDS** — cheap insurance against a structurally hard-to-reach failure mode is defensible; justifying it by an implied frequency it does not have is not.
  **Structural corollary, now in the plan:** if both flanks are right and the donor span count equals the file count, **the interior is forced and cannot slide — so a slide always presents as a count mismatch.** That converts a puzzling asymmetry into a derivable one: mutation A (one-sided bracketing) STRUCTURALLY cannot kill the donor-span fixture, while mutation B (delete count-forcing) must.

  QUEUED (NOT done by me — controller fixes skip review): the structural corollary must land in the donor-span fixture's DOCSTRING, not only in the plan and report. Fold into whatever round the re-review opens; if the re-review is clean, dispatch it as a one-line follow-up to the Task 4 implementer.

## Pacing plan CONFIRMED by owner (independently verified 15:38: 50%, 33.0%/hr, headroom 91 min, reset 19:10)
  Run Task 5 to completion — implementer + both reviewers + any fix round — then CHECKPOINT. Do not start Task 6 inside one task's burn of the 70% band.
  **NEW STANDING RULE, committed to the plan: Task 7 NEVER starts on a partial window.** Six named obligations, the three-instruments bar, the reconciliation check and the Step 9 question do not survive a forced stop coherently. **A half-run measurement gate is worse than none: it produces numbers that look like results.**
  **If Task 5's fix round would push past 70%, STOP BEFORE DISPATCHING IT and checkpoint with the round pending.** Rationale worth keeping: a landed implementer pass plus a NAMED OUTSTANDING ROUND is a clean resume point; a killed fix round mid-edit is the compiles-passes-and-is-wrong state. The unit of atomicity is the dispatch, not the task.

## Why BOTH fixtures exist — must reach the docstring, not just this ledger
Owner ratified renaming `_tape_tag_shift` rather than deleting it, with a reason stronger than "it still passes": it preserves a **distinct and COMMONER phenomenon** — a tape whose own tags are shifted — and this phase has already measured that **24.1% of disagreeing anchors are tape-wrong**. Deleting it would have thrown away coverage of the commoner failure to make room for the rarer one.
  -> Added to the QUEUED docstring action: the fixture pair's docstrings must say why TWO similar fixtures exist (tape-tag shift = commoner, 24.1% tape-wrong; donor-span slide = rarer, the class C+ primarily exists for), or the next reader will read one as redundant and delete it.

## Why the docstring work is queued to a child rather than done by me
Owner's reason is better than my "controller fixes skip review": **a controller edit that skips review is exactly how an unreviewed claim enters the record**, and this docstring carries a STRUCTURAL ARGUMENT — the forced-interior corollary — that should be read by someone other than its author. Fold into the re-review's round; if the re-review is clean, a one-line follow-up dispatched to a CHILD is still preferable to my own hand.
Task 4: scoped re-review ACCEPT (Opus) — all five ADDRESSED, every mutant reproduced independently out-of-worktree, no new breakage. Verdict: /private/tmp/.../sdd-phasec/t4-rerev/report.md
  Finding 2's two pins proven SEPARABLE by the re-reviewer's own H2 (drop the clause + `or ""`): 1 failed, only the DENOMINATOR test. "That is the rot direction that matters." It also verified propose_rows really emits donor_span non-None with proposed=None, so the hand-written row is faithful to production.
  Finding 5: mutant F (drop the agreement conjunct) reddens BOTH layers — 4 ratio tests and 3 bracketing tests. The helper is genuinely shared, not nominally.
  Suite delta confirmed at a level I would not have reached: name sets 41->46, AST body comparison on the 3 renames (one byte-identical, two differ only by dropping an unused third return value), assert counts per test unchanged, file-wide asserts 167->190, the fixture's 14 donor + 13 target durations unchanged. Nothing weakened.
Task 4: complete (commits 4b07645..f149111, review clean after 1 fix round).
  Suite RE-MEASURED by orchestrator: 1622 passed, 7 deselected. PTH-GUARD OK, tree clean.

### FINDING 4's RESIDUAL — a THIRD converging input, and the strongest of the three
The re-reviewer dumped the new `_donor_span_slide` rather than reading its docstring, and verified as TRUE: real-DP-built, ops genuinely non-1:1 (merge at span (6,8); run 5-7 covers donor span (4,8), 4 donor tracks for 3 files), tags all correct, agreement 1.0 / 6 anchors / 0 disagreements, all three rows adopt at penalties 406/406/240 vs floor 60, decline attributable to count-forcing ALONE (gap_span returns (4,8), so bracketing contributes nothing), mutant B kills it.
  **What it judged NOT established: the three interior titles are not demonstrably wrong.** By the fixture's OWN durations the DP's reading has residuals 2.0/2.0/0.0 while the declared truth would require duration errors of ~188 s, ~88 s and ~305 s. **The DP is right and the declared "truth" is the implausible reading.** So the test pins C+'s **YIELD COST** — a correct proposal declined because the donor has one more track than the target has files — not C+ preventing an error. It reproduces the right ARITHMETIC SIGNATURE with a STIPULATED rather than EXHIBITED error.
  Why this is the strongest evidence yet for Step 9: an Opus implementer trying hard, with the mechanism fully explained, **could produce the signature but not the phenomenon** — and disclosed that itself in a docstring HONESTY NOTE and escalated it as report concern 6. Step 9 now has THREE converging inputs from three different instruments: (1) the sweep's single synthetic observation at agreement 0.80; (2) the mechanistic argument that the ambiguity enabling a slide is the same quantity the penalty measures; (3) the constructive failure to exhibit a genuine error even by design.
  Re-reviewer's own summary of the test's residual value, which I accept: it is "load-bearing and better than what it replaced — the only count-forcing test built through the real DP AND at agreement 1.0, and it asserts the span (by[5].donor_span == (4,5)), not just the title, so a fixture that stopped reproducing the shape fails rather than passes vacuously."
  Two residuals carried, neither blocking: (i) the docstring headline is one notch hot — "the class the spec names" is not supported by the fixture's own durations; the re-reviewer's suggested wording is "the ARITHMETIC SIGNATURE of a donor-span slide"; (ii) if Task 7's blind arm finds no real donor-span slide, this test pins a yield cost with no demonstrated error prevented, and **count-forcing's justification then rests on the tag-shift class plus the merge case** — that sentence is the one Task 7 must confirm or refute.

## THREE CONVERGING INSTRUMENTS on Step 9 — recorded in the owner's terms
The constructive-failure result is **the strongest single input Step 9 has**. An Opus implementer, with the mechanism fully explained and **actively trying to build the case**, produced the arithmetic **signature** but not the **phenomenon** — and disclosed it in its own docstring honesty note rather than letting the fixture stand as more than it was.
Three instruments now converge, and they are independent of one another, which is what makes the convergence worth anything:
  1. **One synthetic observation at exactly 0.80** — the sweep's single sighting, in the prefix-mask population.
  2. **A mechanistic argument** — the ambiguity that lets an alignment slide is the same quantity the penalty measures, so two of three routes into the class are self-limiting (penalties collapse to 2-18 s against MIN_EXCLUSION_PENALTY = 60 and layer 3 declines first).
  3. **A failure to exhibit the error by construction** — the fixture reproduces the signature with a stipulated rather than exhibited error.

## Step 9's DECISIVE QUESTION rewritten: C+'s PRECISION, both counts (commit 0a5a00a)
Owner's reframing, and it is sharper than what was in the brief. Put Task 4's two regression fixtures side by side:
  - `_tape_tag_shift`: C+ blocks 3 interior titles, **2 of them correct**, 1 merge wrong.
  - `_donor_span_slide`: C+ blocks 3 titles that by the fixture's own durations are **probably all correct** (DP residuals 2.0/2.0/0.0 vs ~188/88/305 s for the stipulated truth).
  **Across both regression fixtures, C+'s demonstrated behaviour is MOSTLY DECLINING TITLES THAT WERE RIGHT. Neither fixture exhibits C+ preventing a wrong adoption** — one stipulates it, the other pins yield cost.
So the question is not "does the class occur" but: **of the rows C+ declines that the ratio band would otherwise have adopted, how many would have been WRONG and how many RIGHT?** BOTH counts required — **a count of errors prevented with no denominator is the same defect as an unlabelled rate**, which is the unit-naming lesson resurfacing one level up. Ground truth is already to hand: the hidden taper tags the blind arm uses.
Three outcomes, none to be pre-judged: (a) blocks meaningfully more wrong than right -> earns its place, spec stands; (b) blocks mostly-correct titles, prevents few or no real errors -> **a yield cost paying for insurance against a class that has now failed to be exhibited three times** — a legitimate design position, but the spec must SAY SO and the cost must be QUANTIFIED; (c) too few declines to say -> **report the N and say so**, more useful than a rate on four rows.
**Under all three outcomes C+ STAYS.** An unreachable-in-89-shows class is not an impossible one, and **a silent adopter is the one surface where being wrong is unrecoverable.**
Task 4: docstring follow-up DONE (Sonnet). Commit 83b4a19. Suite UNCHANGED at 1622 passed, 7 deselected — the acceptance proof that only prose moved.
  Scope verified by ME independently, not taken on report: `git show 83b4a19` = 52 changed lines, **0 code-shaped added lines** (no assert/def/list-literal), single file, all inside the two fixtures' triple-quoted docstrings.
  All three residuals closed: headline softened to "arithmetic signature", stipulated-vs-exhibited comparison recorded (2.0/2.0/0.0 vs ~188/88/305 s), why-both-fixtures-exist with the 24.1% tape-wrong figure in BOTH docstrings, and the structural corollary extended with the "a reader may mis-fix toward mutation A" caution.
TASK 4 FULLY CLOSED.

Task 5: dispatched, implementer on **SONNET** — FOLLOWING the plan's sizing this time rather than departing from it.
  Why Sonnet is right on the merits, independent of budget: the design work is FINISHED. siblings.py's interfaces are built and twice-reviewed; Task 5 wires them at a seam the plan names exactly (after the overrides loop, before adopt_gap_titles). No new algorithm, no invariant to invent, no measured constant to justify. The dangerous parts are KNOWN AND NAMEABLE rather than discoverable — which is precisely the line between Sonnet work and Opus work. Contrast Task 3, where the data model consumed by three later tasks had to be designed, and Task 4, where "reuse" had to be interpreted.
  Budget agrees (55%, 27 min to the band) but does not drive it; I would escalate to Opus on a BLOCKED-for-reasoning regardless, per policy.
  All five Task-4 concerns handed down explicitly, with concern 1 flagged as the DATA-LOSS one: gather MUST intersect adoptions with the unresolved set or the transfer pass overwrites tracks that already carry tape tags.

## SIZING HEURISTIC, promoted to a plan constraint (commit below)
Owner: the best statement of the line produced in this run, and better than task size or file count because it explains both earlier departures without special-casing them.
  **Escalate an implementer when the dangerous parts are DISCOVERABLE rather than KNOWN AND NAMEABLE.**
  Task 3 -> Opus: designed the data model three later tasks consume; a wrong span convention propagates invisibly into the guard against silent adoption.
  Task 4 -> Opus: "reuse structure's functions" had to be INTERPRETED, and Task 3 had just shown a specification satisfied to the letter leaving its hazard fully intact.
  Task 5 -> Sonnet: interfaces built and twice-reviewed, seam named, every hazard listable in the dispatch — including the data-loss one.
  File count sizes all three identically. **"Is there a decision here whose failure mode is silent?"** separates them correctly.

## Concern #1's pin — the weak version would pass while the bug is live (pushed to the live implementer)
Owner requirement, and it is the third instance of the same distinction this phase: **assert the property you care about, not a proxy that correlates with it today.**
  FORBIDDEN pins: "adoption count is lower", "the unresolved set was consulted", "N tracks adopted" — each passes while an overwrite still happens by another path.
  REQUIRED: on a track the sibling WOULD OTHERWISE HAVE SUPPLIED A TITLE FOR (donor genuinely proposes, row survives C+, so the intersection is the only thing standing between the tape's tag and the donor's title), assert the **pre-existing title is still present and unchanged** — the exact surviving string — and that `title_source` is still `tags`/`sibling-format`/`override`, not `sibling-align`.
  MUTATION REQUIRED: remove the intersection with the unresolved set; the test must go **red naming the clobbered title**. **If removing the intersection breaks nothing, the pin is decorative and the data-loss path is live** — and a decorative pin on THIS path is worse than none, because it reads as coverage.
  Same shape as decline-vs-not-raise on Task 3's None guard, and as shape-vs-content on Phase B's M3 gate.
Task 5: implementer DONE (Sonnet). Commit e34fda0 (models.py, titles.py, stages/gather.py, test_stage_gather.py, test_titles.py; +412/-45).
  Suite RE-MEASURED by orchestrator: 1629 passed, 7 deselected (baseline 1622, +7). PTH-GUARD OK, tree clean.
  ALL FOUR mutations verified on an isolated copy with PYTHONPATH (never a venv console script against a copy):
    A `sibling-align` added to TAUTOLOGICAL_TITLE_SOURCES -> test_sibling_aligned_matches_count_as_independent_coverage_evidence, `assert show.structure.coverage == 5/6` got 0.5. The independence pin exists and bites.
    B bypass cplus_filter -> test_a_bracketing_failure_leaves_the_run_unresolved_with_its_reason_in_notes fails ON TITLE CONTENT (`title_source` shows 'sibling-align' instead of 'unresolved').
    BACKWARD restore the OLD rung -> test_shifted_fully_tagged_sibling_does_not_transfer_positionally fails, track 1 getting the donor's shifted "China Cat Sunflower" instead of its own filename. **The positional hole is proven closed.**
    CONCERN #1 remove the unresolved-only guard -> test_an_already_titled_track_is_never_overwritten_by_a_surviving_adopt_row fails `assert track2.title == "China Cat Sunflower"`, got 'Bertha'. **The owner's requirement was met exactly: the pin asserts the SURVIVING STRING and the mutation names the CLOBBERED TITLE, not a proxy.**
  Concern #1 implemented the right way round: adoption is intersected with the UNRESOLVED set AT APPLICATION TIME rather than trusting cplus_filter, which says nothing about an already-titled track outside a fill run.
  Invariants held: sibling-align NOT in TAUTOLOGICAL_TITLE_SOURCES, `matched` never forced None, transfer runs after the overrides loop and before adopt_gap_titles, cplus_filter called only when rate_alignment routed the pair to "auto".
  Suite delta ITEMISED: +9 added, -2 removed (test_sibling_titles_are_cleaned — old rung positional-shape test; test_sibling_fallback_when_setlist_misaligned — RENAMED to test_resolve_titles_no_longer_has_a_sibling_fallback and now asserts the fallback is GONE). Both subsumed by the 8 new gather-level content tests.
  Census on live ~/.llama (89 shows / 2015 tracks), labelled: tags 1917 | unresolved 75 | sibling 21 | override 2 | sibling-align 0. "After" is NOT measurable before Task 7 — no re-gather harness exists yet. The 21 legacy `sibling` rows are pre-change and unmigrated by design.
  THREE IMPLEMENTER CONCERNS, all for the reviewers:
   (1) **TDD deviation, self-disclosed:** tests and implementation were CO-DEVELOPED rather than strictly red-first, because the DP math was impractical to hand-verify blind. Compensated with the four mutation checks. This is a real deviation from a plan constraint and the reviewers must weigh whether the mutations discharge it.
   (2) new decline-note wording is untested outside this task — worth a check when Task 6 surfaces it to operators.
   (3) **the winning-donor tie-break is implemented per spec but NO fixture exercises two competing donors.** Unpinned logic on a path that decides which donor's titles ship.
  Noted: the child reported SendMessage to "sdd-orchestrator" unreachable — confirming the documented behaviour that subagent TYPE is not a name and children are unnamed by construction. The disk protocol carried the report as designed.

## LESSON, generalises well beyond pacing: an instruction's PREMISE can expire
Owner, 2026-09-02 16:11 (independently verified 66%, 32.6%/hr, headroom 64, reset 19:10).
  **Executing an instruction whose basis has moved is not the same as following it.**
  The 15:38 authorisation ("implementer + both reviewers + any fix round, then checkpoint") was explicitly built on a projection in which the reviewers FITTED and the FIX ROUND was the deferral point. By 66% that projection was false: it had become the REVIEWERS that crossed the band. Obeying literally would have blown the band while technically complying; improvising silently would have been worse.
  **A subordinate who notices the premise has shifted and comes back — rather than either obeying literally or improvising silently — is doing the thing that makes delegation safe.** The cost asymmetry is what makes it easy: asking costs one exchange, being wrong costs the band.
  Sits beside this phase's other recurring shape: a specification satisfied to the letter can leave its hazard intact (Task 3's hygiene composition). Both are cases where literal compliance and actual compliance come apart.

## ============ CHECKPOINT 2: SESSION PAUSED 2026-09-02 16:12 EDT ============
Reason: 5h rate-limit band. 66%, burn 32.6%/hr, reset 19:10. Task 5's two Opus reviewers would land ~74-76%, past the 70% band. Owner chose (b): checkpoint now, reviewers on the fresh window. Reviewers work from the diff, so nothing decays across the gap.

STATE OF THE BRANCH: `sibling-transfer` @ e34fda0 (+ the checkpoint commit below). Tree clean. Suite **1629 passed, 7 deselected**, RE-MEASURED by the orchestrator. PTH-GUARD OK. Nothing pushed, merged, or tagged. Nothing in flight.

TASKS COMPLETE: 1, 2, 3, 4 — each reviewed by two Opus reviewers and re-reviewed after its fix rounds.
TASK 5: implementer landed and verified; **REVIEW NOT YET RUN.**

### >>> RESUME POINT — the IMMEDIATE next dispatch is Task 5's TWO REVIEWERS, not Task 6 <<<
Do not advance to Task 6. Task 5's code is committed and unreviewed; skipping past it would leave the phase's largest wiring change unexamined.
  Dispatch: spec-compliance (Opus) + code-quality (Opus), concurrently, out-of-worktree copies, PYTHONPATH shadowing only, PTH-GUARD as first action.
  Review scope: **83b4a19..e34fda0**. Generate with `scripts/review-package <plan> 83b4a19 e34fda0`.
  Brief: .superpowers/sdd/2026-09-02-sibling-title-transfer/task-5-brief.md ; report: task-5-report.md

  THREE DISCLOSED CONCERNS — hand ALL THREE to the reviewers as named items:
  1. **TDD DEVIATION — carry as a REVIEWER QUESTION, not a footnote, and do NOT pre-judge it in either direction.** Tests and implementation were CO-DEVELOPED rather than strictly red-first, because the DP math was impractical to hand-verify blind. This is a genuine breach of a plan Global Constraint, self-disclosed by the implementer. **The honest question is whether four verified mutations DISCHARGE a red-first requirement or merely RESEMBLE discharging it** — which is exactly the proxy-versus-phenomenon distinction this phase has already hit twice (Phase B's M3 shape gate; Task 4's fixture passing the acceptance wording while reproducing the wrong mechanism). Let the reviewers rule; record the ruling either way.
  2. New decline-note wording is untested outside this task — check when Task 6 surfaces it to operators.
  3. **The winning-donor tie-break decides WHOSE TITLES SHIP and no fixture exercises two competing donors.** Named item for the reviewers. On this phase's record this is expected to become a finding; better raised deliberately than discovered.

  THEN: any Task 5 fix round -> Task 6 -> **Task 7 ONLY if a genuinely full window remains** (plan constraint: Task 7 never starts on a partial window; a half-run measurement gate produces numbers that look like results, which is worse than no numbers). If Task 7 does not fit, checkpoint BEFORE it rather than starting it.

### CARRY-INS (all in committed files, not only here)
  - Plan Global Constraints: console-script/venv hazards; fix-round-shrink itemisation; count-unit naming; **every numeric bound mutated in BOTH directions**.
  - Plan "Notes for the executor": **the sizing heuristic** — escalate an implementer when the dangerous parts are DISCOVERABLE rather than KNOWN AND NAMEABLE. Better than task size or file count; explains Tasks 3, 4 and 5 without special-casing.
  - Plan Task 7: Step 6 (`_hygienic` exposure, pass-vs-adopt, named regression class), Step 7 (target-side-skip cost with a decision criterion), Step 8 (**scorer must measure the SHIPPED guard** — reconciliation check calling `siblings.rate_alignment`), Step 9 (**is the donor-span slide real?** three converging instruments + **C+'s PRECISION with BOTH counts**), the three-independent-instruments bar, and the never-on-a-partial-window rule.
  - CLAUDE.md: the copied-tree console-script warning.
  - Deferred to the FINAL whole-branch review: Task 1's seven minors; Task 2's Unicode-digit gap (`[0-9]{4}` is the likely one-character fix; if it needs more, it STAYS deferred); Task 3's `bool` admitted by the isinstance duration guard, two unpinned hygiene clauses, redundant `is_real_title` at :290, bare assert at :220, `rows.sort`, `rstrip(">")`, per-op DP re-solve; Task 4's untyped `tracks: list`, the unstated positional contract between `rows`/`tracks`, one vacuous assertion.
