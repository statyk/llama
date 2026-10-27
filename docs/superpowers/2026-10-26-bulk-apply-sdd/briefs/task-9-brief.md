### Task 9: `reapply` for packaged, briefed and delivered shows

**Spec:** "Re-processing" (reapply extended; purge; anchor; structure gate), "Known constraints" (show_unit), "The library side" (processed, skips). Strict surface 4. **Implementer: Opus.**

**Files:** Modify `reapply.py` (`reapply_show`, `ReapplyOutcome`), `cli.py` (`reapply` names form output, `--allow-download`); Test `test_reapply.py`.

**Interfaces:**
- Consumes: Tasks 2, 3, 5 (`destination_voiced`, `StationUnreadable`), 8.
- Produces: `ReapplyOutcome` gains `kind: str = "none"` (`fresh` | `reuse` | `needs-llm` | `label-only` | `none`), `audio: dict[str, int] = field(default_factory=dict)`, `align_reproduced: bool | None = None`. `reapply_show(..., with_gather_llm: bool = False, allow_download: bool = False, after_commit: Callable[[ShowWorkspace], None] | None = None)` (`with_gather_llm` is wired in Task 10; `after_commit` is Task 13's `record_after` hook). `llama reapply <name>... --allow-download` on the names form only (`--from-list` with it refuses: `--allow-download takes one named show`); it makes that show's reuse non-strict, as on `redo`/`fix` (Task 8); the names form prints the `--allow-download` hint line after a strict refusal.
- Flow (the order is the contract):
  1. Writes run inside `show_unit(ws, None)`; a dry run takes only `file_lock`. reapply's own audio/manifest undo and its `discard_aside`/`put_back` calls go (the unit does both).
  2. `rec = campaign.read_record(ws)` (`CampaignUnreadable` propagates). A last mark with start `select` → the re-selection skip string. For a non-held show only, a record that is not awaiting and has `processed` → `skipped: processed` (held shows keep today's behaviour). Then the existing digest check.
  3. Held shows keep today's `classify` path and outcomes.
  4. Non-held: `flags` → held commit (today's held writes, `drop:brief` rule included). No flags, no `visible_changes`, `legs.brief == "reuse"`, and NOT (the record is awaiting and the show is delivered and `destination_voiced(...) is False`) → `show.json`-only commit, outcome `label-only` when `shipped_diff` has any value else `unchanged`. Otherwise → brief (reuse or fresh) and package → `cleared`. Every station read before the commit (`destination_voiced`, the pairing check) raises `station_mark.StationUnreadable` for a missing or unreadable station dir or manifest; the voiced rider's purge after the commit keeps `purge_package_audio`'s own skip-and-warn.
  5. The structure gate (`_structure_changed(shipped_diff)` without `allow_structure_change` → `skipped: structure changed`) applies to every state.
  6. A delivered show that will package: `plan_reuse(..., strict=not allow_download)` and `check_pairs` BEFORE the fresh brief (in gather-LLM mode, before the recompute: Task 10).
  7. The first write of a packaged or delivered show is `write_anchor_if_absent`. `show.json` stays the commit marker; after it, `campaign.mark_processed(ws, held=bool(flags))`; then, for a cleared delivered show whose destination is voiced, `purge_package_audio(ws, station)` and an echo of its result; then `after_commit(ws)` when given, still inside the unit (a failure there restores the unit). `echo(f"{slug}: audio reused {r}, downloaded {d}")` after a package.
- [ ] **Step 1: Dry run** (existing tests asserting `skipped: not held` on a packaged show change under "reapply extended").
- [ ] **Step 2: Write the failing tests:**
  - `test_reapply_repackages_a_changed_delivered_show_from_the_station`: delivered unvoiced, changed title, fresh brief (fake) → `cleared`, audio copied from the station, no download, record processed with the new manifest's sha, anchor gone.
  - `test_label_only_commits_show_json_only`: no brief call, no package write, `package/manifest.json` byte-identical, outcome `label-only`.
  - `test_marked_unvoiced_unchanged_show_is_repackaged_for_redelivery` (Review Focus 4).
  - `test_voiced_unchanged_show_commits_show_json_only_and_clear_mark_then_works`.
  - `test_voiced_rider_purges_when_tracks_equal`: a cleared delivered show with a voiced destination whose tracks equal the station's → library audio emptied; tracks differ → kept.
  - `test_newly_held_delivered_show_keeps_an_anchor`: held commit, anchor present, `drop:brief` in `written`; a later `fix --overrule` re-packages from the station through the anchor.
  - `test_processed_and_reselection_rows_are_skipped`; `test_processed_held_show_is_not_skipped` (a held show with a processed record takes today's held path).
  - `test_after_commit_runs_inside_the_unit`: the hook sees the committed `show.json` while the show lock is held; a hook that raises restores every file and the outcome is a failure.
  - `test_reapply_allow_download_by_name_only`: a delivered show with no station dir → names form with `--allow-download` downloads and clears; `--from-list` with it exits 1 with the fixed string.
  - `test_failure_restores_every_file`: a package failure after the brief → every file outside `package/audio/` byte-identical (incl. `campaign.json`, no anchor), added audio gone.
  - `test_station_check_runs_before_the_brief`: unpaired delivered show → `StationUnpaired`, the fake brief provider has zero calls.
  - `test_held_show_behaviour_unchanged` **(pin)**: the existing held-path tests pass untouched apart from the dry-run list.
- [ ] **Step 3:** Run → FAIL. **Step 4: Implement.** **Step 5:** Full suite → PASS. Commit `feat(reapply): every state, inside show_unit, strict reuse, processed`.

---

