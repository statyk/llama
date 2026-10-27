**Verdict:** READY WITH FIXES

I found no Critical issue. All three fixes below are cheap (a doc sentence, a docstring, one call moved earlier), and none of them blocks the campaign's safety properties. I'd make them before tagging 2.20.0, but shipping without them is defensible.

### Strengths

- **Station writer (`station_mark.py`).** It does exactly what the spec pins:
  - It works on the raw dict, never the `Manifest` model, and touches only `MARK_KEY`.
  - It writes a unique temp, flushes it, and re-reads the bytes just before `os.replace`.
  - After the rename it re-reads, verifies every other key, and puts back only over its own bytes (`put_back` checks the sha).
  - `_encode` now matches emcee's and llama's encoding (`json.dumps(indent=2)`, ASCII escapes, newline as read), so a mark followed by a clear gives back the original bytes. The Task 5 `ensure_ascii` minor is fixed.
- **Marking (`_mark_one` / `_mark_station`).**
  - The library record is written durably first, then emcee is checked before each write, then the before copy is saved before the station write.
  - The Task 15b M1 recovery (`_reversal`, two kinds of exact evidence) handles a crash between the station rename and the record line in both `mark` and `unmark`.
  - `_station_copy_problem` separates ENOENT from EIO and similar errors, and `_station_root_problem` rejects an empty mount point.
  - Unplannable rows refuse `--apply` instead of being dropped (M2), and `--campaign-dir` with `--apply` refuses (M3).
- **reapply.**
  - The station reads (`plan_reuse` strict + `check_pairs`, `_destination_voiced`) come before the fresh brief, and in gather-LLM mode before the align call.
  - `after_commit` now runs before the voiced-rider purge (the T9 recommended fix).
  - The re-selection skip is now gated on `awaiting` (the other T9 recommended fix).
  - A snapshot that does not verify is refused before any spend (T13 recommended fix).
  - Failure rows carry the meter and `llm_calls`, so the trial counts spend correctly (T13 recommended fix).
- **Strict reuse in `build_package`.** It never downloads a source that was paired at plan time. Only files no copy ever held download (Review Focus 3). The anchor is consulted only on an identifier match, so it can never pair a re-selected item's audio.
- **Unreadable `campaign.json` is never treated as "no record".** `is_awaiting` returns True, `_awaiting_fix_check`, `_redo_show_locked` and `build_package` all raise, and reapply's LlamaError arm makes the row retryable (Review Focus 5).
- **emcee.** The awaiting check runs first in `_process_one`, before `resolve_voicing`, preflight, the `--fresh` unlink and any spend. `package_status` returns AWAITING before `assess` and keeps `identity()`. `run` skips marked packages before building the spend plan.
- **Untouched list holds.** The junk constants, `DURATION_TOLERANCE_S`, `_pair`, the purge verification, `STOP_AFTER_LLM_FAILURES`, `load_list` and the piece-3 modules have zero diff. The one deviation is `briefing_reusable` gaining `overrules=()`; the ledger records it as parent-authorised (Task 4b), and the default keeps today's rule.
- **Transmitter** already reads `awaiting_fix` (`transmitter/station.py:129`), as CLAUDE.md says.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. **CLAUDE.md:88 misstates what `deliver` refuses, on a strict surface.**
   - **What it says:** "a station copy marked `awaiting_fix` is refused by plain `deliver`".
   - **What the code does:** `deliver` refuses when the *library* campaign record is awaiting (`cli.py` `_awaiting_fix_check`). A *marked station copy* whose library show has been processed is not refused; it is always replaced wholesale, which clears the mark (`cli.py` `_deliver_one`, the `voiced or marked or ...` branch).
   - **Failure scenario:** an agent reading CLAUDE.md, which is authoritative here, believes a marked copy cannot be re-delivered by name. It then either refuses to run the documented `deliver --fixed` route or invents a manual clear.
   - **Fix:** "a show whose campaign record is awaiting fix is refused by `deliver` (by name and in every selector) …; a station copy carrying `awaiting_fix` is always replaced wholesale, which clears the mark".
2. **`reapply.py:11-14`: the module docstring still gives the old order** (processed, then purge, then `after_commit`). The code (`reapply.py:380-386`) runs processed, then the hook, then the purge, which is the T9 fix. The docstring is the stated contract for a strict-surface ordering, so a future editor "restoring" the documented order would bring back the bug where a hook failure cannot restore purged audio.
   - **Fix:** reword it to "processed, then the caller's `after_commit` hook (a failure there restores the unit), then the voiced-rider purge".
3. **`cli.py` `_redo_show_locked`: strict refusals fire only at package time, after gather and brief have spent** (Task 8 M7, deferred).
   - **Failure scenario:** with the station unmounted, `llama fix <delivered> --set-title …`, a triage edit, or a selector `redo --from gather|brief` over delivered shows pays `align_structure` and a fresh brief per show. Each then refuses `StationUnreadable` and the unit rolls it back. The reapply list has its own mount check and per-show pre-brief station reads; redo, fix and triage have neither.
   - **Fix:** call `audio_reuse.check_pairs(reuse, show_ws)` right after `plan_reuse(..., strict=strict)` in `_redo_show_locked`. It is the same plan object `build_package` re-checks, and `check_pairs` does not depend on the new track list (station readable; something pairs), so the outcome is identical, just earlier.

#### Minor (Nice to Have)

- **`cli.py` `_deliver_batch`, the awaiting re-check under the lock** (T4 deferred). A show processed between the scan and the lock falls through to `_deliver_one` and is delivered, but the summary still prints `(refused: awaiting fix)`. No data harm. Fix: on a passing re-check, `marks.pop(slug)`.
- **Appendix B, wave restore.** For a *packaged, undelivered* show, `restore` empties `package/audio/` whenever the package manifest differs (`batch_snapshot._restore_one`). The rewound show then has a manifest whose audio is gone, so the next package re-downloads from archive.org. The station is never involved, so no data is lost, only bandwidth. Add one line to Appendix B.
- **`batch_snapshot._after_records`.** A torn last line, possible only on SIGKILL during `record_after`, refuses the whole restore with no repair route. Document "delete the torn last line; that show then refuses as `no write recorded`", or skip a torn last line.
- **`cli.py` `_fixed_for_delivery` docstring** says `_deliver_one` "re-checks". It re-checks awaiting only, not processed or marked.
- **`cli.py` `_deliver_one`.** The equal-copy refusal comes before the gate, so a held, voiced, marked, processed show is pointed at `clear-mark`, which then refuses "held" (T5 deferred). Wrong pointer only.

### Deferred-minor triage

Every item in `orch-r3/deferred-minors.md`, in file order. "OK" means OK to ship.

**orch/ledger.md**

- **T1** overrules/replay flag-classification duplication: OK. A drift risk only; the arm-flags fixture test pins every known flag.
- **T1** no merge_rules cross-identifier/within-new test: OK. `_ident` includes the identifier; dedupe-within-new is visible in the code.
- **T1** empty titles subject matches any rule: OK. An `unresolved track titles` flag with zero unresolved tracks does not occur.
- **T1** Overrides docstring omits overrules: OK, cosmetic.
- **T2** no test that vet splits only its own flags: OK. `apply_vet` splits only `grounding_flags` output (by reading).
- **T2** typing.Sequence / unannotated rules: OK, style.
- **T2** `llama show` prints `notes.brief`: OK. Read-only and useful.
- **T3** `manifest_sha256` defaults None: OK. A missing key makes clear-mark refuse (safe direction).
- **T3** `row_visible_changes` on needs-llm/unreplayable rows: OK. `_plan_one_mark` checks `_NO_DIFF` first.
- **T3** `after_package` raising after the manifest write: OK. Fixed: `build_package` reads the record first.
- **T3** no test pins the manifest sha after redo: OK. Covered indirectly by the clear-mark tests.
- **T3** `source.identifier` not in `VISIBLE_FIELDS`: OK. The replay never re-selects; re-selections have their own rule.
- **T3** campaign file flushed but its directory not fsynced: OK. The power-loss window is safe-direction: the station mark still blocks emcee, and a lost record only lets an unvoiced copy be re-delivered with its pre-mark data.
- **T4** batch re-check duplication / false "refused" line: OK. See the Minor above.
- **T4** awaiting-before-voiced order not pinned: OK. It is the first statement under the lock.
- **T4** batch test does not assert stderr: OK, test polish.
- **T4** 106-character line: OK.
- **T4b** callers must re-split problems: OK, documented.
- **T4b** duplicated test helper: OK.
- **T4b** unused `_overruled` binding: OK.
- **T5** `ensure_ascii`: OK. Fixed; `_encode` uses ASCII escapes.
- **T5** `_swap_in` raw OSError: OK. Every caller catches it (`_mark_station`, `_clear_mark_one`, `unmark`'s broad except).
- **T5** `_fixed_for_delivery` docstring: OK. Listed as a Minor above.
- **T5** equality refusal before the gate on a held show: OK. Listed as a Minor above.
- **T5** SIGKILL leaves a `.manifest.json.llama-*.tmp`: OK. A dotfile no reader parses; the next re-delivery replaces the directory.
- **T6** interrupt between `clear_mark` and `add_clear`: OK. The end state (station cleared, voicing kept) is the intended one; only the record line and the purge are lost.
- **T6** library-manifest I/O error or failing ps gives a traceback: OK. Nothing has been written at that point.
- **T6** refusal order only partly pinned: OK.
- **T6** compared bytes not tied to rewritten bytes: OK. emcee is checked first and `_rewrite` preserves every other key.
- **T6** put-back-failed message untested: OK.
- **T6** private `campaign._parse` use and copied skip text: OK, style.
- **T7** invalid move prints an error rather than a skip: OK. No spend, exit 1.
- **T7** refusal rebuilt by stripping a prefix: OK. Pinned by mutant d2.
- **T7** `_process_one` docstring: OK.
- **T7** duplicated `_forbid_spend`: OK.
- **T7** identity test checks non-null only: OK.
- **T7** `voice --fresh` on a marked package gives the wrong message: OK. No spend; `_process_one` refuses before the unlink.
- **POINTER T18** (CLAUDE.md re-download wording): done, and correct.
- **T8 M1** `_is_delivered` duplication: OK. Resolved: `ledger.is_delivered` is shared.
- **T8 M2** strict plus `force=True`: OK. Latent; no caller passes `force`.
- **T8 M3** missing paired copy reported as "failed its length check": OK. The wording is imprecise but the outcome (refuse, no download) is right.
- **T8 M4** tally ignores in-place files: OK, cosmetic.
- **T8 M5** triage strict refusal prints no route: OK. Triage prints the refusal; the hint is for by-name commands.
- **T8 M6** no `fix --untitled` hint test: OK.
- **T8 M7** strict refusal after gather/brief spend: **Should fix.** See Important 3.
- **T9** re-selection skip unconditional (RECOMMEND FIX): fixed (`reapply.py:204`, gated on `awaiting`).
- **T9** purge before `after_commit` (RECOMMEND FIX): fixed (`reapply.py:381-386`). Docstring stale: Important 2.
- **T9** label-only commits leave the anchor forever: OK. The anchor pairs only on an identifier match plus title equality, so it stays harmless.
- **T9** a briefed-not-packaged unchanged show stays unpackaged: OK. That is its prior state; 21 shows at most.
- **T9** `_purge_line` duplication: OK.
- **T9** by-name failure line prints the slug twice: OK.
- **T9** dry-run download over-count: OK. It is an upper bound.
- **T10** duplicated scratch block: OK.
- **T10** test no-op and unused parameter: OK.
- **T10** `set_breaks` in `_align_reproduced` unpinned: OK. Trial statistic only.
- **T10** ladder tests use one FakeProvider: OK.
- **T9b** docstring order: **Should fix** (Important 2).
- **T9b** comment wording: OK.
- **T9b** no test for a held show with a processed select mark: OK. The code takes the held path, by reading.
- **POINTER T14** titles subject from the base row: done (`_titles_rule`).

**orch-r1/ledger.md**

- **T11** part-way rewind not resumable: OK. It refuses with a hand-copy route.
- **T11** `_restore_one` catches only `_Unfit`: OK. An OSError aborts the loop with a traceback; shows already restored report `already restored` on a re-run.
- **T11** torn `after.jsonl` line: OK. Safe (refuses); document the repair (Minor above).
- **T11** write-loop duplication and private imports: OK.
- **T11** untested branches: OK.
- **T11** wrong cause named for a changed station: OK.
- **T12** retired-key presence vs non-null: OK. Both refuse or skip in the safe direction.
- **T12** unreadable rekey record returns False: OK.
- **T12** `cmd_pin` does not call `_check_identity`: OK. `code_identity() == tag sha` is still enforced.
- **T12** tracebacks for a missing `--slugs` file etc.: OK.
- **T12** restore exit-1 path undocumented: OK.
- **T12** version-rule duplication: OK.
- **T12** style items: OK.
- **T12** unused `import llama` as a patch seam: OK.
- **T12** first pin does not sync root: OK. Fails safe (no pin).
- **T12** private `_VERSION` import: OK.
- **T13** trial n / failure rows (RECOMMEND-FIX): fixed (`fail()` records `llm_calls` and the meter; `trial(..., spent)`).
- **T13** snapshot without `manifest.json` (RECOMMEND-FIX): fixed (`verify(snap)` before any write).
- **T13** ceiling/stop-at-points inert without a meter: OK. Pacing's documented degradation; the operator's backend is `claude_cli`.
- **T13** EIO via `_station_sha` not counted in the streak: OK. A delivered show's pre-brief strict read already raises `StationUnreadable` on EIO; the residual is undelivered rows on a flaky mount.
- **T13** names-form refusal untested: OK.
- **T13** test hygiene: OK.
- **T13** `retire_rekey_restore` OSError traceback: OK. Before the first show.
- **T13** lost `("cleared", False)` test row: OK.
- **T13** resume line path unquoted: OK.
- **POINTER T18** resume line repeats `--stop-at-points`: done (Appendix A step 7).
- **T14** rulings on flags the base arm did not raise: resolved by Checkpoint A rule (d).
- **T14** `_append_jsonl` duplication: OK.
- **T14** dry run prints no titles subject: OK.
- **T14** retire return value ignored: OK.
- **T14** corrupt verdict aborts the dry run: OK (exit 2, nothing written).
- **T14** `show_unit` restore failure: OK. Pre-existing.
- **T13b** trial test asserts: OK.
- **T13b** `_spend` swallows AssertionError: OK.
- **T13b** snapshot refusal names `problems[0]` only: OK.
- **T13b** bool added to a counter: OK.
- **T13b** `skipped: missing` row carries no meter: OK.
- **T15 M1/M2/M3** (RECOMMEND-FIX): all fixed (`_reversal`/`_UNVERIFIED`, `_Unplannable`, `cmd_mark`'s `--campaign-dir` refusal).
- **T15 M4** FROZEN_NAME / assessment duplication: OK. Drift risk only.
- **T15 M5** private imports: OK.
- **T15 M6** broad except: OK. `_guard_holds` failure means no overrule honoured (marks more); `_plan_state` gives a table column only.
- **T15 M7** test gaps: OK.
- **T15 M8** freeze accepts any arm: OK. Write-once; the runbook freezes from arm-1 at the pin.
- **POINTER T18 M9**: done (Appendix B).
- **T15** dead `copy_problem` assignment: OK.
- **T15** "no station copy" remedy: done (Appendix A step 6).
- **T15** dry-run stat-error branch untested: OK.

**orch-r2/ledger.md**

- **T15b** evidence (1) proves equal JSON, not bytes: OK. It compares canonical re-encoded bytes to `raw` and restores the saved original bytes.
- **T15b** `_reversal` duplicates `_encode`: OK. Drift risk only.
- **T15b** `_mark_station` at/batch_at, inline sha: OK.
- **T15b** fork() warnings: OK. Pre-existing.
- **T15b** "not delivered" never checked: OK. Documented (Appendix A step 6). An awaiting show cannot be delivered, so no station copy appears under it.
- **T15b ⚠️** unmark keeps a `mark_added:false` "marked" line's station mark: **OK to ship.**
  - That library is still awaiting from the earlier batch, so the station mark stays consistent with it, and "marked" only ever blocks voicing and airing.
  - The residual case: an earlier batch whose station write was refused, followed by a new batch before a re-run, then both reversed. It leaves an unvoiced copy marked with the library unawaited (`deliver` then puts back pre-mark data), or a voiced copy needing reapply then clear-mark.
  - Suggest one Appendix B line: "unmark leaves a station mark it did not add a library mark for".
- **T15b** unused locals in tests: OK.
- **T15b** crash simulated by an exception: OK.
- **T16** famous packet ignores filters: OK.
- **T16** `lists` exit 0 after stderr drops and a `--counts` shrink: OK. Unreadable stations are reported on stderr; the projection is slightly low.
- **T16** `_voiced` before the kind filter: OK. Order only.
- **T16** spot-check edge cases: OK.
- **T16** delivered-id set built three times: OK.
- **T16** wave-check skips unreadable `_plan_state`: OK. Disk under-estimate is bounded by the 20 GB margin.
- **T16** awaiting unreplayable row gets kind held: OK. reapply decides the real route.
- **T16** test cannot separate the two re-selection guards: OK.
- **T16** `import random` inside a function: OK.
- **T16 ⚠️** trial-report reads the `"(none)"` key: OK. `cmd_trial_report` iterates queue keys as given.
- **T16** empty mount point passes `is_dir`: fixed for lists/mark/wave-check (a82b0755). reapply checks `is_dir()` only, but the configured root sits two levels below the mount.
- **T16** `os.access` consistency: OK. `_station_root_problem` is now shared.
- **T17** missing resets read as crossed: OK. Safe direction (the block is re-run).
- **T17** material-difference denominator unpinned: OK.
- **T17** `MIN_BLOCK_POINTS` boundary unpinned: OK.
- **T17** unreadable record dropped from revoice-list: OK. Reported on stderr.
- **T17** presenter vs cost drift: OK.
- **T17** unknown queue kinds cost 0: OK.
- **T17** `align_reproduced` double counting: OK. Statistic only.
- **T17** revoice-list arm sha unchecked: OK. Read-only.
- **T17** `_spending_rows` last row only (RECOMMEND-FIX): fixed for other kinds (`_foreign_inside` reads every line). Own-kind last-row collapse remains and over-states cost (the conservative direction).
- **T17** window boundary unpinned: OK.
- **T17** last-row collapse for its own kind: OK. Conservative.
- **T17** refused blocks in the tally and missing prefix: OK.

**orch-r3/ledger.md**

- **T14b** null-subject overlap in the dry run: OK. Documented (Appendix A step 3); 0 measured.
- **T14b** dry-run totals double-count: OK. `merge_rules` dedupes at apply.
- **T14b** precedence untested: OK. A swap changes only the note text.
- **T14b** `_basis` `next()` / positional indexing: OK.
- **T14b** `note: null` in fix overrules: OK.
- **T15c** package-flag-only newly held: OK. 0 rows measured.
- **T15c** stale docstring and order: OK.
- **POINTER T18** fifth trigger in the spec: done (spec line 173).
- **T14c** dead `_NEVER_KINDS_A` and test name: OK.
- **RF** root/copy race giving a terminal "no station copy": OK.
  - The window is a single stat; each item re-checks the root first.
  - Remedy: a fresh marking batch from a new arm re-marks it (`mark_added: false`, station "marked"). Re-running the same batch does not clear it.
- **RF** `_foreign_inside` shape and helper duplication: OK.
- **RF** `os.access` branch unpinned: OK.
- **RF** commit-message count: OK.

### Declined to judge

- `clear-mark` and `--replace-voiced` equality ignore the briefing. A voiced show whose briefing was regenerated, with no visible field changed, clears and keeps a DJ script written from the old briefing. The spec fixes the compared field list.
- `briefing_reusable` gaining `overrules=()` despite being on the Untouched list. The ledger records it as parent-authorised (Task 4b); I did not re-litigate it.
- The doubled-derivative case (the station holds `X_vbr.mp3`, the new list keeps `X.mp3`) downloads under strict reuse. The plan's rule is filename-based ("an unpaired source downloads"), and the spec measured downloads at about 2.6 GB.
- Per-name `reapply <slug>` (Appendix A step 11, voiced shows) takes no batch snapshot. The spec scopes snapshots to batches; `show_unit` still restores on failure.
- Matching each Checkpoint A/B ruling's exact semantics, and the measured counts (494 recorded, 2640 marks). These are operator rulings recorded in the spec; I checked the code implements the stated rules, not the rulings.
- Transmitter's own handling of a mark that appears after planning. The spec assigns it to the scheduler session.
- SMB/NFS rename atomicity, and the station-mark residual window. Both are named open gaps.
- Speed of `emcee_running()` running `ps` once per marking item (about 2,600 calls). A runtime concern, not correctness.
- The trial's statistical design (`MIN_BLOCK_POINTS`, `MATERIAL_DIFFERENCE`). Spec-chosen constants.

### Passes done

All six suggested passes:

1. station_mark, deliver, clear-mark, emcee awaiting-fix.
2. campaign.json, status, catalog, cli_select, ledger.
3. reapply, `build_package` strict reuse, audio_reuse, batch_snapshot.
4. overrules, gather, vet, brief, fix, triage, replay.
5. `scripts/bulk_apply.py`: pin, arm, snapshot, backfill, freeze, reselect-check, mark, unmark, lists, wave-check, spot-check, revoice-list, trial-report, main.
6. CLAUDE.md, the spec and the plan's Appendix A/B against the code.

I re-checked all five Review Focus scenarios across the branch and confirmed their named tests exist. I grepped the diff for the Untouched items. I ran no tests and no mutants: every doubt resolved from the code. I wrote nothing outside this task directory.
