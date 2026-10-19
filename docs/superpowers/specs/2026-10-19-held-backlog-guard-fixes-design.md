# Held-backlog guard fixes (Tier 1): deterministic hold removal, measured by replay

Status: draft for review, not approved, not implemented.
Date: 2026-10-19.
Inputs: four read-only surveys of the held backlog run on 2026-10-19 (venue,
research/briefing, structure, titles; their reports and scripts live in the
session scratchpad and are summarised here with their numbers), plus the
measurements in "Evidence" below, which were re-run for this spec against the
live library (`~/.llama`, read-only) with a prototype of slice 0.
Related draft: `2026-10-19-tracklist-title-correspondence-design.md` (the
numbered-tracklist and filename rungs). It is a separate spec. Its M2 gate, a
full-library offline re-gather, is the harness specified here as slice 0.

## Kickoff

**Review mode: Fable** (one Opus and one Fable breadth reviewer, plus two Opus
strict-surface reviewers; for this run it overrides "never silently upgrade").

**Stakes.** llama feeds an automated radio station. Titles, venues, dates and
set structure are spoken by the DJ and shown to listeners. Every slice in this
spec removes holds, so the strict surface is narrow and specific: **a show
that leaves review carrying a wrong title, venue, date or set structure that
the old guard would have caught.** Each slice must say, from harness data,
which newly cleared shows it lets through and which of them were the closest
calls. Also strict:

- a real tape tag, a `sibling-format` title or an operator `override` is never
  overwritten, with one exception: 2b may demote a `tags` or `sibling-format`
  placeholder to `unresolved`, and never rewrites it to other text.
  `overrides.json` is written by nothing automatic in this spec; only the
  operator-confirmed slice 7 writes it;
- a packaged or delivered show's titles, venue or structure never change
  silently. They change only on an explicit operator `redo`/`fix`, and the
  harness reports in advance what would change;
- no do-not-retune constant named in `CLAUDE.md` moves. `is_real_title`,
  `title_fraction`, `_TRACK_NUM_PREFIX`, `normalize_song`, `DEFAULT_ALIASES`,
  `GD_SHORTHAND`'s family gate, `_RECOVER_BELOW`/`_RECOVER_SIBLING_ABOVE`, the
  tail-guard constants, the junk-duration constants and
  `align_coverage_threshold` all stay byte-identical. Wherever a slice needs
  something those would give, it adds a narrower predicate beside them and
  leaves the original alone.

Everything else gets proportionate review.

## The problem

**1,073 of 3,467 shows in the library are held for review** (counted
2026-10-19 from `show.json` `needs_review`). Each one costs the operator
minutes or more, and the backlog only grows. Counted by flag family over the
held set (a show counts once per family it carries; "sole" means that family
is its only one):

| family | shows | sole |
|---|---|---|
| structure (low-confidence alignment, single-set long show, multi-set evidence, jerrybase set count / closer, low-confidence setlist) | 354 | 181 |
| unresolved track titles | 327 | 166 |
| research asserts unknown song | 312 | 122 |
| research asserts N sets but structure has M | 184 | 110 |
| venue mismatch | 138 | 116 |
| research asserts wrong date / placeholder | 57 | 34 |
| briefing guard (all kinds) | 55 | 55 |
| tape spans / unassigned events | 5 | 0 |
| no playable tracks | 3 | 0 |

The surveys traced most of these holds to a few specific guard misfires:

- the venue tripwire fails on spelling (`Penn's`/`Penns`,
  `Amphitheatre`/`Amphitheater`, `Cornell U`/`Cornell University`) and on a
  blank jerrybase venue. The surveyors estimated its false-positive rate at
  about 99% (1 real wrong venue in 138, from a hand check);
- `is_real_title` rejects real short tags (`J`, `42`, `7-11`, `FF`, `I-55`,
  `1 in 7`);
- the briefing guard reads an empty `encore: []` list as a nonexistent set,
  and reads "the second of Panic's two weekend sets" as a set-count claim;
- grounding flags any second date, even when research also asserts the show's
  own date;
- `evidence_sets` counts the encore as a set (`gather.py:1163` passes
  `{i.set for i in canonical.items}`).

The same surveys found real defects that the guards miss. Junk tag titles
(`tmp`, `Track 01`, `Trac3`) pass `is_real_title` and ship. On held shows the
research flag is currently the only tripwire for them, and they already ship
on packaged shows. `darkstarorchestra-2003-01-25` would air with the wrong
venue and city: `grouping.py:36-43` majority-votes the venue across sibling
recordings, and the vote went to a recording that is not the selected one.

Tier 1 is the set of deterministic fixes, with no LLM involved, that remove
false holds without opening the strict surface, and close the junk-title and
wrong-venue gaps that removing those holds would otherwise expose. It touches
only shows whose gather needs no LLM call; the rest stay held for the LLM
adjudicators of a later tier.

## Evidence

All counts were measured on 2026-10-19 with read-only probes (scratchpad
`work/tier1-spec/`). Survey numbers not re-measured are marked *(survey)*.
**Every prototype number is an estimate**: the prototype's rules differ from
the ones specified here, as listed with each number, and the expected
direction is fewer clears. Re-running the harness on the rules as specified is
slice 0's first acceptance item.

### The replay prototype reproduces the library

A prototype of slice 0 re-ran `run_gather` offline for every show, with
cache-only archive.org and setlist.fm clients, `extract_setlist` skipped, and
`align_structure` answered from the stored result whenever the call's input
was byte-identical. It then ran `grounding_flags` over the stored
`vetting.json` and `briefing_guard` over the stored `briefing.json`.

- **Held shows: 1,071 of 1,073 reproduce their stored gather and vet flags
  exactly.** The two that differ (`soulcoughing-1994-11-30`,
  `trampledbyturtles-2007-07-20`) are code drift since they were gathered.
- **Whole library: 3,456 of 3,467 reproduce.** The 9 non-held drifts are code
  drift or earlier `--overrule`s.
- **Briefing guard: 55 of 55 stored briefing flags reproduce exactly.** No
  clean briefing out of 2,394 fires under today's guard.
- **Zero cache misses** for item metadata (every candidate recording, siblings
  included) and for setlist.fm across all 3,467 shows, so a real re-gather
  needs no fetch.
- **Gather reaches an LLM call on part of the held set**: `align_structure` on
  487 held shows (325 with a stored LLM structure; 162 where the call failed or
  came back below threshold, hence their flag), and `extract_setlist` on 9
  held shows with no canonical plus the 2 library shows whose canonical came
  from the LLM. A real re-gather would ask the LLM again on each, with an
  outcome nobody can predict offline. Tier 1 leaves them held (needs-LLM).
- Runtime: about 15 s for the held set, under a minute for the library.

### Prototype per-slice effect (held shows; gather and vet legs)

Each row is one candidate rule patched into the prototype and compared with
today's code on the same replay. "Clears" means no gather or vet flag; the
show still has to pass `brief`, except in the briefing row, which is measured
on stored briefings.

| slice | flags removed | shows clear | flags added | specified rule differs |
|---|---|---|---|---|
| 1 | venue mismatch on 134 of 138 | 113 | 0 | the prototype swapped to the selected recording on any difference and added no hold; the spec keeps an agreeing vote, swaps only on agreement with jerrybase, keeps two-venue holds and adds 1d. It cleared `darkstarorchestra-2003-01-25`, which must stay held |
| 2a | unresolved titles on 128 | 84 | 31 low-confidence (needs-LLM) | no alphanumeric or junk veto, counted the selected recording's own description, ran before sibling-align and setlist-gap. At least 5 clears rest on `?` tags; 15 changed set labels |
| 2b | — | 0 | 30 unresolved (by design), 25 needs-LLM | its exemption also counted the selected recording's own description |
| 3 | 35 of 55 briefing holds | 35 | 0 on 2,394 clean briefings | its 3c suppressed more (an extra arm, a narrower intervening-word rule, a 4-word negation window, extra scope arms) |
| 4a (with 2a+2b) | unknown-song on +67 shows | +67 | 0 | no own-date requirement or minimum count, counted tautological titles, read the date flags after 4b |
| 4b | wrong date on 37 | 26 | 0 | every other date was context and a yearless own date counted; 4 of its 26 clears are misdated tapes |
| 5a | multi-set flag on 26 | 6 | 6 single-set-long-show | the spec keeps the flag on an unplaced encore (3 of the 6 clears) |
| combined (all but 3 and 5c) | — | **350** | — | all of the above, with no needs-LLM exclusion |

The combined 350 is an upper bound. It excludes slice 3 and 5c (about 27
sole, *survey*, not replayed), and it counts roughly 70–110 shows whose gather
reaches an LLM call, including the 40 whose earlier `align_structure` call
left no result. Tier 1 excludes those, so expect roughly
240–280 before the other rule differences take their share.

### Facts the slices depend on

- **Short real tags (2a).** Over held shows' unresolved tracks whose raw tag
  fails `is_real_title`: **148 tracks on 117 shows equal, after marker
  stripping, an item of some parse** (any recording's description or
  setlist.fm); 113 shows get every unresolved track resolved that way. That
  count counted the selected recording's own description: 63 of 158 candidate
  adoptions, on 40 shows, are corroborated only by it, which 2a does not
  count. The survey's description-token fallback would add only 15 tracks,
  mostly junk (`10`, `[`, `E1:3-4-4-3`, `986 ft`), so **item equality is the
  rule**. Traps: `?` is an item in some parses (`soulive-2010-03-06` adopted
  `? @%*# ->`); timed tracklists make timestamps items
  (`bobbyleerodgers-2010-01-13` adopted `07:22 - IB49`,
  `stantonmoore-2008-09-11` `05:27`); run before the later rungs, 2a displaced
  better titles (`Ramone & Emiglio` from setlist-gap became `R&E`, `1922`
  from sibling-align became `1922 $`); and 15 adoptions carried an attached
  marker (`FF>`, `ML**`).
- **Junk titles on packaged and delivered shows (2b).** Tag-sourced
  placeholders on non-held shows: `eotoband-2007-10-09` (all 9 tracks
  `Track 01`..`Track 09`, delivered), `gratefuldead-1977-03-18` (track 10
  `tmp`, delivered), `newmastersounds-2018-05-08` (`Track 14`, delivered),
  `blitzentrapper-2013-11-12` (`Trac3`, `Trac10`, packaged) and
  `motherhips-2013-06-21` (`Track 16`, packaged): 5 shows, 14 tracks. **Two
  near misses mark where a detector must stop:** pure 4-digit titles are real
  songs (`1979`, Smashing Pumpkins, 21 shows; `1759`, `1103`, `1961`, `1968`,
  `1974`), and Fugazi's `Song #1` is real (2 shows). `eotoband-2007-10-09`'s
  own description lists the same `Track 01`… text as its tags.
- **Positional fill of junk tapes (2b).** 13 to 15 of the 35 junk-detected
  tapes have a parse whose item count equals the track count, which the
  whole-tape `setlist` rung copies by position with no content check
  (`darkstarorchestra-2012-07-21`: 13 `tmp` tracks; on
  `thetravelinmccourys-2014-05-24` the real order is shifted one, so every
  positional title would be wrong).
- **Glued prefixes (2c).** `01Pig In A Pen` and its kind appear on 4 held
  Railroad Earth shows. One repeats a number (`03Four Twenty Hornpipe`,
  `03Colorado`), so "the number equals the play position" would fail.
- **Set structure under a title change.** 15 of 2a's 84 prototype clears
  changed set labels with no LLM call: a new title raised deterministic
  coverage over the threshold and replaced the stored LLM structure. At least
  4 are wrong at a set boundary (`umphreysmcgee-2006-02-17` loses its encore;
  `moe-2005-05-29`, `pnuma-2006-09-21`, `soundtribesector9-2001-03-16` move a
  set-2 opener into set 1). Their stored alignment is `llm`, so they are
  needs-LLM; a deterministic re-gather can still move labels elsewhere, hence
  the structure-changed list.
- **Venue (1).** On 44 of the 138 venue-flag shows the shipped venue is not
  the selected recording's own *(survey)*. Library-wide, the selected
  recording's venue differs from the vote on 648 shows (459 equivalent
  spellings), and the city on 30 by a crude comparison, about 10 of them
  genuine. **Four shipped the wrong venue for the audio, and research.md says
  so** (listed under "Act now"), each a two-performance date by an artist
  jerrybase does not cover; `guster-2003-07-10` ships Cities 97 Studio C while
  the audio is the Minnesota Zoo concert. A naive "always prefer the selected
  recording" rule regressed 2 shows (`This Tent / Bonnaroo , TN`, `Angle's
  Camp`), hence 1d's city gating. Also:
  - `gratefuldead-1978-11-17` is a same-city two-performance date (the
    afternoon Rambler Room benefit and the evening Uptown Theatre show, both
    Chicago); the candidate holds recordings of each, and jerrybase knows only
    the Uptown event;
  - 25 clean shows have a vote that agrees with jerrybase and a selected
    recording that does not (`gratefuldead-1974-06-20` ships "The Omni"; its
    tape says "Atlanta Municipal Auditorium"). Comparing only the selected
    recording would hold them or replace an agreed venue;
  - on 29 shows the selected recording carries a venue but no city, and many
    crude city differences are spelling only (`Ft.`/`Fort Lauderdale`,
    `St.`/`Saint Louis`, `NYC`/`New York`).
- **Right-show gate (4a), prototype.** 110 held shows meet "≥50% of resolved,
  non-filler tape tracks asserted by research, no wrong-date flag, under half
  the tape unresolved"; 106 also have research asserting the show's own date.
  73 sit at a ratio ≥ 2/3, 37 between 0.5 and 2/3. Without 2b it would clear 2
  shows carrying junk titles (`greenskybluegrass-2014-05-22`,
  `neworleanssuspects-2013-05-25`), so 2b lands first. On tiny tapes the
  ratio says nothing: `moontaxi-2010-04-15` and `loslonelyboys-2004-10-24`
  (1 track each; 17 of 18 and 6 of 7 research songs unknown) both cleared.
- **Notes reach the briefing LLM today.** `run_brief` passes the whole
  `show.json` to the prompt (`brief.py:137-139`), and gather merges its notes
  into `structure.conflicts` (`gather.py:1182-1184`).
- **Re-processing cost (6).** The average packaged audio set is 175 MB (630
  shows with audio on disk). `pacing-state.json`'s learned per-show cost reads
  `3.0e-11` over 4,241 samples, which cannot size a batch. `llama redo` is no
  route for this backlog: `_redo_show` drops `vetting.json`, `briefing.json`
  and `briefing.md` first (`cli.py:2223`), so every redo re-runs the LLM
  extraction and a fresh brief, and `_redo_batch` (`cli.py:2933`) has no
  pacing gate (a `RateLimited` is a per-show `FAILED`, and the batch carries on
  into an empty window).

## The rulings this design rests on

1. **A hold is removed only by a rule whose effect the harness can
   enumerate.** Every slice ships with its harness diff: the newly cleared
   shows, the shows whose shipped fields would change, and the closest calls.
   It also needs a hand-check sample, and on a strict-surface slice a hand
   check of every cleared show when there are at most ~150.
2. **Narrow beside, never loosen in place.** Where a protected predicate is
   too strict for one consumer, that consumer gets a narrower predicate with
   corroboration, and every other caller keeps the original. This is how 2a
   treats `is_real_title`, 2c `_TRACK_NUM_PREFIX`, and 3b
   `structure._STRUCTURE_PREFIX`.
3. **Corroboration is cross-source or it does not count.** A short tag is
   accepted because a sibling recording's description or setlist.fm, written
   by someone else, names the same item. The selected recording's own
   description shares the tags' author and never corroborates them. A
   canonical item is never corroborated by itself.
4. **Packaged shows are reported, not migrated.** Nothing here rewrites a
   package. The harness's whole-library run lists every packaged or delivered
   show a redo would now change, and the operator decides.
5. **Tier 1 is LLM-free by scope.** A show is in scope only when its gather
   completes without reaching an LLM call. Any other show is **needs-LLM**: it
   stays held, untouched, for the later LLM adjudicators. The harness and
   `llama reapply` (slice 6) decide this with the same code, so prediction and
   apply cannot disagree.
6. **Operator-facing notes never reach the briefing LLM.** Every note this
   spec adds goes to a sibling `notes.json` in the show directory, read only
   by `llama show` and triage: never into `show.json`, `vetting.json` or
   `structure.conflicts`. `notes.json` is a gather artifact, replaced on every
   gather, so a note never outlives the run that raised it; vet adds 4a's note
   to the file gather wrote.

## Slice 0 — the replay harness (prerequisite)

**What.** `scripts/replay_holds.py`: an offline tool that recomputes every
show's holds from stored artifacts and the cache, under the code on
`sys.path`, and never writes to the library or the cache. `scripts/` is in
pytest `testpaths`, so its tests run with the suite.

**LLM-free gather (shared by the harness and `reapply`).** Gather can run with
no LLM providers, and then reports whether it would have needed one instead
of silently degrading to a flag. It would have needed one when it reaches the
`align_structure` branch (`gather.py` ~1047: canonical items present,
coverage below threshold, no jerrybase anchoring) or the `extract_setlist`
fallback in `build_canonical` (no parse ranks and a non-empty description; an
empty description makes no call today, `gather.py:792-794`, so it is not
needs-LLM). The verdict is a field of gather's result, not an exception. A
show is **needs-LLM** when gather reports either, or when its stored
`structure.alignment` is `llm`. With providers, gather behaves exactly as
today.

**Two subcommands.** `run --out <arm.json> [--held|--all] [--slugs FILE]`
replays each show under the importing tree's code; `compare <base.json>
<cand.json>` diffs two arms. A candidate change is measured by running `run`
in a main checkout and in the slice's worktree, **each with that tree's own
interpreter** (`./.venv/bin/python -m ...`, or a `PYTHONPATH` shadow). `run`
prints `llama.__file__` and refuses to start unless it resolves inside the
invoking tree: the `CLAUDE.md` worktree and copied-tree trap, enforced rather
than remembered. Monkeypatching (what the prototype did) is a probe technique
only; acceptance numbers come from real branches.

Each arm records the git SHA and a config fingerprint, and per show the
digests of its inputs (`show.json`, `overrides.json`, `provenance.json`,
`research.md`, and the extraction part of `vetting.json` — the asserted songs,
dates and set claims, never its flags) and whether a setlist.fm
client is configured. `compare` exits non-zero when the arms' digests or
client configuration differ (the library changed between runs), and when the baseline arm reproduces stored flags on fewer than 99% of
shows. Output schema and default scope are left to the plan.

**Replay, per show.** A scratch `ShowWorkspace` gets a copy of
`overrides.json` and nothing else. `run_gather(force=True)` runs into it with
the stored `provenance.json` candidate and `show.identifier`, no LLM
providers, and:

- a **cache-only archive.org client**: `metadata()` reads
  `cache/md_<id>.json`; a miss marks the show `unreplayable: cache miss`; every
  network method raises;
- a **cache-only setlist.fm client** that derives its cache key through the
  same function `SetlistFMClient` uses (factored out, not restated). A miss
  returns `None` and is counted, because the real client would fetch.

Then `reapply`'s other legs (slice 6), deterministically:

- **vet leg**: `grounding_flags(stored extraction, replayed show)` plus the
  existing placeholder-date adoption, through one function shared with
  `reapply`; the extraction is never re-run. No stored `vetting.json` means
  needs-LLM;
- **brief leg**: `reapply`'s reuse rule. On reuse, `briefing_guard(stored
  briefing, replayed show)` decides; otherwise the show is **needs-brief**
  (one fresh Opus brief, outcome not predicted). The guard is also run over
  every stored briefing and reported, which is how slice 3 is measured.

**Outcome classes.**

- **clears**: no flag on any leg, exact through brief (the stored briefing is
  reused). Package-stage outcomes (a download failure, a duration mismatch)
  are not modelled; the pilot reports them. Only the 55 shows held by the
  briefing guard have a stored briefing, so this class is small.
- **needs-brief**: clears gather and vet; the brief is fresh and not predicted.
- **needs-LLM**: ruling 5's exclusion; listed and counted, never touched.
- **structure-changed**: a would-clear show whose set or segue labels,
  `set_breaks` or `structure.alignment` differ from the stored show. Listed
  apart from clears, and every one is hand-checked against its description
  before it joins an apply list. No slice is exempt.
- **still held**, including **still held (package)**: a stored package-stage
  flag, which the harness does not model, is carried through;
- **unreplayable**.

**Title-source changes.** For every would-clear show the harness lists each
track whose title or `title_source` changes, including setlist-gap and
sibling-align fills a Tier-1 change enables downstream. Every entry is
hand-checked.

**Why a clear is exact through brief.** `reapply` runs the same LLM-free
gather, the same vet function over the stored extraction and the same
briefing-reuse rule. Needs-brief clears are upper bounds, because a fresh
brief can be held by its own guard. A prompt change (4d) cannot be measured offline at all.

**Output per show**: slug; state (held / packaged / delivered, meaning
packaged with `package/audio` purged / clear); stored flags; the arm's flags
per leg; outcome class; briefing reuse or fresh; title and `title_source`
changes; venue and city changes; set and segue label changes; notes emitted;
artifact digests. **Aggregates**: counts per flag family (removed, added); a
**drift report** (stored versus baseline arm); a **packaged-exposure report**
(every non-held show whose shipped fields differ between arms); the
title-source and structure-changed lists; a deterministic **hand-check
sample** of newly cleared shows (20, or all when fewer); and each slice's
**closest-call list**, ranked by the metric that slice defines.

**Narration candidates.** `compare` also lists the held shows whose only
remaining flags are unknowable-structure ones ("single-set structure for a
long show", "low-confidence setlist" with an empty canonical), the `--narration
vague` population, and marks those whose titles are wholly unresolved (slice
7's `--untitled` candidates). The harness emits it for the operator as a
browsable page (one row per show: artist, date, venue, minutes, flags, title
sources, and a description excerpt) and does nothing else with it.

**Acceptance.**

1. The harness is re-run on every slice's rules as specified, and its numbers
   replace every prototype estimate here before any slice's decision point.
2. Over the held set, the baseline arm reproduces stored flags on ≥ 99% of
   shows (prototype: 1,071/1,073); `compare` exits non-zero below that. Every
   drift case is listed.
3. Zero writes outside the scratch directory, tested on a fixture library with
   a read-only root. The cache-only clients raise on any network attempt
   (tested).
4. With no providers, gather makes no LLM call and reports needs-LLM on a
   fixture show that reaches `align_structure` and on one that reaches
   `extract_setlist`; the harness and `reapply` reach that verdict through the
   same code (tested).

## Slice 1 — Venue

**What changes** (`gather.py` venue block, `structure.venues_equivalent`). On
a date jerrybase covers, the tripwire runs these steps in order, each using
1b's equivalence and the city predicate below:

1. **The vote agrees.** If the shipped vote's venue is equivalent to
   jerrybase's and the cities are compatible: no flag, the vote ships, and
   nothing below runs.
2. **The swap.** Otherwise, if the selected recording's own venue is
   equivalent to jerrybase's, two independent sources agree: gather ships the
   selected recording's venue, and its city when it has one (else the vote's),
   with a note. Excluded: candidates whose recordings name two or more
   non-equivalent venues in one city (the two-performance signature, as in
   `gratefuldead-1978-11-17`); those keep the hold. The signature also fires
   on spellings of one hall, and is kept anyway because its error keeps a show
   held: `gratefuldead-1981-09-26` ships "Buffalo Auditorium" against
   jerrybase's "Buffalo Memorial Auditorium", but its recordings also name
   "Community War Memorial Auditorium" (8 tapes against 2), so it stays held
   under Tier 1. Every swap is on the harness change list and hand-checked.
   The swap is evaluated before 1d.
3. **Otherwise** 1a and 1c compare jerrybase with the selected recording, and
   whatever they do not resolve keeps today's flag.

- **1a. A blank jerrybase venue is no evidence.** An empty `event.venue`
  neither flags nor enriches, when the cities are compatible. Fixes
  `darkstarorchestra-2012-05-19`.
- **1b. Better equivalence.** `venues_equivalent` gains:
  - apostrophes *joined* rather than split (`Penn's` = `Penns`);
  - folds for amphitheat(re|er)/ampitheat*, pavill?ion and race track/racetrack;
  - university-class tokens (`u`, `univ`, `uc`, `ucla`, `ucsb`, `uiuc`, `mit`,
    `university`) ignored for the subset test; a strip that empties either
    side means not equivalent (`UCLA` against `UCSB`);
  - a joined-string comparison (`Jahrhundert Halle` = `Jahrhunderthalle`);
  - one edit allowed on tokens of ≥ 6 characters (`Merramec`/`Meramec`).

  Its only caller is the venue tripwire (grep-verified), so nothing else
  moves.
- **1c. Same place, different name, becomes a note.** On a single-event date
  with compatible cities, a remaining mismatch between jerrybase and the
  selected recording (a festival against its site, a renamed hall) becomes the
  note `venue differs from jerrybase: archive 'X' vs 'Y' (same city)` instead
  of a hold. **Shawn ruled that the selected recording's venue string ships**;
  jerrybase's is kept only in the note. 1c does not apply on the
  two-performance signature, and those shows keep the hold.
- **City compatibility** is one predicate shared by steps 1–3, 1a, 1c and 1d,
  and enforced in code on each. In steps 1–3 the archive side is the selected
  recording's city (its `coverage`), else the vote's. Take the first comma
  field, lowercase it, drop punctuation, and fold `ft`→`fort`, `st`→`saint`,
  `mt`→`mount`, `nyc`→`new york city`. The cities are compatible on equality
  of the joined strings; on one edit on ≥ 6 characters; on whole-token
  containment (`Detroit Lakes` inside a festival city field, never `la` inside
  `dallas`); or through a small metro alias table fixed a priori from the
  survey's four measured pairs (Goleta = Santa Barbara, Salinas = Monterey,
  Yuzawa = Naeba, Thornville = Legend Valley). When both sides carry a state
  or region (the second comma field), it must agree too (`Portland, OR` is not
  `Portland, ME`). In steps 1–3, unknown on either side means not compatible.
- **1d. The selected recording's venue wins on a city conflict.** The grouping
  fix lives in **gather**, since grouping runs before selection. It runs on
  every show, jerrybase or not, and fires only when the selected recording
  carries both a venue and a city, and that city is known to be incompatible
  with the vote's city, whatever the swap shipped. An unknown selected city is
  no conflict. When it fires, gather ships the selected recording's venue and
  city and adds the hold **`recordings of this date disagree on city: 'A'
  (selected) vs 'B'`**: the other recordings' descriptions, and setlist.fm's
  venue-keyed pick, may belong to a different performance, which a venue
  string cannot fix. 1d runs before the `overrides.venue`/`overrides.city`
  block, and an operator venue or city override suppresses its hold, so a
  show corrected by hand is not held again on its next redo. With compatible
  cities the vote stays, so there is no string churn on about 618 shows.
  `build_canonical`'s setlist.fm lookup keeps the candidate's venue and city
  byte-identical. Choosing the canonical for two-performance dates is under
  "Next". 1d was not prototyped, so its numbers come from its branch.

The swap's and 1c's notes go to `notes.json` (ruling 6).
Where today's enrichment (a blank vote venue ships jerrybase's,
`gather.py:1138-1139`) sits among the steps is left to the plan.

**Estimates.** Cleared: to be measured on the branch (the signature keeps
many held; 92 of the 138 carry it under today's equivalence). About 110 sole
*(survey)*. Prototype: 134 flags removed, 113 shows clear (rule differed;
expect fewer). `darkstarorchestra-2003-01-25` should change from the wrong
venue (St. Louis) to the correct one (Barrymore Theatre, Madison) through the
swap and stay held under 1d; the branch measurement must show it.

**Acceptance.**

- Hand-check every cleared venue pair; for 1c the check also decides whether
  the shipped string is right. Known wrong strings, which the operator may
  correct with `--set-venue`: `gratefuldead-1967-11-10` and
  `gratefuldead-1968-08-23` ("Shrine Auditorium" against "Shrine Exhibition
  Hall"), `philleshandfriends-2005-12-04` ("Washington St. Armory" against
  "Washington Avenue Armory").
- Zero cleared shows whose cities are not compatible (also unit-tested).
- `darkstarorchestra-2003-01-25` does not clear silently, and
  `gratefuldead-1978-11-17` keeps its hold.
- Library-wide, step 1, 1a and 1b change no shipped venue string; the swap's,
  1c's and 1d's string changes are listed, each one shown.
- Every clear whose shipped venue is not equivalent to the selected
  recording's own is listed.
- Closest calls: the bottom 10 1c clears by token overlap between the archive
  and jerrybase names.

## Slice 2 — Titles

### 2a. Corroborated short tags

**What.** A new pass in gather, after sibling-align and setlist-gap adoption
and before alignment. It fills only tracks still `unresolved`, so it never
pre-empts a later rung (`Ramone & Emiglio` stays, not the tag `R&E`) and never
touches an `override`. It targets tracks whose tag-layer text (the layer
`resolve_titles` used: recovered format titles when recovery fired, otherwise
the delivered tags) fails `is_real_title`. The tag is adopted when all hold:

- its core (the tag minus trailing `> -> => * % # @ ^ ~ $ +` and whitespace)
  contains an alphanumeric character, so a `?`-only core never qualifies;
- the core passes 2a's junk veto, with no exemption. The veto rejects a 2b
  placeholder; a timestamp; a date, meaning a match for a date pattern
  (numeric day, month and year in any order with separators, or a month name
  with a day or year); and filename residue (`d1t02`, `t1`, `NNNNNN_NN`). It
  does not reject a core for having fewer than 3 letters, which is exactly the
  class 2a exists to accept;
- every segue component of the core equals, by `fuzzy_norm_title`, an item of
  a parse whose source is **not** the selected recording's own description (a
  sibling recording's description, or setlist.fm). `build_canonical` exposes
  that item vocabulary additively; no consumer changes;
- the core is not in `metadata_norms` (dates, venue, city, artist), the same
  veto `hygienic_title` applies.

The shipped title is the tag with its trailing taper markers removed, attached
or free-standing (`$ + * > -> =>`; `#` only when free-standing, so `F#` keeps
it): `FF>`, `ML**`, `7-11**` and `FF =>` ship as `FF`, `ML`, `7-11` and `FF`. `%` is not in that set, so `100%` keeps it.
`_FOOTNOTE_TAIL` is unchanged. `title_source` is `sibling-format` when format
recovery fired, otherwise `tags`, and it is **not** added to
`TAUTOLOGICAL_TITLE_SOURCES`: the text is the taper's tag, and the item only
corroborates it, as an ordinary `Bertha` tag also equals an item. Gather
writes a `notes.json` note listing the short tags it accepted.

`is_real_title`, `title_fraction` and every recording-level gate
(`_RECOVER_BELOW`, `fetch_siblings`, `_sibling_titles`) are untouched. Since
sibling-align and setlist-gap have already run, a 2a tag anchors neither in
Tier 1. It is an ordinary title to `align()` and jerrybase anchoring, and
`anchor_spans` counts it as an anchor in `--suggest-titles`'s proposal.

**Estimates.** 113 shows, 94 sole *(survey)*. Prototype: 128 shows lose the
titles flag, 84 clear and 31 more reach `align_structure` (needs-LLM) (rule
differed; expect fewer).

**Acceptance.**

- Hand-check every accepted short tag against its corroborating line.
- Zero accepted cores without an alphanumeric character, in `metadata_norms`,
  caught by the junk veto, or corroborated only by the selected recording's
  own description. No shipped title keeps a trailing taper marker.
- No title that was not `unresolved` changes anywhere in the library run.
- Every set or segue label change is on slice 0's structure-changed list.
- Closest calls: tags accepted from a single parse source, and numeric-only
  cores (`42`, `128`, `102`, `405`, `'99`).

### 2b. Junk-title detector (must land before slice 4)

**What.** At the tag rung inside `resolve_titles`, a placeholder tag is
demoted directly to `unresolved`, with the `notes.json` note `placeholder tag
title`. It never falls through to the whole-tape `setlist` rung, which copies
items by position with no content check (see Evidence). Setlist-gap and
sibling-align, which check their own evidence, are the only ways such a track
can still get a title. The classes are fixed a priori:

- **placeholder vocabulary**: `Track`/`Trac`/`Trk`/`Tr`/`Cut` + number or
  number-word (`Track 01`, `track six`, `Trac3`, `Track ten`); `tmp`/`temp`;
  `No Title`; `Title`. `Untitled`, bare or numbered, is deliberately **not**
  in it: bare `Untitled` is a real Smashing Pumpkins title, and Railroad
  Earth's `Untitled #12` is how all four sources of
  `railroadearth-2013-07-12` name that song. `Song #N` is deliberately **not** in it (Fugazi's
  `Song #1` is the only instance found, and it is real);
- **timestamps**: `27:36.27`, `05:27 -`;
- **pure filename residue**: after deleting the identifier, date, disc/track,
  lineage and extension tokens, fewer than 3 letters remain
  (`buckethead2004-06-04d2t05`, `fIREHOSE 1992-02-19 t02`). **A pure 4-digit
  title is exempt** (`1979`, `1759`, `1103`);
- **recording-level**: one identical string on every track of a ≥ 3-track
  recording (`tmp` × 19), or the item's own title on every file.

**Exemption:** a tag equal, by `fuzzy_norm_title`, to an item of a parse whose
source is not the selected recording's own description (2a's vocabulary) is
never junk. The selected recording's own description does not exempt
(`eotoband-2007-10-09`'s lists the same `Track 01`… text as its tags). Only
`tags` and `sibling-format` titles are judged; an `override`, slice 7's
included, never is.

Recording-level gates keep `is_real_title`, so `_RECOVER_BELOW` does not move;
the cost is that an mp3 tagged `tmp` throughout does not trigger
format-sibling recovery. The harness counts the detected tapes with a format
sibling at ≥ 0.9, and that count is filed rather than acted on.
`fetch_siblings` is a fetch gate, not a measured one ("never wrong, only
wasted"), so it is recomputed over post-detector titles, giving sibling-align
its guarded chance at these tracks; its fills appear on slice 0's
title-source list.

**Packaged shows, reported and not applied:** the 6 shows and 15 tracks in
Evidence. Nothing changes until an operator redoes them.
`eotoband-2007-10-09` is a fully improvised set; slice 7 gives it a route.

**Estimates.** U2: 49 held shows (33 sole) *(survey)*. Prototype: 35 held
shows, 18 wholly junk (its exemption counted the selected recording's own
description; expect more demotions). These shows **move from the research
flag to the titles flag** and stay held, correctly.

**Acceptance.**

- A library-wide list of every title the detector would demote, hand-checked
  in full (≈ 650 tracks, mostly whole tapes, so a per-show check).
- Zero demoted pure-4-digit titles, and zero demoted titles corroborated by a
  sibling description or setlist.fm.
- The packaged-exposure list matches the Evidence list or explains each
  difference.

### 2c. Glued track-number prefix

**What.** In `clean_tag_titles`, a second, independent strip: one leading
2-digit number glued to a capitalised word (`^\d{2}(?=[A-Z][a-z])`), applied
only when the recording-level vote finds the shape on at least
`_ENUMERATED_MIN_FILES` files and `_ENUMERATED_MIN_COVERAGE` of them (the
existing constants, voting over the same `gate_basis`). `_TRACK_NUM_PREFIX` is
not touched. The uppercase-then-lowercase lookahead keeps `3AM`, `M80` and
`7-Up` out of reach.

**Estimate.** 4 Railroad Earth held shows, all sole *(survey)*; the prototype
found the same 4.

**Acceptance.** Every stripped title is listed. Zero strips on recordings
under the vote. The four target shows lose the research flag where the strip
was its cause.

## Slice 3 — Briefing guard (`brief.py`)

**What** (`briefing_guard` and `run_brief`; the vague-narration branch is
unchanged):

- **3a. Empty sets are dropped.** On generation and on every reuse of a
  stored briefing (slice 6), empty `per_set` entries are removed from
  `briefing.json`, and `briefing.md` is re-rendered from it (a pure function).
  The guard never sees an empty set, and no empty `## Encore` heading reaches
  emcee, whose scriptwriter reads `briefing.md`. All 11 shows this clears
  carry one today (for example `warrenzevon-1988-11-30`).
- **3b. Tolerant song matching, narrowly.** A mentioned song is known when
  today's exact `normalize_song` equality holds, **or** when both sides match
  after these deterministic strips: a leading structure prefix (`E:`, `E1:`,
  `Encore:`), trailing segue and footnote markers, and one trailing
  parenthetical (`1979 (Kerry Brown on drums...)`, `Storms (fades in)`). The
  prefix uses a brief-local regex; `structure._STRUCTURE_PREFIX` is untouched
  (it does not match `E1:`, and it feeds `align()`, anchoring and jerrybase
  closer matching). Both sides are split into segue components: a mentioned
  song is known when every component is known (`Drums > Space`), and every
  component of a merged track title counts as a known track title.
  `fuzzy_title_eq`, `loosely_same_title` and subphrase matching are **not**
  used; the survey's looser 20-of-24 used them, which is too loose for a
  guard. **Invariant: the new matcher is a superset of today's**, so it can
  only remove flags.
- **3c. Set-count claims.** The count regex keeps today's single optional
  intervening word, but a count whose intervening word is on a small denylist
  of non-show-wide qualifiers (`electric`, `acoustic`, `night`, `late-night`,
  `afternoon`, `weekend`, `more`, `festival`, `day`) is not a show-wide count:
  "two night sets" and "two electric sets" no longer count, "two excellent
  sets" still does. Count and ordinal matches are also ignored when:
  - `no`, `not` or `never` is one of the two words before the match ("there is
    no second set"), or `instead of`, `expected` or `without` is within the
    four words before it; or
  - a scope phrase follows (`each/every/a/per night|day|weekend|tour`).
    `that` and `this` are not scope words: "two sets that night" is a claim
    about this show.

**Re-checkable offline on stored briefings.** All 55 held briefings exist and
reproduce. Prototype: 3a clears 11, 3b 13, 3c 11; together 35 of 55, and 0 of
2,394 clean briefings newly fire. Variants closer to the specified 3c cleared
34 or 35. The ~20 that remain include the survey's real-looking cases
(`moe-2002-06-22` "two sets and an encore" against 3;
`derektrucksband-1999-02-13` "44 Blues" not on the tape). Their stored
briefing fails the guard, so `reapply` gives each one fresh brief, which its
own guard can hold again. Survey estimate: about 45 of 55, with looser
matching.

**Which briefing ships.** A cleared show reuses its stored briefing when
`reapply`'s reuse rule holds, so the briefing read by hand is the one that
ships. A show whose broadcast fields or narration changed, or whose stored
briefing still fails the guard, gets a fresh brief and is listed as
needs-brief.

**Acceptance.**

- Every briefing that will ship by reuse is read whole by hand: this is the
  strict surface, because the briefing ships as written. The shows getting a
  fresh brief are listed as such.
- Zero newly firing on clean briefings.
- Every match over the 2,449 stored briefings that today's regex flags and the
  new one suppresses is listed and read by hand. That measures the detection
  3c gives up, which "zero newly firing" cannot see. The prototype suppressed
  about 68; the specified rule is re-counted.
- The remaining holds are listed.

**Limit, stated not fixed.** The guard checks the LLM's self-reported
`mentioned_songs`, not the prose. A song named in prose but left out of that
list escapes today and still escapes.

## Slice 4 — Research grounding (`vet_research.py`)

**What:**

- **4a. Right-show gate on unknown songs.** `unknown song` flags are
  suppressed, and recorded instead as a `notes.json` note listing the
  unclaimed songs (ruling 6), when all of these hold:
  - at least `RIGHT_SHOW_MIN_TAPE_FRACTION` (0.5, fixed a priori) of the
    tape's resolved, non-filler tracks are asserted by research (`_known_song`
    in the tape-to-research direction). Tracks whose `title_source` is in
    `TAUTOLOGICAL_TITLE_SOURCES` count in neither numerator nor denominator:
    their text is the canonical's, so agreeing with research is circular;
  - at least 4 tape tracks are asserted, and research's unknown songs number
    no more than the asserted tracks; below that the ratio is not a
    measurement (`moontaxi-2010-04-15`);
  - fewer than half the tape's tracks are `unresolved`;
  - no wrong-date or placeholder-date flag fires, read **before** 4b
    suppresses any;
  - **research asserts the show's own full date**, year included (4b's
    definition).

  It **depends on 2b**: junk titles must already be unresolved, or a tape of
  `tmp` × 19 could pass the fraction test against a whole-performance setlist.
  `briefing_guard`'s independent bar on unknown songs **remains the safety
  net** (a song research asserts but the tape lacks still cannot appear in the
  briefing's `mentioned_songs`), with slice 3's prose limit. The suppressed
  songs stay visible in `notes.json`, which the brief prompt never reads.

  **What `research_vetted` then means, documented and not fixed:** "no
  contradiction found", so the packaged `research.md` may name songs the tape
  lacks. emcee's scriptwriter reads `briefing.md` and the manifest, not
  `research.md` (`emcee/scriptwrite.py`), and `script_guard` checks the
  script's `mentioned_songs` against the manifest's tracks. Such a song can
  reach air only through prose neither guard reads.
- **4b. Adjacent-day dates are context.** When research asserts the show's
  own full date, year included, another asserted full date within one day of
  it is context, not a contradiction (a post-midnight spill or an adjacent
  night). Every other date still flags: research arguing a tape is misdated
  states both dates, so a wider rule clears exactly the shows the flag exists
  for, as the prototype's did (`smashingpumpkins-1993-09-03`, "almost
  certainly wrong… 21 February 1994"; `gratefuldead-1966-02-25`, real date
  1966-03-12; `warrenzevon-1978-04-24`, item notes say 1978-02-24). Misdating
  also happens within a day (`derektrucksband-2005-06-17`, June 16 or 17),
  which is why every 4b clear is read by hand.
  Dates further out go to the LLM date adjudicator under "Next". Date adoption
  on placeholders is unchanged.
- **4c. `normalize_date` range checks.** It produces an invalid ISO date on 4
  stored assertions today; only `ryanadams-2008-11-16`'s `16/11/08` (read as
  `2008-16-11` and flagged, though it is the show date day-first) matters. An
  output with month > 12, day > 31 or day 0 is invalid. If swapping day and
  month makes a slash form valid, it is read day-first, since that reading is
  unambiguous; otherwise the date is unparseable and skipped, like every other
  unparseable date.
- **4d. Prompt wording.** `vet_research.md` item 1 asks for the songs "on this
  recording". This affects only fresh extractions, and `reapply` never
  re-extracts, so 4d is **unmeasurable offline and changes nothing in this
  backlog**. It ships for future shows; `redo --from vet` re-extracts for an
  existing show, as today.

**Estimates.** 4a: 120 shows, 79 sole. 4b: 37, 30 sole *(survey)*. Prototype
(rules differed; expect fewer): 4a clears 67 shows beyond 2a+2b; 4b removes
37 flags and clears 26.

**Acceptance.**

- For 4a, the harness lists every newly cleared show with its ratio, its
  absolute counts (asserted tracks, unknown songs), the unclaimed songs and
  the research date line. Every 4a clear is hand-checked for wrong-show
  research when there are at most ~150, ranked by absolute counts as well as
  ratio. **Decision point (owner):** if the 0.5–2/3 band contains one
  wrong-show research, the constant moves to 2/3 *before* shipping, never
  after.
- For 4b, every cleared show's research date discussion is read by hand.
- For 4c, the four instances, with exactly `ryanadams-2008-11-16` changing.

## Slice 5 — Structure guards

**What:**

- **5a. Numbered sets only.** `evidence_sets` counts numbered sets only,
  matching `structure_guard`'s own docstring and its jerrybase leg, which
  already exclude the encore. With no break, a tape still falls through to the
  long-show check; the prototype shows that net working (26 multi-set flags
  removed, 6 shows picking up "single-set structure for a long show" instead,
  6 clearing). **Exception:** the multi-set flag stays when the canonical has
  an encore and either an encore item is unmatched or a tape track carries an
  encore marker, because then the flag is the only signal that alignment lost
  the encore. 3 of the prototype's 6 clears were this case
  (`littlefeat-2002-08-22` `E] Willin' >`, `soundtribesector9-2005-01-21`
  `E: Rilly Wut?`, `derektrucksband-2007-12-31` `Crowd Encore Call > ...`).
  The marker test (a leading `E:`-style prefix, or the word `encore`) is local
  to this check and does not touch `_STRUCTURE_PREFIX`.
- **5c. Closer tripwire tolerance** (`jerrybase.py`):
  1. `closer_contradictions` does not hard-flag when every track between the
     closer and the next break is `is_filler` (tuning, crowd, `Donor Rap`),
     using the existing filler regex only; the survey's "< 7 min" short-track
     arm is **not** adopted a priori, and the harness reports what it would
     add;
  2. only when today's `anchor_breaks` returns nothing, it may anchor the
     numbered sets when every **numbered** closer matches exactly once and
     only the encore row's closer is missing. Tracks after the last numbered
     closer are labelled `encore` only where the deterministic alignment
     already said encore, or where they match the encore row's songs;
     otherwise they stay in the last set, with a `notes.json` note. Like
     jerrybase's own encore guard, this never invents an encore label;
  3. one fold drops a leading parenthetical (`(I Can't Get No)
     Satisfaction`), on both the closer and the track side. Typos (`Libery`,
     `Unlce John's Band`) stay failures.

  No other anchoring rule or constant changes, and `_resolve_positions` is
  untouched. 5c is prototyped on a harness branch before it ships.

**Estimates.** 5a: 26, 13 sole. 5c: 17 + 17, about 27 sole *(survey)*; **not
prototyped yet**, so its acceptance carries the full burden.

**Acceptance.**

- 5a: the cleared list with each show's canonical set count, minutes and
  description excerpt; every clear is hand-checked (ruling 1).
- 5c: every anchoring change is listed as old breaks → new breaks and
  hand-checked against the jerrybase event. Zero anchoring changes on shows
  that already anchored, which holds by construction because 5c.2 runs only
  when today's anchoring declines (the 2026-08-01 anchoring work's standard:
  "+148 newly anchor and not one show that already anchored changes"). No set
  label changes on non-target shows.

## Slice 6 — `llama reapply` (operator-triggered)

Flags are recomputed only when gather runs, so a cleared show leaves review
only when it is re-processed, and `llama redo` re-asks every LLM call
(Evidence). A dedicated command re-processes held shows with exactly the
harness's computation. `redo`, `fix` and `triage` keep today's semantics
(apart from slice 7's flag).

**The command.** `llama reapply <show>... | --from-list <file> [--dry-run]`
operates on held shows, in place. Per show, it holds `file_lock(show_ws.lock)`,
the per-show lock every single-show mutator takes, from the start of
computing through the last write. Under the lock, just before computing, it
re-checks that the show is still held and that its input digests still match
its row; otherwise it skips the show and reports it.

The steps compute in memory:

1. **gather**, LLM-free (slice 0). A needs-LLM show stops here, writes
   nothing, and is reported.
2. **vet**: the shared vet function (deterministic grounding plus the
   existing placeholder-date adoption) over the stored `vetting.json`
   extraction. No stored `vetting.json` means needs-LLM.
3. **brief**, only when steps 1 and 2 left no flag: the stored briefing is
   reused when `briefing.json` exists, the old and new `show.json` agree on
   every broadcast field (titles, sets, segues, date, venue, city), the
   briefing's recorded narration equals `overrides.narration`, and the stored
   briefing passes the new `briefing_guard`. Reuse applies 3a's normalisation
   and re-renders `briefing.md`. Otherwise one fresh briefing is generated:
   the only LLM work `reapply` does (Opus, a second call if its guard
   retries), under the pacing gate.
4. **package**: a first-time audio download for never-packaged shows.

Then it writes, in this order: `vetting.json`; `briefing.json` and
`briefing.md`; the package (audio and manifest, built from the briefing and
vetting just written); and **`show.json` last**, as the commit marker. Until
`show.json` is rewritten the show is still held, so it stays on every held
list. Nothing is committed on a failure, but a failure can leave a show
partly written; a re-run of the list completes it, because the digest check
covers only what `reapply` never writes before its commit (`show.json`,
`overrides.json`, `provenance.json`, `research.md`, and the extraction part of
`vetting.json`, which `reapply` re-grounds but never changes) and a show whose
`show.json` was not yet rewritten matches its row's digests. `briefing.json`
is an output, not a digest input: the reuse decision re-reads it under the
lock. Package's audio downloads are already atomic per
file.

A show still flagged after step 2, or whose fresh brief its guard holds, is
left held with its new flags written (`show.json` last) and no package: that
is the real outcome. A stored package-stage flag is carried through, and
`reapply` never clears one. `reapply` does not rewrite `reviews.json` or
`provenance.json` and writes no ledger record. On a show the ledger records as
delivered, it prints a reminder to re-deliver.

**Batch state.** `~/.llama/reapply/<hash of the list file>/`, outside `runs/`
so `llama run list` never sees it, holds the input list and an append-only
list of finished shows and outcomes. Re-running the same list finds it and
resumes, skipping finished shows. A failure other than a usage-limit refusal
is recorded as retryable, never as finished. A pacing gate runs before each
show (inert while `pacing-state.json`'s per-show cost reads `3.0e-11`; see
"Next"). A usage-limit refusal stops the batch cleanly at the show boundary
and prints the resume command, and the batch also stops after 3 consecutive
LLM failures of any kind (an openrouter 429 or an unrecognised refusal arrives
as a plain `HerderError`).

**Predicted lists are tied to what produced them.** Each row carries the
show's input digests (slice 0's set), and the list carries the git SHA and
config fingerprint of the harness run. `reapply --from-list` skips and
reports any show whose digests changed (an edit or a `llama get` since the
harness ran), and refuses the whole list if the SHA or config differ from the
running code.

**Cost, refined by the harness.** Only 55 of the 1,073 held shows have a
stored briefing (brief does not run on a show held at gather or vet), so
nearly every clear needs one fresh Opus brief: on the order of the clear
count, about 250, each checked by `briefing_guard` and not read. Add about
175 MB of first-time download per cleared show. Gather needs no fetch (0
cache misses) and no LLM call.

**Procedure.**

1. Run the harness: `compare` main versus the merged slices. It writes the
   predicted list (clears and needs-brief) and the needs-LLM and
   structure-changed lists.
2. Shawn reviews the hand-check lists: the samples, the closest calls, the
   title-source changes and every structure-changed show, which joins the
   apply only once checked. Every hand-checked list is drawn from exactly the
   shows `reapply` will clear.
3. `reapply --dry-run` over the list, then a 10-show pilot that compares
   predicted and actual outcome per show (briefing reuse versus fresh
   included), reports package-stage outcomes, and measures the real per-show
   cost, since `pacing-state.json` cannot size this batch.
4. The rest in waves under the pacing gate.
5. Re-run the harness. Every show whose actual flags differ from the
   prediction is listed; any difference on a `clears` show is a defect to
   explain.

**Acceptance.** On the pilot: predicted equals actual on the gather and vet
legs for every show, and on the brief leg (reuse versus fresh, and a reused
briefing's guard outcome); package-stage outcomes are reported. Zero network
calls outside package downloads, and zero LLM calls outside fresh briefs
(log-verified). A usage-limit refusal leaves the interrupted show
uncommitted and the rest of the list resumable by re-running it. A failure
during the package download leaves the show held, and a re-run completes it.
A show edited by `fix` or triage after its row was written is skipped.
Needs-LLM shows keep their digests.

## Slice 7 — Operator "untitled" resolution

**What.** Some tapes have no valid track names at all: wholly improvised sets
like `eotoband-2007-10-09`'s `Track 01`…`Track 09`, or tapes with no setlist
anywhere (about 24 shows, *survey*). `llama fix <show> --untitled`, and the
triage key `[u]`, are offered only when the show has no resolved titles at all
(every track `unresolved`). The confirmation prompt shows each track's
filename, so a tape whose filenames carry the titles
(`billystrings-2021-12-04`'s `01 Red Daisy.mp3`…) is not discarded unseen. On
confirmation it:

1. writes the overrides: `overrides.titles` `Untitled (track N)` for every
   track, N its track number; `overrides.narration` `vague`; and
   `overrides.set_breaks` `[]`, every track in one set, so gather's override
   path skips `align()` and never asks an LLM about "Untitled" tracks;
2. redoes from gather through vet. Gather and vet may raise flags (a single
   set on a long show, research songs unknown against "Untitled" titles);
   that is expected;
3. clears the hold the way `--overrule` does; the confirmation text says it
   overrules any remaining flags;
4. continues from brief through package.

The end state is packaged, not held, with `narration: vague`. It is
operator-triggered only: not a clearing rule, and not on the strict surface,
because a human confirms it. In one invocation it refuses `--suggest-titles`,
`--exclude`, `--unexclude` and `--include`, and also `--set-title`,
`--set-breaks`, `--set-encore`, `--narration` and `--overrule`, which it sets
itself. 2b never judges these titles, because they are overrides.

`eotoband-2007-10-09` is delivered with `tags` titles, so its route is
`llama redo <show> --from gather` (2b demotes its `Track NN` tags), then
`llama fix <show> --untitled`, then `llama deliver <show>`.

**Acceptance.** Tests pin that it is offered only when every track is
unresolved; that the prompt lists the filenames; that one confirmation writes
the titles, the narration and the single set; that gather makes no
`align_structure` call on the result; the end state (packaged, not held,
`narration: vague`) on a fixture whose gather and vet raise flags; the
refusals; and that the triage key appears only on such shows.

## Order and dependencies

Slice 0, with LLM-free gather, comes first. **2b must land before 4a.** 2a and
2b share the parse vocabulary without the selected recording's own
description, and the placeholder and timestamp classes, so whichever lands
first brings both. Slice 6 comes before any bulk apply. 1, 2c, 3, 4b, 4c, 5a,
5c and 7 are otherwise independent and ship in any order, each measured as
its own branch against main; 5c is prototyped on its branch first. The harness
gives a combined estimate only from a branch with every merged slice; overlaps
are real (the prototype's combined 350 is below the sum of the rows).

## New constants (fixed a priori, do not retune after the harness runs)

- `RIGHT_SHOW_MIN_TAPE_FRACTION = 0.5`, from the survey, changeable only at
  4a's decision point, before shipping; also 4a's minimum of 4 asserted tape
  tracks and its cap of unknown songs at the asserted count.
- 4b's one-day window.
- The metro alias table (4 entries, the survey's measured pairs), the city
  abbreviation folds, and the one-edit rule's 6-character floor.
- The 3c qualifier denylist, the negation words and their windows (2 words;
  4 for `instead of`, `expected`, `without`), and the scope phrases.
- 2b's placeholder vocabulary and residue token set; 2a's trailing-marker
  set, date pattern and residue tokens.
- `reapply`'s stop after 3 consecutive LLM failures.

Everything else is reused: `_ENUMERATED_MIN_*`, `guard_min_minutes`,
`is_filler`, `fuzzy_norm_title`, `metadata_norms`,
`TAUTOLOGICAL_TITLE_SOURCES`.

## Failure modes

- **A wrong short tag (2a).** A tag `42` that equals an item but belongs to a
  different track is no different from today's ordinary wrong tag: same
  protection, same exposure.
- **A same-city second performance (1c).** `gratefuldead-1978-11-17` is kept
  held by the two-venue exclusion, since recordings of both shows are in its
  candidate. A same-city double whose other performance left no recording
  still passes 1c with a note; the hand check is the only defence.
  Different-city doubles are caught by 1d. Step 1's short-circuit (the vote
  equals jerrybase) ships the jerrybase venue even when the selected tape is
  of a same-city second performance, exactly as today's check does; no such
  show is in this library.
- **Right-show research that is wrong-show anyway (4a).** A band with a stable
  repertoire can match half a tape from another night. The own-date
  requirement, the minimum count and the hand check mitigate it, and
  `briefing_guard` is the backstop. 4a reads the date flags before 4b
  suppresses any, so research about an adjacent night that mentions this
  show's date still disqualifies 4a.
- **A fresh brief (`reapply` step 3)** is checked by its guard, not read; its
  show is listed as needs-brief before the apply.
- **The junk detector demoting a real title**, mitigated by the corroboration
  and 4-digit exemptions; the library-wide demotion list is checked in full.

## Testing

TDD per slice in the repo's style:

- unit pins for every new predicate, with the near misses as negative cases
  (`1979`, `Song #1`, bare `Untitled`, `Untitled #12`, `3AM`, `?`, `07:22 - IB49`, `12-28-99`,
  `E1: Ripple`, "two electric sets", "two excellent sets" and "two sets that
  night" (both still claims), "no second set", `Portland, OR`/`Portland, ME`,
  `la`/`dallas`, `UCLA`/`UCSB`, `16/11/08`) and the attached markers `FF>`,
  `ML**`, `FF =>` as positive ones;
- a gather fixture per slice from a captured real item (`scripts/
  capture_fixture.py`): `thenewdeal2006-12-13` (short tags),
  `furthur2012-07-15` (all `tmp`), `railroadearth2013-11-30` (glued),
  `dso2003-01-25` with its Pageant sibling, a two-performance non-jerrybase
  date (`guster2003-07-10`), and the same-city double behind
  `gratefuldead-1978-11-17`;
- gather with no providers: needs-LLM reported on both LLM branches, and no
  call made;
- `reapply` on fixture shows: zero `vet_research` and `align_structure` calls;
  the briefing reused only when the broadcast fields and narration agree and
  the guard passes; nothing written on a needs-LLM show or on a refusal
  mid-show; `show.json` written last, and a show interrupted after an earlier
  write still held and completed by a re-run; the per-show lock held
  throughout, and a show edited between its row and the lock skipped; a show
  with changed digests skipped; a list from another SHA or config refused; a
  re-run of the same list finds its batch and skips finished shows but not
  failed ones; the batch stopping after 3 consecutive LLM failures; the
  re-deliver reminder on a ledger-delivered show;
- the harness on a two-show fixture library under a read-only root;
- mutation per the memory rules: name the expected red test before flipping a
  mutant, isolate `.pyc` per mutant, and run from the worktree's own
  interpreter.

## Unverified premises

- The survey's hand classifications (venue: about 20 hand-checked; research
  S1/S2/S3: a 16-show read) are not re-checked here; the harness hand checks
  replace them.
- Every prototype number (the rules differed, as Evidence lists), including
  how many clears are needs-LLM. Slice 0 re-measures them first.
- Slices 5c and 1d were not prototyped.
- Brief outcomes for needs-brief shows.
- Whether any junk-detected tape has a format sibling clearing 0.9 (counted by
  the harness, not yet).
- Code drift: 2 held and 9 clear shows replay differently under today's code
  for reasons unrelated to this spec. They are listed, not explained.

## Act now (found during design, outside the slices)

Operator actions, outside this spec's code. Each show's library audio has
been purged, so its fix re-downloads it, and the redo re-runs vet and an Opus
brief, which can hold the show again.

- **Wrong venue on air.** `belafleckandtheflecktones-2006-04-21`,
  `guster-2003-07-10` and `stuallenandmarshotel-2012-11-11` (delivered, not
  emcee-voiced) and `ginblossoms-2003-01-24` (packaged) carry another
  performance's venue; their own research.md names the right one (World Cafe
  Live, Philadelphia; the Minnesota Zoo; Moss House, Oakland; Canyon Club,
  Agoura Hills). Route:
  `llama fix <show> --set-venue … --set-city …`, then `llama deliver <show>`
  for the delivered ones. Their setlists may come from the wrong performance
  too, which `llama show` will show.
- **Placeholder titles on air**: the 6 shows in Evidence. Route: `llama fix
  <show> --set-title N=…`, then `llama deliver` for the delivered ones;
  `eotoband-2007-10-09`, which has no song titles, takes slice 7's route.
  `gratefuldead-1977-03-18` is emcee-voiced, so it needs `llama deliver
  --replace-voiced` (which discards its DJ script and audio) and then `emcee
  run`.
- **Duplicate tracks** in `gratefuldead-1972-11-18` (`Bertha > ...` and
  `Bertha \> ...`, 18 tracks for 9 songs) *(structure survey)*. The population
  is unchecked.

## Next (out of scope, later specs; survey estimates)

- **Canonical arbitration**, description against setlist.fm (`rank_parses`
  key 1 is `source == "setlist.fm"`): 52 low-confidence shows, about 37 sole.
  Also the canonical on two-performance dates (1d's held shows).
- **Refining slice 1's two-performance signature**, which fires on spellings
  of one hall and keeps swap-eligible shows held (`gratefuldead-1981-09-26`).
- **Tracklist, filename and disc-keyed title rungs**: draft
  `2026-10-19-tracklist-title-correspondence-design.md` (B2 up to 28 shows, B4
  11, B5 8, B7 2, B9a 10).
- **A `hygienic_title` clause for count-forced gap items** (about 20 shows):
  second-source corroboration for the silent gap adopter. Unprototyped, with
  no defined signature; re-propose it only with a measured yield, once 2a's
  remainder is known.
- **Parser inline set markers** (`Disc 2 (set II)`, `Set 2 1. ...`): about 15
  shows; 71 carry "Set 2" text while their structure has fewer sets.
- **LLM adjudicators**, which also take the needs-LLM shows Tier 1 leaves
  held: set breaks (about 100, 65 sole, plus about 55 keep-structure);
  research claims and dates (about 35, including dates outside 4b's window);
  title proposals into triage (about 90, proposal-only); structure F/K/M
  (about 45). The low-confidence flag on a single-set canonical (survey: 89
  qualify, 43 sole) belongs here too: that flag is raised only after gather
  reaches `align_structure`, so a deterministic demotion would clear nothing in
  Tier 1 and would act unseen on future gathers. If it is ever demoted, it
  needs at least one independently matched track (9 of the prototype's 32
  clears had none).
- **All-`setlist`-sourced count-forced tapes** (C): 17 sole. Needs a venue
  match against setlist.fm.
- **Bulk `--narration vague`** for unknowable structure (H 72, L 39). **Shawn
  wants to look at those shows first**; the harness emits the candidate list
  and nothing here acts on it.
- **A per-artist shorthand fold** (`J` → `Jam` for The New Deal) if it grates
  on air. `J` ships as the taper wrote it.
- **The pacing EWMA**: the learned per-show cost reads `3.0e-11`, which leaves
  the proactive gate inert. A separate small fix.
- **`fix` ordering**: `--narration vague` combined with a gather-stage edit
  clears the hold, then the re-gather holds the show again. (`--untitled`
  avoids this by clearing after the redo, slice 7.)
- **`fix` locking**: `fix` paths that write `overrides.json` or clear a hold
  do so without the per-show lock `redo` and `reapply` take. A pre-existing
  gap.

## Open questions for Shawn

1. 4a's band: 0.5 versus 2/3, decided at 4a's decision point from the hand
   check of the shows between the two (about 37 in the prototype), before 4a
   ships.

## Settled by the operator

- 1d's new city-conflict hold ships.
- `Untitled #12` is a real title (all four sources name it); `Untitled` is out
  of 2b's placeholder vocabulary.
- The narration-candidate list is a browsable page.
- The bulk apply's cost (about 250 fresh Opus briefs and about 175 MB of
  download per cleared show, on this backlog) is put to the operator again at
  apply time with the dry run's exact counts.
