### Spec Compliance

**Compliant: nothing missing, nothing extra, nothing misread.** I checked each interface in the brief against the diff and the spec's "Exact timing" section (spec lines 370-399):

- `station.file_set_key_and_sizes` (station.py:92-100) does one stat per entry. `file_set_key` delegates to it, and the hashed bytes are identical: same `json.dumps([rel, size, mtime_ns]) + b"\n"` stream, same `[:20]` (risk b, verified by reading).
- `Show.meta` gains `total_duration_sec` (float or None, bools excluded), `voiced_profile` (`dj_audio.profile` when it is a non-empty string, else `source.profile`) and `sizes`, at station.py:217-222. The existing keys are unchanged. `dj_audio` is guaranteed to be a dict by the time this code runs, because a non-dict appends a reason and returns `Ineligible` earlier (station.py:150-151).
- `mp3info.mp3_seconds` matches the brief: ID3v2 syncsafe skip plus footer flag, first-sync search, 64 KiB bound, `size` used without a second stat, `(size - offset) * 8 / bitrate`.
- `pieces.estimate_frames`, `CLIP_FALLBACK_SECONDS = 120.0` and `UNVOICED_CLIP_ALLOWANCE_SECONDS = 240.0` match the brief. The join counting is the same predicate as `render.show_layout` (render.py:46, `"clip" in (prev, f.kind)` over the same entry order), and the result goes through `frames_for(pad_to_frame(...), extra)`, as `planned_frames` does (risk e).
- `scripts/probe_estimates.py` has the brief's flags and output columns. `--help` exits 0 (re-run).
- ⚠️ The spec's other estimate clauses (estimates keyed by file-set key and marked as estimates; unvoiced packages keyed by manifest mtime and size; the 4-minute allowance actually applied) belong to later tasks. The diff cannot show them. Only the constant lands here, as the brief says.

**Named risks:**

- **(a) R2 bytes and cache: no published change, old caches still load.**
  - `ShowAnalysis.meta = dict(show.meta)` (analysis.py:91), so new cache files carry `total_duration_sec`, `voiced_profile` and `sizes`.
  - Nothing published serialises `meta` whole:
    - `site.build_timeline` picks `artist/date/venue/city/profile` (site.py:54-58).
    - `site.build_notes` picks named keys through `pick()` (site.py:106-119).
    - `publish.py:261` passes `meta` only to `build_notes`.
  - So timeline.json, notes/ and show/ bytes do not change.
  - `ShowAnalysis.from_json` does `dict(data["meta"])` with no key check, and `ANALYSIS_VERSION` is unchanged. Old cache files without the new keys still load, and no cache is invalidated.
- **(b) Key bytes: identical by reading, but no test can catch a change** (see Important #1).
- **(c) MP3 header parsing: tables and bit fields are right, with test gaps** (see Minor).
  - Version bits: 00 = 2.5, 01 = reserved, 10 = MPEG-2, 11 = MPEG-1. Layer `01` = III.
  - The V1 L3 bitrates (32-320) and the V2/2.5 L3 bitrates (8-160) are correct. Free-format (0), bad (15) and reserved sample-rate index 3 are rejected.
  - Syncsafe masking and the footer flag (`buf[5] & 0x10`) are correct.
  - A false sync inside the tag is skipped, because scanning starts at the tag end.
  - A tag larger than 64 KiB returns None (the 120 s fallback). That follows the spec's literal "first 64 KiB".
  - The MPEG-2 path matters in production: emcee's lameenc clips at 24 kHz are MPEG-2 Layer III CBR (emcee/audio.py:108-116). `test_mpeg2_layer3_bitrate` covers that path.
- **(d) The probe is read-only and Python 3.11-safe.**
  - It calls `load_config`, `station.scan`, `analysis.load_cached` (read only), `render.planned_frames` (pure) and `estimate_frames`.
  - `--time-one` calls `analysis.analyze_show` directly, not `load_or_analyze`, so nothing is written to the cache.
  - It takes no lock and creates no workspace file or epoch.
  - The implementer's tempfile concern is wrong. `aacenc.extra_frames` → `encode_pcm` uses `subprocess.run(capture_output=True)` (aacenc.py:39-49), with no tempfile. The only temp file anywhere is `LoudnessMeter`'s anonymous `tempfile.TemporaryFile()` for stderr under `--time-one` (audio.py:~114). It is unlinked at creation and leaves nothing behind.
  - It imports no llama or emcee code and uses no 3.12+ syntax.

### Strengths

- `file_set_key` is kept as a thin delegate, so every existing caller and cache key is untouched by construction. The one-stat contract is honoured.
- `total_duration_sec` excludes `bool`, which a plain `isinstance(x, (int, float))` would let through.
- `estimate_frames` takes the clip reader as an injected callable, which makes the join, fallback and size-passing tests clean.
- The pieces tests are real: the join-predicate mutant (M5) is caught. The station meta test also checks every size against an actual `stat()`.
- The probe's `--time-one` correctly bypasses `load_or_analyze`, and its docstring states the read-only contract.

### Issues

#### Critical
None.

#### Important

1. **packages/transmitter/tests_transmitter/test_station.py:299-303: `test_file_set_key_unchanged` is tautological and cannot catch a changed key (plan-mandated).**
   - **What:** `file_set_key` is now defined as `file_set_key_and_sizes(...)[0]`, so the assertion `file_set_key(...) == file_set_key_and_sizes(...)[0]` holds whatever the hash computes.
   - **Mutation evidence:** in a scratch copy (import shadowing proven), I changed the hashed bytes to `json.dumps(..., separators=(',', ':'))`. Prediction: SURVIVES. Result: the full transmitter suite passed, 604 passed. The one failure was `test_relay_key_matches_antenna`, which fails identically on the unmutated scratch copy because the archive omits `antenna/src`. No other test pins the key bytes either.
   - **Why it matters:** risk (b) was this test's whole purpose, and the stakes are high. A changed key silently invalidates every cached analysis on hugo, so everything is re-analysed. It also fails key re-validation for every planned row, so the skip path drops them and the plan is rebuilt.
   - **Fix:** in the test, compute the expected key independently with the pre-task formula, for example `hashlib.sha256(b"".join(json.dumps([r, st.st_size, st.st_mtime_ns]).encode() + b"\n" for r in rels for st in [(pkg / r).stat()])).hexdigest()[:20]`, and assert that both functions equal it.

#### Minor

1. **packages/transmitter/tests_transmitter/test_mp3info.py: the mp3info tests do not pin several behaviours.** Each mutant below survived, with the prediction made before the run:

   | Mutant | Result |
   |---|---|
   | M6: ID3 skip removed (`i = 0`) | Survived |
   | M1: footer flag ignored | Survived |
   | M2: MPEG-2.5 mapped to the V1 table | Survived |
   | M3: reserved sample-rate index accepted | Survived |
   | M11: bitrate index 15 accepted | Survived |
   | M10: syncsafe `& 0x7F` masks dropped | Survived |
   | M9: 64 KiB bound removed | Survived |

   - **M6 matters most.** `test_mp3_seconds_skips_id3v2` passes with the skip deleted, because the tag body is all zeros and holds no `0xFF`, so the sync search finds the real header at offset 110 either way. The test named for the false-sync risk does not test it. The brief dictated the zero-filled fixture, so this part is plan-mandated.
   - **Fix:**
     - Put a false sync with a different bitrate inside the tag body, e.g. `FF FB 50 00` (MPEG-1 L3 64 kbps), so skipping changes the answer.
     - Add a header at offset 64 KiB+ that must return None.
     - Add one MPEG-2.5 header (`FF E3 ..`), one footer-flag tag and one reserved-index header.

2. **packages/transmitter/src/transmitter/mp3info.py:31-52 / pieces.py:25: an I/O error propagates out of the estimate.**
   - `mp3_seconds` returns None only for "no header". `open()` and `stat()` raise `OSError` (FileNotFoundError, or ESTALE on NFS), and `estimate_frames` does not catch it.
   - A clip that vanishes between the scan and the estimate is plausible: emcee re-voicing, or llama's replace-swap on the NFS root. It would raise out of the scheduler rather than count the 120 s fallback.
   - This is within the brief's letter, but the estimate only steers the choice.
   - ⚠️ **Carry forward to Task 8:** either map `OSError` to None inside `estimate_frames` (fallback), or make sure the plan step treats it like the scan's "changing" ineligibility.

3. **station.py:217-218: a non-finite `total_duration_sec` crashes the estimate.**
   - `json.loads` accepts `NaN` and `Infinity`, which give `float('nan')` or `float('inf')`.
   - `round(inf * 44100)` raises `OverflowError` in `estimate_frames`, and a negative value under-estimates silently.
   - llama's pydantic writer makes this unlikely.
   - **Fix:** add `math.isfinite(total) and total >= 0` to the guard.

4. **mp3info.py:15: `_RATES` is defined but never used.** Only `rate_idx == 3` is checked, and the duration needs only the bitrate.
   - **Fix:** either drop it, or use it to confirm a second frame header at the computed frame length. A second-frame check would also make a stray `0xFF E?` in junk before the audio far less likely to be accepted.
   - Emphasis `0b10` (reserved) is also not rejected.

5. **mp3info.py:43: the syncsafe decode duplicates `id3._unsyncsafe`** (id3.py:15). It could reuse that function, with the masks applied.

6. **probe_estimates.py: small issues.**
   - `load_config` silently returns the defaults for a mistyped `--config` path (config.py:140-141). On hugo the probe then dies with a `StationRootError` traceback rather than a clear message. Check `args.config.is_file()`.
   - `cache_dir = cfg.root / "cache"` re-derives `Workspace.cache_dir`. `Workspace(cfg.root).cache_dir` would keep the two from drifting.
   - `_is_64k` re-reads each clip's header a second time and back-computes the bitrate as `size * 8 / secs`, which skews by `size / (size - offset)` when a clip carries a tag. Returning the bitrate (or a small `mp3_bitrate` helper) is simpler.

7. ⚠️ **analysis.py:91: the cached analysis now freezes the estimate inputs.** `ShowAnalysis.meta` stores `total_duration_sec` and `voiced_profile`, but the file-set key does not cover `manifest.json`. A manifest-only change (for example a llama `fix` retag that rewrites `total_duration_sec`) leaves the cached copy stale. This is harmless today, since nothing reads those keys from an analysis. Later tasks should read the estimate inputs and `voiced_profile` from the live `Show.meta`, never from `ShowAnalysis.meta`, and should tolerate the keys being absent in pre-task cache files.

8. **Process: RED was never captured** (disclosed by the implementer). The mutation run above stands in for it. The pieces and station-meta tests can fail; the key test and most of the mp3info edge tests cannot (Important #1, Minor #1).

No noise was observed in any test output I ran.

### Assessment

**Task quality:** Needs fixes

**Reasoning:**
- The production code is correct against the brief and the spec on every named risk:
  - key bytes identical;
  - no change to published bytes;
  - old caches still load;
  - Layer III tables and ID3 handling correct;
  - joins counted exactly as `show_layout` counts them;
  - the probe genuinely read-only and 3.11-safe.
- The fix is test-only and cheap: replace the tautological key test with an independently computed key (Important #1, plan-mandated). That test is the only guard on the refactor most able to disrupt hugo, and as written it cannot fail. Strengthening the ID3 test's fixture with an in-tag false sync (Minor #1) is strongly recommended in the same pass. The remaining Minors, especially the `OSError` carry-forward to Task 8, can ride with later tasks.
