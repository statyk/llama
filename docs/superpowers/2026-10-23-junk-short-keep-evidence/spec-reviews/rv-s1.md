Foundation: SOUND -- the migration's consistency premise holds on the library (606 shows carry legacy keys, all are consistent under the harness's own `is not None` test, and none has an exclude/include, .txn or duplicate-filename complication today), and nothing contradicts the tag-based relaxation; the defects below concern how the change rolls out, not what it rests on.

- **[Critical] A v2.17.0 binary silently ignores the migrated keys, and erases them on its first write**
  - Where: 4.3 "When. Once, after the new code is installed and before the first gather under it. The guard in 4.1 enforces the order."
  - Problem: the guard lives only in the new code, so nothing stops the old binary. The old `Overrides` model drops unknown keys (pydantic default, no `extra="forbid"`). Old gather therefore ships tag titles and aligned structure with no override and no flag. Old `fix`/triage then rewrites the file from the old model, which deletes `titles_by_file`/`breaks_after`/`encore_after_file` for good.
  - Evidence: models.py:204-218 (`Overrides`, permissive, legacy fields only); cli.py:1391-1445 (`_edit_overrides`: `read_overrides`, then `write_artifact(show_ws.overrides, data)` with `data` a model copy); gather.py:1253, 1368, 1658 read only `titles`/`set_breaks`/`encore_after`. The operator's `llama` is the signed release binary: `~/.local/bin/llama --version` prints `2.17.0`. The migration is a repo script run from the venv.
  - Failure scenario: the branch merges, Shawn runs `scripts/rekey_overrides.py --apply` from the repo venv, and keeps using `llama triage`/`fix`/`redo` from `~/.local/bin` until the next release is cut. (A `while true; do llama run resume --all` loop gives the same result.) Every gather on the 606 shows drops the operator's titles and breaks silently. Any old-binary `fix` on one of them deletes its filename keys, and writes the new edit as a legacy key. Re-running the migration then maps only that one new key; the erased ones survive only in `overrides.pre-rekey.json`. Undo refuses, because the current file no longer matches.
  - Setup and likelihood: needs only the normal gap between merging and releasing, with the release binary on PATH. Likely.
  - Suggested fix: make old binaries fail loudly. Have the migration also write a sentinel that the old model cannot parse, e.g. `"titles": {"rekeyed": "needs llama >= 2.18"}` (a non-int key fails `dict[int, str]` validation), and have the new code accept and ignore it. In addition, have the migration refuse unless every `llama` on PATH reports the new version, and state in 4.3 that sweep loops are stopped first. Adds about 10 lines and one test.

- **[Important] The legacy guard and the "scratch re-key" have to sit where `reapply` cannot get around them**
  - Where: 4.1 "Gather refuses a show whose `overrides.json` still has a non-empty legacy key"; 5.1 "The replay harness applies the same re-key to its scratch copy when it meets legacy keys".
  - Problem: `llama reapply` (which piece 4 extends to packaged and delivered shows) runs gather through `replay.compute_legs`. That function is also where the harness's scratch copy of `overrides.json` is made, which is the obvious place to put the scratch re-key. Two ways this goes wrong:
    - The re-key goes into `compute_legs`: `reapply` writes a new-code `show.json` while the library file still has legacy keys. That breaks 4.1's premise that "the positions in a legacy file therefore always refer to the on-disk `show.json` written by the old code".
    - The guard goes into `run_gather` but not `compute_gather`: `reapply` reads only the new (empty) keys and silently drops every legacy override.
  - Evidence: replay.py:319-320 (`shutil.copyfile(ws.overrides, scratch / ...)`), then replay.py:327 `compute_gather(ShowWorkspace(scratch), ...)`; reapply.py:93 calls `compute_legs`.
  - Failure scenario: Shawn runs `llama reapply --from-list` on held shows before the migration. Their show.json is rewritten from re-keyed positions (case 1) or with no overrides at all (case 2). A later migration then refuses those shows, or maps against a `show.json` the old code never wrote.
  - Setup and likelihood: needs only an ordering slip during the bulk apply; the spec does not say where either piece lives.
  - Suggested fix: state that the guard sits in `compute_gather`/the resolver, which every path goes through, and that the scratch re-key lives only in `scripts/replay_holds.py` (or behind a harness-only argument that `reapply` never passes). Adds two sentences.

- **[Important] `set_breaks: []` ("force no breaks") falls through both the migration and the guard**
  - Where: 4.1 "a non-empty legacy key"; 4.3 "Per show with a non-empty legacy key"; 4.1 "`breaks_after: [filename]`".
  - Problem: `set_breaks == []` is a live override. It takes the override path and skips alignment. `fix --untitled` and triage `[u]` write it. The spec says "non-empty", which excludes it. The spec also does not say that `breaks_after` keeps the `None` vs `[]` distinction. A show whose only legacy key is `set_breaks: []` is therefore not migrated and not refused, and the new gather drops the override silently. A migrated show with `[]` may be written as "no key".
  - Evidence: gather.py:1658 (`overrides.set_breaks is not None or ...`); cli.py:1819 (`set_breaks=[]` in the `--untitled` writer); library: `delmccouryband-2008-05-24/overrides.json` has `"set_breaks": []` beside 18 titles. The harness's own m4_migrate.py tests `sb is None`, i.e. presence, so the spec's wording disagrees with the measurement it cites.
  - Failure scenario: after the migration, an `--untitled` show (or delmccoury) gathers with alignment back on. Sets and encores reappear on a tape the operator ruled has no knowable structure, with no error.
  - Setup and likelihood: 1 show today; every future `--untitled`/`[u]` writes one.
  - Suggested fix: define "legacy key present" as `titles != {} or set_breaks is not None or encore_after is not None`, both for the guard and for migration selection. Make `breaks_after: list[str] | None` with `[]` preserved, and add a test on the `--untitled` shape.

- **[Important] Undo cannot recompute "what the migration writes from that backup" once `show.json` has changed**
  - Where: 4.3 "restores ... only when the current file is byte-identical to what the migration writes from that backup. That output is deterministic."
  - Problem: the migration's output depends on `show.json` (positions map to `tracks[N-1].filename`), not only on the backup. Once the new code re-gathers a show, positions shift and the step-1 checks fail ("track at a titles key is not override"). So the expected bytes cannot be computed, and undo refuses or errors. Running undo a second time also refuses and exits 1, because the current file now equals the backup.
  - Evidence: 4.3 step 2 "Map each position to `tracks[N-1].filename`". 2.4 and 4: 204 shows have a positional key at or after an insertion, and these are exactly the shows the bulk apply re-gathers.
  - Failure scenario: after the bulk apply, Shawn decides to roll back to v2.17.0 and runs `--undo --apply`. Every show with an insertion before an override is refused or crashes. The legacy data then has to be restored by hand from about 200 `overrides.pre-rekey.json` files.
  - Setup and likelihood: needs a rollback after any new-code gather; when undo is actually used, that is the normal case.
  - Suggested fix: at migration time, record the sha256 of the bytes written (in a sidecar, e.g. `overrides.rekeyed.sha256`). Undo restores when the current file matches that hash, and reports "already undone" (exit 0) when the current file equals the backup. Adds about 15 lines.

- **[Important] Re-voice scope is a list in a document, not a check where the command runs**
  - Where: 5.3 "The 37 voiced shows where the rule restores music are approved for `deliver --replace-voiced` ... The voiced shows whose gain is minor ... are not re-delivered."
  - Problem: nothing at the point of action limits `--replace-voiced` to the 37:
    - `deliver` accepts `--replace-voiced` with batch selectors, and then discards every voiced destination in the selection after one confirmation.
    - emcee keeps voicing delivered shows until the bulk apply, so "delivered unvoiced" at list time is not "unvoiced" at deliver time.
    - The tools point the wrong way. Extended `reapply` prints `re-deliver with: llama deliver <name>` for every delivered show, the 28 minor voiced ones included. `deliver`'s refusal then says "pass --replace-voiced to replace it".
  - Evidence: cli.py:2415-2440 (`_deliver_batch` with `replace_voiced` marks all voiced destinations in `kept`); cli.py:2372-2376 (refusal text); CLAUDE.md reapply bullet ("a delivered show that cleared prints `re-deliver with: llama deliver <name>`").
  - Failure scenario: a bulk re-delivery such as `llama deliver --profile dead --replace-voiced --yes`, meant to cover the 37, also replaces any of the 28 minor shows in that profile, and any show emcee voiced since census2. Paid voicing is discarded with no way back.
  - Setup and likelihood: needs a batch command during a ~1,100-show re-delivery. Plausible.
  - Suggested fix: in section 5, require that `--replace-voiced` is used only by a per-slug loop over `voiced-severe-final.json`, that each slug is checked for membership first, and that it is never combined with a selector. A show voiced at apply time that is not on the list goes to the re-voice-later list, and reapply's re-deliver hint is suppressed for voiced destinations. Adds a paragraph and a one-line check.

- **[Important] Tagged short files never have their filename checked, and on 129 shows the convention arm only asks "does it start with a digit"**
  - Where: 2.1 "The filename-convention arm stays the spam guard and is not touched"; 2.3 "AUTHOR'S CALL, a spam-shape tripwire. A tag containing a URL ...".
  - Problem: `_stem` is the filename up to its first digit. On items whose files are named `01 Song.mp3` the dominant stem is `""`, so any digit-leading spam file passes the convention arm. Until now the short arm was the second barrier for short spam. Under the new rule, a short file with a song-like tag (the canonical spam's tag lies: `Morning Dew`) is kept. The tripwire reads only the tag; the filename is checked only for untagged files (2.4).
  - Evidence: junk.py `_stem` and `_keep_and_exclude`. Library: 129 of 3,980 shows have a dominant stem of `""` and 2,261 have a stem of 3 characters or fewer (computed from show.json filenames).
  - Failure scenario: a future `llama get` picks an item with `01 ... .mp3` naming that also carries `00 FOLLOW-ME @handle.mp3` (40 s, tagged `Intro` or a song title). Before, it dropped as `implausibly short`; now it is kept and airs.
  - Setup and likelihood: needs an LMA spam clip at the rate the canonical fixture shows. 0 such files exist among today's 3,547 drops, so this is prospective.
  - Suggested fix: apply the tripwire to the filename (and the `title`/`album`/`artist` strings) of every file the short rule keeps, whether tagged or not (one line). Record the remainder as an accepted limitation: short spam that matches the naming convention and lies in its tag is admitted, measured 0.

- **[Minor] The backup copy is not atomic or durable, and an existing backup is never replaced**
  - Where: 4.3 step 3 "Copy `overrides.json` to `overrides.pre-rekey.json`, only if no backup exists."
  - Problem: a plain copy killed mid-way leaves a partial backup. Because an existing backup is never replaced, the next run keeps the partial one and then rewrites the original. `atomic_write_bytes` does not fsync, so after a power loss the rename of `overrides.json` can be durable while the backup's data is not. An undo-edit-remigrate cycle also leaves a stale backup.
  - Evidence: workspace.py:26-38 (no fsync); 4.3 step 3.
  - Failure scenario: SIGKILL during the copy, then re-run: the only legacy copy is truncated, and undo for that show is impossible. The override data itself survives in the migrated keys.
  - Setup and likelihood: very rare (a ~1 KB file).
  - Suggested fix: write the backup with temp + fsync + rename before replacing the original. If a backup exists while the current file still has legacy keys, require the two to be byte-equal or refuse the show.

- **[Minor] The migration does not run the C1 staleness check that the writers run**
  - Where: 4.3 step 1 refusal list; 4.2 "every positional translation applies the staleness guard ... (C1)".
  - Problem: the migration's checks prove that `overrides.json` and `show.json` agree. They do not prove that `show.json` is current against `overrides.exclude`/`include` and the cached metadata. Two cases slip through: a `fix --no-run --exclude 5` after `--set-title 5=`, and a unit SIGKILLed after writing overrides but before gather. In both, a title can be mapped onto a file the operator has since excluded, or against a file list the next gather will not produce.
  - Evidence: cli.py:2866-2890 (the C1 comparison, which the migration does not reuse); measured today: 0 legacy shows with exclude ∩ show.json filenames, 0 with includes missing from show.json, 0 `.txn/` dirs. The migration runs later, though, after more v2.17.0 edits.
  - Failure scenario: after the migration, gather raises the resolver `LlamaError` on that show (loud), or keeps a title the operator meant for a different file.
  - Setup and likelihood: rare.
  - Suggested fix: add "`show.json`'s filename list differs from what current metadata plus overrides keep" to the step-1 refusals, reusing the writers' helper.

- **[Minor] The writers' C1 check must use gather's exact kept list, including the protection**
  - Where: 4.2 "the filename list `show.json` holds must equal what the current metadata and overrides keep"; 2.4 "calls `filter_files` again with a keyword (`keep_untagged_short=False`)".
  - Problem: today's C1 recomputes with plain `filter_files(readmit=...)` minus excludes. On a show where gather applied the count-match protection, that recomputation keeps the untagged candidates, so it never matches `show.json`. Every positional `fix`/triage edit on that show is then refused as "stale" for good, and `redo` cannot clear it.
  - Evidence: cli.py:2866-2890.
  - Failure scenario: `ratdog-2007-08-12`: `llama fix ratdog-2007-08-12 --set-title 4=...` always refuses.
  - Setup and likelihood: the 3 protection shows, plus future ones.
  - Suggested fix: compute C1 through the same function `title_inputs` uses for the final kept list (one shared helper).

- **[Minor] The protection's second `filter_files` call must keep the operator's include, and must not drop files the operator named**
  - Where: 2.4 "it calls `filter_files` again with a keyword ... and re-applies the operator exclusion."
  - Problem: the text mentions only the exclusion. If `readmit` is not passed, an operator-included file disappears silently on a protection show. Separately, an untagged short file that carries a `titles_by_file` key is still "untagged", so the protection can drop it, and the resolver then fails the show.
  - Evidence: 2.4 bullet; 4.1 "A key naming a file not in the final kept list raises `LlamaError`".
  - Failure scenario: the operator titles an untagged interior file, or includes one, on a show whose description list later count-matches without it. The include is lost, or the show fails gather.
  - Setup and likelihood: rare.
  - Suggested fix: say that the second call passes the same `readmit`, and that files named in `include` or in any filename key are not protection candidates.

- **[Minor] Numbering in a combined `fix` invocation is unspecified**
  - Where: 4.2 "Each translates number to filename through `show.json`".
  - Problem: today `fix --exclude 3 --set-title 7=X` writes `titles{7}`, and gather applies it after the exclude, i.e. to the old track 8. Under the spec, 7 is translated through `show.json` before the exclude. That is a silent change of meaning. It is also unclear whether C1 compares against the overrides before or after this invocation's exclude; the "after" reading refuses every such combination.
  - Evidence: cli.py:1411-1418 (titles written verbatim beside the exclude edit).
  - Failure scenario: an operator relying on today's behaviour titles the wrong file, with no error.
  - Setup and likelihood: uncommon.
  - Suggested fix: state that numbers always mean the `show.json` numbering the operator saw, and that C1 runs against the overrides before the edit. Add a test for the combined case.

- **[Minor] Acceptance (d) can pass vacuously if the base arm runs on a migrated library**
  - Where: 6(a) "Base arm: `scripts/replay_holds.py run --all` at `e37f670`"; 5.1 "The migration (4.3) runs first"; 6(d).
  - Problem: e37f670 code reads only legacy keys. A base arm run after the migration replays all 606 shows with no overrides, so there are no `override` tracks for (d) to check. Predicted lists computed before the migration carry the old `overrides.json` digests, so `reapply --from-list` afterwards skips all 606 as "inputs changed".
  - Evidence: replay.py:104 (`overrides.json` is in `input_digests`); reapply.py:91.
  - Failure scenario: the bulk apply's compare is run in the wrong order. The repro gate probably catches it (exit 3); (d) alone would not.
  - Setup and likelihood: needs an ordering slip; the gate is a backstop.
  - Suggested fix: state that any arm at pre-piece-4 code runs before the migration (or on a snapshot taken before it), and that apply lists are produced after it.

- **[Minor] `deliver`'s voiced check fails open on a read error, and the bulk re-delivery magnifies that**
  - Where: 5.3 "Delivered unvoiced shows are re-delivered".
  - Problem: `_destination_is_voiced` returns False on any `OSError`. A transient SMB error while reading a voiced destination's manifest during a ~1,100-show re-delivery merges an unvoiced manifest over it (`copytree(dirs_exist_ok=True)`). That discards `dj_audio` without `--replace-voiced`. The behaviour exists today, but the bulk re-delivery makes it far more likely to be hit.
  - Evidence: cli.py:2300-2309, 2385-2388.
  - Failure scenario: an ESTALE/EIO on one of the 28 minor voiced shows, if a selector reaches it. Its voicing is lost and emcee re-voices at full cost.
  - Setup and likelihood: low.
  - Suggested fix: treat only `FileNotFoundError` as unvoiced; any other read error refuses the show (two lines).

### Unverified premises
- **The 37 are approved.** `voiced-severe-review.md` is headed "approve individually for re-voice", and its `re-voice?` column is blank on all 37 rows. The evidence holds no approval. Cheapest test: record the operator's ruling 8 text naming the 37 slugs (or the filled column) beside `voiced-severe-final.json`.
- **No `llama` older than the new release runs between the migration and the end of the bulk apply.** The evidence cannot show this; it depends on procedure. Cheapest test: the migration's own PATH/version precondition (see the Critical finding).
- **No short spam among future items whose naming stem is empty.** 0 among today's 3,547 drops, which are in the library's own shows only. Cheapest test: run the tripwire over the filenames and tags of short-only drops in the 9,844 cached sibling items (premise 3's dump already holds them).
- **Every migrated key resolves under the new rule (new kept ⊇ old kept).** I find this true by construction (every new drop was a short-only drop before; dedupe cannot collide across a duration verdict), and the harness measured 0 play-order flips. Cheapest test: count resolver `LlamaError`s in the candidate arm with the scratch re-key; it must be 0.

TOTAL: 13 findings (1 Critical, 5 Important, 7 Minor)
