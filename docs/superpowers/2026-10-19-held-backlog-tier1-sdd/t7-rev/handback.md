### Spec Compliance

- ✅ Spec compliant. All checks below are against the review diff, 528ab8f..050c84b.
  - Candidate rule: `scripts/replay_holds.py:507-519`. Remaining flags are `_all_flags`, meaning gather+vet+brief (`replay_holds.py:200-201`). The flag set must be non-empty. Each flag must be the `single-set structure for a long show` prefix, or `low-confidence setlist` (also by prefix). A `low-confidence setlist` flag counts only when the stored `structure.source == "none"` or `coverage == 0.0`. This matches the brief's Interfaces exactly.
  - Columns: `replay_holds.py:527-540`, with `NARRATION_HEAD` at 543. They are the 9 the brief lists: slug, artist, date, venue, minutes (sum of `duration_sec` / 60, 0 decimals), flags, title-source counts, untitled yes/no, and a 300-char excerpt (the existing `_excerpt` at 373-375, which is unescaped and so is not double-escaped).
  - Untitled: requires every track to be `unresolved` and needs a non-empty track list (line 531).
  - Sorting: inline JS with no CDN (545-561). The test checks it at test_replay_holds.py `test_narration_candidates_page_lists_unknowable_structure_holds` (no "http" after `<script>`).
  - Escaping: every cell, the header and the flags go through `html.escape` (567-568), tested by the `<b>Hall</b> & Co` case.
  - Root: library reads come from the arm-header `root` (`compare`, line 607) via `_read_json`/`_show_json` (350-357). Those catch OSError/ValueError and return {}, so an unreadable show.json renders "?" placeholders and the slug stays. This is tested.
  - Outputs: `narration_candidates.html` was already in `OUTPUT_FILES` (line 182), so the stale-output unlink covers it. The carried test `test_compare_writes_only_files_named_in_output_files` is present. The page is written after the 99% gate (line 635), so an exit-3 run leaves no page.
- Implementer interpretation 1 ("held" means `state == "held"`): **upheld.** `ShowReplay.state` is the stored `derive_state` (`packages/llama/src/llama/replay.py:440`), and `classify` itself splits held from non-held shows by `stored_state == "held"` (replay.py:354-361). Keying on `outcome` would mix in replay outcomes that are not about the stored hold.
- Implementer interpretation 2 (an unreadable show.json plus only `low-confidence setlist` is excluded): **acceptable.** The brief makes that flag count only on stored-structure evidence, and here there is none. compare does not abort and nothing is fabricated. The cost is that such a show is silently absent from the page (see Minor 3).
- Do-not-retune grep: none of the Global Constraints names appear in the diff. The diff touches only `scripts/`.
- ⚠️ Cannot verify from diff: nothing outstanding.

### Strengths
- The candidate predicate is small and readable, and it mirrors the brief's wording one-for-one. It reuses the existing degrade-to-{} readers and `_excerpt` instead of new IO paths.
- The tests cover the proxy's three branches (source none, coverage 0.0, neither), exclusion by another flag and by no flags, escaping, untitled, an unreadable show.json, and the OUTPUT_FILES superset.
- `OUTPUT_FILES` membership means the stale-clear and exit-3 behaviour from 528ab8f covers the new page with no extra code.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **Sorting by date or slug is wrong.** `scripts/replay_holds.py:553-555` uses `parseFloat`, which reads the leading numeric prefix: `parseFloat("1973-06-10")` is 1973 and `parseFloat("311-1995-01-01")` is 311 (checked with node).
   - Date column: sorting by date compares the year only, so shows within a year keep their previous order and are not in date order.
   - Slug column: an artist slug that starts with digits sorts numerically against `localeCompare`'d text. The comparator is then inconsistent (non-transitive), and the resulting order is undefined.
   - Date is the obvious column to sort this page by.
   - Fix: decide what counts as numeric with a whole-string test, e.g. `var nx = /^-?\d+(\.\d+)?$/.test(x.trim()) ? +x : NaN`. Also put numeric values before text consistently, so "?" minutes do not break transitivity. ISO dates then sort correctly through `localeCompare`.

#### Minor (Nice to Have)
1. **No test of the state filter.** `test_replay_holds.py`: no test has a non-held show carrying only the single-set flag. The brief test's 06-11 exclusion holds through the empty-flags check, not the state check (06-11 is `clean` with no flags). Deleting `if r.get("state") != "held": return False` (replay_holds.py:508-509) would survive. Fix: add one case that gives 06-11 `gather_flags=[SINGLE]`, which is `newly-held`, and asserts it is absent.
2. **Each candidate's show.json is read 3 times.** This happens in `_narration_page` → `_is_candidate` (line 564), `_narration_row` (528) and `_excerpt` → `_description` (360). It is harmless at around 1k shows. Passing the dict through would also remove the theoretical skew of reading a file mid-change.
3. **A missing duration counts as 0, and excluded rows leave no trace.**
   - Missing durations: `float(t.get('duration_sec') or 0)` (line 532) silently under-reports minutes. A "?" or a marker would be more honest.
   - Excluded rows: a show excluded because its show.json is unreadable leaves no trace. A one-line count in the `<h1>` or a footnote would help.
4. **Small tidy-ups:**
   - `NARRATION_FLAGS[1]` is never used. Line 515 hardcodes `"low-confidence setlist"` and line 518 indexes `[0]`, so either use both entries or replace the tuple with two named constants.
   - `str(t.get("title_source"))` renders a missing key as `None:`.
   - The test helper `_hold_with` has an unused `gather_only` parameter (test_replay_holds.py:542).

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The candidate rule, columns, escaping, read-only degradation and the OUTPUT_FILES contract are all correct and tested. The page's sort is wrong for the date and digit-led slug columns, a one-line JS fix (Important 1). The missing state-filter test (Minor 1) is cheap to add in the same pass.
