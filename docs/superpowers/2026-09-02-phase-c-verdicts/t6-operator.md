# Task 6 report: operator surface for the sibling arm

## Status
DONE. Suite green.

## Commits (branch `sibling-transfer`, worktree `.worktrees/sibling-transfer`)
- `a0f35d3` — Task 6 implementation: `gather.load_donor_tapes` extraction,
  `models.ProposalRow.residual_sec`/`note`, `cli._sibling_proposal` entry
  seam + rendering, 6 tests (5 test_cli.py, 1 test_triage.py).
- `3f68c86` — added a second, mutation-B-sensitive test after discovering
  the wholly-untagged fixture cannot demonstrate that mutation (see below).

## Test command and output tail
`./.venv/bin/python -m pytest -q` from the worktree root:
```
1639 passed, 7 deselected, 26 warnings in 6.96s
```
Baseline was 1632 passed, 7 deselected. Delta +7, all additions (itemised
below); no existing test touched.

## Step 2 -- failure output verbatim (pre-implementation)
Reverted `cli.py`/`models.py`/`gather.py` to `16e3e73` (`git stash` /
`git checkout 16e3e73 --`), reran the new tests:

- `test_untagged_fixture_with_tagged_donor_renders_sibling_proposal`:
  `AssertionError: assert 'sibling-align' in 'ymsb2005-12-31: the setlist
  cannot be pinned to tracks 1-24: ... (25 canonical items vs 24 song-like
  tracks - the setlist describes 1 song this tape does not hold)\n'`
- `test_delmccoury_shaped_operator_band_confirms_only_unresolved_rows`:
  `AssertionError: assert 'band operator' in 'delmccoury2001-07-01: the
  setlist cannot be pinned to tracks 14-15: ... (15 canonical items vs 15
  song-like tracks - counts agree)\n'`
- `test_operator_band_sibling_titles_diverge_from_the_canonical_dp`:
  `AssertionError: assert "band operator" in result.output` -- output shows
  the canonical DP's own `duration-model` proposal instead
  (`'ymsb2005-12-31: proposal (duration-model)\n   1.   8:45   274s  Granny
  Woncha Smoke Some > Ride The Wild Turkey\n...'`).
- The three fall-through/pin tests (`below_floor_*`, `c1_staleness_guard`)
  correctly PASSED on the pre-implementation baseline too -- they pin paths
  the sibling arm must leave untouched, so that is expected, not a gap.

Implementation restored (`git checkout HEAD --`) and suite reconfirmed
green before continuing.

## Named mutation A -- renderer applies `cplus_filter`
Applied on a `PYTHONPATH`-shadowed copy outside the worktree (per the
copy-safety rule; never `.venv/bin/pytest` there).

**Failing test:** `test_untagged_fixture_with_tagged_donor_renders_sibling_proposal`
**Verbatim assertion line:** `assert ov.titles[1] == "Song 01"` (test_cli.py:864)
**Verbatim failure:** `KeyError: 1` -- `overrides.titles` came back empty:
C+ demotes every row of the wholly-untagged tape's single all-track run
(no anchors -> no brackets), so the table renders holed/empty exactly as
the plan predicted.

## Named mutation B -- canonical DP runs first
**Discovery, reported rather than hidden:** the wholly-untagged fixture's
canonical DP (`correspondence.propose_titles`) is infeasible *regardless*
of arm order -- a fully-unresolved tape is one run spanning the whole tape,
`structure.gap_span` has no trailing-edge branch, so `_unaccounted` always
declines with "no track ... brackets that run." Verified directly (see
Step 2 above): the mutated code falls through to the sibling arm exactly
as before and produces byte-identical output on that fixture -- mutation B
is structurally invisible on it. I added a second fixture
(`test_operator_band_sibling_titles_diverge_from_the_canonical_dp`) that
reuses `_staged_anchored_ymsb_show` (whose canonical DP IS feasible, and
whose real output -- `ANCHORED_GAPS` -- is independently pinned by
`test_below_floor_donor_with_usable_canonical_falls_through_to_dp`) with an
operator-band donor that tags the same 3 gaps with placeholder text.

**Failing test:** `test_operator_band_sibling_titles_diverge_from_the_canonical_dp`
**Verbatim assertion line:** `assert "band operator" in result.output` (test_cli.py:916)
**Verbatim failure:**
```
AssertionError: assert 'band operator' in 'ymsb2005-12-31: proposal (duration-model)\n   1.   8:45   274s  Granny Woncha Smoke Some > Ride The Wild Turkey\n...'
```
Confirmed the divergence is on title CONTENT, not just header text: with
the "band operator" assertion removed, the mutated code's
`overrides.titles` came back as `{5: 'Steep Grade Sharp Curves', 14: 'Jack
London', 20: 'Ewe With The Crooked Horn'}` (the canonical DP's real titles)
instead of the sibling arm's `{5: 'Placeholder 5', 14: 'Placeholder 14',
20: 'Placeholder 20'}`.

## `cplus_filter` caller check
`grep -rn "cplus_filter" packages/llama/src/` -- the only definition and
only call site are both in `gather.py` (`_sibling_transfer`, line 242);
`cli.py`'s only occurrence is inside a docstring quoting the spec
invariant, never a call; `structure.py`'s only occurrence is a comment.

## Confirmation-write test's exact `overrides.titles` dict
`test_delmccoury_shaped_operator_band_confirms_only_unresolved_rows`:
```python
assert ov.titles == {14: "Beaumont Rag", 15: "Sally Goodin"}
```
(13 anchor tracks, 4 of them disagreeing, are asserted absent by this
exact-dict equality, not merely "not overwritten.")

## Itemised suite delta (+7, all additions)
1. `test_untagged_fixture_with_tagged_donor_renders_sibling_proposal` (test_cli.py)
2. `test_operator_band_sibling_titles_diverge_from_the_canonical_dp` (test_cli.py)
3. `test_delmccoury_shaped_operator_band_confirms_only_unresolved_rows` (test_cli.py)
4. `test_below_floor_donor_with_no_usable_canonical_declines_unchanged` (test_cli.py)
5. `test_below_floor_donor_with_usable_canonical_falls_through_to_dp` (test_cli.py)
6. `test_suggest_titles_c1_staleness_guard_still_fires_before_donor_work` (test_cli.py)
7. `test_suggest_titles_sibling_arm_shares_the_triage_seam` (test_triage.py)

## Files touched
- `packages/llama/src/llama/stages/gather.py` -- extracted `load_donor_tapes`
  (public), `_sibling_transfer` now calls it; behavior-preserving (137
  gather/siblings tests green immediately after the extraction, before any
  CLI work).
- `packages/llama/src/llama/models.py` -- `ProposalRow.residual_sec`/`note`;
  `evidence`/`evidence_source` comments extended with `"sibling-align"`.
- `packages/llama/src/llama/cli.py` -- new `_sibling_proposal` (entry seam),
  `_format_sibling_proposal_row`, `_sibling_canonical_text`,
  `_sibling_donor_coverage`; `_propose_titles_for_show` tries the sibling
  arm before the canonical DP, falling through on `declined`/no donor.
- `packages/llama/tests/test_cli.py` -- `MultiIA`, donor-fixture helpers,
  6 new tests.
- `packages/llama/tests/test_triage.py` -- 1 new test (shared-seam pin).

## Concerns
1. **File-list deviation from the brief's "Files:" line.** The brief named
   only `cli.py`/`models.py`/`test_cli.py`; I also touched
   `gather.py` (donor-loading extraction, ruled explicitly in the brief)
   and `test_triage.py` (the triage pin test -- test_triage.py already
   imports fixtures from test_cli.py for exactly this purpose, and no
   existing convention puts a triage test inside test_cli.py). Flagging
   for the record even though I believe both are the correct, minimal-risk
   choice.
2. **Mutation B required an extra fixture beyond the brief's literal
   framing** ("the untagged-fixture test must fail on title content").
   I verified by direct code inspection and a live mutation run that this
   is impossible for a genuinely wholly-untagged fixture -- its canonical
   DP is unconditionally infeasible regardless of arm order, a structural
   fact of `structure.gap_span`'s missing trailing-edge branch, not a bug
   I introduced. I built a second, targeted fixture instead. This is the
   one place I diverged from the brief's exact wording rather than the
   letter of an instruction; I'd like this specifically checked.
3. **`_donor_key`/`_show_metadata_norms` imported by name from `gather.py`
   into `cli.py`** despite the leading underscore -- no existing precedent
   in this codebase for a cross-module underscored import. I judged the
   drift risk (two definitions of "who wins"/"what's hygienic") worse than
   the convention violation, but it's a judgment call, not something the
   plan ruled on explicitly.
4. The "embed-in-canonical coverage figure" and "head-row caution" text
   (design notes, not in the Step-1 acceptance list) are implemented but
   their exact wording/threshold is my own choice -- no acceptance test
   pins their content, only that a no-anchors proposal prints something.

---

# Task 6 fix round 1

## Status
DONE. Suite green.

## Commits
- `18e618f` -- fix round 1: closes I1, I2/m1, I3, I4, I5, I6, plus Minors
  m2/m3/m4. (Follows `a0f35d3` and `3f68c86` from the initial round.)

## Test command and output
`./.venv/bin/python -m pytest -q` from the worktree root:
```
1642 passed, 7 deselected, 26 warnings in 6.49s
```
Prior state (before this round): 1639 passed, 7 deselected. Delta +3 new
test functions (`test_weak_evidence_decline_keeps_the_dp_candidate_out_of_the_write`,
`test_best_donor_picks_the_higher_agreement_donor_not_the_worse_one`,
`test_operator_band_donor_untitled_on_the_gaps_falls_through_to_the_dp`),
plus `test_untagged_fixture_with_tagged_donor_renders_sibling_proposal`
strengthened IN PLACE (I1/I2/I3, same test name). No test removed or
weakened.

## What changed, and why

**I5 first, since it reshapes the others.** Extracted `gather.best_donor(ia,
candidate, identifier, want, tracks, metadata_norms) -> (donor, rows, res,
notes)` from the four-step loop (`load_donor_tapes` -> `propose_rows` ->
skip `None` -> `rate_alignment` -> `_donor_key` -> sort -> `[0]`) that
`_sibling_transfer` and `cli._sibling_proposal` had each been carrying a
copy of. Both now call it. This also dissolved the need for `cli.py` to
import `_donor_key` privately across the module boundary; the OTHER
private import (`_show_metadata_norms`) was promoted to public
`gather.show_metadata_norms` (I6/private-import ruling from both
reviewers, matching Task 3's `structure.hygienic_title` precedent) --
`cli.py` now imports zero underscore-prefixed symbols from `gather`.

**I1** (`cli.py`, the no-anchors block): the untagged-fixture test's
`"no-anchors" in result.output` was satisfied by the header line alone,
so the donor-id/coverage/caution block was deletable. Strengthened the
SAME test to assert all three verbatim. The coverage figure needed a
second pass: the donor's `Song NN`-templated titles turned out to be
mutually >= 0.80 `SequenceMatcher`-similar to EACH OTHER (differing by one
digit), so ANY `Song NN` canonical item matched ALL 23 adopted rows at
once (measured: 23/23, not the intended 2/23) -- a genuinely
non-degenerate PARTIAL figure was unreachable while every donor title
followed that template. Fixed by giving two tracks (3, 4) distinct real
titles ("Ripple", "Casey Jones") with no textual overlap with `Song NN` or
each other; the fixture's description now quotes those two, giving a
literal, asserted `2/23 (9%)`.

**I2/m1** (`cli.py`, decline-reason rendering): no fixture produced a
declined row at all, so "declined runs printed with their reason line, not
silent holes" was unpinned; the reviewer additionally caught the
rendering ITSELF as a checkerboard (the run's reason repeated verbatim on
every row of it). Rewrote rendering to be genuinely run-shaped:
`_sibling_run_reasons` collapses CONSECUTIVE rows sharing an identical
`note` into one printed line (`track N: reason` / `tracks N-M: reason`);
`_format_sibling_proposal_row` no longer prints an inline bracket at all.
The untagged fixture's donor gained a blank title on track 15 (declines
"sibling track untitled"), and the test asserts both the run-reason line
and the row's own "(unresolved - hand-edit)" text.

**I3** (`cli.py`/`models.py`, `residual_sec`): both existing donors used
exactly-equal durations, so the true residual was always `0.0` and a
`\b0s\b` presence regex could not tell a computed value from a hard-coded
one -- the SAME defect this phase shipped once already in this field,
invisible to mutation testing this time because the mutant (`0.0`) and the
ground truth (`0.0`) agree. Per the sharpened guidance, fixed the FIXTURE,
not the assertion: donor track 2 is now offset +12s from the target's real
duration, and the test asserts `"12s"` on that row and `"0s"` on its
unaffected neighbour (track 1) -- a specific non-degenerate expected value.
Audited the other four new/changed assertions in this round for the same
shape (zero/empty/default expected value): none found -- I4's picks dict
`{3: "Charlie", 4: "Delta"}`, I5's `{2: "Bravo", 3: "Charlie"}`, and I6's
`ANCHORED_GAPS` are all non-trivial, independently-known values, not
defaults.

**I4** (`cli.py`, weak-evidence declines): `siblings.SiblingRow`'s own
docstring says a weak-evidence decline "keeps [its proposed title] so the
operator path can render what the DP thought" -- the implementation
blanked it. Fixed: `note` now carries `f"{reason} - DP proposed
{proposed!r}"` when a declined row still has a candidate; `picks` is now
built in the SAME loop that walks the raw `SiblingRow`s, keyed on
`row.verdict == "adopt"` directly, never on whether `ProposalRow.title`
happens to be truthy -- closing the leak the reviewer's inverse mutation
found (a declined title reaching `overrides.titles` because `picks` used
to gate on title-emptiness).

Per the follow-up sharpening (assert the PROPERTY, not the mechanism): the
new test's decisive assertion is `1 not in ov.titles and 2 not in
ov.titles` against the WRITTEN `overrides.json` (via `read_overrides`),
not against the rendered row being blank -- a future change that
reintroduced the title through a different code path would still be
caught.

The donor for this scenario (`test_siblings.py`'s own 25s-fragment
near-ambiguous-merge fixture) could not be routed through a real donor
RECORDING here: `filter_files`'s relative duration floor
(`SHORT_FRACTION_OF_MEDIAN=0.25`) excludes a 25s file against a ~300-500s
median, so the fragment never survives `load_donor_tapes`, and the merge
-- hence the decline -- never happens (verified directly: the same numbers
built as an actual donor recording produce a plain 4-track all-adopt
table, no merge, no decline). A brute-force search for a same-shape
scenario that BOTH survives the floor AND stays under
`MIN_EXCLUSION_PENALTY` turned up nothing in a broad parameter sweep.
Resolved by monkeypatching `gather.best_donor` (via the SAME
`gather_mod`-monkeypatch pattern this file already uses for
`build_canonical`) to hand `_sibling_proposal` the exact rows
`test_siblings.py` already unit-tests, since I4 is about the CLI's
rendering/write-gating of an ALREADY-weak-evidence row, not about whether
`propose_rows` finds one.

**I6** (spec finding, `cli.py`): `_sibling_proposal` used to return
`(prop, picks)` unconditionally once a band was accepted, even when
`picks` came back empty (an operator-band donor untitled on exactly the
tape's unresolved tracks) -- preempting the canonical DP, which might have
proposed real titles for those same tracks. Fixed: `_sibling_proposal`
itself returns `None` when `picks` is empty (after echoing its own table,
so an operator still sees it as corroborating evidence), which the
existing caller (`if sib is not None: return sib`) already falls through
on correctly -- no caller-side change needed. New fixture: an
operator-band donor (16/21 real anchors agree) blanked on exactly the 3
gap tracks (`ANCHORED_GAPS`); asserts the canonical DP's titles land
(`ov.titles == ANCHORED_GAPS`), not the sibling table's.

**Minors also fixed:** m2 (`structure.loosely_same_title`'s docstring now
names its two new CLI callers, `_sibling_canonical_text`/
`_sibling_donor_coverage`, and states why they don't enter its "DO NOT
RETUNE" measurement basis); m3 (`models.ProposalRow.note`'s comment
trimmed to the two sources that actually reach the field -- the "C+-style
run reason" and "head-rows caution" claims were both unreachable, since
the renderer never calls `cplus_filter` and the caution is always a
standalone echoed line); m4 (`cli._sibling_proposal` now echoes
`load_donor_tapes`'s fetch-failure notes before the band check, so a
donor that existed and failed to fetch is no longer indistinguishable from
no donor at all on the one path where a human is deciding).

**Deferred, as flagged in the review:** m5 (the "nothing to adopt: every
track already has a title" message is reachable-but-false when every row
declined rather than every track being titled -- this is pre-existing
shared code in `_propose_and_confirm_titles`, not new to this task, and
I6's fix reduces its exposure from the sibling side rather than
eliminating it); m6 (citation for `_sibling_donor_coverage`'s "missed
gd1982-10-10 at 92%" claim -- should point at the design spec's line, not
sourced in this round); spec-m7 (`penalty_sec` is not carried onto
`ProposalRow`/rendered -- the spec's untagged-path list mentions "per-row
residuals and penalties," only the first shipped).

## Mutation verification (I1, I2, I3, I5, I6 -- each on a fresh
PYTHONPATH-shadowed copy, `__pycache__` purged before/after, shadowing
re-verified via `llama.__file__` before every run)

- **I1** -- `if res.band == "no-anchors":` -> `if False and ...`:
  `test_untagged_fixture_with_tagged_donor_renders_sibling_proposal` fails
  at `assert "embeds in canonical setlist: 2/23 (9%)" in result.output`.
- **I2** -- the `_sibling_run_reasons` print loop replaced with `for lo,
  hi, note in []:`: same test fails at `assert "track 15: sibling track
  untitled" in result.output`.
- **I3** -- `residual_sec=row.residual_sec` -> `residual_sec=0.0`: same
  test fails at `assert "12s" in row2 and "0s" not in row2` (actual:
  `'   2.   7:10     0s  Song 02'`).
- **I5** -- `gather.best_donor`'s `candidates.sort(key=lambda c: c[0])` ->
  `..., reverse=True)`: `test_best_donor_picks_the_higher_agreement_donor_not_the_worse_one`
  fails at `assert f"donor {donor_a_ident}" in result.output` (actual
  output shows `donor twodoors2012-02-02.aud.bad` won).
- **I6** -- removed the `if not picks: return None` guard (always `return
  prop, picks`): `test_operator_band_donor_untitled_on_the_gaps_falls_through_to_the_dp`
  fails at `assert "proposal (duration-model)" in result.output or
  "proposal (sibling-duration)" in result.output` (actual output ends
  `nothing to adopt: every track already has a title`, the sibling table's
  own empty-picks message, never reaching the DP).

## Concerns carried over from round 1, now resolved or narrowed
- Private cross-module imports (`_donor_key`, `_show_metadata_norms`):
  RESOLVED -- `_donor_key` no longer crosses the boundary at all
  (`best_donor` owns it), `_show_metadata_norms` promoted to public
  `show_metadata_norms`.
- Mutation B's second fixture: unchanged from round 1, both reviewers
  independently reproduced and endorsed it.
- File-list deviation (`gather.py`, `test_triage.py`): both reviewers
  ruled this correct scope, not creep.

## New concerns from this round
1. The I4 fixture cannot be built as a real donor RECORDING (the
   near-ambiguous-fragment scenario dies against `filter_files`'s
   duration floor) -- resolved via a `gather.best_donor` monkeypatch
   instead, which tests `_sibling_proposal`'s rendering/gating in
   isolation from `propose_rows`/`load_donor_tapes`. This is a narrower
   test than an end-to-end one, though the narrowing exactly matches what
   I4 is actually about (the CLI's handling of an already-weak-evidence
   row, not the DP's own classification of one, which
   `test_siblings.py` already unit-tests).
2. Deferred m5/m6/spec-m7 per the review's own "at the controller's
   discretion" framing -- flagging again in case the controller wants them
   in this round rather than the final one.
