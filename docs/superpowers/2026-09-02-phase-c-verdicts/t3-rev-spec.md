# SPEC ✅ — Task 3 (`siblings.py`), spec-compliance review

Pointer guard `OK` before and after (`llama.__file__` inside the worktree).
Worktree `git status --porcelain` empty; no commits made. All mutation work on
a copy at `…/scratchpad/workc/t3-rev-spec`, driven by
`$WT/.venv/bin/python -m pytest` with `PYTHONPATH` at the copy; shadowing
proven with a planted `SENTINEL_MARKER` (`module file:` resolved to the copy,
`sentinel: copy-is-live`); `__pycache__` purged before and after every run.
Baseline on the copy: **1587 passed, 7 deselected**.

## Brief requirements, one line each

| Requirement | Verdict | Location |
|---|---|---|
| `DonorTape` fields (identifier/names/durations/titles) | MET | `siblings.py:76-92` |
| `SiblingRow` fields (track/proposed/donor_span/residual_sec/penalty_sec/verdict/reason) | MET, exact | `siblings.py:95-131` |
| `align_durations(target, donor, forbid)` signature + `(cost, ops)` | MET | `siblings.py:151-217` |
| Ops: `min(a,b)==1`, `max<=MAX_MERGE`, cost `abs(Σa−Σb)` | MET | `siblings.py:197-208` |
| Skip cost = the skipped duration | MET | `siblings.py:184-195` |
| Forbid-and-resolve exclusion penalty | MET | `siblings.py:186,190,201` + `264-266` |
| `propose_rows(..., *, metadata_norms)` signature | MET | `siblings.py:220` |
| Whole-tape preconditions: complete durations both sides | MET | `siblings.py:245-250` |
| Whole-tape precondition: `MIN_MATCH_FRACTION` | MET | `siblings.py:256-261` |
| **No whole-donor tag-fraction gate** | MET — grepped: no `MIN_SIB_TAGGED`/`MIN_SIB_DUR`; untitled donor declines only its own row (`siblings.py:284-287`), pinned by `test_an_untitled_donor_track_declines_only_its_own_row` | |
| Per-row `penalty < 60` → decline `weak evidence` | MET | `siblings.py:291-295` |
| Donor song split across target files → those rows decline | MET | `siblings.py:274-280` |
| Hygiene by IMPORT, not copy (`is_real_title`/`is_junk_title`/`MAX_TITLE_LEN`/no trailing `:`/`metadata_norms`) | MET — `from llama.setlist import MAX_TITLE_LEN, is_junk_title`, `from llama.titles import is_real_title`, `from llama.structure import fuzzy_norm_title` (`siblings.py:40-42`); composed at `133-149`; no predicate reimplemented | |
| **PURE** — no IO, no LLM, no `stages/` import | MET — the module's ONLY imports are `dataclasses` + those three pure `llama` modules (verified by grepping every `import` line, not by assumption) | `siblings.py:36-42` |
| Constants at module top with do-not-retune comment citing the Task-7 evidence doc by name | MET — one block header cites `docs/superpowers/2026-09-02-sibling-transfer-evidence.md` and covers all four; each constant carries its own rationale comment | `siblings.py:47-79` |
| A count in a comment names its UNIT | MET — "up to **3 of the other tape's songs**", "~4 **s**", "~90 **s**", "at least this **fraction** of the target's tracks" | |
| Acceptance assertions are on title STRINGS, not counts | MET — every adoption case asserts exact strings; the only counts are verdict lists beside them | |
| Full suite green, nothing removed/weakened | MET — diff is `+626 / -0`, two NEW files only; 1568 → 1587 = +19 = the 19 `def test_` in the new file | |

### The brief's enumerated cases, all eight present

1. 1:1 adoption string-by-string — `test_one_to_one_alignment_adopts_the_donors_titles_string_by_string` (five exact strings).
2. Merged pairing proposes `"Alpha > Bravo"` exactly — `test_a_merged_target_file_proposes_the_segue_join:122`.
3. A2-shaped — `test_a2_deleted_donor_head_track_declines_the_orphan_and_keeps_the_rest`: orphan declines with reason `"no sibling track"`, and **four** post-deletion titles by exact string (brief asked for ≥3).
4. A3-shaped — `test_a3_deleted_donor_middle_track_…`, same property, four exact strings.
5. Near-ambiguous — `test_near_ambiguous_pairing_declines_on_weak_evidence` (fixture substituted; adjudicated below).
6. Untitled donor track — `test_an_untitled_donor_track_declines_only_its_own_row` (67 %-tagged donor, neighbours adopt).
7. Donor split — `test_a_donor_song_split_across_target_files_declines_those_rows`.
8. Metadata-norm hygiene — `test_a_donor_track_titled_with_show_metadata_fails_hygiene`.

## Mutation evidence

### Mutation 1 — positional transfer (required)

Applied on the copy: the entire ops-driven row loop in `propose_rows` replaced by
`for i in range(len(target_durs)): t = donor.titles[i] …` (hygiene and the
untitled check kept, so the mutant is as strong as the old rung was).

Command:
`PYTHONPATH=$C/packages/llama/src:… $WT/.venv/bin/python -m pytest packages/llama/tests/test_siblings.py -q`

Result: **6 failed, 13 passed**. The named test went red:

```
FAILED packages/llama/tests/test_siblings.py::test_a2_deleted_donor_head_track_declines_the_orphan_and_keeps_the_rest
>       assert got[1].verdict == "decline"
E       AssertionError: assert 'adopt' == 'decline'
E         - decline
E         + adopt
packages/llama/tests/test_siblings.py:147: AssertionError
```

Also red: `test_a3_…` (`assert 'Alpha' == 'Alpha > Bravo'`, line 166),
`test_a_merged_target_file_proposes_the_segue_join` (line 122),
`test_near_ambiguous_pairing_declines_on_weak_evidence`,
`test_a_donor_song_split_across_target_files_declines_those_rows`,
`test_the_exclusion_penalty_is_what_the_best_rival_explanation_costs`.
(The implementer reported 7; I get 6 because my mutant kept per-title hygiene,
so the metadata-norm test survives. Immaterial — the named pin fired.)

### Mutation 2 — `MIN_EXCLUSION_PENALTY = 0.0` (required)

`sed -i '' 's/^MIN_EXCLUSION_PENALTY = 60.0$/MIN_EXCLUSION_PENALTY = 0.0/'`,
then the FULL suite: **1 failed, 1586 passed, 7 deselected**.

```
FAILED packages/llama/tests/test_siblings.py::test_near_ambiguous_pairing_declines_on_weak_evidence
>       assert got[1].verdict == "decline"
E       AssertionError: assert 'adopt' == 'decline'
E         - decline
E         + adopt
packages/llama/tests/test_siblings.py:194: AssertionError
```

Exactly one test, the intended one — the constant is pinned by the case that
measures it and nothing else leans on it.

### My own probes

| Mutation | Result |
|---|---|
| `span = (j0+1, j1+1)` (1-based) | **3 failed** — `test_donor_span_is_half_open_and_zero_based_while_track_is_one_based` (`assert (1, 2) == (0, 1)`), `test_a_merged_target_file_proposes_the_segue_join` (`assert (1, 3) == (0, 2)`), `test_a_donor_song_split_…` |
| `span = (j0, j1-1)` (inclusive) | **3 failed**, same three |
| `MAX_MERGE = 1` | 5 failed |
| `MAX_MERGE = 4` | 1 failed (`test_too_few_matched_tracks_declines_the_whole_pair`) |
| `MAX_MERGE = 2` | **1185 passed — BREAKS NOTHING** (finding F1) |
| `MIN_MATCH_FRACTION = 0.0` | 1 failed |
| `SKIP_COST_MULT = 2.0` | 4 failed |
| Add an arm to `structure._hygienic` outside the 14-case table (`not t.endswith("!")`) | **19 passed — BREAKS NOTHING** (finding F2) |

## Span convention: PINNED, not merely documented

`donor_span` is half-open over **0-based** donor indices, matching what
`structure.anchor_spans`/`gap_span` return, so Task 4's bracketing guard needs
no conversion. It is pinned three ways, and both directions of confusion go
red: shifting to 1-based and collapsing to inclusive each break the same three
tests, named above. `test_donor_span_is_half_open_and_zero_based_while_track_is_one_based`
asserts `(0,1)/(1,2)/(2,3)` on a 3-track 1:1 tape; the merged test asserts
`(0,2)`; the split test asserts `(0,1)` on both split rows. The asymmetry
(1-based `track`, 0-based span) is stated in the `SiblingRow` docstring, and
the docstring's "spans do not partition the donor when a split is present — do
not sum them" is exactly the trap Task 4 could otherwise fall into.

## Findings

- **F1 (Minor).** `MAX_MERGE = 3` is a do-not-retune constant whose value is
  only half-pinned: `1` and `4` both break tests, but retuning **3 → 2** is
  invisible (no fixture exercises a 3-way merge). A future "simplification"
  downward would pass green while invalidating the Task-7 evidence the comment
  cites. Cheap fix: one fixture with a 1:3 pairing. Not blocking.
- **F2 (Minor).** The anti-drift pin
  `test_hygiene_matches_structures_own_predicate_exactly` is only as strong as
  its 14-case table. Demonstrated: adding an arm to `structure._hygienic`
  (`not t.endswith("!")`) leaves all 19 sibling tests green — the drift the
  test exists to catch is invisible outside the enumerated cases. See concern 3.
- **F3 (Minor, informational).** Two branches in `propose_rows` are dead:
  `penalty = … if alt != INF else INF` and the `cost == INF` → `"no legal
  alignment"` guard. `align_durations` can only return `INF` when a *skip* op
  is forbidden, and `propose_rows` only ever forbids pairing ops. Both are
  honestly documented as unreachable. See concern 1.
- **No scope creep.** `git diff --stat 0548092..ce80541` = two new files,
  `+626 / -0`. No existing test removed, rewritten, skipped or weakened.
- **No spec-invariant violation.** Purity, hygiene-by-reuse and
  per-item-not-per-donor all verified by reading the code, not by assumption.

## The three concerns, adjudicated independently

1. **`penalty_sec = inf` unreachable, branch kept, pin displaced — ACCEPTABLE.**
   I verified the unreachability myself rather than taking it on report:
   `align_durations` returns `INF` only if `dp[n][m]` is `INF`, and the skip
   ops that make every cell reachable are barred only when they equal `forbid`
   — which `propose_rows` never sets to a skip. So the branch cannot fire from
   this caller. Keeping it is right: the field is part of the published
   interface, the value is well-defined, and a Task-4/5 caller that forbids
   differently would reach it. What matters is that the displacement did not
   cost coverage, and it did not — the substituted
   `test_the_exclusion_penalty_is_what_the_best_rival_explanation_costs` pins
   the penalty's *meaning* (a lone pairing's only rival is "skip both sides",
   so penalty = 600 s = the two skipped durations) and is genuinely load-bearing:
   it went red under mutation 1 and under `MAX_MERGE=1`. A test asserting an
   unreachable `inf` would have been a fiction. Recorded as F3, not a defect.

2. **Substituted near-ambiguous fixture — SOUND, and I verified the mechanism
   numerically rather than trusting the claim.** Running the brief's own sketch
   (two adjacent 300 s songs both sides) through the shipped code gives
   penalties of **600.0 on every row, all `adopt`** — it cannot exercise the
   sub-60 path at all, because barring a 1:1 op forces a skip on both sides and
   the rival explanation costs about a whole track. The shipped fixture (25 s
   donor fragment, 10 s drift) gives **penalty 20.0 on rows 1 and 2, `decline`,
   reason `weak evidence`, while rows 3 and 4 adopt `"Charlie"`/`"Delta"` by
   exact string**. 20 sits strictly between 0 and 60, which is precisely what
   makes mutation 2 discriminating — a fixture at 0 would flip on nothing and a
   fixture at 600 would never flip. The substitute also matches the constant's
   own stated mechanism (boundary drift vs. a song's length) better than the
   brief's sketch did. Deviation approved; the brief's sketch is the thing that
   was wrong.

3. **Composed hygiene + 14-case equality table vs. importing `_hygienic` —
   the implementer FOLLOWED THE BRIEF, and I would keep it, with a caveat.**
   The brief is explicit ("import from `setlist`/`titles`, do not copy"), and
   the code does exactly that: every predicate is imported, only the *shape* of
   the conjunction is restated. The docstring argument for not importing
   `_hygienic` is the weakest part of the case — a docstring sentence is
   editable, and siblings' adoption is not silent anyway (Task 4's guard sits
   above it) — but the stronger argument stands on its own: `_hygienic` is
   private to `structure`, and importing a private from a second module is a
   coupling the brief deliberately avoided. The caveat is F2: the table pin is
   real but bounded, and I demonstrated an arm added to `_hygienic` slipping
   past it. Recommendation for Task 7 (not blocking): lift the shared predicate
   into a public helper both modules call, or note in the spec that the table is
   the drift budget.

**Verdict: SPEC ✅.** Both named mutations reproduce independently with the
named tests and verbatim assertions; the span convention is pinned in both
directions; every enumerated brief case exists and asserts strings; the three
binding invariants (purity, hygiene-by-reuse, per-item-not-per-donor) hold; no
scope creep. Three Minor findings, none blocking.
