# The taper's set/encore markers win (held-backlog part 1, piece 2)

Date: 2026-10-22. Branch `held-backlog-taper-markers` from `main` @ `a26c4d1` (v2.15.0).
Inputs: `docs/superpowers/2026-10-21-held-backlog-adjudication/` (handoff-design, synthesis,
bugs-found) and the classification of the 394 `set-source-precedence` verdicts in
`docs/superpowers/2026-10-22-taper-set-markers-evidence/`.

**Review mode: Opus** (Opus spec and plan reviewers, Opus final branch reviewer). Operator
choice, 2026-10-22.

**Stakes.** llama feeds an automated radio station. Set structure reaches air twice: the
briefing (and from it emcee's DJ script) says what opened the second set and what the encore
was, and the manifest's set labels group the tracks. A wrong break is spoken as fact. Strict
surfaces in this spec:

- **Clearing a hold.** A show this change un-holds ships with no human look. The harness must
  enumerate every newly cleared show and each one is hand-checked (Opus pre-screen, then the
  operator) before any apply, as in Tier 1 and piece 1.
- **Changing the structure of shows that already shipped.** Packaged, delivered and voiced shows
  with no flag can change set breaks under this rule. Re-delivering a voiced show discards its DJ
  script and audio (`llama deliver --replace-voiced`). Nothing in this spec re-processes or
  re-delivers a non-held show. The harness lists them, and what happens to them is a separate,
  operator-gated step (below).

Nothing here deletes or overwrites user data in code: the code change only alters what a
future gather computes.

## Why

The 2026-10-21 overnight adjudication judged every held show (1,063). The largest single cause
of holds was **set-source-precedence: 394 shows** where the taper wrote the set structure and
llama shipped something else, usually one unlabelled set from setlist.fm, or breaks moved or
erased by alignment or jerrybase anchoring. 375 of the 394 verdicts were a `llama fix`, 320 of
them setting the structure (`--set-breaks`/`--set-encore`).

Most of the 394 are already dealt with: **312 carry an operator structure override and are not
held; 82 remain held.** The payoff is therefore mostly future gathers, and shipped shows that
carry the same defect with no flag. Example (held): `acousticsyndicate-2005-05-29`, whose
description marks `Set 1 … / Set 2 … / encore:` while setlist.fm's single unlabelled set
shipped.

The operator's standing rule ([[llama-accuracy-philosophy]], restated 2026-10-22): **the
original archive description is ground truth unless something clearly says otherwise, and we
would rather repeat an error that comes from the tape than incorrectly correct the tape.** The
operator has not hand-cleared enough of these shows to supply counter-examples, so the evidence
steers.

### What the evidence says (classification, 394 shows)

- **282 (72%)**: an explicit taper marker on the selected recording supports *every* corrected
  break. 57 more are partial (the taper marks some boundaries, usually only the encore). 55 have
  none (the correction rests on a sibling recording's description 27, reviews 9, blank lines,
  disc splits or durations), and those are out of scope by definition.
- By where the marker sits, the 282 split:
  - **262 in a description form** (set headers 144, disc lines naming a set 67, encore-only 36,
    inline markers 14, other 1). In about 10 of these the markers are actually in the item's
    `notes` field.
  - **20 out of scope**: the marker is only in filenames (7) or in the taper's track tags (13).
    These stay fixable with `llama fix`.
- Among the 282, what lost:
  - **102: the parser does not recognise the marker form.**
    - `Disc 2 (Set 2)`, `Disc One - Set 1` (38). `_NOISE` drops every line starting
      `Disc` before set markers are considered.
    - header variants (39): `I:`/`II:`/`III:`, `1:`/`2:`, bare `I`/`II` lines, `S1`/`S2`,
      `[Set One]`, `~Set One~`, `-Set I-`, `Set 1/`, `[1] [2] [E]`, own-line `(Set 2)`.
    - encore variants (11): `ENC:`, `E.`, `E:)`, `Encores:`, `==encores==`,
      `Encore ======`, `(E)Song`, a trailing `enc`.
    - inline or parenthetical markers (8): `9. Oakland (start of Set II)`, `(set II)`,
      `(first set)`.
    - set labels in the taper's own track tags (5), out of scope.
  - **88: setlist.fm outranks the taper.** `structure.rank_parses` sorts setlist.fm first
    unconditionally, so a labelled description never wins when setlist.fm has the show. Either
    setlist.fm's single unlabelled set ships (53), or its labels differ, for example a named
    encore counted as a set (35).
  - **61: alignment** (29 deterministic, 32 the LLM fallback). The labelled parse was available
    but placing it on the tracks failed. A sample shows these are mostly other pieces' defects:
    a junk-dropped closer (piece 4), shifted MP3 tags (piece 5), an untagged tape laid out by
    position (piece 3), an encore lost behind filler.
  - **12: jerrybase anchoring** overrode the taper (the Phil Lesh & Friends one-set rows,
    `bugs-found.md` #4).
  - **19: other.**
- 18 shows carry their markers in the item's `notes` metadata field, which llama never reads.
- In 8 shows, all `partial`, the adjudicator's target differs from the taper's labels:
  - `derektrucksband-2005-01-09`, `darkstarorchestra-2007-05-08`, `thedead-2009-04-29`: the
    disputed boundary is an encore the taper did not label.
  - `gratefuldead-1970-05-15-spans` stays held by `tape spans`.
  - `deadandcompany-2018-06-16`, `gratefuldead-1981-12-31`, `stevekimockband-2003-03-11`,
    `ekoostikhookah-2009-12-31`.

  Wherever the taper owns the structure (section 4) its structure ships, and with no taper
  encore marker its last set runs to the end of the tape unless section 2's veto applies. These
  are expected disagreements with the adjudicator, not failures, and Measurement 1 scores them
  by these expectations.
- About 10 verdicts carry the adjudicator's `partial-tape` tag: `citizencope-2007-12-29`,
  `gratefuldead-1970-02-11-spans`, `campervanbeethoven-2003-01-18`, `gratefuldead-1970-06-06`,
  `soulcoughing-1998-10-25`, `gratefuldead-1981-12-31`, `derektrucksband-2004-04-15`,
  `darkstarorchestra-2008-02-17`, `darkstarorchestra-2004-04-17`, `waynehancock-2004-04-08`.
  The Measurement 2 pre-screen checks every newly cleared show against this tag.

The rule in this spec covers the 262 minus the encore-only rows and the rows whose markers are
only forms it does not recognise (bare digits, bare roman numerals, `S1`/`S2`, `E.`, `(E)`, a
trailing `enc`, inline markers; section 1). How many of those it owns is to be measured by the
gate before building (Measurement).

## Goals

1. **Recognise the taper's worded set/encore markers** in the selected recording's description,
   or in its `notes` field when the description has no explicit marker.
2. **The taper owns the whole structure or nothing.** When its text asserts two or three
   numbered sets and llama can place every boundary on the tape, exactly the taper's structure
   ships, over setlist.fm's labels, the LLM alignment and jerrybase anchoring. Otherwise the
   show is computed exactly as today, every flag included.
3. **A taper-owned show is not held because jerrybase disagrees with the taper's own text.** The
   disagreement becomes an operator note.
4. **Measure it with the replay harness** (`scripts/replay_holds.py`, as in Tier 1 and piece 1),
   including the full list of non-held shows whose structure changes.

## Non-goals

- **Guessing where a taper's break falls.** If llama cannot place every boundary from evidence
  on the tape (section 3), the taper owns nothing and the show is computed as today, holds
  included. A misplaced break would be llama's error, not the taper's. The 61 alignment
  failures are expected to shrink as pieces 3–5 land, and are not this piece's target.
- **Encore-only descriptions** (about 36 of the 262). They are computed as today and are left for
  a later piece.
- **Filenames and track tags as marker sources.** Filename set tokens (`s2t05`, where some
  tapers use `s3` for the encore and `s0` for pre-show) and set labels in track tags are not
  read in this piece. They may be added later if the shipped-show report shows they would earn
  it.
- Sibling recordings' descriptions as structure authority. They stay where they are in
  `rank_parses`.
- Treating disc boundaries, track-number restarts, blank lines or `Early Show`/`Late Show` and
  act headers (`((Hellbilly))`, `Disc Two - NRPS`, `*** New Riders ***`) as set markers. They
  are inferences or show and act labels. Multi-event dates already split at grouping.
- Re-processing or re-delivering any show. That is the operator-gated apply step.
- **Changing titles.** Titles do not change, by construction: `parse_setlist` is untouched
  (section 1). The harness verifies zero title changes, and any title change is a defect.
- The vet stage's research flags (`research asserts N sets but structure has M`, 123 of the
  394). They should clear by themselves once the structure is right. The harness shows the rest.
- The junk constants, `is_real_title`, `_TRACK_NUM_PREFIX`, `_STRUCTURE_PREFIX` and the
  `_NOISE` disc rule. Only the structure-only reader (section 1) gives a disc line that also
  names a set header meaning.

## Anti-goals (a failure even if the tests pass)

- **Non-marker text read as a marker.** Only worded forms are recognised (section 1); bare
  digits, roman numerals, `S1` and `E.` are not markers at all. Each recognised form's
  false-positive exposure is measured over the cached corpus, not just the 394
  (Measurement 5). "J" and "Untitled #12" are real titles (operator rulings), and tests pin
  that neither becomes a marker.
- **A taper break silently moved.** When the taper's markers and the tape disagree in a way
  llama cannot resolve, the taper owns nothing and the show is computed exactly as today. It is
  never given a nearby break.
- **A newly cleared show that is wrong**, found only after it airs.
- **Silent structure changes on shipped shows.** Every shipped show the harness replays, and
  every one it cannot, appears in report 3.

## Constraints

- Python, llama package only. emcee and transmitter are untouched (`structure.alignment` is
  llama-internal state in `show.json`, not manifest contract; verify no reader outside llama
  switches on its value).
- `show.json`, `notes.json` and the other persisted artifacts stay permissive. The new
  `StructureInfo.alignment` value (`"taper"`) and the new ownership field (section 4) must not
  break any reader of old show dirs, and old dirs must still read.
- Operator overrides (`overrides.set_breaks`/`encore_after`) still win over everything,
  unchanged. Shows fixed overnight with `--set-breaks` keep their override.
- Offline and deterministic. No LLM call is added. A taper-owned show must not reach the
  `align_structure` LLM fallback. This is how it stops being needs-LLM, together with
  section 7.
- The protected matchers in CLAUDE.md stay as they are (`normalize_song`, `DEFAULT_ALIASES`, the
  tail-guard constants, `align()`'s lookahead). New marker recognition lives in the
  structure-only reader and a new structure step, not in `parse_setlist` and not by loosening a
  matcher.

## The design (decided)

### 1. What counts as the taper's explicit marker

**Sources (operator ruling, 2026-10-22).** The taper's text is the selected recording's
**description**. Its **`notes`** metadata field (string or list, like `description`) is read
only when the description has no explicit marker at all. Notes lines never become canonical
setlist items, and notes go through the same reader and placement as a description.
Lineage text such as "Set 1: MSR> C> DAT", "Set 2 is seamless" or "Encore: None" places no
boundary, because its items match no track (section 3), so the taper owns nothing.

**The parser stays untouched.** `parse_setlist`'s output stays byte-identical. Markers are read
by a separate, structure-only reader of the chosen recording's description (or notes), used
only to derive and place the taper's structure. It reuses `setlist.py`'s regexes and helpers
without changing their behaviour for `parse_setlist`. It never truncates; it only reads labels.
The canonical setlist, `rank_parses`, `blend_segues`, `_corroboration`, the title rungs and
`--suggest-titles` see no change from this piece.

**Worded markers only (operator ruling, 2026-10-22).** The reader recognises:

- **numbered sets:** the word `Set` followed by 1–3, `one`–`three` or `I`–`III`, word-bounded
  (`Set Intro` and `Set IV` are not set 1), and the ordinals `First Set`/`Second Set`/
  `Third Set` and `1st`/`2nd`/`3rd Set`. Any decoration may surround the header (dashes,
  asterisks, tildes, brackets, parentheses, `=`), and it stands alone on the line or is followed
  by `:`/`-` and songs. `Disc N (Set M)`, `Disc N - Set M` and `Disc N / Set M` read as set M.
- **the encore:** a line starting (after decoration) with `Encore`, `Encores`, `ENC` or `E`,
  either followed by `:` (or `- `) and songs or standing alone on the line (`Encore`,
  `==encores==`, `Encore ======`, a bare `E`): the existing `_ENCORE_LINE` shapes plus
  `Encores`/`ENC` and decoration, and the numbered `Encore 1:`/`Encore #1:`/`1st Encore:`
  (each counts as an encore line, so the first starts the encore and later ones continue it).
  (My call: alone-on-line forms count, as `parse_setlist` already reads them; Measurement 5
  measures their collisions.)

Operator ruling 2026-10-22 (Checkpoint A): a recognised numbered header followed directly by a
duration or time annotation in parentheses, `(50:28)` or `(9:30PM - 10:46PM)`, or by `...`, is
still that header: `SET ONE (50:28)`, `Set One (9:30PM - 10:46PM):`, `Disc 1 - Set 1 (61:20):`,
`Disc 2 - Set II...`. The annotation must directly follow the header token, so prose such as
"Set I is Bobby and Jerry playing acoustic" stays excluded.

Operator ruling 2026-10-22 (Checkpoint A): the disc-and-set shapes below are admitted and read as
set M. Every one carries the word `Set` or an ordinal set (`1st Set`):

- set first: `Set 1 Disc 1`, `Set I Disc I`, `Set I Disc 1: 74:16`, `set 1 - disc 1`,
  `Set 1/Disc 1:`, `set 2 / disc 2`;
- disc first: `Disc I 1st Set`, `Disk 1: Set 1`, `Disc 1, Set 1`, `DISC 1 SET ONE`,
  `DISC 01:SET I :`, `disc 01 [Set I]`, `CD1 Set 1`, `Disc/Set1`, and the colon form
  `Disc N: Set M`.

`Disc`, `Disk` and `CD` are interchangeable in these shapes and in `Disc N (Set M)`,
`Disc N - Set M` and `Disc N / Set M`. `Set 1/2`, `(Start Set N)` and `(start of Set II)` are not
admitted: the ruling admits the disc-and-set family only.

Markers are tested on each line **after** stripping a leading track or disc prefix
(`_TRACK_PREFIX`, and the enumerated `_NUM_PREFIX` when the text is enumerated), so
`18. E: Let's Go Get Stoned` and `3. Encore: Higgins` are encore lines. (My call.)

**Inline markers** (my call, restoring what `parse_setlist` already reads): the reader applies
`setlist._INLINE_MARKER`'s split exactly as `_emit_items` does, so a mid-line `Set II:` or
`E:`/`Encore:` (`…, Sugar Magnolia, E: It's All Over Now Baby Blue`) starts a set or the encore
there.

**The reader never sees less than `parse_setlist` does** (my call). As a cross-check, the
taper owns nothing when `parse_setlist` of the same text yields an encore label, or a numbered
set label, that the reader's structure does not have (for example `set 3, disc 2`, which
`_SET_LINE` reads and the reader's header shape does not). Any mention of a set numbered 4 or
higher (`Set 4`, `Set IV`, `Set Four`, `4th Set`) anywhere in the text voids the structure, as
section 2 says; the reader recognises these for voiding only.

Not recognised, so they assert nothing: bare digits (`1:`, `[1]`), bare roman numerals (`I`,
`II:`), `S1`/`S2`, `E.`, `(E)`, a trailing `enc`, and parenthetical markers
(`(start of Set II)`, `(set II)`). `Acoustic`/`Electric`/`Early`/`Late Set` (they may
be two shows, or unnumbered), `Early Show`/`Late Show` and act headers stay non-markers, though
`parse_setlist` keeps parsing them as today. A recognised form with collision risk and tiny
yield may be dropped by Measurement 5. The builder adds no other form.

**Required negative tests**, on real cases. Unless stated otherwise each asserts that the
named line or text asserts no structure:
`giantsand-1991-01-30` and the other `N:` tracklists (`giantsand` 1989-05-10, 1996-02-03,
2001-01-08, 2001-03-04, 2004-10-15, 2005-09-02; `calexico` 1998-06-14, 2000-07-01, 2003-04-25;
`signalpath-2005-06-09`); the DSO bare-digit disc lines (`1:`, `2:`, `3:` in
`darkstarorchestra-2005-11-16`, `-2004-04-20`, `-2005-12-03`, `-2004-04-24`) are not markers
and not song items, while the same texts' worded `Set 2:`/`E:` still assert a structure
(2005-11-16 then declines at placement on its repeated `NFA`); in `umphreysmcgee-2004-04-14`
and `lotus-2005-10-15` the set-and-encore disc line asserts nothing and the later `e:` still
starts the encore (umphreysmcgee-2004-04-14 is taper-owned, identical to today);
`davidnelsonband-2007-09-07` (its `encore: Box Of Rain (set 2)` line, after track-prefix
stripping, is followed by `set 2`, a numbered marker after the encore, so the structure is
void); `moe-1997-02-21` (`Encore 1:` is recognised, and its encore boundary does not place, so
the show is computed as today); the `[1]` footnotes of `moe-2002-06-22` and
`kinggizzardandthelizardwizard-2025-08-17`; `railroadearth-2008-08-17`'s `(E) With Allie Kral`;
`antibalasmusic-2003-04-28`'s `[1]…[5]` track numbers; `E.Ville`; `B. E. Women`;
`E. Rutherford, NJ`; `I Know You Rider`; `J`; `Untitled #12`; `1:08:07`; "Set I is Bobby and
Jerry playing acoustic" (`gd1981-10-16`); `Set Intro`; `Set IV` (voids, not set 1);
`paf2007-10-12.schoeps.taraszki.barfield.87850.flac24` (`set 3, disc 2` is read by
`parse_setlist` and not by the reader's header shape, so the cross-check means the taper owns
nothing); `stringcheeseincident-2004-06-19` (`Set 4:` voids).

**Positive tests:** `charliehunter-2001-12-08` is NOT taper-owned (`Early Show`/`Late Show`
plus an encore only); `tedeschitrucksband-2019-02-16` (`18. E: …` is an encore line, so its
encore is not folded into set 2); `gratefulshred-2023-11-10` (`14 E. Playin' Reprise` is
unrecognised encore-like text, so the veto applies and the show is computed as today);
`gratefuldead-1990-03-22` (the inline `…, E: It's All Over Now Baby Blue` starts the encore, so
the taper's structure keeps it); a `Disc 2 (Set 2)` show; a notes-only show.

### 2. What the taper asserts

- **The taper asserts a structure** only when its text names a numbered structure of two or
  three sets, consecutive from set 1, with or without an encore (operator ruling,
  2026-10-22). A single numbered set, or an encore marker alone, asserts nothing.
- **A leading unlabelled block** before the first explicit set marker is set 1 only when the
  first explicit marker is set 2 (`Set II` after an unlabelled block, or `Disc 2 - Set 2` with
  no `Set 1`). When the first explicit marker is set 1, lines before it are header text and are
  ignored. (About 30 of the 282 mark set 2 and later but not set 1.)
- **Lines that assert nothing:** a header naming both a set and the encore (`Disc 3 - Set 2 +
  Encore`, `Set One & Encore`); a repeated set number (`Disc 3 (Set 2 cont.)`, `Set 2
  continued`), which is a continuation; and every encore line after the first, which is also
  continuation. The first encore marker starts the encore.
- **Lines that void the structure:** a decreasing, restarting or skipping set number, a set
  number 4 or higher, an empty set (a header followed directly by another header), or any
  numbered marker after the encore marker means the taper asserts **no** structure, and the
  show is computed as today. (My call.)
- **No encore marker** (operator ruling, 2026-10-22): the taper's last set runs to the end of
  the tape, so encore songs listed under set 2 ship in set 2, repeating the tape. This applies
  only when the taper truly wrote no encore. **Veto** (my call): the taper owns nothing, and the
  show is computed as today, when its text has no recognised encore marker but either
  - some track title on the tape matches `structure._ENCORE_MARKER` (the test `encore_lost`
    already uses), or
  - the taper's text (the description and the notes, whichever was read) carries encore-like
    words outside a recognised marker: `\bencores?\b`
    or `\benc\b` anywhere (an inline `… US Blues. Encore: Touch of Grey`, `encore break`), or a
    song line (after track-prefix stripping) starting `E.`, `E)`, `E` plus a digit, or `(E)`.
  An unrecognised encore must never become "no encore": that would fold an encore the taper
  wrote into the last set.
- Operator ruling 2026-10-22 (Checkpoint A): **keep today's encore.** When the taper's text has
  no recognised encore marker and today's (step 1) structure has an `encore` label on any track
  after the taper's last placed numbered boundary, the taper owns nothing and the show is
  computed as today. This applies in `decide_taper`, after placement, using `today_sets`. It
  only turns ownership off: the two structures are never merged.
- The shipped labels are always the taper's: 1..n, and `encore` if it marks one.

### 3. Placing the taper's structure on the tape

**The reader's output** is the ordered song items (those that are not `is_filler`), each with
its taper set label (`1`, `2`, `3`, `encore`). It is produced with `setlist.py`'s existing line
handling, as `_emit_items` does (`_NOISE`, `_TRACK_PREFIX`, the enumerated `_NUM_PREFIX`,
segue splitting), plus stripping a leading duration or timestamp (`-04:41.50-`). Bare
`\d{1,3}:?` lines (DSO disc numbers) and items that are only a timestamp (`(2:33:33)` after a
set header) are dropped, not song items. (My call.)

**Matching.** A tape track matches an item when `fuzzy_title_eq` holds for its title, or for a
title component of a merged track, with gather's family aliases. Only tracks whose
`title_source` is not in `TAUTOLOGICAL_TITLE_SOURCES` and not `unresolved` count. The same test
decides whether a title "also occurs on the other side" below.

**Placement** (my call). A boundary between taper set A and the next set B (the encore counts as
the last set) is **placed** only when all of these hold:

- exactly one tape track matches A's last song item (track *a*) and exactly one matches B's
  first song item (track *b*), and *a* < *b*;
- every track strictly between *a* and *b* is `is_filler`;
- neither *a* nor *b* is a merged track with components on both sides;
- neither A's last nor B's first song title also occurs on the other side of the boundary in
  the taper's list (`Jam`, `Drums`, `Space`, reprises).

Otherwise the boundary is unplaced, and so the taper owns nothing. This is an exact structural
test, never a score or margin threshold, and not a new fuzzy rule.

**Filler between *a* and *b*** (my call): if today's (step 1) structure splits that filler run,
the split point stays where today's puts it, with the taper's labels on each side. Otherwise the
filler goes with B, so `Set II intro`/tuning opens set 2. A taper boundary that agrees with
today's at song level therefore moves no filler.

### 4. Precedence

**The taper owns the structure** when its text asserts one (section 2) and every boundary of
that structure is placed (section 3). There is no merge of taper and fallback parts.

For each show without an operator structure override, in this order:

1. **Today's structure (step 1):** deterministic alignment of the winning canonical, then
   jerrybase anchoring, exactly as today. This is the reference for every "was …" note.
2. **The reader and placement** (sections 1–3).
3. **If the taper owns the structure**, exactly its structure ships: its numbered breaks and, if
   it marks one, its encore. The `align_structure` LLM is not called, as successful jerrybase
   anchoring skips it today. Segues and `matched` come from step 1's alignment, unchanged.
4. **Otherwise**, everything from here on is exactly today's path: the LLM branch, then every
   flag.

jerrybase anchoring therefore never moves or removes a taper boundary, and the PLF one-set rows
stop erasing tapers' set 2.

**Low-confidence flag on a taper-owned show** (my call): raised, with no LLM call, only when
today's path would have reached the LLM branch (no anchoring and step-1 coverage below
`align_coverage_threshold`) **and** the coverage of the reader's items aligned with `align()`
against the tape is also below the threshold. That coverage is recorded.

**Provenance** (my call):

- `StructureInfo` gains one permissive boolean field recording that the taper owns the structure
  (name the builder's choice, for example `taper_owned`; absent or false on old dirs). Gather
  also exposes it to its callers in-process (section 7).
- `StructureInfo.alignment` becomes `"taper"` when the taper owns the structure **and** its
  breaks differ at song level from the step-1 structure. Otherwise it keeps today's value
  (`deterministic`, `jerrybase`, `llm`).
- In that same "differs" case, an operator note records what the taper replaced
  (`set breaks from the taper's markers (was …)`, citing the step-1 breaks), following today's
  jerrybase note pattern.
- `StructureInfo` is created whenever the taper owns the structure, even when there is no
  canonical source.

### 5. Holds and notes

On a show the taper does not own, every hold and note is computed as today. On a taper-owned
show (my call: the narrowest version that still removes the PLF-style holds):

- `structure has N sets but jerrybase shows M` becomes an operator note when the taper's own set
  count differs from jerrybase's. Otherwise it is computed as today.
- **The jerrybase closer tripwire (`closer_contradictions`)** is skipped, as today, when the
  shipped numbered breaks came from jerrybase anchoring, because anchoring cannot contradict
  itself. The test is ownership plus mechanism (the taper does not own the structure and
  `alignment` is `jerrybase`), not the `alignment` string alone. On a taper-owned show it runs,
  and a hard closer flag for jerrybase set k (mapped by set number; "last numbered" means
  jerrybase's last) becomes an operator note when the taper's own last song of set k differs
  from jerrybase's closer of set k, or the taper has no set k. Otherwise it stays hard: it then
  catches llama's placement, not the taper's text.
- Today's `set breaks anchored from jerrybase (was …)` entry is dropped from `notes` and
  `conflicts` (it would reach the briefing contradicting the shipped labels), and so is
  `merge_conflicts` (the `merged track(s) … span a set break` flag), since placement already
  excludes merged tracks at taper boundaries.
- `structure_guard` runs as today. Every other flag is untouched.

**Where the notes go (my call):** operator notes (`notes.json`, via gather's `op_notes`), never
`StructureInfo.conflicts`. Conflicts reach the briefing LLM, and the briefing should state the
taper's structure plainly rather than hedge on a source we chose to overrule. This matches 5c.1.
The "was …" note goes to operator notes too; `alignment` and the ownership field record the
mechanism.

### 6. Where it lives

The builder's call, within these lines. The structure-only reader may live in `llama/setlist.py`
and reuse its regexes and helpers, without changing their behaviour for `parse_setlist`. It
never truncates. Taper-structure derivation and placement belong in a pure function beside
`structure.py`/`jerrybase.py`. `compute_gather` composes it (the harness and `reapply` call
`compute_gather`, not `run_gather`). The `notes` field is read only for the chosen recording.

### 7. Stored LLM alignments in the harness and `reapply`

Today `replay.compute_legs` marks every show whose stored `structure.alignment` is `"llm"` as
needs-LLM, before anything else, and `reapply` shares that code. The builder check counted 76 of
the 339 yes/partial shows stored `llm`, and 462 packaged or delivered shows.

The stored LLM structure was never an input to the replay. The rule exists because
deterministic re-gathers wrongly replaced LLM structures (Tier 1 spec: 15 of 84 prototype
clears, at least 4 of them wrong at a set boundary). Relaxing it is justified only where the
shipped structure is wholly the taper's, placed by section 3's exact test.

**Relaxation (my call):** the relaxation keys on exactly one gather-reported predicate, "the
taper owns the structure" (section 4's in-process field), and nothing else: never "the gather
made no LLM call", never the `alignment` string. A stored-`llm` show whose candidate is
taper-owned is replayable; a stored-`llm` show whose candidate is not taper-owned stays
needs-LLM exactly as today (Tier 1's mutant keeps holding). This changes `llama/replay.py`,
which `reapply` uses, so it is a strict surface. Tests in both directions, mutation-pinned, plus
one on section 2's veto. Every stored-`llm` show this moves is listed for the pre-screen, with
its segue changes.

**Structure-changed accounting.** Because `alignment` stays unchanged when the taper merely
agrees (section 4), `replay._structure_changed` needs no change. If the builder still finds a
flood of label-only changes, they report it; they do not change `_structure_changed`'s rule,
which is a `reapply` gate.

## Measurement and acceptance

**Gate before building** (my call). Before any build task, a read-only prototype of the reader
and placement runs over the 339 yes/partial shows (tracks from the evidence's `sort1.json`) and
reports placed, unplaced and owned, and how many owned shows match the adjudicator's target at
song level. If fewer than half of the in-scope rows the rule covers (see "Why") are owned, the
work stops and the result goes to the operator. The same prototype also runs over every library show's
selected description and stored tracks, and reports how many shipped shows would become
taper-owned with breaks or encore different from what they ship today, with a sample of each
kind (songs moved, encore folded or added, filler only). A large count of encores folded or
sets merged is a reader defect to fix before building, not a finding to report later.

Replay harness, two arms from clean trees (`main` @ `a26c4d1` as base, the branch as
candidate), `--all` so non-held shows are covered, plus a cached-corpus check for the reader:

1. **The 394.** For each show in `classified.jsonl` with `taper_explicit` `yes` or `partial`,
   compare the candidate's shipped structure to the adjudicator's target at song level. Report
   matches, misses and declines (not taper-owned, so computed as today) by `primary` form, with
   every miss listed; filler-only differences are their own class, not misses. Expected: most
   in-scope `yes` rows match, except the alignment-caused ones. Encore-only rows and rows whose
   markers are only unrecognised forms (bare digits, roman numerals, inline) keep today's
   behaviour. Filename and track-tag rows are reported apart as out of scope. The 8 known
   disagreements are scored by the expectations under "What the evidence says". Shows that
   carry an operator structure override are evaluated in an override-ignoring mode (required
   harness task): it strips only `overrides.set_breaks`/`encore_after`, keeping excludes,
   includes and titles, since the adjudicator's targets are in post-exclusion numbering. It
   runs as a script-side scratch transform, is stamped in the arm, and is never a
   `compute_legs` parameter, so it can never feed a `--from-list` apply. (My call.)
2. **Newly cleared holds.** Every show held in base and not held in candidate is listed. An
   Opus pre-screen of the list runs **before merge**, so a rule defect it finds is fixed on the
   branch. It checks every newly cleared show for completeness against the adjudicator's
   `partial-tape` tag, and checks the date of every newly cleared show on which any jerrybase flag
   became a note (a misdated tape whose description fits it loses its jerrybase holds on a
   taper-owned show, whatever else cleared with them). The operator's hand check of the list gates the **apply**, not the merge,
   as in piece 1. (My call.)
3. **Non-held shows whose structure changes**, in a new harness report (report 3):
   - "before" is the **base arm's replay**, or the stored structure where the base arm is
     needs-LLM, with the stored value alongside, so old-code drift is not attributed to this
     piece;
   - rows are tiered: songs moved between sets, filler labels only, provenance only;
   - each row gives state (packaged, delivered, voiced), before and after breaks, the marker
     that drove it, and which source it overruled. Voiced status is read read-only from the
     station root's manifest `dj_audio`, as `deliver`'s voiced check does (llama's
     `derive_state` has no voiced state);
   - a section lists shipped shows unreplayable in either arm and `slfm_miss` rows, so no
     shipped show the rule could touch is silently absent;
   - rows that need the LLM in the candidate are split by the candidate's ownership: those not
     taper-owned are provably unchanged by this piece and are counted, not listed.

   An **Opus pre-screen before merge** covers every row with songs moved and a stratified
   sample of the rest by marker form, as for report 2. (My call.) The operator reads the count
   and shape before deciding on re-processing.
4. **Nothing newly held without explanation, and zero title changes.** Any title change is a
   defect.
5. **Marker false positives.** Per recognised form, count its raw matches over every cached
   description and every cached `notes` field (`~/.llama/cache` item metadata, not only shown
   items) and hand-sample them: every hit on a family artist, plus 30 random others per form
   (all, if fewer). The drop criterion is a non-marker match that **places a boundary or
   changes ownership**; lineage text that placement neutralises does not count. A form whose
   sample shows one is dropped or narrowed before merge, never patched around.
6. Suite green, including the negative and positive tests in section 1. A mutation check (per
   [[mutation-scoring-needs-a-prediction]]) pins each load-bearing rule: the set-number rule,
   the placement exactness, jerrybase not moving a taper break, section 2's veto, the forms'
   word boundaries, and the needs-LLM relaxation in both directions.

The 99% reproduction gate fails on this library regardless of code (piece 1: 13 drift rows).
Running `compare --no-repro-gate` for this measurement is acceptable. Using it to *apply* needs
the operator's explicit call.

## Applying it (operator-gated, after merge)

Not part of the build. After merge and release:

- **Held shows:** `llama reapply --from-list` from the harness's lists. Structure-changed held
  shows need `--allow-structure-change`, which is this piece's whole point, after the hand
  check. Piece 1's apply folds in here, so that measurement re-runs from the merged tree.
- **Non-held shows:** the operator decides from report 3. The likely route is
  `llama redo <show> --from gather` (regenerates the briefing, so an LLM call per show, and
  re-downloads purged audio for delivered shows), then `llama deliver`, with
  `--replace-voiced` for voiced ones. emcee re-voicing stays deferred by the operator.

## Documented limitations

- After release, any later `fix`/`triage`/`redo --from gather` of a shipped show re-gathers under
  the new rule and may change its breaks without a listing.
- New `llama get` gathers run the rule with no hand check; the pre-merge pre-screens of reports
  2 and 3 are the check.
- Explicit single-set statements ("One Set", "no set break") are not read.
- `is_filler` is a substring test, so a real song matching the filler pattern between *a* and *b*
  can move sides.
- A `Set Break` or `Donor Rap` track between sets, or a title repeated across a boundary, leaves
  the boundary unplaced, so the show falls back to today's behaviour (section 3).
- Encore-only descriptions and the unrecognised forms (section 1) keep today's behaviour.
- On a taper-owned show, jerrybase's set-count and closer disagreements are notes, so a misdated
  tape whose description fits it is no longer held by them. Venue mismatch still holds a
  different venue, but not a same-venue multi-night run, the commonest Dead misdate. The
  report-2 pre-screen checks dates for this case.
- An encore written in a form the reader does not recognise is caught only by section 2's veto
  words; an encore the veto also misses would fold into the last set.

## Left to the builder

- Exact regexes, within the forms in section 1 and the false-positive measurement.
- The ownership field's name, where the reader's coverage is recorded, and `StructureInfo`'s
  `source`/`coverage` values when there is no canonical source.
- Note wording, the harness report's file name and format, and test layout.
- How the required harness changes (report 3, the override-ignoring mode, the section 7
  relaxation in `replay.py`) split into tasks.

## Open questions

None for the operator at this time. Rulings this spec rests on: description as ground truth
(2026-10-22); the taper's sources (2026-10-22): the description first, the `notes` field only
when the description has no explicit marker, filenames and track tags out of this piece; the
whole-structure rule (2026-10-22): the taper owns the whole structure (two or three numbered
sets, with or without an encore, every boundary placed) or nothing, worded markers only,
encore-only descriptions out of this piece, and with no encore marker the last set runs to the
end of the tape; a jerrybase disagreement on a taper-owned show is a note, and
alignment-placement failures are out of scope (2026-10-22); delivered shows are listed first and
re-processing decided after seeing them (2026-10-22); Opus review mode (2026-10-22).
