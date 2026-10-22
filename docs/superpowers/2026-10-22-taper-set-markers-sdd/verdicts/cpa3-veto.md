# cpa3-veto handback: Checkpoint A own-less set-like veto

**Status: DONE_WITH_CONCERNS.** The concern is minor (see Concerns).

## Commit
- `5da667b` feat(taper): own-less set-like veto (llama-db ruling, Checkpoint A2). Parent c7eb3b0. Trailer per the mandates.
- Suite: `./.venv/bin/python -m pytest -q` gives **4365 passed, 1 skipped**, 8 deselected (was 4326, +39 new tests).
- `git diff main -- packages/llama/src/llama/setlist.py` is empty. No protected name is touched, and no recognised form was added.

## What was built (packages/llama/src/llama/taper.py)
- **Decline reason: `"veto: set-like text"`.**
- `TaperText.set_like: bool = False` is a new field. It is computed in `read_taper_structure` over the final items by `_set_like(items)`. The reasons the reader gives for owned texts are unchanged.
- **The "set token" test:**
  - It uses `_SET_LIKE = \b` + `_SET_TOKEN`, the same numbered-set spellings the reader reads (`Set 1`/`one`/`I`, `Set1`, `first set`, `2nd set`), word-bounded on both sides.
  - It applies only to items whose label is `1`/`2`/`3`. Encore items are skipped, because they are the notes after the encore songs.
  - **Exemption:** a token whose number equals the item's own set and is followed by a continuation (`con't`/`cont…`, `_CONT_AFTER`) is not set-like. Example: `Set 2 con't` inside set 2. This keeps the 9 `con't` rows owned. cpa2-tiers measured those rows as identical either way.
- **Placement in `decide_taper`:** the veto runs after the encore checks (track title, encore-like) and before placement. When both vetoes fire, the existing reasons stay unchanged. It also applies when the taper marks an encore (thedead-2009-04-25 has `E:`).
- **Docs:**
  - The module docstring has a new paragraph on set-like text, and the `TaperDecision.reason` comment lists the new reason.
  - Spec §2 has one added sentence after the encore-veto bullet, attributed "(llama-db ruling, Checkpoint A2, 2026-10-22)".

## Tests (packages/llama/tests/test_taper.py, appended)
- **`test_set_like_real_cases_are_not_owned`, 6 real cases.** Each uses a verbatim excerpt from `~/.llama/cache/md_<id>.json` plus the show's track list and stored sets:
  - thedead-2009-04-25 (`- end of set one`)
  - gratefuldead-1974-07-19 (`Set 1.5:`)
  - ryanadams-2008-01-21 (`Cardinals Set 1 CD 2`)
  - localh-2004-12-31 (`Set I * ["Pack Up The Cats"]`)
  - neworleanssuspects-2012-08-02 (`Set 1.`, with its setlist-gap sources)
  - motherhips-1995-08-06 (notes, `set one-(1:05:59)`)

  Each asserts that the text asserts a structure, that `set_like` is True, and that the result is not owned with the new reason. On HEAD c7eb3b0, all 6 were owned (reason None).
- **Negative, owned:** `test_set_like_skips_notes_after_the_encore`. The real case philleshandfriends-2006-07-03 has `Trey Anastasio plays entire 2nd set and encore` as an encore item. It stays owned with boundaries (5, 16). There is also `test_set_like_notes_after_the_encore_do_not_veto`, which covers 4 constructed post-encore notes, including `Set 1.5: Seastones` after the encore.
- **`test_set_like_tokens_in_a_numbered_set_item`:** 11 constructed token shapes, which are the 6 real shapes plus `into the Set1 closer`, `Set II (late)`, `end of the first set`, `2nd set starts here`, and `Set 1 con't` inside set 2 (a continuation of the wrong set).
- **`test_set_like_negatives`:** 14 lines are not set-like:
  - the con't forms of the item's own set;
  - `The Sun Also Sets`, `Set The Controls…`, `set list`, `DJ Set:`, `Set`, `CD 2`;
  - `Sunset 1`, `Reset 2`, `Set In Stone`, `Sets 1 and 2`.
- **Others:**
  - `test_recognised_markers_are_never_set_like` (pin);
  - `test_set_like_veto_applies_with_a_marked_encore`;
  - `test_encore_like_veto_reason_wins_over_set_like`.
- **RED:** the new test file was run against HEAD's code in a `git archive` scratch copy. 38 tests failed and 271 passed.
- **Mutants**, run in the scratch copy; each was caught exactly by the tests predicted for it:
  - con't exemption dropped: 4 con't negatives fail;
  - encore skip dropped: 4 post-encore-note tests fail;
  - left `\b` dropped: `Sunset 1` and `Reset 2` fail.

## Gate4 (`scripts/taper_probe.py gate --out ~/.llama-harness/piece2/gate4`, then `delta --old gate3 --new gate4 --out gate4`)
- **Gate, unchanged from gate3:**
  - in-scope 186, owned 77, ratio 77/186 = 0.414;
  - target match exact 42/54 = 0.778, incl. filler-only 53/54 = 0.981, misses 1;
  - renum 8, no target 15.
- **Library:** taper-owned **642** (was 648). Labels identical to stored: 552. Labels differ: 90.
- **Library tiers:** songs moved 33 (was 35), encore added 31, sets merged 4 (was 5), sets split 21 (was 22), filler only 1, labels renamed 0, encore folded 0.

### Delta flip list, gate3 to gate4
- **Gate, in scope and all yes/partial:** newly owned 0, newly not owned 0, labels changed 0.
- **Library:** newly owned 0, **newly not owned 6**, each `veto: set-like text`. They are exactly the six named:
  - gratefuldead-1974-07-19
  - localh-2004-12-31
  - motherhips-1995-08-06
  - neworleanssuspects-2012-08-02
  - ryanadams-2008-01-21
  - thedead-2009-04-25

  Owned rows whose labels changed: 0.
- **Reason-only changes, with no ownership change.** These rows were already unplaced (not owned). The veto now runs before placement, so their reason reads `veto: set-like text`. The triggering item is given for each:
  - gate (3, in scope):
    - joerussosalmostdead-2019-03-03 (`Set One @ (8:16PM - 9:18PM):`)
    - strangefolk-2002-09-01 (`Set One (Acoustic)`)
    - tealeafgreen-2002-11-21 (`Entire 3rd set with Josh on acoustic guitar`)
  - library (7):
    - furthur-2010-07-02 (`- I did not cut the second set for CDs`)
    - gratefuldead-1978-11-20 (notes, `Set2 patches: MSC`)
    - gratefuldead-1981-10-16 (`Set 1 Acoustic Cindy Poris Opened`, in set 2)
    - karldensonstinyuniverse-2011-10-28 (`Set I (Sticky Fingers): Brown Sugar`)
    - soundtribesector9-2003-06-13 (`set 1 pt. 1`, `Set2   Pt.3`)
    - tedeschitrucksband-2019-08-24 (`- Set two featured Trey Anastasio…`)
- **Did any row flip that is NOT one of the 6 named?** No. Only reason strings changed, on the 10 already-not-owned rows above.
- **Any newly owned row?** None. The veto can only remove ownership.
- **Which of the 7 post-encore-notes rows stayed owned?** All 7:
  - davidnelsonband-2009-06-27
  - gratefuldead-1993-09-22
  - philleshandfriends-2006-07-03
  - tedeschitrucksband-2020-02-21
  - tedeschitrucksband-2021-10-08
  - umphreysmcgee-2002-12-31
  - yondermountainstringband-2008-10-11

  Also still owned: the JRAD "Set Break Music" rows and thedead-2009-05-07, plus all 8 checked con't rows (clubdelf-2011-04-09, discobiscuits ×3, railroadearth-2005-01-28, stuallenandmarshotel ×2, thegourds-2002-09-04).

## Concerns
- **Notes after the LAST NUMBERED SET are not exempt.** The ruling exempts only notes after the encore. On a show with no encore marker, a trailing note that names a set carries the last set's label, so it vetoes. Examples: `- Set two featured Trey…`, `Entire 3rd set with Josh…`, `I did not cut the second set for CDs`. In this corpus all three were already unplaced, so ownership cost is 0. In general it is own-less collateral, which matches the ruling's principle. Exempting it would mean detecting "notes" on a no-encore show, and nothing distinguishes a note from an unrecognised header at the end of a set. I left it as the ruling states it.
- The con't exemption is my narrowing. Without it, 9 owned rows the reviewer measured as harmless would flip as well.
