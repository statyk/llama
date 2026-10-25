Foundation: SOUND -- the strict-surface premises I could check hold on the library (606 shows carry legacy keys, all have show.json and none has a .txn/; all 37 approved shows and all 28 minor ones are voiced at the station right now; no URL or @handle among the short-only drops). The defects below are gaps in the design, and each can be fixed inside it.

- **[Critical] The installed v2.17.0 binary silently ignores the migrated keys, and erases them on any edit**
  - Where: 4.3 "When. Once, after the new code is installed and before the first gather under it. The guard in 4.1 enforces the order."
  - Problem: the guard exists only in the new code. The old binary's `Overrides` is a plain permissive `BaseModel`, so it parses a migrated `overrides.json` by dropping `titles_by_file`/`breaks_after`/`encore_after_file` without a word. Its `_edit_overrides` then writes the model back out, which deletes the new keys from disk for good. The spec never discusses version skew or a rollback binary.
  - Evidence: `~/.local/bin/llama --version` prints `2.17.0` (the operator's PATH binary is the signed release; the migration script runs from the repo venv). models.py:204-217 (`class Overrides(BaseModel)`, no `extra=`, so pydantic v2's default `ignore`). workspace.py:59-62 `read_overrides`. cli.py:1398-1444 `_edit_overrides` reads the model, `model_copy`s it and `write_artifact`s it, so only known fields survive. Undo (4.3) says it "needs the old code to be useful", so the rollback path itself puts the old binary in front of migrated files.
  - Failure scenario: the migration runs from the venv before v2.18 is installed in `~/.local/bin`, or the operator rolls back to v2.17.0 and some undos refuse (any show edited or re-gathered since). Then `llama fix <show> --exclude 7`, `--set-venue`, `--narration vague` or a triage edit under 2.17.0 rewrites `overrides.json` with every filename-keyed title, break and encore gone. Its auto-redo gathers without them, and the show ships its tag titles and aligned structure: no flag, no error. A plain `llama redo --from gather` or `reapply` under 2.17.0 does the same without erasing the file. Up to 606 shows' hand-authored overrides (3,203 titles) are exposed, which is the spec's own worst case.
  - Setup and likelihood: plausible. One machine, but two llama builds sit on it (release binary on PATH, editable venv for scripts). The order "install the release, then migrate" is stated, not enforced against the old build.
  - Suggested fix: make migrated files unreadable to 2.17.0. For example, the migration writes a legacy key with an invalid type (`"set_breaks": "rekeyed-by-filename"`, which fails 2.17.0's `list[int] | None`), and the new model accepts and ignores that sentinel. Every old-binary read then fails loudly. Also have the script refuse unless `llama --version` on PATH is the new version. Adds one sentinel field, one test and one version check.

- **[Important] Undo compares against a recomputation that depends on show.json, which every new-code gather rewrites**
  - Where: 4.3 Undo, "only when the current file is byte-identical to what the migration writes from that backup. That output is deterministic."
  - Problem: the migration's output is a function of the backup *and* of `show.json` (position N maps to `tracks[N-1].filename`, and the refusal checks read `title_source`). Once the new code re-gathers a show, `show.json` has the `short_kept` tracks inserted. The recomputed mapping then differs, or the refusal checks fail, so undo refuses. That is every one of the 1,534 changed shows after the bulk apply, which are exactly the shows a rollback is for. Also, an undo that does succeed leaves legacy numbers sitting beside a new-numbering `show.json`. Until a 2.17.0 re-gather, `show --tracks` and 2.17.0's `fix --set-title N` number against the wrong list.
  - Evidence: 4.3 step 2 "Map each position to `tracks[N-1].filename`"; 4.1 says gather writes the inserted tracks into `show.json`.
  - Failure scenario: bulk apply, then a defect is found, then `rekey_overrides.py --undo --apply` refuses roughly 1,534 shows as "operator edit came after the migration". Those shows then fall under the Critical above when the operator goes back to 2.17.0.
  - Setup and likelihood: certain on any rollback after the bulk apply. Undo is the only rollback the spec names.
  - Suggested fix: at migration time, record the exact bytes written (`overrides.rekeyed.json`, or its sha256 next to the backup), and have undo compare against that record instead of recomputing. State undo's post-condition: run `llama redo <show> --from gather` under the old binary. Adds one sidecar file.

- **[Important] Explicit `set_breaks: []` (a forced no-breaks structure) has no defined encoding in the new keys**
  - Where: 4.1 "`breaks_after: [filename]`", and the guard's and migration's "non-empty legacy key".
  - Problem: today `set_breaks is not None` (an empty list included) sends gather down the structure-override path: alignment is skipped and there is one set. The new fields don't say whether `breaks_after` keeps the None/[] distinction. Both the guard and the migration key on *non-empty*, so an empty list can slip through both.
  - Evidence: gather.py:1658 `if overrides.set_breaks is not None or overrides.encore_after is not None:`. The library has `delmccouryband-2008-05-24/overrides.json`, with `"set_breaks": []`, 18 titles, and show.json `structure.alignment == "override"`. CLAUDE.md says `--untitled` writes `set_breaks=[]`.
  - Failure scenario: the plan models `breaks_after: list[str] = []`, like `exclude`. The migration maps `[]` to `[]`, which reads as "no override". Delmccoury's next gather runs alignment and may ship set breaks the operator ruled out, with no flag. Every future `--untitled` loses its `set_breaks=[]` the same way.
  - Setup and likelihood: 1 show today, plus every `--untitled`. Likely unless the plan happens to pick `None`.
  - Suggested fix: specify `breaks_after: list[str] | None = None`, with `[]` meaning forced no breaks. The migration copies None/[] exactly, and the guard tests "legacy key not at its default" rather than "non-empty". A test pins delmccoury's shape. One sentence and one test.

- **[Important] A refused show has no supported way out**
  - Where: 4.1 guard (gather, `fix` and triage all refuse a legacy show) and 4.3 refusals ("`show.json` is missing", and so on).
  - Problem: a refused show keeps its legacy keys. New-code gather, `fix` and triage then refuse it, and the migration refuses it again, so the only exits are hand-editing `overrides.json` (which the project rule forbids) or the old binary. The spec names neither. The ordinary repair for a half-done show, `llama redo <show> --from gather`, is exactly what the guard blocks.
  - Evidence: CLAUDE.md, fix/redo: a stale `.txn/` "is deleted, never restored", and `llama redo <show> --from gather` "is also the repair for any show left part-way". workspace.py:93-102: redo from gather deletes `show.json` first.
  - Failure scenario: between today and the bulk apply, a `fix --set-title` auto-redo is SIGKILLed after `drop_stage_artifacts`. The show has legacy keys and no show.json, and the migration prints `refused: <slug>: show.json is missing`. Every new-code command refuses it, and the operator is stuck or hand-edits. Today the count is 0 (I verified: all 606 have show.json, none has a .txn/), but the state can arise at any time before the apply.
  - Setup and likelihood: rare, and loud.
  - Suggested fix: document the route. Keep v2.17.0 available until the migration exits 0. A refused show is repaired with 2.17.0's `llama redo <show> --from gather`, then the migration is re-run (with the sentinel above, this applies only to files not yet migrated). A few lines; no new mechanism.

- **[Important] Scope of the 37 voiced re-deliveries is not enforced, and voicing can be discarded with no gain shipped**
  - Where: 5.3 "The 37 voiced shows where the rule restores music are approved for `deliver --replace-voiced`... The voiced shows whose gain is minor... are not re-delivered."
  - Problem: the spec doesn't say how `--replace-voiced` is confined to those 37. `deliver` has no name-list selector. Its batch selectors (`--state`, `--packaged`, `--artist`, `--run`, `--profile`) combined with `--replace-voiced` replace every voiced destination in the selection. The spec also sets no precondition that the re-packaged library manifest actually contains the restored files before the irreversible discard.
  - Evidence: cli.py:2455-2470 (only single-name or selector forms), cli.py:2430-2440 (`_deliver_batch` replaces every voiced destination when `replace_voiced`). 5.3: "A minor show may be re-gathered in the library", so the 28 minor shows can become `packaged` with a changed package.
  - Failure scenario: the bulk-apply plan uses `llama deliver --state delivered --replace-voiced --yes`, or a `--profile` batch, to handle the 37 together with re-delivered unvoiced shows. The 28 minor shows (re-gathered in the library), and any show emcee voiced since the list was cut, lose paid voicing. Or a severe show's re-gather comes out without the restored file (the protection drops it, a format flip, a different selection), and its voicing is discarded for an identical package.
  - Setup and likelihood: depends on the separately planned bulk apply. This spec is where the constraint has to be written down.
  - Suggested fix: require `--replace-voiced` only as one named invocation per slug in `voiced-severe-final.json`, each preceded by a check that the destination is voiced and that the library manifest's `tracks` include every file the json lists for that slug, and never combined with a selector. Adds a short bulk-apply rule; optionally `deliver` itself refuses `--replace-voiced` with a selector.

- **[Minor] Backup lifecycle: non-atomic, never refreshed, never removed**
  - Where: 4.3 step 3 "Copy `overrides.json` to `overrides.pre-rekey.json`, only if no backup exists."
  - Problem: a kill mid-copy leaves a truncated backup that every re-run keeps. Migrate, then undo, then a 2.17.0 edit, then migrate again keeps the first, stale backup, so the second pre-migration state is never saved and undo then refuses that show. No fsync before the original is replaced (macOS, and purge already uses `F_FULLFSYNC` for this reason).
  - Evidence: 4.3 step 3. workspace.py:27-40 (`atomic_write_bytes` exists but has no fsync).
  - Failure scenario: as described. The worst case is a lost legacy original. The information mostly survives in the new keys plus show.json.
  - Setup and likelihood: rare.
  - Suggested fix: write the backup with `atomic_write_bytes` plus `F_FULLFSYNC` before replacing the original. A successful undo deletes the backup. A re-run that finds an existing backup refuses the show unless current equals the backup, or equals the recorded migration output. A few lines.

- **[Minor] The spam tripwire reads only the tag, and the convention arm is weaker than the spec implies**
  - Where: 2.1 "The filename-convention arm (the spam guard...)", 2.3 "AUTHOR'S CALL, a spam-shape tripwire. A tag containing a URL...", and 2.4 "filename stem, with leading digits and separators removed".
  - Problem: the convention arm compares only the filename prefix before the first digit (`_stem`). A spam clip named with the item's prefix (`gd73-06-10 @BYPIKENO.mp3` has stem `gd`) passes it. Today a short one is still dropped by the duration arm. Under the rule it is kept whenever its tag is non-junk, and spam tags lie: section 7's own canonical spam file is tagged `Morning Dew`. The filename-junk check strips only *leading* digits, so `gd73-06-10promo` is not caught either.
  - Evidence: junk.py:75-81 `_stem` ("Filename up to the first digit"); 7, "`FOLLOW-ME @BYPIKENO.mp3`, tagged `Morning Dew`".
  - Failure scenario: a convention-prefixed promo clip under the floor, tagged with a song title, is kept and aired. 0 measured cases.
  - Setup and likelihood: very low on this library. Strict surface (c), so reported.
  - Suggested fix: apply the spam-shape tripwire to the filename of every short candidate, tagged or not, word-bounded (`https?://`, `www\.`, `@\w{3,}`, `\bfollow\b`). Plain substring matching would hit the real files `bwww1996-12-31t01.mp3` and `…JohnFollowsHisFingers…`. One line plus tests.

- **[Minor] The junk verdict is on the file's own tag only; later rungs can name a kept short file as junk and ship it**
  - Where: 2.2 "Each ships 2b-demoted as `unresolved`, and so holds"; 2.3.
  - Problem: D, setlist-gap and sibling-format can give a kept short file a wholly junk title, and nothing re-checks it. In the arm_final replay, 2 added files ship that way.
  - Evidence: `~/.llama-harness/piece45/spec/arm_final.jsonl` against `arm_base.jsonl`. `thenewdeal-2005-09-17` `tnd2005-09-17d3t02.mp3`, with filename-residue tag, interior: titled `(crowd)` by `setlist-gap`, outcome `clean-changed`, no flags. `buckethead-2004-06-04` `d1t01`, a placeholder-tagged edge file: titled `Crowd Noise` by `desc-position`. The second also contradicts "and so holds" for placeholder-tagged edge files.
  - Failure scenario: a short crowd clip airs with the title "(crowd)". The same path could carry a non-performance description entry onto an untagged interior file of an FM tape; 0 measured.
  - Setup and likelihood: 2 of about 2,643 added files, both crowd.
  - Suggested fix: record it as an accepted limitation, or add an operator note in `notes.json` when a `short_kept` track's final title is wholly junk under `short_tag_is_junk`. No new hold class needed.

- **[Minor] Apply lists predicted before the migration go stale**
  - Where: 5.1 "The replay harness applies the same re-key to its scratch copy when it meets legacy keys."
  - Problem: `input_digests` includes `overrides.json`. A predicted list built before the migration (which the scratch re-key invites) skips every overrides-bearing row once the migration rewrites those files.
  - Evidence: replay.py:89-104 (`"overrides.json": of(ws.overrides)`).
  - Failure scenario: about 606 rows come back `skipped` (input changed). Loud and recoverable by re-running the harness.
  - Suggested fix: state that apply lists come from a harness run after the migration; the scratch re-key is for measurement only. One sentence.

- **[Minor] The protection's second `filter_files` call: include and override interplay unspecified**
  - Where: 2.4 "calls `filter_files` again with a keyword (`keep_untagged_short=False`) and re-applies the operator exclusion."
  - Problem: the spec names exclusion but not `readmit=overrides.include`. It also doesn't say whether an operator-included untagged short file counts among "the tape's untagged short candidates". If the second call drops one that carries a `titles_by_file` key, the resolver raises (loud). If `readmit` were omitted, an operator re-admission would be silently undone.
  - Evidence: gather.py:1069 (the first call passes `readmit=frozenset(overrides.include)`).
  - Suggested fix: say the second call passes the same `readmit`, and that operator-included files are never protection candidates. One sentence and one test.

### Unverified premises
- The old binary is not run against the library after the migration. Cheapest test: none possible; it has to be enforced (sentinel plus version check, finding 1).
- The plan's `breaks_after` keeps None distinct from []. Test: a fixture of delmccouryband-2008-05-24's overrides run through migrate, then gather, and assert `structure.alignment == "override"` and `set_breaks == []`.
- "All 606 pass every check" still holds on migration day. Test: rerun `~/.llama-harness/piece45/spec/m4_migrate.py` immediately before `--apply` (it is read-only). I confirmed today: 606 shows, 0 without show.json, 0 with `.txn/`.
- Each of the 37 packages actually contains its restored files after re-processing. Test: before each `--replace-voiced`, diff the library manifest's track filenames against `voiced-severe-final.json`'s `files`.
- No short convention-matching spam exists in the sibling and cached items either. Test: run the word-bounded filename tripwire over the census dump's 9,844 sibling items' short drops (as premise 3 does for tags).

TOTAL: 10 findings (1 Critical, 5 Important, 4 Minor)
