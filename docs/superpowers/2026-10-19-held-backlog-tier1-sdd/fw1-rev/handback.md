VERDICT: APPROVED

fw1-rev: combined spec-compliance and code-quality review of 09d50fd..0c916da (one commit, 0c916da). Reviewed read-only in the snapshot `git archive 0c916da`. Shadowing was proven: llama resolved to the snapshot's `packages/llama/src`.

## Spec compliance (fw1-brief.md)
| Item | Status | Where |
|---|---|---|
| 1 I2: `clear_encore=True` passed in `_untitled_resolution`'s `_edit_overrides` call | ✅ | cli.py:1640 |
| 1 `assert ov.encore_after is None` in `test_untitled_one_confirmation_...` | ✅ | test_fix.py:735 |
| 1 new test: seed encore_after=3, `--untitled` + y, cleared, single set label (no encore) | ✅ | test_fix.py:739-754 (runs the real compute_gather and expects `{"1"}`) |
| 2 status return `tuple[Literal["declined","held","packaged"], Path \| None]` | ✅ | cli.py:1620-1649 |
| 2 both call sites use the status | ✅ | cli.py:1754-1757 (triage), 2797-2801 (fix) |
| 2 `_overrides_snapshot` removed; no other users (grep over packages and scripts: 0 hits) | ✅ | |
| 2 printed texts and exit codes unchanged (`declined; nothing written` exit 0; `packaged: <p>` / `still held: <slug>`; triage `continue` on decline) | ✅ | |
| 3a zero-track refusal pinned: exit 1 plus the exact `(0 of 0 resolved)` text, no write, no redo | ✅ | test_fix.py:757 |
| 3b decline: output text, exit 0, overrides byte-identical (seeded file, so stronger than "absent"), no redo | ✅ | test_fix.py:767 |
| 3c triage `[u]` decline: prompt shown twice (`count("[u]ntitled") == 2`, input `u,n,s`), nothing written, no packaged/held line | ✅ | test_triage.py:631-632 |
| Nothing extra changed (3 files, +57/-16; `typing.Literal` import only) | ✅ | |
| Do-not-retune names: grepped the diff for every Global Constraints name and the CLAUDE.md constants: none touched | ✅ | |

## Findings
Critical: none. Important: none.

Minor:
- **M-1: the "confirmed but still held" path of `--untitled` / `[u]` is untested.** Reviewer mutant M3 changes cli.py:1649 so that a confirmed run that is still held returns "declined". The full suite SURVIVES it (114/114 in test_fix + test_triage).
  - Effect: after overrides were written and two redos ran, the operator would read `declined; nothing written` from fix, and triage would silently re-prompt.
  - This branch was untested before this commit as well. The refactor is what makes the status distinction explicit, which makes the gap worth closing.
  - Fix: one test in test_fix.py. Stub `_redo_show` to return None for both stages, run `--untitled` with `y`, and assert `still held: gratefuldead-1973-06-10` is in the output and `declined` is not (optionally the triage twin). Non-blocking.
- **M-2 (observation, an improvement): a narrow edge case changes behaviour.** The old byte-snapshot check misreported one case as "declined": a confirmation whose `_edit_overrides` rewrote identical bytes (the overrides already held exactly the untitled resolution) and whose redo stayed held. It now correctly reports `still held`. This is consistent with the intent of brief item 2. No action.
- **M-3 (style, optional):** the callers still choose between `packaged:` and `still held:` by `pkg` truthiness rather than by `status`. The two are equivalent as written (`packaged` iff pkg is not None). Leave it.

Test quality: the new tests check behaviour. The gather half of the seeded-encore test is load-bearing on its own: with `encore_after=3` and `set_breaks=[]`, the real compute_gather labels the tracks `1,1,1,encore,encore,encore`, and with None it gives `{"1"}` (probe run in the snapshot). So the test would catch the I2 symptom even without the `encore_after is None` assert.

## Mutation spot-check
Recipe: rsync copies under MROOT=/var/folders/yn/jlwxryrj1ds7jpvw931jk1jm0000gn/T//mut-fw1-rev-ZyosL2, PYTHONPATH shadowing proven per copy, a private PYTHONPYCACHEPREFIX per mutant, and predictions logged before the flip. Run: test_fix.py + test_triage.py.
| mutant | predicted test | caught by |
|---|---|---|
| M1 drop `clear_encore=True` | test_untitled_clears_a_pre_existing_encore_so_the_tape_is_one_set | that test (1 failed / 113 passed) ✅ matches the implementer's claim |
| M2 decline returns `("held", None)` | test_untitled_declined_says_so_... + test_triage_u_declined_writes_nothing_... | both (2 failed / 112 passed) ✅ matches the implementer's claim |
| M3 (reviewer-added) held path returns `("declined", None)` | predicted SURVIVED (no test reaches the both-redos-None path) | SURVIVED (114 passed) — see M-1 |

## Suite (snapshot 0c916da)
`3772 passed, 1 skipped, 8 deselected, 26 warnings in 94.22s` (the implementer's claim of 3772/1/8 is confirmed).
