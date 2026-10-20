### Spec Compliance

- ✅ Spec compliant. All five removals in the brief are present and nothing else is touched:
  - jerrybase.py:357-408 (old): `anchor_numbered_sets` is deleted whole. Its only helper was `_closer_candidates`, and that function stays, as do every other helper the brief lists (the diff removes lines only below `filler_tail_closers`).
  - gather.py:1270-1279 (old): the `if anchored is None and event is not None:` block is deleted whole. The `anchored = (...)` line and the `if anchored is not None:` branch are untouched context.
  - test_jerrybase.py: the import is reduced to `_closer_candidates` (line 5) and the four `test_5c2_*` tests are deleted (old 427-466). The 5c.3 test above them is untouched context.
  - test_stage_gather.py: both `test_5c2_*` tests are deleted. The 5c.1 test keeps its fixture, event and assertions; only its comment is rewritten (lines ~3000-3001).
  - replay_holds.py:178: the `("5c.2", ...)` NOTE_GROUPS row is deleted, and the `5c.1` row stays.
- ✅ STRICT surface (set-break placement on shipped shows):
  - Check: `git diff df602e0 098c2b2 -- packages/llama/src/llama/stages/gather.py`. The only remaining hunk is the 5c.1 routing at gather.py:1455-1457 (`op_notes += jerrybase.filler_tail_closers(tracks, event)`, after `notes += soft`).
  - So a show whose `anchor_breaks` declines reaches exactly the pre-Task-18 path: the LLM/low-coverage elif and the closer tripwire.
- ✅ Acceptance grep: `grep -rn 'anchor_numbered_sets\|5c\.2\|numbered_note' packages/ scripts/` returns no hits (run by me).
- ✅ The count reconciles: 3692 − 6 deleted tests (4 jerrybase + 2 gather) = 3686, which matches the reported 3686 passed / 1 skipped / 8 deselected.
- ✅ Do-not-retune constants: the diff is deletions plus one comment rewrite (148 deleted, 3 inserted). No protected constant or predicate is touched.
- ⚠️ Cannot verify from the diff: the binding docs still describe 5c.2 as shipping. `grep` finds 5c.2 in:
  - docs/superpowers/plans/2026-10-19-held-backlog-tier1.md: the Contracts row at :78, the file table at :129, the notes.txt groups at :989, and the Task 18 spec at :2573-2574 and :2703;
  - docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md:814.
  The brief scoped removal to packages/ and scripts/, so this is not the implementer's miss. The orchestrator should record the Checkpoint F drop in the plan/spec (as it did for Checkpoint E in a92dd72), so the Contracts table no longer names a note id with no producer.

### Strengths

- The removal is surgical. Every 5c.2 artifact named in the brief is gone, and the gather.py diff against df602e0 shows that 5c.2 left no trace on the decision path.
- The 5c.1 test's comment was rewritten without reshaping the test. That is correct: its event has no encore row, so 5c.2 never fired there, and removing 5c.2 does not change what the test exercises.
- `op_notes` is still the single sink for operator notes (gather.py:996 definition, :1457 5c.1 append, :1534 `GatherResult(notes=op_notes)`). Removing the 5c.2 append orphans nothing.
- The mutation table covers the four surviving mutants (a, d, e, f), each caught by its predicted test. The report correctly says b, c and g went away with 5c.2.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
- The commit subject is `revert(jerrybase): ...` (098c2b2), but this is a forward commit and not a `git revert`, and it also touches gather.py, tests and replay_holds.py. The prefix could mislead someone grepping history for reverts of e9e84e1. This is cosmetic; leave it unless the commit is rewritten anyway.

Named risks checked:
1. **Something left behind by the removal in gather.py.** Diffed gather.py against df602e0; only the 5c.1 hunk remains.
2. **A helper orphaned or wrongly deleted.** From the diff, the only jerrybase deletion is `anchor_numbered_sets`. In test_jerrybase.py, `_event(` still has 25 uses.
3. **Dead test scaffolding.** No remaining `real_align`/`gather_mod.align` monkeypatch in test_stage_gather.py.
4. **The harness still expecting a 5c.2 group.** test_replay_holds.py's 5c references (:491, :746-781) cover only the 5c.3/5c.1 subsections.

### Assessment

**Task quality:** Approved

**Reasoning:** 5c.2 is removed completely from code, tests and the harness. gather.py is byte-identical to df602e0 apart from the approved 5c.1 note routing, so the strict set-break surface is back on its pre-Task-18 path, and the 5c.1/5c.3 tests are unchanged and still pinned by mutation. The only follow-up is record-keeping in the plan/spec, which is outside this task's scope.
