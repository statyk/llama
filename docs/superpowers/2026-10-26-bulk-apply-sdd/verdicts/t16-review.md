# t16-review (Task 16: wave lists, wave check, spot checks, famous-shows packet), range a2d5122d..928b784b

### Spec Compliance
- ❌ Issues found:
  - **The voiced exclusion fails open when the station is unmounted or unconfigured.** `scripts/bulk_apply.py:1287-1304` (`_voiced`) treats `station_root is None` as unvoiced. It also treats an ENOENT under the station root as "no station copy", which means unvoiced. `cmd_lists` (`:1364-1422`) never checks that the station root is mounted. So a missing mount makes every voiced delivered show read as unvoiced, and the brief's "never ... voiced ... without `--include-voiced`" no longer holds. `mark` (`:1136-1139`) and `wave-check` (`:1428-1432`) both refuse in this case; `lists` does not. Details under Important 1.
  - Everything else in the brief is implemented:
    - The pin and arm-sha gate, plus the fingerprint check (`:1367-1378`).
    - The doc shape and slug order (`:1410-1415`, `select_wave` iterates `sorted(rows)`).
    - The listing rule: awaiting fix with start `gather`, or label-only with no record, or `newly-held` (`:1325-1346`).
    - The exclusions: processed, re-selection by both `reselections.json` and the last mark's `select`, famous, and voiced (`:1318`, `:1331-1333`, `:1406-1407`).
    - Kind order: needs-llm, then held, then label-only, then briefing (`:1277-1284`).
    - `--profile` matches `provenance.profile` exactly; `--state` uses `_plan_state`.
    - `--counts` prints `{profile: {kind: {unvoiced, voiced}}}`.
    - `wave-check` matches the brief: a readable root, `read_station_manifest` per delivered row, the summed `audio/*` sizes, and `needed + 20e9 > free` as the refusal (exit 2, via `StationRefused(LlamaError)`, caught at `:1572`).
    - `spot-check`: a seeded sample of the `cleared`/`held` rows, with the seed printed. The before side reads `<batch>/snapshot/shows/<slug>/show.json`. I checked that path against `batch_snapshot.py:7,192` (`<snap>/shows/<slug>/`) and `cli.py:4236` (`batch / "snapshot"`), and it matches the real layout. The outcomes match `reapply.py:64-68,391`.
  - The orchestrator's decisions:
    - **(a) is implemented correctly.** `read_record` plus `awaiting_fix` is equivalent to `is_awaiting`. An unreadable record is reported with the exact Contracts string, which comes from `campaign._unreadable` (`campaign.py:81-85`), and the show is not listed.
    - **(b) is correct only while the station root is mounted.** See Important 1.
    - **(c) is implemented correctly.** `row_label_only` (which calls `row_visible_changes`) is only reached when `outcome not in _NO_DIFF` (`:1338`). `_row_kind` is guarded by `stored is not None` (`:1282`), and `_famous_packet` by `_NO_DIFF` (`:1270`).
- ⚠️ Cannot verify from the diff alone:
  - Whether Task 17's `trial-report` reads the `--counts` JSON as written. That includes the `"(none)"` profile key for shows with an unreadable or absent provenance profile.
  - Whether the runbook's `--counts` call should include label-only and held kinds. They are emitted as separate kinds, so the consumer can weight them.

### Strengths
- **One selector feeds both paths.** `select_wave` is shared by the list and `--counts`, so the projection queue and the waves cannot drift apart.
- **No unreadable input is ever treated as "no record".** An unreadable campaign record, an unreadable `show.json` and an unreadable station copy all go to stderr and never into the list. That is the safe direction, and it matches Review Focus 5.
- **Pointer (c) is applied consistently** at all three call sites: selection, kind and the famous packet.
- **`wave-check` treats a stat or read error on the station audio as a refusal.** Only a missing `audio/` dir counts as 0 bytes (`:1446-1452`).
- **`spot-check` is reproducible.** The slugs are sorted before `Random(seed).sample`, and the test checks this by comparing two runs with the same seed byte for byte.
- **RED evidence is present.** All 11 tests failed first (log lines 904-915).
- **The constants the global constraints mark untouched are unchanged.** I grepped the diff for `DURATION_TOLERANCE_S`, `STOP_AFTER_LLM_FAILURES`, `SHORT_FRACTION`, `briefing_reusable` and `purge_package_audio`: no hits.
- **The written list is accepted by `reapply.load_list`** (`test_list_feeds_reapply`).

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **`scripts/bulk_apply.py:1287-1304` and `cmd_lists` `:1364-1422`: an unmounted or unconfigured station root lists voiced shows as unvoiced.**
   - **The failure.** With the station root missing, `_station_copy_problem` gets ENOENT, which reads as "no station copy", which reads as unvoiced. With `delivery_path` unset, `_voiced` returns False outright. Either way, voiced delivered shows land in the wave list with exit 0 and no warning.
   - **Measured.** I ran a probe at `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-bulk-apply/6d6081a6-72bc-4b0b-afbd-ff5351b19e6a/scratchpad/t16/probe_test.py`. It builds the test's `_world`, renames the station dir away, and runs `lists`. The result was rc 0 with rows `['famous', 'fresh', 'label', 'newly', 'reuse', 'unvoiced', 'voiced']`.
   - **Why it matters.**
     - This is exactly the mount-drop scenario the spec guards against elsewhere.
     - The spec's design call is that voiced shows are re-processed only when Shawn schedules their re-voice.
     - Nothing downstream catches it. `wave-check` does not look at voicing, and reapply accepts a voiced delivered show as a "rider" (`reapply.py:292-300,383`). So a list built while the mount was down, then run after a remount, re-processes voiced Voxtral shows. That spends LLM on fresh briefs and copies their audio back into the library.
     - The `--counts` projection miscounts in the same way: voiced shows become unvoiced.
   - **Fix.**
     - In `cmd_lists`, refuse as `mark` does: `no delivery_path in config`, and `station root … is not mounted or not a readable directory`.
     - Add a test that lists with the station root missing, expecting exit 2 and no list written.
2. **`scripts/test_bulk_apply_lists.py:549-560` (`test_famous_shows_go_to_a_packet`) never tests the packet's after side.**
   - **The failure.** The fixture rows from `_row` carry `filenames` but no `titles`, `sets` or `segues`, so every after title is `None` and every line is starred. `render_side_by_side` also never compares filenames, so the comment "t2 -> t9 starred" is wrong.
   - **Measured.** A probe at `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-bulk-apply/6d6081a6-72bc-4b0b-afbd-ff5351b19e6a/scratchpad/t16/probe2_test.py` monkeypatches `ba._row_side` to return `[]`, an empty after side. The test still passes.
   - **Why it matters.** The packet stands in for the structure gate on the famous shows; Shawn hand-checks from it. Its wiring to the arm's `titles`, `sets` and `segues` (`:1233-1234`) is pinned by nothing.
   - **Fix.** Give the famous row explicit `titles`, `sets` and `segues` that differ from `show.json` at one known index. Assert the exact `before->after` substrings on that line, and assert that an unchanged index is not starred.

#### Minor (Nice to Have)
1. **The famous packet covers every famous slug in the arm, regardless of the wave's filters** (`:1418-1421`, `_famous_packet` called on all `famous`). Verdict on the implementer's concern 3: acceptable but noisy. Runbook step 8 passes `--famous` on every per-profile wave, so each wave's packet repeats the whole list, including shows already processed or outside the profile. Consider limiting it to famous slugs that would otherwise pass this wave's selection and filters.
2. **`lists` exits 0 when it dropped shows to stderr** (an unreadable campaign record, `show.json` or station copy; `:1394-1396`). The `mark` dry run exits 1 on unplannable shows (`:1186`). A `dropped N show(s), see above` line, or a non-zero exit, would keep a dropped show from going unnoticed. This matters most for `--counts` piped to a file, where the queue silently shrinks.
   - Verdict on the implementer's concern 4: dropping a show with an unreadable station copy even under `--include-voiced` is right. Reapply would refuse it as `station copy unreadable` anyway, and the show stays awaiting fix. The only gap is the silent exit code.
3. **`_voiced` runs, and reports problems, for shows that the `--kind` filter removes afterwards** (`:1359-1360` vs `:1392-1393`). Applying `--kind` inside `select_wave`, before the station reads, avoids extra station I/O and stderr noise about shows outside the slice.
4. **`spot-check` on a mistyped `--batch` path** (no `progress.jsonl`) prints only `seed: N` and exits 0 (`:1466-1470`). It should refuse a dir with no progress file. A negative `--n` raises an uncaught `ValueError` traceback; a negative `--limit` on `lists` silently drops the tail rows (`picked[:-1]`).
5. **The delivered-id set is now built inline three times**: `cmd_mark` `:1162`, `select_wave` `:1314`, `cmd_wave_check` `:1436`. A small `_delivered_ids(root)` helper would serve all three.
6. **`wave-check` skips any row whose `_plan_state` is `unreadable`** (`:1442`) without saying so. A delivered show whose provenance cannot be read then gets no station check and adds no bytes. It should print or refuse.
7. **An awaiting `unreplayable` row gets kind `held`** (the `ShowReplay.briefing` default is `"none"`, `replay.py:716`). The label misleads, though reapply would fail the row anyway. Mapping `_NO_DIFF` outcomes to their own kind, or reporting them, would be clearer.
8. **The test can't tell the two re-selection guards apart.** The `resel` fixture is both in `reselections.json` and marked `select`, so neither exclusion path (`:1318` vs `:1333`) is pinned on its own.
9. **Warnings in the full-suite output.** The 26 `DeprecationWarning: ... fork()` lines all come from pre-existing tests (`test_atomic_write`, `test_concurrency`, `test_ledger_concurrency`, `test_locks`, `test_sessions`), not from this task.
10. **`import random` sits inside `cmd_spot_check`** (`:1463`); it belongs with the module imports.

**Verdicts on the implementer's concerns:**
1. **`wave-check` refuses (exit 2) a delivered row with no station copy: correct.** The brief requires every delivered row's manifest to read. The spec treats a missing dir as `station copy unreadable` for delivered shows, and reapply would refuse the show anyway, so refusing the wave up front is right.
2. **`--counts` excludes famous slugs and honours the filters: acceptable.** The runbook's `--counts` call passes no `--famous` and no filters, so it covers the whole awaiting queue as the brief asks. Re-selections are excluded, which the spec allows ("The 17 re-selections are not measured"). Label-only and newly-held shows are included as their own kinds, which goes slightly beyond "awaiting, unprocessed" but is harmless because the kinds are separate.
3. **The famous packet covers every famous slug in the arm: acceptable, but noisy.** See Minor 1.
4. **An unreadable station manifest or stat error drops the show, even with `--include-voiced`: correct.** See Minor 2 for the exit code.

### Assessment
**Task quality:** Needs fixes

**Reasoning:** The selection, kind, wave-check and spot-check logic match the brief, and the orchestrator's decisions are applied consistently. Two gaps remain. `lists` fails open on an unmounted or unconfigured station root, so voiced shows reach a wave list, which the spec's design call forbids; this was measured. The famous-packet test pins nothing about the after side that Shawn's hand-check relies on, which a probe confirmed.
