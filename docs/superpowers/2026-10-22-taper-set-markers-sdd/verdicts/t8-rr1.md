**Verdict: all findings are ADDRESSED, and the fix diff introduces no new Critical or Important breakage.** Status: DONE. I made no commits and no repo edits.

### Finding Verdicts

- **I1: mutation.md called (o)'s word boundary redundant in the header reader, and its header-side effect was unpinned.** **ADDRESSED.**
  - The pin is `packages/llama/tests/test_taper.py:4104-4114`, `test_token_glued_to_cont_or_disc_is_a_song_title`. It has 5 params:
    - `Set2cont`, `Set 2cont:`, `Set IIcont`;
    - `Set 1CD1`, `Set 1Disc 1`.
  - It pins today's reading:
    - `asserts=True` and `reason=None`;
    - the titles include the line;
    - the line's label is `"2"`;
    - `set_like=False`.
  - **My re-run of (o): exactly 6 red.** They are `[Set In Stone]` plus all 5 glued params. `test_set_intro_is_not_set_one_and_set_iv_voids` stayed green. That is what I predicted.
  - **The record is corrected** (mutation.md, "Observations", the (o) bullet). It now says the boundary is load-bearing in the header reader, gives the `_CONT`/disc-label mechanism and the effect for each line, and names the pin. That matches t8-rev's measurement and my run.
- **I2: o2 and o3 survived (the ordinal tokens' `(?!\w)`, taper.py:166-167).** **ADDRESSED.**
  - Four set-like negatives were added at `test_taper.py:4094-4096`, two per token family:
    - ord family: `songs from the first setlist`, `Second Settlement`;
    - ordn family: `2nd settle`, `1st Setting Sun`.
  - **My re-run:**
    - **o2:** exactly `[Second Settlement]` and `[songs from the first setlist]` red, 767 passed.
    - **o3:** exactly `[1st Setting Sun]` and `[2nd settle]` red, 767 passed.
    - Both match my predictions.
  - mutation.md has rows for o2 and o3 at lines 102-103, plus an Observations bullet.
- **Minor 1: the extra-red count was 12, not 13.** **ADDRESSED.**
  - mutation.md:9-12 now says Thirteen and splits them:
    - undeclared: a, b, c1, c2, d, d2, e;
    - declared: i, j1, j2, l, m, n.
  - I checked this against the table rows. The per-row n values add up: a=2, b=1, c1=1, c2=1, d=1, d2=1, e=1, i=2, j1=1, j2=1, l=1, m=2, n=3.
- **R15 caveat: label strict-superset reds as caught, with the extras noted.** **ADDRESSED.**
  - The scoring rules at mutation.md:57-61 now separate CAUGHT-AS-PREDICTED (exactly the prediction) from `CAUGHT (+n undeclared|declared, read)`.
  - **Labels a–e** use `CAUGHT (+n undeclared, read)`.
  - **Labels i/j1/j2/l/m/n** use `CAUGHT (+n declared, read)`. That is the right call. Their extras were named as collateral before the run, so "undeclared" would be false, and both variants are defined in the scoring rules, so the record describes itself.
  - Every row still labelled CAUGHT-AS-PREDICTED is "exactly" its prediction.
- **R16 comment fix at taper.py:170.** **ADDRESSED.**
  - `git diff 6bddf0d 22f565a -- packages/llama/src` touches only the comment above `_CONT` (taper.py:169-172).
  - The new text is accurate: my (o) run shows the glued forms are kept out only by `(?!\w)`.

### Checks run

- **Source changes since 6bddf0d are comment-only.** `git diff 6bddf0d 22f565a -- packages/llama/src` has one `-` line, which is the old comment.
- **setlist.py is untouched.** `git diff main -- packages/llama/src/llama/setlist.py | wc -l` gives 0.
- **No existing test line was removed.** Under `packages/` and `scripts/`, the only `-` line in 6bddf0d..22f565a is that taper.py comment. The test_taper.py diff is +16 and -0.
- **My own mutant runs.**
  - **Setup:**
    - base: `git archive 22f565a` into `scratchpad/t8-rr1/base`, with a fresh copy per run;
    - run from an empty scratch cwd as `<wt>/.venv/bin/python -m pytest -p no:cacheprovider`;
    - `PYTHONPATH` shadowing and a fresh `PYTHONPYCACHEPREFIX` per run;
    - the 6 Task-8 test files, 769 tests;
    - each run asserted that `llama`, `llama.taper`, `llama.stages.gather`, `llama.replay` and `herder` resolve inside its own copy;
    - old text had to occur exactly once.
  - **Predictions** went to the log at 14:24:06, before any copy or flip.

  | run | result | as predicted? |
  |---|---|---|
  | S0 | 769 passed | yes |
  | SENT (`raise` at the top of `read_taper_structure`, plus a module attribute `SENTINEL_T8RR1`) | 634 red, including all 22 `test_set_like_negatives` and glued-token params; the copy's `llama.taper.SENTINEL_T8RR1` reads True | yes; the copy is what ran |
  | o | the 6 listed above | yes |
  | o2 | the 2 listed above | yes |
  | o3 | the 2 listed above | yes |

  Each mutant was a one-line diff, and every outcome matches t8-fix1's `results.jsonl`.
- **I did not re-run the full suite.** The fix report claims 4443 passed and 1 skipped, which is the earlier 4434 plus 9 new test ids. That is consistent with the +4 and +5 params.

### New Breakage in the Fix Diff

None at Critical or Important.

- **Minor:** mutation.md:102-103 describes o2/o3's history as "first run: 0 red (SURVIVED, found by t8-rev)". But the record's own headline (lines 9-10) says o2 and o3 were not in the first run; they were added in fix round 1.
  - Strictly, they survived t8-rev's run against the first run's tests.
  - This is disclosed, and line 17 says it plainly, so it is wording only.

### Out-of-Scope Observations

- **Deferred minor (t8-rev Minor 2, not part of this round).** The collateral declarations for (l) and (n) are open-ended. So the `(+1 declared)` label for (l) and the `(+3 declared)` label for (n) rest on generous declarations. They are acceptable as recorded.
- **Behaviour note, not a defect.** The new pin locks `Set 1CD1` and `Set 1Disc 1` as set-2 song titles. That is today's reading, as R16 asked. If a later task decides these should be headers, this test is the one to change on purpose.

### Verdict

**Fix round:** All findings addressed, no new Critical or Important breakage.

**Evidence:**
- **Log:** `$D/t8-rr1/t8-rr1.log`, with the predictions first and then the teed run.
- **Scratch:** `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/0443a042-e8ee-4093-a603-2fbd14e62179/scratchpad/t8-rr1/`, which holds `rr.py` and `base/`. The per-mutant copies were removed after each run.
