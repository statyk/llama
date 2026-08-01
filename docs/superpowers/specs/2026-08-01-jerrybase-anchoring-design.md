# Jerrybase break anchoring — evidence-triggered and fuzzy-matched

**Date:** 2026-08-01
**Status:** Approved design, pending implementation plan
**Phase:** 1 of the setlist-alignment change set (items 5 + 6). Items 1–4
(the `align()` fuzz set) and the description-parser work follow in later phases.

## The bug this comes from

`llama show gratefuldead-1973-08-01` splits sets after track 14 (Me & My Uncle)
instead of after track 11 (Casey Jones), and holds the show on two jerrybase
closer flags. Reproduced exactly offline. Root cause chain:

1. setlist.fm wins `rank_parses`, and its data is *correct* (set 1 = 11 songs
   ending Casey Jones).
2. `align()` matches on normalized titles; 4 of 22 tracks miss because taper tags
   differ from canonical names — `Around & Around`/`Around and Around`,
   `Me & My Uncle`/`Me and My Uncle` (`_PUNCT` deletes `&`), `Mississippi Half
   Step`/`…Uptown Toodeloo` (subtitle), `You Ain't Woman Enough`/`…(to Take My
   Man)` (parenthetical).
3. An unmatched track inherits the **previous** track's set
   (`structure.py` `align()`). Tracks 12/13/14 are exactly set 2's first three
   songs, so they get dragged into set 1.
4. Coverage lands at 0.8182 against `align_coverage_threshold` **0.8** — so
   jerrybase anchoring *and* the LLM realignment fallback were both skipped.

**The show is uniquely broken because it was just barely too good to trigger any
repair path.** That last point is what this phase fixes, and it is why this phase
goes first: the coverage gate is a trap for every later improvement too. Better
title matching (phase 2) and a cleaner description parser (phase 3) both *raise*
coverage, and would therefore switch off the very repair paths that currently
rescue the shows they help. Removing the gate defuses that coupling once, for
everything downstream.

Measured instance of the coupling: `1968-10-12` goes 0.750 → 0.833 under the
phase-2 fuzz rules, crossing the gate and disabling the jerrybase anchoring that
today gets it exactly right (its break would move 4 → 5).

## Scope

Two changes, both confined to jerrybase evidence handling:

- **Item 6 — trigger anchoring on its own evidence.** Anchoring is attempted
  whenever a single jerrybase event is in hand, and it wins whenever it
  succeeds — instead of being gated behind `coverage < align_coverage_threshold`.
- **Item 5 — match closers the way tapers actually write them.** `anchor_breaks`
  and `closer_contradictions` compare closers by raw normalized equality today.
  They gain `&`-folding, subphrase matching, merged-track component splitting,
  and a resolution rule for repeated closers.

**Explicitly out of scope for this phase**, to keep it strictly additive:

- `normalize_song` is **not** touched. Folding `&` there is item 1 and belongs to
  phase 2, because it changes `align()`'s coverage for every show at once.
- `align()` is **not** touched at all. No fuzzy matching, no component runs, no
  window change on the track-matching path.
- The hardcoded shorthand/alias table and known-distinct blocklist (item 4) and
  the trailing-parenthetical drop are phase 2. The anchoring profile below was
  measured *without* them, so this phase ships exactly what was measured.
- Item 7 (boundary-filler placement convention) is **resolved by deletion** — see
  "Filler push, dropped" below.

## The anchoring rule

Today (`jerrybase.py:anchor_breaks`): for each jerrybase set, find tracks whose
`norm_title` equals the closer's `norm_title`; require **exactly one** hit per
closer and strictly increasing positions, else give up.

The new rule keeps that shape and relaxes only the matching and the ambiguity
handling:

1. **Component-aware closer matching.** A merged track (`China Cat > Rider`,
   `GDTRFB > NFA`) closes on its *last* component, so the title is split on
   interior segue separators (`->`, `>`, `→`) and the last component is what a
   closer is compared against.
2. **`&` → `and` folding** before normalization, on both sides.
3. **Subphrase matching.** A normalized title of **2 or more words** that appears
   as a contiguous word run inside the other side matches it
   (`Mississippi Half Step` ↔ `Mississippi Half Step Uptown Toodeloo`). The
   2-word floor is deliberate: single-word shorthand is the hardcoded table's job
   in phase 2, not a general rule's.
4. **Exact-first candidates.** Within a closer's candidate list, if any candidate
   matches *exactly*, only the exact ones are considered; fuzzy candidates are
   used only when there is no exact match.
5. **Repeated closers resolve to the latest candidate before the next closer.**
   Instead of bailing on ambiguity, positions are chosen right-to-left: the last
   set's closer takes its last candidate, and each earlier set takes its latest
   candidate still strictly before the following set's chosen position. If any
   set has no candidate below its successor, anchoring fails as before.

### Filler push, dropped

An earlier exploratory version also pushed each break past trailing filler
(tuning, crowd, announcements). Measurement killed it: it accounted for **157 of
159** disagreements against today's anchoring, it is unsupported by any evidence,
and the stored show library is itself inconsistent about where boundary filler
goes (5/07 vs 5/08). It is not in this design. Item 7 needs no further decision.

### Encore preservation guard

Jerrybase frequently records only the numbered sets. Where a tape has a trailing
encore that jerrybase does not know about, anchoring would otherwise absorb it
into the final numbered set — measured on `1972-08-27`, which would lose its
break at `[17]`.

Guard: when the jerrybase event has **no** set named `encore` but the aligned
structure ends in a trailing run of tracks labelled `encore`, those tracks keep
their aligned `encore` label after anchoring. The guard only ever restores a
label alignment already produced; it never invents one.

## Measured profile (acceptance criteria)

Scored over the evaluation corpus (1181 shows, 756 carrying jerrybase evidence)
with `anchor_variants.py` in `~/projects/llama-setlist-analysis/`:

```
today  (exact, single-hit)      anchors 385/756
AGREED (no push, exact-first)   anchors 533/756   both-anchor agree 385  DISAGREE 0
  ...without exact-first        anchors 537/756   both-anchor agree 383  DISAGREE 2
exploratory (filler-push)       anchors 537/756   both-anchor agree 226  DISAGREE 159
```

As shipped, with the encore-only guard below, this becomes **530/756, both
agree 383, DISAGREE 0** — the three fewer anchors are the three errors that
guard removes.

**+148 shows newly anchor, and not one show that anchors correctly today changes
at all.** That zero is the whole argument for this phase: it is the safest
possible change profile. Exact-first costs 4 anchors to buy the last 2
disagreements (`Not Fade Away` vs `Not Fade Away Chant`) — worth it.

All four shows where `anchor_breaks` returns `None` today (1977-02-26, 1977-05-08,
1981-03-09, 1987-09-18) then anchor and land exactly on the stored breaks. Two
were blocked by shorthand, two by repeated closers (a PITB sandwich, Good Lovin'
played twice).

The non-Dead regression corpus (874 shows, 30 collections) carries **0 jerrybase
rows**, so this phase is provably a no-op there — confirmed, not assumed.

## Break changes from item 6

Removing the coverage gate means anchoring now overrides aligned breaks on shows
that previously kept them. Triage of the 214 shows whose breaks change under the
full change set:

```
~113  jerrybase anchoring succeeds   -> this phase; anchoring overrides aligned breaks
  15  filler-only shift              -> cosmetic; not applicable, push dropped
  52  no jerrybase at all            -> phase 2; aligned breaks ship
  34  has jerrybase, anchoring fails -> phase 2; aligned breaks ship
   1  dso2014-05-16                  -> NOT a jerrybase gap; see below
```

### Encore-only events, and the `dso2014-05-16` correction

The exploratory triage attributed `dso2014-05-16` to incomplete jerrybase data.
**That diagnosis was wrong.** Jerrybase records the breaks; llama discards them:
`normalize_set_label` cannot map labels like `First part`, `Second part`,
`1st Set` or `Acoustic`, so `build_index` silently truncates such an event down
to its `Encore` row alone — 66 of 7158 events (~0.9%) repo-wide.

An event with no numbered set carries no set-break information at all, so
anchoring on one labels the entire show `encore` with zero breaks. That is a
structurally invalid show, and `structure_guard` does not catch it: an
encore-only event yields `expected_set_count == 0` against `actual == 0`.

`anchor_breaks` therefore **declines any event with no numbered set**. Measured
cost over the corpus: 533 → 530 anchors, and all three removed anchors were
errors (`dso2014-05-16`, `dso2014-05-17`, `dso2004-11-13`). Two of the three
anchor under *today's* rule as well, producing an all-`encore` label set, so
this fixes a pre-existing bug rather than merely avoiding a new one — and it is
the reason the "identical where both anchor" count is 383 rather than 385.

Widening `normalize_set_label` to accept those labels is deferred to a later
phase; declining is correct regardless of whether it is widened.

Every shape among the reviewed shows was sampled and adjudicated against the
setlist's own `[set]` labels; the new rules were correct in all of them.

## Consequences accepted

- **`closer_contradictions` gets fuzzier and so will find closers it used to
  miss.** This cuts soft "closer not found" notes and can raise new hard flags
  where a closer really does sit mid-set. This is the tripwire working as
  intended. It is also run on strictly *fewer* shows than before, since gather
  skips it when `alignment == "jerrybase"` and far more shows now anchor.
- **`dso2014-05-16` is a known cosmetic regression** against the stored library,
  attributed to incomplete jerrybase data rather than to the rule.
- Anchoring winning whenever it succeeds means jerrybase is treated as
  higher-authority than description/setlist.fm alignment for *break placement
  only*. It remains, as before, never a setlist source.

## Not changed

`align_coverage_threshold` keeps its meaning and its 0.8 default for the LLM
realignment fallback and the "low-confidence structure alignment" flag. Only
anchoring stops consulting it.

## Deferred to a later phase (raised in whole-branch review, deliberately not done)

Each of these is a real improvement that would change the measured profile, and
this phase's whole value is shipping exactly what was scored. They are recorded
here so phase 2 inherits them instead of re-deriving them.

- **Exact-first is global, applied before positional resolution.** Because a
  closer's exact candidates are chosen before `_resolve_positions` runs, an
  exact hit that is positionally *invalid* can turn a resolvable anchor into a
  decline — e.g. tracks `[A, Uncle Johns Band Jam, B, C, Uncle Johns Band]`
  against closers `Uncle John's Band` / `C` declines, where fuzzy alone would
  resolve to `[1, 3]`. The `X` / `X Jam` / `X Reprise` shape is real in the
  closer vocabulary. A strictly better design returns `(index, is_exact)` and
  lets resolution prefer the latest *positionally valid* exact candidate,
  falling back to fuzzy. Needs a re-score.
- **`normalize_set_label` coverage.** It cannot map `1st Set`, `2nd set`,
  `First part`, `Second part`, `Acoustic`, `Electric`, truncating 66 of 7158
  events (~0.9%). The encore-only guard makes this safe, not correct.
- **`/` is not treated as a segue separator**, so `Sugar Magnolia/Sunshine
  Daydream` fails to split. Adding it is risky across non-Dead collections
  (`AC/DC Bag`), so it needs its own measurement. Failure mode is a decline,
  not a mis-anchor.
- **`gather.py`'s multi-event span re-check still uses raw `norm_title`** while
  everything else in the jerrybase path is now fuzzy. Pre-existing, but newly
  inconsistent: a `/eN` tape that anchors on a fuzzy closer can fail to trip the
  span check.
