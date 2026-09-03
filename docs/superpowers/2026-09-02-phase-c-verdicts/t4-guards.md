# Task 4 report — the guards: `loosely_same_title`, the ratio band, guard shape C+

**Status: COMPLETE.** Suite green, all four spec invariants held, all three named
acceptance mutations kill their named tests, every numeric bound pinned in both
directions.

## Pointer guard

`PTH-GUARD: OK` at start and again after every mutation run (the copies were driven
with `$WORKTREE/.venv/bin/python -m pytest` + `PYTHONPATH`, never a `.venv/bin/*`
console script; shadowing asserted per-mutant by `assert '<mut>/packages' in
llama.__file__`). `git status` clean; `__pycache__` purged from the copies.

## Commits

- `491088b` siblings: the ratio band and guard shape C+, by reuse — `structure.loosely_same_title` + `LOOSE_TITLE_RATIO`; `siblings.AUTO/FLOOR/MIN_ANCHORS/INDEPENDENT_TITLE_SOURCES`, `Disagreement`, `GuardResult`, `rate_alignment`, `cplus_filter`; 27 new tests.
- `8c78eb3` test(siblings): one assertion per wrong title in the localised-shift pin — split a compound assertion so mutations A and B each name the exact title they would ship.

## Test command and output tail

```
$ ./.venv/bin/pytest -q
1617 passed, 7 deselected, 26 warnings in 5.38s
```

Baseline 1590 → 1617, **+27, none removed, none renamed**: +8 in `test_structure.py`
(the comparator: normalized equality, containment both ways, the ratio case, the two
known-limit misses, two different songs, an empty side, the value pin) and +19 in
`test_siblings.py` (8 band-routing/anchor-definition, 8 C+ run-level, 3 localised-shift
and invariant-1 pins).

## Step 2 — failure output before implementing, verbatim

```
packages/llama/tests/test_siblings.py:403: in <module>
    from llama.siblings import (
E   ImportError: cannot import name 'AUTO' from 'llama.siblings' (/Users/shawn/projects/llama/.worktrees/sibling-transfer/packages/llama/src/llama/siblings.py)
___________ ERROR collecting packages/llama/tests/test_structure.py ____________
packages/llama/tests/test_structure.py:1887: in <module>
    from llama.structure import LOOSE_TITLE_RATIO, loosely_same_title
E   ImportError: cannot import name 'LOOSE_TITLE_RATIO' from 'llama.structure' (/Users/shawn/projects/llama/.worktrees/sibling-transfer/packages/llama/src/llama/structure.py)
=========================== short test summary info ============================
ERROR packages/llama/tests/test_siblings.py
ERROR packages/llama/tests/test_structure.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
2 errors in 0.11s
```

One test then failed on its own expectation rather than on the code (see Concerns 1):
`test_runs_decline_individually_...` expected track 5 — a *titled* track outside every
fill run — to be demoted. C+ gates fill runs; the expectation was wrong, and the
behaviour is now pinned deliberately by `test_cplus_says_nothing_about_a_track_that_
already_has_a_title`.

## The three named acceptance mutations

All run on out-of-worktree copies (`.../workc/t4-guards/mut-*`), shadowing proven.

### Mutation A — `gap_span` call replaced by one-sided bracketing

`span = gap_span(...)` replaced with: compute `left`/`right`, accept when
`left is not None or right is not None`, taking the run's own file count on the open
side. **4 failed, 181 passed.**

| failing test | verbatim assertion line |
|---|---|
| `test_a_tail_run_never_adopts_automatically` | `assert "Charlie" not in _adopted(out).values()` |
| `test_the_localised_shift_adopts_zero_interior_titles_under_cplus` | `assert "Hotel" not in adopted.values()        # bracketing catches 8-9` |
| `test_runs_decline_individually_one_unbracketed_run_does_not_sink_the_pair` | `assert _adopted(out) == {1: "Alpha", 2: "Bravo", 3: "Charlie",` (left had `{6: 'Foxtrot', 7: 'Golf'}` extra) |
| `test_a_disagreeing_anchor_does_not_bracket_even_though_it_is_titled` | `assert "Bravo" not in _adopted(out).values()` |

Both required tests fail. The reuse of `gap_span` is load-bearing, not decorative.

### Mutation B — count-forcing clause deleted

**2 failed, 183 passed.**

| failing test | verbatim assertion line |
|---|---|
| `test_a_run_whose_donor_span_holds_more_tracks_than_files_declines` | `assert _adopted(out) == {1: "Alpha", 5: "Foxtrot"}` (left had `{2: 'Bravo', 3: 'Charlie > Delta', 4: 'Echo'}` extra) |
| `test_the_localised_shift_adopts_zero_interior_titles_under_cplus` | `assert "Kilo > Xray" not in adopted.values()  # count-forcing catches 11` |

Both required tests fail, and the localised-shift fixture does reproduce the sweep's
finding: bracketing catches its runs 8-9, and **count-forcing alone catches the last
one** — track 11 is bracketed by two *agreeing* anchors and would otherwise ship
`"Kilo > Xray"` onto a file that holds one song.

### Mutation C — `MIN_ANCHORS = 1`

**2 failed, 183 passed.**

| failing test | verbatim assertion line |
|---|---|
| `test_a_single_agreeing_anchor_routes_to_the_operator_not_auto` | `assert res.band == "operator"` (got `"auto"`) |
| `test_a_setlist_gap_title_is_not_an_anchor` | `assert res.band == "operator"` (got `"auto"`) |

The named routing test fails. The second failure is a bonus: it proves the
setlist-gap-is-not-an-anchor test is a real band assertion, not a count assertion.

## Both-directions results for every numeric bound

Each cell is a mutant run on its own copy. **No bound is inert in either direction**,
and each is caught by a *behavioural* test, not only by its value pin.

| bound | direction | tests that die | verbatim line |
|---|---|---|---|
| `AUTO` 0.80 | ↑ 0.85 | `test_the_localised_shift_passes_the_ratio_band_the_ratio_is_blind` | `assert res.agreement == AUTO` |
| `AUTO` 0.80 | ↓ 0.65 | `test_agreement_below_auto_but_above_floor_routes_to_the_operator`, `test_the_localised_shift_passes_the_ratio_band...` | `assert res.band == "operator"` |
| `FLOOR` 0.50 | ↑ 0.75 | `test_agreement_below_auto_but_above_floor_routes_to_the_operator` | `assert res.band == "operator"` |
| `FLOOR` 0.50 | ↓ 0.10 | `test_agreement_below_floor_is_declined_outright` | `assert res.band == "declined"` |
| `MIN_ANCHORS` 2 | ↓ 1 (mutation C) | `test_a_single_agreeing_anchor_routes_to_the_operator_not_auto`, `test_a_setlist_gap_title_is_not_an_anchor` | `assert res.band == "operator"` |
| `MIN_ANCHORS` 2 | ↑ 3 | `test_two_agreeing_anchors_are_enough_for_the_automatic_band`, `test_an_override_title_anchors_the_guard_like_a_tag` | `assert res.band == "auto"` |
| `LOOSE_TITLE_RATIO` 0.80 | ↑ 0.85 | `test_loosely_same_title_accepts_a_spelling_variant_on_the_ratio`, `test_loose_title_ratio_is_the_measured_bound` | `assert loosely_same_title("Mister Charlie", "Mr. Charlie")` |
| `LOOSE_TITLE_RATIO` 0.80 | ↓ 0.75 | `test_loosely_same_title_misses_the_rain_go_away_near_miss_known_limit`, `test_loose_title_ratio_is_the_measured_bound` | `assert not loosely_same_title("Rain Please Go Away", "Rain go away (?)")` |

(`LOOSE_TITLE_RATIO` is not one of the three the brief named, but it is a numeric bound
in new code and part of the measured basis, so it got the same treatment. The two
known-limit cases turn out to be exactly the two-sided pin: 0.833 above, 0.774 below.)

## Invariant 1 — `cplus_filter` is called by nothing in the renderer path

`grep -rn "cplus_filter" packages/llama/src/llama/cli.py packages/llama/src/llama/
correspondence.py packages/llama/src/llama/stages/` → **NONE**. Repo-wide, the only
non-test occurrences are its definition in `siblings.py` and a docstring mention in
`structure.loosely_same_title`. The spec's own sentence is quoted verbatim in
`cplus_filter`'s docstring, and the invariant is pinned behaviourally by
`test_cplus_applied_to_the_display_would_blind_the_operator`: a wholly untagged tape
adopts `{}` while every row still carries its proposed title for the renderer.

`loosely_same_title` is likewise called only from `rate_alignment`/`cplus_filter` —
never from `align()` or `normalize_song`.

## Invariant 3 — reuse, not a second anchor definition

`cplus_filter` calls the **real** `structure.unresolved_runs` and
`structure.gap_span(anchors, lo, hi, len(tracks))`. There is no copy of the
leading-edge exception, no trailing-edge branch, and no re-derivation of either — the
mutation-A result is the proof: breaking the call breaks the tests. `anchor_spans`
itself is deliberately **not** called and the docstring says why: it binds tracks to
canonical setlist *items* by title matching, whereas here the binding is the DP's own
duration pairing. What is reused from it is the half-open span *shape*, which is what
lets `gap_span` be called with `donor_span`s unconverted.

The one arithmetic line that resembles `adopt_gap_titles` is count-forcing
(`span[1] - span[0] != files`). It is deliberately **not** factored into a shared
helper: spec invariant 2 says this instance is weaker and differently justified, and
warns that a later simplification "would naturally unify or borrow them and be wrong
both times". Both invariants are quoted at the definition.

## Invariant 4

Nothing here touches `TAUTOLOGICAL_TITLE_SOURCES`. `INDEPENDENT_TITLE_SOURCES`
(`tags`, `sibling-format`, `override`) is a separate frozenset with its own comment
explaining why `setlist`/`setlist-gap` and `sibling`/`sibling-align` are excluded from
*anchoring*; it makes no claim about alignment evidence.

## The localised-shift fixture

Built through the **real DP** (`propose_rows`) from durations, not hand-assembled rows:
13 target files against a 14-track donor. Tracks 1-5 tagged and correct; tracks 6-7
tagged one song forward (the shift); 8-9 and 11 unresolved; 10, 12, 13 tagged and
correct. Donor track 12 ("Xray", 95 s) is a donor-only segment the target's taper
dropped, and the DP absorbs it into target track 11 exactly as the module docstring
predicts, producing `donor_span=(10, 12)`, `proposed="Kilo > Xray"`, `verdict="adopt"`,
`penalty=100 s`.

- `rate_alignment` → `agreement == AUTO` (8/10), `n_anchors == 10`, `band == "auto"`,
  disagreements `{(6, "Golf", "Foxtrot"), (7, "Hotel", "Golf")}`. **The ratio is blind
  to the shift** — pinned as documentation, and the reason layer 2 exists.
- `cplus_filter` → adopts **zero** interior titles. Run 8-9 declines
  `"tracks 8-9: not bracketed by agreeing anchors"` (its left flank is a disagreeing
  anchor); run 11 declines `"track 11: donor span holds 2 tracks for a 1-file run"`.

## Concerns

1. **C+ says nothing about a track that already has a title, by design.** Rows outside
   an unresolved run keep `verdict="adopt"` — including a row on a *disagreeing* anchor
   (the tape says "Casey Jones", the sibling proposes "Echo"). That is safe only because
   the transfer fills `title_source == "unresolved"` tracks and nothing else. **Task 5
   must not write every adopt row onto its track**; it must intersect with the
   unresolved set, exactly as `adopt_gap_titles` does. Pinned by
   `test_cplus_says_nothing_about_a_track_that_already_has_a_title`, whose docstring
   states the consequence. I kept `cplus_filter`'s contract as briefed rather than
   widening it to demote those rows, since the briefed signature is per-run.
2. **`cplus_filter` returns rows only, so a run with no adopt rows records no reason.**
   The spec wants per-run decline reasons in `show.json` notes. A run whose rows were
   already declined at layer 3 (untitled donor, split song) carries its layer-3 reason
   instead of the C+ one — arguably correct, but if Task 5 wants a complete per-run
   audit it will need the run reasons returned separately rather than reconstructed from
   rows.
3. **`cplus_filter` does not itself check the band.** It is a pure run-level filter;
   gather must apply `rate_alignment` first and call C+ only in the `auto` band. Nothing
   in this module enforces the ordering.
4. **Anchors require the row to carry a proposal.** A tagged track the DP paired with an
   *untitled* donor track is not counted as an anchor at all (neither agreeing nor
   disagreeing), so an untitled donor cannot drag a correct alignment below FLOOR. This
   is a judgement I made from the spec's "over target tracks carrying a surviving real
   tag that the alignment paired" plus "agreement = fraction whose own title loosely
   matches the row's proposal"; if the measurement scorers counted such rows as
   disagreements, Task 7's numbers will differ slightly from the sweep. Pinned by
   `test_an_unpaired_tagged_track_is_not_an_anchor`.
5. **Fewer than `MIN_ANCHORS` anchors routes to `operator` even below FLOOR.** The
   spec says both "under it, operator path regardless of agreement" and "agreement <
   FLOOR: declined outright"; I resolved the overlap the way the brief orders the bands
   ("`operator` ≥ 0.50 **or** < 2 anchors" before "`declined` < 0.50") and documented the
   reasoning in `rate_alignment`'s docstring: over one anchor the ratio is not the
   measured statistic, so it may neither license adoption nor justify discarding the
   proposal. Worth a reviewer's eye — it is the one band-routing question the spec
   answers twice.

---

# Task 4 — FIX ROUND 1

**Status: COMPLETE.** All four Important findings addressed plus the spec reviewer's
Minor (finding 5). PTH-GUARD `OK` before and after. `./.venv/bin/pytest -q` →
**1622 passed, 7 deselected** (was 1617).

**Commit `f149111`** — siblings: fix round 1 — pin what the docstrings only claimed.

## Suite delta, case by case

**+5 added, 3 renamed, 0 removed, 1 re-fixtured.**

Added:
1. `test_a_single_disagreeing_anchor_routes_to_the_operator_not_declined` (finding 1)
2. `test_a_row_with_no_proposal_does_not_crash_the_guard` (finding 2, crash half)
3. `test_a_track_paired_with_an_untitled_donor_is_not_counted_as_an_anchor` (finding 2, denominator half)
4. `test_a_donor_span_slide_passes_the_ratio_band_with_perfect_agreement` (finding 4)
5. `test_a_donor_span_slide_adopts_zero_interior_titles_under_cplus` (finding 4)

Renamed (same fixture, same or stronger assertions — no case lost):
- `test_an_unpaired_tagged_track_is_not_an_anchor` → `test_a_track_the_dp_paired_with_nothing_is_not_an_anchor`
- `test_the_localised_shift_passes_the_ratio_band_the_ratio_is_blind` → `test_a_tape_tag_shift_passes_the_ratio_band_the_ratio_is_blind`
- `test_the_localised_shift_adopts_zero_interior_titles_under_cplus` → `test_a_tape_tag_shift_adopts_zero_interior_titles_under_cplus`
- (helper `_localised_shift` → `_tape_tag_shift`)

Re-fixtured, name unchanged: `test_cplus_leaves_a_layer_three_decline_reason_alone`.

## Every hollow pin, killed by the reviewer's own mutant

Each run on its own out-of-worktree copy (`.../workc/t4-guards/mut-*`), shadowing
asserted per run (`assert '<mut>/packages' in llama.__file__`), `__pycache__` purged,
driven by `$WORKTREE/.venv/bin/python -m pytest` + `PYTHONPATH`. Every mutant was run
over the **whole** `packages/llama/tests/` tree, so "1 failed, 1219 passed" means the
new test is the only thing standing between the mutation and a green suite.

| finding | mutant (reviewer's, verbatim) | before | after | red test | verbatim line |
|---|---|---|---|---|---|
| 1 | **D** — `declined` moved above the anchor-count clause | 1215 passed, **0 failed** | **1 failed**, 1219 passed | `test_a_single_disagreeing_anchor_routes_to_the_operator_not_declined` | `assert res.band == "operator"` |
| 2 | **H** — delete `and bool(row.proposed)` | 1215 passed, **0 failed** | **2 failed**, 1218 passed | `test_a_row_with_no_proposal_does_not_crash_the_guard` and `test_a_track_paired_with_an_untitled_donor_is_not_counted_as_an_anchor` | `E AttributeError: 'NoneType' object has no attribute 'replace'` |
| 2 | **H2** — mine: drop the clause but make the comparison `None`-safe (no crash, denominator widened) | n/a | **1 failed**, 1219 passed | `test_a_track_paired_with_an_untitled_donor_is_not_counted_as_an_anchor` **only** | `assert res.n_anchors == 1                   # track 1 only, not track 2` |
| 3 | **E** — delete `r.verdict == "adopt"` from the final comprehension | 1215 passed, **0 failed** | **1 failed**, 1219 passed | `test_cplus_leaves_a_layer_three_decline_reason_alone` | `assert by[3].reason == "sibling track untitled"      # layer 3 survives` |

H2 is the point of splitting finding 2 into two tests, demonstrated rather than
asserted: it preserves the no-crash behaviour (the crash test stays green) while
changing the anchor denominator, and only the denominator test dies. Under H alone
both go red by `AttributeError`, because the crash precedes the count.

## The three named acceptance mutations, re-run after the renames

| mutation | result | named tests that die |
|---|---|---|
| **A** one-sided bracketing | 5 failed, 1215 passed | `test_a_tail_run_never_adopts_automatically` (`assert "Charlie" not in _adopted(out).values()`) and `test_a_tape_tag_shift_adopts_zero_interior_titles_under_cplus` (`assert "Hotel" not in adopted.values()`) — the test the brief called "the localised-shift test", renamed per finding 4. Plus 3 others, now including the re-fixtured layer-3 test. |
| **B** count-forcing deleted | 3 failed, 1217 passed | `test_a_run_whose_donor_span_holds_more_tracks_than_files_declines` (`assert _adopted(out) == {1: "Alpha", 5: "Foxtrot"}`), `test_a_tape_tag_shift_adopts_zero_interior_titles_under_cplus` (`assert "Kilo > Xray" not in adopted.values()`), and the new `test_a_donor_span_slide_adopts_zero_interior_titles_under_cplus` (`assert "Echo" not in adopted.values()`) |
| **C** `MIN_ANCHORS = 1` | 3 failed, 1217 passed | `test_a_single_agreeing_anchor_routes_to_the_operator_not_auto` (`assert res.band == "operator"`), plus the new disagreeing-anchor test and `test_a_setlist_gap_title_is_not_an_anchor` |

**Mapping for the acceptance record:** the brief's "localised-shift test" is
`test_a_tape_tag_shift_adopts_zero_interior_titles_under_cplus` — same fixture, same
assertions, renamed only. It still dies under A and B as required.

## Finding 4 — I built the donor-span slide, and it took a compromise worth naming

`_donor_span_slide` is built through the real DP (`propose_rows`) from durations, and
it does reproduce the spec's class:

- 9 target files, 10-track donor. **Every tape tag is correct**, all 6 anchors agree,
  `rate_alignment` returns `agreement == 1.0`, `band == "auto"` — the ratio has
  nothing to object to at all, which is sharper than the tag-shift fixture's
  exactly-AUTO blindness.
- The donor's track 5 ("Echo") is cut from the target. The three interior files pair
  one donor track early: spans `(4,5)`, `(5,6)`, `(6,8)` proposing `"Echo"`,
  `"Foxtrot"`, `"Golf > Hotel"` where the fixture's declared truth is Foxtrot, Golf,
  Hotel. **Three wrong titles, all `adopt` rows**, exclusion penalties 406 / 406 /
  240 s — layer 3 sees nothing wrong, because each pairing genuinely is the best
  explanation of the durations.
- Bracketing cannot catch it (both flanks correct and agreeing). Count-forcing does:
  the donor span holds 4 tracks for a 3-file run. Mutation B ships all three.

**A structural point that fell out and is worth keeping:** if both flanking anchors
are right *and* the span count equals the file count, the interior is forced and
cannot slide. So a donor-span slide **always** presents as a count mismatch — a
donor-side skip or a merge inside the run. That is why mutation A structurally cannot
kill this test and mutation B must, and it is the count-forcing clause's real safety
argument in this layer (distinct from `adopt_gap_titles`', as spec invariant 2
insists).

**The compromise, stated in the fixture's docstring and here.** Forcing a slide
through an L1 duration cost requires the target's songs to differ from the donor's by
*minutes*, which is not credible tape-to-tape drift. I tried the credible mechanism
first — several adjacent songs of near-equal length with one missing from the target
(donor `[300, 305, 298, 302]`, target `[306, 299, 303]`) — and **it never reaches
C+**: with near-equal durations every rival pairing is nearly as cheap, so exclusion
penalties collapse to **2–18 s** against `MIN_EXCLUSION_PENALTY = 60`, and layer 3
declines the rows first. The full run is in the log. The ambiguity that lets an
alignment slide is the same quantity the penalty measures, so the two mechanisms pull
against each other: a slide is either duration-implausible (my fixture) or
penalty-ambiguous (declined before C+).

Per the orchestrator's instruction I am reporting this rather than investigating it.
**The question for Task 7's blind arm:** does a donor-span slide with high anchor
agreement *and* forced pairings actually occur in the corpus, or is it an artifact of
the synthetic prefix-mask arm where the sweep saw it once at agreement exactly 0.80?
Two of the three ways to produce one are now known to be self-limiting — layer 3
catches the near-equal-duration form, and the implausible-drift form is what I had to
synthesise. If the blind arm finds none, C+'s primary justification rests on the
tag-shift class (where it is doing real work) plus the merge case, and the count-forcing
yield cost (4–17%) should be re-read against that.

## Finding 5 — one definition of an agreeing anchor

`_anchor_agrees(track, row)` in `siblings.py`, called by both `rate_alignment` (to
count agreement) and `cplus_filter` (to build the bracket set). Nothing was logically
duplicated before, which is exactly the shape of Task 3's drift: a change to what
agreement means in layer 1 would silently not have reached layer 2.

## Not done (deferred by the orchestrator to the final review)

`tracks: list` untyped in the public signatures; the unstated positional contract
between `rows` and `tracks`; the vacuous second assertion in
`test_cplus_says_nothing_about_a_track_that_already_has_a_title`.

## Concerns

The five Task-5 concerns from the first report stand unchanged; the reviewer confirmed
all five and upgraded #4, whose clause is now pinned twice. One addition:

6. **The donor-span-slide class may be thinner than the guard's design assumes** — see
   finding 4 above. This is a question for Task 7's blind arm, not a defect here.
