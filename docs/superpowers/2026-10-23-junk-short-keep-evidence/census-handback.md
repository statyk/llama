# Pieces 4-5 sizing census (read-only, current code e37f670)

**Ground state.** At start and end, HEAD was e37f670, the tree was clean, and `llama.__file__` resolved inside `/Users/shawn/projects/llama`. Nothing in the repo or `~/.llama` was written. I made no LLM calls and dispatched no subagents.
- **Replay:** all 3,983 shows replayed with overrides kept (`compute_legs`, cache-only, ~1 minute at 7 jobs); none unreplayable. Each show's dump also holds:
  - the selected item's raw junk-filter verdict per audio file (no `overrides.include`);
  - every canonical parse (setlist.fm and each recording's description);
  - all 9,844 sibling recordings, junk-filtered the same way (no metadata cache misses).
- **Library:** 2,566 delivered + 220 voiced, 842 packaged, 334 held, 21 briefed.
- **"Silent"** means current code ships the show with no flag.
- **Meter at hand-back:** 5h 29%, week 78%.

## Yield table

Abbreviations used in the table and below:
- "est." = estimated.
- "dlv" = delivered.
- "pkg" = packaged.
- "CB" = Checkpoint B.

| slice | shows / tracks | state (shows) | silent | holds cleared / added (replayed) | precision (my hand look) | complexity | seed recall | my rec |
|---|---|---|---|---|---|---|---|---|
| **4-seg**: short drop whose own tag ends `>`/`->`, or whose previous tag does and its own is a song title | 329 / 472 files | 217 dlv, 11 voiced, 82 pkg, 18 held, 1 briefed | 242 | 4 / 19. 15 of the 19 are low-confidence coverage dilution only. 51 shows carry position-keyed overrides that the inserted track would shift. | ~95% music in a 60-row look; ~5% fragments/false starts; ~0-2 junk | S-M: `junk._keep_and_exclude` exemption after the floor; coverage denominator in `structure`; override re-keying | 88/177 | **build** (with override re-keying) |
| **4-named-only**: short drop with a song-like tag named in the canonical or description, no segue | 285 / 355 | 177 dlv, 17 voiced, 62 pkg, 27 held, 2 briefed | 203 | (in union) | ~70% music with my wide junk vocab; **~55% if built on `structure.is_filler`** (219 more spoken/banter files pass) | M | +40 | **leave to adjudicator** |
| 4-union (seg + named) | 586 / 827 | 379 dlv, 28 voiced, 133 pkg, 43 held, 3 briefed | 424 | 8 / 36. 25 of the adds are low-confidence only and 5 are override exposure. 81 shows are exposed; on **11, an override title lands on the wrong file silently**. | ~85% | M | 128/177 | split as above |
| 4-conv: convention mismatch (case-only, set/disc stems, or named) | 13 / 90 | 4 dlv, 1 voiced, 5 pkg, 1 held | 8 | 1 / 1 | high: 51 of 90 already operator-included | S | 6 | build only if cheap; tiny |
| **5a**: head/tail unmatched canonical run at coverage >= 0.8 | 764 raw; 244 corroborated; 72 with a sibling >= 5 min longer | (72) 35 dlv, 5 voiced, 14 pkg, 18 held | 651 raw / 51 | a flag would add ~651 holds raw, ~51 at the strictest cut | **1 of 10 silent rows real**; 5 of 14 overall in the strongest stratum | M (`structure.conflicts` positions) | 37/75 any run; 10 strict | **leave to adjudicator** |
| **5b-runtime**: a sibling +10 min and +10%, with no fewer canonical items | 147 | 72 dlv, 27 voiced, 21 pkg, 27 held | 103 | (re-selection, no flag measured) | mixed: real cuts on some SBDs (gd77-09-03); others are aud padding | M-L (select_recording weights) | 24/73 | **adjudicator, or flag-only (needs ruling)** |
| 5b-trunc: >= 3 songs >= 60 s and >= 20% shorter than on one sibling, none longer | 129 (>=5 songs: 42) | 79 dlv, 22 voiced, 16 pkg, 11 held | 101 | — | unmeasured; padding versus a real cut cannot be told without listening | M | 9 | hand-check first |
| 5b-items: sibling covers +2 canonical items | 328 | — | 172 | — | mostly an artifact: runtime ratio ~1.0, i.e. the selected tape is untagged, not shorter | — | 36 | drop as a criterion |
| **5c-shift**: +-1 tag shift on duration-tight pairs, confirmed by 2+ siblings | 10 (raw tags) | 5 dlv, 5 pkg | 9 | +9 holds | the 4 I inspected look real, incl. deadandcompany-2016-07-15 | M (`siblings.align_durations` reuse) | 4/74 | **flag-only, 2+ siblings required** |
| 5c-shift, single sibling | 21 | 12 dlv, 1 voiced, 7 pkg, 1 held | 13 | +13 | unknown: either tape may be the shifted one | — | 5 | not without a 3rd source |
| 5c control: the SIBLING is shifted | 45 | — | 39 | 0 | (not our defect) | — | — | n/a |
| 5c-order: encore stored mid-tape (file order) | 18 sibling-confirmed (46 raw) | 14 held, 3 dlv, 1 voiced | 4 | +4 | the 14 held match overnight verdicts | S | 11 | adjudicator; already held |

## Piece 4: what the junk filter drops

**3,698 dropped files in 1,880 shows.**
- **By arm:**
  - `implausibly short` 3,547: all but 2 under the tape-relative floor;
  - convention mismatch 77 other + 16 case-only + 11 set/disc-stem;
  - conv+short 7;
  - duplicate-listing 40.

**Tag class** (census vocabulary, wider than `is_filler`):
- **Junk-vocab: 2,494.** intro 450, tuning 267, banter 263, crowd 152, band intros, donor rap, encore break, ...
- **Song title: 793.** Short songs, reprises, segue pieces under a song name.
- **Music word: 212.** jam, drums, space, prelude, reprise, percussion.
- **Untagged: 159.**

**Size of what is lost (union arm):**
- **Whole song: 298 files.** A canonical item no kept track covers: `Slipknot!`, `Abba Zaba >`, `Polythene Pam >`, `Fun, Fun, Fun`, `Suicide`.
- **Repeat/continuation: 274.** A reprise or the tail of a split song: `St. Stephen>` reprise, `Willin'`, `Kamaole Sands`.
- **Segue or named piece: 255.** `WRS Prelude`, `Jam ->`, `Drums >`, `7/4 Jam`.

**Ground truth: 239 dropped files the operator later `include`d.**
- The union arms catch 192 of them (80%).
- **Missed (47):**
  - 23 junk-vocab titles that are music: `We Bid You Goodnight`, sung `Happy Birthday`, `Countdown >`, `Blues Penitentiary Intro`.
  - 14 untagged DSO segue pieces.
  - A few teases.

**Precision.** From a 60-row look at each arm:
- **Segue arm: ~95% music.** Exceptions: `Escape >` (5 s), `Cassidy (Oops)`, a spoken `Eulogy`.
- **Named-only arm: ~70% music.** The ~25% junk is spoken material the taper names. Examples: `"really hot show"`, `Al.noumcements`, `tuni{ng`, `Production credits`, `(second set)`, `[drum check]`, `(bantor)`, `[cheering]`, `Glen explains...`. Plus fragments: `(Cut)`, `(aborted)`, `cuts after 50 seconds`.
- **A naming rule built on llama's own `is_filler`** would also pass `introduction`, `donor rap`, `thanks`, `[fade out]`, `set break`, `encore call`: 219 more files, pulling precision to ~55%.

**Holds:**
- Re-admission clears almost nothing (union 8). The value is entirely in the **424 silent shows** that air with a hole in continuous music or a missing short song.
- **Adds: 25 of 36 are `low-confidence structure alignment`.** setlist.fm does not list segue pieces, so a re-admitted `Jam >` is an unmatched song-like track. Excluding exempted tracks from the coverage denominator should remove most of these (estimated, not run).

**Migration hazard (must be ruled on):**
- An exemption inserts a track and renumbers the rest.
- 81 union shows (51 seg) have `overrides.titles`/`set_breaks`/`encore_after` at or after the insertion. On 11, an override title now lands on a different file, **with no flag**: bobschneider-2005-04-19, builttospill-1997-10-13, davealvin-2004-01-10, ...
- 407 delivered/voiced shows would need re-delivery (and re-voicing) to air the fix.

Seeds: 177 overnight `junk-filter-dropped-real-music` shows; all 177 have a drop, and 134 have a union/conv-arm file.

## 5a: partial tape at high coverage

Of 3,788 eligible shows (>= 5 song-like canonical items, >= 3 matched):
- **764 have an unmatched head or tail run at coverage >= 0.8.**
  - Head runs: 1 = 401, 2 = 80, 3+ = 84.
  - Tail runs: 1 = 350, 2 = 111, 3+ = 165.
  - 207 are encore-only tails.
- 244 are corroborated: the other source also lacks the items, or a sibling's tags name them.
- **Only 72 also have a sibling >= 5 min longer** (35 of them encore-only). Taper "not on tape" wording appears in 58 of 764 descriptions.

**Hand look:**
- **Silent rows:** 9 of 10 "missing" songs are on the tape under another spelling or merged:
  - yondermountainstringband-2005-04-29: `Troubled Mind > 20 Eyes`.
  - moe-2009-10-31: `TGORM`.
  - philleshandfriends-1999-04-15: `Hello Old Friends`.
  - derektrucksband-2004-04-15: `Jackson Soul Stew`.
  - gratefuldead-1994-10-05: `The Mighty Quinn`.
- **The one real silent partial is minutemen-1985-11-30** (voiced): 8 songs missing at the tail, and the sibling is 100 min against 83.
- **Real partials among held rows:** gd1990-05-05, gd1985-07-02, gd1984-03-31 (encores) and gd1994-08-01 (6-song head). All four are already held.

**Conclusion:** a head/tail check on `align()`'s unmatched items mostly measures title-matching misses. The coverage gap in CLAUDE.md is real but rare once spelling is accounted for.

Seeds: 37 of 75 have any run; 10 meet the strict cut. The rest are no run (26), a mid-show gap (7), or too small a canonical (5).

## 5b: a better sibling

- **Completeness by canonical items (+2): 328 shows.** Mostly an artifact. The runtime ratio is ~1.0, so the selected tape has unresolved titles rather than less music. `select_recording`'s completeness is kept-track count relative to the best sibling, and on 186 of these the selected tape had >= the sibling's track count.
- **Runtime-better (+10 min, +10%, no fewer items, ratio <= 1.6): 147 shows, 103 silent.**
  - Why selection won: lineage 78, downloads 59, rating/other 31, track count 29.
  - Some are real. gd77-09-03 (SBD, shnf) has `Promised Land` 246 s vs the matrix's 410 s, `Loser` 499 vs 655, `Truckin'` 514 vs 792: an edited/cut SBD beats a complete matrix on lineage.
  - Others are aud tapes with tuning/crowd folded into each track.
- **Per-song truncation (>= 3 songs >= 60 s and >= 20% shorter than on one sibling, none longer): 129 shows, 101 silent, 22 voiced.** The most common pairs are sbd vs matrix (23) and sbd vs aud (23).
  - **This is the adjacent class clearly larger than 5a**: SBD transfers with cuts and fades within songs, which neither track count nor coverage can see.
  - **Precision is unmeasured.** Padding can mimic a cut, and only listening, or the taper's own "cut"/"patch" notes, settles it.

Seeds: 43 of 73 meet some "better" criterion; 17 meet both items and runtime.

## 5c: shifted or scrambled tags

**Method.** I duration-aligned each show's tape against up to 4 tagged siblings (`siblings.align_durations`). On 1:1 pairs within max(10 s, 6%), I compared titles in three views: raw tags, independent shipped titles, and all shipped titles. 2,099 shows have a usable tagged sibling.

**Results:**
- **A +-1 run of >= 3 against a sibling:**
  - **The sibling is the shifted one in 45 shows**: other siblings agree with us. A one-sibling rule would add 39 false holds here.
  - **Confirmed by 2+ siblings with none agreeing: 10 shows (raw tags), 9 of them silent.** deadandcompany-2016-07-15 (8-9 late against all 3 siblings) is the known case.
  - **Inspected; these look real:**
    - gratefuldead-1979-09-01: 5-6 early against 4 siblings from track 12;
    - gratefuldead-1982-08-08: tracks 12-14 early;
    - gratefuldead-1990-09-19 and -1990-07-16: tail sections;
    - gratefuldead-1977-05-22: a far scramble, with a 954 s file tagged `Peggy-O`.
  - **Single sibling only: 21 shows.** I cannot tell which tape is wrong without a third source; written durations in the description could arbitrate.
- **On our pipeline's own fills:** using all shipped titles adds only 3 `setlist` shifted rows. Our positional rungs barely show up here (piece 3 already gated them).
- **Seed recall is low (9 of 74), and that is the finding, not a miss:**
  - **32 seeds have no tagged sibling with durations.**
  - **Most of the rest are FILE-ORDER defects:** the titles are right but the encore is stored on disc 1. Separately: **encore stored mid-tape** is 18 sibling-confirmed shows, 14 of them already held and 11 of them seeds. 4 are silent: gd1966-05-19 (voiced), gd1983-10-11, gd1991-03-31, umphreysmcgee-2004-12-03.
  - Others are untitled tapes whose sibling was the shifted one.
- **A general out-of-order (LIS) test** flags 542 shows, 165 sibling-confirmed. **Too noisy to act on**: Playin' sandwiches and setlist.fm order quirks.

## Packets (for the Sonnet fleet; I dispatched nothing)

All under `~/.llama-harness/piece45/packets/<class>/`, each with `packet.jsonl` and `INSTRUCTIONS.md` (answer schema included):
- **`p4/` (37 rows):**
  - segue arm, 9 silent + 4 flagged;
  - named-only arm, 9 silent + 4 flagged;
  - untagged-after-segue;
  - 5 junk-vocab controls (is the filter right?);
  - 4 convention-mismatch rows.
- **`5a/` (30 rows):**
  - corroborated + longer sibling, 10 silent + 4 held;
  - 8 corroborated, no longer sibling;
  - 8 canonical-only.
- **`5b/` (40 rows):**
  - runtime-better, 12 silent + 6 held/flagged;
  - 8 items-only;
  - 4 with ratio > 1.6 (suspect);
  - 10 per-song truncation, silent.
- **`5c/` (42 rows):** every 2+-sibling and single-sibling shift, the unclear rows, the 4 silent encore-order rows, and 5 "sibling is shifted" controls.

## Open questions for Shawn
1. **Piece 4 relaxes a safety filter.** The segue arm is ~95% music by my look, ~5% fragments, and near-zero junk. The named arm is ~70%, or ~55% on llama's own filler vocabulary. Build the segue arm only? Leave named-in-description to the adjudicator?
2. **Should a re-admitted piece count in alignment coverage?** If it does, ~25 holds are added for nothing.
3. **Overrides keyed by track number shift when an exemption inserts a track.** Options: re-key by filename at migration, skip shows with positional overrides, or apply only to new gets. 81 shows are exposed; 11 would silently mis-title.
4. **Re-deliver the ~407 delivered/voiced shows** a seg/union arm would change, or apply to new gets only?
5. **5b:** should selection weigh absolute runtime or per-song truncation against lineage? Today an edited SBD beats a complete matrix or aud. This is a taste call (sound vs completeness), and the truncation precision needs a listen sample first.
6. **5c:** a FLAG only when 2+ independent siblings agree against us (~10 shows, ~9 new holds)? The single-sibling cases go to the adjudicator.

## My recommendation
- **4-seg:** build, with coverage exclusion and override re-keying. 242 silent shows, ~95% precision.
- **4-named and 4-conv:** adjudicator. Named is ~55-70% precision; conv is 13 shows, already operator-included.
- **5a:** adjudicator, no rule. 1 real case in 10 silent rows.
- **5b:** adjudicator, plus a ruling on lineage vs completeness. Per-song truncation (129 shows) is the class to hand-check before deciding.
- **5c:** flag-only on the 2+-sibling consensus (10 shows); everything else to the adjudicator. Encore-stored-mid-tape is already held in 14 of 18.

## What I could not measure
- **Content correctness:** I listened to nothing. Precision figures are my reading of tags, durations and descriptions over the samples above.
- **The census matcher is a greedy approximation of `align()`.** 5a's false positives are spelling misses that llama's matcher shares, so the conclusion stands.
- **Junk vocabulary is census-only** (wider than `is_filler`); it is labelled as such.
- **Unconverted lossless originals** (no MP3 derivative) measured only 2. This is likely an undercount: Shorten lengths in metadata are unreliable.
- **The coverage-exclusion fix for piece 4's added holds** is estimated, not replayed.

## Files and re-run
- **Files** (all in `~/.llama-harness/piece45/`):
  - `dump.py` → `dump.jsonl` (all shows);
  - `p4.py`, `p4b.py` → `p4_files.jsonl`, `p4b_files.jsonl`, `p4_arms.json`;
  - `exempt_*.json` → `arm_*.jsonl` (`dump.py --exempt`, the patched-filter replays) → `p4c.py`/`p4c.json`;
  - `p5.py` → `p5_rows.jsonl`;
  - `p5c.py` (shift), `p5d.py` (order, encore), `p5ab.py` (5a/5b), `p5b2.py` (truncation);
  - `packets.py` → `packets/`.
- **Re-run:**
  ```
  cd ~/.llama-harness/piece45
  PY=/Users/shawn/projects/llama/.venv/bin/python
  $PY dump.py --jobs 7
  $PY p4.py && $PY p4b.py
  for k in segtag seg union conv; do $PY dump.py --exempt exempt_$k.json --out arm_$k.jsonl; done
  $PY p4c.py && $PY p5.py && $PY p5c.py && $PY p5d.py && $PY p5ab.py && $PY p5b2.py && $PY packets.py
  ```
