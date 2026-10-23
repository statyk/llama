# Title hygiene: mutation record (Task 20)

## Method

- Scratch copy: `git archive 415f8d7 | tar -x -C ~/.llama-harness/piece3/mutation/scratch`. The live worktree was never edited; every mutant lives in the scratch copy.
- Command form (cwd = scratch, never the worktree):
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=<fresh dir per mutant> PYTHONPATH=<scratch>/packages/llama/src:<scratch>/packages/herder/src:<scratch>/packages/emcee/src <worktree>/.venv/bin/python -m pytest -q -p no:cacheprovider -rfE <scratch>/packages/llama/tests/<module>`
  Never `.venv/bin/pytest`, never `pip`.
- Shadowing proof: under that env `import llama` resolves to `.../mutation/scratch/packages/llama/src/llama/__init__.py` (herder likewise inside the scratch). A planted `raise RuntimeError("SENTINEL")` at the end of the scratch `title_hygiene.py` made `test_title_hygiene.py` ERROR at collection (`title_hygiene.py:671: RuntimeError: SENTINEL`). The file was then restored from the archive and `cmp` against `git show 415f8d7:...` was identical.
- Unmutated scratch baseline, every module used: test_title_hygiene 89, test_desc_list 36, test_structure 224, test_lossless_titles 28, test_title_cosmetics 10, test_stage_gather 231, test_replay 94, all passed.
- Per mutant: predicted test written down first; smallest edit realising the description (single-occurrence replace); the predicted test's WHOLE module run; the file restored from the archive and `cmp`-verified identical before the next mutant. Classes: CAUGHT (predicted test red), SURVIVED (predicted green, nothing red), SURPRISE (predicted green, another test red).
- All 28 predicted test names exist under those names (no name drift). Slices dropped at Checkpoint A: none.

## Result: 27 CAUGHT, 2 SURVIVED, 0 SURPRISE (29 mutants; (z) is three)

Files are under `packages/llama/src/llama/`; tests under `packages/llama/tests/`.

| id | description | mutated at | edit | predicted test | result | other red tests in the module |
|---|---|---|---|---|---|---|
| a | check 2 declines only the duplicate | title_hygiene.py:408 (decide_d) | `failed.append(("adjacent duplicate",...))` -> `cands.pop(dup[0])` | test_title_hygiene::test_check2_one_duplicate_declines_every_fill | CAUGHT | test_check_order_and_all_failures_recorded |
| b | filler tag vs song entry neutral | title_hygiene.py:183 | `return "disagree"` -> `"neutral"` | test_title_hygiene::test_filler_tag_against_song_entry_disagrees | CAUGHT | test_check3_disagreement_declines |
| c | short cores via `loosely_same_title` | title_hygiene.py:72 | short-core branch `return na == nb` -> `return loosely_same_title(na, nb)` | test_title_hygiene::test_short_core_compares_by_equality_only | CAUGHT | test_agreement_share |
| d | own-tag-core exemption removed | title_hygiene.py:116 | `digits != own_core.strip() and (` -> `True and (` | test_title_hygiene::test_bare_number_rules | CAUGHT | none |
| e | leader strip without the vote | desc_list.py:128 | `_build(s, d, t, vote)` -> `_build(s, d, t, True)` | test_desc_list::test_leader_stripped_only_under_the_vote | CAUGHT | none |
| f | leader lookahead removed | desc_list.py:37 | drop `(?=[^\d\s])` from `_ENTRY_LEADER` | test_desc_list::test_date_shaped_entries_keep_their_numbers | CAUGHT | none |
| g | Q1 removed | title_hygiene.py:571 (plan_setlist_rung) | `if wholly_untagged:` -> `if False:` | test_title_hygiene::test_s_never_fills_a_wholly_untagged_tape | CAUGHT | test_untagged_with_no_s_positions_writes_no_note, test_chosen_canonical_untagged_without_list_declines |
| h | deferred S fills after a shift | title_hygiene.py:599 | `if d is not None and d.shift:` -> `if False:` | test_title_hygiene::test_deferred_s_declines_with_d_on_a_shift | CAUGHT | none |
| i | `declined` ignored by setlist-gap | structure.py:1440 | `if any(lo <= p <= hi for p in declined):` -> `if False:` | test_structure::test_declined_positions_bind_setlist_gap | CAUGHT | none |
| j | 2a-shape delivered tag is a C1 target | lossless_titles.py:170 | condition reduced to `if _real(dt):` | test_lossless_titles::test_2a_shape_delivered_tag_is_not_a_c1_target | CAUGHT | test_2a_shape_delivered_tag_goes_to_c2 |
| k | C scope gate removed | lossless_titles.py:126 | `if not in_scope:` -> `if False:` | test_lossless_titles::test_c_does_not_run_below_recover_below | CAUGHT | none |
| l | C +/-1 skip removed | lossless_titles.py:146 | `if len(shifted) >= 2:` -> `if False:` | test_lossless_titles::test_two_off_by_one_lossless_tags_skip_c | CAUGHT | test_exactly_two_off_by_one_lossless_tags_skip_c |
| m | slice 4 neighbour requirement removed | title_hygiene.py:657 | `if "agree" not in verdicts:` -> `if False:` | test_title_hygiene::test_short_tag_needs_an_agreeing_neighbour | CAUGHT | test_declines_recorded_with_reason |
| n | stem veto removed | title_hygiene.py:660 | `if len(core) >= STEM_SUBSTRING_MIN and ...` -> `if False and ...` | test_title_hygiene::test_core_inside_the_stem_is_refused | CAUGHT | test_declines_recorded_with_reason |
| o | bare `m:ss Word` stripped | title_cosmetics.py:18 | `_LEADING_TIME` alternation gains `\|\s+` | test_title_cosmetics::test_bare_time_word_titles_are_never_stripped | CAUGHT | none |
| p | self-filled ignores `failed` | title_hygiene.py:461 | `if d is None or d.failed:` -> `if d is None:` | test_title_hygiene::test_self_filled_requires_d_to_pass_every_check | CAUGHT | none |
| q | Q2 applies with one independent title | title_hygiene.py:466 | `all(... == DESC_POSITION ...)` -> `any(...)` | test_stage_gather::test_one_independent_title_keeps_low_confidence | CAUGHT | none |
| r | replay relaxation unconditional | replay.py:333 | `if (stored.structure is not None` -> `if (False and stored.structure is not None` | test_replay::test_stored_llm_not_self_filled_stays_needs_llm | CAUGHT | test_stored_llm_alignment_is_needs_llm, test_stored_llm_deterministic_candidate_stays_needs_llm, test_stored_llm_anchored_candidate_stays_needs_llm, test_cross_check_failure_keeps_stored_llm_needs_llm, test_track_title_veto_keeps_stored_llm_needs_llm |
| s | `desc-position` not tautological | structure.py:1154 | drop `"desc-position"` from `TAUTOLOGICAL_TITLE_SOURCES` | test_structure::test_desc_position_is_tautological | CAUGHT | none |
| t | disc index where set index applies | title_hygiene.py:301 | `if all(b == "set" for b in kept) and ...:` -> `if False:` | test_title_hygiene::test_set_headers_use_set_index | CAUGHT | none |
| u | agreement floor `<=` | title_hygiene.py:428 | `ag[0] < AGREEMENT_FLOOR` -> `ag[0] <= AGREEMENT_FLOOR` | test_title_hygiene::test_agreement_exactly_at_floor_passes | **SURVIVED** | none (also all 3051 tests in packages/llama/tests green) |
| v | `Filler:` entry shipped | title_hygiene.py:108 | `if c.filler_marked:` -> `if False:` | test_title_hygiene::test_filler_marked_entry_is_never_filled | CAUGHT | test_filler_entry_is_per_track, test_donor_not_called_without_candidates |
| w | tolerance without the 10% | title_hygiene.py:212 | `max(TOL_SEC, TOL_FRAC * w)` -> `TOL_SEC` | test_title_hygiene::test_written_tolerance_scales_with_length | CAUGHT | none |
| x | contiguity check removed | desc_list.py:240 | `if not ok:` -> `if False:` | test_desc_list::test_gaps_are_inadmissible | CAUGHT | test_numbering_continuing_across_a_header_is_one_list_two_blocks, test_restart_after_encore_line |
| y | reader (ii) accepts a 2-item line | desc_list.py:353 | `if c == 1 or k in exempt:` -> `if c in (1, 2) or ...` | test_desc_list::test_a_line_split_into_two_items_is_inadmissible | CAUGHT | test_removed_indices_exempt_their_lines, test_banner_and_noise_lines_are_exempt |
| zD | D writes a non-`unresolved` position | title_hygiene.py:439 (apply_d) | drop `and out[pos].title_source == "unresolved"` | test_title_hygiene::test_d_fills_unresolved_and_never_touches_resolved | **SURVIVED** | none |
| zS4 | slice 4 writes a non-`unresolved` position | title_hygiene.py:640 | `if t.title_source != "unresolved" or i in demoted:` -> `if i in demoted:` | test_title_hygiene::test_fills_only_unresolved_and_never_demoted | CAUGHT | none |
| zS | deferred S writes a non-`unresolved` position | title_hygiene.py:604 | drop `tracks[p].title_source == "unresolved"` from `open_` | test_title_hygiene::test_deferred_s_fills_only_unresolved | CAUGHT | test_deferred_s_rechecks_against_current_tracks |
| aa | `judge` compares a bare number with the 0-based position | title_hygiene.py:117 | `int(digits) == track_no` -> `int(digits) == track_no - 1` | test_title_hygiene::test_bare_number_rules | CAUGHT | test_bare_number_list_equal_to_track_numbers_declines_every_position |

## Survivors (findings, not fixed here)

- **(u) agreement floor.** `test_agreement_exactly_at_floor_passes` never reaches the comparison it names: it computes `agreement_share(...) == 0.5` and asserts `not share < AGREEMENT_FLOOR`, a tautology on the constant, without going through `decide_d`. The `<` at title_hygiene.py:428 is therefore unpinned (the whole `packages/llama/tests` tree stays green under `<=`). Owner: Task 6 (D decision). Needs a `decide_d` case with share exactly 0.5 that must pass.
- **(zD) `apply_d`'s unresolved-only guard.** `test_d_fills_unresolved_and_never_touches_resolved` builds the decision with `decide_d`, which only fills `unresolved` positions, so `apply_d`'s own guard is never exercised. Needs a hand-built `DDecision` with a fill at a resolved position. It may be defence in depth only, since `decide_d` already restricts fills; the orchestrator decides whether it is an equivalent mutant on the gather path or a missing pin. Owner: Task 6.
- **Resolution (174995e).** Both survivors killed by 174995e: (u) by `test_decide_d_agreement_exactly_at_floor_passes`, (zD) by `test_apply_d_guard_skips_a_resolved_position`, each 1 failed / 90 passed under its mutant. The tautological `test_agreement_exactly_at_floor_passes` was folded into the former and deleted (fix wave after Checkpoint B).
