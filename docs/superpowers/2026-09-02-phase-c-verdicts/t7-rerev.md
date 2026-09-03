# Task 7 — scoped re-review, fix round 1 — VERDICT

`PTH-GUARD: OK` (worktree). All controls RUN, not read; outputs pasted verbatim.
Range reviewed: `905007a..3d834c7` (2 commits). **HEAD is `83ea17f`, one commit past
the stated range** — it touches only `scripts/sibling_blind_arm.py` (+6/-1, the
`--schema` unit line) and the spec; it carries Q7's "`--schema` names its unit" half,
so I reviewed it too. Zero `packages/` lines in `905007a..HEAD`.

## Verdicts

| finding | verdict |
| --- | --- |
| Q1 plant could fail to corrupt / 74-74 provenance | **ADDRESSED** |
| Q2 `population_oracle` not independent | **ADDRESSED** (with an overclaim in the new wording — below) |
| Q3 `ARMS['numeric'] = (None, None)` | **ADDRESSED** |
| Q4 Step 8's zero had no plant | **ADDRESSED** |
| Q5 "six zero-shaped" over eight rows | **ADDRESSED** |
| Q6 no committed mode computed 135/1 | **ADDRESSED** |
| Q7 three mislabelled quantities | **ADDRESSED** |
| F3 SYNTH/REAL mixed in one table | **ADDRESSED** |
| folded-in single-donor slice | **ADDRESSED** (one unreproducible denominator — below) |

## Q1 — run, and independently falsified

```
$ ./.venv/bin/python scripts/sibling_blind_arm.py --selftest align.jsonl
population  : 716 targets from align.jsonl
TRUTH plant : 4146/4146 correct  -> PASS
POISON plant: 4133/4133 wrong      -> PASS  (21 track(s) had no loosely-different title on their own tape and are excluded)
DEGENERACY  : the two plants differ -> PASS
```

- Population is the **716-target certified population** (`align.jsonl`, 716 lines,
  md5 `f34606dc…`, the same cache `--oracle` recounts), named on line 1 of stdout.
- **The 21 unplantable tracks are PRINTED IN THE OUTPUT**, not merely computed —
  they appear in the pasted stdout above, on the POISON line. Confirmed against the
  orchestrator's sharpening: reading the summary alone still surfaces the count.
- Exclusion is correctly scoped: `a["track"] - 1 not in unplantable` removes them from
  the POISON **denominator only**, per-entry, and unplantable tracks keep their truth
  (so they could only have inflated a pass — excluding them is the conservative side).
- **Falsification (mine, not the author's):** monkeypatching `_plant_titles` back to a
  plain rotation makes the control **FAIL** — `POISON plant: 0/14 wrong -> FAIL`,
  `DEGENERACY -> FAIL`, exit 1. The control can fail.
- **The named leak is gone and so is its class:** on
  `gd1968-10-12.sbd.gans.miller.owen.9385.shnf` t15 truth `'Jam >'` now plants
  `'St Stephen >'` (was `'Jam \'`), and a census over all 716 targets finds
  **0 loosely-same leaks** among plantable hidden tracks.
- Provenance recorded at doc lines 105-106 ("the earlier draft quoted 74/74 … from a
  12-target smoke cache").

## Q2 — independent in substance; the new wording overclaims

`--oracle align.jsonl` → `oracle targets (>= 6 tracks): 716; … measured: 716`,
`in oracle, not measured: 0`, `measured, not in oracle: 0`, `ORACLE: -> PASS`.

AST audit of `population_oracle`'s call graph:
- locally-defined module functions called: **`read_cache`**
- method calls on the local `CacheIA`: **`ia.identifiers`, `ia.metadata`**
- shipped `llama` functions: `group_candidates`, `filter_files`, `clean_tag_titles`,
  `title_fraction`, `length_seconds`

The three functions the finding named — `build_candidates`, `load_target`,
`gather.load_donor_tapes` — are genuinely gone, along with `_collection_of` and
`_doc_of`; the collection key, doc shape, target test and donor test are written out
inline. The shipped-`llama` sharing is legitimate: the population *is* defined as
"what `filter_files` keeps and `group_candidates` groups", so re-implementing them
would measure a different population. **So: ADDRESSED.**

**But the absolute claim is literally false**, in the docstring *and* in the
deliverable (doc line 82): "calling **no function defined in the instrument file**".
It calls `read_cache` and the `CacheIA` accessors. `read_cache` is harmless (a 4-line
JSONL reader over the artifact under audit; its only failure mode makes `missing`
non-empty, i.e. FAIL, never a false pass). `CacheIA.identifiers()` is the one real
residual shared dependency — a glob that under-enumerates would shrink both sides
equally and pass silently. Correction needed: "calls no function that constructs the
population, sharing only a read-only cache accessor and the shipped `llama` functions".

## Q3 / Q4 — plants run, both directions

```
SELFTEST-REGRESS (arm=gap): harness CAN report a regression -> PASS
SELFTEST-REGRESS (arm=sibling): harness CAN report a regression -> PASS
SELFTEST-REGRESS (arm=numeric): harness CAN report a regression -> PASS
  (all three: REGRESS yondermountainstringband-2010-07-16 t1: tags/'Too Late Now' -> tags/'SELFTEST-REGRESSION')

arm=sibling: compared 89 shows (0 skipped) | 0 regressions; 1 newly resolved
arm=numeric: compared 89 shows (0 skipped) | 0 regressions; 1 newly resolved
  ADOPTED trampledbyturtles-2007-07-20 t21: unresolved/'TBT2007-07-20D2T08.mp3' -> sibling-align/'1922'

RECONCILE: 40 targets, 0 mismatched | bands {'auto':31,'operator':8,'declined':1}
           non-empty adopted-title sets compared: 31 (612 title strings) -> PASS
RECONCILE (PLANTED): 40 targets, 40 mismatched | PLANT expects mismatches -> PASS
```

`ARMS["numeric"] = ("unresolved", None)`; source side is `"unresolved"` in all three
arms, so an already-resolved track's retitle is illegal everywhere — which is exactly
what the plant exercises. The zero is now falsifiable.

## Q5 — ten, and ten

Doc line 140 says **Ten**; the table at lines 145-156 has **ten** rows. Counted.

## Q6 — `--slide-rank`, reconciled

```
pairs 11258 | auto_band_pairs 8355 | localised_slides 136 | distinct_targets 75
slide_donor_is_the_agreement_winner 1 | outranked_by_a_cleaner_donor 135
winners_with_exactly_one_donor 1
winner: TBT2007-07-20.sbd.flac <- tbt2007-07-20.391.flac16, agreement 0.909, run [1,2] offset +1
```

Reconciliation, computed from that JSON: **sum of the 16 per-performance counts = 136**;
`localised_slides = 136`; `135 + 1 = 136`. All three agree.
`slide_rank`'s winner selection (`min` over all rated donors by `_donor_key`) is faithful
to shipped `best_donor`, which likewise ranks before any band filter.

## Q7 — units, checked against the artifacts

- `$ --schema align.jsonl --dump detail.json` → `cache: 716 targets, 11258 pairs, 230600 rows`
  / `detail: 11849 records (of 12888 trials)` / `SCHEMA: 0 violations -> PASS`.
  716 × 3 × 6 = **12,888** ✓. The unit is named in the tool's own output.
- `ls ~/.llama/cache | wc -l` = **1059**; `ls ~/.llama/cache/md_*.json | wc -l` = **968**. ✓
- Enrichment arithmetic: 20/3 = 6.67 → **6.7:1** ✓; 20/153 = 13.07% vs 3/148 = 2.03%,
  ratio 6.44 → **6.5×** ✓; 20/4,636 = 0.431% vs 3/13,291 = 0.023%, ratio 19.11 → **19.1×** ✓.
  Also spot-checked and correct: 3.37%/0.83% ("4×"), 28.7:1, 54:1.

## F3 — split

Doc lines 584-593: a **SYNTH** table (random + prefix mask) and a separate **REAL**
table (the single named pair, its donor forced), with "neither is summed with it"
stated between them. Confirmed.

## Folded-in single-donor slice — independently reproduced

- **9 of 716 (1.26%)**: recomputed directly from `align.jsonl` (`len(pairs) == 1`) →
  **9, 1.26%**, identifiers listed. ✓
- **5 of the 9 are same-item format twins**: verified from the target→donor pairs —
  infamousstringdusters flac16↔flac24 (2), larrykeel flac16↔flac24 (2),
  `ymsb2005-12-31.flac16` ← `ymsb2005-12-31.flac16.wav` (1) = **5**. ✓
- **Exactly 1 slide case, the named survivor**: `winners_with_exactly_one_donor = 1`,
  `TBT2007-07-20.sbd.flac`. ✓
- **Layer 3 stops it, measured not asserted**: unmasked, band `auto`, agreement 0.9091,
  22 anchors; `t1 verdict='decline' penalty=28.0`, `t2 verdict='decline' penalty=0.0`
  — both under `MIN_EXCLUSION_PENALTY=60`. ✓
- **C+ counterfactual reproduced verbatim**: masking tracks 1-2 leaves band `auto` at
  agreement **1.0** (20 anchors); forcing both rows to `adopt` and calling `cplus_filter`
  returns, for both, `verdict='decline' reason='tracks 1-2: not bracketed by agreeing
  anchors'` — the exact string the doc quotes. ✓
- **Framing correction present** (doc 526-536, and the spec via `83ea17f`): "the
  tie-break eliminated 135" and "135 are multi-donor" stated as one observation.
- **One number I could not reproduce:** the ungated denominator **"790 of 968"**. Two
  independent reconstructions of my own (donors qualifying by `filter_files` +
  complete durations; target gate on/off) both give **782**, not 790 — while the
  load-bearing figure, **exactly-1-donor = 14**, reproduces in both (1.79% of 782 vs
  the doc's 1.77% of 790). The doc cites "a follow-up census; report retained in the
  run scratchpad", and no such report is present under the run scratchpad. Minor and
  presentational, but this document's whole standard is that every figure reconciles:
  either commit the census as a mode beside `--slide-rank`, or cite its file path.

## Suite and blast radius

```
$ ./.venv/bin/python -m pytest -q
1642 passed, 7 deselected, 26 warnings in 6.59s
```
(Run once, from an isolated copy, because it is the ship gate's stated precondition.)

**Zero `packages/` lines.** `git diff --numstat 905007a..3d834c7` → three files:
`docs/…-evidence.md` 168/61, `scripts/regather_diff.py` 51/5,
`scripts/sibling_blind_arm.py` 275/54. Sum of added+deleted lines under `packages/` = **0**,
and the same holds for `905007a..HEAD` (which adds only the spec doc). Task 7 changed
no production behaviour.

## New breakage in the fix diff

**One, minor, in prose not code:** the Q2 independence claim as newly worded
("calls no function defined in the instrument file") is literally false — see Q2 above.
Introduced by this round in both `population_oracle`'s docstring and doc line 82.
It does not invalidate the oracle; it overstates it, in a document whose value is that
its claims are exactly the size of their evidence.

No functional defect found in the diff. Reviewed and found sound:
`_plant_titles` (deterministic, per-entry, no leakage across entries; `pick is None`
handled rather than silently skipped), `_plant_rows` (rotates the cached side only),
`_selftest`'s per-bucket accounting, `ARMS`, `_selftest_regress`, `slide_rank`'s
donor ranking, `_show_key` (documented as presentational; the identifier prefix is
retained, so different artists on one date cannot merge).

## Deferred (out of scope, one line each)

- `_DATE4`/`_DATE2` use `__import__("re")` at module level instead of a normal import — cosmetic.
- `_show_key`'s `_DATE2` branch hard-codes the `19xx` century; fine for this corpus, would mis-key a 20xx two-digit identifier.
- `--slide-rank` recomputes the full rating pass that `--score` already does; a shared helper would remove one copy of the loop.

## VERDICT

**PASS — ship.** All nine open findings ADDRESSED, every control re-run rather than
read, Q1 additionally falsified by mutation, the suite holds at 1642/7, and the range
contains zero `packages/` lines. The two residues — Q2's overstated independence
wording and the unreproducible 790 denominator — are prose accuracy nits worth one
commit, not blockers, and neither touches a measured result.
