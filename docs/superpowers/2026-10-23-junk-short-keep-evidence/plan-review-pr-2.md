# Plan review pr-2: piece 4 plan (plan-r1-frozen.md) against spec-final.md

Reviewer: Opus. Read-only. Checked against the code at the worktree (= e37f670) and the reference harness under `~/.llama-harness/piece45/spec/r1/`.

Overall, the plan follows the spec closely. Every 6(f) test item and every required mutation has a named home. The two "plan readings" (Task 16 "track list changed" = any change of packaged names; Task 19's up-front snapshot comparison) are reasonable and stricter than the spec. The fixed strings, exit codes and the migration contract block are consistent. The findings below are about gaps where the code differs from what the plan assumes.

## Findings, most severe first

- **[Important] Audio is set aside only when the list changed "vs the current show.json", so the deferred-package path leaves old-numbered files in place**
  - Where: Task 12, "when `reuse` is given and `[t.filename for t in show.tracks] != list(reuse.old_filenames)`, `set_aside` once before the loop"; and the pin `test_unchanged_list_behaves_as_today` (no aside dir).
  - Problem: `old_filenames` is the show.json in place when the unit starts. A show can be re-gathered without being re-packaged:
    - a reapply or redo whose outcome is held (no `build_package` call, `reapply.py:166-171`);
    - a redo from gather that ends held.
    After that, show.json already holds the new list while `package/audio/` still holds files packaged under the old numbering. Then a later `fix --overrule` or `redo --from package` runs:
    - `plan_reuse` sees the new show.json, so the list "did not change" and nothing is set aside;
    - the library manifest no longer pairs, so it contributes `{}`;
    - `build_package` finds `packaged_filename(i, title)` already present (`package.py:46-50`, `if not dest.exists()`) and retags the OLD file.
    This is exactly the case spec 5.4 rules out: "old-numbered files must never be left in place: a renumbered track with the same title as the old track at its number would inherit the wrong audio."
  - Evidence: m3 shows 16 packaged (library audio present) and 17 delivered shows turned into holds by the rule. All of them will be triaged and overruled later, which is the deferred path. Only the 5 s duration-mismatch flag partly catches it; a near-equal duration ships silently.
  - Fix: decide "changed" against the audio actually on disk, not against show.json. Simplest: whenever a reuse plan is given and `package/audio/` is non-empty and the library manifest does not pair index-for-index with `show.tracks`, set the whole directory aside. Add a test for the gather → held → overrule → package path.

- **[Minor] `_destination_is_voiced` gains a raising mode, but one caller outside `cli.py` is not updated**
  - Where: Task 16, "any other `OSError`, invalid JSON, or a non-object → `raise LlamaError(...)`"; Files lists only `cli.py`/probe.
  - Evidence: `scripts/replay_holds.py:688-692` (`_is_voiced`) imports `llama.cli._destination_is_voiced` and is called inside `compare` (`_taper_changes`). After Task 16, one unreadable station manifest crashes the Task 22 `compare` run.
  - Also: the new `reapply` hint calls it with `config.delivery_path / slug`, and the plan does not say what happens when `delivery_path` is None.
  - Fix: add `replay_holds._is_voiced` to Task 16 (catch `LlamaError` and report the row as unreadable), and print the hint unchanged when there is no `delivery_path`.

- **[Minor] The planned interior test cannot catch mutant (e)**
  - Where: Task 1, `test_untagged_interior_kept_edge_dropped` ("untagged short first and last files drop"); Task 21 (e) predicts this test.
  - Problem: with one untagged file at each edge, "counts untagged candidates as neighbours" gives the same answer. Nothing sits before the first file or after the last. Task 21 will score a survivor. This is strict surface (c): the mutant admits extra edge files.
  - Fix: add two consecutive untagged short files at an edge (U1, U2, K…). The mutant keeps U2; the rule drops it.

- **[Minor] The corpus test feeds the census's `pos`, so `_keep_and_exclude`'s own interior derivation and tag lookup are never corpus-checked**
  - Where: Task 1, `test_deny_vocabulary_corpus` calls `short_verdict(name, tag, None, interior=(pos == "interior"))`.
  - Problem: spec 6(f) asks that "every measured drop stays dropped and every measured keep stays kept". Here, play order, the kept ∪ tagged-kept neighbour set and the original-title fallback inside the filter are covered only by small unit fixtures and by the Task 9 reproduction.
  - Fix: say in the test docstring that it covers the verdict only, and make Task 9's per-show reference reproduction explicitly the end-to-end gate for the 3,547 rows (list any row whose keep/drop differs from `r1_dec`).

- **[Minor] Briefing reuse is not quite `reuse_r1.new_rule`, so the Task 15 count can drift**
  - Where: Task 11, "drop tracks whose filename is in `short` on both shows … This is `reuse_r1.new_rule` with today's messages"; Task 15 Step 1, "1,017 of 1,415".
  - Evidence: the reference used `short = set(KEPT) - {stored filenames}` (`reuse_r1.py:53`). So the 173 already-included files stayed in the comparison on both sides. The plan (and the spec text) drop them from both sides.
  - Fix: keep the spec's rule, delete the "This is new_rule" sentence, and accept "≥ 1,017, each difference explained" at Task 15.

- **[Minor] A `.lock`-only or empty show directory makes the snapshot fail verification forever**
  - Where: Task 18 `verify_snapshot`, "a recorded slug has no entry"; spec "every show directory … has its entries".
  - Problem: `show_unit` limitation 2 (a racing `rm`) leaves `.lock`-only husks. `.lock` is not copied, so the slug is recorded with zero files. `--apply` then refuses with "no verified snapshot" and no route.
  - Fix: record each slug's file list (possibly empty) in `manifest.json` and verify against that. Or make `--snapshot` refuse up front, naming the husk and its removal.

- **[Minor] The process check matches the script's own parent shell**
  - Where: Migration contracts / Task 17, "a shell … whose command line contains the word `llama` followed by a space; the line whose pid is `self_pid` never matches".
  - Problem: a wrapper such as `zsh -c 'cd /Users/shawn/projects/llama && …/python scripts/rekey_overrides.py --apply'` matches. Claude Code's Bash tool runs commands this way. The script then refuses itself; it fails safe but confuses the operator.
  - Fix: exclude `self_pid` and all of its ancestors (walk `ppid` from the same `ps` listing, adding `ppid=` to `-o`). Add that case to `test_process_check_matches`.

- **[Minor] reapply's failure path restores old names but leaves the call's new audio beside them**
  - Where: Task 13, "`try: … except BaseException: put_back(ws); raise`".
  - Problem: unlike `show_unit` (`restore_snapshot` step (c) drops added audio), reapply does not delete files it downloaded or reused. If the failure comes after `build_package` (e.g. the commit-marker write, which is the test's own injection point), the new `package/manifest.json` stays. Old audio is put back under names that may coincide with the new manifest's entries. The show stays held, so nothing ships, but the package dir is inconsistent.
  - Also: the plan says reapply deletes a leftover aside "at its entry". That must not happen under `--dry-run`.
  - Fix: on failure also delete audio not in the pre-call name set and drop `package/manifest.json`. Skip the leftover-aside deletion in dry runs.

- **[Minor] The premise-5 grep omits `Track.index`**
  - Where: Task 3 Step 5 greps `.titles/.set_breaks/.encore_after` only.
  - Problem: spec 8 premise 5's test is "a grep over every reader of `Overrides` and `Track.index` in `llama`, `scripts` and `emcee`".
  - Fix: add the `Track.index` / `.index` grep and list its readers in the commit message.

- **[Minor] `--exclude` plus a clear of the same file in one invocation is refused**
  - Where: Task 4, "`_keyed_files(sws, this invocation's new title/break/encore files)`".
  - Problem: this invocation's `--clear-title <f>`, `--clear-set-breaks` and `--clear-encore` are not subtracted. `fix --exclude 4 --clear-title 4` refuses and tells the operator to pass the flag they already passed.
  - Fix: compute the keyed set after applying this invocation's clears as well as its additions.

- **[Minor] Small executability gaps an implementer would have to invent**
  - Task 5: "reuse its predicate, not its `Exit`". `_refuse_legacy` has no separate predicate. Define `_legacy_message(sws) -> str | None` in Task 4.
  - Task 5: the metadata line for a filename key not in show.json (dangling) has no rendering rule.
  - Task 2: "right after slice 5's `strip_notes`". That code sits inside `if "slice5" in enabled_slices:` (`gather.py:2018-2025`). State that the junk note runs unconditionally.
  - Task 3: the `slug` passed by `compute_gather` is unspecified. Replay and reapply run it on `ShowWorkspace(scratch / "show")`, so `show_ws.dir.name` reads `show`. Use `slugify(candidate.performance_id)`.
  - Task 12: `packaged_filename` takes three arguments (`index, title, suffix`).
  - Task 8: `r_packets.py` is at `~/.llama-harness/piece45/r_packets.py`, not under `spec/r1/`.

- **[Minor] Task 9 Step 1's base-tree checks**
  - Where: "`git worktree add --detach .claude/worktrees/junk-filter-base e37f670` … `git diff e37f670 HEAD -- packages scripts` there is empty".
  - Problem: the relative path nests the base worktree inside the junk-filter worktree unless run from the main checkout. In a tree detached at e37f670 the diff is trivially empty.
  - Fix: give the absolute path `/Users/shawn/projects/llama/.claude/worktrees/junk-filter-base`, and check `git -C <base> status --porcelain` is empty and `git -C <base> rev-parse HEAD` == e37f670.

- **[Minor] Interface lists disagree, and `rekey-applied.json` spans attempts**
  - Global Constraints list `ShowReplay.filenames, short_kept, flags`; Task 6 also adds `segues` and `breaks`, which Task 7's `repro` needs. Align the Global list.
  - `rekey-applied.json` "accumulat[es] across interrupted runs". After a `--restore` and a NEW snapshot, the stale file names the old snapshot and old shows. Reset it when its `snapshot` differs from the one in use.

## Checked and fine (no finding)

- Decomposition, order and checkpoints: A comes after the measurement and before section-5 work; B comes before `deliver`; C is last.
- The `ordering["short_kept"]` / `Track.short_kept` / coverage wiring: `_songish_coverage` is the only coverage computation (`structure.py:1129,1253`).
- Legacy classification: `TypeAdapter(int).validate_json` matches v2.17.0 for every spec example. I verified this on pydantic 2.13 (`" 7"`→7, `"7_0"`→70, `true`→1, `2.0`→2, `2.5`/`"Track 7"`/`""` rejected). The new `int | str` model keeps `"7"` as a str and `true`/`2.0` as ints, all still legacy.
- The resolver is reached through `title_inputs` by gather, redo, reapply and replay.
- Every writer goes through `_edit_overrides`, so translating through show.json covers `fix`, triage, `--suggest-titles` and `--untitled`.
- The migration gates, routes, raw-JSON rewrite, restore ordering and the "not reverted" lists match spec 4.3.
- The 34-hold class order reproduces m3's split (4/18/3/6/2/1).
- The fixture names in Task 1 Step 5 exist.
- `fixture_library.library_show` and `helpers.tree_bytes` exist.
- Scripts tests already put llama's tests directory on `sys.path`.

TOTAL: 13 findings (0 Critical, 1 Important, 12 Minor)

Ready to execute once the one Important item (Task 12's set-aside condition) is fixed; the Minor items can be folded into their tasks' briefs.
