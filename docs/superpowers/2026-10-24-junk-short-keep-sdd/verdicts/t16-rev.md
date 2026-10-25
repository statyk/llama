### Spec Compliance

- ✅ Spec compliant (spec 5.5, every bullet the branch owns, plus the brief's interfaces and the two parent rulings).
  - Selector refusal: `cli.py:2697-2699`. It uses `other_selector`, comes before `_setup()` and before the "not both" check, and the string is verbatim. Every selector in the signature (`cli.py:2670-2678`: held, packaged, state, artist, run, profile) is in `other_selector`; `--dest` and `--yes` are not selectors.
  - Unreadable destination: `_read_destination_manifest` (`cli.py:2471-2488`). Only `FileNotFoundError` returns None; any other `OSError`, `ValueError` or non-object raises `LlamaError`, and the message is verbatim per the fixed string. A missing `out`, or an `out` that is a file (`NotADirectoryError`, an `OSError`), also goes this way, which is safe.
  - Single name: `_deliver_one` reads the destination once under the show lock (`cli.py:2569`) and lets the error propagate. The single-name caller turns it into exit 1 (`cli.py:2711-2715`, checked outside the diff).
  - Batch preflight: catches per show, marks the row, skips it and continues (`cli.py:2637-2649`, `2653-2654`).
  - Changed track list: replaced through `_replace_destination` (`cli.py:2588-2591`). A missing manifest merges, as the brief says.
  - `reapply`: both hints go through `_echo_redeliver_hint` (`cli.py:3776`, `3925`, `3782-3796`). It prints nothing for `delivery_path` None, deliver's refusal for an unreadable copy, nothing for a voiced one, and the old hint otherwise.
  - `replay_holds`: `_is_voiced` returns None on `LlamaError` (`replay_holds.py:747-757`), and `_state_label` maps None to `unreadable` (`1118-1126`). `_taper_changes` now routes through `_state_label` (`788`), and `_title_changes` lists the new state (`1244`).
  - `voiced-precheck`: has all four checks (`short_keep_probe.py:776-864`) and is read-only.
  - Ruling 2: the note text is reworded (`cli.py:2648`), and its test is updated.
- ✅ Every file the brief names has its hunk: cli.py, test_deliver_cmd.py, test_reapply.py, replay_holds.py, short_keep_probe.py, test_replay_holds.py, test_short_keep_probe.py. Every test the brief names exists.
- ✅ The dry-run expectation changes match the brief's two (`test_unparseable_destination_manifest_is_not_voiced` deleted, `test_batch_replace_voiced_*` rewritten). The two further changes each follow a recorded parent ruling: `test_cli_reapply_names_form` (ruling 1a) and `test_batch_without_flag_notes_how_many_will_be_refused` (ruling 2).
- ✅ Global-constraint grep: the diff touches none of the untouched names (no junk, structure or titles constants, `DURATION_TOLERANCE_S` or `purge_package_audio`). `catalog.purge_package_audio` is still called unchanged after the copy.
- ⚠️ Cannot verify from diff: CLAUDE.md line ~71 still says "a batch confirmation marks or counts the voiced destinations". The "marks" mark (`(voiced: DJ script/audio will be discarded)`) is gone, and `--replace-voiced` is now single-name only. The doc pass (Task 23) should fix that line, and the `(single name only)` wording near line ~309.

### Strengths
- All three strict paths are closed at the narrowest point:
  - The selector refusal sits on `other_selector`, so a future selector is covered without anyone having to remember it.
  - `_deliver_batch` lost its `replace_voiced` parameter (`cli.py:2618`), so no batch path can reach a replace at all.
  - The destination manifest is read once, under the show lock, and that single read drives both the voiced decision and the list comparison (`cli.py:2569-2570`, `2588-2590`). No second read can disagree with the first.
- A destination whose `tracks` field cannot be compared resolves toward replace, not merge (`_track_filenames`, `cli.py:2500-2506`). That is the right direction on a "no stale file beside a new manifest" surface, and `test_destination_without_a_usable_track_list_is_replaced` pins it.
- Strong tests:
  - The selector refusal is parametrised over every selector, including two that actually match the voiced show (where today's code would replace). It checks the tree bytes, the clip bytes and the ledger bytes.
  - The unreadable cases run both with and without `--replace-voiced`, and check for no swap siblings, no purge and no ledger row.
  - The atomicity of the new replace path is tested at both of its failure points: the copy failure and the rename-in failure, with the old tree byte-identical.
  - `test_copy_failure...` also asserts that the merging copytree is never used for a changed list.
- The precheck reuses deliver's own `_destination_is_voiced`, so it cannot disagree with deliver about voiced or unreadable. I checked it against the real `~/.llama-harness/piece45/spec/voiced-severe-final.json`: a list of 37 `{slug, files: [[file, dur, title, kind]]}` rows, one row per slug, every file entry of length 4. That is the shape `voiced_precheck` reads (`short_keep_probe.py:792`).
- `replay_holds` callers: all five `_state_label` sites (`replay_holds.py:788, 1152, 1167, 1240, 1293`) take any label. Only `_title_changes` enumerates states, and it gained `unreadable`, so an unreadable show is neither dropped nor crashes `compare`.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. `cli.py:2588-2591` (plan-mandated by the brief: "a missing destination manifest keeps today's merge"). A station directory that exists with audio but no `manifest.json` is still overlaid. One way to get there: an interrupted pre-branch first copy, then a re-gather, then a re-delivery. Old-numbered files can then survive beside the new manifest. They do not air, because emcee and transmitter read only the tracks the manifest lists, so this is a consistency issue, not an audio one, and it is rare. The fix would be to treat "`out` exists, no manifest, but `out/audio` is non-empty" as a replace. That is the operator's call, since the brief fixed the current behaviour.
2. `short_keep_probe.py:808,822` against `cli.py:2566`. The precheck calls `.expanduser()` on `delivery_path` and `root`, but deliver and `_echo_redeliver_hint` use `config.delivery_path` as given (`config.py:146` has no expansion). With a `~`-relative `delivery_path`, the precheck would read a different station copy than the one deliver writes. The real config is absolute, so there is no impact today. Drop the `expanduser` on `delivery_path` so the precheck reads the path exactly as deliver does.
3. `test_deliver_cmd.py`, Task 16 block: `test_unchanged_track_list_still_overlays` nearly duplicates the existing `test_unvoiced_existing_destination_still_overlays` (`test_deliver_cmd.py:~350-367`), which already pins the overlay, with and without the flag. The brief named the pin as "today's test", so renaming or annotating the existing test was enough.
4. `test_deliver_cmd.py`: `from helpers import tree_bytes  # noqa: E402` sits in mid-file, beside the top-level `from helpers import build_ready`. `SELECTOR_REFUSAL` and `tree_bytes` are also first used by `test_batch_replace_voiced_is_refused_and_a_single_name_replaces`, which sits above their definition. That works at run time but reads badly. Move both to the top of the file.
5. `cli.py:2645-2649`. In a batch, a show refused as unreadable still appears in `_confirm_plan`'s list, so it counts toward the "N show(s) to deliver" total. The mark says it is refused, but the count overstates by one per unreadable show. This is cosmetic, because the delivery loop skips the show.
6. `cli.py:2574-2578`. The per-show voiced refusal still ends `(pass --replace-voiced to replace it ...)`. In a batch, that line prints per show, and following it literally (adding the flag to the batch) now gets the selector refusal. That is safe but slightly misleading. The implementer flagged it, and a test pins the text. One option is a batch-context suffix, "re-deliver it by name with --replace-voiced", which would need a test-text change.
7. No test pins that the list comparison is *ordered*: a destination with the same filenames in a different order should replace. Order changes are unlikely while filenames carry track numbers. A one-line reorder case in `test_changed_track_list_replaces_an_unvoiced_destination` would cover it.
- Test output: the implementer's full-suite line reports `26 warnings`. Previous tasks' records in `$D` show the same count, so this is baseline and not new noise from this task.

Checks run (read-only, no tests executed):
- Callers of `_destination_is_voiced`, `_deliver_one`, `_is_voiced`, `replace_voiced` and `_read_destination_manifest` across `packages/` and `scripts/` (non-test). Every caller of the now-raising `_destination_is_voiced` handles `LlamaError`: the batch preflight, the reapply hint, `replay_holds._is_voiced` and the precheck. `_deliver_one` is called with `replace_voiced` only from the single-name path (`cli.py:2712`).
- The `deliver` signature, to confirm `other_selector` covers every selector.
- `_replace_destination` (`cli.py:2508-2530`), to confirm that the patch in the new failure test hits the real rename-in, and that the swap is atomic for the new caller. `out` always exists on this path, because replace runs only when `dest_manifest` is not None.
- `config.delivery_path`, for expansion (Minor 2).
- The real `voiced-severe-final.json` shape.
- `_state_label`'s consumers in `replay_holds.py`.

### Assessment

**Task quality:** Approved

**Reasoning:** Every strict deliver surface in spec 5.5 is closed:
- no batch path can replace a voiced copy;
- an unreadable station manifest refuses the show;
- a changed track list swaps the destination atomically instead of merging.

Each surface is tested against the behaviour today's code would actually exhibit. The remaining items are a plan-mandated edge (a destination with no manifest), a `~`-expansion inconsistency in a read-only probe, and test and wording polish.
