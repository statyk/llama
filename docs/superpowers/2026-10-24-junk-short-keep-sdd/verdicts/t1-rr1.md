### Finding Verdicts
- **Important 1: the interior test ran over pre-dedupe listings, so an untagged short edge file was kept on a duplicate-listed item.** ADDRESSED.
  - The fix is at `packages/llama/src/llama/junk.py:244-258`. The pool (kept + tagged keeps + untagged candidates) is sorted by name and passed through the unchanged `_dedupe_duplicate_listings`.
  - Both tests now run on the collapsed `listings`, per the orchestrator ruling. The "complete and unique" test is at `:247-248`. The neighbour test (`:252-258`) looks up each file's listing position by `_listing_key`.
  - The rule is still called from inside `_keep_and_exclude` (`:335`).
  - `_dedupe_duplicate_listings` is byte-identical to e37f670's. I checked this by diffing the function body extracted from both revisions: no output.
  - The name sort matches what dedupe receives in `filter_files`. `_keep_and_exclude` returns `kept` name-sorted (`:338`), and `filter_files` hands that to dedupe (`:439`). So the order of first appearance of each listing key, which sets filename-order positions, is the same in both places.
  - `_listing_key` (`:192-196`) uses the same expression dedupe computes inline (`:358`), so every pool file maps to a key in `pos`.
  - A candidate whose own copy is the one dedupe drops is judged by its listing's position, not its own copy's. Every copy of a listing gets the same verdict, and the final dedupe keeps one. `short_kept` is cut down to the surviving copy (`:472`), which `test_doubled_listing_untagged_short_interior_file_is_kept` pins.
  - Tests: the new `edge_file_drops[first]` and `[last]` cover the reported defect. The implementer's report shows them RED at fdd7f1d. I confirmed the old code's index arithmetic: the prefixed t01 sat at index 7, inside base span 1..13.
  - `test_doubled_listing_order_follows_unique_tags_after_dedupe` covers the ruling's other half. In a scratch copy, I ran the uniqueness test over the uncollapsed pool while still ordering the collapsed listings. I predicted this test would go red, and only it did: `1 failed, 3 passed` (the short_kept assertion, test file line 364). Restored, the scratch copy gives `58 passed`.
  - The report names its covering tests and shows their output: 58 passed in the file, full suite 4848 passed.

### New Breakage in the Fix Diff
- None at Critical or Important.
- Minor, theoretical (`junk.py:246`): dedupe can pick a different winning copy for a listing in the pool than in the final kept set. The trigger is narrow:
  - an untagged short candidate and a non-short base copy share a key (basename plus rounded duration; possible only when the floor falls between two durations that round to the same second);
  - the candidate comes first by name;
  - neither copy has a title.

  The pool then keeps the candidate's copy, and its track tag feeds the uniqueness test. The final set may keep the other copy. The worst case is a track-tag versus filename order mismatch in the interior test on an exotic item. It does not reach the reported defect class, and I would not block on it.
- Minor (test file): `_doubled`'s `prefix` parameter is never passed a non-default value. The case where the prefix sorts before the top level (for example `aaa/`) is not exercised. I traced it by reading: the order of first appearance in name order is then the prefixed block, whose basenames come in the same order, so positions are unchanged.

### Out-of-Scope Observations
- Not touched by the fix: untagged candidates the rule then rejects are still in the pool for the "complete and unique" test. One candidate without a track tag forces filename order for the interior test, even when the final kept set would be in track-tag order. This predates the fix.
- `_listing_key` copies dedupe's key logic because the function must stay byte-identical. That is a drift risk if dedupe's key ever changes; its docstring records the coupling.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
