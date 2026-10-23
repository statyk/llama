### Spec Compliance
- ✅ Spec compliant (Task 20, 8842acd, plus the survivor follow-up 174995e).
  - All 29 mutants are present: (a) through (y), the three (z) mutants zD/zS4/zS, and (aa). Each row has its predicted test, the edit and the observed result (mutation.md table). There are 28 distinct predicted tests because (d) and (aa) share `test_bare_number_rules`, as the brief specifies.
  - Shadowing was proven both ways. `llama.__file__` and `herder.__file__` resolved inside the scratch copy. A planted `raise RuntimeError("SENTINEL")` made the module ERROR at collection, and the file was then `cmp`-restored. Every mutant ran with a fresh `PYTHONPYCACHEPREFIX` and `PYTHONDONTWRITEBYTECODE=1`. The record lists the unmutated scratch baseline for all 7 modules.
  - The scratch copy is `git archive 415f8d7`, which was HEAD when Task 20 ran (8842acd's parent). The commit touches only `docs/superpowers/2026-10-23-title-hygiene-sdd/mutation.md`, and the commit message matches Step 4.
  - The two survivors were sent back to the owning task (Task 6) as Step 3 requires. t6fix (174995e) is tests only.
  - Neither commit touches a protected name from Global Constraints. The diff is one docs file and 19 added test lines, and no `src/` file changed between 415f8d7 and 174995e (`git diff --stat` is empty).
- ⚠️ Cannot verify from diff: t6fix's full-suite claim (4762 passed, 1 skipped, 8 deselected). I confirmed only the module count: 91 passed on the unmutated 174995e scratch copy.

**Does each mutant do what the brief describes?** I read the code at every cited site; each cited line matches its source line at 415f8d7/174995e.
- (a): `failed.append(("adjacent duplicate"…))` becomes `cands.pop(dup[0])`. This drops only the duplicate and lets the rest fill, which is the description.
- (b): the `tf != ef` branch at title_hygiene.py:183-184 now returns neutral.
- (c): the short-core branch at :72.
- (d): the `digits != own_core.strip()` clause at :116.
- (aa): `int(digits) == track_no` at :117.
- (g): the Q1 branch at :571, which sits after the `chosen` branch and before `deferred`.
- (h): :599.
- (j): lossless_titles.py:170 reduced to `_real(dt)`, so a 2a-shape tag becomes a C1 target.
- (k): :126. (l): :146.
- (o): the alternation in `_LEADING_TIME` gains `|\s+`, so `m:ss Word` is stripped.
- (p): :461. (q): `all` becomes `any` at :466.
- (r): replay.py:333 `False and …`, so the stored-`llm` needs-llm leg never fires. That is "relaxation unconditional".
- (s): structure.py:1154. (t): :301. (u): :428. (v): :108. (w): :212.
- (x): desc_list.py:240. (y): :353. (e): :128. (f): :37. (i): structure.py:1440.
- zD: :439. zS4: :640. zS: :604.

None of the mutants changes something other than what its row describes, so I found no false CAUGHT.

**Spot-checks.** I ran three mutants in the scratch copy `~/.llama-harness/piece3/mutation/t20-rev/src`, made with `git archive 174995e`. Shadowing was proven: `llama`, `herder` and `llama.title_hygiene` all resolved under the scratch. Each run used a fresh pycache prefix and no bytecode writes. The unmutated baseline was test_title_hygiene 91 passed and test_structure 224 passed. Each file was `cmp`-restored after its mutant. Log: `$D/t20-rev/t20-rev.log`.
- **(u)** `ag[0] < AGREEMENT_FLOOR` → `<=` at :428: 1 failed, 90 passed. The failure is `test_decide_d_agreement_exactly_at_floor_passes`, with `d.failed` containing `('agreement', "track 2 'Jack Straw'")`. It is killed for the right reason: the boundary share 0.5 now trips the agreement decline through `decide_d`.
- **(zD)** guard dropped at :439: 1 failed, 90 passed. The failure is `test_apply_d_guard_skips_a_resolved_position`, where `out[0]` became `('Wrong Title', 'desc-position')`. Killed for the right reason.
- **(s)**, the recorded CAUGHT I doubted most, because the predicted test opens with a membership assertion on the constant:
  - As recorded, the test fails at test_structure.py:2120, which is exactly that membership assertion.
  - I then removed that line from the scratch test and re-ran. The behavioural line at :2121 still fails: `_songish_coverage` returns 0.667 against the expected 0.5.
  - So the CAUGHT holds on behaviour, not only on inspecting the constant.

### Strengths
- The record is auditable. It gives the exact edit per mutant and the "other red tests" column. It is honest about scope: "other red" means within the predicted test's module only, and the (u) row says the whole 3051-test `packages/llama/tests` tree stayed green.
- Both survivor diagnoses are correct.
  - (u): the old test asserts `not share < AGREEMENT_FLOOR` on `agreement_share`'s output (test_title_hygiene.py:228-232), so it never reaches :428.
  - (zD): `decide_d` builds `open_` from unresolved positions only (title_hygiene.py:386), so a decision built through it can never reach the guard.
- The new tests are behavioural, not tautological.
  - `test_decide_d_agreement_exactly_at_floor_passes` (test_title_hygiene.py:619-626) goes through `decide_d` and asserts both `failed == ()` and the fill. The `agreement_share(...) == AGREEMENT_FLOOR == 0.5` line is a precondition guard that keeps the fixture on the boundary, not the assertion under test. 1/2 is exact in floating point.
  - `test_apply_d_guard_skips_a_resolved_position` (:629-635) checks both sides: the resolved track is untouched, and the unresolved track is filled and stamped `desc-position`. A guard that blocked every fill would also fail it.

### Issues
#### Critical (Must Fix)
None.
#### Important (Should Fix)
None.
#### Minor (Nice to Have)
1. **test_title_hygiene.py:228-232: the old `test_agreement_exactly_at_floor_passes` is still a tautology.** It asserts `not 0.5 < AGREEMENT_FLOOR` and pins nothing, and mutation.md row (u) still names it as the predicted test. This matters because a future reader takes the brief's predicted name as the pin. Fix: delete it, or fold its `agreement_share == 0.5` line into the new test.
2. **mutation.md Survivors section is out of date after 174995e.** It still reads as open findings: "not fixed here", "orchestrator decides". Fix: add a resolution line naming 174995e, the two killing tests and their observed results (1 failed, 90 passed each). Then the record states that every listed mutant is now killed.
3. **(zD) is equivalent on the production path; this answers the record's open question.**
   - `apply_d`'s only call site is stages/gather.py:1432-1437. It is called immediately on the same `tracks` that `decide_d` just saw, and `decide_d` fills only unresolved positions (title_hygiene.py:386).
   - So the guard at :439 is unreachable from gather today. The new test pins `apply_d`'s documented contract (docstring at :436), not any gather outcome.
   - That is a legitimate defence-in-depth pin, but it should say so. Under Global Constraints, a test of existing behaviour is marked **(pin)**, and neither new test carries the marker; `test_decide_d_agreement_exactly_at_floor_passes` is likewise a pin of existing behaviour.
   - Fix: add `(pin)` to both docstrings. For the apply_d test, add a clause noting the guard is unreachable through `decide_d`.

### Assessment
**Task quality:** Approved
**Reasoning:** Every recorded mutant matches its description at the cited line, and shadowing and bytecode isolation were proven. My three spot-checks confirm that (u) and (zD) are now killed for the right reason and that the most doubtful CAUGHT, (s), holds on behaviour. What remains is housekeeping: the leftover tautological test, the stale Survivors section, and the missing (pin) markers.
