# T14c review (f1f447db..3497e77e), reviewer on Opus

### Spec Compliance
- ✅ Spec compliant. The commit implements the T14c ruling exactly:
  - Rule (b) now records a never-ruled `research-song` flag. `scripts/bulk_apply.py:313` gates (b) on `_NEVER_KINDS_B = {"titles"}` (`:149`), so `titles` is still never recorded under (b).
  - The ruling exclusions still apply to both rules. `eligible` (`:308-309`) keeps the still-listed check (`_STILL_LISTED`) and the `_NEVER_RULINGS` check, so a flag ruled `research-wrong` or `research-right-show-wrong` is not recorded under (a) or (b).
  - Rule (a) is unchanged. It still requires `fix` and `_STRUCTURE_KINDS`, and now also excludes `_NEVER_KINDS_A = {titles, research-song}` (`:310-311`).
  - The order is unchanged: today's rule (`:298-301`, `continue`), then (a) (`if`), then (b) (`elif`), then the list. Rule (c) (`v is None` branch) and rule (d) (the `for f in named` loop) are untouched.
  - `_NEVER_KINDS` has no remaining references: the only hits are lines 148-149, 311 and 313.
- The moved expectation is justified. `test_rule_a_and_b_never_record_titles_unknown_song_or_research_rulings` (test file :437-457) uses a `fix` verdict and a rehold `overrule`, so the never-ruled `research asserts unknown song: S` now falls to (b). The test now asserts that record exactly, with the rule-b note. These stay listed with their reasons and still pin their exclusions with (b) active:
  - `unresolved track titles`;
  - both `research-wrong` flags;
  - the `research-right-show-wrong` song.

  (a) is also active in that test (fix verdict), so the same assertions cover it. The implementer stated the move before editing (handback "Existing expectation moved"), as the plan's dry-run rule requires.
- The new test `test_rule_b_covers_research_song_but_not_titles` (:460-482) pins both sides:
  - `rb` (rehold overrule): the song is recorded with kind `research-song`, subject `["s"]` and the rule-b note, and the titles flag stays listed.
  - `fx` (fix verdict, no rehold file): both flags stay listed.
- ⚠️ Cannot verify from the diff: whether the ruling is written down anywhere outside the code comment and the commit message. The T14b brief at line 14 still says the NEVER exclusions cover (b) for `research-song`; that line is now superseded. This is a ledger matter, not a code defect.

### Mutation evidence (scratch copies via `git archive 3497e77e scripts`, run from the copy with `$W/.venv/bin/python -m pytest -q -p no:cacheprovider`, `PYTHONDONTWRITEBYTECODE=1`; log `t14c-review.log`)
| mutant | predicted red | result |
|---|---|---|
| baseline | none | 18 passed |
| m1: `_NEVER_KINDS_B = {"titles","research-song"}` (re-adds song to b) | both tests | 2 failed (moved :449, new :473) |
| m2: `_NEVER_KINDS_B = frozenset()` (drops titles from b) | both tests | 2 failed (titles recorded under rule b) |
| m3: delete the `_NEVER_KINDS_B` check at :313 | both tests | 2 failed |
| m4: `_NEVER_KINDS_A = frozenset()` | none (dead, see Minor 1) | 18 passed, as predicted |

All three mutants of m1-m3 went red only in the copy, which shows the copy's code ran.

### Strengths
- The change is minimal and local. Splitting the constant per rule keeps each rule's exclusions explicit, and moving the kind test out of `eligible` is the correct place for it.
- Both the new test and the reworded test assert exact `(flag, note)` pairs and exact `listed` reasons, not just counts.
- The `fx` arm of the new test separates (a) from (b) in one fixture.
- The TDD RED/GREEN evidence is recorded, and the moved expectation was declared up front.

### Issues
#### Critical (Must Fix)
None.
#### Important (Should Fix)
None.
#### Minor (Nice to Have)
1. `scripts/bulk_apply.py:148,311`: `_NEVER_KINDS_A` is dead code. Neither `titles` nor `research-song` is in `_STRUCTURE_KINDS` (`:151`), so the extra check can never change an outcome, and mutant m4 survives. The implementer's report says so openly. The `fx` arm of the new test passes because of `_STRUCTURE_KINDS`, not `_NEVER_KINDS_A`, so the comment's claim that "a fix verdict (a) does not" cover songs is true but is not pinned by this constant. It is harmless as documentation. If kept, a one-line comment saying it is redundant with `_STRUCTURE_KINDS` would stop a reader from thinking it is load-bearing.
2. `scripts/test_bulk_apply_backfill.py:437`: the test name `test_rule_a_and_b_never_record_titles_unknown_song_or_research_rulings` now overstates (b), since (b) does record unknown songs. The name was fixed by the brief, and the new inline comment points at the ruling, so a rename is optional.
3. A pre-existing T14b item, not introduced here: the `_NEVER_RULINGS` check in `eligible` (`:309`) is redundant with `_STILL_LISTED`. A flag ruled `research-wrong` or `research-right-show-wrong` always lists as `ruled …`, because only `spurious`/`flag-spurious` count as ok. So deleting that clause would not turn any test red. The brief explicitly asked for it to be kept "explicit in code or a test", so it is fine.

### Out of scope
- The superseded T14b brief line 14 (see ⚠️ above) should get a note in the SDD ledger, so a later reader does not "fix" (b) back.

### Assessment
**Task quality:** Approved
**Reasoning:** The diff implements the ruling exactly, with the order and rules (a), (c) and (d) unchanged. The moved expectation follows directly from the ruling. Mutants that re-add `research-song` to (b) or drop `titles` from it each turn both tests red. The only findings are a dead constant and a stale test name.
