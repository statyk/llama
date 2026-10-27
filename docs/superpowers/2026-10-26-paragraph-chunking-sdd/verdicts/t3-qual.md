Spec compliance: not judged here (separate reviewer). Code-quality review of c110c025..8ac30889 (Task 3, room-tone fill).

### Strengths
- room_tone.py:1-8 docstring cites the spec section, and room_tone.py:14-21 states the constants with one-line meanings, as loudness.py does. ROOM_TONE_VERSION carries the required cache-key comment (room_tone.py:20-21).
- Edge handling is right and cheap. An odd byte length passes its trailing byte through (room_tone.py:41-42, 85). A partial tail frame never enters the pool (room_tone.py:52). Edge runs use lo=0/hi=size with the envelope at the clip ends (room_tone.py:72-75). xf<1 or n<=xf returns early, so the chaining loop always makes progress (room_tone.py:47-48).
- `_zero_runs` (room_tone.py:24-29) is one vectorised helper used for both the run detection and the pool exclusion. It is not duplicated.
- The seed is sha256 and the rng is drawn sequentially per run, so output is deterministic (room_tone.py:67-68). The spy test pins exactly one rng creation per call with the exact seed (test_room_tone.py:76-87). The spy is installed after `_clip` builds its data, which avoids a false count.
- The pool-exclusion test has both an exclusion arm and a control arm (test_room_tone.py:108-131). Each arm checks level and zero runs, so it pins the rule in both directions.
- Mutation evidence: all three mutations have a stated prediction, and each observed result follows from its edit. A also failing test_noop_when_pool_empty is expected, because those frames become poolable. The implementer caught and discarded a BSD `sed -i` no-op run, which was honest and correct.
- Tests are fast: 12 passed in 0.13 s, run in scratch copy 8ac30889 with emcee shadowing proven, and with no warnings under `-rw`.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. room_tone.py:85 casts with `astype("<i2")`, which truncates toward zero. loudness.py:65 uses `np.rint` before its cast. Pool samples are integers, but the crossfade samples (about a third of the fill: 5 ms of every 15 ms), the envelope ramps and the overlapped neighbouring audio are not. The bias pulls them toward 0 and makes exact zeros where the source had none.
   - Measured in scratch: a floor at RMS ~2 with no zeros produced a fill that was 10.2% exact zeros, at RMS 1.74 (about 1.2 dB low).
   - At the -60 dBFS levels of real clips the effect is negligible.
   - Fix: `np.rint(np.clip(...))`. Do it now, while ROOM_TONE_VERSION is still unshipped "v1"; a later fix would need a version bump and re-renders.
2. Two guards can never fire:
   - room_tone.py:53-54 (`if not len(frames)`): a qualifying run needs x.size >= min_run = round(0.02*rate) = n, so there is always at least one whole frame.
   - room_tone.py:62-63 (`if not len(pool)`): a linear-interpolated percentile is >= the minimum of the eligible RMS values, so the pool is never empty.
   - They are harmless, but a reader will look for the case that reaches them. Drop them or comment them as defensive.
3. The two behaviours added beyond the brief, odd byte length and the degenerate-rate early return (room_tone.py:41-42, 47-48, 85), have no test and are not in the docstring (room_tone.py:33-37), which lists only the three brief no-op cases. Add one line each to the docstring, plus a one-line test that a 1-byte-longer PCM keeps its trailing byte.
4. test_odd_length_pcm (test_room_tone.py:183-191) passes for an identity function: length unchanged, and both ends are 0 already. It never shows the edge runs were filled, which Review Focus 4 asks for ("must be filled"). This is not a coverage hole: the scratch mutant below proves the other tests exercise partial frames. Still, the test named for the case should assert it. Add `_longest_zero_run(out) < round(0.02 * RATE)`. The brief listed only these assertions (plan-level weakness, minor).
5. Linear crossfades are applied to uncorrelated noise (room_tone.py:69, 80). The sum dips by about 3 dB at the middle of each 5 ms crossfade, which is an amplitude modulation every 15 ms (about 67 Hz) on the fill. This is mandated by the harness and the brief ("as the harness"), and probably inaudible at -60 dBFS. Flag it for the listening check. An equal-power ramp (sqrt) would remove it, at the cost of a version bump.
6. Process notes for the controller, not code defects:
   - (a) The handback says the mutations ran in the live worktree, restored with `git checkout`. That breaches child mandate 5 (scratch copy only), but global-constraints.md's mutation procedure ("restore with git checkout -- <file>") implies the worktree. The two instructions conflict and should be reconciled for later tasks.
   - (b) RED evidence is just an ImportError after writing the implementation and tests together. That is weak TDD evidence; the mutations carry the real pinning.

Checks run (scratch copy of 8ac30889, `PYTHONPATH=<scratch>/packages/emcee/src:<scratch>/packages/herder/src`, emcee.__file__ proven inside scratch; nothing run in the live worktree):
- `python -m pytest -p no:cacheprovider .../test_room_tone.py -q --durations=5 -rw`: 12 passed in 0.13 s, no warnings.
- Named risk, quadratic chaining via repeated np.concatenate (room_tone.py:77-80): a 60 s clip with 100 runs took 0.019 s, and single runs of 5/20/60 s took 0.003/0.025/0.267 s. No issue.
- Named risk, runs separated by fewer than 2*xf live samples: two 0.1 s runs 5 samples apart. The fills overlap and add, the RMS around the join is 34 against 27 inside the run, and there is no hole. Acceptable.
- Named risk, truncation in the int16 cast: see Minor 1 (quiet floor at RMS 2 gives 10.2% zeros in the fill).
- Named risk, whether partial-frame inputs are actually exercised (my own mutant: `if x.size % n: return pcm` before run detection). Prediction: only test_odd_length_pcm could catch it, and it would pass. Observed: 6 failed. `_clip` and the edge-run clip are not multiples of 480, so the partial-frame path is well covered. My prediction was wrong; that supports downgrading item 4 to Minor. Restored and diffed clean.

### Assessment

**Task quality:** Approved

**Reasoning:** The module is small, pure, vectorised where it matters and well covered. Its edge handling (partial frames, clip-edge runs, odd bytes, empty pool) is correct, and its tests pin the seed, the pool rule and the overlap. The int16 cast truncates where loudness.py rounds; that is worth a one-line fix before ROOM_TONE_VERSION ships. The rest is polish.
