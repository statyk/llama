# Task 6 — SPEC COMPLIANCE REVIEW

**SPEC ✅** (approved with 1 Important and 4 Minor findings; no missing requirement, no scope creep)

Pointer guard: `PTH-GUARD: OK`. Worktree untouched (`git status --porcelain` empty at end).
All mutation work on the shadowed copy `…/workc/t6-rev-spec`, shadowing proven by planted
sentinel (`llama.cli.__file__` = copy path, `SENTINEL_T6_REV_SPEC = "copy"`), `__pycache__`
purged before and after every run, `./.venv/bin/python -m pytest` only, never `.venv/bin/pytest`.

## Brief requirement → verdict

| Brief requirement | Verdict | Evidence |
|---|---|---|
| Entry seam before the canonical DP in `_propose_titles_for_show` | ✅ | cli.py:1504-1511 — `_sibling_proposal(...)` called after `build_canonical`, before `propose_titles` |
| Donors loaded exactly as gather does (one definition, factored) | ✅ | `gather.load_donor_tapes` extracted (gather.py:121-169) and called from both `_sibling_transfer` (gather.py:~215) and `cli._sibling_proposal` (cli.py:1361) |
| Accept `operator`/`auto`/`no-anchors`; `declined`/no donor → fall through unchanged | ✅ | cli.py:1376-1377; `rate_alignment` has exactly 4 bands (siblings.py:380), so no band is unhandled |
| Renderer never calls `cplus_filter`, spec sentence at call site | ✅ | see Invariant section |
| `ProposalRow.residual_sec` / `note`; `evidence="sibling-align"` | ✅ | models.py:333-343; cli.py:1379-1385 |
| `TitleProposal.evidence_source = "sibling-align"` | ✅ | models.py:371; cli.py:1386 |
| Declined runs printed with reason, not silent holes | ✅ (with Minor 3) | cli.py:1324-1327; observed under mutation A: 24 rows each `(unresolved - hand-edit) [tracks 1-24: not bracketed by agreeing anchors]` |
| Three-way disagreement `tape / sibling / setlist` | ✅ | cli.py:1394-1400; asserted per-track in `test_delmccoury_shaped_operator_band_confirms_only_unresolved_rows` for t4/t8/t10/t12 with all three strings |
| no-anchors: donor id + embed-in-canonical coverage + head-row caution | ✅ (with Minor 5) | cli.py:1401-1406; live render: `embeds in canonical setlist: 0/24 (0%)` + caution line |
| Confirmation path unchanged (`_propose_and_confirm_titles`, overrides write, redo-from-gather) | ✅ | diff touches no other cli.py hunk; only two hunks in cli.py |
| C1 staleness guard fires before donor work | ✅ | guard at cli.py:~1497 returns before `build_canonical` **and** before `_sibling_proposal`; `test_suggest_titles_c1_staleness_guard_still_fires_before_donor_work` also asserts `"proposal (" not in result.output` |
| Triage `[t]` inherits, one test | ✅ | `test_suggest_titles_sibling_arm_shares_the_triage_seam` (test_triage.py) — asserts `sibling-align` and the exact merged title `{9: "Song 09a > Song 09b"}` |
| Untagged fixture ≥3 exact titles incl. merged `A > B` + residual column | ✅ | `assert ov.titles[1] == "Song 01"`, `ov.titles[9] == "Song 09a > Song 09b"`, `ov.titles[24] == "Song 24"`, `re.search(r"\b0s\b", ...)` |
| Below-FLOOR + no usable canonical → existing decline path unchanged | ✅ | `test_below_floor_donor_with_no_usable_canonical_declines_unchanged` |
| Below-FLOOR + usable canonical → DP, pinned on `evidence_source` | ✅ | `test_below_floor_donor_with_usable_canonical_falls_through_to_dp` asserts `"sibling-align" not in output` and `proposal (duration-model)`/`(sibling-duration)` present |
| Confirmation writes the EXACT `overrides.titles` dict, anchors never written | ✅ | see below |
| Suite 1632 → 1639 (+7), nothing removed/weakened | ✅ | diff has zero deleted test lines (all `-` lines are models.py comment rewrites + the gather block moved into `load_donor_tapes`); 7 new test functions, itemised in the report and present in the diff |

`evidence_source` distinctness: `"sibling-duration"` is still produced independently at
`correspondence.py:26` and is a separate value from `"sibling-align"` (models.py:371). The two
render through different formatters — `_format_proposal_row` (margin/forced column) vs
`_format_sibling_proposal_row` (residual column, `[note]` suffix) — and different header lines
(`proposal (duration-model)` vs `proposal (sibling-align, donor …, band …)`).

## Invariant: the renderer never calls `cplus_filter`

Verified three ways, none of them by trusting the comment:

1. `grep -rn "cplus_filter" packages/llama/src/` — 9 hits: definition `siblings.py:474`, one comment
   `siblings.py:312`, one comment `structure.py:209`, import + 3 docstring/comment mentions + the
   **only call** `gather.py:242` (`filtered = cplus_filter(rows, tracks)`), and `cli.py:1349`.
2. **AST proof (stronger than grep):** parsing `cli.py` with `ast` and walking for every
   `Call`/`Name`/`Attribute` named `cplus_filter` returns `[]`. The single textual occurrence at
   cli.py:1349 is inside `_sibling_proposal`'s docstring — the parser sees a string constant, not a
   name — and cli.py imports nothing named `cplus_filter` (`ast.Import`/`ImportFrom` scan: no hits).
   cli.py's import from gather is exactly `_donor_key, _show_metadata_norms, load_donor_tapes`, none
   of which reaches C+.
3. **Behavioural proof:** the live untagged render prints all 24 rows with titles (captured below),
   which is the opposite of what C+ produces on a zero-anchor tape.

The spec sentence IS at the call site, cli.py:1349-1355, quoted from spec §"Two invariants on C+"
item 1 (`docs/…/2026-09-02-sibling-title-transfer-design.md:353-360`).

## Mutation evidence

### Mutation A — renderer applies `cplus_filter`
Inserted after the band gate in `_sibling_proposal`:
```python
from llama.siblings import cplus_filter        # MUTATION A
rows = cplus_filter(rows, show.tracks)         # MUTATION A
```
Command:
`PYTHONPATH=<copy>/packages/llama/src:…/herder/src:…/emcee/src ./.venv/bin/python -m pytest <copy>/packages/llama/tests/test_cli.py <copy>/packages/llama/tests/test_triage.py -q -p no:randomly`

Result: **3 failed, 65 passed** (baseline on the same copy: 68 passed).
- `test_untagged_fixture_with_tagged_donor_renders_sibling_proposal` — verbatim:
  `test_cli.py:864: KeyError: 1` (`assert ov.titles[1] == "Song 01"`; `overrides.titles` empty)
- `test_delmccoury_shaped_operator_band_confirms_only_unresolved_rows`
- `test_suggest_titles_sibling_arm_shares_the_triage_seam` (triage seam killed too)

The table under the mutant is **holed exactly as predicted** — all 24 rows became
`(unresolved - hand-edit)  [tracks 1-24: not bracketed by agreeing anchors]`, coverage line
degraded to `0/0 (n/a)`, and the run ended `nothing to adopt: every track already has a title`.
This is the untagged tape shown nothing, i.e. the exact hazard spec invariant 1 names.

### Mutation B — canonical DP runs first
Swapped the arm order in `_propose_titles_for_show` so `propose_titles` runs first and
`_sibling_proposal` is consulted only when the DP is infeasible.

Result: **1 failed, 67 passed** — `test_operator_band_sibling_titles_diverge_from_the_canonical_dp`,
verbatim first failure at `test_cli.py:916`:
`AssertionError: assert 'band operator' in 'ymsb2005-12-31: proposal (duration-model)\n   1.   8:45   274s  Granny Woncha Smoke Some > Ride The Wild Turkey\n   2...'`

### Verdict on the implementer's mutation-B structural claim: **both halves confirmed, one wording correction**

(i) *The untagged fixture cannot catch mutation B.* **True, verified independently.** I ran a probe
that monkeypatched `cli._sibling_proposal` to return `None` on the untagged fixture and captured the
canonical DP's own verdict:
`ymsb2005-12-31: the setlist cannot be pinned to tracks 1-24: no track with a title of its own brackets that run, so nothing fixes where in the setlist it starts (25 canonical items vs 24 song-like tracks …)`
— i.e. the DP is infeasible on that fixture irrespective of arm order, so the test passes under the
mutant (it did: the untagged test was green under mutation B). **Wording correction:** the cause is
not solely "`gap_span` has no trailing-edge branch". A wholly-untagged tape has *zero* anchors, so
`gap_span` (structure.py) fails **all** its branches — `left and right`, and the leading-edge
`right is not None and lo == 0` — because there is no anchor anywhere. The absent trailing-edge
branch is one of three reasons, not the reason. The conclusion (structurally impossible on that
fixture, not a defect the implementer introduced) is nevertheless correct.

(ii) *The second fixture catches it on title content, not just the band string.* **True, verified by
mutation.** I neutralised `assert "band operator" in result.output` in that test and re-ran under
mutation B. It still fails, now on the exact-dict content assertion at `test_cli.py:918`:
`AssertionError: assert {5: 'Steep Gr...Crooked Horn'} == {5: 'Placehol...aceholder 20'}`
— the canonical DP's real titles vs the sibling arm's placeholders. This is a genuine title-content
kill. The test additionally pins the divergence structurally:
`assert set(ov.titles.values()).isdisjoint(ANCHORED_GAPS.values())`.

## The exact `overrides.titles` dict the confirmation test asserts

`test_delmccoury_shaped_operator_band_confirms_only_unresolved_rows`:
```python
assert ov.titles == {14: "Beaumont Rag", 15: "Sally Goodin"}
```
Exact-dict equality, not a shape test. 13 anchor tracks — including the 4 deliberately disagreeing
ones (t4 Dire Wolf, t8 Casey Jones, t10 Ripple, t12 Loser), whose sibling rows also carry an
`adopt` verdict — are excluded by the equality, so **anchors are provably never written**. The gate
that does it is cli.py:1408-1409 (`show.tracks[r.index - 1].title_source == "unresolved"`), the same
gate the canonical DP's own picks use (cli.py:1531).

Also exact-dict asserted: `ov.titles == ANCHORED_GAPS` (fall-through test) and
`ov.titles == {5: "Placeholder 5", 14: "Placeholder 14", 20: "Placeholder 20"}` (mutation-B test);
`ov.titles == {}` in both the C1 and no-usable-canonical tests.

## Live render (unmutated copy, untagged fixture) — invariant 1 in the output

```
ymsb2005-12-31: proposal (sibling-align, donor ymsb2005-12-31.aud.sibling, band no-anchors)
   1.   8:45     0s  Song 01
   …
   9.  12:30     0s  Song 09a > Song 09b
   …
  24.   6:35     0s  Song 24
  no independent anchors on this tape -- donor ymsb2005-12-31.aud.sibling, embeds in canonical setlist: 0/24 (0%)
  caution: check track 1 by ear before confirming -- the one measured miss on this path was a head-banner title shifted onto the tape's first track
```
All 24 rows render with zero anchors; the merged `A > B` row is real DP output (the donor's 12:30
file was split into 400 s + 350 s, so no positional transfer can produce it).

## Findings

### Important
1. **cli.py:1408-1410 — the sibling arm preempts the canonical DP even when it produces zero picks.**
   `_sibling_proposal` returns `(prop, picks)` unconditionally once the band is accepted. If a donor
   reaches the `operator` band but every row covering the tape's *unresolved* tracks declines (donor
   track untitled, split-across-files, weak evidence), `picks` is empty and the operator gets
   `nothing to adopt: every track already has a title` — with the canonical DP, which may well have
   proposed those tracks, never consulted. This is reachable: a donor sharing lineage with the target
   is exactly the donor most likely to be untagged on the same tracks. The brief mandates the arm
   *order*; it does not mandate losing the DP fallback when the winning arm yields nothing. Suggested
   fix: `return sib` only when `sib[1]` is non-empty, else fall through (and still echo the sibling
   table, which is useful evidence). No test covers this case either way.

### Minor
2. **models.py:341 — comment describes behaviour that does not exist.** It says `note` carries "the
   head-rows caution the CLI stamps on a no-anchors proposal's early rows." The CLI stamps no such
   note on any row; the caution is a standalone echo at cli.py:1404. Trim the comment to what the
   field actually holds (`siblings.SiblingRow.reason` verbatim).
3. **cli.py:1324-1327 — rendering is per-row, not run-shaped.** The brief asked for "contiguous
   proposed runs, and declined runs printed with their **reason line**". The implementation appends
   the *run's* reason to every row of that run: under mutation A the same
   `[tracks 1-24: not bracketed by agreeing anchors]` printed 24 times. Not a silent hole (the brief's
   actual hazard is avoided) but noisy on a wide decline; one reason line per run would match the brief.
4. **cli.py:1361 — `_donor_key` / `_show_metadata_norms` imported private across modules.** See
   concern ruling 3 below. Inconsistent with `load_donor_tapes`, promoted to public *in this same
   diff* for the identical reason, and with Task 3's `structure._hygienic` → `structure.hygienic_title`
   precedent (public today at structure.py:249).
5. **cli.py:1401-1406 — the coverage figure and caution wording are unpinned by any test** (the
   implementer's own concern 4, confirmed). On the shipped fixture the figure renders `0/24 (0%)`
   because the synthetic donor's titles are `Song NN` placeholders that embed in nothing — so the one
   asserted no-anchors path exercises the *degenerate* value of the figure the spec calls "useful
   evidence". A 0% embed rate also produces no stronger operator warning than the generic track-1
   caution. Consider one assertion that the figure is non-degenerate on a donor whose titles do embed.

## Rulings on the three implementer concerns

**1. `gather.py` + `test_triage.py` beyond the brief's "Files:" line — CORRECT SCOPE, not creep.**
The brief's own Design notes say "factor the donor-loading helper so the two share it — one
definition of 'qualifying donor'", which cannot be done without editing `gather.py`; the "Files:"
line is under-specified against the brief's own instruction, not a boundary the implementer crossed.
The extraction is behaviour-preserving: the diff shows the block moved verbatim (same three
qualification conditions, same `IAError` note text), with the only change being
`rec.identifier` → `donor.identifier` in the sort key, which is the same string. Likewise the brief
demands "Triage `[t]` … add one test proving it" — `test_triage.py` is where triage tests live and it
already imported `test_cli`'s fixtures before this task (`ANCHORED_GAPS`, `_staged_anchored_ymsb_show`).
Putting a triage test in `test_cli.py` to satisfy a file list would have been the worse choice.

**2. The second mutation-B fixture — JUSTIFIED, and the extra test is the right response.**
Both halves of the claim verified independently above (probe + assertion-neutralisation). The
implementer reported the limitation instead of quietly weakening the acceptance criterion, and the
replacement test kills the mutant on title content. Note the wording correction in (i): the cause is
zero anchors failing every `gap_span` branch, of which the absent trailing-edge branch is one; the
report should be corrected but the engineering judgment stands. Recommend the brief's acceptance
line be amended to name `test_operator_band_sibling_titles_diverge_from_the_canonical_dp` as the
mutation-B test of record.

**3. Private cross-module import — SHOULD BE PROMOTED, matching Task 3. (Minor severity.)**
The parallel is exact and the diff is internally inconsistent about it: three helpers in `gather.py`
were needed by `cli.py` for the same "one definition or it drifts" reason, and one of them
(`load_donor_tapes`) was promoted to public while two were imported through the underscore. Task 3
faced this and resolved it by promoting `structure._hygienic` to `structure.hygienic_title`; that is
the codebase's own precedent and there is no reason this seam is different. The implementer's
*substantive* judgment — share, do not duplicate — is right and should not be reversed; only the
spelling is wrong. Promote to `gather.donor_key` and `gather.show_metadata_norms` (or keep the names
and drop the underscore), update the two call sites in `gather.py` and the one import in `cli.py`.
A leading underscore that three modules read is a false statement about the API surface, and the
next reader who "simplifies" by re-privatising it will silently fork the definition.

## Strengths
- The invariant is defended in three independent places: the docstring quotes the spec verbatim, the
  untagged test asserts rows render with zero anchors, and the triage test pins the same seam — so
  the mutation kills three tests, not one.
- Every exact-title assertion is a real dict equality; not one shape assertion in the seven tests.
- Track 9's merged row is constructed so only a genuine DP can produce it (donor 400 s + 350 s
  against one 12:30 target file) — a positional or count-based transfer cannot fake it.
- The delmccoury fixture's two-description trick (empty at gather time, real at `--suggest-titles`
  time) is documented in the docstring with the reason, and is what keeps the `setlist` rung from
  pre-resolving the very tracks under test.
- `test_below_floor_donor_with_usable_canonical_falls_through_to_dp` pins on `evidence_source`
  rather than on titles landing right — a regression shows up as the wrong tag before the wrong title.

## Assessment
**Task quality: Approved** (fix Important #1 before phase close; Minors at the controller's discretion).
