Foundation: SOUND -- the premises still hold, and the round-1 fixes are mostly right. The new loud-failure encoding has a library-wide blast radius that breaks the spec's own repair and undo routes.

- **[Important] An old binary fails on every show once any one file is migrated, which breaks the refusal repair route and undo's post-condition**
  - Where: 4.3 "A refused show is repaired with the old binary: `llama-2.17.0 redo <show> --from gather`, then re-run the migration."; Undo "Its post-condition is the old binary's `llama-2.17.0 redo <show> --from gather`"; 4.1 "Old binaries fail loudly"
  - Problem: v2.17 reads every show's `overrides.json` just to resolve one name. `resolve_show` → `iter_shows` → `read_overrides` runs for every show dir, so the loud failure is library-wide, not per show. As soon as `--apply` has migrated any show, `llama-2.17.0 redo <refused-show>` dies with a `ValidationError` before reaching the refused show. The same happens after a partial undo, where any show refused by undo stays migrated. The runbook nevertheless applies and repairs in the opposite order: apply, then repair.
  - Evidence: catalog.py:343-348 (`resolve_show` builds `iter_shows`), catalog.py:291-311 (`overrides=read_overrides(ws)` per show), and the r1 measurement that v2.17's model raises on filename values. This holds even for a path argument, since `resolve_show` still calls `iter_shows`.
  - Failure scenario: on migration day, one show is refused, say a metadata cache refresh moved its kept list. The other 605 are applied, and the operator follows the printed route. `llama-2.17.0 redo X --from gather` gives a traceback, and the refused show has no supported path except a hand edit. In a rollback, undo restores 600 shows and refuses 6 that the operator edited after the migration. The old binary is then unusable everywhere.
  - Setup and likelihood: 0 refusals were measured today, but the spec says to re-run the checks on migration day, which is exactly when a refusal would appear. A rollback with any post-migration edit always hits this.
  - Suggested fix: make `--apply` all-or-nothing. It refuses to write anything while a dry run would refuse any show, and the runbook repairs refusals with `llama-2.17.0` before step 5's `--apply`, while the library is still all-legacy. Make `--undo --apply` all-or-nothing in the same way, and state that the old binary cannot run any command while any file is migrated. Cost: a pre-pass and two sentences.

- **[Important] The new model's types are unspecified; typed naively, the NEW binary also crashes library-wide on legacy files**
  - Where: 4.1 "One resolver ... It refuses with `LlamaError`, naming the show: a file with any legacy value ..."; the encoding table
  - Problem: the per-show `LlamaError` only exists if the new `Overrides` model parses both forms. An implementer who types the new fields as the table shows (`set_breaks: list[str] | None`, `encore_after: str | None`) gets a `ValidationError`, because pydantic v2 does not coerce int to str. That error then fires inside `iter_shows` for every command: from runbook step 3 (new release installed) until step 5 (migration), and forever for any refused show. That is the round-1 skew failure in the other direction.
  - Evidence: catalog.py:310 (every listing and resolution parses every `overrides.json`); spec 4.1 gives value shapes but no model types.
  - Failure scenario: right after step 3, `llama status`, `fix` and `deliver` all crash on the 606 legacy files, and so does any later command if a refused show stays legacy.
  - Setup and likelihood: likely, because the table invites `str` types.
  - Suggested fix: specify `titles: dict[str, str]`, `set_breaks: list[int | str] | None` and `encore_after: int | str | None`. Parsing never refuses; only the resolver and the writers do. Add a test that the new `iter_shows` lists a library holding a legacy file. Cost: one line plus one test.

- **[Minor] An interrupted migration can leave a show migrated with no sidecar, which undo can never restore and a re-run never revisits**
  - Where: 4.3 "Write, in this order: 1. the backup ... 2. the new `overrides.json` ... 3. the sidecar"
  - Problem: a crash between steps 2 and 3 leaves a filename-valued file with no sidecar. A re-run skips it (no legacy keys). Undo finds no hash match and the file differs from the backup, so it refuses for good, and the backup has to be copied by hand.
  - Suggested fix: write the sidecar, which is the hash of the bytes about to be written, before the new `overrides.json`. If the crash lands between the two writes, the file is still legacy and equals the backup, so undo reports `already undone` and a re-run proceeds normally. Cost: reorder two steps.

- **[Minor] Writers on a legacy or mixed file are undefined; `--no-run` can persist a mixed file that the migration cannot read**
  - Where: 4.1 "a file mixing legacy and filename values" (resolver only); 4.2 has no writer rule for legacy files (round 1's "fix and triage refuse the same way before any prompt" is gone)
  - Problem: a new-binary `fix --set-title 7=X` on a legacy (for example refused) show adds a filename key next to integer keys. The auto-redo fails and rolls back, but `--no-run` "validates nothing", so the mixed file persists. 4.3's checks (`a titles key outside 1..len(tracks)`) are undefined on a filename key, so the migration crashes or mis-reports.
  - Suggested fix: writers refuse a legacy file up front ("run the migration"), and the migration refuses a mixed file by name. Cost: two sentences and one test.

- **[Minor] Station-copy reuse misdescribes the package step, and stale old-numbered library audio can be reused for a different track**
  - Where: 5.4 "The copy is taken into the library under the source name, and packaging then renames and re-tags it as usual."; "Before the re-gather rewrites `show.json`, the unit pairs ..."
  - Problem: `build_package` has no source-named step. It downloads straight to `packaged_filename(index, title)`, and it skips the download whenever that name already exists (package.py:47-52). Reapply and redo drop only `manifest.json` (workspace.py:99), so on the ~445 changed shows that still hold library audio (packaged, held, briefed), the old-numbered files stay in place. When a new track N has the same title as the old track N (adjacent duplicate titles like `Drums`/`Jam`/`Space`, or an inserted `Drums` before a `Drums`), the old track's audio is silently re-tagged under the new track. Only the 5 s duration flag catches it. Library read: 12 of the 848 shows with library audio have adjacent duplicate titles. The spec also doesn't say which commands ("the unit") capture the pre-regather mapping and hand it to `build_package`. And `ffprobe` would be a new runtime dependency of the signed `llama` binary, which uses mutagen's `read_duration` today.
  - Suggested fix: before re-packaging a show whose track list changed, move the old `package/audio/*` aside and feed it through the same index pairing used for the station copy. That removes the collision and also saves the downloads on the 311 packaged shows. Name the units (redo/fix/triage/reapply) and verify with `read_duration`. Cost: a few lines.

- **[Minor] Re-delivering renumbered unvoiced shows leaves the old-numbered audio in each station directory**
  - Where: 5.5 "Delivered unvoiced shows are re-delivered, minor fixes included"
  - Problem: the unvoiced path is `copytree(pkg, out, dirs_exist_ok=True)` (cli.py:2386-2387), which never deletes files. Every track after an insertion gets a new `NN - title` name, so each of the ~1,028 station dirs keeps the old copies next to the new ones. That roughly doubles them on the SMB share. They are harmless to emcee and transmitter, which read the manifest and `broadcast.m3u`, but the disk cost is unsized.
  - Suggested fix: re-deliver these through `_replace_destination` as well (it is wholesale and atomic), or size the growth in the bulk-apply plan. Cost: one line.

- **[Minor] The voiced pre-check reads source filenames out of a manifest that holds only packaged names**
  - Where: 5.5 "the re-packaged library manifest's tracks include every restored file listed for that slug"
  - Problem: `ManifestTrack.filename` is the packaged name (`01 - Morning Dew.mp3`, models.py:271). `voiced-severe-final.json` lists source filenames, so the check as written can never pass.
  - Suggested fix: check the re-packaged `show.json` track filenames, or `short_kept`, and confirm the manifest exists. Cost: wording.

- **[Minor] `_destination_is_voiced` raising would abort a whole `deliver` batch**
  - Where: 5.5 "Any other read error, or a malformed manifest, refuses the show."
  - Problem: `_deliver_batch` calls it inside a list comprehension before the confirmation (cli.py:2428). If it now raises, one bad destination aborts the whole unvoiced batch rather than refusing that one show.
  - Suggested fix: specify per-show handling in the batch preflight (mark the show refused and continue), with a test. Cost: one sentence.

- **[Minor] Briefing reuse is ambiguous for operator-included short files**
  - Where: 5.3 "per-track `(title, set, segue)` over the tracks that are not `short_kept`, matched by filename"
  - Problem: the 173 already-included short files sit in the stored show and are `short_kept` in the new one. If only the new side is filtered, every such show needs a fresh brief it does not need. The cost is a brief, not safety.
  - Suggested fix: filter both sides by the new show's `short_kept` filenames.

- **[Minor] The script's version gate has no defined reference**
  - Where: 4.3 runbook step 3 "The script refuses `--apply` unless every `llama` on PATH reports the new version."
  - Problem: "the new version" is not defined. The script runs from the repo venv, which can be ahead of the release or `-dirty`.
  - Suggested fix: compare against the venv's own `llama.__version__`, and refuse a dirty or mismatched tree. Cost: one sentence.

### Unverified premises
- Most delivered station files pass the 1 s duration check against archive metadata lengths, which are VBR estimates; the package step itself tolerates 5 s. Cheapest test: run the check over 20 delivered shows and count the fallbacks.
- The tripwire is checked against a short kept song whose own title is `Follow…`/`Download` (`I Will Follow`), which would drop. 0 such files exist today, and dropping reproduces today's behaviour. Cheapest test: none needed beyond the corpus test.

TOTAL: 10 findings (0 Critical, 2 Important, 8 Minor)
