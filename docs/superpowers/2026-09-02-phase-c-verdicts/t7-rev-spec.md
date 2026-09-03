# Task 7 — SPEC-COMPLIANCE REVIEW (ship gate)

# SPEC OK (PASS)

Pointer guard `PTH-GUARD: OK`. Worktree clean, no commits, nothing modified.
Everything below was **re-run independently** from a cache I built myself
(`--build-cache`, 716 targets / 11,258 pairs / 230,600 rows — the documented
population reproduced exactly), not read off the implementer's report.

---

## 1. The spec amendment (`905007a`, +49/-7) — the thing to check hardest

Read at `19b4ef1` and `905007a` side by side. **No threshold, gate, or safety
claim was weakened. No production code changed anywhere in the range** —
`git diff --stat 19b4ef1..905007a` is docs + `scripts/` only (0 lines under
`packages/`), so the "measurement, not behaviour" bar holds structurally.
`AUTO=0.80`, `FLOOR=0.50`, `MIN_ANCHORS=2`, `MAX_MERGE`, `SKIP_COST_MULT`,
`MIN_EXCLUSION_PENALTY=60`, `MIN_MATCH_FRACTION` are all untouched.

| # | amended claim | verdict |
| --- | --- | --- |
| 1 | localised-shift class "n=1 ... empirical base thin" -> **136 REAL pairs, 1.63% of auto-band, 75 targets** | **HONEST RECORD.** Moves the claim in the *unflattering* direction (the class is 136x more common than the spec claimed) and then states the two removers. A softener would have gone the other way. |
| 2 | automatic library yield **0 -> 1 track** (TBT t21 `1922`, via `sibling-align` not `setlist-gap`) | **HONEST RECORD.** Corrects a factual prediction against measurement; also unflattering (the rung is *more* active than promised). Marked `-> REVIEW` by the instrument itself, escalated rather than absorbed. |
| 3 | C+ justified as catching the localised-shift class -> **"cheap insurance with a quantified yield cost", 28.7 correct blocked per error prevented, "never to be defended as measured necessity"** | **HONEST RECORD, and the strongest evidence against softening.** Makes C+ look *worse*, discloses a cost the spec previously hid, keeps the guard anyway. Exactly the plan's outcome (b), in the words it demanded. |
| 4 | failure-modes bullet follows #1 | **HONEST RECORD.** Replaces "C+ caught the one measured instance; the class is n=1" with the 136 + two-removers framing and names the re-opening condition (`_donor_key` ordering, single-donor performances). |

**Verdict: 4 of 4 are honest records of what was measured. None is a claim
softened so a gate would pass.**

---

## 2. The gates — measured next to expected (all re-run by me)

| gate | expected | measured (my re-run) | |
| --- | --- | --- | --- |
| S1 probe baseline | 23/23 by string | **23 adopt, 23/23 vs `YMSB_TRUTH`, 1 decline**; band `no-anchors`, 0 automatic | PASS |
| S1 A2/A3 deletions | decline orphans, 0 wrong | **A2 24/24/0 wrong/0 declined; A3 15/15/0 wrong/9 declined** | PASS |
| S1 rotation | ships zero | named arm (a) **0 automatic, 23/23 scored wrong**; corpus arm (b) 405 honest / **19 rotated, 0 WRONG** | PASS (see F2) |
| S1 prefix-mask arm | 0 in every stratum | **0 / 0 / 0** | PASS |
| S1 localised-shift pair | C+ ships 0 of the ratio's 7 | worst cell 0.833: bare ratio **11 adopted / 8 wrong**; C+ **2 adopted / 0 wrong** | PASS |
| S1 wrong-performance donor | below FLOOR 0.50 | **0.083** and **0.000**, both `declined` | PASS |
| S2 wholesale failures | zero in every stratum | prefix 0/0/0; random 0/2/2 (**4 titles / 2 pairs**, loose definition), **both hand-triaged to zero** | PASS (see F4) |
| S2 loose error <= 1.87-1.99% | at or under C+ cells | **0.80% / 0.82% / 0.96%** | PASS |
| S2 triage vs tag-rung typo baseline | genuine class compared | **4 genuinely wrong / 13,291 distinct = 0.030%** vs setlist-gap 1.54% and the >=0.60% typo floor; offered as a bound | PASS |
| S3 six-show table | ymsb 23+decline; delmccoury 0.69/5/4; TBT `1922` | **reproduced to the digit** (0.6923, 13 anchors, 5 proposals, 4 disagreements; TBT 0.909, 22 anchors, band `auto`) | PASS |
| S3 automatic library yield 0 | 0 | **1** | DEVIATION, escalated |
| S4 re-gather diff | every resolved track byte-identical | **89 shows, 0 skipped, 0 regressions, diff = 1 row** (`1922`) | PASS |
| S6 `_hygienic` exposure | measured number led, 18 as population, bound-vs-measured in one sentence | **0 of 18 alter a shipped title**; 18 kept as the `iacache` UPPER BOUND, same sentence, plus the caveat that none of the 18 is in the cache | PASS (see F5) |
| S7 target-side skip | numbers + a decision criterion | **474 / 230,600 rows = 0.21%; 258 / 11,258 pairs = 2.3%**; absorption alternative **38,435 rows (16.7%), 81x**, yield-only; criterion given | PASS |
| S8 scorer measures the SHIPPED guard | must CALL `rate_alignment` | **confirmed by source**: imports and calls `rate_alignment`/`cplus_filter`; `--reconcile` calls live `gather.best_donor`. 40 targets, `{auto 31, operator 8, declined 1}`, **612 title strings, 0 mismatches**, prints `DEGENERATE` if 0 | PASS |
| S9 slide real? + C+ precision both counts | count + population, labelled, never pooled | **136 / 8,355 auto-band (1.63%), 75 targets, 0.800-0.926 — reproduced exactly.** C+ precision: random **417 wrong / 11,971 right** (12,388), prefix **269 / 14,520** (14,789), **28.7:1** and **54:1** | PASS |
| Suite | 1642 passed, 7 deselected | **1642 passed, 7 deselected** | PASS |
| Doc at cited path | exact filename | present, 644 lines; **both `siblings.py` DO-NOT-RETUNE blocks cite it by filename** | PASS |

Every headline number reproduced **exactly**: population 716/11,258/230,600;
schema 0 violations; strata adopted 34,161/20,167/7,298, wrong 274/166/70;
blocked 12,388/14,789 split 417+11,971 and 269+14,520; row census
258/38,435/6,488/16,618/6,466 and skip histogram 11,000/161/33/34/16/14;
slide 136/8,355/75; M1 6,815 adoptions at 8.77%.

---

## 3. Findings

**F1 — MEDIUM. `--selftest`'s cited numbers do not reproduce, and the committed
instrument's own gate now prints FAIL.** Doc and report cite "TRUTH 74/74,
POISON 74/74". Running the doc's own reproduce block at HEAD against a cache
built by the committed script gives **TRUTH 247/247 -> PASS, POISON 246/247 ->
FAIL, DEGENERACY -> FAIL, exit 1**. `_selftest` is deterministic given the cache
(first 40 entries, `random_hidden(..., seed=11)`), was introduced once in
`915d799` and never modified, and `build_cache` is unchanged across
`a755c47`/`4213e33` — so 74/74 was taken against some other cache state and is
not re-derivable from the documented steps. **I diagnosed the single leak and it
is benign:** `gd1968-10-12.sbd.gans.miller.owen.9385.shnf` t15, truth `'Jam >'`,
proposed `'Jam \'` — tracks 15 and 17 share that title, so the poison rotated a
Jam onto a Jam and *failed to corrupt that row*. Plant artifact, **not** scorer
blindness. Substance of proof 2 stands (plants non-empty, decisively opposed,
TRUTH perfect). But a ship-gate doc needs re-derivable instrument proofs, and
the next reader following "Reproducing" hits an exit-1 FAIL on line 3. **Fix is
small: re-take the number at HEAD and have the plant skip rows whose rotated
title is `loosely_same_title` to the truth.** Not blocking — no measurement
depends on it.

**F2 — LOW, ruled NOT a softened gate.** The brief says "rotation control ships
zero". The **named** control (arm a) ships **0** — met as written. Corpus arm
(b) is an extension beyond the brief; it ships 19 and gates on "0 wrong", and an
earlier log line shows it printing `-> FAIL` before the two-arm split. **I
verified the redefinition empirically rather than accepting the explanation:
reproduced 405 honest / 19 rotated / 0 WRONG.** The mechanism — a donor carrying
an extra leading track is *already* displaced, so rotating it *corrects* the
correspondence — is sound, stated in the code docstring and in the doc under
"Rotation arm (b) is a weaker instrument than it looks, and this is stated
rather than hidden", and confirmed by all 19 leaked titles being correct.
Honest instrument repair, disclosed.

**F3 — LOW. One table mixes SYNTH and REAL rows.** The C+ precision table
carries two SYNTH rows and one `REAL, named localised-shift pair` row. Each is
labelled and nothing is summed across them, but the standing bar reads "never
pooled in **any** table". Cosmetic; split it.

**F4 — INFO. Step 2's wholesale gate is met by adjudication, not mechanically.**
4 titles / 2 pairs trip a deliberately loose definition; both hand-triaged to
zero — one where the **adoptions are right and the tape's tags are wrong**
(adjudicated against the target's own description; DP residuals 4/6/57 s vs
191/192/238 s), one a correct 1:1 alignment with a dirty donor *string*. The
definition and both adjudications are stated so the number is re-derivable.

**F5 — INFO. Step 6's 0 is true but uninformative about the 18, and the doc says
so.** None of the 18 is in `~/.llama/cache`, so the re-gather could not exercise
them. The doc states this in the same breath, keeps 18 as the bound, and flags
the re-measure trigger. Exactly what the brief asked.

No Critical or High findings.

---

## 4. Rulings on the four escalations

**1. Yield 1, not 0 — amendment correct; no safety claim changes.** Reproduced:
`--six-shows` prints `AUTOMATIC BAND'S LIBRARY YIELD: 1 tracks (EXPECTED 0)
-> REVIEW`; both re-gather arms show the same row. The track is correct
(`1922`, residual 0 s, bracketed by agreeing anchors t20/t22, count-forced) and
the 89-show diff carries **0 regressions**, so a non-zero yield weakens no
safety claim — it falsifies a prediction about *which rung* fires. **Accept the
amendment over the prediction.**

**2. Step 9 inverts the prior — VERIFIED in full; serious but correctly
stated.** Re-ran `--slide-scan`: **136 slides / 8,355 auto-band / 75 targets /
0.800-0.926** — exact match. I verified the unreachability mechanism
*independently*: recomputing every target's winner under the shipped
`_donor_key` (confirmed by source to sort `(-agreement, cost, identifier)`)
gives **slide donor is winner: 1; outranked: 135**, sole survivor
`TBT2007-07-20.sbd.flac` <- `tbt2007-07-20.391.flac16` at 0.909, tracks 1-2
offset +1. Its two displaced rows decline at layer 3 with
`weak evidence (penalty 28s)` and `(penalty 0s)` against
`MIN_EXCLUSION_PENALTY = 60.0`. **Net 0 slide-induced titles reach C+ or the
library — confirmed end to end.** Seriousness: real, and the doc states it
plainly — safety rests on a *selection* tie-break never designed as a guard, and
the single-donor sub-population is **unsized**. Named "the sharpest follow-up"
in the falsifier list and in the spec's failure-modes bullet. Right disposition
for a ship gate; **recommend the owner require the single-donor sub-population
be sized before any change to `_donor_key`'s ordering, and a test pinning that
ordering.**

**3. Filename-shaped donor tag — blast radius 0 confirmed, correctly filed.**
The 89-show diff is one row and it is `1922`; neither `gd1973-08-01` item is a
library show. Written up as a **named regression class** with its own section,
the mechanism (`hygienic_title` passes it; `_TRACK_NUM_PREFIX`'s `\d{1,3}` bound
deliberately does not strip it), sibling shapes, SYNTH cost (4 of 510 wrong
entries), and why the fix is its own phase. **Accept as filed, not fixed.**

**4. `blind_tag_gapfill.py` repair — verified.** Re-ran it: **6,815 distinct
adoptions, 598 wrong = 8.77%**, matching Phase A to two decimals. No drift.

---

## 5. Standing bars

- **Units named**: PASS. Explicit "Units" paragraph defines `trials`, entries vs
  `distinct` triples, states the two are never mixed in a ratio; table headers
  carry units.
- **SYNTH/REAL never pooled**: PASS with one exception (**F3**); nothing summed
  across them.
- **Rates as upper bounds + ground-truth caveat**: PASS, stated three times
  (instrument docstring, M1 comparison, falsifier list).
- **Doc at the exact cited path**: PASS, and **both** DO-NOT-RETUNE blocks in
  `siblings.py` cite it by filename.
- **No production behaviour changed**: PASS — zero lines under `packages/`;
  suite **1642 passed, 7 deselected**, unchanged.

## Recommendation

**Ship.** Every gate is met as written, verified by independent re-run rather
than by reading the report. The four spec amendments are honest records that
each move a claim in the direction less flattering to the work. F1 should be
corrected before the doc is treated as a reproducible reference, but it is a
documentation defect in one instrument proof whose substance I verified by
hand, and no measurement depends on it.
