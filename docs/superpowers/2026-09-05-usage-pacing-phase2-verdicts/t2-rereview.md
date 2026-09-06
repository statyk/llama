# Scoped re-review — Task 2, fix round 1

Range `8c0a56d..6901427` (one commit, `packages/herder/tests/test_usage.py`, +64 lines, **test-only** —
`git diff --name-only` in the range has no non-test path).

## Verdict: **all three findings ADDRESSED. Approve.**

---

## Harness — proof it looked

Private copy at `$D/work/t2-rereview/copy/` (full `packages/herder` src+tests). The worktree was
read only: never modified, never committed to, its suite never run.

- **Shadowing proven twice.** A planted `SENTINEL_REREVIEW` attribute was read back from the copy;
  then, under pytest itself, a throwaway `test_zz_pathproof.py` printed
  `HERDER_USAGE_FILE=.../work/t2-rereview/copy/src/herder/usage.py` and asserted the path — so the
  copy, not the main venv's `_editable_impl_llama_herder.pth`, is what the tests import.
- Runner is `/Users/shawn/projects/llama/.venv/bin/python -B -m pytest` (never the console script),
  with `PYTHONDONTWRITEBYTECODE=1` and `__pycache__` cleared before every run — the implementer's
  reported stale-bytecode false alarm cannot recur here.
- **Control: `11 passed`, rc=0** on the unmutated copy, re-run after the sweep (`RESTORE CHECK: 11 passed`).
- **Harness control mutant M11** (weekly-all bound `SEVEN_DAY`→`FIVE_HOUR`) went **red**, killed by two
  tests. So a green result from this harness is a real result, not a check that never looked.
- Copy's `usage.py` verified byte-identical to the worktree's at start and at end (`diff` → identical).

Full log: `$D/t2-rereview/t2-rereview.log`.

## Mutation sweep — 11 mutants, independently applied

| # | mutation | result | killed by |
| --- | --- | --- | --- |
| M1 | `_SESSION_RE` `(.*)$` → `([\s\S]*)$` | **CAUGHT** | `test_session_line_without_its_own_reset_is_not_polluted_by_a_later_clause` |
| M2 | `_WEEK_ALL_RE` `(.*)$` → `([\s\S]*)$` | **CAUGHT** | `test_weekly_all_line_without_its_own_reset_is_not_polluted_by_a_later_clause` |
| M3 | `_WEEK_MODEL_RE` `(.*)$` → `([\s\S]*)$` | **CAUGHT** | `test_per_model_meter_parses_percent_reset_and_strips_whitespace` |
| M4 | `_SESSION_RE` `^` anchor dropped | **CAUGHT** | `test_session_line_is_matched_only_at_its_own_line_start` |
| M5 | `_SESSION_RE` `$` anchor dropped | SURVIVED | *equivalent mutant — see below* |
| M6 | per-model `Meter(int(mm.group(2)),` → `Meter(0,` | **CAUGHT** | `test_per_model_meter_...` |
| M7 | per-model `parse_reset(mm.group(3)` → `mm.group(2)` | **CAUGHT** | `test_per_model_meter_...` |
| M8 | per-model key `.strip()` dropped | **CAUGHT** | `test_per_model_meter_...` |
| M9 | per-model bound `SEVEN_DAY` → `FIVE_HOUR` | **CAUGHT** | `test_per_model_meter_...` |
| M10 | session bound `FIVE_HOUR` → `SEVEN_DAY` | **CAUGHT** | `test_session_reset_far_beyond_the_five_hour_bound_is_rejected` |
| M11 | *(harness control)* weekly-all bound → `FIVE_HOUR` | **CAUGHT** | 2 pre-existing tests |

Every mutant was killed by **exactly the test that claims it**, and by no other — so no new test is
passing on a coincidence, and none is a duplicate of an existing one. All five new tests pin what
they claim; the implementer's self-verification reproduces independently.

## Findings

**F1 — ADDRESSED** (`packages/herder/tests/test_usage.py:65-75`, `:110-117`, `:120-126`).
Three of the five listed mutations (M1, M2, M4) are killed by three new purpose-built tests; the
fourth (M3) is killed by F2's test; the fifth (M5) is an equivalent mutant, not a gap. The two
"pollution" fixtures are well built rather than merely present: each polluting reset clause was
chosen to sit **inside** the bound that would otherwise reject it — the weekly `Sep 5 at 9pm` in the
session test is 4.5 h ahead of `NOW` (under `FIVE_HOUR_MAX_AHEAD_S` = 5.5 h), and the per-model
`Sep 12 at 7am` in the weekly test is 6.6 d ahead (under `SEVEN_DAY_MAX_AHEAD_S` = 7.5 d). Had
either been placed outside its bound the test would have passed vacuously under the mutant. This is
precisely the harm the quality review measured, and it is now pinned.

**F2 — ADDRESSED** (`packages/herder/tests/test_usage.py:84-95`).
One fixture and one assertion kill all four listed survivors (M6-M9) **plus** M3. The `EXTRA_MODEL`
fixture supplies the three properties the old assertion lacked: a non-zero percent (31, kills the
percent group), its own dated reset (kills the group-3→group-2 swap and the bound swap), and
whitespace around the key `( Codex )` (kills the dropped `.strip()`). The fixture is built by
`REAL.replace(...)`; note this fails **loudly**, not silently, if `REAL`'s Fable line ever drifts —
the replace would no-op and `r.per_model["Codex"]` raises `KeyError`. No tautology remains: each
asserted field differs from its type's zero value.

**F3 — ADDRESSED** (`packages/herder/tests/test_usage.py:98-107`).
M10 confirmed red. The test supplies a session reset ~6.9 days out — over the 5.5 h session bound,
under the 7.5 d weekly bound — so it discriminates the two constants rather than merely any bound.

## The equivalence claim (M5): **the implementer is right.**

`(.*)$` and `(.*)` under `re.M` without `re.DOTALL` compute the same function, and no test can
discriminate them. Chasing it would be wasted work; it is correctly noted rather than "fixed".

*Reasoning.* Greedy `.*` in non-DOTALL mode halts at exactly one of two positions: immediately before
a `\n`, or at end of string. Python's `$` under `re.M` matches at exactly those same two positions
(Python treats only `\n` as a line boundary — unlike JS, it does **not** additionally break on `\r`,
`\x0b` or `U+2028`). The two sets are identical, so `$` always succeeds where greedy `.*` leaves the
cursor, never forces backtracking, and — being zero-width — changes neither `span()` nor `groups()`.
The complementarity is exact, which is why the claim holds universally and not just for this fixture.

*Evidence.* Two differential runs, **zero differences**:
- Exhaustive over **37,449** strings (all lengths ≤ 5 from the alphabet
  `{'X','a','\n','\r',' ','\x0b','$',' '}`) comparing `re.compile(r"^X(.*)$", re.M)` against
  `re.compile(r"^X(.*)", re.M)` on full `finditer` span-and-group sequences.
- **60,000** randomized realistic `/usage` texts (real meter lines shuffled, LF and CRLF separators,
  with and without trailing newline) comparing the shipped `_SESSION_RE` against the M5 mutant.

Worth recording so it is not re-derived: the equivalence is specific to `(.*)`. It would **not** hold
under `re.DOTALL`, nor for the `([\s\S]*)` widen mutants — which is exactly why M1-M3 are real gaps
and M5 is not.

## New breakage introduced by the fix diff

**None — Critical or Important.** The diff adds test code only; no production line changed, so no
behaviour moved and no other test can be affected. The five new tests are green on the pristine copy,
and each fails only under its own target mutation.

## Deferred minors (out of scope for this round)

1. **The bound *values* are still unpinned, only their *identities* are.** `FIVE_HOUR_MAX_AHEAD_S`
   `5.5*3600` → `24*3600` and `SEVEN_DAY_MAX_AHEAD_S` `7.5*86400` → `30*86400` both **survive** green.
   F3 as written pins "the session call uses the tighter constant", which is the finding it was given;
   pinning the magnitudes would need a boundary-straddling fixture per constant. Not a regression — the
   fix round did not widen this.
2. **`fetched_at=now` → `fetched_at=None` still survives** — pre-existing quality-review Minor 5,
   explicitly deferred by the orchestrator, re-confirmed still open. Same for Minors 4 and 6-10.
3. `$D/work/t2-quality/` (the previous reviewer's copy) is still on disk; the implementer's
   `$D/work/t2/` is correctly empty. Housekeeping only.

## Isolation and hygiene

- Worktree `/Users/shawn/projects/llama-wt-pacing2` is **clean** (`git status --porcelain` empty) and
  still at `6901427`, checked before and after all mutation work. Its suite was never run by me.
- The implementer's throwaway copy is **gone**: `$D/work/t2/` is empty and no `mutcheck*` path exists
  anywhere under `$D/work/`.
- All mutation work happened in `$D/work/t2-rereview/`. `$D/t2-rereview/` holds only the log, this
  report, and the sentinel.

## Commits

**None.** Reviewers do not commit, and I had no reason to want one.
