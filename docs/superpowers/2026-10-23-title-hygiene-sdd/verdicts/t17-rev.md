### Spec Compliance
- ✅ The code follows the spec. ❌ Two tests do not test what the brief asks (Important 1 and 2 below).
  - gather.py:1735: `elif today_llm and not cascade.self_filled:` is the only change to gather. `today_llm` is computed at :1702 and passed to `decide_taper` at :1703-1704 unchanged. With the skip, `needs_align` (:1772) and the not-owned low-confidence flag (:1779) cannot be reached. `is_self_filled` (title_hygiene.py:457-466) is False when D failed or any track is `unresolved`, which matches Task 6's ruling. It runs after `apply_deferred_setlist` (gather.py:1440-1451), so a deferred S fill also blocks it.
  - replay.py:89-94: the relaxation is `... == "llm" and not gathered.taper_owned and not gathered.self_filled`. It only drops the stored-llm marker when `self_filled` is True, so no other stored-llm show becomes replayable. `enabled_slices` is passed through: `replay_show` (:170, :193) -> `compute_legs` (:63, :87) -> `compute_gather`. Each defaults to `title_hygiene.ENABLED_SLICES`, and no module global is rebound.
  - `ShowReplay` (replay.py:118-123) adds the six new fields after the piece-2 fields. All have defaults (`False`, `0`, `default_factory`). `to_dict` order is pinned in test_replay.py:306-317. `_cascade_dict` (:129-151) has exactly the brief's 12 keys, with 1-based positions. `cascade` is `{}` on an unreplayable row (it keeps its default, because the exception fires before :219) and on a needs-LLM row (:219, `r.needs_llm` non-empty, which is the same thing as `classify`'s needs-llm outcome).
  - Protected names: I grepped the diff. The only hits are docstring lines mentioning `TAUTOLOGICAL_TITLE_SOURCES` (it matches the pattern `AUTO`); none is an edit. `git diff main -- packages/llama/src/llama/setlist.py` is empty.
  - Step 4: the existing tests that changed are the mccoury test (now no flag and `needs_review` False, as spec Q2 says) and the `to_dict` key list. Both changes are expected.
- ⚠️ Cannot verify from the diff: whether the full suite really ended at 4737 passed. I did not re-run it. In scratch I ran the five touched/related test files (822 passed) and the whole `packages/llama/tests` directory except `test_packaging` against the mutant copies (3009 passed).

### Strengths
- The gather change is minimal and in the right place. Its comment cites spec Q2 and says that `today_llm` passed to `decide_taper` is unchanged.
- The relaxation, the slice threading and the `today_reaches_llm` argument are all tested in a way that fails when broken. Mutation results in a scratch copy (git archive of 0a9a0a3; imports shown to come from the scratch tree with a planted sentinel; `PYTHONDONTWRITEBYTECODE=1`; expected red tests written to the log before each run). Each line is the mutant, then what turned red:
  - M1, drop `and not gathered.self_filled`: `test_stored_llm_self_filled_is_replayable` and `test_reapply_processes_a_self_filled_stored_llm_show`. Caught, as predicted.
  - M2, `compute_legs` ignores `enabled_slices`: `test_compute_legs_threads_enabled_slices`. Caught.
  - M3, `replay_show` does not pass it on: the same test. Caught.
  - M4, revert the Q2 branch: 5 tests turn red (mccoury, self-filled, stored_llm_self_filled, record_carries_title_fields, reapply). Caught.
  - M6, `today_reaches_llm=today_llm and not self_filled`: `test_today_reaches_llm_unchanged_for_self_filled`. Caught.
  - So the implementer's admitted gap (no separate RED run for the replay tests) is closed: the tests catch these breakages.
- The defensive test `test_taper_never_owns_a_self_filled_tape` (test_taper.py:594-606) has a control case: the same tape with tag titles is owned. So it is not testing something that is always true.
- Making `_cascade_dict` keys strings so the record survives a JSON round trip is a good call, and the test checks it (`json.dumps(r.to_dict())`).

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **The self-filled test never gives gather an `align_provider`, so the "no LLM call" half of Q2 is untested** (test_stage_gather.py:517-534; the jerrybase test at :554 has the same mis-wiring).
   - What's wrong: `_NoAlignProvider()` is passed as the third positional argument. In `compute_gather` (gather.py:1558-1566) that is `provider`, the extract_setlist fallback provider. `align_provider` is keyword-only and stays None in every new test.
   - Why it matters: in production `run_gather` always passes `align_provider` (gather.py:2038-2047), so spending that call is exactly the production cost Q2 removes. Mutant M5 calls `align_structure` for a self-filled tape but hides the flag and the `needs_align` verdict. It passes all 3009 tests in the llama test directory. On strict surface (e), the brief's requirement "an `align_provider` that raises if called → no call" is not met.
   - On named risk 2: the implementer said a non-matching setlist.fm canonical makes D's agreement check decline. That is only true when agreement is below 0.5. In my probe, a `_FakeSetlistFM` canonical with 4 of 6 items matching (`["Zebra Stripes", <mccoury 2-4>, "Ostrich Dance", "All Aboard"]`) gives D passed, `self_filled` True, coverage 0.0 and S mode `untagged`. So the brief's fixture is buildable. With `align_provider=_NoAlignProvider()` as a keyword it passes on HEAD and catches M5 ("ALIGN PROVIDER CALLED"). Coverage on a self-filled tape is always 0.0, so the substituted chosen canonical still takes the same branch, but it does not test "whatever the canonical".
   - Also, "labels equal deterministic align()'s" is only checked by comparing two skipped runs with each other (:533), which are trivially equal. It should compare against `align(tracks, canonical)` directly.
   - Fix: pass `align_provider=_NoAlignProvider()` as a keyword (in both tests), and add the partial setlist.fm canonical case alongside the chosen one.
2. **The "one independent title" check (the pin) does not pin the narrow exception** (test_stage_gather.py:509-544; also test_replay.py:373-379).
   - What's wrong: the tag `Zebra Stripes` disagrees with list entry 1. D therefore declines on check 3: `failed=(('tape agreement', "track 1 'Rain and Snow'"),)`. All five other tracks stay `unresolved`, and the show is held for `unresolved track titles` as well. `self_filled` is False because D failed, not because of the "ANY independent song-like title" rule the docstring names. That rule only applies when D passes and one track keeps an independent tag.
   - Why it matters: this is named risk 1. Mutant M11 skips whenever D passed, ignoring the independent-title clause. It passes all 3009 tests in the llama test directory. The unit pin in test_title_hygiene catches only a predicate-level mutant (M10), not a widening at the gather site.
   - The narrow case is reachable. In my probe, a single tag `Rain and Snow` (which agrees with the list) plus the partial setlist.fm canonical gives: D passed; tracks `['tags', 'desc-position' x5]`; `self_filled` False; `needs_llm=('align_structure',)`; flag `low-confidence structure alignment`. M11 turns this to no flag and no needs_llm, so the fixture catches it.
   - Fix: re-base the pin, and the replay pin, on that fixture. Keep the current one only if relabelled as the D-declined case.

#### Minor (Nice to Have)
1. replay.py:219: nothing tests `cascade == {}` on a needs-LLM row. Mutant M7 (always fill it) survives. Add an assertion on a stored-llm, not-self-filled row; `test_stored_llm_not_self_filled_stays_needs_llm` could check `_replay(...).cascade == {}`.
2. replay.py:142: "`d_failed` = the FIRST failed check" is untested. The D-declined fixture in test_replay.py:399-405 has a single failure, so mutant M8 (`failed[-1]`) survives. Make the fixture fail two show-level checks, for example an annotation entry plus a tape disagreement.
3. replay.py:130-131: the `_cascade_dict` docstring says only `d_track_declines` and `short4_declined` have string keys, but `c_changed` does too.
4. replay.py:21: `from llama import title_hygiene` is out of order among the `from llama.x` imports.
5. test_reapply.py:1131 imports `_SF_SONGS`/`_untag` from the `test_replay` module. It works, but it is the only cross-test-module import in that file; shared fixture helpers belong in a helper module or conftest.
6. gather.py:1736-1741: the explanatory comment sits inside the branch it says a self-filled tape never enters. It would read better just above the `elif`.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The production change is correct and minimal, and the replay relaxation and slice threading are well tested. On strict surface (e), though, the two gather tests the brief calls for do not test their stated claims. No test catches an extra `align_structure` call on a self-filled tape (M5), and no test catches a skip that ignores the independent-title clause (M11). I've given working fixtures for both above.

Evidence: the log is at $D/t17-rev/t17-rev.log (the predictions and every mutant result). The scratch copy and probes are at ~/.llama-harness/piece3/scratch/t17-rev/ (`probe/p1.py`, `probe/p2.py`, `probe/mut.py`, mutant trees under `mut/`). The worktree was not touched.
