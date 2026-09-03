QUALITY: CHANGES REQUESTED

Pointer guard: `PTH-GUARD: OK`. Worktree untouched (`git status --porcelain` empty), no commits.
All mutations run on a PYTHONPATH-shadowed copy at
`/private/tmp/.../scratchpad/workc/t6-rev-qual/`; shadowing proven with a planted
`SENTINEL_T6REVQUAL` (resolved to the copy's `cli.py`), sentinel removed before any run,
`__pycache__` purged before and after every run. Baseline on the copy:
`test_cli.py` + `test_triage.py` = 68 passed; `test_stage_gather.py` + `test_siblings.py`
= 137 passed (the extraction is behaviour-preserving).

# Findings

## Important

### I1. The whole no-anchors block is deletable with the suite green (unpinned safety text)
`packages/llama/src/llama/cli.py:1385-1393`
Mutation **M4** — `if res.band == "no-anchors":` -> `if False and res.band == "no-anchors":`
— deletes the donor identifier, the embed-in-canonical coverage figure and the head-row
caution, and **68/68 pass**. The untagged test's `assert "no-anchors" in result.output`
is satisfied by the header line (`band no-anchors`), not by the block. The design spec
calls the caution "the only remaining check" on the wholly-untagged path (spec line ~445),
so this is the phase's standing rule violated on the highest-stakes string in the change.
Change: in `test_untagged_fixture_with_tagged_donor_renders_sibling_proposal`, assert
`"caution: check track 1 by ear"`, the donor identifier, and the literal coverage line;
and add a donor whose titles DO embed in the canonical so the fraction is asserted at a
non-zero, non-degenerate value (today it renders `0/24 (0%)` and nothing checks it, so
`_sibling_donor_coverage` could `return 0, len(adopted)` unconditionally and stay green).

### I2. Per-row decline reasons are deletable with the suite green
`packages/llama/src/llama/cli.py:1327-1328`
Mutation **M6** — never append `f"  [{r.note}]"` — **68/68 pass**. The brief's
"declined runs printed with their reason line, not silent holes" is entirely unpinned:
neither fixture produces a declined row. Change: give one fixture a donor track with an
empty/junk title (`sibling track untitled`) or a sub-`MIN_EXCLUSION_PENALTY` pairing, and
assert both the `(unresolved - hand-edit)` row and its bracketed reason render.

### I3. `residual_sec` hard-coded to 0.0 passes everything — the exact prior-phase hollow test
`packages/llama/src/llama/cli.py:1377`
Mutation **M9** — `residual_sec=0.0` — **68/68 pass**. Both fixtures build donors with
exactly-equal durations, so `re.search(r"\b0s\b", result.output)` (test_cli.py:861) pins
column *presence* only, and its comment ("every row's residual is 0s (exact duration
match)") is what makes that invisible. This is the same failure mode the phase already
shipped once (`residual_sec` hard-coded to 0.0 passing all 19 tests). Change: offset one
donor track by, say, 12 s and assert `12s` renders on that row and `0s` on its neighbour.
(M7, `residual_sec=None`, IS caught — presence is pinned, correctness is not.)

### I4. Weak-evidence declines silently lose the title the DP proposed
`packages/llama/src/llama/cli.py:1375` — `title=(row.proposed if row.verdict == "adopt" else "")`
`siblings.SiblingRow`'s docstring (siblings.py:124-127) states the opposite contract
verbatim: "A declined row may still carry a `proposed` title: `weak evidence` keeps it so
**the operator path can render what the DP thought**." This IS the operator path, and it
throws that text away, showing `(unresolved - hand-edit) [weak evidence (penalty 3s)]`
where the whole point was to show the candidate title next to its weak evidence.
Mutation **M10** (`title=(row.proposed or "")`) also passes 68/68, which means neither the
current behaviour nor its inverse is tested — and the inverse would leak a *declined*
title straight into `overrides.titles` via `picks`, because `picks` keys off
`r.title` being non-empty rather than off the verdict.
Change: keep the DP's text in the note —
`note=("" if row.verdict == "adopt" else (f"{row.reason} - DP proposed {row.proposed!r}" if row.proposed else row.reason))`
— and make `picks` gate on an explicit adopt set rather than on title emptiness, so the
two concerns stop sharing one field. Add a test for a weak-evidence row: reason rendered,
proposed text visible, **not** in `overrides.titles`.

### I5. "Which donor wins" is now duplicated, and the CLI copy has no test
`cli.py:1360-1373` vs `stages/gather.py:216-228`
The extraction achieved one definition of *qualifying donor* (good), but
`_sibling_proposal` then re-implements gather's winner-selection block essentially
verbatim: `propose_rows` -> skip `None` -> `rate_alignment` -> `_donor_key` -> `sort` ->
`[0]`. Mutation **M8** (`candidates.sort(..., reverse=True)`, i.e. pick the *worst* donor)
**passes 68/68** — no CLI fixture has two qualifying donors, so the copy is untested as
well as duplicated. That is exactly the drift class the task existed to close, one level up.
Change: extract `gather.best_donor(ia, cand, identifier, want, tracks, metadata_norms)
-> (donor, rows, res, notes) | None` from the block that follows `load_donor_tapes`, call
it from both sites, and add a two-donor CLI fixture pinning that the higher-agreement donor
wins. This also **dissolves finding I6** — neither private helper needs to cross the module
boundary any more.

### I6 (ruling). The private cross-module import should not stand
`cli.py:1359` — `from llama.stages.gather import _donor_key, _show_metadata_norms, load_donor_tapes`
The implementer's premise (one definition beats convention) is right; the conclusion is
wrong, and there IS a codebase precedent, one task old and in this same feature: Task 3 hit
the identical choice and resolved it by promoting `structure._hygienic` to public
`structure.hygienic_title`, whose docstring now opens "PUBLIC, and deliberately
single-sourced" and explains exactly this reasoning. A leading underscore is a promise to
the rest of the codebase that a symbol can be renamed or re-signatured freely; importing it
across a module boundary makes that promise false without telling the next reader.
Ruling: **promote, don't reach in.** Preferred: extract `best_donor` per I5, which removes
both imports outright. Otherwise rename to `gather.donor_key` / `gather.show_metadata_norms`
with a one-line "PUBLIC because the operator surface shares it" note, matching
`hygienic_title`'s wording, and update gather's 4 internal call sites.

## Minor

- **m1. Flat checkerboard, not run-shaped.** `cli.py:1379-1382` prints one line per track
  with the same reason repeated on every row of a declined run; the brief and spec both ask
  for run-shaped rendering ("`tracks 7-9: not bracketed by agreeing anchors`"). Under
  mutation A I watched 24 identical `[tracks 1-24: not bracketed by agreeing anchors]`
  brackets stack up. `gather._sibling_transfer` already has the collapse idiom 40 lines
  away (`seen_reasons`). Collapse consecutive equal notes to one line under the run.
- **m2. `loosely_same_title`'s docstring is now false.** `structure.py:209-211` reads
  "USED BY THE SIBLING GUARD (`siblings.rate_alignment`/`cplus_filter`) AND THE MEASUREMENT
  SCORERS ONLY." Two new CLI callers exist (`_sibling_donor_coverage`,
  `_sibling_canonical_text`). Add the display use and mark it explicitly
  non-measurement-entering, so the "DO NOT RETUNE" basis stays legible.
- **m3. `models.py:331-338` documents two unreachable note sources.** A "C+-style run
  reason" cannot occur (the renderer never calls `cplus_filter` — the whole invariant), and
  no head-rows caution is ever stamped onto a row (it is echoed as its own line). Trim to
  the two sources that actually reach the field.
- **m4. Donor fetch failures are swallowed on the operator surface.** `cli.py:1364` —
  `donors, _notes = load_donor_tapes(...)`. gather surfaces those notes; here a donor that
  existed and failed to fetch is indistinguishable from no donor at all, on the one path
  where a human is deciding. Echo them (`typer.echo` per note) before the band check.
- **m5. "nothing to adopt: every track already has a title" is reachable and false.**
  Reproduced live under mutation A: every row declined, zero picks, and the CLI told the
  operator every track already has a title. Reword `cli.py:1549` to cover "the proposal
  adopted nothing".
- **m6. Provenance comment is under-cited.** `_sibling_donor_coverage`'s docstring cites
  "it missed gd1982-10-10 at 92%" with no source; house style wants script/date/corpus.
  Point at `docs/superpowers/specs/2026-09-02-sibling-title-transfer-design.md` (~line 445).
- **m7 (for the spec reviewer, noted not adjudicated).** The spec's untagged-path list says
  "per-row residuals **and penalties**"; `penalty_sec` is not carried onto `ProposalRow` and
  not rendered.

## What is clean

- The `gather.load_donor_tapes` extraction is genuinely shared and genuinely
  behaviour-preserving: one definition, no second copy of the qualifying-donor conditions
  (`grep` confirms), and 137 gather+siblings tests green on the copy.
- `cplus_filter` really is never called from `cli.py` (only quoted in a docstring), and the
  invariant is pinned three ways — mutation A (apply it in the renderer) fails
  `test_untagged_fixture_with_tagged_donor_renders_sibling_proposal`,
  `test_delmccoury_shaped_operator_band_confirms_only_unresolved_rows` and
  `test_suggest_titles_sibling_arm_shares_the_triage_seam`.
- Function-local imports match cli.py's established style (30+ existing instances).
- No `Optional`-field drift: both new `ProposalRow` fields default, every existing
  construction still works, and `evidence_source`'s values are distinguished in rendering
  (`proposal (sibling-align, donor X, band Y)` vs `proposal (duration-model)`); the
  fall-through test's `"sibling-align" not in result.output` is sound because
  `"sibling-duration"` does not contain it.
- `picks` is built identically to the canonical DP's (`title_source == "unresolved"` gate),
  so the two arms cannot diverge on what gets written.
- **Scope: both extra files are necessary, not creep.** `gather.py` is the extraction the
  brief itself ruled on; `test_triage.py` is where the brief's required triage pin belongs
  (it already imports test_cli fixtures for exactly this).
- **Commit messages: both state the test command** (`./.venv/bin/python -m pytest -q`) with
  counts.
- **Suite delta +7, all additions.** The diff on both test files is purely additive
  (imports, `MultiIA`, helpers, 7 tests); no existing test was edited, deleted or weakened.

# Test hygiene — what edit kills each new test

| # | Test | Killing edit (verified) |
|---|------|--------------------------|
| 1 | `test_untagged_fixture_with_tagged_donor_renders_sibling_proposal` | apply `cplus_filter` in the renderer (M4-A); `residual_sec=None` (M7). **Does NOT kill:** deleting the no-anchors block (M4), dropping notes (M6), `residual_sec=0.0` (M9). |
| 2 | `test_operator_band_sibling_titles_diverge_from_the_canonical_dp` | canonical DP first (mutation B) — on title content; drop the `title_source` picks gate (M2) |
| 3 | `test_delmccoury_shaped_operator_band_confirms_only_unresolved_rows` | apply `cplus_filter` (A); drop the picks gate (M2); delete the disagreements block (M3); blank the `setlist:` column (M5) |
| 4 | `test_below_floor_donor_with_no_usable_canonical_declines_unchanged` | admit the `declined` band (M1) |
| 5 | `test_below_floor_donor_with_usable_canonical_falls_through_to_dp` | admit the `declined` band (M1) |
| 6 | `test_suggest_titles_c1_staleness_guard_still_fires_before_donor_work` | move the sibling arm above the C1 filename-list compare (guard is order-pinned; not separately mutated, the assertion `"proposal (" not in result.output` makes it structural) |
| 7 | `test_suggest_titles_sibling_arm_shares_the_triage_seam` (test_triage.py) | apply `cplus_filter` (A) — proves `[t]` reaches the same seam |

Three source edits survive the whole suite and are the substance of I1/I2/I3:
M4 (delete the no-anchors donor/coverage/caution block), M6 (never render a decline
reason), M9 (`residual_sec=0.0`). M8 (pick the worst donor) also survives — I5.

# Mutation-B two-fixture verdict: CLAIM VERIFIED

I reproduced it rather than accepting it. Under mutation B (canonical DP attempted first,
sibling arm only on infeasible) **`test_untagged_fixture_...` still passes** — the
wholly-untagged tape's canonical DP is infeasible either way, so arm order is genuinely
unobservable on it, exactly as reported; the implementer's structural explanation
(`structure.gap_span` has no trailing-edge branch, so a whole-tape run always declines)
matches `gap_span`'s own docstring ("DELIBERATELY NO TRAILING-EDGE BRANCH").
The second fixture **does** kill mutation B, and **on title content, not on the band
label**: I deleted its `assert "band operator" in result.output` line and re-ran the
mutant, which then failed at the exact-dict assertion —
`{5: 'Steep Grade Sharp Curves'} != {5: 'Placeholder 5'}`,
`{14: 'Jack London'} != {14: 'Placeholder 14'}`.
Building the second fixture was the correct call, and the report disclosed the deviation
rather than hiding it.

# Private-import ruling (restated)

Do not ship the underscore imports. Task 3's `structure._hygienic` ->
`structure.hygienic_title` promotion is the governing precedent, from this same feature one
task back, and its docstring already argues the case. Preferred resolution is I5's
`gather.best_donor` extraction, which removes both imports and closes the duplicated
winner-selection at the same time; the fallback is a straight promotion to
`gather.donor_key` / `gather.show_metadata_norms`.
