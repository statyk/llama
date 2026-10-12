# task7-impl handback — Task 7: gapless decode, loudness meter, analysis cache

Status: DONE_WITH_CONCERNS (minor; see Concerns)
Commit: 8a0c345 on playout-phase1 (single commit; one coherent step)

## Implemented
- `packages/transmitter/src/transmitter/audio.py` — verbatim from brief: `decode_cmd`, `iter_decode`
  (ffmpeg -> f32le 44.1k stereo, stderr to temp file, DecodeError on nonzero exit/partial frame,
  kills ffmpeg if the generator is abandoned), `Loudness`, `METER_FILTER`
  (`ebur128=peak=true:framelog=verbose`, accepted by ffmpeg 5.1 — no fallback needed),
  `LoudnessMeter` (lazy start; write/finish/abort), `parse_ebur128_summary` (last Summary wins;
  I <= -70 LUFS -> None; non-finite -> None; no summary -> AnalysisError).
- `packages/transmitter/src/transmitter/analysis.py` — verbatim from brief: `ANALYSIS_VERSION=1`,
  `TRUE_PEAK_CEILING_DB=-1.0`, `FileAnalysis`, `ShowAnalysis` (+to_json/from_json),
  `gain_db` (I None -> 0.0 unity), `analyze_show`, `load_cached`, `load_or_analyze`.
- `tests_transmitter/helpers.py` — appended `stereo_sine`, `write_mp3`; dropped the now-stale
  `# noqa: F401` on the module-top `Path` import (Path is now used). No new imports needed
  (subprocess, np, Path already at module top).
- `tests_transmitter/test_audio.py`, `test_analysis.py` — verbatim from brief, except per ruling
  dropped the unused `audio` import from test_analysis.py.

## Tests
- `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_audio.py ...test_analysis.py -q` (3.14, ffmpeg 8.1.1): 17 passed
- `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`: 107 passed
- `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider` (CPython 3.11): 107 passed
- Debian 12 gate `packages/transmitter/scripts/test-in-debian12.sh`: rc 0,
  `ffmpeg version 5.1.9-0+deb12u1`, `Python 3.11.2`, **107 passed**.
- Full repo suite `./.venv/bin/python -m pytest -q`: **2256 passed, 7 deselected**, 26 warnings.
- Measured on ffmpeg 8.1.1: 8 s 1 kHz sine amp 0.1 -> Loudness(i_lufs=-20.0, tp_dbfs=-20.0);
  3 s zeros -> Loudness(None, None) (ebur128 prints `Peak: -inf dBFS`). Same tests pass on 5.1.9,
  so no 5.1/8.1 discrepancy large enough to matter; no tolerance changed.

## TDD evidence
RED: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_audio.py packages/transmitter/tests_transmitter/test_analysis.py -q`
-> `ImportError: cannot import name 'analysis' from 'transmitter'` (and same for `audio`),
"2 errors during collection". Expected: the modules did not exist yet (brief predicted
ModuleNotFoundError; `from transmitter import X` surfaces it as ImportError — same cause).
GREEN: same command -> 17 passed.
Review focus #4 covered: `test_parse_summary_handles_silence` and `test_gain_db_unmeasurable_is_unity`
pass; `test_meter_on_silence_and_on_nothing` confirms it end-to-end through real ffmpeg on both versions.

## Files changed
- A packages/transmitter/src/transmitter/audio.py
- A packages/transmitter/src/transmitter/analysis.py
- A packages/transmitter/tests_transmitter/test_audio.py
- A packages/transmitter/tests_transmitter/test_analysis.py
- M packages/transmitter/tests_transmitter/helpers.py

## Self-review
- Did not touch spike/aacenc/grid/adts/id3/segment. No llama/emcee imports (guard test passes).
  Python 3.11-safe (no 3.12+ syntax; verified on 3.11 locally and in Debian).
- Cleanup paths: a failed clip decode aborts the clip meter, and the outer handler aborts the
  tracks meter; `finish()` releases the process/temp file before raising. An abandoned
  `iter_decode` generator kills ffmpeg in `finally`.
- No linter available in .venv (no ruff/pyflakes); imports were checked by hand — all used.

## Concerns (minor, not acted on — brief code kept verbatim)
1. `load_cached` relies on `workspace.read_json`, which only swallows FileNotFoundError: a corrupt
   or schema-mismatched cache file (JSONDecodeError/KeyError/TypeError) would raise rather than
   re-analyze. Atomic writes make truncation unlikely; Task 8 or a reviewer may want to treat an
   unreadable cache entry as a miss.
2. Process note: the Debian run's stdout first went to a scratch file in this task dir and was then
   appended to task7-impl.log and the scratch/rc files removed (mandate 2 asks for a direct tee).
   The log holds the full Debian output.
