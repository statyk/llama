# Title hygiene: fill unnamed tracks from trustworthy sources, stop positional junk

Status: draft for operator approval and spec review; not implemented.
Date: 2026-10-22.
Part of: the held-backlog work, part 1, piece 3 ("title hygiene").

Predecessors:
- Pieces 1 and 2: `2026-10-21-held-backlog-small-fixes-design.md` and `2026-10-22-taper-set-markers-design.md`.
- Tier 1: `2026-10-19-held-backlog-guard-fixes-design.md` (slices 2a and 2b).
- The unreviewed draft `2026-10-19-tracklist-title-correspondence-design.md`. This spec takes over that draft's *position key* (a description whose line count equals the file count) and its finding that the whole-tape `setlist` rung is live. Its number key and filename rung stay in that draft, untouched.

Evidence lives in `docs/superpowers/2026-10-22-title-hygiene-evidence/`:
- `census.py`, `dump.py`, `census-summary.json`, `census-handback.md`: a library-wide census. All 3,983 shows were replayed under 11dbffb with `overrides.titles` stripped, to see what a fresh get ships.
- `s_packets.py`, `s_rows.json`: the setlist-rung population.
- `handcheck/`: the brief and eight Sonnet hand-check outputs (per-show rows and handbacks).

These are model judgements, good for choosing rules and finding examples, not ground truth. Acceptance is measured by the replay harness plus a hand check of what changes.

## Kickoff

**Review mode: Fable** (operator ruling 2026-10-22): one Opus and one Fable reviewer on spec and plan; the Fable seat reviews the final branch. For this run this overrides "never silently upgrade".

**Stakes.** llama feeds an automated radio station. A track's title is spoken by the DJ and shown to listeners. The costly outcome is a WRONG title that ships with no review flag: it airs. The title cascade ("never guess, flag unresolved") exists to prevent that. `briefing_guard` and emcee's `script_guard` cannot see it, because both take the tracklist as the definition of truth. An unresolved title that holds a show is cheaper: it costs operator time. That is the resource this piece is meant to save, and the operator has said plainly that saving it must not come at the price of wrong titles.

**Strict surfaces:**
- (a) every path that adopts a title without operator confirmation (the three fills below);
- (b) never overwriting a real tape tag the cascade already trusts, an `override`, or a title an earlier rung adopted. There is one explicit exception: C2 (slice 3) chooses between the item's two tag sets AT THE TAG LAYER, before any rung reads them. So every later rung, and every anchor, sees the chosen tag; nothing is overwritten after the fact;
- (c) the do-not-retune constants and protected predicates listed under Constraints;
- (d) any change that adds holds. Each one must be justified by the wrong titles it stops, with the count of good shows it would hold.

## Intent (operator's words, 2026-10-22)

"My main goal here is to clear holds, as accurately as possible, without a ton of manual human intervention." "I am reluctant to make a change that will result in significantly more holds." "I'm not completely averse to adding holds to stop flagrantly wrong data from slipping through, but it depends on the specifics and the numbers." "If the setlist-rung check prevents an off-by-one error where all the tracks are wrong by one position, then that's worth holding." A correct title with a timestamp in it "is not a big deal."

The payoff is judged mainly by **future `llama get`s**. Most of today's held shows already carry overnight overrides, and the operator has not triaged the rest.

## What the measurement found (summary)

| Class | Population (current code, title overrides stripped) | Hand-check result |
|---|---|---|
| **D. Description is a numbered list, one line per file** | 85 shows; 698 unresolved tracks; 570 would get a hygienic title | 30 shows sampled. All-right 17, some-wrong 9, shifted 4. The gate in slice 2 blocked 12 of the 13 bad shows and fired on no good one (a normalized comparison is needed). The leak, furthur-2012-04-21, is untagged with a run-on description. |
| **C. Same item: lossless original vs MP3 derivative tags disagree** (format recovery did not fire) | 119 shows with different words (65 ship silently); 18 with an MP3 placeholder vs a real lossless title (furthur/DSO `tmp`); 36 with a blank MP3 vs a real lossless title | 30 sampled. Fix helps 19, neutral 8, hurts 3. All 3 hurts have a tell: bracketed banter labels, footnote markers, description fragments ending `(0:25):`. |
| **A_rev. Real short tags thrown away** (`J`, `420`, `M80`, `I-55`) | 74 shows, 95 tracks. 93 fail `is_real_title`, and 2a does not rescue them because the selected recording's own description is not a witness (2a ruling 3). The operator later set the same title by hand on 62 tracks. | 30 sampled. Keeping the tag: right 24, wrong 5. All 5 wrong are blocked by the gate in slice 4. |
| **S. Whole-tape `setlist` rung** (canonical count = file count and parse confidence not `low`; copy item N to track N; the only content check refuses `is_placeholder_text` items, `titles.py:475-502`; 93 of 128 canonicals from setlist.fm) | 128 shows; 77 ship unflagged | **All 128** checked. All-right 85, some-wrong 28, shifted 9, cant-tell 6. 16 bad shows ship silently. On 76 single-track fills the rung usually rescues a short real tag (`42`, `405`, `118`): right 60 of 76. |
| **A. Junk inside a title that passes as real** (`06:58 - Song`, `Band - d2t07-Song`, `S2: Song`) | 86 shows, 741 tracks; 35 silent | 30 sampled. Strip fixes it 15, not enough 9 (the taper's own `Track 11`, `track seventeen`, bare `01.`), would damage 6 (`4:20 Polka`, `8 Cylinders`, `1 Samuel 15:23`, `16 Military Wives`). |
| **B. Unknown-song flags that echo an untitled tape** | 266 shows | Not built. Collapsing them changes the hold reason, never the held state. They disappear on their own once the tracks are named. |

**The census counted problem instances, not holds cleared.** The net hold effect of the slices below is unknown until the replay harness measures it (see Acceptance).

## Goals

1. **Fill unresolved tracks automatically when a trustworthy source names them,** so the show is not held for `unresolved track titles`. The three fills are D, C1 and A_rev.
2. **Stop the positional rungs from shipping junk or shifted titles silently.** This covers S, and gives D the same protection. A track that fails the check stays `unresolved`, as it would have without the rung.
3. **Replace a stale lossy-derivative title with the item's own lossless title** when the evidence favours it (C2). It adds no holds.
4. Add-ons, smaller and separately sliced:
   - a taper's own placeholders that ship today as titles (`Track 11`, `track seventeen`, `Disc 1, Track 10`, a bare `01.`) become `unresolved`;
   - narrow cosmetic stripping of timestamp, filename and set-prefix junk from otherwise-right titles.

## Non-goals

- B (echo-flag collapsing).
- The draft tracklist spec's number key and filename rung.
- Siblings, partial tapes, shifted *tags* (piece 5).
- The junk filter (piece 4).
- Changing what counts as a structure hold, except as ruled under "Operator rulings" Q2 (self-filled tapes ship).
- Re-processing delivered shows. The bulk apply of pieces 1-3 is a separate, operator-gated step after merge.

## Anti-goals (failure even if it "works")

- A fill that ships shifted titles: every title one track late.
- A guard that holds the rung's correct single-track rescues (`42`, `405`, `118`, `2:45 AM`, `420`). Those are numbers and short strings, and a naive "junk title" test would catch them.
- Loosening `is_real_title` in place, widening `_TRACK_NUM_PREFIX`'s `\d{1,3}`, or retuning any do-not-retune constant to make a number move.
- A new hold class that fires on a meaningful share of good shows.

## Constraints and binding rulings

- **Taper notes are presumed correct unless clearly contradicted** (`llama-accuracy-philosophy`). "J" and "Untitled #12" are real titles. "Taper/description wording ships."
- **Predicates sit beside the protected ones, never loosening them.** This covers:
  - `is_real_title`, `_TRACK_NUM_PREFIX` (the `\d{1,3}` bound), `_STRUCTURE_PREFIX`;
  - `placeholders.py`'s 2b vocabulary ("fixed a priori: do not retune");
  - `_RECOVER_BELOW`/`_RECOVER_SIBLING_ABOVE`;
  - the sibling-align and tail-guard constants;
  - `songs.normalize_song`/`DEFAULT_ALIASES`.

  A new rung or check adds its own constants, fixed before measurement.
- **Accepted losses:** `100 Years`-style losses on enumerated tapes stay accepted.
- **Reviews:** titles from reviews only need confirmation; nothing here reads reviews.
- **Corroboration on the number-keyed tracklist rung stays** (operator ruling). Slice 2 is a position key, and an untagged tape gives it nothing on the tape side to corroborate with. Q1 rules where it may fill a wholly untagged tape.
- **Ordering:** no rung overwrites a track an earlier rung resolved, and no rung touches an `override`.
- **Notes:** operator notes go to `notes.json`, never into `structure.conflicts`, and never reach the briefing LLM.
- **Persisted models stay permissive.** A new `title_source` value must read cleanly on old show dirs and in emcee and transmitter. Neither branches on `title_source` today; the builder confirms this.

## The design

### Slice 1. One positional gate, shared by both positional rungs

Both the S rung (canonical item N to track N) and the new D rung (description line N to track N) call one predicate. It decides per track whether a positional candidate may be adopted. Some checks are per show (a show-level failure declines every positional fill on that show); others are per track. The checks:

1. **Candidate hygiene (per track).** The candidate, after `strip_taper_markers`-style cleanup of `>`, `->`, `*`, `@`, footnote parentheticals and a leading `E:`/`Encore:`/`Filler:`, must not be any of these:
   - empty, or containing no letter or digit (`?`, `??`, `???`);
   - a 2b placeholder (`Track N`, `track seventeen`, `tmp`);
   - a bare number equal to the track's position or zero-led (`01`, `01.`);
   - a set or disc header (`"Set" 1:`, `Set 2`, `Disc 1, Track 10`);
   - filename residue (`s1t07:`, `d2t07`);
   - a leading timestamp followed by `)`, `]` or ` - `;
   - an annotation line (starting `w/` or `with `, or containing `opened`).

   Short real titles pass: `42`, `405`, `118`, `2:45 AM`, `420`, `J`, `1 in 7`. **The hand-check's crude regex fired on 9 good S shows by treating bare numbers as junk.** The rule above rejects a bare number only when it equals the position or is zero-led. The builder must re-measure that rule against all 128 S rows before relying on it.

   **One definition.** `structure.py:1350-1361` requires every silent adopter to share `hygienic_title`. This check therefore reuses its parts: `MAX_TITLE_LEN`, `is_junk_title`, the trailing-`:` rule and the `metadata_norms` exclusion. It replaces only `hygienic_title`'s `is_real_title` requirement, so a short candidate qualifies when it passes 2a's shape (`tag_core` non-empty and alphanumeric, `is_junk_tag` veto). The builder may parameterize `hygienic_title` or compose a sibling predicate over its parts, but must not fork the parts. The S rung's existing `is_placeholder_text` refusal and `confidence != "low"` gate stay; this check is a superset of them.
2. **No adjacent duplicate (per show).** No positional candidate may equal the title of the track before or after it, after normalizing with `fuzzy_norm_title` plus a spelling fold that catches `Sailing On` vs `Sailin On`. This is the shift signature (derektrucksband-2007-05-27, robertrandolph-2005-05-29, particle-2003-06-14, gratefuldead-1972-04-26, railroadearth-2007-01-28). **One hit declines EVERY fill that rung would make on the show,** not just the duplicate track. On a shift, the rest of the run is wrong too; declining only the duplicate would leave one-late titles in place for the operator to inherit (operator, 2026-10-22: an off-by-one where all tracks are wrong "is worth holding"). A song genuinely split across two files also trips it, and holding that is acceptable.
3. **Tape agreement (per show).** Every non-filler track carrying an independent real title must agree with the list line at its position, by `loosely_same_title` after slice 1's cleanup. The independent sources are `tags` (including 2a's accepted short tags), `sibling-format`, `override` and `sibling-align`. A filler track (`is_filler`) agrees when its line is filler too, and otherwise counts as neither agreeing nor disagreeing. One disagreeing track declines every positional fill on the show. This catches D's shifted and scrambled shows (gracepotter-2009-07-26, gratefuldead-1983-09-04, zwan-2001-12-13). The census's crude count (28 of 85 D shows with at least one disagreement) is an upper bound under strict string equality; the Checkpoint A yield gate measures the real figure.
   - **Applied to D, and to S only when S's canonical came from the selected recording's own description** (`canonical_source == "chosen"`). On a setlist.fm canonical it misfires on about 8 good S shows, because setlist.fm names differ from the taper's (GY!BE aliases, spelled-out numbers).
   - The comparison must be normalized: umphreysmcgee-2004-03-17 `Joel Piano Solo (02:05)` vs `piano solo^` must not fail it.
4. **Description presence (per track, S only, measured before adoption).** When the selected description contains a setlist, the copied canonical title must appear in its text, via `structure.contains_sequence`, which is fuzzy and order-free for a single title. This targets the silent S failures where setlist.fm disagrees with the taper (stevekimockband-2000-03-31 and -04-01, loslobos-2024-06-14, buttholesurfers-1988-11-22). It is **unscored**: spelling variants (`Rock You` vs `Rock It`) would misfire. Ship it only if the measurement shows it holds no more good shows than it saves.

**A track that fails the gate stays `unresolved`.** That is the state it would have been in without the rung, so the existing `unresolved track titles` hold catches it, and no new flag string is needed. Each declined track writes one operator note (rung, position, which check fired, the candidate).

**Expected S effect:** checks 1 and 2 catch about 8 of the 16 silent bad S shows; check 4 may catch more. About 6 bad S shows cannot be caught from the show's own data. Examples: mountaingoats-2008-10-21 (no tags, no description), joerussosalmostdead-2023-10-13, where only the filenames carry titles (the filename check is the draft spec's), and leftoversalmon-1996-03-16, where only a sibling's durations prove it. Those stay accepted limitations.

### Slice 2. The description position rung (D)

**Source.** The SELECTED recording's own description. The taper's list is the evidence; setlist.fm is never the source here. The rung reads a list of entries from it, and there are two admissible lists:
- **(i) numbered lines:** lines or `<br />`-separated entries that each start with a number. The numbers must run 1..N contiguously, or restart at 1 per set or disc (`Set 2 1. Water of Love`). This is the taper's own numbering; the rung never compares entry numbers against file numbers, because S0 found that misfires on derektrucksband-2004-11-20.
- **(ii) `parse_setlist`'s own items** for the selected description, when that description gives one item per line (or per `<br />`).

**A list taken from a single run-on line is never admissible.** furthur-2012-04-21, the one untagged leak, came in this way. `parse_setlist` mis-counts most of these lists (60 of the census's 85 came through (i) only). The builder decides whether (i) is a new reader or `parse_setlist` keeping per-entry text additively, as the draft spec proposes. Either way, `parse_setlist`'s existing outputs and every consumer of them stay byte-identical. When both lists qualify and differ, prefer (i).

The census's 85 shows and 570 tracks were computed with `hygienic_title` and with run-on lists included. The yield gate re-measures under these rules.

**When it fires.** The entry count equals the kept track count, and the show has at least one still-`unresolved` track after every earlier rung. It runs after `adopt_gap_titles`, 2a (`accept_short_tags`) and slice 4, before `align()`. Slice 4 goes first because it ships an independent tag; a track D filled would be tautological and out of coverage. It never touches a resolved track or an override.

**What it ships.**
- The entry text, cleaned like slice 1's hygiene step (taper markers, trailing tab-plus-duration, `(GA)`-style initials kept per "taper wording ships", leading `E:`), for each unresolved track that passes slice 1's gate.
- The new `title_source` is `description-position`.
- A compound entry (`Pyramid County (1) > Little Maggie`) ships as the taper wrote it, segue marker cleaned.

**Tautology.** The fill IS the description's own text. Canonical setlists are often built from that same description, so `description-position` joins `TAUTOLOGICAL_TITLE_SOURCES`: excluded from coverage, `matched=None`. On a partly-tagged tape, coverage is measured over the tagged tracks as today. On a wholly description-filled tape, the independent set is empty and coverage reads 0.0. What happens next depends on the branch (`gather.py:1361-1456`):
- **Jerrybase anchoring resolves** (Garcia-family shows; `anchor_breaks` matches closers whatever the `title_source`, `jerrybase.py:257`), or the canonical is empty: no structure flag, and the hold clears. 12 of the census's 85 D shows are family shows.
- **Otherwise** (`today_llm`, `gather.py:1386`): gather spends one `align_structure` LLM call. That call cannot win, because `apply_llm_alignment` also excludes tautological tracks (`structure.py:1248`). Gather then raises `low-confidence structure alignment` and the show stays held. Replay marks these shows needs-LLM.

**Operator ruling Q2 changes this:** a tape whose every song-like track was filled from the selected description ships. Gather skips the doomed LLM call and raises no low-confidence flag. See Operator rulings.

**Wholly untagged tapes.** Gate check 3 is vacuous on these tapes. 31 of the 85 D shows are wholly untagged. D may fill them (operator ruling Q1). The sample holds 15 of them:
- 11 all-right;
- 3 placeholder lists that slice 1's hygiene declines (fishbone-2011-02-27 `?`, pnuma-2005-05-09 timestamps, soulive-2012-02-24 filename stems);
- 1 run-on list that the run-on rule declines (furthur-2012-04-21).

Six of the 11 all-right ones came through `parse_setlist` items, not numbered lines, which is why (ii) is admissible.

### Slice 3. Per-track lossless titles from the same item (C)

`_recover_format_titles` is wholesale and gated at 0.5/0.9, and those constants stay. This slice sits beside it. It runs only when recovery did NOT fire and the filename-stem bijection with a lossless format of the same item holds, the same bijection `titles.sibling_format_titles` builds.

**Placement: the tag layer, per track,** before `resolve_titles` and therefore before the S rung, overrides, sibling-align, setlist-gap and 2a. The chosen tag IS the tag every later rung and anchor reads. The consequence is intended. For the 39 blank-MP3 stems that S (19), setlist-gap (15) and sibling-align (5) fill today, the item's own lossless tag wins over a positional or cross-item fill. derektrucksband-2007-05-27 t1 becomes `Announcements/crowd`, which is right, instead of S's wrong `Sailing On`. A merged title from C carries `title_source=sibling-format` per track, so a manifest may now mix `tags` and `sibling-format` tracks. That differs from wholesale recovery, which never interleaves sources; nothing downstream branches on it (emcee and transmitter checked).

Per stem:

- **C1, fill.** The delivered tag is blank, fails `is_real_title`, or is a 2b placeholder (`tmp`), and the lossless tag is a real, hygienic title. Ship the lossless title, `title_source=sibling-format`. This is the furthur/DSO `tmp` class: 18 shows, and with the blank-MP3 class, 36 more. It clears holds.
- **C2, replace.** Both tags are real and differ substantively (not case, punctuation, whitespace or `normalizes-equal`), and the lossless tag agrees with the description text or the canonical while the delivered tag does not. Ship the lossless title. It adds no holds. It fixes silent errors like radiators-1991-11-01 (`No Skin Off My Back` on what is `Mood To Move`).
- **Never** take a lossless tag that is:
  - bracketed (`[Banter]`, `[John's Still Got Some Gas…]`);
  - ending in `:` or `(m:ss):`;
  - the delivered title plus only a trailing symbol marker (`@ ^ * #`).

  Under the first two, builttospill-1997-10-13 and mountaingoats-2017-06-02 decline. Under the third, greensky-2014-07-18 keeps its clean title.
- **Show-level decline:** skip C for the show when two or more lossless tags each equal (by `loosely_same_title`, after slice 1's cleanup) the selected description's entry at position ±1 but not at their own position, as builttospill-1997-10-13 shows. The test applies only when the description yields an admissible slice-2 list; without one this decline cannot fire, and the per-tag vetoes above still apply.

C1 and C2 write one operator note per changed track. `LOSSLESS_TITLE_FORMATS` is read-only and unchanged.

### Slice 4. Short real tags confirmed by the taper's own list (A_rev)

This extends 2a (`accept_short_tags`) with one more witness: **the selected recording's own description, at the same position.** That relaxes 2a's ruling 3 ("never the selected recording's own description") under a stricter, positional condition (operator ruling Q3: yes). A still-`unresolved` track whose tag fails `is_real_title` and is not 2b-demoted is accepted when all of these hold:

- its core (`tag_core`) equals, by `fuzzy_norm_title`, the WHOLE description entry at the same position. Same reader and count condition as slice 2: entry count = kept track count;
- among the tracks within ±2 that carry real tags, at least one agrees with its entry at its own position and none disagrees. This blocks robertwalters `VA` (the comma-split "Quantico, VA") and zwan's scramble. With no real-tagged neighbour within ±2, the slice does not fire;
- the core is not a token of the file's own stem (`d206` on jackiegreene-2011-12-31);
- 2a's existing junk veto (`is_junk_tag`) and its `metadata_norms` exclusion still apply. That knowingly keeps out GY!BE's `12.28.99`/`12-28-99` (date-shaped, 7 tracks) and `2:22`, which the hand-check rated right. This is the author's call; the operator may overrule.

Slice 4 runs after 2a and before slice 2 (see slice 2).

It ships `shipped_short_tag(tag)`, as 2a does today, which strips segue arrows and footnotes from `X >`, `415 ->`, `7-11 (3)>`. It fills only `unresolved` tracks. moe-2008-01-26 and discobiscuits-2006-08-26 show why: a better title already shipped there.

**Not caught:** godspeedyoublackemperor-2011-03-15, where tag and description agree but durations show the file is mostly another piece. That is 1 in 30, an accepted limitation.

### Slice 5 (add-on). Placeholders that ship as titles

These titles ship today as if they were songs:
- a taper's own placeholders that 2b's vocabulary does not catch: `Disc 1, Track 10`, `Track One`, `track seventeen`, `Track 11` where 2b's cross-source protection kept them;
- bare list numbers (`01.`) from the whole-tape rung. Slice 1 already declines these.

They become `unresolved`, which means a hold unless slices 2-4 fill the track. 2b's vocabulary stays fixed. This is a separate, narrow class beside it, fixed before measurement. **It adds holds, and the measurement must report how many before it ships.**

### Slice 6 (add-on). Cosmetic junk stripping

Strip only these shapes from a tag-layer title:
- a leading `m:ss` or `h:mm:ss` followed by `)`, `]` or ` - `;
- an embedded identifier/date/disc-track stem (`d&co2017.06.17.mg21.set01t01`, `dNNtNN-`, `sNtNN`);
- a leading set marker (`S2:`, `set1:`, `E:`);
- a `.wav`/`.flac` tail, and a pasted `.flac:<md5>` tail.

The result must be non-empty, pass `is_real_title` (or 2a), and not be a placeholder. Otherwise the title is left exactly as it was. **Never strip** a bare `m:ss Word` (`4:20 Polka`), a spaced leading number (`8 Cylinders`, `16 Military Wives`, `20 Eyes`, `3 AM`), or a number inside a title (`1 Samuel 15:23`). The `NN-` joined prefix is already handled by 2d; it does not need to equal the position (ryanadams runs 02..26 on positions 1..25). Slice 6 changes shipped strings and never a hold.

## Acceptance

All measurements use the replay harness and the census tooling from the merged tree, compared with 11dbffb. The census's `dump.py` and `census.py` are the starting instruments; the builder versions what it uses. `scripts/replay_holds.py` has no mode that strips `overrides.titles` (only `--strip-structure-overrides`), so the plan adds one (`--strip-title-overrides`, read-only, no apply lists) or measures the "fresh get" view with `dump.py`.

1. **Yield gate before wiring.** This is piece 2's lesson. Each slice's rule runs offline over `dump.jsonl`, scored against the hand-check rows, before gather is touched. Report per slice:
   - tracks filled or changed;
   - the hand-checked wrong count among them;
   - good shows newly held;
   - bad shows newly held.

   Checkpoint A (operator) sees this table.
2. **Per slice, after wiring, over the whole library** (`--all`, title overrides stripped AND as-is):
   - **holds cleared**, split three ways: held now / would-hold on a fresh get / currently packaged;
   - **holds added**, and their flag;
   - **titles changed on shows that stay unheld**, split by state (packaged / delivered / voiced).
3. **Hand check** by Sonnet with an Opus pre-screen: every newly cleared show, or a stratified 60 if there are more, and every changed title on a delivered show. This is a hold-clearing change, and a cleared hold is the strict surface.
4. **Accuracy bar (operator ruling Q4):**
   - wrong titles ≤ 2% of the tracks the slices fill automatically (the house standard: gap-fill 2.4%, sibling-align 1.9%);
   - zero shifted shows among those newly cleared;
   - slice 1 holds no more than 2 hand-checked-good S shows.
5. Suite green from the worktree's own venv. `test_align_default_lookahead_is_8` and the other pinned constants are untouched.

## Operator rulings (2026-10-22)

- **Q1. Wholly untagged tapes.** The **taper's own description list may fill a wholly untagged tape by position** (slice 2), under the count match plus slice 1's hygiene, no-duplicate and run-on checks. The **S rung may NOT fill a wholly untagged tape when its canonical did not come from the selected recording's own description** (setlist.fm, or a sibling item's description). There every S candidate is declined, and the tracks stay `unresolved`. In the hand-check, those fills were 18 right of 38 whole-tape fills, against D's 11 of 15. The ruling adds about 13 holds, which stop 5 silent bad shows. When S's canonical IS the selected description (`chosen`), S is treated as D and gets the full slice 1 gate, check 3 included.
- **Q2. Self-filled tapes ship.** The operator: "Let them ship. I consider the setlist in the item description more reliable than track tags, as the uploader is probably more likely to revise and correct the description than the file tags." The case: a tape where no song-like track carries an independent title, because every one was filled from the selected description (`description-position`, or S with a `chosen` canonical), each passing slice 1's gate. On such a tape gather neither spends the `align_structure` LLM call nor raises `low-confidence structure alignment`. Set breaks come from piece 2's taper rule when it owns the structure, else jerrybase anchoring, else the deterministic alignment as today. The exception is deliberately narrow: a tape with ANY independent title, or with any track filled from setlist.fm or a sibling, keeps today's coverage rule and flag.
- **Q3. A short name in the taper's list confirms the same short tag** (slice 4), at the same position with an agreeing neighbour. The operator: "yes, of course." This relaxes 2a's ruling 3 for that positional condition only. 2a's cross-source rule is unchanged otherwise.
- **Q4. Accuracy bar accepted:** at most 2% wrong among automatically filled tracks, and zero shifted shows among those newly cleared.
- **Review mode: Fable** (operator, "Opus/Fable for this round"): one Opus reviewer and one Fable reviewer on spec and plan; the Fable seat also reviews the final branch. For this run that overrides "never silently upgrade".
- **Standing principle recorded with Q2:** where the selected description and the tape's own tags disagree about a title, the description is presumed the more reliable of the two. This piece applies it in two places: check 3 still DECLINES a positional fill on any disagreement, because a disagreement at a position is the signature of a shifted list, not evidence about which title is right; and C2 prefers the lossless tag only when it agrees with the description.

## Author's calls (settled after the builder check; the operator may overrule)

- C sits at the tag layer and beats later positional and cross-item rungs on its stems (slice 3).
- An adjacent duplicate declines every positional fill on the show, not just the one track (slice 1, check 2).
- Check 3 counts `sibling-align` and 2a's tags as independent, treats filler as neutral, and applies to S when S's canonical is the taper's own description.
- D admits `parse_setlist` items only when there is one item per line, never from a run-on line. Contiguity is the taper's own numbering, never compared with file numbers.
- Slice 1 hygiene reuses `hygienic_title`'s parts and relaxes only its `is_real_title` requirement.
- Slice 4 runs before D, and needs at least one agreeing real-tagged neighbour within ±2. It keeps 2a's date and timestamp veto, which knowingly keeps out GY!BE `12.28.99` and `2:22`.

## Left to the builder

- Module layout.
- Whether the D reader is new or a `parse_setlist` additive field.
- The exact spelling fold for check 2.
- Constant values the spec does not fix. Fix them before measurement and record them.
- Note wording.
- Slice order inside the plan, with one fixed rule: slice 1 lands before or with slice 2.
- Test fixtures, from the hand-check's named shows. Captured real metadata, offline.
