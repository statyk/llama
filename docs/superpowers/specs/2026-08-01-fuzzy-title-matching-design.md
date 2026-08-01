# Fuzzy title matching in `align()` — phase 2 of the setlist-alignment work

Phase 1 (`2026-08-01-jerrybase-anchoring-design.md`) made jerrybase break
anchoring evidence-triggered and gave it fuzzy closer matching, deliberately
leaving `normalize_song` and `align()` untouched. This phase changes `align()`:
it is items 1–4 of the original change set, plus item 8, and nothing else.

## What is wrong today

`align()` matches a track to a canonical setlist item by exact equality of
normalized titles. Taper tags and canonical names disagree constantly, in four
recurring shapes:

- **`&` vs `and`.** `normalize_song`'s punctuation strip turns `&` into
  whitespace, so `Me & My Uncle` normalizes to `me my uncle` and
  `Me and My Uncle` to `me and my uncle`. Highest-volume single miss in the
  corpus: Samson And/& Delilah on 47 shows, plus Cold Rain, Around And/& Around,
  Me And/& My Uncle.
- **Dropped subtitles and parentheticals.** `Mississippi Half Step` vs
  `... Uptown Toodeloo`; `You Ain't Woman Enough` vs `... (to Take My Man)`.
- **Merged tracks.** `China Cat Sunflower > I Know You Rider` is one file
  carrying two canonical items. It can never equal either of them.
- **Single-word shorthand.** `Scarlet`, `Help`, `Slip`, `Frank`, `Estimated`,
  `Eyes`, `Sailor`, `Saint`, `Dew`, `Wheel`, `Stephen`, and closed-up spellings
  such as `Chinacat` (found live on gd1986-03-19).

An unmatched track inherits the *previous* track's set (`structure.py:248`), so
a miss is not neutral — it drags the following songs into the wrong set. That is
the exact mechanism that put gd 1973-08-01's break at track 14 instead of 11.

Separately, `jerrybase.artist_key` (line 30) strips `&` instead of folding it,
so `Dead & Company` keys as `deadcompany` against the CSV's `deadandcompany`,
and `Phil Lesh & Friends` as `philleshfriends` against `philleshandfriends`.
Both acts get zero jerrybase evidence today — confirmed live: 92 corpus rows for
Dead & Company, 0 hits.

## Scope

In: items 1–4 (the `&` fold, subphrase matching, merged-track components with a
trailing-parenthetical drop, and a gated alias table with a blocklist) and item
8 (`artist_key`'s fold). Then stop and re-score.

Out: the parser work (bare `E:` mid-line, leading track-number prefixes, junk
setlist items), and the four items phase 1 deferred (global exact-first on the
`X`/`X Jam` shape, `normalize_set_label` coverage, `/` as a segue separator,
`gather`'s span re-check on raw `norm_title`). The parser phase is designed
against *fresh* miss numbers, which is what this phase produces; folding any of
it in now would confound the re-score.

Explicitly not widening `align()`'s 4-item lookahead window. Measured: only 4
in-window title mismatches exist corpus-wide, and 73% of misses are songs absent
from the parsed setlist entirely. The window is not the lever it looks like.

## Layering: the fuzz stays at the matching layer

`songs.normalize_song` is **not edited**. `align()` compares
`fuzzy_norm_title(track.title)` against `fuzzy_norm_title(item.title)`,
re-normalizing both sides at compare time and bypassing the precomputed
`SetlistItem.normalized` (which stays on the model, unchanged, for
`blend_segues` and everything else).

This is exactly the configuration that was scored. In the external analysis
repo (`~/projects/llama-setlist-analysis/`, not part of this repo),
`score.py:19-21` applies the
`&` fold to both sides at the matching layer and imports `normalize_song`
unmodified. Folding into `normalize_song` instead would also change
`grouping.py`, `stages/vet_research.py`, `stages/brief.py` and `setlistfm.py` —
two of which generate `needs-review` holds — with no measurement behind it, and
the re-score could not tell an `align()` effect from a `brief` effect.

The cost accepted: two normalizers coexist, and `align()` normalizes item titles
per comparison rather than reading a precomputed field. On a 25-track show
against a 25-item setlist inside a 4-wide window that is roughly 100 extra
string operations.

## `align()`'s matching order

Signature becomes `align(tracks, canonical, lookahead=3, aliases=None)`. Per
track, in order — mirroring the scored implementation at `score.py:45-72`:

1. **Merged run.** Split the raw title on interior `->` / `>` / `→`. If more
   than one component survives, scan the window for an index `k` where every
   component fuzzy-equals `items[k…k+n-1]` consecutively. On a hit the track
   takes `items[k]`'s set and the pointer advances to `k + n`.
2. **Single match.** Exact equality across the whole window first, then
   subphrase across the whole window. Exact-first is load-bearing: it is what
   stops `Not Fade Away` losing to `Not Fade Away Chant`.
3. **Miss.** Inherit the previous track's set, as today.

A trailing separator yields no empty component, so a dangling `>` remains a
segue marker rather than becoming a phantom song. That behavior already exists
in `title_components` and is preserved.

### Trailing parentheticals

Each component has a trailing `(...)` stripped before normalizing, and a
component that reduces to nothing is dropped from the list.

This is a correction to an earlier assumption. Run-matching is *not*
self-guarding: `Lazy Lightning* -> (Cripe)` was observed forming a merge run
that matched `(Cripe)` to a real setlist item. Dropping the empty component
turns that title into a single-component match, and makes `Space > patch` and
`E1: New Orleans > (w/ Rick Danko & Levon Helm)` safe deliberately rather than
by accident. Seen live: `(Cripe)`, `(SBD)`, `(Tape Flip)`, `(White Strat)`,
`(w/ Rick Danko…)`.

## Vocabulary, and the family gate

`songs.GD_SHORTHAND: dict[str, str]` maps normalized shorthand to normalized
canonical titles: the single-word cases listed above plus closed-up compounds
such as `chinacat`. It is a new table, separate from `DEFAULT_ALIASES`.

Each entry's canonical target is verified present in the vendored
`set_breaks.csv` song vocabulary during implementation, and each is written in
already-normalized form (lowercase, apostrophes dropped, punctuation to spaces)
so it can be applied after `normalize_song` rather than before it. An entry
whose target does not appear in that vocabulary is dropped rather than guessed.

Single-word shorthand is only safe when we know we are inside the Dead canon.
`scarlet`, `help`, `dew`, `eyes`, `wheel`, `saint` and `stephen` are ordinary
English words; a Beatles cover titled `Help` on a punk tape must not become
`help on the way`. So the table is gated on artist.

`jerrybase.is_family_artist(artist)` returns true when `artist_key(artist)`
matches one of the distinct artist keys in the vendored `set_breaks.csv`
(verified: exactly 10, all Garcia-universe — GratefulDead, DarkStarOrchestra,
Ratdog, PhilLeshAndFriends, Jerry Garcia Band, Furthur, BobWeir,
DeadAndCompany, TheDead, TheOtherOnes), or is in a small extras set for family
acts the dataset lacks (`joerussosalmostdead`, `jrad`). Deriving the set from
the CSV means the nine tribute/side acts need no maintained list.

The predicate is built independently of `[jerrybase] enabled`. Disabling
*event evidence* must never silently disable *vocabulary*.

`gather` composes and passes down:

```python
aliases = GD_SHORTHAND if jerrybase.is_family_artist(artist) else {}
result = align(tracks, canonical, aliases=aliases)
```

Non-family shows receive an empty dict, so the table is a provable no-op on the
non-Dead corpus rather than an argued one.

`DEFAULT_ALIASES` stays global and unchanged. Its entries (`china cat`, `nfa`,
`playin`, `gdtrfb`, `st stephen`) are unambiguous strings rather than English
words, they are today's measured baseline, and moving them behind the gate
would change non-Dead behavior in a way this phase's re-score is not designed to
isolate. Recorded as a deferred cleanup.

### The jerrybase closer path gets the table unconditionally

`_closer_candidates` and `closer_contradictions` pass `GD_SHORTHAND` with no
gate. A jerrybase event only exists when the artist is in the dataset, so that
path is inherently family-gated. This is where two of the four known
non-anchoring shows were blocked by shorthand.

### `artist_key` (item 8)

`artist_key` folds `&` to `and` before stripping to alphanumerics, so
`Dead & Company` and `Phil Lesh & Friends` key onto their CSV rows. Without it
the family gate ships with two known-broken members, and both acts continue to
get no event evidence. Expect newly-anchoring shows in the re-score from this
alone; that is the fix working, not drift.

## Blocklist

`structure.py` holds a frozenset of normalized title pairs that must never
fuzzy-match, seeded with `{"its all over now", "its all over now baby blue"}`.
It is checked inside `fuzzy_title_eq` ahead of the subphrase rule, so it
protects `align()` and closer matching alike.

This is required, not optional: the subphrase rule fires on 15 corpus shows for
that pair, and they are two genuinely different songs both in the Dead
repertoire. `its all over now baby blue` ↔ `baby blue` is a correct match and
must keep working.

## Merged runs that span a set break

`AlignResult` gains `merge_conflicts: list[int]`, holding 1-based track numbers.
When a run matches but the matched items do not all carry the same `set`, the
track takes the **first** component's set and its number is recorded.
`gather` turns a non-empty list into a review flag
(`merged track 12 spans a set break`).

A merged track cannot physically straddle a set break — `China Cat > Rider` is
one continuous performance. The condition is therefore evidence that the parse
is wrong, and it is worth surfacing rather than shipping silently or discarding
by refusing the match (which would send the track back to inheriting the
previous set, the failure mode this whole phase exists to reduce).

## Acceptance criteria

Baseline to beat: **1201 tests green**; corpus **530 anchors / 0 disagreements**
(phase 1's verified figures, not the 533/385 estimates that preceded it).

1. Full suite green, no regressions.
2. gd 1973-08-01 still anchors to `[11, 20]` with both closer hold flags absent.
3. `verify_impl.py --src=<checkout>/packages/llama/src` and `score.py` re-run
   against **both** `corpus.jsonl` and `corpus-nondead.jsonl`. Unlike phase 1
   this will not be a no-op on the non-Dead corpus, since `align()` changes —
   that corpus is the anti-overfit guard and its results are read, not assumed.
4. The two-word floor is re-validated against the 516 distinct jerrybase closers
   *with* `GD_SHORTHAND` applied. Phase 1's validation (19 fuzzy-equal pairs, 18
   benign, 1 cross-song, no event carrying both) is explicitly scoped to the
   pre-table vocabulary; the table widens that surface.
5. The non-Dead corpus shows zero effect from `GD_SHORTHAND` specifically —
   the gate demonstrated, not asserted.

The `score.py` gotcha applies: it hardcodes the *main* checkout's `src` path at
line 9. Pass `--src=<worktree>/packages/llama/src` (or `LLAMA_SRC`) to
`verify_impl.py`, or the measurement silently scores main and reports a
convincing no-change.

## Consequences accepted

- Two normalizers coexist. A maintainer adding vocabulary must know that
  `DEFAULT_ALIASES` is global and `GD_SHORTHAND` is family-gated. Docstrings on
  both say so.
- The `&` fold is applied at two layers (matching titles, and `artist_key`) but
  not in `normalize_song`, so `SetlistItem.normalized` still carries the
  unfolded form. Anything comparing that field directly is unaffected by this
  phase — including `gather`'s multi-event span re-check, which stays on raw
  `norm_title` (deferred from phase 1, still deferred).
- Coverage rises across the library. Phase 1 already removed the coupling that
  made this dangerous: anchoring now runs on its own evidence, and
  `align_coverage_threshold` gates only LLM realignment and the low-confidence
  flag. Shows that previously fell below the gate and got LLM realignment may
  now clear it and keep the deterministic alignment — which is the intent.

## Not changed

`normalize_song`, `DEFAULT_ALIASES`, `SetlistItem.normalized`, the lookahead
window width, `blend_segues`, `rank_parses`, the setlist description parser, and
every stage other than `gather`.
