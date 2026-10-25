# tfw1-impl handback: fix wave part 1 (I-1 format choice, I-2 one derivative per original)

**Status: DONE (with concerns, below).** Branch `held-backlog-junk-filter`. Started at a693878. No push, merge or branch switch.

## Commits

| commit | what |
|---|---|
| `20a3102` | fix(junk): format by kept running time; one derivative per original (I-1 + first cut of I-2, tests, tsp + sci fixtures) |
| `c880759` | fix(junk): the derivative dedupe only drops, never reorders (I-2 revised after M2 found a wrong reorder; jrad fixture) |
| `bcfeef4` | test(junk): give the jrad2023-05-12 pin its live track tags (the slim capture drops `track`) |

Full suite at `bcfeef4`, run from the worktree root as `./.venv/bin/python -m pytest -q`: **5388 passed, 1 skipped, 8 deselected**. The baseline was 5372 / 1 / 8; the 16 new tests are the difference. Interpreter check: `./.venv/bin/python -c "import llama; print(llama.__file__)"` prints `.../worktrees/junk-filter/packages/llama/src/llama/__init__.py`.

**Pre-existing test expectations changed: none.** No existing test or fixture was edited. Three fixtures were added (`tsp2007-07-28.csb.flac24.json`, `sci1999-12-31.dsbd.shnf.json`, `jrad2023-05-12.json`, all from `scripts/capture_fixture.py --from-cache`). `test_short_keep_rule.py::test_short_keep_false_reproduces_today` globs every fixture, so these three are now also checked against the frozen v2.17.0 model with `short_keep=False`. It stays green.

## What was built, per requirement

All code is in `packages/llama/src/llama/junk.py`.

### I-1: format choice by kept running time
- `_choose_format(files, wanted, orig_tracks)` is the new `short_keep=True` path. Each format is run through `_keep_and_exclude` with the rule, then `_dedupe_duplicate_listings`, then `_dedupe_derivatives`. The winner is the format with the greatest total kept running time.
- Ties: the comparison is strict `>`, so an earlier `FORMAT_BY_AUDIO` format wins a tie.
- If no format keeps anything, the first format with any audio is returned, as before, so `excluded` still explains.
- Running time is measured **after both dedupes**. That way a format listed twice cannot win on doubled time. It is measured before `readmit`, because readmit names the winning format's files only and its position is unchanged.

### I-2: at most one derivative per original
- **Constants:**
  - `DUPLICATE_DERIVATIVE_REASON = "duplicate derivative"`, defined once.
  - `PREFER_VBR_DERIVATIVE = False` is the one named place for the preference. Its comment gives the ruling's measured basis (2,017 of 2,017 pairs: the plain copy is newer; `_vbr` bitrate is a median 2.6% higher). Flipping it to `True` is a one-line change.
  - `_derivative_preference` is the sort key: whether the stem ends in `_vbr`, compared with the constant, then the name.
- **The new step `_dedupe_derivatives(kept)`:**
  - It groups `source == "derivative"` files by `original` and keeps the lowest-key copy of each group.
  - Each dropped copy goes to `excluded` with the reason above and its `duration_sec`.
  - A file that is not a derivative, or has no `original`, is never grouped.
- `_dedupe_duplicate_listings` is byte-identical.

### Orchestrator ruling: `short_keep=False` is byte-identical to v2.17.0
- `filter_files` branches on `short_keep`. The `else` arm is a693878's loop and listing dedupe, verbatim, with `deriv_dropped = []` added. So with `short_keep=False` neither I-1 nor I-2 applies, and `final_kept(..., short_keep=False)` is unchanged.
- Pinned in three places:
  - `test_short_keep_false_keeps_the_first_non_empty_choice`
  - `test_short_keep_false_keeps_both_derivatives` (also covers `final_kept`)
  - the existing v2.17.0 equivalence test, now over 3 more fixtures.

### Where the I-2 step sits, and why
- **Order:** the junk arms + floor, then the short-keep rule (inside `_keep_and_exclude`), then `_dedupe_duplicate_listings`, then **`_dedupe_derivatives`**, then `readmit`, then play order.
- **After the short-keep rule:** the rule re-admits both copies of a short piece, so the dedupe has to see its output. It cannot run before the floor either, because that would move the two-pass median, which the global constraints forbid.
- **Before `readmit`:** a dropped copy sits in `excluded`, so `overrides.include` re-admits it exactly the way it re-admits a duplicate listing. The readmit code is unchanged; only its comment changed. Pinned by `test_include_re_admits_a_dropped_duplicate`, and by the jrad readmit case.
- **`ordering["short_kept"]`** is still `kept ∩ names the rule kept`. A dropped copy is never in it unless the operator re-admitted it, in which case it is in `kept`, the same as a re-admitted duplicate listing. Pinned by `test_a_short_doubled_pair_keeps_one_copy_and_short_kept_names_it_only`.
- **Play order: the step only drops, it never reorders.** `filter_files` decides track-tag vs filename order as if every dropped copy (not re-admitted) were still in `kept` (the `order_nums` lines). A dropped copy shares its kept copy's original, and so its track tag. The tags are therefore non-unique and the order stays filename order, exactly as before the step. The short-keep rule's play-order pool keeps both copies (a693878's pool, comment only), so its interior test reads the same order.
- **Why this changed between commits.** My first cut (`20a3102`) did the opposite: it collapsed the pool too, so a doubled tape would order like its single copy. Measurement 2 showed that this reorders exactly one library show, and wrongly:
  - `joerussosalmostdead-2023-05-12` (`jrad2023-05-12`). The uploader renamed its originals and their track tags went stale: `12.5 The Other One` is tagged 14 and `14.5 Bird Song` 13; `16.5 Morning Dew` is tagged 18, after the encore `17 Casey Jones` (17).
  - A stale derivative, `14 The Other One.mp3`, also points at `12.5 The Other One.flac`. Its duplicate tag is what kept the show in its correct filename order. The operator's titles, set break and encore follow that order.
  - Deduping it unmasked the stale tags. Bird Song moved before The Other One, and Morning Dew moved after the encore.
- `c880759` makes the step drop-only. Pinned by `test_the_derivative_dedupe_never_changes_play_order` and `test_jrad_stale_derivative_keeps_the_filename_order`. The jrad test carries the raw-cache track tags, plus a guard that those tags do reorder the tape once the stale copy is gone. Both tests are red on `20a3102` and green now.

## RED / GREEN

**RED** before any implementation: `./.venv/bin/python -m pytest -q packages/llama/tests/test_format_choice_and_derivatives.py` gave **10 failed, 5 passed**. The full output is in `tfw1-impl.log`.
- Failures:
  - I-1: `'Flac' == '24bit Flac'` on the tsp shape and on the longer-second-format test.
  - Constants: `module 'llama.junk' has no attribute 'PREFER_VBR_DERIVATIVE'`.
  - I-2: the `_vbr` copies were kept, e.g. `assert 58 == 29` on sci unrepaired and `max per original 2 == 1` on sci repaired.
- The 5 that passed are the pins: tie order, fallback, the two `short_keep=False` pins, and the no-`original` test.

**RED for the revision tests**, run against `20a3102` in a scratch `git archive` copy with `PYTHONPATH` shadowing (verified via `llama.__file__`): **2 failed, 14 passed**. The failures were `test_the_derivative_dedupe_never_changes_play_order` (`'track-tags' == 'filename'`) and `test_jrad_stale_derivative_keeps_the_filename_order`.

**GREEN:** the targeted files give `134 passed` (new + `test_short_keep_rule.py` + `test_junk.py`), and the full suite gives 5388 passed, 1 skipped, 8 deselected.

**Mutation check** (mandate 5: scratch copy, scratch cwd, `PYTHONPATH` shadow verified, `-B` with no bytecode). Each mutant's expected red test was named before it was flipped, and every mutant was caught by those tests:
- M2, first-non-empty on the new path: the tsp test and the longer-second test.
- M3, `>=` (ties go to the later format): the tie pin, plus `test_junk.py::test_filter_files_prefers_plain_flac_and_never_unions`.
- M4, prefer `_vbr`: the preference test, both pair tests, the include test and both sci tests.
- M5, no final derivative dedupe: the pair tests, the include test and the sci tests.
- M6, grouping files without an `original`: the no-`original` test, among 42 failures.
- The ordering rule was checked by the 20a3102 RED above.
- M1 (no dedupe in the pool) was run against the first cut and is moot after the revision.

## Tests added
All in `packages/llama/tests/test_format_choice_and_derivatives.py`.

**I-1:**
- `test_tsp_shape_whole_24bit_show_beats_one_short_16bit_file`: real fixture; `24bit Flac`, 33 tracks.
- `test_a_longer_second_format_wins_over_a_non_empty_first`
- `test_a_running_time_tie_is_broken_by_preference_order` (pin)
- `test_no_format_keeps_anything_falls_back_to_the_first_with_audio` (pin)
- `test_short_keep_false_keeps_the_first_non_empty_choice` (pin, against the v2.17.0 model)

**I-2:**
- `test_the_preference_is_the_plain_copy`
- `test_a_long_doubled_pair_keeps_the_plain_copy`: the reason and the full excluded entry.
- `test_a_short_doubled_pair_keeps_one_copy_and_short_kept_names_it_only`
- `test_the_derivative_dedupe_never_changes_play_order`
- `test_jrad_stale_derivative_keeps_the_filename_order`: real fixture plus raw-cache tags.
- `test_an_edge_short_untagged_pair_drops_like_the_single_copy` (pin)
- `test_include_re_admits_a_dropped_duplicate`
- `test_files_without_an_original_are_never_duplicates`
- `test_short_keep_false_keeps_both_derivatives` (pin, filter and `final_kept`)
- `test_sci_hand_repaired_show_ships_each_song_once`: real fixture, with the show's own include/exclude lists copied in as literals. 25 tracks; Countdown, Mean Mr. Mustard, Polythene Pam, Golden Slumbers and The End each appear once; the d4 post-show tracks stay out.
- `test_sci_unrepaired_ships_each_original_once`: 29 tracks, 29 drops.

No test reads `~/.llama`.

## Measurements
Everything is under `~/.llama-harness/piece4/fw1/`: scripts, JSON outputs and `.log` files. All reads are `read_text` on `~/.llama/cache` and `~/.llama/shows`; nothing there was opened for write, locked or fsynced.
- The old arm is a693878's `junk.py`, saved as `junk_a693878.py` (sha in `junk_a693878.sha`) and loaded as its own module. It is patched into `gather.final_kept` and `select_recording` with `mock.patch.object`; neither file was changed by FW1.
- `common.py` asserts that `llama` resolves inside this worktree.
- All three ran on the final `junk.py` (identical at `c880759` and `bcfeef4`).

### M1: cache format-choice scan (`m1_cache_format_scan.py`)
- 15,607 cached items (every `md_*.json`), 0 unreadable.
- **Format flips: mp3 0 (as required), flac 31** (`m1_flips.json`). Every flip moves from `Flac` to `24bit Flac` and raises both the track count and the running time.

| item | before | after |
|---|---|---|
| DSO2007-07-03.DSO07-07-03.24bit.flac | Flac 1t 105.3s | 24bit Flac 10t 3284.3s |
| JeffAustinBand2018-04-28.AKGC1000s | Flac 8t 3822.2s | 24bit Flac 12t 7130.0s |
| TTB2018-11-03.MK41.flac24 | Flac 1t 517.7s | 24bit Flac 12t 5933.8s |
| bonerama2008-07-10.matrix.flac24 | Flac 1t 338.2s | 24bit Flac 14t 6791.4s |
| dso2017-02-11.cp4.flac24 | Flac 1t 796.0s | 24bit Flac 18t 10147.1s |
| ftw2015-07-05.schoeps-sonosax.flac24 | Flac 7t 2578.4s | 24bit Flac 13t 9699.4s |
| furthur2010-06-29.neumann-km140.bauer.113049.flac24 | Flac 1t 321.7s | 24bit Flac 18t 10030.0s |
| furthur2011-12-31.dpa.russjcan.117905.flac24 | Flac 8t 4016.0s | 24bit Flac 18t 11705.1s |
| garaj2005-04-10_24bit | Flac 1t 998.7s | 24bit Flac 11t 8517.1s |
| gd1973-07-28.152004.SonyStereo.ECM.Moskal.t.flac24 | Flac 2t 2296.7s | 24bit Flac 20t 8245.3s |
| gd1975-06-17.fob.menke.motb.97078.flac24 | Flac 1t 195.1s | 24bit Flac 17t 6350.9s |
| gd1977-05-08.148737.SBD.Betty.Anon.Noel.t-flac2448 | Flac 3t 1725.3s | 24bit Flac 20t 9006.8s |
| gd1978-04-15.137402.sbd.msc.happyjack.flac24 | Flac 1t 261.4s | 24bit Flac 10t 4859.2s |
| gd1980-10-31.131907.stankiewicz.flac2496 | Flac 1t 374.3s | 24bit Flac 21t 8375.3s |
| gd1981-03-14.174928.aud.Bernstein.ackerman.noel.flac2496 | Flac 2t 814.3s | 24bit Flac 20t 8795.7s |
| gd1981-12-05.139179.beyers.craigl.flac2448 | Flac 1t 431.5s | 24bit Flac 21t 9039.3s |
| gd1982-08-28.158652.senn421.vita.miller.clugston.flac2496 | Flac 1t 430.5s | 24bit Flac 23t 9104.0s |
| gd1982-09-15.akg414.streeter.miller.118451.flac24 | Flac 1t 527.5s | 24bit Flac 19t 7436.6s |
| gd1984-04-20.141519...Noel.fix.t-flac2496 | Flac 1t 846.1s | 24bit Flac 9t 4308.4s |
| gd1985-07-01.144157.nak304.guy.pailes.miller.clugston.flac2496 | Flac 5t 0.0s | 24bit Flac 16t 7283.4s |
| gd1985-11-02.senn421s.nak300s.alexander.77906.flac24 | Flac 1t 456.0s | 24bit Flac 17t 7840.6s |
| gd1986-07-04.143038.FOB.Senn441.Akerman.Noel.t-flac2496 | Flac 3t 1230.3s | 24bit Flac 16t 5347.6s |
| gd1987-03-26.150850.senn441.lamarre.miller.2496 | Flac 1t 335.5s | 24bit Flac 19t 8245.9s |
| gd1990-04-02.145219.OTS.Senn.Hessberg.Miller.Noel.t-flac2496 | Flac 1t 354.6s | 24bit Flac 18t 8132.6s |
| gd1990-07-14.152773.5-1.tobin.flac1648 | Flac 7t 3661.5s | 24bit Flac 14t 6344.1s |
| gd1990-07-16.Nak100sSenn421.Hill.Keo.131229.Flac2496 | Flac 1t 1048.4s | 24bit Flac 23t 9303.4s |
| jgb2019-10-13.aud.c480b.ck63.mkh8040.nico11104.flac24 | Flac 1t 587.4s | 24bit Flac 14t 7752.2s |
| tf2013-01-19.flac | Flac 3t 2451.0s | 24bit Flac 27t 8951.5s |
| tsp2007-07-28.csb.flac24 | Flac 1t 60.8s | 24bit Flac 33t 10358.1s |
| ttb2017-02-24 | Flac 7t 4446.4s | 24bit Flac 9t 4615.8s |
| ymsb2007-04-14.blackfingers.flac24 | Flac 1t 70.6s | 24bit Flac 29t 9379.8s |

- **Kept changed without a flip:** mp3 111 items (1,970 files, all `duplicate derivative` drops); flac 0. **Non-I-2 drops, adds or reorders: 0 under both formats.**
- `m1b_group_shapes.py`: of the 1,970 collapsed groups, 1,947 are plain + `_vbr` pairs. 23 groups in 7 items have no `_vbr` member (stale or renamed derivatives), so name order decides them. These are listed in `m1b_group_shapes.json`, and `m1c_nonvbr_mtime.json` shows that name order keeps the newer file in 12 of the 23. Durations agree within 1 s in all 23.

### M2: whole library, final kept lists (`m2_library_kept.py`)
- 3,983 shows measured, 0 skipped, with `audio_format` mp3 from the config and each show's own `overrides.json`.
- **23 shows change, 414 files. Every one is a `duplicate derivative` drop of a `_vbr` copy. There are 0 other drops, 0 adds, 0 order changes, and 0 originals left with no copy (no song lost).** List in `m2_changed.json`:

| show | kept before -> after | I-2 drops |
|---|---|---|
| gratefuldead-1966-12-01 | 54->27 | 27 |
| gratefuldead-1968-10-13 | 22->11 | 11 |
| gratefuldead-1969-04-21 | 46->23 | 23 |
| gratefuldead-1970-06-07 | 29->27 | 2 |
| gratefuldead-1972-11-18 | 18->9 | 9 |
| gratefuldead-1973-10-29 | 47->24 | 23 |
| gratefuldead-1974-05-25 | 48->24 | 24 |
| gratefuldead-1974-09-11 | 45->23 | 22 |
| gratefuldead-1978-12-30 | 54->27 | 27 |
| gratefuldead-1987-06-30 | 50->25 | 25 |
| gratefuldead-1987-07-06 | 40->20 | 20 |
| gratefuldead-1988-03-27 | 42->21 | 21 |
| gratefuldead-1988-06-23 | 38->19 | 19 |
| gratefuldead-1989-07-18 | 40->20 | 20 |
| gratefuldead-1989-07-19 | 21->20 | 1 |
| gratefuldead-1989-08-19 | 38->19 | 19 |
| gratefuldead-1990-03-16 | 40->20 | 20 |
| gratefuldead-1990-07-14 | 42->21 | 21 |
| gratefuldead-1991-04-05 | 39->20 | 19 |
| gratefuldead-1991-06-25 | 34->17 | 17 |
| gratefuldead-1991-10-31 | 42->21 | 21 |
| gratefuldead-1995-03-18 | 36->18 | 18 |
| stringcheeseincident-1999-12-31 | 30->25 | 5 |

- These are the 20 wholly doubled GD shows plus the 3 hand-repaired shows of review I-2. The reviewer's 8 shows / 15 short `_vbr` files are a subset.
- **First-cut surprise, now fixed:** at `20a3102`, `joerussosalmostdead-2023-05-12` reordered (explained above). Two more shows, `gratefuldead-1970-05-06` and `gratefuldead-1985-11-10`, changed only the `order_source` label, with the same order. All three are gone at `c880759`.
- **Duration check** (`m2b_pair_durations.py`, `m2b_pair_duration_mismatch.json`): 13 of the 414 dropped `_vbr` copies differ from the kept plain copy by more than 2 s, and **in all 13 the dropped `_vbr` copy is the shorter, truncated one.** Examples:
  - `gd78-12-30d2t01_vbr.mp3` Sugaree: 16 s vs 725 s.
  - `gd78-12-30d2t03_vbr.mp3` I Need A Miracle: 71 s vs 260 s.
  - `gd95-03-18d1t10_vbr.mp3` Playing In The Band: 70 s vs 359 s.
  - `gd90-07-14d1t01_vbr.mp3` Shakedown Street: 775 s vs 817 s.
  - At a693878 the short-keep rule kept those truncated Sugaree / Miracle / PITB stubs on air.

### M3: selected recording (`m3_selection.py`)
- `run_select_recording` was re-run for every library show from its stored `provenance.json` candidate and assessment, with `replay.CacheOnlyIA` (no network, no LLM), the config's `[selection]`, and mp3. It ran once with each filter, into a scratch `ShowWorkspace` that was deleted afterwards. 3,983 measured, 0 skipped (1,720 have a single candidate recording).
- **The SELECTED recording changes on 20 shows** (`m3_changed.json`; "kept" is the two recordings' kept tracks, before -> after):

| show | before -> after | kept |
|---|---|---|
| gratefuldead-1966-12-01 | gd1966-12-01.sbd.32800.shnf -> gd66-12-01.sbd.ladner.8575.sbeok.shnf | 54/26 -> 27/26 |
| gratefuldead-1968-10-13 | gd1968-10-13.sbd.gans.miller.owen.9386.shnf -> gd1968-10-13.sbd.miller.owen.7772.sbeok.shnf | 22/11 -> 11/11 |
| gratefuldead-1969-04-21 | gd1969-04-21.sbd.clugston.6182.shnf -> gd1969-04-21.sbd.miller.88465.sbeok.flac16 | 46/20 -> 23/20 |
| gratefuldead-1970-05-06 | gd70-05-06.sbd.gans.94.sbefail.shnf -> gd1970-05-06.sbd.gans-hall.95.shnf | 18/11 -> 9/11 |
| gratefuldead-1972-11-18 | gd1972-11-18.sbd-set2.lai.9182.shnf -> gd1972-11-18.123077.sbd.miller.flac16 | 18/10 -> 9/10 |
| gratefuldead-1973-10-29 | gd1973-10-29.sbd.kaplan.1070.shnf -> gd1973-10-29.sbd.miller.32352.sbeok.flac16 | 47/25 -> 24/25 |
| gratefuldead-1973-11-14 | gd1973-11-14.sbd.miller.79049.flac16 -> gd73-11-14.sbd.vernon.5612.sbeok.shnf | 26/28 -> 26/28 |
| gratefuldead-1974-05-25 | gd1974-05-25.sbd.jmiller.205.sbeok.shnf -> gd74-05-25.sbd.moog.2635.sbeok.shnf | 48/24 -> 24/24 |
| gratefuldead-1974-09-11 | gd1974-09-11.sbd.unknown.4647.shnf -> gd1974-09-11.135883.sbd.miller.repatched.flac16 | 45/20 -> 23/20 |
| gratefuldead-1977-04-23 | gd1977-04-23.mtx.seamons.97596.sbeok.flac16 -> gd77-04-23.sbd.jerugim.1827.sbefail.shnf | 22/30 -> 22/30 |
| gratefuldead-1978-12-30 | gd1978-12-30.sbd.tonyg.8826.shnf -> gd78-12-30.sbd.miller.18092.sbeok.shnf | 54/27 -> 27/27 |
| gratefuldead-1981-12-09 | gd1981-12-09.sbd.miller.87349.sbeok.flac16 -> gd81-12-09.sbd.clugston.13061.sbeok.shnf | 24/24 -> 24/24 |
| gratefuldead-1983-10-08 | gd1983-10-08.senn441.silberman.miller.97883.sbeok.flac16 -> gd83-10-08.fob-aud.willy.11734.sbeok.shnf | 19/19 -> 19/19 |
| gratefuldead-1985-11-10 | gd1985-11-10.sbd.doughty.12202.shnf -> gd85-11-10.sbd.barbella.12264.sbeok.shnf | 38/20 -> 19/20 |
| gratefuldead-1987-07-06 | gd87-07-06.beyerM88s.connor.2583.sbeok.shnf -> gd1987-07-06.138790.pcm.sbd.miller.flac1644 | 40/22 -> 20/22 |
| gratefuldead-1988-03-27 | gd1988-03-27.sbd.jerugim.braverman.fix-406.3383.shnf -> gd88-03-27.matrix.braverman.17262.sbeok.shnf | 42/23 -> 21/23 |
| gratefuldead-1988-06-23 | gd1988-06-23.sbd.unknown.9456.shnf -> gd88-06-23.sennheiser.ladner.17407.sbeok.shnf | 38/21 -> 19/21 |
| gratefuldead-1990-03-16 | gd90-03-16.sbd.willy.5227.sbeok.shnf -> gd1990-03-16.sbd.miller.85201.sbeok.flac16 | 40/20 -> 20/20 |
| gratefuldead-1990-07-14 | gd1990-07-14.sbd.unknown.31950.shnf -> gd1990-07-14.sbd.miller.106403.flac16 | 42/21 -> 21/21 |
| gratefuldead-1991-06-25 | gd91-06-25.sbd.screenwriter.489.sbeok.shnf -> gd91-06-25.sbd.miller.26350.sbeok.shnf | 34/19 -> 17/19 |

- **Why they change.**
  - 16 of the 20: the doubled recording had been winning on its doubled completeness (kept / max kept).
  - The other 4 (1973-11-14, 1977-04-23, 1981-12-09, 1983-10-08): the two recordings shown are unchanged. A third sibling was doubled, and it set the `max_kept` denominator (56->28, 60->31, 48->25, 34->20), so every sibling's completeness rose and the ranking moved.
  - In every row, the "before" recording is also the stored `selection.json` recording.
- Context, not FW1: on 46 shows the old arm already differs from the stored `selection.json` (`m3_old_vs_stored.json`), from code and input drift since those shows were selected. M3 compares the two filters on identical inputs only.

## Concerns
1. **I-1 flips 31 cached items under flac, not the 2 the reviewer's narrow fix flipped.** Running time also fixes the pre-existing v2.17.0 class, where `Flac` holds a few floor-passing tracks of a partial copy and `24bit Flac` holds the whole show. Every flip gains tracks and time.
   - Production is mp3: 0 flips and 0 library effect.
   - The closest call is `ttb2017-02-24` (7 tracks / 4,446 s vs 9 / 4,616 s).
   - Where the two formats hold *different* parts of a show, one part is still lost, because the never-union rule is unchanged.
2. **Flipping `PREFER_VBR_DERIVATIVE` would ship truncated songs.** In all 13 library pairs whose durations differ, the `_vbr` copy is the truncated one (M2 duration check). I'd raise this with Shawn before any flip.
3. **23 non-`_vbr` groups fall to name order** (7 cached items: stale or renamed derivatives, typos). Name order keeps the newer file in 12 of the 23, and durations agree in all. In the library, the two such shows (`jrad2023-05-12`, the `ttb2022-07-08` show) were already operator-excluded on exactly the copy name order drops, so nothing changes there. Picking by newest `mtime` would match the ruling's "newer re-derivation" basis better, but the slim fixtures drop `mtime`. I left it as the operator's call.
4. **Operator excludes of `_vbr` files now match nothing.** I-2 drops those copies first, so gather logs `overrides.exclude entry ... matched no file` on hand-repaired shows: the sci show's 24 `_vbr` entries, plus jrad, ttb2022, 1970-05-06 and 1985-11-10. This is harmless: no refusal reads `exclude` (`override_keys`' dangling check covers titles, set_breaks and encore_after only). But it is log noise. Clearing those entries is optional cleanup.
5. **The 20 changed selections need llama-db's ruling for the bulk apply.**
   - `selection.json` persists, so a show re-selects only if its selection is redone.
   - Two of the 20 carry operator overrides on the currently selected recording: `gratefuldead-1970-05-06` (exclude) and `gratefuldead-1985-11-10` (exclude, set_breaks, encore_after). A re-select to the other recording would orphan those filename-keyed overrides.
6. **Docs for Task 23:** CLAUDE.md's "the winner is the first format whose **kept** set is non-empty" (Domain gotchas, `FORMAT_BY_AUDIO`) and the plan's Global Constraint on `filter_files`' format choice are superseded by I-1. I did not edit them, per scope. The doubled-derivative dedupe and `duplicate derivative` also want a CLAUDE.md line.
7. **Fixture convention:** `capture_fixture.py`'s slim shape drops `track`, so the jrad test injects the raw-cache tags as a literal (documented in the test). Any future fixture that depends on tags needs the same treatment.
