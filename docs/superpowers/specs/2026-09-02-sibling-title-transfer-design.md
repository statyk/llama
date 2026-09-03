# Sibling title transfer: duration-aligning a tagged sibling onto an untagged tape

Status: revised draft for owner review, not approved, not implemented.
Date: 2026-09-02 (rev 2 — after the band sweep and guard-shape sweep; the
first draft's open decisions 1, 2 and 4 are resolved below, decision 3
remains deferred to a measurement).
Premise: the Phase B conclusion (`docs/superpowers/2026-08-31-phase-b-sdd-ledger.md`,
merged to main in `44038ae`) — duration-vs-setlist correspondence cannot
safely title an untagged tape (uniform shift, 45–52% wrong, internally
consistent so no self-check catches it), and anything that helps untagged
tapes must add **evidence**, not another gate. This design adds the
evidence: a second, independently-recorded measurement of the same event.

## The problem

The library's unresolved-title inventory is 75 tracks across 6 shows, 62 of
them in two wholly untagged tapes. The motivating case remains
`yondermountainstringband-2005-12-31`: 24 untagged files, a correct 25-item
description, a fully and correctly tagged sibling recording of the same
performance — and every rung declines, so all 24 tracks ship
`title_source="unresolved"` and the show is held. Phase B's merged
`--suggest-titles` surface (main @ `44038ae`) correctly *refuses* this show
— its guard requires anchors an untagged tape cannot have — so the surface
exists but the evidence to feed it does not.

The current sibling rung (`titles.py:~162`) is the specific thing being
replaced:

```python
elif sibling_titles and len(sibling_titles) == n:
    title, source = sibling_titles[pos], "sibling"
```

Exact count equality, then **positional** transfer. Two consequences:

- It almost never fires (21 of 2,015 library tracks), because two tapers
  rarely cut a show into the same number of files. ymsb2005's correct sibling
  has 28 tracks against 24 kept files and is rejected outright.
- When counts *do* coincide without the cuts actually corresponding, the
  transfer is positionally blind to a shift — the same failure class that
  killed Phase B's setlist DP, here with no guard at all. `_sibling_titles`'
  `all(is_real_title(t))` whole-donor gate is the only protection, and it is
  the wrong shape (below).

## Evidence

Three measurement campaigns feed this design. The probe (2026-09-01,
prototype `sibalign.py`) established the mechanism; the band sweep and the
guard-shape sweep (2026-09-02, `bandsweep/report.md` and `report2.md` in the
run scratchpad) set the thresholds and the guard's shape. The scratchpad is
not permanent, so the durable numbers are restated here.

### The population caveat — read this before any table below

**Tapers tag everything or nothing.** Over the whole cache (1,059 items, 757
recordings with ≥1 usable sibling), there are exactly **5 genuinely
partly-tagged targets** in the 20–95% own-tag range (plus 3 tapes missing a
single track's tag); 47 targets sit at exactly 0% and 702 at ≥95%. The
entire 20–95% band every threshold below was tuned on is therefore a
**synthetic arm** — well-tagged tapes with tags hidden under a labelled
mask. Numbers below are marked **SYNTH** (10,577 pairs, 5 random-hide reps
per stratum) or **REAL** (the 8 partly-tagged targets, 70 pairs; or the
6-show library table). No table mixes them, and none may in the acceptance
run either. On top of that, **every error rate everywhere is an upper
bound**: ground truth is the target taper's own tags, which the adjudication
below measures to be wrong in 24% of anchor disagreements — in several
sampled cases the sibling is the more correct source (`Goldbreaken` vs
`Goldbricking`, `Gool Lovin'` vs `Good Lovin'`).

### Probe controls (mechanism validity)

| control | result |
| --- | --- |
| baseline, honest sibling | 23 adopted, 23 correct |
| A — scorer honesty: sibling titles rotated +1/+2 | 23 adopted, 23 scored wrong (scorer can see failure) |
| A2 — sibling's **first track deleted** | 20 adopted, 20 correct, 3 declined, **0 wrong** |
| A3 — sibling's middle track deleted | 16 adopted, 16 correct, 7 declined, **0 wrong** |
| B — sibling withheld | declines, produces nothing |
| A5 — **wholly unrelated performance** as sibling | **adopts 5–7 wrong titles** |

A2/A3 are the load-bearing controls: deleting a sibling track plants exactly
the uniform shift that killed Phase B, and the method self-corrected both
times — durations discriminate where a bare count could not.

A5 is the honest defect: the per-pairing exclusion penalty measures "is there
a nearby alternative", **not** "is this alignment any good". A wholly wrong
donor still yields a locally-unambiguous, globally-garbage alignment. The
anchor-reproduction guard is what closes this; the penalty is row-level
evidence strength only, never validity. The band sweep re-confirmed this at
scale: the probe's four named wholesale failures all pass every a-priori DP
gate (`decline=None`) and are caught **only** by the anchor guard (all four
at agreement 0.00).

### The six unresolved shows, against independent ground truth (REAL)

Net: **28 of 75 unresolved tracks resolved, 28 correct, 0 wrong.**

- `ymsb2005-12-31`: 23 adopted / 23 correct / 1 declined (the one row it
  would have got wrong — the sibling has an `Intro` the target lacks). It
  recovers both reprises setlist.fm dropped and reproduces the merged
  `If You're Ever In Oklahoma > Spanish Harlem Incident`. Phase B's setlist
  DP rendered 13 of 22 wrong here; the shipped cascade resolves 0.
- `delmccouryband-2003-04-19`: 5 adopted on unresolved tracks, 5 correct —
  and the alignment shows the *target's own tags* are shifted by one at
  tracks 2–4, with the description-derived canonical (a third source)
  siding with the sibling.
- `trampledbyturtles-2007-07-20`: its one unresolved track aligned to the
  sibling's `1922` at **0 s residual** and was refused solely by
  `is_real_title` (defect 1 below).
- `ymsb2002-12-31`: declines (only sibling is 0% tagged). `greensky…` and
  `stringdusters…`: no sibling recording exists. Honest non-coverage.

Sibling supply: 67 of 89 library shows have ≥1 sibling that is ≥90% tagged
with complete per-track durations.

### The threshold curve — cumulative is flat, marginal has the knee (SYNTH)

The guard statistic: **anchor agreement** — over target tracks that still
carry a surviving real tag and that the alignment paired, the fraction whose
own tag loosely matches the donor's proposed title.

The probe's threshold table (and this spec's first draft) read the
**cumulative** error at each cut and found it nearly flat (loose error
3.14% → 2.48% across AUTO 0.50 → 0.80), concluding 0.80 was a taste call
inside a wide margin. **That reading is the misleading one, and a future
reader re-deriving it will reach the same wrong conclusion — hence this
paragraph.** 75% of all adoptions sit at agreement exactly 1.00, and that
mass drowns the cumulative signal. The decision-relevant curve is the
**marginal** error — what admitting each agreement band actually buys
(SYNTH, 50–80% stratum, loose comparator; same shape in the 20–50% and
80–95% strata):

| agreement band | adopted | marginal loose error |
| --- | --- | --- |
| [0.00, 0.30) | 1,388 | 68–99% |
| [0.30, 0.70) | 983 | **plateau, 32–40%** |
| [0.70, 0.80) | 744 | **17.3%** |
| [0.80, 0.90) | 3,513 | **6.3%** |
| [0.90, 1.00) | 7,284 | 3.8% |
| [1.00] | 41,204 | 1.9% |

The knee is at 0.80: it is the first cut whose admitted marginal band is
single-digit. Admitting 0.50–0.80 instead would buy 1,518 extra adoptions
at a 26.5% marginal error rate. **AUTO = 0.80 — the probe picked the right
number for the wrong reason.**

Two more sweep findings that bound the guard:

- **FLOOR: the probe's "every wholesale-failure pair scores 0% anchor
  agreement" is refuted at population scale**, narrowly: with wholesale
  defined over fills only, ~1.5% of wholesale pairs clear 0.50 and ~0.7%
  clear 0.80 (8 distinct pairs across all strata/reps). FLOOR's real basis
  is operator economics, not exclusion: below 0.30 proposals are 68–99%
  wrong and waste the operator's attention; 0.30–0.50 is ~40% wrong.
  **FLOOR = 0.50.**
- **The random mask flatters the guard.** Re-run with a **prefix** mask —
  the realistic pattern, a taper who tagged from the top and stopped — the
  bare ratio at AUTO 0.80 admits **89 wholesale-failure pairs per rep**
  (510 wrong titles) where the random mask admits 0. The guard-shape rules
  below (C+) ship **zero** titles under the prefix mask in every stratum:
  a prefix-tagged tape gets no automatic help at all and routes to the
  operator. That is the safe direction and is accepted as a stated cost.

### The localised shift — the failure class a global ratio cannot see

The worst guard-beating pair (`gd1971-08-06.aud.wolfe…` ←
`…mtx.seamons.96668`) is not a wholesale failure: tracks 1–4 correct, 5–10
off by one, 13–14 off, tail correct. It scored agreement exactly 0.80
because 8 of its 10 anchors landed in the two correct regions — **the guard
is a global statistic over a local failure mode.** Measured against the
candidate guard shapes in the one sweep cell that admits it: the bare ratio
ships **7 wrong titles**; a trailing-anchor rule (≥1 agreeing anchor after
the last fill) ships **the same 7** — the tape's tail is correct, so an
anchor sits after the last fill and the rule is satisfied while the interior
ships wrong; bracketed runs (C) ship 1; bracketed + count-forced (C+) ships
**0**. Trailing-anchor closes the prefix hole and is blind to the interior
one; it was measured and rejected.

**AMENDED BY THE ACCEPTANCE RUN (2026-09-03, `docs/superpowers/2026-09-02-sibling-transfer-evidence.md`). This case is
NOT n=1.** An unmasked census of all 11,258 REAL (target, donor) pairs found
**136 pairs exhibiting a localised slide** at agreement 0.80–0.93 — 1.63% of
the 8,355 pairs reaching the automatic band, over 75 distinct targets. The
draft's "empirical base thin" is superseded; the class is common in the raw
corpus. **It is nonetheless unreachable in production, and the reason splits
cleanly along one line: 135 of the 136 are MULTI-DONOR and 1 is not.** For
the 135, a displaced pairing scores lower anchor agreement than a clean one,
so `best_donor` simply selects the clean donor — stated in the weaker and
accurate form, the tie-break does not *filter* a failure class, it *selects
among donors*, and "the tie-break eliminated 135" and "135 are multi-donor"
are one observation, not two (a tie-break needs >= 2 donors to exist). For
the 1, there is no tie-break at all: the single-donor slice is **9 of 716
target recordings (1.26%)**, or **14 of 790 (1.77%)** without the tagging
gate — the unit is the target recording, since the tie-break is evaluated
per target — and it contains **exactly one** slide case, the same tape.
Its displaced rows carry exclusion penalties of 28 s and 0 s against
`MIN_EXCLUSION_PENALTY = 60`, so **layer 3** declines them, and a
counterfactual mask shows **C+ would decline them too** ("tracks 1-2: not
bracketed by agreeing anchors"). Net: 136 slide-shaped pairs, 0
slide-induced titles reaching C+, 0 reaching the library. **Anything that
changes `_donor_key`'s ordering re-opens the 135**; the single-donor slice's
only protection has always been layer 3 and C+, and one case is not a rate.

### The delmccoury class at population scale (REAL tags, adjudicated)

9,135 real-tag pairs, 9,167 disagreeing anchors, adjudicated by the
description-derived canonical as a third source: **24.1% are tape-wrong**
(sibling + canonical agree against the tape's own tag) — as common as
sibling-wrong (25.8%). "The tape's own tags are wrong" is a population-level
phenomenon, not an anecdote. Separately, only 59.3% of disagreements are
genuinely different songs; the rest are non-song cut differences
(`Drums`/`Space`/`tuning`, 22.6%), comparator misses on variants (10.1%),
and non-song-vs-non-song (7.9%) — so the agreement statistic is
systematically depressed by ~40% noise and **errs toward rejection**, the
conservative direction. Discounting tape-wrong anchors moves only 0.31% of
pairs across AUTO=0.80, so the class barely costs the automatic band — but
**31% of pairs in the operator band [0.50, 0.80) carry ≥1 tape-wrong
disagreement**, which is exactly the population the three-way disagreement
display exists for.

`Del2003-04-19.flac` reproduces to the digit: 13 anchors, agreement 0.69
(9/13), disagreements = tracks 2–4 (tape-wrong / both-present) + one
comparator near-miss. It lands in the operator band at AUTO 0.80 under
every guard shape. Counterfactually lowering AUTO to 0.65 to auto-adopt its
5 fills does not survive the guard shape either: 4 of its 5 fills sit next
to *disagreeing* anchors, so bracketing declines them (C+ adopts 1 of 5 at
AUTO 0.65). The 5 tracks go through the operator, where the display shows a
human that the tape's tracks 2–4 are the thing that is wrong.

### Real yield, stated plainly (REAL)

At AUTO 0.80 the automatic band's net yield on today's library is **1
track** — **AMENDED (2026-09-03, `docs/superpowers/2026-09-02-sibling-transfer-evidence.md`): the draft predicted 0, and
the measured value is 1.** That track is `trampledbyturtles-2007-07-20` t21
→ `1922`, residual 0 s, bracketed and count-forced; the composition note
below expected it via `setlist-gap`, but `sibling-align` runs earlier in the
cascade and gets there first. Correct title, safe direction. The draft's
reasoning, otherwise unchanged, was **0
tracks** (the sweep's full real-arm table: the only ≥0.80 partly-tagged
target's fills are already resolved by other rungs; delmccoury is 0.69;
GSBG2015-02-27 is 0.77). The automatic rung's value is **prospective** —
every future gather over the general population, where the blind arm
measures its behaviour — while today's 75-track library backlog flows
through the **operator path**: ymsb2005's 23 rows and delmccoury's 5, all
human-confirmed. The design accepts this; a rung that adopts nothing
automatically today and is measurably safe is the correct trade against one
that adopts 5 tracks by lowering AUTO into a 26.5%-marginal-error band.

## The ruling this design rests on

**An alignment is validated by reproducing independent evidence, never by
its own cost structure.** The exclusion penalty, DP cost, and match fraction
are all self-referential (A5 proved a wholly wrong donor passes them); the
target's own surviving tags are the one independent check available.

Two corollaries, both now measured:

- **Gates on evidence are per-item, never per-donor** (recurring principle,
  third instance: the `all(...)` whole-donor gate in `_sibling_titles`, the
  `sibling_item_durations` all-or-nothing diagnosis, the prototype's
  `MIN_SIB_TAGGED`) — a whole-donor gate hides correct rows behind
  unrelated bad ones (an 86%-tagged sibling refused wholesale hid 5 correct
  titles). Any future evidence gate defaults to per-item and must argue its
  way to per-donor.
- **Positioned evidence beats counted evidence.** Bracketing (anchors
  *around* the fills) subsumes an anchor-count floor: under the C+ guard,
  sweeping MIN_ANCHORS 1→5 leaves error flat (2.01–2.03%), because
  bracketing already demands ≥2 agreeing anchors placed where they matter.

Where no independent check can run (a wholly untagged tape), the human is
the guard, exactly as Phase B ruled.

## The design

### Mechanism

A new pure module, `packages/llama/src/llama/siblings.py` (`correspondence.py`
is the merged Phase B canonical-setlist DP; this is a different alignment —
tape against tape — and gets its own module). It contains the
duration-sequence DP from the prototype, unchanged in shape:

- Monotone alignment of the target's per-track durations against the
  sibling's. Ops: an a:b pairing with `min(a,b)==1` and
  `max(a,b) <= MAX_MERGE` (3), cost `|Σdur_a − Σdur_b|`; or a skip on either
  side at cost = the skipped duration. Merges, splits, extra filler on
  either side, and different track counts are all representable.
- Per-row evidence strength: re-solve with that pairing forbidden; the
  penalty is how much the best global explanation degrades without it.
- Constants, all fixed a priori in the prototype before any score was read
  and never swept: `MAX_MERGE = 3`, skip cost multiplier 1.0,
  `MIN_EXCLUSION_PENALTY = 60.0` s (mechanism-derived: boundary drift
  between two tapes of one show is ~4 s, the shortest plausible song ~90 s),
  `MIN_MATCH_FRACTION = 0.80`. These join the do-not-retune class
  (tail-guard, junk-duration, `_RECOVER_*`): every measurement above was
  taken at these values, and changing any of them invalidates all of it.

`siblings.py` is pure — it takes two loaded track lists (name, duration,
cleaned title) and returns rows + diagnostics. All IO (fetching sibling
metadata, `filter_files`, `clean_tag_titles`) stays in `gather`, matching
the existing layering (`structure.py` is pure; stages do IO).

### Donor eligibility — per-item, not per-donor

- **Required, whole-tape, structural:** complete per-track durations on both
  sides. This is genuinely global — one missing duration corrupts the whole
  DP, so it is a validity precondition, not an evidence gate.
- **Removed: the whole-donor tag-fraction gate** (`MIN_SIB_TAGGED = 0.90` in
  the prototype's first cut). A sibling track without a usable title
  declines *that row* (`sibling track untitled`); the rest of the donor's
  correct rows are kept. The delmccoury proposal exists only because of
  this change (its donor is 86% tagged).
- Donor candidates come exclusively from `candidate.recordings` — the same
  set `_sibling_titles` iterates today. Every qualifying donor is aligned;
  the adopted one is chosen deterministically: highest anchor agreement,
  then lowest DP cost, then identifier order.

### The guards

**Layer 1 — the ratio band (pair-level validity).** Anchor agreement,
computed with the loose comparator (below), over target tracks carrying a
surviving real tag that the alignment paired:

- **agreement ≥ AUTO (0.80)**: the pair is eligible for automatic adoption,
  which layer 2 then gates run by run.
- **FLOOR (0.50) ≤ agreement < AUTO**: operator band. The alignment is
  rendered as a `--suggest-titles` / triage proposal only; nothing
  automatic. Every disagreeing anchor is displayed three-ways (tape says /
  sibling says / canonical says) — 31% of this band's pairs carry a
  tape-wrong disagreement, so the display is the band's payload, not
  decoration.
- **agreement < FLOOR**: declined outright, recorded in the show's notes
  (`sibling alignment declined (anchor agreement 31%)`), not rendered even
  as a proposal — below 0.30 the marginal error is 68–99% and 0.30–0.50 is
  ~40%; a failed guard is evidence of a *bad alignment*, not weak evidence
  of a good one.
- **MIN_ANCHORS = 2** for the automatic band (bands measured over ≥2
  anchors; under it, operator path regardless of agreement). Not 5 — the
  sweep shows the break is between 1 and 2 anchors, 5 forfeits the sparse
  strata entirely for no measured gain, and under layer 2 the count floor
  is nearly redundant anyway (bracketing needs ≥2 agreeing anchors
  positioned around the fills, a strictly stronger condition than counting
  them anywhere on the tape). It stays at 2, not 1, as the last stop
  against a pair whose single agreeing anchor brackets nothing.

**Layer 2 — guard shape C+ (run-level, automatic band only).** Defined by
reuse, not reinvention, from the primitives the setlist-gap rung already
ships in `structure.py`:

- An **agreeing anchor** is a target track that still carries its own real
  tag *and* was paired by the DP with donor track(s) whose title loosely
  matches it. Its span is the donor-track interval `[min j, max j + 1)` —
  the same half-open shape `anchor_spans` returns, with the donor's track
  sequence playing the canonical's role and the DP's own pairing supplying
  the binding.
- Fill runs come from `structure.unresolved_runs`, verbatim.
- Bracketing is **`structure.gap_span`'s rule verbatim**: both flanking
  tracks must be agreeing anchors, the leading-edge exception is kept (run
  starts at track 0 with the right anchor present), and there is **no
  trailing-edge branch** — which llama removed on measured evidence for
  setlist-gap and which here also falls out structurally (a run at the
  tape's end has no track at `hi+1`). The trailing-anchor alternative was
  separately measured and rejected: it closes the prefix hole but is blind
  to the interior one (ships the localised-shift case's same 7 wrong
  titles).
- Plus `adopt_gap_titles`' second condition, **count-forcing**: the donor
  span between the two anchors holds exactly as many donor tracks as the
  run holds files. A run containing a merge is therefore declined from the
  automatic band (part of C+'s measured 4–17% yield cost vs C); the
  operator path still proposes it.
- **Runs decline individually.** One unbracketed run must not sink the
  pair: the sweep measures a checkerboard as the *default* admitted
  outcome (~half of admitted tapes decline ≥2 runs; 60–74% of declined
  runs are interior — SYNTH numbers, real run shapes are likely blockier
  and unmeasured). Each declined run records its own reason.

Measured effect of C+ over the bare ratio, worth its yield cost: **zero
wholesale-failure titles in every stratum under both masks** (the bare
ratio ships 4.8/rep random, 510/rep prefix), the localised shift's last
wrong title caught, and lower loose error in every cell (e.g. 1.87% vs
2.48% in the 50–80% stratum).

**C+'S PRECISION, MEASURED (2026-09-03, `docs/superpowers/2026-09-02-sibling-transfer-evidence.md`). Stated plainly,
because the paragraph above implies a frequency the automatic band does not
see: C+ is mostly INSURANCE, and its yield cost is real and now
quantified.** Of the rows C+ declines that the ratio band would otherwise
have adopted: **random mask — 417 wrong, 11,971 right** (12,388 entries;
153 / 4,483 distinct); **prefix mask — 269 wrong, 14,520 right** (14,789
entries). That is **28.7 correct titles blocked per error prevented** under
the random mask, 54:1 under the prefix mask. Two readings keep it from being
pure cost: the blocked population's error rate (3.37%) is **4×** the
admitted population's (0.83%), and on C+'s own primary class the enrichment
is **6.7×** — 20 distinct shift-shaped errors blocked against 3 admitted,
of which one is tape-wrong and two are a `Tuning` label coinciding with a
neighbour. On the named localised-shift pair with its donor forced, C+ is
decisive: bare ratio 11 adopted / 8 wrong, C+ 2 adopted / 0 wrong. **C+
stays regardless** — a silent adopter is the one surface where being wrong
is unrecoverable, and the corpus is 89 shows — but it must be defended as
cheap insurance with a quantified yield cost, never as a measured
necessity.

**Two invariants on C+, stated here because a later "simplification" would
naturally unify or borrow them and be wrong both times:**

1. **C+ gates the automatic band, NEVER the proposal display.** A wholly
   untagged tape has no anchors and therefore no brackets; applied to the
   renderer, C+ would show ymsb2005 *nothing* — the phase's trigger case
   destroyed by its own guard. The proposal renders every row the DP
   produced, with residuals and per-run annotations; C+ decides only what
   ships without a human.
2. **C+'s count-forcing is weaker than `adopt_gap_titles`', and its
   justification is measurement, not the upstream mechanism argument.** In
   the setlist-gap rung the item count comes from the canonical setlist — a
   source independent of the tape — so count-forcing there removes all
   assignment freedom. Here the donor span's endpoints are read off the
   *same alignment under test*: partly self-referential, exactly the
   property the A5 ruling warns about. It measured better anyway (the
   tables above); do not restate the setlist-gap safety argument for it.

**Layer 3 — per-row evidence and hygiene** (both bands): exclusion penalty
≥ 60 s to adopt; a sibling song split across multiple target files declines
those rows (no title convention exists for a partial song); an untitled
sibling track declines its row; a merged pairing renders `"A > B"` per the
existing convention. Hygiene identical in kind to `adopt_gap_titles`': the
proposed title passes `is_real_title` (as amended below), is not
`setlist.is_junk_title`, is within `MAX_TITLE_LEN`, and is not
show-metadata residue (`metadata_norms` passed down from gather). This is
what keeps a donor's lineage-banner "track" from being adopted as a title
even when the DP pairs it — the gd1982-10-10 banner fails hygiene on its
face; the residual risk there is the *shift* it induces on later rows,
which hygiene cannot see and the operator gate owns.

**The loose comparator needs a named home.** Every agreement number above
was measured with: `fuzzy_norm_title` equality, or containment either way,
or `SequenceMatcher.ratio() >= 0.80` — deliberately looser than
`fuzzy_title_eq`, because taper spelling variants (`BIODTL`,
`Mister Charlie`) must count as agreement or the guard fires on
orthography. It lands in `structure.py` beside the other matching-layer
comparators (proposed name `loosely_same_title`), used by the guard, the
agreeing-anchor determination, and the measurement scorers only — **not**
by `align()` and not by `normalize_song` (the fuzzy-matching spec's
layering rule stands). Its definition is part of the measured basis of
every table above: 10.1% of anchor disagreements are its own misses, so
retuning it moves every agreement number and shifts the knee — any change
re-runs the acceptance measurements, all of them.

### Same-performance precondition (control A5)

Production donors come from `candidate.recordings`: the recordings grouping
placed on the same performance (artist + date + venue, split per jerrybase
event). The design **mandates** that donors only ever come from the target's
own candidate — no cross-candidate lookup exists or may be added — but does
**not** treat grouping as a safety argument, because the hole is reachable:

- A date carrying two performances **with no jerrybase data** is not split
  (per the grouping design, deliberately), so both shows' tapes share one
  candidate. A donor from the other performance is A5 in production
  clothing: same artist, same venue, same date, different setlist.
- The early/late split's set-closer assignment can err; `spans`/`unassigned`
  tapes are held as *targets*, but assignment mistakes put a tape in the
  wrong event's candidate.

So the same-performance guarantee is carried by the guards, not by
upstream: for an anchored target, a wrong-performance donor proposes titles
that contradict the surviving tags and scores ~0% agreement (the sweep's
wholesale failures include exactly this class); for an untagged target,
nothing ships without an operator. **No additional explicit
performance-identity check is added**, and the argument is recorded here
rather than assumed: the exclusion penalty does not test validity (A5), the
anchor guard does, and the one population the anchor guard cannot cover is
already operator-gated for the independent reason of the untagged caveat.

### What is deterministic and what is operator-gated

| population | path | writes |
| --- | --- | --- |
| agreement ≥ 0.80, ≥2 anchors: runs passing C+ | automatic, in gather | `title_source="sibling-align"` on filled tracks |
| same pair: runs C+ declines | stay unresolved, per-run reason in notes; renderable via `--suggest-titles` | nothing automatic |
| 0.50 ≤ agreement < 0.80, or < 2 anchors | `llama fix --suggest-titles` / triage `[t]`, confirmation required | `overrides.titles` (`title_source="override"` after redo) |
| wholly untagged target | operator only, always | `overrides.titles` |
| agreement < 0.50 | declined; note recorded | nothing |
| no qualifying donor | declines, exactly as today | nothing |

**Rendering is run-shaped with a per-run reason** — not a flat track list
with holes. The checkerboard is the measured default, and per-run reasons
are what make it actionable: `tracks 7–9: not bracketed by agreeing
anchors` tells the operator that resolving one flanking tag (a single
`--set-title`, or confirming one proposed row) and re-running unlocks the
run — a real operator loop this design deliberately supports, not an
accident of the guard. For the wholly untagged path the proposal
additionally renders: per-row residuals and penalties, the donor
identifier, the sibling-embeds-in-canonical coverage figure (the tested
fallback — useful evidence, known-insufficient guard: it missed
gd1982-10-10 at 92%), and an explicit first-rows caution, because the one
measured miss was a head-banner +1 shift and the operator's eyes on track 1
are the only remaining check. On ymsb2005 this path turns a 0-of-24 show
into 23-of-24 with every row traceable to a sibling track and a duration
residual.

### Placement and plumbing

In `run_gather`:

- `_sibling_titles` (gather.py:108) and the positional `elif` rung in
  `titles.resolve_titles` are **removed** (the `sibling_titles` parameter
  goes with them). The transfer is a **separate pass over the resolved
  `Track` list**, exactly like `adopt_gap_titles`: it fills only tracks
  whose `title_source == "unresolved"`, stamping `"sibling-align"`. This
  placement is what makes "reuse, not reinvention" literal — `Track`
  objects exist, so C+ calls `structure.unresolved_runs` and
  `structure.gap_span` themselves rather than a mask-based reimplementation
  that could drift.
- It runs **after the overrides loop and before `adopt_gap_titles`** — the
  same position, for the same ratified reason as Phase A's shipped
  deviation: an operator-forced title is independent evidence and must be
  able to serve as an agreement/bracketing anchor, not merely survive.
  Anchor status for the guard = a track whose `title_source` is
  independent evidence (`tags`, `sibling-format`, `override`) with a real
  title; the agreement measurement used tags, and overrides are the same
  trust class or stronger.
- gather computes the transfer where the sibling fetch happens today:
  loads each `candidate.recordings` donor via `filter_files` +
  `clean_tag_titles` + the dedupe fix, calls `siblings.py`, applies the
  ratio band and C+ against the resolved tracks. (Format-recovered titles
  already reached the tracks as their tag layer via `resolve_titles`, so
  no separate substitution is needed.)
- The fetch gate loosens from today's `title_fraction < 1.0 and (confidence
  low or count mismatch)` to `title_fraction < 1.0` — the count-mismatch
  condition was an artifact of the exact-count rung. The `kept and` guard
  stays (an exclude-everything tape must not fetch siblings to resolve zero
  titles).
- Effective cascade order is unchanged for any single track: tags →
  whole-tape setlist rung (measured dead, kept, annotated) → override →
  sibling-align → setlist-gap → unresolved. A sibling-aligned title is
  independent evidence and legitimately **anchors** setlist-gap runs and
  `align()`.
- Pair-level and run-level declines append reasons to the show's `notes`,
  so declines are auditable in `show.json` without a new surface.

### `title_source` semantics

New value **`"sibling-align"`**, added to the enumerating comment at
`models.py:157`. The old `"sibling"` value stops being produced but stays
documented as legacy — 21 library tracks carry it and remain valid until
their shows are naturally re-gathered; no migration (house rule).

**It is NOT added to `structure.TAUTOLOGICAL_TITLE_SOURCES`.** The test the
constant encodes is textual origin: a `setlist`/`setlist-gap` title IS the
canonical item's own text, so `align()` matching it back is circular. A
sibling-aligned title's text originates from a different taper's tags,
assigned by duration — two facts with no dependence on the canonical — so
`align()` matching it against the canonical is a real cross-source
agreement measurement, the same status as `tags`, `sibling-format`, and
the old `sibling`. Excluding it would be the inverse of Phase A's error:
where Phase A initially counted tautological evidence as independent
(inflating coverage, suppressing the low-confidence flag), over-excluding
here would shrink the independent-evidence denominator on exactly the
shows where coverage already rides on few points — a mostly
sibling-resolved show would have its honest matches discarded and its
low-confidence flag fire on nothing.

One caveat is recorded rather than engineered around: on the operator path
for untagged tapes, the donor was *screened* by the embeds-in-canonical
check, which correlates donor text with the canonical. That path writes
`overrides.titles`, so the resulting tracks are `override`-sourced and the
question never reaches `_songish_coverage`. Only the automatic rung
produces `"sibling-align"`, and there the donor was validated against the
target's tags, not the canonical.

## The three incidental defects (in scope, each independently useful)

1. **`is_real_title` rejects numeric titles.** `1922` (a real TBT song)
   fails the ≥3-ASCII-letters test, which cost the probe its one TBT pick
   at a 0 s residual — and the same narrowness afflicts the tag rung (a
   tape tagged `2001` for the song goes unresolved today). Fix: also accept
   a title that is **entirely digits, exactly 4 of them** — year-like
   numeric song titles — leaving `d1t02`-style residue and bare 1–3-digit
   track numbers rejected. Ships only behind a measurement: census the
   cache for tag titles that are pure 4-digit strings, count how many
   items' `title_fraction`/cascade outcomes change, and hand-check a
   sample — the risk is tapers who tag every track with the year, which
   this change would promote from unresolved to wrong-titled at the tag
   rung. If the census finds that population is material, the acceptance
   is scoped down to the sibling/setlist-gap hygiene check only and the
   tag rung keeps today's behaviour. **Scope decision deferred to the
   census output (owner decision 3, still open); carried in the plan as a
   task with the decision point named.** Composition note, ruled expected
   and fine: this fix makes `adopt_gap_titles` adopt TBT's `1922`
   automatically (it is count-forced; only `_hygienic` refuses it today) —
   which erases the merged branch's single demonstrated automatic
   adoption; the branch's standing value is its operator surface and
   footnote strip, which this design builds on.
2. **Per-item, not per-donor** — designed in above; recorded here as the
   recurring principle.
3. **`filter_files` does not dedupe duplicate listings.** Some items list
   every track twice — top level and under an `<identifier>/` prefix —
   with identical durations and tags on only one copy; ymsb2005's donor
   showed 56 files for 28 tracks, halving its apparent tag fraction. Fix
   in `junk.py`, after `_keep_and_exclude`: collapse on
   (basename, rounded duration), preferring the copy that carries a title,
   excluded reason `duplicate-listing`. This touches every `filter_files`
   consumer (gather, junk stats, m3u), so it ships with its own
   full-corpus sweep enumerating every item whose kept set changes, each
   change hand-checked — and lands as its own commit *before* the sibling
   rung, so the rung's acceptance run measures the fixed filter. The
   2026-08-30 spec filed this exact gap out of scope because it could not
   revive the exact-count rung; the alignment rung is why it now pays.

## Failure modes

Unchanged in shape from the predecessor spec: a wrong title propagates to
manifest v3, ID3 `TIT2`, the packaged filename, the briefing, and emcee's
script, with `briefing_guard` and `script_guard` structurally blind because
both define truth from the tracklist. `vet_research.grounding_flags` is the
one partial backstop (needs ≥2 unknowns and >⅓ unmatched).

New to this design:

- **The automatic band's residual wrong class** is scattered variant and
  non-song boundary errors (`Drums`/`Space`/`Jam` cut differences), with
  C+ measuring 1.87–1.99% loose error (SYNTH, random mask, upper bound)
  and zero wholesale titles in every stratum under both masks — paid only
  on tracks that today ship as filenames.
- **The localised-shift residual**: a shift confined to the tape's middle
  with anchors sampling the correct ends. **Measured 2026-09-03: 136 REAL
  pairs, not one** — but 135 of the 136 are multi-donor, so `best_donor`
  selects a cleaner sibling instead, and the single remaining one is
  declined by layer 3 (and, counterfactually, by C+). The residual is
  therefore the single-donor slice — **9 of 716 target recordings (1.26%)**,
  one slide case in it — plus any change to `_donor_key`'s ordering. If
  either ever lets one through, the fix is positional (agreement measured
  over the fills' neighbourhood), not a different threshold.
- **Prefix-tagged tapes get no automatic help** — under a prefix mask C+
  ships zero titles, by construction (no run has a right anchor). The
  realistic partly-tagged taper routes entirely to the operator. Safe
  direction, stated as a cost, not discovered later.
- **The untagged-path residual** is the gd1982-10-10 head-shift, closed
  only by the operator. It must be presented, not papered over: the
  proposal renders residuals and flags the head rows.
- **A wrong tape tag can veto a correct donor** (delmccoury inverted): the
  guard treats target tags as truth and 24% of adjudicated disagreements
  measure the tape as the wrong party. Cost is a decline or a demotion to
  the operator band — conservative, visible in the notes, and the
  three-way display turns it into signal.

## Composition with the merged Phase B surface

Phase B is on main (`44038ae`, suite 1557): `correspondence.py`
(canonical-setlist DP + count-forced feasibility guard + footnote strip),
`llama fix --suggest-titles` and triage's `[t]` resolution
(`cli._propose_titles_for_show` → `_propose_and_confirm_titles`), the C1
staleness guard, and confirmation writing `overrides.titles` with redo from
gather. (The first draft of this spec carried an unmerged-branch
contingency; it is deleted, the merge decided it.)

This phase extends that surface rather than duplicating it:

- `--suggest-titles` and triage `[t]` gain the sibling arm as the
  **preferred** evidence source: when a donor alignment reaches the
  operator bands, the proposal is built from it (per-row sibling titles,
  residuals, penalties, run-shaped decline reasons, the three-way anchor
  display) and the canonical DP is not consulted. This **supersedes**
  rather than feeds `sibling_item_durations`: Phase B's own counterfactual
  measured that even *perfect* per-item durations leave 4 wrong titles on
  ymsb2005 (the canonical is missing both reprises — no item-duration
  model can invent absent items), while sibling-tape alignment scores
  23/23 because the donor actually played the reprises. The canonical DP
  remains the fallback when no donor qualifies.
- The C1 staleness guard, the `--exclude` combination refusal, the
  footnote strip, and the confirmation/redo plumbing are reused as-is —
  the sibling arm enters at the proposal-construction seam
  (`_propose_titles_for_show`), below all of them.
- Triage's `[t]` inherits the sibling arm for free (both call sites share
  `_propose_and_confirm_titles`); including triage is resolved, not open.
- Phase B's "adopts on 1 of 89 (setlist.fm active) / 0 of 89 (offline)"
  census figure becomes moot once defect fix 1 lands (the `1922` case
  moves to setlist-gap); expected and accepted.

Nothing in this design touches `correspondence.py`'s internals, and Phase
B's DP stays un-reopened per the scope ruling.

## Testing

Unit (`test_siblings.py`, pure): merge/split/skip alignment shapes; the
A2/A3 deletion controls as fixtures (deleted-track rows decline, remainder
correct **by title identity**); exclusion penalty declines a
near-ambiguous pairing; per-row untitled-donor decline; hygiene rejects a
banner title; comparator cases (`BIODTL`, containment, the `(?)` near-miss
documented as a known comparator limit).

Guard unit tests (`test_structure.py` / `test_siblings.py`): the ratio
bands route to adopt/proposal/decline; agreeing-anchor binding through the
DP pairing; bracketing reuses `gap_span`'s real function (pinned by
mutation, not by a reimplementation drifting); leading-edge exception
adopts; a tail run never adopts automatically; count-forcing declines a
merge-containing run; **runs decline individually** (a pair with one
bracketed and one unbracketed run adopts exactly the bracketed one); the
localised-shift shape as a synthetic fixture (correct head/tail anchors,
shifted interior → C+ adopts nothing in the interior).

Invariant tests: the proposal renderer is **ungated by C+** — an untagged
fixture (ymsb2005 fixture, on main since Phase B) renders all its rows
while the automatic rung adopts none of them; `"sibling-align"` absent from
`TAUTOLOGICAL_TITLE_SOURCES` pinned by mutation (adding it must fail a
named test that asserts a sibling-aligned track's real `matched`
measurement and coverage contribution).

Integration (`test_stage_gather.py`): an anchored fixture adopts
`sibling-align` titles and the adopted strings equal the expected titles
(content assertion); a fully-tagged show is byte-identical; the untagged
fixture gets **no** automatic adoption — pinned, because nine Phase B
tests once pinned the opposite and had to be rewritten; a below-FLOOR
donor leaves a decline note; per-run decline reasons reach `notes`.

Defect fixes: dedupe (an item listing tracks twice keeps each once,
preferring the tagged copy, reason recorded); `is_real_title("1922")` True,
`is_real_title("d1t02")`/`("01")` still False; the enumerated-tape gate's
pinned tests all still pass.

## Acceptance criteria — content-based, never shape

Phase B's gate passed on shape while 13 of 22 titles were wrong; none of
the following may be satisfied by counting rows, checking feasibility, or
asserting a table rendered. Every criterion compares **adopted title
strings against independently-derived ground truth, identity by identity**,
every wrong adoption is hand-triaged (variant / non-song boundary /
genuine) before a rate is read, and SYNTH and REAL numbers are reported in
separate tables, labelled.

1. **Controls re-run through the shipped code** (not the prototype):
   probe baseline 23/23 correct; A2/A3 decline exactly the orphaned rows
   and adopt 0 wrong; the rotation control (sibling titles rotated +1)
   ships zero automatic titles; the **prefix-mask arm ships zero automatic
   titles in every stratum**; the named localised-shift pair
   (`gd1971-08-06.aud.wolfe…` ← `…mtx.seamons.96668`) ships **0** of the 7
   titles the bare ratio ships; A5's wrong-performance donor is rejected
   below FLOOR.
2. **The six-show table**, against the same hand-established ground truth
   (ymsb2005's Section-B table + LMA canonical): ymsb2005 renders 23
   correct rows and declines track 1 via the operator path; delmccoury
   lands in the operator band (agreement 0.69) with its 5 correct fills
   proposed and its 4 anchor disagreements displayed three-ways; TBT
   adopts `1922` (via setlist-gap once fix 1 lands, per the composition
   note); **zero wrong titles on any path**, and the automatic band's
   library yield of 0 tracks is asserted as the expected result, not
   explained away.
3. **Blind arm re-run through the shipped functions** with the shipped
   gates under **both masks** (per-row donor gating and C+ change the
   measured population, so the sweep's tables do not transfer
   automatically): zero wholesale-failure titles in every stratum;
   per-stratum loose error at or below the sweep's C+ cells (1.87–1.99%
   random-mask); every wrong adoption hand-triaged and the genuine class
   compared against the tag rung's own typo baseline per M1's standard.
4. **Full-library offline re-gather** (M2-standard): every
   currently-resolved track's title byte-identical; the complete diff is
   the enumerated set of new adoptions on the 75-track unresolved
   population, each checked by hand. Both arms stated: offline
   (`setlistfm=None`) and, for the shows whose canonicals are
   setlist.fm-won, a spot-check with the key active — neither arm
   dominates (setlist.fm dropped both Yonder reprises), so per-show
   disagreement between arms is itself a reported finding, not noise.
5. **Dedupe sweep**: every cache item whose kept set changes is listed
   with before/after counts; no library show's delivered track list
   changes except where intended and named.
6. **Numeric-title census** (gates defect fix 1's scope, before it ships):
   pure-4-digit tag titles across the cache, items affected, sample
   hand-checked; the global-vs-hygiene-only scope decision is made on its
   output and recorded.

An in-repo evidence doc at the `2026-08-03-tail-guard-sanity-check.md`
standard records all of it; the constants' comments cite it.

## What could falsify this design

Stated so the acceptance run knows what it is looking for:

- **The synthetic population.** 5 real partly-tagged targets exist; every
  band edge and every run-shape number rests on masked well-tagged tapes
  whose anchors are correct by construction. The random mask is the
  friendliest synthesis (the prefix arm proved it flatters the bare
  guard), and real unresolved runs are likely blockier than the
  manufactured checkerboard. If a real corpus of partly-tagged tapes ever
  exists, every SYNTH table gets re-taken on it before the bands are
  defended with these numbers.
- **The wrong-anchor interaction is unmeasured.** SYNTH anchors are
  correct by construction, so the sweep cannot see a wrong anchor meeting
  a shifted alignment; the REAL arm is the only window and it has no
  hidden ground truth.
- **The localised-shift class is n=1.** C+'s interior protection is
  mechanically argued and empirically thin; a second instance in
  production that C+ misses reopens the positional-agreement design.
- **Comparator fragility.** 10.1% of anchor disagreements are the loose
  comparator's own misses; any change to it moves every agreement number,
  shifts the knee, and re-runs criteria 1–3.
- **Ground-truth noise ceiling.** All rates are upper bounds against tags
  measured 24% wrong at disagreements; if criterion 3's hand-triage finds
  the genuine class larger than the sweeps suggest, AUTO moves up or the
  band closes.
- **The near-fully-tagged trade.** In the 80–95%/≥95% strata a
  trailing-anchor rule ships more than C+ at slightly higher error; if
  production targets turn out overwhelmingly to be 1–2-fill tapes, that
  trade deserves re-examination (today it is dominated by the sparse
  strata the feature exists for).
- **The no-jerrybase double-date hole.** If a wrong-performance donor ever
  *passes* the ratio band at AUTO, the same-performance argument above is
  wrong and an explicit performance-identity check becomes mandatory.
- **The dedupe and numeric-title fixes are corpus-wide behaviour changes**
  riding along; either one's sweep finding material collateral damage
  (criterion 5/6) blocks it independently without blocking the rung.

## Out of scope, filed not built

- Any LLM touchpoint. The finding is that none is needed; none is designed.
- Re-opening `correspondence.py`'s canonical-setlist DP internals.
- Automating the wholly untagged path (blocked on the gd1982-10-10 class;
  the only evidence that could close it is audio-level — silence/
  fingerprint analysis — already filed by the predecessor spec).
- Positional (fill-neighbourhood) agreement — the localised-shift class's
  structural fix, filed against the n=1 evidence base.
- Using anchor disagreements to *correct* a target's own wrong tags
  (delmccoury tracks 2–4; 24% of disagreements population-wide): the
  three-way display gives the operator the evidence, but proposing
  overwrites of `tags`-sourced titles is a new trust decision — filed for
  a future phase with its own measurement.
- Widening manifest v3 to carry `title_source` (unchanged ruling).
- The loose comparator's known near-miss classes (`(?)` suffixes) beyond
  documenting them.

## Decisions

Resolved (2026-09-02, owner-ratified via the band and guard-shape sweeps):

1. **AUTO 0.80 / FLOOR 0.50 / MIN_ANCHORS 2, guard shape C+** — chosen on
   the marginal-error knee and the shape sweep, not taste; the reasoning
   is in the Evidence section and binds future retuning to re-measurement.
2. **The `title-correspondence` branch merged** (`44038ae`); this phase
   extends its surface. Defect fix 1 erasing the branch's `1922` adoption
   is expected and accepted.
3. **Triage's `[t]` is included** — it shares `_propose_and_confirm_titles`
   with `fix --suggest-titles`, so the sibling arm reaches it for free.

Still open, deliberately:

4. **Numeric-title fix scope** (global `is_real_title` vs hygiene-only) —
   decided on criterion 6's census output, not before. The plan carries it
   as a task with the decision point named.
