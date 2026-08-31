# Blind-the-tags: how often is the `setlist-gap` rung wrong?

**This is the M1 evidence for Phase A of the title-correspondence plan.** It
answers one question: when `structure.adopt_gap_titles` fills a count-forced
run of unresolved tracks from the canonical setlist, how often is the title it
adopts *not* the title the tape itself carries?

> **Revised 2026-08-31 after review.** The first version of this document
> drew two claims its instrument could not support, and both are corrected
> below rather than quietly softened. (1) Its merged-anchor gate was attributed
> by the *adjacent* anchor, which answers a different question than the one the
> gate exists to ask — see "The gate answered a question nobody asked". (2) It
> estimated the cost of the trailing-edge fix at ~3.6× the measured value. The
> fix itself has since been applied to `structure.adopt_gap_titles`, so the
> corpus is now reported at two code states, both named.

**Branch:** `title-correspondence`. Two code states are measured and every
number below says which:

- **`a37bb83`** — the reviewed Phase A HEAD, before the trailing-edge fix. This
  is the population the hand triage was performed on.
- **`b1ca393`** — with the trailing-edge fix (`adopt_gap_titles` no longer fills
  a run reaching the last track). **This is what ships.**

Reproduce the `a37bb83` sweep with
`git checkout a37bb83 -- packages/llama/src/llama/structure.py`, run, then
`git checkout HEAD -- packages/llama/src/llama/structure.py`. Neither the
harness nor this document touches `packages/` otherwise.

**Source:** every number comes from the REAL
`llama.structure.adopt_gap_titles`, run in-process. The harness
(`scripts/blind_tag_gapfill.py`) is a driver and a scorer; it reimplements
nothing it measures. `adopt_gap_titles`, `titles.resolve_titles`,
`junk.filter_files`, `setlist.parse_setlist`, `structure.rank_parses`,
`structure.blend_segues`, `gather._collect_parses`,
`gather._strip_head_banner`, `gather._drop_artist_items`,
`gather._show_metadata_norms`, `gather._sibling_titles` and
`gather._recover_format_titles` are all imported and called. The canonical
setlist is therefore **the real gather canonical**
(`_collect_parses` → `rank_parses` → `blend_segues` → `_strip_head_banner` →
`_drop_artist_items`), not raw `parse_setlist` output — which is the specific
thing that made the design spec's 45–52% pilot figure a bound rather than a
truth.

**Merged anchors are attributed three ways, and the distinction is the whole
point.** A merged anchor can corrupt a gap by binding its own flank wrongly
(*adjacent*), or by mis-advancing the walk pointer so that every gap after it
is shifted (*upstream*) — and `adopt_gap_titles`' docstring states the risk in
the second form. Each adoption therefore carries `merged_attr` ∈
{`adjacent`, `upstream`, `none`}. The first version of this document reported
only the adjacent split; see "The gate answered a question nobody asked".

**Anchor kinds are spied, not inferred.** `adopt_gap_titles` does not expose
which anchors it bound or how. The harness wraps `structure._merge_run` for the
duration of each call and records which of its calls returned a hit; a track
carrying more than one title component whose `_merge_run` call succeeded was
bound as a **merged** anchor, and every other anchor by exact normalized
equality. The breakout below is therefore a reading taken from the function
under test, not a guess about it.

**Standing caveat (offline).** These runs have `setlistfm=None`. Several of
these shows' real canonicals are setlist.fm-won, and setlist.fm parses are
cleaner than LMA description parses. **Every figure here is a bound, not a
truth**, and it is a bound in the pessimistic direction for correctness: the
LMA-only canonical is the noisier input.

---

## The harness can return non-empty — checked before anything below was believed

A harness that silently adopts nothing and a harness that correctly finds no
errors produce identical output. This exact failure has already happened twice
on this branch in miniature (a verification that produced nothing because a
plugin was not on `PYTHONPATH`, which looked precisely like a clean run), so it
was checked first and is checked on every run.

**1. The summary block prints an adoption count and a firing count
unconditionally**, on stdout and stderr, whether or not anything was wrong. On
the corpus run those read `trials in which gap-fill FIRED: 15118` and `scored
adoptions: 28605`. Neither number can be nonzero unless the real
`adopt_gap_titles` ran and really adopted.

**2. The scorer was shown to be able to emit `wrong` at all**, against cases
built to produce one:

```console
$ ./.venv/bin/python scripts/blind_tag_gapfill.py --selftest
# selftest: real adopt_gap_titles, real spy, real scorer
  A single-anchor gap that is right: track 3 anchor=single verdict=ok adopted='Deal' hidden='Deal'
  B single-anchor gap that is WRONG (canonical disagrees with the tape): track 3 anchor=single verdict=wrong adopted='Sugaree' hidden='Deal'
  C merged-anchor gap (left anchor consumes two items): track 2 anchor=merged verdict=ok adopted='Estimated Prophet' hidden='Estimated Prophet'
# selftest adoptions=3 saw_wrong=True
# SELFTEST PASSED: the harness adopts, and it can score an adoption wrong
```

Case B is a four-track tape tagged `Bertha / Jack Straw / Deal / Loser` against
a canonical reading `Bertha / Jack Straw / Sugaree / Loser`; track 3 is blinded,
the gap is count-forced 1-for-1 between two exact anchors, and a correct
implementation *must* adopt `Sugaree`. Case C additionally proves the
`_merge_run` spy fires and is attributed to the right track: the left anchor is
one tagged file `Scarlet Begonias > Fire On The Mountain` consuming two
canonical items, and the row comes back `anchor=merged`. The selftest exits
non-zero if it ever adopts nothing or never scores a `wrong`.

---

## Method

For every cached archive.org item under `~/.llama/cache/md_*.json`
(read-only; nothing under `~/.llama` is written):

1. Group the cache into performances with the real
   `grouping.group_candidates` — so early/late splits, `/spans` and
   `/unassigned` come out exactly as production produces them — and measure
   every recording in turn as the *chosen* one, since the chosen recording is
   the one whose tags are on trial.
2. Reproduce `run_gather`'s prefix (gather.py:508–635) minus the workspace I/O
   and the setlist.fm lookup, ending in the `tracks` list and the
   `metadata_norms`/`aliases` that `adopt_gap_titles` is called with.
3. Enumerate every window of 1–3 consecutive **tag-titled** tracks whose
   flanking tracks are themselves titled (or which touch a tape edge). Windows
   whose neighbour is *already* unresolved are skipped: blinding one would
   merge with a pre-existing run and only part of the resulting gap would have
   ground truth behind it.
4. Blind that window — one window per trial — by applying
   `resolve_titles`' own fallback ladder (titles.py:150–160) to those tracks
   only: the whole-tape `setlist` rung if it is live for this recording, else
   the `sibling` rung, else `unresolved`. Nothing else on the tape moves.
   (Blanking the file dicts and re-running `resolve_titles` outright was
   rejected: removing three titles perturbs `clean_tag_titles`' enumerated-tape
   gate and can change the *other* tracks' titles — i.e. the anchors.)
5. Call the real `adopt_gap_titles`, with the `_merge_run` spy armed.
6. Score every adopted track inside the blinded window against the tag it could
   not see, by `fuzzy_norm_title` equality. Adoptions *outside* the window are
   **induced by the blinding** — removing an anchor changes the monotone walk
   and can let a pre-existing unresolved run elsewhere become fillable — have no
   ground truth, and are counted separately as unverifiable (135 of 28,740 at
   `a37bb83`, 54 of 27,273 at `b1ca393`).

### Two populations are reported, and they are different

Trials overlap by construction: blinding `[3,3]`, `[3,4]` and `[3,5]` all put
track 3 in a gap. **Per-trial** counts therefore weight a track by how many
windows contain it. **Distinct** counts collapse every row making the same
claim about the same track — the key is (identifier, track, adopted title,
hidden tag, anchor kind, merged attribution, verdict). The triage below operates
on the distinct population, and so does the ship gate; the per-trial numbers are reported because the spec's pilot
counted that way ("1,652 firings, 3,144 adoptions") and the comparison is
otherwise not like-for-like.

---

## Corpus and headline numbers

### At `a37bb83` (pre-fix) — the population the triage was performed on

```console
$ git checkout a37bb83 -- packages/llama/src/llama/structure.py
$ ./.venv/bin/python scripts/blind_tag_gapfill.py --progress 500 > sweep-prefix.tsv
format=mp3
cached items scanned          : 968
items with usable audio       : 960
items offering >=1 blind run  : 949
blinding trials run           : 57098
  trials pre-empted by a higher rung: setlist=25416, sibling=1138
trials in which gap-fill FIRED: 15118
scored adoptions              : 28605
unverifiable adoptions        : 135
  pooled  ok=26497 wrong=2108 rate=7.37%
distinct adoptions            : 6864
  pooled  ok=6237 wrong=627 rate=9.13%
  [adjacency view, NARROWER THAN THE MECHANISM -- see merged_attr]
  single  ok=5990 wrong=617 rate=9.34%
  merged  ok=247 wrong=10 rate=3.89%
  [merged attribution: adjacent | upstream-only | none]
  adjacent  ok=247 wrong=10 rate=3.89%
  upstream  ok=279 wrong=25 rate=8.22%
  none      ok=5711 wrong=592 rate=9.39%
edge is a TRIAL property; 922 of 6864 distinct adoptions carry both values
  edge population, first-window-wins : 1156
  edge population, any-edge-wins     : 1594
  edge population, any-interior-wins : 672
$ git checkout HEAD -- packages/llama/src/llama/structure.py
```

### At `b1ca393` (shipped)

```console
$ ./.venv/bin/python scripts/blind_tag_gapfill.py --progress 500 > sweep-postfix.tsv
trials in which gap-fill FIRED: 14414
scored adoptions              : 27219
unverifiable adoptions        : 54
distinct adoptions            : 6546
  pooled  ok=5972 wrong=574 rate=8.77%
  adjacent  ok=241 wrong=10 rate=3.98%
  upstream  ok=248 wrong=20 rate=7.46%
  none      ok=5483 wrong=544 rate=9.03%
```

**The 25,416 pre-empted trials are not a harness defect and are worth reading.**
On a recording where the parsed canonical's item count happens to equal the kept
file count, `titles.resolve_titles`' whole-tape `setlist` rung answers first and
the gap never forms — so `adopt_gap_titles` is unreachable on that recording, in
this experiment and in production alike. That is 44% of trials. It is the same
mechanism as the fixture caveat below, at corpus scale.

**Raw wrong-rate is not the answer.** 627 distinct wrong adoptions is the number
before triage, and the pilot's headline contained all three classes. The great
majority of these are the scorer disagreeing with itself, not the adoption being
wrong.

### The `edge` split is collapse-rule-dependent and no single number is the truth

`edge` is a property of the **trial** — did the blinded window touch a tape end
— not of the adoption. The same adoption is reached by several windows, and
**922 of 6,864 distinct adoptions carry both values**. Any edge/interior split
is therefore an artifact of the collapse rule, and the answer moves with it:

| collapse rule | edge population (of 6,864) |
|---|---|
| first window wins | 1,156 |
| any edge window wins | 1,594 |
| edge only if every window was an edge | 672 |

The first version of this document reported the 1,156 figure without stating
that a rule had been chosen. The harness now prints all three. Wherever an
edge-conditioned rate appears below, it uses **first-window-wins** and says so.

### Robustness: the same sweep on `flac`

```console
$ ./.venv/bin/python scripts/blind_tag_gapfill.py --format flac --progress 500 > sweep-flac.tsv
format=flac
cached items scanned          : 968
items with usable audio       : 683
distinct adoptions            : 4700
  pooled  ok=4328 wrong=372 rate=7.91%
  adjacent  ok=173 wrong=8 rate=4.42%
  upstream  ok=178 wrong=9 rate=4.81%
  none      ok=3977 wrong=355 rate=8.19%
```

Different delivery format, largely overlapping but differently-filtered tapes,
same raw rate to within a point. The flac sweep was **not** hand-triaged; it is
reported as a consistency check on the pre-triage rate only, and no gate is
taken from it. Note that `upstream` and `none` sit close together here, which is
one more reason not to read a mechanism into the mp3 gap between them.

---

## The three-way triage

Every one of the 627 distinct wrong adoptions at `a37bb83` was classified by
hand into exactly one class. 627 rows collapse to **382 distinct
(adopted, hidden) pairs**; the classification is per pair, applied to every row
carrying it.

**The classification ships as data, not as prose.**
`docs/superpowers/2026-08-31-gap-fill-blind-test.triage.tsv` carries all 382
pairs, one per row, and `scripts/blind_tag_gapfill.py --triage <that file>
--rows <sweep.tsv>` produces every class count below. The tables later in this
section are generated from the same file, so they cannot drift from it.

**The rule, stated before the exceptions:**

- **`scorer-artifact`** — adopted and hidden name the same song or the same
  segment, differing only by spelling variant, punctuation, diacritics, a
  leading article, a subtitle kept or dropped, a segue/encore/duration/taper
  annotation, an abbreviation or nickname, or **because one side merges songs
  the other splits and the extra components are accounted for at neighbouring
  positions**. The adoption is acceptable; the strict `fuzzy_norm_title`
  equality the scorer uses is what failed. **This class includes cases where the
  adopted title is the *worse* rendering of the right song** (`Sugar Magnoli`
  for `Sugar Magnolia`, `Miles From Denver` for `40 Miles From Denver` — the
  canonical's own text, warts included). Those are cosmetic, not correspondence
  errors.
- **`tag-typo-adoption-superior`** — the hidden tag is a misspelling or mangling
  and the adopted title is the correct rendering. Split out from
  `scorer-artifact` on this test: is the *tag* a plausible rendering of the
  song's name at all? `Lazy Lightnin'` is; `Loset` is not.
- **`genuinely-wrong`** — the adopted title names a different song, a different
  segment, or a different movement (main vs reprise) than the tape carries at
  that position — **including the case where the adopted title names an
  ADDITIONAL song the track does not contain.**

**Auditing this classification:** every pair in the `genuinely-wrong` and
`tag-typo-adoption-superior` tables below is enumerated in full; everything else
is `scorer-artifact`, and the residue is enumerated in the companion
`.triage.tsv`.

Four judgement calls made deliberately and recorded so they can be overturned:

1. **Main vs reprise counts as genuinely wrong.** `Playin' In The Band` and
   `Playin' In The Band Reprise` are different tracks in different halves of a
   Dead second set, and the pairing appears in both directions in the data
   (`Reprise` adopted over a `Band` tag *and* `Band` adopted over a `Reprise`
   tag), which is the signature of a shift rather than of loose tagging. Same
   for `Dark Star Reprise`/`Dark Star` and `Hey Jude Reprise`/`Hey Jude`.
   **Fifteen** distinct adoptions ride on this call. Calling them cosmetic
   instead would move the strict rate from 1.65% to **1.43%** (98/6,864).
2. **Interchangeable jam/segment labels are a subclass, not an exclusion — and
   this call is in tension with call 1.** `Jam` adopted where the tape says
   `Space`, `Drums` where the tape says `Jam`, and so on: 56 distinct adoptions
   where both sides are improvisation-segment names tapers use interchangeably,
   so no song is misattributed. **But `Drums`↔`Space` appears in both
   directions too**, which is the exact signature call 1 uses to convict the
   reprises. The two calls cannot both be right on that test, and rather than
   invent a principle to reconcile them **the headline is published as the range
   1.54%–2.38%** (shipped code), with the subclass counted at the top end. Where
   a single number is unavoidable below, the strict figure is used and labelled
   strict.
3. `Phil & Ned`/`Seastones` and `Sunshine Daydream`/`Sugar Magnolia` are the
   same music under two names and are `scorer-artifact`;
   `One More Saturday Night`/`One More Halloween Night` is a taper's Halloween
   joke on the same song and is likewise `scorer-artifact`.
4. **An adopted title that names an *extra* song is genuinely wrong, not an
   artifact.** Five adoptions where the canonical item is a merged string
   asserting a song the track does not contain —
   `Dancin' In The Streets Scarlet Begonias` over a `Dancing In The Street` tag
   (×3), `Not Fade Away Encore Baby Blue` over `Not Fade Away`,
   `Don't Ease Me In Touch Of Gray` over `Touch Of Grey`. The first version of
   this document classed them `scorer-artifact` under a rule that covered only
   the *opposite* direction (the adoption naming one component of a merged tape
   track, where nothing is invented). They are reclassified, which moved the
   strict rate 1.57% → 1.65% pre-fix. Direction matters: dropping a name the
   track has is a lesser fault than asserting one it does not.

### Results

```console
$ ./.venv/bin/python scripts/blind_tag_gapfill.py \
    --triage docs/superpowers/2026-08-31-gap-fill-blind-test.triage.tsv \
    --rows sweep-prefix.tsv
distinct adoptions            : 6864
unclassified wrong adoptions  : 0   (must be 0; a nonzero value means the sweep and the classification have drifted apart)
  ok                                6237  90.87%
  scorer-artifact                    417  6.08%
  tag-typo-adoption-superior          41  0.60%
  genuinely-wrong                    113  1.65%
  genuinely-wrong/filler-segment      56  0.82%
  HEADLINE RANGE: genuinely-wrong 1.65% -- incl. filler-segment 2.46%
  by merged attribution (genuinely-wrong, strict / incl. filler):
    adjacent  n=  257 strict=   1 (0.39%)  incl-filler=   1 (0.39%)
    upstream  n=  304 strict=   8 (2.63%)  incl-filler=   8 (2.63%)
    none      n= 6303 strict= 104 (1.65%)  incl-filler= 160 (2.54%)
```

Same command with `--rows sweep-postfix.tsv` (the shipped code):

```console
distinct adoptions            : 6546
  ok                                5972  91.23%
  scorer-artifact                    378  5.77%
  tag-typo-adoption-superior          40  0.61%
  genuinely-wrong                    101  1.54%
  genuinely-wrong/filler-segment      55  0.84%
  HEADLINE RANGE: genuinely-wrong 1.54% -- incl. filler-segment 2.38%
    adjacent  n=  251 strict=   1 (0.40%)
    upstream  n=  268 strict=   8 (2.99%)
    none      n= 6027 strict=  92 (1.53%)
```

**The headline is a range, not a point.**

> **`setlist-gap` is wrong on 1.54%–2.38% of the adoptions it makes** (shipped
> code; 1.65%–2.46% before the trailing-edge fix). The low end excludes the
> filler-segment subclass, the high end includes it, and the doc's own
> reasoning does not settle which is right — see judgement call 2.

The upper end is very close to the spec pilot's **2.4% interior / 1.5% edge**,
from a different instrument on a differently-built canonical. That is
corroboration, not a coincidence to lean on.

**The `--triage` roll-up carries its own non-empty discipline.** It prints
`unclassified wrong adoptions` unconditionally and exits 1 when that is nonzero,
so a sweep and a classification that have drifted apart cannot be mistaken for a
clean run. Demonstrated by truncating the classification file to its first 100
rows: `unclassified wrong adoptions : 507`, exit 1.

### The gate answered a question nobody asked

**This is the most important methodological finding in this document, and it is
a finding about the gate, not about the code.**

The by-anchor-kind gate was added because `adopt_gap_titles`' docstring names a
specific weakness: `_merge_run` compares components with `fuzzy_title_eq`, which
falls through to `_is_subphrase`, so **a merged anchor can bind one item off and
count-forcing cannot catch a same-size shift** — and the consequence the
docstring states is that the mis-advanced pointer **shifts every gap that
follows**.

The first version of this document labelled a gap `merged` when its
*immediately adjacent* anchor was merged. That measures whether a merged anchor
corrupts **its own** gap. The stated risk is about gaps **downstream** of it. A
gap two tracks past a mis-bound merged anchor was recorded as `single`. The gate
was therefore defined over what was easiest to label rather than over the
mechanism it meant to bound — and it reported `0.39% vs 1.62%`, which reads as
an exoneration.

Re-attributed on the mechanism the docstring actually describes, the sign
reverses:

| attribution (pre-fix) | n | genuinely-wrong | rate | Wilson 95% CI |
|---|---|---|---|---|
| `adjacent` — a flanking anchor was merged | 257 | 1 | 0.39% | 0.07%–2.17% |
| `upstream` — a merged anchor bound before this gap, none adjacent | 304 | 8 | **2.63%** | 1.34%–5.11% |
| `none` — no merged anchor anywhere before this gap | 6,303 | 104 | 1.65% | 1.36%–2.00% |

257 + 304 + 6,303 = 6,864 and 1 + 8 + 104 = 113, so the partition reconciles
with the totals above.

**The lesson, stated so it is not learned again:** a gate must be defined over
the mechanism it means to bound, not over the property that is easiest to
attach to a row. A gate that is merely absent leaves a question open; a gate
that measures the wrong thing *closes* it, wrongly, and hands you a number that
looks like reassurance. This is the fourth instance in this design of a metric
that is blind at exactly its own boundary — the tail-guard evidence docs record
two, the spec's coverage-vs-correctness finding a third.

### Both directions are underpowered — apply symmetric skepticism or none

The replacement figure deserves exactly the skepticism the original one did.

- `adjacent`: 1 observed against **4.2 expected** at the `none` rate. Fisher
  one-sided P(X ≤ 1) = **0.078**. The interval 0.07%–2.17% overlaps `none`'s
  1.36%–2.00%: the data are consistent with the adjacent path being somewhat
  *worse*.
- `upstream`: 8 observed against **5.0 expected** at the `none` rate. Fisher
  one-sided P(X ≥ 8) = **0.143**. The interval 1.34%–5.11% likewise overlaps.

So the honest statement is: **no evidence of harm, no evidence of safety, and
underpowered in both directions.** Seven or eight events license a code change
no more than one event licensed calling the path safe. The words "passes
decisively", "four times better" and "the merged path is the better one" were in
the first version of this document and are withdrawn. On the `flac` corpus
`upstream` (4.81%) and `none` (8.19%) sit the other way round again, which is a
further reason to read no mechanism into the mp3 gap.

### The `_merge_run` tightening: OPEN, with a reactivation condition

**Not applied — and the disposition is OPEN, not settled.** The reasoning that
matters is not the first version's ("the merged path is better"; withdrawn) but
this:

1. **Both directions are underpowered**, per the section above. A tightening
   justified by eight events would be exactly the kind of unmeasured knob this
   project refuses to ship — the tail-guard constants carry their measurements
   in comments precisely so that a constant nobody can re-validate does not
   become folklore.
2. **It would guard a path that does not currently execute.** After the
   trailing-edge fix the rung makes **one** adoption on the whole 960-item
   cache, and that adoption's `merged_attr` is `none` (the only merged anchor on
   that tape is at track 22, *after* the gap at track 19). So the tightening
   would change nothing that runs today, and could not be re-validated
   afterwards either.

**Reactivation condition, stated as a requirement rather than an aside:** the
merged-anchor question is **open**; the three-way partition above is the best
available evidence and is underpowered in both directions; and **if this rung
begins making natural adoptions on a future corpus, the merged-anchor error rate
MUST be re-measured with adequate power BEFORE any adoption is trusted.**

**The prepared response, so whoever re-measures does not have to re-derive it:**
in `adopt_gap_titles`' anchor pass, require exact per-component equality at
`_merge_run`'s call site instead of `fuzzy_title_eq` — i.e. accept a merged
anchor only when every component matches a canonical item's normalized form
exactly. It is strictly conservative: a declined merged anchor makes the
adjacent gaps decline rather than mis-adopt.

### What the genuinely-wrong adoptions actually are

Reading the 92 distinct pairs below, they fall into five recognisable shapes,
and the first one accounts for most of them:

**1. The tape carries filler the canonical does not list.** `Estimated` adopted
over a `Tuning` tag; `Bertha` over `Tuning`; `Blues For Allah` over `Tuning`;
`Saint Stephen` over `Tuning/Dead Air`; `Sugaree` over `Crowd/Tuning`;
`Crazy Fingers` over `Tuning/ Bill Graham intro`. The tape has a tuning track
between two songs, the canonical setlist does not, so the one-file gap is
count-forced against the *next song's* item and every adoption in that
neighbourhood slides by one. **Count-forcing is satisfied exactly because the
shift is size-preserving** — this is the same "consistency is not correctness"
failure the spec records for the LLM aligner and the unanchored DP, in its
third costume. It is the dominant failure mode of this rung and it is not
detectable from inside the mechanism.

**2. The canonical carries a truncated or split item.** `Prophet` adopted over
a `Bertha` tag (the parser emitted a bare `Prophet` item, splitting
`Estimated Prophet`), `Weather Report Suite Part 1` over `Let It Grow`, and
`Let It Grow` over `Spanish Jam` on five different tapes of gd1974-07-19 — one
upstream parse defect reproduced across every recording of the same
performance. Note the corollary: **wrong adoptions are correlated across
sibling recordings**, so 113 distinct adoptions are far fewer than 113
independent failures.

**3. Main vs reprise.** Fifteen adoptions, per judgement call 1 above.

**4. The adopted item names an extra song.** Five adoptions, per judgement call
4 above.

**5. Tail junk adopted as a title — the shape that got fixed.**
`gd1991-09-10` (two recordings): the last track's tag is
`It's All Over Now Baby Blue` and the adopted title was
**`Branford Marsalis on saxophone throughout`** — a taper's credit line sitting
at the *end* of the parsed setlist. `_strip_head_banner` cleans the head only;
there is no tail counterpart, and `_hygienic` passes the string (three letters,
under 80 characters, not `is_junk_title`, not in `metadata_norms`). Same shape:
`= no lyrics` adopted on two recordings of gd1975-06-17, both at track 18. All
four sat at `track == n_tracks`, and **all four are gone at `b1ca393`** — see
"Exposure" for the fix and its measured cost.


### The classification, in full

Generated from `2026-08-31-gap-fill-blind-test.triage.tsv` joined onto the
`a37bb83` sweep, so these tables cannot drift from the data the roll-up counts.
Every `genuinely-wrong` and `tag-typo-adoption-superior` pair is listed;
`scorer-artifact` is the residue and only its 20 most frequent pairs are shown
here. `n` is distinct adoptions (not trials). **merged reach** is the three-way
attribution. **fix removes** is how many of that pair's adoptions the
trailing-edge fix eliminates.

#### genuinely-wrong — 113 distinct adoptions, 92 distinct pairs (12 removed by the trailing-edge fix)

| n | adopted (canonical item) | hidden (tape tag) | merged reach | fix removes | first example |
|---|---|---|---|---|---|
| 4 | `Estimated` | `Tuning` | none:4 | 0 | `gd1977-04-23.143220.weidner.akg-d200e.miller.flac1644 t12` |
| 3 | `Playing In The Band` | `Playin' (Reprise)` | none:3 | 0 | `gd1991-06-17.dts.dan.33670.sbeok.flac16 t18` |
| 3 | `Prophet` | `Bertha` | none:3 | 0 | `gd1977-04-23.139535.fob.ecm.99a.hopkins.miller.clugston.flac1648 t21` |
| 2 | `Bertha` | `Tuning` | none:2 | 0 | `gd1977-04-23.139535.fob.ecm.99a.hopkins.miller.clugston.flac1648 t22` |
| 2 | `Blues For Allah` | `Tuning` | none:2 | 0 | `gd1975-06-17.fob.menke.motb.97078.flac24 t10` |
| 2 | `Dancin' In The Streets Scarlet Begonias` | `Dancing In The Street` | none:2 | 0 | `gd1977-05-08.aud.moore.berger.28354.flac16 t11` |
| 2 | `Estimated` | `Take A Step Back` | none:2 | 0 | `gd1977-04-23.139535.fob.ecm.99a.hopkins.miller.clugston.flac1648 t19` |
| 2 | `Hey Jude Reprise` | `Hey Jude ->` | none:2 | 0 | `gd1989-10-09.sbd.miller.32902.sbeok.flac16 t20` |
| 2 | `Let It Grow` | `Spanish Jam >` | none:2 | 0 | `gd1974-07-19.mtx.sirmick.103132.sbeok.flac16 t20` |
| 2 | `Mama Tried` | `Sugaree` | none:2 | 0 | `gd1979-12-28.167365.nak700.biggar.smith.miller.clugston.flac1648 t2` |
| 2 | `Playin' In The Band` | `Playing In The Band (reprise)` | none:2 | 0 | `gd1977-11-04.141004.aud.boswell.smith.sirmick.flac2496 t21` |
| 2 | `Playin' In The Band Reprise` | `Playin in the Band>` | none:2 | 0 | `gd1989-10-09.125737.mk4.48khz.flac16 t14` |
| 2 | `Saint Stephen` | `Tuning/Dead Air` | none:1/upstream:1 | 0 | `gd1977-05-08.sbd.cantor.sacks.266.shnf t17` |
| 2 | `Stronger Than Dirt Or Milkin' The Turkey` | `Blues For Allah >` | none:2 | 0 | `gd1975-06-17.fob.menke.motb.97078.flac24 t11` |
| 2 | `Sugaree` | `Crowd/Tuning` | none:2 | 0 | `gd1979-12-28.167365.nak700.biggar.smith.miller.clugston.flac1648 t1` |
| 2 | `There Is a Time` | `Red Daisy` | adjacent:1/upstream:1 | 0 | `billystrings2021-08-14.Neumann t3` |
| 2 | `Weather Report Suite Part 1` | `Let It Grow >` | none:2 | 0 | `gd1974-07-19.mtx.sirmick.103132.sbeok.flac16 t19` |
| 1 | `(Encores) It's All Over Now` | `Sugar Magnolia` | none:1 | 0 | `gd1982-08-10.sbd.kempa.334.shnf t46` |
| 1 | `= no lyrics` | `U.S. Blues` | none:1 | 1 | `gd1975-06-17.mtx.menke.gems.97079.flac16 t18` |
| 1 | `Alligator` | `Jam` | none:1 | 0 | `gd71-04-29.sbd.frisco.16782.sbeok.shnf t22` |
| 1 | `Angeline` | `Instrumental` | none:1 | 0 | `bluegrassgenerals2017-01-06.matrix t8` |
| 1 | `Back In The Goodle Days` | `Good Ole Days` | none:1 | 0 | `tmc2015-05-23 t7` |
| 1 | `Beat It On Down The Line` | `Crazy Fingers` | none:1 | 0 | `gd1975-06-17.fob.menke.motb.97078.flac24 t2` |
| 1 | `Bertha` | `The Music Never Stopped` | none:1 | 0 | `gd1977-04-23.sonyECM99a.hopkins.minches.83685.flac16 t15` |
| 1 | `Blue Collar Blues` | `I Love My Job` | none:1 | 0 | `ymsb2010-07-16.aud.flac16 t2` |
| 1 | `Boo Boo` | `Rise Up` | none:1 | 0 | `los1996-08-09.shnf t2` |
| 1 | `Branford Marsalis on saxophone throughout` | `It's All Over Now Baby Blue` | none:1 | 1 | `gd1991-09-10.fob.brennecke-young.GEMS.96422.flac16 t22` |
| 1 | `Branford Marsalis on saxophone throughout` | `It’s All Over Now, Baby Blue` | none:1 | 1 | `gd1991-09-10.153418.mtx.photoleon.flac1644 t22` |
| 1 | `Crazy` | `Used To Call Me Baby` | none:1 | 0 | `ymsb2010-07-16.aud.flac16 t8` |
| 1 | `Crazy Fingers` | `Tuning/ Bill Graham intro` | none:1 | 0 | `gd1975-06-17.fob.menke.motb.97078.flac24 t1` |
| 1 | `Crowd/Tuning` | `I Know You Rider` | none:1 | 0 | `gd1982-08-10.sbd.kempa.334.shnf t28` |
| 1 | `Crowd/Tuning` | `Stagger Lee` | none:1 | 0 | `gd1982-08-10.sbd.kempa.334.shnf t20` |
| 1 | `Cryptical Envelopment` | `Drums` | none:1 | 0 | `gd85-06-30.aud.oade-sacks.set2.7833.sbefail.shnf t5` |
| 1 | `Cryptical Envelopment` | `Drums >` | none:1 | 0 | `gd1985-06-30.165131.s2.sbd.pcm.latvala.miller.flac1644 t6` |
| 1 | `Cryptical Envelopment` | `Midnight Hour` | none:1 | 0 | `gd1968-02-14.sbd.douglas-cleef.2267.shnf t7` |
| 1 | `Dancin' In The Streets Scarlet Begonias` | `Dancin' In The Streets` | upstream:1 | 0 | `gd77-05-08.sbd.hicks.4982.sbeok.shnf t11` |
| 1 | `Dark Star Reprise` | `Dark Star >` | none:1 | 0 | `gd1991-09-10.sbd.sacks.tetzeli.fix-511.34678.reflac.flac16 t13` |
| 1 | `Depot Bay` | `Too Tired` | none:1 | 0 | `gsbg2014-02-28.BusmanLD.24bit t13` |
| 1 | `Don't Ease Me In Touch Of Gray` | `Touch Of Grey` | none:1 | 0 | `gd84-10-31.senn.14947.sbeok.shnf t9` |
| 1 | `Drums` | `Dark Star` | none:1 | 0 | `gd91-06-17.sbd.gardner.3591.sbeok.shnf t14` |
| 1 | `E. And We Bid You Good Night` | `Not Fade Away` | none:1 | 1 | `gd1989-10-26.sbd.cribbs.1829.shnf t34` |
| 1 | `Estimated Prophet` | `Crowd` | none:1 | 1 | `gd1977-02-26.sbd.wizard.32009.sbefail.shnf t31` |
| 1 | `Ewie with the Crooked Horn` | `Instrumental (forgot)` | none:1 | 0 | `ymsb2010-07-16.aud.flac16 t13` |
| 1 | `Feel Like A Stranger` | `Tuning` | none:1 | 0 | `gd1980-11-30.128440.naks.mason.flac16 t2` |
| 1 | `First Terrapin Station` | `E: U.S. Blues` | none:1 | 1 | `gd1977-02-26.sbd.wizard.32009.sbefail.shnf t30` |
| 1 | `Fixin' To Ruin` | `Old Dangerfield*` | none:1 | 0 | `bluegrassgenerals2017-01-06.matrix t5` |
| 1 | `Good Morning Little Schoolgirl` | `Morning Dew` | none:1 | 0 | `gd68-02-14.sbd.kaplan.15640.sbeok.shnf t1` |
| 1 | `Good Times` | `Never Trust A Woman >` | none:1 | 0 | `gd84-04-26.sbd.pj.4770.sbeok.shnf t13` |
| 1 | `Hey Jude Reprise` | `Hey Jude >` | none:1 | 0 | `gd1989-10-09.mtx.v2.haugh.92495.flac16 t19` |
| 1 | `Hillbillies` | `Getting Down The Road**` | none:1 | 0 | `bluegrassgenerals2017-01-06.matrix t14` |
| 1 | `Introduction` | `Morning Dew` | none:1 | 0 | `gd1968-10-12.139745.sbd.miller.Glassberg.flac1644 t1` |
| 1 | `It Must Have Been The Roses` | `Run For The Roses` | none:1 | 0 | `gd1974-06-18.sbd.bertha-ashley.18150.sbeok.shnf t2` |
| 1 | `It's All Over Now Baby Blue` | `Crowd` | none:1 | 1 | `gd1991-09-10.fob.brennecke-young.GEMS.96422.flac16 t21` |
| 1 | `It's All Over Now Baby Blue` | `encore break` | none:1 | 1 | `gd1991-09-10.153418.mtx.photoleon.flac1644 t21` |
| 1 | `La Bamba` | `Good Lovin\'` | none:1 | 0 | `gd1987-09-18.sbd.bobh.10536.sbeok.shnf t30` |
| 1 | `Let It Grow` | `Spanish Jam` | none:1 | 0 | `gd1974-07-19.sbd.gans-finney.217.sbeok.shnf t5` |
| 1 | `Let It Grow` | `Spanish Jam ->` | none:1 | 0 | `gd1974-07-19.shure.unknown.102766.flac16 t20` |
| 1 | `Let It Grow` | `Spanish Jam>` | none:1 | 0 | `gd1974-07-19.sbd.pre-dankfix.4596.sbeok.shnf t20` |
| 1 | `Man Smart` | `Shakedown Street>` | none:1 | 0 | `gd1987-09-18.nak300.pasternak.mallick.105497.flac16 t8` |
| 1 | `Momma` | `outtro and taper signout` | none:1 | 1 | `HackensawBoys2007-06-13 t31` |
| 1 | `Morning Dew` | `Good Morning Little Schoolgirl` | none:1 | 0 | `gd68-02-14.sbd.kaplan.15640.sbeok.shnf t2` |
| 1 | `Natural to Be Gone` | `What's the Difference >` | none:1 | 0 | `tmc2015-05-23 t6` |
| 1 | `Not Fade Away` | `Saint Stephen` | upstream:1 | 0 | `gd77-05-08.sbd.hicks.4982.sbeok.shnf t15` |
| 1 | `Not Fade Away` | `Saint Stephen->` | none:1 | 0 | `gd1977-05-08.sbd.cantor.sacks.266.shnf t18` |
| 1 | `Not Fade Away Encore Baby Blue` | `Not Fade Away` | none:1 | 1 | `gd84-04-26.sbd.pj.4770.sbeok.shnf t18` |
| 1 | `On the Run` | `Encore break` | none:1 | 0 | `ymsb2009-08-28.dpa4027.flac16 t27` |
| 1 | `Playin' In The Band` | `Playin' In The Band Reprise` | none:1 | 0 | `gd1977-11-04.141833.sony.ecm33p.moore.dalton.miller.clugston.flac1644 t20` |
| 1 | `Playin' In The Band Reprise` | `Playin` | none:1 | 0 | `gd89-10-09.schoeps.howland.443.sbeok.shnf t12` |
| 1 | `Playin' In The Band Reprise` | `Playin' In The Band` | none:1 | 0 | `gd1989-10-09.nak300.juteau.116646.flac t14` |
| 1 | `Playin' In The Band Reprise` | `Playin' in the Band` | none:1 | 0 | `gd83-06-18.senn421.nawrocki.14411.sbeok.shnf t16` |
| 1 | `Saint Stephen` | `Not Fade Away` | upstream:1 | 0 | `gd77-05-08.sbd.hicks.4982.sbeok.shnf t16` |
| 1 | `Saint Stephen` | `Not Fade Away->` | none:1 | 0 | `gd1977-05-08.sbd.cantor.sacks.266.shnf t19` |
| 1 | `Scarlet Begonias` | `Minglewood Blues` | upstream:1 | 0 | `gd1978-04-16.sbd.unknown.20085.shnf t14` |
| 1 | `Shakedown Street` | `E: Knockin' On Heaven's Door` | none:1 | 0 | `gd1987-09-18.nak300.pasternak.mallick.105497.flac16 t7` |
| 1 | `Supplication` | `Don't Ease Me In` | none:1 | 0 | `gd84-10-31.senn.14947.sbeok.shnf t8` |
| 1 | `Take a Step Back` | `Fire On The Mountain` | none:1 | 0 | `gd1977-04-23.sbd.aj.gardner.4334.shnf t34` |
| 1 | `The Music Never Stopped` | `tuning` | none:1 | 0 | `gd1977-04-23.sonyECM99a.hopkins.minches.83685.flac16 t16` |
| 1 | `The Other One` | `Spanish Jam` | none:1 | 0 | `gd84-04-07.sbd.dodd.13816.sbeok.shnf t15` |
| 1 | `The Wheel` | `Space >` | none:1 | 0 | `gd84-07-13.sbd.ferguson.353.sbeok.shnf t15` |
| 1 | `Throwing Stones` | `The Other One` | none:1 | 0 | `gd84-04-07.sbd.dodd.13816.sbeok.shnf t16` |
| 1 | `Throwing Stones` | `Wharf Rat` | none:1 | 0 | `gd84-04-07.sbd.dodd.13816.sbeok.shnf t17` |
| 1 | `Tied Down` | `[banter/crowd]` | upstream:1 | 0 | `gsbg2007-03-03.matrix.flac16 t28` |
| 1 | `Tuning` | `Feel Like A Stranger` | none:1 | 0 | `gd1980-11-30.128440.naks.mason.flac16 t1` |
| 1 | `U.S. Blues` | `Crowd` | none:1 | 1 | `gd1975-06-17.mtx.menke.gems.97079.flac16 t17` |
| 1 | `U.S. Blues` | `Crowd + Tune Up` | none:1 | 1 | `gd1977-02-26.sbd.wizard.32009.sbefail.shnf t29` |
| 1 | `Weather Report Suite Part 1` | `Let It Grow` | none:1 | 0 | `gd1974-07-19.sbd.gans-finney.217.sbeok.shnf t4` |
| 1 | `Weather Report Suite Part 1` | `Let It Grow ->` | none:1 | 0 | `gd1974-07-19.shure.unknown.102766.flac16 t19` |
| 1 | `Weather Report Suite Part 1` | `Let It Grow>` | none:1 | 0 | `gd1974-07-19.sbd.pre-dankfix.4596.sbeok.shnf t19` |
| 1 | `Weather Report Suite Prelude` | `WRS Part I>` | none:1 | 0 | `gd1974-07-19.sbd.pre-dankfix.4596.sbeok.shnf t18` |
| 1 | `Wharf Rat` | `Throwing Stones` | none:1 | 0 | `gd84-04-07.sbd.dodd.13816.sbeok.shnf t18` |
| 1 | `What You're Selling` | `Things You're Selling` | none:1 | 0 | `ymsb2007-02-01.SBD-KM184.flac16 t21` |
| 1 | `Wheel Hoss` | `Tied Down` | upstream:1 | 0 | `gsbg2007-03-03.matrix.flac16 t27` |

#### genuinely-wrong / filler-segment subclass — 56 distinct adoptions, 25 distinct pairs (1 removed by the trailing-edge fix)

| n | adopted (canonical item) | hidden (tape tag) | merged reach | fix removes | first example |
|---|---|---|---|---|---|
| 10 | `Jam` | `Space ->` | none:10 | 0 | `gd1989-10-09.aud.robr.31211.sbeok.shnf t18` |
| 10 | `Jam` | `Space >` | none:10 | 0 | `gd1989-10-09.dts.dan.26235.sbeok.shnf t16` |
| 5 | `Jam` | `Space>` | none:5 | 0 | `gd1989-10-09.125737.mk4.48khz.flac16 t17` |
| 3 | `Drums` | `Dark Star Jam >` | none:3 | 0 | `gd1991-06-17.dts.dan.33670.sbeok.flac16 t14` |
| 3 | `Space` | `Drums ->` | none:3 | 0 | `gd1991-06-17.128692.mtx.dusborne.flac16 t15` |
| 3 | `Space` | `Drums >` | none:3 | 0 | `gd1991-06-17.dts.dan.33670.sbeok.flac16 t15` |
| 2 | `Drums` | `Dark Star Jam ->` | none:2 | 0 | `gd1991-06-17.128692.mtx.dusborne.flac16 t14` |
| 2 | `Drums` | `Space ->` | none:2 | 0 | `gd1984-06-27.getto.aud.122873.flac16 t7` |
| 2 | `Drums` | `Space >` | none:2 | 0 | `gd84-03-28.fob-faintych.miller.27303.sbeok.shnf t15` |
| 1 | `= no lyrics` | `Crowd Out` | none:1 | 1 | `gd1975-06-17.fob.menke.motb.97078.flac24 t18` |
| 1 | `Drums` | `Dark Star jam ->` | none:1 | 0 | `gd1991-06-17.150371.FOB.Schoeps.Brotman.Metchick.Miller.Noel.t-flac1648 t13` |
| 1 | `Drums` | `Jam` | none:1 | 0 | `gd68-10-12.sbd.eD.10909.sbeok.shnf t8` |
| 1 | `Drums` | `Jam \>` | none:1 | 0 | `gd1968-10-12.sbd.gans.miller.owen.9385.shnf t16` |
| 1 | `Drums` | `Space` | none:1 | 0 | `gd85-06-30.aud.oade-sacks.set2.7833.sbefail.shnf t6` |
| 1 | `Intro` | `Blah, Blah, Blah` | none:1 | 0 | `ymsb2006-08-25.neumann140.flac16 t1` |
| 1 | `Jam` | `Primal Jam >` | none:1 | 0 | `gd1971-04-29.sbd.murphy.1858.shnf t39` |
| 1 | `Jam` | `Space` | none:1 | 0 | `gd91-06-17.sbd.gardner.3591.sbeok.shnf t16` |
| 1 | `Jam` | `Space/Jam` | none:1 | 0 | `gd90-03-22.sbd.bertha-ashley.21433.sbeok.shnf t15` |
| 1 | `Jam` | `The Eleven Jam % >` | none:1 | 0 | `gd1975-09-28.aud.gofob.86250.flac16 t9` |
| 1 | `Jam` | `eleven jam>` | none:1 | 0 | `gd1975-09-28.sbd.unknown.2562.sbefail.shnf t9` |
| 1 | `Space` | `Drums` | none:1 | 0 | `gd91-06-17.sbd.gardner.3591.sbeok.shnf t15` |
| 1 | `Spanish Jam` | `Space` | none:1 | 0 | `gd84-04-07.sbd.dodd.13816.sbeok.shnf t14` |
| 1 | `Spanish Jam` | `Space ->` | none:1 | 0 | `gd84-04-23.set2-sbd.miller.14949.sbeok.shnf t7` |
| 1 | `[ instrumental ]` | `Unknown Title #1` | none:1 | 0 | `delmccouryband2005-07-29.flac16 t5` |
| 1 | `[ instrumental ]` | `[ banjo tune ]` | none:1 | 0 | `del2005-07-29.mk21.flac16 t5` |

#### tag-typo-adoption-superior — 41 distinct adoptions, 34 distinct pairs (1 removed by the trailing-edge fix)

| n | adopted (canonical item) | hidden (tape tag) | merged reach | fix removes | first example |
|---|---|---|---|---|---|
| 3 | `Loser` | `Loset` | none:3 | 0 | `gd1974-02-24.136140.mtx.tobin.flac16 t10` |
| 2 | `Around & Around` | `Arouond & Around` | none:2 | 0 | `gd1977-05-25.147785.fob.shure.sm57.sublette.miller.clugston.flac1648 t22` |
| 2 | `Gimme Some Lovin'` | `Gimmie Some Lovin` | none:2 | 0 | `gd1985-06-30.126176.chasingwilma.flac24 t12` |
| 2 | `Mexicali Blues` | `Mexical Blues` | none:2 | 0 | `gd1980-11-29.132456.aud.flac16 t8` |
| 2 | `Mexicali Blues` | `Mexicalli Blues` | none:2 | 0 | `gd85-06-30.aud.set1.mckeown.7893.sbefail.shnf t5` |
| 2 | `Watermelon Man` | `is Watermelon Man` | adjacent:1/upstream:1 | 0 | `lkeel2009-03-07.dpa4022_portico t6` |
| 1 | `- All Four Wheels` | `All Four` | none:1 | 0 | `gsbg2015-01-22.c4.flac16 t19` |
| 1 | `Box Of Rain` | `Box OfRain` | none:1 | 0 | `gd1973-02-09.sbd.ashley.12571.shnf t24` |
| 1 | `Brown Eyed Women` | `Bown Eyed Women` | none:1 | 0 | `gd79-10-27.sbd.clugston.13980.sbeok.shnf t6` |
| 1 | `Damned If The Right One Didn't Go Wrong` | `Damed if the right one didnt go wrong` | none:1 | 0 | `ymsb2006-08-25.neumann140.flac16 t10` |
| 1 | `First Girl I Ever Loved` | `is First Girl I Ever Loved` | adjacent:1 | 0 | `lkeel2009-03-07.dpa4022_portico t3` |
| 1 | `Franklin's Tower` | `Franklins's Tower` | none:1 | 0 | `gd1975-09-28.unknown.beggs.236.shnf t5` |
| 1 | `GDTRFB` | `Goin' Down The Raod Feeling Bad` | none:1 | 0 | `gd1977-04-23.143220.weidner.akg-d200e.miller.flac1644 t20` |
| 1 | `Gimme Some Lovin'` | `Gimmie Some Lovin'` | none:1 | 0 | `gd85-06-30.aud.oade-sacks.set2.7833.sbefail.shnf t3` |
| 1 | `Goldbricking` | `Goldbreaken` | none:1 | 0 | `del2002-05-24.shnf t3` |
| 1 | `Greatest Story Ever Told` | `Greates Story Ever Told ->` | none:1 | 0 | `gd1971-04-29.sbd.unknown.4333.shnf t42` |
| 1 | `I Ain't Superstitous` | `I Ain' Superstitious` | none:1 | 0 | `gd85-04-08.sbd.wiley.8755.sbeok.shnf t7` |
| 1 | `It Hurts Me Too` | `It Hurts Me To` | none:1 | 0 | `gd1971-04-29.sbd.haugh.33565.flac16 t3` |
| 1 | `It's All Over Now Baby Blue` | `It's All Ove Now Baby Blue` | none:1 | 1 | `gd84-12-31.sbd.gorinsky.6395.sbeok.shnf t21` |
| 1 | `Jack Straw` | `Jack Staw` | none:1 | 0 | `gd1978-04-16.139240.sbd.ForTheFaithful_KTS528-529.flac1644 t1` |
| 1 | `Looks Like Rain` | `Look Like Rain` | none:1 | 0 | `gd1973-05-26.147312.aud.taback.flac16 t8` |
| 1 | `Loser` | `Lose/r` | none:1 | 0 | `gd1980-11-30.128440.naks.mason.flac16 t3` |
| 1 | `Me And Bobby McGee` | `Me & My Bobby McGee` | none:1 | 0 | `gd1971-04-29.sbd.haugh.33565.flac16 t12` |
| 1 | `Me And Bobby McGee` | `Me and My Bobby McGee` | none:1 | 0 | `gd1971-04-29.mtx.hansokolow.97660.flac16 t12` |
| 1 | `Morning Dew` | `Moring Dew` | none:1 | 0 | `gd1977-05-08.148737.SBD.Betty.Anon.Noel.t-flac2448 t22` |
| 1 | `New Minglewood Blues` | `New Minlewood Blues` | none:1 | 0 | `gd1982-08-10.152133.mouth.akg-ce1.mac.uherarchive.rogers.wise.flac2444 t3` |
| 1 | `New Speedway Boogie` | `New Speedway Boogies` | none:1 | 0 | `ymsb2010-07-17.aud.flac16 t9` |
| 1 | `Peggy-O` | `Peggio` | none:1 | 0 | `gd1975-06-17.aud.unknown.87560.flac16 t5` |
| 1 | `Playin' In The Band` | `Playing In The Bnad` | none:1 | 0 | `gd1974-07-19.shure.unknown.fix-102766.102866.flac16 t10` |
| 1 | `Stronger Than Dirt Or Milkin' The Turkey` | `tronger Than Dirt Or Milkin' The Turkey >` | none:1 | 0 | `gd1975-06-17.fob.menke.motb.97078.flac24 t13` |
| 1 | `Tennessee Jed` | `Tennesee Jed` | none:1 | 0 | `gd1973-11-17.sbd.patched.bec.22799.flac16 t6` |
| 1 | `Tennessee Jed` | `Tennesse Jed` | none:1 | 0 | `gd1974-06-18.sbd.bertha-ashley.18150.sbeok.shnf t21` |
| 1 | `They Love Each Other` | `The Love Each Other` | none:1 | 0 | `gd77-09-03.sbd.unk.276.sbefixed.shnf t2` |
| 1 | `Wharf Rat` | `Whar Rat` | none:1 | 0 | `gd84-04-19.aud.willy.14013.sbeok.shnf t17` |

#### scorer-artifact — 417 distinct adoptions, 231 distinct pairs (20 most frequent; the class is the residue and is enumerated in full in the companion `.triage.tsv`)

| n | adopted | hidden |
|---|---|---|
| 31 | `Minglewood Blues` | `New Minglewood Blues` |
| 16 | `Promised Land` | `The Promised Land` |
| 11 | `We Can Run But We Can't Hide` | `We Can Run` |
| 8 | `Mississippi Half-Step Uptown Toodleloo` | `Mississippi Half-Step Uptown Toodeloo` |
| 8 | `Touch Of Gray` | `Touch of Grey` |
| 8 | `Drums` | `Drumz>` |
| 7 | `New Minglewood Blues` | `Minglewood Blues` |
| 7 | `Day Job` | `Keep Your Day Job` |
| 6 | `Prophet` | `Estimated Prophet` |
| 5 | `She Makes My Love` | `She Makes My Love Come Rolling Down` |
| 5 | `My Brother Esau` | `Brother Esau` |
| 5 | `CC Rider` | `C.C. Rider` |
| 4 | `We Bid You Good Night` | `And We Bid You Good Night` |
| 4 | `Mississippi Half-Step Uptown Toodleloo` | `Mississippi Half Step` |
| 4 | `The Promised Land` | `Promised Land` |
| 4 | `Stronger Than Dirt Or Milking The Turkey` | `Stronger Than Dirt Or Milkin' The Turkey >` |
| 4 | `Mississippi Half Step` | `Mississippi Half-Step Uptown Toodeloo` |
| 4 | `C.C. Rider` | `CC Rider` |
| 4 | `Women Are Smarter` | `Man Smart, Woman Smarter` |
| 4 | `Mississippi Half-Step Uptown Toodleloo` | `Mississippi Half-Step Uptown Toodeloo >` |


---

## Exposure: what the rung does to the cache as it actually stands

The blind test manufactures gaps. This measures the real ones — blinding
nothing, running `adopt_gap_titles` over every cached item exactly as gathered.

### Before the fix (`a37bb83`): two adoptions, one of them junk

```console
$ ./.venv/bin/python scripts/blind_tag_gapfill.py --natural --progress 500
items measured                : 960
naturally unresolved tracks   : 210
items the rung changes at all : 2
tracks the rung fills         : 2

is2008-12-06.flac16.aud   34  for being so nice and quiet which allowed me to pull a nice recording.
ymsb2010-07-17.aud.flac16 19  Robot Jam
```

- `ymsb2010-07-17` track 19 is the mechanism working as designed. The tape's own
  tags run `... Another Day / <untagged> / Ramblin In The Rambler pt.1 ...`; the
  canonical has `Another Day / Robot Jam / Ramblin In The Rambler pt.1`; the gap
  is one file against one item between two exact anchors, in the **interior** of
  the tape. `Robot Jam` is a title nothing else in llama could have recovered,
  and before this rung it shipped as `ymsb2010-07-17d2t10.mp3`.
- `is2008-12-06` track 34 is failure shape 5. It is the **last** file on the
  tape; the parsed canonical's 39th and final item is the tail of the taper's
  notes; the gap is a trailing run anchored on the left only, so its span ran to
  the end of the canonical. One item, one file, count-forced, and `_hygienic`
  cannot reject the sentence. That tape's canonical tail is
  `... / Tuning / Banter / for being so nice and quiet which allowed me to pull
  a nice recording.` — and `ymsb2010-07-17`'s is
  `Zoom H4n @ 44.1/16 / sdhc card / Sound Forge 6 / TLH`. The trailing span of a
  parsed LMA setlist really is where the lineage notes live.

### The fix, and its measured cost

`adopt_gap_titles` no longer fills a run reaching the last track
(`b1ca393`). The leading-edge branch is kept — its span ends at a real anchor's
item, so it can never reach the canonical's tail. Cost measured by sweeping the
corpus with and without:

| | `a37bb83` | `b1ca393` | delta |
|---|---|---|---|
| distinct adoptions | 6,864 | 6,546 | **−318 (−4.6%)** |
| — correct | 6,237 | 5,972 | −265 |
| — scorer-artifact | 417 | 378 | −39 |
| — tag-typo (adoption superior) | 41 | 40 | −1 |
| — **genuinely-wrong** | 113 | 101 | **−12** |
| — genuinely-wrong / filler | 56 | 55 | −1 |
| strict genuinely-wrong rate | 1.65% | **1.54%** | −0.11 pp |

The first version of this document estimated the cost as "the 1.99% edge
population" — 1,156 adoptions, 17% of the corpus. **The measured cost is 318,
4.6%**, roughly 3.6× smaller. That estimate was wrong because it conflated the
whole edge population with the *trailing* half of it.

**On the blind corpus the fix trades 265 correct titles for 12 wrong ones —
about 22:1 — and that lopsided ratio is the right trade, because the two costs
are not comparable.** A **declined** title leaves the track showing its
filename, which the operator repairs with a single `llama fix --set-title N=…`
call, and which `llama status` already surfaces as an unresolved title. A
**wrong** title is silent: it reaches `manifest.json`, the m3u, the ID3 tags and
the air, and neither of the guards downstream can catch it — llama's
`briefing_guard` and emcee's `script_guard` both take the tracklist as their
definition of truth, so a title that is confidently wrong is simply the premise
they reason from. Asymmetric costs justify a lopsided ratio.

**And the fix is targeted rather than blunt.** All five bad adoptions in
evidence — four in the blind corpus, one natural — sit at `track == n_tracks`.
The good natural adoption is interior and survives.

### After the fix (`b1ca393`): one adoption, and it is the right one

```console
$ ./.venv/bin/python scripts/blind_tag_gapfill.py --natural --progress 500
items measured                : 960
naturally unresolved tracks   : 210
items the rung changes at all : 1
tracks the rung fills         : 1

ymsb2010-07-17.aud.flac16 19  Robot Jam
```

**One adoption across 960 cached items and 210 genuinely-unresolved tracks, and
it is correct.** This is the number that matters for shipping, and it should be
read plainly in both directions: the rung's blast radius on today's corpus is
one track, and so is its yield. The other 209 unresolved tracks are untouched —
overwhelmingly because they sit on wholly-untagged tapes where there are no
anchors at all, or in runs whose item count does not match. That is
count-forcing declining, which is what it is for.

**The rung is very nearly inert on this corpus, and that is a measurement, not
a defect.** Its value is prospective: it fires when a tape is well tagged
*except* for a short interior run, and the `--natural` measurement says that
situation occurs once in 960 cached items today. Anyone who finds this rung
later and wonders whether it is dead code should re-run the command above rather
than re-diagnose it:

> `./.venv/bin/python scripts/blind_tag_gapfill.py --natural` — 2026-08-31,
> 960 cached items, 210 unresolved tracks, **1 adoption**
> (`ymsb2010-07-17.aud.flac16` t19 → `Robot Jam`), correct.

---

## The ship gate

The plan's gate: *"ship unflagged only if `genuinely-wrong` is at or below the
tag rung's own typo baseline."* Ruling 9 of the Phase A SDD ledger
(`docs/superpowers/2026-08-31-phase-a-sdd-ledger.md`) made the by-anchor-kind
breakout a second, independent gate; Ruling 7 there is the merged-anchor
question and Ruling 6 the escalation rule.

**Gate on the merged-anchor path: NOT PASSED, NOT FAILED — the gate as
originally instrumented was measuring the wrong thing, and re-instrumented it is
underpowered in both directions.** See "The gate answered a question nobody
asked" and "Both directions are underpowered". The first version of this
document reported this gate as passing decisively; that is withdrawn. The
merged-anchor question is **open**, with the reactivation condition and the
prepared tightening recorded above.

**Gate on the pooled rate: cannot be settled as written, because the reference
quantity does not exist.** "The tag rung's own typo baseline" has never been
measured in this repo, and this instrument cannot measure it without
circularity: the tags are the ground truth here, so an experiment that scores
them needs a *third* source. What this instrument does yield are two bounds:

- **≥ 0.60%** of adoptions (41 of 6,864) sit at a position where the tape's tag
  is demonstrably defective and the adopted canonical title is better — a
  *floor* on the tag rung's error rate, since it only counts tag defects large
  enough to be scored wrong and small enough for me to adjudicate.
- **6.5%** of scored disagreements (41 of 627) are the tag's fault rather than
  the adoption's.

Against the floor, the shipped strict rate of 1.54% is about 2.6× the tag rung's
demonstrated error rate, so on a literal reading the pooled gate **does not
pass**. Against any honest estimate of the true tag-typo rate the comparison is
unresolved — the floor is certainly a large undercount, because every tag defect
the canonical happens to reproduce is invisible to this experiment.

**The gate is recorded as unresolvable as specified rather than adjusted until
it resolves.** No threshold was moved and no class boundary was drawn to reach a
number: judgement calls 1–3 were made before the first roll-up was run, and
judgement call 4 (added at review) moved the headline **up**, not down.

### Recommendation

**Ship Piece 1. The trailing-edge fix is applied; do not add a review flag; do
not apply the `_merge_run` tightening.** Reasoning, in the order it should be
weighed:

1. **The trailing-edge path was the one shape that could not ship, and it is
   fixed.** Measured cost 318 adoptions (4.6%), trading 265 declined titles for
   12 wrong ones at asymmetric cost, and on the natural population it removes
   the one junk adoption while sparing the one good one. See "Exposure".
2. **The shipped rate is 1.54%–2.38%**, the range rather than a point because
   judgement calls 1 and 2 are in tension (see call 2). Against the alternative
   — the track ships as `gd77-05-08d2t04.mp3` — a title that is right 97.6–98.5%
   of the time is a large improvement in what a listener sees and what a
   scriptwriter reads. Two thirds of the residual error is one upstream
   parse-defect class, correlated across sibling recordings, so 101 distinct
   adoptions are far fewer than 101 independent failures.
3. **Do not apply the `_merge_run` tightening**, for the reasons in its own
   section: both attributions are underpowered, this project does not ship
   knobs it cannot re-validate, and the sole natural adoption has
   `merged_attr = none`, so the tightening would not touch anything that
   currently executes. The question stays open with a stated reactivation
   condition rather than being retired.
4. **No review flag.** At the measured exposure it would fire on one show in 89
   and would flag the correct adoption. The shape that needed catching was
   specific enough to decline outright, and it has been.
5. **What would change this recommendation:** the rung making natural adoptions
   at any volume on a future corpus. At that point the merged-anchor rate must
   be re-measured with adequate power before adoptions are trusted, and the
   1.54%–2.38% rate — measured on synthetic gaps — should be re-derived on the
   real population rather than assumed to carry over.

**This is a recommendation, not a decision.** Ruling 6 of the SDD ledger applies:
whether Phase A ships unflagged, ships flagged, or is held is the plan owner's
call.

---

## Fixture caveat: `gd73_metadata.json` pre-empts the code under test

**Read this before writing any test against the canonical fixture.** It cost the
Phase A plan author three separate debugging cycles, and Phase B has more
fixture-dependent tests than Phase A did.

`packages/llama/tests/fixtures/gd73_metadata.json` filters to **6 kept `VBR MP3`
files**, and its description parses to **6 setlist items at
`confidence="high"`**:

```console
$ ./.venv/bin/python -c "..."   # filter_files + parse_setlist on the fixture
kept mp3 files: 6
parsed items: 6 confidence: high
names: ['gd73-06-10d1t01.mp3', ..., 'gd73-06-10d3t01.mp3']
items: ['Morning Dew', 'China Cat Sunflower', 'I Know You Rider', 'Dark Star', 'Eyes of the World', 'Johnny B. Goode']
```

`titles.resolve_titles`' whole-tape rung is gated on
`setlist.confidence != "low" and len(setlist.items) == n` (titles.py:129–147).
On this fixture that is `6 == 6`, so **the rung fires**. Consequences:

- **A test that blanks a tag on gd73 to create an unresolved run does not create
  one.** The blanked positions resolve as `title_source == "setlist"` and
  `adopt_gap_titles` never sees a gap. The test then passes or fails for reasons
  that have nothing to do with the code it names.
- **This is a fixture property, not a production one.** The same rung fires
  **zero** times across 2,015 production tracks:

  ```console
  $ ./.venv/bin/python scripts/title_source_census.py     # 2026-08-31
  shows=89 tracks=2015
    tags 1917
    unresolved 75
    sibling 21
    override 2
  ```

  The census prints only the sources it observes, and **neither `setlist` nor
  `setlist-gap` appears at all** — 1917 + 75 + 21 + 2 = 2015, so both are
  exactly 0. Exact count equality between a parsed
  description and a tape's file list is close to a measure-zero event on real
  tapes. The corpus sweep above says the same thing from the other side: 25,416
  of 57,098 blinding trials were pre-empted by this rung, because blinding
  manufactures the untagged condition that lets it be reached.

**The workaround, used by the Phase A tests that need a real gap:** add an
`overrides.exclude` entry for a file that is already untagged, breaking the
count coincidence without touching either anchor or the gap under test —

```python
write_artifact(sws.overrides, Overrides(exclude=["gd73-06-10d3t01.mp3"]))
# kept=5, items=6 -> the whole-tape rung declines, adopt_gap_titles is reachable
```

See `test_gap_fill_resolves_a_mixed_show` and
`test_adopted_titles_make_the_closer_tripwire_reachable` in
`packages/llama/tests/test_stage_gather.py`, both of which carry this reasoning
in their docstrings.

**Do not re-cut the fixture.** It is the canonical fixture for the whole repo;
changing its file or item count would invalidate measurements and pinned
expectations across `test_stage_gather.py`, `test_structure.py`, `test_junk.py`
and `test_setlist.py`. The count coincidence is a known trap to route around,
not a defect to fix.

---

## User-visible behaviour change shipped by Phase A

**A show whose every songish title came from the setlist now sets
`needs_review = True` where it previously set `False`**, with the review flag
`"low-confidence structure alignment"`.

The mechanism: `structure.TAUTOLOGICAL_TITLE_SOURCES` is
`{"setlist-gap", "setlist"}`, and `_songish_coverage` excludes both from its
denominator, because a track whose title *is* the canonical item's own text
cannot furnish independent evidence that `align()` matched it. On a show where
every songish track is `setlist`-sourced the independent-evidence set is empty,
coverage is the safe-direction `0.0`, and the low-confidence flag fires.
`gather.py`'s final track assembly tests the same constant, so those tracks also
report `matched = None` ("not measured") rather than `True`.

**This is the safe direction and it is honest** — such a show has literally zero
independent evidence its alignment is right, which is exactly what the flag
exists to say. It is nonetheless user-visible, so it is recorded here rather
than only in a test docstring.

**Scoping: 0 of 2,015 production tracks are affected.** Per the census quoted
under the fixture caveat above (`shows=89 tracks=2015`, 2026-08-31), the
`setlist` rung produces **0** tracks in the live library, so no existing show
flips. The change is reachable in tests (`test_gather_artist_item_does_not_block_title_resolution` in
`test_stage_gather.py` asserts it directly, with the reasoning in its
docstring) and on any future tape where that rung fires.

---

## Candidate population, and why one adoption understates the trajectory

Measured 2026-08-31 over the same 958 usable cached items, counting the SHAPE
the rung needs rather than the adoptions it makes:

| tag state of the item | items |
|---|---|
| every track tagged | 880 |
| no track tagged | 57 |
| **mixed** | **21** |
| ...of which carry an interior untagged run between tagged tracks | **17** |

Split by artist family (`jerrybase.is_family_artist`):

| | interior-gap items |
|---|---|
| other artists | 16 |
| Garcia family | 1 |

Two things follow, and the second corrects an impression the one-adoption
headline gives on its own.

**The binding constraint is conversion, not population.** Seventeen items
already have the target shape and the rung adopts on one. So the filter is not
"mixed-tag shows are rare" — they are seventeen times more common than the
adoption count. It is that count-forcing rarely holds even when the shape is
right. Sharpest form: those 17 include all four partially-unresolved shows in
the live library (Del McCoury 8/21, Greensky, Stringdusters, Trampled) and the
rung resolves none of them.

**The population skews 16:1 away from the Dead**, toward exactly the acts where
a taper tags most tracks and leaves a couple they do not recognise — Del
McCoury, Greensky Bluegrass, Infamous Stringdusters, Trampled by Turtles,
Yonder Mountain. A library that grows in lower-profile acts grows this rung's
candidate pool along the axis that feeds it, so its value trends up over time
rather than down. That is the forward-looking case for keeping it, and it is
measured rather than assumed. It does not change the present-day number.

Census command: `scripts/title_source_census.py` for the library view; the
tag-state census above is reproducible from the cache with `filter_files` +
`clean_tag_titles` + `is_real_title` over `~/.llama/cache/md_*.json`.

## What this does not measure

- **`setlistfm=None`.** Stated at the top and restated here because it is the
  single largest caveat: every canonical here is LMA-only, and the real
  canonicals for several of these shows are setlist.fm-won. **Every number in
  this document is a bound.**
- **Correlated failures are counted as independent.** The 113 distinct
  genuinely-wrong adoptions include the same upstream parse defect reproduced
  across five recordings of gd1974-07-19 and two of gd1991-09-10. The count of
  distinct *causes* is materially smaller, which cuts both ways: it makes the
  rate look worse than the number of underlying problems, and it means a single
  upstream parser fix could remove a large slice of it.
- **The blinded population is not the production population.** Blinding a
  well-tagged tape's tuning track manufactures a one-file gap that production
  reaches only when the tape is untagged at that spot. The `--natural` run is
  the honest exposure measure; the blind test is the honest *rate* measure, on a
  population chosen to be measurable rather than to be representative.
- **The blind test systematically bypasses the sibling rung, so production's
  pre-emptions are undercounted.** `prepare()` computes `sibling_titles` from
  the *unblinded* tape, so a fully-tagged tape has `title_fraction == 1.0` and
  gather's sibling-lookup gate never fires — whereas in production that same
  tape with a genuinely untagged run would fetch sibling recordings and often
  resolve the gap before `adopt_gap_titles` is reached. The 1,138 recorded
  sibling pre-emptions are therefore a floor. This inflates the blind test's
  *firing* rate, not its error rate, and it is one more reason `--natural` is
  the number to ship on.
- **The `extract_setlist` LLM fallback population is silently excluded.** When
  `rank_parses` returns None, production runs the `extract_setlist` LLM task on
  the longest description; the harness is offline and uses an empty canonical
  instead, so those recordings contribute no adoptions either way. Their true
  behaviour is unmeasured here.
- **The 135 unverifiable adoptions are *induced* by the blinding, not merely
  out of window.** Removing an anchor changes the monotone walk, which can let a
  pre-existing unresolved run elsewhere on the tape become count-forced and
  fillable. They are an artifact of the experiment rather than a property of the
  code — consistent with `--natural` finding one fill in the whole cache — and
  they are excluded from every rate above because they have no ground truth. The
  trailing-edge fix drops them to 54.
- **`edge`-conditioned figures depend on a collapse rule.** See "The `edge`
  split is collapse-rule-dependent".
- **Coverage is not evaluated here.** The known gap recorded in `CLAUDE.md` —
  coverage never inspects unmatched *items* — is untouched by this work.
- **The `flac` sweep is untriaged.** Its rate is a raw rate and no gate is drawn
  from it.
- **Statistical power.** Every by-attribution comparison in this document rests
  on single-digit event counts and none of them is significant. Intervals are
  given so this is visible rather than implied.

---

## Reproduction

From the worktree root, with its own venv (never a bare `pytest`/`python`).
The harness reads `~/.llama/cache/md_*.json` and writes nothing anywhere.

```bash
# 0. the non-empty demonstration -- run this first, it exits non-zero on failure
./.venv/bin/python scripts/blind_tag_gapfill.py --selftest

# 1. the shipped code (b1ca393)
./.venv/bin/python scripts/blind_tag_gapfill.py --progress 500 > sweep-postfix.tsv
./.venv/bin/python scripts/blind_tag_gapfill.py --format flac  > sweep-flac.tsv
./.venv/bin/python scripts/blind_tag_gapfill.py --natural      > natural-postfix.tsv

# 2. the pre-fix population the hand triage was performed on (a37bb83)
git checkout a37bb83 -- packages/llama/src/llama/structure.py
./.venv/bin/python scripts/blind_tag_gapfill.py --progress 500 > sweep-prefix.tsv
./.venv/bin/python scripts/blind_tag_gapfill.py --natural      > natural-prefix.tsv
git checkout HEAD -- packages/llama/src/llama/structure.py

# 3. every class count in this document, from the shipped classification
./.venv/bin/python scripts/blind_tag_gapfill.py \
    --triage docs/superpowers/2026-08-31-gap-fill-blind-test.triage.tsv \
    --rows sweep-prefix.tsv
./.venv/bin/python scripts/blind_tag_gapfill.py \
    --triage docs/superpowers/2026-08-31-gap-fill-blind-test.triage.tsv \
    --rows sweep-postfix.tsv

# 4. the 2,015-track production census used by the fixture caveat
./.venv/bin/python scripts/title_source_census.py
```

`--triage` exits 1 if any wrong adoption in the sweep has no class in the
classification file, so a sweep and a classification that have drifted apart
report loudly instead of looking clean.

Suite at the time of writing: `./.venv/bin/pytest -q` → **1500 passed, 7
deselected**.


## M2: full-library no-op check (2026-08-31)

Gate M2 from the spec, run by `scripts/regather_diff.py`. Re-gathers every show
in the on-disk library twice from cached metadata — once with the rung active,
once with `adopt_gap_titles` monkeypatched to a no-op — and asserts that
enabling it changes no track the unwired run already resolved.

    $ ./.venv/bin/python scripts/regather_diff.py --assert-no-regressions
    compared 89 shows (0 skipped)
    0 regressions; 0 newly resolved
    exit 0

Wired-vs-unwired rather than "stored show.json vs new code": the stored shows
were produced by several older code versions (some by a released binary
predating `Track.matched`), so a diff against them would be dominated by
unrelated drift and could attribute nothing to this change.

**Zero regressions AND zero adoptions cannot, on its own, distinguish a check
that ran from one that never engaged**, so the harness carries a `--selftest`
mode that substitutes a deliberately wrong adopter:

    $ ./.venv/bin/python scripts/regather_diff.py --selftest
    compared 89 shows (0 skipped)
    0 regressions; 75 newly resolved
    SELFTEST: harness CAN detect a difference -> PASS

75 is exactly the library's unresolved-track count, so the comparison is live
and the real run's zeros are a measurement.

Zero adoptions on the library is consistent with the one natural adoption
reported above: `ymsb2010-07-17` is cached but is not one of the 89 shows.

Standing caveat, as everywhere else here: this runs with `setlistfm=None`, so
shows whose real canonical was setlist.fm-won are re-derived from LMA
descriptions alone. It bounds the change's blast radius; it does not replicate
production.
