### Spec Compliance
- ❌ Issues found:
  - **The sibling-durations pair count deviates from the brief and spec, and the deviation makes the check fire less** (`title_hygiene.py:211-215`). The brief says `sibling_disagreement` "counts a pair only for a row whose `donor_span` has length 1 and is shared by no other row, whose donor title passes `is_real_title`, with filler on either side neutral". Filler is listed as how a counted pair is *compared*, not as a reason to leave it out of the count. The spec ("Wholly untagged tapes" (b)) also counts tracks "the alignment pairs one-to-one" against `MIN_ANCHORS`. The implementation `continue`s on filler before `pairs.append`, so a filler pair does not count toward `MIN_ANCHORS` (implementer's judgement call 5). Probe (logged): `sibling_disagreement({0:'Bertha',1:'Tuning'}, donor(['Jack Straw','Tuning'], [(0,1),(1,2)]))` returns `None`. Under the brief there are 2 pairs and one disagrees, so it should return `(0, 'Bertha', 'Jack Straw')`. `is_real_title` is True for `Tuning`/`Banter`/`Crowd`/`Intro`/`Jam`, so the `is_real_title` filter does not remove these pairs first.
  - Everything else matches the brief:
    - `decide_d` returns None on a count mismatch or when nothing is `unresolved` (`:241-245`).
    - Candidates are judged with `track_no=i + 1`, `first=i == 0`, the file stem and the tag core (`:251-261`).
    - The check order is check 1 show-level, then 2, then 3, then written durations, then (only when `wholly_untagged`) block size and sibling, then agreement (`:262-286`).
    - `donor()` is called only when wholly untagged and there are candidates (`:275-282`).
    - `aliases` reaches only `_agreement` (`:284`); check 3 and the sibling check call `agrees` with no aliases (`:218`).
    - `_DISC_INDEX` and `_SET_INDEX` are byte-identical to the Global Constraints (`:115-120`). They run on the stem, and the last match wins (`:123-129`).
    - The encore fold, the inertness conditions and the set-index replacement follow the brief (`:146-176`).
    - `donor_span` is read correctly as half-open, which I checked against `siblings.py:106` (`span[1]-span[0] != 1` is length 1). `row.track - 1` indexes `cands` (`:205`).
    - `SHIFT_CHECKS` is exactly the six show-level names that do not start with `hygiene:` (`:110-111`), and a test pins it.
    - `d_notes` strings match the fixed strings: one show-level note from `failed[0]`, plus one note per per-track decline (`:302-311`).
    - `apply_d` writes only positions that are still `unresolved`, so an override is never touched (`:292-299`).
    - `is_self_filled` requires `not d.failed` and every song-like track to be `desc-position` (`:314-320`).
    - Protected names: a grep of the diff finds only imports and uses (`is_real_title`, `MIN_ANCHORS`, `GD_SHORTHAND`, `AGREEMENT_FLOOR`) and no edits. Only `title_hygiene.py` and its test file changed.
- ⚠️ Cannot verify from diff:
  - **Review Focus 5 ("missing per-file durations … on the untagged sibling check").** `test_sibling_check_inert_without_durations` covers only `donor()` returning None and a donor with one pair. `decide_d` never reads durations on the sibling path. The real exposure is whether Task 11's `donor` callable returns None, without raising, when the target's `length` is missing. Task 11's reviewer should check that.
  - **Task 7's reading of `track_declines`.** Judgement call 6 (no `donor()` call when every unresolved position was declined per track) is moot for S: under Q1, S never fires on a wholly untagged tape, and only wholly untagged tapes run the sibling check. Whether S-deferred may fill D's per-track-declined positions is Task 7's call.
  - **Concern 1 (`07-8th Wonder`) is a cleaning consequence from Task 1 and the spec, not something Task 6 does.** The step-2 leader strip requires a non-digit after the leader, so `07-8th Wonder` keeps its `07-`. D would then ship that text unflagged on rosehilldrive-2008-12-31. The text is cosmetic, but it is a wrong title on surface (a), so it should be a gate row for the operator at Checkpoint A. The RHD test does not assert position 6's text, so nothing pins either behaviour.

### Strengths
- Composition, not re-implementation. `decide_d` calls Task 4-5's `judge`, `adjacent_duplicate`, `tape_disagreement`, `written_duration_mismatch` and `agrees`. The only refactor, `agreement_share` → `_agreement` (`:68-95`), keeps `agreement_share`'s value byte-for-byte, and the Task 5 tests are green.
- Every show-level failure is recorded, not just the first (`test_check_order_and_all_failures_recorded` pins all five in order). The gate gets full data while the note names only `failed[0]`.
- Real-case tests use verbatim descriptions with their slugs cited: rosehilldrive-2008-12-31, belafleckandtheflecktones-2003-06-08, billystrings-2023-06-10 and derektrucksband-2003-11-26. These are the spec's own U-class cases, and they cover the per-track `?` declines, the `"Set" 1:` trailing colon that is not a shift, and both shifted shows caught by block size.
- The disc-index grammar is pinned against `dsbd`/`sbd`/`cd`/`disc_N_track_N` (`test_disc_index_grammar`).
- Block-size inertness is tested on every arm: no index, one file missing the index, 3 discs vs 2 blocks, a single block, interleaved discs, and the encore fold with and without `fold_encore`.
- `test_d_never_touches_an_override` and `test_d_may_fill_a_2b_demoted_position` cover the two edges of the spec's "When it fires".

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **`title_hygiene.py:211-215`: filler-neutral pairs are left out of the `MIN_ANCHORS` count.** This contradicts the brief's wording and the spec's "the alignment pairs fewer than `MIN_ANCHORS` tracks".
   - **What goes wrong:** a wholly untagged tape whose sibling alignment pairs one song track (which disagrees) and one or more filler tracks one-to-one is declared inert. D then fills it with no sibling evidence against a shift.
   - **Why it matters:** this is strict surface (a), where an unflagged wrong title is the costly outcome, and the deviation errs toward not declining. On wholly untagged tapes the sibling check is one of only three shift detectors, alongside written durations and block size.
   - **How to fix:** append filler pairs to the counted list as neutral, so they count toward `MIN_ANCHORS` but never disagree, and add a test with one disagreeing song pair plus one filler pair that expects a `sibling durations` failure.
   - **Alternative:** if the orchestrator prefers the implementer's "one comparable pair is not evidence" reading, record it as a plan reading the gate reports, the way R10 and R15-R17 are, so the operator can overrule it at Checkpoint A. It should not stay an undocumented implementer choice.

#### Minor (Nice to Have)
1. **`title_hygiene.py:180-183`: dead defensive code.**
   - **What's wrong:** after folding, every folded block holds at least one entry, so `sizes[k]` is never 0 and `first >= len(dl.cleaned)` cannot happen. The same goes for the redundant `ag[1] is not None` at `:285` (a share below 0.5 implies a miss) and `tag or ""` at `:255`.
   - **Why it matters:** readers may assume these states are reachable.
   - **How to fix:** simplify to `_detail(blocks.index(k), dl.cleaned[blocks.index(k)].text)`.
2. **`title_hygiene.py:319`: `is_self_filled` classifies a track as song-like by `is_filler(t.title)`, and an `unresolved` track's title is its filename** (`titles.py:492,501`).
   - **What's wrong:** `is_filler('d1t01 Tuning.flac')` and `is_filler('intro.mp3')` are True (probe logged), so an unresolved track with a filler-named file does not block self-filled.
   - **Why it matters:** the show still holds on `unresolved track titles`, so a wrong title cannot ship this way. But Q2 would skip the LLM alignment and suppress the low-confidence flag on a tape that is not wholly filled.
   - **How to fix:** treat any `unresolved` track as blocking, as in `all(t.title_source == DESC_POSITION for t in songs) and not any(t.title_source == "unresolved" for t in tracks)`, or document the filler reading.
3. **`test_set_headers_use_set_index` uses artificial dual-token filenames.** The implementer disclosed this, and it is acceptable because no real LMA name was found; the `gd77-05-08s1t..` set-only case is real-shaped.
4. **The reported full-suite run shows "26 warnings".** The file-level run (`52 passed in 0.32s`) shows none, so they do not come from this task's tests. They look pre-existing, but nobody has accounted for them against the baseline. Whoever owns the baseline should confirm the count did not change.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The D decision, block size, notes and self-filled predicate are correct, well composed and well tested against the spec's real U-class cases. One deviation needs fixing or an explicit ruling first: the sibling-durations check leaves filler pairs out of the `MIN_ANCHORS` count, which makes a shift detector inert where the brief and spec say it should decline, on the surface where an unflagged wrong title costs the most.
