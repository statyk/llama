### Task 2: numeric-title census, then the scoped `is_real_title` fix

**Files:** create `scripts/numeric_title_census.py`; modify `packages/llama/src/llama/titles.py`, `packages/llama/tests/test_titles.py`.

**Decision point, named:** the census output decides scope — **global** (`is_real_title` itself accepts an all-digit 4-char title) versus **hygiene-only** (only the sibling/setlist-gap adoption check accepts it; the tag rung unchanged). **STOP after Step 2 and report the numbers to the owner if the census finds any item where the widening would promote year-as-title junk into the tag rung** (any item with ≥2 pure-4-digit tag titles, or any hand-checked sample entry that is a date rather than a song). Zero such items → proceed global without stopping, recording the census numbers in the code comment.

- [ ] **Step 1: census.** Script walks the cache, reports: count of tag titles matching `^\d{4}$` after `clean_tag_title`, per item; distinct values; items where the change moves `title_fraction` across `gather._RECOVER_BELOW` (0.5) or to/from 1.0. Cite-style output like `title_source_census.py`.
- [ ] **Step 2:** run it; record output; apply the decision rule above.
- [ ] **Step 3: failing tests.** `is_real_title("1922") is True`, `is_real_title("2001") is True`, `is_real_title("d1t02") is False`, `is_real_title("01") is False`, `is_real_title("174") is False` (or the hygiene-scoped equivalents if the owner ruled that way). Verify the enumerated-tape gate's existing pinned tests (`test_clean_tag_titles_leaves_an_unnumbered_year_title_alone`, strip-once) still pass untouched.
- [ ] **Step 4:** implement per scope; full suite green.

**Acceptance (content/mutation):**
- Census numbers recorded in the constant's comment (house citation style: script name + date + numbers).
- Named mutation: revert the widening. `test_is_real_title_accepts_a_year_like_numeric_title` (name it exactly that) must fail. Additionally, after Task 5 lands, the TBT expectation in Task 7's six-show table (`1922` adopted) depends on this — noted there, not re-tested here.
- Composition note for the reviewer, from the spec: this erases the merged branch's single demonstrated `--suggest-titles` adoption (`1922` becomes a count-forced `setlist-gap` adoption). Expected; do not "fix".

---

# Phase 2 — the alignment module and its guards (pure)

