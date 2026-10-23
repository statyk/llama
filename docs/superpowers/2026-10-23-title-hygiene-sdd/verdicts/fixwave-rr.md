### Finding Verdicts

**F1. C-1, the preferred fix (ruling 1): ADDRESSED.**
- **The signature and the threshold.** `lossless_titles.py:239-242` computes `delivered_shift` with C's own `_real` and `agrees`, both unmodified. It counts the in-range neighbours i±1 and requires `len(...) >= 2`. It runs only when there is a `ref` and C was not skipped (J1).
- **What it keeps and what it blanks.** C's C1/C2 changes are kept (`i not in changed`). Every other `_real`, non-`is_filler` delivered tag that does not agree with `ref[i]` is blanked (`:243-247`). Sources stay the incoming tag source.
- **Overrides are untouched.** `gather.py:1209-1231` (`_without_override_positions`) restores a demoted override position, drops it from `demoted`, and rebuilds or removes the note. Pinned by `test_shifted_set_demotion_never_touches_an_override`.
- **One note per show.** It uses the brief's fixed string exactly (`SHIFTED_DELIVERED_NOTE` / `demoted_note`, `:217-222`), 1-based and ascending.
- **The DSO-2014 fixture.** It is verbatim, with the description, 21 stems and the MP3 and FLAC titles (`test_lossless_titles.py`, `DSO_2014_07_31_*`). At gather level, `test_title_cascade.py::test_shifted_mp3_tag_set_darkstarorchestra_2014_07_31` pins:
  - #3 is not `Duprees Diamond Blues`, and its source is unresolved, desc-position or setlist;
  - the show is "held, or flagged, or ships no unconfirmed tag" (a disjunction, as the brief allows; the implementer's probe shows it held);
  - tracks 4-20 are the C2 FLAC titles;
  - with slice 3 off, the old shifted title comes back.
- **The negative case.** `test_one_shifted_delivered_tag_changes_nothing` covers the case with exactly one signature position.
- **Kill-check of the threshold.** I ran it in a scratch copy (`git archive c49cdd1`). `llama.__file__` and `herder.__file__` were proven under the scratch, with `PYTHONDONTWRITEBYTECODE=1`, from the scratch cwd, using the worktree's `.venv/bin/python -m pytest -p no:cacheprovider` over test_lossless_titles, test_title_cascade, test_replay and scripts/test_replay_holds.
  - Baseline: 261 passed.
  - `>= 1`: **2 failed.** `test_lossless_titles.py::test_one_shifted_delivered_tag_changes_nothing` (predicted) and `test_lossless_titles.py::test_derektrucksband_2007_05_27_track1`.
  - `>= 3`: **3 failed.** `test_shifted_delivered_set_demotes_every_other_unconfirmed_real_tag`, `test_shifted_delivered_set_keeps_filler_and_unreal_tags` and `test_readmitted_file_tag_is_demoted_on_a_shifted_set`. These are the predicted exactly-2-signature cases; DSO has 18, so it stays green.
  - Both mutants are killed. The log is in `fixwave-rr.log`.
- See New Breakage #1 for a false-signature hole in the ruled design.

**F2. I-1 (ruling 4): ADDRESSED.**
- `replay.py:542`: `r.cascade = _cascade_dict(g.title_record)` is now unconditional, inside the `try`. Unreplayable rows keep the `{}` default because the assignment is the try's last statement.
- The `ShowReplay` comment is updated (`:303-309`).
- `test_replay.py::test_stored_llm_not_self_filled_stays_needs_llm` now asserts `outcome == "needs-llm"`, the full key list and the `d_fills`.
- `c_demoted` (J5) is attributed to slice3 through `SLICE_OF_DECLINE` (`replay_holds.py:1409-1412`) and pinned in `test_added_hold_attributed_from_declines`.
- `_d_reach`'s fallback is kept, with a valid reason: old arms carry `{}`.

**F3, D cleaning, leading segue: ADDRESSED.**
- `desc_list.py:49` `_LEAD_SEGUE` covers `-->`, `->`, `=>` and `>`, with optional spaces. It is applied first in `_finish` (`:102`).
- Pinned by `test_leading_segue_marker_is_stripped_deepbananablackout_2004_04_01`, on a verbatim excerpt.

**F3, D cleaning, trailing `^`/`$`: ADDRESSED.**
- `desc_list.py:47` adds `\^+|\$+` inside the one `_TRAIL_MARKERS`.
- `lossless_titles.py:46` still imports it, and `test_c_title_strip_shares_the_trailing_marker_set` asserts identity (`is`).
- The mymorningjacket `cobra          $` and deepbananablackout `Boot!^` cases are pinned.

**F3, D cleaning, glued duration after `)`: ADDRESSED.**
- `desc_list.py:39` `_PAREN_TIME = (?<=\))(<m:ss|h:mm:ss>)\s*$` needs `)` immediately before the time.
- `1 Samuel 15:23 -> 1 Samuel` is still today's R19 strip, unchanged, as the orchestrator's correction rules. `Psalm 23` is kept.
- Pinned by the darkstarorchestra-2011-04-15 test (duration 411.0).

**F3, slice 5, M-6 bracket veto: ADDRESSED.**
- `title_cosmetics.py:620-624` `_bracket_debris`: an empty pair in the result, OR a pair absent from the original (J6). It is ANDed with `_acceptable` (`:650`).
- `Esau (s2t01)` and `Banks of the Ohio (actually d2t10)` are declined. `[05:12] Song` and the untouched `(Bend Over)` still strip.

**F3, slice 5, artist prefix only when equal to the show artist: ADDRESSED.**
- `_strip_artist` (`:599-607`) compares the text before the first ` - ` with the artist by `fuzzy_norm_title` equality; an empty artist strips nothing.
- `compute_gather` passes its `artist` (`gather.py:2014`; the artist is `_creator(meta) or candidate.collection`). The wiring is pinned by `test_cosmetic_strip_receives_the_show_artist`.
- Another artist, a partial name and no artist all keep the prefix (pinned).

**F3, slice 5, ` H2`, `Encore- ` and `E: `: ADDRESSED.**
- `_H2_TAIL = \s+H2\s*$` is case-sensitive. `Song H2O`, `SongH2` and `Song h2` are kept.
- `_ENCORE_DASH = ^\s*encore ?- ` covers gratefuldead-1974-10-18 `5:46] Encore- U.S.Blues -> U.S.Blues`.
- `E: Ripple`, `Encore: Ripple` and `Encore-Ripple` are kept (pinned).
- The acceptability test still gates every result (`test_new_shapes_keep_the_acceptability_test`).

**F3, M-1 lone markers as a check-1 header: ADDRESSED.**
- `title_hygiene.py:675` `_LONE_MARKER` is ORed beside `is_header_shape` (`:698`), giving `hygiene:header`.
- `taper._SET_HEADERS` is untouched. `Encore:` is already emptied by the cleaner and keeps `no alnum` (J8, the same show-level outcome).
- Near-misses (`Intermission Jam`, `The Intermission`, ...) are not headers (pinned).

**F4, M-6: ADDRESSED** (done in F3, above).

**F4, `_sibling_transfer` docstring sweep: ADDRESSED.**
- Every listed site now names `_sibling_transfer_full` or "the transfer pass": gather.py `_dedupe_ordered`, `load_donor_tapes` and `best_donor`; test_stage_gather.py :323 and :402-440; titles.py :458; test_titles.py :60; cli.py :2687.
- The remaining `_sibling_transfer` mentions are its definition, which is correctly labelled "off the production path" (gather.py:306), its pin test, and two scripts.
- No code changed.

**F4, slice5-disabled test: ADDRESSED.** `test_stage_gather.py::test_cosmetic_strip_off_when_slice5_disabled` now uses `title_hygiene.ALL_SLICES - {"slice5"}`.

**F4, compare summary for both arms: ADDRESSED.** `replay_holds.py:1462-1463` prints `disabled slices: base [...], cand [...]`, pinned by `test_summary_states_the_disabled_slices_of_both_arms`.

**F4, tautological floor test: ADDRESSED.**
- `test_agreement_exactly_at_floor_passes` is deleted, and its share assertion is folded into `test_decide_d_agreement_exactly_at_floor_passes`.
- `mutation.md`'s Survivors section gains the resolution line as the brief words it.

#### Judgement calls

- **J1 (the lossless skip wins): sound.** C changes nothing on a skipped show, so it demotes nothing either. A set whose delivered AND lossless tags are both shifted still ships as today. That is pre-existing behaviour, not a regression.
- **J2 (a re-admitted file is demoted): sound.** It is the safe direction and follows the brief literally.
- **J3 (override positions count toward the signature but are never demoted): sound.** The delivered tag is evidence about the tape, and Review Focus 2 holds.
- **J4 (demotions are not in `c_changed`): sound.** One cosmetic leak follows from it; see New Breakage #2.
- **J5 (`c_demoted` harness key): sound.** Ruling 4 needs it so every added hold is attributed.
- **J6 (the M-6 veto's second arm, "pair edited"): sound.** It declines more, never less, and it is required for the brief's own zentricksters example.
- **J7 (`1 Samuel` keeps R19's strip): sound.** It matches the orchestrator's correction.
- **J8 (`Encore:` stays `no alnum`): sound.** It is the same show-level decline.
- **J9 (exact forms): sound.** Each form is conservative.
- **J10 (the probe passes no artist): sound for this wave.** The Task 21 re-measure goes through `replay_show` → `compute_gather`, which does pass it. Note the divergence in acceptance.md if the probe's `dump` is cited.
- **J11 (test placement): sound.**

### New Breakage in the Fix Diff

**1. Important. The outcome is the same class as C-1's Critical; only its unmeasured rarity keeps it below Critical. The C-1 signature is symmetric and uncorroborated, so it can demote RIGHT tags on an unshifted show, and the cascade then fills the shifted reference with no flag.** `lossless_titles.py:239-247`; `gather.py:1349` and `:1449`.

- **Why it happens.** `delivered_shift` cannot tell "the delivered tags are shifted against a right reference" from "the reference is shifted against right delivered tags": both give the same ±1 pattern. The only disambiguator is the lossless off-by-one skip, and it fires only when two or more lossless tags are real at the shifted positions.
- **Why nothing then catches it.** After demotion, `wholly_untagged`, the S plan, `decide_d(tag_titles=titles)` (check 3) and setlist-gap all read the post-demotion layer. The demoted tags are invisible to every later check, and the survivors agree with the reference by construction.
- **Reproduced at gather level** (`compute_gather`, all slices). The script is `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-title-hygiene/3400e369-2549-431e-baec-1d7836216a9e/scratchpad/demo/demo_gather.py`, run read-only against the worktree code; its output is in `fixwave-rr.log`.
  - The tape: 8 MP3 tags, all right (`Bertha, Sugaree, Deal, Loser, Jack Straw, Stella Blue, Big River, Ripple`). The FLAC has titles only on tracks 1 and 8. The description's numbered list is count-matched but shifted: it omits Sugaree and adds `Mama Tried`.
  - Result: tracks 2-6 are demoted, and setlist-gap ships `Deal, Loser, Jack Straw, Stella Blue, Mama Tried` (source `setlist-gap`) with `needs_review False` and no flag.
  - With slice 3 off, the same tape ships all 8 right titles.
- **The same mechanism at the lossless layer.** The implementer's own `test_shifted_delivered_set_demotes_every_other_unconfirmed_real_tag` blanks track 4 `Big River`, although its FLAC twin agrees with it (only the list says `Loser`).
- **The canonical reference.** When there is no count-matched list, `ref` is the canonical (`:155`), which can carry setlist.fm items. That case is plainly outside ruling 2's "the description outranks tags" principle. I read this from the code; I did not run it.
- **Reachability is unmeasured.** It needs MP3 titles that are mostly right, FLAC titles silent or unreal at the shifted positions, and a count-matched reference with compensating errors. The implementer's probe covered only the four C2-note census shows, and that census is selected on C2 having fired, so it cannot see this population.
- **Suggested narrowing, for the operator to rule on.** Count only the signature positions C itself confirmed: `sum(1 for i in delivered_shift if i in changed) >= 2`. Those are positions where the lossless tag independently agrees with the reference against the delivered tag. Optionally, also exempt a delivered tag whose lossless twin agrees with it.
  - In scratch, this narrowing keeps all 261 focused tests green, DSO included: 17 of its 18 signature positions are C2.
  - It closes the reproduction above, which then ships all 8 right titles.
  - It changes nothing on the four census shows.
  - The trade-off: it gives up demotion on an uncorroborated shifted set, which ships as it did before the fix.
- **If the ruling stands unchanged**, the Task 21 hand check must cover every row with `c_demoted`, and specifically each demoted position with no lossless corroboration.

**2. Minor.** `gather.py:1294-1306`. The 2c/2d note loop skips only `c_changed`, so a position C-1 demoted whose raw tag had a glued or joined track number still gets a `stripped glued/joined track number` note for a title that no longer ships. This is a notes.json inaccuracy only.

**3. Minor.** `title_hygiene.agrees` cleans both sides with `clean_one` (`title_hygiene.py:72-73`), so the new D-cleaning strips (leading segue, `^`/`$`, glued duration after `)`) also widen `agrees` everywhere it is used: C, the delivered-shift signature, check 3 and slice 4. The direction is benign, since only marker debris now compares equal. It is not separately pinned.

### Out-of-Scope Observations

- `scripts/title_hygiene_probe.py:94-116` patches `G._sibling_transfer`, which has been off the production path since Task 16. Gather calls `_sibling_transfer_full`, so the probe's sibling patch is probably inert. This is pre-existing; check it before the probe is cited again.
- Self-titled songs: a tag such as `<Artist> - <qualifier>`, where the artist name is also a song title, would strip to `<qualifier>`. The acceptability test only catches an empty or placeholder result. The risk is negligible, and ruling 5 authorises the shape.
- I could not identify the "stale comment" at old `test_title_hygiene.py:542`, which the implementer left. Lines 536-546 at 174995e look current.
- No protected name was edited. A grep of the diff's +/- lines against the plan's Global Constraints list finds only imports and uses of `fuzzy_norm_title`, `is_filler` and `hygienic_title`, docstring mentions, and the deleted `AGREEMENT_FLOOR` assertion. The protected files (`setlist.py`, `structure.py`, `placeholders.py`, `siblings.py`, `songs.py`, `junk.py`, `taper.py`) have an empty 174995e..c49cdd1 diff, and `git diff main -- setlist.py` is empty. `_TRAIL_MARKERS` is a fixed constant that ruling 5 explicitly changes, not a protected name.

### Verdict

All findings addressed: yes.

New Breakage #1, Important, should go to the operator before the Task 21 re-measure, so that the re-measure measures the final rule. The question for the operator: keep the ruled uncorroborated signature, or count only the signature positions C confirmed.
