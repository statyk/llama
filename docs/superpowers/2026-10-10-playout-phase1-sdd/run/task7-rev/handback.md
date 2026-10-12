### Spec Compliance

The task is compliant. All five files match the Task 7 brief verbatim, with two exceptions, both covered by orchestrator rulings: the unused `audio` import was dropped from `test_analysis.py`, and the now-stale `# noqa: F401` was removed from `helpers.py` (`Path` is used now). There is nothing missing and nothing extra. Every interface named in the brief is present with the specified signature (`decode_cmd`, `iter_decode`, `Loudness`, `METER_FILTER`, `LoudnessMeter.write/finish/abort`, `parse_ebur128_summary`, `ANALYSIS_VERSION`, `TRUE_PEAK_CEILING_DB`, `FileAnalysis`, `ShowAnalysis.to_json/from_json`, `analyze_show`, `load_cached`, `load_or_analyze`, `gain_db`, `stereo_sine`, `write_mp3`).

Review focus #4 (silent or unmeasurable shows):
- **No crash on `-inf`.** `audio.py` `_finite()` (diff l.213-218) maps `-inf` and `nan` to None, so `-inf` cannot crash the parser.
- **Gain at the silence gate is 0 dB, not +54 dB.** `parse_ebur128_summary` sets `I <= -70.0` to None (l.230-232), and `gain_db` returns 0.0 whenever I is None (l.77-78). This holds even when TP is finite.
- **End-to-end check.** It was verified through real ffmpeg on 5.1.9 and 8.1.1 by `test_meter_on_silence_and_on_nothing`.

Gapless decode: `test_decode_honours_lame_delay_and_padding` splits the audio at a sample that is not on a frame boundary (123,457) and asserts exact lengths for both halves. Without LAME delay/padding trimming this would be off by about 1,105 samples plus padding, so the test really does pin trimming. It passed in the Debian-12 / ffmpeg 5.1 gate (I checked the claim against the handback and log, not by re-running).

Joins and loudness (from the constraints): the tracks meter is one continuous ebur128 stream over the tracks only, and each clip gets its own meter. This matches "music target measured over tracks only; DJ clips their own target". The gain rule `min(target − I, ceiling − TP)` is implemented exactly; when TP is None it falls back to loudness alone.

Python 3.11: annotation names are all imported at module top (`Path`, `Iterator`, `np`, `Show`), and there is no 3.12+ API.

### Strengths
- **Subprocess hygiene is correct.** Every ffmpeg's stderr goes to an anonymous temp file, so nothing can deadlock on pipes. The decode pipe and the meter pipe are independent processes, so a read/write cycle is impossible. Return codes are checked, and a partial trailing frame (`pending`) is treated as a decode failure.
- **Clean shutdown on abandonment.** If an `iter_decode` generator is abandoned (`GeneratorExit` / consumer exception), its `finally` kills ffmpeg. Meters are aborted on every failure path (inner handler for the clip meter, outer for the tracks meter). `finish()` releases its resources before raising.
- **`-map 0:a:0` is load-bearing and correct.** archive.org MP3s often carry ID3 APIC cover art (a video stream). Without the map, an `f32le` output would choke on it.
- **`framelog=verbose` is the right choice.** For audio-only ebur128 the default per-frame log level is INFO. Pushing frame lines to VERBOSE keeps the stderr temp file small, from a few hundred bytes to about 16 MB, on a 3-hour show, while the INFO-level Summary still prints.
- **The cache key invalidates on re-voicing.** It is `station.file_set_key`: sha256 of the m3u paths plus sizes plus mtimes, which is hex and therefore filename-safe. A re-voiced clip therefore invalidates the cache. `load_cached` also checks both `version` and `key`.
- **Mutation evidence.** I planted a mutant in a scratch copy, run via `python -m pytest` with PYTHONPATH shadowing (import path verified). The mutant feeds clip PCM into the tracks meter as well. `test_analyze_show_counts_samples_and_measures_tracks_apart_from_clips` caught it (tracks_i_lufs −15.1 vs −13.98±1.0). My prediction had been that it would survive, so the test is stronger than I credited, though see Minor 3 on the margin.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **A corrupt cache file wedges the whole render/plan loop instead of being re-analysed.** This is plan-mandated: the code is verbatim from the brief, and the implementer flagged it.
   - **Location:** `analysis.py` `load_cached` (diff l.114-118).
   - **How it fails:** `workspace.read_json` swallows only `FileNotFoundError`.
     - A zero-length or truncated file raises `json.JSONDecodeError` (a `ValueError`).
     - A non-dict file raises `AttributeError` on `.get`.
     - A malformed `files` entry raises `TypeError` / `KeyError` in `from_json`.
   - **None of these is a `TransmitterError`.** The plan's consumers catch only `TransmitterError`: `planner.extend` skips a show "whose `frames_of` raises `TransmitterError`" (plan l.2915), and `render_step` has `except TransmitterError` (plan l.4478). One bad `<key>.json` therefore escapes both handlers, so every `plan_step`/`render_step` tick crashes for every show, not just the affected one. Nothing self-heals until a human deletes the file. That is an on-air-continuity risk: the publish horizon drains to the fallback loop.
   - **Likelihood is low but real.** `atomic_write_text` does `mkstemp` + `os.replace` with no fsync (`workspace.py` l.20-24 checked). For a new file, ext4's `auto_da_alloc` does not apply, so a power loss shortly after an analysis can leave a zero-length cache file.
   - **Fix (small):** in `load_cached`, treat `(ValueError, TypeError, KeyError, AttributeError)` and a non-dict payload as a miss (return None). `load_or_analyze` then re-analyses and atomically overwrites the bad file. Add a test that writes `""` and `"[]"` into `<key>.json` and asserts `load_or_analyze` re-analyses.

#### Minor (Nice to Have)
1. **Silence-path tests are thin.** `test_parse_summary_handles_silence` only exercises I and TP both missing together. Nothing tests I = −70.0 with a finite TP (gain must still be 0), or finite I with TP `-inf` (the parse must yield `Loudness(I, None)`). The code handles both, but neither is pinned against a regression.
2. **The `-inf` path is not tested through `gain_db`.** There is no `gain_db` test fed from a parsed silent summary. The meter test covers this end-to-end, so this is coverage polish only.
3. **The clip-separation assertion has a thin margin.** The clip-leak mutant above was caught by 0.1 dB (−15.1 vs a lower bound of −14.98). Tightening `abs=1.0` to about 0.5 would give real margin; the honest value is about −14.0. Alternatively, write louder clips, which the relative gate cannot hide.
4. **Gapless joins are not checked directly.** The test pins lengths only, not sample continuity at the join. An assertion that `concat(a, b)` matches the source within the codec's error near index `split` would test "no inserted silence" directly.
5. **⚠️ Untested: segues on 48 kHz sources.** `-ar 44100` resamples each file independently. On 48 kHz sources (LAME keeps the source rate, so some LMA derivatives are 48k), the resampler starts each file with zero history. That can leave a small transient at a segue join: not inserted silence, but a possible tick. There is no test with a non-44.1k track pair. Worth one test in Task 8 or a note.
6. **The cache ignores the ffmpeg version.** Rendering must reproduce the cached sample counts exactly. A Debian ffmpeg point upgrade that changed MP3 trim or resampler lengths would surface as `FrameCountDrift`, which `render_step` re-raises rather than skips. This is very unlikely on a 5.1.x point release. Folding `ffmpeg -version`'s first line into the key or `meta` would make it self-healing.
7. **No timeouts on the ffmpeg subprocesses.** The station root is an NFS mount (`station.py` error text). A hard-mounted, unreachable share would hang `iter_decode` indefinitely. This is out of scope for this task, but worth a decision at the service layer.
8. **`iter_decode` yields read-only arrays** (`np.frombuffer` over `bytes`). Task 8's planned code uses `pcm * gain` (a copy), so this is safe today. An in-place `pcm *= g` by a future consumer would raise a non-`TransmitterError` `ValueError`. A docstring note, or `bytearray`, would prevent it.
9. **Dead counter.** `LoudnessMeter.samples` is incremented but never read. It is harmless.

### Assessment
**Task quality:** Needs fixes

**Reasoning:** The implementation matches the brief exactly and gets the review-focus items right: −70 LUFS and `-inf` give unity gain with no crash, LAME trimming is pinned by an exact-length test that passed on ffmpeg 5.1, and the subprocess handling is sound. The one Important item is plan-mandated and cheap to fix, but it is real: a corrupt cache file raises a non-`TransmitterError` that escapes both later handlers and stalls rendering for the whole station. `load_cached` should treat an unreadable entry as a miss.
