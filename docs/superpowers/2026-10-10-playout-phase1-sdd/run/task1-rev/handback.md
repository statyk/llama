### Spec Compliance
- ✅ Spec compliant. All 19 files in the brief are present. The code matches the brief's listings character for character (I compared each listing against the diff hunks). `packages/transmitter/LICENSE` is byte-identical to `packages/emcee/LICENSE` (checked with `cmp`). `pytest.ini` testpaths matches the brief. Every exported name under "Interfaces / Produces" exists with the stated signature: errors taxonomy (with `FrameCountDrift(RenderError)`), grid constants and functions, `id3.PRIV_OWNER/timestamp_tag/parse_timestamp_tag`, `adts.AdtsHeader/parse_header/frame_offsets/split_frames/build_frame/require_station_format`, `segment.assemble/parse/segment_key`, `cli.app/main_cli`, `helpers.HAVE_FFMPEG/requires_ffmpeg`. No extra files and no out-of-scope edits. llama, emcee and herder are untouched.
- I checked the grid constants by hand against the Global Constraints: 441×1024 = 451584; D_US = 10_240_000; TS_PER_SEGMENT = 921_600; 9321×921600 mod 2^33 = 299_008. The ID3 tag is 73 bytes, with frame size 53 = 0x35 and tag size 63 = 0x3f, both syncsafe, v2.4. The ADTS header of `build_frame(bytes(23))` works out by hand to `fff1508003dffc`.
- No Python 3.12+ APIs are used. I looked for `itertools.batched`, `Path.walk`, PEP 695 syntax and the 3.12-only `fromisoformat` extensions: the only strings parsed are ones 3.11 accepts, and `"Z"` is rewritten to `+00:00` anyway. `typing.Sequence` and `int | None` are fine on 3.11.
- ⚠️ Cannot verify from the diff: the RED step happened in the stated order. The implementer says the implementation was written before RED, and RED was then shown on a scratch copy with the modules removed. That is acceptable for a verbatim-brief task, but it is a process deviation. Also unverifiable: the reported 29 passed / 2178 passed. I did not re-run the suite, as instructed. The report mentions no warnings.
- ⚠️ Tested on Python 3.14 only, not 3.11. Nothing in the diff is version-sensitive, and Task 2's Debian-12 gate will cover it.

### Strengths
- All grid arithmetic is integer-only. The exactness assert in `grid.py` (`SEGMENT_SAMPLES * 1e6 % SAMPLE_RATE`, and the same for 90 kHz) fails at import if a constant is ever edited into a non-exact `d`. `first_segment_at_or_after` gets ceiling division right using negated floor division.
- The 2^33 wrap is tested on both sides of the boundary (9320 and 9321), with a hand-computed value plus a formula cross-check.
- The ADTS sync mask `0xF6` checks the sync nibble and layer==0 while accepting either MPEG ID bit and either protection bit. `frame_offsets` detects truncation and lost sync, and it returns the N+1 offsets that later layout code needs.
- The import guard asserts that its own glob found files, so a broken path anchor cannot make it pass while scanning nothing. It also splits its own self-test string so the file does not trip its own scan. It covers both src and tests.
- I probed the CLI error boundary from a scratch cwd with a throwaway command attached to `app`: `TransmitterError` prints `error: msg` plus indented details and exits 1; `KeyboardInterrupt` exits 130 (typer 0.27.3); `--version` is tested.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **`packages/transmitter/src/transmitter/adts.py:22-36` and `:75-79`: the raw-data-block count is never checked.**
   - **What:** `parse_header` reads only bytes 0-5 and ignores `number_of_raw_data_blocks_in_frame` (byte 6, low 2 bits). `require_station_format` therefore cannot reject a multi-block frame. I confirmed it: a header ending `0xFE` (3 blocks, 3072 samples) parses as an ordinary station frame.
   - **Why it matters:** the whole grid assumes 1 ADTS frame = 1024 samples. A multi-block frame would make a "441-frame" segment longer than 10.24 s with no error raised. ffmpeg's native `aac` encoder always writes one block per frame, so this is defensive, not a live bug. Task-level FrameCountDrift checks may also catch it, which I can't see from this diff.
   - **Fix:** add a `raw_blocks` field (or reject `b6 & 3 != 0`) and enforce it in `require_station_format`.
   - **Related:** for `protection_absent=0` the header is 9 bytes, but the `length < 7` check uses the 7-byte minimum.
2. **`packages/transmitter/src/transmitter/id3.py:28-43`: malformed input can raise `IndexError` instead of `ValueError`.**
   - **What:** if the declared tag size runs past the end of `data`, the frame loop slices empty bytes and `_unsyncsafe` raises `IndexError`. I confirmed this with `b'ID3\x04\x00\x00\x00\x00\x01\x00'`.
   - **Also:** the parser returns `end` as `tag_length` without checking `end <= len(data)`. It never checks the version byte or that `ts < 2^33`.
   - **Why it matters:** `segment.parse` is the verification path for published bytes, so callers that catch `ValueError` would see a traceback instead.
   - **Fix:** bound the loop with `min(end, len(data))`, or raise `ValueError` when `end > len(data)`.
3. **`packages/transmitter/src/transmitter/segment.py:21-22`: `segment_key` accepts negative `n`.**
   - **What:** it would happily form `seg/<e>/-1.aac`. The spec says `N < first` is absent.
   - **Fix:** a cheap `n < 0 → ValueError` guard at the key-naming boundary. It is not a spend path today, since key count does not change.
4. **`packages/transmitter/src/transmitter/adts.py:55-71`: `build_frame` silently masks out-of-range fields.**
   - **What:** `object_type=5`, `channel_config=8`, `sample_rate_index=16` get truncated by the bit masks instead of rejected.
   - **Why it matters:** it is test/contingency-only, but a typo in a later test would build a header unlike the one intended and could still pass.
   - **Fix:** range-check each field and raise `ValueError`.
5. **`packages/transmitter/src/transmitter/grid.py:74-76`: `us_to_iso` silently truncates to milliseconds.**
   - **What:** round-trip is exact only for ms-aligned instants. `D_US` multiples are, but `frame_to_us` results generally are not.
   - **Fix:** a one-line docstring note, so later timeline code does not rely on lossless round-trip at frame granularity.
6. **Test coverage gaps (all small):**
   - nothing tests `main_cli`'s `TransmitterError` → stderr/exit 1 mapping (I verified it by hand);
   - `test_pattern_catches_both_forms` does not exercise the `__import__(...)` arm;
   - `test_split_rejects_truncated_frame` does not `match=` the message, so any `AdtsError` passes;
   - no test covers `parse_header`'s `length < 7` rejection;
   - the ADTS comment cites "ffmpeg 8.1" while the target is 5.1. The header bytes are format-defined, so this is harmless, but worth a word.
7. **`packages/transmitter/src/transmitter/segment.py:5`: imports `typing.Sequence`.** This is brief-mandated; `collections.abc.Sequence` is the modern spelling. A style nit only.

### Assessment
**Task quality:** Approved
**Reasoning:** The implementation is a faithful, verbatim realization of the brief. The arithmetic, byte layouts and the error/CLI boundary are correct by hand-check and by probe. The remaining items are defensive hardening of the parsers (the raw-data-block count, the `IndexError` on malformed ID3) and small test gaps, none of which affects the station's own well-formed output.
