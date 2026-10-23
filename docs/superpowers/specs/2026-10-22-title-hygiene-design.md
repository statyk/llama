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
- `untagged_packets.py`, `untagged-index.json`: the untagged population (class U) and its hand-check packets.
- `handcheck/`: the brief and the Sonnet hand-check outputs (per-show rows and handbacks): eight for the classes D, C, A_rev, S and A, and `U0`–`U3` for class U.

These are model judgements, good for choosing rules and finding examples, not ground truth. Acceptance is measured by the replay harness plus a hand check of what changes.

## Kickoff

**Review mode: Fable** (operator ruling 2026-10-22): one Opus and one Fable reviewer on spec and plan; the Fable seat reviews the final branch. For this run this overrides "never silently upgrade".

**Stakes.** llama feeds an automated radio station. A track's title is spoken by the DJ and shown to listeners. The costly outcome is a WRONG title that ships with no review flag: it airs. The title cascade ("never guess, flag unresolved") exists to prevent that. `briefing_guard` and emcee's `script_guard` cannot see it, because both take the tracklist as the definition of truth. An unresolved title that holds a show is cheaper: it costs operator time. That is the resource this piece is meant to save, and the operator has said plainly that saving it must not come at the price of wrong titles.

**Strict surfaces:**
- (a) every path that adopts or changes a title without operator confirmation: C1, C2, D, slice 4, the changed S rung and slice 5;
- (b) never overwriting a real tape tag the cascade already trusts, an `override`, or a title an earlier rung adopted. There is one explicit exception: C2 (slice 3) chooses between the item's two tag sets AT THE TAG LAYER, before any rung reads them. So every later rung, and every anchor, sees the chosen tag; nothing is overwritten after the fact;
- (c) the do-not-retune constants and protected predicates listed under Constraints;
- (d) any change that adds holds. Each one must be justified by the wrong titles it stops, with the count of good shows it would hold;
- (e) the Q2 self-filled exemption (slice 2): it ships a structure with no structure flag.

## Intent (operator's words, 2026-10-22)

"My main goal here is to clear holds, as accurately as possible, without a ton of manual human intervention." "I am reluctant to make a change that will result in significantly more holds." "I'm not completely averse to adding holds to stop flagrantly wrong data from slipping through, but it depends on the specifics and the numbers." "If the setlist-rung check prevents an off-by-one error where all the tracks are wrong by one position, then that's worth holding." A correct title with a timestamp in it "is not a big deal."

The payoff is judged mainly by **future `llama get`s**. Most of today's held shows already carry overnight overrides, and the operator has not triaged the rest.

## What the measurement found (summary)

| Class | Population (current code, title overrides stripped) | Hand-check result |
|---|---|---|
| **D. Description is a numbered list, one line per file** | 85 shows; 698 unresolved tracks; 570 would get a hygienic title (both upper bounds) | 30 shows sampled. All-right 17, some-wrong 9, shifted 4. The gate blocks 12 of the 13 bad shows; furthur-2012-04-21 is among them, because no reader admits its run-on description. It also declined one all-right fill, darkstarorchestra-2014-07-31, whose own tags are shifted, a hold the checker judged justified. The one leak is godspeedyoublackemperor-2011-03-15: `12-28-99` passes hygiene, and the file is mostly Gathering Storm. That is an accepted limitation. |
| **U. Effectively untagged tape with a count-matched description list** | 202 of 3,980 shows (5.1%) have fewer than 2 independent song-like titles; 50 (1.3%) also have a count-matched description list | **All 50** checked. All-right 34; 12 lists that are not titles, declined by hygiene; 1 with set-header lines, declined by the header rule; 1 run-on (furthur-2012-04-21), declined; 2 shifted, both caught by slice 2's block-size check. Neither untagged check fired on a right show. |
| **C. Same item: lossless original vs MP3 derivative tags disagree** (format recovery did not fire) | 119 shows with different words (65 ship silently); 18 with an MP3 placeholder vs a real lossless title (furthur/DSO `tmp`); 36 with a blank MP3 vs a real lossless title | 30 sampled. Fix helps 19, neutral 8, hurts 3. All 3 hurts have a tell: bracketed banter labels, footnote markers, description fragments ending `(0:25):`. |
| **A_rev. Real short tags thrown away** (`J`, `420`, `M80`, `I-55`) | 74 shows, 95 tracks. 93 fail `is_real_title`, and 2a does not rescue them because the selected recording's own description is not a witness (2a ruling 3). The operator later set the same title by hand on 62 tracks. | 30 sampled. Keeping the tag: right 24, wrong 5. All 5 wrong are blocked by the gate in slice 4. |
| **S. Whole-tape `setlist` rung** (canonical count = file count and parse confidence not `low`; copy item N to track N; the only content check refuses `is_placeholder_text` items, `titles.py:475-502`; 93 of 128 canonicals from setlist.fm) | 128 shows; 77 ship unflagged | **All 128** checked. All-right 85, some-wrong 28, shifted 9, cant-tell 6. 16 bad shows ship silently. On 76 single-track fills the rung usually rescues a short real tag (`42`, `405`, `118`): right 60 of 76. |
| **A. Junk inside a title that passes as real** (`06:58 - Song`, `Band - d2t07-Song`, `S2: Song`) | 86 shows, 741 tracks; 35 silent | 30 sampled. Strip fixes it 15, not enough 9 (the taper's own `Track 11`, `track seventeen`, bare `01.`), would damage 6 (`4:20 Polka`, `8 Cylinders`, `1 Samuel 15:23`, `16 Military Wives`). |
| **B. Unknown-song flags that echo an untitled tape** | 266 shows | Not built. Collapsing them changes the hold reason, never the held state. They disappear on their own once the tracks are named, except that vet's 4a cannot rescue unknown-song flags on tracks that count as tautological (`vet_research.py:194-199`), and D-filled tracks are tautological (slice 2). |

**The census counted problem instances, not holds cleared.** The net hold effect of the slices below is unknown until the replay harness measures it (see Acceptance). The census's "ships silently" counts strip only title overrides; the yield gate recomputes them on the fresh-get view (Acceptance).

## Goals

1. **Fill unresolved tracks automatically when a trustworthy source names them,** so the show is not held for `unresolved track titles`. The three fills are D, C1 and A_rev.
2. **Stop the positional rungs from shipping junk or shifted titles silently.** This covers S, and gives D the same protection. A track that fails the check stays `unresolved`, as it would have without the rung.
3. **Replace a stale lossy-derivative title with the item's own lossless title** when the evidence favours it (C2). It adds no holds.
4. Add-on, smaller and separately sliced: narrow cosmetic stripping of timestamp and filename junk from otherwise-right titles (slice 5).

## Non-goals

- B (echo-flag collapsing).
- The draft tracklist spec's number key and filename rung.
- Siblings, partial tapes, shifted *tags* (piece 5).
- The junk filter (piece 4).
- Changing what counts as a structure hold, except as ruled under "Operator rulings" Q2 (self-filled tapes ship).
- Re-processing delivered shows. The bulk apply of pieces 1-3 is a separate, operator-gated step after merge.
- `llama fix`/`redo`/triage auto-redo re-gathers a show under the new rules, so a delivered show edited for any reason picks up piece-3 changes; that is the existing re-gather contract, documented, not changed.

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
  - the sibling-align constants (`siblings.MIN_ANCHORS` among them) and the tail-guard constants;
  - `songs.normalize_song`/`DEFAULT_ALIASES`, and every matching-layer normalizer (`fuzzy_norm_title`, `loosely_same_title`).

  A new rung or check adds its own constants, fixed before measurement.
- **Accepted losses:** `100 Years`-style losses on enumerated tapes stay accepted.
- **Reviews:** titles from reviews only need confirmation; nothing here reads reviews.
- **Corroboration on the number-keyed tracklist rung stays** (operator ruling). Slice 2 is a position key, and an untagged tape gives it nothing on the tape side to corroborate with. Q1 rules where it may fill a wholly untagged tape.
- **Ordering:** no rung overwrites a track an earlier rung resolved, and no rung touches an `override`.
- **Notes:** operator notes go to `notes.json`, never into `structure.conflicts`, and never reach the briefing LLM.
- **Persisted models stay permissive.** A new `title_source` value must read cleanly on old show dirs. The manifest has no `title_source` field (`models.py:267-273`); only llama readers (`llama show`, replay's `shipped_diff`) see it.

## The design

**Definitions.** These terms mean the same thing everywhere below.
- **Independent title:** a title from `tags`, `sibling-format`, `override` or `sibling-align`, or a short tag accepted by 2a or slice 4.
- **Real tag:** a tag that passes `is_real_title` and is not `is_placeholder_text`.
- **2a shape:** a tag whose `tag_core` is alphanumeric, is not `is_junk_tag`, and is not a placeholder (the short real tags `J`, `42`, `M80`).
- **Song-like:** not `is_filler`.
- **Admissible list:** a list read from the selected recording's description by slice 2's reader (i) or (ii). A **count-matched** admissible list also has exactly as many entries as the tape has kept tracks; every positional use below (D, the S rung's yield, C's same-position references and its show-level decline) needs a count-matched one.
- **Entry** (slice 4): a list entry after slice 1's cleanup.
- **Wholly untagged:** fewer than `siblings.MIN_ANCHORS` (2) independent song-like titles at the tag layer. Slice-4 tags do not count here, nor in Acceptance's 100% hand-check stratum. This reuses an existing constant; it is never retuned.
- **Self-filled:** the predicate defined under slice 2, "Self-filled tapes".
- **Real-tagged neighbour** (slice 4): a track carrying an independent title.
- **Agree** (C1(c)): the two tags are equal under case, punctuation or `normalizes-equal`, or `loosely_same_title` holds; cores under 3 letters compare by equality only.

### Slice 1. One positional gate, and where the S rung fires

**The S rung splits by canonical source.**
- **S with a `chosen` canonical** (the canonical came from the selected recording's own description) no longer fires inside `resolve_titles`. That is the same evidence as D, and the D rung (slice 2) handles it with reader (ii). Those fills move from `resolve_titles` to D's slot, after slice 4 and before `align()`. The yield gate re-counts the S population under this placement.
- **S with any other canonical** (setlist.fm, a sibling item's description, an `extract_setlist`/LLM canonical) stays inside `resolve_titles`, at its current place. It is gated by check 1 (hygiene) and check 2 (adjacent duplicate), with check 2 evaluated against the tag-layer titles and the other S candidates, which is what exists at that point. It has two more firing conditions:
  - **When the selected description yields a count-matched admissible list, S fills only where D does not.** The operator presumes the taper's list more reliable than setlist.fm. S's fills on such a show are settled once D has decided:
    - if D fills, S yields to it;
    - if D declined on a shift signature (check 2, check 3, written durations, either untagged check, or the agreement check), S declines too, and the show is held;
    - if D declined only on hygiene or admissibility grounds, S's own gates decide.

    The yield gate attributes the shows where S was withdrawn.
  - **It never fires on a wholly untagged tape** (operator ruling Q1).

  The yield gate also reports, for the operator, a stricter alternative: non-chosen S fills only runs bracketed on both sides by independent song-like titles (`gap_span`'s rule). It reports that alternative's added holds and the bad shows it would stop, but does not adopt it.

**D** (slice 2) is gated by checks 1, 2 and 3 below, the written-duration check, and slice 2's agreement and untagged checks.

**Show-level or per-track.** A candidate that fails check 1 as any of the following declines EVERY fill that rung would make on the show:
- a set or disc header;
- a `metadata_norms` hit on the first list entry (the banner position);
- an annotation line;
- filename residue, including a candidate equal to the file's own stem;
- a timestamp-shaped entry;
- an over-length entry.

Such an entry takes a slot, so the list is not 1:1 with the files. Only slot placeholders keep the list 1:1, so they decline per track: `?`-only, 2b vocabulary (`Track N`, `track seventeen`, `tmp`), `unknown`/`unk`/`(unknown)`, and a bare number that is zero-led or equals the position. A `metadata_norms` hit on any entry but the first also declines per track: it may be a self-titled or city-named song. Every other check-1 failure (`is_junk_title`, a trailing `:`, and the shapes above) is show-level. Checks 2 and 3, the written-duration check, the agreement check and the untagged checks are show-level.

**The checks.**

1. **Candidate hygiene.** Before every test, strip written durations and taper markers. A written duration is stripped wherever it sits: bracketed or trailing (`[4:47]`, `(6:40)`, tab plus `4:47`) or leading (`(05:12) `, `05:12 - `), so `1. (05:12) Bertha` yields `Bertha`. Taper markers are `>`, `->`, `*`, `@` and footnote parentheticals. The candidate is declined when it is any of these:
   - over `MAX_TITLE_LEN`, `is_junk_title`, ending in `:`, or in `metadata_norms`: `hygienic_title`'s parts except its `is_real_title` requirement;
   - `is_placeholder_text`: 2b's vocabulary, a bare timestamp, or pure filename residue (`is_residue`, gated on `is_real_title` as that predicate already is);
   - filename residue (`looks_like_filename`), or equal to the file's own stem;
   - a leading `m:ss` (or `h:mm:ss`) followed by `)`, `]` or ` - `, with an optional leading `(`, when nothing title-like remains after the duration strip;
   - empty, or containing no letter or digit after cleanup;
   - `unknown`, `unk` or `(unknown)`;
   - a set or disc header (`"Set" 1:`, `Set 2`, `Disc 1, Track 10`);
   - an annotation line: `w/ …`, or a line containing `opened` (support-act notes);
   - a bare number, `^\d+[.\-)]?$` (so `01.` and `01-` are bare numbers, and `09-15-00` and `12.28.99` are not), unless it equals the track's own raw tag core (`tag_core`). Otherwise a bare number declines when it is zero-led or equals the position.

   `is_junk_tag` is NOT used: its leading-timestamp and date arms decline the real titles `2:45 AM` and `09-15-00`, which the hand-check rated right on elliottsmith-1998-06-02 and -1998-10-11 and on GY!BE 2002-01-22, 2002-04-03 and 2003-03-27.

   Fixtures that must PASS: `2:45 AM`, `09-15-00`, `12.28.99`, `42`, `405`, `118`, `420`, `J`, `1 in 7`. Fixtures that must DECLINE: `?`, `??,  [4:47]`, `01.`, `01-`, `"Set" 1:`, `Disc 1, Track 10`, `s1t07:`, `(05:12) 01-`, `w/ Eric Johnson`, `Fruit Bats opened`, `Unknown`, `soulive2012-02-24-d1t01`.

   A crude bare-number test fired on 9 hand-checked-good S shows. The rule above declines a bare number only when it is zero-led or equals the position, and never when it is the track's own tag core. The builder must re-measure that rule against all 128 S rows before relying on it. The `metadata_norms` exclusion stays, so there is one definition; the yield gate counts the self-titled songs it declines (`Railroad Earth`).

   **One definition.** `structure.py:1350-1361` requires every silent adopter to share `hygienic_title`. This check reuses its parts. The builder may parameterize `hygienic_title` or compose a sibling predicate over its parts, but must not fork the parts. The S rung's existing `is_placeholder_text` refusal and `confidence != "low"` gate stay; this check is a superset of them. The new shapes apply to S and D only. setlist-gap and sibling-align keep `hygienic_title` as it is, since their adoptions were measured under it, so `w/ Eric Johnson` in a count-forced gap remains a documented limitation.
2. **No adjacent duplicate (per show).** No positional candidate may match the title of the track before or after it. This is the shift signature (robertrandolph-2005-05-29, particle-2003-06-14, gratefuldead-1972-04-26, railroadearth-2007-01-28). **One hit declines EVERY fill that rung would make on the show,** not just the duplicate track. On a shift, the rest of the run is wrong too; declining only the duplicate would leave one-late titles in place for the operator to inherit (operator, 2026-10-22: an off-by-one where all tracks are wrong "is worth holding"). A song genuinely split across two files also trips it, and holding that is acceptable: darkstarorchestra-2004-08-31's `Jam`/`Jam` across a disc change is such a hold, counted at the yield gate.
   - `is_filler` titles are exempt on both sides.
   - Two titles match when their `fuzzy_norm_title` forms are equal or `structure.fuzzy_title_eq` holds. There is no containment arm: `Truckin'` and `Truckin' Jam` must not match.
   - The comparator does NOT match `Sailing On`/`Sailin On` (`fuzzy_title_eq` is False on that pair; measured). That miss is accepted: on derektrucksband-2007-05-27, the one hand-checked case, slice 3 fills track 1 with its lossless `Announcements/crowd` before S runs. No spelling fold is added.
3. **Tape agreement (per show, D only).** Every song-like track carrying an independent title must agree with the list entry at its position. One disagreeing track declines every D fill on the show. This catches D's shifted and scrambled shows (gracepotter-2009-07-26, gratefuldead-1983-09-04, zwan-2001-12-13). The census's crude count (28 of 85 D shows with at least one disagreement) is an upper bound under strict string equality; the Checkpoint A yield gate measures the real figure.
   - **Neutral:** `setlist-gap` and `setlist` titles, and a filler track whose entry is filler too.
   - **Disagreement:** a filler tag against a song entry counts as a disagreement; it is a shift signature.
   - **Comparison:** cores under 3 letters compare by `fuzzy_norm_title` equality only, because `loosely_same_title("J", "Jack Straw")` is True. Otherwise `loosely_same_title`, unmodified.
   - The comparison runs on cleaned copies: umphreysmcgee-2004-03-17 `Joel Piano Solo (02:05)` vs `piano solo^` must not fail it.
   - It is not applied to S. On a setlist.fm canonical it would misfire on about 8 good S shows, because setlist.fm names differ from the taper's (GY!BE aliases, spelled-out numbers).

**Written durations (per show, D only).** When at least half of the list's entries carry a written duration, compare every position whose entry carries one, filled or tagged, and decline the show if any of those tracks' file length differs from its entry's duration by more than `WRITTEN_DURATION_TOL`. An entry with more than one duration counts as having none. `WRITTEN_DURATION_TOL` is a new constant, fixed before measurement; the builder proposes a value with its rationale (for example 15 s or 10%, whichever is larger). On an untagged tape the shift detectors are written durations and slice 2's two untagged checks (block size and sibling durations).

**A track that fails the gate stays `unresolved`.** That is the state it would have been in without the rung, so the existing `unresolved track titles` hold catches it, and no new flag string is needed. Each declined track writes one operator note (rung, position, which check fired, the candidate).

**Declines bind setlist-gap.** `adopt_gap_titles` receives S's declined positions; a run containing a declined position is not filled. D and slice 4 run after it and need nothing here.

**Expected S effect:** the yield gate recomputes S's caught and uncaught bad shows after Q1 and the split by canonical source.

### Slice 2. The description position rung (D)

**Source.** The SELECTED recording's own description. The taper's list is the evidence; setlist.fm is never the source here. The rung reads a list of entries from it, and there are two admissible lists:
- **(i) numbered lines:** lines or `<br />`-separated entries read by the census reader's grammar (`NUMLINE` and the timestamp-line exclusion in `numbered_lines`, `docs/superpowers/2026-10-22-title-hygiene-evidence/census.py`): an optional disc or track prefix, a number of 1-3 digits, optional punctuation, then the text.
  - The numbers run 1..N within each block. Contiguity is there to catch blank or missing entries (alabamashakes-2012-01-13, delmccouryband-2004-06-12).
  - A restart at 1 begins a new block only after a recognised header: `taper.py`'s set and disc header grammar (`_SET_HEADER`, `_DISC_SET_HEADER` and the rest of `_SET_HEADERS`), or a bare disc label (`CD 2`, `Disc Two`). Blank lines, decoration (`=====`) and non-numbered lines may sit between the header and the restart. So a numbered footnote or lineage block never reads as a new set.
  - A change of inline disc prefix (`d1t10-` → `d2t01-`) is a restart.
  - 3-digit `1NN`/`2NN` numbering reads as disc-prefixed.

  This is the taper's own numbering; the rung never compares entry numbers against file numbers, because S0 found that misfires on derektrucksband-2004-11-20.
- **(ii) `parse_setlist`'s own items** for the selected description, cleaned exactly as `build_canonical` cleans them (banner strip, artist drop). Admissibility is judged over the lines that contribute to the cleaned list:
  - header-only lines (`Set 1:`, `Encore:`) and the banner or artist lines that `build_canonical`'s cleaning removes are exempt;
  - every other non-empty line, judged on the raw line before any number-prefix strip, must yield exactly one item. A line split on `>`, `,` or `;` into two items makes the list inadmissible.

  This needs a per-line reader beside `parse_setlist`; the builder writes it. `parse_setlist`'s outputs and every consumer of them stay byte-identical. In the D sample, six of the 11 all-right untagged shows came through `parse_setlist` items, not numbered lines, which is why (ii) is admissible.

A numbered line with no text (`07) `) makes both readers inadmissible.

Neither reader can produce a list from a single run-on line: (i) takes at most one entry per line, and (ii)'s per-line test fails on a line that yields several items. furthur-2012-04-21's description is such a line. `parse_setlist` mis-counts most numbered lists (60 of the census's 85 came through (i) only). The builder decides whether (i) is a new reader or `parse_setlist` keeping per-entry text additively, as the draft spec proposes. Either way, `parse_setlist`'s existing outputs and every consumer of them stay byte-identical. When both lists qualify, prefer (i).

The census's 85 shows and 570 tracks are an upper bound: they were computed with `hygienic_title`, with run-on lists included, and with a reader that did not require contiguity. The yield gate re-measures under these rules.

**When it fires.** The entry count equals the kept track count, and the show has at least one still-`unresolved` track after every earlier rung. It runs after `adopt_gap_titles`, 2a (`accept_short_tags`) and slice 4, before `align()`. Slice 4 goes first because it ships an independent title, which check 3 can then use. D never touches a resolved track or an override. It may fill a 2b-demoted position: it is a gated positional rung. This amends 2b's ruling that only setlist-gap and sibling-align may title such a track (guard-fixes spec, "2b"); see "Amendments confirmed by the operator".

**What it ships.**
- The entry text for each unresolved track that passes slice 1's gate, cleaned: taper markers and a trailing segue marker removed, an interior footnote parenthetical (`(1)`) removed, written durations removed wherever they sit, and a leading `E:`/`EN:`/`Encore:`/`Filler:` marker and wrapping quote marks removed, in the way `shipped_short_tag` strips a leading encore marker for 2a. `(GA)`-style initials stay, per "taper wording ships". The S rung never shipped `E:` (`parse_setlist` consumes the marker), and the taper reads the description's markers itself.
- A compound entry keeps its interior `>`: `Pyramid County (1) > Little Maggie` ships as `Pyramid County > Little Maggie`. Only reader (i) yields such entries, since (ii) splits them.
- The new `title_source` is `desc-position`. At 13 characters it fits the 14-character column `llama show --tracks` prints (`cli.py:1583-1591`).

**Tautology.** `desc-position` joins `TAUTOLOGICAL_TITLE_SOURCES`. That is one definition, so `_songish_coverage`, `align`, `apply_llm_alignment`, gather's final assembly (`matched=None`), `taper._counts`, `right_show_gate` and replay's source listing all treat it correctly with no change of their own. A fill copied from a list proves nothing when matched back against a list. Its agreement with a canonical from elsewhere is checked once, explicitly, by the agreement check below.

Two consequences:
- (1) On a partly tagged tape, D-filled tracks leave `_songish_coverage`'s denominator, where today their unresolved filenames count as misses. Coverage over the remaining independent tracks may therefore rise and clear `low-confidence structure alignment` flags. The yield gate counts these.
- (2) vet's 4a (`right_show_gate`) does not count D-filled tracks as resolved, so unknown-song flags on mostly D-filled tapes are not rescued by 4a. That is a limitation, and the yield gate counts it.

On a wholly description-filled tape the independent set is empty and coverage reads 0.0. Without Q2, what happens next depends on the branch (`gather.py:1361-1456`):
- **Jerrybase anchoring resolves** (Garcia-family shows; `anchor_breaks` matches closers whatever the `title_source`, `jerrybase.py:257`), or the canonical is empty: no structure flag, and the hold clears. 12 of the census's 85 D shows are family shows.
- **Otherwise** (`today_llm`, `gather.py:1386`): gather spends one `align_structure` LLM call. That call cannot win, because `apply_llm_alignment` also excludes tautological tracks (`structure.py:1248`). Gather then raises `low-confidence structure alignment` and the show stays held.

**Agreement check (per show).** When there is a canonical and it did not come from the selected description (setlist.fm, a sibling item, an LLM extraction), D computes `align()` of its filled titles against the canonical, treating them as independent for this one computation only. If that coverage, over song-like filled tracks, is below `align_coverage_threshold`, D declines every fill on the show: the tracks stay `unresolved`, and the show is held as today. This is the operator's rule for a list that substantially disagrees with the canonical (see "Amendments confirmed by the operator").

The agreement check is NOT a shift detector. `align()` is order-preserving, so a list shifted against the files still agrees with setlist.fm (billystrings-2023-06-10 scores 1.00). The shift detectors are checks 2 and 3, written durations and the untagged checks below.

**Self-filled tapes (operator ruling Q2).** A tape is **self-filled** when every song-like track is `desc-position` and D passed all its checks, including the agreement check when it applies. On a self-filled tape, whatever the canonical:
- gather skips the `align_structure` LLM call;
- gather does not raise `low-confidence structure alignment` on the not-owned branch (`today_llm`);
- the `today_reaches_llm` value passed to `decide_taper` is unchanged.

The owned-path flag site (`today_llm and reader_coverage < threshold`) is unreachable: `taper._counts` excludes tautological sources, so the taper never owns a self-filled tape. A defensive test pins that, instead of a suppression at that site. Set labels come from jerrybase anchoring when it resolves, else from the deterministic `align()` of the D titles against the canonical. `GatherResult` carries a `self_filled` boolean.

**Replay.** Piece 2's relaxation (`replay.py:330-332`) extends, keyed on `self_filled`: a stored-`llm` show that the new gather finds self-filled is replayable, because no LLM call is made.

**Wholly untagged tapes.** D may fill them (operator ruling Q1). Check 3 is vacuous on these tapes, so D runs two more checks on them. Either one failing declines every D fill on the show.
- **(a) Block size.** It fires only when both hold:
  - the list has 2 or more blocks, separated by recognised set or disc headers or by a numbering restart (reader (i));
  - the filenames carry a disc index (a `dN`/`cdN`/`discN` token before the track number) giving the same number of discs as there are blocks.

  Then each block's entry count must equal its disc's file count. With a different block or disc count, or no disc index, the check is inert.
- **(b) Sibling durations.** Gather already loads donors for sibling-align on these tapes (`fetch_siblings` is true). When a tagged sibling recording is available (the donors sibling-align uses), run `siblings.py`'s duration alignment of the target against the best donor. Every track the alignment pairs one-to-one must have its D candidate agree with the donor's title, by check 3's comparator, with filler neutral. Any disagreement declines the show. When no donor exists, or the alignment pairs fewer than `MIN_ANCHORS` tracks, the check is inert.

Their constants and the disc-index grammar are fixed before measurement.

**Measured (class U).** 202 of 3,980 shows (5.1%) have fewer than 2 independent song-like titles. 50 of them (1.3%) also have a count-matched description list, and all 50 were hand-checked (`handcheck/U0`–`U3`):
- 34 all-right;
- 12 lists that are not titles (bare numbers, durations, filename stems, `?`, `track one`…), declined by hygiene;
- 1 with set-header lines, declined by the header rule;
- 1 run-on (furthur-2012-04-21), which no reader admits;
- 2 shifted (billystrings-2023-06-10, derektrucksband-2003-11-26). Both are caught by (a): Set 1 has 13 entries against 12 disc-1 files, and discs of 9 + 5 entries against 10 + 4 files. Billy Strings is caught by (b) as well.

Neither check fired on any of the 34 right shows; 14 of the 50 have a tagged sibling.

**Residual, an accepted limitation:** an untagged tape with no disc structure, no tagged sibling and no written durations can still hide a coincidental shift. The sample had 0 such failures, an upper bound of a few percent of that subgroup, under 1% of the library.

### Slice 3. Per-track lossless titles from the same item (C)

`_recover_format_titles` is wholesale and gated at 0.5/0.9, and those constants stay. This slice sits beside it. It uses `recovery_basis`, the same basis as recovery, and the filename-stem bijection with a lossless format of the same item that `titles.sibling_format_titles` builds.

**Scope.** C runs only when the delivered format's `title_fraction` is at least `_RECOVER_BELOW` (0.5), that is, only where recovery's first gate excluded the item. A tape below 0.5 whose lossless set is below 0.9 is the decision space the 166-item measurement rejected, and C must not re-open it. 2b's recording-level demotion (`recording_level_junk`) is computed on the delivered layer before C, and applies to the stems C did not change.

**Placement: the tag layer, per track,** before `resolve_titles` and therefore before the S rung, overrides, sibling-align, setlist-gap and 2a. The chosen tag IS the tag every later rung and anchor reads. The consequence is intended. For the census's 39 blank-MP3 stems (counted before C's ≥ 0.5 scope rule and agreement requirement; the yield gate recounts) that S (19), setlist-gap (15) and sibling-align (5) fill today, the item's own lossless tag wins over a positional or cross-item fill. derektrucksband-2007-05-27 t1 becomes `Announcements/crowd`, which is right, instead of S's wrong `Sailing On`. A title from C carries `title_source=sibling-format` per track, so a manifest may now mix `tags` and `sibling-format` tracks. That differs from wholesale recovery, which never interleaves sources.

**Per-track source.** `tag_layer` returns a per-track source list. These consumers must use it:
- `resolve_titles` stamping;
- `accept_short_tags` stamping;
- the 2c/2d stripped-number notes, which skip C-changed positions;
- 2b's "format sibling tagged … filed, not acted on" note, which is not written when C acted.

These also drop C-changed stems:
- 2b's per-position demotion notes;
- the `demoted` set passed to `accept_short_tags`;
- `fetch_siblings`' `or demoted` arm.

Per stem:

- **C1, fill.** The delivered tag is blank, a 2b placeholder (`tmp`), or fails `is_real_title`, and the lossless tag is a real tag that is also hygienic. A delivered tag with the 2a shape (`J`, `42`, `M80`) is not a C1 target; it goes to C2's rule. A C1 fill is adopted only when the lossless title agrees with one of:
  - (a) the same-position entry of a count-matched admissible list;
  - (b) the canonical item at the same position, when the canonical item count equals the file count;
  - (c) failing both, the show's own consistent tags: on at least `MIN_ANCHORS` comparison stems the delivered and lossless tags agree (Definitions), and on none do they disagree. The comparison stems are those that are not C1 targets: both tags real, neither a placeholder.

  Otherwise C1 declines for the show. Ship the lossless title, `title_source=sibling-format`. This is the furthur/DSO `tmp` class: 18 shows, and with the blank-MP3 class, 36 more (census counts, before the scope and agreement rules). It clears holds where a count-matched reference or consistent tags exist; the yield gate counts the rest.
- **C2, replace.** Both tags are real (or the delivered one has the 2a shape, as above) and differ substantively (not case, punctuation, whitespace or `normalizes-equal`), and the lossless tag agrees with the reference while the delivered tag does not. "Agrees" means `loosely_same_title` (cores under 3 letters: `fuzzy_norm_title` equality) against the same-position entry of a count-matched admissible list, or the canonical item at the same position when the canonical count equals the file count. With neither available, C2 does not fire. Whole-text containment is never used. Ship the lossless title. It adds no holds. It fixes silent errors like radiators-1991-11-01 (`No Skin Off My Back` on what is `Mood To Move`).
- **Never** take a lossless tag that is:
  - bracketed (`[Banter]`, `[John's Still Got Some Gas…]`);
  - ending in `:` or `(m:ss):`;
  - the delivered title plus only a trailing symbol marker (`@ ^ * #`).

  Under the first two, builttospill-1997-10-13 and mountaingoats-2017-06-02 decline. Under the third, greensky-2014-07-18 keeps its clean title.
- **Show-level decline:** skip C for the show when two or more lossless tags each equal (by `loosely_same_title`, after slice 1's cleanup) the reference's entry at position ±1 but not at their own position, as builttospill-1997-10-13 shows. The reference is whichever one C1 or C2 used: the count-matched admissible list or the count-matched canonical. Without either, this decline cannot fire, and the per-tag vetoes above still apply.

C1 and C2 write one operator note per changed track. `LOSSLESS_TITLE_FORMATS` is read-only and unchanged.

### Slice 4. Short real tags confirmed by the taper's own list (A_rev)

This extends 2a (`accept_short_tags`) with one more witness: **the selected recording's own description, at the same position.** That relaxes 2a's ruling 3 ("never the selected recording's own description") under a stricter, positional condition (operator ruling Q3: yes). A still-`unresolved` track whose tag fails `is_real_title` and is not 2b-demoted is accepted when all of these hold:

- its core (`tag_core`) equals, by `fuzzy_norm_title`, the WHOLE entry (Definitions) at the same position. Same reader and count condition as slice 2: entry count = kept track count;
- among the real-tagged neighbours within ±2, at least one agrees with its entry at its own position and none disagrees, by check 3's comparator. This blocks robertwalters `VA` (the comma-split "Quantico, VA") and zwan's scramble. With no real-tagged neighbour within ±2, the slice does not fire;
- the core is not a case-insensitive substring of the file's stem, at least 2 characters long (`d206` on jackiegreene-2011-12-31);
- 2a's existing junk veto (`is_junk_tag`) and its `metadata_norms` exclusion still apply. That knowingly keeps out GY!BE's `12.28.99`/`12-28-99` (date-shaped, 7 tracks) and `2:22`, which the hand-check rated right. This is the author's call; the operator may overrule. D may still ship `09-15-00` or `12.28.99` at a count-matched position, so the veto matters only where D does not fire.

Slice 4 runs after 2a and before slice 2 (see slice 2).

It ships `shipped_short_tag(tag)`, as 2a does today, which strips segue arrows and footnotes from `X >`, `415 ->`, `7-11 (3)>`. It fills only `unresolved` tracks. moe-2008-01-26 and discobiscuits-2006-08-26 show why: a better title already shipped there.

**Not caught by any text check:** godspeedyoublackemperor-2011-03-15, where tag and description agree but durations show the file is mostly another piece (1 in 30). Slice 4's date veto keeps its `12-28-99` out only incidentally, and D fills it (summary table, row D), an accepted limitation.

### Slice 5 (add-on). Cosmetic junk stripping

Slice 5 is a cosmetic pass on the FINAL resolved title strings. It runs after every gather flag is computed, immediately before `Show` is built, so after structure is decided and after every recording-level gate (`title_fraction`, format recovery, `fetch_siblings`, the enumerated-tape votes, 2b). It never runs inside `clean_tag_title`/`clean_tag_titles`.

Strip only these shapes:
- a leading `m:ss` or `h:mm:ss` followed by `)`, `]` or ` - `;
- an embedded identifier/date/disc-track stem (`d&co2017.06.17.mg21.set01t01`, `dNNtNN-`, `sNtNN`);
- a `.wav`/`.flac` tail, and a pasted `.flac:<md5>` tail.

A leading `E:` and set markers (`S2:`, `set1:`) are not stripped: structure readers key on them.

The result must be non-empty, pass `is_real_title` (or 2a), and not be a placeholder. Otherwise the title is left exactly as it was. **Never strip** a bare `m:ss Word` (`4:20 Polka`), a spaced leading number (`8 Cylinders`, `16 Military Wives`, `20 Eyes`, `3 AM`), or a number inside a title (`1 Samuel 15:23`). The `NN-` joined prefix is already handled by 2d; it does not need to equal the position (ryanadams runs 02..26 on positions 1..25). Slice 5 changes shipped strings only. Its acceptance: the replay shows zero gather flag and set-label changes from it, and any vet or brief flag change is reported and hand-checked.

## Acceptance

All measurements use the replay harness and the census tooling from the merged tree, compared with 11dbffb. The census's `dump.py` and `census.py` are the starting instruments; the builder versions what it uses. **The fresh-get view strips title AND structure overrides together.** `scripts/replay_holds.py` has `--strip-structure-overrides` but no mode that strips `overrides.titles`, so the plan adds `--strip-title-overrides` beside it (both read-only, no apply lists). The census stripped only title overrides, so Q1's trade and the "ships silently" counts are recomputed on the fresh-get view at the yield gate.

1. **Yield gate before wiring.** This is piece 2's lesson. Each slice's rule runs offline over `dump.jsonl`, scored against the hand-check rows, before gather is touched. Report per slice:
   - tracks filled or changed;
   - the hand-checked wrong count among them;
   - good shows newly held;
   - bad shows newly held.

   Also report:
   - the S population re-counted under the split by canonical source, and S's caught and uncaught bad shows after Q1 and that split;
   - the shows where S was withdrawn because D declined (slice 1);
   - the stricter non-chosen S alternative (`gap_span`-bracketed runs only): its added holds and the bad shows it would stop, for the operator, not adopted;
   - Q1's trade and the "ships silently" counts on the fresh-get view;
   - the self-titled songs the `metadata_norms` exclusion declines;
   - check 2's holds on songs genuinely split across files (`Jam`/`Jam`);
   - the `low-confidence structure alignment` flags cleared by D-filled tracks leaving coverage's denominator, and the unknown-song flags 4a no longer rescues (slice 2's consequences (1) and (2));
   - D's residual on untagged tapes with no disc structure, no tagged sibling and no written durations;
   - a hand check of every wholly untagged show with a count-matched list (50 in the census view; all hand-checked as class U), recounted under the Definitions predicate.

   Checkpoint A (operator) sees this table.
2. **Per slice, after wiring, over the whole library** (`--all`, on the fresh-get view AND as-is):
   - **holds cleared**, split three ways: held now / would-hold on a fresh get / currently packaged;
   - **holds added**, their flag, split by state;
   - **titles changed on shows that stay unheld**, split by state (packaged / delivered / voiced);
   - **needs-LLM outcomes**, counted as held and listed separately, with how many D shows reach the agreement check's decline or the LLM branch.
3. **Hand check** by Sonnet with an Opus pre-screen. It covers changed titles, fills and replacements alike, on packaged, delivered and voiced shows, and on future gets through the fresh-get view:
   - every newly cleared wholly untagged show (Definitions) where D filled 3 or more tracks, all self-filled tapes included;
   - a stratified 60 of the other newly cleared shows;
   - every changed title on a delivered show.

   This is a hold-clearing change, and a cleared hold is the strict surface.
4. **Accuracy bar (operator ruling Q4):**
   - wrong titles ≤ 2% of the tracks the slices fill or replace automatically, per adopting path (C1, C2, D, slice 4, S, slice 5) and pooled (the house standard: gap-fill 2.4%, sibling-align 1.9%);
   - zero shifted shows in the hand check of item 3 and in the yield gate's wholly untagged hand check;
   - slice 1 holds no more than 2 hand-checked-good S shows, excluding the operator-ruled Q1 declines, which are reported separately.
5. Suite green from the worktree's own venv. `test_align_default_lookahead_is_8` and the other pinned constants are untouched.

## Operator rulings (2026-10-22)

- **Q1. Wholly untagged tapes.** The **taper's own description list may fill a wholly untagged tape by position** (slice 2), under the count match, the readers' admissibility rules, slice 1's gate, the written-duration check and the untagged checks. The **S rung may NOT fill a wholly untagged tape** when its canonical did not come from the selected recording's own description (setlist.fm, a sibling item's description, an LLM canonical). There every S candidate is declined, and the tracks stay `unresolved`. In the hand-check, those fills were 18 right of 38 whole-tape fills, against D's 11 of 15. The census view suggests about 15 holds, 8 on hand-checked-good shows and 2 cant-tell, to stop 5 silent bad shows; this is recomputed on the fresh-get view at the yield gate. When S's canonical IS the selected description (`chosen`), the fill is made by D.
- **Q2. Self-filled tapes ship.** The operator: "Let them ship. I consider the setlist in the item description more reliable than track tags, as the uploader is probably more likely to revise and correct the description than the file tags." The case is a self-filled tape (slice 2): every song-like track is `desc-position` and D passed all its checks, including the agreement check when the canonical came from elsewhere. On such a tape, whatever the canonical, gather neither spends the `align_structure` LLM call nor raises `low-confidence structure alignment`. Set labels come from jerrybase anchoring when it resolves, else from the deterministic `align()` against the canonical. The exception is deliberately narrow: a tape with ANY independent song-like title keeps today's coverage rule and flag. A list that substantially disagrees with a canonical from elsewhere is held by D's agreement check (see below).
- **Q3. A short name in the taper's list confirms the same short tag** (slice 4), at the same position with an agreeing neighbour. The operator: "yes, of course." This relaxes 2a's ruling 3 for that positional condition only. 2a's cross-source rule is unchanged otherwise.
- **Q4. Accuracy bar accepted:** at most 2% wrong among automatically filled tracks, and zero shifted shows among those newly cleared.
- **Q5. Untagged tapes get deterministic shift checks, not a confirmation band.** The operator chose deterministic shift checks for wholly untagged tapes (slice 2's block-size and sibling-duration checks) and rejected a band held for confirmation: "there isn't a world where I have time to manually clear hundreds or thousands of shows." A show's routes are deterministic checks, an LLM adjudicator later, air, or don't air.
- **Review mode: Fable** (operator, "Opus/Fable for this round"): one Opus reviewer and one Fable reviewer on spec and plan; the Fable seat also reviews the final branch. For this run that overrides "never silently upgrade".
- **Standing principle recorded with Q2:** where the selected description and the tape's own tags disagree about a title, the description is presumed the more reliable of the two. This piece applies it in three places: the S rung yields when D fills from a count-matched admissible list of the selected description, and declines with D when D finds a shift; check 3 still DECLINES a D fill on any disagreement, because a disagreement at a position is the signature of a shifted list, not evidence about which title is right; and C2 prefers the lossless tag only when it agrees with the taper's list or the canonical at that position.

### Amendments confirmed by the operator (2026-10-22)

- **D may fill a 2b-demoted position** (slice 2). This amends 2b's ruling that only setlist-gap and sibling-align may title such a track. Operator: "Yes".
- **A D list that substantially disagrees with a canonical from elsewhere holds the show** (slice 2, "Agreement check"). Against setlist.fm's, a sibling's or an LLM's canonical, D declines its fills when the agreement check fails. Operator: "when they substantially disagree, hold the show." The operator approved carrying this as a local check inside D. Note on which canonical a show gets: `structure.rank_parses` ranks `p.source == "setlist.fm"` first (`structure.py:532-566`), so whenever setlist.fm returns a setlist it IS the canonical, whatever the descriptions say; a `chosen` canonical therefore occurs only when setlist.fm has nothing for the show (or is not configured), and the agreement check applies to most D shows. The taper's segue marks are blended onto a setlist.fm canonical (`blend_segues`), and piece 2's taper markers still own set structure when they place exactly.

## Author's calls (settled after the builder check; the operator may overrule)

- C sits at the tag layer and beats later positional and cross-item rungs on its stems (slice 3). It runs only at or above `_RECOVER_BELOW`, and a C1 fill needs agreement with the taper's list, the canonical, or the show's own consistent tags.
- The S rung splits by canonical source: a `chosen` canonical is D's job; any other canonical fills only where D does not, declines with D on a shift signature, and never fills a wholly untagged tape, defined by `siblings.MIN_ANCHORS`.
- A check-1 failure declines per track only for a slot placeholder or a `metadata_norms` hit off the first entry; every other failure declines the show. Hygiene is composed from `hygienic_title`'s parts without its `is_real_title` requirement, plus `is_placeholder_text`, the filename and file-stem tests and the timestamp shape; it never uses `is_junk_tag`. setlist-gap and sibling-align keep `hygienic_title` unchanged.
- An adjacent duplicate declines every positional fill on the show, not just the one track (check 2). It compares by `fuzzy_norm_title` equality or `fuzzy_title_eq`, with no containment arm.
- Check 3 applies to D only, counts the independent sources in Definitions, treats filler against filler as neutral and a filler tag against a song entry as a disagreement, and compares cores under 3 letters by equality only.
- D's reader (i) is the census `NUMLINE` grammar with contiguity within each block, a new block starting only after a recognised header or at a disc-prefix change; reader (ii) admits `parse_setlist` items only when every contributing raw line yields one item. Numbering is the taper's own, never compared with file numbers.
- `desc-position` is always tautological, by one definition; D's agreement check, not coverage, compares the list with a canonical from elsewhere.
- D ships titles without a leading `E:`/`EN:`/`Encore:`/`Filler:` marker or wrapping quote marks.
- Slice 4 runs before D, and needs at least one agreeing real-tagged neighbour within ±2. It keeps 2a's date and timestamp veto, which knowingly keeps out GY!BE `12.28.99` and `2:22`.
- Slice 5 runs on final titles only, immediately before `Show` is built, and never strips `E:` or set markers.

## Left to the builder

- Module layout.
- Whether reader (i) is new or a `parse_setlist` additive field, and the per-line reader that reader (ii) needs.
- `WRITTEN_DURATION_TOL`'s value, proposed with its rationale.
- The disc-index grammar and the untagged checks' constants, fixed before measurement.
- Constant values the spec does not fix. Fix them before measurement and record them.
- Note wording.
- Slice order inside the plan, with one fixed rule: slice 1 lands before or with slice 2.
- Test fixtures, from the hand-check's named shows and slice 1's named PASS/DECLINE strings. Captured real metadata, offline. They include a fixture pinning that check 2's comparator does not match `Truckin'`/`Truckin' Jam`, and the defensive test that the taper never owns a self-filled tape.
