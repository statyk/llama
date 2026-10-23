# fixwave handback: the fix wave after Checkpoint B (title hygiene, piece 3)

Status: DONE_WITH_CONCERNS (the concerns are judgement calls for review, listed below. Nothing is blocked.)

Branch held-backlog-title-hygiene. Four commits on 174995e, each one green:

| F | commit | subject |
|---|---|---|
| F1 | `95c6bb2` | fix(lossless_titles): demote unconfirmed tags on a shifted delivered tag set (C-1) |
| F2 | `efafc8c` | fix(replay): record the cascade on needs-LLM rows; attribute C-1 demotions (I-1) |
| F3 | `8cf89c5` | fix(title_hygiene): cosmetic constants from Checkpoint B ruling 5 (M-1, M-6) |
| F4 | `c49cdd1` | chore(title_hygiene): Fable's fix-before-merge minors (ruling 8) |

Final full suite: `./.venv/bin/python -m pytest -q -p no:cacheprovider` gives **4783 passed, 1 skipped, 8 deselected, 26 warnings in 71.94s**. The baseline at 174995e was 4762 passed.

Checks:
- `git diff main -- packages/llama/src/llama/setlist.py` is empty.
- No protected name was edited: the 174995e..HEAD diff touches none of `placeholders.py`, `structure.py`, `siblings.py`, `songs.py`, `taper.py`, `setlist.py` or `junk.py`, and a grep of the diff for the protected names finds only one comment that mentions `taper._SET_HEADERS`.
- The pins in `test_titles.py`, `test_structure.py` and `test_siblings.py` are unedited. The one exception is the docstring line in test_titles.py:60 that F4 asks for.
- The untracked `acceptance.md` was not touched.
- llama resolves to the worktree: `./.venv/bin/python -c "import llama; print(llama.__file__)"` prints `.../worktrees/title-hygiene/packages/llama/src/llama/__init__.py`.

## Consolidated RED on 174995e

I built a scratch copy with `git archive 174995e`, put HEAD's eight changed test files over it, and ran it shadowed. The copy imported its own code: `llama.__file__` and `herder.__file__` both resolved inside the copy. I used a separate `PYTHONPYCACHEPREFIX` and ran with no cacheprovider. Command:

```
PYTHONPYCACHEPREFIX=$S/.pyc PYTHONPATH=$S/packages/llama/src:$S/packages/herder/src:$S/packages/emcee/src:$S/packages/transmitter/src \
  <worktree>/.venv/bin/python -m pytest -q -p no:cacheprovider packages/llama/tests/test_lossless_titles.py \
  packages/llama/tests/test_title_cascade.py packages/llama/tests/test_replay.py scripts/test_replay_holds.py \
  packages/llama/tests/test_desc_list.py packages/llama/tests/test_title_hygiene.py \
  packages/llama/tests/test_title_cosmetics.py packages/llama/tests/test_stage_gather.py
```

Result: **25 failed, 613 passed**. The failures:

```
F1  test_lossless_titles.py::test_shifted_delivered_set_demotes_the_unconfirmed_tag_darkstarorchestra_2014_07_31
F1  test_lossless_titles.py::test_shifted_delivered_set_demotes_every_other_unconfirmed_real_tag
F1  test_lossless_titles.py::test_one_shifted_delivered_tag_changes_nothing            (AttributeError only: negative pin)
F1  test_lossless_titles.py::test_shifted_delivered_set_keeps_filler_and_unreal_tags
F1  test_lossless_titles.py::test_no_reference_no_delivered_shift_demotion             (AttributeError only: negative pin)
F1  test_lossless_titles.py::test_lossless_off_by_one_skip_wins_over_the_delivered_shift (AttributeError only: negative pin)
F1  test_lossless_titles.py::test_readmitted_file_tag_is_demoted_on_a_shifted_set
F1  test_title_cascade.py::test_shifted_mp3_tag_set_darkstarorchestra_2014_07_31
F1  test_title_cascade.py::test_shifted_set_demotion_never_touches_an_override
F2  test_replay.py::test_stored_llm_not_self_filled_stays_needs_llm
F2  test_replay.py::test_cascade_record_carries_the_shifted_set_demotions
F2  test_replay.py::test_record_carries_title_fields                                   (_CASCADE_KEYS gains c_demoted)
F2  scripts/test_replay_holds.py::test_added_hold_attributed_from_declines
F3  test_desc_list.py::test_leading_segue_marker_is_stripped_deepbananablackout_2004_04_01
F3  test_desc_list.py::test_trailing_caret_and_dollar_markers_are_stripped
F3  test_desc_list.py::test_c_title_strip_shares_the_trailing_marker_set
F3  test_desc_list.py::test_duration_glued_after_a_parenthesis_darkstarorchestra_2011_04_15
F3  test_title_hygiene.py::test_lone_encore_setbreak_intermission_are_header_shapes
F3  test_title_cosmetics.py::test_strip_leaving_an_empty_or_edited_bracket_pair_is_declined
F3  test_title_cosmetics.py::test_leading_artist_prefix_stripped_greenskybluegrass_2013_05_04
F3  test_title_cosmetics.py::test_trailing_h2_recorder_suffix_stripped_lotus_2008_02_07
F3  test_title_cosmetics.py::test_leading_encore_dash_stripped_gratefuldead_1974_10_18
F3  test_title_cosmetics.py::test_new_shapes_keep_the_acceptability_test
F3  test_title_cascade.py::test_cosmetic_strip_receives_the_show_artist
F4  scripts/test_replay_holds.py::test_summary_states_the_disabled_slices_of_both_arms
```

The per-item REDs below were captured in the live worktree, before each implementation. They are also in `fixwave.log`.

## F1. C-1: a shifted delivered tag set (ruling 1, preferred fix)

**What changed**

`lossless_titles.apply_lossless`, after C2. The demotion runs only when C has a reference `ref` and was not skipped by the lossless off-by-one rule. It computes `delivered_shift`: the positions where the delivered tag is `_real`, does not `agrees` with `ref[i]`, and does agree with `ref[i±1]`. `_real` and `agrees` are the same tests C already uses, unmodified. When `len(delivered_shift) >= 2`:
- Every delivered tag that is `_real`, not `is_filler`, not in `changed` (C's confirmed C1 and C2), and does not agree with `ref[i]` is set to `""` and listed in the new `LosslessResult.demoted` (0-based, ascending).
- The source at those positions stays the incoming tag source, so `resolve_titles` reads the blank as an S position or as `unresolved`.
- One note is written: `lossless titles: shifted delivered tag set; unconfirmed tags demoted: tracks <n>, <n>` (`demoted_note()`, with the prefix constant `SHIFTED_DELIVERED_NOTE`).
- `LosslessResult.demoted` defaults to `()`.

`gather._without_override_positions` now also restores any demoted position that is an `overrides.titles` position, drops it from `demoted`, and rebuilds the single note, or removes it when nothing is left. This respects Review Focus 2.

**Tests**
- `test_lossless_titles.py`:
  - a verbatim darkstarorchestra-2014-07-31 fixture: the description, the 21 stems, MP3 and FLAC titles and lengths, copied read-only from `~/.llama/cache/md_dso2014-07-31.461.bsc1.littlebox.json` and exported as `DSO_2014_07_31_*` / `dso_2014_07_31_files()`;
  - a synthetic "every other" case;
  - the threshold-2 negative case;
  - the filler and placeholder tags are kept;
  - no reference means no demotion;
  - the lossless skip wins;
  - a re-admitted file is demoted.
- `test_title_cascade.py`:
  - `test_shifted_mp3_tag_set_darkstarorchestra_2014_07_31`, at gather level through `compute_gather`. Track 3 is not "Duprees Diamond Blues" and its source is one of `unresolved`/`desc-position`/`setlist`. The show is held, flagged, or ships no unconfirmed tag. Tracks 4-20 are the FLAC titles with source `sibling-format`, and paths 4-20 are `C2`. The note is present. With slice 3 off, track 3 ships the shifted tag.
  - `test_shifted_set_demotion_never_touches_an_override`: an override at 3 keeps its title and source `override`, `demoted == ()`, and there is no note.

**RED** (worktree, before implementation):
```
./.venv/bin/python -m pytest packages/llama/tests/test_lossless_titles.py -q
E  AssertionError: assert ('Duprees Diamond Blues' == ''
E  At index 3 diff: 'Big River' != ''
E  AttributeError: 'LosslessResult' object has no attribute 'demoted'
E  ... 'Morning Dew' == ''
7 failed, 28 passed
./.venv/bin/python -m pytest packages/llama/tests/test_title_cascade.py -q -k "darkstarorchestra or override"
E  AssertionError: assert 'duprees diamond blues' != 'duprees diamond blues'
E  AttributeError: 'LosslessResult' object has no attribute 'demoted'
2 failed, 15 passed, 23 deselected
```

**GREEN**:
- `./.venv/bin/python -m pytest packages/llama/tests/test_lossless_titles.py packages/llama/tests/test_title_cascade.py -q` gives 75 passed.
- Full suite: 4771 passed, 1 skipped, 8 deselected.

**Re-measure of the four signature shows.** This was a read-only `compute_gather` probe from the cache, all slices, no overrides (the fresh-get title view), with no harness arm written:
- **darkstarorchestra-2014-07-31.** Track 3 becomes `unresolved`. The notes are `lossless titles: shifted delivered tag set; unconfirmed tags demoted: tracks 3` and `positional fill declined: desc-position track 3 slot placeholder '?'`. The show is **held** on `unresolved track titles`, where at 174995e it was clean. Tracks 4-20 are C2 and 21 is C1, unchanged.
- **lettuce-2002-07-13.** Unchanged, and nothing is demoted. Tracks 10 `Superfred` and 16 `Headin' Home (Josh Redman)` agree with the taper's 16-entry list at their own positions. The cleaned entries 10 and 16 read exactly `Superfred` and `Headin' Home (Josh Redman)`, so both are confirmed by the reference (M-7). Clean.
- **tedeschitrucksband-2019-02-15.** Unchanged. This is the 14/15 swap: every other delivered tag agrees with the list at its own position. Clean.
- **tedeschitrucksband-2020-01-15.** Unchanged, and nothing is demoted. Clean.

## F2. I-1: the cascade record on needs-LLM rows (ruling 4)

**What changed**
- `replay.py`: `r.cascade = _cascade_dict(g.title_record)` on every replayed row. Unreplayable rows keep `{}`; the existing pin in `test_record_carries_title_fields` still holds. The `ShowReplay` comment now records the deviation and why it is safe.
- `_cascade_dict` gains `c_demoted`: F1's demotions, 1-based. In `scripts/replay_holds.py`, `SLICE_OF_DECLINE` gains `("c_demoted", "slice3")`, so a hold that F1 adds is attributed and not left "unattributed". (Judgement call J5.)
- `_d_reach`'s note and `desc_position` fallback is **kept**, with its docstring rewritten. It is not dead: `compare` still reads arms written before this change, and those carry `{}` on needs-LLM rows. On a current arm the note arm and `d_failed` agree, because the show-level note names the first failed check.

**Tests**
- `test_stored_llm_not_self_filled_stays_needs_llm` now asserts `outcome == "needs-llm"`, `list(r.cascade) == _CASCADE_KEYS` and `d_fills == [2,3,4,5,6]`, `d_failed is None`.
- `_CASCADE_KEYS` gains `c_demoted`.
- New: `test_cascade_record_carries_the_shifted_set_demotions` (the DSO fixture: `c_demoted == [3]`).
- `test_added_hold_attributed_from_declines` gains a `c_demoted` row, which must be attributed to slice3.

**RED**:
```
./.venv/bin/python -m pytest packages/llama/tests/test_replay.py scripts/test_replay_holds.py -q -k "needs_llm or cascade or attributed"
E  AssertionError: assert [] == ['s_mode', 's..._failed', ...]
E  KeyError: 'c_demoted'
E  AssertionError: assert 'demote' in ' (1)\n  multi\n-- '
3 failed, 14 passed, 167 deselected
```

**GREEN**:
- test_replay, test_replay_holds and test_reapply: 249 passed.
- Full suite: 4772 passed, 1 skipped, 8 deselected.

## F3. Cosmetic constants (ruling 5; M-1, M-6)

**What changed**

D cleaning (`desc_list.py`):
- `_LEAD_SEGUE = ^\s*(?:-->|->|=>|>)\s*`, applied first in `_finish`.
- `_TRAIL_MARKERS` gains `\^+|\$+` and stays ONE definition: `lossless_titles` still imports it, and a test asserts `lt._TRAIL_MARKERS is desc_list._TRAIL_MARKERS`.
- `_PAREN_TIME = (?<=\))(<m:ss|h:mm:ss>)\s*$` joins the duration step. It does not set `trailing_time_stripped`, because it is not R19's form.

Slice 5 (`title_cosmetics.py`):
- `_strip` order: leading time, stem, tail, then artist prefix, `Encore- `/`Encore - ` (`^\s*encore ?- `, case-insensitive), then a trailing ` H2` (`\s+H2\s*$`, case-sensitive).
- The artist prefix is the text before the first ` - `, kept only when `fuzzy_norm_title(prefix) == fuzzy_norm_title(artist)` and is non-empty.
- `cosmetic_strip(tracks, *, artist=None)`. `compute_gather` passes its `artist`. The M-6 debris veto `_bracket_debris(old, new)` is ANDed with the existing acceptability test.
- `E: ` is untouched.

Check 1 (`title_hygiene.py`): `_LONE_MARKER = ^\s*(?:encore\s*:?|set ?break|intermission)\s*$` (case-insensitive) is ORed with `is_header_shape`, giving `hygiene:header`. `desc_list.is_header_shape` and `taper._SET_HEADERS` are untouched.

**Tests.** Each embeds verbatim cache excerpts and cites its slug:
- deepbananablackout-2004-04-01: the description excerpt, `-->` entries and `Boot!^`.
- mymorningjacket-2004-06-18: the Disc 2 excerpt, `cobra          $`.
- darkstarorchestra-2011-04-15: the Disc 3 excerpt, `Playing In The Band(reprise)6:51` giving `Playing In The Band(reprise)` with duration 411.0. `1 Samuel 15:23` is unchanged from today.
- zentricksters-2002-12-31: `Banks of the Ohio (actually d2t10)`, plus `Esau (s2t01)`.
- greenskybluegrass-2013-05-04: the tags `Greensky Bluegrass - d2t07-In Control` and others.
- lotus-2008-02-07: `d01t01 Lucid Awakening H2`.
- gratefuldead-1974-10-18: #24 `5:46] Encore- U.S.Blues`.
- M-1: a lone-marker pin, with no slug named in the brief.
- Wiring: `test_cosmetic_strip_receives_the_show_artist` in test_title_cascade.py, which runs `compute_gather` with the artist prefix on the gd73 fixture.

**RED** (worktree; a truncated excerpt, the full list is in the consolidated RED above):
```
E  AssertionError: assert ('--> Take the Time' == 'Take the Time'
E  AssertionError: assert 'Boot!^' == 'Boot!'
E  AssertionError: assert ('Playing In T...(reprise)6:51' == 'Playing In The Band(reprise)'
E  AssertionError: Encore  assert (True, None, None) == (False, 'show...giene:header')
E  assert ('Esau ()', [...au ()'"], [0]) == ('Esau (s2t01)', [], [])
E  TypeError: cosmetic_strip() got an unexpected keyword argument 'artist'
E  AssertionError: assert 'Lucid Awakening H2' == 'Lucid Awakening'
E  AssertionError: assert 'Encore- U.S.Blues' == 'U.S.Blues'
E  AssertionError: assert 'Grateful Dead - Morning Dew' == 'Morning Dew'
```

**GREEN**:
- desc_list, title_hygiene, title_cosmetics, stage_gather and lossless: 414 passed.
- Full suite: 4783 passed, 1 skipped, 8 deselected.
- After moving the wiring test out of test_stage_gather.py (amended into F3): test_title_cascade plus test_stage_gather give 272 passed.

## F4. Fable's fix-before-merge minors (ruling 8)

- **M-6:** done in F3.
- **`_sibling_transfer` sweep.** Comments and docstrings only, at:
  - gather.py: the `_dedupe_ordered` docstring, the `load_donor_tapes` docstring and the `best_donor` docstring;
  - titles.py: the `resolve_titles` docstring;
  - cli.py: the `_sibling_proposal` docstring;
  - test_stage_gather.py: the section comment at :323, and the docstring and comment of `test_a_sibling_fetch_failure_is_noted_not_fatal`;
  - test_titles.py:60.

  They now name `_sibling_transfer_full`, or "the transfer pass (then `_sibling_transfer`)" where the text is historical. The remaining `_sibling_transfer` mentions are its own definition and its pin test, which are correct.
- **`test_cosmetic_strip_off_when_slice5_disabled`** now uses `enabled_slices=title_hygiene.ALL_SLICES - {"slice5"}`.
- **Compare summary** now reads `disabled slices: base [...], cand [...]`. New test: `test_summary_states_the_disabled_slices_of_both_arms`.
  - RED: `E assert 'disabled slices: base ["slice5"], cand []' in [...]`, 1 failed.
  - GREEN: test_replay_holds gives 90 passed.
- **Floor test:** `test_agreement_exactly_at_floor_passes` is deleted, and its share assertion (`_dl("One Way","Two Way")` against `_canon("One Way","Other Song")` gives 0.5) is folded into `test_decide_d_agreement_exactly_at_floor_passes`. The Survivors section of `docs/superpowers/2026-10-23-title-hygiene-sdd/mutation.md` gains the resolution line as the brief words it.
- Full suite: 4783 passed, 1 skipped, 8 deselected.

## Judgement calls (each pinned by a test where it is behavioural)

- **J1 (F1): the lossless off-by-one skip wins.** When C is skipped for the show (two or more LOSSLESS tags shifted), C changes nothing and demotes nothing, even if the delivered set is shifted too. This is the narrowest reading of "after C chooses its reference": the demotion is part of C acting. Pin: `test_lossless_off_by_one_skip_wins_over_the_delivered_shift`. The demotion also runs only when there is a reference and C is in scope with a lossless format, because the out-of-scope and no-lossless returns come earlier.
- **J2 (F1): the re-admitted file is demoted.** A file in `kept` but not in `recovery_basis` has no lossless title. Its delivered tag still counts in the signature and is demoted like any other unconfirmed real tag. This follows the brief's "every OTHER delivered real, non-filler tag" literally, and it is the safe direction on a strict surface. The module docstring's "never changed" was about C's replacement. Pin: `test_readmitted_file_tag_is_demoted_on_a_shifted_set`. Re-admitted files are rare; the opposite reading would ship a possibly shifted tag.
- **J3 (F1): override positions still count in the signature.** An override position's delivered tag counts toward the signature as evidence about the tape, but it is never demoted and never named in the note (`_without_override_positions`). With an override at track 3 on DSO, the signature is still 18, so nothing else is demoted and no note is written. Pin: `test_shifted_set_demotion_never_touches_an_override`.
- **J4 (F1): demoted positions are not in `c_changed`.** They are not added to the 2b/2c/2d skip set and not to the "C acted" test for the format-sibling note: a demoted tag is real, so 2b never notes it. `title_paths` gives no path to a demotion, because it is not a fill. The demotion is visible in `title_record.lossless.demoted` and, after F2, in the harness record as `c_demoted`.
- **J5 (F2): `c_demoted` is a harness record key.** It was not explicitly asked for. I added it so that holds created by F1 are attributed to slice3 in `holds_delta.txt` (ruling 4's "every added hold is attributed"). Pinned in test_replay and test_replay_holds.
- **J6 (F3): M-6 has two arms.** The veto declines when the result contains an empty `()` or `[]` (the literal rule), OR a bracket pair the original title did not have (a strip that cut inside a pair). The second arm is needed because the brief's own example `Banks of the Ohio (actually d2t10)` strips to `(actually )`, which is not an empty pair; ledger cpb-k09 shows this is the case the brief means. A pair the strip leaves intact (`Booty Jam(Bend Over)`) is kept, and a leading `[05:12] ` still strips because the strip removes the whole pair. Pin: `test_strip_leaving_an_empty_or_edited_bracket_pair_is_declined`.
- **J7 (F3): `1 Samuel 15:23` keeps today's D cleaning (`1 Samuel`).** The new glued-duration rule fires only directly after `)`, so a number inside a title is never touched by it. I did NOT revert the existing trailing-`m:ss` strip, which the plan pins (`test_duration_forms`) and Checkpoint A handled as R19; ruling 5 does not mention it. Slice 5 still never strips it (existing pin). If the brief's "stays" was meant to remove R19's strip, that is a separate ruling.
- **J8 (F3): `Encore:` keeps `hygiene:no alnum`.** A lone `Encore:` reaches check 1 already emptied, because the cleaner's leading encore marker (`^\s*(?:e|en|enc|encore)\s*:\s*`) strips the whole entry. Today that is a show-level `hygiene:no alnum` decline. I left it there: same outcome, different class name. The `:?` in `_LONE_MARKER` is kept as the brief words it. Pin: in `test_lone_encore_setbreak_intermission_are_header_shapes`.
- **J9 (F3): exact forms for the new strips.** `Set Break` matches `set ?break` (one optional space). `Encore-` matches `encore ?- ` (case-insensitive; `Encore-Ripple` with no space after the dash is not stripped). `H2` is case-sensitive and must stand alone (`Song h2`, `Song H2O` and `SongH2` are kept). The artist prefix compares only the text before the first ` - `.
- **J10 (F3): the probe does not pass the artist.** `scripts/title_hygiene_probe.py` `_run_arm` still calls `cosmetic_strip(tracks)` with no artist, because the brief threads it from `compute_gather` only. That probe is the Checkpoint-A measurement tool. Its slice-5 arm will not strip artist prefixes, so a re-run of `dump` would differ from gather on that one shape.
- **J11: test placement.** The F3 wiring test lives in test_title_cascade.py, not test_stage_gather.py, so that test_stage_gather.py carries only the edits F4 asks for (the docstring sweep and the slice5-disabled test).

## Concerns

- **F1 changes outcomes on real shows.** darkstarorchestra-2014-07-31 goes from clean (wrong title) to held (correct, honest). Re-run `compare` (Task 21) to see whether any other show in the library carries the delivered signature. Among the four census shows only DSO demotes anything.
- **The stale comment at `test_title_hygiene.py:542`** (Task 6 triage, "fix with C-1's commit") was not in my brief, and I left it.

## Files changed (174995e..c49cdd1)

Source:
- `packages/llama/src/llama/lossless_titles.py`
- `packages/llama/src/llama/stages/gather.py`
- `packages/llama/src/llama/replay.py`
- `packages/llama/src/llama/desc_list.py`
- `packages/llama/src/llama/title_cosmetics.py`
- `packages/llama/src/llama/title_hygiene.py`
- `packages/llama/src/llama/titles.py` (docstring only)
- `packages/llama/src/llama/cli.py` (docstring only)
- `scripts/replay_holds.py`

Tests:
- `packages/llama/tests/test_lossless_titles.py`
- `packages/llama/tests/test_title_cascade.py`
- `packages/llama/tests/test_replay.py`
- `packages/llama/tests/test_desc_list.py`
- `packages/llama/tests/test_title_hygiene.py`
- `packages/llama/tests/test_title_cosmetics.py`
- `packages/llama/tests/test_stage_gather.py` (F4 only)
- `packages/llama/tests/test_titles.py` (docstring line 60 only)
- `scripts/test_replay_holds.py`

Docs:
- `docs/superpowers/2026-10-23-title-hygiene-sdd/mutation.md`

Full suite (final): `./.venv/bin/python -m pytest -q -p no:cacheprovider` gives **4783 passed, 1 skipped, 8 deselected, 26 warnings in 71.94s**.
