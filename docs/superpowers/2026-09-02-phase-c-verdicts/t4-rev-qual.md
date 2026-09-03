QUALITY: CHANGES REQUESTED

Pointer guard `OK` before and after. Worktree untouched, `git status` clean, no commits.
All mutation runs on out-of-worktree copies under
`.../scratchpad/workc/t4-rev-qual/`, shadowing proven by a planted `SENTINEL_MARK`
(`SHADOW-FILE:` resolved into `mut*/packages/llama/src/llama/siblings.py`),
`__pycache__` purged before each run, driven by
`$WORKTREE/.venv/bin/python -m pytest` + `PYTHONPATH` — never a `.venv/bin/*`
console script.

**The source is clean. Every finding below is test-side.** I found no defect in
`loosely_same_title`, `rate_alignment` or `cplus_filter` themselves; three clauses
of them are simply not pinned, and the headline regression fixture reproduces a
different failure from the one it names.

---

## Verification of the brief's three named mutations (all pass)

| mutant | result | named tests that die |
|---|---|---|
| A — `gap_span` call replaced by one-sided bracketing | 4 failed, 181 passed | `test_a_tail_run_never_adopts_automatically`, `test_the_localised_shift_adopts_zero_interior_titles_under_cplus` (+2 others) |
| B — count-forcing clause deleted | 2 failed, 183 passed | `test_a_run_whose_donor_span_holds_more_tracks_than_files_declines`, `test_the_localised_shift_adopts_zero_interior_titles_under_cplus` |
| C — `MIN_ANCHORS = 1` | 2 failed, 183 passed | `test_a_single_agreeing_anchor_routes_to_the_operator_not_auto` (+`test_a_setlist_gap_title_is_not_an_anchor`) |

The implementer's table reproduces exactly. **The reuse of `structure.gap_span` is
real, not decorative** — I additionally deleted `gap_span`'s leading-edge branch in
`structure.py` (mutant F) and it killed
`test_a_leading_edge_run_adopts_gap_spans_exception_is_inherited` alongside the two
pre-existing tests in `test_structure.py` / `test_correspondence.py`. That is the
proof the brief wanted: the exception is inherited from the one definition, and the
Task-3 "duplicated composition one level up" failure is not repeated here. There is
no second copy of `unresolved_runs`, no restated trailing branch, and no re-derived
anchor walk.

---

## Findings

### 1. IMPORTANT — the band precedence, the one thing the spec answers twice, is unpinned

`packages/llama/src/llama/siblings.py:~430` (`rate_alignment`, the band ladder).

The docstring makes a deliberate claim: "**fewer than MIN_ANCHORS anchors routes to
the operator whatever the ratio says, including below FLOOR**". I mutated the ladder
to reorder it so `declined` outranks the anchor-count clause:

```python
if agreement < FLOOR:        band = "declined"
elif n_anchors < MIN_ANCHORS: band = "operator"
elif agreement >= AUTO:       band = "auto"
else:                         band = "operator"
```

**The entire llama suite passes (185/185 in the two files, and mutant D was green
across `packages/llama/tests/`).** The documented precedence is behaviourally
untested. The reason is arithmetic: the only inputs that separate the two orderings
are 1 anchor that *disagrees* (agreement 0.0 and `< MIN_ANCHORS` simultaneously),
and no test constructs one. Every single-anchor test in the file uses an *agreeing*
anchor (agreement 1.0), which both orderings route to `operator`.

**Change:** add one test — one `tags` track whose tag disagrees with its proposal,
every other track `unresolved`, asserting `res.n_anchors == 1`,
`res.agreement == 0.0`, `res.band == "operator"`. That is the assertion the
docstring's sentence is making, and it is currently the docstring's word alone.

(On the related question raised mid-review: the **0-anchor case is handled
explicitly and correctly** — `if n_anchors == 0: return GuardResult(None, 0, [],
"no-anchors")` sits *before* the division, so nothing is inherited from float
semantics, and `agreement is None` is documented as distinct from `0.0`. It **is**
pinned: mutant G, which replaced the early return with
`agreement = (agreeing / n_anchors) if n_anchors else 0.0`, killed
`test_a_wholly_untagged_tape_has_no_anchors_and_no_agreement`. And the ladder is
written as a precedence — anchor count first, ratio clauses simply not reached —
not as a tie-break. The expression of the rule is right; only the proof is missing.)

### 2. IMPORTANT — `test_an_unpaired_tagged_track_is_not_an_anchor` is hollow for the clause it names, and that clause is the only thing preventing a crash

`packages/llama/tests/test_siblings.py:~570`; source `siblings.py` `_anchor_row`.

`_anchor_row` has four clauses; the test's fixture row is
`SiblingRow(2, None, None, ...)` — **`donor_span is None` already excludes it**, so
the test never reaches `bool(row.proposed)`. I deleted the `and bool(row.proposed)`
clause (mutant H): **1215 passed, 0 failed** across `packages/llama/tests/`.

This is not cosmetic. The uncovered shape is a tagged track the DP *did* pair, with
a donor track that has no usable tag — `SiblingRow(i, None, (j, j+1), ..., "decline",
"sibling track untitled")`, a row `propose_rows` emits on its own. Under the mutant I
ran that shape through `rate_alignment` directly:

```
RAISES: AttributeError 'NoneType' object has no attribute 'replace'
```

(`fuzzy_norm_title(None)` inside `loosely_same_title`.) So the unpinned clause is
simultaneously the implementer's Concern 4 *and* the guard against a stage crash.

**Change:** keep the existing test, and add a second one using the untitled-donor
shape above — a real `propose_rows`-style row with a non-`None` `donor_span` and
`proposed=None` — asserting `n_anchors == 1` (only the other tagged track) and that
no disagreement is recorded. Rename the existing one to say what it actually pins
(`..._a_track_the_dp_paired_with_nothing_...`).

### 3. IMPORTANT — `test_cplus_leaves_a_layer_three_decline_reason_alone` is hollow

`packages/llama/tests/test_siblings.py:~640`.

Its fixture is `("Alpha","tags"), ("f2.mp3","unresolved"), ("Charlie","tags")`: the
single-track run at position 1 is bracketed by two agreeing anchors *and*
count-forced, so `cplus_filter` hits `continue` and `demoted` is empty. The test
asserts a reason survives a rewrite that never happens.

I deleted `r.verdict == "adopt"` from the final comprehension (mutant E) — the exact
guard the test's name claims to pin — and got **1215 passed, 0 failed**.

**Change:** move the layer-3 decline into a run that C+ actually demotes. E.g. make
it a *tail* run (`("Alpha","tags"), ("Bravo","tags"), untitled-donor decline at 3,
unresolved at 4`) so `demoted` covers tracks 3–4, and assert track 3 still reads
`"sibling track untitled"` while track 4 reads the C+ reason. That fixture kills
mutant E.

### 4. IMPORTANT — the localised-shift fixture reproduces a *tag* shift, not a *donor-span* shift

`packages/llama/tests/test_siblings.py:~690` (`_localised_shift`).

Answering the question directly: **it is genuine as machinery and mislabeled as
evidence.** It is built through the real DP from real durations (not hand-assembled
rows), it does produce `agreement == AUTO` with `band == "auto"` over 10 anchors,
and it does adopt zero interior titles — and mutations A and B each kill it naming a
different title. By the brief's own acceptance wording it passes.

But I dumped the rows, and the alignment inside it is **correct end to end**:

```
6 'Foxtrot' (5,6) adopt | tag: Golf      <- the tape's TAG is a song ahead
7 'Golf'    (6,7) adopt | tag: Hotel     <- ditto
8 'Hotel'   (7,8) adopt | tag: f8.mp3 unresolved
9 'India'   (8,9) adopt | tag: f9.mp3 unresolved
ops: [(0,1,0,1), (1,2,1,2), ... (9,10,9,10), (10,11,10,12), ...]   # 1:1 throughout
```

So the two interior fills C+ blocks (`"Hotel"`, `"India"`) are the **correct**
titles, refused because their left flank is a disagreeing anchor. Only track 11's
`"Kilo > Xray"` is genuinely wrong, and count-forcing catches it. The spec's actual
case (`design.md:166`) is the opposite mechanism — "tracks 1–4 correct, 5–10 off by
one … the bare ratio ships **7 wrong titles**, C ships 1, C+ ships **0**": there the
*alignment* slides and the tags are right. The fixture shows "C+ ships 0 titles, 2 of
them correct", which is a different claim, and the docstring's "the shift's last
wrong title" is true only of track 11.

**Change:** rename this one to what it is (a disagreeing-anchor / tape-tag-shift pin
— it is worth keeping, it is the only pin on the ratio's blindness) and correct its
docstring, which currently claims the interior is shifted. Then add the counterpart:
target durations chosen so the **DP itself** pairs an interior file with the wrong
donor track (a donor-only track inside the run that the DP does not absorb), head and
tail anchors still agreeing, so the proposals on the unresolved interior are actually
wrong titles and count-forcing declines them on `span[1]-span[0] != files`. That is
the fixture that proves C+ catches the harm rather than merely declining when anchors
disagree.

### 5. MINOR — `tracks` is untyped in the public signatures

`siblings.py`: `rate_alignment(rows: list[SiblingRow], tracks: list)`,
`cplus_filter(rows: list[SiblingRow], tracks: list)`, `_anchor_row(track, row)`.
`structure.py` annotates the same thing `list["Track"]` throughout. **Change:** use
`list["Track"]` with a `TYPE_CHECKING` import of `llama.models.Track` (models is pure;
the module's no-`stages` mandate is not at risk).

### 6. MINOR — the positional contract between `rows` and `tracks` is unstated

Both functions do `by_track = {r.track: r for r in rows}` and then
`for pos, track in enumerate(tracks)`, i.e. they assume `tracks[pos]` is the target
track `propose_rows` numbered `pos + 1`. `models.Track` carries `index`, which is
never consulted. If Task 5 ever passes a filtered or reordered list the mismatch is
silent (rows just stop matching, agreement drops, band degrades — no error).
**Change:** one line in the docstring stating "`tracks` is the same list, in the same
order, whose durations produced `rows`", or an `assert len(tracks) >= max(r.track)`.
Positional indexing itself is right — it matches `unresolved_runs`/`gap_span`.

### 7. NIT — the second assertion in `test_cplus_says_nothing_about_a_track_that_already_has_a_title`

`assert [t.title_source for t in tracks] == ["tags"] * 3` cannot fail: nothing in the
module mutates `tracks`, and `Track` is a pydantic model the function never copies.
Harmless, but it reads as a purity pin that isn't one. The first assertion carries the
test.

---

## Things I checked and found sound (no action)

- **Symmetry of `loosely_same_title`.** Both the containment arm (`na in nb or nb in
  na`) and the ratio arm are symmetric. I searched 200,000 random title pairs for an
  asymmetric case and found **0**, and checked the classic difflib shapes
  (`"abcd"/"dabc"`, reversed-word pairs, `autojunk` territory at 249 chars —
  `0.9979959919839679` in both directions). The containment direction *is* pinned in
  both orders (`test_loosely_same_title_accepts_a_dropped_parenthetical_either_way`;
  mutant K, dropping `nb in na`, kills it). The ratio arm's symmetry is not pinned,
  but I could not construct a case where it matters, and `difflib`'s `autojunk`
  (the only known asymmetry source) needs a 200-element `b`, while `proposed` is
  bounded by `MAX_TITLE_LEN = 80` via `hygienic_title`. Not worth a test.
- **No O(n²) blowup.** `SequenceMatcher.ratio()` on 4,000-character input measures
  <1 ms here, and both sides are short titles. One call per anchor per pass.
- **`structure.py` imports no stage** (only `difflib.SequenceMatcher` added at
  module top, correctly placed with `re`); `siblings.py` stays pure — its new imports
  are `dataclasses.replace` and four names from `structure`.
- **Constants follow house style.** `AUTO` / `FLOOR` / `MIN_ANCHORS` /
  `INDEPENDENT_TITLE_SOURCES` / `LOOSE_TITLE_RATIO` each carry a DO-NOT-RETUNE
  provenance comment naming the evidence doc, the mechanism and the measured numbers
  with units (`26.5%` marginal error, `68–99%` below 0.30, `10.1%` of disagreements).
  `LOOSE_TITLE_RATIO`'s note that "0.80 is not AUTO's 0.80 — the two are independent
  bounds that happen to share a value" is exactly the kind of trap-defusing comment
  this codebase wants. The comparator's two known misses are pinned as tests with the
  ratios in the comments (0.40 initialism, 0.774 near-miss) rather than fixed.
- **The count-forcing clause was rightly NOT factored into a shared helper.** This is
  duplication of an *arithmetic expression*, not of a *rule*: `adopt_gap_titles`'
  version compares against a canonical-setlist item count (a source independent of the
  tape, so it removes all assignment freedom), and this one compares against a donor
  span read off the very alignment under test (partly self-referential, justified by
  measurement alone). A shared `_count_forced(span, files)` would invite exactly the
  wrong inference — that the setlist-gap safety argument transfers — and both
  docstrings say so at length. This is restraint, not duplication wearing an
  invariant's clothes. Keep it.
- **No scope creep.** Four files, all named in the brief; +670/−3, the 3 being the
  replaced import block. Nothing outside `structure.loosely_same_title` and the new
  guard section is touched.
- **Nothing removed or weakened.** `git diff 4b07645..8c78eb3 -- packages/llama/tests`
  has **zero** removed lines (`grep -c '^-[^-]'` → 0) and +27 `def test_` — matching
  1590 → 1617 exactly. Both commit messages state the test command and its output
  (`Tests: ./.venv/bin/pytest -q -> 1617 passed, 7 deselected`), and `491088b` also
  states the baseline and the split. Mid-file imports in both test files follow the
  established convention in those files (`test_structure.py` already does this at
  lines 288, 315, 348, 393, 1643).

---

## Test hygiene — what edit makes each new test fail

**`test_structure.py` (8):**

| test | killing edit |
|---|---|
| `..._equates_normalized_spellings` | drop `fuzzy_norm_title` for `norm_title` (un-folds `&`→`and`) |
| `..._accepts_a_dropped_parenthetical_either_way` | drop `nb in na` — **verified, mutant K kills it** |
| `..._accepts_a_spelling_variant_on_the_ratio` | `LOOSE_TITLE_RATIO` ↑ past 0.833; or delete the ratio arm |
| `..._misses_an_initialism_known_limit` | add an initialism arm; or ratio ↓ below 0.40 |
| `..._misses_the_rain_go_away_near_miss_known_limit` | `LOOSE_TITLE_RATIO` ↓ to 0.75 |
| `..._rejects_two_different_songs` | ratio ↓ below 0.5 |
| `..._rejects_an_empty_side` | delete `if not na or not nb: return False` (then `"" in nb` → True) |
| `test_loose_title_ratio_is_the_measured_bound` | value pin only — tautological by design, house convention |

**`test_siblings.py` (19):**

| test | killing edit |
|---|---|
| `..._below_auto_but_above_floor_routes_to_the_operator` | `AUTO` ↓ to 0.65 (**verified by the implementer's table**); also `Disagreement(pos+1 → pos)` |
| `..._below_floor_is_declined_outright` | `FLOOR` ↓ to 0.10 |
| `test_two_agreeing_anchors_are_enough_for_the_automatic_band` | `MIN_ANCHORS` ↑ to 3 |
| `test_a_single_agreeing_anchor_routes_to_the_operator_not_auto` | `MIN_ANCHORS` ↓ to 1 — **verified, mutant C** |
| `test_a_wholly_untagged_tape_has_no_anchors_and_no_agreement` | delete the `n_anchors == 0` early return — **verified, mutant G** |
| `test_an_override_title_anchors_the_guard_like_a_tag` | drop `override`/`sibling-format` from `INDEPENDENT_TITLE_SOURCES` |
| `test_a_setlist_gap_title_is_not_an_anchor` | add `setlist`/`setlist-gap` to `INDEPENDENT_TITLE_SOURCES` — **verified, also dies under mutant C** |
| `test_an_unpaired_tagged_track_is_not_an_anchor` | **HOLLOW for its named clause** — drop `bool(row.proposed)` and it stays green (mutant H). Only `donor_span is not None` is pinned. **Finding 2.** |
| `..._bracketed_count_forced_interior_run_adopts_its_titles` | any unconditional decline in `cplus_filter`; flip the count-forcing `!=` to `==` |
| `..._leading_edge_run_adopts_gap_spans_exception_is_inherited` | delete `gap_span`'s leading branch — **verified, mutant F** |
| `test_a_tail_run_never_adopts_automatically` | add a trailing branch to `gap_span`, or one-sided bracketing — **verified, mutant A** |
| `..._donor_span_holds_more_tracks_than_files_declines` | delete count-forcing — **verified, mutant B** |
| `test_runs_decline_individually_...` | one-sided bracketing — **verified, mutant A** |
| `test_cplus_says_nothing_about_a_track_that_already_has_a_title` | widen C+ to demote disagreeing-anchor rows (an addition, not a deletion). Second assertion is vacuous — **Finding 7** |
| `test_a_disagreeing_anchor_does_not_bracket_...` | drop the `and loosely_same_title(...)` filter when building `anchors` — **verified, also dies under mutant A** |
| `test_cplus_applied_to_the_display_would_blind_the_operator` | make `cplus_filter` clear `proposed`, or make unanchored runs adopt |
| `test_cplus_leaves_a_layer_three_decline_reason_alone` | **HOLLOW** — drop `r.verdict == "adopt"` and it stays green (mutant E). **Finding 3.** |
| `..._localised_shift_passes_the_ratio_band_the_ratio_is_blind` | `AUTO` moved in either direction |
| `..._localised_shift_adopts_zero_interior_titles_under_cplus` | mutants A **and** B, each naming its own title — genuine machinery, but see **Finding 4** on what it reproduces |

**Score: 3 of 27 do not bind what their names claim** (two hollow, one vacuous
assertion), plus one documented precedence with no test at all. That is a real
improvement on the prior tasks' rate, and the guard's load-bearing clauses — the
`gap_span` reuse, count-forcing, `MIN_ANCHORS`, the 0-anchor return, the containment
arm — are all genuinely pinned.

---

## Verdict on the implementer's five Task-5 concerns

1. **Rows on already-titled tracks stay `adopt`; gather must intersect with the
   unresolved set — REAL, and the most dangerous of the five.** Verified: with three
   tagged tracks `unresolved_runs` returns `[]`, so `cplus_filter` demotes nothing and
   a disagreeing anchor's row (`tape: "Casey Jones"`, `proposed: "Echo"`) survives as
   an `adopt`. A Task-5 wiring that writes every adopt row onto its track overwrites
   the tape's own tags with the sibling's. The contract is correctly left as briefed
   (per-run) and the consequence is documented in the test's docstring — but this must
   be an explicit, tested line in Task 5, not an inherited assumption.
2. **Run reasons only visible via demoted rows — REAL but minor.** A run whose rows
   were all declined at layer 3 records no C+ reason, so `show.json` notes
   reconstructed from rows will be incomplete for exactly the runs where two reasons
   apply. Cheap fix if Task 5 wants a full audit: return `(rows, run_reasons)` or
   expose the loop as a small public helper. Not a Task 4 defect.
3. **`cplus_filter` does not check the band — REAL but already mitigated.** The
   ordering obligation is stated plainly in the docstring, and folding the band check
   in would break spec invariant 1 (C+ must be callable by gather and not by the
   renderer, and the renderer needs the *rows*, not a band decision). Correct as
   briefed. Task 5 should pin the ordering with a test that a `declined` pair adopts
   nothing, since nothing in this module enforces it.
4. **An untitled-donor row is not counted as an anchor at all — REAL, and I am
   upgrading it.** The judgement is right (an untitled donor offers nothing to agree
   *with*, and counting it as a disagreement would let a partly-untagged sibling drag
   a correct alignment below `FLOOR` — the module's own "gates on evidence are
   per-item, never per-donor" principle). But the clause implementing it is **entirely
   unpinned and load-bearing against a crash** — see Finding 2. Fix the test before
   Task 5 builds on the behaviour. The implementer's caveat about Task 7's scorers
   possibly counting such rows as disagreements is worth carrying forward verbatim.
5. **Sub-`MIN_ANCHORS` routes to `operator` even below `FLOOR` — REAL as a question,
   correctly resolved, and unpinned.** The resolution is right and for the stated
   reason: `MIN_ANCHORS` exists because the ratio is too noisy to be a measurement
   below 2, not because a low value means a bad alignment, so a single disagreeing
   anchor may neither license adoption nor justify discarding the proposal (and ~24%
   of disagreeing anchors are the *tape* being wrong). It is expressed as a genuine
   precedence — anchor count evaluated first, ratio clauses unreachable below it — not
   as a bolted-on tie-break, and the docstring earns it. The 0-anchor case is likewise
   explicit and pinned. **But the precedence itself survives mutation** (Finding 1);
   add the single-disagreeing-anchor test and this concern closes.

---

## Summary of required changes

1. Add the single-disagreeing-anchor band test (Finding 1).
2. Add the untitled-donor anchor test; rename the existing one (Finding 2).
3. Re-fixture `test_cplus_leaves_a_layer_three_decline_reason_alone` so `demoted`
   actually covers its track (Finding 3).
4. Correct `_localised_shift`'s docstring and add the true donor-span-shift
   counterpart (Finding 4).
5. Optional: `list["Track"]` annotations, the positional-contract line, drop the
   vacuous assertion (Findings 5–7).

None of these touches the guard's behaviour. Re-review should be quick.
