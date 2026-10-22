# Taper set/encore markers: mutation record (Task 8)

Spec: `docs/superpowers/specs/2026-10-22-taper-set-markers-design.md`, Measurement 6.
Plan: Task 8. Orchestrator ruling R14 added mutants (q) to (y) and the Step A killing tests.
Orchestrator ruling R16 (fix round 1, after review t8-rev) added mutants o2 and o3, the
header-side pin for (o), and the corrections below.

**Result: 32 mutants, 32 caught, 0 survived, 0 hangs.** That is 30 in the first run, plus
o2 and o3 in fix round 1, where (o) was also re-run. Every mutant turned its predicted test
red. Thirteen mutants also turned other tests red:
- undeclared beforehand: a, b, c1, c2, d, d2, e;
- declared beforehand as possible collateral: i, j1, j2, l, m, n.

Each of those extra failures was read, and each one fails because of the mutated rule's own
behaviour. None fails for an unrelated reason (see "Extra reds" below).

In review, t8-rev found o2 and o3 SURVIVING on the first run's tests, and found (o)'s
header-side effect unpinned. Both are now pinned (fix round 1); see "Fix round 1".

## Method

- **Code under test:** `git archive c26fd59` (Task 8 Step A on top of `a892b7a`), extracted
  into a scratch directory outside the worktree. Each mutant gets its own fresh copy.
- **Diff check:** each mutant is exactly one changed line. The runner asserts that the old
  text occurs exactly once and that the unified diff has a single hunk, one `-` line and one
  `+` line.
- **How tests run:** `<worktree>/.venv/bin/python -m pytest -q -p no:cacheprovider`, started
  from an empty scratch cwd, with:
  - `PYTHONPATH=<copy>/packages/llama/src:<copy>/packages/herder/src`;
  - a fresh `PYTHONPYCACHEPREFIX` per mutant;
  - a 600 s timeout.
- **Import check:** before every mutant's test run, the runner asserts that `llama`,
  `llama.taper`, `llama.stages.gather`, `llama.replay` and `herder` all import from that
  mutant's copy.
- **Test files (760 tests):** `packages/llama/tests/test_taper.py`, `test_stage_gather.py`,
  `test_replay.py`, `test_reapply.py`, `scripts/test_replay_holds.py`,
  `scripts/test_taper_probe.py`.
- **Predictions first:** every prediction was written to the run log before any mutant was
  flipped. Each prediction is a core set of tests that must go red, plus a declared list of
  possible collateral.
- **Hangs and aborts:** none. Every run finished, and every run's passed + failed count is
  760. So no mutant hung, and none aborted the session (which would show up as a short
  count).

**The copy is really what runs (planted sentinels, same harness).** In each sentinel run, all
the red tests are in the predicted files. The files no sentinel was planted for stay green.

| sentinel | planted at | red |
|---|---|---|
| S0 | none (unmutated copy) | 0 of 760 |
| S1 | `raise` at the top of `decide_taper` | 396: gather 156, taper 73, reapply 62, replay_holds 61, replay 43, taper_probe 1 |
| S2 | `raise` in `demote_jerrybase_flags` | 15, all in test_stage_gather.py |
| S3 | `raise` before `compute_legs`' needs-LLM check | 107: reapply 46, replay_holds 35, replay 26 |

**How verdicts are scored:**
- **CAUGHT-AS-PREDICTED:** the red set is exactly the core prediction.
- **CAUGHT (+n undeclared, read)** or **CAUGHT (+n declared, read):** every core-predicted test
  is red, and the red set is a strict superset of the prediction. Each of the n extra reds was
  read and fails because of the mutated rule's own behaviour. "Declared" means it was named
  beforehand as possible collateral.
- **SURPRISE-CATCH:** a core-predicted test stayed green, or a red test fails for an unrelated
  reason.
- **SURVIVED:** nothing went red.
- **HANG:** the run timed out.

After scoring, every mutant was re-run on just the files that had failures. The failure counts
reproduced, and every failure was an assertion. The one exception is (c1); see below.

**Where the brief's test names were corrected.** These corrections were recorded before
flipping:
- The brief names `test_unrecognised_forms_are_not_markers` for (l), (m) and (o). No test has
  that name. The forms are pinned by `test_title_lookalikes_are_not_markers`, the
  `n_colon`/`dso_bare_digit` tests and `test_set_like_negatives`.
- For (d), the brief names `test_void_rules`. The skipped-set case lives in its parametrized
  sibling, `test_void_rules_synthetic`.

## Mutants

All paths are under `packages/llama/src/llama/`. Test ids are shortened (`[...]` stands for a
parametrized id).

| id | mutation | file:line | predicted (core) | observed red | verdict |
|---|---|---|---|---|---|
| a | placement accepts a non-filler track between a and b: `if not is_filler(t.title) or not _counts(t):` → `if not _counts(t):` | taper.py:715 | `test_non_filler_between_is_unplaced` | that test, plus `test_every_boundary_must_place`, `test_real_case_declines` (not declared) | CAUGHT (+2 undeclared, read) |
| b | placement accepts a non-unique match: `if len(a_hits) != 1:` → `if not a_hits:` | taper.py:684 | `test_missing_or_ambiguous_match_is_unplaced` | that test, plus `test_real_case_declines` (not declared) | CAUGHT (+1 undeclared, read) |
| c1 | repeated-title check removed, a side: `if any(... a_all ... right_norms):` → `if False:` | taper.py:703 | `test_repeated_title_across_boundary_is_unplaced` | that test, plus gather `test_not_owned_is_exactly_today` (not declared) | CAUGHT (+1 undeclared, read) |
| c2 | repeated-title check removed, b side: `if any(... b_all ... left_norms):` → `if False:` | taper.py:705 | `test_repeated_title_across_boundary_is_unplaced` | that test, plus `test_comma_part_counts_for_the_other_side_check` (not declared) | CAUGHT (+1 undeclared, read) |
| d | set-number rule accepts a skip mid-sequence: `elif number > s.current + 1:` → `elif False:` | taper.py:541 | `test_void_rules_synthetic[Set 1 / Set 3 - skipped]` | that test, plus `test_decide_taper_reports_source_and_reader_reason` (not declared) | CAUGHT (+1 undeclared, read) |
| d2 | (extra) set-number rule accepts a skip at the first header: `s.set_void("skipped set number")` → `pass` | taper.py:532 | `test_void_rules_synthetic[Set 2 / Set 1 - skipped]` | that test, plus `test_leading_block_is_set_one_only_before_set_two` (not declared) | CAUGHT (+1 undeclared, read) |
| e | numbered marker after the encore is ignored: `s.set_void("numbered marker after the encore")` → `pass` | taper.py:514 | `test_void_rules`, `test_void_rules_synthetic[... numbered marker after the encore]` | those, plus `test_set_and_encore_disc_line_asserts_nothing` (not declared) | CAUGHT (+1 undeclared, read) |
| f | cross-check removed: `reason = f"cross-check: ..." if missing else None` → `reason = None` | taper.py:591 | `test_cross_check_against_parse_setlist`, `test_set_i_prose_is_not_a_marker`, replay `test_cross_check_failure_keeps_stored_llm_needs_llm` | exactly those 3 | CAUGHT-AS-PREDICTED |
| g | `decide_taper`'s encore-like veto removed: `if taper.encore_like:` → `if False:` | taper.py:772 | `test_encore_like_text_anywhere_vetoes[*]` (3), `test_veto_gap_real_cases_are_not_owned[*]` (7), `test_encore_like_veto_reason_wins_over_set_like` | exactly those 11 | CAUGHT-AS-PREDICTED |
| h | `decide_taper`'s track-title veto removed: `if any(_ENCORE_MARKER.search(...)):` → `if False:` | taper.py:770 | `test_track_title_encore_vetoes`, gather `test_track_title_veto_is_exactly_today`, replay `test_track_title_veto_keeps_stored_llm_needs_llm` | exactly those 3 | CAUGHT-AS-PREDICTED |
| i | relaxation keys on "no LLM needed" instead of ownership: `and not gathered.taper_owned):` → `and not (not gathered.needs_llm)):` | replay.py:331 | replay `test_stored_llm_deterministic_candidate_stays_needs_llm`, `..._anchored_candidate_stays_needs_llm`, `test_track_title_veto_keeps_stored_llm_needs_llm` | those, plus `test_stored_llm_alignment_is_needs_llm` and reapply `test_reapply_writes_nothing_on_a_needs_llm_show` (both declared) | CAUGHT (+2 declared, read) |
| j1 | relaxation removed: `and not gathered.taper_owned):` → `and True):` | replay.py:331 | replay `test_stored_llm_taper_owned_is_replayable` | that test, plus reapply `test_reapply_processes_a_taper_owned_stored_llm_show` (declared) | CAUGHT (+1 declared, read) |
| j2 | relaxation unconditional: `and not gathered.taper_owned):` → `and False):` | replay.py:331 | replay `test_stored_llm_alignment_is_needs_llm` plus the four stays/keeps tests | those 5, plus reapply `test_reapply_writes_nothing_on_a_needs_llm_show` (declared) | CAUGHT (+1 declared, read) |
| k | closer demotion ignores the taper's text agreement: `if agrees:` → `if False:` | stages/gather.py:124 | `test_closer_flag_stays_hard_when_taper_text_agrees`, `test_closer_agreement_uses_fuzzy_song_matching[*]` (3), `test_duplicate_closer_flags_consume_sets_in_order` | exactly those 5 | CAUGHT-AS-PREDICTED |
| l | an `E.` form recognised as an encore marker: `_E_HEADER` tail `(?::\|[-–—]+...)` → `(?::\|\.\|[-–—]+...)` | taper.py:223 | `test_title_lookalikes_are_not_markers[E.Ville]`, `[E. Rutherford, NJ]`, `[E.]`, `test_encore_like_text_anywhere_vetoes[... E. Box Of Rain]` | those 4, plus `test_encore_like_flag_real_case` (declared as a real-case fixture with a line starting `E.`) | CAUGHT (+1 declared, read) |
| m | a bare `1:` recognised as a set header: `_SET_TOKEN`'s `set\s*` → `(?:set\s*\|(?=[123]:))` | taper.py:165 | `test_n_colon_tracklists_are_not_markers[*]` (10), `test_signalpath_n_colon_is_not_a_marker`, `test_dso_bare_digit_disc_lines_are_not_markers[*]` (3), `test_dso_bare_digit_lines_with_worded_set_two` | those 15, plus `test_leading_timestamp_and_disc_number_items_dropped` and `test_set_like_real_cases_are_not_owned[ryanadams-2008-01-21]` (both declared as fixtures with a `1:`/`2:`/`3:` line) | CAUGHT (+2 declared, read) |
| n | jerrybase anchoring applied after the taper step on an owned show: `shipped_sets = list(decision.placement.sets)` → `list(anchored) if anchored is not None else ...` | stages/gather.py:1400 | `test_taper_beats_jerrybase_anchoring` | that test, plus `test_set_count_note_excludes_the_taper_encore`, `test_set_count_disagreement_is_a_note_when_taper_text_disagrees`, `test_closer_flag_is_a_note_when_taper_text_names_another_closer` (all declared) | CAUGHT (+3 declared, read) |
| o | word boundary dropped from the `Set 1-3 / one-three / I-III` token: `(?!\w)` removed after `(?P<tok>...)` | taper.py:165 | first run: `test_set_like_negatives[Set In Stone]`, with `test_set_intro_is_not_set_one_and_set_iv_voids` predicted GREEN. Fix-round re-run: that test, plus `test_token_glued_to_cont_or_disc_is_a_song_title[*]` (5) | first run: exactly `[Set In Stone]`. Re-run: exactly the predicted 6 | CAUGHT-AS-PREDICTED |
| o2 | (fix round 1) word boundary dropped after the ordinal token: `(?P<ord>first\|second\|third)\s+set(?!\w)` → `...\s+set` | taper.py:166 | `test_set_like_negatives[songs from the first setlist]`, `[Second Settlement]` | first run: 0 red (SURVIVED, found by t8-rev). Re-run: exactly the predicted 2 | CAUGHT-AS-PREDICTED |
| o3 | (fix round 1) word boundary dropped after the numeric-ordinal token: `(?P<ordn>1st\|2nd\|3rd)\s+set(?!\w)` → `...\s+set` | taper.py:167 | `test_set_like_negatives[2nd settle]`, `[1st Setting Sun]` | first run: 0 red (SURVIVED, found by t8-rev). Re-run: exactly the predicted 2 | CAUGHT-AS-PREDICTED |
| p | merged-track-across-boundary rule removed: `if on_left and on_right:` → `if False:` | taper.py:712 | `test_merged_track_spanning_the_boundary_is_unplaced` | exactly that | CAUGHT-AS-PREDICTED |
| q | set-like veto removed: `if taper.set_like:` → `if False:` | taper.py:774 | `test_set_like_real_cases_are_not_owned[*]` (6), `test_set_like_tokens_in_a_numbered_set_item[*]` (11), `..._veto_applies_with_a_marked_encore`, `test_split_ordinal_header_is_set_like`, `test_bare_set_item_real_case_is_not_owned`, `test_set_like_token_in_a_set_three_item` | exactly those 21 | CAUGHT-AS-PREDICTED |
| r | bare-`Set` item rule removed: `if item.title.strip(_ITEM_DECOR).lower() == "set":` → `if False:` | taper.py:557 | `test_split_ordinal_header_is_set_like`, `test_bare_set_item_is_set_like[*]` (4), `test_bare_set_item_real_case_is_not_owned` | exactly those 6 | CAUGHT-AS-PREDICTED |
| s | con't exemption dropped: `if str(number) == item.set and _CONT_AFTER.match(...):` → `if False:` | taper.py:562 | `test_set_like_negatives[Set 2 con't]`, `[Set II (con't.)]`, `[Set 2(con't)-]`, `[Set 2 (con’t):]` | exactly those 4 | CAUGHT-AS-PREDICTED |
| t | Task 5 M5, the encore counted in the taper's set count: `taper_n = len({... if i.set != "encore"})` → `len({i.set for i in taper.items})` | stages/gather.py:105 | `test_set_count_note_excludes_the_taper_encore` | exactly that | CAUGHT-AS-PREDICTED |
| u | Task 5 M6, raw string equality: `agrees = bool(songs) and fuzzy_title_eq(...,` → `agrees = bool(songs) and songs[-1] == st.closer and (songs[-1],` | stages/gather.py:122 | `test_closer_agreement_uses_fuzzy_song_matching[*]` (3) | exactly those 3 | CAUGHT-AS-PREDICTED |
| v | Task 5 M2, the closer compared with the last song of any taper set: `songs = [... if i.set == st.name]` → `sorted({j.set: j.title ...}.values(), key=<matches closer>)` | stages/gather.py:121 | `test_closer_maps_to_the_taper_set_of_the_same_number`, `test_duplicate_closer_flags_consume_sets_in_order` | exactly those 2 | CAUGHT-AS-PREDICTED |
| w | Task 5 M3, duplicate closers not consumed in order: `if n not in used and m is not None ...` → `if m is not None ...` | stages/gather.py:115 | `test_duplicate_closer_flags_consume_sets_in_order` | exactly that | CAUGHT-AS-PREDICTED |
| x | Task 4 M4, the filler exclusion in the "labels differ" check: `if not is_filler(t.title)):` → `if True):` | stages/gather.py:1405 | `test_filler_only_label_difference_keeps_step_one_alignment` | exactly that | CAUGHT-AS-PREDICTED |
| y1 | owned low-confidence flag, `canonical.items and` dropped | stages/gather.py:1397 | `test_owned_low_confidence_needs_canonical_items` | exactly that | CAUGHT-AS-PREDICTED |
| y2 | owned low-confidence flag, `anchored is None and` dropped | stages/gather.py:1397 | `test_owned_low_confidence_needs_no_anchoring` | exactly that | CAUGHT-AS-PREDICTED |
| y3 | owned low-confidence flag, `and result.coverage < threshold` dropped | stages/gather.py:1397 | `test_owned_low_confidence_needs_weak_step_one` | exactly that | CAUGHT-AS-PREDICTED |

Mutant (t) and mutants (u) to (x) are killed only by the Step A tests (commit `c26fd59`). The
Task 4 and Task 5 reviews had found them surviving.

## Extra reds (read, not assumed)

Each extra red was re-run on the mutant and its assertion read. Each one fails because of the
mutated rule's own behaviour.

**Not declared beforehand:**
- **(a)** `test_every_boundary_must_place`: a placement now succeeds across a non-filler track.
  `test_real_case_declines`: a real show places that should decline.
- **(b)** `test_real_case_declines`: the ambiguous `'NFA'` match passes the uniqueness check.
  The show then declines later, for a different reason, so the test's `'NFA'` reason is gone.
- **(c1)** gather `test_not_owned_is_exactly_today`: its text lists `Charlie` on both sides, so
  the show is now owned. The test's `res.taper.reason.startswith(...)` then raises
  `AttributeError` on the `None` reason. This is the one red that is not an `AssertionError`,
  and it is still this rule's behaviour.
- **(c2)** `test_comma_part_counts_for_the_other_side_check`: the b-side half of the same check
  (comma parts) now places.
- **(d)** `test_decide_taper_reports_source_and_reader_reason`: its `Set 1 / Set 3` text no
  longer voids, so the reason becomes `unplaced:` instead of `void:`.
- **(d2)** `test_leading_block_is_set_one_only_before_set_two`: a first marker of `Set 2` with
  no leading block now asserts.
- **(e)** `test_set_and_encore_disc_line_asserts_nothing`: its later numbered marker no longer
  voids, so the reason becomes `one set`.

**Declared beforehand as possible collateral:**
- **(i), (j1), (j2):** the reapply and replay needs-LLM tests.
- **(l):** a real-case fixture with an `E.` line.
- **(m):** fixtures with `1:`/`2:`/`3:` lines.
- **(n):** the Task 5 jerrybase-enabled gather tests, on which anchoring differs from the
  taper.

## Observations

- **(o): the word boundary is load-bearing in the header reader too.** This corrects the
  first version of this record, which called it redundant there.
  - Not every header needs a separator right after the token: `_CONT` and the disc label in
    `_SET_DISC_HEADER` may follow it directly.
  - Without the boundary:
    - `Set2cont`, `Set 2cont:` and `Set IIcont` become continuation headers;
    - `Set 1CD1` and `Set 1Disc 1` become set-1 headers that void (`decreasing set
      number`).
  - Today all five are set-2 song titles. `test_token_glued_to_cont_or_disc_is_a_song_title`
    pins that (fix round 1).
  - What the first version did get right: `Set Intro` stays a (filler) song without the
    boundary. `test_set_intro_is_not_set_one_and_set_iv_voids` stays green under (o), as
    predicted.
  - The boundary is also load-bearing in `_SET_LIKE`, which reuses `_SET_TOKEN`; there,
    `[Set In Stone]` pins it.
- **The ordinal tokens' boundaries (o2, o3) are load-bearing through `_SET_LIKE`.** Without
  them, `songs from the first setlist`, `Second Settlement`, `2nd settle` and
  `1st Setting Sun` become set-like and fire the set-like veto. That only costs yield; it
  never ships a wrong structure. They survived the first run, and now four
  `test_set_like_negatives` params pin them.
- **The `_CONT` comment (taper.py:170) is corrected.** It used to list `Set2cont` as a
  recognised continuation form, but the boundary stops it being read as one. This was a
  comment-only change, behaviour unchanged.
- **Extra mutants:** (c) was split into two one-line mutants, one per side of the
  repeated-title check. (d2) was added for the first-header half of the set-number rule. Both
  were caught.

## Fix round 1 (R16)

**Setup.** The base was `git archive 6bddf0d`, plus the fix round's `taper.py` (comment only)
and `test_taper.py`. Everything else was the same instrument as the first run:
- each mutant ran in its own fresh copy, from an empty cwd, under `PYTHONPATH` shadowing;
- each run had its own `PYTHONPYCACHEPREFIX` and a 600 s timeout;
- imports were asserted to come from the copy;
- each mutant was checked to be a one-line diff;
- predictions were logged before the run.

**Results.** 769 tests in total: the 760 from before, plus 4 new negatives and the 5-param
glued-token test.

| run | red |
|---|---|
| S0 (unmutated) | 0 / 769 |
| S1 sentinel (`raise` in place of `_set_like`'s final `return False`) | 595 / 769: taper 262, gather 164, reapply 62, replay_holds 61, replay 43, taper_probe 3 |
| o | exactly the predicted 6 |
| o2 | exactly the predicted 2 |
| o3 | exactly the predicted 2 |

S1 was predicted as "most of test_taper.py red". It went wider, because every `compute_gather`
call reads the taper text. That is consistent with a sentinel and proves the copy is what runs.
