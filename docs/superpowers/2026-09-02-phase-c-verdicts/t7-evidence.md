# Task 7 — the ship gate — REPORT (fix round 1)

**Status: COMPLETE. Q1–Q7 and F3 fixed; the single-donor slice folded in. Every control re-run and its output pasted below. No control was weakened to pass.**

`PTH-GUARD: OK`. Suite unchanged throughout — **1642 passed, 7 deselected** — this round changed instruments and prose, not behaviour.

## Commits (round 1 on top of `905007a`)

| sha | what |
| --- | --- |
| `dc26d1f` | Q1/Q2/Q3/Q4/Q6 — the instrument fixes |
| `3d834c7` | Q1/Q2/Q3/Q4/Q5/Q6/Q7/F3 doc corrections + single-donor fold-in |
| `83ea17f` | `--schema`'s own output names its unit; the spec carries the corrected slide framing |

Earlier: `915d799`, `a755c47`, `ffd8562`, `4213e33`, `2b21b66`, `905007a`.

```
$ ./.venv/bin/pytest -q
1642 passed, 7 deselected, 26 warnings in 5.73s
```

## Q1 — the plant failed to CORRUPT; the scorer did not fail to see

The spec reviewer's diagnosis is confirmed exactly. I reproduced the leak and isolated it:

```
LEAK gd1968-10-12.sbd.gans.miller.owen.9385.shnf t15 'Jam >' -> 'Jam \\'
```

The tape has two `Jam` tracks; the rotation landed a loosely-identical string on t15, and the scorer scored that adoption correct **because it was correct**. Fixed on the plant side only — `_plant_titles` now picks, per hidden track, a title from the same tape that is **verifiably not `loosely_same_title`** to that track's truth. The scorer is untouched and the threshold is untouched. Tracks for which no loosely-different title exists anywhere on their own tape are *unplantable*: excluded from the denominator and **counted in the printed line**, not absorbed.

`--selftest` now runs the **whole cache by default** and **names the population on its first line**, which is the other half of Q1 — the old `74/74` came from a 12-target smoke cache, not the 716-target population the tables certify.

```
$ ./.venv/bin/python scripts/sibling_blind_arm.py --selftest align.jsonl
population  : 716 targets from align.jsonl
TRUTH plant : 4146/4146 correct  -> PASS
POISON plant: 4133/4133 wrong      -> PASS  (21 track(s) had no loosely-different title on their own tape and are excluded)
DEGENERACY  : the two plants differ -> PASS
```

## Q2 — oracle A made genuinely independent

It called `build_candidates`, `load_target` and `gather.load_donor_tapes` — all used by `build_cache`, so an instrument bug moved both sides. It now **calls no function defined in the instrument file**: its own collection key, search-document shape, target test and donor test are written out. What it still shares is stated explicitly in its docstring and in the doc — the **shipped `llama` functions the population is *defined* in terms of** (`group_candidates`, `filter_files`, `clean_tag_titles`, `title_fraction`, `length_seconds`); an oracle that re-implemented `filter_files` would be measuring a different population.

```
$ ./.venv/bin/python scripts/sibling_blind_arm.py --oracle align.jsonl
oracle targets (>= 6 tracks): 716; oracle targets under 6 tracks: 6; measured: 716
  in oracle, not measured: 0 []
  measured, not in oracle: 0 []
ORACLE: -> PASS
```

## Q3 — `--arm numeric`'s zero is now falsifiable

`ARMS["numeric"] = (None, None)` made every title change legal, so no code change could have produced a regression. The source side of a legal transition is now **never** `None` (`numeric` is `("unresolved", None)`: the widening may resolve a previously-unresolved track by any rung that consults the predicate, but a change to an already-resolved track is a regression in every arm). New plant `--selftest-regress` retitles an already-resolved track:

```
$ for a in gap sibling numeric; do ./.venv/bin/python scripts/regather_diff.py --arm $a --selftest-regress | tail -1; done
SELFTEST-REGRESS (arm=gap): harness CAN report a regression -> PASS
SELFTEST-REGRESS (arm=sibling): harness CAN report a regression -> PASS
SELFTEST-REGRESS (arm=numeric): harness CAN report a regression -> PASS
```

Both real arms re-run under the tightened rule, **unchanged**:

```
arm=sibling: compared 89 shows (0 skipped)
0 regressions; 1 newly resolved
  ADOPTED  trampledbyturtles-2007-07-20 t21: unresolved/'TBT2007-07-20D2T08.mp3' -> sibling-align/'1922'
arm=numeric: compared 89 shows (0 skipped)
0 regressions; 1 newly resolved
  ADOPTED  trampledbyturtles-2007-07-20 t21: unresolved/'TBT2007-07-20D2T08.mp3' -> sibling-align/'1922'
```

## Q4 — Step 8's zero now has a plant in the committed script

`--reconcile … --plant` rotates every cached pair's proposed titles by one row, leaving the live path untouched, so a working reconciliation must report mismatches:

```
$ ./.venv/bin/python scripts/sibling_blind_arm.py --reconcile align.jsonl --reconcile-n 40
RECONCILE: 40 targets, 0 mismatched
  bands: {'auto': 31, 'operator': 8, 'declined': 1}
  non-empty adopted-title sets compared: 31 (612 title strings)
  -> PASS

$ ./.venv/bin/python scripts/sibling_blind_arm.py --reconcile align.jsonl --reconcile-n 40 --plant
RECONCILE (PLANTED): 40 targets, 40 mismatched
  PLANT expects mismatches -> PASS
```

## Q5 — the degeneracy count

Corrected: the table now has **ten** zero-shaped rows (two added this round — the numeric arm and the POISON plant's own pairing), and the prose says ten. The old "six over an eight-row table" is recorded as the error it was.

## Q6 — a committed mode computes 135/1, and the per-show counts reconcile

New `--slide-rank align.jsonl`, which recomputes each target's winner with the shipped `rate_alignment` and the shipped `gather._donor_key`:

```
pairs = 11258 | auto_band_pairs = 8355 | localised_slides = 136 | distinct_targets = 75
slide_donor_is_the_agreement_winner = 1
outranked_by_a_cleaner_donor = 135
winners_with_exactly_one_donor = 1
winner: TBT2007-07-20.sbd.flac <- tbt2007-07-20.391.flac16, agreement 0.909, run [1,2] offset +1
```

The illustrative per-performance counts were wrong because the grouping key failed on archive.org's two date conventions (`gd1973-02-15…` vs `gd73-02-15…` are the same night). `_show_key` folds both, and the counts now **sum to exactly 136**: gd1978-07-08 28 · gd1971-08-06 18 · gd1989-10-26 16 · gd1984-10-12 14 · gd1973-02-15 12 · gd1987-09-18 11 · gd1982-10-10 8 · gd1976-06-14 6 · gd1977-05-09 6 · gd1971-04-29 4 · gd1974-07-19 4 · gd1975-09-28 4 · gd1973-05-26 2 · gd1976-06-09 1 · gd1990-03-29 1 · tbt2007-07-20 1.

## Q7 — three labels renamed to the quantity they measure

| was | is |
| --- | --- |
| "11,849 trials" | **11,849 detail records**, of **12,888 trials** (716 × 3 strata × (5 random + 1 prefix)). A record is written only when a trial adopted or blocked ≥1 row. Fixed in the doc **and in `--schema`'s own output** |
| "1,059 cached items" | **968 cached `md_*.json` item records**; 1,059 is the file count of `~/.llama/cache` |
| "6.7× enrichment" | three named quantities: **20 vs 3 raw counts (6.7:1)**; **13.1% vs 2.0% as a share of each population's wrong rows (6.5×)**; **0.431% vs 0.023% as a rate over each population's rows (19.1×)** |

## F3 — SYNTH and REAL split

The C+ precision table is now two tables: a SYNTH table (random + prefix masks) and a REAL one (the single named pair, its donor forced), labelled as a single case and never summed with the SYNTH rows.

## Folded in — the single-donor slice

Incorporated into the evidence doc (Step 9) and into the spec's amended paragraph:

- **9 of 716 target recordings (1.26%)** are single-donor in the detector population; **14 of 790 (1.77%)** without the tagging gate. **The unit is the target recording, not the performance** — the tie-break is evaluated per target. 5 of the 9 are same-item format twins.
- **Exactly 1 slide case in that slice, and it is the named survivor** (`TBT2007-07-20.sbd.flac` ← `tbt2007-07-20.391.flac16`, 0.909, offset +1). Stopped by **layer 3** (28 s and 0 s, both under 60, mask-independent) **and independently by C+** (counterfactual mask → band stays `auto`, `cplus_filter` returns `decline`, "tracks 1-2: not bracketed by agreeing anchors"). `--slide-rank`'s `winners_with_exactly_one_donor = 1` reproduces the slice membership from the committed script.
- **Framing correction carried into both doc and spec**, in the weaker and accurate form: "the tie-break eliminated 135" and "135 are multi-donor" are **the same observation**. `best_donor` selects among donors; where a better donor exists the slide pair simply is not the one used. A tie-break needs ≥2 donors to exist.
- Stated plainly: on the **only** measured single-donor encounter C+ has with its own class it declined correctly, and **one case is not a rate** — the doc says exactly that and does not turn it into one.

## Unchanged from round 0

Every result stands; nothing moved. Controls all still PASS (baseline 23/23; A2 24/24; A3 15/15; rotation named 0 automatic + 23/23 scored wrong, corpus arm 405 honest / 19 rotated / **0 wrong**; prefix 0/0/0; localised shift bare 8 wrong → C+ 0 wrong; A5 0.083 / 0.000). Six-show table unchanged, library yield still **1** (`1922`) against the spec's stated 0 — that remains the one item needing an owner ruling, and the spec amendment recording it was ruled honest by the spec reviewer.

## Escalations still open for the owner

1. **Automatic library yield is 1, not the spec's 0** (`1922`, via `sibling-align` rather than the predicted `setlist-gap`). Spec amended; confirm the amendment rather than the prediction.
2. **Named regression class, filed not fixed**: a filename-shaped donor tag (`gd19730800.07.weather report suite`) clears `hygienic_title` and is proposed onto a different tape. Library blast radius 0.
3. **Single-donor slice is now sized (9 of 716) but its slide count is 1.** One case is not a rate. A second single-donor slide that layer 3 admitted is the falsifier, and nothing measured rules it out.
