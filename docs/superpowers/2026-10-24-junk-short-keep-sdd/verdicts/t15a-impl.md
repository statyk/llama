# t15a-impl handback: briefing reuse refuses a briefing that mentions a restored file

**Status: DONE_WITH_CONCERNS.** The concerns are listed at the end. The headline one: on today's library, the gate as shipped leaves **0** reusable briefings among restored shows.

**Commit:** `49f9274 feat(replay): briefing reuse refuses a briefing that mentions a restored file`, on `held-backlog-junk-filter`, parent `251bbea`. I did not push or merge.

## What I built (packages/llama/src/llama/replay.py)

`briefing_reusable` now runs one more check, last, after `briefing_guard`. A rejection by any of the earlier checks still returns that check's existing reason.

- **Restored files.** These are tracks of the new show with `short_kept` set whose filename is not among the stored show's track filenames (requirement 1). With no restored file, `_restored_file_mention` returns None, so the function behaves exactly as it did after Task 11.
- **Fields scanned.** Every text field of `Briefing`, lowercased: `context`, `significance`, `per_set` (keys and values), `notable_moments`, `review_sentiment`, `cautions` and `mentioned_songs`. They are listed in `BRIEFING_TEXT_FIELDS`, and a test pins that list against `Briefing.model_fields` minus `narration` and `non_attendee_sentiment`, and checks it against what `_briefing_texts` actually reads.
- **Arm (a), names.** A briefing names a restored file if it contains any of these:
  - the file's basename;
  - its stem (`junk.basename_without_extension`);
  - its disc/track tail. The tail is taken from the stem by `_TRACK_TAIL`, for example `d3t04`, `s2t01`, `D3_T02`, `t14` or `track01`. In the prose it matches as `d3t04`, `d3_t04`, `s2t01`, `disc 3, track 4`, or a bare `t04`, with an alphanumeric boundary on the left.
- **Arm (b), wording.** Arm (b) fires on wording **anywhere** in the briefing, not only near a restored file (the conservative choice). The terms, in check order:
  1. `excluded` (exclude/excluded/excludes/excluding/exclusion)
  2. `implausibly short`
  3. `too short`
  4. `left out` (left/leave/leaves/leaving + out/off)
  5. `omitted` (omit/omits/omitted/omitting/omission)
  6. `absent` (absent/absence)
  7. `not present`
  8. `missing`
  9. `dropped` (dropped/dropping)
  10. `not represented`
  11. `not part of`
  12. `not a track` (`not [a|as a|its own] [separate|titled|distinct|individual] track(s)`)
  13. `track count`: a number (digits or words up to sixty, compounds like `twenty-one`) followed by `tracks`, `songs` or `files`; or `N-track`, `N-song`, `N-file`; or `tracks N through/to/-/– M`.
- **Reason text.** The prefix is fixed: `briefing mentions a restored file: names <filename> in <field>` or `briefing mentions a restored file: says '<term>' in <field>`. The first hit wins: files in track order, then the terms in the order above.
- **Callers.** `compute_legs` (replay.py:371), and through it `reapply` and the harness, needed no change.

## The vocabulary decision and the measurement

All reads were read-only. Outputs are only under `~/.llama-harness/piece4/ckb/15a/`. I wrote nothing under `~/.llama` or the station share.

- **Rows.** The input is the 1,014 rows of `held_reuse.json` with `reason` null: 901 have arm `reuse`, and 113 have arm `none` (held).
- **Dump.** `dump_15a.py` re-ran `compute_legs` on each row's re-keyed shadow, the same way `held_reuse.py` does. It recorded each row's restored files and its stored briefing (`dump.jsonl`). There were 0 errors.
- **Every row has a restored file.** All 1,014 rows have at least one, and every restored file is in the stored `show.json`'s `excluded_files`. So the briefing LLM saw every one of them as excluded, which is premise 4's structural cause.
- **Counts.** `final_15a.py` computes them through the shipped functions (`_restored_mentions` / `_restored_file_mention`). Output: `final.txt`, `final.json`.

**Headline: the gate refuses 1,014 of 1,014 rows (901 of the 901 arm rows). Still reusable: 0 of 1,014 and 0 of 901.**

Rows where each arm fires (a row can fire both):

| | arm a fires | arm b fires | a only | b only | both |
|---|---|---|---|---|---|
| of 1,014 | 406 | 1,014 | 0 | 608 | 406 |
| of 901 | 369 | 901 | 0 | 532 | 369 |

Per term, the rows where it fires, and the rows where it is the only hit:

| term | of 1,014 | of 901 | only hit |
|---|---|---|---|
| a: filename | 84 | 76 | 0 |
| a: stem (without the filename) | 44 | 40 | 0 |
| a: tail (without filename or stem) | 279 | 254 | 0 |
| b: excluded | 677 | 607 | 5 |
| b: implausibly short | 788 | 711 | 0 |
| b: too short | 55 | 46 | 0 |
| b: left out | 437 | 387 | 5 |
| b: omitted | 45 | 39 | 0 |
| b: absent | 66 | 61 | 1 |
| b: not present | 199 | 180 | 0 |
| b: missing | 180 | 161 | 0 |
| b: dropped | 89 | 79 | 0 |
| b: not represented | 8 | 8 | 0 |
| b: not part of | 139 | 120 | 0 |
| b: not a track | 22 | 15 | 0 |
| b: track count | 886 | 792 | 5 |

First hit, which is the reason the gate returns: names a file 406; excluded 389; implausibly short 133; left out 49; too short 25; track count 5; absent 3; not part of 2; missing 1; not present 1.

### Nested vocabularies (`variants.txt`), and why the larger ones are kept

| vocabulary | refuses of 1,014 | refuses of 901 | rows let through |
|---|---|---|---|
| V0: brief minimum (`excluded`, `implausibly short`, `left out/off`) plus filename/stem | 998 | 889 | 16 |
| V1: V0 plus tail, `omit`, `absent`, `not present`, `missing`, `dropped`, `not represented`, `not part of`, `not a track` | 1,009 | 898 | 5 |
| V2: V1 plus `too short` | 1,009 | 898 | 5 |
| V3: V2 plus `track count` (shipped) | 1,014 | 901 | 0 |

**V0 to V1.** I hand-read the first hit on each of V0's let-through rows. Several are real absence claims that the minimum misses:
- `dawes-2011-12-07`: t06/t08 named;
- `discobiscuits-2009-12-31`: "three short files are not part of the setlist: t01 … t07 … t18";
- `elliottsmith-2000-05-08`: "file 1 (d1t01, 44 seconds …) is not a song";
- `johnkadlecik-2013-04-13`: "three additional songs that are absent from the show data";
- `perpetualgroove-2005-04-01`: "dropped from the track list as too short".

The others are over-refusals, which only cost a brief:
- `cracker-1991-11-10`: "absence of breaks";
- `stevekimockband-2004-08-21`: "Jim Kost's absence";
- `johnkadlecik-2010-05-10`;
- `deadandcompany-2016-07-09`: "the setlist taken from file names … was missing 'Cassidy' …", about a source setlist that has since been corrected;
- `drive-bytruckers-2006-06-22` and `greatamericantaxi-2008-07-19`, refused by `not part of`; both describe the restored intro accurately.

**Earlier draft.** It lacked "left off" and "leaves out". I hand-read the 8 rows that a first draft let through. That reading found `tedeschitrucksband-2016-01-17` ("A 31-second opening file was **left off** the program as too short"), a real false claim, and `trampledbyturtles-2008-03-06` ("the show data **leaves out** three short archive tracks"). So I widened `left out` and added `too short`.

**V2 to V3 (`track count`).** These are the 5 rows refused only by a count, each hand-read:
- `gratefuldead-1970-06-07` (arm none, held): "Set 1 … nine tracks". **This is a real false claim.** Two `d1t03` files are restored into set 1, so set 1 now has 11 tracks. Nothing else in the briefing catches it.
- `joerussosalmostdead-2018-11-08` (reuse): "five-song segued suite", "three-song". Safe: the restored Band Intro and Encore Break are described as present ("a short band-intro track (about 1:14)", "a separate encore-break track").
- `papadosio-2008-08-02` (reuse): "all nine songs". Safe: the restored Set Intro is described as "file 1".
- `soundtribesector9-2004-06-18` (none): "seven songs", "two songs". Safe: "counts the 16-second stage-talk file as track 1".
- `soundtribesector9-2011-07-14` (reuse): "twelve songs", "two-song encore". Safe: "runs about 1:57 including the one-minute set intro".

I kept `track count` for two reasons:
- It catches a real false claim (GD 1970) at a cost of 4 safe briefings, 3 of them in the arm.
- The p4 reader found song and track counts made false by restored *songs*: 1976 "Fifteen tracks", 1977-11-06 "Ten songs", 1973 "Thirteen tracks". A future row whose only stale claim is a count would otherwise ship.

**Dropping `track count`** is a one-line change to `_RESTORED_WORDING` (and its test cases). It would let through 5 of 1,014 and 3 of 901. Of the 5, 4 are safe and 1 (GD 1970, held) ships "nine tracks" if it is ever reused.

**Evidence that the gate is conservative:**
1. Every row a narrower vocabulary lets through was hand-read. The rows that carried a stale claim (TTB, GD 1970, and the V0 to V1 cases above) made me widen the vocabulary.
2. Arm (b) fires anywhere and never needs to be near a file name.
3. Matching is case-insensitive.
4. The stem and tail patterns match substrings. A short or odd stem can only add refusals.

## RED and GREEN

**RED** (tests written first, before any code): `./.venv/bin/python -m pytest packages/llama/tests/test_replay.py -q -p no:cacheprovider -k "restored or absence or neither or already_kept or no_restored or case_insensitive or text_field or bare_track or anywhere"` gave `36 failed, 3 passed, 102 deselected`.
- The 3 that passed are the pins, which hold on today's code: neither mention, already-kept short file, no restored file.
- The failures included every wording case (for example `test_each_absence_wording_refuses[... track count]`), the anywhere test, case-insensitivity, all 8 field cases, and the field pin.

**GREEN:** `./.venv/bin/python -m pytest packages/llama/tests/test_replay.py -q -p no:cacheprovider` gave `141 passed`.

**After GREEN** I added two wording cases ("leaves out", "not part of") with their patterns, and strengthened the field pin. Result: `143 passed`. These two cases were not run RED separately. On the base code they cannot pass, because base never refuses on wording.

**Mutants** (in a scratch `git ls-files | tar` copy, import shadowing verified, each red test predicted beforehand). Both were caught exactly as predicted:
- **M1**, restored = every `short_kept` track (the stored-filename filter dropped): only `test_an_already_kept_short_file_does_not_trigger_the_gate` failed.
- **M2**, the `missing` term deleted: only `test_each_absence_wording_refuses[...missing]` and `test_wording_refuses_anywhere_not_only_about_the_restored_file` failed.

**Full suite:** `./.venv/bin/python -m pytest -q -p no:cacheprovider` gave `5117 passed, 1 skipped, 8 deselected, 26 warnings in 84.01s`. The baseline was 5076, plus 41 new test cases. I confirmed `llama.__file__` resolves inside the worktree.

**Tests added**, in `packages/llama/tests/test_replay.py`, section "Task 15a":
- a restored file named in cautions refuses (with a control);
- stem and shorthand refuse: the stem, `d3t04`, `(d3t03, d3t04)`, `disc 3, track 4`, `D3_T04`;
- a bare `t14` tail refuses;
- each wording term refuses (20 cases);
- wording refuses anywhere;
- a briefing mentioning neither still reuses **(pin)**;
- an already-kept short file does not trigger the gate, even when the briefing names it and says "implausibly short" **(pin)**;
- no restored file keeps today's rule, and earlier reasons come first **(pin)**;
- case-insensitive;
- every text field is read (8 cases);
- the field list matches `Briefing` **(pin)**.

## Files changed
- `packages/llama/src/llama/replay.py`
- `packages/llama/tests/test_replay.py`

Measurement files, outside the repo, read-only against `~/.llama`, all in `~/.llama-harness/piece4/ckb/15a/`:
- scripts: `dump_15a.py`, `vocab_15a.py` (exploratory), `final_15a.py`, `variants_15a.py`;
- outputs: `dump.jsonl`, `vocab_hits.json`, `escapes.txt`, `escapes_full.txt`, `final.json`, `final.txt`, `variants.txt`.

Run them from the worktree root with `./.venv/bin/python`. The dump needs `scripts/` on the path, as `held_reuse.py` does.

## Concerns
1. **There is no reuse at all among restored shows today.** The gate refuses all 1,014 rows, compared with the ruling's estimate of about 98% (992 by the earlier proxy). The ruling budgets about 1,000 fresh briefings, so the extra roughly 22 briefs stay within what the operator accepted. I therefore did not treat this as BLOCKED. If the operator wants a little reuse back, the cheapest lever is to drop `track count`: 5 rows are let through, 1 of them carrying a real stale count.
2. **A possible duplicate listing (outside my scope; flagged for the Review Focus 2 owner).** `gratefuldead-1970-06-07` restores both `gd70-06-07d1t03.mp3` and `gd70-06-07d1t03_vbr.mp3` as short-kept tracks 3 and 4, both titled "My Dog Has No Nose", and also `gd70-06-07d3t01_vbr.mp3`. It looks like an mp3 and a `_vbr` derivative of the same original were both kept. I did not investigate it further.
3. The gate reads the briefing as passed in, and `briefing_guard` reads the normalised form. The raw form contains everything the normalised one does, so the gate can only refuse more. In `compute_legs` the two are already identical (`_read_briefing` normalises).
4. Spec 5.3's text is not updated; that is Task 23, per the brief.
