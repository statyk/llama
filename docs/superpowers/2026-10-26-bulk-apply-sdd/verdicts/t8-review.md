# Task 8 review: strict station reuse and the held-outcome anchor (402d138c..6a8f7d81)

Reviewer: Opus. One pass over the review package. I read the brief, the implementer's handback, plan lines 15-84 and the spec's "Re-processing" section. Line numbers below are `diff:N` (lines in review-402d138c..6a8f7d81.diff) unless a source path is given.

### Spec Compliance

- ✅ **Spec compliant.** Every interface in the brief is present: `ANCHOR`, `StationUnpaired`, the two `ReusePlan` fields, `plan_reuse(strict=)`, `check_pairs`, `write_anchor_if_absent`, `drop_anchor`, `build_package(tally=)`, `_redo_show_locked(allow_download=)`, and `--allow-download` on `redo` and `fix`. The fixed strings match the Contracts exactly:
  - `station copy does not pair` / `station copy unreadable`
  - `no copy pairs`, `a different recording`, `<file> has no metadata length`, `<file> failed its length check`, `no delivery_path in config`
  - the hint line (diff:371-373)
  - `--allow-download takes one named show`
- Every brief-named test exists, under the brief's name or a near variant. Review Focus 3 is pinned by `test_strict_downloads_only_files_the_station_never_held` (diff:864-882). It asserts one download (`s.mp3`), `tally == {"reused": 3, "downloaded": 1}` and the exact log line.
- **The deviation is correct and required (approve it).** The anchor is ignored unless `anchor.identifier == show.json.identifier` (diff:166-169).
  - In the brief's literal rule, the station pairing checks only anchor vs station identifier.
  - Under that rule, a held re-selection works like this: show.json names item B, while the anchor and the station copy are item A. Item A's station audio would then pair under B's same-named sources.
  - The build-time guard (diff:666, 676) compares the plan-time `show.json` identifier (B) with `show.identifier` (B). It cannot catch this.
  - That breaks the spec's identity rule: a copy pairs only when it is of the item being packaged, and the anchor carries `source.identifier` precisely so it can be compared.
  - Through the anchor, the station pairing now requires anchor == show == station identifier, which is the same as `same_item`. That is the correct rule.
  - It is pinned by `test_anchor_pairs_no_station_copy_for_a_show_json_of_another_item` (diff:1063-1073) and by the pre-existing `test_held_reselection_then_overrule_never_ships_the_old_items_station_audio` (mutant M3 in the handback).
  - Recommend the plan/brief text be amended to match.
- **Extras (small, tested, each noted by the implementer):**
  - `station_mark.StationUnreadable.detail` (diff:776-789). `station_mark.py` is not in the brief's file list. It is needed to carry the one-line detail without parsing the message, and no second exception class was added.
  - `build_package` now calls `campaign.read_record` up front (diff:659). This is the Task 3 review minor, with its own test (diff:1091-1104). It only moves an existing refusal earlier.
- ⚠️ **Cannot verify from diff:** the spec's "Each show prints files reused vs downloaded" and "stop after 3 unreadable in a row" for reapply waves. `tally` is not threaded through `process_show`/`reapply`, and `reapply.py:159` still plans non-strict. The controller should confirm Task 9/13 consume `tally` and pass `strict=`.

### Strengths

- The refusal happens before any download in every strict branch: `check_pairs` comes first, then the identifier guard, then the paired-not-placed raise (diff:663-668, 700-703). A source no copy ever held still downloads, which is exactly the spec's carve-out.
- `_strict_refusal_hint` is entered outside `show_unit` (diff:502, 477, 594), so the restore runs before anything prints. The CLI tests assert byte-identical trees after refusal (diff:1241, 1255, 1274, 1157).
- The anchor is written inside the unit (diff:422-423), so a failed unit deletes it. It is written once and never replaced (diff:226-227; `test_anchor_is_written_once`). It is dropped only after the manifest write (diff:752), and `test_campaign` confirms it is in no stage's artifact list (diff:1088). This matches "it goes only when a package is built, never at a held commit". The held-then-clear CLI round trip is pinned end to end (diff:1340-1359).
- The selector refusal runs before `_setup` and before any write, across all five forms including the bare one (diff:568-570, 1316-1327).
- `test_undelivered_reuse_unchanged` pins today's fall-back for non-strict plans across all three download reasons (diff:1049-1060).
- There is a mutation table with predictions, run in a scratch copy, and every mutant was caught.

### Untouched-names check

I grepped the diff's `+`/`-` lines for `DURATION_TOLERANCE_S =`, `def _pair(`, `purge_package_audio`, `STOP_AFTER_LLM_FAILURES`, `load_list`, `briefing_reusable`, the junk constants, `_apply_short_rule`, `AGREEMENT_FLOOR`, `MIN_ANCHORS`, `_manifest_identifier` and `same_item`.
- The only hits are the restructured `_pair(...)` call sites (diff:165, 180-182, 197-198). The rule `same_item` + `_pair` is unchanged.
- `_pair` itself is context only (diff:99-107). `DURATION_TOLERANCE_S = 5.0` is context only (diff:615). `purge_package_audio` is absent from the diff.
- `_pair_anchor` (diff:126-134) applies the same length+title rule to the anchor's list.

### Checks run

- `./.venv/bin/python -c "import llama; print(llama.__file__)"` resolves inside the worktree.
- `./.venv/bin/python -m pytest packages/llama/tests/test_audio_reuse.py test_redo_cmd.py test_fix.py test_campaign.py -q -p no:cacheprovider`: 249 passed, 3.03 s.
- **Named risk: does `force=True` reach a strict plan?** I checked `cli.py:3098` (`process_show` gets no `force`), `pipeline.py:170` and `reapply.py:194` (`force=False`). No caller passes `force` today, so M2 below is latent.
- **Named risk: does `drop_stage_artifacts` delete library audio before the build?** `workspace.py:94-114`: `package` drops only `package/manifest.json`. The plan-time and build-time library state therefore agree.
- **Named risk: is `StationUnreadable` caught by the hint on an unrelated station read in `fix`/`redo`?** I grepped `cli.py`/`campaign.py`/`pipeline.py`/`show_unit.py` for `station_mark.`. The only reads are in deliver/clear-mark (cli.py:2655-2968), outside the wrapped units. There is no misattribution.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

- **M1. Duplicated helper.** `packages/llama/src/llama/cli.py:3051-3053` (`_is_delivered`, diff:389-391) is a verbatim copy of `reapply.py:66-68` (`_delivered`). Task 9 will need the same predicate for strict reapply. Move one copy to `ledger`/`catalog` and import it from both.
- **M2. Latent spurious refusal under `force`.** `packages/llama/src/llama/stages/package.py` (diff:668, 683, 697-703): `paired` is captured before the in-place narrowing `reuse = replace(reuse, library={})`. Under strict with `force=True`, where the library file is in place and the station does not pair, `reuse_into` finds no candidate. `t.filename in paired` then raises `failed its length check` over a file sitting in place. No caller passes `force` with a strict plan today. Either guard with `dest.exists()` before raising, or document that strict ignores `force`.
- **M3. Loose detail for a missing copy.** diff:700-703: a paired copy that is simply absent (a partially purged library, with the station unpaired) reports `<file> failed its length check`. It is safe (no download), and the handback notes it.
- **M4. Tally omits in-place files.** diff:690-710, 728-729: in-place files (dest exists, no placement) count as neither reused nor downloaded, so an in-place re-package logs `audio reused 0, downloaded 0`. This is rare for delivered (purged) shows. Consider counting in-place files as reused, or say so in the docstring.
- **M5. Triage strict refusals print no hint.** Triage has no `--allow-download`, so a strict refusal prints `error: <slug>: station copy ...` with no route. The contract scopes the hint to by-name commands, so this is compliant. A pointer to `llama fix <slug> ... --allow-download` would help the operator. Controller's call.
- **M6. Coverage gap.** There is no test of the `fix --untitled` path under `_strict_refusal_hint` (diff:477-479). The redo and fix edit paths are covered.
- **M7. Refusal timing.** Strict refusals fire at build time, after gather/vet/brief. A `fix --narration full` on a delivered show with an unreadable station copy spends a fresh brief, then refuses, and the unit discards it. This is defensible: a held outcome must not refuse, and the brief puts `check_pairs` in `build_package`. The spec's per-wave mount check (Task 13) is the intended guard, so it matters there.

### Assessment

**Task quality:** Approved

**Reasoning:** The strict surface refuses before any download in every paired branch, restores the unit, and prints the contract strings exactly. The anchor lifecycle matches the spec, and the implementer's identifier tightening closes a real wrong-audio path the brief's literal rule left open. The remaining items are latent, cosmetic or coverage-only.
