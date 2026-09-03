### Task 5: gather — replace the sibling rung with the guarded transfer pass

**Files:** modify `packages/llama/src/llama/stages/gather.py`, `packages/llama/src/llama/titles.py`, `packages/llama/src/llama/models.py`, `packages/llama/tests/test_stage_gather.py`, `packages/llama/tests/test_titles.py`.

**Design notes:**
- Delete `_sibling_titles` and `resolve_titles`' `sibling_titles` parameter + `elif` rung (update `test_titles.py` accordingly: the old rung's tests are replaced, not weakened — the replacement pins that a count-equal fully-tagged sibling list no longer transfers positionally).
- New `_sibling_transfer(ia, candidate, identifier, want, tracks, metadata_norms) -> tuple[list[Track], list[str]]` in gather: loads every non-self `candidate.recordings` donor (`filter_files` + `clean_tag_titles` + `length_seconds`; skip donors with incomplete durations), calls `siblings.propose_rows` + `rate_alignment` + `cplus_filter`, picks the winning donor (highest agreement, then lowest DP cost, then identifier), applies `auto`-band C+-surviving rows to `unresolved` tracks with `title_source="sibling-align"`, returns notes for pair-level declines and per-run declines. Runs **after the overrides loop, before `adopt_gap_titles`** (see the Deviation section).
- Fetch gate: `kept and title_fraction(clean_tag_titles(kept)) < 1.0` — drop the count-mismatch/confidence condition.
- `models.py:157` comment: add `sibling-align`, mark `sibling` legacy (still-valid stored value, no migration).
- **Do NOT touch `TAUTOLOGICAL_TITLE_SOURCES` and do not force `matched=None`** for sibling-aligned tracks — they are independent evidence; `align()`'s match on them is a real measurement (spec's title_source section).

- [ ] **Step 1: failing tests** (`FakeProvider` pattern, offline fixtures):
  - an anchored fixture (mixed tags + unresolved, donor sibling in the candidate) adopts into the gap and the adopted titles equal the expected strings; `title_source == "sibling-align"`; `matched` is `align()`'s real verdict (assert it is not forced to None);
  - a fully-tagged show is byte-identical through gather (no donor fetch: the loosened gate's `title_fraction < 1.0` arm);
  - the ymsb2005 untagged fixture (`packages/llama/tests/fixtures/ymsb2005_metadata.json`, on main since Phase B) gets **zero** automatic adoptions — the pin whose inverse Phase B shipped nine times;
  - a below-FLOOR donor produces no adoption and a `sibling alignment declined (anchor agreement N%)` note;
  - a C+-declined run leaves its tracks unresolved and its per-run reason in notes;
  - old-rung removal: a donor with exactly `len(kept)` fully-tagged tracks but shifted content does NOT transfer positionally (assert the target track's title is still its filename, not the donor's shifted title — this is the test the old rung could never pass).
- [ ] **Step 2:** failures verified. **Step 3:** implement. **Step 4:** suite green; run `scripts/title_source_census.py` against the live library and record before/after counts in the commit message.

**Acceptance (content/mutation):**
- Named mutation A: add `"sibling-align"` to `TAUTOLOGICAL_TITLE_SOURCES`. A named test must fail by asserting a sibling-aligned track's coverage contribution (a weak-independent-evidence fixture whose flag state flips when its sibling-aligned matches are discarded). If no existing test catches it, write that test in Step 1 — this is the independence pin.
- Named mutation B: bypass `cplus_filter` in the gather call (adopt everything the ratio band admits). The C+-declined-run test must fail on *title content* (the declined track suddenly carries the donor title).
- The shifted-donor test from Step 1 shown failing against a copy with the OLD rung restored (this is the one backward mutation: prove the replacement actually closed the positional hole).

