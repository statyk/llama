# Task 1 fix round 1 (t1-fix1)

**Status:** DONE
**Commit:** `7b8a30e` fix(junk): derive the short rule's interior test over one copy per listing
**Full suite:** `./.venv/bin/python -m pytest -q` -> `4848 passed, 1 skipped, 8 deselected, 26 warnings in 76.75s` (4844 before, plus 4 new tests)

## The finding
Review Important 1: the interior test ran over pre-dedupe listings. On an item listed twice, an untagged short file at a tape edge was kept.

## What changed (`packages/llama/src/llama/junk.py`)
- **New `_listing_key(f)`.** It returns `(basename, round(length_seconds(length) or 0))`. That is the key `_dedupe_duplicate_listings` computes inline, computed the same way. `_dedupe_duplicate_listings` itself is unchanged: its source is byte-identical to e37f670's, checked by diff.
- **The pool is collapsed before the interior test.** In `_apply_short_rule`:
  - the play-order pool (kept + tagged keeps + untagged candidates) is sorted by name, which is the order filter_files hands to dedupe;
  - it is passed through the unchanged `_dedupe_duplicate_listings`, leaving one copy per listing.
- **Both tests run on the collapsed pool:**
  - the "track numbers complete and unique" test runs over the survivors;
  - the order is track-tag order when that test passes, else the deduped filename order;
  - the neighbour test compares each file's listing position (looked up by `_listing_key`) against the positions of the kept and tagged-kept listings.
- **Unchanged:** the rule still lives inside `_keep_and_exclude` (spec 2.5), and nothing else changed. The comment block records why the dedupe is load-bearing.

## Covering tests (added to `packages/llama/tests/test_short_keep_rule.py`)
- `test_doubled_listing_untagged_short_edge_file_drops[first]` and `[last]`:
  - setup: a 7-track tape listed at top level and under `band99/`, every copy carrying its track tag, with an untagged 30 s t01 (or t07);
  - expected: both copies are excluded with `implausibly short` and `short_kept == []`;
  - kept basenames equal the single listing's.
- `test_doubled_listing_untagged_short_interior_file_is_kept`: an untagged 30 s t04 on the doubled item is kept, with `short_kept == ["band1t04.mp3"]`. The prefixed copy is a `duplicate-listing` drop.
- `test_doubled_listing_order_follows_unique_tags_after_dedupe`: one copy per listing has unique track tags, so the interior test follows them. The untagged short file is last by filename and track 4 by tag, and it is kept with `order_source == "track-tags"`.

## Evidence
- **RED** (new tests against HEAD fdd7f1d's junk.py, scratch copy via `git archive`, PYTHONPATH-shadowed; `llama.junk.__file__` resolved inside the copy):
  - command: `python -m pytest -q tests/test_short_keep_rule.py -k doubled`
  - output: `FAILED ...edge_file_drops[first]`, `FAILED ...edge_file_drops[last]`, then `2 failed, 2 passed`.
  - The two passing tests are the interior and unique-tags cases, which the old code also got right.
- **GREEN:** `./.venv/bin/python -m pytest -q -p no:cacheprovider packages/llama/tests/test_short_keep_rule.py` -> `58 passed in 0.35s`.
- **Full suite:** `./.venv/bin/python -m pytest -q -p no:cacheprovider` -> `4848 passed, 1 skipped, 8 deselected, 26 warnings in 76.75s (0:01:16)`. No existing test changed.

## Concerns
None. The deferred minors were not touched, as instructed.
