# Final whole-branch code-quality verdict — usage-pacing phase 1

**Verdict: Changes requested** — four small items (one false comment, one unpinned
cross-package contract, two pieces of dead surface). Nothing structural; the feature
design is sound and the implementation hangs together. Total fix is roughly a dozen
lines and no behaviour change.

Reviewed: `9f4440e..8ac1e3c` (22 commits), read-only. No edits, no commits.
`git status --porcelain` is **empty** — confirmed before the first mutation, after
every restore, and after the final run.

---

## Instrument check

| run | result |
|---|---|
| BASELINE (pre-mutation) | 1741 passed, 7 deselected, 5.8s |
| RESTORED (post-mutation) | 1741 passed, 7 deselected, 6.8s |
| `git status --porcelain` before / after | empty / empty |
| HEAD before / after | `8ac1e3c` / `8ac1e3c` |

Baseline and restored agree; the instrument is sound. Every mutation ran with
`PYTHONDONTWRITEBYTECODE=1`, a `timeout 600`, a `__pycache__` sweep and a
`git checkout --` restore verified by `git status --porcelain` before the next one.
Log: `scratchpad/sdd/finalqual/finalqual.log`.

---

## Mutation kill table — 28 mutations, 25 KILLED, 3 SURVIVED

| # | mutation | result | killed by |
|---|---|---|---|
| M1 | `limits.classify` never matches (returns None) | KILLED | `test_claude_cli.py::test_session_limit_on_nonzero_exit_raises_rate_limited` (+6 more, **all herder-side** — see "end-to-end promise") |
| M2 | `RateLimited(HerderError)` → `RateLimited(Exception)` | **SURVIVED** | — (1741 green) |
| M3 | drop `RateLimited, classify, parse_reset` from `herder/__init__.py` | **SURVIVED** | — (1741 green) |
| M4 | `if not pace.enabled:` → `if False:` in `_process` | KILLED | `test_pace_loop::test_pacing_disabled_records_the_limit_as_a_show_failure` |
| M5 | `pace_options` hardcodes `enabled=True` (config ignored) | KILLED | same |
| M6 | delete gather's `except RateLimited: raise` (swallow into a flag) | KILLED | `test_stage_gather::test_gather_rate_limit_during_llm_alignment_propagates_and_does_not_flag` |
| M7 | drop `RateLimited` from `_with_transport_retry`'s no-retry tuple | KILLED | `test_llm_tasks::test_rate_limit_is_not_retried_as_transport_noise` |
| M8 | `sessions._write` never writes `pause_scope` | KILLED | `test_pace_loop::test_a_pause_records_the_reset_time_and_the_scope` |
| M9 | `unprocessed.extend(pending[idx:])` → `pending[idx + 1:]` | KILLED | `test_pace_loop::test_the_show_that_hit_the_limit_is_retried_not_dropped` |
| M10 | remove `set_capture_dir(...)` from `_execute` | KILLED | `test_pace_loop::test_the_run_switches_on_raw_capture_for_every_provider` |
| M11 | `capture_failure` is a no-op | KILLED | `test_claude_cli::test_a_failure_is_captured_when_a_capture_dir_is_set` |
| M12 | `resume_at` drops `reset_skew_s` | KILLED | `test_pace_loop::test_the_resume_hint_prints_a_max_wait_the_shell_can_actually_take` |
| M13 | delete the `MAX_RESET_AHEAD_S` bound in `parse_reset` | KILLED | `test_limits::test_reset_past_today_rolls_to_tomorrow_only_within_the_bound` |
| M14 | `classify` always passes `scope=None` | KILLED | `test_claude_cli::test_session_limit_on_nonzero_exit_raises_rate_limited` |
| M15 | KeyboardInterrupt branch calls `mark_incomplete`, not `mark_paused` | KILLED | `test_pace_loop::test_an_interrupt_during_the_wait_checkpoints_rather_than_losing_the_run` |
| M16 | progress watermark starts at `0` instead of `-1` | KILLED | `test_pace_loop::test_a_backend_that_keeps_refusing_checkpoints_instead_of_napping_forever` |
| M17 | `stalled = False` (no-progress guard removed) | KILLED | same |
| M18 | `_state_of` drops `STATE_PAUSED` (paused degrades to incomplete) | KILLED | `test_pace_loop::test_a_checkpoint_leaves_the_interrupted_show_for_the_resume` |
| M19 | `run list` stops printing `resumes <instant>` | KILLED | `test_run_namespace::test_run_list_shows_paused_label_and_resume_suffix` |
| M20 | `_session_json` drops `resume_after`/`pause_reason` | KILLED | `test_run_namespace::test_run_list_json_carries_the_resume_time_of_a_paused_run` |
| M21 | swap `_process`'s except arms (generic `HerderError` first) | KILLED | `test_pace_loop::test_the_show_that_hit_the_limit_is_retried_not_dropped` |
| M22 | `if limited:` stops re-queuing `deferred` (locked shows lost) | KILLED | `test_pace_loop::test_a_limit_mid_pass_keeps_the_shows_another_run_had_locked` |
| M23 | drop `pace.wait` from the sleep condition (`--no-wait` ignored) | KILLED | `test_pace_loop::test_a_checkpoint_carries_the_failures_the_run_had_already_taken` |
| M24 | `duration_arg` floors instead of ceilings | KILLED | `test_pace_loop::test_the_resume_hint_prints_a_max_wait_the_shell_can_actually_take` |
| M25 | `sleep_until` drops the naive-datetime guard | KILLED | `test_pacing::test_sleep_until_rejects_a_naive_when` |
| M26 | `resume_at` drops the naive `resets_at` clause | KILLED | `test_pacing::test_resume_at_declines_a_naive_reset_rather_than_guessing_its_zone` |
| M27 | `_execute`'s `if pace is None:` default raises instead of defaulting | **SURVIVED** | — (1741 green: the branch is dead) |
| M28 | `_ATTENTION_LABELS` loses its `STATE_PAUSED` entry | KILLED | `test_run_namespace::test_attention_dicts_carry_a_paused_entry` |

89% kill rate, and the kills are by the *right* tests — every queue-arithmetic mutation
was caught by a test whose name describes exactly that arithmetic. This is materially
better than the earlier rounds on this branch (7 and 22 survivors).

### The end-to-end promise

**Proven by composition, not by a single test.** M1 (classify neutered) kills 7 tests,
**every one of them herder-side**; not one llama test notices. The llama end-to-end
tests at `packages/llama/tests/test_sessions.py:335+` do drive the real CLI through the
real pipeline and real stages — but they inject an already-constructed `RateLimited`
at the *provider object* boundary, so the first hop (raw `claude -p` text →
`RateLimited`) is proven only in `test_claude_cli.py` isolation.

The chain is nevertheless unbroken and every link is individually mutation-pinned:
`claude_cli` classification (M1, M14) → `_with_transport_retry` pass-through (M7) →
`run_json_task`, which catches only `(ValidationError, ValueError)` and so cannot
swallow it (read, `tasks.py:97`) → gather's re-raise (M6) → `_execute`'s arm ordering
(M21) → the pause/queue machinery (M9, M15–M23). I could construct no mutation that
breaks the whole path while leaving the suite green.

Recommendation, not a blocker: one test that patches `subprocess.run` to return the
literal measured message, drops a real `ClaudeCLIProvider` into the existing
`test_sessions.py` fixture, and asserts a `paused` marker comes out would convert
composition into proof for about 15 lines. Filed as Minor #10.

---

## Findings

### Important

**1. `packages/llama/src/llama/stages/gather.py:999-1004` — the comment asserts the
opposite of what the branch shipped.**
> "That pause handler does not exist yet: today this still reaches `cli.py`'s per-show
> `except (TaskFailed, HerderError, IAError)` and is recorded as a per-show failure,
> same as any other unrecovered error — a later task is what makes the pause real."

The later task landed: `cli.py:262` catches `RateLimited` *before* that arm and pauses
the run. This is the one place on the branch where **the seams genuinely show** — a
Task-3-era comment survived Tasks 7 and 8 untouched, in the very module that raises the
exception, and it will mislead the next person debugging a pause. Comment-only fix.

**2. `packages/herder/src/herder/limits.py:53` — `RateLimited`'s `HerderError` base is
load-bearing and unpinned (M2 SURVIVED at 1741).**
Two places depend on it and neither is tested: `cli.py:262`'s ordering comment
("Caught BEFORE the HerderError arm below, which it subclasses" — M21 proves the
*ordering* matters, nothing proves the *subclassing*), and `cli.py:2643`'s
`except (LlamaError, HerderError)` in `main_cli`, which is exactly what CLAUDE.md's new
"boundary (b)" paragraph relies on when it promises a run-level `RateLimited` produces
"exit 1, no checkpoint" rather than a stack dump. Break the base class and that
documented behaviour silently becomes `except Exception: traceback.print_exc()` at
`cli.py:2652`. One assertion —
`assert isinstance(RateLimited("x"), HerderError)` in `test_limits.py` — closes it.

### Minor

**3. `packages/herder/src/herder/__init__.py:2` — the `RateLimited, classify,
parse_reset` re-export is dead (M3 SURVIVED).** Every consumer imports from
`herder.limits` directly: `cli.py:16`, `gather.py:8`, `tasks.py:7`, and all tests.
Deleting it makes the codebase uniform and simultaneously resolves deferred minor #13
(gather importing `RateLimited` from the submodule while the line above imports from the
package) — the right fix there is to drop the export, not to change gather.

**4. `packages/llama/src/llama/cli.py:180-181` — `_execute`'s
`if pace is None: pace = pace_options(config)` is dead (M27 SURVIVED).** All four call
sites (`_get_query`, `_get_profile`, `run_approve`, `run_resume`) pass a resolved
`PaceOptions` built by `_pace`. The default is worse than no default: a future caller
that forgets gets config values silently substituted for the operator's flags, instead
of a `TypeError` at the call site. Make `pace` a required parameter.

**5. `pause_scope` is write-only.** `sessions.py:30` writes it, `cli.py:331` sources it
from `RateLimited.scope`, and nothing anywhere reads it — `SessionInfo` has no field and
`_session_json` (`cli.py:2313-2322`) deliberately excludes it. M8 was killed only by an
assertion on the write itself. This makes the whole `scope` chain
(`_SIGNATURES`' `five_hour`/`seven_day` labels → `RateLimited.scope` → marker) an
unconsumed contract. Documented and deliberate; noting it because it is the branch's one
interface built and not consumed.

**6. `cli.py:184` — capture is switched on only inside `_execute`, but CLAUDE.md now
claims it is universal.** The new doc text says "Every failed `claude -p` is captured
whole under `~/.llama/llm-failures/`". `set_capture_dir` has exactly one non-test call
site, so no capture happens during `redo`, `fix`, `triage`, `deliver`, or any emcee run.
That matters because the doc's stated *purpose* for capture is learning the still-unobserved
7-day refusal wording — and a weekly limit is most likely to land in a long batch `redo`
(`cli.py:2030`), which is precisely where capture is off. Either widen the call or soften
the sentence.

**7. `~/.llama/llm-failures/` has no pruning, rotation, or size cap.** One file per failed
`claude -p`, forever.

**8. Two renderings of one concept.** `cli.py:355` prints `resumes 15:10` (localized
`%H:%M`); `cli.py:567` prints `resumes 2026-09-04T15:10:00+00:00` (raw ISO). These are
the two places an operator reads the same fact.

**9. `cli.py:163` — continuation indent is 11 spaces where the open paren wants 10.**
Same class as deferred minor #14; no linter is configured.

**10. No single test drives raw refusal text to a `paused` session.** See "The
end-to-end promise" above.

### Critical

None.

---

## Coherence, YAGNI, and the whole-branch judgement

**This reads as one designed feature, not eight stapled tasks.** Concerns are cleanly
separated one per module — `herder.failures` (capture), `herder.limits`
(classification), `llama.pacing` (policy and arithmetic), `cli._execute` (the loop) —
with the app→herder direction preserved throughout and no `llama` import anywhere in
`herder`. The three CLI commands take a byte-identical `--wait/--no-wait/--max-wait/
--no-pacing` block and all route through the single `_pace` helper. Error handling
varies only where it should: capture never raises, classification returns `None` rather
than guessing, both naive-datetime paths refuse rather than coerce and say why.

The docstrings are the branch's strongest feature and match this repo's established
idiom — they carry measured provenance (`limits.py:3-15`), the do-not-loosen rule, the
reason a false positive is worse than a false negative, and — in `test_pace_loop.py:1-9`
and `test_sessions.py:394-397` — an explicit note about which assertions would *still
pass* under the bug the test exists to catch. That last habit is what the branch's
mutation record is made of.

**Seams that show:** exactly two — finding #1 (the false comment) and finding #3 (an
export nobody uses, contradicting the codebase's own import convention).

**Duplication:** one real instance, and it is already on the deferred list — the three
near-identical raise sites in `claude_cli._run` (#12 below). The two `mark_paused` call
sites (`cli.py:349` and `cli.py:369`) are the other candidate; a `_checkpoint` closure
would be better, but at six arguments across two lines the drift risk is visible and a
mutation (M15) pins the weaker site.

**YAGNI: clean.** No usage-cache reader, no EWMA, no percent thresholds, no fixed rail,
no `llama pacing` command — grepped for all of them. `pacing.py:5-7` names them as
deliberately absent. The only speculative surface is the `seven_day` and generic
signatures in `_SIGNATURES`, both labelled "Unverified", both one regex line, both
degrading correctly to `scope=None`. That is the right amount of speculation.

---

## Deferred-minor triage — 16 items

| # | item | ruling |
|---|---|---|
| 1 | capture uniqueness via `time.monotonic_ns() % 1_000_000` | **deliberate, leave it** — ugly, but it is a diagnostic artifact name |
| 2 | ~1e-6 filename collision silently overwrites | **deliberate, leave it** — same reason; losing one capture is not a data loss |
| 3 | capture stamp is unmarked local time, filename only | **deliberate, leave it** — nice-to-have; the body already has cmd/exit/stdout/stderr |
| 4 | uniquifier test pins only probabilistically | **deliberate, leave it** — follows from #1/#2 being non-critical |
| 5 | `proc` unannotated, duck type undocumented | **deliberate, leave it** — the duck typing is intentional and item #11 depends on it |
| 6 | no hour-range guard (`25:10am` → 1:10am) | **deliberate, leave it** — `\d{1,2}` plus `% 12` bounds it and `MAX_RESET_AHEAD_S` catches the rest; a tighter `(1[0-2]\|0?[1-9])` would be free if anyone touches the regex |
| 7 | naive injected `now` reads as machine-local | **deliberate, leave it** — `now` is a test seam; production passes tz-aware or `None` |
| 8 | spring-forward resolves 1h late; `fold=0` undocumented | **deliberate, leave it** — `MAX_RESET_AHEAD_S` bounds the damage to one hour, twice a year |
| 9 | exact-equality rollover returns `now`, undocumented | **deliberate, leave it** — pinned, and the alternative is not better |
| 10 | `re.Pattern[str]`; `now = now or ...`; generic `herder.classify` export | **SPLIT: fix the export before merge** (= finding #3, delete it); the other two **deliberate, leave**. `now = now or ...` is a latent bug *shape* but a falsy `datetime` cannot exist |
| 11 | `_run`'s `TimeoutExpired` branch is uncaptured | **deliberate, leave it** — real, one line, correctly out of phase 1; backlog it with #12 |
| 12 | a `_fail(cmd, proc, message) -> NoReturn` helper | **deliberate, leave it** — I agree it is the right refactor and it is the branch's only real duplication, but doing it at a window's end is how the gaps it prevents get introduced. Backlog |
| 13 | gather imports `RateLimited` from `herder.limits` beside a `herder` import | **fix before merge** — but by deleting the export (finding #3), not by changing gather |
| 14 | continuation indent at `test_stage_gather.py:288` | **deliberate, leave it** — no linter; same class as my finding #9 |
| 15 | the spec's audit note misidentifies `cli.py:2505` | **fix before merge (docs-only)** — `docs/.../2026-09-04-usage-pacing-design.md:368` still says `cli.py:1902`/`cli.py:2505` "belong to `fix`/`triage`". 2505 is `main_cli`. Task 7 was warned and did not trust it, but the spec is now a permanent doc with a wrong claim in it |
| 16 | `cli.py:1902`/`2030` batch `redo` loop burns one limit hit per show | **deliberate, leave it** — correctly out of scope and documented. Note it is also the loop with no failure capture (finding #6) |

**Follow-ups filed as not-minors:** all four correctly out of phase 1. I verified the
first two are now genuinely documented in `CLAUDE.md` (the openrouter-429 and
run-level-stage boundaries), not merely claimed to be — that documentation is the best
part of the branch's write-up and should not be trimmed.

**Merge-blocking:** none of the deferred minors. The four items I want fixed first are
findings #1, #2, #3 and #4 above, plus deferred #15 — roughly a dozen lines across five
files, no behaviour change, and #3 subsumes deferred #13 and #10's export half.

---

## Confirmations

- `git status --porcelain` is **empty**. Verified before the first mutation, after each
  of the 28 restores, and after the final run.
- HEAD unchanged at `8ac1e3c`. No edits, no commits made by this review.
- BASELINE 1741 == RESTORED 1741. Instrument sound.
- Not BLOCKED.
