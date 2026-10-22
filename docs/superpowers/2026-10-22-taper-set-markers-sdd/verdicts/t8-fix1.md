# t8-fix1 handback: Task 8 fix round 1 (R16)

**Status: DONE**

## Commits
- **f6f4000** `test(taper): pin the set tokens' word boundaries (Task 8 fix round 1)`. Tests, plus one comment-only change in taper.py.
- **22f565a** `docs: taper-markers mutation record, fix round 1 corrections`.

## Finding → change → test
| finding | change | test |
|---|---|---|
| I2: o2 and o3 survive (the ordinal tokens' `(?!\w)`) | test-only | 4 new `test_set_like_negatives` params: `songs from the first setlist`, `Second Settlement` (ord family); `2nd settle`, `1st Setting Sun` (ordn family) |
| I1: (o)'s header-side effect is unpinned | test-only | new `test_token_glued_to_cont_or_disc_is_a_song_title`, 5 params (below) |
| I1: mutation.md misstates (o) | doc | observation rewritten (below) |
| Minor 1: extra-red count | doc | 13, not 12 |
| R15 caveat: verdict labels | doc | relabelled (below) |
| `taper.py:170` comment | comment only | — |

**The glued-token test.**
- The 5 params are `Set2cont`, `Set 2cont:`, `Set IIcont`, `Set 1CD1` and `Set 1Disc 1`.
- Each line sits in `Set 1:\nBertha\nSet 2:\nSugaree\n<line>\nRipple\n`.
- It pins today's reading:
  - `asserts=True` and `reason=None`;
  - titles == [Bertha, Sugaree, line, Ripple];
  - the line's label is "2";
  - `set_like=False`.

**The mutation.md corrections.**
- **(o) observation.** The boundary is load-bearing in the header reader too, since `_CONT` and the disc label may follow the token directly. It is now pinned by the new test. The `Set Intro` prediction (stays green) is kept as the part that was right.
- **o2/o3.** I added their rows, the (o) re-run, and a "Fix round 1" section with the sentinel results.
- **Extra-red count.** It is 13, not 12:
  - undeclared: a, b, c1, c2, d, d2, e;
  - declared: i, j1, j2, l, m, n.
- **Verdict labels.** Wherever a mutant's red set is a strict superset of the prediction, the label is now `CAUGHT (+n undeclared, read)` (a–e) or `CAUGHT (+n declared, read)` (i, j1, j2, l, m, n). I used the "declared" variant because "undeclared" would misstate the six whose extras were declared beforehand.

**The comment fix.** The `_CONT` comment no longer lists `Set2cont`. It now says that a `cont` glued to the token (`Set2cont`, `Set 2cont:`, `Set IIcont`) is not a continuation, because the token's `(?!\w)` stops it. No behaviour changed.

## Mutant re-runs
**Setup.** The base was `git archive 6bddf0d` plus the edited taper.py and test_taper.py, which I checked were identical to the worktree. Each mutant got:
- a fresh copy under the scratch dir `t8-fix1/m/<id>`;
- an empty cwd and its own `PYTHONPYCACHEPREFIX`;
- a 600 s timeout;
- an assertion that its imports come from the copy;
- an assertion that its diff is one line.

**Predictions** were logged at 14:00:14, before any flip.

**One sentinel deviation.** My first S1 form (replacing an `if` line) would not have parsed. I revised it before running and logged the revision.

**Results.** The six relevant files hold 769 tests.

| run | result | as predicted? |
|---|---|---|
| S0-base | 769 passed, 0 red | — |
| S1-sentinel (raise in place of `_set_like`'s final `return False`) | 595 failed: taper 262, gather 164, reapply 62, replay_holds 61, replay 43, taper_probe 3 | Wider than "most of test_taper.py", which still proves the copy runs |
| o | 6 failed, 763 passed: `test_set_like_negatives[Set In Stone]` plus all 5 `test_token_glued_to_cont_or_disc_is_a_song_title` params | Exactly as predicted |
| o2 | 2 failed, 767 passed: `[songs from the first setlist]`, `[Second Settlement]` | Exactly as predicted |
| o3 | 2 failed, 767 passed: `[1st Setting Sun]`, `[2nd settle]` | Exactly as predicted |

## Commands
- `./.venv/bin/python -m pytest -q`, run from the worktree: **4443 passed, 1 skipped, 8 deselected**. That is 4434 plus 9 new test ids.
- `git diff main -- packages/llama/src/llama/setlist.py | wc -l` gives **0**.

## Evidence
- **Scratch dir:** `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/0443a042-e8ee-4093-a603-2fbd14e62179/scratchpad/t8-fix1/`. It holds `gen.py`, `mutants.json`, `results.jsonl`, `runner.py` and `base/`.
- **Log:** `$D/t8-fix1/t8-fix1.log`. The scoring dump of the sentinel's 595 reds is in it too; it is verbose but harmless.

## Concerns
None.
