VERDICT: APPROVED

Reviewed e7a029e (33f44b4..e7a029e: CLAUDE.md, reapply.py +17, test_reapply.py +89) in snapshot `git archive e7a029e`, PYTHONPATH shadowing proven (`llama.__file__` -> snapshot). Reviewer model: Opus. No worktree files changed, no commits.

## Spec table (fw3-brief.md)

| Item | | Where |
|---|---|---|
| Drop on `briefing is None` + held + stored briefing + shipped-field diff | ✅ | reapply.py:148-161 (`briefing is None and flags and (json or md exists) and any(shipped_diff(...).values())`) |
| Uses `drop_stage_artifacts(ws, "brief")`, reports what it drops | ✅ | reapply.py:160; comment 153-157 and handback name briefing.json, briefing.md, package/manifest.json |
| `written` records `"drop:brief"` | ✅ | reapply.py:161 |
| Existing helper reused, named | ✅ | `replay.shipped_diff` (replay.py:185), imported reapply.py:28-29 |
| Unchanged when no stored briefing / nothing shipped moved | ✅ | guard conditions; tests (c) x2 |
| Write order vetting -> notes -> (drop) -> show.json; crash comment | ✅ | drop sits after briefing writes, before `if not flags`/show.json; comment 158-159. Drop test pins `["vetting.json","notes.json","drop:brief","show.json"]` |
| Test: held + title change + stored briefing -> gone, new titles, `written` lists drop | ✅ | test_reapply.py `test_a_held_outcome_with_changed_titles_drops_the_stale_briefing` |
| No-drop (a) failed fresh brief | ✅ | `test_a_failed_fresh_brief_is_not_dropped_even_when_titles_changed` |
| No-drop (b) reused briefing | ✅ | `test_a_reused_briefing_is_not_dropped` (forced via wrapped `compute_legs`; reuse+flags is unreachable by construction, compute_legs only reuses when flags == []) |
| No-drop (c) held, no shipped change | ✅ | two tests (carried package flag; real held fixture) |
| No-drop (d) cleared | ✅ | `test_a_cleared_outcome_is_not_dropped` |
| CLAUDE.md one sentence in reapply bullet | ✅ | CLAUDE.md:120-122 |
| Nothing extra changed | ✅ | 3 files only |

Do-not-retune grep over every +/- line of the diff (is_real_title, title_fraction, _TRACK_NUM_PREFIX, normalize_song, DEFAULT_ALIASES, GD_SHORTHAND, _RECOVER_*, tail-guard trio, junk trio, align_coverage_threshold, _ENUMERATED_MIN_*, _STRUCTURE_PREFIX, _FOOTNOTE_TAIL, lookahead): 0 hits.

Direction check: the change only ever removes a briefing (more LLM work at the eventual overrule, never a fewer-holds loosening). Verified the regeneration path: `fix --overrule` -> `_redo_show(..., "package")` -> `process_show` -> `run_brief`, which regenerates when `briefing.json` is absent (`should_run`) and runs `briefing_guard` via `generate_briefing`; `build_package` hard-fails without briefing artifacts, so no route ships without one.

## Findings

Critical: none. Important: none.

Minor
1. **Drop predicate is wider than "briefing stale".** `shipped_diff` also reports `title_source` and `structure.alignment`; `replay.briefing_reusable` (replay.py:237) explicitly excludes title_source ("the briefing never sees it"). A held replay that changes only a title_source (same text) or only the alignment mode drops a briefing that is still correct, costing one Opus brief at the eventual overrule. Safe direction; the brief asked for exactly this helper, so acceptable as is. If wanted: compare the broadcast fields `briefing_reusable` lists (titles, sets, segues, set_breaks, date, venue, city) — e.g. factor that list out of `briefing_reusable` into `broadcast_changes(o, n) -> list[str]` and use it in both places.
2. **`or ws.briefing_md.exists()` is unpinned** (my M6 survived). Behaviourally near-equivalent: an orphan briefing.md with no briefing.json is overwritten anyway when `run_brief` regenerates. Keep the `or` (it is tidier to remove both); no test needed, or add one row with only briefing.md.
3. `flags` in the condition is redundant (`briefing is None` implies `legs.brief == "none"`, which compute_legs yields only when flags are non-empty). Harmless defensive clause; fine.
4. CLAUDE.md:120-122 leaves one 120-char line in a ~80-col wrapped paragraph; cosmetic.
5. Not in scope, for the orchestrator: this fix does not remediate shows the finished reapply waves may already have written held with shipped changes and a stale briefing (a re-run compares against the already-new show.json, so diff is empty, no drop). Final review I4 argued G could not produce that case from predicted-list rows (digest check); if that argument is not already verified on the library, a read-only sweep of held shows whose `show.json` is newer than `briefing.json` and whose briefing fails `briefing_reusable`-style field checks would settle it.

## Extra check: dropping `package/manifest.json` — recommend KEEP

Evidence (read in snapshot):
- `catalog.derive_state` returns `held` before looking at delivered/manifest, so `status`/`show` state is unaffected; `llama show`'s stage table merely shows the manifest missing, which is accurate.
- `deliver_refusals`: a held show is refused with or without a manifest. Without one it says `not packaged` and `_deliver_pointer` prints `redo --from package` instead of `triage` — but that is already the message for every held show held before package (the common case), so no new behaviour class.
- Every route out of held drops the manifest anyway: overrule -> redo from `package` (drops it), accept-vague -> redo from `brief` (drops it), metadata/file edits -> redo from `gather` (drops it); reapply's own cleared path drops it ("a stale manifest must never short-circuit the package").
- Keeping it would be the hazard: the manifest lists the OLD titles/filenames and the package dir holds the OLD briefing copies. Any `process_show` without a force stage (e.g. `run resume` after a `fix --overrule --no-run`) would regenerate the briefing, then short-circuit `build_package` on the stale manifest and record the show as selected with an old-title package.
- Delivered + purged held show: `needs_audio_download` is True either way (audio gone); `purge_package_audio` runs only after a deliver, which a held show cannot pass; the re-deliver path is `redo --from package`, which drops and rebuilds the manifest regardless. emcee and transmitter read only the station copy under `[station] root` (emcee never imports llama; transmitter never imports either), which this change never touches.
- Undelivered held show with library audio: dry-run `needs_audio_download` now counts it as a download; `build_package` reuses same-named files, but titles changed so packaged filenames mostly change anyway. GB-estimate effect only.

## Mutation spot-check (snapshot copies under a private MROOT, PYTHONPATH shadowing proven per mutant, private PYTHONPYCACHEPREFIX; predictions logged before flipping)

| mutant | predicted test | caught by / SURVIVED |
|---|---|---|
| M2 (implementer's) drop whenever held, diff ignored | test_a_held_outcome_with_no_shipped_change_keeps_the_briefing | caught by predicted, plus ..._and_no_carried_flag_keeps_the_briefing and existing test_a_show_still_flagged_after_vet_is_written_held_with_no_briefing_or_package |
| M4 (unlisted) drop without `written.append` | test_a_held_outcome_with_changed_titles_drops_the_stale_briefing | caught by predicted |
| M5 (unlisted) `drop_stage_artifacts(ws, "package")` instead of "brief" | test_a_held_outcome_with_changed_titles_drops_the_stale_briefing | caught by predicted |
| M6 (unlisted) condition checks only briefing_json | none predicted | SURVIVED — near-equivalent (Minor 2) |

Implementer's M1/M3 claims not re-run; M1 is implied by M4/M5's test, M3's test asserts `"drop:brief" not in out.written` on a fresh failed brief with a retitled stored show, which bites as described.

## Suite

Snapshot, full: `3792 passed, 1 skipped, 8 deselected, 26 warnings in 126.04s` (matches the implementer's count). Snapshot and MROOT removed.
