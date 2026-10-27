# t1-rev: Task 1 review (base 9f3aadec, head 717bef24)

### Spec Compliance

- ✅ Spec compliant. `_DOTTED_ABBREV_RE = (?:[A-Za-z]\.){2,}` (packages/emcee/src/emcee/audio.py:56) with a pre-pass over `raw_parts` (audio.py:76-89) that runs before the unchanged merge loop (audio.py:90-102), matching spec §4 ("applied to the raw split parts as a pre-pass, before ... the short-fragment merge") and brief Step 3: last whitespace word, leading non-alphanumerics stripped, fullmatch, repeats for chains, one-space join. The existing abbreviation/initial/decimal/short-fragment loop is untouched. The three tests are verbatim from the brief (packages/emcee/tests/test_audio.py:112-150). No extra scope.
- ⚠️ Cannot verify from diff: the `rephrase_problems` / `_locate_block` callers (spec says the fix applies there too). They are unchanged code that inherits the splitter. The implementer reports `pytest packages/emcee -q` at 951 passed, which includes test_scriptwrite.py. I did not re-run it.

### Strengths

- The pre-pass is small and self-contained. The comment (audio.py:76-78) says why it must come before the merge loop, which is the spec's ordering requirement, so a later editor is unlikely to reorder it.
- The outro test's `max(len(p)) < 320` bound is well chosen. On HEAD the outro splits into 8 pieces with a maximum of 307 (the "Think back..." sentence), so the bound sits just above the longest legitimate piece and below the ~500-character wrong-order glue.
- The parametrized suffix "Blues for the crowd." is exactly 20 characters, so `too_short` (`< 20`) cannot mask the rule on either side, as the test comment claims.
- Edge probes on HEAD (scratch copy, run from the HEAD tree) all behave as intended:
  - `U.S. B.B. King` chains.
  - `(D.C. The band` strips the leading paren.
  - A trailing `U.S.A.` stays as a single piece.
  - `8 p.m. The band` glues two sentences, which spec §4 accepts.
  - `e.g. Big Railroad` no longer splits, which is an incidental improvement.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. **Mutation A as run was degenerate. This is a handback evidence note, not a code defect.** The named doubt was: does "8 failed, including the ≥20-char parametrized cases" plausibly follow from "pre-pass moved after the merge loop"? It does, but only for a literal block move. Moved verbatim below the loop, the block still iterates `raw_parts` and assigns `raw_parts = joined`. That variable is dead by then, because the loop has already consumed it and the function returns `sentences`. So the mutant is the same as deleting the rule. I reproduced this in a scratch copy: verbatim block moved after the loop gave **8 failed**, which matches the report.
   - That mutant does not test the ordering requirement the plan meant to pin.
   - I ran the faithful version myself: the same join pass applied over `sentences` after the merge loop. The prediction was the outro test only. Observed: **1 failed** (`test_split_outro_keeps_us_blues_without_gluing_three_sentences`), 7 passed.
   - So the ordering *is* pinned, by exactly the test the plan predicted. The prediction was stated and the observation follows from the edit, so this does not meet the reject bar. The handback should not cite its Mutation A as ordering evidence, though.
   - Mutation B (`{2,}`→`{3,}`) giving 8 failures follows directly. Every test token is two letters, so the rule vanishes for all 8 cases.
2. **No test for the chain behaviour.** brief Step 3 says "Repeat while it applies, so `U.S. B.B.` chains", but no test pins it. A probe confirms it works on HEAD (`...take on U.S. B.B. King tunes...` stays as one piece). If added, a chain test should be one parametrized case, e.g. `"...a long version of U.S. B.B. Blues for the crowd."`.
3. **Docstring not updated.** The `_split_sentences` docstring (audio.py:62-73) still lists only abbreviations, initials and decimals as no-split cases. The new rule appears only in the inline comment. Add "dotted abbreviations (U.S., D.C.)" to the docstring's list.
4. **Inline regex.** `re.sub(r"^[^A-Za-z0-9]+", ...)` at audio.py:84 is an inline pattern next to the module-level compiled ones. `re` caches it, so this is only a style point: a `_LEADING_PUNCT_RE` constant would match the file's convention.

### Checks run (scratch copy at `git archive 717bef24`, shadowing proven: `emcee.__file__` resolved inside the scratch tree)
- Printed the HEAD split of the outro: 8 pieces, lengths 130/307/193/138/153/112/67/88. The "The encore was U.S. Blues, still..." piece is intact.
- Faithful order mutant (join over `sentences` after the loop): 1 failed (outro), 7 passed.
- Literal-move mutant: 8 failed.
- Edge probes listed under Strengths.
- No test was run in the live worktree, and nothing in it was modified.

### Assessment

**Task quality:** Approved

**Reasoning:** The pre-pass implements spec §4 exactly, in the required position, with the merge loop untouched. The ordering requirement is pinned by the outro test, as an independent faithful mutant shows. The remaining items are a degenerate-mutation note in the handback, a missing chain test, and docstring polish.
