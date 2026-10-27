# Task 3 spec-compliance review: room-tone fill (c110c025..8ac30889)

Reviewer: spec-compliance, Opus. Read the brief, the global constraints, Review Focus item 4, spec section 3, the harness `room_tone()` (read only, not run), the handback, and the diff (complete; no hunk was cut off).

## What was done well
- `fill_room_tone` follows the brief's pseudocode line for line. Runs are found on the input (`_zero_runs(x, min_run)`). The pool is built from whole frames only, with `rms > LIVE_RMS` and the >= 1 ms zero-run exclusion applied first and the 8th percentile taken over what remains (the order spec section 3 asks for). The seed is `int.from_bytes(sha256(seed_text.encode()).digest()[:8], "big")`. `start_edge`/`end_edge`/`lo`/`hi` match the brief exactly. The fill chain is the harness's own expression. The envelope is ramp up over `[:xf]` and ramp down over `[-xf:]`, and the tone is added, not substituted.
- All six constants match the brief and the global constraints (0.02 / 8.0 / 0.005 / 0.02 / 0.001 / 1.0). `ROOM_TONE_VERSION = "v1"` carries the required comment wording. The module docstring cites the spec, section 3.
- Every no-op the spec names (not mono, no live frames, empty pool after exclusion, no qualifying run) returns the input `bytes` object unchanged.
- Review Focus 4: an odd sample count is safe because the pool uses whole frames only and the fill uses `x.size`. Runs at both edges are filled with `lo = 0` / `hi = x.size`. A single run that spans the whole clip has no live frame, so the fill is a no-op. `need >= min_run = n = 4*xf`, so the two envelope ramps never overlap.
- All 12 tests the brief lists are present, and they match its fixtures: 24 kHz; 0.5 s bursts of a -20 dBFS RMS sine (the 1.4 factor is about sqrt 2) plus the floor; 0.15 s floor-only pauses (about 23% of frames); one 0.3 s exact-zero gap; a 24 001-sample odd-length clip with 0.1 s edge runs; the 10-sample ±2 dither edge clip.
- The seed spy is installed after the fixture is built, so it records only the module's own call. That detail is right.
- Mutation evidence meets the rubric. Each of A, B and C states its predicted test before the run, and each observed result follows from its edit. A also failing `test_noop_when_pool_empty` is expected: without the exclusion, that fixture's pool is no longer empty. The handback also says openly that a first BSD `sed -i` attempt did not apply and was redone.

## Spec Compliance
- ✅ Spec compliant: every requirement in the brief, in global-constraints.md (room-tone line, mono only, sha256 seed and never `hash()`), in Review Focus 4 and in spec section 3 has its code and its test.
- ⚠️ Cannot verify from this diff:
  - Wiring into `_chunked_pcm`, the `[tts] room_tone` switch, and `tone=<ROOM_TONE_VERSION>` in the cache key. Later tasks build these, per the spec's sections 3 and 6.
  - That callers pass the spoken text as `seed_text`.

## Issues (spec only)

### Critical (Must Fix)
None.

### Important (Should Fix)
None.

### Minor (Nice to Have)
1. **`test_pool_excludes_frames_with_a_1ms_zero_run` (test_room_tone.py:110-132): its "no zero run >= 24" assertion does not discriminate on this fixture.**
   - Named risk: the brief asks the test to check that the fill holds no zero run of 24 or more samples.
   - What I checked: I applied mutation A (`if _zero_runs(...)` changed to `if False:`) in a `git archive` scratch copy, with shadowing proven (`emcee.__file__` inside the scratch tree). The zero-run assertion **passes** under the mutant. Only the next line, `15 < rms < 25`, fails (observed rms 4.45).
   - Why: the holes sit at offset 50..80 of each frame. That is inside the 120-sample crossfade, where the previous frame's tail is blended in, and the first frame's hole lands before the gap window. So the fill never shows the 30-zero run.
   - Effect: the rule is still pinned, through the RMS assertion. But the assertion named in the brief is dead weight.
   - Fix: place the hole beyond `xf`, e.g. `f[200:230] = 0`. The zero-run assertion then fails under mutation A on its own.
2. **Extras beyond the brief.** None changes a specified behaviour:
   - a trailing odd byte is passed through;
   - an early return when `n <= xf or xf < 1`;
   - `max(1, round(POOL_ZERO_RUN_S*rate))`;
   - a `len(frames)` guard and a `len(pool)` guard, of which the second can never trigger.
   Each is listed honestly in the handback. Acceptable as defensive code.
3. **Process: TDD order.** The handback says the implementation and tests were written together, and RED was then shown by moving `room_tone.py` aside (ImportError). That is the failure Step 2 expects, but it is not test-first as Steps 1-3 order it. Noted only.

## Assessment
**Spec compliance:** Approved

Probe run (scratch copy only; live worktree untouched): `PYTHONPATH=<scratch>/packages/emcee/src:<scratch>/packages/herder/src PYTHONDONTWRITEBYTECODE=1 <worktree>/.venv/bin/python -m pytest -p no:cacheprovider <scratch>/packages/emcee/tests/test_room_tone.py -q -k pool_excludes`, with mutation A applied. Result: 1 failed, on the RMS line. Scratch at `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-emcee-paragraph-chunking/5419dfd4-2b2c-4fbf-aff9-2cdd628626ee/scratchpad/t3spec`.
