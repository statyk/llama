# Task 2 — SPEC-COMPLIANCE review (usage-pacing phase 2)

Range reviewed: `e2ada6a..8c0a56d`, from `$D/reviews/task-2-package.md` (diff not re-derived).
Worktree read-only; every experiment ran on a private copy under `$D/work/t2-spec/`.

## Verdict: **Spec OK (PASS)**

The diff is the brief's Step 1 and Step 3 code blocks, **byte-for-byte**. Verified
mechanically, not by eye: extracting the two ```python blocks from
`briefs/task-2-brief.md` and comparing to the committed files gives an exact string
match on both (2549 and 3527 chars). Two files, 149 insertions, no other file touched.
No less than the brief asked for; nothing added beyond it.

## Requirement checklist

| Requirement | Status |
| --- | --- |
| `packages/herder/src/herder/usage.py` created | OK, 87 lines |
| `packages/herder/tests/test_usage.py`, brief's 6 test bodies verbatim | OK |
| `Meter(percent, resets_at)` | OK `usage.py:45-48`, frozen dataclass |
| `UsageReading(five_hour, seven_day, per_model, fetched_at)` | OK `usage.py:51-56` (typing caveat, F3) |
| `parse_usage_text(text, now=None) -> UsageReading \| None` | OK `usage.py:59` |
| Constants `FIVE_HOUR_MAX_AHEAD_S` / `SEVEN_DAY_MAX_AHEAD_S` / `STALE_MARKER` | OK `usage.py:31-35`; 5.5 h / 7.5 d / "Showing last-known usage" match spec 168-175 |
| Never raises; every failure path returns `None` | OK, verified empirically (below) |
| Stale banner -> None | OK `usage.py:67`; mutation M7 (drop check) CAUGHT |
| Missing session line / empty / prose -> None | OK `usage.py:69-71` |
| Per-model negative lookahead | OK `usage.py:42`; mutation M5 (remove it) CAUGHT |
| Session meter uses `FIVE_HOUR_MAX_AHEAD_S` | OK in code (`usage.py:73`) — but UNPINNED by tests, F1 |
| Weekly meter uses `SEVEN_DAY_MAX_AHEAD_S` | OK `usage.py:78-79`; mutation M6 CAUGHT |
| Per-model meters use `SEVEN_DAY_MAX_AHEAD_S` | OK `usage.py:82-83` — UNPINNED, F2 |
| Per-line slice honors Task 1's one-clause contract | OK, verified: with the two-clause REAL fixture the session meter resolves to 21:20Z, not the weekly `Sep 12` clause. `(.*)$` under `re.M` cannot cross a newline, so each `parse_reset` call sees exactly one line's tail. Mutation M11 (drop `re.M`) CAUGHT. |
| No `read_usage` / subprocess call (Task 3) | OK — no `read_usage`, no `subprocess.` call site; see F4 |
| `herder` does not import `llama` | OK; `test_no_llama_imports.py` globs `src/**/*.py`, covers the new file automatically |
| `openrouter.py` untouched | OK, not in the stat |
| No constant swept/retuned | OK; `limits.MAX_RESET_AHEAD_S` unchanged |
| Tests offline/deterministic (fixed NOW, no $HOME, no subprocess, no sleep) | OK |

**Never-raises, checked rather than assumed.** On the private copy I fed `parse_usage_text`
`None`, `""`, `"Current session: % used"`, a 24-digit percent, a `99:99pm (Bogus/Zone)`
clause, `Feb 30`, CRLF line endings, an indented session line, and the stale marker embedded
mid-prose. No exception in any case; each returned `None` or a well-formed `UsageReading`.

## Findings

**F1 — Important — the brief's own binding constraint "the session meter uses
`FIVE_HOUR_MAX_AHEAD_S`" is pinned by no test.** `usage.py:73`. Confirmed by mutation on a
private copy: rewriting that call to `max_ahead_s=SEVEN_DAY_MAX_AHEAD_S` leaves all six
tests green. The REAL fixture's session reset is only ~50 minutes ahead of NOW, so it clears
both bounds identically. The counterpart on the weekly meter IS pinned (M6 caught), which
makes the asymmetry easy to miss. Test gap, not an implementation defect — the shipped code
is correct — but it is exactly the invariant the spec calls out as the reason the bound became
per-call (spec 168-176: a widened session bound "would let a mis-parsed session reset
manufacture a week-long sleep"). Three lines close it:
`parse_usage_text("Current session: 9% used · resets Sep 12 at 7am (America/New_York)\n",
now=NOW).five_hour.resets_at is None`. The implementer named this in its self-audit; I
reproduced it rather than taking it on trust.

**F2 — Minor — the entire per-model *reset* path is unexercised.** `usage.py:81-83`. The only
per-model fixture line (`Current week (Fable): 0% used`) carries no reset clause, so its
trailing group is `""`. Two independent mutations survive: `mm.group(3)` -> `mm.group(2)`
(feeding percent digits to `parse_reset`), and the per-model bound `SEVEN_DAY` -> `FIVE_HOUR`.
Both confirmed SURVIVED. If a per-model line ever renders a reset clause, nothing in the suite
would notice the wrong group or the wrong bound.

**F3 — Minor — `UsageReading.fetched_at` is `datetime | None = None`, but both the brief's
Interfaces line and the spec (design doc line 135) declare it non-optional `datetime`.**
`usage.py:55-56`. `parse_usage_text` always populates it (`usage.py:87`), so nothing is wrong
today; the defaults only weaken the contract for the constructors Tasks 3-5 add, where a
`UsageReading` with `fetched_at=None` becomes constructible and any staleness check downstream
must handle it. Compounding it, no test asserts `fetched_at` at all — mutating `fetched_at=now`
to `fetched_at=None` survives all six tests (confirmed). Either drop the defaults or assert the
field once, before Task 4 depends on it.

**F4 — Minor — `import json` (`usage.py:20`) and `import subprocess` (`usage.py:22`) are unused
in Task 2.** They are Task 3's dependencies and the only trace of Task 3 in this diff. The brief
mandated them verbatim and the implementer correctly declined to "improve" the mandated block,
so this is scope creep in the brief, not by the implementer. No CI consequence: no
ruff/flake8/lint config exists in the repo or `packages/herder/pyproject.toml`, so nothing fails
on an unused import. Acceptable if Task 3 lands in the same branch; if Task 3 is deferred, drop
them.

**F5 — Minor — `.strip()` on the per-model key (`usage.py:81`) is dead against every known
input** and its removal survives the suite (confirmed). `([^)]+)` sits between `(` and `):`,
which in observed output never carries padding. Harmless defensiveness; noted so the
mutation-survival list is complete.

**F6 — Minor — `UsageReading` is `frozen=True` with a `dict` field**, so the generated
`__hash__` raises `TypeError` on any attempt to hash a reading (`usage.py:51-56`). `Meter` is
fine. No caller hashes one today; flagged in case Task 4 wants to memoize on one.

**F7 — Minor / observation — the `""` case in `test_missing_session_line_is_a_failed_read`
(`test_usage.py:49`) is redundant with the missing-session branch**: dropping `not text` from
`usage.py:67` leaves all six tests green, because `""` fails `_SESSION_RE` anyway. The guard is
NOT dead, though — it is the only thing that makes `parse_usage_text(None)` return `None`
instead of raising `TypeError` on the `in` test, and that (out-of-type-contract) input is
untested. Keep the guard; the test just does not test what it appears to.

**F8 — observation, no action — `percent` is not range-validated.** `Current session:
999999999999999999999999% used` parses into a Meter with that value. It fails safe for phase 2
(a huge percent makes `decide()` more conservative, not less), so this is a note for Task 4's
policy table, not a defect here.

## Could not verify from the diff

- **The full-suite result.** The implementer reports `1755 passed, 7 deselected`. Per the
  isolation rules I did not run the suite in the shared worktree, and ran no pytest at all — my
  mutation work used a hand-rolled runner over a private copy of `usage.py`/`limits.py`/
  `provider.py` with an asserted `__file__` anchor. The 1755 figure is yours to confirm.
- **The fixture's fidelity.** `REAL` is documented as captured verbatim from `claude -p "/usage"`
  on CLI 2.1.252. Not checkable from inside the repo; if the capture is wrong, every assertion in
  the file is wrong with it and the parser would still be green.

## Process notes

- No commits made (reviewer). Nothing in the worktree was modified; `usage.py`'s hash is
  unchanged at `44fa623339f6bb5c5e44047b1b9d28cce4c30320`.
- Mutation runs, private module copies and the probe script live in `$D/work/t2-spec/`; only
  `report.md`, `t2-spec.log` and the sentinel were written to `$D/t2-spec/`.
