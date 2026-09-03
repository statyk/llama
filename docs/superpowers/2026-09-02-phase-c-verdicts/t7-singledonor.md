# T7 follow-up — the single-donor slice of the localised donor-span slide

**Bottom line: the gap CLOSES. The single-donor slice is tiny (9 targets), it contains
exactly ONE slide case, and that case is stopped TWICE over — by layer 3 in production, and
(verified counterfactually) by guard C+ as well. Neither defence depends on the tie-break.**

Worktree `/Users/shawn/projects/llama/.worktrees/sibling-transfer` @ `905007a`. `PTH-GUARD: OK`.
Repo untouched — `git status --porcelain` empty, no commits. All output under
`.../scratchpad/workc/t7-singledonor/` (`summary.json`, `targets.json`, `slides.json`,
`attribution.json`, drivers `singledonor.py`, `attribute.py`, `cplus_probe.py`).

## The detector — reused, not reinvented

`slide_scan` / `_localised_slide` from `scripts/sibling_blind_arm.py` (the committed harness
that produced the 136), **imported and called**, over the same unmasked corpus loop
(`build_candidates` → `load_target` → `load_donor_tapes` → `propose_rows` → `rate_alignment`).
The only thing added is the per-target segmentation key: `len(candidates)` inside
`gather.best_donor`'s loop — the count of donors that produce usable rows, i.e. exactly the
set the tie-break chooses among. **`n == 1` means no tie-break exists.** No second definition
of the slide class was written.

**Whole-population reproduction (the detector's own positive control):**
11,258 pairs / 8,355 auto-band pairs / **136 localised slides** / 75 distinct targets —
identical in every figure to Task 7 step 9. The instrument is the same instrument.

## Q1 — how large is the no-tie-break slice?

| population | unit | with ≥1 usable donor | with **exactly 1** |
| --- | --- | --- | --- |
| detector population (`~/.llama/cache`, ≥95%-tagged targets, ≥6 kept tracks) | target recordings | **716** | **9 (1.26%)** |
| all cached recordings, qualifying donors only (no tagging gate, no DP) | recordings | 790 / 968 | **14 (1.77% of 790)** |

Primary answer: **9 of 716 target recordings (1.26%)** in the detector population have exactly
one usable donor. The looser second row is the production-facing bound — it drops the
`WELL_TAGGED`/`MIN_TRACKS` gates the detector needs for ground truth, and counts
`load_donor_tapes` qualification rather than DP-usable, so it is the larger, safer number.
The unit is the **target recording**, not the performance, because `best_donor`'s tie-break is
evaluated per target: a 2-recording performance yields two single-donor targets.
Composition note: 5 of the 9 are same-item format twins (`flac16`/`flac24`,
`flac16`/`flac16.wav`), not genuinely different tapes; 4 are real distinct tapes
(the TBT pair, the Yonder Mountain 2009-04-17 pair).

## Q2 — how many single-donor cases exhibit the slide class?

**1 pair.** Denominators, all from the same run:
- **1 of 8** auto-band pairs among single-donor targets (the 9th, `ymsb2005-12-31.flac16`,
  is `no-anchors` and never reaches the band).
- **1 of 9** single-donor targets.
- **1 of 136** slide pairs corpus-wide; the other **135 are multi-donor** — which is the same
  fact Task 7 reported from the other side. A tie-break needs ≥2 donors, so "135 eliminated
  by the tie-break" and "135 are multi-donor" are one observation, not two independent ones.

The single case: target `TBT2007-07-20.sbd.flac`, donor `tbt2007-07-20.391.flac16`,
agreement 0.909 over 22 anchors, tracks 1–2 displaced at a constant offset +1. **It is the
same pair Task 7 named as the one survivor of the tie-break** — so the "1 survivor" and "the
only single-donor slide" are the same tape. That is the finding: the tie-break's 135 and layer
3's 1 partition exactly along the multi/single-donor line, by construction rather than by luck.

## Q3 — what stops it

| layer | verdict on `TBT2007-07-20.sbd.flac` ← `tbt2007-07-20.391.flac16`, tracks 1–2 |
| --- | --- |
| donor tie-break | **absent by construction** — sole donor, nothing to outrank it |
| **layer 3** (`penalty < MIN_EXCLUSION_PENALTY = 60`) | **STOPS IT.** t1 `decline`, penalty 28 s; t2 `decline`, penalty 0 s. Mask-independent (`propose_rows` reads only durations + donor tags), so this is exact, not a counterfactual |
| guard C+ | **would also stop it.** Counterfactual probe: mask tracks 1–2 (what production sees when they are untagged) → band stays `auto` (agreement 1.000), so C+ *is* reached; forcing the two rows to `adopt` and calling `cplus_filter` returns **`decline` — "tracks 1-2: not bracketed by agreeing anchors"** (a leading-edge run) |
| net | 0 titles ship on the slid run, with two independent reasons |

## Positive controls for the zero-shaped claims

The load-bearing zeros are "0 adopt rows survive on the slid run" and "0 single-donor slides
ship". Each is paired with a non-zero companion **from the same call**:

1. **Detector non-degeneracy:** the same code path returns **136** slides / 8,355 auto-band
   pairs / 75 targets corpus-wide — Task 7's figures exactly. A stub returning nothing cannot
   produce that.
2. **Row-verdict machinery non-degeneracy:** the very pair whose slid run yields 0 adopts
   carries **21 adopt rows elsewhere on the same tape**, from the same `propose_rows` call.
   Layer 3 is discriminating, not blanket-declining.
3. **C+ non-degeneracy:** `cplus_filter` returned `decline` with a C+-specific reason string
   only when the rows were **forced to `adopt` first** — proving the filter was exercised and
   is capable of a non-trivial verdict, rather than passing through rows that were already
   `decline`. Masking also moved agreement 0.909 → 1.000, showing the mask engaged.
4. **Segmentation non-degeneracy:** the single-donor bucket is **9**, not 0, and the
   usable-donor histogram is populated across 1…36.

SYNTH and REAL are not pooled anywhere here — **every figure in this report is REAL,
unmasked corpus**, except the explicitly labelled C+ counterfactual, which masks two named
tracks of one named tape and is reported as a probe, not as a rate.

## Caveats bounding the answer

- The exact (`usable`) census is over ≥95%-tagged targets, because the detector needs the
  tape's own tags as ground truth. Production's real targets are the *untagged* ones. The
  9/716 figure is therefore the rate over tapes that can be measured, not over tapes that get
  filled; the 14/790 qualifying-donor row is the wider bound that does not need tags.
- Cache-only, `setlistfm=None`, 968 cached items — the standing offline caveat.
- Target tags are the ground truth and are ~24% wrong at anchor disagreements (spec), so the
  slide count is an **upper** bound in both slices.

## Scope

Nothing was fixed, pinned, or edited. Two adjacent observations, reported not repaired:
(a) the tie-break/layer-3 partition above is structural and should be *stated* that way if the
spec ratifies it; (b) `best_donor`'s tie-break protects only the multi-donor 135 — the
single-donor slice's protection has always been layer 3 + C+, and this run is the first
measurement of that.
