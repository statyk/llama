# t11b-impl handback (Task 11b)

**Status: DONE_WITH_CONCERNS.** The concerns are deviation 1 (a scoped predicate) and a cleanup slip in the mutation step (see "Concerns").

**Commit:** `9b74164` fix(titles): placeholder refusal in the setlist rungs + 2a/2c shipped-title cosmetics. It holds code, tests and the plan-doc note, on BASE 127dd45.

**Tests:** `./.venv/bin/python -m pytest -q` gives 3481 passed, 1 skipped, 8 deselected (48 s). `llama.__file__` resolves inside the worktree.

## What changed
- **Part A (the defect).**
  - New `titles.is_placeholder_text(t)` = `is_placeholder(t) or is_timestamp(t) or (is_real_title(t) and is_residue(t))`. This is exactly 2b's per-title arm. `placeholder_positions` now calls it, with identical behaviour, so the 2b demotion and the refusals share one definition.
  - **`setlist` rung** (titles.py, `resolve_titles`): `elif aligned and not is_placeholder_text(aligned[pos].title):`. A placeholder item now leaves the position `unresolved` (title = filename).
  - **`setlist-gap`** (structure.py, `adopt_gap_titles`): a check beside `hygienic_title`, which itself is unedited. `if any(is_placeholder_text(it.title.strip()) for it in gap): continue`, so one placeholder declines the whole gap (the orchestrator's ruling).
    - Import cycle: titles.py and placeholders.py both import structure at load time. So `adopt_gap_titles` uses a function-local `from llama.titles import is_placeholder_text`, the same pattern `hygienic_title` already uses for `is_real_title`/`is_junk_title`.
  - **Real-data check** (replay harness `run --slugs`, which reads `~/.llama` read-only; output in the scratchpad):
    - zachdeputy-2008-12-06 tracks 1, 2, 3, 8 and 14 were `Track 01…` with source `setlist-gap` in B-cand-all. They are now `TrackNN.mp3` with source `unresolved`.
    - infamousstringdusters-2010-10-15 tracks 3 and 9 are now `unresolved`.
- **Part B (cosmetics).**
  - New `titles.shipped_short_tag(tag)` runs `strip_taper_markers`, then three strips:
    - `_SHIPPED_PUNCT_TAIL` `[\s,;:]+$`
    - `_SHIPPED_FOOTNOTE_PAREN` `\s*\(\s*(?:\d+|[*#^+~@]+)\s*\)\s*$`
    - `_SHIPPED_ENCORE_LEAD` `^\s*(?:e|enc|encore)\s*:\s*` (case-insensitive)
  - The strips repeat to a fixpoint. A strip that would leave no alphanumeric character is not applied.
  - `accept_short_tags` ships this title. The 2a note quotes the cleaned title in the unchanged Contracts format. `strip_taper_markers` itself is unchanged.
  - 2c: new `_GLUED_FOOTNOTE_TAIL` `\s+[#^*+~@]+\s*$`, applied in `clean_tag_titles` only to titles the glued strip actually changed. The 2c note shows the cleaned title. `F#`, `Untitled #12` and `Key Of F#` are untouched.
  - All new constants carry a comment citing "Checkpoint B operator decision 2 (2026-10-19)".
  - Set markers are deliberately not handled. Of the 91 accepted 2a tags in `cmp-B-all/notes.txt`, none carries `Set N:`. The only prefix seen was `E: 2x2`.
  - Real data shows `M80`, `2x2`, `42`, `The Cuckoo`, `Cold Rain And Snow` and `Walls Of Time`, with matching notes.
  - `scripts/test_replay_holds.py` passes; its 2a note regex is unaffected.
- **Part C.** A "**Recorded at Checkpoint B (operator, 2026-10-19):**" block now sits under the Checkpoint B **Ask:** paragraph in the plan.
- **Do-not-retune check.** Grepping the diff for every protected name found only imports, comments and the unchanged *call* `is_real_title(t) and is_residue(t)` moved into the helper. No protected constant changed.

## Sibling-align finding
Sibling-align could adopt a placeholder, so I fixed it.
- In `siblings.propose_rows`, a donor's title is gated only by `is_real_title` + `hygienic_title`. `Track 02` and `tmp` pass both.
- Probe before the fix: donor `["Alpha","Track 02","Charlie"]` gave row 2 `adopt 'Track 02'`. With `tmp` the same happened.
- Whether that row ships automatically depends on the auto band and C+ bracketing. A mostly-real-tagged donor with one placeholder tag is exactly the case that brackets.
- The fix is the one-line refusal at the adoption point, folded into the existing hygiene decline: `elif not all(hygienic_title(t, metadata_norms) and not is_placeholder_text(t.strip()) for t in titles):`. The reason stays "sibling title fails hygiene".
- This also keeps the placeholder out of the operator proposal surface (`best_donor`/`propose_rows`), which shares the code path.
- Test: `test_siblings.py::test_a_donor_track_titled_with_a_placeholder_fails_hygiene[Track 02|tmp]`.

## Deviations
1. **Scoped predicate instead of literal `placeholders.is_placeholder_title`.**
   - That function's own docstring requires callers to pre-gate on `is_real_title`: without the gate, its residue arm returns True for `42`, `FF`, `J` and `7-11`.
   - Used literally in the whole-tape `setlist` rung, it would refuse real short items that the rung adopts today.
   - `is_placeholder_text` applies that gate to the residue arm only. Vocabulary and timestamps are still refused unconditionally.
   - In `setlist-gap` the two are equivalent, because `hygienic_title` already requires `is_real_title`.
   - Pinned by `test_setlist_rung_still_adopts_real_and_short_items` (mutant m7).
2. **Sibling-align was changed**, as allowed by the brief, since it was the same one-line refusal.
3. **The 2b corroboration exemption is not applied in these refusals.** The brief says "never adopt"; a cross-source-corroborated `Track 01` setlist item is not a measured case.

## Mutation table (Global Constraints recipe)
Each mutant ran in a fresh rsync copy under `$TMPDIR`, with PYTHONPATH shadowing and a private PYTHONPYCACHEPREFIX. Shadowing was proven for every mutant (`llama.__file__` was under the copy). Predictions were written to the log before running. Test files: test_titles, test_structure, test_siblings, test_stage_gather and scripts/test_replay_holds.

| mutant | predicted test | caught by |
|---|---|---|
| m1 remove `setlist`-rung refusal | test_titles::test_setlist_rung_refuses_a_placeholder_item | that test |
| m2 remove `setlist-gap` refusal | test_structure::test_placeholder_items_gap_is_not_readopted | that test + test_one_placeholder_item_declines_the_whole_gap |
| m2s remove sibling-align refusal | test_siblings::test_a_donor_track_titled_with_a_placeholder_fails_hygiene | both params ([Track 02], [tmp]) |
| m3 drop trailing `,;:` strip | test_titles::test_shipped_short_tag[M80,-M80] | that + [FF;] [J :] [M80, *] + test_stage_gather::test_accept_short_tags_ships_and_notes_the_cleaned_title |
| m3b strip also `!?` | test_shipped_short_tag[Help!-Help!] | that + [Who Are You?] |
| m4 drop leading `E:` strip | test_shipped_short_tag[E: 2x2-2x2] | that + [enc: FF] [ENCORE : J] [Enc:J] + gather cleaned-title test |
| m5 drop `(1)` footnote strip | test_shipped_short_tag[42(1)-42] | that + [42( 2 )] [J (*)] [FF (#)] [42(1) >] + gather cleaned-title test |
| m5b widen to any parenthetical | test_shipped_short_tag[Jam (Reprise)-Jam (Reprise)] | that + [J (Jam)] |
| m6 drop 2c `#`/`#^` strip | test_titles::test_glued_strip_also_drops_a_free_standing_footnote_run | that + test_stage_gather::test_2c_ships_and_notes_railroad_earths_titles_without_footnote_marks |
| m6b strip a glued `#` (`\s*`) | test_glued_strip_also_drops_a_free_standing_footnote_run (`Key Of F#`) | that test |
| m7 literal `is_placeholder_title` in setlist rung | test_titles::test_setlist_rung_still_adopts_real_and_short_items | that test |
| m8 footnote strip on every title of a glued tape | test_titles::test_footnote_strip_is_only_on_the_glued_path | that test |

There were no survivors.

## Concerns
- **Mutation-copy cleanup was too broad.** After the run I removed my scratch copies with `rm -rf "$TMPDIR"/mut-*`. That glob would also have removed any other agent's `mut-*` copies under the same `$TMPDIR` (`/var/folders/yn/.../T/`) if one was running concurrently. I did not check first. If another child was mid-mutation, it may see its copy vanish; its results would fail loudly, not silently.
- **Setlist-rung test coverage.** The rung is measured dead in production. The `setlist` refusal is pinned by unit tests only; the real-data effect was observed on the `setlist-gap` rung.
