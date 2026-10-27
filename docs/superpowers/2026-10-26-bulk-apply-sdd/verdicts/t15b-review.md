### Spec Compliance
- ✅ Spec compliant. M1, M2 and M3 meet the brief, and the brief's fixed test names are present.
  - **M1:** the implementer chose design (a). `_mark_station` is at `scripts/bulk_apply.py:739-772`, `_reversal` at `:712-736`, `_own_station_mark` at `:929-955`, and the `_unmark_one`/`unmark` changes at `:958-1028`.
  - **M2:** `mark_plan` at `:626-657`, `_could_mark` at `:618-623`, `_stored_show` at `:546-550`, `_print_mark_plan` at `:1120-1122`, and `cmd_mark` at `:1171-1178`.
  - **M3:** `cmd_mark` at `:1133-1135`.
- ⚠️ Cannot verify from this diff (outside this task's scope; noted for the whole-branch review): a line with `mark_added: false` is still "kept" by `unmark` (`:1012-1014`, Task 15's design). That includes a `marked` line where THIS batch wrote the station mark because the library was already awaiting from an earlier batch, or because `campaign.json` was unreadable.
  - In that case `unmark` exits 0 and the station keeps a mark this batch wrote.
  - The library is still awaiting, so the state is consistent, and the brief scopes M1 to `mark_added: true`.
  - Whether the spec's "the key is removed only where the manifest still equals what marking wrote" wants the station put back here is a question for the branch review. This task did not change it.

### Strengths
- **Every put-back is safe by construction.** I checked every path that reaches `put_back`:
  - Evidence (1) (`:723-728`) requires `encode(before + current mark) == raw`. Evidence (2) (`:729-734`) requires `sha(raw) == after_sha256` and `sha(raw minus the mark) == before_sha256`.
  - Either way, the bytes put back carry exactly the current station content minus this batch's key. Evidence (2) is also sha-identical to the recorded pre-mark bytes.
  - So a put-back can never undo an emcee rewrite. An emcee change makes both checks fail, and the line is then `_UNVERIFIED` or listed by `unmark`, never written.
  - `put_back` is called with `expect = sha(raw)` (`:955`, `:996`), so a write landing after the check is refused by the existing sha re-check.
  - `emcee_running()` still runs before every station write (`:847`, `:993`). The recognition path in `mark_apply` writes no station bytes.
- **Reusing `at` is sound** (`:839-841`).
  - The station `marked_at` now equals the batch's library mark `at`, so one identity ties the record line, the library mark and the station mark together.
  - If the show is processed between runs, `is_awaiting` becomes false and `add_mark` creates a newer mark, so a stale `at` is never reused across processing.
  - It fits `cli._processed_since_mark` (`cli.py:2883-2896`), which needs processing at or after the station's `marked_at`. A `marked_at` equal to the library mark is no later than the real write time, so that check stays correct.
  - `test_rerun_marks_the_station_with_the_batchs_own_at` pins it. My control mutant M4 removed the reuse and that test went RED, as predicted.
- **The new outcomes fit the skip set and the exit rule.**
  - `done` excludes `_RETRIED` by prefix (`:875-876`), and the parenthesised `_UNSAVED` text still matches.
  - Neither new outcome is in `_STATION_OK`, so both are listed by the per-item flag (`:858`) and by the whole-record loop (`:904-907`).
  - The `counts` key split (`:885`) gives a clean label.
  - A healed `_UNSAVED` line becomes the slug's last line as `marked` (covered by `test_rerun_heals_an_unsaved_before_copy`).
- **`unmark` now covers the windows the record cannot show.**
  - A before copy with no record line is listed (`:1003-1008`). An unreadable station copy that has a before copy is listed (`:941-944`).
  - Without a before copy this batch never wrote that copy: `_write_durable(saved, raw)` always runs before `write_mark` (`:765-766`), so the silent no-problem return at `:942` is justified.
  - `before/*.json` does not match the `.tmp` names `_durable_replace` leaves behind (`batch_snapshot.py:97`).
- **M2's scope is consistent with "never silently drop".**
  - `_could_mark` (`:618-623`) is exactly the condition under which `_plan_one_mark` can return non-None: a re-selection, a `_NO_DIFF` row only via the frozen list, and every other outcome possibly (visible change or guard).
  - The rows it leaves out (needs-llm or unreplayable, off the frozen list, not re-selected) are never marked even when their directory exists, so nothing that should be marked is dropped.
  - Unreplayable ones still appear on the `unreplayable, not marked:` line. The rule is conservative toward marking: a removed `clean` row still blocks `--apply`.
- **M2/M3 refusals happen before any write.** Both come before `retire_rekey_restore`, the backup and the batch dir. The tests assert this with whole-tree file snapshots (`test_apply_refuses_while_shows_are_unplannable`, `test_campaign_dir_refused_with_apply`).
- **The RED evidence is genuine** (`t15b-impl.log:43-300`, and `:390` for the scratch-copy RED of the tenth test).
- **Suite:** 6301 passed, 1 skipped, 8 deselected (`log:398`).
- **Untouched items:** grepping the diff for `DURATION_TOLERANCE_S`, `STOP_AFTER_LLM_FAILURES`, `briefing_reusable`, `purge_package_audio`, `load_list` and the junk constants finds nothing. No llama source changed.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **Two new safety branches are unpinned (RECOMMEND-FIX before `mark --apply`).** I ran mutants in a scratch copy (`git archive d6a9eb24`), using the worktree venv's `python -m pytest` with PYTHONPATH shadowing. Both `llama.__file__` and `bulk_apply.__file__` resolved inside the copy, and `PYTHONDONTWRITEBYTECODE=1` was set. Predictions were written to the log before each run.
   - **M1 survived** (`scripts/bulk_apply.py:756`, `return _UNVERIFIED, None, _sha(raw)` replaced with `return "already marked", None, None`): 38/38 passed. No test drives `mark_apply` into `_UNVERIFIED`. The mutant would make `mark --apply` exit 0, and record a terminal outcome that is never retried, while the station holds a mark with no verified reversal. `unmark` would still list it.
     - Fix: add a test where the station copy carries the batch's `marked_at` but neither kind of evidence holds. For example, rewrite `dj_notes` in the marked copy after a crash-after-write. Assert the line is `_UNVERIFIED`, rc is 1, it is listed, and the station bytes are unchanged.
   - **M2 survived** (`:941-942`, the `saved.exists()` distinction replaced so an unreadable station copy is never a problem): 38/38 passed. This is precisely the "unmark exits 0 while the station may carry this batch's mark" case, for example with the station root unmounted. The code is right, but no test pins it.
     - Fix: add a test with a `refused`/`_UNSAVED` line, `mark_added: true`, `before/<slug>.json` present and the station manifest unreadable. Assert exit 1 with the "cannot check the station copy" line, and the library mark kept.
   - **Controls behaved as predicted:**
     - M4 (drop the `at` reuse) turned `test_rerun_marks_the_station_with_the_batchs_own_at` RED.
     - M8 (`elif False` in place of the `_unmark_one` non-`marked` branch) turned `test_before_save_failure_after_write_is_not_recorded_refused` and `test_unmark_never_reports_success_over_this_batchs_station_mark` RED.
2. **Evidence (1)'s trailing-newline rule is unpinned** (`:726`). Mutant M7 forced `newline=True` and survived. The cost of a regression is safe, since mismatching newlines only stop evidence (1) from verifying. Still, a test with a llama-encoded (no trailing newline) station copy through the crash-recognition path would pin it, and it is the only point where `_reversal` mirrors `write_mark`'s encoding.
3. **Evidence (1) proves equal JSON, not equal bytes.**
   - `_reversal` returns the saved before bytes whenever `encode(parse(before) + mark) == raw`, even if a different byte string was the actual pre-mark file. That can happen only when a concurrent writer replaced the file between marking's read and `write_mark`'s read with semantically equal but differently formatted JSON.
   - Both real writers use the canonical encoding, so this is negligible, and content is never lost.
   - If you want bytes: when the line has a `before_sha256`, prefer evidence (2), or require `sha(before) == line["before_sha256"]` whenever the line carries one.
4. **The design duplicates `write_mark`'s change rule.** `_reversal` (`:727`) rebuilds `write_mark`'s change rule (`{**bdata, key: mark}`, which matches `dict(data); new[KEY] = mark` in `station_mark.py:170-173`) and calls the private `station_mark._encode`. `campaign._now`/`_parse` are still private imports, the same family as Task 15's M5.
   - A public `station_mark.marked_bytes(before: bytes, mark: dict) -> bytes`, used by both `write_mark` and `_reversal`, would remove the risk of the two drifting apart.
   - The handback says "I added `station_mark._encode`". The function already existed (`station_mark.py:99-106`, untouched by this diff); only the call is new.
5. **Small consistency points.**
   - `_mark_station` takes both `at` and `batch_at`, which are equal whenever `batch_at` is not None (`:839-841`, `:851`). One parameter plus a `recognise: bool` would read more plainly.
   - `_unmark_one`'s `marked` branch still calls `hashlib.sha256(...).hexdigest()` directly (`:973`, `:976`), next to the new `_sha` helper.
   - The `for slug in sorted(...) if before_dir.is_dir() else []:` header (`:1004-1005`) is correct but dense. A named list would read better.
6. **Warnings in the suite run.** The full-suite runs show 26 `DeprecationWarning: ... use of fork() may lead to deadlocks` (`t15b-impl.log:379-388`). They come from untouched llama test files (`test_atomic_write`, `test_concurrency`, `test_ledger_concurrency`, `test_locks`, `test_sessions`) under Python 3.14. They predate this task and are not attributable to it, but they are noise in the evidence.
7. **The `not delivered` edge** (`:986`). A slug whose last line is `not delivered` is never checked against the station. If an earlier run of this batch wrote the station and crashed before its line, and the ledger then stopped listing the show as delivered, `unmark` would not notice. The before copy would then have a line, so it is not listed either. This is very remote, since the ledger would have to lose the delivered entry. Mention it in the runbook, or extend the `_own_station_mark` check to `not delivered` lines that have a before copy.

### Assessment
**Task quality:** Approved
**Reasoning:** All three fixes meet the brief and the binding spec. The new recognition and put-back path can only put back the current station content minus this batch's mark, and only under the existing sha-checked `put_back` and the emcee guard. Its interaction with the skip set, the whole-record exit rule and `_STATION_OK` is correct. The remaining items are test gaps (surviving mutants M1 and M2 on the strict surface, which I recommend fixing before `mark --apply`) and polish.
