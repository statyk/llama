# t2-impl handback: DONE
Commit c110c025 feat(emcee): paragraph-aware chunk planner (plan_chunks)
Files: packages/emcee/src/emcee/audio.py (_greedy, plan_chunks, placed before _bitrate_for_rate); packages/emcee/tests/test_audio.py (import + 15 plan_chunks tests, reusing OUTRO_1974_05_19).
Tests: ./.venv/bin/python -m pytest packages/emcee -q -> 966 passed, 1 deselected (baseline 943 + 8 Task1 tests? + 15 new).
RED: -k plan_chunks -> ImportError: cannot import name 'plan_chunks'. GREEN: 15 passed.
All expected literals agreed with the algorithm; none changed.
Mutations (live worktree, committed state, restored with git checkout, status clean after each):
A. changed `while i < len(chunks) and len(chunks) > 1:` to `while False:` (step 4 off). Predicted tiny_chunk_joins_neighbour. Observed: that + tiny_first_chunk_joins_the_next failed (2 failed).
B. `re.split(r"\n\s*\n", text)` -> `re.split(r"\n+", text)`. Predicted a_wrap_inside_a_long_sentence. Observed: only that failed.
C. `chunks = _greedy(units, ceiling)` -> `chunks = units`. Predicted paragraphs_that_fit_share_a_chunk. Observed: only that failed.
Concerns: none. Note: first attempt at a scratch edit hung on a stray `cat`; no effect on files.
