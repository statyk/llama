# Acceptance: the taper's set/encore markers (piece 2)

Plan Task 9 Step 6; spec "Measurement and acceptance". Built from the run-3 files, not from memory. The record copies are in `docs/superpowers/2026-10-22-taper-set-markers-sdd/acceptance/` (run 3 files) and `.../verdicts/` (every reviewer report, by task name). Nothing here has been applied to the library: applying is operator-gated.

## Arms

- **base** = main @ a26c4d1c601d90e942df7819d77cd4323fc2810f, run from `.claude/worktrees/taper-base` with its own venv, generated 2026-10-22T20:21:49Z.
- **cand** = a9016b55677fb4457ca53c6378c747ea64ab4125 (`--all`).
- **cand-stripped** = the same sha with `--strip-structure-overrides --slugs <the 394>`.
- Files: `~/.llama-harness/piece2/accept3/` (`base.json`, `cand.json`, `cand-stripped.json`, `the394.txt`, `cmp/`, `score/`, `step3.txt`). Commands as in plan Task 9 Steps 1-2, with `compare --no-repro-gate`. The base reproduces 133/146 (`cmp/summary.txt`); the repro gate fails on this library regardless of code, per the spec. Run 3 reused run 2's base (base code is unchanged between them; `compare` refuses differing digests).
- **History.** Run 1 at 22f565a (`accept/`) found rule defects; run 2 at 9388d09 (`accept2/`) and run 3 at a9016b5 (`accept3/`) followed the fix rounds. Owned counts: run 1 645, run 2 628, run 3 627. Run 3 is the record.

## Measurement 1: score (stripped arm against the adjudicator's targets)

Source: `score/score_summary.txt`. Yes/partial rows 339; 313 excluding filename/track-tag rows; 26 of those reported apart as out of scope.

Counts by primary form (in scope):

| primary | declined | match | filler-only | known disagreement | owned, no target | owned, renumbered (not graded) | miss |
|---|---|---|---|---|---|---|---|
| desc-blank-line | 5 | | | | | | |
| desc-disc-only | 3 | | | | | | |
| desc-disc-with-set | 47 | 16 | 2 | 1 | 6 | 1 | |
| desc-encore-only | 41 | | | | | | |
| desc-inline-marker | 12 | 1 | | 1 | 1 | | |
| desc-set-header | 92 | 35 | 9 | 2 | 9 | 1 | 4 |
| jerrybase | | | | 1 | | | |
| other | 12 | | | | | | |
| sibling-description | 8 | | | 3 | | | |

- **In scope: 186 rows** (the gate's definition): match 52, filler-only 11, miss 1 of 64 graded, declined 104. All rows: graded 67 (match 52, filler-only 11, misses 4), declined 220, known disagreements 8.
- The file's own two lines differ on the miss count (in-scope line: 1 of 64; all-rows block and `counts by primary`: 4 of 67, all under desc-set-header). The run-2 ledger records the same split. I could not reconcile it from the files, so both are given; all 4 misses are listed and explained below.
- **Every miss** (acc-explain section B, run 1; the structure of each is unchanged by the later fixes):
  - `furthur-2012-07-08`: the taper wrote no encore and step 1 has none, so the labels equal today's. The adjudicator's encore (Samson) is the accepted unmarked-encore class: the last set runs to the end. jerrybase's closer flag becomes a note (spec section 5), so a fresh gather would ship it unheld; the show carries an operator override in production. Verdict: as designed.
  - `greenskybluegrass-2014-02-28`: no encore word in the description or notes; the target's encore rests on a blank line and a reviewer's `E:`. Labels equal today's. As designed (unmarked-encore class).
  - `darkstarorchestra-2007-05-17`: the taper marked the encore (`E:`, `E2:`), but the disc-3 tags are one file late, so placement lands the encore one track early. Structure equals today's; stays held on unresolved titles. As designed (shifted tags, out of scope for this piece).
  - `thenewdeal-2005-04-29`: the description marks no encore; the item's notes mention an "encore break" but the veto does not read notes when the description supplied the markers. Labels equal today's, shipped impact 0 (a recorded concern).
  - `stevekimockband-2000-03-31` was a fifth miss in run 1 (rule defect B4, below). It is no longer a miss: B4 now declines it (`veto: step-1 break before set 1`).
- **Known disagreements: 8 scored, 7 as expected.** The exception, `gratefuldead-1970-05-15-spans`, is held in substance (`tape spans 2 events` is a deterministic hold no LLM call can clear; the taper does not own it; the candidate equals base). It is a scorer strictness artifact: the scorer counts needs-llm as not held (acc-explain C).

## Measurement 2: newly cleared (report 2)

`cmp/taper_cleared.txt` lists 8 shows (`cmp/summary.txt` separately reports "newly cleared: 0" for the non-taper report). Per pre2-cleared (run 1; `taper_cleared` is identical in runs 2 and 3), **4 are caused by this piece, all `structure-changed`** (would be needs-brief, taper-owned, structure equal to the taper's text and to the adjudicator's target where there is one, zero title and zero segue changes): `corblund-2004-11-04`, `derektrucksband-2004-04-15`, `derektrucksband-2008-10-23`, `yondermountainstringband-2006-07-04`. The other 4 are identical in both arms (something in base already clears them): `darkstarorchestra-2004-11-14` (not owned, repeated `Playin'` decline), `johnkadlecik-2021-11-28` (owned but labels agree with step 1), `northmississippiallstars-2010-03-11`, `themotet-2013-04-20` (operator override).

Per-show verdicts (pre2-cleared): corblund-2004-11-04 CONCERN; darkstarorchestra-2004-11-14 OK for this piece; derektrucksband-2004-04-15 CONCERN (major); derektrucksband-2008-10-23 OK; johnkadlecik-2021-11-28 OK; northmississippiallstars-2010-03-11 OK for this piece; themotet-2013-04-20 OK for this piece; yondermountainstringband-2006-07-04 CONCERN (minor). The 3 CONCERNs:

- `derektrucksband-2004-04-15` is a named partial tape: about 110 s of "Hey Driver" is missing (the item's notes say so; 637 s on this tape against 746 s on the sibling). The adjudicator's action was "hold". The structure flags were all that held it, and llama has no flag for the dropout. Do not apply it with the structure-changed list without deciding the selection first.
- `corblund-2004-11-04`: the item date is 2004-11-04, the description says November 5, 2004. The adjudicator reserved the call for the operator (undecidable). The date flag is already dropped in base (Tier 1 4b), so this piece's clear is the last gate.
- `yondermountainstringband-2006-07-04`: the 68 s "Freebird Tease" (d03t01) is junk-excluded; the structure is right and needs no change. The adjudicator's fix re-admits it (`--include`).

## Measurement 3: report 3, tiers

`cmp/taper_changes.txt`, run 3: songs moved 78, labels renamed 0, filler labels only 7, segues changed 30, provenance only 498, needs-llm not owned 459, unreplayable 0, stored-llm moved 45.

Counts by state, from the file's `[state]` column (the `needs-llm not owned` tier is a count only, with no rows listed; `labels renamed` and `unreplayable` are empty):

| tier | packaged | delivered | voiced | held | total |
|---|---|---|---|---|---|
| songs moved | 5 | 69 | 4 | 0 | 78 |
| labels renamed | 0 | 0 | 0 | 0 | 0 |
| filler labels only | 1 | 6 | 0 | 0 | 7 |
| segues changed | 4 | 26 | 0 | 0 | 30 |
| provenance only | 56 | 399 | 43 | 0 | 498 |
| stored-llm moved | 6 | 36 | 0 | 3 | 45 |

**Voiced rows** (voiced shows are re-voiced only by an operator `emcee` run; the voiced files are station-side):

- songs moved (4): gratefuldead-1974-09-18, tedeschitrucksband-2018-10-13, tedeschitrucksband-2022-03-26, tedeschitrucksband-2023-03-31.
- provenance only (43): georgeporterjr-andrunninpardners-2010-01-29, gratefuldead-1968-02-14, -1971-02-18, -1971-04-29, -1972-09-28, -1973-05-26, -1973-06-22, -1973-11-11, -1973-11-14, -1973-12-18, -1975-06-17, -1976-06-09, -1977-05-04, -1977-05-18, -1978-04-16, -1978-04-24, -1978-07-08, -1978-12-16, -1979-11-01, -1979-12-01, -1980-06-21, -1981-02-27, -1982-10-09, -1982-10-10, -1983-10-15, -1983-10-17, -1983-10-21, -1985-06-30, -1985-07-01, -1989-10-26, -1990-03-22, -1990-03-24, -1990-07-18, mymorningjacket-2008-06-13, newmastersounds-2008-01-18, tedeschitrucksband-2019-01-22, -2019-02-16, -2019-02-26, -2021-10-08, -2023-02-18, themotet-2006-08-11, -2011-10-29, -2011-10-31.

The `provenance only` tier now excludes the 30 `segues changed` rows (the R1 report-3 tiering fix).

**Pre-screen summaries** (all Opus, read-only):

- **pre3-moved** (run 1; 83 songs moved + 8 filler rows, 91 checked): after-better 70, after-equal 14, after-worse 5, unclear 2. One defect class (G, encore folding on a stored-llm show below the coverage threshold), ruled G1 and fixed. Of the 5 worse rows, 3 were class G, 1 is `mymorningjacket-2018-03-05` (worse for the performance but held by vet, by design), and 1 is a cosmetic filler label (`yondermountainstringband-2010-07-17`). The 2 unclear: `darkstarorchestra-2006-11-29` and `gratefuldead-1974-09-18` (voiced; the taper's "Set Three" gives three sets and jerrybase's two-set count becomes a note).
- **pre3-llm** (run 1; 62 stored-llm rows plus a 538-row provenance sample): rows 9 cand-better, 44 equal, 7 cand-worse (4 song level, 3 filler only), 2 unclear; segues 171 lost (157 real), 4 gained. Two classes: D1 (segue regression on owned stored-llm shows, ruled accept) and D2 (= G). R1 harness defect: report 3's `provenance only` ignored segue changes (fixed, new `segues changed` tier). Of the 494 non-stored-llm provenance rows, 492 identical to base, 2 closer flag to note (dates OK); a 48-row sample confirmed across 10 forms.
- **rescreen2** (run 2, what moved after the fix round): removals are exactly the 17 G1 rows, each now computed exactly as today (needs-llm in both arms); the 30 `segues changed` rows are all on today's LLM path (inside D1); 120 segues lost (116 real), 2 gained (spurious); tiers correct. Net of G1: 2 correct taper structures lost (`greenskybluegrass-2013-05-04` delivered, `soulive-2001-12-15` held), 1 mixed, 4 encores kept, about 18 real segues back.
- Run 3 had no re-screen (ruling R20): exactly one row moved (`joerussosalmostdead-2019-09-28`), it is no longer owned, and Step 3's zero-diff check proves it equals base.

## Measurement 4: newly held, and titles

**8 newly held at run 3**: run 1's 10 minus `jackiegreene-2011-02-12` and `soulive-2001-12-15`, which G1 removed. Explanations from acc-explain section A (run 1; the flags are unchanged), one per show. For 9 of the 10 run-1 shows, every candidate flag was already in base's deterministic flags; they count as "newly held" only because base was needs-LLM, which keeps a show out of the held count. The only gather or vet flag this piece causes is mymorningjacket-2018-03-05's.

1. `darkstarorchestra-2009-11-14` (delivered), 2. `deadandcompany-2015-10-29` (delivered), 3. `stringcheeseincident-2005-03-25` (delivered): stored with an `llm` alignment and no flags; in base they are needs-LLM with `low-confidence structure alignment`. The taper owns each, so no LLM call is made; the owned structure equals the stored LLM structure at song level in all three. Each is held by `low-confidence structure alignment` alone under spec section 4: step-1 coverage and the reader's align() coverage are both under 0.8 (DSO 0.476/0.714 and D&C 0.588/0.588 because tags carry duration or filename residue; SCI 0.737/0.474 because a generic `Jam` item cascades). The stored LLM alignments scored 0.905, 1.0 and 0.842. By design (CONCERN): a correct structure held, one overrule each, only if the operator re-gathers these non-held shows.
4. `joerussosalmostdead-2017-11-09` (packaged): markers come from `notes`; owned breaks 6/13, encore 14, equal to the stored LLM structure (step 1 had 7/13). Held only by 8 `research asserts unknown song` flags (the taper's footnoted teases), which base computes identically. Not caused by this piece.
5. `joerussosalmostdead-2023-01-26` (packaged): structure unchanged (6/13, encore 14); held only by `research asserts wrong date: January 26, 2022`, which base raises identically. Not caused by this piece.
6. `mymorningjacket-2018-03-05` (delivered): the taper's "Set 2" runs Circuital into The Waterfall, so 3 sets (14/24/34) become 2 (14/34); vet raises `research asserts 3 sets but structure has 2`. setlist.fm and the Jambands write-up say three sets, so the 2-set structure is probably wrong; the vet backstop holds it, by design. The operator picks between the taper (`--overrule`) and `--set-breaks 14,24 --set-encore 34`.
7. `derektrucksband-2003-12-26` and 8. `radiators-1991-01-18`: already held before the piece (stored held), still held on a subset of their stored flags (DTB: unresolved track titles; radiators: 4 unknown-song vet flags). The taper replaced a wrong stored structure with its own and cleared `low-confidence` on both. An improvement.

Not newly held, though they appeared on run 1's list because base was needs-LLM: `jackiegreene-2011-02-12` and `soulive-2001-12-15` (both removed by G1, computed as today, still held for their stored reasons).

**Title changes: 0.** `step3.txt`: "title diffs 0". The one row in `title_sources.txt` is `northmississippiallstars-2010-03-11` track 12 (`ML`, 2a short-tag adoption), identical in both arms, not caused by this piece.

**Not-owned rows differing from base: 0** (`step3.txt`: "not-owned diffs 0", positive control 139 owned rows that do differ). `step3.txt` does not print the replayable not-owned row count; run 2's was 3355. Run 2 to run 3 differs in exactly one row, `joerussosalmostdead-2019-09-28`, which stopped being owned ("veto: step-1 break before set 1", now equal to base). Newly held: 8; owned: 627 (run 2 628).

## Measurement 5: the false-positive scan of the recognised forms

Done at Checkpoint A (before the build), not in the acceptance runs, by cpa-forms (first scan) and cpa2-forms (after the form additions). Both verdict lines, verbatim: cpa-forms "### Verdict — NO DEFECT CLASS"; cpa2-forms "### Verdict — NO DEFECT CLASS". Reports: `verdicts/cpa-forms.md` (sha256 b89974f1ec15c678579f2c1b2ee1cc87291901ca4013f28ea95b640b26facf81), `verdicts/cpa2-forms.md` (a768f5816d801e9ec1ff280bc5e011229d43984d84c20d1f62d4d504161c70f6); the other Checkpoint A reports are `verdicts/cpa-decl.md`, `cpa2-tiers.md`, `cpa3-*.md`.

## Rule defects found, and how they were ruled

Rulings quoted verbatim from `orch-r2/ledger.md` (llama-db / operator).

- **B4** (acceptance defect, `stevekimockband-2000-03-31`; found by acc-explain): "B4 → (b) taper owns nothing when step 1 has a numbered break before the taper's set-1 first-song hit (keyed to step 1, like (d)); test stevekimockband-2000-03-31."
  - Uniqueness ruling (B4 observation): "own-less, consistent with placement's uniqueness — if set 1's first song matches more than one track, B4 declines; unique hit checked as now; test (repeated 'Jam'-style opener) + mutation pin; behaviour change → re-run cand arm/library probe, report owned delta (expected joerussosalmostdead-2019-09-28)."
  - Narrowing to the latest hit: "with several hits for set 1's first song, B4 checks against the LATEST hit — the taper owns nothing when step 1 has a numbered break before that latest hit; otherwise B4 passes. Update tests/mutation pins, restore umphreysmcgee-2004-04-14's spec positive if it comes back, re-run cand arms, report which of the 15 stay declined (expected: only those with a step-1 break in the window)."
- **G** (pre3-moved class G, pre3-llm D2) **→ G1**: "G → G1: no recognised taper encore marker AND today's path would reach the LLM branch (canonical items, no anchoring, step-1 coverage < align_coverage_threshold) → taper owns nothing ("ruling (d) read as what today ships"); tests on the 4 named shows + inverse (encore marked → still owned)." Attribution: "llama-db reading of operator ruling (d), 2026-10-22".
- **D1** (segue loss on owned stored-llm shows): "(c) ACCEPT the segue loss. Keep taper ownership on weakly aligned shows (subject to B4 (b) and G1, which stand); no second needs-LLM predicate; document in Documented limitations: "on a taper-owned show whose step 1 is in today's LLM branch, segues come from step 1's alignment, so segues the LLM would have restored are lost (measured: 157 real segues over 41 of 62 stored-llm shows); segues are a nice-to-have per the operator". R1 stays in."
- **R1** (harness defect, report 3's `provenance only` ignored `segue_changes`): fixed in `scripts/replay_holds.py`; adds the `segues changed` tier ("R1 stays in" above). Its needs-LLM-base branch needed a test fixture fix (t9-rev I1, mutant M1, caught after the fix).

Owned deltas: gate in scope 77 -> 76 (G1, soulive-2001-12-15) -> 75 (B4 uniqueness, joerussosalmostdead-2017-03-11) -> 76 (latest-hit narrowing). Library 641 -> 628 (13 G1 flips) -> 613 (15 lost to uniqueness) -> 627 (latest-hit narrowing; only joerussosalmostdead-2019-09-28 lost against gate6). Arms 645 -> 628 (17 lost, all G1) -> 627. Stored-llm relaxation population 62 -> 45. Newly held 10 -> 8. Fix rounds 22f565a..a9016b5 (ec90395, 6727429, 2bc84b1, 26b4f4e, 9388d09, 4aa9f8c, 6a117f2, 722d4d0, cef2675, 77e5322, 95c735a, a9016b5); suite 4474 passed, 1 skipped, 8 deselected.

## Pre-screen and review verdicts

First `VERDICT` line verbatim, with the sha256 of each task's `handback.md` (copies under `verdicts/`):

- **pre2-cleared** `918d23e947c99aa50fba4cad59a9687fedc28ee65517567ca4947404d8d00b88`: "VERDICT: NO RULE DEFECT. 3 CONCERNs: derektrucksband-2004-04-15 (major), corblund-2004-11-04, yondermountainstringband-2006-07-04 (minor)."
- **pre3-moved** `6f993203206942c34dea455daadb25917a49fc91ed5e092727053b18a85f066a`: "VERDICT: RULE DEFECT (1 class). Rows checked 91 (83 songs moved + 8 filler labels only): after-better 70, after-equal 14, after-worse 5, unclear 2."
- **pre3-llm** `fbebc8eb5d0ad2c52a38c2223a815e55d14f88af93f3198d231246c648099fc1`: "VERDICT: RULE DEFECT (2 classes). Both are spec-level wiring gaps that need an operator ruling before the fix: the code does what the spec text says, but section 7's justification does not hold on these rows. (A): 62 rows; 9 cand-better, 44 equal, 7 cand-worse (4 at song level, 3 filler only), 2 unclear. Segues: 171 lost (157 real, 14 spurious), 4 gained (all real)."
- **acc-explain** `80f3bd0ca039452fccea2d29bd3c3d44139c81dce7e8eaf247863a37baf26e6b`: "VERDICT: RULE DEFECT (1)"
- **rescreen2** `374556000002b9fc66f990fd91ddbc6532f639d7751a2adbd447f1c680c3139d`: "VERDICT: NO RULE DEFECT"

Task-review chain (Opus), the fix-round reviews:

- **t9-rev** `83cf2bec0846df14b55b99590417e0dec06fdb30aa0d0ea987d6fc1f8deb11ff`, review of 22f565a..9388d09: "Spec: ✅ / Quality: Needs fixes" (one Important: R1's needs-LLM-base branch untested, mutant M1 survived; plus Minors).
- **t9-rr1** `f18213edee26e569b03e246037c9c1b4e85f576fe3458a730368693e72c5a6cf`, 9388d09..cef2675: "NOT ALL CLEAN: findings 1-7 are all ADDRESSED. One Minor (test coverage) is open under finding 7: the umphreysmcgee-2004-04-14 gather test no longer checks the owned path on a real fixture."
- **t9-rr2** `57e9db77f4e09e3231ac292b815cf4793e0ad48cd419779b52b4409586976cb4`, cef2675..a9016b5: "ALL ADDRESSED, NO NEW BREAKAGE"

## For the operator's hand check before any apply

- `derektrucksband-2004-04-15`: a partial tape (about 110 s dropout in "Hey Driver"), which the adjudicator wanted held for a selection decision. Exclude it from the structure-changed apply list, or decide the selection (air as is, or re-select `dtb2004-04-15.pvm480s.flac16` and exclude its interview track) first.
- `corblund-2004-11-04`: decide the date (11-04 vs 11-05) before apply; the clear pre-empts the question. Tracks 1 and 34 also ship as "Gonna) Shine up My Boots" (pre-existing).
- `mymorningjacket-2018-03-05`: the taper's 2 sets against setlist.fm's 3; held by vet. Choose `--overrule` or `--set-breaks 14,24 --set-encore 34`.
- The 3 delivered shows held by owned low-confidence (`darkstarorchestra-2009-11-14`, `deadandcompany-2015-10-29`, `stringcheeseincident-2005-03-25`): correct structures held because align() undercounts; one overrule each. DSO and D&C also carry duration or filename residue in tags that is on air today.
- G1's cost: `greenskybluegrass-2013-05-04` (delivered) and `soulive-2001-12-15` (held) lose a correct taper structure; they are computed as today.
- `joerussosalmostdead-2019-09-28`: B4's latest-hit narrowing declines it, a row pre3-moved judged better under the taper ("Set One ... Encore: The Weight", was 3 sets). It is computed as today.
- The D1 segue loss: 143 segues lost over 36 shows (about 139 real). Keep the 30 `segues changed` rows out of non-held re-processing (apply only to held shows, or accept the loss show by show).
- `tedeschitrucksband-2023-03-31`: its description is headed March 18, 2023 (pre3-moved side note) while the show is 2023-03-31; it is a voiced songs-moved row.
- Also carried: the 4 voiced songs-moved rows above change labels on aired packages; re-voicing is a separate operator decision.
