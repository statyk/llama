# Deferred minors, ⚠️ items and parked findings from every task review (four orchestrator ledgers, in task order)

## from orch/ledger.md
Task 1: minor (deferred): overrules.py:26-51 duplicates replay.py:153-167 flag classification (drift risk)
Task 1: minor (deferred): no test that merge_rules keeps the same kind/subject on another identifier, or dedupes within new
Task 1: minor (deferred): overrules.py:80-81 empty titles subject matches any rule; comment it
Task 1: minor (deferred): Overrides docstring (models.py:221-224) omits overrules
Task 2: minor (deferred): no test pins "vet splits only its own flags" (vet_research.py:321)
Task 2: minor (deferred): typing.Sequence vs collections.abc in vet_research.py:3; gather.py:2236 rules unannotated
Task 2: minor (deferred): llama show prints notes.brief (unasked, small, tested)
Task 3: minor (deferred): campaign.py:40 manifest_sha256 defaults None though contract requires the key (missing reads as held, not malformed)
Task 3: minor (deferred): replay.py:258-261 row_visible_changes on needs-llm/unreplayable rows returns ["files"] — POINTER T15/T16: check outcome before row_visible_changes (plan T15 already says needs-llm/unreplayable never get the visible-change reason)
Task 3: minor (deferred): package.py:140 after_package can raise CampaignUnreadable after the manifest write (outside show_unit: get/run resume) — POINTER T8: consider reading the record at the top of build_package
Task 3: minor (deferred): cli.py:2817 no test pins manifest sha after redo (held=pkg is None)
Task 3: minor (deferred): replay.py:236 spec lists source.identifier as visible; plan's VISIBLE_FIELDS omits it (re-selections marked by their own rule)
Task 3: minor (deferred): campaign.py:77-81 file flushed, dir not fsynced (brief-mandated mechanism)
Task 4: minor (deferred): cli.py:2713-2720 batch re-check duplicates _deliver_one's first check (double lock; a show processed after the scan prints refused yet delivers)
Task 4: minor (deferred): no test pins awaiting-before-voiced order (cli.py:2623)
Task 4: minor (deferred): batch test (test_deliver_cmd.py:891) doesn't assert stderr refusal/pointer or no ledger row
Task 4: minor (deferred): cli_select.py:59 106 chars
Task 4b: minor (deferred): generate_briefing returns all problems; callers must split again (docstring-only guard)
Task 4b: minor (deferred): test_stage_brief.py _songs_briefing duplicates _x_briefing
Task 4b: minor (deferred): unused _overruled binding (replay.py:539, brief.py split)
Task 5: minor (deferred): station_mark.py:104 ensure_ascii=False re-encodes emcee's \uXXXX escapes (data equal, bytes outside the mark change; clear does not restore originals) — fix ensure_ascii=before.isascii(); candidate for final review
Task 5: minor (deferred): station_mark.py:111-129 _swap_in raises raw OSError (not StationRefused) on a failed write — POINTER T6/T15: catch OSError per show (or wrap) so a dropped mount cannot crash the batch
Task 5: minor (deferred): cli.py:2710 _fixed_for_delivery docstring overstates the re-check
Task 5: minor (deferred): cli.py:2658-2664 equality refusal before the gate tells a held voiced marked show to clear-mark, which refuses held — POINTER T6
Task 5: minor (deferred): station_mark.py:115 SIGKILL leaves .manifest.json.llama-*.tmp (no sweep)
Task 6: minor (deferred): cli.py:2956-2962 interrupt between clear_mark and add_clear leaves station cleared, no clear recorded, audio unpurged; re-run refuses "not marked" (known limitation)
Task 6: minor (deferred): cli.py:2944/2951 library-manifest I/O error or failing ps escapes as traceback (nothing written yet)
Task 6: minor (deferred): refusal order only partly pinned (held/sha/differences swaps pass)
Task 6: minor (deferred): cli.py:2932 vs 2956 compared bytes not tied to rewritten bytes (small risk)
Task 6: minor (deferred): cli.py:2968-2971 put-back-failed message untested
Task 6: minor (deferred): cli.py:2887 private campaign._parse; 2877 copies catalog skip-reason text
Task 7: minor (deferred): cli.py:506-512 marked package with invalid recorded move prints error/exit 1 rather than skip; neither order tested
Task 7: minor (deferred): cli.py:263-268 refusal rebuilt by stripping the status-line prefix (pinned by mutant d2)
Task 7: minor (deferred): cli.py:254 _process_one docstring omits the awaiting-fix first step
Task 7: minor (deferred): test_run_cmd.py:791 _forbid_spend duplicates helpers.forbid_spend
Task 7: minor (deferred): test_status_cmd.py:770-772 identity test checks non-null only
Task 7: minor (deferred): cli.py:628-637 voice --fresh on a marked package fails on stem validation first (no spend; message wrong)
POINTER T18: CLAUDE.md "a purged show re-delivers via redo --from package, which re-downloads" is now wrong for delivered shows.
Task 8: minor (deferred): M1 cli.py:3051-3053 _is_delivered duplicates reapply.py:66-68 _delivered — POINTER T9: share one helper
Task 8: minor (deferred): M2 package.py paired captured before in-place narrowing; strict + force=True would refuse over an in-place library file (latent, no caller passes force)
Task 8: minor (deferred): M3 missing paired copy reports "failed its length check"
Task 8: minor (deferred): M4 tally counts in-place files as neither reused nor downloaded
Task 8: minor (deferred): M5 triage strict refusal prints no route
Task 8: minor (deferred): M6 no test for fix --untitled under the refusal hint
Task 8: minor (deferred): M7 strict refusals fire at build time after gather/brief spend (T13 mount check is the guard)
Task 9: minor (deferred, RECOMMEND FIX at final review): reapply.py:179 re-selection skip unconditional — a processed (or held) re-selected show still points the operator at another redo --from select (full re-download); gate on awaiting_fix
Task 9: minor (deferred, RECOMMEND FIX at final review): reapply.py:330-336 purge before after_commit — a hook failure cannot restore purged library audio (station copy still holds it); run the hook before the purge
Task 9: minor (deferred): reapply.py:286 label-only/unchanged commits leave reuse-anchor.json forever
Task 9: minor (deferred): reapply.py:214-220 briefed-not-packaged show with no visible change commits show.json only, stays unpackaged
Task 9: minor (deferred): reapply.py:114 _purge_line duplicates cli._echo_purge messages
Task 9: minor (deferred): cli.py:4122 by-name failure line prints slug twice
Task 9: minor (deferred): cli.py:4269 dry-run download count over-counts delivered shows reused from the station
Task 10: minor (deferred): reapply.py:212-217/231-239 scratch-dir + compute_legs block duplicated
Task 10: minor (deferred): test_reapply.py:700-701 no-op statement; :575 unused config param
Task 10: minor (deferred): no test pins set_breaks comparison in _align_reproduced
Task 10: minor (deferred): ladder tests use one FakeProvider for all rungs (escalated rung reach checked directly by the reviewer, not pinned)
Task 9b: minor (deferred): reapply.py:11-14 module docstring still says purge before after_commit
Task 9b: minor (deferred): reapply.py:380 comment wording ("a hook failure restores the unit, which cannot bring back purged audio")
Task 9b: minor (deferred): no test for a held show whose select mark was processed taking the held path
- T14: build the titles subject from the base row's title_sources; never records_for(show) on today's show.json (T1 ⚠️).

## from orch-r1/ledger.md
Task 11: minor (deferred): part-way rewind not resumable (_rewind/_restore_one); KeyboardInterrupt there gets no message
Task 11: minor (deferred): _restore_one catches only _Unfit — an OSError from _file_shas aborts the whole restore loop (catch OSError, refuse per show)
Task 11: minor (deferred): torn final after.jsonl line blocks every restore with no repair route
Task 11: minor (deferred): write-all loop x3; _durable_replace overlaps workspace.atomic_write_bytes; imports private catalog._sync_fd
Task 11: minor (deferred): untested: _check_station_root, 'show directory is gone', 'not in this snapshot', malformed after.jsonl, part-way rewind message
Task 11: minor (deferred): library-restored-but-station-changed refused as 'library files changed' (wrong cause named)
Task 12: minor (deferred): retire writer treats "retired" key presence as retired; reader requires non-null
Task 12: minor (deferred): retire_rekey_restore returns False for unreadable/non-dict record, same as absent; untested branch
Task 12: minor (deferred): cmd_pin does not call replay_holds._check_identity (recorded worktree may not be the tree checked)
Task 12: minor (deferred): bulk_apply main lets OSError (missing --slugs file) / replay_holds.Refusal outside arm escape as tracebacks
Task 12: minor (deferred): restore exit 1 path undocumented in docstring and untested
Task 12: minor (deferred): version rule duplicates rekey_overrides.py:779-830 (acceptable per brief; note for final review)
Task 12: minor (deferred): style — mid-file imports in test_campaign_gate.py; split Path imports; bulk_apply._config re-implements replay_holds config resolution
Task 12: minor (deferred): bulk_apply.py keeps unused 'import llama' as a test patch seam (patch llama module directly instead)
Task 12: minor (deferred): first pin creating root/campaign does not sync root (entry for campaign/); safe failure (no pin)
Task 12: minor (deferred): bulk_apply imports private campaign_gate._VERSION
Task 13: minor (deferred, RECOMMEND-FIX): trial n counts zero-spend skips and excludes failed rows; failure rows carry no meter → biases the per-show cost the trial measures
Task 13: minor (deferred, RECOMMEND-FIX): a non-fresh batch whose snapshot/ lacks manifest.json → every write's record_after raises, unit restores after the brief spend, no stop; verify the snapshot once before the first show
Task 13: minor (deferred): --stop-at-points/--seven-day-ceiling silently inert when the meter does not apply (refuse up front)
Task 13: minor (deferred): EIO/ETIMEDOUT station read via _station_sha (_Unfit) or is_dir() OSError in the hook not counted toward the unreadable streak
Task 13: minor (deferred): names-form refusal of --seven-day-ceiling/--stop-at-points untested
Task 13: minor (deferred): test hygiene (unused 'real', unasserted comment, float|None annotations)
Task 13: minor (deferred): retire_rekey_restore OSError escapes _reapply_list as a traceback
Task 13: minor (deferred): test_retryability_per_outcome lost its ("cleared", False) row in the fix (behaviour unchanged)
Task 13: minor (deferred): resume line's {path} unquoted
POINTER T18: runbook — after a trial stop the resume line repeats --stop-at-points; drop it once the trial is accepted.
Task 14: minor (deferred → CHECKPOINT A question): verdict rulings on flags the base arm did not raise are neither recorded nor listed — 174 (slug, flag) pairs over 36 shows; none raised by migration-post.json
Task 14: minor (deferred): _append_jsonl duplicates record_after's durable-append loop; imports private catalog._sync_fd / batch_snapshot._sync_dir
Task 14: minor (deferred): dry run prints 'record: unresolved track titles' without its subject
Task 14: minor (deferred): retire_rekey_restore return ignored (no note when nothing retired)
Task 14: minor (deferred): a corrupt verdict file aborts the dry run (exit 2) rather than listing that show
Task 14: minor (deferred): show_unit's own restore failing leaves overrides rewritten; a re-run reports nothing to record (pre-existing unit limitation)
Task 13b: minor (deferred): trial test asserts neither exit code nor that the block's last slug was never processed
Task 13b: minor (deferred): _spend test helper swallows AssertionError from FakeProvider (couples to an empty queue)
Task 13b: minor (deferred): snapshot refusal names only problems[0] (no count of the rest)
Task 13b: minor (deferred): block[1] += spent adds a bool (int(spent))
Task 13b: minor (deferred): 'skipped: missing' progress row carries neither llm_calls nor meter (zero-spend by construction)
Task 15: minor (deferred, RECOMMEND-FIX): M1 station mark written without its record line (crash after rename, or before-copy write failing) → re-run records 'already marked', unmark removes the library mark and reports success, station keeps the batch's mark
Task 15: minor (deferred, RECOMMEND-FIX): M2 missing show dir / unreadable show.json silently drops a row from the mark plan (unsafe direction)
Task 15: minor (deferred, RECOMMEND-FIX): M3 --campaign-dir with --apply splits campaign state (campaign.frozen_slugs reads <root>/campaign) → refuse the combination
Task 15: minor (deferred): M4 FROZEN_NAME duplicates campaign.FROZEN_FILE; reselect assessment copies cli.py:3087-3090 verbatim (drift)
Task 15: minor (deferred): M5 six more private cross-module imports
Task 15: minor (deferred): M6 broad except Exception in _guard_holds/_plan_state
Task 15: minor (deferred): M7 test gaps (missing-pin refusal, resume after emcee stop, unmark emcee refusal)
Task 15: minor (deferred): M8 freeze takes any arm (no sha/fingerprint/coverage check; write-once)
POINTER T18: M9 runbook — reverse only the latest marking batch, or re-derive with a fresh batch afterwards; plus (e) reverse marking before restoring the backfill.
Task 15: minor (deferred): dead 'copy_problem = None' assignment (bulk_apply.py:756)
Task 15: minor (deferred): a recorded 'no station copy' can never clear within its batch, yet the listing says re-run until exit 0 — runbook must say what clears it (re-deliver, or accept by hand) → POINTER T18
Task 15: minor (deferred): dry-run stat-error branch of _station_state untested

## from orch-r2/ledger.md
Task 15b: minor (deferred): evidence (1) proves equal JSON not equal bytes; prefer evidence (2) / require sha(before)==before_sha256 when the line carries one (negligible: both writers canonical)
Task 15b: minor (deferred): _reversal duplicates write_mark's change rule + private station_mark._encode; a public station_mark.marked_bytes would remove drift; campaign._now/_parse private imports (T15 M5 family)
Task 15b: minor (deferred): _mark_station takes both at and batch_at (equal when set); _unmark_one still hashlib.sha256 inline beside _sha; dense for-header at unmark's before_dir loop
Task 15b: minor (deferred): 26 fork() DeprecationWarnings under Python 3.14 from untouched llama tests (pre-existing noise)
Task 15b: minor (deferred): a slug whose last line is 'not delivered' is never checked against the station (remote: ledger must lose its delivered entry) → POINTER T18 runbook, or extend _own_station_mark to not-delivered lines with a before copy
Task 15b: ⚠️ (for final review): unmark keeps a mark_added:false 'marked' line's station mark (Task 15 design; library still awaiting, consistent) — does the spec's "removed only where the manifest still equals what marking wrote" want a put-back there?
Task 15b: minor (deferred): fix-round tests carry unused locals (original, ws, cfg) and a partly used 7-tuple helper
Task 15b: minor (deferred): crash simulated by an exception mark_apply catches, not a process death (on-disk state equivalent)
Task 16: minor (deferred): famous packet covers every famous slug in the arm regardless of the wave's filters (repeats per wave)
Task 16: minor (deferred): lists exits 0 after dropping shows to stderr (mark dry run exits 1 on unplannable); --counts queue can silently shrink
Task 16: minor (deferred): _voiced runs and reports for shows --kind later removes (filter kind before station reads)
Task 16: minor (deferred): spot-check on a batch without progress.jsonl prints seed and exits 0; negative --n traceback; negative --limit drops tail rows
Task 16: minor (deferred): delivered-id set built inline three times
Task 16: minor (deferred): wave-check silently skips rows whose _plan_state is unreadable
Task 16: minor (deferred): an awaiting unreplayable row gets kind held (ShowReplay.briefing defaults to none)
Task 16: minor (deferred): test cannot tell the two re-selection guards apart (fixture triggers both)
Task 16: minor (deferred): import random inside cmd_spot_check
Task 16: ⚠️ (for T17): trial-report must read --counts JSON as written, incl. the "(none)" profile key
Task 16: minor (deferred): an empty mount-point dir passes is_dir (mark has the same gap); the configured station root /Volumes/media/lma-radio/delivered sits two levels below the mount, so an empty /Volumes/media fails is_dir — a shared sentinel/non-empty check would close it generally
Task 16: minor (deferred): wave-check checks os.access(R_OK), lists/mark do not (consistency nit)
Task 17: minor (deferred): a missing/unparseable five_hour_resets (failed meter read) reads as a crossed reset → block discarded; should be 'no usable measurement'
Task 17: minor (deferred): material-difference denominator (max) unpinned (mutant m3 survived); name it in the constant's comment
Task 17: minor (deferred): MIN_BLOCK_POINTS boundary (<) unpinned; d5 == 5 block should assert no bound
Task 17: minor (deferred): unreadable campaign record drops a show from revoice-list (stderr only) — list it in the trailing unknown group
Task 17: minor (deferred): presenter column (recorded voiced_by) and cost (current tts_now) can describe different voices after reassignment
Task 17: minor (deferred): queue kinds outside the known five silently cost 0; non-dict cell traceback
Task 17: minor (deferred): align_reproduced re-reads every block incl. discarded; a batch passed twice counts twice
Task 17: minor (deferred): revoice-list does not check the arm's sha/fingerprint against the pin
Task 17: minor (deferred, RECOMMEND-FIX before the trial is read): _spending_rows reads only each slug's last progress row, so an other-kind row that failed inside the window after spending, then re-ran outside it, hides its spend (probe: shows=20 delta5=10, no refusal) — read every progress line
Task 17: minor (deferred): the inclusive window boundary is unpinned (mutant M3 survived)
Task 17: minor (deferred): last-row collapse for the block's own kind — an earlier failed attempt's spend is in the delta but n counts the slug once (pre-existing)
Task 17: minor (deferred): align_reproduced tally includes refused (not-contiguous) blocks; 'not contiguous' line lacks the 'block ' prefix
Next: Task 18 (whole-branch review + CHECKPOINT C) waits for Shawn's A/B rulings and their follow-ups. Final review must triage deferred minors in all three ledgers; the RECOMMEND-FIX ones from orch-r2: T17 _spending_rows last-row-only (read every progress line before the trial is read); T15b ⚠️ unmark keeps a mark_added:false 'marked' line's station mark (Task 15 design — spec question); T16 empty mount-point dir passes is_dir (mark too; not exposed with the current station root).

## from orch-r3/ledger.md
Task 14b: minor (deferred): dry run can list a flag a recorded null-subject rule overrules (identity = kind+subject; (d) widens it); measured 0 overlaps on CP-A data → POINTER T18 runbook caveat
Task 14b: minor (deferred): dry-run totals can count two same-identity planned rules (merge_rules dedupes at apply) — dedupe record by _ident in _plan_one
Task 14b: minor (deferred): precedence today-vs-a and a-vs-b untested (a swap changes only the persisted note text); rule-(c) titles with _titles_rule None untested
Task 14b: minor (deferred): _basis next() without default; positional _BASES[i][0] indexing; _print_plan does filesystem I/O to spot rule-(c) shows
Task 14b: minor (deferred): "note": null now written into fix/triage/untitled overrules (brief-allowed; no byte-compare users)
Task 15c: minor (deferred): a non-held show newly held ONLY by a carried package flag gets the bare reason and reapply cannot clear it (0 rows today; B-90 measured stored_flags empty on all 89)
Task 15c: minor (deferred): _could_mark docstring "an arm row with a diff" stale; NEWLY_HELD used ~600 lines before its definition
POINTER T18: spec "Who gets marked"/"Marking skips" still list four triggers — add the fifth (Checkpoint B ruling) at the doc pass
Task 14c: minor (deferred): _NEVER_KINDS_A is dead (documentation only); test name test_rule_a_and_b_never_record_titles_unknown_song_or_research_rulings overstates (b); _NEVER_RULINGS clause redundant with still-listed (brief-mandated explicit)
Task RF: minor (deferred): pre-existing race — share unmounting between the root check and _station_copy_problem records terminal 'no station copy' (listed, exit 1, not retried); re-check root on 'no station copy'
Task RF: minor (deferred): _foreign_inside re-reads list.json without shape validation (share a _list_kinds helper); test helper _append_line duplicates _add_row
Task RF: minor (deferred): os.access(R_OK) branch unpinned (M11 survived); mid-batch test's _now stub rmtree on every call is fragile
Task RF: minor (deferred): commit 547b5cb7 message says 6345 passed (actual 6346)

