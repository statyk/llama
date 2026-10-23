### Finding Verdicts
- **(Important) A partly removed multi-item line was exempt in `read_parse`, so its leftover fragment entered the list** — ADDRESSED. `packages/llama/src/llama/desc_list.py:334-342` now counts removed items per line (`removed_per_line`, indexed via `line_of`, which covers both the cleaner's report and the leading-artist-drop indices merged into `removed` at :331) and exempts line k only when `c and removed_per_line[k] == c`. The ruling is met point for point: the comment at :334-337 cites spec slice 2 (ii) and names the `_strip_head_banner` mid-line case; the docstring (:308-309) says "a line ALL of whose items ... removed". In `packages/llama/tests/test_desc_list.py`, `test_removed_indices_exempt_their_lines` now asserts that `{0}`/`{0}` gives `"line yields 2 items: Fox Theatre, Boulder CO"`, that `{0,1}`/`{0,1}` is a `DescList` with raws `("Bertha","Deal","Ripple")`, and that the `frozenset()` and rewrite-only cases are unchanged. The fix report names the covering test and shows a RED run of the new test against the f172be3 code in a scratch copy (the old `DescList(raws=('Boulder CO', ...))` result), GREEN for the file (34 passed) and the full suite (4508 passed, 1 skipped). The old `raws == ("Boulder CO", ...)` assertion is gone.

### New Breakage in the Fix Diff
None. I checked:
- A c==1 line still always passes, whether its item was kept or removed.
- A c==0 line can never reach `exempt` (the `c and` guard) and falls through to the unchanged marker/`_NOISE` rule. That matches the old behaviour, since such a line owns no index in `line_of`.
- The `0 <= i < len(line_of)` guard keeps the old tolerance for out-of-range indices in a cleaner's report.
- `removed` is a set, so no item is counted twice and a per-line count cannot exceed c.

The stricter rule now also makes a two-item banner line inadmissible when only the leading-artist drop removed part of it (for example "Railroad Earth, Fox Theatre"). That follows the binding spec (ii) wording, and the report says `test_artist_item_dropped_only_in_the_banner` (the verbatim RRE description) still passes.

### Out-of-Scope Observations
- None that block. `read_parse` still checks `consistent` after the line judgement (unchanged), so a cleaner whose report disagrees with its output can still have lines judged against an untrustworthy `removed` before it returns "cleaner count disagrees". Either way the result is inadmissible, so this is harmless.

### Verdict
All findings addressed: yes
