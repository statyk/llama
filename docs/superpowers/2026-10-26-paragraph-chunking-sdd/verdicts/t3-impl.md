# Task 3 handback: room-tone fill
Status: DONE. Commit 8ac30889 feat(emcee): room-tone fill for exact-silence runs.
Files: packages/emcee/src/emcee/tts/room_tone.py (new), packages/emcee/tests/test_room_tone.py (new, 12 tests).
Tests: `./.venv/bin/python -m pytest packages/emcee -q` -> 978 passed, 1 deselected (baseline 943 + 12 new... see note: suite grew by other pre-existing tasks).
RED: I wrote impl and tests together, then moved room_tone.py aside and ran the new tests: collection error (ImportError), as expected; restored.
Implementation follows brief pseudocode. Additions beyond brief: odd BYTE length tolerated (trailing byte passed through); returns input if xf<1 or n<=xf (degenerate rates); zero-run exclusion uses max(1, round(0.001*rate)).
Mutations (run in live worktree on committed state, restored via git checkout, status clean after each):
- A: `if _zero_runs(frames[i], pool_zero):` -> `if False:`. Predicted test_pool_excludes_frames_with_a_1ms_zero_run. Observed: that test failed, plus test_noop_when_pool_empty (2 failed).
  (A first attempt via BSD sed -i silently did not apply; 978 passed was an unmutated run, discarded and redone via python edit.)
- B: seed -> `abs(hash(seed_text))`. Predicted test_seed_is_the_sha256_of_the_text. Observed: failed (1 failed).
- C: `lo = 0 if start_edge else s - xf` -> `else s`. Predicted test_fill_overlaps_neighbouring_audio_by_the_crossfade. Observed: failed (1 failed).
Self-review: seed-spy test installs the spy after building the clip (the helper uses default_rng itself). No background processes left.
