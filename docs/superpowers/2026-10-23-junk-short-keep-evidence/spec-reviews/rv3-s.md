# rv3-s: strict-surface review of section 4 (spec-r3-frozen.md)

Reviewer: Opus. Read: the frozen spec (all of it; section 4 judged), CLAUDE.md, code at e37f670 (models.py `Overrides`/`Show`/`Track`, workspace.py, catalog.py `iter_shows`/`resolve_show`, cli.py `_resolve_exclude_tokens`/reapply loop, stages/gather.py override handling, replay.py `replay_show`/`input_digests`, scripts/replay_holds.py `_gates`/`compare`), `~/.local/bin/llama --version`/`fix --help`. Pydantic behaviour was checked by running e37f670's `Overrides` and the spec's new field types against scratch JSON (`rv3-s-scratch/t.py`).

Verified facts I rely on below:
- e37f670 `Overrides` raises `ValidationError` on filename keys in `titles`, `set_breaks` or `encore_after` (confirmed). The message names the model and the field only, never the show or file path. cli.py has no `ValidationError` handler outside reapply's per-row loop.
- e37f670 `Overrides` silently drops an unknown key (`{"titles": {"1": "X"}, "note": "keep me"}` parses to titles only). It also lax-parses `" 1"`, `"1.0"` and `"1_0"` (as 1, 1 and 10) as `titles` keys, `["3"]` and `[2.0]` as `set_breaks`.
- `iter_shows` is called only by `resolve_show` users plus batch deliver/redo/rm, triage, status and `_by_run_rollup`. `get`, `run resume [--all]`, `run list` (apart from `--by-run`), `pacing` and `reapply --from-list` (built per row, by design) never call it.
- `replay_show` reads overrides before `input_digests`, so an e37f670 arm on a migrated show records it `unreplayable` with empty digests. `compare._gates` then refuses with `digests differ`. Apply lists come from the candidate alone (`outcome in CLEARING`).
- Gather's override path ships `show.json.set_breaks = sorted(set(breaks) | {encore_after})` and sets a forced title exactly (`title_source="override"`). `_validate_structure_override` raises on out-of-range breaks or encore, and on an encore at or before `max(breaks)`.
- `~/.local/bin/llama` is a single-file Mach-O binary (2.17.0), so a renamed copy works. The repo venv's `llama` reports `0.1.0`.

## Scenarios

**1. Normal run. PASS.** 4.3: "`--apply` is all-or-nothing. It first runs every check over every show with a legacy value". Then the per-show map, backup, sidecar and rename. 4.1's "One resolver" maps the filename keys onto the new kept list. Measured: "All 606 pass every check", and the harness re-key gave "0 override titles on a different file". This depends on I2 (the raw-JSON round trip) being specified.

**2. Dry run refuses k shows; repair with the old binary. PASS with gaps.** Each table row's route works on a wholly legacy library:
- a missing `show.json` and a stale `show.json` take an old `redo`;
- an out-of-range title takes `--clear-title`;
- a stale backup is moved aside.

The gaps:
- Out-of-range `set_breaks`/`encore_after` reach only the "redo" route, and that redo fails (M3).
- A mixed file breaks the old binary for the whole library, so it must be repaired first, and by hand (M5).
- A filename-valued file written by the new binary between steps 3 and 5 makes every old-binary route unusable (I7).

**3. Interrupts inside and between shows. PASS for the per-show sequence; FAIL for one recovery path.**
- **Inside a show:** backup, sidecar, then rename. After the backup only, the file is legacy and equal to its backup, which the backup rule accepts. After the sidecar, the file is legacy and equal to its backup, which undo treats as `already undone`. After the rename, the show is migrated and a re-run skips it. So "either legacy and equal to its backup, or matching its sidecar" holds for SIGKILL and Ctrl-C. Power loss is not covered (M7).
- **Between shows:** a re-run of `--apply`, `--undo`, the old binary (loud) and the new binary (loud on the legacy rest) all work. The exception is a re-run in which any remaining legacy show newly fails a check. The run then writes nothing, and every repair route names `llama-2.17.0`, which cannot run on a partly migrated library. The way out is not documented (I3).

**4. Undo. Partial FAIL.**
- All shows undoable: PASS. One show not undoable: PASS (named, nothing written).
- The documented escape for that show ("move that show's backup over `overrides.json`... undo then reports it `already undone`") does not work. With the backup moved, the "equals the backup" arm cannot match, so the show stays not undoable (I4).
- Interrupted mid-undo: the order of the sidecar and backup removals is unspecified. Removing the backup first leaves a sidecar with no backup, which reports as "edited after the migration" and blocks the next undo (I4).
- Run twice: PASS (the undo set is empty).
- After undo:
  - The old binary's positional edits against a re-gathered `show.json` can silently mis-point (I5).
  - Filename-valued files that carry no sidecar still break the old binary (I6).

**5. Version skew. PASS on the core property** (no silent loss in either direction), with inaccurate prose.
- **v2.17.0 on a migrated or partly migrated library:** every `iter_shows` command raises. `get`, `run resume`, the sweep, `pacing` and `reapply --from-list` keep running. They fail per show only where gather, brief or reapply reads a migrated file; package does not read it (M1).
- **The new binary on a legacy, partly migrated or mixed library:** "Both forms always parse" plus the `iter_shows` test cover reads. "Writers refuse legacy... (`--no-run` included)" covers writes, and the resolver refuses gather. The error text that v2.17.0 prints names no show (M1).

**6. Writer edits on a legacy file before the migration. PASS, except while `--apply` is running.**
- **Old binary:** an edit plus its auto-redo keeps `show.json` consistent. A `--no-run` edit is caught by the override-title, set-break or filename-list check, with a redo route. An edit between the dry run and `--apply` is caught by `--apply`'s re-check.
- **New binary:** refuses before any prompt.
- **During `--apply`:** the gap between the check and the write under the lock can silently discard an old-binary edit (I1).

**7. Writer edits after the migration. PASS.**
- Numbers translate through `show.json`. The staleness check refuses positional edits until the show is re-gathered, and `--clear-*` skips it.
- `--exclude N` of a keyed file refuses up front. The filename form is not stated (M8).
- `--untitled` and triage `[u]`/`[t]` are covered by the same staleness rule.
- Residual: with no `show.json`, the `--clear-*` flags refuse, so a dangling key cannot be cleared without a hand edit (M2).

**8. `set_breaks: []`, `titles: {}`, encore-only. PASS.**
- "An empty `set_breaks: []` needs no re-key and is left as is."
- The check is `sorted(set_breaks ∪ {encore_after})`, which matches gather's `sorted(set(breaks_in) | {encore})`. Encore-only gives `[encore]`.
- Undo restores the exact bytes, and the `delmccouryband` test is pinned.
- A file whose only content is `[]` or `{}` is not legacy, so it gets no sidecar and no backup, which is correct.

**9. Harness and replay. FAIL in one place.**
- Base arm before the migration: PASS (step 4).
- Base arm at e37f670 after the migration: loud (606 rows unreplayable, empty digests, and `compare` refuses `digests differ`). PASS as "fails loudly".
- Apply lists from before the migration: refused whole (the code-identity `sha`) or skipped per row (the `overrides.json` digest). PASS.
- Reapply on a migrated library goes through the resolver. PASS.
- Step 7 ("Build apply lists only from a harness run after the migration") names no base arm that can pass `compare`'s gates. An e37f670 base cannot, and a snapshot base differs in digests. Step 4 also says nothing about where the candidate arm of 6(a) must run (I8).

**10. Two writers at once. FAIL.**
- Taking the show lock per show is right.
- The checks are not re-run on the bytes read under the lock, and the source of the backup bytes is not stated (I1).
- The sweep: steps 1 and 6. PASS.
- Concurrent `--apply` runs: no migration-wide lock (folded into I1).

**11. Metadata-cache refresh. PASS.**
- **Before `--apply`:** its full re-check catches the change (filename-list row, redo route).
- **After the migration:** a dangling key fails gather loudly, and `--clear-*` skips the staleness check. Two residuals:
  - the resolver names one key, so clearing the keys one at a time rolls back on the next dangling key (M2);
  - the no-`show.json` case (M2).

**12. The version gate. PASS with gaps.**
- An old `llama`, a dev build (`0.1.0`), or several `llama` entries (each checked through `which -a`) are refused.
- `--undo` is exempt, which is correct.
- Not covered:
  - no `llama` on PATH passes trivially;
  - the gate is "> 2.17.0", not "has the resolver";
  - an old `llama` process that is already running is invisible (M6).

## Findings

- **[Important] I1. `--apply` checks every show, then writes under each show's lock without re-checking.**
  - Where: 4.3, "`--apply` is all-or-nothing... Otherwise, per show, under the show lock... 1. Map... 2. Write".
  - Problem: the all-show check runs unlocked, before any write. The per-show step takes the lock, but the spec never says it re-reads `overrides.json` and `show.json` under the lock, re-runs that show's checks on those bytes, and backs up exactly those bytes. There is also no migration-wide lock against a second `--apply`/`--undo`.
  - Evidence: old `fix`/triage hold the show lock for their whole unit, and `get`/`redo` hold it around `process_show`. `--apply` would block behind them and then act on its earlier reading.
  - Failure scenario: during `--apply` the operator runs `llama-2.17.0 fix X --set-title 7=Foo` (step 5 invites the old binary, and the gate checks only PATH names). Fix wins the lock, writes `{7: Foo}` and re-gathers. The migration then maps the overrides it read in the check pass, which lack track 7, and writes a backup and new file without it. Foo is silently lost, and the backup is not the pre-migration truth either.
  - Suggested fix: per show, under the lock, re-read both files, re-run that show's checks on the bytes just read, and back up exactly those bytes. If the show is now refused, stop the run and print the refusal and the "partial: re-run or undo" state (see I3). Take a migration-wide flock (e.g. `<root>/.rekey.lock`) for `--apply` and `--undo --apply`.

- **[Important] I2. "Every other field round-trips unchanged" is unsafe if done through the model.**
  - Where: 4.3 step 1.
  - Problem: `Overrides` is permissive and drops unknown keys silently. A migration that parses the file with the model and dumps it back deletes any key the model does not know (an older field, or an operator's note), with no message. The spec does not say the rewrite works on the raw JSON object.
  - Evidence: e37f670 `Overrides.model_validate_json('{"titles": {"1": "X"}, "note": "keep me"}')` parses to `{titles: {1: X}}`.
  - Failure scenario: a show whose file carries a key from an older llama, or a hand-added one, loses it on migration. Undo would restore it, but only inside the undo window.
  - Suggested fix: specify that the rewrite loads the file as a raw JSON object, replaces only the values of `titles`, `set_breaks` and `encore_after`, and keeps every other key and value exactly. Add a test with an unknown key, and have the migration report any key the model does not know.

- **[Important] I3. A re-run after a partial `--apply` can refuse, and then has no route.**
  - Where: 4.3, "A re-run of an interrupted `--apply` completes the remaining legacy shows, which passed the all-show check", and the repair table ("old binary, before `--apply`").
  - Problem: the re-run re-checks the remaining legacy shows. If one now fails (metadata refreshed, a new-binary write per I7, or a stale backup from a Ctrl-C during an earlier cycle), the run writes nothing. Every repair route names `llama-2.17.0`, which cannot run any `iter_shows` command once any show is migrated. The new binary refuses to write to legacy files. Nothing documents the way out.
  - Evidence: `resolve_show` goes through `iter_shows`, which reads every `overrides.json` with the old model. 4.1 says itself that "once any file is migrated the old binary cannot run any command on this library".
  - Failure scenario: Ctrl-C after 300 shows, a cache refresh of one remaining item, a re-run refuses it, and the operator is stuck in a half-migrated library.
  - Suggested fix: document the route: `--undo --apply` back to wholly legacy, repair with `llama-2.17.0`, then dry run and `--apply`. Alternatively, let the re-run's refusal of a remaining show be per-show, migrating the rest and leaving the refused show legacy, since the new binary is committed to at that point, and name a new-binary repair for it. Either way, the refusal text must say which applies.

- **[Important] I4. The manual-rollback escape and the undo's removal order break "already undone".**
  - Where: 4.3 Undo: "they move that show's backup over `overrides.json` by hand... undo then reports it `already undone`", and "removes the sidecar and the backup".
  - Problem: after `mv backup overrides.json`, no backup exists, so "when the current file equals the backup" cannot hold. The show falls into "otherwise... not undoable", which blocks the all-or-nothing undo for good. Separately, the order of removing the sidecar and the backup is unspecified. If the backup goes first and the run is interrupted, a sidecar is left with no backup, and the next undo misreports the show as "edited after the migration". The case of a hash that equals the sidecar while the backup is missing is also unspecified.
  - Failure scenario: the operator follows the spec's own escape for one edited show, re-runs `--undo --apply`, and it still refuses on the same show.
  - Suggested fix: say `cp`, not move. Better, give undo a `--accept-loss <slug>` style option that does the restore itself. Specify the removal order: rename the restore, then remove the sidecar, then the backup. Specify that a sidecar without a backup is "already undone" when the file is legacy, and "backup missing: not undoable" when the file matches the sidecar.

- **[Important] I5. After undo, an old-binary positional edit can silently mis-point.**
  - Where: 4.3, "Its post-condition is the old binary's `llama-2.17.0 redo <show> --from gather` for every show whose `show.json` has a `short_kept` track".
  - Problem: after undo, a show re-gathered under the new rule has legacy positions next to a new-rule `show.json`. `llama-2.17.0 show --tracks` prints the new numbering. `llama-2.17.0 fix --set-title 7=X` stores `{7: X}` and re-gathers under the old rule, where track 7 is a different file whenever a short-kept file sat before it. That is a silent re-point, the worst outcome named in the stakes. The spec states the redo only as a post-condition, with nothing to make it happen first.
  - Failure scenario: undo, reinstall 2.17.0, fix one held show from the triage list before running the redo sweep, and a title lands on the wrong file with no flag.
  - Suggested fix: make `--undo --apply` print the post-condition list and the exact `llama-2.17.0 redo` commands, and write a marker file (e.g. `<root>/rekey-undo-pending`). Say in the runbook that no positional `fix` or triage edit may happen until every listed redo has run. A stronger alternative: undo also removes `show.json` from each listed show. Today's `fix` still accepts `--set-*` without `show.json`, though, so that alone does not block the edit; the ordering rule is what matters. Also note that each redo spends a vet and a brief.

- **[Important] I6. Undo does not restore old-binary readability for files without a sidecar.**
  - Where: 4.3 Undo, "The undo set is every show with a sidecar", and 4.1's all-or-nothing rationale.
  - Problem: after the migration, the new binary writes filename keys into shows that had no positional keys before (no sidecar): any `--set-title`, `--set-breaks`, `--set-encore`, `--untitled` or triage `[t]`. Undo never sees these files. After undo and reinstalling 2.17.0, every `iter_shows` command raises a `ValidationError` that names no show.
  - Evidence: the undo set definition, and the pydantic message (`1 validation error for Overrides / titles.\`x.mp3\`.[key]`, no path).
  - Failure scenario: a week after the migration the operator undoes. Undo reports success, the old binary still cannot run, and the operator has to find the file by hand.
  - Suggested fix: the undo dry run and `--undo --apply` also scan every show for any filename value. They refuse and name each such show that has no sidecar, with the route (clear it with the new binary before reinstalling the old one, noting the values). Undo then really means "the old binary can read this library".

- **[Important] I7. Runbook steps 3 to 5 let the new binary break the old-binary repair routes.**
  - Where: 4.3 runbook, step 3 (install the new release) before step 5 ("Repair each refused show with `llama-2.17.0`... while the library is still wholly legacy"), and 4.1's "Writers refuse legacy".
  - Problem: new-binary writers refuse only legacy files. On a show with no positional keys whose kept list the rule does not change (passing the staleness check), a new-binary `fix --set-title 3=X` writes a filename key. From then on the library is not wholly legacy. `llama-2.17.0` fails on every `iter_shows` command with an error that names no show, and every step-5 repair is blocked.
  - Failure scenario: after step 3, the operator idly fixes a show with the new `llama`, then the dry run refuses one show and its old-binary repair crashes library-wide.
  - Suggested fix: either make every new-binary writer refuse while the library holds any legacy file (a library-level check: "the library is not yet migrated; run the migration"), or add a runbook rule that the new binary must not be used between steps 3 and 6. In both cases have the dry run list every file that already holds filename values, as a refusal ("filename value before migration: clear with the new binary").

- **[Important] I8. The harness steps are not executable as written.**
  - Where: 4.3 runbook steps 4 and 7; 6(a).
  - Problem:
    - An e37f670 base arm after the migration records every migrated show `unreplayable` with empty digests, so `compare` refuses with `digests differ`.
    - A base on a pre-migration snapshot differs in `overrides.json` digests from any post-migration candidate, so `compare` refuses again.
    - Step 7 therefore has no base that passes `compare`'s gates. The spec does not name one: a new-code base, and whether `--no-repro-gate` is needed.
    - The acceptance candidate of 6(a) ("with the harness re-key") must read the same library state as the base, but step 4 sets only where the base runs.
  - Evidence: `replay_show` (overrides read before `input_digests`, `_OverridesUnreadable` leading to `unreplayable`) and `replay_holds._gates` (`digests differ`).
  - Failure scenario: the operator runs the base on a snapshot, migrates, runs the candidate, and `compare` exits 2. Or step 7 cannot be run at all, which invites bypassing the gate.
  - Suggested fix:
    - Step 4: run both acceptance arms (base, and candidate with the re-key) before step 5, or on the same snapshot.
    - Step 7: name the post-migration list arm and its base, e.g. the branch's own arm as both base and candidate, with `--no-repro-gate`. Alternatively, have `compare` accept a legacy and migrated `overrides.json` pair as equal digests through the sidecar or backup hashes.

- **[Minor] M1. The claim that the failure is library-wide on every command is inaccurate, and the error names no show.**
  - Where: 4.1, "v2.17.0 reads every show's `overrides.json` on every command (`catalog.iter_shows`)" and "a sweep loop... fails loudly".
  - Problem:
    - `get`, `run resume` (and `--all`), `run list` (apart from `--by-run`), `pacing` and `reapply --from-list` do not call `iter_shows`. An old sweep on a migrated library keeps running and fails only per show, and only where gather, brief or reapply reads a migrated file. That is still loud and not silent, so the core property holds, but the stated rationale for all-or-nothing rests on a wrong premise.
    - cli.py has no handler for `ValidationError`, so the operator sees a traceback with no show path.
  - Suggested fix: correct the sentence, and keep the all-or-nothing rule on the true premise (`resolve_show`/`status`/`fix`/`triage`/`deliver`/`redo` are all blocked). Have the migration and undo print the slug of any file the old model cannot read.

- **[Minor] M2. A dangling key cannot always be cleared through `fix`.**
  - Where: 4.2, "Without `show.json` these flags refuse" (which includes `--clear-title`/`--clear-set-breaks`/`--clear-encore`), and "the operator clears the dangling key with `fix` and never hand-edits"; 4.1, "a filename value whose file is not in the final kept list (naming the key and the file)".
  - Problem:
    - A SIGKILLed `redo` can leave no `show.json` (the stale `.txn/` is deleted, not restored). Combined with a dangling key, gather refuses, and the clears refuse and name `redo --from gather`, which refuses: a loop that only a hand edit breaks. Today, CLAUDE.md lets `--clear-*` run without `show.json`.
    - The resolver names one key. With several dangling keys, each single clear's auto-redo fails on the next key and rolls back.
  - Suggested fix: the three `--clear-*` flags (with the filename form) work without `show.json`, and the resolver's refusal lists every dangling key with the single `fix` command that clears them all (or says to use `--no-run`).

- **[Minor] M3. The repair table has no route for out-of-range structure overrides.**
  - Where: the 4.3 table row "when `set_breaks` or `encore_after` is present...", route "`llama-2.17.0 redo <show> --from gather`".
  - Problem: when the mismatch exists because a break or encore is out of range, or the encore is at or before `max(breaks)` (for example after a `--no-run` edit or a metadata shrink), that redo raises `_validate_structure_override`'s `LlamaError`. The documented route then fails, which is inconsistent with "Every refusal has a route".
  - Suggested fix: add rows for out-of-range breaks or encore, and for an encore at or before `max(breaks)`, with `llama-2.17.0 fix <show> --clear-set-breaks` / `--clear-encore` (note the values first). Have the migration compute these checks itself rather than leaving them to the redo.

- **[Minor] M4. "Legacy" is defined more narrowly than the old model's reading.**
  - Where: 4.1, "a `titles` key made only of digits..., an integer in `set_breaks`, or an integer `encore_after`".
  - Problem: e37f670 reads `" 1"`, `"1.0"` and `"1_0"` as track numbers in `titles`, and `["3"]` and `[2.0]` in `set_breaks`. The spec classifies the string forms as filenames, so they are not migrated, and the new gather refuses them as dangling. A JSON float `2.0` is an "integer" only after parsing. This is loud, not silent, and only a hand edit produces it.
  - Suggested fix: define legacy as "a value e37f670's vendored model accepts as an int". Classify on the raw JSON. Refuse any non-canonical form (route: re-enter with `llama-2.17.0 fix`).

- **[Minor] M5. The mixed-file route is out of order and hard to act on.**
  - Where: the 4.3 table, mixed row, "undo that hand edit".
  - Problem: a mixed file holds a filename value, so `llama-2.17.0` cannot run any `iter_shows` command. Every other old-binary repair is blocked until this one is fixed, and the operator may not know what the hand edit was.
  - Suggested fix: say to repair it first, by hand. For each filename value, either delete it or replace it with its track number from `show.json`. Name the offending key or keys in the refusal.

- **[Minor] M6. The version gate has gaps.**
  - Where: 4.3 runbook step 3.
  - Problem:
    - No `llama` on PATH passes trivially.
    - "2.17.0 or earlier" would let a hypothetical 2.17.x hotfix without the resolver through. Loud afterwards, but avoidable.
    - A `llama` process already running from before the install (an open `triage`, a long `get`) is invisible to a PATH check. Old fix and triage do refuse "changed by another command" afterwards, but I1's window remains.
  - Suggested fix: require at least one `llama` on PATH, every one at or above the first piece-4 version. Refuse while `pgrep -x llama` finds a process, or tell the operator to check for one.

- **[Minor] M7. The write order is not durable across power loss.**
  - Where: 4.3, "each as a temp file, `F_FULLFSYNC`, then rename".
  - Problem: the renames are not made durable in order without an `F_FULLFSYNC` on the show directory after each rename. On power loss, the `overrides.json` rename could persist without the backup's. The scenario list covers SIGKILL and Ctrl-C, where order holds.
  - Suggested fix: run `F_FULLFSYNC` on the directory fd after each rename (the backup before the sidecar, before the new file), as the purge does for station files.

- **[Minor] M8. The scope of the exclusion refusal is ambiguous.**
  - Where: 4.2, "`fix --exclude N` (and triage exclusion) refuses when that file carries a title, break or encore key".
  - Problem: it does not say whether `--exclude <filename>` and `--no-run` are covered. Without that, `--no-run --exclude f.mp3` on a keyed file writes, and the next gather fails on a dangling key. That is loud, but avoidable.
  - Suggested fix: state that both forms, with or without `--no-run`, refuse.

- **[Minor] M9. Unreadable inputs are unspecified.**
  - Where: the 4.3 checks.
  - Problem: the spec does not say what the migration does with an `overrides.json` that is not valid JSON or fails both models, or with a legacy show whose `selection.json` (needed for the helper's format) is missing.
  - Suggested fix: add refusal rows for both. The routes are: an unreadable file is fixed by hand (the old binary is already blocked by it); a missing `selection.json` takes `llama-2.17.0 redo <show> --from gather`, or `rm`.

TOTAL: 17 findings (0 Critical, 8 Important, 9 Minor)

Verdict: not ready for a plan. The design (filename keys, the parse-both model, writers refusing legacy files, and the backup and sidecar rules) is sound. The undo and recovery paths (I3 to I6), the check-then-write gap (I1), the raw-JSON round trip (I2), the steps 3 to 5 window (I7) and the harness steps (I8) each need a short spec revision before planning. None is a Foundation problem.
