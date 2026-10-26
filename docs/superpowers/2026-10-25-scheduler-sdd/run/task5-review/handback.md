### Spec Compliance

**Compliant, with one test gap the brief asked for explicitly.** Every interface in the brief exists with the specified shape and behaviour:
- `interstitials.folder`, `row_dir`, `scan`
- `announce.render_time`, `render`, `ann_id`, `Form`, `text_for`, `Needed`, `needed`
- `InterstitialsConfig` (strict) on `TransmitterConfig.interstitials`, with a commented `[interstitials]` section in `DEFAULT_CONFIG_TOML`
- the `announcements` command with `--clock`, `--days` and `--export`

Nothing missing, nothing extra.

Checked against the named risks:
- **(a) scan.** A missing folder, a folder that is a file, and a permission error all return `[]` (`interstitials.py:270-273`). An `OSError` on one file skips only that file (`:285-291`). Zero-byte files, directories and dotfiles are skipped. Only `id-*.mp3` and `ann-*.mp3` are read. The quiet period is judged by mtime. `ann_id` is the part of the stem after `ann-`. `key` is `station.file_set_key(folder, [name])`. `meta` is `{role, ann_id, sizes}`, and `pieces.estimate_frames` reads `sizes` keyed by entry path. The folder stays invisible to `station.scan` (`test_interstitials.py:486-491` asserts `skipped == []`).
- **(b) render_time.** Probed outside the tests:
  - Newfoundland gives `8:30` / `4:30`, Nepal `4:45` / `12:15`, UTC `11` / `6:30`.
  - The DST-ambiguous 01:30 renders as `1:30 Eastern`.
  - Midnight and noon render as `12`; 24h midnight renders as `00:00`.
  - A negative microsecond value is correct.
  - Minutes appear only when that zone's minute is non-zero, zone by zone.
  - `time_format` is already a validated `Literal`, and the templates are validated by `clock.AnnounceConfig._templates`, so `str.format` cannot raise a `KeyError` at run time.
- **(c) needed().**
  - One-block forms are always produced for a titled X.
  - Two-block forms are produced only when the following occurrence is titled.
  - Untitled X gets nothing.
  - Results are de-duplicated by id and kept in time order.
  - Degraded or open-at-runtime blocks are correctly ignored here: the spec says "the text is derived from the clock alone", and a titled open block is announced.
  - The "+2 days" lookahead turned out *not* to be a truncation at the default span. I probed a two-block Saturday-only clock from each of the 7 weekdays with `--days 8`: all 8 ids every time. It also holds for a single weekly block at `--days 0.5`. The reason: `occurrences()` includes the occurrence in progress at `from_us`, and its following occurrence starts at that occurrence's `end_us`, at most 7 days out.
- **(d) the command.**
  - It is read-only apart from `--export`.
  - The live path uses `live_clock(Workspace(cfg.root), save=False)`, and `Workspace` has no constructor side effects.
  - A `--clock` read or parse failure raises `ConfigError`, a `TransmitterError`, so `main_cli` exits 1.
  - "Present" ignoring the quiet period is **correct, not a defect**. The spec's quiet period governs *airing*. This command decides what to *export for voicing*, and honouring the quiet period would re-export, and invite re-voicing, a clip voiced minutes ago. Mutant M10 confirms the test pins this choice.
- **(e) config.** `test_config.py` is green. The new section is comments only, and the model is strict.
- **(f) the render premise.** The test compares `render_show`'s return value with `render.planned_frames(...)`. `render_show` (`render.py:111`) returns the frame count read from the real encoded ADTS file, and it raises `FrameCountDrift` on its own internal mismatch. The assertion is therefore real, and an independent computation via `planned_frames`. It ran with ffmpeg present.

⚠️ What the diff cannot show: whether the later placement task calls `text_for` with the same (X, block after X) pairing. If it does not, ids listed here will never be chosen.

### Strengths
- `scan` is small and defensive in the right places: one `try` around `iterdir` and one per file, and the folder is never written to.
- `announce` is pure, derived from the clock alone, and `ann_id` is exactly as briefed. The id/text contract is easy to audit.
- The CLI test does real work. It derives the expected ids from `needed()` itself, plants one present clip, and asserts the exact exported file set and contents. Mutants M4 (export everything) and M10 (present honours the quiet period) both go red.
- The single-clip frame-count premise test exercises the real encoder path end to end.
- No noise: the focused tests pass under `-W error`.

### Issues

#### Critical
None.

#### Important
1. **`test_cli.py:382-416`: the "no `clock.last-good.toml` is written" assertion is vacuous, so `save=False` is unpinned.**
   - **What:** The test always passes `--clock`, so `live_clock` is never called. Its clock file also sits at `tmp_path/clock.toml`, not under `TRANSMITTER_ROOT`.
   - **Evidence:** In a scratch copy, mutant M5 (`save=False` → `save=True` at `cli.py:136`) **survived** (57 passed). The live-clock branch of the command, including the `note:` line, is untested.
   - **Why it matters:** The brief mandates this exact assertion. The command's read-only property is a stakes item: a listing command must not write the workspace. The code is correct today, but nothing would catch a regression.
   - **Fix:** Add an invocation without `--clock` that writes the clock to `$TRANSMITTER_ROOT/clock.toml`. Assert the same listing, and assert `clock.last-good.toml` does not exist afterwards. Optionally add an invalid live clock to pin the `note:` path.

#### Minor
1. **`interstitials.py:257-264`: a relative `[interstitials] dir` breaks the brief's `row_dir` invariant.**
   - **What:** The brief says `row_dir` returns "its absolute path string" when the folder is outside the station root, and that `Path(station_root) / row_dir` resolves back to the folder. With `dir = "clips"` and root `/nfs/station`, `row_dir` returns `'clips'`. `Path('/nfs/station') / 'clips'` is not the folder, which resolves against the cwd (probed).
   - **Why it matters:** A later plan row would store a path that render resolves somewhere else.
   - **Fix:** Return `str(Path(folder).absolute())` in the fallback, or reject a relative `dir` in `InterstitialsConfig` (the template already shows an absolute path).
2. **`interstitials.py:285-293`: three stats per clip where one would do.**
   - **What:** `p.stat()`, then `p.is_file()`, then `file_set_key` stats again. The quiet check and `sizes` come from the first stat; `key` comes from the third.
   - **Why it matters:** A clip replaced in between (an NFS write) is admitted as quiet with a key from the new file. Re-validation will likely catch it later, so the window is narrow.
   - **Fix:** Use `station.file_set_key_and_sizes(folder, [name])`, which yields the same key, plus `stat.S_ISREG(st.st_mode)`, so the quiet check, the size and the key all come from one stat.
3. **Untested brief behaviours (scratch-copy mutants survived):**
   - M8: the per-file `OSError` skip at `interstitials.py:290`.
   - M12: a directory named `id-x.mp3` must be skipped.
   - M9: `needed()`'s `x.nominal_us >= until` bound.
   - Untested, no mutant run: `--clock` with a bad file exiting 1.

   Each is a cheap test. The `OSError` case can monkeypatch `Path.stat` for one name.
4. **`cli.py:140-144`: no station root and no `[interstitials] dir` lists everything as `missing` without explanation.** The same happens with a folder that does not exist. A quiet empty pool is right for `scan`. For this operator command, a one-line `note: no interstitials folder (...)` on stderr would prevent a confusing "everything missing" reading. Optional.
5. **⚠️ Spec observation, to escalate before the operator voices any clips (not an implementer defect: the brief's rule is followed literally).**
   - **What:** When the occurrence after X is X itself, the two-block forms read badly on air. For a single daily block, `needed()` yields `"Stay tuned for Funk at 7 Eastern, 4 Pacific, followed by Funk at 7 Eastern, 4 Pacific."`. The test pins this as 4 ids ("a daily block follows itself"). A weekday rotation behaves the same way: Funk on Monday is followed by Funk on Tuesday, and the next-day time is read as if it were today.
   - **Why now:** Ids are a contract. Deciding this after clips are voiced retires them.
   - **One candidate rule:** produce two-block forms only when `y.block.name != x.block.name`. That is an operator call.
   - **Related limit:** with zones whose DST rules differ (e.g. Eastern plus UTC), texts change at DST transitions. The spec's "at most four per block start" then becomes per DST season, and an 8-day listing only covers the current season. This is inherent to the spec, and harmless with the default zones.

### Assessment
**Task quality:** Needs fixes

**Reasoning:** The implementation matches the brief and the spec on every named risk. Time rendering is correct across offset and DST edge cases, `needed()`'s window is complete at the default span, and the command is read-only. The one Important item is test-only but brief-mandated: the read-only/`save=False` property of the live-clock path is not pinned (mutant M5 survives). Fix it with a no-`--clock` invocation. The Minors (relative `dir` breaking `row_dir`'s invariant, the single-stat key, small test gaps) are cheap and can ride with that fix. Minor 5 is a spec question for the operator, not a code change for this task.

Evidence: probe and mutation output are in `task5-review/task5-review.log`. The scratch copy is at `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-scheduler/6a271170-52a3-49a3-b4db-a9d5cd08acfc/scratchpad/t5mut`; `transmitter.__file__` and `tests_transmitter.__file__` were proven to resolve inside it. Mutants were run from an empty cwd with `-B` and `PYTHONDONTWRITEBYTECODE=1`:

| Mutant | Result |
|---|---|
| M1, M2, M3, M4, M6, M7, M10, M11 | caught by the predicted tests |
| M5, M8, M9, M12 | survived |
