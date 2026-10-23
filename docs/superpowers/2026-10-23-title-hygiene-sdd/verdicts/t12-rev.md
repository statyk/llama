### Spec Compliance
- ✅ Spec compliant. Every interface the brief names is present: `run --strip-title-overrides`, alone or with `--strip-structure-overrides` (scripts/replay_holds.py:1116-1119, keys built at :178-179, dispatch on `if keys` at :194-197). `_shadow(d, shadow_root, keys: tuple[str, ...])` (:106) strips only the given keys, with `TITLE_KEYS = ("titles",)` (:100). The arm key `title_overrides_stripped` (:213). `_gates` refuses a mismatch with exit 2, reading a missing key as False through `bool(...)` (:299-300). `compare` writes no apply lists when either flag is set (:1046, :1058, :1089-1090). The four named tests are present (test_replay_holds.py:946-1012), plus a contract test that pins Task 13's `_shadow(d, root, ("titles","set_breaks","encore_after"))` call (:963-970).
- Cherry-pick safety: the diff touches only `scripts/`. `git diff --stat 11dbffb dd3a513 -- scripts/` is empty, so fb5affa applies to the base tree without conflict.
- Global Constraints: I grepped the diff for every protected name and `setlist.py`. There are no hits, and the diff has no `packages/` file.
- ⚠️ Cannot verify from the diff: the implementer's suite counts (76 / 4683 passed). Step 6 (the base-tree worktree, its venv and the `llama.__file__` check) belongs to the orchestrator.

### Strengths
- The generalization is minimal and correct. One `keys` tuple drives both the shadow and the dispatch, so a title-only run no longer silently replays unstripped. The old `if args.strip_structure_overrides` dispatch would have done exactly that.
- The tests check real behaviour, not mocks. A spy on `replay_show` reads the overrides the replay actually saw (test:922-926). The live file's bytes are asserted unchanged (:932), which is the Task 13 contract. The `stripped` row record is checked for both flag combinations (:951, :959-960).
- `test_no_apply_lists_for_title_stripped_arms` is load-bearing. `compare` deletes stale outputs unconditionally at replay_holds.py:1006-1007, so the glob assertion fails only if the lists get re-written. That is what a mutant dropping `and not title_stripped` would do.
- The mixed-arm refusal is checked in both directions (test:988-990), and so is the stderr text.

### Issues
#### Critical (Must Fix)
None.
#### Important (Should Fix)
None.
#### Minor (Nice to Have)
1. **scripts/replay_holds.py:1046-1050: the taper reports are still written for a title-only-stripped arm.** The guard's own comment says why stripped arms are excluded: "a stripped arm replays without the operator's overrides: not the shipped library". That holds just as much when the title overrides are gone. Titles feed alignment, so `taper_changes.txt` (whose `segues changed` rows steer re-processing) would describe a view that is not the shipped one. This is low impact: Task 13's fresh-get arms set both flags, so `stripped` suppresses the reports there, and the implementer flagged it as a judgement call. Fix: gate on `stripped or title_stripped` with a matching summary line, or note why title-only is deliberately kept.
2. **scripts/replay_holds.py:99: `STRIPPED_KEYS` was renamed with no alias.** The archived evidence script `docs/superpowers/2026-10-22-taper-set-markers-sdd/evidence/orch-r1/t7a-rr1/check_renum.py:5` does `from replay_holds import STRIPPED_KEYS` and would now fail with ImportError if re-run. It is a frozen evidence artifact, so this only matters if someone re-runs it. Fix (optional): `STRIPPED_KEYS = STRUCTURE_KEYS  # back-compat for piece-2 evidence scripts`.
3. **scripts/test_replay_holds.py:991-994: the "pre-piece-3 arm reads as unstripped" check compares an arm with itself.** Both sides lack the key, so a mutant that drops the `bool()` coercion in `_gates` (:299, `None != None` is False) still passes. The claim that a missing key equals an explicit False is not pinned. The existing structure-strip test (:903-909) has the same weakness, so this copies a pattern rather than introducing one. For Task 13 it hardly matters, since the base tree gets the cherry-picked key. Fix: compare the key-deleted arm against a fresh unstripped arm (explicit `False`) and expect 0.
4. **scripts/replay_holds.py:1089: the summary line says `--strip-structure-overrides or --strip-title-overrides` rather than naming the flag(s) actually set.** This is polish, and harmless.

### Assessment
**Task quality:** Approved
**Reasoning:** The change does exactly what the brief asks: title-only and combined stripping, the shadow-only rewrite with the live file untouched, the stamped arm, the mismatch refusal and the apply-list suppression. The tests would catch the meaningful mutants, and the diff is scripts-only and cherry-picks cleanly onto 11dbffb. The remaining items are minor consistency and pinning gaps.

(Named-risk checks run: `git diff --stat 11dbffb dd3a513 -- scripts/` for cherry-pick safety; a repo grep for `STRIPPED_KEYS`, `*_overrides_stripped` and `_shadow(` readers, which found taper_probe.py:931; `score` refuses any arm without the structure strip, so a title-only arm is refused, which is correct; a read of compare's stale-output unlink at :1006 to judge the no-lists test. No tests re-run.)
