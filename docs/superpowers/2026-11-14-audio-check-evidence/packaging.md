# Packaging the audio check (plan Task 11)

Spec: `../specs/2026-11-14-junk-drop-audio-check-design.md`, "Packaging".

## What the binary carries

- `packaging/llama.spec`: `binaries = collect_dynamic_libs("onnxruntime")` (the contrib
  `hook-onnxruntime` does the same; stated explicitly so the spec does not depend on it) and
  `hiddenimports = ["onnxruntime", "miniaudio", "_miniaudio", "_cffi_backend", "numpy"]`.
  The runtime imports are lazy (inside functions); `_cffi_backend` is imported by
  miniaudio's CFFI extension `_miniaudio` at C level, which the import scan cannot see.
- Model, class map and tone ride the existing `collect_data_files("llama.data")`.
  `yamnet.onnx` is **16.1 MB** (16,108,442 bytes), not the ~4 MB the spec estimated (the
  ONNX export stores float32 weights for ~3.7M params plus the log-mel front end).
- Verified in the local macOS arm64 binary with PyInstaller's archive viewer:
  `onnxruntime/capi/libonnxruntime.1.32.0.dylib`, `onnxruntime/capi/onnxruntime_pybind11_state.so`,
  `_miniaudio.abi3.so`, `_cffi_backend.cpython-314-darwin.so`, `llama/data/yamnet.onnx`,
  `llama/data/yamnet_class_map.csv`, `llama/data/audio_check_tone.mp3`.

## Smoke step

`packaging/build.py` `smoke_test`, for target `llama` only, runs
`<binary> _audio-check <PROJECT_ROOT>/packages/llama/src/llama/data/audio_check_tone.mp3`
(the source-tree tone) and fails the build unless the command exits 0 and its STDOUT
starts `verdict=music` or `verdict=junk` (stderr, where `unchecked: <reason>` and a
model-load warning go, is never parsed). Tests: `packages/llama/tests/test_build_smoke.py`.

## Rehearsal version

`2.24.0-rc.audiocheck1` (accepted by build.py, which does not validate, and by
`release.yml`'s `^[A-Za-z0-9._+-]+$` allowlist; a prerelease of the next minor, so it
cannot pass for a release). Use the same string for the CI rehearsal (Step 5):
`gh workflow run release.yml --ref audio-check -f version=2.24.0-rc.audiocheck1 -f skip_release=true`.

## Local build (Step 2), macOS arm64, this Mac

`./.venv/bin/python packaging/build.py --version 2.24.0-rc.audiocheck1 --skip-sign --target llama`
at `d339be3a` + the Task 11 changes (worktree venv, Python 3.14, PyInstaller 6.22.3,
onnxruntime 1.32.0, miniaudio 1.73): build and both smoke steps passed
(`llama _audio-check -> verdict=junk run=0 frac=0.00`).

| binary | size | `llama --version` (median of 5, warm) |
|---|---|---|
| baseline: installed v2.23.0 release (CI-built, Python 3.12, signed) | 18,159,616 B (18.2 MB) | 1.51 s |
| new: local unsigned `2.24.0-rc.audiocheck1` (Python 3.14) | 59,445,952 B (59.4 MB) | 1.78 s |

Growth about +41 MB (onnxruntime ~35 + ~43 MB uncompressed, compressed ~21 MB; the model
~14 MB compressed; miniaudio, cffi, numpy the rest). Startup +0.27 s (onefile extraction
of the larger archive; the runtime is not imported for `--version`). One `_audio-check`
of the 5 s tone: 2.30 s median, start to finish. The baseline is the release binary, not
a like-for-like local build of the pre-audio-check commit (a different Python and a
CI build); the CI rehearsal below gives the per-leg like-for-like numbers.

## Labelled gate on the local binary (Step 3)

`./.venv/bin/python scripts/audio_check_labelled_gate.py --binary dist/llama` (station
share mounted, read-only; ~2.5 min at `--jobs 4`): **145 labelled tracks found on the share,
0 missing, exit 0 (PASS), 0 flips.**

| group | tracks | music | junk | unchecked | flips | blocking |
|---|---|---|---|---|---|---|
| drops (rounds 1-3, vs `population2.tsv` by slug + station file) | 118 | 31 | 87 | 0 | 0 | 0 |
| control songs (must read music) | 12 | 12 | 0 | 0 | 0 | 0 |
| Space/Drums controls (listed) | 12 | 7 | 5 | 0 | - | never |
| extra Gomez "Silence" (listed) | 3 | 3 | 0 | 0 | 0 | never |

Drops: 31 music = the 30 `music_chosen` non-Silence rows of the sample plus
gomez-2006-03-21 "Silence" (round 1). Space/Drums reads music in 7 of 12, as the spec's
"Known limits" says. Every Gomez "Silence" run/frac equals the spike's.

## CI rehearsal (Steps 5-6) -- to fill after operator approval

Run id: _TBD_. Per leg (size of `llama`, `llama --version` startup; before = v2.23.0
release artifact of the same leg):

| leg | before size | after size | before startup | after startup | smoke |
|---|---|---|---|---|---|
| linux x64 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| linux arm64 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| macos arm64 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| windows x64 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

Labelled gate on the downloaded `macos-arm64` artifact: _TBD_ (tracks found, exit code,
per-group result).
