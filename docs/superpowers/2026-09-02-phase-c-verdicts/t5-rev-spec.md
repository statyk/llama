# Task 5 — SPEC COMPLIANCE REVIEW

## SPEC ✅ (with one Important test-coverage gap, no rework of shipped behaviour required)

Reviewed `83b4a19..e34fda0`. Pointer guard: `PTH-GUARD: OK`. All mutations run on an
out-of-worktree copy (`git archive e34fda0`) shadowed by `PYTHONPATH`, never a
`.venv/bin/*` console script, `__pycache__` purged between every run, shadowing proven
first by a planted sentinel (`"sibling-align"` -> `"SENTINEL"` made
`test_sibling_transfer_adopts_into_a_bracketed_gap` red).

## Brief requirements, one line each

| Requirement | Verdict | Location |
|---|---|---|
| Delete `_sibling_titles` | MET | gather.py: symbol gone; `grep _sibling_titles src/` = 0 hits |
| Remove `resolve_titles`' `sibling_titles` param + `elif` rung | MET | titles.py:236 signature, :292 rung deleted |
| New `_sibling_transfer(ia, candidate, identifier, want, tracks, metadata_norms)` | MET | gather.py:121-207, exact signature |
| Loads non-self donors: `filter_files` + `clean_tag_titles` + `length_seconds`, skips incomplete durations | MET | gather.py:157-171 (`if any(d is None ...): continue`) |
| `propose_rows` + `rate_alignment` + `cplus_filter` | MET | gather.py:172-192 |
| Winning donor = highest agreement, then lowest DP cost, then identifier | MET in code (`_donor_key`, gather.py:110-118); **UNPINNED by any test** — see Q2 |
| `auto`-band C+-surviving rows applied to unresolved tracks, `title_source="sibling-align"` | MET | gather.py:192-206 |
| Notes for pair-level and per-run declines | MET | gather.py:181-190 (pair), :202-205 (per-run) |
| Runs after `overrides.titles` loop, before `adopt_gap_titles` | MET | overrides loop :775-779, transfer :786-789, `adopt_gap_titles` :819 |
| Fetch gate loosened to `kept and title_fraction(clean_tag_titles(kept)) < 1.0` | MET | gather.py:773; count-mismatch/confidence condition gone |
| `models.py:157` comment: `sibling-align` added, `sibling` marked legacy | MET | models.py:157 |
| Do NOT touch `TAUTOLOGICAL_TITLE_SOURCES` / force `matched=None` | MET | structure.py:954 unchanged; gather.py:897 unchanged |
| Test: anchored fixture adopts, exact strings, `sibling-align`, `matched` not None | MET | `test_sibling_transfer_adopts_into_a_bracketed_gap` |
| Test: fully-tagged show, no donor fetch | MET | `test_fully_tagged_tape_does_not_fetch_a_sibling_for_title_transfer` (CountingIA; gate pinned — see extra mutation E) |
| Test: ymsb2005 untagged -> zero adoptions | MET | `test_wholly_untagged_tape_gets_zero_automatic_sibling_adoptions` |
| Test: below-FLOOR donor -> no adoption + `sibling alignment declined (anchor agreement N%)` | MET | `test_below_floor_sibling_alignment_declines_with_a_note` |
| Test: C+-declined run stays unresolved, reason in notes | MET | `test_a_bracketing_failure_leaves_the_run_unresolved_with_its_reason_in_notes` |
| Test: shifted same-count donor does not transfer positionally | MET | `test_shifted_fully_tagged_sibling_does_not_transfer_positionally` |
| Step 4: census before/after | PARTIAL — see finding 3 |
| No scope creep | MET — `e34fda0` touches exactly the brief's 5 files; the extra `plans/*.md` line in the review range is a separate commit `2a5cfd0` (orchestrator's sizing-heuristic note), not the implementer's |

## Findings

1. **Important — the winning-donor tie-break is pinned by nothing.** Every one of the 8
   sibling fixtures appends exactly one donor recording, so `candidates.sort` is trivial.
   Proven, not asserted: inverting `_donor_key` to `(rank, -cost, identifier)` — i.e. the
   WORST-agreeing, highest-cost donor wins — leaves the entire llama suite green
   (`1227 passed`). This is the path that decides whose titles ship. See Q2 for the
   minimal fixture.
2. **Minor — TDD deviation** (self-disclosed): tests and implementation co-developed. See
   Q1; ruled discharged for the four named hazards, no residual defect found.
3. **Minor — Step 4's census has a "before" only.** Legitimately explained (no re-gather
   harness before Task 7, an "after" would need live archive.org), but the brief's wording
   ("record before/after counts") is not literally satisfied. Task 7 owns the after.
4. **Nit — the "byte-identical through gather" test** asserts titles + sources + fetch
   count, not byte-identity of the show artifact. Substantively equivalent; noted only so
   the wording isn't read as stronger than the pin.

## Invariants — explicit yes/no with evidence

- **`sibling-align` NOT in `TAUTOLOGICAL_TITLE_SOURCES`** — YES.
  `structure.py:954: TAUTOLOGICAL_TITLE_SOURCES = frozenset({"setlist-gap", "setlist"})`,
  unchanged in the diff.
- **`matched` NOT forced to None for sibling-aligned tracks** — YES. `gather.py:897`
  forces None only for `t.title_source in TAUTOLOGICAL_TITLE_SOURCES`, which
  `sibling-align` is not; `test_sibling_transfer_adopts_into_a_bracketed_gap` asserts
  `all(got[i].matched is not None for i in (2,3,4,5))`.
- **Transfer after the `overrides.titles` loop, before `adopt_gap_titles`** — YES.
  Line order 775 (overrides) -> 786 (`_sibling_transfer`) -> 819 (`adopt_gap_titles`). An
  override-forced title therefore carries `title_source == "override"`, is fed into
  `rate_alignment(rows, tracks)` as an anchor, and is protected from overwrite by the
  same `!= "unresolved"` guard.
- **`siblings.py` pure; all fetching in gather** — YES. `siblings.py` imports only
  `dataclasses`, `llama.structure`, `llama.titles`; no `ia`, no `stages/` import. The two
  `ia.metadata()` calls live in `gather._sibling_transfer`. `siblings.py` is untouched by
  this commit.
- **`cplus_filter` applied only in the `auto` band** — YES. `gather.py:181-190` returns
  early for `declined`/`operator`/`no-anchors`; the `cplus_filter` call at :192 is
  unreachable for any other band.
- **Adoption intersected with the unresolved set at application time** — YES.
  `gather.py:194-198` reads `tracks[pos].title_source != "unresolved": continue` against
  the pre-transfer list, writes into a copied `new_tracks`. Mutation D proves it is
  load-bearing.
- **Old rung fully removed** — YES. `_sibling_titles`, the `sibling_titles` parameter and
  the `elif sibling_titles and len(sibling_titles) == n` rung are all absent;
  `is_real_title` dropped from gather's imports and unused there.

## Mutation evidence

### A — add `"sibling-align"` to `TAUTOLOGICAL_TITLE_SOURCES` (structure.py:954)
RED: `test_sibling_aligned_matches_count_as_independent_coverage_evidence`
```
>       assert show.structure.coverage == 5 / 6
E       AssertionError: assert 0.5 == (5 / 6)
E        +  where 0.5 = StructureInfo(source='chosen', alignment='deterministic', coverage=0.5, conflicts=['Morning Dew', 'Space']).coverage
```
(`test_sibling_transfer_adopts_into_a_bracketed_gap` also goes red.) The number is
hand-checkable, not merely observed: 6 song-like tracks, 5 matching canonical items,
"Drums" not matching -> 5/6; under the mutation the denominator collapses to the 2
anchors with 1 match -> 0.5, below the 0.8 threshold. 2 failed, 1225 passed.

### B — bypass `cplus_filter` (`filtered = rows`)
RED: `test_a_bracketing_failure_leaves_the_run_unresolved_with_its_reason_in_notes`
```
>       assert [got[i].title_source for i in (3, 4, 5, 6)] == ["unresolved"] * 4
E       AssertionError: assert ['sibling-ali...ibling-align'] == ['unresolved'... 'unresolved']
E         At index 0 diff: 'sibling-align' != 'unresolved'
```
The brief demands failure **on title content**, and pytest stops at the source assertion
first, so I neutralised that one line and re-ran to expose the next:
```
>       assert [got[i].title for i in (3, 4, 5, 6)] == [got[i].filename for i in (3, 4, 5, 6)]
E       AssertionError: assert ['I Know You ...nny B. Goode'] == ['gd73-06-10d...-10d3t01.mp3']
E         At index 0 diff: 'I Know You Rider' != 'gd73-06-10d1t03.mp3'
```
Content acceptance satisfied: without C+, the declined track takes the donor's title.
1 failed, 1226 passed.

### C — BACKWARD: restore the OLD positional rung (`git show 83b4a19:` gather.py + titles.py)
RED: `test_shifted_fully_tagged_sibling_does_not_transfer_positionally`
```
>       assert [t.title for t in show.tracks] == [t.filename for t in show.tracks]
E       AssertionError: assert ['China Cat S...'Morning Dew'] == ['gd73-06-10d...-10d3t01.mp3']
E         At index 0 diff: 'China Cat Sunflower' != 'gd73-06-10d1t01.mp3'
```
The old rung ships the entire tape rotated one song over (track 1's true title is
"Morning Dew"), silently. The positional hole is genuinely closed.

### D — DATA LOSS: remove the unresolved-set intersection
RED: `test_an_already_titled_track_is_never_overwritten_by_a_surviving_adopt_row`
```
>       assert track2.title == "China Cat Sunflower"
E       AssertionError: assert 'Bertha' == 'China Cat Sunflower'
```
Names the clobbered title exactly: the tape's own tag `China Cat Sunflower` replaced by
the donor's `Bertha`. `test_sibling_aligned_matches_count_as_independent_coverage_evidence`
also goes red (`got[1].title_source == 'sibling-align'` where `'tags'` was expected).
2 failed, 1225 passed.

### E (extra, reviewer-added) — drop the fetch gate (`fetch_siblings = bool(kept)`)
RED: `test_fully_tagged_tape_does_not_fetch_a_sibling_for_title_transfer`
```
>       assert ia.calls.count(SIB_ID) == 1
E       AssertionError: assert 2 == 1
```
The loosened gate is pinned as a gate, not just as an outcome.

### F (extra, reviewer-added) — invert `_donor_key` to `(rank, -cost, identifier)`
**MUTATION DID NOT BREAK ANYTHING** — `1227 passed, 7 deselected`. Finding 1.

## Suite delta — itemised and confirmed independently

`git show`-diffed the test function names across `83b4a19..e34fda0`:
`test_stage_gather.py` -1/+8, `test_titles.py` -1/+1 => net +7, 1622 -> 1629. Matches the
report exactly.

- Removed `test_sibling_titles_are_cleaned`: exercised the old rung's happy path. Genuinely
  subsumed — the mechanism it tested no longer exists, its replacement happy path is
  `test_sibling_transfer_adopts_into_a_bracketed_gap`, and the defect it could not catch is
  now pinned by `test_shifted_fully_tagged_sibling_does_not_transfer_positionally`. The one
  incidental thing it also covered — id-prefixed tag cleaning — survives in
  `test_prefixed_tag_titles_align` (test_stage_gather.py) and `test_titles.py`'s own
  `clean_tag_title` tests. Nothing weakened.
- Removed `test_sibling_fallback_when_setlist_misaligned`: renamed in place and inverted to
  `test_resolve_titles_no_longer_has_a_sibling_fallback` (same fixture, opposite assertion,
  asserting `title_source == "unresolved"` and `tracks[0].title == "d1t01.mp3"`). Strictly
  stronger than a deletion. Nothing weakened.

## Q1 — does four verified mutations DISCHARGE red-first, or merely resemble it?

**Ruling: DISCHARGED for the four named hazards; NOT a general substitute for red-first.
Minor finding, accepted, no rework.**

First a factual correction to the framing: strict red-first is not in this plan's *Global
Constraints* block. It appears as each task's Step 1/Step 2 and via the required
subagent-driven-development/TDD sub-skill. The Global Constraint that *is* load-bearing
here is "**Acceptance is never a shape test** — every task's acceptance is a content-based
check on title strings, or a named mutation shown failing", and that constraint is fully
satisfied: three named mutations plus the orchestrator's data-loss one all go red, each on
a named test, and each failure is on a **title string** or a hand-checkable number, not on
shape.

Why it discharges rather than resembles, in this instance specifically. Red-first exists to
prevent a test being shaped to whatever the implementation happens to do. A mutation
discharges that same risk *for the property mutated* when two conditions hold, and both do
here: (a) the hazard was named **in the brief, before the implementation existed** — the
implementer did not choose which properties to prove; (b) the mutation is applied by an
**independent party** against a tree they did not write. A test that passes green and goes
red under an adversary's inversion demonstrably discriminates. That is the guarantee
red-first buys, obtained by a different route.

Where the concern the orchestrator raises — the gate that passed on shape while 13 of 22
titles were wrong; the fixture that reproduced the wrong mechanism — would bite is on
properties **nobody named**. And this run shows exactly that failure mode, live: the
donor tie-break has no mutation named for it, has no fixture, and is provably worth
nothing (mutation F). So the honest summary is that mutation coverage discharges
*fit-to-implementation* for what it covers and says nothing about *completeness*. Red-first
would not have caught the tie-break either — a happy-path test written first has the same
blind spot — so this is not a cost of the deviation; it is a cost of nobody enumerating
that hazard.

One residual I checked rather than assumed: the implementer's stated reason was that the DP
numbers were not hand-computable. If true in a load-bearing way, a wrong DP could have been
papered over by tuning the fixture until green. It is not: the adopted **title strings** in
every fixture are the real setlist in play order (hand-verifiable, and they are what the
acceptance asserts), and the single derived number, `coverage == 5/6`, is hand-derivable
from the fixture as shown under mutation A. The DP itself is Task 4's code under its own
mutations; Task 5's brief is the wiring, and the wiring is what the four mutations pin.

Do not read this as "mutations replace TDD generally". The deviation was real, was
disclosed, and the cost was borne — accept it here, and keep the enumerate-the-hazards
discipline, since that is the part actually doing the work.

## Q2 — is the untested tie-break an Important gap?

**Yes, Important** — and not on principle: mutation F proves the code has zero
discrimination there, and this is the path that decides **whose titles ship** onto a show.
It is also the only unguarded decision left in the pass: every other choice (band, C+,
unresolved intersection) has a mutation-verified pin.

**Minimal fixture** (one test, ~15 lines, no new fixture file), modelled on
`test_sibling_transfer_adopts_into_a_bracketed_gap`:

- Same target: tracks 1 and 6 tagged (anchors), tracks 2-5 stripped.
- **Donor A**, identifier `gd73-06-10.aud.a-loser` (sorts FIRST alphabetically, so the
  identifier tiebreak cannot accidentally produce the right answer): agrees with only one
  anchor — e.g. track 1 "Morning Dew", track 6 "Truckin'" — and proposes distinguishable
  interior titles `["Wrong Two", "Wrong Three", "Wrong Four", "Wrong Five"]`.
- **Donor B**, identifier `gd73-06-10.aud.z-winner`: agrees with both anchors and carries
  the true interior titles.
- Assert the adopted strings for tracks 2-5 are Donor B's `["China Cat Sunflower",
  "I Know You Rider", "Dark Star", "Eyes of the World"]` and that no `"Wrong "` string
  appears anywhere in `[t.title for t in show.tracks]`.

That pins the primary key (agreement) and rules out the identifier fallback deciding it.
A second, optional case pins the DP-cost tie: two donors at equal agreement, one with an
extra spurious file so its alignment carries a higher cost, asserting the lower-cost
donor's strings win. The first test alone closes the Important part; mutation F should go
red after it (`_donor_key` inverted -> "Wrong Two" adopted).

**Recommendation:** land the primary-key fixture in Task 5's fix round (small, additive,
no production change). It is not a blocker on shipped behaviour — the implementation
follows the spec's stated order — but leaving it green under a full inversion is exactly
the "half-loose constant" pattern this plan's own Global Constraints call out as a finding
against the tests rather than a shrug.
