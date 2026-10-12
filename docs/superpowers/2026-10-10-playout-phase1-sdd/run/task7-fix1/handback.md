# task7-fix1 handback — Task 7 review fix round 1

Status: DONE
Commit: e71dcc8 (on top of 8a0c345)

## What changed
1. **Corrupt cache is a miss** (`analysis.load_cached`). The read and `from_json` are wrapped:
   a non-dict payload, a version/key mismatch, or any ValueError (incl. JSONDecodeError and
   UnicodeDecodeError), TypeError, KeyError or AttributeError returns None. `load_or_analyze`
   then re-analyses and atomically overwrites the file. OSError (e.g. a permission error) is
   deliberately still raised, because a rewrite would fail the same way. Docstring explains why.
2. **fsync before rename** (`workspace.atomic_write_bytes`): `f.flush(); os.fsync(f.fileno())`
   inside the `with`, before `os.replace`. The no-temp-left behaviour and its test are unchanged.
   No directory fsync, per the ruling.
3. **Clip-leak margin** (`test_analyze_show_counts_samples_and_measures_tracks_apart_from_clips`).
   - Measured fact: the honest tracks value is **−14.8 LUFS**, not −14.0. −13.98 was 20·log10(0.2)
     in dBFS peak; BS.1770's −0.691 offset and K-weighting below 1 kHz account for the difference.
   - With the old quiet clips (−30.3 LUFS), ebur128's relative gate hides them: the leak mutant
     read −15.1, only 0.3 dB from honest. Tightening the tolerance alone could not give a clear margin.
   - So I made the clips loud (amplitude 0.7 → −7.3 LUFS; still mono 24 kHz), and the mutant now
     reads −10.3. Measurements (ffmpeg 8.1.1, scratch script):
     clip amplitude 0.05: honest −14.8 / mutant −15.1; 0.5: −14.8 / −12.4; 0.7: −14.8 / −10.3.
   - New assertions:
     - `tracks_i_lufs == approx(-14.8, abs=0.5)`
     - exactly 2 clips, each with `i_lufs > tracks_i_lufs + 5`. This replaces `< -25`, which loud
       clips no longer satisfy; the claim is still that clips are measured on their own meter.
   - Unused `numpy` import dropped.

## Covering tests (new)
- `test_a_corrupt_cache_file_is_a_miss_and_is_rewritten[empty|empty-list|list|wrong-shape]`
  writes `""`, `"[]"`, `"[1]"` and a dict whose `files` entry has a `bogus` field. Each case asserts
  `load_cached` is None, that `load_or_analyze` re-decodes every entry (counted through
  `iter_decode`), and that the rewritten file loads back equal to the result.
  - `"[1]"` was added because `"[]"` already passed before the fix: an empty list is falsy, so the
    old `not data` check caught it.
- `test_atomic_write_fsyncs_the_temp_file_before_the_rename` records the call order:
  `[("fsync", 5 bytes), ("replace", "s.json")]`.

## TDD evidence (RED, before implementation)
`./.venv/bin/python -m pytest .../test_analysis.py .../test_workspace.py -q` → 4 failed, 15 passed:
- [empty]: `json.decoder.JSONDecodeError: Expecting value`
- [list]: `AttributeError: 'list' object has no attribute 'get'`
- [wrong-shape]: `TypeError: FileAnalysis.__init__() got an unexpected keyword argument 'bogus'`
- fsync: `assert [('replace', 's.json')] == [('fsync', 5), ('replace', 's.json')]`

These are exactly the three exception classes the reviewer named, plus the missing fsync. GREEN
after the fix (see below).

## Mutation check (scratch copy, mandate 5)
I copied src/ and tests_transmitter/ to the scratchpad and ran them with `.venv/bin/python -m pytest`
and PYTHONPATH shadowing. The import path was verified inside the copy, with no bytecode written.
The mutant is the reviewer's: clip PCM is also written to the tracks meter.
Predicted red: the analyze_show test.
- Result: FAILED at the clip>tracks+5 assertion.
- With that assertion removed in the copy, it FAILS at the tolerance alone:
  `assert -10.3 == -14.8 ± 0.5`, outside the band by 4.0 dB (previously 0.1 dB).

## Results
- `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`: 112 passed
- `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider`: 112 passed
- `packages/transmitter/scripts/test-in-debian12.sh`: rc 0, `ffmpeg version 5.1.9-0+deb12u1`,
  `Python 3.11.2`, **112 passed**. The −14.8 ± 0.5 band and the clip separation hold on 5.1.
  I did not extract the exact 5.1 numbers; the passing band bounds them.
- Full repo suite `./.venv/bin/python -m pytest -q`: 2261 passed, 7 deselected.

## Files changed
- packages/transmitter/src/transmitter/analysis.py
- packages/transmitter/src/transmitter/workspace.py
- packages/transmitter/tests_transmitter/test_analysis.py
- packages/transmitter/tests_transmitter/test_workspace.py

## Concerns
None blocking. The coordinator's "honest ≈ −14.0" was the dBFS approximation; the measured LUFS
value is −14.8.
