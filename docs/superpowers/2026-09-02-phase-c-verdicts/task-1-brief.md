### Task 1: `filter_files` duplicate-listing dedupe

**Files:** modify `packages/llama/src/llama/junk.py`, `packages/llama/tests/test_junk.py`; create `scripts/dedupe_sweep.py`.

**Design notes:** Some archive.org items list every track twice — once at top level, once under an `<identifier>/` directory prefix — identical durations, tags on only one copy (ymsb2005's donor: 56 files for 28 tracks). Collapse inside `filter_files`, after `_keep_and_exclude` for the winning format: key = (basename, `round(duration or 0)`), keep the first copy unless a later duplicate carries a title the kept one lacks (then swap), excluded reason `duplicate-listing`. Play-order derivation runs on the deduped list. This is a behaviour change for every consumer, which is why the sweep gates it and it lands before the rung.

- [ ] **Step 1: failing tests.** In `test_junk.py`: an item listing `d1t01.mp3` at top level (untitled) and `ident/d1t01.mp3` (titled `Alpha`, same length) keeps **one** file and `clean_tag_titles` on the kept set yields `["Alpha"]` (content: the *titled* copy survives, asserted by title string, not by count); the dropped copy appears in `excluded` with reason `duplicate-listing`; two files sharing a basename but with lengths 180 vs 420 are **both** kept (different tracks, not duplicates); a clean item is byte-identical through `filter_files`.
- [ ] **Step 2:** run them, verify they fail on current behaviour (both copies kept).
- [ ] **Step 3:** implement; full suite green.
- [ ] **Step 4: the sweep.** `scripts/dedupe_sweep.py`: walk `~/.llama/cache/md_*.json`, run old and new `filter_files` per item/format, print every item whose kept set changes (identifier, before/after counts, the dropped names). Run it; commit the script; paste the summary into the commit message.

**Acceptance (content/mutation):**
- Sweep output enumerated; **every** changed item is a same-basename/same-duration collapse (spot-check ≥10 by hand, recorded in the PR/commit text); **no library show's kept set changes** except the known duplicate-listing items, named.
- Named mutation: invert the tagged-copy preference (keep the untitled copy). The Step-1 title-content test must fail on `["Alpha"]` vs `[""]` — a count-based test would stay green, which is why the assertion is on the string.

