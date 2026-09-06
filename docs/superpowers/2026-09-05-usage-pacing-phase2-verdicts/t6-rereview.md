# Task 6 — scoped RE-REVIEW of fix round 1 (`4aef34a..a3d8cdc`)

**Verdict: both findings ADDRESSED. Approved.** One new Minor introduced by the fix
diff (a markdown-structure regression in the spec); nothing Critical or Important.

Harness: private copy `$D/work/t6-rereview/repo`, shadowed via `PYTHONPATH` over the
worktree's venv interpreter and **proven** by a planted `MUTATION_SENTINEL_T6RR`
reading back `'copy'` with `llama.cli.__file__` and `herder.__file__` both resolving
under the copy (sentinel then removed, `cmp` byte-identical). Green baseline asserted
over the whole `packages/llama/tests` dir: **1347 passed, 7 deselected** — summary line
carries `passed`. `python -B -m pytest -p no:cacheprovider`, `PYTHONDONTWRITEBYTECODE=1`,
`__pycache__` cleared before every run, `</dev/null` on every pytest call, every anchor
count-asserted unique before substitution. Worktree `git status` clean and untouched
before and after; nothing committed; the real `claude` binary never invoked.

---

## I2 — `pause_reason` asserted by substring — **ADDRESSED**

Both directions reproduced independently, varying **only the test assertions** against
one identically-mutated source file, so the mutant's liveness is proved by direction A
rather than assumed in direction B.

Mutant `str(limited)` → `repr(limited)` at `cli.py:196` (anchor
`getattr(limited, "scope", None), str(limited))` asserted unique — note `str(limited)`
appears **twice** in `cli.py`, the second at `:377` in the per-show loop, so the
line-level anchor rather than the token was required).

| Direction | Assertions in tree | Result |
| --- | --- | --- |
| B (old form) | `assert "session limit" in marker["pause_reason"]` ×2 | **SURVIVED** — 1347 passed / 32 passed in `test_pace_loop.py` alone |
| A (as shipped) | `== "You've hit your session limit"` ×2 | **CAUGHT** — 1 failed (`test_a_run_level_pause_records_the_reset_plus_skew_once`) |

Direction B reproduces the reviewer's finding exactly, and the `32 passed` figure
matches the implementer's report to the test. The implementer's claim that it ran both
directions is **corroborated, not merely accepted**.

**Extra check the brief did not ask for, and it earns the second assertion its place.**
The reviewer's suggested change named only `test_pace_loop.py:522`; the implementer
tightened `:416` too. That second site does **not** see the `:196` mutant (it drives the
per-show loop, whose own `reason = str(limited)` lives at `cli.py:377`). I mutated
`:377` separately: **CAUGHT** by `test_a_pause_records_the_reset_time_and_the_scope`.
So the two equality assertions guard two different production sites, and neither is
redundant. Copy restored byte-identical after each mutant.

## I1 — the record was wrong in four places — **ADDRESSED** (six of six)

1. **Follow-up commit, not amend/rebase** — YES. `git log` shows `cbaad44`
   (`cbaad44d869c...`, 2026-09-05 23:56) and `4aef34a` (`4aef34a3bf37...`, 00:00) intact
   at their original shas with their original subjects; `a3d8cdc` sits on top, and
   `4aef34a..a3d8cdc` is exactly one commit. Its message states plainly what is and is
   not covered ("names `interpret`, which is NOT covered, and omits `discover`, which
   is … covers exactly run_discover, run_search and run_winnow").
2. **Comment at the catch enumerating the three** — YES, `cli.py:254-257`: names
   `run_discover`, `run_search`, `run_winnow` and explicitly "NOT run_interpret".
   The operator-facing note changed with it (`limit hit in discover/search/winnow …`),
   which is the load-bearing half — the old wording was what an operator actually read.
3. **Comment at the `run_interpret` call site with the unresumability reason** — YES,
   `cli.py:436-439`: criteria.json written only on success, `run resume` refuses a
   session without one, query lives only in argv, points at T6b.
4. **Spec Problem section de-names `interpret`** — YES, now "`discover`, `search` or
   `winnow`", plus a paragraph tracing the bad phrasing to phase 1's spec and warning
   that `_PIPELINE_RUN_STAGES` is a third, different triple.
5. **Known-gap paragraph in both** — YES: spec `### Known gap: run_interpret is not
   covered` (L37-52) and plan L1138-1151.
6. **T6b filed as UNBUILT and not implemented** — YES. Plan L1153,
   "**Status: UNBUILT. Do not implement as part of phase 2.**" Verified **no code wraps
   `run_interpret`**: `grep -n run_interpret cli.py` returns the import, the two call
   sites (440, 2556) and two comment lines — no `try`, no `except` around either call.

The one thing deliberately left wrong is `cbaad44`'s subject in the git log, per
instruction; the plan carries the "Correction, post-review" paragraph directly beneath
the block that prescribed it, which is the right place for a reader to hit it.

## Line citations — spot-checked, all six resolve

`cli.py:440` → `criteria = run_interpret(ws, …)`; `cli.py:2556` → `criteria =
run_interpret(scratch, …)`; `cli.py:708-710` → `if not ws.criteria.exists():` / echo /
`raise typer.Exit(1)`; `cli.py:1186` → `_PIPELINE_RUN_STAGES = ["interpret", "search",
"winnow"]`; `stages/interpret.py:13` → `write_artifact(ws.criteria, criteria)`;
`2026-09-04-usage-pacing-design.md:346-348` contains the literal
`` `interpret` (`run_discover`) ``. **Zero drift.** The re-derivation was real work, not
a claim: the +4 offset on the `cli.py` citations is exactly the four-line comment the
same commit inserted at 436.

## Deferred Minors — none opportunistically fixed

Verified untouched in the shipped tree: unreachable `getattr(limited, "scope", None)`
default (`:196`), `when = when or resume_at(...)` truthiness on a datetime (`:191`),
redundant `failures or []` (`:195`), docstring's plural "run-level pause **sites**" and
its three not-yet-called params (`:180-189`), stderr/stdout split (`paused:` on stderr
at `:192`, note and resume hint on stdout at `:193`/`:198`), overpromising
`test_run_level_ratelimited_is_caught_before_herdererror` (body and name unchanged),
the leftover local `import json` (now at `test_pace_loop.py:427`, drifted not edited),
and no `CliRunner` symmetry test added. Diff is 4 files / +85 −11 and touches nothing
else.

## Unchanged test count — consistent

`git diff 4aef34a..a3d8cdc -- packages/llama/tests | grep -c '^+def test_'` → **0**. The
test diff is 12 lines: two assertions rewritten, two `capsys` assertions retargeted at
the new note text, three comment lines. An unchanged 1814 is exactly what that predicts.
(I did not run the branch suite; the orchestrator does. My copy's `packages/llama/tests`
slice was green at 1347 both before and after every mutant restore.)

## New findings from the fix diff

**Minor 1 (new, introduced by this diff) — the spec's `### Known gap` heading is
spliced into the middle of a three-item bullet list.** The Problem section opens "Three
things are left undone, and they are the whole of phase 2:", and the H3 now lands
between bullets 2 and 3 (spec L37), so the third bullet ("There is no way to plan a run
against the window", L53-55) renders *under the Known-gap heading* and out of the list
it belongs to. Content is correct; only the structure regressed. One-line fix: move the
Known-gap block to after the third bullet. Flagged rather than fixed — I make no commits.

**Minor 2 (optional) — the second `run_interpret` call site (`cli.py:2556`, profile
creation) carries no comment**, only the first. The requirement said "the call site"
singular and the docs name both, so this is satisfied as specified; a reader landing on
2556 gets nothing local. Half a line would close it.

No Critical or Important breakage. The catch's control flow, region boundaries and
`--no-pacing` behaviour are byte-for-byte unchanged by this diff — it edits comments, one
note string, and four assertions.

## Closing verdict

**I1 ADDRESSED (6/6). I2 ADDRESSED, both mutation directions reproduced independently,
plus a third mutant establishing the second assertion is not redundant.** No new
Critical/Important. Two Minors above, both cosmetic and neither a merge blocker.
