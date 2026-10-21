### Spec Compliance
- ✅ Spec compliant. All four interfaces match the brief and spec §3 exactly: the six `KIND_*` constants (sessions.py:20-25); `classify_failure` in the mandated order (sessions.py:28-43), with the first-match order load-bearing because `RateLimited`, `TaskFailed` and `ResearchNotSupported` all subclass `HerderError` (checked: herder/provider.py:13,17 and limits.py:106) and `IADownloadError` subclasses `IAError` (ia_client.py:49); `failure_record` returns `{show, error, kind, at}` with the class-name fallback for an empty `str()` (sessions.py:46-50); `failure_kind` reads legacy records (sessions.py:53-60). Both `_execute` sites use `failure_record(pid, exc)` (cli.py:580, 590). The FAILED echo text and the exception text are unchanged, so the `download of <filename>` prefix survives into `error` (raised at ia_client.py:444).
- ⚠️ Cannot verify from the diff alone: none of substance. I took the claim that "no existing whole-dict assertions needed changing" as a named risk and grepped for it. Every whole-list `failures ==` comparison either compares against `[]` or round-trips a hand-built dict through `mark_incomplete` (test_sessions.py:547, test_run_namespace.py:199/544/556). The `_execute`-driven assertions compare `f["show"]` only (test_pace_loop.py:213/335/400; test_sessions.py:589/728). So the claim holds.

### Strengths
- The parametrized `test_classify_failure_follows_the_order` cases catch every order mutation that matters: RateLimited before HerderError, TaskFailed before HerderError, ResearchNotSupported before HerderError, IADownloadError before IAError, plus the fallthrough to other.
- `failure_kind` copes with records that have no `error` key (`{"show": "s"}` is tested), which keeps persisted state permissive as required.
- `now` can be injected. The UTC offset is asserted both on an injected value and on the default `datetime.now(timezone.utc)` path.
- The end-to-end `test_execute_records_kind_for_a_failed_show` goes through the real `_execute` catch arm via `_drive`, not a unit stub.
- Named risk, an import cycle from `sessions.py` now importing `llama.ia_client`. Checked ia_client.py:1-18: it imports only download_slots, errors, status and workspace, never sessions, so there is no cycle.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. cli.py:560: the comment `# {show, error} per show this run lost` is now stale, since the records carry `kind`/`at`. Update it to `{show, error, kind, at}`.
2. sessions.py:48: `failure_record` trusts a caller-supplied `now`. A naive datetime would persist an `at` with no offset, which breaks the docstring's "UTC ISO". No caller passes `now` today. Either convert with `.astimezone(timezone.utc)` or reject naive values.
3. Test coverage: no test drives the `--no-pacing` `RateLimited` site (cli.py:580) to check that it records `kind == "rate-limited"`. That site is otherwise identical to the tested one, so this is breadth, not a correctness gap.
4. test_sessions.py:1659-1664: the new imports sit mid-module rather than in the import block at the top of the file (E402 style). `RateLimited`, `pytest`, `datetime` and `timedelta` are already imported at the top (lines 4, 7, 21). Move the new ones up for consistency.
5. test_pace_loop.py `test_execute_records_kind_for_a_failed_show` does not assert that `failure["error"]` starts with `download of `. That prefix is the cross-task contract the legacy rule and the operator's greps depend on. One extra assertion would pin it end to end.

### Assessment
**Task quality:** Approved
**Reasoning:** The implementation matches the brief and spec §3 exactly, with the ordering pinned by tests that would catch any subclass-order mutation, and legacy records are read permissively. The only findings are a stale comment, a naive-`now` edge and small test-breadth gaps.
