# Header truncation, parse ranking, and track-side prefixes — phase 4a

Phase 3 fixed the parser's junk emission and left one defect deliberately on
the table, sized: descriptions whose first structure marker is an encore
marker, where `parse_setlist`'s header truncation discards the entire setlist
above it. This phase fixes that truncation, lands the coupled second half of
the leading-dash tolerance, re-ranks `rank_parses` so a parser defect of this
class can never again outrank a complete sibling parse, and adds the one
measured matching-layer remainder small enough to carry: track-side numeric
prefixes. **The window/desync redesign (4b) is explicitly out of scope** — it
must be designed against the numbers this phase produces, not projections.

Every number below was measured against shipped code at `db02575`
(code-identical to `a997e49` for all of `llama/`; `db02575` adds only docs)
over `corpus.jsonl` (1181 rows) and `corpus-nondead.jsonl` (874 rows), with
descriptions re-parsed end-to-end from `iacache`. **The 4c backfill is done:
iacache now covers 1166/1181 Dead rows (the remaining 15 have no usable
description in their metadata) and 874/874 non-Dead. End-to-end numbers are
now authoritative on BOTH corpora.** One consequence to absorb: the phase-3
record's Dead end-to-end figures (0.8206 → 0.8834) came from the 39-row
pre-backfill sample and were labelled indicative; the authoritative full-corpus
figure at HEAD is **0.7982** (17116/20921 over 1081 usable shows). The 39-row
sample overstated Dead coverage by ~8 points. Use 0.7982 as 4a's Dead
end-to-end baseline.

**Preprocessing is part of every number.** All description-level measurements
mirror the parser's own text preparation — `<br>` → newline, generic
`<[^>]+>` tag stripping, `html.unescape` — before any line logic. An ad-hoc
preparation (only `<br>` handling) reads the headline truncation shape as
82/78 instead of 149/145 on the same data. State the preprocessing next to
every number, alongside its baseline pair.

## The defect

`parse_setlist` (setlist.py:235-241) finds the first line matching
`_SET_LINE` / `_LABELED_SET_LINE` / `_ENCORE_LINE` and discards every line
above it as header. That is correct when the marker starts the show
("Set 1:" — the block above is band/venue/lineage). It is wrong when the
marker cannot start a show: a description shaped

```
Shimmy She Wobble
Back Back Train
...six more songs...
Encore:
Rollin' N Tumblin'
```

loses its entire main setlist and parses encore-only — and the truncated
parse then *gains* confidence (`saw_marker` becomes true), which is what let
it outrank complete siblings (see §3).

Measured incidence, end-to-end, parser preprocessing, at `db02575`. Two
counts exist and both are stated: the *description sweep* (all cached
descriptions, no track requirement — the parser-level view) and the *corpus
rows* with ≥3 tracks (the alignment-level view the upside is priced on):

```
description sweep (pre-backfill 923):  encore-first 149 (145 >=10, 3 5-9, 1 <5)
                                       set>=2-first 7 (5 >=10)
corpus rows with tracks, in shape      non-Dead 148/848   Dead 73/1166
  passing the >=5 floor                  146                70
  matched-track upside (naive, L=3)     +1091 (492->1583)  +554 (257->811)
```

Dead incidence is **6.3% of rows (73/1166) — real, not near zero**, roughly
40% of the non-Dead rate (17%). The pre-backfill 39-row Dead sample contained
zero of them; that was sample bias, now retired. Combined naive upside
**+1645 matched tracks** across both corpora before any window work — versus
phase 3's total end-to-end gain of +231. (An earlier figure of +1129 for
non-Dead was measured on the encore shape only, without the floor; the
unified-definition number is +1091. The in-shape counts include 3 non-Dead
and 1 Dead rows whose first marker is a *labeled set line with an
unrecognized ordinal* — under the rule below those truncate as today, so the
implementer's re-measure should come in marginally under these figures and
must say so rather than chase the delta.)

## Scope

Four changes, in dependency order. §1 and §2 land in the SAME change — that
coupling is a hard constraint, not a preference.

### 1. Truncation: only a show-starting marker may truncate

**Rule.** Compute `first_marker` exactly as today (over pre-split lines — the
C1 reorder stands). Truncate when the first marker is a **set-1** marker or a
**labeled set line with an unrecognized ordinal** (the parser already
resolves those to set 1, and "may this marker start a show" must get the same
answer). When it is an **encore** marker or a **set ≥ 2** marker with a
recognized ordinal, probe the lines above: if they parse to **≥ 5 items** on
their own (the parser's own confidence floor, via a recursive
`parse_setlist` of the above block — which cannot itself truncate, since the
block contains no markers by construction), **keep them**; below the floor,
truncate as today.

**Set labels fall out correctly with no extra machinery.** Untruncated
pre-marker lines flow through the parse loop with `current_set = None`, so
their items get set `"1"` — exactly right for the set≥2 shape (the block IS
set 1) and the honest answer for the encore shape (the block is the main
body; its internal breaks are unknowable from this source — alignment,
jerrybase anchoring, and `structure_guard` own that question downstream).

**The floor is 5, not 10 — a correction to the phase-4 proposal.** The
proposal implied the measured ≥10 band was the target. Inspecting the 5-9
band: all three non-Dead cases (`bfft2002-06-29`, `guster2006-06-19`,
`rad1996-05-03`) are real discarded songs, not headers. The single <5 case
(`charliehunter2009-09-09`: `One Set: (1:39:44)` / `1. intro` / `2.` / `3.`)
is junk and keeps truncating. Floor 5 recovers 148/149 encore-shape and 6/7
set≥2-shape descriptions on the non-Dead sweep.

**Out of scope, measured and declined: set-1-first with content above.**
43 non-Dead descriptions have non-noise lines above a "Set 1" marker; the
sampled ≥10-item blocks are header/support-act material (`Blues Traveler /
8/1/98 / H.O.R.D.E. Festival`), not lost setlists. Truncating them is the
feature working. Do not "generalize" the rule further than the two marker
classes above; record any future evidence instead.

**Rejected alternative (do not re-propose on elegance):** "prefer the first
SET marker, fall back to an encore marker only when no set marker exists."
Already rejected in the C1 record for failing the numbered-tracklist-with-no-
set-header cases (`spindoctors2001-09-07` et al.), which are exactly the 149
shape. The C1 reorder fixed the split-created-marker half; this section fixes
the line-start half.

**Existing tests that must move, named here so their changes are read as
signal:** `test_encore_rule_above_a_tracklist_does_not_truncate` is the
coupling guard — after §1+§2 it must be retargeted to assert the tracklist
survives AND `Rollin' N Tumblin'` is labelled `encore` (its docstring says to
do exactly this when the coupled fix lands).
`test_dash_decorated_set_headers_are_recognized` must stay green untouched:
its fixture is set-1-first with a 3-line header (below floor on both counts).
`test_gd74_windsor_keeps_the_whole_setlist_around_its_inline_encore` (34 =
26 + 8) must stay byte-identical. Sweep the suite for any other test pinning
encore-first truncation as correct; retarget with a comment, never delete.

### 2. The coupled patch: `_LEAD_DECOR` on `_ENCORE_LINE`

`dash-tolerance-FULL.patch` (preserved in the phase-3 ledger scratchpad,
verified to apply cleanly at `a997e49`/`db02575`) gives `_ENCORE_LINE` the
same leading-decoration tolerance set markers got in `31c763e`. **It must
land WITH §1 and never before it**: alone, recognising `---encore:` as a
marker makes it a `first_marker` and the truncation defect then discards the
22 tracks above it — measured cost **26 real songs on `nmas2013-02-13.16.44`
(32 → 6 items)**. With §1 in place the same recognition becomes a pure win:
that description must parse to ≥ 32 items with the encore correctly labelled,
and is named in the acceptance gates below.

The patch's header carries two obligations that are part of this section's
definition of done: rewrite the "SET MARKERS ONLY" comment paragraph in
`setlist.py` (it justifies the omission this patch removes), and retarget the
coupling guard test per §1. Landing the hunk without them leaves the tree
contradicting its own comments.

### 3. `rank_parses`: a truncated parse must not outrank a complete one

`structure.py:250-266` ranks `(source==setlist.fm, confidence, multi_set,
-|len-target|)`. Confidence sits above completeness, and a truncated parse
has *higher* confidence than a complete unmarked sibling (`saw_marker` true,
≥5 items → "high" vs "medium"). That is the amplifier from the C1 record: an
8-item encore-only parse outranked a complete 34-item sibling.

**Design: insert a plausibility tier above confidence:**

```python
plausible = len(p.parsed.items) >= max(5, target_count // 2)
return (p.source == "setlist.fm", plausible, _CONF_RANK..., multi_set, ...)
```

A parse covering less than half the tape's track count is implausible as the
show's setlist and may win only when nothing plausible exists. Degrades
gracefully: when every candidate is implausible (or every one is), the tier
is constant and today's ordering decides.

**Alternative recorded (narrower):** demote only encore-only parses (no
numbered set). Rejected as the primary because it guards exactly one defect
shape; the plausibility tier also catches the next truncation-like defect,
which is the point of insurance. If measurement shows the plausibility tier
changing winners it should not (see gate 6), fall back to this.

**setlist.fm stays on top.** Its tier is untouched; this section only stops a
*truncated LMA parse* beating a *complete LMA parse*.

### 4. Track-side numeric and duration prefixes (matching layer only)

Tag titles like `18 Lost My Driving Wheel`, `08 History Lesson - Part II`,
`[05:20] KC Jones**` fail to match items that are present. Measured among
residual absent-bucket misses at HEAD (end-to-end, both corpora): non-Dead
244 prefix-carrying misses, **96** match an item once stripped; Dead 235,
**164**. Floor ≈ **+260 matched tracks**.

**Design constraints (each one is load-bearing):**

- **Matching layer only.** Stored `Track.title` is never modified — it feeds
  briefings, dj-notes and the manifest. The strip happens inside `align()`'s
  compare path, exactly as phase 2's fuzz does. `songs.normalize_song` and
  `DEFAULT_ALIASES` stay untouched (standing invariant).
- **Miss-path fallback only.** Try the unstripped title first; attempt the
  stripped form only when `_window_match` returns None. This self-guards the
  hazard titles: a track genuinely titled `8 Miles High` matches its item
  unstripped and never reaches the strip.
- **Gated on an enumerated tape**, mirroring the parser's document-level
  discriminator: apply only when ≥ 3 of the tape's cleaned tag titles begin
  with a digit-prefix shape. A lone numeric-titled song on a non-enumerated
  tape is never touched.
- Prefix shape: 1-2 digit index with optional `.`/`)`/`-` punctuation, or a
  bracketed/bare `mm:ss` duration. The 2-digit cap plus the fallback ordering
  protects `1952 Vincent Black Lightning` twice over.

The +96/+164 sizing was measured with an *unconditional* strip applied only
to already-missed tracks; the shipped, gated form must be re-measured and may
come in slightly under the floor. Report the delta, not the projection.

## What this phase does NOT do

- **No lookahead/window change of any kind** (4b). The sweep evidence and
  design candidates are recorded in the phase-4 proposal; 4b's spec is
  written against post-4a numbers.
- No set-1-first truncation change (§1, measured, header-dominated).
- No credit-title widening (the 175 still-emitted credit-shaped titles), no
  `_NOISE` format-chatter widening, no `_NEVER_EQUAL` space-collapse keying
  (latent, not live), no Space synthesis — all per the standing phase-3
  deferrals, none invalidated by anything measured here.
- No trailing-decoration stripping (ruling 21 stands; the `('-','1')`
  residual remains pinned by test).

## Acceptance criteria

Baseline to beat: **1261 passed / 7 deselected** at `db02575`; anchoring
**560/756, 0 disagreements**; end-to-end coverage **0.5033 non-Dead / 0.7982
Dead**; full-corpus (stored-setlist) coverage 0.4734 non-Dead / 0.7765 Dead.
Every reported number states its baseline pair and instrument; every
description-level number uses the parser's own preprocessing.

1. Full suite green. Anchoring unchanged or better, **0 disagreements**.
2. **Songs lost = 0**, per description, over the full iacache sweep (now
   2040 usable descriptions, not 923 — re-baseline the sweep first and state
   both counts). The unit is SONGS, not items: an item-count delta cannot
   distinguish junk from songs (ruling 17). Any lost song anywhere is
   stop-and-escalate, enumerated, never netted against wins.
3. §1+§2 recovery: re-baseline the description sweep over the FULL iacache
   first (state the new description count next to the old 923), then report
   recovered / unchanged / regressed per marker class against the sizing
   table above. Named canaries: `nmas2013-02-13.16.44` ≥ 32 items with the
   encore labelled (the §2 coupling proven fixed); `spindoctors2001-09-07`
   unchanged from HEAD (53 items); the ~70 floor-passing Dead rows and ~146
   non-Dead rows recover, minus the unrecognized-ordinal handful, which stay
   as today and are listed.
4. End-to-end coverage rises on BOTH corpora; matched-track deltas reported
   against the naive-fix projections (+1091 / +554) — shortfalls explained,
   not excused. **Prediction with falsification clause:** the miss buckets
   re-measured with a true-pointer classifier (see protocol) should show a
   further C→A migration on both corpora. If C does NOT fall on the shows §1
   touches, the recovered blocks are not the real setlists and §1 needs
   re-examination before 4b is designed on these numbers.
5. **Set-label gate for §1+§2:** for every description whose parse changes,
   diff aligned per-track set labels old→new. Shows may move encore-only →
   full structure (the win); **zero shows may move full → encore-only or
   lose a numbered set they had**. Enumerate every label regression;
   `gd74_windsor` byte-identical; anchored shows: anchoring output unchanged
   (jerrybase wins regardless of alignment, so any change there is a defect).
6. **Set-label gate for §3:** group corpus rows by performance (artist +
   date); for every group with ≥2 parses, compute the winner under old and
   new ranking. Enumerate every changed winner; each must be justified by
   completeness (more items, closer to track count, or multi-set where the
   old winner was implausible); **zero groups may flip to a LOWER-item-count
   winner**. Report the count of changed winners — if it exceeds ~2% of
   groups, stop and re-examine before shipping.
7. §4 re-measured in its shipped, gated form on both corpora; report
   actual vs the +96/+164 floor; zero regressions among currently-matched
   tracks (the fallback ordering makes this structural — verify it anyway).
8. D stays 0 under the true-pointer classifier on both corpora. Title
   matching remains done; nothing in this phase reopens it.

## Measurement protocol

- **Instruments:** end-to-end = re-parse from `iacache` with the checkout
  under test; full-corpus = stored `row['setlist']` (matching-layer only —
  it CANNOT see §1/§2, and a no-change there for the parser sections is
  expected, not exculpatory). The corpus stores pre-parsed setlists; any
  parser measurement from `row['setlist']` silently measures the old parser.
- **iacache is now full** (1166/1181 Dead, 874/874 non-Dead). If any fetch
  runs concurrently with a measurement, pin the file set first (snapshot the
  md_*.json list) — this review's own sweeps were nearly polluted by the
  live backfill.
- **Any miss-bucket classifier must prove itself**: reproduce `align()`'s
  matched vector exactly (0 divergences) over both corpora before its
  numbers are recorded. `phase4-review-audit/audit_window.py` (in the
  phase-3 ledger scratchpad) does this via `mirror_align`; reuse or match it.
  The phase-3 `measure2.py` classifier does not meet this bar — do not reuse
  it for bucket claims.
- Verify `llama.__file__` resolves to the checkout under test; a worktree
  needs its own venv (`score.py` hardcodes the main checkout).
- Never verify library behaviour with `llama show` (renders stored state).
- Baseline pair and preprocessing stated next to every number, including in
  commit messages that cite numbers.

## Sizing appendix (all at db02575, end-to-end, parser preprocessing, corpus rows with ≥3 tracks)

```
truncation shape           non-Dead 148/848 rows    Dead 73/1166 rows
  passing >=5 floor          146                      70
  naive upside (L=3)        +1091 matched            +554 matched
track-side prefixes         +96 floor                +164 floor
rank_parses re-rank         insurance (defect class closed by §1; gate 6 sizes it)
combined                   ≈ +1900 potential matched tracks vs phase 3's +231 e2e
```

New authoritative end-to-end HEAD baselines for 4b to be designed against
(post-backfill, full corpora): **non-Dead 0.5033 (6070/11734, 641 shows);
Dead 0.7982 (17116/20921, 1081 shows)**. Miss split at HEAD (fuzzy,
order-free membership): present-somewhere vs absent = 69.2% / 30.8% non-Dead,
52.4% / 47.6% Dead — the window/desync headroom 4b will re-derive after this
phase lands.
