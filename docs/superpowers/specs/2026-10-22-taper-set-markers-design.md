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
erased by alignment or jerrybase anchoring. 375 of the 394 verdicts were a plain
`llama fix --set-breaks … --set-encore …`. The same defect ships unflagged on shows no tripwire
caught.

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
    - set labels in the taper's own track tags (5): `Set 2 intro`, `SET 2 - intro`,
      `E: Tighten Up`, `Encore: Mulche's Odyssey`, `Set 1 Spinna`.
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
- 18 shows carry their markers in the item's `notes` metadata field, which llama never reads.
- In 8 shows the adjudicator overrode the taper's own labels with a sibling's or jerrybase's
  (`deadandcompany-2018-06-16`, `derektrucksband-2005-01-09`,
  `gratefuldead-1970-05-15-spans`, `darkstarorchestra-2007-05-08`, `gratefuldead-1981-12-31`,
  `stevekimockband-2003-03-11`, `thedead-2009-04-29`, `ekoostikhookah-2009-12-31`). Under this
  rule the taper's version ships. These are expected disagreements with the adjudicator, not
  failures.

## Goals

1. **Recognise the taper's explicit set/encore markers** in every form the evidence lists: in
   the selected recording's description, its `notes` metadata field, its filenames and its own
   track tags.
2. **The taper's explicit structure wins** over setlist.fm's labels, the LLM alignment and
   jerrybase anchoring, wherever llama can place the taper's boundaries on the tape.
3. **Where the taper marks only some boundaries, it wins those, and the existing machinery fills
   the rest.** Example: an encore-only description sets the encore boundary, and the set break
   still comes from setlist.fm, alignment or jerrybase.
4. **A show whose structure comes from the taper is not held because another source
   disagrees.** The disagreement becomes an operator note.
5. **Measure it with the replay harness** (`scripts/replay_holds.py`, as in Tier 1 and piece 1),
   including the full list of non-held shows whose structure changes.

## Non-goals

- **Guessing where a taper's break falls.** If llama cannot place a marked boundary on the tape
  from evidence on the tape (below), that boundary is not taper-placed and falls back to
  today's behaviour, holds included. A misplaced break would be llama's error, not the taper's.
  The 61 alignment failures are expected to shrink as pieces 3–5 land, and are not this piece's
  target.
- Sibling recordings' descriptions as structure authority. They stay where they are in
  `rank_parses`.
- Treating disc boundaries, track-number restarts, blank lines or `Early Show`/`Late Show` and
  act headers (`((Hellbilly))`, `Disc Two - NRPS`, `*** New Riders ***`) as set markers. They
  are inferences or show and act labels. Multi-event dates already split at grouping.
- Re-processing or re-delivering any show. That is the operator-gated apply step.
- Changing titles. This piece moves set labels only. The canonical setlist's titles and order, and every
  title rung, must come out unchanged except where a parser change is unavoidable (a disc-header
  line that today is dropped could now be read as a header). Any title change the harness
  shows must be explained.
- The vet stage's research flags (`research asserts N sets but structure has M`, 123 of the
  394). They should clear by themselves once the structure is right. The harness shows the rest.
- The junk constants, `is_real_title`, `_TRACK_NUM_PREFIX`, `_STRUCTURE_PREFIX` and the
  `_NOISE` disc rule's purpose: dropping disc lines as songs stays. Only a disc line that
  *also* names a set gains header meaning.

## Anti-goals (a failure even if the tests pass)

- **A real song title read as a marker.** `E` is not a song, but `E.`, `I`, `S1` and a bare
  `1:` look like plenty of things. Every new marker form must be recognised only in header
  shape (line start, alone on a line or followed by songs, in a description that otherwise
  reads as a setlist). Each form's false-positive exposure must be measured over the cached
  corpus, not just the 394 (see Measurement). "J" and "Untitled #12" are real titles (operator
  rulings), and tests should pin that neither becomes a marker.
- **A taper break silently moved.** When the taper's markers and the tape disagree in a way
  llama cannot resolve, the show stays held exactly as today. It is never given a nearby
  break.
- **A newly cleared show that is wrong**, found only after it airs.
- **Silent structure changes on shipped shows.** Every one must appear in the harness's list.

## Constraints

- Python, llama package only. emcee and transmitter are untouched (`structure.alignment` is
  llama-internal state in `show.json`, not manifest contract; verify no reader outside llama
  switches on its value).
- `show.json`, `notes.json` and the other persisted artifacts stay permissive. A new
  `StructureInfo.alignment` value (my call: `"taper"`) must not break any reader of old show
  dirs, and old dirs must still read.
- Operator overrides (`overrides.set_breaks`/`encore_after`) still win over everything,
  unchanged. Shows fixed overnight with `--set-breaks` keep their override.
- Offline and deterministic. No LLM call is added. A show whose every boundary is taper-owned
  (section 4.5) must not reach the `align_structure` LLM fallback. This is how it stops being
  needs-LLM, together with section 7.
- The protected matchers in CLAUDE.md stay as they are (`normalize_song`, `DEFAULT_ALIASES`, the
  tail-guard constants, `align()`'s lookahead). New marker recognition lives in the parser and
  in a new structure step, not by loosening a matcher.

## The design (decided)

### 1. What counts as the taper's explicit marker

Text written for **this** recording, in one of four places:

1. its **description**;
2. its **`notes`** metadata field (string or list, like `description`). This is read only for
   structure. Its lines never become canonical setlist items, because notes carry lineage and
   commentary;
3. its **filenames**: a set token in every kept track's filename (`set1t03`, `s2t05`,
   `SET01_TK08`, `…set2t08.mp3`). Disc tokens (`d1t01`) are not set tokens;
4. its **own track tags**: a title that names a set or the encore in header shape
   (`Set 2 intro`, `SET 2 - intro`, `E: Tighten Up`, `Encore: …`, `Set 1 Spinna`).

A marker is explicit when it names a set by number, ordinal or roman numeral, or names the
encore. Forms to recognise are those listed under "What the evidence says", plus the existing
ones. `Early Set`/`Late Set` and `Acoustic Set:`/`Electric Set:` already parse as labelled sets
(`_LABELED_SET_LINE`) and keep doing so. `Early Show`/`Late Show` stay unrecognised.

### 2. What the taper asserts

- A **numbered break** is asserted at each explicit numbered-set marker that has taper items
  before it. `Set II` after an unlabelled block asserts the break before it, and the block is
  set I. The same holds for `Disc 2 - Set 2` with no `Set 1`, and for `(set II)`/`(set III)`.
  The parser's default label `"1"` for unmarked items asserts nothing by itself. A lone `Set 1`
  header with no later numbered marker asserts no numbered break, and neither confirms nor
  denies a set 2. (Builder check: about 30 of the 282 mark set 2 and later but not set 1.)
- **Set numbers.** When the taper owns the numbered structure (section 4), the shipped labels
  are the taper's numbers. A tape whose list starts at the taper's `Set 2` (a partial tape)
  ships set `2`, because that is what the tape says. (My call.)
- An **encore boundary** is asserted by an explicit encore marker.
- Filenames assert numbered breaks where the set token changes, and only when every kept track
  carries a token and the tokens never decrease. Filenames never assert an encore.
- A track-tag label asserts the boundary at that track: the labelled track opens the named set
  or the encore.
- If two of the taper's own sources disagree (for example the description's set 2 starts one
  track later than the filenames' set 2), that boundary is **not** asserted, and it falls back.

### 3. Placing the taper's boundaries on the tape

Filename and track-tag boundaries are already per-track. Description and notes boundaries must
be placed:

- A description boundary between taper set A and the next taper set B is **placed** after tape
  track *t* only when the evidence pins it there. That means the tape tracks matching A's items
  all come at or before *t*, the tracks matching B's items all come after *t*, and no song-like
  tape track between the last A-match and the first B-match is left unaccounted for. This is
  the same count-forced spirit as `setlist-gap` and `structure.gap_span`: an exact structural
  test, never a score or margin threshold. Filler tracks (`is_filler`) between the two may go
  to either side by a fixed rule the builder chooses (my default: filler before a set's first
  song belongs to the set it introduces, so `Set II intro`/tuning opens set 2; filler after the
  last song before the encore stays with the set).
- Matching reuses llama's existing matcher (`align()` and `fuzzy_norm_title`, family aliases as
  gather already computes them) against the **taper's** parse. It is not a new fuzzy rule.
  Tracks whose `title_source` is tautological (`TAUTOLOGICAL_TITLE_SOURCES`) are not evidence
  for placement, because their text is the setlist's own.
- A boundary that cannot be placed is **unplaced** and falls back. The other boundaries still
  count.

### 4. Precedence and merging

For each show without an operator structure override:

1. Compute the existing structure exactly as today: deterministic alignment of the winning
   canonical, then jerrybase anchoring.
2. Compute the taper-placed boundaries (sections 2–3).
3. The structure has two independent parts, and each is owned all-or-nothing (my call: the
   simplest rule that can never ship a half-taper, half-fallback numbered structure):
   - **Numbered breaks:** the taper owns them only when it asserts at least one numbered break
     and **every** numbered break it asserts is placed. Then exactly the taper's numbered
     breaks ship, with the taper's set numbers, and today's numbered breaks are dropped.
     Otherwise every numbered break comes from today's structure, exactly as now.
   - **The encore boundary:** the taper owns it when it asserts an encore and the boundary is
     placed. Then the taper's encore boundary ships. Otherwise today's.
   - The two parts must combine monotonically (every numbered break before the encore
     boundary). If they cannot, the taper-owned part ships, the conflicting fallback boundary
     is dropped, and an operator note records it.
4. jerrybase anchoring never moves or removes a taper-owned boundary. The PLF one-set rows
   therefore stop erasing tapers' set 2.
5. The low-coverage path (the `align_structure` LLM realignment and the
   `low-confidence structure alignment` flag) is skipped only when **every boundary in the
   shipped structure** is taper-owned, meaning the taper owns the numbered breaks and either
   owns the encore or the show ships no encore boundary. That mirrors how successful jerrybase
   anchoring skips it today. A show whose numbered breaks still come from a weak alignment
   (for example an encore-only description) goes down the low-coverage path exactly as now. (My
   call. Builder check: the literal reading would have cleared those with no flag.) The
   coverage number is still recorded.

`StructureInfo.alignment` becomes `"taper"` when any part of the structure is taper-owned. Today's
`"jerrybase"` note pattern applies: when the taper's structure differs from what today's code
would have shipped, record what it replaced (`set breaks from the taper's markers (was …)`).

### 5. Holds and notes

On a show whose structure has any taper-owned part:

- `structure has N sets but jerrybase shows M` is not raised when the taper owns the numbered
  breaks. It becomes an operator note. When the taper owns only the encore, the check runs as
  today.
- **The jerrybase closer tripwire (`closer_contradictions`)**, which reports a closer that sits
  at no break and does not pair closers with breaks:
  - it is still skipped entirely when the numbered breaks came from jerrybase anchoring, as
    today, because anchoring cannot contradict itself;
  - otherwise it runs as today, but a hard closer flag becomes an operator note when the taper
    owns the numbered breaks, or when the closer is the last numbered set's closer and the taper
    owns the encore boundary that ends that set;
  - every other closer flag stays hard. (My call: the narrowest version that still removes the
    PLF-style holds, which are all taper-owned numbered breaks.)
- `setlist evidence shows multiple sets but alignment found none` and
  `single-set structure for a long show`: today `structure_guard` returns early on **any**
  break, and the encore boundary counts as one. On a show with a taper-owned encore and no
  taper-owned numbered breaks, these two checks count **numbered breaks only**, so a taper's
  `Encore:` line alone cannot silence a long single set. (My call. Shows with no taper-owned
  part are unchanged.) A taper explicitly asserting a single set is a future question, and the
  evidence does not show it.
- Every other flag is untouched.

**Where the notes go (my call):** operator notes (`notes.json`, via gather's `op_notes`), not
`StructureInfo.conflicts`. Conflicts reach the briefing LLM, and the briefing should state the
taper's structure plainly rather than hedge on a source we chose to overrule. This matches 5c.1.
The "was …" provenance note (section 4) goes to operator notes too, and `alignment: "taper"`
records the mechanism.

### 6. Where it lives

The builder's call, within these lines. Parser recognition belongs in `llama/setlist.py`, and
it must not regress its documented, measured hazards (header truncation and
`_may_start_a_show`, the `_NOISE` disc rule, the inline-marker split order). Taper-structure
derivation and placement belong in a pure function beside `structure.py`/`jerrybase.py`.
`run_gather` composes it. The marker vocabulary may also improve how *sibling* descriptions
parse in `rank_parses`, which is acceptable but must show up in the harness. The `notes` field and filenames
are read only for the chosen recording.

### 7. Stored LLM alignments in the harness and `reapply`

Today `replay.compute_legs` marks every show whose stored `structure.alignment` is `"llm"` as
needs-LLM, before anything else, and `reapply` shares that code. The builder check counted 76 of
the 339 yes/partial shows stored `llm`, and 462 packaged or delivered shows.

**Relaxation (my call):** a stored `llm` alignment stops making a show needs-LLM when the
candidate's gather does not reach the LLM. That is the case when every boundary is taper-owned
(section 4.5), so the stored LLM output is no longer an input to anything the replay ships. The
rule stays exactly as today for every other show. This changes `llama/replay.py`, which
`reapply` uses, and so it is a strict surface: the existing needs-LLM pin (Tier 1's mutant) must
keep holding for non-taper shows, and the relaxation gets its own mutation-pinned tests in both
directions.

Shipped shows that still need the LLM in the candidate have an unknowable "after" offline.
Report 3 lists them in their own section (`after: needs LLM`) rather than dropping them, so
every shipped show the rule could touch appears somewhere.

## Measurement and acceptance

Replay harness, two arms from clean trees (`main` @ `a26c4d1` as base, the branch as
candidate), `--all` so non-held shows are covered, plus a cached-corpus check for the parser:

1. **The 394.** For each show in `classified.jsonl` with `taper_explicit` `yes` or `partial`,
   compare the candidate's shipped breaks to the adjudicator's target on the boundaries the
   taper marks. Report matches, misses and declines (unplaced, so falling back) by `primary`
   form, with every miss listed. Expected: most `yes` rows match, except the alignment-caused
   ones. The 8 known disagreements ship the taper's version. Shows that already carry an
   operator structure override (fixed overnight) are evaluated with the override ignored, in a
   harness mode or a scratch copy, since the override otherwise masks the rule.
2. **Newly cleared holds.** Every show held in base and not held in candidate is listed. An
   Opus pre-screen of the list runs **before merge**, so a rule defect it finds is fixed on the
   branch. The operator's hand check of the list gates the **apply**, not the merge, as in
   piece 1. (My call.)
3. **Non-held shows whose structure changes**, in a new harness report, split by state
   (packaged, delivered, voiced). For each: before and after breaks, the marker that drove it,
   and which source it overruled. The operator reads the count and shape before deciding on
   re-processing.
4. **Nothing newly held without explanation, and no title changes without explanation.**
5. **Parser false positives.** For each new marker form, count its matches over the cached
   corpus (`~/.llama/cache` item metadata, all descriptions, not only shown items) and
   hand-sample them. Any form whose sample shows a real song read as a marker is narrowed or
   dropped before merge.
6. Suite green. A mutation check (per [[mutation-scoring-needs-a-prediction]]) pins each
   load-bearing rule: both-sets-marked, the placement exactness, jerrybase not moving a taper
   break, and the false-positive guards.

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

## Left to the builder

- Exact regexes and their guards, given the forms above and the false-positive measurement.
- How the taper's parse is obtained: a provenance flag on `ParsedSetlist`/`SetlistItem` saying
  which labels came from explicit markers, or a separate structure-only parse. Either is fine
  provided the default `"1"` label is distinguishable from an explicit `Set 1`.
- The filler-side rule in placement (default given above).
- Note wording, the harness report's file name and format, and test layout.
- Whether the harness changes (report 3, the override-ignoring mode, and the section 7
  relaxation in `replay.py`) are their own tasks.

## Open questions

None for the operator at this time. Rulings this spec rests on: description as ground truth
(2026-10-22); delivered shows are listed first and re-processing decided after seeing them
(2026-10-22); Opus review mode (2026-10-22); the scope playback (taper wins where it marks,
others fill the rest; disagreement is a note; alignment-placement failures out of scope) accepted
2026-10-22.
