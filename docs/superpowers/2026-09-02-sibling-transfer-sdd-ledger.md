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
