# Plan review pr-1: piece 4 plan (plan-r1-frozen.md) against spec-final.md

I read the code at the worktree, `~/.llama-harness/piece45/spec/r1/` (`dump_r1.py`, `rprime2.py`, `r1_files.py`, `reuse_r1.py`, `m3_cmp.py`, `r1_files.jsonl`) and the evidence dir, all read-only. I checked the fixture claims in Task 1 Step 5 against the real `filter_files`: they are accurate. Task 1 Step 4's interior algorithm matches `dump_r1.kae` (spam and filename-junk files are left out of the order set; track-tag order only when complete and unique).

## Findings, most severe first

- **[Important] The aside trigger misses library audio left behind by an earlier unit, so old-numbered files can still be reused by name**
  - Where: Task 12, "when `reuse` is given and `[t.filename for t in show.tracks] != list(reuse.old_filenames)`, `set_aside` once before the loop". Also `ReusePlan.old_filenames`: "the current show.json's source filenames".
  - Problem: "changed" is judged against the `show.json` the unit starts with. That is not the numbering the library audio carries when an earlier unit re-gathered without packaging.
  - Evidence:
    - `_redo_show_locked` → `drop_stage_artifacts(..., "gather")` deletes `show.json`, notes and `package/manifest.json`, but never `package/audio/*` (`workspace.py:92-112`).
    - `process_show` returns None before `run_package` when the re-gather holds (`pipeline.py:157-164`).
    - `reapply_show` writes the new `show.json` without packaging on a held outcome (`reapply.py:165-176`).
    - `build_package` skips any `dest` that exists (`package.py:45-48`).
  - Failure scenario:
    1. A packaged, undelivered show has library audio. It is triaged with a `fix` edit, or `reapply`'d, after the rule inserts a file.
    2. The re-gather holds (a new unresolved track, the 18-show class). `show.json` now has the new list and the audio has the old numbering.
    3. A later `fix --overrule` runs `redo --from package`. `old_filenames` (the new `show.json`) equals the new list, so nothing is set aside. Library pairing fails, because the manifest is gone.
    4. `NN Title.mp3` from the old numbering is shipped for any new track N with the same title (e.g. a short-kept `Drums` piece inserted before the long `Drums`).
    5. Only the 5 s duration flag stands in the way. Spec 5.4 says "old-numbered files must never be left in place".
  - The same baseline also misses retitle-only changes: the packaged names change and the library copies are never reused (re-download plus stale files).
  - Suggested fix: decide aside-vs-keep from what is actually in `package/audio/`. Keep the files in place only when the library manifest exists and its packaged names equal the new show's `packaged_filename(index, title)` list; otherwise set aside whenever `package/audio/` is non-empty. Add a test for the held-then-overrule sequence.

- **[Minor] The corpus test's totals are mis-stated for the verdict function as specified**
  - Where: Task 1 Step 2, "Assert the totals: 2,822 keep, 685 junk, 3 filename, 37 edge-or-filename".
  - Evidence: two `drop-edge` rows (`01 Crowd.mp3` ×2) are filename-junk. `short_verdict` checks filename junk before interior, so it returns `"filename"` for them: 5 `filename` and 35 `edge` as verdict counts.
  - Failure scenario: an implementer who counts verdicts sees 5/35 and either edits the expectation or reports BLOCKED.
  - Suggested fix: state the totals per `r1_dec` class (or as verdicts: 2,822 / 685 / 5 / 35).

- **[Minor] The corpus test never exercises the interior computation**
  - Where: Task 1, `interior=(pos == "interior")`.
  - Evidence: the corpus `pos` is census r.py's definition (relative to the base-kept files only, `r.py:121`). `dump_r1` computes interior over kept ∪ tagged-kept ∪ untagged candidates. The corpus test therefore checks only the verdict logic; a wrong interior implementation stays green until Task 9's reference reproduction.
  - Suggested fix: say so in the task, or add a check that the untagged files `filter_files` keeps across the library fixtures match `arm_r1.jsonl`'s added untagged files for those slugs.

- **[Minor] Making the rule live (Task 1) before the re-key (Task 3) invites laundering an override mis-point into test expectations**
  - Where: Task 1 Step 5, "Then update each listed test with a comment naming its clause".
  - Evidence: `test_stage_gather.py:206` (`set_breaks=[11], encore_after=26` on gd74_windsor, which gains `Weather Report Suite Part I >`); `:2453` (furthur titles).
  - Failure scenario: a positional override in a fixture test shifts onto another file. The test is "explained" by the rule and its expected output edited. Task 3's conversion to filenames then keeps the wrong file.
  - Suggested fix: in Task 1's dry run, renumber an override that an insertion shifted so it stays on the same file (comment "re-keyed by filename in Task 3"), and never change its expected output.

- **[Minor] Task 11's "This is `reuse_r1.new_rule` with today's messages" is not true, so Checkpoint B's 1,017 may not reproduce**
  - Where: Task 11, `short = {t.filename for t in new_show.tracks if t.short_kept}`, dropped on both shows.
  - Evidence: `reuse_r1.py` uses `short = set(KEPT) - {stored filenames}`. The 173 already-included files stay in the comparison on both sides, and the break key skips only new files. The plan follows spec 5.3 (drop them on both sides), which is more permissive than what was measured.
  - Failure scenario: Task 15 Step 1 counts more than 1,017 and the orchestrator chases a non-defect.
  - Suggested fix: drop the "is new_rule" sentence; tell Task 15 to expect ≥1,017, and to explain the difference by the 173-file rows.

- **[Minor] The process check's shell clause is too broad**
  - Where: migration contracts, `llama_processes`: "a shell ... whose command line contains the word `llama` followed by a space".
  - Failure scenario: a wrapper such as `zsh -c "cd ~/projects/llama && .venv/bin/python scripts/rekey_overrides.py --apply"` matches on `projects/llama &&`. That wrapper is the script's own parent, so `--snapshot`/`--apply`/`--restore` refuse and nothing can override it.
  - Suggested fix: exclude the script's ancestor pids (read `ppid` from `ps`), and require `llama` in command position. Add the `cd …/llama && …` wrapper to `test_process_check_matches` as a non-match.

- **[Minor] `verify_snapshot` adds a rule the spec does not have, and the snapshot copies `.audio-aside/`**
  - Where: Task 18, "or the snapshot holds a file the manifest does not list". Also "every file under the show dir outside `package/audio/`".
  - Failure scenario:
    - A Finder `.DS_Store` in the snapshot dir makes `--apply` and `--restore` refuse permanently.
    - A leftover `.audio-aside/` from a SIGKILL'd unit (Task 12) puts audio into the "280 MB" snapshot.
  - Suggested fix: either drop the unlisted-file rule or ignore `.DS_Store`. Leave `.audio-aside/` out of the snapshot, as `.lock` is.

- **[Minor] Task 7's base-consistency formula omits carried package flags**
  - Where: Task 7, "the replay base row's ... `gather_flags + vet_flags + brief_flags` against `arm_base.jsonl`'s ... `flags`".
  - Evidence: `arm_base` `flags` = `legs.flags` = gather + vet + **carried** + brief (`dump.py:224`, `replay.Legs.flags`).
  - Failure scenario: every show with a `package`-family flag is listed as a mismatch at Checkpoint A.
  - Suggested fix: add the base row's `stored_flags` whose `flag_family` is `package`.

- **[Minor] Appendix A step 3's candidate arm overwrites Task 9's evidence, and step 9 contradicts the never-run-base rule**
  - Where: Appendix A step 3, `--out ~/.llama-harness/piece4/cand.json`. Step 9: "`compare` against a post-migration base".
  - Problem:
    - Step 3 writes the same path Task 9 Step 2 wrote and `acceptance.md` cites.
    - A "post-migration base" cannot be an e37f670 arm (spec 4.1).
  - Suggested fix: name the migration-day arms distinctly (`migration-base.json` / `migration-cand.json`). Say that step 9's base is a new-code arm, or leave step 9 wholly to the bulk-apply plan.

- **[Minor] An activated venv makes `--apply` refuse**
  - Where: Appendix A step 6; Task 19 gate "every `(path, out)` in `llama_versions()` has `version_ok(out)`".
  - Evidence: `/Users/shawn/projects/llama/.venv/bin/llama --version` prints `0.1.0`.
  - Suggested fix: add to Appendix A that the venv must not be activated (no `.venv/bin` on PATH). Have the gate's refusal name the path, as it already plans to.

- **[Minor] `repro` fails permanently on a show that is unreplayable in both arms**
  - Where: Task 7, "exit 1 ... on a row lacking these fields".
  - Failure scenario: one cache-miss or darked show in both pre and post blocks step 7 forever (0 today; `m3`: unreplayable 0).
  - Suggested fix: treat unreplayable-in-both with an equal reason as equal and list it.

- **[Minor] Task 9 Step 3 does not say what to do when `compare` refuses**
  - Where: Task 9 Step 3, "passes its gates (exit 0)".
  - Evidence: CLAUDE.md and memory record a failing 99% repro gate (13 drift rows). The sweep loop may change digests between the two arms.
  - Suggested fix: run the arms back to back, report exit 2 or 3 with the drift rows at Checkpoint A, and use `--no-repro-gate` only on an operator ruling.

- **[Minor] It is unclear whether reuse applies when the track list is unchanged**
  - Where: Task 12, "for a track whose `dest` is missing, `reuse_into` ... runs before the download". Also the pin `test_unchanged_list_behaves_as_today` ("no aside dir, no copy").
  - Problem: with a purged delivered show and an unchanged list, the interface copies from the station; the pin says no copy.
  - Suggested fix: say explicitly that an unchanged list still reuses the station copy for missing files, and scope the pin to "no aside, nothing moved".

- **[Minor] Reapply's failure path leaves the copies placed by reuse**
  - Where: Task 13, "`try: … except BaseException: put_back(ws); raise`".
  - Problem: `reapply` has no `show_unit` step (c). New-named files placed by `reuse_into` stay in `package/audio/` beside the restored old names.
  - Suggested fix: on failure, delete the names `build_package` placed, then `put_back`. Assert in `test_reapply_reuses_audio_and_puts_it_back_on_failure` that `package/audio/` holds exactly the old names.

- **[Minor] Mutant (e)'s predicted test cannot catch it**
  - Where: Task 21 (e) → `test_untagged_interior_kept_edge_dropped` (Task 1: "untagged short first and last files drop").
  - Problem: with untagged neighbours counted, a lone first file still has nothing before it, so the mutant survives.
  - Suggested fix: add two consecutive untagged short files at one edge to the Task 1 test.

- **[Minor] Triage `[m]` refuses venue/city/date edits on a stale show (an unmarked plan reading)**
  - Where: Task 5, "`[m]`, `[t]` and `[u]` run `_stale` before their own prompts".
  - Problem: spec 4.2 refuses positional edits only, and `fix --set-venue` still works. `[m]` mixes both kinds.
  - Suggested fix: run `_stale` only when the `[m]` answers change titles or breaks, or mark it as a plan reading.

- **[Minor] Interface gaps an implementer must fill in**
  - Task 1: `_keep_and_exclude` must report which names the rule kept, for `ordering["short_kept"]`. Its new return shape is not given, and it needs `orig_tracks` for `_track_number`.
  - Global Constraints lists the new `ShowReplay` fields as `filenames, short_kept, flags`; Task 6 also adds `segues` and `breaks`.
  - Task 19: what `rekey-applied.json` does after a `--restore` and a new snapshot (start a new record, or append) is unspecified.
  - Task 3 Step 5: the grep covers `Overrides` positional readers but not the `Track.index` readers that spec 8 premise 5 names.

- **[Minor] Proportion: Task 3 is very large for one implementer pass**
  - Where: Task 3 bundles the model, `override_keys.py`, the resolver wiring through `title_inputs`/`title_cascade`/`compute_gather`, `_edit_overrides` translation, the probe signature, and converting every positional-override test.
  - Problem: the interim state is awkward. Triage's `[m]` default renders `filename=Title` until Task 5, so tests are edited twice.
  - Suggested fix: split the pure `override_keys` and model work (with its oracle tests) from the gather and cli wiring, or tell Task 3 that triage display tests are Task 5's to change.

- **[Minor] Task 9 Step 1's `git diff e37f670 HEAD -- packages scripts` is a no-op**
  - Where: Task 9 Step 1.
  - Problem: HEAD is e37f670 in that worktree, so the diff is always empty.
  - Suggested fix: use `git -C <base> status --porcelain` empty plus `rev-parse HEAD == e37f670`.

TOTAL: 19 findings (0 Critical, 1 Important, 18 Minor)

Ready to execute after the Important finding (Task 12's aside trigger) is fixed; the Minors can be folded in during execution.
