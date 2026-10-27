# Task 6 review: `llama clear-mark` (+ station encoding scope addition)

Reviewer: Opus. Range f53a3931..003a5404 (one commit, 003a5404). Read-only; nothing staged or committed.

### Spec Compliance

- ✅ Spec compliant. Brief, Contracts and the spec's "Clearing without re-delivery…" bullets are all met. Checked against the code:
  - Refusal order, exact strings, exit 1 and nothing written all match the brief: cli.py:2906-2954. `delivery_path` is checked before the lock. Unreadable (StationUnreadable), not marked, unvoiced (`dj_audio` null), not processed since the mark, held, sha≠record, differences without the flag, and `emcee_running()` last, just before the write.
  - "Processed after `marked_at`" uses the station's `marked_at` as well as the record's last mark (cli.py:2880-2892), following the spec's literal wording. It only refuses more often.
  - The sha test treats a held-processing null sha, a changed manifest, or an unreadable manifest as "changed" (cli.py:2942-2946). The overrule redo still qualifies through `campaign.after_package` (test_processed_then_overruled_still_clears).
  - The comparison is raw JSON through `station_mark.manifest_differences` (Task 5's COMPARED set, which matches the spec's field list).
  - The station write goes through marking's writer (`station_mark.clear_mark`). The outcome is recorded after that write succeeds (cli.py:2956-2962). The fixed string `mark cleared; the voicing is kept` is printed, plus `change accepted: <names>`.
  - Purge: the equal case uses deliver's three messages through the shared `_echo_purge` (cli.py:2700). The accepted case prints `library audio kept (track lists differ)` on catalog's track-list skip (cli.py:2977-2981).
  - It runs under the show lock only, with the campaign write inside it, so lock order is unchanged. It imports nothing from emcee.
- ✅ Scope addition (encoding). `station_mark._encode` is now `json.dumps(data, indent=2) + newline-follows-input`. This is exactly emcee's `package_io.rewrite_manifest` (`json.dumps(data, indent=2) + "\n"`, emcee/package_io.py:83). It is also llama's `write_artifact` (`json.dumps(_to_jsonable(data), indent=2)`, no newline; workspace.py:41-44), and `_to_jsonable` dumps models with `mode="json"` and no ensure_ascii override. The pin `test_mark_then_clear_reproduces_the_writers_bytes[emcee|llama]` covers a non-ASCII title: mark then clear comes back byte-identical for both writers. **Nothing differs.**
  - Extra evidence (my own read-only check of the live station; reads are allowed): all 2786 `/Volumes/media/lma-radio/delivered/*/manifest.json` round-trip byte-identically under the new `_encode`, with the newline following the input. There are 0 mismatches and 0 unreadable. No live station manifest contains non-ASCII bytes.
- ⚠️ Cannot verify from this diff: Task 9's flow (`test_voiced_unchanged_show_commits_show_json_only_and_clear_mark_then_works`, plan :371) feeds clear-mark a show whose `package/audio/` was purged at delivery. That path will print `warning: kept library audio for <slug>: already purged` on every successful equal clear. The text is deliver's own and harmless, but it reads as a warning on the normal path. Whoever owns Task 9 should decide whether "already purged" stays silent there.

### Strengths

- Strict-surface error handling is careful:
  - An OSError from the station write becomes a clean exit 1. The message re-reads the station and says whether the mark is still there (cli.py:2956-2959, `_station_state`).
  - A failed record write puts the station mark back with a sha-guarded `put_back`, and says what to check by hand if that fails too (cli.py:2961-2973). This is tested: station bytes are identical afterwards.
- `_refused` checks every refusal properly: the station tree, record bytes and whole library tree are byte-identical, not just the exit code.
- The tests exercise the real `catalog.purge_package_audio` in the equal and accepted cases (only the skip/partial message tests stub it). `test_accept_change_clears_and_keeps_library_audio` therefore pins catalog's skip text, which `_PURGE_SKIP_TRACKS_DIFFER` depends on.
- Splitting out `_echo_purge` is a behaviour-identical refactor of `_purge_after_delivery` (diff lines 27-43).
- The autouse `emcee_running` stub removes the `ps` flake the implementer hit on the first full run, and the two emcee tests opt back in.
- The implementer's mutants M1/M3/M4/M5 had named predictions, and M2 was correctly argued equivalent.
- Untouched names: I grepped the diff for the junk constants/rule, `DURATION_TOLERANCE_S`, `audio_reuse`, `purge_package_audio`, `STOP_AFTER_LLM_FAILURES`, `load_list`, `briefing_reusable`, the piece-3 constants, emcee imports and `class Manifest`. `purge_package_audio` appears only as call sites (diff :29-30, :163) and test stubs. catalog.py, models.py, emcee and transmitter have no diff.
- Targeted run: `./.venv/bin/python -m pytest packages/llama/tests/test_clear_mark.py packages/llama/tests/test_station_mark.py -q` → 47 passed, with no warnings. `llama.__file__` resolves inside the worktree.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **The gap between the station write and the record write is not covered** (cli.py:2956-2962). A SIGKILL or Ctrl-C after `clear_mark` and before `add_clear` leaves the station cleared and the record with no `clears` entry. Library audio is also left unpurged. A re-run then refuses with "not marked; nothing to clear", so nothing completes the record or the purge. Nothing reads `clears` today (grep: only campaign.py:179 writes it), so the cost is a missing audit line and some leaked disk space. Fix: document it as a known limitation in Task 17's CLAUDE.md / open-gaps list, or have a "not marked" refusal note when the record's last processing has no matching clear.
2. **Two raw exceptions can escape as tracebacks** before anything is written:
   - `campaign.manifest_sha256` catches only FileNotFoundError, so EACCES/EIO on the library manifest propagates (cli.py:2944).
   - `station_mark.emcee_running()` → `campaign_gate.ps_lines()` uses `check=True`, so a failing `ps` raises CalledProcessError (cli.py:2951).
   Both are safe, since they come before any write, but the user sees a traceback instead of an error line. Fix: wrap them into LlamaError, or note it.
3. **Only part of the refusal order is pinned.** Tests pin awaiting-before-held (test_awaiting_is_checked_before_held) and emcee-last. Swapping held↔sha or sha↔differences would pass every test: in test_held_refuses the manifest is unchanged, and test_library_changed_since_processing_refuses edits only `briefing.vetted`, which is not compared. One test each, with both conditions true, would pin the brief's order.
4. **The compared station bytes are not bound to the bytes cleared** (cli.py:2932 reads, cli.py:2956 re-reads inside `clear_mark`). Between them, `station_mark.clear_mark` works on whatever is on disk at that moment. The risk is small: only emcee (dj blocks only, never a COMPARED field) and llama-under-the-show-lock write there, and the emcee check runs right before. Task 5's API takes no `expect`, so passing the read bytes would be a Task 5 change. Noted, not required.
5. **Untested path:** the both-failed message ("the station mark could not be put back … check both by hand", cli.py:2968-2971) has no test.
6. **Style:** `_processed_since_mark` calls the private `campaign._parse` (cli.py:2887-2891). `_PURGE_SKIP_TRACKS_DIFFER` duplicates catalog's literal (cli.py:2877); a test pins it, but a named constant in catalog would be cleaner. The constraint is to leave the purge's verification untouched, not its module.

### Assessment

**Task quality:** Approved

**Reasoning:** All eight refusals, the record-after-write ordering, the put-back on a failed record and both purge outcomes match the brief and spec. Each is pinned by a test that checks the station, record and library trees are byte-identical. The encoding change reproduces both writers exactly, confirmed on all 2786 live station manifests. The remaining items are minor robustness and coverage gaps on paths that write nothing, or on an interrupt window, where the cost is an audit line.
