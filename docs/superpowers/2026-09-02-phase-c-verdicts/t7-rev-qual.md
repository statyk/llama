# QUALITY: CHANGES REQUESTED

Task 7 code-quality / instrument review. Pointer guard `PTH-GUARD: OK`. Worktree
untouched; no commits. Diff `19b4ef1..905007a` touches **no production code**
(`git diff --stat 19b4ef1..905007a -- packages/` is empty), so the unchanged
1642-test suite is consistent with the change and I did not re-run it.

**I re-ran the instruments rather than reading them.** Every headline number in
the doc that I could re-derive, I did -- from the run's own artefacts
(`workc/t7-evidence/align.jsonl`, `detail.json`, `slide.out`, `score.out`,
`m1-rerun.err`) and by re-executing the committed scripts. **The measurements
themselves hold up unusually well.** What fails is the *proof layer* the plan
made the credit condition, in three specific places, plus two zeros that cannot
mean what the doc says they mean.

## Verification I performed

Reproduced exactly, from the committed scripts, this session:

| re-run | result |
| --- | --- |
| `--schema align.jsonl --dump detail.json` | 716 / 11,258 / 230,600 / "11,849 trials", 0 violations -- identical |
| `--row-census` | skip 474 rows / 258 pairs; split 38,435 / 6,488; merged 16,618 / 6,466; histogram 11000/161/33/34/16/14 -- identical |
| `--oracle` | 716 = 716, 6 under `MIN_TRACKS`, PASS -- identical |
| `sibling_controls --baseline / --deletions / --rotation --n 120 / --localised-shift / --wrong-performance / --six-shows` | every measured value identical (23/23/1; A2 24/24/0; A3 15/15/9; 405 vs 19-of-which-0-wrong; bare 11 (8 wrong) -> C+ 2 (0 wrong); 0.083 / 0.000; whole six-show table incl. 0.6923 / 13 anchors / 5 / 4 and `AUTOMATIC BAND'S LIBRARY YIELD: 1 (EXPECTED 0) -> REVIEW`) |

Recomputed independently from `detail.json` (my own aggregation, distinct =
`(target, donor, track)`): random 61,626 adopted / 510 wrong / 13,291 distinct /
148 distinct wrong; blocked 12,388 / 417 wrong / 11,971 right / 4,636 distinct /
153 / 4,483; prefix blocked 14,789 / 269 / 14,520 / 8,906 / 188 / 8,718.
**Every C+ precision figure in the doc is exact.** SYNTH and REAL are never
pooled in any table. All per-stratum arithmetic checks (0.80/0.82/0.96%,
3.37% vs 0.83%, 28.7:1, 54:1, 51x, 20x, 81x, 1.63%).

M1 repair: `m1-rerun.err` shows `distinct adoptions 6815 / pooled wrong rate
8.77%` -- the re-measurement used the repaired script (the pre-repair script
could not import at all). The repair itself is correct: `_show_metadata_norms`
-> `show_metadata_norms` (Task 5 rename) and removal of the positional
`_sibling_titles` rung Phase C deleted, mirrored in the blinding ladder and
documented in the docstring.

## Three-proofs table

| instrument | schema | planted positive control | independent oracle | oracle genuinely independent? |
| --- | --- | --- | --- | --- |
| `scripts/sibling_blind_arm.py` | PASS, reproduced, 0 violations | **FAIL -- see Critical 1**: the 74/74 figures come from `smoke.jsonl` (12 targets), not the 716-target population they certify; run as documented (`--selftest align.jsonl`) the committed script FAILS, exit 1 | A `--oracle` reproduced; B `--reconcile` 612 strings, 0 mismatches | **A: NO.** It calls the instrument's own `build_candidates` and the same `load_donor_tapes`; only the per-recording eligibility test is re-derived. The enumeration layer -- exactly where Task 2's first-non-empty-format bug lived -- is shared. **B: YES**, and materially: live `best_donor` re-fetches donors and recomputes `propose_rows`, validating the cached DP and the reimplemented donor sort |
| `scripts/sibling_controls.py` | PASS -- `YMSB_TRUTH` 24-for-24, asserted on every invocation (fired in all six modes) | PASS, reproduced: rotated donor 23/23 WRONG; A5 0.083 / 0.000 | `YMSB_TRUTH`, hand-established in Phase B | **YES** -- a hand transcription shares no code with anything. Best instrument of the three |
| `scripts/regather_diff.py` | PASS -- 89 compared / 0 skipped; track-count change is itself a regression | PARTIAL -- `--arm gap --selftest` only; the plant is gated on `arm == "gap"` yet `main` still prints `SELFTEST: harness CAN detect a difference -> PASS` for other arms off the real diff | `sibling_controls --six-shows` (I re-ran it; independently reports the same single row) + an **uncommitted** setlist.fm heredoc | **YES** for `--six-shows` (different driver, `best_donor` + stored `show.json` vs `run_gather`; no shared harness code) |
| `scripts/blind_tag_gapfill.py` | repair only, no new proofs claimed | -- | -- | repair correct; 6,815 / 8.77% verified from the run's own output |

## Degeneracy section -- every reported zero

| reported zero | positive control shown? | verdict |
| --- | --- | --- |
| prefix mask ships 0 automatic in every stratum | YES -- the same `adopted` counter reads 61,626 under the random mask in the same run; same cells report 14,789 blocked | non-degenerate |
| named rotation arm ships 0 automatic titles | WEAK -- the honest baseline for this pair is also 0 (band `no-anchors`), so this zero distinguishes nothing; the real control is the adjacent 23/23-wrong scoring | mis-paired in the degeneracy table |
| corpus rotation arm ships 0 wrong | WEAK -- the doc concedes rotation is not guaranteed corruption (all 19 leaks are correct, one donor family). A "0 wrong" from a plant that may not corrupt | honestly disclosed, still weak |
| C+ ships 0 wrong on the named pair | YES -- bare ratio ships 8 wrong in the identical cell | non-degenerate |
| `--arm sibling`: 0 regressions | YES -- `--arm gap --selftest` fires the diff machinery; the arm's own 1-row adoption proves the monkeypatch bites | non-degenerate |
| `--arm numeric`: 0 regressions | NO -- structurally impossible to be anything else (Critical 2) | **degenerate** |
| Step 6: 0 of 18 alter a shipped title | HONEST -- no positive control is possible (none of the 18 is in the cache) and the doc says so in the same sentence | honest |
| Step 8: 0 mismatches | NOT BY THE RUN -- no implementer plant. I supplied one: mutated `cf`'s titles in an out-of-tree copy -> `8 targets, 8 mismatched ... -> FAIL`. The oracle does bite | non-degenerate (proven by me) |
| setlist.fm arm: 0 tracks differ on six shows | WEAK -- companion is a *canonical* difference, not proof the arm can report a track difference; script uncommitted | weak; absent from the degeneracy table |
| Step 9: 0 slide-induced titles reach C+ / the library | YES -- 136 pairs found, survivor's declines verified | non-degenerate |

**Bookkeeping defect inside this very section:** the prose says "**Six** of the
results below are zero-shaped" above an **eight-row** table (the report says
"Eight").

## Issues

### Critical

**1. `sibling_blind_arm.py`'s planted control was not run on the population it
certifies, and the committed script fails the command the doc publishes.**
Doc: "planted control | `--selftest align.jsonl` | TRUTH plant: 74/74 ... POISON
plant: 74/74 wrong", and `--selftest align.jsonl` is item 3 of "Reproducing".
Measured this session:

```
$ ./.venv/bin/python scripts/sibling_blind_arm.py --selftest <align.jsonl>
TRUTH plant : 247/247 correct  -> PASS
POISON plant: 246/247 wrong      -> FAIL
DEGENERACY  : the two plants differ -> FAIL          (exit 1)

$ ./.venv/bin/python scripts/sibling_blind_arm.py --selftest <smoke.jsonl>   # 12 targets
TRUTH plant : 74/74 correct  -> PASS
POISON plant: 74/74 wrong      -> PASS
```

The 74/74 is the 12-target smoke cache; every number the doc credits comes from
the 716-target cache. Under the plan's own words ("a planted synthetic positive
control run through the *committed* script"), the credit condition is unmet for
the instrument carrying the entire SYNTH half of the evidence.

The scorer is **sound** -- I traced the single failure: at
`gd1968-10-12.sbd.gans...` t15 the rotation maps `'Jam >'` onto `'Jam \\'`,
which `loosely_same_title` correctly calls the same song, so the plant did not
corrupt that row. The defect is the **gate**:
`_selftest`'s `ok_rot = rot_wrong == rot_adopted` (sibling_blind_arm.py:686) is
all-or-nothing over a corpus with repeated titles. Fix: run the plant on the
real cache, exclude rotations whose source and destination are
`loosely_same_title` (or gate at >=99% with the exception enumerated), record
the real numbers, and keep "Reproducing" identical to what produced them.

**2. `--arm numeric`'s "0 regressions" is degenerate by construction.**
`regather_diff.py:76` -- `ARMS = {... "numeric": (None, None)}` -- and `main`'s
`if legal_from is None or (...)` routes **every** title change to `adopted`. No
title change can ever be a regression on that arm; only a track-count change
can. The doc quotes the arm's output verbatim in Step 6 without noting the first
half of the line is unfalsifiable. Give the arm a real legality rule, or strike
"0 regressions" from Step 6 and say the arm enumerates rather than gates.

### Important

**3. The doc overstates oracle A's independence, on precisely the axis the bar
protects.** `population_oracle` (sibling_blind_arm.py:803) opens with
`for cand in build_candidates(ia)` -- the instrument's own enumeration, the same
call `build_cache` makes (line 231) -- then calls the same `load_donor_tapes`.
The doc says it uses "its own grouping/tag/duration tests, sharing no code with
`build_cache`". Own tag/duration tests: yes. Own *grouping*: no. A
grouping/collection bug -- the class of the Task 2 bug that motivated this rule
-- moves both sides identically and the oracle prints 716 = 716 either way.
Downgrade the claim, or enumerate identifiers directly.

**4. `--arm numeric` only partially applies its own intervention, undisclosed.**
`_gather` patches `titles_mod.is_real_title`. `structure.hygienic_title` imports
it inside the function (structure.py:1155), so the patch reaches `_hygienic` --
Step 6's actual target, which is why the Step 6 conclusion survives. But
`siblings.py:46` binds it at module import, so `siblings.py:293` and `:392` keep
the widened predicate on both sides. The doc's "turns off `is_real_title`'s
pure-4-digit clause and re-gathers the whole library" is not what runs.

**5. "6.7x enrichment" is a bare count ratio wearing a rate's name.** It is
20 / 3 -- 20 distinct blocked shift-errors against 3 admitted -- across
populations of very different size (4,636 distinct blocked vs 13,291 distinct
adopted). Normalised: **6.5x** as a share of errors (13.1% vs 2.0%) or **19x**
per adoption. Direction is conservative, but the phase's own rule is that a
count without a denominator is the same defect as an unlabelled rate, and this
sits inside the ruling paragraph that decides C+'s fate.

**6. Step 9's headline mechanism is correct but not reproducible from the
committed instruments.** `--slide-scan` emits only the slide pairs, never the
per-target agreement ranking, so nothing in "Reproducing" regenerates "135 of
136 outranked". I re-derived it over `align.jsonl` with the shipped `_donor_key`
and got exactly 135 / 1. Add it as a mode (or emit each slide pair's rank).

**7. Step 9's illustrative per-show counts do not reconcile with `slide.out`.**
Doc: "`gd1971-08-06` (7 pairs), `gd1978-07-08` (19), `gd1987-09-18` (11),
`gd1989-10-26` (14), `gd1982-10-10` (8)". Measured from the run's own output --
by target date: **17 / 27 / 10 / 16 / 8**; by unordered pair: 18 / 28 / 10 / 16 /
8; by distinct target: 5 / 9 / 10 / 8 / 8. Only `gd1982-10-10` matches under any
grouping, and the largest omitted cluster (`gd1984-10-12`, 14) outranks three of
the five named. The headline 136 / 8,355 / 75 / 0.800-0.926 is exact; this
breakdown is not.

**8. Unit error in the schema row: "11,849 trials".** The doc's own Units
paragraph defines `trials` = (target, stratum, mask, rep) = 716 x 3 x 6 =
**12,888** (the cell table's 3,580x3 + 716x3 confirms it). 11,849 is the length
of the detail dump. `check_schema` prints `detail: {n} trials`, propagating the
mislabel. Call it "detail records".

**9. `--selftest` is a silent no-op on two of three arms yet still reports
PASS.** `regather_diff.py:104` gates the plant on `arm == "gap"`, while `main`'s
`ok = bool(adopted or regressions)` reads the *real* diff -- so
`--arm sibling --selftest` prints PASS having planted nothing.

### Minor

- "1,059 cached items" (Step 2 preamble) is the *file* count of `~/.llama/cache`
  (968 `md_*` + 90 `slfm_*` + 1 `artist_*`). The implementer's own M1 rerun
  prints `cached items scanned : 968`.
- "Six of the results below are zero-shaped" over an eight-row table.
- `reconcile`'s MISMATCH line prints only donor/agreement/band
  (sibling_blind_arm.py:545) -- on a title-set mismatch all three are identical,
  so the operator gets three matching fields and no diff (seen in my mutation
  run). Print the differing tracks.
- The setlist.fm arm is an uncommitted heredoc: its Step 4 result, and one of
  `regather_diff`'s two oracles, cannot be re-run from the repo, and
  "Reproducing" lists no command. The committed `--six-shows` oracle carries the
  claim, so this is a reproducibility gap, not a credit gap.
- `blind_tag_gapfill.py:277` -- the repair left a run-on line well past the
  file's width.

### Strengths

- **`sibling_controls.py` is the model instrument in this phase**: a hand
  transcription asserted for shape on every invocation, expectations printed
  beside measurements, a genuinely code-free oracle, and it reproduced to the
  digit six modes later in a different session.
- **The POISON-plant design is exactly right**, and its docstring reasoning
  (rotate only the hidden tracks, because rotating the whole donor makes the
  guard decline and "0 adoptions, 0 errors" is indistinguishable from a blind
  scorer) is the sharpest thinking in the task. Critical 1 is about where it was
  run, not what it is.
- **`--reconcile`'s degeneracy guard** -- counting and printing the 612 compared
  strings with an explicit `DEGENERATE` branch -- is the right instinct and
  survived my mutation.
- **Step 6 is the honest handling of a structurally unmeasurable zero.**
- **Deviations were reported, not absorbed**: the yield-1 deviation is printed
  by the instrument itself as `REVIEW`, escalated, and amended in the spec in
  the plan's own words.
- **The doc's structure meets the brief**: verdict first, controls before SYNTH,
  SYNTH/REAL never pooled, falsifier list carried forward and updated.

## Verdict on Step 9's count and mechanism

**Both are correct, and I verified them independently rather than accepting
them.**

- **136 pairs / 8,355 auto-band pairs / 11,258 rated / 75 distinct targets /
  agreements 0.800-0.926 / offsets +/-1, +/-2 / runs of 2-4 tracks** --
  re-derived from `slide.out`, exact.
- **135 outranked / 1 survivor** -- re-derived by me over `align.jsonl`, rating
  every donor of every target with the shipped `rate_alignment` and ranking with
  the shipped `_donor_key`: 135 of 136 slide donors are not their target's
  winner; the single survivor is `TBT2007-07-20.sbd.flac` <-
  `tbt2007-07-20.391.flac16` at 0.909, tracks 1-2 at offset +1 -- the identical
  pair the doc names.
- **The survivor's escape route** -- read from the cached rows directly: t1
  `penalty 28.0 s`, t2 `penalty 0.0 s`, both `verdict='decline'`,
  `reason='weak evidence'`, against `MIN_EXCLUSION_PENALTY = 60.0`. Layer 3
  declines them before C+ is consulted, exactly as claimed.
- **The single-donor gap IS stated in the doc**, not only in the report: the
  falsifier list carries "A performance with exactly one qualifying donor has no
  cleaner alternative to be outranked by; that sub-population was not separately
  sized here and is the sharpest follow-up", and the spec amendment repeats it.

The only Step 9 defects are presentational (finding 7) and reproducibility
(finding 6). The conclusion -- the class is REAL at 136 and unreachable in
production by donor selection plus layer 3 -- stands as measured.

## Assessment

**Task quality: Needs fixes.**

**Reasoning:** Every headline measurement I could re-derive is exact, and the
Step 9 finding -- the phase's decisive question -- survives independent
recomputation. But the plan made three proofs per instrument the condition for
crediting any of it, and for `sibling_blind_arm.py` the planted control was run
on a 12-target smoke cache while the doc publishes it as a proof over the
716-target population, where the committed script actually fails; the oracle
that would have covered for it shares the enumeration layer it is supposed to
check. Add one zero that is unfalsifiable by construction (`--arm numeric`'s "0
regressions") and the fixes are bounded and mostly documentary -- no
re-measurement of the corpus is required.
