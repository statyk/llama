# t11b-rev: Task 11b review (127dd45..9b74164)

### Spec Compliance

- ✅ **Spec compliant.** All three brief parts are implemented, with tests.
  - **Part A, `setlist` rung** (titles.py:382): the position stays unresolved and keeps its filename as the title.
  - **Part A, `setlist-gap`** (structure.py:206-211): a check beside `hygienic_title` declines the whole gap. `hygienic_title` itself is unedited. The circular import is solved with a function-local import (structure.py:190), the same pattern `hygienic_title` already uses.
  - **Part B, 2a path**: `shipped_short_tag` (titles.py:314-333) is used only by `accept_short_tags` (gather.py:162). The 2a note quotes the cleaned title, in the unchanged Contracts format.
  - **Part B, 2c path**: `_GLUED_FOOTNOTE_TAIL` (titles.py:238, 261) applies only to titles the glued strip changed. The 2c note shows the cleaned title. That works because gather.py:1108 compares the raw tag with the cleaned `tag_titles`.
  - **Part C**: the plan note is present under Checkpoint B's **Ask:** (plan doc, diff lines 34-37) and covers all three items the brief asked for.
  - **Tests**: every test the brief requires exists:
    - zachdeputy-shape gap: test_structure.py `test_placeholder_items_gap_is_not_readopted`
    - real-title gap still adopts: `test_a_real_title_gap_beside_placeholder_shapes_still_adopts`
    - whole-tape rung refusal: test_titles.py `test_setlist_rung_refuses_a_placeholder_item`
    - real aligned title still adopts: `test_setlist_rung_still_adopts_real_and_short_items`
    - each cosmetic case plus the "stays" set (`Help!`, `(Reprise)`, `Untitled #12`, `F#`, `100%`): `test_shipped_short_tag`, `test_glued_strip_also_drops_a_free_standing_footnote_run`
  - **Mutation table**: complete for m1-m6b, plus m2s, m7 and m8. Each row names its predicted test.
- **Deviations, judged on their merits**:
  1. **`is_placeholder_text` instead of `is_placeholder_title`: accepted.**
     - `placeholders.is_placeholder_title`'s own docstring (placeholders.py:134-136) requires callers to pre-gate on `is_real_title`. Without that gate it refuses `42`, `FF` and `J`.
     - Used literally on the `setlist` rung, it would therefore refuse real short items.
     - On `setlist-gap` the two predicates are equivalent, because `hygienic_title` already requires `is_real_title`.
     - The new helper also single-sources 2b's per-title arm. `placeholder_positions` (titles.py:359) behaves identically, and the suite stays green.
     - Pinned by m7.
  2. **Sibling-align guarded: accepted.**
     - It is the one-line refusal at the adoption point, folded into the existing hygiene decline (siblings.py:87-91). The brief allows exactly that.
     - The reason string is unchanged, so no new note or flag text was added.
     - My probe agrees with the implementer: before the fix, `Track 02` and `tmp` pass both `is_real_title` and `hygienic_title`.
  3. **No corroboration exemption: accepted.** The brief says "never adopt", and no case of a cross-source `Track 01` item was measured.
- **Global constraints**:
  - **Do-not-retune.** I grepped the diff's +/- lines for every protected name. The hits were imports, comments, and the unchanged *call* `is_real_title(t) and is_residue(t)` moved into the helper. No protected definition changed. `hygienic_title` and `strip_taper_markers` are untouched.
  - **Overwrites.** Real tags are never overwritten. Both refusals sit after the tag/demotion branches (titles.py:375-386), and sibling adoption is still intersected with the unresolved set downstream.
  - **Notes to the LLM.** No new note reaches the LLM. No new flags or `conflicts` entries were added.
- ⚠️ **Cannot verify from diff**:
  - **Other agents' mutation copies.** I cannot tell whether the implementer's `rm -rf "$TMPDIR"/mut-*` deleted another agent's live copies. The controller should check whether any concurrent child reported a vanished `mut-*` tree in the same window.
  - **Real-data effect.** The zachdeputy and infamousstringdusters result is taken from the implementer's replay output. I did not re-run the harness.
  - **Operator proposal path.** `correspondence.propose_titles` (`--suggest-titles` / `[t]`) does not share the hygiene veto, so it may still propose a `Track 01` setlist item. It is operator-confirmed and outside the brief's scope. It is listed only so the gap is known.

### Strengths
- **Import cycle.** It is named and solved with the module's existing pattern, and the reason is commented in place (structure.py:188-190).
- **Narrowed predicate.** The rationale is in the docstring (titles.py:284-300), and m7 pins it. Using the literal predicate would have been a silent regression.
- **`shipped_short_tag`.**
  - It runs to a fixpoint with an alphanumeric floor, so `42(1) >` and `M80, *` come out bare, and `E:` alone is never reduced to nothing.
  - Its parametrized table covers both strip and stay cases, including `Every Day` and `Set 2: FF`.
- **2c strip.**
  - It is gated per title on `_GLUED_NUM_PREFIX.match(t)`, so a 2c note can never fire for a footnote-only change.
  - `test_footnote_strip_is_only_on_the_glued_path` pins that scope, on both a vote-passing tape and a vote-failing one.
- **Mutation table.** Every mutant has a named predicted test, there are no survivors, and each mutant ran from a shadowed copy with its own bytecode cache.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **A placeholder with a segue marker gets past the sibling check** (siblings.py:88).
   - The refusal tests `t.strip()`, but `proposed` is built from `t.strip().rstrip(">").strip()`.
   - Probe result: `is_placeholder_text("tmp >")` is False, while the same text with the `>` stripped is True.
   - So a donor tag `tmp >` is still adopted. `Track 02 >` is caught by another arm.
   - Fix: test the same normalised form that `proposed` uses.
   - Edge case only; it does not affect the measured shows.
2. **The `setlist` rung now also refuses some vocabulary words** (titles.py:382).
   - Because the refusal applies the vocabulary regardless of `is_real_title`, setlist items `Title`, `Temp`, `Cut 3` and `Trk 5` are no longer adopted (probe confirmed).
   - This is within the brief's "never adopt" wording, and the rung is measured dead (titles.py:441-453), so the cost is effectively nil. Noted for the record only.
3. **The footnote-parenthesis strip also removes a year** (titles.py:315).
   - `\d+` strips a trailing 4-digit parenthetical, so `42 (2001)` becomes `42` (probe).
   - The ruling's word is "a parenthesised NUMBER", so this complies. It only reaches 2a-accepted tags.
   - If a year-in-parentheses ever matters, a `\d{1,3}` bound would separate footnotes from years.
4. **Style: `import pytest` mid-file** (test_siblings.py:1063, diff line 415), not at the top of the module. test_titles.py has a precedent for mid-file imports, but pytest was not previously imported in test_siblings.py. Move it to the top.
5. **Process: the mutation-copy cleanup was over-broad.**
   - The implementer ran `rm -rf "$TMPDIR"/mut-*` across a shared `$TMPDIR`, which violates mandate 5 ("Clean up only your own scratch dirs, by exact path").
   - The implementer reported this themselves. There is no effect on the code. See the ⚠️ item above.

### Assessment

**Task quality:** Approved

**Reasoning:** The defect fix refuses placeholders at all three adoption rungs through one shared predicate, and real tags plus the protected constants are untouched. The cosmetics are tightly scoped to the 2a and 2c paths and pinned by targeted, mutation-checked tests. The remaining items are edge cases or style.

### Checks run
- **Named risk: the narrowed predicate could refuse real setlist items.** I probed `is_placeholder_text` and `is_real_title` over about 35 realistic titles:
  - `Dew`, `Jam`, `Space`, `Drums`, `Tuning`, `Intro`, `1999`, `2001`, `3:10 To Yuma`, `Tracks`, `Temptation`, `Untitled` and `Jam #2` are all False.
  - `Title`, `Temp`, `2:22`, `Tr 2`, `Cut 3` and `Trk 5` are True.
- **Named risk: a `shipped_short_tag` edge collapses or over-strips a title.** I probed 14 tags (`E:`, `Re:`, `E: (1)`, `Encore: Jam (1),`, `42 (2001)` and others). None came out empty, and the only over-strip found is Minor 3.
- **Named risk: the sibling refusal is bypassed by a segue suffix.** Probed: `tmp >` bypasses it (Minor 1).
- **Do-not-retune.** Grepped the diff's +/- lines for every protected name: clean.
- **2c note emission.** Read gather.py:1108: the note compares the raw tag with the cleaned title and is gated on `_GLUED_NUM_PREFIX.match(raw)`.
- **Focused tests.**
  - Command: `./.venv/bin/python -m pytest -q` over test_titles, test_structure, test_siblings and scripts/test_replay_holds, with `-k "placeholder or shipped or glued or footnote or setlist_rung or real_title_gap or replay"`.
  - Result: 123 passed, 252 deselected.
  - `llama.__file__` resolves inside the worktree.
