# t12-rev: Task 12 review (5c78650..5a89be0, 3 commits)

### Spec Compliance

- ✅ **Spec compliant**, checked against the brief's interfaces and spec 5.4. Evidence:
  - `ReusePlan`, `plan_reuse`, `set_aside`, `reuse_into`, `put_back`, `discard_aside` and `ASIDE_DIR` all match the brief's signatures (audio_reuse.py:58-180).
  - **Pairing** is by index, needs equal length and an equal title at every index, and is made against the plan-time show.json (audio_reuse.py:85-93). Without a readable show.json both pairings are `{}` while `library_names` is still read (`:100-112`).
  - **Keep-or-aside** comes only from `reuse.library_names` (the plan-time manifest) compared with the target show's packaged names, plus whether `package/audio/` holds any file (package.py:376-381). It never uses the show.json the unit started with. My full (i2) mutant (below) confirms this.
  - **Station copy** is tried only after the library candidate (audio_reuse.py:142-146), and only for a dest that is still missing (package.py:390-396).
  - **Length check**: a copy is used only when its read duration and the cached metadata `length` are both known and within `DURATION_TOLERANCE_S` (audio_reuse.py:140-152). Anything else downloads exactly as today (package.py:397-399).
  - **show_unit**: entry deletes a leftover aside right after the `.txn/` check, and refuses if it cannot (show_unit.py:275-278). `_tracked_files` skips `ASIDE_DIR` (`:246`). On failure the order is restore → put_back → discard (`:302-304`); on success, discard_aside → discard_snapshot (`:306-307`).
  - **`reuse=None`**: the only change on that path is that `files` is split out of the `md5s` comprehension (package.py:373-374). The download branch is unchanged when `placed is None`, and `test_build_package_without_reuse_never_sets_aside` pins it.
- **Global-constraint grep**: `DURATION_TOLERANCE_S` occurs 6 times in the diff, all as use or context. No +/- line touches `DURATION_TOLERANCE_S = 5.0`, `purge_package_audio`, `SHORT_FRACTION_OF_MEDIAN`, `MIN_PLAUSIBLE_SEC`, `is_real_title` or `_TRACK_NUM_PREFIX`.
- **Every test the brief names is present.** Review Focus 5: test_audio_reuse.py:561. Review Focus 6: test_stage_package.py:907.
  - One small location deviation: the brief puts `test_same_title_renumbered_never_inherits_the_wrong_audio` in test_audio_reuse.py (it is not marked as another file), but it lives in test_stage_package.py:869. That is harmless.
- ⚠️ **Cannot verify from the diff**: what happens when Task 13 threads `reuse` through `_redo_show_locked` and `reapply_show`. See Important 1: whether a unit can reach two non-in-place re-packagings is a Task 13 property.

### Strengths
- **The aside is in the right place.** It sits in `<show>/.audio-aside/`, outside `package/` and on the same filesystem, so `os.replace` is atomic. `_tracked_files` skips it, so restore step (a) cannot delete it (the implementer's mutant showed that).
- **`reuse_into` copies and never moves** (dot-temp, then `os.replace`, with the temp removed on `BaseException`, audio_reuse.py:153-159). The aside survives for a put-back, and the station file is only read. Mutant m3 (copy → move) is caught by both the station-unchanged assertion and the put-back test. Restore step (c) also deletes a leftover dot-temp, because `_audio_names` counts dotfiles.
- **The failure tests are strong.** `test_failed_unit_puts_aside_audio_back_under_old_names` compares `tree_bytes(ws.dir)` with the audio included, so names, bytes and manifest are all checked. The mid-`set_aside` KeyboardInterrupt test (test_show_unit.py:751) covers the partial-move case.
- **The fake-audio design** (bytes carry the source filename and length, and survive `tag_audio`) lets tests assert *which source* sits under each name. That is exactly the property this strict surface needs.
- **Extra guards**: `_manifest_tracks` refuses a manifest filename that is not a bare name, so a station manifest cannot point outside `audio/` (audio_reuse.py:78-81). Entry refuses when an aside cannot be removed, so a stale aside can never be put back.

### Mutation checks (scratch copy from `git archive 5a89be0`)
Each mutant ran in its own copy under `PYTHONPATH` shadowing (sentinel proved in each) with a separate `PYTHONPYCACHEPREFIX` and `-p no:cacheprovider`. Each ran the three task test files (55 tests at base). The failing test was predicted before each run.

| mutant | predicted | result |
|---|---|---|
| m1, the **full (i2)**: `library_names` taken from the plan-time show.json's packaged names instead of the manifest | `test_audio_without_a_library_manifest_is_set_aside` | **caught**, by it and 4 plan tests |
| m2: station tried before library | `test_reuse_into_tries_the_library_before_the_station` | caught (1) |
| m3: `reuse_into` moves instead of copying | reuse-order test + failed-unit put-back | caught (3, the station test too) |
| m6: `put_back` before `restore_snapshot` | predicted to SURVIVE (equivalent) | survived. Restore step (c) only deletes names outside the snapshot's audio list, so the two orders give the same tree. The brief's ordering is correct but not load-bearing today. **No finding.** |
| m7: tolerance `>` → `>=` | `test_duration_mismatch_or_unreadable_falls_back_to_download` | caught (1) |

The implementer's (i2) mutant was approximate. m1 is the real one, and it is caught. The keep-or-aside decision does come from the plan-time manifest names and what is on disk.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)

**1. Latent: `set_aside` silently overwrites an existing aside entry, so a second re-packaging inside one unit breaks the failure guarantee and can put the wrong audio under an old name.**
- **Where:** audio_reuse.py:127-129 (`os.replace(p, aside / p.name)` onto an existing aside file), together with `reuse_into` consulting `<aside>/<plan.library name>` whatever call populated the aside (`:143-144`).
- **Probe (unmodified code, scratch):** a packaged show `[A(a), Jam(j1), Jam(j2)]` gets two `plan_reuse` + `build_package(reuse=)` passes with changed lists inside one `show_unit`, then a `LlamaError`. After the "restored" failure, `package/audio/` holds `03 - Jam.mp3` with **j1's** audio, while the restored manifest and show.json say track 3 is j2. It also holds two unit-added strays, `02 - Crowd.mp3` and `04 - Jam.mp3`. The second `set_aside` moved build-1 files over the pre-unit originals of the same name, and `put_back` runs after restore step (c), so it re-introduces them.
- **Reachability today: none.**
  - Task 12 threads no caller.
  - The only double `_redo_show_locked` in one unit is `fix --untitled` (cli.py:1950-1956). Its second pass is `--from brief` with the same show.json, so `in_place` is True and `set_aside` does not run again.
  - But nothing in the module enforces "one aside per unit", and Task 13 is about to thread `reuse` through `_redo_show_locked` and `reapply_show`. The same root cause lets an in-place build that finds a dest missing draw from an aside that a different plan populated (the implementer's own concern 2).
- **Fix (cheap):** make the aside single-use. `set_aside` raises `LlamaError` when `ASIDE_DIR` already exists, which turns the hazard into an ordinary restore, because the original aside is intact. Alternatively, `plan_reuse` refuses when an aside exists. Also, `build_package` should hand `reuse_into` library candidates only when this call did the `set_aside`. Add a test of two re-packagings in one unit.

#### Minor (Nice to Have)

**1. Keep-in-place trusts packaged names alone, so a changed source at an index with an identical title keeps the old file.**
- **Where:** package.py:377-378. Probe: old `[A(a), Jam(j1), B(b)]`, new `[A(a), Jam(j0), B(b)]`. The names are identical, `in_place` is True, and `02 - Jam.mp3` ships j1's audio as j0's track, unflagged within tolerance.
- **This rule is plan-mandated.** It needs every title and index equal with a different source file. The bulk apply only inserts files, so it cannot reach this; a hand `fix` that excludes one file and includes a same-titled one at the same position could. It is within the spec's stated worst case ("re-shipping audio this show already packaged").
- **One-line strengthening:** also require `all(reuse.library.get(t.filename) == n for t, n in zip(show.tracks, names))`. The unchanged-list pin, the purged-library case and the retitle case all still behave the same under it.

**2. Docstring gap on a failed put-back.** show_unit.py:196-202, limitation 5, names SIGKILL and a failed restore but not a failed `put_back` (an OSError mid-loop). That also leaves `.txn/` and a partial aside for the next entry to delete, and its exception masks the original (the original survives only as `__context__`). Add it to the sentence.

**3. Test-file style.** test_show_unit.py:715-726 and test_stage_package.py:826-837 append mid-file imports with `# noqa: E402`; `from pathlib import Path` is imported mid-file too. This is cosmetic; moving them to the top of each file would be cleaner.

**4. `plan_reuse` catches broadly** (`except Exception`, audio_reuse.py:100-103). This is intentional (an unreadable show.json gives empty pairings, which is the safe direction), but `(OSError, ValueError, pydantic.ValidationError)` would not hide a programming error. Low priority.

### Assessment

**Task quality:** Needs fixes. The fix is small: Important 1 only.

**Reasoning:** The module, the `build_package` hook and the unit's set-aside / put-back match spec 5.4 and the brief. `reuse=None` is unchanged, the station copy is only read, and every keep, aside, tolerance and put-back mutant I ran is caught. The one gap is that the aside is not single-use. A second re-packaging in one unit, which nothing does yet but Task 13 is about to wire, would make a failed unit restore the wrong audio under an old name. A guard of a few lines plus one test closes it.
