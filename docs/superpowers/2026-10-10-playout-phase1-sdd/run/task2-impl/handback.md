# task2-impl handback: Task 2 Steps 1-10 (Spike B)

**Status: DONE_WITH_CONCERNS** (the concerns are minor; none blocks the operator checkpoint)

## Commits (branch playout-phase1, not pushed)
- `575087c` feat(transmitter): native-aac encoder wrapper (aacenc) and decode_adts test helper
- `0504571` feat(transmitter): native-aac encoder wrapper and the phase-1 container spike

## Implemented
- `packages/transmitter/src/transmitter/aacenc.py`: verbatim from the brief.
- `packages/transmitter/src/transmitter/spike.py`: verbatim from the brief.
- `packages/transmitter/scripts/test-in-debian12.sh`: verbatim, chmod +x.
- `packages/transmitter/tests_transmitter/test_aacenc.py`: verbatim, plus `assert frames` before the per-frame loop in `test_encode_pcm_yields_station_format_frames` (orchestrator ruling).
- `packages/transmitter/tests_transmitter/test_spike.py`: verbatim.
- `packages/transmitter/tests_transmitter/helpers.py`: adds `decode_adts`. I merged the new imports (`subprocess`, `numpy`) into the existing top import block instead of appending them mid-file. Also added `from pathlib import Path  # noqa: F401` (orchestrator ruling).
- `.gitignore`: adds `*.aac`.
- An AST check found no unused imports in the new files. The one exception is the deliberate `Path` in helpers.py.

## Tests
- Full repo suite, `./.venv/bin/python -m pytest -q` (3.14): **2193 passed, 7 deselected**.
- Transmitter suite, `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`: **44 passed**.
- Transmitter suite, `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider`: **44 passed**.
- Debian 12, `packages/transmitter/scripts/test-in-debian12.sh` (pulled debian:12): exit 0.
  ```
  ffmpeg version 5.1.9-0+deb12u1 Copyright (c) 2000-2026 the FFmpeg developers
  Python 3.11.2
  ............................................                             [100%]
  44 passed in 1.39s
  ```
  The frame-count model holds on ffmpeg 5.1. Both `test_priming_matches_the_declared_constant` and `test_extra_frames_is_the_same_for_every_padded_length[3,441,1000]` pass. I did not record the numeric `extra_frames()` value on 5.1; the tests only assert it is consistent. The host runs ffmpeg 8.1.1.

## TDD evidence
- RED 1: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_aacenc.py -q` failed with `ImportError: cannot import name 'aacenc' from 'transmitter'` (collection error). This was expected because the module did not exist yet. The message is ImportError rather than the brief's ModuleNotFoundError because the test uses `from transmitter import aacenc`; same cause.
- GREEN 1: the same command gave 11 passed.
- RED 2: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_spike.py -q` failed with `ImportError: cannot import name 'spike' from 'transmitter'`. This matches the brief.
- GREEN 2: the same command gave 4 passed.

## Spike build for the operator
Command: `./.venv/bin/python -m transmitter.spike build .../.superpowers/sdd/2026-10-10-playout-phase1/spike-out` (default 12 minutes, took about 6 s). It produced 71 segments, plus index.html, meta.json and vod.m3u8. The output is gitignored and was not committed.
```json
{
  "n0": 9279,
  "count": 71,
  "wrap_between": [
    9320,
    9321
  ],
  "segue_at_s": 86.40764172335601,
  "show_gap_at_s": 288.043537414966,
  "show_b_at_s": 290.06367346938777,
  "wrap_at_s": 430.08
}
```
Offsets into the VOD, as `serve` prints them (`.1f`):
- **segue at 86.4 s**
- **show gap at 288.0 s** (show B starts at 290.1 s)
- **wrap at 430.1 s**
- VOD total: 71 × 10.24 = 727.04 s

**Is the build deterministic?** I built twice into separate dirs:
- `meta.json` (and so every offset) was identical.
- All 71 `seg/*.aac` files were byte-identical (same shasums).
- `vod.m3u8` differed only in its `#EXT-X-PROGRAM-DATE-TIME` lines, which are stamped from `time.time()` at build time.

So the operator's own `build` on this Mac (same ffmpeg 8.1.1) prints the same offsets. `serve` reads them back from whatever `meta.json` the operator built. A different ffmpeg version could shift `show_gap_at_s`/`show_b_at_s` by whole frames if its `extra_frames` differs; `segue_at_s` and `wrap_at_s` do not depend on the encoder.

## Self-review
I reviewed the full diff against the brief. The only departures are the two orchestrator rulings and the import-block merge in helpers.py. I did not restructure anything. No network calls (apart from the allowed debian:12 pull), no credentials, and nothing written outside the worktree's ignored dirs and my scratchpad. `spike serve` was not run.

## Concerns (minor, for reviewers / later tasks)
1. `AacFileEncoder.__exit__` only aborts on an exception. On a clean `with` exit without an explicit `close()`, the temp file and the ffmpeg process are left behind. This is the brief's design, and it is fine as long as callers always `close()` inside the `with`. Later tasks (renderer) should know this.
2. `test-in-debian12.sh` excludes `./.venv` but not `./.venv311`, so the worktree's 72 MB 3.11 venv is copied into the container. It works, and I kept the script verbatim; `--exclude='./.venv*'` would fix it.
3. The spike page loads hls.js from the jsDelivr CDN in the operator's browser. This is documented in the brief as local-spike-only.
4. `helpers.py` carries an intentionally unused `Path` import (per the ruling) with `# noqa: F401`.
