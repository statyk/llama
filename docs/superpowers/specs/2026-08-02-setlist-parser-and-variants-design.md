# Setlist parser, non-songs, and title variants — phase 3

Phase 1 made jerrybase anchoring evidence-triggered. Phase 2 fixed title
*matching* and measured its own completion: the in-window mismatch bucket (D)
went to **zero on both corpora**, so no further matching ambition — edit
distance, phonetic, LLM fallback — is justified. What remains is upstream: the
setlist we parse is polluted and incomplete, and a handful of same-song-two-names
cases that no general rule can reach.

Every number below was measured against shipped phase-2 code
(`102ef2e`) over `corpus.jsonl` (1181 rows) and `corpus-nondead.jsonl` (874).

## Where the misses actually are

```
                      Dead (1079 usable)      non-Dead (637 usable)
C absent from setlist   2696  56.3%             2509  39.4%
A ahead of window       1971  41.1%             3817  59.9%
B behind pointer         125   2.6%               43   0.7%
D in-window mismatch        0   0.0%                0   0.0%
```

A is inflated by cascade — once the two-pointer desyncs, every later miss in
that show counts as A — so its size is not evidence the lookahead window is too
narrow. **The window is not widened in this phase.** The cascade's cause is
upstream: junk items inflate the setlist until the pointer falls behind.

## Scope

Five changes, in dependency order. Each is measured separately before the next
is designed.

### 1. Non-song recognition

Per the project owner's ruling (2026-08-01), two axes must not be collapsed:

- **Is it a song for setlist reconciliation and set-break placement?**
- **Does it make the final on-air cut?** — a separate, show-by-show human
  decision, already served by `overrides.exclude` / `llama fix --exclude`.

**Drums, Space and Feedback are songs.** They segue into and out of adjacent
songs and sit mid-second-set from roughly 1979 on; they must never be treated as
filler. `_FILLER` correctly omits them today, and a regression test will pin
that so nobody "tidies" them in later. `Drumz` with a z is the same thing.

**Intro, Outro, Chat, Talk, Banter, Tuning, Stage announcements and Encore
Break are non-songs** for reconciliation purposes, always. `_FILLER` covers
tuning/repairs/announce/applause/crowd/banter/soundcheck/equipment but misses
the intro/outro/chat/talk and encore-break class — 60 and 55 misses respectively
on the Dead corpus, 77 + 21 + 15 + 12 on the non-Dead one.

### 2. Parser: stop emitting junk as setlist items

Measured directly from a synonym sweep, where these appeared as high-frequency
"pairs" precisely because they are items no track can ever match:

```
39 shows  'comment'                34 shows  'jerry garcia guitar'
22 shows  'bob weir guitar'        ~90 rows  'del mccoury band'
non-Dead: 'los lobos', 'built to spill', 'justin townes earle', 'spin doctors'
19 + 21   '01 intro'   <- leading track-number prefix
```

Four junk classes to reject:

- **Personnel/lineup credits** — `Jerry Garcia - guitar`, `Bob Weir - guitar`.
- **Band/artist names** as items — `Del McCoury Band`, `Los Lobos`.
- **Leading track numbers** — `01 intro`, `1.Sugaree`, `01....Song`, `207. Space >`,
  `d2t01 - Drums`. Note `_TRACK_PREFIX` already exists for the `d\d+t\d+` shape;
  it is not applied to parsed setlist items.
- **Bare durations and disc markers** — `(13:33)`, `01:50`, `Disc #2`.

This is the largest lever on the A cascade, and it also recovers Space on
post-1995 shows for free (see §5).

### 3. Bare `E:` mid-line

`setlist.py:22` `_ENCORE_LINE` uses `e\d?` — digit **optional** — so a bare
`E:` at line start is handled. `setlist.py:26-29` `_INLINE_MARKER`'s lookahead
uses `e\d` — digit **mandatory** — so a bare mid-line `E:` never splits. A
description reading `... Sugar Magnolia; E: Goin' Down the Road` therefore
leaves the encore songs in set 2 with `E: ` glued to the title.

(There is no `_SET_SPLIT` symbol. An earlier note named one; it never existed.)

Phase 2 left a characterization test pinning today's wrong behavior, commented
as such and naming `_INLINE_MARKER` as the fix site. **That test's set-label
assertion is expected to change in this phase** — that is the signal it worked.

Measured incidence: `E: Brokedown Palace` 18 shows, `E: Johnny B. Goode` 11,
`E: Casey Jones` 7, `E: Black Muddy River` 7, and more.

### 4. Title variants

Three classes, from a corpus-wide sweep that ranked candidate pairs by how many
*distinct shows* they recur in.

**Spacing — a rule, not a table.** All of these are identical once spaces are
ignored:

```
29 shows  'turn on your lovelight'  <-> 'turn on your love light'
18 + 18   'cc rider'                <-> 'c c rider'
 8 shows  'west la fadeaway'        <-> 'west l a fadeaway'
```

A space-insensitive comparison is added as a **fallback after** exact and
subphrase matching, never before. It must be validated against the 517 distinct
jerrybase closers exactly as the two-word floor was in phases 1 and 2: any pair
it newly equates must be inspected, and any cross-song pair recorded in
`_NEVER_EQUAL`.

**Spelling variants — a table.** Family-gated alongside `GD_SHORTHAND`:

```
22 shows  'touch of grey'                     <-> 'touch of gray'
15 shows  'mississippi half step uptown toodeloo' <-> '... toodleloo'
10 shows  'drumz'                             <-> 'drums'
 8 shows  'throwin stones'                    <-> 'throwing stones'
```

**True synonyms — the same table.** One pair recurs corpus-wide:

```
21 shows  'man smart woman smarter'  <-> 'women are smarter'
```

Neither is a subphrase of the other, so no general rule can ever connect them.
This is the only full-name synonym the sweep found above threshold; the table is
not speculative padding, and entries are added only on measured recurrence.

### 5. `Jam` items and `Space` tracks

Setlists frequently write `Jam` where the tape says `Space` — 45 shows, the
highest-frequency pair in the sweep. Per the owner's ruling:

> Space is always a jam, but a jam is not always space. Space basically implies
> a jam without the drummers (Drums being the inverse — just the drummers), so
> the lines get fuzzy.

The rule is therefore **directional and conditioned**: a track *called* Space,
**immediately preceded by a Drums track**, may match an otherwise-unclaimed
`Jam` item. Never the reverse — a `Jam` track does not match a `Space` item, and
a Space track with no preceding Drums does not either. The track's own title is
the evidence that licenses the match.

## Space's absence, and what this phase does NOT do

Rows whose tape has a Space track but whose parsed setlist has no Space item:
**218**, of which 209 are 1979 or later — matching the owner's account that the
Drums/Space pairing became a regular feature around 1979. Only 12 rows pre-1979
have a Space track at all.

A 30-show scrape of the source descriptions found:

```
22/30  description lists Drums, never Space   -> genuine source gap
 6/30  description DOES list Space            -> our parser dropped it
 2/30  mentions neither
```

Every one of the six parser drops has a cause already in scope: leading track
numbers (`7.Drums>` / `8.Space>`, `207. Space >`), `d2t01 - ` disc prefixes, and
`Space Jam` versus bare `Space`. **So the post-1995 Space cases are fixed by §2,
not by new work.**

**Synthesising a missing Space item is deliberately NOT in this phase.** The
bracket-guard design was worked out (Space immediately after Drums, bracketing
songs consecutive in the setlist, bounded intervening material — 101 shows
strict, ~122 with a one-track gap allowance) and it is recorded here so it is
not re-derived. But §2 and §5 both attack the same 218 rows from other
directions, and the honest order is to fix those first and re-measure. Deciding
to invent setlist entries against numbers that three other changes are about to
move would be exactly the mistake this project has avoided twice.

One case from that analysis is worth keeping as a warning: `gd1987-04-07`'s
"gap" is 17 items — the entire show unmatched, a total parse desync, not
intervening material. Any future synthesis guard must reject it by construction.

## Acceptance criteria

Baseline to beat: **1227 tests green**; anchoring **534/756, 0 disagreements**;
`align()` coverage **0.7598** (Dead) and **0.4653** (non-Dead).

1. Full suite green; anchoring unchanged or better, still 0 disagreements.
2. Coverage improves on **both** corpora. The non-Dead corpus is the
   anti-overfit guard and its results are read, not assumed — in phase 2 it
   improved *more* than the Dead corpus, and a phase-3 change that helps only
   Dead tapes needs explaining.
3. The C/A/B/D buckets re-measured on both corpora. **D must remain 0.** A
   should fall as junk items stop inflating the setlist; if it does not, the
   cascade theory is wrong and the parser work needs re-examining before
   anything else is built on it.
4. The space-insensitive comparison validated against all 517 jerrybase closers,
   with any cross-song pair added to `_NEVER_EQUAL` and a test.
5. `GD_SHORTHAND`'s family gate still a provable no-op off-family, and the new
   variant table gated identically.
6. A test pins that `Drums`, `Drumz`, `Space` and `Feedback` are **not** filler.

Measurement uses `verify_impl.py --src=<checkout>/packages/llama/src` and the
corpus scripts in `~/projects/llama-setlist-analysis/`. Verify `llama.__file__`
resolves to the checkout under test before trusting any number: `score.py`
hardcodes the main checkout's path, and a worktree needs its own venv.

Do not verify library-visible behavior with `llama show` — it renders stored
state and never re-runs `gather`, so it cannot detect a code change. Verify
in-process or drive a redo in a throwaway workspace.

## Measured results (phase 3)

Measured at `da88db0` against `673c357`. **1261 passed / 7 deselected** (baseline
1227, +34). 25 commits, no new dependencies. Whole-branch review: ready to
merge, zero Critical.

### Instrument, and its limits — read this before the numbers

Two instruments, because neither covers everything:

- **Full-corpus (stored setlists).** Uses each corpus row's `setlist` field,
  which was parsed at corpus-build time. It therefore reflects only the
  **matching-layer** changes (Tasks 1, 6, 7, 8) — the parser tasks are
  invisible to it. Covers all 1181 Dead / 874 non-Dead rows.
- **End-to-end (live re-parse).** Re-parses the cached archive.org description
  with the checkout under test, then aligns. This is the real delta. But
  `iacache` covers **874/874 non-Dead rows (100%) and only 39/1181 Dead rows
  (3%)**, so the end-to-end figure is authoritative for non-Dead and merely
  indicative for Dead.

The first instrument reproduces the phase-2 baselines to within rounding
(0.7592 vs 0.7598 recorded Dead; 0.4655 vs 0.4653 non-Dead), which is what
validates it.

### Anchoring — improved, gate held

```
Dead:      anchors 385/756 (old rule) -> 560/756      DISAGREE: 0   (383 both-anchor)
non-Dead:  0/0 — no jerrybase rows, provably a no-op
```
Phase 2 left this at 534. Nothing that anchored correctly changed.

### Coverage — improved on both corpora, by different mechanisms

```
full-corpus (matching layer only)
  Dead      0.7592 -> 0.7765     matched 16538/21334 -> 16649/20945
  non-Dead  0.4655 -> 0.4734     matched  5839/12215 ->  5702/11742

end-to-end (live re-parse)
  non-Dead  0.4655 -> 0.5033     matched  5839/12215 ->  6070/11734
  Dead(39)  0.8206 -> 0.8834     matched   622/761   ->   670/753
```

Note the mechanism differs. Under the full-corpus instrument non-Dead `matched`
**falls** (5839 -> 5702) and coverage rises only because the denominator shrinks
faster — Task 1 correctly reclassifies ~473 tracks as non-songs, some of which
were previously matching. Under the end-to-end instrument, which sees the parser
work, non-Dead `matched` genuinely **rises** by 231. Both are real; quoting only
the first would understate the work and only the second would overstate it.

### Miss buckets — THE CASCADE THEORY IS FALSIFIED

End-to-end, non-Dead (the only corpus this instrument covers at scale):

```
              baseline        phase 3
C absent       4107 (64.4%)   2213 (39.1%)    -46%
A ahead        2248 (35.3%)   3436 (60.7%)    +53%   <-- ROSE
B behind         16            12
D in-window       5             3
total misses   6376           5664            -11%
```

The plan predicted A would **fall** as junk items stopped inflating the setlist,
and said plainly that if it did not, the cascade theory was wrong and should be
stated rather than worked around. **A rose by 53%.**

This is not a regression — total misses fell 11% and matched rose by 231. What
happened is a **migration, not an elimination**: the parser now emits setlist
items it previously dropped, so songs move out of "absent from the setlist" (C)
and into "present, but further ahead than the lookahead window can reach" (A).
Fixing the parser converts C into A.

**Consequence for phase 4, and it inverts the standing guidance.** The rule
"do not widen the 4-item window" was premised on A being cascade-inflated by
junk items and on D being 0. D is still ~0 (see below), but A is no longer
inflated — it is now genuinely "the item exists and we cannot reach it," and it
is the **dominant residual at 61% of all misses**. The next lever is the
two-pointer desync, not more parser work. The still-unfixed 149-description
truncation defect will convert yet more C into A when it lands, reinforcing this.

### D stayed ~0, with an honest caveat

D is 5 -> 3 (non-Dead) and 0 -> 1 (Dead, 39-row subset). The recorded baseline
says D = 0 on both. The discrepancy is instrument, not regression: coverage comes
from the shipped `align()`, but bucket classification uses this script's own
two-pointer, which cannot exactly reproduce `align()`'s internal advance. Either
way D is <=0.2% of misses and did not materially move. **Title matching remains
done; do not reopen it.**

### Space gap

Dead rows with a Space track, live re-parse (29 rows — 3% instrument coverage,
so indicative only): Space item present 1 -> 5, gap 28 -> 24. The parser tasks do
recover some Space items. The sample is far too small to retire the deferred
synthesis question.

### Closer validation

Task 6: **18 fuzzy-equal pairs** over the jerrybase closers, 2 new vs phase 2's
16 (`and we bid you good night | goodnight`, `turn on your love light |
lovelight`) — both one song, two spellings. Task 7 re-run after the table grew:
**18, unchanged**, run as a diff not a fresh count. **No `_NEVER_EQUAL`
additions.** Independently verified: **0 of the 18 pairs co-occur in any of 7055
jerrybase events.**

Closer count reads **516**, not the 517 quoted earlier in this document: the new
`women are smarter -> man smart woman smarter` synonym collapses one duplicate
closer into its canonical form. The table working, not a lost row.

### Deferred, with sizing — the largest defect found this phase

**149 of 923 cached descriptions have an encore marker as `first_marker` with
non-noise lines above it; in 145 the discarded block parses to >=10 items on its
own.** Roughly 5x the bug phase 3 fixed. It is **pre-existing** — present in both
the before and after above, so it does not distort this delta. A pre-built,
pre-measured `dash-tolerance-FULL.patch` is preserved with the ledger and applies
cleanly; it is the coupled second half of the leading-dash tolerance and must land
**with** this fix, never before it (alone it costs 26 real songs on
`nmas2013-02-13.16.44`).

Also deferred: 175 still-emitted credit-shaped titles (a scope limit of the
plan's mandated regex, not a regression); keying `_NEVER_EQUAL` on space-collapsed
forms (verified **latent, not live** — the one blocklisted pair differs by an
appended phrase, not spacing); and `rank_parses` ordering confidence above
multi-set and item count, which is the amplifier that turns a parse defect into a
shipped-structure defect.
