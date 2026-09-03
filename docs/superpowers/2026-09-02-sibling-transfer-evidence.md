# Sibling title transfer: the acceptance measurement

Date: 2026-09-03. Branch `sibling-transfer` @ `4213e33`+.
Design: `docs/superpowers/specs/2026-09-02-sibling-title-transfer-design.md`.
Suite at every measurement below: `./.venv/bin/pytest -q` → **1642 passed, 7 deselected**.
Standard: `docs/superpowers/2026-08-03-tail-guard-sanity-check.md`.

Everything here ran through the **shipped** functions — `siblings.propose_rows`,
`siblings.rate_alignment`, `siblings.cplus_filter`, `gather.load_donor_tapes`,
`gather.best_donor`, `gather._sibling_transfer`, `structure.loosely_same_title` —
never a prototype. The four do-not-retune constants in `siblings.py`
(`MAX_MERGE`, `SKIP_COST_MULT`, `MIN_EXCLUSION_PENALTY`, `MIN_MATCH_FRACTION`)
and the three guard constants (`AUTO`, `FLOOR`, `MIN_ANCHORS`) cite this file:
every number below was taken **at** those values, so changing one invalidates
all of them, not just its own table.

**Neither population is frozen.** The single-donor section below discloses
that the cache moved (968 → 981 `md_*.json` items) between this document's
measurement and a later recount. The same caveat applies to the show
**library** the full-library re-gather ("89 shows" throughout) was taken
against: it too has grown since, to 98 shows. Every figure keyed to either
population is a snapshot, not a fixed constant — re-running against a later
cache or library is expected to shift raw counts even where, as verified
for both the cache and the library, the underlying conclusions reproduce.

---

## Verdict

**The rung is safe to ship, and the automatic band is nearly inert on today's
library — one track, and it is correct.**

- Every named control passes, scored by **string identity against independent
  ground truth**, not by row counts.
- Full-library offline re-gather: **89 shows, 0 regressions**, and the complete
  diff is **one** new adoption — `trampledbyturtles-2007-07-20` t21 →
  `sibling-align/'1922'`, hand-checked correct.
- Blind arm, random mask (SYNTH): loose error **0.80% / 0.82% / 0.96%** per
  stratum, all below the sweep's C+ cells (1.87–1.99%). Hand-triage of every
  distinct wrong adoption puts the **genuinely-wrong-song** class at **4 of
  13,291 distinct adoptions (0.030%)** — 51× below the setlist-gap rung's
  measured 1.54% and below the ≥0.60% floor on the tag rung's own typo rate.
- Prefix mask (SYNTH): **zero automatic titles in every stratum**, as designed.

**Three deviations from the spec's stated expectations, all reported rather
than absorbed:**

1. **The automatic band's library yield is 1 track, not 0.** The spec predicted
   `1922` would arrive via `setlist-gap`; `sibling-align` runs earlier in the
   cascade and gets there first. Safe direction, correct title, but the spec's
   "0 tracks" sentence is now wrong and should be amended.
2. **A localised donor-span slide with high anchor agreement is REAL, not a
   synthesis artifact** — 136 pairs in the unmasked corpus, against the spec's
   n=1. It is nevertheless unreachable in production: **135 of the 136 are
   multi-donor, so a cleaner donor of the same performance is the one
   `best_donor` selects** (that is one observation, not a filter — a tie-break
   needs ≥2 donors to exist), and the single-donor survivor's shifted rows are
   declined by layer 3 *and*, verified counterfactually, by C+. See Step 9.
3. **A hygiene gap the sibling arm propagates**: a donor tagged
   `gd19730800.07.weather report suite` (a filename/lineage stamp) clears
   `hygienic_title` and is proposed verbatim onto a *different* tape. Named
   regression class below; filed, not fixed.

**C+'s precision — the question the phase hung on — is answered in full below
and does not collapse to one number.** Both counts, both units, both masks, and
the hand-triage are in "Step 9 / C+ precision".

---

## Instruments, and the three-way proof for each

The bar: a schema check, a **planted synthetic positive control run through the
committed script**, and an **independent oracle sharing no code with the
instrument**. Every number below is credited only after all three.

### 1. `scripts/sibling_blind_arm.py` — the masked arm (SYNTH)

Population: every cached recording that is ≥95% self-tagged, has complete
per-track durations, has ≥6 tracks, and has ≥1 qualifying donor, drawn from
**968 cached archive.org items** (`~/.llama/cache` holds 1,059 *files*; 968 of
them are `md_*.json` item records and the rest are indexes — the earlier draft
quoted the file count and called it items). **716 target recordings, 11,258
(target, donor) pairs, 230,600 rows.** The DP sees only durations, so it
is computed once per pair and cached; every stratum/mask/rep re-runs only the
guards.

| proof | command | result |
| --- | --- | --- |
| schema | `--schema align.jsonl --dump detail.json` | 716 targets / 11,258 pairs / 230,600 rows / **11,849 detail records** (a record is written only when a trial adopted or blocked ≥1 row; the run performed **12,888 trials** = 716 × 3 strata × (5 random reps + 1 prefix)), **0 violations** (rows cover 1..n exactly once; half-open spans in range; no `adopt` without a title; `adopted` ∩ `cplus_blocked` = ∅ and both ⊆ `bare_adopted`; no rows outside the automatic band) |
| planted control | `--selftest align.jsonl` — **the whole 716-target certified population**, and the line printed names it | TRUTH plant (donor == target): **4,146/4,146 adoptions correct**. POISON plant: **4,133/4,133 adoptions wrong**, with **21 tracks excluded and counted** as unplantable. Both non-empty; they disagree. |
| independent oracle A | `--oracle align.jsonl` | recounts the population sharing **no domain judgment with the instrument**: `build_candidates`, `load_target` and `gather.load_donor_tapes` — the three functions the coupling finding was actually about — are never called, and no grouping decision, tag-fraction test, duration test or donor-qualification test is reused; its own collection key, search-document shape, target test and donor test are written out below, re-derived from scratch. It does still call two in-file helpers that carry no judgment of their own — `read_cache` (a plain JSONL reader) and `CacheIA.identifiers`/`.metadata` (cache file access) — plus the shipped `llama` functions the population is *defined* in terms of (`group_candidates`, `filter_files`, `clean_tag_titles`, `title_fraction`, `length_seconds`). **716 = 716**, plus 6 targets under `MIN_TRACKS` the oracle deliberately does not filter. A third, throwaway probe counted 722 = 716 + 6. |
| independent oracle B | `--reconcile align.jsonl --reconcile-n 40` | the cached path vs a **live `gather.best_donor`** call: 40 targets, bands `{auto: 31, operator: 8, declined: 1}`, **31 non-empty adopted-title sets / 612 title strings compared, 0 mismatches**. Its plant, `--reconcile … --plant` (rotate the cached proposals): **40 of 40 mismatched, PASS** — so the zero is falsifiable. |

The POISON plant is the load-bearing half, and it took two corrections.

**First**, the obvious plant — rotate the whole donor — is useless here: the
guard then declines the pair, the scorer is never asked a question, and "0
adoptions, 0 errors" is indistinguishable from a scorer that cannot see failure.
So the corruption is confined to the hidden tracks, leaving the anchors honest.

**Second, and found by review: a rotation among the hidden tracks can fail to
corrupt.** Run over the full population the first cut printed `POISON 246/247 →
FAIL`. The single leak was `gd1968-10-12.sbd.gans.miller.owen.9385.shnf` t15,
truth `Jam >` against a planted `Jam \` — the tape has two `Jam` tracks, the
two strings loosely match, and **the scorer scored that adoption correct because
it was correct.** The plant had failed to corrupt; the scorer had not failed to
see. Accepting 246/247 would have converted a fixable control into a permanently
blunted one, so `_plant_titles` now picks, per hidden track, a title from the
same tape that is **verifiably not `loosely_same_title`** to that track's truth.
Where no such title exists anywhere on the tape the track is *unplantable*, is
excluded from the plant's denominator, and the count is printed (**21 of 4,154**)
rather than absorbed.

**The earlier draft of this document quoted `74/74` for both plants. That number
came from a 12-target smoke cache, not from the 716-target population the tables
below certify** — a plant proven on 12 targets says nothing about a measurement
made on 716. `--selftest` now runs the whole cache by default and prints the
population it covered on its first line.

### 2. `scripts/sibling_controls.py` — the named controls and the six-show table (REAL)

Deliberately a **second driver**: named identifiers and the on-disk library
rather than a cache sweep, reaching the same shipped functions by a different
route, so a mistake in one driver cannot silently move the other's numbers.

| proof | result |
| --- | --- |
| schema | `YMSB_TRUTH` is 24 entries for a 24-track tape, none empty — asserted on every invocation. A transcription that lost a line would shift every comparison by one, which is the failure this phase is about. |
| planted control | rotation arm (a): the ymsb2005 donor rotated +1 — the scorer marks **23/23** of the resulting proposals WRONG against `YMSB_TRUTH`. A5: a wholly unrelated donor scores **0.083** and **0.000** agreement, both below `FLOOR`. |
| independent oracle | `YMSB_TRUTH` is Phase B Section B's **hand-established** mapping (`docs/superpowers/2026-08-31-gap-fill-blind-test.md`), derived by cumulative-offset alignment across all three discs BY HAND — it shares no code with anything. Separately, delmccoury's agreement reproduces the spec's independently measured **0.69** to the digit (0.6923, 13 anchors). |

### 3. `scripts/regather_diff.py --arm sibling | numeric` (REAL)

Phase A's M2 harness, generalised: same driver, one thing turned off, every
moved track enumerated and attributed. Arms name the one legal `title_source`
transition; anything else is a regression.

| proof | result |
| --- | --- |
| schema | 89 shows compared, 0 skipped; a track-count change between arms is itself recorded as a regression (none occurred) |
| planted control (legal change) | `--arm gap --selftest` (a deliberately wrong adopter) → **harness CAN detect a difference, PASS** |
| planted control (regression) | `--arm {gap,sibling,numeric} --selftest-regress` retitles an **already-resolved** track → **all three arms report REGRESS, PASS**. This is what makes each arm's "0 regressions" falsifiable, and it is the fix for a real defect: `ARMS["numeric"]` was `(None, None)`, i.e. *every* title change was legal, so that arm's zero **could not have been non-zero for any code change**. The source side of a legal transition is now never `None`; both arms were re-run under the tightened rule and both are unchanged (0 regressions, 1 adoption). |
| independent oracle | `sibling_controls --six-shows`, a different driver reading stored `show.json`, independently reports the same single automatic adoption; and the live-network setlist.fm arm reproduces the same single row |

### Explicit degeneracy check

**A measurement whose expected value is degenerate — zero, empty, the identity,
the default — cannot distinguish *computed correctly* from *never computed*, and
survives mutation.** **Ten** of the results below are zero-shaped (an earlier
draft said "six" over an eight-row table; the count was wrong and two rows have
since been added). Each is paired with a non-zero companion from the *same* run
that proves the machinery engaged:

| zero-shaped result | its non-degenerate companion |
| --- | --- |
| prefix mask ships **0** automatic titles in every stratum | the same cells report **14,789** rows that the bare ratio *would* have adopted; the 0 is C+ declining them, not the harness computing nothing |
| ymsb2005 ships **0** automatic titles | the same call renders **23 adopt-verdict rows**, all correct |
| rotation control ships **0** automatic titles on ymsb2005 | the same run scores **23/23** rotated proposals wrong |
| localised-shift pair: C+ ships **0** wrong | the bare ratio ships **8 wrong** in the identical cell |
| re-gather: **0** regressions | the same run reports **1** newly resolved row, and `--selftest` produces many |
| Step 6: **0** of the 18 pure-4-digit items alter a shipped title | the numeric arm's diff is **non-empty** (1 row moves), proving the arm engages |
| A5 donor agreement **0.000** on one donor | the other A5 donor scores **0.083** — a real, non-zero, still-below-FLOOR reading |
| `--reconcile` **0** mismatches | it reports the **612 title strings** it actually compared, prints `DEGENERATE` if that count is 0, and `--plant` (corrupt the cached rows) makes the same call report **40 of 40 mismatched** |
| `--arm numeric` **0** regressions | `--selftest-regress` makes that arm report a regression. Until the legality rule was tightened this zero was **unfalsifiable by construction**, which is worse than degenerate — see the `regather_diff.py` proof table |
| POISON plant expects **all** adoptions wrong | its twin, the TRUTH plant, expects **all correct**, from the same code path on the same 716 targets; and the plant now verifies it actually corrupted each row before demanding the scorer call it wrong |

---

## Step 1 — the named controls (REAL)

`./.venv/bin/python scripts/sibling_controls.py --baseline | --deletions |
--rotation align.jsonl --n 120 | --localised-shift | --wrong-performance`

| control | expected | measured | |
| --- | --- | --- | --- |
| probe baseline, `ymsb2005-12-31.flac16.wav` ← `ymsb2005-12-31.flac16` | 23 adopt / 23 correct / 1 decline | **23 adopt, 23 correct by string against `YMSB_TRUTH`, 1 decline** (track 1, `Intro > Granny … > Ride The Wild Turkey`, penalty 0 s) | PASS |
| same pair, automatic band | 0 automatic titles | band `no-anchors`, **0** | PASS |
| A2 — donor track 1 (`Intro`) deleted | orphaned rows decline, 0 wrong | **24 adopt, 24 correct, 0 wrong, 0 declined** | PASS |
| A3 — donor track 18 (a mid-set-2 song) deleted | orphaned rows decline, 0 wrong | **15 adopt, 15 correct, 0 wrong, 9 declined** | PASS |
| rotation (a), named control | 0 automatic titles, scorer sees failure | **0 automatic; 23/23 scored wrong** | PASS |
| rotation (b), corpus-wide, 120 pairs | 0 **wrong** automatic titles | honest donor ships **405**; rotated donor ships **19**, of which **0 wrong** | PASS |
| prefix-mask arm, every stratum | 0 automatic titles | **0 / 0 / 0** | PASS |
| localised shift, `gd1971-08-06.aud.wolfe…` ← `…mtx.seamons.96668` | C+ ships 0 of the bare ratio's wrong titles | worst cell (agreement 0.833): bare ratio adopts **11 (8 wrong)**; C+ adopts **2 (0 wrong)** | PASS |
| A5 — wrong-performance donor | below `FLOOR` (0.50) | **0.083** and **0.000**, both `declined` | PASS |

**A2's result is better than the control's own baseline, and that is why it is
scored against `YMSB_TRUTH` rather than against the baseline run.** Deleting the
donor's `Intro` *corrects* target track 1 — the baseline merges the Intro in and
declines the row; A2 adopts the correct `Granny Woncha Smoke Some > Ride The
Wild Turkey`. A same-as-baseline comparator would have scored a correction as a
regression.

**Rotation arm (b) is a weaker instrument than it looks, and this is stated
rather than hidden.** Rotation is not a guaranteed corruption: where a donor
carries one extra leading track its tag list is *already* displaced by one
relative to the target's songs, so rotating it **fixes** the correspondence.
All 19 leaked titles are correct, and all 19 come from one such donor family
(`gd1982-10-10.111039.nak300.hoey.flac16`). Counting "titles shipped" there
measures the corpus's donor shapes; only "wrong titles shipped" measures the
guard, so that is what the arm gates on.

---

## Step 2 — the blind arm (SYNTH)

`./.venv/bin/python scripts/sibling_blind_arm.py --build-cache align.jsonl` then
`--score align.jsonl --dump detail.json`, 2026-09-03, `~/.llama/cache`
(**968 cached `md_*.json` item records** → 716 eligible target recordings; the
1,059 figure an earlier draft used is the file count of `~/.llama/cache`).

**Units.** `trials` = (target, stratum, mask, rep). `adopted` / `wrong` /
`blocked` are **adopted-title instances (entries)** unless the row says
`distinct`, which means distinct `(target, donor, track)` triples. One error is
re-drawn by every rep whose mask happens to hide that track, so the entry count
is several times the distinct count; the two are never mixed in a ratio.

**SYNTH and REAL are not pooled anywhere in this document.**

### Random mask (5 reps per stratum, seeds derived from target index)

| stratum (visible tags) | trials | reached `auto` | adopted | wrong | loose error | C+ blocked | wholesale titles |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 20–50% | 3,580 | 3,328 | 34,161 | 274 | **0.80%** | 8,577 | 0 |
| 50–80% | 3,580 | 3,326 | 20,167 | 166 | **0.82%** | 2,979 | 2 |
| 80–95% | 3,580 | 3,326 | 7,298 | 70 | **0.96%** | 832 | 2 |

Gate: per-stratum loose error at or below the sweep's C+ cells (1.87–1.99%).
**Measured 0.80 / 0.82 / 0.96% — PASS in every stratum.**

### Prefix mask (deterministic, 1 rep per stratum)

| stratum | trials | reached `auto` | adopted | wrong | C+ blocked | wholesale titles |
| --- | --- | --- | --- | --- | --- | --- |
| 20–50% | 716 | 675 | **0** | 0 | 8,581 | 0 |
| 50–80% | 716 | 670 | **0** | 0 | 4,609 | 0 |
| 80–95% | 716 | 669 | **0** | 0 | 1,599 | 0 |

The spec's stated cost reproduces exactly: **a prefix-tagged tape gets no
automatic help at all.** Every run has an unresolved tail with no right anchor,
so C+ declines all of it.

### The wholesale-failure gate, and its definition

Definition used here, stated because the sweep's is not reconstructible: a pair
is a **wholesale failure** when it adopts ≥2 titles on hidden tracks and ≥80% of
them are loose-wrong. That is deliberately looser than the probe's four named
whole-tape-garbage pairs (all at agreement 0.00, which cannot reach the
automatic band at all).

Mechanically: **4 titles across 2 pairs**, in 2 of 6 cells. Both hand-triaged in
full:

- `gd1976-06-14.sbd.orf.240.shnf` ← `gd1976-06-14.sbd.bettycantor.gems.82308`
  (t16, t17). **The adoptions are RIGHT and the tape's tags are WRONG.**
  Adjudicated against a third source — the target's **own description**, which
  lists 22 songs including `Dancing In The Street` between `Crazy Fingers` and
  `Cosmic Charlie`, for 21 files. The DP's reading has residuals 4 / 6 / 57 s;
  the tape-tag reading needs 191 / 192 / 238 s. The taper dropped one title and
  slid the rest.
- `gd1973-08-01.140895…wotf-outtakes` ← `gd1973-08-01.148528…wake-of-the-flood`
  (t7, t9). The alignment is 1:1 and correct; the donor's tags are
  filename-shaped (`gd19730800.07.weather report suite`), so the comparator
  scores them wrong. Right song, dirty string — see the named regression class.

**Zero wholesale alignment failures in any stratum under either mask. PASS**,
with the definition and the triage stated so the number can be re-derived.

### Hand-triage of every wrong adoption (random mask)

`--triage detail.json --truths align.jsonl`. 510 wrong **entries** = **148
distinct** (target, donor, track). All 148 were read; the 80 the classifier put
in `genuine` were read individually.

| class | entries | distinct | after hand-review |
| --- | --- | --- | --- |
| classifier `genuine` | 273 | 80 | **4 genuinely wrong song**; 2 tape-wrong (the adoption is right); 74 same-song variants and non-song banter the aggressive-containment test missed |
| classifier `non-song boundary` | 200 | 56 | cut/label differences (`Tuning` vs `Encore break`, `Space` vs `Jam`, `Alligator ->` vs `Gator Jam`) |
| classifier `variant/comparator` | 30 | 9 | `s1t04 Jack-A-Roe` vs `Jackaroe`, `Dr..ums >` vs `Drums` |
| classifier `shift` | 7 | 3 | 1 tape-wrong (gd1976-06-14, above); 2 are `Take A Step Back` vs `Tuning`, a non-song label that coincidentally matches a neighbour |
| **TOTAL** | **510** | **148** | **4 genuinely wrong** |

The 74 reclassified out of `genuine` are the comparator's own misses, and the
list reads like the spec's own examples: `Goldbricking`/`Goldbreaken`,
`BIODTL`/`Beat It On Down The Line`, `Peggy O`/`Peggio`, `Used To Love
Her`/`It's All Over Now` (same Stones song, chorus-named), every permutation of
`Man Smart (Woman Smarter)`, every permutation of `Playin' (In The Band)
Reprise`, `Hey Jude Reprise`/`Hey Jude Finale`, `Disc01,Track09
Masterpiece`/`When I Paint My Masterpiece`.

The 4 genuinely wrong, in full:

| target ← donor | track | tape says | sibling says |
| --- | --- | --- | --- |
| `gd77-05-17.sbd.weiner.18554` ← `gd1977-05-17.sbd.leonard.1107` | 1 | `Jack Straw` | `Minglewood Blues` |
| `gd1977-06-09.sbd.fishman.3869` ← `gd1977-06-09.sbd.dauria.3372` | 12 | `Help On The Way ->` | `Finiculi Finicula` |
| `ymsb2006-10-19.flac16` ← `ymsb2006-10-19.mk41.flac16` | 22 | `Good News Blues` | `Only A Northern Song` |
| `ymsb2006-10-19.mk41.flac16` ← `ymsb2006-10-19.flac16` | 22 | `Only A Northern Song` | `Good News Blues` |

The last two are **one disagreement measured in both directions**, so at most
one of them is a real error: the true count is 3 or 4, never more.

### Against the M1 standard

| rung | distinct adoptions | genuinely-wrong | rate |
| --- | --- | --- | --- |
| `setlist-gap` (Phase A, M1, shipped) | 6,546 | 101 | **1.54%** |
| tag rung's own typo floor (M1, ≥) | — | 41 of 6,864 | **≥0.60%** |
| `sibling-align`, this run (SYNTH, random mask) | 13,291 | **4** | **0.030%** |

**51× below the setlist-gap rung and 20× below the floor on the tag rung's own
error rate.** Every rate here is an **upper bound**: ground truth is the target
taper's own tags, measured 24.1% wrong at anchor disagreements (spec), and two
of the errors above are demonstrably the tape's fault, not the rung's. Phase A's
M1 gate was itself recorded as *unresolvable as specified* because the reference
quantity does not exist; that reading stands, and the comparison above is
offered as a bound, not a settled gate.

M1 re-run on this branch for drift (`scripts/blind_tag_gapfill.py`, repaired —
it had not imported since Task 5 removed `gather._sibling_titles`): **6,815
distinct adoptions, raw wrong rate 8.77%** against Phase A's 6,546 / 8.77%. The
rate is unchanged to two decimals; the population grew by 269 adoptions, which
is the numeric widening plus the removed positional sibling rung.

---

## Step 3 — the six-show table (REAL)

`./.venv/bin/python scripts/sibling_controls.py --six-shows`, over every library
show carrying an `unresolved` track.

| show | unresolved | donor | agreement | anchors | band | proposals on unresolved | automatic |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `yondermountainstringband-2005-12-31` | 24 | `ymsb2005-12-31.flac16` | — | 0 | `no-anchors` | 24 rendered (**23 adopt-verdict, 23 correct**, track 1 declined) | **0** |
| `delmccouryband-2003-04-19` | 8 | `del2003-04-19` | **0.6923** | 13 | `operator` | **5** | **0** |
| `trampledbyturtles-2007-07-20` | 1 | `tbt2007-07-20.391.flac16` | 0.909 | 22 | `auto` | 1 | **1** |
| `yondermountainstringband-2002-12-31` | 38 | `ymsb2002-12-31.fullshow` | — | 0 | `no-anchors` | 0 | 0 |
| `greenskybluegrass-2007-08-05` | 1 | — | — | — | no qualifying donor | 0 | 0 |
| `infamousstringdusters-2014-03-15` | 3 | — | — | — | no qualifying donor | 0 | 0 |

**ymsb2005** — expected 23 correct rows + track 1 declined; measured exactly
that, by string, against `YMSB_TRUTH`. It recovers both reprises setlist.fm
drops and reproduces both merges (`Peace Of Mind > King Ebenezer Rap`,
`If You're Ever In Oklahoma > Spanish Harlem Incident`). Phase B's canonical DP
rendered 13 of 22 wrong here.

**delmccoury** — expected: operator band at 0.69, 5 correct fills proposed, 4
disagreements displayed. Measured: agreement **0.6923** (9/13), band `operator`,
**5** proposals on unresolved tracks (t1 `Travelin Teardrop Blues`, t5 `Just
Because`, t6 `Learning the Blues`, t8 `Nashville Cats`, t16 `Blackjack County
Chains`), **4** disagreements — tracks 2, 3, 4 and the t10 comparator near-miss
`Rain Please Go Away` / `Rain go away (?)`. Reproduces the spec to the digit.

The tracks 2–4 disagreement is settled here in the sibling's favour, and the
adjudication is worth recording because the spec's parenthetical is slightly
wrong. Both tapes hold **21 tracks** and align 1:1 with residuals of 0–2 s on
every row, so the correspondence is forced. The donor's description is a
complete numbered 21-item list; the target's description is the *same defective
list as its own tags* (it omits `Count Me Out` and leaves 8 slots blank), so it
is not an independent third source — it is the same uploader's single mistake,
appearing twice. The forced 1:1 alignment is the evidence, and it says the
tape's tags 2–4 are shifted by one.

**TBT `1922`** — the spec's composition note expected this to arrive via
`setlist-gap` once the numeric fix landed. **It arrives via `sibling-align`
instead**, because that rung runs earlier in the cascade. Row: track 21,
`TBT2007-07-20D2T08.mp3` → `1922`, residual **0 s**, penalty 406 s, bracketed by
agreeing anchors at t20 (`Valley`) and t22 (`Trouble`) and count-forced between
them. Correct.

**The automatic band's library yield: expected 0 tracks, measured 1.** This is a
deviation from the spec's stated result and is recorded as one, not explained
away. The direction is safe (the title is correct and independently expected by
the spec's own composition note), but **the spec's "0 tracks" sentence should be
amended to "1 track, `1922`, via `sibling-align` rather than `setlist-gap`."**

---

## Step 4 — the full-library re-gather (REAL)

`./.venv/bin/python scripts/regather_diff.py --arm sibling`, offline
(`setlistfm=None`, `FakeProvider`, cached metadata only).

```
arm=sibling: compared 89 shows (0 skipped)
0 regressions; 1 newly resolved
  ADOPTED  trampledbyturtles-2007-07-20 t21: unresolved/'TBT2007-07-20D2T08.mp3' -> sibling-align/'1922'
```

- **Every currently-resolved track's title is byte-identical** with the rung
  wired and unwired, across all 89 shows. 0 regressions.
- **The complete diff is one row**, hand-checked above.

### The setlist.fm arm

Run live with the key active over all six shows carrying unresolved tracks:
**0 tracks differ between the offline and setlist.fm arms on any of the six.**

That is not a degenerate result — the canonicals genuinely differ:

| show | offline canonical | setlist.fm canonical |
| --- | --- | --- |
| `yondermountainstringband-2005-12-31` | `chosen`, **25 items** | `setlist.fm`, **23 items** |
| `trampledbyturtles-2007-07-20` | `lma:tbt2007-07-20.391.flac16`, **28 items** | `setlist.fm`, **23 items** |
| `delmccouryband-2003-04-19` | `lma:del2003-04-19`, 22 items | `lma:del2003-04-19`, 22 items (setlist.fm has nothing) |

**Finding: on these six shows the canonical-source difference does not reach a
single shipped title.** Phase B's arm disagreement was in the *canonical*, and
it stops there, because the setlist rung resolves nothing on a wholly untagged
tape either way. The sibling arm never consults the canonical at all — it is
tape-against-tape — so the only path by which setlist.fm could move its output
is by changing which tracks are still `unresolved` when it runs, and on this
library it does not.

---

## Step 6 — the `_hygienic` exposure (REAL)

`./.venv/bin/python scripts/regather_diff.py --arm numeric` turns off
`is_real_title`'s pure-4-digit clause and re-gathers the whole library.

```
arm=numeric: compared 89 shows (0 skipped)
0 regressions; 1 newly resolved
  ADOPTED  trampledbyturtles-2007-07-20 t21: unresolved/'TBT2007-07-20D2T08.mp3' -> sibling-align/'1922'
```

**Measured: 0 of the 18 pure-4-digit canonical items alter a shipped track title
in a real re-gather of the 89-show library; 18 remains the UPPER BOUND on
exposure over the `iacache` corpus it was drawn from, and is not the exposure.**
The one title the widening moves is `1922` — the case it exists for.

**One caveat, stated in the same breath as the number, because it changes what
the 0 means:** none of the 18 items is present in `~/.llama/cache` at all (all
18 checked by identifier). So the 0 is a true measurement of *this library's*
exposure and **not** a test of the 18 — the library re-gather could not have
exercised them. The 18 stay filed as the `iacache`-corpus bound; if a future
library ever draws one of those items in, this measurement must be re-taken.

Because the exposure is 0, **no member of the 18 becomes a named regression
class here.** One unrelated silent-adoption defect did surface, below.

---

## Step 7 — the target-side skip (REAL)

`--row-census align.jsonl`, over all 11,258 cached alignments / 230,600 rows.

| quantity | pairs | rows | share of rows |
| --- | --- | --- | --- |
| target-side skip (`no sibling track`) | 258 (2.3%) | **474** | **0.21%** |
| donor song split across target files (declines every row it covers) | 6,488 (57.6%) | **38,435** | **16.7%** |
| merged pairing (one target file, ≥2 donor tracks) | 6,466 (57.4%) | 16,618 | 7.2% |

Skips per pair: 11,000 pairs have none, 161 have one, 33 two, 34 three, 16 four,
14 five or more.

**The decision criterion, with numbers.** A target-side skip is confirmed
structurally rare — **0.21% of rows, 2.3% of pairs** — exactly as the module
docstring argues. But the absorption the DP prefers instead is **81× more
expensive in rows**: 38,435 rows are declined because a donor song was spread
across several target files, each such run losing every row it covers. That is
the multi-row cost, sized. It is a **yield** cost only — a split declines rows,
it never ships a wrong title — so nothing here argues for adding the
skip-preferring tie-break Task 3 deliberately withheld. A future phase wanting
that yield now has the number it would be buying: up to 38,435 SYNTH-population
rows, on a change that would silently re-decide which of two equal-cost
solutions wins.

---

## Steps 8 and 9 — the shipped guard, and C+'s precision

### Step 8 — the scorer measures the shipped guard

The scorer calls `siblings.rate_alignment` and `siblings.cplus_filter`
directly; it never re-derives agreement. `_anchor_row`'s narrowing —
`bool(row.proposed)` on top of the spec's literal denominator, so a tagged track
paired with an *untitled* donor is neither an agreeing nor a disagreeing anchor
— is therefore inherited rather than restated.

**Reconciliation, the acceptance:** `--reconcile align.jsonl --reconcile-n 40`
re-runs the **live** `gather.best_donor` → `rate_alignment` → `cplus_filter`
path and requires identical donor, agreement, band, **and adopted title
strings**.

```
RECONCILE: 40 targets, 0 mismatched
  bands: {'auto': 31, 'operator': 8, 'declined': 1}
  non-empty adopted-title sets compared: 31 (612 title strings)
  -> PASS
```

The second line is the anti-degeneracy guard: "0 mismatched" over 40 empty title
sets would compare nothing and read as a pass. 612 strings were compared.

### Step 9 — is the localised donor-span slide real?

**REAL arm, no mask.** `--slide-scan`: a ≥95%-tagged tape is its own ground
truth, so every paired track is an anchor and a displacement is directly
visible. A pair counts when its agreement is ≥ `AUTO` (0.80) **and** some run of
≥2 consecutive disagreeing anchors has, for every member, a proposal that
loosely matches the tape's own title at one **constant non-zero offset**.

All of the following is computed by the committed script —
`--slide-scan` for the census and `--slide-rank align.jsonl` for the
winner/outranked split, which recomputes the winner for each target with the
shipped `rate_alignment` and the shipped `gather._donor_key`. (An earlier draft
had no committed mode for the 135/1 split and quoted per-performance counts that
reconciled under no grouping; both are fixed.)

| quantity | REAL, unmasked | unit |
| --- | --- | --- |
| (target, donor) pairs rated | **11,258** | pairs |
| pairs reaching the automatic band | **8,355** | pairs |
| pairs exhibiting a localised slide | **136** (1.63% of auto-band pairs) | pairs |
| distinct targets carrying one | **75** (of 716) | target recordings |
| slide pairs whose donor **is** its target's agreement-winner | **1** | pairs |
| slide pairs outranked by a cleaner donor of the same performance | **135** | pairs |
| of the 1 winner, targets with **exactly one** usable donor | **1** | target recordings |

**The class is REAL. It is not a synthesis artifact, and the spec's n=1 is
wrong by two orders of magnitude.** 136 pairs, at agreements from 0.800 to
0.926, with runs of 2–4 tracks at offsets ±1 and ±2. By performance, and these
sum to exactly 136:

`gd1978-07-08` 28 · `gd1971-08-06` 18 · `gd1989-10-26` 16 · `gd1984-10-12` 14 ·
`gd1973-02-15` 12 · `gd1987-09-18` 11 · `gd1982-10-10` 8 · `gd1976-06-14` 6 ·
`gd1977-05-09` 6 · `gd1971-04-29` 4 · `gd1974-07-19` 4 · `gd1975-09-28` 4 ·
`gd1973-05-26` 2 · `gd1976-06-09` 1 · `gd1990-03-29` 1 · `tbt2007-07-20` 1.

(Grouping a performance requires folding archive.org's two date conventions —
`gd1973-02-15…` and `gd73-02-15…` are the same night. Keying them apart is what
made the earlier draft's counts reconcile to nothing.)

**Why it is nevertheless unreachable in production — stated in the weaker and
more accurate form.** An earlier draft said "the tie-break eliminated 135",
which reads as a filter removing a failure class. It is not. `best_donor`
*selects among donors*, and a displaced pairing scores lower agreement than a
clean one, so **where a better donor of the same performance exists, the slide
pair simply is not the one used**. "The tie-break eliminated 135" and "135 of
the slide pairs are multi-donor" are **one observation, not two independent
ones** — a tie-break needs ≥2 donors to exist at all. The safety it provides is
real but incidental to its purpose, which is still worth knowing before anyone
"simplifies" `_donor_key`.

### The single-donor slice — where no tie-break exists

Measured separately (read-only, same detector, `--slide-rank`'s
`donors_for_target` and a follow-up census; report retained in the run
scratchpad):

| population | unit | with ≥1 usable donor | with **exactly 1** |
| --- | --- | --- | --- |
| detector population (≥95%-tagged targets, ≥6 kept tracks) | target recordings | **716** | **9 (1.26%)** |
| all cached recordings, `load_donor_tapes`-qualifying donors, no tagging gate | recordings | 790 of 968 (denominator disputed — see note below) | **14 (1.77–1.79%)** |

**Denominator discrepancy, disclosed rather than resolved.** The 790-of-968
row above is this document's original figure; the run that produced it is
not retained in the scratchpad, so it cannot be re-derived against its own
population. A later scoped re-review reconstructed the same population
independently twice and got **782** both times. A further independent
recount for this correction got 782 as well, by the same method stated
precisely: `build_candidates(ia)` over the cache, then per recording —
`filter_files` + the `MIN_TRACKS` (6) floor, all per-track durations
present, **no** `WELL_TAGGED` title-fraction gate — then keep it if
`load_donor_tapes` returns at least one donor. But that recount ran against
`~/.llama/cache` as it stood on 2026-09-03: **981** cached `md_*.json`
items, not the 968 this document's own SYNTH population (716 targets) was
measured against — the cache grew by roughly a dozen items in the interim.
The cache is not a frozen artifact, so none of the three 782s actually
confirm what 790 should have been against its *own* population; they
confirm what a slightly larger population yields. **What does not move: the
single-donor count is 14 in the original write-up and in all three
independent recounts**, so the finding this table exists to support — one
measured single-donor encounter with the slide class, stopped by layer 3
and by C+ — is unaffected by which denominator is correct.

**The unit is the target recording, not the performance**, because
`best_donor`'s tie-break is evaluated per target: a 2-recording performance
yields two single-donor targets. 5 of the 9 are same-item format twins
(`flac16`/`flac24`, `flac16`/`flac16.wav`) rather than genuinely different
tapes.

**Exactly 1 slide case falls in that slice, and it is the same tape as the one
survivor above** — so "the 1 survivor of donor selection" and "the only
single-donor slide" are one pair, and the 135/1 split partitions exactly along
the multi-donor/single-donor line by construction rather than by luck.

`TBT2007-07-20.sbd.flac` ← `tbt2007-07-20.391.flac16`, agreement 0.909 over 22
anchors, tracks 1–2 displaced at offset +1 (the target has a `Wizard Intro`,
288 s, the donor lacks). It is stopped **twice over**:

| layer | verdict on tracks 1–2 |
| --- | --- |
| donor tie-break | **absent by construction** — sole usable donor, nothing to outrank it |
| **layer 3** (`penalty < MIN_EXCLUSION_PENALTY = 60`) | **stops it**: t1 declines at 28 s, t2 at 0 s. `propose_rows` reads only durations and donor tags, so this is mask-independent and exact, not a counterfactual |
| **guard C+** | **would also stop it**: masking tracks 1–2 (what production sees when they are untagged) leaves the band `auto` at agreement 1.000, so C+ *is* reached; forcing the two rows to `adopt` and calling `cplus_filter` returns **`decline` — "tracks 1-2: not bracketed by agreeing anchors"**, a leading-edge run |

That is Task 4's mechanistic argument (*the ambiguity that lets an alignment
slide is the same quantity the penalty measures*), observed rather than argued.
**And it is the only measured encounter C+ has with its own class in the
single-donor slice — on which it declined correctly. One case is not a rate,
and this document does not turn it into one.**

Net for the REAL corpus: **136 slide-shaped pairs, 0 slide-induced wrong titles
reaching C+, 0 reaching the library.**

### THE DECISIVE QUESTION — C+'s precision, both counts, both units

Of the rows C+ declines that the ratio band would otherwise have adopted, how
many would have been **wrong** and how many **right**?

**SYNTH** (masked arm, 716 targets) — the two are never pooled with the REAL row
below, and neither is summed with it:

| arm | blocked (entries) | **wrong** | **right** | blocked (distinct) | **wrong** | **right** |
| --- | --- | --- | --- | --- | --- | --- |
| random mask | 12,388 | **417** | **11,971** | 4,636 | **153** | **4,483** |
| prefix mask | 14,789 | **269** | **14,520** | 8,906 | **188** | **8,718** |

**REAL** (one named pair, its donor forced; a single case, not a rate):

| pair | blocked rows | **wrong** | **right** |
| --- | --- | --- | --- |
| `gd1971-08-06.aud.wolfe…` ← `…mtx.seamons.96668`, worst cell | 9 | **8** | **1** |

**N is large. This is not outcome (c).** Under the random mask C+ blocks
**28.7 correct titles for every wrong one**; under the prefix mask, 54:1 — and
there it blocks *everything*, which is the design's stated cost, not a surprise.

Three readings that the raw ratio hides, all of which the owner needs:

1. **The blocked population is 4× more error-prone than the admitted one.**
   Random mask: blocked error 417/12,388 = **3.37%**; admitted error
   510/61,626 = **0.83%**. C+ is not blocking at random — it is selecting a
   materially worse subpopulation. It is just not selecting a *mostly-wrong*
   one.
2. **On its own primary class it is enriched, and the factor depends on which
   quantity you name — so all three are named.** Triaging the blocked errors the
   same way as the adopted ones (same classifier, same units): random-mask
   blocked errors are 74 distinct `genuine`, 45 `non-song`, **20 `shift`**, 14
   `variant` — against **3** distinct `shift` among the 148 admitted errors, of
   which one is tape-wrong and two are a `Tuning` label coinciding with a
   neighbour.
   - **Raw count ratio: 20 vs 3 (6.7:1).** This is a count comparison, not a
     rate, and the two populations are different sizes — an earlier draft called
     it "6.7× enrichment", which named the wrong quantity.
   - **As a share of each population's wrong rows: 13.1% vs 2.0% — 6.5×.**
   - **As a rate over each population's rows: 0.431% (20/4,636) vs 0.023%
     (3/13,291) — 19.1×.**

   The 20 blocked shifts are substantive:
   `gd1971-04-29` tracks 20–26 (a seven-track displacement), `gd1973-02-15`
   t23, `gd1980-11-30` t10, `gd1987-09-18`'s filler tracks, and the
   `gd1976-06-14` tape-tag case in both directions. **C+ is catching the class
   it was built for.**
3. **The one cell where C+ blocks mostly-wrong is the named regression pair**,
   with the donor forced: bare ratio 11 adopted / 8 wrong → C+ 2 adopted /
   0 wrong. Under shipped donor selection that donor does not win, which is why
   the corpus-wide ratio looks so lopsided.

**Ruling as the plan frames it: this is between (a) and (b), and closer to (b)
on volume while landing on (a) on class.** C+ prevents real errors — 417 under
the random mask, 8 on the named pair, and it is the only layer that catches the
`gd1971-04-29`-shaped displacements — but it pays for them with roughly 29
correct titles each, on a population where those correct titles would otherwise
ship. **Under every reading C+ stays**, as the plan requires: a silent adopter
is the one surface where being wrong is unrecoverable, and the corpus is 89
shows.

**Required spec amendment.** The spec justifies C+ on the localised-shift case
as the class it exists to catch, citing n=1. Both halves now need correcting,
in opposite directions:

- The class is **real and common in the raw corpus** (136 pairs, not 1) — the
  spec's "the class is n=1 … the empirical base thin" is superseded.
- **It is nonetheless not what C+ is currently earning its keep on in
  production**, because donor selection removes 135/136 and layer 3 removes the
  last one. C+'s measured value in this corpus is the enrichment in
  point 2 above, at a quantified yield cost of **11,971 correct titles per
  11,971 + 417 blocked** (random mask, SYNTH). The spec must state the cost in
  those words and must not imply a frequency the automatic band does not see.

---

## Named regression class: a filename-shaped donor tag ships verbatim

**The only defect this run found that reaches a shipped title.** Not one of the
18; unrelated to the numeric widening; pre-existing in `clean_tag_titles` /
`hygienic_title` but **newly propagated to a different tape** by this rung.

`gd1973-08-01.148528.sbd.flac16.wake-of-the-flood-outtakes.flac16` tags every
track with a filename/lineage stamp:

```
gd19730800.07.weather report suite
gd19730800.09.weather report suite take 3
gd19730800.03.let me sing my blues away
```

`hygienic_title('gd19730800.07.weather report suite', set()) is True` — it has
≥3 ASCII letters, is not `is_junk_title`, is inside `MAX_TITLE_LEN`, and matches
no show-metadata norm. `clean_tag_titles`' leading-track-number strip does not
fire because `titles._TRACK_NUM_PREFIX` is bounded at `\d{1,3}` (deliberately —
it is what protects `1952 Vincent Black Lightning` and a bare `2001`, and must
never be widened to `\d+`).

The same shape appears on other tapes as `s1t04 Jack-A-Roe`, `s1t08 Memphis
Blues Again`, `Disc01,Track09 Masterpiece`, `s1 t07 Techincal Difficulties`.

Blast radius, measured: **0 tracks in the 89-show library** (neither
`gd1973-08-01` item is a library show, and the re-gather diff is one row). In
the SYNTH arm it accounts for 4 of the 510 wrong entries. **Filed, not fixed** —
fixing it means widening a title cleaner whose narrowness is itself pinned by
tests, which is a change with its own corpus sweep, not a Task 7 edit.

---

## What would falsify this evidence

Carried from the spec, with what this run changed:

- **The synthetic population.** Still the biggest hole. 716 masked targets, 0
  real partly-tagged ones. The random mask flatters the guard; the prefix mask
  is the realistic taper and gets nothing automatic at all. If a corpus of
  genuinely partly-tagged tapes ever exists, every SYNTH table above is re-taken
  on it before the bands are defended with these numbers.
- **The wrong-anchor interaction is still unmeasured.** SYNTH anchors are
  correct by construction. The REAL arm has no hidden ground truth. Nothing
  here closes it.
- **The localised-shift class is no longer n=1** — it is 136 — and for the 135
  multi-donor pairs its production reachability rests on **donor selection**,
  which was never designed as a guard. Anything that changes `_donor_key`'s
  ordering re-opens those. **The single-donor slice, where no tie-break exists,
  is now sized: 9 of 716 target recordings (1.26%), or 14 of 790 without the
  tagging gate (denominator disputed, see the note under "The single-donor
  slice" — three independent recounts got 782 instead, but not against the
  original run's own population; the numerator, 14, is unaffected either
  way), containing exactly 1 slide case** — stopped by layer 3 and
  independently by C+. That is one case, not a rate; a second single-donor slide
  that layer 3 admitted would be the falsifier, and nothing here rules it out.
- **Comparator fragility.** 74 of 80 hand-reviewed `genuine` errors turned out
  to be `loosely_same_title` misses. Any change to it moves every agreement
  number, shifts the knee, and re-runs everything above.
- **Ground-truth noise ceiling.** Every rate is an upper bound against tags the
  spec measures 24.1% wrong at disagreements; two of this run's four
  genuinely-wrong entries are demonstrably the tape's fault.
- **The no-jerrybase double-date hole.** No wrong-performance donor passed the
  ratio band anywhere in 11,258 REAL pairs; A5's forced ones scored 0.083 and
  0.000. The argument stands, unchanged.
- **The `1922` yield.** The automatic band's library yield is 1, not 0. If a
  future re-gather moves it back to `setlist-gap` (or to 0), that is expected
  cascade behaviour and not a regression — but the spec should say which.

## Reproducing

```console
$ ./.venv/bin/python scripts/sibling_blind_arm.py --build-cache align.jsonl --progress 20
$ ./.venv/bin/python scripts/sibling_blind_arm.py --schema align.jsonl --dump detail.json
$ ./.venv/bin/python scripts/sibling_blind_arm.py --selftest align.jsonl   # all 716 targets
$ ./.venv/bin/python scripts/sibling_blind_arm.py --oracle align.jsonl
$ ./.venv/bin/python scripts/sibling_blind_arm.py --reconcile align.jsonl --reconcile-n 40
$ ./.venv/bin/python scripts/sibling_blind_arm.py --reconcile align.jsonl --reconcile-n 40 --plant
$ ./.venv/bin/python scripts/sibling_blind_arm.py --score align.jsonl --dump detail.json
$ ./.venv/bin/python scripts/sibling_blind_arm.py --triage detail.json --truths align.jsonl
$ ./.venv/bin/python scripts/sibling_blind_arm.py --row-census align.jsonl
$ ./.venv/bin/python scripts/sibling_blind_arm.py --slide-scan
$ ./.venv/bin/python scripts/sibling_blind_arm.py --slide-rank align.jsonl
$ ./.venv/bin/python scripts/sibling_controls.py --baseline
$ ./.venv/bin/python scripts/sibling_controls.py --deletions
$ ./.venv/bin/python scripts/sibling_controls.py --rotation align.jsonl --n 120
$ ./.venv/bin/python scripts/sibling_controls.py --localised-shift
$ ./.venv/bin/python scripts/sibling_controls.py --wrong-performance
$ ./.venv/bin/python scripts/sibling_controls.py --six-shows
$ ./.venv/bin/python scripts/regather_diff.py --arm sibling
$ ./.venv/bin/python scripts/regather_diff.py --arm numeric
$ ./.venv/bin/python scripts/regather_diff.py --arm gap --selftest
$ ./.venv/bin/python scripts/regather_diff.py --arm gap --selftest-regress
$ ./.venv/bin/python scripts/regather_diff.py --arm sibling --selftest-regress
$ ./.venv/bin/python scripts/regather_diff.py --arm numeric --selftest-regress
```

All read-only against `~/.llama/cache` and `~/.llama/shows`; the setlist.fm arm
is the only one that touches the network.
