### Spec Compliance
- ✅ Spec compliant. All five interfaces match the brief's signatures (`batch_snapshot.py` lines 193, 285, 367, 417, 431 of the new file; the review diff gives them at 176-540). `take` copies per slug under the show lock, leaving out `package/audio/`, `.audio-aside/`, `.txn/` and the top-level `.lock` (`_metadata_files`, diff 149-170). Each copy is sha256-verified and flushed, and the station sha (or None) is recorded under the lock. `manifest.json` is written last through tmp+rename, and any failure removes the partial directory and raises LlamaError (diff 193-268). `restore` follows the brief's decision table and uses its three refusal strings verbatim (diff 70-73, 473-484). It empties audio only when the package manifest differs, deletes created files, does atomic write-back in the brief's order (diff 485-536), reports only without `apply`, and never writes the station. The copy/verify pattern is ported, and `scripts/rekey_overrides.py` is not imported or changed (only 2 files change). All seven named tests are present (test file, diff 635-813).
- Spec "Undo" ("refuses, per show, any show whose library files or station manifest changed after the batch"; "rewinds no station mark"): satisfied. The campaign records are included: `campaign.json` and `reuse-anchor.json` are covered and pinned at diff 645.
- ⚠️ Cannot verify from this diff:
  - **Task 13 must not re-`take` on a resumed batch.** `take` refuses an existing `snap` (diff 202-205). A reapply batch resumes in the same `<root>/reapply/<hash>/` dir, so a re-run must reuse the existing snapshot (and its `after.jsonl`), not re-take one.
  - **Task 13: classify `record_after` failures.** `record_after` raises when the station root is not a directory ("is the station mounted?", diff 138-141, 374). Under `after_commit` that fails the row after the commit and `show_unit` restores it. Task 13 should treat that as a retryable row failure and ideally count it toward the stop on three unreadable station copies; otherwise a mount drop on a held show (which never touches station reuse) produces a different, non-stopping failure.
  - **Restoring the backfill after marking.** The backfill's after-records predate marking, and marking rewrites delivered station manifests. Restoring the backfill after marking will therefore refuse every marked delivered show with `station manifest changed…: roll forward` until marking is reversed. That is consistent with the spec's literal rule and its order (reverse marking first), but the Task 15 runbook should say so.
  - **Nothing tracked is written after `after_commit` (checked; not a defect).** If the unit wrote a tracked file after the hook, every restore would refuse. In `reapply.py:376-383`, `mark_processed` runs before `after_commit`, and only `purge_package_audio` (audio, excluded) runs after it. `audio_reuse.py:233` (the anchor unlink) belongs to deliver, which also changes the station manifest. So the after-record is the final state. Task 14's per-show unit must keep the same property.

### Strengths
- **Fail-closed throughout.**
  - Restore refuses wholesale on a non-verifying snapshot or a bad `after.jsonl` line before reading any show.
  - Every snapshot copy is re-hashed immediately before the first write (diff 497-505).
  - A missing show dir is refused without taking `file_lock`, which would otherwise recreate the directory (diff 464-466, pinned at diff 692).
  - `take` never takes over or removes an existing directory (pinned at diff 695-699).
- **`already restored` is a sound addition.** Without it a second `restore --apply` would wrongly report "library files changed after the batch". Its `untouched` sub-case (the batch wrote identical bytes) is pinned by the seal test (diff 828).
- **Station-root checks.** Refusing a non-directory station root at every entry point stops an unmounted share from reading as "no station copy", which would otherwise make the station guard vacuous. The station path `station_root/slug/manifest.json` matches deliver's destination (`cli.py:2926`, `reapply.py:93`: `delivery_path / ws.dir.name`).
- **Directory durability.** `take` syncs each directory it creates, deepest first, then `shows/`, `snap` and `snap.parent`.
- **Mutation evidence.** The report predicts which test catches each of 10 mutants, and one surviving mutant (M10, the station ignored with no after-record) led to a real new assertion (diff 804-812).
- **Untouched items.** A grep of the diff for the Untouched items (`DURATION_TOLERANCE`, `STOP_AFTER_LLM`, `briefing_reusable`, `purge_package_audio`, `load_list`, the junk constants, `class Manifest`, `import emcee`) finds no hits.
- **Lock discipline.** `seal` locks and then calls the lock-free `record_after`, so the same lock is never taken twice.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **A part-way rewind is not resumable.** `batch_snapshot.py` `_rewind` (diff 506-536) and `_restore_one` (diff 479-482). If the rewind crashes or hits an OSError after deleting or rewriting some files, the next run refuses `library files changed after the batch`, and recovery is by hand. A clean rewind is idempotent ("already restored"), but a torn one is not. The window is small on local disk, and the message names the copy source, so this is Minor. Fix: in `_restore_one`, accept a state in which every tracked file is at its after-sha or its snapshot-sha and no file outside `after ∪ snap` exists. Treat that as "resume the rewind", and say so in the message. A KeyboardInterrupt in that window gets no message at all.
2. **One unreadable file aborts the whole restore loop.** `_restore_one` (diff 468-472) catches only `_Unfit`. A `PermissionError` or other OSError from `_file_shas`'s `read_bytes` propagates out of `restore`, abandons the remaining shows and reaches the CLI as a non-LlamaError. Fix: catch `OSError` there too and return `refused: <slug>/<rel> unreadable (...)`, so one show cannot abort the batch.
3. **A torn last line in `after.jsonl` blocks every restore with no repair route.** `_after_records` (diff 402-412) refuses the whole restore on any bad line, including a torn final line from a SIGKILL mid-append. That outcome is unlikely (a single small `write` with O_APPEND) but has no repair route. Consider naming the hand repair in the message ("remove line N if it is a torn final append"), or ignoring only a final line that has no newline.
4. **The write-all loop is duplicated three times and `_durable_replace` overlaps an existing helper.** The `memoryview`/`os.write` loop appears in `_write_copy` (diff 94-96), `_durable_replace` (diff 117-119) and `record_after` (diff 383-385). `_durable_replace` also near-duplicates `workspace.atomic_write_bytes` (`workspace.py:26`), differing only by the F_FULLFSYNC. Fix: factor out a `_write_all(fd, data)` helper. The module also imports the private `catalog._sync_fd` (diff 57); a public alias would be cleaner.
5. **Coverage gaps (not refused behaviour, just untested).** No test covers:
   - `_check_station_root` (an unmounted station root);
   - `refused: the show directory is gone`;
   - `refused: not in this snapshot`;
   - a malformed `after.jsonl` line;
   - the part-way rewind message.

   The first two guard real operator scenarios and each needs only a few lines of test.
6. **The refusal for a library put back while the station changed is misleading.** `_restore_one` (diff 477-482): with an after-record, current files equal to the snapshot and a station that has changed since the after-record, the show is refused as `library files changed after the batch: <rel>`. Refusing is correct, but the cause named is the wrong one; the station check could run first in that branch.

### Assessment
**Task quality:** Approved
**Reasoning:** Every brief interface, refusal string and named test is present and correct. The behaviour beyond the brief (`refused:` prefix, `already restored`, the extra refusals, the station-root check, `record_after`'s slug check, the hand-recovery message) is fail-closed and justified on the merits. The remaining items are Minor robustness and coverage points, plus three hand-offs for Task 13, Task 14 and the Task 15 runbook (resume reuse of the snapshot, classifying a `record_after` failure, restoring the backfill only after marking is reversed).
