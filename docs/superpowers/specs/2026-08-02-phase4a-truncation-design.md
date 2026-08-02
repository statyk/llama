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

#### 1b. AMENDED 2026-08-02: the gather-side head-banner guard

Task 1 as first shipped (`98ba55d`) exposed a regression the original §1 did
not anticipate: the recovered block is sometimes a **taper banner** (band /
venue / city / date / rig lines), and §1 places it at the head of the
setlist — the one position where junk is unrecoverable, because `align()`'s
pointer starts there and only advances on a match. Measured on the common
population (shows usable under both checkouts; track construction:
`clean_tracks` = dominant extension + consecutive-dedup; baseline pair
`db02575` → `98ba55d`): Dead 14 shows worse, all 14 to zero matched;
non-Dead 40 worse, 39 to zero. **The truncation rule itself is vindicated** —
strip the banner items from `dc2022-06-18` and the recovered parse aligns
23/23 vs the old parse's 0.6190 — and independent review established the
deeper mechanism: `align()` has a cliff (a run of ≥4 unmatchable items
annihilates everything downstream, wherever it sits; 3 are free). That cliff
is pre-existing, is filed as a 4b headline, and is NOT addressed here.

**Why not a song-likeness floor:** the recovered block is usually *mixed* —
74 of 88 collapsed blocks contain ≥5 real songs below their banners — so any
refinement of the parse-time floor is one bit deciding a which-lines
question: keep (align 0.0) or drop (lose the songs). Rejected. `align`
hardening is rejected for this task (4b scope; and `resolve_titles` sits
upstream and is poisoned by the same items). The fix point is **gather**,
which holds the one thing the parser never sees: this show's own metadata.
That turns "is this line a song?" (open) into "is this literally this show's
venue, city or date?" (closed).

**Design: widen `_drop_artist_items` into a head-banner strip** at the same
hoisted call site (before `resolve_titles`, per phase 3's ruling 14/15 — the
`len(items) == len(tracks)` sibling gate then sees cleaned counts, the same
coupling that motivated the hoist). Head-span only — a song legitimately
colliding with the venue or city name survives mid-setlist; only the artist
drop stays global (as shipped). No gazetteer anywhere: the place vocabulary
is this show's metadata; the only fixed lists are rig/lineage chatter (the
parser's own `_NOISE` vocabulary, widened) and the closed 50-state postal
codes (matched uppercase-only, whole-item).

Semantics, with every constant carrying its rationale:

1. **Stage 1 — metadata span.** Within the first **K=10** items (bounds the
   blast radius of any false positive), find the LAST item exactly matching
   (normalized) the show's metadata: artist; venue/city/state from candidate
   metadata, item `coverage`, and **every jerrybase event on the date**
   (**RATIFIED DEVIATION 2026-08-02** — this originally read "the resolved
   jerrybase event". A multi-event date leaves `event is None` while the
   banner still names the building, so the resolved event is unavailable in
   exactly the case the guard is needed. Accepted cost, stated: using every
   event on the date widens the place vocabulary, so a song titled like
   *another* event's venue could match. Bounded by the K=10 head span and the
   majority gate; no gazetteer is introduced) — each split
   on `,`/`@`, plus leading-article-stripped and leading-digit-stripped
   variants (the parser's own enumerated gate strips `40` off
   `40 Watt Club` before gather sees it); and an enumerated set of date
   renderings of the show date (month-name/abbrev × day-ordinal × year ×
   weekday × slash/dash numeric forms — the list in the measurement harness
   is the reference). Strip items 0..p — but ONLY if metadata items form a
   **majority** of that span: a lone coincidental match (a song titled like
   the city) must not eat the real songs before it. Rationale for
   strip-to-last rather than a strict leading run: banners do not interleave
   songs, and the strict run measured 29 residual zero-shows because it
   stops at the first unrecognized fragment.
2. **Stage 2 — chatter run.** From the new head, trim items matching the
   rig/lineage lexicon (`location:`/`source`/`transfer`/`tagging` prefixes;
   `resampl*`, `dither*`, `wavelab`, `izotope`, mic/gear vocabulary, `mics`,
   `xlr`, `foh/fob/dfc`, urls, `N ft`/`N khz`/`N bit` shapes, digit+quote
   heights, `row N`, model-number shapes) or the state-code list, allowing a
   **gap of ≤2** unrecognized items when chatter resumes immediately after —
   banner tails carry arbitrary fragments (`din`, `110`) between
   recognizable lines, and the gap bound caps the worst false-positive cost
   at 2 items.
3. Then the existing global artist drop, unchanged.

**Measured hazards that are now design constraints (do not relearn them):**
- `fades?` as a chatter token matches the word *Fade*: it stripped
  `Not Fade Away` and `West L.A. Fade Away` heads. Excluded. Any token
  proposed for the lexicon must be checked against real titles first.
- Bare `@`/`~`/`#` match trailing **annotation markers** Dead tapers put on
  titles (`Peggy-O @`, `Raise The Roof #`). Anchor positionally
  (`@ <digits>`, leading `~`) — never bare.
- **Greedy strip + broad lexicon is the wrong combination**: putting the
  chatter lexicon inside stage 1's strip-to-last predicate cost −10/−9/−8
  real songs per show (toad1996-09-18, joshritter2015-05-29,
  damienrice2015-04-14). Broad vocabulary belongs only in the
  gap-bounded run.

**Measured result (v7, the profile the implementation must reproduce or
beat; full tables and iteration history in the measurement record kept with
the phase-4 scratchpad):**

```
BEFORE(db02575) -> AFTER(98ba55d)+guard, common population
Dead      1080 shows  0.7990 -> 0.8777   +1468   98 better  1 worse  1 to-zero
non-Dead   636 shows  0.5056 -> 0.8508   +3933  245 better  5 worse  2 to-zero
guard cost (AFTER -> AFTER+guard): Dead 0 worse; non-Dead 3 worse (−7 tracks)
```

Enumerated residuals, accepted. **CORRECTED 2026-08-02 — two class labels
here were false, and the error was systematic: the −N figures are MATCHED
counts, and two of them had been read as TRACK counts, which made two shows
look like tiny tapes that could be waved through. Executed track counts are
given below.** They fall into three distinct classes and the spec must not
blur them:

- **Residual Task-1 damage the guard does not reach** (already zero on the
  unguarded tree — the baseline pair, not the magnitude, is what identifies
  this class): `del2026-05-24` (−1; **23 clean tracks, 21 songish — NOT a
  single-track tape**); `Ween2008-07-09` (−5, free-prose banner tail beyond
  any closed lexicon). File against 4b. Do **not** describe these as "the
  guard's residual".
- **The guard behaving correctly on a tape with no songs:** `RuthieFoster2016-09-03`
  (−3; **13 clean tracks — NOT a three-track support-set tape**). Every one
  of its track titles is the literal banner
  `NN - Ruthie Foster, Strawberry Music Festival, Tuolumne CA, 03-SEPT-2016`,
  so its 3 baseline matches were banner-track ↔ banner-item. **Zero is the
  right answer**; restoring those matches would ship a wrong title into the
  manifest and briefing instead of flagging for review. Any future variant
  that "retires" this show must classify each restored match as real-song vs
  phantom before it counts as a win.
- **Partial-tape class, out of reach of any head-strip:** `rad2008-06-22`
  (−7, recovered set-1 block over a set-2-only tape; resolved by 4b's resync).
- **Genuine losses to the stage-2 lexicon, now FIXED** (see the stage-1
  evidence requirement below): `bts2008-10-21` (−2, `Liar`);
  `ween2001-07-28` (−2, `buckingham green` — a real Ween song). These were
  the visible tip of an ungated open-vocabulary path: measured over both
  corpora, 480 shows had items stripped, **15 stripped with zero metadata
  hits**, and 3 of those stripped an item matching a real track.

Six shows, −20 tracks, against +5401 across both corpora. Any implementation
whose residual list differs must enumerate and explain the difference, not
net it off.

#### 1c. AMENDED 2026-08-02: the probe must be structurally non-truncating

The original §1 asserted the recursive probe "cannot itself truncate, since
the block contains no markers by construction." **False.** The probe re-runs
the full preprocessing (`html.unescape`, tag stripping), so escaped markup
inside the block can manufacture a marker that truncates the probe's own
input — a reviewer built a case losing 4 real songs, and the same shape can
land five junk items at the head (one past the cliff). Corpus incidence is
0, so it is latent, not benign. The root cause is general and belongs in the
code comment: **the probe is a proxy, and not a faithful one — it asks what
`parse_setlist` would make of the block in isolation, and the block is never
parsed in isolation.** (`setlist.py:267-268` currently asserts the
opposite; correct it.)

Fix shape (structural, not conditional): extract the item-emission loop into
a helper that operates on **already-preprocessed lines** and has **no
truncation step**, used by both the main parse and the probe; the probe
calls it on `raw_lines[:fm]` directly. No re-preprocessing, no recursive
`parse_setlist`, no truncation path to guard against. Replacing "the block
has no markers" with "no markers after unescaping" would be the same bet at
one remove — rejected.

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

- **No lookahead/window change of any kind, and no `align()` hardening**
  (4b). The sweep evidence and design candidates are recorded in the
  phase-4 proposal; 4b's spec is written against post-4a numbers.
  **Filed for 4b as its likely headline, measured this phase:** `align()`'s
  pointer advances only on a match, so a run of ≥4 unmatchable items is an
  absorbing barrier — coverage after a junk run at the head reads 1.0 / 1.0
  / 1.0 / 0.0 as the run grows 1→4, and a 4-junk run at index 0/5/10 scores
  0.00/0.25/0.50. Three junk items are free; the fourth annihilates
  everything downstream, wherever the run sits. This is pre-existing at
  `ad7a05e`, it is the exact mechanism by which desync destroys a show, and
  it makes the window question sharper than the lookahead sweep alone did.
  The §1b guard narrows how often parses feed it; only 4b removes it.
- No set-1-first truncation change (§1, measured, header-dominated).
- No credit-title widening (the 175 still-emitted credit-shaped titles), no
  `_NOISE` format-chatter widening, no `_NEVER_EQUAL` space-collapse keying
  (latent, not live), no Space synthesis — all per the standing phase-3
  deferrals, none invalidated by anything measured here.
- No trailing-decoration stripping (ruling 21 stands; the `('-','1')`
  residual remains pinned by test).

## Acceptance criteria (REVISED 2026-08-02 — read the note in gate 0 first)

Baseline to beat: **1261 passed / 7 deselected** at `db02575`; anchoring
**560/756, 0 disagreements**; end-to-end coverage **0.5033 non-Dead / 0.7982
Dead**; full-corpus (stored-setlist) coverage 0.4734 non-Dead / 0.7765 Dead.
Every reported number states its baseline pair, instrument, **level (parse
items vs aligned tracks)**, normalization function, preprocessing, and —
for anything derived from track lists — the **Track construction** (two
honest harnesses this phase read 53 vs 88 zero-shows from the same defect
because they built track lists differently).

0. **STANDING GATE for every remaining phase-4 task — per-show alignment
   regression on the common population.** After every task, both corpora:
   per-show aligned-matched delta over shows usable under BOTH the task's
   before and after. **No show may drop to zero matched UNENUMERATED.** Any
   show that does must be named, its mechanism diagnosed, and its acceptance
   ruled by the owner — never netted against wins, never averaged away.
   **A show that LEAVES THE POPULATION by falling below the item floor counts
   as a to-zero event and must be enumerated as one** (added 2026-08-02).
   Dropping out of the population is a *result*, not an exemption from
   reporting. This clause exists because seven shows had their entire setlist
   wiped by the head-banner guard and every one was filed as "dropped from
   population" rather than "worse" or "to-zero" — `nmas2013-02-13.16.44` went
   **24/28 matched → 0**, a single loss larger than every counted loss in the
   gate-2a headline combined, and no gate in this suite would have surfaced it.
   The separate-reporting rule for population changes was invented to be
   honest about them; it became the perfect hiding place for the worst
   outcome. **The general lesson, now four for four: every metric acquires a
   blind spot exactly where its own definition draws a boundary** — items vs
   songs, parse-level vs alignment-level, count vs identity, and in-population
   vs out-of-population. When adding a gate, ask what its boundary excuses.
   (**Reworded 2026-08-02.** This gate first read "zero tolerance", which was
   unachievable: §1b's own accepted-residual list admits three shows, so the
   gate contradicted the spec it sits in. An unachievable gate is worse than
   a loose one because it trains evasion — and the gate had already done its
   real job, which is to force an escalation instead of a netting. What is
   forbidden is a *silent* collapse, not a collapse.) Shows merely worse are enumerated
   with magnitudes. Population changes (newly-qualifying shows,
   dropped-from-population shows) are reported **separately** from
   common-population deltas and never averaged into a headline. This gate
   exists because the original gate 2 **passed** while 53 shows fell to zero
   coverage: no song left the parse; the alignment collapsed. A parse-level
   gate cannot see an alignment-level failure. Both levels are required
   from here on.
1. Full suite green. Anchoring unchanged or better, **0 disagreements**.
2. **Songs lost = 0 at the parse level**, per description, over the full
   iacache sweep (now 2052 usable descriptions, not 923 — re-baseline the
   sweep first and state both counts; 43 iacache entries carry no
   description field). The unit is SONGS, not items (ruling 17). This gate
   is **necessary but not sufficient** — it is blind to alignment collapse
   by construction; gate 0 is the other half.
2a. **The head-banner guard (§1b) reproduces or beats the v7 profile:**
   Dead ≤1 worse / ≤1 to-zero, non-Dead ≤5 worse / ≤2 to-zero on the common
   population vs `db02575`, with net matched ≥ +1400 Dead / +3900 non-Dead;
   guard cost vs the unguarded tree: 0 worse Dead, ≤3 worse non-Dead. Every
   residual show named, with its class (residual-Task-1-damage /
   correct-on-a-songless-tape / partial-tape / free-prose tail — the four
   classes enumerated in §1b, **not** "tiny tape", which was a misreading of
   matched counts as track counts). A residual list that differs from §1b's is explained
   item by item.
2b. **§1c verified structurally:** the probe path contains no truncation
   step and no re-preprocessing (assert by construction/inspection, plus the
   reviewer's escaped-markup case as a test).
   **CORRECTED 2026-08-02 — the original wording asked for something false.**
   It required the escaped case to "parse identically with and without the
   escape". `&lt;br&gt;` and `<br>` are **different documents**: a literal
   `<br>` genuinely *is* a line break, converted by top-level preprocessing
   *before* unescaping, so the two inputs differ in line structure before the
   probe is ever reached. On the reviewer's own fixture the literal form also
   falls below the recovery floor and therefore truncates correctly by §1.
   The two assertions that are well defined, and which replace it:
   1. the escaped case no longer loses the four head songs (mutation-verified);
   2. on a fixture where **both** sides clear the floor, both parses are pinned
      exactly and **neither truncates** — every song above the marker survives
      on both, the only difference being debris local to the escape.
3. §1+§2 recovery: re-baseline the description sweep over the FULL iacache
   first (state the new description count next to the old 923), then report
   recovered / unchanged / regressed per marker class against the sizing
   table above. Named canaries: `nmas2013-02-13.16.44` ≥ 32 items with the
   encore labelled (the §2 coupling proven fixed); `spindoctors2001-09-07`
   unchanged from HEAD (53 items); the ~70 floor-passing Dead rows and ~146
   non-Dead rows recover, minus the unrecognized-ordinal handful, which stay
   as today and are listed.
4. End-to-end coverage rises on BOTH corpora. The original naive-fix
   projections (+1091 / +554) are superseded by gate 2a's guarded profile
   (+1468 Dead / +3933 non-Dead on the common population) — measure against
   that; shortfalls explained, not excused. **Prediction with falsification clause:** the miss buckets
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

**AMENDED 2026-08-02:** the naive projections above were made before the
banner regression was found; the operative figures are §1b's guarded
profile — **+1468 Dead / +3933 non-Dead matched on the common population**
(the guard recovers alignment on shows the naive projection scored at the
parse level only, which is why the guarded numbers exceed the naive ones).
The measurement record with the full iteration history (v1–v7, including the
three designs that failed and why) sits with the phase-4 scratchpad
(`phase4/RESULTS.md`, `dump.py`, `compare.py`), preserved alongside the
phase-3 ledger's audit directory.

New authoritative end-to-end HEAD baselines for 4b to be designed against
(post-backfill, full corpora): **non-Dead 0.5033 (6070/11734, 641 shows);
Dead 0.7982 (17116/20921, 1081 shows)**. Miss split at HEAD (fuzzy,
order-free membership): present-somewhere vs absent = 69.2% / 30.8% non-Dead,
52.4% / 47.6% Dead — the window/desync headroom 4b will re-derive after this
phase lands.
