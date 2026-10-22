import json
T = "packages/llama/src/llama/taper.py"
G = "packages/llama/src/llama/stages/gather.py"
R = "packages/llama/src/llama/replay.py"
TT = "packages/llama/tests/test_taper.py::"
TG = "packages/llama/tests/test_stage_gather.py::"
TR = "packages/llama/tests/test_replay.py::"
M = []
def add(id, file, old, new, predicted, collateral=(), note=""):
    M.append(dict(id=id, file=file, old=old, new=new, predicted=list(predicted),
                  collateral=list(collateral), note=note))

# --- brief (a)-(p)
add("a", T, "        if not is_filler(t.title) or not _counts(t):", "        if not _counts(t):",
    [TT + "test_non_filler_between_is_unplaced"])
add("b", T, "    if len(a_hits) != 1:", "    if not a_hits:",
    [TT + "test_missing_or_ambiguous_match_is_unplaced"])
add("c1", T, "    if any(fuzzy_title_eq(x, n) for x in a_all for n in right_norms):",
    "    if False:", [TT + "test_repeated_title_across_boundary_is_unplaced"],
    note="brief (c), the a-side half of the repeated-title check")
add("c2", T, "    if any(fuzzy_title_eq(x, n) for x in b_all for n in left_norms):",
    "    if False:", [TT + "test_repeated_title_across_boundary_is_unplaced"],
    note="brief (c), the b-side half of the repeated-title check")
add("d", T, "    elif number > s.current + 1:", "    elif False:",
    [TT + "test_void_rules_synthetic[Set 1:\\nBertha\\nSet 3:\\nSugaree\\n-void: skipped set number]"],
    note="brief predicted `test_void_rules`; the skip case lives in its parametrized sibling test_void_rules_synthetic")
add("d2", T, '        else:\n            s.set_void("skipped set number")', "        else:\n            pass",
    [TT + "test_void_rules_synthetic[Set 2:\\nSugaree\\nSet 1:\\nRipple\\n-void: skipped set number]"],
    note="extra: the first-header half of the set-number rule (a first marker of 2 with no leading block, or 3)")
add("e", T, '        s.set_void("numbered marker after the encore")', "        pass",
    [TT + "test_void_rules",
     TT + "test_void_rules_synthetic[Set 1:\\nBertha\\nSet 2:\\nSugaree\\nE: Ripple\\nSet 3:\\nMorning Dew\\n-void: numbered marker after the encore]"])
add("f", T, "        reason = f\"cross-check: {', '.join(missing)}\" if missing else None",
    "        reason = None",
    [TT + "test_cross_check_against_parse_setlist", TT + "test_set_i_prose_is_not_a_marker",
     TR + "test_cross_check_failure_keeps_stored_llm_needs_llm"])
add("g", T, "        if taper.encore_like:", "        if False:",
    [TT + "test_encore_like_text_anywhere_vetoes[*]", TT + "test_veto_gap_real_cases_are_not_owned[*]",
     TT + "test_encore_like_veto_reason_wins_over_set_like"])
add("h", T, "        if any(_ENCORE_MARKER.search(t.title) for t in tracks):", "        if False:",
    [TT + "test_track_title_encore_vetoes", TG + "test_track_title_veto_is_exactly_today",
     TR + "test_track_title_veto_keeps_stored_llm_needs_llm"])
add("i", R, "            and not gathered.taper_owned):", "            and not (not gathered.needs_llm)):",
    [TR + "test_stored_llm_deterministic_candidate_stays_needs_llm",
     TR + "test_stored_llm_anchored_candidate_stays_needs_llm",
     TR + "test_track_title_veto_keeps_stored_llm_needs_llm"],
    [TR + "test_stored_llm_alignment_is_needs_llm", TR + "test_cross_check_failure_keeps_stored_llm_needs_llm",
     "packages/llama/tests/test_reapply.py::* (a held show with stored llm alignment whose replay gather needs no LLM)"])
add("j1", R, "            and not gathered.taper_owned):", "            and True):",
    [TR + "test_stored_llm_taper_owned_is_replayable"],
    ["packages/llama/tests/test_reapply.py::* (an owned show with stored llm alignment)"])
add("j2", R, "            and not gathered.taper_owned):", "            and False):",
    [TR + "test_stored_llm_alignment_is_needs_llm",
     TR + "test_stored_llm_deterministic_candidate_stays_needs_llm",
     TR + "test_stored_llm_anchored_candidate_stays_needs_llm",
     TR + "test_cross_check_failure_keeps_stored_llm_needs_llm",
     TR + "test_track_title_veto_keeps_stored_llm_needs_llm"],
    ["packages/llama/tests/test_reapply.py::* (stored llm alignment expected to stay needs-llm)"])
add("k", G, "        if agrees:", "        if False:",
    [TG + "test_closer_flag_stays_hard_when_taper_text_agrees",
     TG + "test_closer_agreement_uses_fuzzy_song_matching[*]",
     TG + "test_duplicate_closer_flags_consume_sets_in_order"])
add("l", T, "    rf\"(?:{_E_DECOR}$|[~*=\\s]*(?::|[-–—]+(?=\\s|$))\\s*(?P<rest>.*)$)\",",
    "    rf\"(?:{_E_DECOR}$|[~*=\\s]*(?::|\\.|[-–—]+(?=\\s|$))\\s*(?P<rest>.*)$)\",",
    [TT + "test_title_lookalikes_are_not_markers[E.Ville-E.Ville-True]",
     TT + "test_title_lookalikes_are_not_markers[E. Rutherford, NJ-E. Rutherford-True]",
     TT + "test_title_lookalikes_are_not_markers[E.-E.-True]",
     TT + "test_encore_like_text_anywhere_vetoes[Set 1: Bertha, Let It Grow\\nSet 2: Scarlet Begonias, Truckin\\nE. Box Of Rain\\n]"],
    ["any real-case fixture with a line starting `E.` (its encore would now start there)"],
    note="brief predicted `test_unrecognised_forms_are_not_markers`, which does not exist; the E. lookalikes are pinned by test_title_lookalikes_are_not_markers")
add("m", T, '    r"(?:set\\s*(?P<tok>one|two|three|iii|ii|i|[123])(?!\\w)"',
    '    r"(?:(?:set\\s*|(?=[123]:))(?P<tok>one|two|three|iii|ii|i|[123])(?!\\w)"',
    [TT + "test_n_colon_tracklists_are_not_markers[*]", TT + "test_signalpath_n_colon_is_not_a_marker",
     TT + "test_dso_bare_digit_disc_lines_are_not_markers[*]", TT + "test_dso_bare_digit_lines_with_worded_set_two"],
    ["any fixture with a line starting `1:`/`2:`/`3:` (now a set header)",
     "any numbered-set item containing a word-bounded `[123]:` (now set-like, e.g. a time `1:08`)"],
    note="brief predicted `test_unrecognised_forms_are_not_markers`, which does not exist")
add("n", G, "            shipped_sets = list(decision.placement.sets)",
    "            shipped_sets = list(anchored) if anchored is not None else list(decision.placement.sets)",
    [TG + "test_taper_beats_jerrybase_anchoring"],
    [TG + "test_set_count_note_excludes_the_taper_encore", TG + "test_set_count_disagreement_is_a_note_when_taper_text_disagrees",
     "other Task 5 jerrybase-enabled gather tests on which anchoring succeeds with labels differing from the taper's"])
add("o", T, '    r"(?:set\\s*(?P<tok>one|two|three|iii|ii|i|[123])(?!\\w)"',
    '    r"(?:set\\s*(?P<tok>one|two|three|iii|ii|i|[123])"',
    [TT + "test_set_like_negatives[Set In Stone]"],
    ["real-case ownership tests whose numbered-set items contain `Set I...`/`Set 1x` words (now set-like)"],
    note="brief predicted `test_unrecognised_forms_are_not_markers` (does not exist) on `Set Intro` reading as set 1. Predicted instead: the header regexes need `:`/dash/decoration/line end straight after the token, so `(?!\\w)` is redundant there and `Set Intro` stays a (filler) song; the boundary is load-bearing only in `_SET_LIKE`, so test_set_intro_is_not_set_one_and_set_iv_voids is predicted GREEN")
add("p", T, "            if on_left and on_right:", "            if False:",
    [TT + "test_merged_track_spanning_the_boundary_is_unplaced"])
# --- R14 (q)-(y)
add("q", T, "    if taper.set_like:", "    if False:",
    [TT + "test_set_like_real_cases_are_not_owned[*]", TT + "test_set_like_tokens_in_a_numbered_set_item[*]",
     TT + "test_set_like_veto_applies_with_a_marked_encore", TT + "test_split_ordinal_header_is_set_like",
     TT + "test_bare_set_item_real_case_is_not_owned", TT + "test_set_like_token_in_a_set_three_item"])
add("r", T, '        if item.title.strip(_ITEM_DECOR).lower() == "set":', "        if False:",
    [TT + "test_split_ordinal_header_is_set_like", TT + "test_bare_set_item_is_set_like[*]",
     TT + "test_bare_set_item_real_case_is_not_owned"])
add("s", T, "            if str(number) == item.set and _CONT_AFTER.match(item.title[m.end():]):",
    "            if False:",
    [TT + "test_set_like_negatives[Set 2 con't]", TT + "test_set_like_negatives[Set II (con't.)]",
     TT + "test_set_like_negatives[Set 2(con't)-]", TT + "test_set_like_negatives[Set 2 (con\\u2019t):]"],
    ["real-case ownership tests whose texts carry a same-set con't item"])
add("t", G, '        taper_n = len({i.set for i in taper.items if i.set != "encore"})',
    "        taper_n = len({i.set for i in taper.items})",
    [TG + "test_set_count_note_excludes_the_taper_encore"], note="Task 5 M5")
add("u", G, "        agrees = bool(songs) and fuzzy_title_eq(fuzzy_norm_title(songs[-1], aliases),\n                                                fuzzy_norm_title(st.closer, aliases))",
    "        agrees = bool(songs) and songs[-1] == st.closer and (songs[-1],\n                                                fuzzy_norm_title(st.closer, aliases))",
    [TG + "test_closer_agreement_uses_fuzzy_song_matching[*]"], note="Task 5 M6")
add("v", G, "        songs = [i.title for i in taper.items if i.set == st.name]",
    "        songs = sorted({j.set: j.title for j in taper.items}.values(), key=lambda t: fuzzy_title_eq(fuzzy_norm_title(t, aliases), fuzzy_norm_title(st.closer, aliases)))",
    [TG + "test_closer_maps_to_the_taper_set_of_the_same_number", TG + "test_duplicate_closer_flags_consume_sets_in_order"],
    note="Task 5 M2, one-line form: songs[-1] is a set's last song matching the closer when any set's does")
add("w", G, "if n not in used and m is not None and st.closer == m.group(1)", "if m is not None and st.closer == m.group(1)",
    [TG + "test_duplicate_closer_flags_consume_sets_in_order"], note="Task 5 M3")
add("x", G, "                   if not is_filler(t.title)):", "                   if True):",
    [TG + "test_filler_only_label_difference_keeps_step_one_alignment"], note="Task 4 M4")
add("y1", G, "            if (canonical.items and anchored is None and result.coverage < threshold",
    "            if (anchored is None and result.coverage < threshold",
    [TG + "test_owned_low_confidence_needs_canonical_items"])
add("y2", G, "            if (canonical.items and anchored is None and result.coverage < threshold",
    "            if (canonical.items and result.coverage < threshold",
    [TG + "test_owned_low_confidence_needs_no_anchoring"])
add("y3", G, "            if (canonical.items and anchored is None and result.coverage < threshold",
    "            if (canonical.items and anchored is None",
    [TG + "test_owned_low_confidence_needs_weak_step_one"])
json.dump(M, open("mutants.json", "w"), indent=1, ensure_ascii=False)
print(len(M))
