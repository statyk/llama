# Phase C — final whole-branch review

**VERDICT: SHIP WITH FIXES** — two mechanical fixes (one test, one sentence). No
production-logic change required. Nothing here blocks a merge on correctness.

Guard: `PTH-GUARD: OK`. Worktree clean, no commits made. Suite re-measured on the
worktree and on an out-of-worktree copy: **1642 passed, 7 deselected** (both).

---

## Findings by severity

### Major

**MAJ-1 — `FLOOR` is half-loose: 0.50 → 0.30 leaves the entire suite green.**
`packages/llama/src/llama/siblings.py:333`. Mutation run on a shadow-proven copy
(`__pycache__` purged): every other bound breaks in both directions —
`AUTO` 0.60/0.95 (6/1 fail), `MIN_ANCHORS` 1/5 (3/6), `MIN_EXCLUSION_PENALTY`
20/200 (1/3), `MIN_MATCH_FRACTION` 0.50/0.95 (1/2), `MAX_MERGE` 2/4 (1/1),
`LOOSE_TITLE_RATIO` 0.60/0.95 (2/2). `FLOOR` breaks 2 tests when *tightened* to
0.70 and **zero** when loosened to 0.30.

Cause is precise, not diffuse: both below-FLOOR fixtures sit at agreement **0.20**
(`test_stage_gather.py:484`) and **0.15** (`test_siblings.py:470`). Nothing
exercises the **[0.30, 0.50)** region FLOOR's own justification is written about
("marginal error … ~40% from 0.30 to 0.50", siblings.py:331-332).

This is the exact class the plan's Global Constraint 25 names: *"A bound that
breaks nothing in one direction is a finding against the tests, not a shrug."*

Blast radius if loosened: FLOOR gates `declined` vs `operator`, so no silent
adoption — but a below-FLOOR pair routed to `operator` **preempts the canonical
DP** in `cli._sibling_proposal` (cli.py:1577-1580) whenever it yields any pick,
so the operator loses a fallback table to a known-bad alignment.

**Fix: one test.** A `rate_alignment` fixture at ~0.40 agreement (e.g. 2 of 5
anchors agreeing) asserting `band == "declined"`. Passes today; fails at
FLOOR = 0.30.

### Minor

**MIN-1 — the spec carries a framing the evidence doc explicitly retracts.**
`specs/2026-09-02-sibling-title-transfer-design.md:391` states "on C+'s own
primary class the enrichment is **6.7×** — 20 distinct shift-shaped errors
blocked against 3 admitted." The evidence doc at
`2026-09-02-sibling-transfer-evidence.md:636-640` says of that exact number:
*"This is a count comparison, not a rate … an earlier draft called it '6.7×
enrichment', which named the wrong quantity"*, and gives the three correct
readings (6.7:1 raw count, 6.5× as share of wrong rows, 19.1× as a rate). The
spec is the durable artifact; a future reader gets the retracted framing.
**Fix: one sentence**, mirroring the evidence doc's three-reading form.

**MIN-2 — the spec cites the disputed denominator without its dispute.**
spec:192 gives "**14 of 790 (1.77%)**". The evidence doc (lines 559-576) discloses
that 790 could not be re-derived and that three independent recounts got **782**
(against a slightly grown cache), while the numerator 14 is stable. Add the
caveat or cite the numerator only.

**MIN-3 — stated populations have already drifted; the doc flags the cache but
not the library.** The evidence doc discloses the cache is not frozen (968 → 981)
but presents "89 shows" as if fixed. Measured today: **981** cached `md_*.json`,
**98** library shows, **7** shows with unresolved tracks (not 6). *Every
conclusion reproduces on the larger population* (below), so this is a labelling
issue, not a result issue — but the library deserves the same non-frozen caveat
the cache got.

**MIN-4 — a target tape with one missing `duration_sec` declines every donor
silently.** `siblings._all_present` (siblings.py:150) fails → `propose_rows`
returns `None` → the donor is skipped in `best_donor` → `_sibling_transfer`
returns with no note. "No qualifying donor" and "this tape has an untimed file"
are indistinguishable to the operator. Diagnostic gap only; matches prior
behaviour. Ship-deferred.

### Nits
- `siblings.py:222` bare `assert step is not None` in a documented-unreachable
  branch; stripped under `python -O`, then raises `TypeError`. Harmless.
- `siblings.py:293` `is_real_title` is re-checked ahead of `hygienic_title`
  (which calls it). Not truly redundant — it buys a distinct operator-facing
  reason string ("sibling track untitled" vs "fails hygiene"). Recommend closing
  this deferred item as won't-fix rather than leaving it open.

---

## Claims section

### Verified against the artifacts (executed, not read)

| claim | source | result |
| --- | --- | --- |
| Suite 1642 / 7 deselected | evidence doc header | **PASS**, worktree and copy |
| Library re-gather: 0 regressions, 1 adoption, TBT t21 → `sibling-align/'1922'` | Step 4 | **PASS**, byte-identical output at 98 shows (doc says 89) |
| `--arm numeric`: 0 regressions, same single row | Step 6 | **PASS** |
| Regather harness is falsifiable (`--selftest-regress`) | proof table | **PASS**, 4 REGRESS rows reported |
| Six-show table: delmccoury 0.6923 / 13 anchors / operator / 5 proposals / 4 disagreements; TBT auto / 0.909 / 22 anchors / 1 automatic; both ymsb no-anchors / 0 automatic | Step 3 | **PASS**, reproduced to the digit |
| SYNTH schema: 716 targets / 11,258 pairs / 230,600 rows / 0 violations | instrument 1 | **PASS**, re-run on the retained `align.jsonl` |
| SYNTH random mask 50–80%: 20,167 adopted / 166 wrong (0.82%); 80–95%: 7,298 / 70 (0.96%); C+ blocked 2,979 / 832 | Step 2, Step 9 | **PASS**, re-scored, exact match |
| `hygienic_title('gd19730800.07.weather report suite', set()) is True` | regression class | **PASS** |
| `is_real_title('1922')` True; `'19770101'` False; `'d1t02'` False | titles.py comment | **PASS** |
| `loosely_same_title` misses: BIODTL ratio **0.40**, Rain **0.774** | structure.py:222-224 | **PASS**, both exact |
| **Single-donor slide, the residual's whole basis:** TBT2007-07-20.sbd.flac ← tbt2007-07-20.391.flac16, agreement 0.909 / 22 anchors, t1 penalty **28 s**, t2 **0 s** vs `MIN_EXCLUSION_PENALTY=60`; masked band `auto` at agreement **1.000**; forced rows → C+ returns `decline — "tracks 1-2: not bracketed by agreeing anchors"` | Step 9 | **PASS — every figure reproduced independently.** This was the doc's one claim with no committed script ("report retained in the run scratchpad"); it is now verified end to end |

### Verified by mutation (the class that killed this phase's late Criticals)

Shadowing proven with a planted sentinel before every run; `__pycache__` purged
between runs; `python -m pytest` from the copy.

| mutation | result |
| --- | --- |
| delete the automatic-band gate (`if res.band != "auto"` → `if False`) | **2 FAIL** — `test_operator_band_run_stays_unresolved_even_though_cplus_would_bracket_it`, `test_below_floor_sibling_alignment_declines_with_a_note`. **The Critical that could once be deleted with a green suite is now pinned.** |
| remove `cplus_filter` from gather | **1 FAIL** — `test_a_bracketing_failure_leaves_the_run_unresolved_with_its_reason_in_notes` |
| reverse `best_donor`'s sort (pick the worst donor) | **2 FAIL**, in both gather and cli |
| delete concern #1 (`title_source != "unresolved"`) | **2 FAIL**, incl. the coverage-evidence pin |
| widen `INDEPENDENT_TITLE_SOURCES` with `setlist`/`setlist-gap`/`sibling-align` (circular anchors) | **1 FAIL** — `test_a_setlist_gap_title_is_not_an_anchor` |
| **make the renderer apply `cplus_filter`** | **5 FAIL** across `test_cli.py` and `test_triage.py` — spec invariant 1 is pinned, not merely documented |
| drop hygiene from `propose_rows` | **1 FAIL** |
| drop the numeric clause from `is_real_title` | **1 FAIL** |
| drop `bool(row.proposed)` from `_anchor_row` | **2 FAIL** |
| every numeric bound, both directions | all break both ways **except `FLOOR` loosened** — see MAJ-1 |

### Unverifiable from the repo (findings in their own right, not softened)

1. **The 790-recording denominator.** The doc says so itself: the producing run
   is not retained and cannot be re-derived against its own population. Three
   independent recounts got 782 against a grown cache. **Disclosed honestly and
   correctly bounded** — the numerator (14) is stable and the conclusion does not
   depend on it. No action.
2. **The hand-triage of 148 distinct wrong adoptions** (4 genuinely wrong) is a
   human judgement, not re-derivable by script. The classifier's raw output is
   reproducible via `--triage`; the reclassification of 74 of 80 out of `genuine`
   is not. Accept as a stated hand-check; it is labelled as one.
3. **The 18-item `hygienic_title` exposure list** is *stated* by the doc to be
   untestable on this library ("none of the 18 items is present in
   `~/.llama/cache`"). The 0 is real, the 18 is unmeasured. Correctly framed.

No claim I sampled was found **false**.

---

## The three owner-facing items — as decisions

### 1. Automatic yield is 1, not 0 (TBT t21 `1922` via `sibling-align`, not `setlist-gap`)

**Evidence:** reproduced today at 98 shows. Track 21, residual **0 s**, penalty
**406 s**, bracketed by agreeing anchors at t20/t22, count-forced between them,
band `auto` at 0.909 over 22 anchors. Both regather arms produce the identical
single row. Title hand-checked correct.

**Does it change any safety claim? NO.** The safety argument is per-rung, not
per-cascade-position: `sibling-align`'s licence is anchor agreement + C+ +
hygiene, and this row satisfies all three independently of which rung would have
gotten there second. The one claim it *does* touch — the numeric widening's
justification ("narrowing it back out would take 1922 with it") — is unaffected:
`--arm numeric` shows the widening is still what makes this row possible.

**Options:** (a) ship, spec already amended to "1 track"; (b) reorder the cascade
so `setlist-gap` wins. **Recommendation: (a).** The spec amendment
(`design.md:231-237`) is accurate. Do not reorder — `sibling-align` running
earlier is what lets an operator override anchor the guard.

### 2. The filename-shaped donor tag (`gd19730800.07.weather report suite`)

**Evidence:** verified — `hygienic_title(...) is True`. Library blast radius **0**
(neither `gd1973-08-01` item is a library show; the regather diff is one row,
re-confirmed at 98 shows). SYNTH cost: 4 of 510 wrong entries, and those 4 are
*right song, dirty string* — the comparator scores them wrong, the alignment is
correct. The shape is pre-existing in `clean_tag_titles`; what is new is that the
rung propagates it to a **different** tape.

**Options:** (a) ship with the class named — status quo; (b) fix first by widening
`titles._TRACK_NUM_PREFIX` beyond `\d{1,3}`; (c) add a filename-shaped-tag veto
inside `hygienic_title`.

**Recommendation: (a), ship as-is.** (b) is explicitly forbidden by an existing
ruling — the `\d{1,3}` bound is what protects `1952 Vincent Black Lightning` and a
bare `2001` and "must never be widened to `\d+`". (c) is a new predicate on the
pipeline's **only silent adopter**, which needs its own corpus sweep — exactly the
change class this project keeps ruling should not be made inside a ship task. The
class is named, sized, and its blast radius measured at zero. Filing it is the
correct outcome.

### 3. The named falsifier list

**Verdict: complete and honest.** Six entries; I checked each against what I could
reach, and the two hardest are stated *against* the branch rather than for it —
the synthetic population is named "still the biggest hole," and the wrong-anchor
interaction is declared unmeasured with nothing closing it. The single-donor entry
carries "that is one case, not a rate" in its own text.

**One entry warrants action now, and it is the only one:** *"Anything that changes
`_donor_key`'s ordering re-opens those [135 pairs]."* That dependency is currently
protected by two tests that fail on a reversed sort (verified above) — good — but
**neither test names the 135 slide pairs as what it is protecting.** A future
"simplify the tie-break" reader sees two tests about picking the higher-agreement
donor and no signal that a measured failure class rides on it.

**Recommendation:** add a one-line cross-reference in `gather._donor_key`'s
docstring to the evidence doc's Step 9 (~2 minutes, no logic change). The
remaining five falsifiers need no action now.

**One thing the list is missing, given MAJ-1:** it names `_donor_key` as the
fragile dependency but not `FLOOR`, whose loosening is unpinned. Fixing MAJ-1
makes this moot.

---

## Deferred-minor triage (ledger line 778, ~27 items)

### Must fix before merge — 1

- **MAJ-1, the `FLOOR` test gap.** Not on the ledger's list; found in this review.
  One test. This is the only must-fix.

### Fix now if the owner wants them (both verified trivial, neither blocking)

- **Task 2 — the Unicode gap.** `is_real_title("١٩٧٧")` is True.
  **I verified the standing ruling's condition is met:** substituting `[0-9]{4}`
  for `\d{4}` at `titles.py:24` gives `is_real_title('1922') → True`,
  `is_real_title('١٩٧٧') → False`, and the **full suite stays at 1642 passed /
  7 deselected**. It is exactly the character class plus a test, so the ruling
  says it *may* be fixed rather than must stay deferred.
  **Recommendation: fix it.** It is two lines against a verified-green result, and
  it hardens the pipeline's only silent adopter. Pre-existing with no observed
  trigger, so deferring is also defensible — but the ruling's own bar is met.
- **MIN-1 / MIN-2, the spec's two stale claims.** Two sentences in the ship
  artifact a future reader relies on. **Recommendation: fix both.**

### Ship deferred — the rest (~26)

- **Task 5 — the duplicated sibling-fetch note. CONFIRMED REAL, and the channel
  is confirmed too.** Both `gather.py:155` (`load_donor_tapes`) and
  `gather.py:323` (`_collect_parses`) emit the byte-identical string for the same
  identifier, both flow into `notes`, and `notes` reaches
  `StructureInfo.conflicts` at `gather.py:1066` → `show.model_dump_json()` →
  `brief.py:138`, i.e. the briefing LLM prompt, on the unlabeled channel already
  parked from Phase B. **But:** it fires only on an `IAError`, `conflicts` has no
  other consumer in the codebase (grepped — no gate, no review flag), and the
  payload is a duplicate diagnostic line, not a wrong fact. **Recommendation:
  ship deferred, and file it with the parked Phase B channel defect rather than
  alone** — the right fix is labelling that channel, not de-duping one string on
  it. If the owner wants it closed now it is a one-line dedupe at `gather.py:873`.
- **Task 1 (5):** redundant `order` list; the `(basename, round(secs))` key vs
  `titles._stem_no_ext` (measured 0/968 corpus incidence); the "byte-identical"
  test name at `test_junk.py:240`; sweep `n_pairs` counting absent formats; the
  additive median-perturbation test. All cosmetic or already measured inert.
- **Task 3 (7):** `bool` admitted by the `isinstance` duration guard (unreachable
  — durations come from `length_seconds`); two hygiene clauses lacking a
  siblings-side fixture; the redundant `is_real_title` (recommend **won't-fix**,
  see Nits); the bare `assert`; `rows.sort`; `rstrip(">")`; the per-op DP re-solve
  (cost measured and ruled acceptable).
- **Task 4 (3):** untyped `tracks: list`; the unstated positional contract; one
  vacuous assertion. Documentation-grade.
- **Task 5's second item:** I3's inert `"Wrong "` assertion.
- **Task 6 (6 minors):** as listed in `t6-rev-qual`.
- **Task 6's `scripts/blind_tag_gapfill.py` un-importable — ALREADY CLOSED.**
  Verified: the script parses and `--help` runs. The evidence doc's repair claim
  (line 310) holds. Strike it from the list.

---

## The single-donor residual — verdict

**Acceptable as documented, with the one-line cross-reference from item 3.**

The reasoning is sound and I verified its load-bearing half myself rather than
taking the doc's word: on the one measured single-donor slide, layer 3 declines
t1 at 28 s and t2 at 0 s against a 60 s threshold, and the C+ counterfactual
returns `decline` with the leading-edge reason — **two independent stops**, both
reproduced. The population is 1.26–1.77% of target recordings.

Against a follow-up pin: the protection is already pinned *as a mechanism* —
`MIN_EXCLUSION_PENALTY` breaks in both directions under mutation, and C+'s
bracketing breaks when removed. What is unpinned is only the *role*: no test says
"this is what stops a single-donor slide." A pin in that role would be a fixture
reproducing the class, which is a measurement task, not a test edit, and the doc
is explicit that one case is not a rate. **Recommendation: do not build the pin
now.** Take the docstring cross-reference instead, and re-open only if a second
single-donor slide ever appears.

---

## Constraints — all confirmed

| constraint | status |
| --- | --- |
| Suite 1642 passed, 7 deselected | **HOLDS** (worktree + copy) |
| `sibling-align` not in `TAUTOLOGICAL_TITLE_SOURCES` | **HOLDS** — `structure.py:961` is `{"setlist-gap", "setlist"}` |
| `matched` never forced to `None` for `sibling-align` | **HOLDS** — `gather.py:981` keys off that same frozenset; pinned by `test_stage_gather.py:596-606` and by the M4 mutation |
| `cplus_filter` has no caller in the renderer path | **HOLDS** — grepped: production callers are `gather.py:267` only; every `cli.py` occurrence is comment text. Pinned: adding it to the renderer breaks **5** tests |
| `siblings.py` is pure | **HOLDS** — imports are `dataclasses`, `llama.structure`, `llama.titles`. No I/O, no LLM, no `stages/` |
| One definition each of hygiene / winner selection / donor loading | **HOLDS** — `structure.hygienic_title` (one def, 2 call sites), `gather.best_donor` and `gather.load_donor_tapes` (one def each, shared by gather + cli + both scripts). Reversing the sort now breaks tests in both gather and cli |

Additionally verified: no stale references to the removed positional `sibling`
rung outside deliberate historical comments; legacy `title_source == "sibling"`
is excluded from `INDEPENDENT_TITLE_SOURCES` (conservative, correct) and
documented as no-migration.

---

## What would stop a merge

Nothing on correctness. MAJ-1 is a test-coverage gap on a constant whose shipped
value is correct; the two spec fixes are sentences. All three are mechanical and
none touches production logic.
