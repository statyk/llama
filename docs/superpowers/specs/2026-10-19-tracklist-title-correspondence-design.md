# Tracklist title correspondence: titles from the tape's own tracklist and filenames

Status: draft for review, not approved, not implemented.
Date: 2026-10-19.
Predecessors: `2026-08-30-title-correspondence-design.md` (Phase B: the
anchored `setlist-gap` rung and the operator proposal surface),
`2026-09-02-sibling-title-transfer-design.md` (Phase C: `sibling-align`), and
the two rulings they rest on — **unanchored positional correspondence is not
auto-adoption grade** (45–52% wrong, consistent by construction), and **an
alignment is validated by reproducing independent evidence, never by its own
cost structure**. This design adds a third evidence source, the one the
cascade has never read: the chosen recording's OWN per-track tracklist and
its OWN filenames.

## Kickoff

**Review mode: Fable** — one Opus reviewer, one Fable reviewer; the Fable seat
reviews the final branch too. For this run this overrides "never silently
upgrade".

**Stakes.** llama feeds an automated radio station: a track's title is spoken
by the DJ and shown to listeners. The costly outcome is a WRONG title that
ships with no review flag — it airs, and the whole title cascade ("never guess
— flag unresolved") exists to prevent exactly that; `briefing_guard` and
emcee's `script_guard` are structurally blind to it because both define truth
from the tracklist. An unresolved title that holds the show is cheap: operator
time. **Strict surfaces:** (a) any path that adopts a title without operator
confirmation; (b) never overwriting a real tape tag, a `sibling-format` title
or an operator `override`; (c) every existing consumer of the setlist parse —
`align`, `rank_parses`, jerrybase anchoring, `setlist-gap`, `blend_segues`,
the correspondence DP, vet and brief — sees byte-identical behaviour unless
this spec says otherwise in so many words, so set/segue structure on
already-good shows does not move. Everything else is proportionate.

## The problem

`billystrings-2021-12-04` (item `billystrings2021-12-04.AKG.ck63`) is held
with all 22 tracks `title_source="unresolved"`, although the information is
sitting in the item three times over. Verified against the cache on
2026-10-19:

- The description is a per-TRACK enumerated tracklist under `Set 1`/`Set 2`/
  `Encore` markers: `01 Red Daisy`, `02 Taking Water > Ice Bridges`, …,
  `13 Pyramid Country > Ride Me High > Pyramid`, `16 Paul Cauthen Intro`,
  `17 Mama Tried*`, …, `22 Long Gone`, then a footnote line `*w/Paul Cauthen`.
  Its entry numbers 01–22 are the tape's track numbers one-for-one: the FLAC
  originals carry `track: "01"` … `"22"` (the MP3 derivatives carry none, and
  `junk._track_number` reads the original's — `order_source` is
  `track-tags`), and the filenames are `01 Red Daisy.mp3` … `22 Long Gone.mp3`.
- The filenames carry the titles, with `_` and `--` standing in for `>`
  (`02 Taking Water _ Ice Bridges.mp3`, `13 Pyramid Country -- Ride Me High.mp3`).
- Neither format carries a title tag (`title_fraction` 0.0 both sides), so the
  tag rung and `sibling-format` recovery have nothing.

Why every rung declines, each checked against the code:

- `titles.resolve_titles`'s whole-tape `setlist` rung needs
  `len(canonical.items) == len(files)`. The canonical is setlist.fm (25 items;
  `rank_parses` ranks setlist.fm first, a ranking that exists for SET
  STRUCTURE per `2026-07-14-set-structure-recovery-design.md` and is out of
  scope here). The description parses to 28 items.
- `setlist._emit_items` DETECTS the enumeration (`_enumerated_prefix`) and
  then throws the number away (`_NUM_PREFIX.sub`) before `_split_songs` cuts
  each line on `>`/`,`/`;`. `SetlistItem` has no field for the line or the
  entry, so "Taking Water" and "Ice Bridges" both sitting under entry 02 is
  lost, and the footnote `*w/Paul Cauthen` is emitted as a third encore item
  (28th, set `encore`) — verified by running the parser.
- `sibling-align`: the one sibling (`…InsideOut_AKG.ck63`) is the same taper's
  other mix, equally untagged → "tape has no independent anchors" (the note
  is in the show's `structure.conflicts`). `setlist-gap` and the
  correspondence DP need anchors too and decline wholly untagged tapes by
  design.
- Nothing reads filenames. CLAUDE.md's "track filenames don't carry song
  titles" is true of `gd73-06-10d1t04` and false here.
- `align()` fell through to the LLM (`alignment: "llm"`, coverage 1.0): that
  result feeds set labels only and cost an LLM call to learn what the
  description already said.

A probe feeding cleaned filename stems into the deterministic `align()`
matched 20/21 song tracks against setlist.fm and 21/21 against the
description parse; the setlist.fm misses were "Cocaine Blues" (setlist.fm:
"Let the Cocaine Be") and the "Paul Cauthen Intro" filler.

## Evidence

Everything in this section is a **read-only probe taken 2026-10-19 over
`~/.llama/cache`** (13,324 `md_*.json` items; 13,201 with a non-empty mp3 kept
set after the real `filter_files`; 12,005 "tagged" at `title_fraction >= 0.9`,
1,025 "untagged" below 0.5). It sizes premises; it is **not** the measurement
gate (section "Measurement before banding"), which re-runs everything through
the shipped functions with hand-triage. Two caveats stand over every number:
the cache is selection-biased and not a rate over the archive (CLAUDE.md,
`docs/2026-08-07-lma-census.md`); and every "wrong" is an **upper bound**
scored by `structure.loosely_same_title` against tags that the sibling
evidence doc measured 24% wrong at disagreements.

### Prevalence — what each rung would fire on

| rung | items it fires on | of which untagged (the beneficiaries) |
| --- | --- | --- |
| numbered tracklist, entry numbers ↔ tape `track` tags bijective | 981 (7.4%) | 86 |
| enumerated description, no bijection (count or numbering differs) | 957 | — |
| enumerated with DUPLICATE numbers (per-set / per-disc restarts), unexamined | ~2,700 of 4,725 enumerated | — |
| un-numbered, song-bearing line count == kept count (crude line split) | 1,393 | 158 |
| filename stem verifies against ≥1 parsed item of the same description | 809 | **293** |

The untagged population is 1,025 items; the filename rung reaches 293 of
them, the numbered rung 86. Both are far larger than the 2 whole-tape
candidates the 2026-08-30 census found, because this is a different
population: tapes whose titles live in the item's text and names rather than
its tags.

### The numbered rung is NOT watertight on its own — the shift class survives a bijection

Scored on the 898 tagged bijective items (13,948 tracks): **467 loose-wrong
(3.3%), 36 items with ≥3 wrong**. Hand-reading the samples splits them:

- **Numbering songs, not files, with a coincident count.**
  `Cracker2012-05-05.digitalist0ne-remaster`: the taper numbered from the
  "DCA intro" (omitting the tape's `t01` pre-intro), the tape's 22nd file
  (`outtro`, 16 s) was junk-filtered, so entries 1–21 and KEPT tags 1–21
  biject while every title is off by one — 21 of 21 wrong. **Taking the
  tape's number set over ALL files of the delivered format (kept or
  excluded) declines it** (tape 1–22 ≠ description 1–21): 467 → 446 wrong,
  36 → 35 shift-like items. This is why the match is defined over the whole
  tape below.
- **A description for a different cut of the same show.**
  `DCO2016-07-09.MK22`: 17 entries, 17 files, both numbered 1–17, but the
  description merges `drums > space` into one entry while the tape splits
  them and the description ends on a song the tape lacks — a copy from
  another recording or the taper's other master. Numbers cannot see it;
  filenames here are `SET0205`-style and cannot either. **Only tape-side
  evidence or a human can.**
- **Tape numbering disagreeing with the taper's own list.**
  `ButtholeSurfers-2009-10-14`: files t24–t28 rotated against entries 24–28.
  `tsp2007-10-04`: a shift from track 13 to the end.
- **Tag-wrong, not description-wrong — placeholder tags.** `SoulCoughing…1999-05-07`
  (every tag is the item title), `nma2017-10-05` (`CD Track 01`),
  `whitedenim2013-07-04` and `JeffAustin2014-03-07` (`Track 01`),
  `tsp2018-08-28` (`20180828_SmashingPumpkins…`). `is_real_title` accepts
  these — "Track" has five letters — so they corrupt the ground truth AND,
  separately, **ship on air today via the tag rung**. Filed, not fixed here
  (see Out of scope); the harness must exclude them from ground truth.
- **Scorer misses**: `get out my life 7:35` vs `Get Out My Life Woman`
  (trailing written duration), credit parentheticals (`Sweet Emotion Tease
  (Steven Tyler)`).

Net: a number bijection catches the count-mismatch class and nothing else.
By the house standard (gap-fill's 2.4% per track; the sibling auto band's
1.9%) **bijection alone is not an automatic band**, and the agreed design's
"when the numbers match one-for-one, each track gets its entry text" is
amended below to require tape-side corroboration for the automatic band.
Uncorroborated-but-bijective tapes go to the operator as a keyed proposal —
one confirmation instead of 22 `--set-title` calls, which is still the win
the feature exists for.

### Tape-side corroboration exists, and it discriminates

Per track, two things on the tape side can agree with an entry independently
of the numbering: the **filename stem** (`loosely_same_title` on the cleaned
stem vs the entry) and a **written duration on the line** (within 5 s of the
file length). Over the bijective items:

| population | items | filename agrees on ALL tracks | on ≥1 | written durations on ≥1 line | neither |
| --- | --- | --- | --- | --- | --- |
| tagged (full-tape bijection) | 895 | 47 | 87 | 46 | 768 |
| **untagged** | 86 | **15** | **21** | 6 | **61** |

Of the 35 shift-like tagged items, **0 have filenames agreeing on all
tracks** and 5 agree on ≥1. On those 5 a bracketing rule (adopt an entry
only on a track whose filename agrees, or inside a run of non-agreeing
tracks bracketed on both sides by agreeing ones — `gap_span`'s rule, leading
edge kept, trailing edge declined) adopts **0 genuinely wrong titles**: the
Butthole Surfers and tsp2007 shifts are trailing runs and decline; the 10
"wrong" it adopts on JeffAustin are `Track NN` placeholder tags and the 4 on
gourds are credit-parenthetical scorer misses. That is a hand-read of five
items, not a rate — the harness measures it — but it is the shape the
sibling design measured for the same failure class (C+, zero wholesale
titles under both masks), reached by the same primitive.

So the automatic band is corroboration-bracketed; 61 of the 86 untagged
beneficiaries have nothing to corroborate with and route to the operator.
`billystrings-2021-12-04` has 22 of 22 filenames agreeing and adopts.

### The filename rung measures clean

Over the 809 items with ≥1 verified stem: 10,029 tracks verified; on tagged
items 5,092 scored, **16 loose-wrong (0.31%)**, and the samples are
tag-wrong (`tmp`, seven tracks tagged `Santa Fe Downs` on gd1983-09-11) or
orthography (`XYU` vs `X.Y.U`), with one genuine (`Mao Reminisces…` vs
`Border Ska` — a filename that names the wrong song, verified against a
canonical that contains both). Verification against the canonical is what
makes it clean; Dead-style `gd73-06-10d1t04` stems clean to residue, fail
`is_real_title`, and are inert.

### The whole-tape `setlist` rung is not dead at library scale

`scripts/title_source_census.py` over today's 3,441-show library: tags
61,543 | unresolved 2,384 | sibling-format 751 | **setlist 549** |
setlist-gap 32 | override 31 | sibling 21 | sibling-align 12. The rung
measured dead on the 89-show library (2026-08-30) fires on 102 shows now,
29 of them wholly `setlist`-sourced — and **27 of those 102 carry
`low-confidence structure alignment`**: every `setlist` track is excluded
from `_songish_coverage` as tautological, so a wholly `setlist` show has an
EMPTY independent set, reads coverage 0.0, spends an LLM realignment call
that reads 0.0 again, and is held. That is the measured consequence of
putting a whole-tape source in `TAUTOLOGICAL_TITLE_SOURCES`, and it decides
the tautology ruling below. It also makes the rung a positional count-match
from a canonical that may be setlist.fm — the weaker evidence class, which
the numbered rung must sit above.

## The ruling this design rests on

**A per-track correspondence is adopted automatically only when it is KEYED
(by the tape's own track numbers) and CORROBORATED on the tape side
(filename or written duration agreeing with the keyed entry, bracketing the
run as `gap_span` requires).** A key without corroboration is a proposal; a
count without a key is a proposal unless the same corroboration brackets it.
Filenames become titles only when VERIFIED against a canonical setlist item,
per track. Where neither holds, the human is the guard — exactly as Phases B
and C ruled — and the operator surface renders the keyed table.

Two corollaries carried over: gates on evidence are **per-item, never
per-tape** (a bad entry declines its track, not the tape); and the shipped
text is **the taper's**, warts and all — "we're presenting an archive tape".

## The design

### 1. The parser keeps the entry, additively

`setlist._emit_items` continues to emit exactly the song-level items it
emits today, in the same order with the same titles, sets and segue flags —
**the item list is unchanged for every consumer**. Each `SetlistItem`
additionally records:

- which post-split line it came from (an ordinal within the parse, so songs
  split from one line share it);
- when the list is enumerated and the line carried a leading number, that
  number (captured from the match `_NUM_PREFIX`/`_TRACK_PREFIX` strips,
  never re-parsed from the stripped text);
- a duration written on the line, when one is (the `_ITEM_TRAILING_DURATION`
  shape, bare or bracketed), as seconds.

Both new fields default to "absent", so every existing constructor
(`from_setlistfm`, tests, scripts) is valid unchanged, `model_copy` in
`blend_segues`/`_strip_head_banner`/`_strip_footnote_markers` carries them
through, and the parser tests — which compare `[i.title for i in items]`
lists — are untouched. An un-numbered line inside an enumerated list (the
`*w/Paul Cauthen` footnote; a stray prose line) yields items with **no
entry number**: they are items, not entries. `_split_songs`' existing
`.strip("*")` and the canonical's `_strip_footnote_markers` are not changed;
entry TEXT is cleaned by the tracklist module (below), not the parser.

Disc/track tokens (`d1t04`, `1-002`) are stripped today by `_TRACK_PREFIX`
without yielding a single tape-wide integer. **v1 records no entry number
for them** and such descriptions decline the numbered key; the harness
measures their prevalence (and that of the ~2,700 per-set/per-disc
restarting descriptions) so a `(set, n)` / `(disc, track)` key can be a
later, measured extension rather than a guess.

### 2. The tracklist module — one keyed correspondence, two keys

A new pure module, `packages/llama/src/llama/tracklist.py` (not
`correspondence.py`, which is the canonical-setlist DP; not `siblings.py`,
which is tape-against-tape). It takes loaded, already-filtered inputs and
returns per-track rows plus diagnostics; all IO stays in `gather`.

**Entries.** From the CHOSEN recording's own description parse — never
setlist.fm, never the canonical winner, never a sibling's description:
correspondence is a property of this tape, structure of the performance. An
entry is one description line that produced ≥1 item; its text is the line's
song text with the number, trailing footnote markers (`_FOOTNOTE_TAIL`'s
shape) and a trailing written duration removed, segue separators normalised
to the `" > "` convention `title_components` already parses, whitespace
collapsed, and otherwise verbatim. `Taking Water > Ice Bridges` ships as one
title on one file, as it does today for a tagged merged track.

**The tape's numbers.** ONE definition, shared with play order: the leading
integer of the file's `track` tag, the original's for a derivative
(`junk._track_number` — exposed, not reimplemented, e.g. via `filter_files`'s
`ordering`), when every file of the delivered format carries one and they
are unique; else the leading integer of the filename stem (`\d{1,3}(?!\d)`,
the same bound as `titles._TRACK_NUM_PREFIX`, no `dNtM`) under the same
completeness/uniqueness condition; when both exist and disagree on any
file, no number key. **Play-order position is not a number** — that is the
positional key below. The number set is taken over **every audio file of
the delivered format, kept or excluded**, so a junk-dropped or
operator-excluded track still accounts for its entry (the Cracker lesson);
each KEPT file must carry a number or the key declines.

**The number key.** The entry-number set equals the tape's number set
exactly, both unique. Not "count equal": entries 1–21 against a 22-file tape
decline, entries 1–28 (songs) against 22 files decline, a description with
restarting numbers declines. On a match each kept track is keyed to the
entry carrying its number.

**The position key.** An un-numbered description whose entry count equals
the tape's file count (over the whole delivered format, ≥ 5 entries — the
parser's own confidence floor) keys track *i* to entry *i*. This is the
measured failure class (positional transfer; 12% loose-wrong in the crude
probe) and never adopts without corroboration bracketing.

**Corroboration.** A keyed track is an **agreeing anchor** when any of:
(a) it already carries an independent title (`tags`, `sibling-format`,
`override`) that `loosely_same_title`s its entry — such a track is never
written, it only anchors; (b) its cleaned filename stem (section 3's
cleaning) `loosely_same_title`s its entry; (c) the entry's written duration
is within `WRITTEN_DURATION_TOL` of the file length. A keyed track whose
independent title DISAGREES with its entry is a **disagreement**, recorded in
the notes; it is not an anchor and so bounds the runs beside it. Agreement is
`loosely_same_title` — the agreement rule, not the matching rule, for the
reason the sibling design gives (orthography must not read as a wrong
alignment) — and nothing here touches `fuzzy_norm_title`,
`songs.normalize_song` or `DEFAULT_ALIASES`.

**Bands.**

| band | condition | what happens |
| --- | --- | --- |
| **auto** | key holds; the track is an agreeing anchor, or sits in a run of non-anchor keyed tracks bracketed by agreeing anchors (`structure.gap_span`'s rule reused verbatim: both flanks, the leading-edge exception kept, **no trailing-edge branch**) | each still-`unresolved` track in the run takes its entry text, stamped `tracklist` (number key) or `tracklist-line` (position key) |
| **proposal** | key holds, some runs unbracketed, or no anchors at all | nothing written; the unbracketed runs are recorded per run in notes; the operator surface renders the keyed table |
| **declined** | no key: numbers mismatch, duplicate numbers, counts differ, a kept file without a number | a note names why; nothing rendered automatically (the operator surface may still show the partial keyed rows, section 7) |

Runs decline individually, as in C+. Whether the **position key's** auto band
ships at all, and whether the **number key's** uncorroborated band may ever
be promoted, are the measurement gate's decisions (section 9), not this
document's: the default shipped is the table above.

**Hygiene, per entry.** `structure.hygienic_title` on every component of the
entry text (the single-sourced predicate the two existing silent adopters
share; `metadata_norms` passed down from gather). A failing entry declines
its track only. `Paul Cauthen Intro` passes and ships — it is what that file
holds, and `is_filler` keeps it out of coverage as today.

### 3. The filename rung

A cleaned filename stem becomes a title only when **verified against the
canonical setlist** (the `build_canonical` winner, whichever source), per
track. Cleaning reuses `titles.clean_tag_title` (identifier prefix, audio
extension, edge junk) plus the leading track number under the same recording-
level enumerated gate `clean_tag_titles` uses, and then tries a small fixed
set of separator readings — `_` as a space; `_`, `--` and ` - ` as segue
marks — because tapers use `_` both ways. A reading verifies when **every
component** `fuzzy_title_eq`s some canonical item (the existing matching
layer: `title_components` → `fuzzy_norm_title` → `fuzzy_title_eq`; no new
normalisation); the fewest-component verifying reading wins; none verifying
leaves the track unresolved. The shipped text is the filename's own spelling,
components joined `" > "`. Dead-style residue (`gd73-06-10d1t04`) cleans to
nothing `is_real_title` accepts and is inert by construction — pinned by
test on the gd73 fixture. CamelCase and concatenated stems (`CrookedHitch`,
`violaleeblues`) are out of scope: no reading splits them.

The filename rung is also the main supplier of **corroboration** to section
2 and of **anchors** to `sibling-align` and `setlist-gap` (section 4), which
is why it runs before them.

### 4. Cascade placement and plumbing

Effective order for one track, in `run_gather`:

1. `resolve_titles`: `tags` / `sibling-format` → **`tracklist` (auto band of
   the number key)** → whole-tape `setlist` → `unresolved`. The number key's
   auto-band titles enter `resolve_titles` as a filename-keyed layer exactly
   like `format_titles`, consulted after the tag layer and before the
   whole-tape rung, so **a keyed, corroborated entry pre-empts a positional
   count match from the canonical** — the stronger evidence wins where both
   fire (the 549-track census is the reason this ordering matters).
   Real tags still win: a `tracklist` title can only land where today's
   outcome is `setlist` or `unresolved`.
2. The `overrides.titles` loop — operator overrides win, unchanged.
3. **`filename`** — a pass over `unresolved` tracks, verified against the
   canonical. Runs here so its titles can anchor everything below.
4. `sibling-align` — unchanged, except that `tracklist` and `filename` join
   `siblings.INDEPENDENT_TITLE_SOURCES` (they are independent of a sibling
   tape, which is what that set means there).
5. `adopt_gap_titles` (`setlist-gap`) — unchanged; `anchor_spans` already
   treats any non-`unresolved` track as a candidate anchor, so the new
   titles anchor gaps for free. (On billystrings the number key resolves
   everything first; where only the filename rung fires, "Cocaine Blues"
   failing to verify against setlist.fm's "Let the Cocaine Be" leaves a
   count-forced bracketed single gap that `setlist-gap` fills with the
   canonical's wording — existing behaviour, unchanged, noted because it is
   the one place the taper's-text principle yields to an older rung.)
6. **`tracklist-line`** — the position key's pass over whatever is still
   `unresolved`, last, because it is the weakest key: it must not pre-empt a
   measured rung, and a merged line (two items, one file) is exactly the
   case `setlist-gap`'s count-forcing declines, so running after it costs
   nothing.
7. `align()`, jerrybase anchoring, flags — unchanged.

The number key's **proposal/declined** diagnostics are computed in the same
pass as its auto band and appended to `notes` (so `show.json` records why a
numbered description did not resolve a tape), as `_sibling_transfer` does.

### 5. `title_source` values, the tautology ruling, `matched`, flags

Three new values: **`tracklist`**, **`tracklist-line`**, **`filename`**.
`Track.title_source` is a plain `str` with an enumerating comment
(`models.py`), not a `Literal`; `ManifestTrack` carries no `title_source`;
emcee and transmitter never read it (grep-verified) — the manifest contract
is untouched. `cli._format_tracks`'s column is 14 wide ("sibling-format");
`tracklist-line` is exactly 14, so the column does not move.

**None of the three joins `structure.TAUTOLOGICAL_TITLE_SOURCES`.** The
constant encodes "text copied from the canonical by a positional mechanism
whose shift coverage was the last detector of" (`setlist-gap`, `setlist`).
These rungs differ on both halves: their text comes from the tape's own
description or filenames (cross-source against a setlist.fm or sibling
canonical; the tape's own text against a `chosen` canonical), and their
shift protection is the key plus corroboration, which coverage could not
improve on — a keyed title shifted onto the wrong file is still in setlist
order and matches exactly as well. What excluding them WOULD do is measured
above: a wholly `tracklist`-resolved show whose canonical is its own
description would read coverage 0.0 over an empty independent set, pay an
LLM realignment, and be held "low-confidence" — the 27-of-102 outcome the
`setlist` rung produces today. So `Track.matched` is `align()`'s real verdict
(against setlist.fm, a real cross-source measurement — "Cocaine Blues" reads
`?`; against the chosen description, trivially `True`), and gather appends a
**note**, not a flag, whenever the canonical source is `chosen` and any
track is `tracklist`/`tracklist-line`-sourced: *structure and titles both
come from the chosen recording's tracklist; no cross-source check was
available*. The low-confidence flag keeps its existing semantics and
threshold.

The **"unresolved track titles" hold** keeps its predicate (any `unresolved`
track). A tape the number key resolves wholesale clears it; a proposal-band
tape stays held and the hold now carries the note that a keyed proposal is
available.

### 6. Interaction with structure, jerrybase, overrides and redo

- **Structure still comes from `align()` over the canonical.** An entry-titled
  merged track aligns as a merged run (`title_components` → `_merge_run`, all
  components consecutive within the lookahead-8 window). Where the canonical
  disagrees with the taper's merge (`Pyramid Country > Ride Me High >
  Pyramid` vs setlist.fm's items), the run declines, the track falls to the
  single-title cascade, misses, and inherits the previous set — today's
  behaviour for any merged tag title, and the set label is right by
  inheritance. The entry's own set marker and trailing segue flag are NOT
  stamped onto the track: `align()` overwrites `set`/`segue` for every
  track and must keep doing so (strict surface (c)).
- **Jerrybase anchoring** reads closers against `Track.title`'s last component
  and runs unchanged; it benefits from real titles where it had filenames.
- **`--suggest-titles`, triage `[t]`**: section 7.
- **`llama redo --from gather` on shipped shows.** A `tags`/`sibling-format`/
  `override` title cannot change: `tracklist` sits below the tag layer and the
  three passes fill only `unresolved`. Two classes CAN change on re-gather
  and are stated as intended: `unresolved → tracklist|filename|tracklist-line`
  (the feature), and **`setlist → tracklist`** where a numbered, corroborated
  description now pre-empts the positional count match — the text may change
  wording (canonical/setlist.fm → taper's) and, where the positional match
  was shifted, correctness. The full-library re-gather (section 9, M2) must
  enumerate every such track; any other transition is a defect. Delivered,
  voiced shows are not re-gathered by anything but an explicit `redo`/`fix`.

### 7. The operator surface

`cli._propose_titles_for_show` gains a **tracklist arm, tried first**, before
the sibling arm and the canonical DP: when the chosen description keys to
the tape (number or position key) it renders the keyed table — track, file,
entry text, and per row which corroboration held (`fn`, `dur`, `tag`), with
unbracketed runs annotated per run exactly as the sibling arm annotates C+
declines, and a declined key (numbers mismatch) rendered as the partial
keyed rows with the mismatch named, so the operator sees what the taper
wrote next to what the tape holds. It is the most direct claim available
("file N is X", from the person who cut the files), and the human is the
guard. On confirmation the picks land in `overrides.titles` and redo from
`gather`, through the existing `_propose_and_confirm_titles` plumbing (C1
staleness guard, `--exclude` refusal, the `unresolved`-only pick filter — a
proposal never overwrites a titled track). Triage's `[t]` inherits it for
free; the `[t]` offer condition is unchanged. The sibling arm and the DP
remain the fallbacks when no key holds, unchanged.

**Invariant, as in Phase C: bracketing gates the automatic band, never the
rendering.** The 61 uncorroborated untagged tapes are the population this
surface exists for.

### 8. Fixture and capture

`scripts/capture_fixture.py` slims files to `name/source/original/format/
length/md5/title` — **it drops `track`**, and so does every fixture in
`tests/fixtures/` (0 of 15–247 files carry one, checked). No fixture today
can exercise track-tag play order or the number key. The script keeps
`track` from now on (existing fixtures are not re-captured; they are
unaffected). Capture `billystrings2021-12-04.AKG.ck63` as
`billystrings2021_metadata.json`: 22 untagged mp3s, FLAC originals with
`track`, a 22-entry numbered description with a merged entry, a filler entry,
a footnote line and a footnote-marked title — every shape this design
handles, on one real item.

### 9. Measurement before banding — the gate

A new read-only harness, `scripts/tracklist_blind_arm.py`, to the standard of
`blind_tag_gapfill.py` and `sibling_blind_arm.py`: it **imports and calls the
shipped functions** (`parse_setlist`, `filter_files`, `build_canonical`'s
pieces, `tracklist.*`, the filename rung) and writes only a driver and a
scorer. Over the cache (and `iacache` if available), for every tagged item
(`title_fraction >= 0.9`, **placeholder tags excluded** — a tag equal to the
item title, `Track NN`, the stem, or an identifier-derived string is not
ground truth), hide the tags, run each rung, score adopted titles against
the hidden tags with `loosely_same_title`, and hand-triage every wrong
adoption into {orthography, non-song boundary, tag-wrong, genuine}. Two
masks as in the sibling evidence: all tags hidden (the real untagged case:
corroboration from filenames and durations only), and a random partial mask
(SYNTH, labelled) for the tag-anchored arm. Report, per rung and per band:
items fired, tracks adopted, wrong by class, and prevalence over the
UNTAGGED population — the beneficiaries — separately. Also measure: the
whole-tape `setlist` rung on the same instrument (the baseline the number
key shadows), the disc-token and duplicate-number populations, and the
written-duration residual histogram.

**Decision point (owner), on the harness output:** for each of the three
automatic bands — number key corroborated, position key corroborated, and
filename — ship unflagged only if genuine-wrong is at or below the tag
rung's own typo baseline (M1's standard); otherwise demote that band to
proposal-only. The uncorroborated number-key band is promoted to automatic
only if its genuine-wrong class is empty after the full-tape number rule,
which the probe says it is not (DCO2016-07-09, ButtholeSurfers 2009-10-14,
tsp2007-10-04) — so the expected outcome is that it stays a proposal.

**M2 (gates everything): full-library offline re-gather** asserting that
every `tags`/`sibling-format`/`override` title is byte-identical, every
`set`/`segue`/`set_breaks` on a show with no new adoption is byte-identical,
and the complete diff is the enumerated set of `unresolved → …` and `setlist
→ tracklist` transitions, each hand-checked. Both arms stated (offline
`setlistfm=None`; key active for setlist.fm-won shows).

**M3: the six-plus-one table** — the predecessor specs' held shows plus
billystrings — rendered through the operator surface and checked by hand;
billystrings must resolve 22/22 automatically with `Taking Water > Ice
Bridges` on track 2 and `Paul Cauthen Intro` on track 16.

An in-repo evidence doc at the `2026-09-02-sibling-transfer-evidence.md`
standard records all of it; the constants cite it.

## Constants — fixed a priori, do not retune after the harness runs

- `WRITTEN_DURATION_TOL = 5.0` s — written times are `m:ss` rounded, file
  lengths are exact; set from the mechanism before any score is read, same
  class as `MIN_EXCLUSION_PENALTY`. The harness reports the residual
  histogram; if the choice is wrong it is changed at the decision point
  BEFORE banding, never after.
- `MIN_POSITION_ENTRIES = 5` — the parser's own confidence floor, reused.
- Bijection is exact set equality over the whole delivered format; the
  number regexes are the existing `_NUM_PREFIX`/`_TRACK_PREFIX` (parser side)
  and `\d{1,3}(?!\d)` (filename side, `titles._TRACK_NUM_PREFIX`'s bound).
- Agreement is `structure.loosely_same_title` (`LOOSE_TITLE_RATIO 0.80`,
  already do-not-retune); verification is `fuzzy_title_eq`.
- Bracketing is `structure.gap_span`, imported, not restated.

## Failure modes

Unchanged in shape: a wrong title propagates to manifest v3, ID3 `TIT2`, the
packaged filename, the briefing and emcee's script, with both factual guards
blind. New to this design:

- **A different-cut description with a coincident count and corroborating
  filenames** (DCO's class plus titled filenames) would pass the number key
  and the corroboration. The filenames would then also be wrong — the taper
  named the files from the same wrong list — and only a sibling tape or a
  human could see it. Accepted as the residual of the automatic band;
  sized by the harness (the probe found 0 of 35 shift-like items with all
  filenames agreeing).
- **A filename that names the wrong song of the same show** (`Mao
  Reminisces…` on a `Border Ska` file) verifies and ships — 1 of 5,092 in
  the probe, tag-corrected only. Rate measured by the harness.
- **Placeholder tags ship today** (`Track 01`, `CD Track 01`, the item title
  on every file) via the tag rung, which this design neither causes nor
  fixes; the harness excludes them from ground truth and the census of them
  is filed.
- **Taper text is taper text**: `Dear Head On The Wall`, `Sweet Emotion
  Tase`, trailing `>` on a line — shipped as written, by the wording
  principle; apparatus (numbers, markers, durations) is stripped, spelling
  is not. The operator surface shows the canonical's spelling beside it, as
  the sibling arm already does.
- **Per-set restarting numbers and disc tokens are declined, not keyed** — a
  stated v1 cost, measured for a later key.

## Testing

Parser (`test_setlist.py`): items unchanged on every existing fixture
(pinned by the existing title/set/segue list assertions); entry numbers
recorded on an enumerated list, shared by songs split from one line, absent
on an un-numbered footnote line and on a non-enumerated description; a
written duration recorded and the title unchanged.

Module (`test_tracklist.py`, pure): number key — bijection on the whole
delivered format (a junk-excluded 22nd file declines a 1–21 description: the
Cracker shape as a fixture), duplicate numbers decline, song-numbered (28 vs
22) declines, tag-vs-filename number disagreement declines; corroboration —
filename, duration and independent-title anchors each agree/disagree by
`loosely_same_title`; bracketing reuses `gap_span` (a mutation that
reimplements it must fail a named test); a trailing run never adopts; a
bracketed interior run adopts; runs decline individually; hygiene declines
one entry without sinking the tape; the shipped text keeps a segue chain and
strips number, marker and duration; position key never adopts an
unbracketed run. Filename rung: each separator reading; every component must
verify; fewest components wins; gd73-style stems are inert; CamelCase stays
unresolved.

Integration (`test_stage_gather.py`): the billystrings fixture resolves
22/22 `tracklist` with the expected strings (content assertions, not counts),
hold clears, `Track.matched` is `align()`'s real verdict, the `chosen`-canonical
note appears on an offline run; gd73 and every fully-tagged fixture are
byte-identical; a `tags`-titled track is never overwritten (mutation-pinned);
`setlist → tracklist` pre-emption on a constructed fixture; `tracklist` and
`filename` anchor `sibling-align`'s guard and `setlist-gap`; neither new
source is in `TAUTOLOGICAL_TITLE_SOURCES` (a mutation adding one must fail a
test that asserts the wholly-resolved offline show is NOT held
low-confidence and makes no LLM call).

CLI (`test_cli.py`/`test_triage.py`): the tracklist arm renders before the
sibling arm and the DP, writes `overrides.titles` on confirmation and redoes
from `gather`; declines render the partial keyed rows; picks exclude titled
tracks; `[t]` shares the path. `capture_fixture.py` keeps `track` (a test on
the slim-field set).

## Unverified premises

| premise | cheapest test |
| --- | --- |
| Tapers who number a description number the FILES, with the same numbers the tape carries | the harness's bijection/no-bijection/duplicate split over the 4,725 enumerated descriptions (probe: 981 / 957 / ~2,700 — most enumerated descriptions do NOT key in v1) |
| `track` tags on originals are the right primary number source and filename prefixes agree with them when both exist | count disagreements in the harness; probe saw `order_source="track-tags"` on 12,006 of 13,201 items |
| Written durations on lines are rare enough that filenames carry the corroboration load | probe: durations on 6 of 86 untagged bijective items vs filenames on 21 — harness confirms over the position-key population too |
| `loosely_same_title` is an adequate agreement rule for taper text vs filename stems and tags | hand-triage of the harness's disagreement sample; credit parentheticals already measured as a miss class |
| Placeholder tags are a material fraction of "tagged" ground truth | census of tags equal to `Track NN` / item title / stem across the cache (one script run) |
| The `chosen`-canonical self-alignment note, not a flag, is the right operator signal | M3's hand check of offline billystrings and two more `chosen`-won shows |
| `gap_span`'s bracketing shape transfers from canonical items to keyed entries | the harness's shift-like items under the bracketing rule (probe: 0 genuine on 5 items) |
| The cache's untagged fraction (7.8%) and the beneficiaries (86 + 293 items) say anything about the archive | nothing cheap; CLAUDE.md's standing caveat applies and is restated in the evidence doc |

## Out of scope, filed not built

- `(set, n)` and `(disc, track)` keys for restarting numbers and `dNtM`
  tokens — measured for prevalence by the harness, designed later.
- Placeholder tags passing `is_real_title` (`Track 01`, `CD Track 01`, the
  item title on every file) — a tag-rung defect that ships today; needs its
  own census and ruling.
- Inline-numbered single-line tracklists (`Set 1: 01 A, 02 B, …`) — the
  parser's `_split_songs` does not strip inner numbers; declines in v1.
- CamelCase / concatenated filename stems.
- Re-ranking `rank_parses` so a tape's own enumerated description wins
  structure — structure is the performance's; explicitly out of scope.
- Any LLM touchpoint. None is needed; none is designed.
- Widening manifest v3 to carry `title_source` (unchanged ruling).
- Using a sibling tape's duration alignment to validate a keyed description
  (the DCO class) — the right second corroborator for Dead-style-filename
  tapes; filed with the harness's count of that population.

## Decisions and open questions for the owner

1. **Departure from the agreed design, on evidence:** the number key's
   automatic band requires tape-side corroboration bracketing; bijection
   alone is a proposal. Evidence: 35 of 895 bijective tagged items are
   shift-like after the whole-tape number rule, with named genuine cases
   (DCO2016-07-09, ButtholeSurfers 2009-10-14, tsp2007-10-04); 0 of 35 have
   all filenames agreeing. Cost: 61 of 86 untagged beneficiaries route to the
   operator instead of resolving silently. **Confirm or overrule.**
2. `tracklist` pre-empting the whole-tape `setlist` rung changes wording on
   re-gather for some of the 549 `setlist`-sourced tracks (M2 enumerates
   them). Recommended; confirm.
3. The three source names (`tracklist`, `tracklist-line`, `filename`) and the
   ruling that none is tautological (with the `chosen`-canonical note).
4. Whether the position key's automatic band exists in v1 at all, or ships
   proposal-only until the harness has run. Default here: it exists, gated
   by the same bracketing, and the harness decides.
5. `WRITTEN_DURATION_TOL = 5.0` s, fixed before the harness runs.
