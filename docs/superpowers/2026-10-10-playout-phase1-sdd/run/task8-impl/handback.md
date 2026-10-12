# Task 8 handback (task8-impl) — Status: DONE

## Implemented
- `packages/transmitter/src/transmitter/render.py`: verbatim from the brief. `FileSpan`, `ShowLayout`,
  `show_layout` (clip<->track and clip<->clip joins get `pause_samples`, track->track 0, padded to whole
  frames), `planned_frames`, `RenderSettings` + `from_config`, `file_gain` (linear; tracks use the show's
  track-set I/TP vs music target, clips their own I/TP vs speech target), `render_show` (key and file-set
  check -> RenderError "does not match"; per-file decode, `np.clip(pcm * gain, -1, 1)` into a new array,
  silence for pauses and the final pad; decoded-count mismatch -> RenderError "the package changed";
  explicit `enc.close()` on success, `enc.abort()` on any BaseException; frame count from
  `adts.frame_offsets` -> FrameCountDrift and unlinks the output on mismatch).
- `packages/transmitter/tests_transmitter/test_render.py`: verbatim from the brief (8 tests).
- No unused imports in either file; every annotation name is imported.

## TDD evidence
- RED: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_render.py -q` ->
  `ImportError: cannot import name 'render' from 'transmitter'` (collection error). Expected: module not
  yet created (brief predicted ModuleNotFoundError; `from transmitter import render` surfaces it as ImportError).
- GREEN: same command -> 8 passed. `transmitter.__file__` resolves inside this worktree.

## Test results
- Python 3.14 / ffmpeg 8.1.1: test_render 8 passed; tests_transmitter 154 passed.
- CPython 3.11 (`./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider`): 154 passed.
- Debian 12 gate (`packages/transmitter/scripts/test-in-debian12.sh`, background, chunked poll, rc 0):
  `ffmpeg version 5.1.9-0+deb12u1`, `Python 3.11.2`, 154 passed in 5.98s.
- Full repo suite (`./.venv/bin/python -m pytest -q`): 2303 passed, 7 deselected.

## Measured (ffmpeg 8.1.1, segue test package)
frames 411 (== planned); files clip 44100, track 130001, track 134599, clip 44100 (tracks sum to exactly
6.0 s: gapless MP3 decode holds); tracks I -21.0 LUFS, TP -20.2 dBFS; segue-join RMS 0.1220 vs expected
0.1257 (ratio 0.971, tolerance 0.15); clip->track pause peak 0.0. No tolerance was changed; 5.1 passed the
same tests.

## Files changed
- packages/transmitter/src/transmitter/render.py (new)
- packages/transmitter/tests_transmitter/test_render.py (new)
Commit: 9fc3c57

## Self-review
- Matches the brief's listings exactly; no cross-module refactor (clip-pause count via
  `samples_for_seconds` as written).
- Failure paths: mismatch check happens before the encoder is created (no ffmpeg/tmp); any exception
  inside the encode loop or `close()` -> `abort()` (which is a no-op after close() already cleaned up);
  the drift path unlinks the renamed output. Tests confirm no output and no `.x.aac.*` temp left.
- Decoder generators abandoned mid-iteration by an exception are closed by CPython refcounting when the
  loop unwinds, and `iter_decode`'s finally kills its ffmpeg.

## Concerns
- None blocking. Minor/observational: a "package changed" mismatch is only detected after the whole file
  has been decoded and encoded (by design of the brief); a file that grew is detected the same way.
