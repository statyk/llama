# rv4-s: strict-surface review of spec-r4-frozen.md, section 4

Reviewer: Opus. I read the frozen spec and the e37f670 code: models.Overrides, workspace.read_overrides/write_artifact/drop_stage_artifacts, catalog.iter_shows/resolve_show/remove_show, cli._edit_overrides/fix/_redo_show/reapply loop, stages/gather.py (override application, `_validate_structure_override`), stages/package.py `build_package`, replay.py and scripts/replay_holds.py. I ran v2.17.0's `Overrides` model, plus a stand-in for the new union model, against scratch JSON in `rv4-s-scratch/` (t1.py, t2.py). `~/.local/bin/llama --version` reports 2.17.0, and `which -a llama` lists the same path twice. The repo `pyproject` reports `0.1.0`.

Measured facts used below:
- v2.17.0 lax int accepts `" 7"`, `"7.0"`, `"+7"`, `"07"`, `"7\n"`, `"7_0"` (giving 70), `true` (giving 1), `2.0`, `"-1"` and `"0"`. It rejects `"1e1"`, `2.5` and `"x.mp3"`.
- `{"3":"a","03":"b"}` parses to `{3:"b"}` (last wins).
- Under the new `int | str` union, `true` and `2.0` become ints and `"3"` / `" 4"` stay strings.
- v2.17.0 `fix --clear-title` requires `isdigit()`, so `-1` cannot be typed.
- `build_package` skips any `dest` that already exists (`if not dest.exists() or force`), and `drop_stage_artifacts("package")` deletes only `package/manifest.json`.
- The e37f670 harness (`replay_show`) catches an unreadable `overrides.json` and records the row as `unreplayable`. The run still exits 0.

## Scenario walk-through

1. **Normal run: PASS.** The dry run reports 0 refused. Then `--snapshot`, the install, and the `--apply` gates (4.3). The per-show re-check, the map through `tracks[N-1].filename` and the atomic write follow. The new resolver maps filename values onto the new kept list (4.1 "One resolver"). The new rule only adds short candidates, so every keyed file is still kept and the mapping resolves. The staleness check plus the override-title and set_breaks equality checks prove that position N in `show.json` is what v2.17.0's next gather would use. So the map is exact. Caveat: step 7 restarts the sweep before step 8 (finding 15).

2. **Dry-run refusals repaired under v2.17.0: PASS with gaps (finding 10).** While the library is all legacy, every route in the table runs under v2.17.0. Three gaps:
   - A title key `<= -1` cannot be cleared with v2.17.0 `--clear-title`.
   - Duplicate-after-parse keys (`"7"` and `"07"`) make the "exactly the forced title" check unclearable by `redo`.
   - `redo --from gather` itself fails when there is no `provenance.json` or the item is darked, and the spec gives no fallback route for that.

3. **SIGKILL or Ctrl-C inside `--apply`: PASS for the files.**
   - Before the rename, the legacy file is intact. A stray temp file is harmless; restore deletes it.
   - After the rename, the show is migrated, and a re-run skips it ("A migrated show has no legacy value and is skipped"). The gate leaves migrated files out.
   - The old binary fails loudly library-wide (`resolve_show` goes through `iter_shows`, so there is no path that bypasses it).
   - The new binary refuses legacy shows in writers and in gather.
   - There is no `--undo`. `--restore` is the only undo, and the spec says so.
   - FAIL on the route after a per-show re-check refusal: it says "`--restore` is the way back", but not what comes next (finding 2).

4. **`--restore`: PARTIAL FAIL.**
   - Right after the migration: PASS.
   - After edits, gathers and the bulk apply: PASS for the show dirs, but it leaves reapply batch state (finding 11) and the station (finding 12).
   - Interrupted mid-way: PASS only because the bullets happen to be ordered "empty audio, then copy" (finding 4).
   - Run twice: PASS.
   - Shows created after the snapshot: FAIL (finding 5).
   - Audio already re-packaged: FAIL for a show that had no manifest at snapshot time (finding 4).
   - Station copy re-delivered: PASS, but nothing is listed (finding 12).
   - Concurrency: FAIL (finding 6).

5. **Version skew: PASS.**
   - v2.17.0 on a part- or wholly-migrated library: every listing and resolve raises `ValidationError` (`iter_shows`). `fix`, triage and `--no-run` all resolve through it. `reapply --from-list` builds per row and fails the migrated rows individually. v2.17.0 has no lenient overrides read anywhere.
   - The new binary: parsing accepts legacy, migrated and mixed files. Writers refuse legacy and mixed files before any prompt. Gather refuses them through the resolver.
   - The claim in 4.1 that "an old-commit harness arm fails loudly" is false (finding 7).

6. **Writer edit on a legacy file before the migration.**
   - v2.17.0: PASS. The edit normalizes keys. If it lands after the snapshot, the mtime gate trips. A `--no-run` stale `show.json` is caught by the staleness and override-title checks.
   - The new binary: PASS, it refuses.
   - FAIL: when that catch happens at `--apply` time, the printed route cannot run (finding 2).

7. **Writer edits after the migration: PASS.**
   - The staleness check refuses positional edits on rule-changed shows until they are re-gathered. Numbers translate through `show.json`. The `--clear-*` flags skip the check, which is safe.
   - The up-front refusal on excluding a keyed file holds.
   - `--untitled` and `[u]` write filename keys plus `[]`. `[t]` translates through `show.json`.
   - Caveat: the shows the rule changes but the bulk apply leaves out are blocked indefinitely (finding 14).

8. **`set_breaks: []`, `titles {}` and encore-only files: PASS.** An empty `[]` or `{}` is not legacy and is left as is. Encore-only files check against `sorted(∅ ∪ {e})`. The delmccoury shape is pinned, and restore is byte-exact.

9. **Harness and replay: PARTIAL.**
   - Base arm before the migration: PASS.
   - Base arm after the migration: not loud; 606 rows come back `unreplayable` (finding 7).
   - Apply lists generated before the migration: skipped on `input_digests`, which is loud: PASS.
   - `reapply` on a migrated library goes through the resolver: PASS.
   - The post-migration self-check compares only outcome and titles (finding 3).
   - Restore and re-run of the same list: rows are silently skipped (finding 11).

10. **Two writers.**
    - `--apply` against a fix, redo or triage holding the show lock: PASS. It waits on the blocking `file_lock`, then re-checks. The fix/triage `changed by another command` check covers the reverse race.
    - The sweep loop during `--apply`: PASS, because show locks protect it and the new writers refuse legacy files.
    - The sweep loop during `--snapshot` or `--restore`: FAIL (findings 1 and 6).

11. **Metadata-cache refresh.**
    - After the migration: PASS. Gather names every dangling key, and `--clear-*` (filename form, no staleness check) clears them.
    - Between the dry run and `--apply`: refused loudly, but with an unrunnable route (finding 2).

12. **Gates.**
    - Snapshot missing: PASS.
    - Stale snapshot: only by `overrides.json` mtime (finding 1).
    - Corrupt snapshot: FAIL. It is not verified until restore, which then writes nothing (finding 1).
    - PATH binary old, absent, or more than one `llama`: PASS (`which -a`, every entry).
    - Dev build: PASS only if the minimum version is a constant, not the branch's `llama.__version__` (`0.1.0`) (finding 8).
    - A `llama` process running: partial (finding 9).
    - `--restore` after v2.17.0 is reinstalled: PASS for the restore itself. The routes for listed shows then need the new binary (finding 5).

## Findings

### 1. [Important] The snapshot is not verified, bound or made consistent at the point of no return
- **Where:** 4.3 `--snapshot`; the first `--apply` gate; `--restore` "verifies every hash … writes nothing if one fails".
- **Problem:** `--apply` checks only two things: a directory with a `manifest.json` exists, and it is "newer than" the last legacy `overrides.json` write. Four gaps follow:
  - Nothing checks the snapshot's hashes, its coverage, or that its contents equal the files about to be rewritten.
  - "Snapshot time" is undefined: the directory-name timestamp at start, the manifest mtime, or the copies' mtimes, which `copy2` would preserve.
  - `--snapshot` takes neither the migration lock nor the show locks, and checks for `llama` processes only at start. A gather or fix that lands mid-copy can give a show an inconsistent `overrides.json`/`show.json` pair in the snapshot, or a stale copy.
  - `--snapshot` does not refuse a library already partly migrated, so a snapshot taken after an interrupted `--apply` passes the gate and is a useless rollback point.
- **Evidence:** the gate's text in 4.3. `--restore` is the first and only reader of `manifest.json`'s hashes.
- **Failure scenario:** a snapshot file is damaged or deleted after creation, or the snapshot is incomplete. `--apply` passes and migrates 606 files. Weeks later "piece 4 is wrong", and `--restore` finds a hash mismatch and writes nothing. There is no rollback and no route. Alternatively, a hand edit or a restored-from-backup `overrides.json` with an old mtime passes the gate, and restore later silently reverts it.
- **Suggested fix:**
  - Define snapshot time as the moment copying starts, recorded in `manifest.json`.
  - `--snapshot` takes the migration lock and each show's lock while copying that show, and refuses if any `overrides.json` holds a filename value.
  - `--apply` verifies the chosen snapshot's every hash before writing anything.
  - Per show, under the show lock, `--apply` requires `overrides.json` and `show.json` to be hash-equal to their snapshot copies, which replaces the mtime test.
  - `--apply` records the snapshot path it was gated on in `<root>/rekey-applied.json`. `--restore` warns when given a different snapshot.

### 2. [Important] Refusals found at `--apply` time print routes the installed binary cannot run
- **Where:** 4.3 runbook steps 2-6; the checks table ("repair (step 3, v2.17.0 installed)"); `--apply` "If any show would be refused it writes nothing and prints each refusal"; re-check step 1.
- **Problem:** `--apply` re-runs every check after step 5, with the new binary installed. Any change since the last dry run is refused there, with the table's route: a v2.17.0 `fix --no-run`, a cache refresh, or a v2.17.0 edit followed by a re-snapshot. The route is usually `llama redo <show> --from gather`. Under the new binary, that redo's resolver refuses the still-legacy show with `run the migration`. So `--apply` says redo, and redo says run the migration.
  - For a refusal inside the per-show re-check, the spec says only "`--restore` is the way back". It does not say to reinstall v2.17.0, repair, and resume at step 2.
- **Evidence:** 4.1 "It refuses with `LlamaError` … a file with any legacy value (… run the migration)", and 4.2 "Writers refuse legacy".
- **Failure scenario:** the dry run is clean. The operator does a quick `fix --no-run` under v2.17.0, snapshots, installs, and runs `--apply`, which refuses with `llama redo …`. The redo refuses. This is loud, but the documented way out is circular.
- **Suggested fix:** at `--apply` time (exit 1), print the route: "nothing written; reinstall v2.17.0, take the repair, return to step 2". After a re-check refusal, print the full route: `--restore <snapshot>`, reinstall v2.17.0, take the named repair, then step 2 (a new snapshot is needed). Put both in the runbook.

### 3. [Important] The post-migration self-check compares only outcome and titles, so 427 breaks and 365 encore keys are never checked end to end
- **Where:** 4.3 "Harness and apply lists": "must reproduce the pre-migration candidate's per-show outcome and titles"; 6(d) "Every base override track keeps its title on the same file".
- **Problem:** the harness re-key imports the migration's mapping function. The only migration code the post-migration re-run uniquely exercises is the raw-JSON rewrite, plus the legacy classification on raw values. A rewrite bug that drops or mangles `encore_after` or `set_breaks` changes set labels but neither titles nor, usually, the outcome. 6(d) likewise measures only titles.
- **Evidence:** the quoted text. Set labels are not part of the "outcome".
- **Failure scenario:** the rewrite drops `encore_after` when `set_breaks` is absent (encore-only files). Gather falls back to alignment, the encore folds into the last set, and no flag fires. Both checks pass.
- **Suggested fix:** compare the per-track `(filename, title, title_source, set, segue)` and `show.set_breaks` for every show. Extend 6(d): every base override-path structure keeps each break and the encore after the same file.

### 4. [Important] Restore can leave new-numbered audio beside a restored old manifest
- **Where:** 4.3 `--restore`, first bullet: "when the show's current `package/manifest.json` differs from its snapshot copy, it empties `package/audio/`".
- **Problem:**
  - The rule does not cover a show with no `package/manifest.json` at snapshot time but one now: a held or briefed show the bulk apply packages, of which 123 held and 10 briefed shows change. Restore then deletes that manifest as an "other file" and leaves `package/audio/` intact.
  - v2.17.0 `redo --from package` drops only `manifest.json`, and `build_package` skips any existing `packaged_filename(index, title)`. That is the exact hazard 5.4 describes.
  - Crash safety also depends on the bullets' order. If the manifest is copied back before the audio is emptied and the run is interrupted, the re-run sees equal manifests and never empties the audio. The spec does not mark the order as load-bearing.
- **Evidence:** `stages/package.py` (`if not dest.exists() or force`); `workspace.show_stage_artifacts("package")` holds only `manifest.json`.
- **Failure scenario:** the bulk apply clears a held show and packages it with the new numbering. Restore runs, the operator later overrules the hold under v2.17.0, and a track whose new index and title equal the old ones keeps the wrong file (a repeated `Jam`, `Tuning` or `Drums`). The wrong audio airs.
- **Suggested fix:** empty `package/audio/` unless the snapshot holds a `package/manifest.json` byte-equal to the current one. That covers absent on either side. State that emptying precedes every copy and is re-decided from the snapshot on a re-run. Pin both with a test.

### 5. [Important] Shows created after the snapshot keep a new-rule `show.json` that v2.17.0 edits silently mis-point
- **Where:** 4.3 `--restore`: "A listed show is not restored: it keeps the new rule's `show.json` … A listed show with no filename value needs nothing"; and the `llama rm <show>` route.
- **Problem:**
  - v2.17.0's positional writers have no staleness check. They store N and gather applies N to v2.17.0's own old-rule kept list. On a listed show, the operator reads N from the new-rule `show --tracks`, which counts the short-kept files. A `--set-title`, `--set-breaks` or `--set-encore` then lands on a different file, silently with `--no-run`. This is the re-point piece 4 exists to stop.
  - The route `--clear-title <filename>` under the new binary auto-redoes from gather, under the new rule.
  - `llama rm <show>` (no `--forget`) leaves the ledger rows, so "it is re-fetched by a later `get`" is false for a delivered or suppressed show.
- **Evidence:** `cli.fix` stores `parsed_titles[int(n)]` with no translation; `catalog.remove_show` defaults to "ledger untouched".
- **Failure scenario:** a `get` after the migration creates a show. The operator restores and reinstalls v2.17.0, then runs `llama fix <show> --set-title 7=X --no-run` against the new-rule numbering. The title lands on the old-rule track 7.
- **Suggested fix:** for every listed show:
  - with the new binary, clear each filename value with `--no-run`;
  - after reinstalling v2.17.0, run `llama redo <show> --from gather` before any edit, or `llama rm <show> --forget` when it should be re-fetched;
  - restore prints this for listed shows with no filename value too.

### 6. [Important] Restore takes no show locks, and nothing stops the sweep loop around it
- **Where:** 4.3 `--restore` ("refuses while a `llama` process is running, and takes the migration lock"); runbook step 7 restarts the sweep loop; no step exists for restore.
- **Problem:**
  - Neither llama binary honours `.rekey.lock`, and the process check runs once at start. A sweep iteration (the loop sleeps 600 s, so `pgrep` passes) or any concurrent unit can run inside a restore.
  - Restore overwrites files under a live unit and deletes its `.txn/` (the "every other file" bullet).
  - A unit that started first can finish afterwards and write a new-rule `show.json` or package over a restored show. The show is then legacy overrides plus new-rule numbering, the state finding 5 shows v2.17.0 mis-points on.
  - Between restore and reinstalling v2.17.0, the new binary's sweep turns every legacy show's run into a `needs attention` (`other`) failure.
- **Evidence:** `--apply` takes `locks.file_lock(ws.lock)` per show, and `--restore` does not. The runbook restarts the loop at step 7, before any restore could happen.
- **Failure scenario:** a restore during normal operation with the loop running. A resume's gather of show S is under way when restore reaches S, and the gather's `show.json` lands after restore's copy.
- **Suggested fix:**
  - Restore takes each show's lock while restoring it.
  - Add a restore runbook: stop the sweep loop, `pgrep` check, restore, reinstall v2.17.0, then restart the loop.
  - `--snapshot` takes show locks too (finding 1).

### 7. [Minor] An e37f670 harness arm does not "fail loudly" on migrated files
- **Where:** 4.1 "An old binary, a sweep loop or an old-commit harness arm therefore fails loudly".
- **Problem:** `replay_show` catches the `ValidationError` and records `unreplayable: overrides.json unreadable`. `run` still exits 0, and `compare`'s repro gate counts only held, non-needs-LLM rows, so it may pass. This is not a silent override drop, but the claim is wrong, and an arm with 606 unreplayable rows looks like data.
- **Evidence:** `replay.py:505-555`; `replay_holds.py` `_targets` docstring ("not via `catalog.iter_shows`").
- **Failure scenario:** an operator re-runs the base after the migration "to be sure" and compares.
- **Suggested fix:** correct the sentence. Have the branch's `compare` refuse an arm with any `overrides.json unreadable` row. Say that the base arm runs only before the migration.

### 8. [Minor] The version gate's threshold, and the script's code identity, are unspecified
- **Where:** 4.3 `--apply` gate "at least the version this branch ships"; "run from the repo as `/Users/shawn/projects/llama/.venv/bin/python scripts/rekey_overrides.py` (branch code)".
- **Problem:**
  - Branch code reports `0.1.0` (pyproject) or `0.0.0+unknown`, and the release version is stamped only at release. If the gate reads `llama.__version__`, v2.17.0 passes it.
  - The root venv imports the main checkout, not a worktree, so "branch code" holds only if the main checkout is at the release commit.
- **Suggested fix:** keep a `MIN_LLAMA` constant in the script, set when the release is cut. Make the script refuse unless `llama.__file__` is inside its own tree and that tree is clean at the tag of that version (as `replay_holds._check_identity` does).

### 9. [Minor] "No llama process is running" cannot see everything it needs to
- **Where:** 4.3 gates for `--snapshot`, `--apply` and `--restore`; runbook step 1.
- **Problem:**
  - `pgrep -x llama` misses a `.venv/bin/llama` run (its process name is Python) and a sleeping sweep loop.
  - The PATH gate checks only the script's own PATH, not that of the shell running the loop or of a launchd job.
- **Suggested fix:** also match `pgrep -f '(^|/)llama( |$)'`. Rely on show locks for the real exclusion (findings 1 and 6). Have runbook step 1 name the loop's process.

### 10. [Minor] Gaps in the refusal table's routes
- **Where:** 4.3 checks table.
- **Problems:**
  - A title key `<= -1` cannot be typed into v2.17.0 `--clear-title` (`isdigit`), so the route should be a hand edit.
  - Non-canonical keys that collapse on parse (`"7"` and `"07"`): the "exactly the forced title" check fails for the shadowed key forever. Define the checks over v2.17.0's parsed model (last wins), or refuse as "duplicate key: hand edit".
  - `redo --from gather` fails with no `provenance.json` (`reprocess it via its run first`) or on a darked item, and no fallback is given. Use `fix --clear-*` (works without `show.json`) or `rm --forget`.
  - "then set them again" should read "set corrected values". `--set-breaks` replaces the list on its own, and each v2.17.0 `fix` auto-redoes and spends a vet and a brief, so combine the edits in one invocation.

### 11. [Minor] Restore leaves reapply batch state, so re-running a list silently skips shows
- **Where:** 4.3 `--restore` ("discards every … apply made since").
- **Problem:** `<root>/reapply/<sha256(list)[:16]>/progress.jsonl` survives a restore. Restore and re-migrate with the same code: the files are byte-identical, so the `input_digests` match and the regenerated list's bytes are identical. The batch resumes and skips every committed row, so those shows silently stay on today's filter. The ledger, `runs/` and the cache are not reverted either, and the spec does not say so.
- **Suggested fix:** restore moves aside, and lists, the `reapply/` batch directories created after the snapshot. State what restore does not revert.

### 12. [Minor] Restore does not list station copies re-delivered since the snapshot
- **Where:** 4.3 "Restore does not touch the station".
- **Problem:** the operator cannot tell which station copies carry new-rule packages. That includes the 37 re-voiced with `--replace-voiced`, and re-delivering those from the restored library would need `--replace-voiced` again (strict surface (b)).
- **Suggested fix:** restore prints every show whose station manifest differs from the restored library manifest, marking voiced destinations. It says that re-delivering a voiced one is a section-5(b) decision.

### 13. [Minor] The legacy-value examples diverge from the rule they illustrate
- **Where:** 4.1 "a string that `int()` parses after stripping whitespace".
- **Problem:** pydantic accepts `"7.0"`, which Python's `int()` rejects, and `true`. An implementation written from the example (`int(s.strip())`) misclassifies `"7.0"` as a filename. That case is loud (a dangling key), but it is avoidable.
- **Suggested fix:** require the test to be `TypeAdapter(int).validate_python` in lax mode, or the vendored v2.17.0 model. Add `"7.0"` and `true` to the pinned cases.

### 14. [Minor] Rule-changed shows outside the bulk apply cannot take positional edits
- **Where:** 4.2 "Until a show is re-gathered under the new rule … refuses positional edits"; 5.2 "The 28 voiced-minor shows … are left out".
- **Problem:** for the 28 voiced-minor shows, and any rule-changed show the apply skips, the only route is `redo --from gather`. That spends a vet and a brief and makes the library diverge from the voiced station copy, against the re-voice-later decision.
- **Suggested fix:** state it as an accepted limitation, or let the reapply-path re-gather (no LLM) be the named route.

### 15. [Minor] Step 7 restarts the sweep before step 8's harness self-check
- **Where:** 4.3 runbook, steps 7-8.
- **Problem:** sweep resumes that gather or brief under the new rule change stored artifacts. They then differ from the pre-migration candidate and stop the apply ("Any difference stops the apply"), or change `input_digests`.
- **Suggested fix:** restart the loop after the post-migration harness re-run, or after the bulk apply.

TOTAL: 15 findings (0 Critical, 6 Important, 9 Minor)

Verdict: not yet ready for a plan. The normal path (scenarios 1, 5, 7, 8) holds, and nothing on it silently re-points an override. But the one rollback has three silent-wrong cases (findings 4, 5, 6) and is never verified before the point of no return (finding 1). Refusals found at `--apply` time route in a circle (finding 2), and the end-to-end check is blind to 792 structure keys (finding 3). One more revision round should close all six.
