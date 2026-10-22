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
carry the same defect with no flag. Example: `gratefulshred-2023-11-10` shipped unflagged with
"Dancin' in the Streets" in set 1, while its own description lists it second under `Set 2:`.

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
  - **262 in scope**: a description form (set headers 144, disc lines naming a set 67,
    encore-only 36, inline markers 14, other 1). In about 10 of these the markers are actually
    in the item's `notes` field.
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
    disputed boundary is an encore the taper did not label, so the fallback's encore ships.
  - `gratefuldead-1970-05-15-spans` stays held by `tape spans`.
  - `deadandcompany-2018-06-16`, `gratefuldead-1981-12-31`, `stevekimockband-2003-03-11`,
    `ekoostikhookah-2009-12-31`: the taper's version ships on the boundaries it marks.

  These are expected disagreements with the adjudicator, not failures, and Measurement 1
  scores them by these expectations.
- About 10 verdicts carry the adjudicator's `partial-tape` tag: `citizencope-2007-12-29`,
  `gratefuldead-1970-02-11-spans`, `campervanbeethoven-2003-01-18`, `gratefuldead-1970-06-06`,
  `soulcoughing-1998-10-25`, `gratefuldead-1981-12-31`, `derektrucksband-2004-04-15`,
  `darkstarorchestra-2008-02-17`, `darkstarorchestra-2004-04-17`, `waynehancock-2004-04-08`.
  The Measurement 2 pre-screen checks every newly cleared show against this tag.

## Goals

1. **Recognise the taper's explicit set/encore markers** in every description form the
   evidence lists, in the selected recording's description, or in its `notes` field for a part
   (numbered sets, encore) the description says nothing about.
2. **The taper's explicit structure wins** over setlist.fm's labels, the LLM alignment and
   jerrybase anchoring, wherever llama can place the taper's boundaries on the tape.
3. **Where the taper marks only some boundaries, it wins those, and the existing machinery fills
   the rest.** Example: an encore-only description sets the encore boundary, and the set break
   still comes from setlist.fm, alignment or jerrybase.
4. **A show is not held because jerrybase disagrees with the taper's own text** on a part the
   taper owns. The disagreement becomes an operator note.
5. **Measure it with the replay harness** (`scripts/replay_holds.py`, as in Tier 1 and piece 1),
   including the full list of non-held shows whose structure changes.

## Non-goals

- **Guessing where a taper's break falls.** If llama cannot place a marked boundary on the tape
  from evidence on the tape (below), that boundary is not taper-placed and falls back to
  today's behaviour, holds included. A misplaced break would be llama's error, not the taper's.
  The 61 alignment failures are expected to shrink as pieces 3–5 land, and are not this piece's
  target.
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

- **Non-marker text read as a marker.** `E` is not a song, but `E.`, `I`, `S1` and a bare
  `1:` look like plenty of things. Every marker form is recognised only under its guard
  (section 1), and each form's false-positive exposure is measured over the cached corpus, not
  just the 394 (Measurement 5). "J" and "Untitled #12" are real titles (operator rulings), and
  tests pin that neither becomes a marker.
- **A taper break silently moved.** When the taper's markers and the tape disagree in a way
  llama cannot resolve, the show stays held exactly as today. It is never given a nearby
  break.
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
- Offline and deterministic. No LLM call is added. A show that meets the section 4 skip must
  not reach the `align_structure` LLM fallback. This is how it stops being needs-LLM, together
  with section 7.
- The protected matchers in CLAUDE.md stay as they are (`normalize_song`, `DEFAULT_ALIASES`, the
  tail-guard constants, `align()`'s lookahead). New marker recognition lives in the
  structure-only reader and a new structure step, not in `parse_setlist` and not by loosening a
  matcher.

## The design (decided)

### 1. What counts as the taper's explicit marker

**Sources (operator ruling, 2026-10-22).** The taper's text is the selected recording's
**description**. Its **`notes`** metadata field (string or list, like `description`) is a
fallback **per part**: the numbered structure is read from notes only when the description
asserts no numbered structure (no explicit numbered marker), and the encore only when the
description has no encore marker. Each part therefore has exactly one source, so there is no
rule for the two disagreeing. (Example: `railroadearth-2009-01-15` has `Set One`/`Set Two`
only in notes and an `E:` line in its description, so its numbered part comes from notes and
its encore from the description.) The per-part split is my call, refining the operator's
"notes when the description has none".

Notes lines never become canonical setlist items. A notes boundary goes through exactly the
same guards and placement test as a description boundary. Lineage text such as
"Set 1: MSR> C> DAT", "Set 2 is seamless" or "Encore: None" asserts nothing, because its items
match no track (placement needs matches on both sides, section 3).

**The parser stays untouched.** `parse_setlist`'s output stays byte-identical. Markers are read
by a separate, structure-only reader of the chosen recording's description (or notes), used
only to derive and place taper boundaries. It may reuse `setlist.py`'s regexes and helpers but
must not change their behaviour for `parse_setlist`. The canonical setlist, `rank_parses`,
`blend_segues`, `_corroboration`, the title rungs and `--suggest-titles` see no change from this
piece.

A marker is explicit when it names a set by number, by ordinal (`First Set`, `Second Set`,
`Third Set`) or by roman numeral, or names the encore. Forms to recognise are those listed under
"What the evidence says", plus the existing ones. `Acoustic Set`, `Electric Set`, `Early Set`,
`Late Set` and similar are **not** explicit for this rule (they may be two shows, or unnumbered),
though `parse_setlist` keeps parsing them as today. `Early Show`/`Late Show` and act headers
stay non-markers.

**Guards, per form** (requirements, not suggestions):

- No marker form ever acts as a truncation point. The reader does not truncate; it only reads
  labels.
- Digit forms (`1:`, `2:`, `[1]`): a header only when the text has no line of that same form
  numbered 4 or higher, and the numbers used run 1, 2 (and 3 if present). An `N:` followed by
  duration digits (`1:08:07`) is not a marker.
- Bracketed forms (`[1]`, `[E]`, `[Set One]`): only alone on the line.
- Bare roman numerals (`I`, `II`, `III`): only alone on the line, or followed only by `:` or
  `-` and then text. `I Know You Rider` is never a marker.
- `E.`: only when followed by whitespace and a capital (never `E.Ville`, `E.T.I`, `E.S.P.`).
- `(E)` and `[N]` followed by prose (a lowercase word, or `With …`), or appearing after the last
  song, are footnote legends, never markers.
- `Set I…` needs a word boundary (`Set Intro` and `Set IV` are not set 1).
- An encore form with collision risk and tiny yield may be dropped by Measurement 5. The builder
  adds no form the evidence did not list.

**Required negative tests**, on real cases, each asserting no marker or no break:
`giantsand-1991-01-30` and the other `N:` tracklists (`giantsand` 1989-05-10, 1996-02-03,
2001-01-08, 2001-03-04, 2004-10-15, 2005-09-02; `calexico` 1998-06-14, 2000-07-01, 2003-04-25;
`signalpath-2005-06-09`); the `[1]` footnotes of `moe-2002-06-22` and
`kinggizzardandthelizardwizard-2025-08-17`; `railroadearth-2008-08-17`'s `(E) With Allie Kral`;
`antibalasmusic-2003-04-28`'s `[1]…[5]` track numbers; `E.Ville`; `I Know You Rider`; `J`;
`Untitled #12`; `1:08:07`; "Set I is Bobby and Jerry playing acoustic" (`gd1981-10-16`).

### 2. What the taper asserts

- A **numbered break** is a change of explicit set number. A leading unlabelled block before the
  first explicit number counts as set 1 when the first explicit number is 2: `Set II` after an
  unlabelled block asserts the break before it, and the same holds for `Disc 2 - Set 2` with no
  `Set 1`, and for `(set II)`. (About 30 of the 282 mark set 2 and later but not set 1.)
- The taper asserts a numbered structure only if its set numbers run consecutively from 1
  (1, 2, and 3 if present) and strictly increase, with no numbered marker after its encore
  marker. A repeated label (continuation headers, `Disc 3 (Set 2 cont.)`) is not a change and
  asserts nothing. Any decreasing, restarting, skipping or post-encore number means the taper
  asserts **no** numbered structure; its encore assertion is judged on its own. (My call.)
- A lone `Set 1` header with no later numbered marker asserts no numbered break, and neither
  confirms nor denies a set 2.
- When the taper owns the numbered structure (section 4), the shipped labels are the taper's
  numbers, which are therefore always 1..n.
- An **encore boundary** is asserted by an explicit encore marker.

### 3. Placing the taper's boundaries on the tape

A boundary between taper set A and the next taper set B is **placed** after tape track *t* only
when all of these hold (my call):

- The tape has a matched track for A's **last song item** and one for B's **first song item**
  (song items are those that are not `is_filler`). Each match must be independent: its
  `title_source` is not in `TAUTOLOGICAL_TITLE_SOURCES` and not `unresolved`. With track *a*
  matching A's last song and *b* matching B's first, *a* < *b*.
- Every track strictly between *a* and *b* is filler (`is_filler`). A tautological, unresolved
  or song-like track between them leaves the boundary unplaced.
- Neither *a* nor *b* is a merged track whose components match items on both sides.
- Neither A's last song title nor B's first song title also occurs on the other side of the
  boundary in the taper's list (`Jam`, `Drums`, `Space`, reprises). Such a boundary is unplaced.

Otherwise the boundary is **unplaced** and falls back; the taper's other boundaries still count.
This is an exact structural test, never a score or margin threshold. Matching uses
`fuzzy_norm_title`, title components and gather's family aliases, as today. It is not a new
fuzzy rule.

**Filler between *a* and *b*** (my call): if today's structure puts its break inside that
filler run, those filler tracks keep today's labels. Otherwise the filler goes with the set it
introduces (B), so `Set II intro`/tuning opens set 2. This way a taper boundary that agrees with
today's at song level moves no filler labels.

The encore boundary is placed by the same test, with A the last numbered set and B the encore.

### 4. Precedence and merging

For each show without an operator structure override, in this order:

1. **Today's structure:** deterministic alignment of the winning canonical, then jerrybase
   anchoring, exactly as today. This is the reference for every "was …" note, and the
   fallback unless step 4 replaces it.
2. **Taper derivation and placement** (sections 2–3).
3. **Ownership.** The structure has two independent parts, and each is owned all-or-nothing (my
   call: the simplest rule that can never ship a half-taper, half-fallback numbered structure):
   - **Numbered breaks:** the taper owns them only when it asserts a numbered structure
     (section 2) with at least one break, and **every** numbered break it asserts is placed.
     Then exactly the taper's numbered breaks ship, with the taper's set numbers, and the
     fallback's numbered breaks are dropped. Otherwise every numbered break is the fallback's,
     exactly as now.
   - **The encore boundary:** the taper owns it when it asserts an encore and the boundary is
     placed. Then the taper's encore boundary ships. Otherwise the fallback's.
4. **The `align_structure` LLM path**, only if the skip below does not apply, evaluated exactly
   as today on the non-taper path. When it runs, its result is the fallback.
5. **The merge.** Taper-owned parts replace the fallback's. If the taper-owned part and the
   fallback part cannot combine monotonically (every numbered break before the encore
   boundary), the show is held with a new flag, `taper set markers conflict with the aligned
   structure`. This is the safe direction. (My call.)

jerrybase anchoring therefore never moves or removes a taper-owned boundary, and the PLF
one-set rows stop erasing tapers' set 2.

**The LLM skip** (my call). Every shipped boundary is taper-owned when the taper owns the
numbered breaks and either owns the encore or the show ships no encore boundary. The
`align_structure` realignment is skipped only when every shipped boundary is taper-owned **and**
no source asserts an encore the shipped structure lacks: neither an unplaced taper encore marker
nor a canonical encore item. That mirrors how successful jerrybase anchoring skips it today. A
show whose numbered breaks still come from a weak alignment (for example an encore-only
description) goes down the low-coverage path exactly as now. When the skip applies, the
`low-confidence structure alignment` flag is still raised, with no LLM call, if the coverage of
the taper's own parse against the tape is below `align_coverage_threshold`. That coverage is
recorded.

**Provenance** (my call):

- A new permissive `StructureInfo` field records which parts the taper owns (name the builder's
  choice, for example `taper_owned: list[str]` with values `numbered` and `encore`; empty or
  absent on old dirs). Gather also exposes this ownership to its callers in-process (section 7).
- `StructureInfo.alignment` keeps naming the mechanism of the numbered breaks. It becomes
  `"taper"` only when the taper owns the numbered breaks **and** they differ at song level from
  today's structure. Otherwise it keeps today's value (`deterministic`, `jerrybase`, `llm`). An
  encore-only ownership never changes `alignment`.
- In that same "differs" case, an operator note records what the taper replaced
  (`set breaks from the taper's markers (was …)`), following today's jerrybase note pattern.
- `StructureInfo` is created whenever any part is taper-owned, even when there is no canonical
  source.

### 5. Holds and notes

- `structure has N sets but jerrybase shows M` becomes an operator note only when the taper owns
  the numbered breaks **and** the taper's own numbered set count differs from jerrybase's. If the
  taper's text agrees with jerrybase's count, the flag is computed as today on the shipped
  structure. (My call.)
- **The jerrybase closer tripwire (`closer_contradictions`)**, which reports a closer that sits
  at no break and does not pair closers with breaks:
  - it is still skipped entirely when the numbered breaks came from jerrybase anchoring, as
    today, because anchoring cannot contradict itself. The test is ownership plus mechanism (the
    taper does not own the numbered breaks and `alignment` is `jerrybase`), not the `alignment`
    string alone;
  - otherwise it runs as today, but a hard closer flag becomes an operator note only when the
    taper owns the break that ends that set (for the last numbered set, the encore boundary)
    **and** the taper's own last song of that set differs from jerrybase's closer. If the
    taper's text names the same closer, the hard flag stays: it then catches llama's placement,
    not the taper's text;
  - every other closer flag stays hard. (My call: the narrowest version that still removes the
    PLF-style holds.)
- When the taper owns the numbered breaks, today's `set breaks anchored from jerrybase (was …)`
  entry is dropped (it would reach the briefing contradicting the shipped labels), and
  `merge_conflicts` (the `merged track(s) … span a set break` flag) is computed against the
  shipped breaks.
- `structure_guard` (`setlist evidence shows multiple sets but alignment found none`,
  `single-set structure for a long show`) runs as today on the merged structure. (My call.)
- The new `taper set markers conflict with the aligned structure` hold (section 4).
- Every other flag is untouched.

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

**Relaxation (my call):** a stored `llm` alignment stops making a show needs-LLM only when the
candidate's gather reports that every shipped boundary is taper-owned (the section 4 skip
condition, from gather's in-process ownership). It never keys on "the gather made no LLM call"
or on the `alignment` string. The rule stays exactly as today for every other show. This
changes `llama/replay.py`, which `reapply` uses, so it is a strict surface. Tests in both
directions, mutation-pinned: a stored-`llm` show whose candidate is all-taper is replayable; a
stored-`llm` show whose candidate is deterministic, anchored or only partly taper-owned stays
needs-LLM (Tier 1's mutant keeps holding). Every stored-`llm` show this moves is listed for the
pre-screen, with its segue changes.

**Structure-changed accounting.** Because `alignment` stays unchanged when the taper merely
agrees (section 4), `replay._structure_changed` needs no change. If the builder still finds a
flood of label-only changes, they report it; they do not change `_structure_changed`'s rule,
which is a `reapply` gate.

## Measurement and acceptance

Replay harness, two arms from clean trees (`main` @ `a26c4d1` as base, the branch as
candidate), `--all` so non-held shows are covered, plus a cached-corpus check for the reader:

1. **The 394.** For each show in `classified.jsonl` with `taper_explicit` `yes` or `partial`,
   compare the candidate's shipped breaks to the adjudicator's target on the boundaries the
   taper marks. Report matches, misses and declines (unplaced, so falling back) by `primary`
   form, with every miss listed. Expected: most in-scope `yes` rows match, except the
   alignment-caused ones; filename and track-tag rows are reported apart as out of scope. The 8
   known disagreements are scored by the expectations under "What the evidence says". Shows
   that carry an operator structure override are evaluated in an override-ignoring mode
   (required harness task): it strips only `overrides.set_breaks`/`encore_after`, keeping
   excludes, includes and titles, since the adjudicator's targets are in post-exclusion
   numbering. It runs as a script-side scratch transform, is stamped in the arm, and is never a
   `compute_legs` parameter, so it can never feed a `--from-list` apply. (My call.)
2. **Newly cleared holds.** Every show held in base and not held in candidate is listed. An
   Opus pre-screen of the list runs **before merge**, so a rule defect it finds is fixed on the
   branch. It checks every newly cleared show for completeness against the adjudicator's
   `partial-tape` tag. The operator's hand check of the list gates the **apply**, not the merge,
   as in piece 1. (My call.)
3. **Non-held shows whose structure changes**, in a new harness report (report 3):
   - "before" is the **base arm's replay**, with the stored value alongside, so old-code drift
     is not attributed to this piece;
   - rows are tiered: songs moved between sets, filler labels only, provenance only;
   - each row gives state (packaged, delivered, voiced), before and after breaks, the marker
     that drove it, and which source it overruled. Voiced status is read read-only from the
     station root's manifest `dj_audio`, as `deliver`'s voiced check does (llama's
     `derive_state` has no voiced state);
   - a section lists shipped shows unreplayable in either arm and `slfm_miss` rows, so no
     shipped show the rule could touch is silently absent;
   - stored-`llm` shipped shows that still need the LLM in the candidate are listed with
     `after: needs LLM`.

   An **Opus pre-screen before merge** covers every row with songs moved and a stratified
   sample of the rest by marker form, as for report 2. (My call.) The operator reads the count
   and shape before deciding on re-processing.
4. **Nothing newly held without explanation, and zero title changes.** Any title change is a
   defect.
5. **Marker false positives.** Per form, new and existing forms the reader uses alike, count
   its matches over every cached description and every cached `notes` field (`~/.llama/cache`
   item metadata, not only shown items) and hand-sample them. The drop criterion is **any
   non-marker text read as a marker**: a song, track number, footnote, duration, credit,
   lineage or prose. A form whose sample shows one is dropped or narrowed before merge, never
   patched around.
6. Suite green, including the negative tests in section 1. A mutation check (per
   [[mutation-scoring-needs-a-prediction]]) pins each load-bearing rule: the set-number rule,
   the placement exactness, jerrybase not moving a taper break, the conflict hold, the
   per-form guards, and the needs-LLM relaxation in both directions.

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
- A long single set whose only break is an encore boundary is not flagged, as today.
- A taper whose set boundary lands next to a title repeated across it falls back (section 3).

## Left to the builder

- Exact regexes, within the per-form guards in section 1 and the false-positive measurement.
- The ownership field's name, where the taper parse's coverage is recorded, and
  `StructureInfo`'s `source`/`coverage` values when there is no canonical source.
- Note wording, the harness report's file name and format, and test layout.
- How the required harness changes (report 3, the override-ignoring mode, the section 7
  relaxation in `replay.py`) split into tasks.

## Open questions

None for the operator at this time. Rulings this spec rests on: description as ground truth
(2026-10-22); the taper's sources (2026-10-22): the description first, the `notes` field only
when the description has no markers, filenames and track tags out of this piece; delivered shows
are listed first and re-processing decided after seeing them (2026-10-22); Opus review mode
(2026-10-22); the scope playback (taper wins where it marks, others fill the rest; disagreement
is a note; alignment-placement failures out of scope) accepted 2026-10-22.
