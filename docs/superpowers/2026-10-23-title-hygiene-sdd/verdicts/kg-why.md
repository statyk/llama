# kg-why handback: why kinggizzardandthelizardwizard-2022-10-22 newly holds

**Verdict.** The hold is caused by **C2 (slice 3)**, and by nothing else.

- Both C2 replacements are correct.
- Together they lower deterministic `align()` coverage from **12/13 = 0.9231** to **10/13 = 0.7692**, under the 0.8 threshold.
- Either replacement alone leaves coverage at 11/13 = 0.8462, which does not hold.
- With `--disable-slices slice3` the show replays `clean`, so this is not a non-piece-3 arm difference.
- This is the only show, in either r2 view, where C2 adds a low-confidence/needs-LLM state. C2 removes that state from 6 shows (as-is) and 9 shows (fresh).
- The spec says, unconditionally, that C2 "adds no holds". The arm contradicts it.
- **Recommendation: (a) accept as a documented cost.** Correct the spec sentence and the acceptance row, and attribute the hold to slice 3.

All Python ran with each tree's own interpreter from the scratch cwd `~/.llama-harness/piece3/kg-why/scratch`. `llama.__file__` was asserted inside the tree each time:
- base: `.../title-hygiene-base/packages/llama/src/llama/__init__.py`
- candidate: `.../title-hygiene/packages/llama/src/llama/__init__.py`

No tracked file was changed (`git status` is clean). The option-(b) measurements patch `gather.align` in memory only. No LLM was called.

## 1. Coverage, computed by the real `align()` inside a one-show `replay_holds.py run`

Command: `<tree>/.venv/bin/python ~/.llama-harness/piece3/kg-why/capture.py <tree> <prefix>`. It wraps `llama.stages.gather.align`, then calls `replay_holds.main(["run","--slugs",…])`.

**Base (74ec267).** Output: `coverage 0.9231 = 12/13; canonical 14 items`; replay `clean=1`.
- Track #3 `K.G.L.W. (Outro)` is filler, which is why the denominator is 13.
- Unmatched track: #7 `Her and I (Slow Jam II)`.
- Unmatched canonical item: `['Her and I (Slow Jam 2)']`.

**Candidate (c49cdd1 code).** Output: `coverage 0.7692 = 10/13`; replay `needs-llm=1`.
- Unmatched tracks: #6, #7 and #14.
- Unmatched canonical items: `['Organ Farmer', 'Her and I (Slow Jam 2)', 'Altered Beast IV']`.

Tracks whose matched-state changes:

| Track | Base | Candidate | Why |
|---|---|---|---|
| #6 | `Organ Farmer`, matched | `Her and I (part one)`, unmatched | `fuzzy_title_eq('Her and I (part one)', 'Her and I (Slow Jam 2)')` is False: the norms `her and i part one` and `her and i slow jam 2` differ in the subtitle, not by dropping one |
| #14 | `Evil Death Roll`, matched | `Evil Death Roll`, unmatched | #13 `Evil Death Roll (part one)` fuzzy-matches the canonical `Evil Death Roll` (True), skipping `Altered Beast IV`. That consumes the last canonical item, so #14, the second half of the same song, has nothing left to match |

#13 is matched in both arms. #7 is unmatched in both arms, because `Slow Jam II` vs `Slow Jam 2` fails `fuzzy_title_eq`; that miss predates piece 3.

The root issue: `align()` handles merged tracks but not one song split across two tracks. The stale MP3 tags happened to fit setlist.fm's 14 items one-to-one, so the base scored 12/13 on wrong titles.

There is no D fill (`d_fills: []`). The earlier "D fills leave the denominator" explanation is wrong. The arm rows agree: base `outcome clean`, cand `gather_flags ['low-confidence structure alignment']`, `needs_llm ['align_structure']`, `cascade.c_changed {'6':'C2','13':'C2'}`. The as-is rows come from `accept/arms/base-asis.json` and `r2/arms/cand-asis.json`.

## 2. Cause: C2, proven three ways

**C2 disabled.** Command: `capture.py <cand tree> …/cand-noslice3 --disable-slices slice3`. Output: `replayed 1 show(s): clean=1`, `coverage 0.9231 = 12/13`, `gather_flags [] needs_llm [] title_changes []`. Slice 3 is C, per `lossless_titles.py`'s docstring.

**Counterfactuals on the candidate's own tracks and canonical.** Command: `variants.py`; output is in `cand-variants.variants.json`.

| Variant | Coverage | Hold? |
|---|---|---|
| As the candidate ships (C2 on #6 and #13) | 0.7692 = 10/13 | yes |
| Revert #6 only | 0.8462 = 11/13 | no |
| Revert #13 only | 0.8462 = 11/13 | no |
| Revert both (= base titles) | 0.9231 = 12/13 | no |
| Whole FLAC tag set (C2 plus merged #5 `Predator X > Organ Farmer` and #12 `Alter Me III > Altered Beast IV`) | 0.7692 = 10/13 | yes |

**Control.** The candidate replays without the patch (`blast.py … 0`, `--all`, both views) differ from the r2 arms on **0** shows in (outcome, low-confidence flag, needs_llm). So the current tree reproduces r2 exactly. No other piece-3 slice and no arm difference contributes.

## 3. The canonical items, and whether the new titles are right

The canonical source is setlist.fm (`slfm_936017e7….json`, also stored `structure.source`). Its 14 items, in order:

| # | Item | Note |
|---|---|---|
| 1 | Oddlife | |
| 2 | Billabong Valley | |
| 3 | K.G.L.W. | info: Outro |
| 4 | Mars for the Rich | |
| 5 | Predator X | |
| 6 | Organ Farmer | |
| 7 | Her and I (Slow Jam 2) | |
| 8 | Crumbling Castle | |
| 9 | The Fourth Colour | |
| 10 | The Grim Reaper | |
| 11 | Ice V | |
| 12 | Alter Me III | info: `>` |
| 13 | Altered Beast IV | |
| 14 | Evil Death Roll | |

At the track positions:
- Track #6 sits at item 6, `Organ Farmer`.
- Track #13 sits at item 13, `Altered Beast IV`.

That is why the base's stale tags matched setlist.fm by position.

The taper's description lists:
- `05. Predator X > Organ Farmer`
- `06. Her and I (part one) >`
- `07. Her and I (Slow Jam II)`
- `12. Alter Me III > Altered Beast IV`
- `13. Evil Death Roll (part one) >`
- `14. Evil Death Roll`

It also says: "(part one) is added for where I mistracked the songs (my apologies)". The 24-bit FLAC tags carry exactly this list. The VBR MP3 tags carry setlist.fm-shaped single titles:

| Track | MP3 tag | FLAC tag |
|---|---|---|
| #5 | `Predator X` | `Predator X > Organ Farmer` |
| #6 | `Organ Farmer` | `Her and I (part one) >` |
| #12 | `Alter Me III` | `Alter Me III > Altered Beast IV` |
| #13 | `Altered Beast IV` | `Evil Death Roll (part one) >` |

These come from `md_kglw2022-10-22.ScheopsMK41.Flac24.json`.

**So the new titles are right, and the base's #6 and #13 are wrong.** The taper says his track splits fall late, and under the steering rule the taper is presumed correct. #6 is the start of Her and I, not Organ Farmer, and #13 is the start of Evil Death Roll. The durations fit that account, though this is inference, not listening: t05 is 420 s for two songs, t06 412 s, t12 407 s for two songs, t13 437 s.

**Remaining imperfection, in both arms:** #5 ships `Predator X` and #12 ships `Alter Me III`. Each track also contains the next song. C2 does not replace them, because `agrees('Predator X', 'Predator X > Organ Farmer')` is True, so the delivered tag already agrees with the reference. This is unchanged from the base.

## 4. Spec deviation, and other shows in the same situation

The spec, `docs/superpowers/specs/2026-10-22-title-hygiene-design.md`:
- Line 57 (Goal 3): "**Replace a stale lossy-derivative title with the item's own lossless title** when the evidence favours it (C2). It adds no holds."
- Line 290 (C2 rule): "… Ship the lossless title. It adds no holds. It fixes silent errors like radiators-1991-11-01 …"

Both are unconditional. The spec does analyse coverage side-effects for D (line 215, "slice 2 consequence (1)": D fills leave `_songish_coverage`'s denominator). It never analyses C2's effect on coverage. "Adds no hold flag of its own" is a charitable reading of the intent. By the letter, this is a **spec deviation**: C2 changes independent `tags`-class titles, so it moves `align()` coverage in both directions.

Sweep of every show with a C2 entry in `cascade.c_changed`, base arm vs r2 candidate arm. Command: `python3 ~/.llama-harness/piece3/kg-why/c2_sweep.py`.

| View | Shows with a C2 change | Low-confidence/`align_structure` added | Low-confidence/`align_structure` removed |
|---|---|---|---|
| as-is | 32 | **1** (kinggizzard only) | 6: explosionsinthesky-2010-09-02, lettuce-2010-11-14, newmastersounds-2009-06-06, newmastersounds-2011-06-04, robertwalters20thcongress-2009-04-29, stuallenandmarshotel-2012-04-18 |
| fresh | 42 | **1** (kinggizzard only) | 9: the six above plus bigheadtoddandthemonsters-1991-01-21, jimlauderdale-2011-07-22, lettuce-2002-07-13 |

Some of the removing shows also carry C1 fills. No other show is in kinggizzard's situation.

The replay tags this hold `unattributed` because attribution is keyed on declines, and C2 is a change, not a decline.

**Real-world caveat.** The harness records `needs-llm`, not a confirmed hold. With a provider, gather would spend one `align_structure` call. If the LLM alignment reached 0.8 or more, the show would ship unflagged. That outcome was not measured, since no LLM was allowed.

## 5. Options (none implemented)

**(a) Accept as a documented cost. Recommended.**
- Correct spec lines 57 and 290 to say what is true: C2 raises no flag of its own, but changes alignment coverage in both directions. Measured: 1 added versus 6/9 removed.
- Fix the acceptance (d) rows: the cause is slice 3 via coverage. It is not "UNEXPLAINED", and not D.
- Optionally make replay attribute a changed align state on a show with `c_changed` to slice3.
- Cost: one packaged, not delivered, show either costs one `align_structure` call or waits for an operator `fix --overrule`. Nothing wrong ships.
- Cost if this choice is wrong: the same single show stays held. It does not compound.

**(b1) A general split-continuation rule in `align()`.** An unmatched track whose previous track matched, and whose title `fuzzy_title_eq`s that track's title, would count as matched to the same item, with the pointer unchanged. It was measured in memory over all 3983 shows.
- It fired 327 times (as-is) and 341 times (fresh), mostly on consecutive duplicate titles and on `intro` → song pairs.
- It removed low-confidence/`align_structure` from **7 shows (as-is)** and **8 (fresh)**: allenstone-2012-11-04, gratefuldead-1968-08-23, kinggizzard, lettuce-2008-08-06, mogwai-1998-11-30, mountaingoats-2017-06-02, mountaingoats-2018-04-12, plus moe-1996-04-21 in the fresh view, where it goes needs-llm → newly-held. It added none.
- Every change raises coverage, which `_songish_coverage`'s docstring calls the dangerous direction. None is hand-checked, and it touches `align()`, the do-not-retune core. Not worth it for one show.

**(b2) The same rule, gated on an explicit `(part one|1|i)` / `(pt 1)` marker on the previous track.** Measured: it fires **once** in the whole library (`('Evil Death Roll (part one)', 'Evil Death Roll')`). It clears only kinggizzard in both views (needs-llm → clean-changed) and changes nothing else.
- Coverage would rise to 11/13 = 0.846, but only because #14 is rescued. #6 still misses.
- It is a one-show rule, overfit by construction, and adds a new matching rule and spec surface to fix one show that ships nothing wrong.

**(c) Literal "C2 adds no holds".** Recompute coverage with C2 reverted, and skip the LLM call and the flag when only C2 crosses the threshold. Blast radius is 1 show by construction, per the sweep. But it justifies structural confidence with titles the same code has just ruled wrong. Not recommended.

## Files written

- In `~/.llama-harness/piece3/kg-why/`:
  - Scripts: `capture.py`, `variants.py`, `c2_sweep.py`, `blast.py`, `blast_part.py`, `blast_cmp.py`, `blast_cmp_part.py`
  - Outputs: `base.{arm,align}.json`, `cand.{arm,align}.json`, `cand-noslice3.{arm,align}.json`, `cand-variants.{arm,variants}.json`, `*.slugs`
  - In `blast/`: `ctl-{asis,fresh}.json`, `cont-{asis,fresh}.json`, `part-{asis,fresh}.json`
  - `scratch/`
- In `$D/kg-why/`: `kg-why.log` (all command output teed), `handback.md`, `done`.
