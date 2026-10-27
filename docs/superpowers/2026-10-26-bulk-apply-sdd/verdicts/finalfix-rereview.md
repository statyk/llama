# finalfix-rereview: scoped re-review of the final-review fix wave (44ae6cf2..65d13e35)

I read the diff file once, read the code it touches, and ran the tests in scratch copies made with `git archive 65d13e35 | tar -x`. I made no changes to the live worktree and no commits.

## Per finding

**I1: ADDRESSED.**
- `CLAUDE.md:88` now says the refusal comes from the LIBRARY campaign record, an unreadable record included, both by name and in selectors.
- It also says a processed show's marked STATION copy is not refused and is replaced wholesale, which clears the mark.
- The code agrees:
  - `cli.py:2608-2622`: `_awaiting_fix_check` reads `campaign.read_record`.
  - `cli.py:2651`: it is the first check under the lock in `_deliver_one`.
  - `cli.py:2681-2682`: `voiced or marked or …` leads to `_replace_destination`.
  - `catalog.py:45`: an unreadable record counts as awaiting in `CatalogEntry.awaiting_fix`, which the batch uses.
- The other mark sentences are consistent with the code: `CLAUDE.md:95` (clear-mark), `:96` (status) and `:664` (the contract paragraph).
- Wording nit (Minor, below): after the rewrite, the colon that introduces the fixed refusal strings follows the station-copy clause ("…which clears the mark: `refusing to deliver …`"). That makes the refusal text read as if it belonged to the replacement case.

**I2: ADDRESSED.**
- `reapply.py:11-15` now gives the order processed → `after_commit` → purge, and says why: a failing hook restores the unit, and purged audio could not be put back.
- The code matches: `reapply.py:381` (`mark_processed`), `:382-383` (`after_commit`, whose inline comment already said "before the purge"), then `:386-387` (purge).

**I3: ADDRESSED.**
- `cli.py:3087-3088` calls `audio_reuse.check_pairs(reuse, show_ws)` right after `plan_reuse(..., strict=strict)` and before `drop_stage_artifacts` and `process_show`. The import is `cli.py:25`, and `audio_reuse` is not shadowed anywhere in `cli.py`.
- **No side effects.** `audio_reuse.py:199-212` only reads `plan.strict` and `plan.station_problem`, calls `is_file()` on `package/audio/<name>`, and raises.
- **Gating is identical to `build_package`'s.**
  - `package.py`: `strict = reuse is not None and reuse.strict`, then `check_pairs`.
  - In redo, `reuse` is always non-None, and `check_pairs` returns at once when `not plan.strict`.
  - `plan.strict` comes from `strict = delivered and from_stage != "select" and not allow_download` (`cli.py:3080`).
  - So a non-strict redo, `--from select`, an undelivered show and `--allow-download` are all no-ops.
- **The early check never refuses a case the late check would have passed.**
  - `station_problem` and the station pairing are fixed at plan time.
  - The library leg can only lose files between plan time and `build_package` (`drop_stage_artifacts`), never gain them.
- **Same exception path.** `pipeline.process_show` has no handler for `StationUnpaired`/`StationUnreadable`. The exception therefore always propagated out of `_redo_show_locked` to the same callers: `_strict_refusal_hint` (`cli.py:3043-3052`, unchanged text and hint), triage, `fix`, and batch redo.
  - It is still raised inside the caller's `show_unit`, so the anchor that `write_anchor_if_absent` wrote just before is rolled back. The test asserts `tree_bytes(ws.dir) == before`.
- **Untouched list holds.** The fix diff does not touch `audio_reuse.py` or `stages/package.py`, so `plan_reuse`, `check_pairs`, the pairing rule and `purge_package_audio` are unchanged.
- **Test.** `test_redo_cmd.py:885-908` is `test_redo_of_a_delivered_show_refuses_strict_reuse_before_any_llm_call`, parametrized over `gather` and `brief`.
  - It asserts the `station copy unreadable: no directory …` text, `HINT`, exit 1, `spent == []` (recording wrappers on `pipeline.run_gather` and `pipeline.run_brief`), no downloads and an unchanged tree.
  - It counts stage entries, not fake-provider calls. That is an equivalent proxy for zero LLM spend.
- **Mutant run.** In a scratch copy I deleted the new `check_pairs` line. Interpreter shadowing was checked first: `llama.__file__` resolved inside the copy.
  - Mutant: exactly the 2 predicted parametrizations failed (`2 failed, 131 passed` over `test_redo_cmd.py` and `test_deliver_cmd.py`). The log shows researching, vetting and briefing ran before packaging.
  - Unmutated copy: 133 passed.

**M1: ADDRESSED. The added line is adequate and not misleading.**
- `cli.py:2787-2798`: when the under-lock `_awaiting_fix_check` passes for a show in `awaiting`, the batch prints `<slug>: processed since the plan was listed; delivering` and goes on to `_deliver_one`. The usual `delivered: <path>` follows, or the refusal if something else turns the show away.
- The implementer's concern is correct. The `(refused: awaiting fix)` suffix is printed by `_confirm_plan` (`cli.py:2467-2478`) before any lock, and `marks` is never read after that.
  - So `marks.pop(e.slug, None)` at `cli.py:2796` is dead code: harmless, but it does nothing.
  - The explicit line is what fixes the report. It names the transition in the order the operator reads it: plan says refused, later line says processed since and delivering, then `delivered:`.
  - Re-scanning before the plan would only move the race window, so it is not worth it.
- Test: `test_deliver_cmd.py:903-923` asserts the line, delivery to the destination, exit 0 and no `refusing`.

**M2: ADDRESSED.**
- `cli.py:2716-2721` now says `_deliver_one` re-checks only the awaiting-fix refusal under the show lock, not the processed or marked tests.
- That matches `_deliver_one`, which re-runs `_awaiting_fix_check` (`cli.py:2651`) and does not re-run the `processed`/`mark_of` predicate. Its voiced, gate and replace logic is separate and not part of the `--fixed` predicate.

**M3: ADDRESSED, all three lines.**
- **(a) Audio cost of restoring a wave.** Plan Appendix B now says restoring a wave empties `package/audio/` when the package manifest differs. This matches `batch_snapshot.py:467-472` (`empty = snap_files[package manifest] != current[...]`) and `restore`, which "Never writes the station". The line says "packaged, undelivered show", and that is the case that costs a download; a delivered show's audio is normally already purged.
- **(b) Torn `after.jsonl` line.** The refusal text `<path> line N is not an after-record; nothing restored` matches `batch_snapshot.py:395` exactly. Once the torn line is deleted, the show's `after` is None, which gives `refused: changed, and this batch recorded no write for it` (`NO_WRITE`, `:53`, `:458-459`). It gives `untouched` if nothing changed.
  - Wording nit: the doc says the show "restores as `changed, …`", but it is a refusal (`refused: …`).
- **(c) `unmark` and `mark_added: false`.** This matches `scripts/bulk_apply.py:1126` (docstring) and `:1143-1145`: `kept (this batch added no library mark)`, with no station write.

## New breakage in the fix diff

**Critical:** none.

**Important:** none.

**Minor:**
1. **A strict redo that ends held is now refused when the station cannot be read.** This is a behaviour change inherent to I3, not a regression in what I3 asked for.
   - Before the fix, a strict redo (`fix --set-title` on a delivered show, a triage edit, `redo --from gather`) whose re-gather or brief ended HELD never reached `build_package`. It therefore succeeded as `still held` even with the station unmounted or not pairing (`pipeline.py:161/168` return before packaging).
   - Now it is refused up front with the `--allow-download` hint, and that hint does nothing for a show that would not have downloaded anything.
   - The refusal is conservative: the unit rolls back and nothing is lost. The fix is "remount the station first" or `--allow-download`.
   - Worth knowing for triage over held, delivered shows while the NFS/SMB station mount is down. Every edit in such a session will now refuse, where before only the edits that cleared the hold did.
   - `reapply` avoids this by checking only when it already knows the show will package. redo cannot know that in advance.
2. **`marks.pop(e.slug, None)` at `cli.py:2796` is dead code**, because `marks` is not read after `_confirm_plan`. Its comment implies it corrects the report. It is harmless, and could be dropped or recommented.
3. **Two doc wording nits.**
   - The `CLAUDE.md:88` colon placement described under I1.
   - Appendix B's "restores as `changed, and this batch recorded no write for it`" would read better as "is refused as".

## Out-of-scope observations
- In the `CLAUDE.md:88` sentence, "refused … in every selector" is loose for `deliver --fixed`: `_fixed_for_delivery` silently drops an awaiting-fix show from the selection rather than listing it as refused. The effect is the same, since it is never delivered.
- `reapply.py:15` is now one over-long docstring line. Cosmetic only.

## Verification run
Both runs used the scratch copies, with `PYTHONPATH` shadowing and `-p no:cacheprovider`. Shadowing was proven via `llama.__file__`.
- Unmutated copy, `packages/llama/tests` plus `scripts`: 4299 passed, 7 deselected.
- Mutant, as above: the 2 new tests failed, the rest passed.

**Verdict:** all addressed. I1, I2, I3, M1, M2 and M3 are all ADDRESSED. There is no Critical or Important breakage, only the three Minors above. The one worth an operator note is the strict up-front refusal of a redo that ends held.
