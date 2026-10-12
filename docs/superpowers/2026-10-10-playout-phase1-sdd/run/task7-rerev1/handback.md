# task7-rerev1: scoped re-review of Task 7, fix round 1 (8a0c345..e71dcc8)

**Verdict:** All three findings are ADDRESSED. There are no new issues of Important severity or above. **Task quality: Approved.**

## Finding Verdicts

**1. A corrupt or wrong-shaped cache must be a miss, not a non-TransmitterError: ADDRESSED.**
- **The fix.** `analysis.py` `load_cached` (fix diff, analysis.py hunk) wraps both `read_json` and `from_json`. A non-dict payload, a version or key mismatch, or `(ValueError, TypeError, KeyError, AttributeError)` returns None.
  - `JSONDecodeError` and `UnicodeDecodeError` are both `ValueError` subclasses, so invalid UTF-8 is covered too.
  - `load_or_analyze` is unchanged, so a miss re-analyses and atomically overwrites the bad file.
- **Real errors are not swallowed.** `OSError` is deliberately not caught: a permission error or a directory in place of the file still raises. That is the right call, because the rewrite would fail the same way. I checked that the except tuple contains no `OSError` or `Exception`.
- **A future `from_json` bug would not hide silently.** If such a bug were swallowed, every tick would re-analyse. `test_load_or_analyze_caches_by_key` still turns that into a red test, because a second decode trips its `boom` monkeypatch.
- **Test.** `test_a_corrupt_cache_file_is_a_miss_and_is_rewritten`, with cases empty, empty-list, list and wrong-shape. Each asserts that the load misses, that every entry is decoded again, and that the rewritten file loads back equal to the result.
- **Mutant (revert to 8a0c345's `load_cached`).** I predicted [empty], [list] and [wrong-shape] would fail and [empty-list] would pass. Measured: exactly that, 3 failed and 1 passed. This also confirms the implementer's point that `"[]"` alone was vacuous before the fix.

**2. `atomic_write_bytes` flushes and fsyncs before `os.replace`: ADDRESSED.**
- **The fix.** `workspace.py` `atomic_write_bytes`: `f.flush(); os.fsync(f.fileno())` inside the `with`, before `os.replace`. There is no directory fsync, per the ruling. The cleanup path is unchanged.
- **Test.** `test_atomic_write_fsyncs_the_temp_file_before_the_rename` records `("fsync", st_size)` then `("replace", name)`. Because it captures the file size at fsync time, it pins the flush as well as the ordering.
- **Mutant (delete `f.flush()`).** I predicted the test would fail with size 0 at fsync. Measured: FAILED.

**3. The clip-separation test needs real margin against the leak mutant: ADDRESSED.**
- **The fix.** The clips are now amplitude 0.7, still mono 24 kHz, measuring about −7.3 LUFS. The new assertions:
  - exactly 2 clips;
  - each clip's `i_lufs > tracks_i_lufs + 5`;
  - `tracks_i_lufs == approx(-14.8, abs=0.5)`.
- **Leak mutant on a scratch copy of e71dcc8** (clip PCM also fed into the tracks meter), run with `python -m pytest` and PYTHONPATH shadowing, import path verified, no bytecode written:
  - As committed: FAILED at the clip > tracks+5 assertion, which was my prediction.
  - With that assertion deleted in the copy: FAILED with `assert -10.3 == -14.8 ± 0.5`. That is 4.0 dB outside the band, up from 0.1 dB before the fix.
  - With the mutant, all 11 other tests in `test_analysis.py` still pass, so only the intended test catches it.
- **Still meaningful on ffmpeg 5.1.** The shift the leak causes comes from BS.1770 gating arithmetic: loud clip blocks pass the relative gate and pull the mean up. It does not depend on the ffmpeg version. The honest value passed the ±0.5 band in the Debian-12 / 5.1.9 run (112 passed, per the fix report; I did not re-run it). The +5 dB clip assertion has about 2.5 dB of headroom (−7.3 vs −14.8+5 = −9.8).
- ⚠️ **I did not measure the mutant's reading on 5.1 itself.** The 4 dB margin is far wider than any plausible difference between 5.1 and 8.1 ebur128 output.

## New Issues in the Fix Diff
- **Minor: a code comment overstates the evidence.** The comment in `test_analyze_show_...` says the tracks "measure −14.8 LUFS on ffmpeg 5.1 and 8.1". The 5.1 number was never extracted, only bounded by the ±0.5 band (the fix report says so itself). Rewording it to "−14.8 on 8.1; within ±0.5 on 5.1" would be exact. This is cosmetic.
- No other issues. Imports are clean (the unused `numpy` was dropped, and `os` was added to `test_workspace.py` and is used). The new test helpers are 3.11-safe.

## Out-of-Scope Observations
- **`OSError` from `read_json` still escapes as a non-TransmitterError.** It would still wedge a tick, but that is an environmental fault (permissions or a disk problem) where re-analysis cannot help. Wrapping it as `AnalysisError` at the caller would at least turn it into a per-show skip. This is a Task 9 decision, not a defect here.
- **fsync now covers every `atomic_write_bytes` write, including render segments.** Plan l.4492 writes rendered segments this way. The initial lead fill can write thousands of roughly 160 KB segments in one tick, each now with its own fsync. On hugo's disk that is likely seconds, but it is worth noticing if a first fill seems slow. It is not a correctness issue.
- **Valid JSON with wrong value types is accepted.** For example, `"samples": "abc"` or `"files": []` passes `from_json`, because the dataclasses do not validate. Truncation cannot produce such a file, so it is not a realistic failure mode.

## Verdict
**Task quality:** Approved

**Reasoning:** Each finding is fixed and pinned by a test that I mutation-verified on a scratch copy of e71dcc8. All four mutants failed exactly the tests I predicted beforehand. The miss path swallows only parse and shape errors and leaves real I/O errors raising.
