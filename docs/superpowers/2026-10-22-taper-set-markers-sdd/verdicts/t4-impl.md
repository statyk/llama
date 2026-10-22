# t4-impl handback: Task 4, wire the taper into compute_gather

**Status: DONE_WITH_CONCERNS** (the concerns are scope notes for Task 5 and one test-input deviation; nothing is blocked)

## Commits (branch held-backlog-taper-markers, on top of 6cf03ea)
- `db47340` feat(models): StructureInfo.taper_owned and GatherResult's taper fields (defaulted). This adds the fields only, with no behaviour change, plus the pin `test_old_structure_info_reads_without_taper_owned`. Suite: 4374 passed, 1 skipped.
- `19b0ad2` feat(gather): the taper's markers own the structure when they place exactly. This is the plan's subject (ruling R1), and the Step 4 grep result is in its message. Suite: 4391 passed, 1 skipped.

## Test commands and results (final tree, HEAD 19b0ad2)
- Task tests: `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q -k "taper or today or umphreys or old_structure_info or merge_conflicts or notes_lineage or notes_used or segues_and_matched or structure_info_created or label_rename or reader_coverage or align_structure"` gave 20 passed: the 18 new tests plus 2 existing align_structure tests the filter also matches.
- `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q` gave 189 passed.
- Full suite `./.venv/bin/python -m pytest -q` gave **4391 passed, 1 skipped**. The baseline was 4373, plus 18 new tests.
- Before implementing, every new test except 2 failed. The 2 that passed are the override and notes pins, which pass on old code by design.
- No existing test changed: no `-` lines in the test-file diff against 6cf03ea. `git diff main -- packages/llama/src/llama/setlist.py` is empty.

## Where each brief test is
All tests are appended at the end of `packages/llama/tests/test_stage_gather.py`, under the header "Held-backlog piece 2, Task 4". They use a synthetic one-recording item built by `_tp_md` (originals plus tagged mp3 derivatives), a `_FakeSetlistFM` stub, and `_oracle`, which gathers with `llama.taper.decide_taper` patched to a not-owned decision. `_sans_taper` is `r._replace(taper=None)` (ruling R2). Every brief test name is used as-is:
- test_taper_structure_beats_unlabelled_setlistfm
- test_taper_agreeing_with_today_keeps_alignment
- test_label_rename_at_same_positions_is_recorded
- test_taper_beats_jerrybase_anchoring
- test_taper_owned_skips_align_structure
- test_owned_low_confidence_uses_reader_coverage: three sub-cases (good / weak = 2/7 / no canonical). It also checks coverage against `align(tracks, reader items)`.
- test_track_title_veto_is_exactly_today (pin): asserts `taper.reason == "veto: track title"`.
- test_not_owned_is_exactly_today (pin): an `unplaced:` decline.
- test_structure_override_bypasses_the_taper (pin): a patched `decide_taper` that raises; `taper`/`step1_alignment` are None.
- test_notes_lineage_never_places: `taper.source == "notes"`, equals the oracle.
- test_notes_used_when_description_has_no_marker
- test_segues_and_matched_come_from_step_one
- test_owned_show_drops_merge_conflicts_not_owned_keeps_them
- test_structure_info_created_without_canonical
- test_umphreys_2004_04_14_taper_owned_identical_to_today
- test_old_structure_info_reads_without_taper_owned (pin)

Two extras:
- `test_taper_owned_never_calls_the_align_provider`: a provider is passed and must get zero calls.
- `test_today_sets_is_step_one_parallel_to_tracks`: a spy on `decide_taper` checks that `today_sets` has the track count and equals step 1's labels. This is the parallel check the orchestrator asked for. The code also asserts it.

## Step 4 grep output
`grep -rn "alignment" packages/emcee packages/transmitter antenna/src`:
```
packages/transmitter/src/transmitter/layout.py:4:pre-encoded silence; segment N is frames [441N, 441N+441). Grid alignment is by
```
This is a docstring about the segment grid. No reader switches on `structure.alignment`.
On the llama side the only value readers are in `replay.py` and `scripts/replay_holds.py`: an `== "llm"` check and a stored-vs-new diff. Those belong to Task 6/7.

## Implementation (gather.py structure block)
1. **Step 1 is unchanged.** The anchoring note is now held in `anchor_note` and appended only when the show is not owned, so notes keep the same order as today.
2. **Step 2.** `step1_alignment`/`step1_sets` are captured, with `assert len(step1_sets) == len(tracks)`. Then `taper.decide_taper(tracks, meta, aliases=family_aliases, today_sets=step1_sets)` runs, where `meta` is `md.get("metadata", {})`, the same object as `md["metadata"]`.
3. **Owned.** `if taper_owned:` / `elif anchor_note` / `elif <today's LLM condition>`. The LLM branch keeps its original indentation, so its diff is just the `elif` line.
   - Reader coverage is `align(tracks, ParsedSetlist(items=[SetlistItem(title, normalize_song(title), set)…]), aliases=family_aliases).coverage`.
   - The flag is raised only when there are canonical items, no anchoring, step-1 coverage is under the threshold, and reader coverage is under it too.
   - When any non-filler label differs from step 1, `alignment = "taper"` and an op note is added: `set breaks from the taper's markers (was {_breaks_of(step1_sets)} {ordered distinct step-1 labels})`. Example: `(was [3, 6] ['1', '2', '3'])`.
   - Tracks take the taper's sets with step 1's segues and `matched` (the TAUTOLOGICAL override is unchanged). Coverage is the reader's coverage, and the `merged track(s)` flag is skipped.
   - `StructureInfo` is created whenever the show is owned (source "none" with no canonical) and carries `taper_owned`.
4. **Not owned:** byte-for-byte today's path.
5. **Override path:** `decide_taper` is never called; `taper_owned=False`, `taper=None`, `step1_alignment=None`.

## Deviations
- **The umphreys test also embeds the cached setlist.fm set names.** They are copied once, read-only, from `~/.llama/cache/slfm_6f592f90d24abbb461b32c5a41207695adfa1584.json` as the literal `UM_SLFM`.
  - **Why:** with the description as the only source, today's `parse_setlist` does not read `Disc 2 - Set 2`. Today then labels set 1 straight through to the encore, and the "identical to today" claim fails at index 11. The shipped show's canonical is setlist.fm (stored `structure.source == "setlist.fm"`, set_breaks `[11, 18]`).
  - **Result:** with setlist.fm stubbed as in production, the taper owns the show and labels, breaks `[11, 18]`, flags and `alignment` ("deterministic") all equal the oracle's. There is no "was" note.
  - **Consequence:** an umphreys-shaped show with no setlist.fm would be owned AND change from today (1/encore becomes 1/2/encore). That is the intended behaviour, but "identical to today" holds only with setlist.fm available.
- The `<labels>` part of the fixed note string is rendered as the ordered distinct step-1 labels (a Python list repr). The plan does not pin the exact rendering beyond "was [] …".

## Concerns / notes for the reviewer
- **Task 5 territory, left untouched:**
  - The closer tripwire still keys on `alignment != "jerrybase"` alone. A taper-owned show that agrees with anchoring keeps `alignment == "jerrybase"`, so its tripwire is skipped. An owned show where the taper differs (alignment "taper") now runs the tripwire on the taper's labels and may raise hard closer flags.
  - `structure has N sets but jerrybase shows M` still fires on owned shows. For example, `test_taper_beats_jerrybase_anchoring`'s show carries it; the test does not assert on it.
  - The multi-event "spanned" check is also unchanged.
  - Spec §5 and Task 5 handle all of these.
- **Step-1 conflicts are kept.** On an owned show, `StructureInfo.conflicts` still carries step 1's align conflicts (unmatched canonical items), along with any build/sibling notes. The spec drops only the anchoring note and merge_conflicts, so I kept the rest.
- **No test for filler-only label differences.** "Filler excluded" in the differs test has no dedicated test. The placement rule keeps today's split point inside a filler run, so a filler-only difference looks unreachable through `decide_taper`. Task 8's mutation run may want to probe it.
- **Production assert.** The parallel check is an `assert` in production code, so it is stripped under `-O`. The spy test covers the same thing.
