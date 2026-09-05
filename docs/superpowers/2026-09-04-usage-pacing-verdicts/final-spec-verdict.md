# Final whole-branch spec-compliance verdict — usage pacing, phase 1

Branch `usage-pacing`, 22 commits `9f4440e..8ac1e3c`. Read-only review.
Suite re-run from repo root with `./.venv/bin/python -m pytest -q`:
**1741 passed, 7 deselected** (matches the reported figure; `llama`/`herder`
both resolve inside this checkout).

## Overall spec verdict: ✅

Phase 1 delivers every commitment the spec makes for it. Nothing half-builds
phase 2: there is no snapshot reader, no `UsageMeter`, no percent threshold,
no `shows_per_batch`/`--batch`, no `llama pacing` command, and no config field
for any of them. `[pacing]` carries exactly the five keys `pace_options`
consumes. No blocking findings; the residue is documentation staleness and
cosmetics.

## Promise-by-promise

| Spec promise | Delivered at | Holds end to end? |
| --- | --- | --- |
| A limit is *classified*, not collapsed into a flat `HerderError` | `herder/limits.py:31-41,53-65,99-105`; raised from `claude_cli.py:128-133` (returncode branch) and `:145-150` (`is_error` envelope) | ✅ `RateLimited(HerderError)` with `scope`/`resets_at`. Negative pin `test_dropped_connection_stays_a_plain_herder_error` keeps CLOSED_MID a plain `HerderError`. Ordering of `_SIGNATURES` pinned by `test_specific_pattern_wins_when_generic_also_matches`. |
| Not retried as transport noise | `herder/tasks.py:40` | ✅ In the no-retry tuple with `TaskFailed`/`ResearchNotSupported`. Also verified it is not re-swallowed by `run_json_task`/`run_research_task`'s validation loop (`tasks.py:93-103,122-133` catch only `ValidationError`/`ValueError`) — pinned by `test_rate_limit_is_not_retried_as_transport_noise` and `test_rate_limit_propagates_from_a_research_task`. |
| Not recorded as a per-show failure | `cli.py:263-272` (`except RateLimited` **above** `except (TaskFailed, HerderError, IAError)` at `:273`) | ✅ Sets `limited` and returns; `failures[]` untouched. The escape hatch (`--no-pacing`/`enabled=false`) deliberately restores the old failure entry — pinned by `test_pacing_disabled_records_the_limit_as_a_show_failure`. |
| Second swallow site closed | `stages/gather.py:993-1005` (`except RateLimited: raise` above the broad clause) | ✅ Pinned by `test_gather_rate_limit_during_llm_alignment_propagates_and_does_not_flag`, which also asserts `show.json` is not written. Independent audit of every broad `except` on the `_execute` path confirms the spec's conclusion: `setlistfm.py:96`, `jerrybase.py:128`, `audio.py:37`, `correspondence.py:307` are `except Exception` but contain **no** provider/LLM call (grepped for `run_json_task`/`run_research_task`/`.complete(`/`.research(` — zero hits in all four), so none can see a `RateLimited`. |
| Reset instant comes from the refusal text, with no dependence on Claude Code state files | `herder/limits.py:48-50,68-96`; consumed via `pacing.resume_at` (`pacing.py:122-137`) | ✅ `limits.py` opens no file and imports only stdlib + `herder.provider`. Sanity bound `MAX_RESET_AHEAD_S = 5.5h` pinned on both sides (`test_reset_just_over_the_bound_is_refused` / `..._under_...`), zone-from-message pinned (`..._in_the_zone_the_message_names_not_the_callers`), DST pinned, 12am/12pm pinned. |
| Run checkpoints as `paused`, `run list` surfaces it | `sessions.py:17,22-32,59-67,84-85,102-103,133-134`; `cli.py:346-360` (`mark_paused`), `:567-568` (`resumes <instant>` on the table), `:2306-2309` (attention label + hint), `:2319-2323` (`--json`) | ✅ `attention_sessions` is `state != complete`, so a paused run stays on the list. `_write` is wholesale, so a later `mark_complete`/`mark_incomplete` erases the pause block (`test_sessions.py:320-325`). |
| Resume costs nothing for shows already packaged | Pre-existing `workspace.should_run`, gating every stage: `interpret.py:8`, `discover.py:34`, `search.py:35`, `select_recording.py:53`, `gather.py:826`, `research.py:13`, `vet_research.py:162`, `brief.py:126`, plus `package` | ✅ structurally — every LLM-bearing stage early-returns on an existing artifact, and this branch changed none of that. ⚠️ The spec's named test ("a fake provider with a call counter proves already-packaged shows make zero LLM calls on re-entry") was never written; the plan omitted it. Behaviour is delivered, the pin is not. Minor. |
| `max_wait` governs whether a pause is waited out | `cli.py:361-372`; `pacing.pace_options`/`PaceOptions.max_wait_s` | ✅ `if not stalled and pace.wait and wait_s <= pace.max_wait_s: sleep` else checkpoint, with the over-cap line and a `--max-wait <duration_arg>` hint that round-trips through `parse_duration` (`test_the_resume_hint_prints_a_max_wait_the_shell_can_actually_take`, `test_duration_arg_round_trips_through_parse_duration`). R21's no-progress guard is present at `cli.py:341-345` and pinned three ways (packaged/held/failed each counted as progress). |
| Ctrl-C during a pause is a clean checkpoint | `cli.py:365-370` | ✅ `KeyboardInterrupt` around `sleep_until` → `mark_paused` → `return` → exit 0, same resume command. Pinned by `test_an_interrupt_during_the_wait_checkpoints_rather_than_losing_the_run`. |
| A limit on the *first* show checkpoints and exits 0 (R20) | Same path — the loop has no first-show special case | ✅ `done_before_pause = -1` guarantees the first pause is never "stalled", so the first show behaves like the seventh. |
| Raw failure capture, switched on once | `herder/failures.py`; `cli.py:181-184` | ✅ Capture on all four `_run` failure branches (`returncode`, non-JSON stdout, `is_error`, missing `result`), each pinned; `set_capture_dir` called once in `_execute`, pinned by `test_the_run_switches_on_raw_capture_for_every_provider`. |

## Coherence across tasks

The loop rewrite (`cli.py:296-380`) is internally consistent under trace:
`unprocessed` always receives the show that hit the limit (`pending[idx:]`,
sliced **after** the call) plus every still-`Locked` deferral, with no
duplication (deferrals only accrue at indices `< idx`) and no drop. The
`while` terminates in every path — `if not limited: break` on a clean pass, and
the one-cycle no-progress guard bounds a backend that keeps refusing.

Findings:

1. **Minor — stale code comment contradicting shipped behaviour.**
   `stages/gather.py:998-1004` still says "That pause handler does **not exist
   yet**: today this still reaches `cli.py`'s per-show `except (TaskFailed,
   HerderError, IAError)` and is recorded as a per-show failure … a later task
   is what makes the pause real." Task 7 built that handler. The comment now
   describes the opposite of what happens. *Fix before merge* (delete the last
   four lines of the comment).

2. **Minor — `pause_scope` is written and never read.** `sessions._write`
   persists it (`sessions.py:30`) and `cli.py:349,358` supply it, but there is
   no `SessionInfo.pause_scope`, no renderer, and it is excluded from
   `_session_json`. The only reader is a test (`test_pace_loop.py:413`). This
   is *documented as deliberate* at `cli.py:2314-2318`, has forward value for
   phase 2's window-aware rendering, and costs one JSON key. **Deliberate,
   leave it** — but it is genuinely write-only today, so say so rather than
   letting a later reader assume it is consumed.

3. **Minor — unconsumed top-level re-exports.** `herder/__init__.py:2` exports
   `classify` and `parse_reset`; nothing outside `herder` imports either
   (`claude_cli` uses `herder.limits.classify`, `llama` imports only
   `RateLimited`). Harmless surface area. Leave.

4. **Minor — a fourth `_execute` funnel the flags do not reach.**
   `_redo_run_level` (`cli.py:2055`, i.e. `llama redo --run S --from
   search|winnow`) re-enters `_execute` with `pace=None`, so it silently
   inherits config pacing — including `wait = true`, which can park that
   command for up to 6 h with no `--no-wait`/`--max-wait`/`--no-pacing` to
   override. Behaviour is *correct* (a limit there pauses and checkpoints);
   the spec's "Flags on `get`, `run resume` and `run approve` (all three funnel
   into `_execute`)" is simply incomplete. Backlog, not merge-blocking.

5. **Minor — no retention policy on `~/.llama/llm-failures/`.** Every failed
   `claude -p` writes a file; nothing prunes. Fine at today's volumes, worth a
   backlog line.

6. **Minor (cosmetic) — `paused after {packaged + held} shows`**
   (`cli.py:347`) omits shows lost to real failures, so a run with 2 packaged
   and 1 failed reports "paused after 2 shows" having processed 3. The very
   next line prints the accurate `{len(unprocessed)} shows left`. Leave.

No dead code, no duplicated constant, no config key without a reader, no
interface built and never consumed (beyond items 2–3 above).

## Spec truthfulness

Both late-added limitations were verified **against the code, not the prose**:

- **openrouter 429 gap — TRUE.** `openrouter.py:36-37` raises a bare
  `HerderError(f"openrouter returned {resp.status_code}: …")` on any non-200.
  `classify()` is called nowhere in that module (grep: zero hits for
  `classify`/`RateLimited`/`429`), and the message text matches none of
  `_SIGNATURES`. So a 429 there is retried 3× by `_with_transport_retry` and
  then fails the show, exactly as CLAUDE.md:265-271 and the spec state.
- **`interpret`/`search`/`winnow` gap — TRUE.** `run_discover`
  (`cli.py:191-197`), `run_search` (`:216`) and `run_winnow` (`:218-221`) are
  called bare, with no `try`. `_execute` has no pre-flight check. A
  `RateLimited` from any of the three reaches `main_cli`'s
  `except (LlamaError, HerderError)` (`cli.py:2643-2647`), which prints
  `error: …` and `SystemExit(1)`; no `mark_*` runs, so no `session.json` is
  written and there is no `paused`/`resume_after`. Precisely as R22 says.

Three inaccuracies remain in the docs:

7. **Minor — the spec's status header is stale.** Line 3 still reads
   "Status: approved design, **not yet implemented**." Phase 1 is implemented
   and merged into this branch. *Fix before merge* — one line.

8. **Minor — the R22 amendment's own audit note is wrong about a line it
   cites.** The spec (and the amendment added in `8c98dc8`) says
   "`cli.py:1902`/`cli.py:2505` belong to `fix`/`triage`, outside `_execute`."
   Verified against the branch point: `9f4440e:cli.py:1902` is the batch
   `redo --state` loop's `except (LlamaError, TaskFailed, HerderError,
   IAError)`, and `9f4440e:cli.py:2505` is **`main_cli`'s global boundary**,
   which wraps `_execute` too. Neither belongs to `fix`/`triage`. This was
   already caught in `deferred-minors.md` and carried into Task 7's dispatch,
   but never corrected in the spec — so the one section written to be truthful
   contains a false provenance claim, and it sits two paragraphs below the
   (correct) R22 statement that depends on `main_cli` catching the exception.
   Behaviourally harmless; *fix before merge* as a doc correction.

9. **Minor — `run list`'s own help text was not updated.** `cli.py:578`:
   "List sessions awaiting approval or incomplete (the attention-list)" — it
   now also lists `paused`. Trivial; fix before merge or leave.

Everything else the spec describes but the branch does not build (percent
rules, staleness ladder, EWMA, fixed rail, `llama pacing`, `--batch`,
`--force`, the false-positive cross-check, the snapshot-reader tests) is
phase 2, correctly named in the plan's "Out of scope (phase 2)", and is **not**
faulted here. The one place that boundary is untidy is the spec's *Testing*
section, which still lists the snapshot-reader and false-positive-cross-check
tests without a phase marker, while its neighbouring mutation list item 4 *did*
get one. Cosmetic asymmetry; leave.

## Deferred-minor triage

Task 1:
1. `time.monotonic_ns() % 1_000_000` uniquifier — **deliberate, leave it** (debug aid; needs same second + same pid to matter).
2. ~1e-6 collision silently overwrites — **deliberate, leave it** (same reasoning; loss is one capture file).
3. Capture stamp unmarked local time, filename only — **deliberate, leave it** (backlog: an ISO-UTC line in the body would be one line).
4. `test_each_capture_gets_its_own_file` pins the uniquifier only probabilistically — **deliberate, leave it** (a deterministic pin needs a patched clock for little gain).
5. `proc` unannotated / duck type undocumented — **deliberate, leave it** (all three attributes are read via `getattr` with defaults; the docstring names them).

Task 2:
6. No hour-range guard (`25:10am` → 1:10am, while `11:75am` is rejected) — **deliberate, leave it.** Asymmetric with the minute guard, but `MAX_RESET_AHEAD_S` bounds the damage and no such message exists. Note the asymmetry in the backlog.
7. Naive injected `now` reads as machine-local — **deliberate, leave it** (production passes `None` → aware UTC; every test passes aware).
8. Spring-forward resolves 1 h late; fall-back correct by `fold=0` — **deliberate, leave it** (a 1 h error on two days a year, absorbed by `reset_skew` and the re-probe).
9. Exact-equality rollover undocumented — **deliberate, leave it** (pinned by `test_reset_exactly_now_rolls_to_tomorrow`).
10. `re.Pattern[str]`, `now = now or …` vs `is None`, generic `herder.classify` export — **deliberate, leave it** (typing/cosmetic; no datetime is falsy).

Batch:
11. `_run`'s `TimeoutExpired` branch uncaptured — **deliberate, leave it; backlog.** A real diagnostic gap (a 900 s hang leaves nothing), a one-line fix, but outside phase 1's promise and additive.
12. A `_fail(cmd, proc, message) -> NoReturn` helper — **deliberate, leave it** (refactor; the four branches are now all correct and pinned).
13. `gather.py` imports `RateLimited` from `herder.limits` while the line above imports from `herder` — **deliberate, leave it** (cosmetic; both are legal for an app module).
14. Continuation indent at `test_stage_gather.py:288` — **deliberate, leave it** (no linter configured; `cli.py:162`'s `_pace` signature has the same one-space drift).
15. The spec's audit note misidentifies `cli.py:2505` — **FIX BEFORE MERGE.** Verified wrong (see finding 8); a doc-only correction.
16. `cli.py:1902` batch `redo` loop still burns one limit hit per show — **deliberate, leave it; backlog** (outside `_execute`, outside phase 1's stated guarantee).

Also-filed follow-ups:
17. `RateLimited` from `interpret`/`search`/`winnow` loses the run — **deliberate, leave it.** Verified true; now documented in the spec (R22) and CLAUDE.md. Phase 2's pre-flight gate.
18. `openrouter.py:37` plain `HerderError` on 429 — **deliberate, leave it.** Verified true and documented.
19. `cli.py:1902` (duplicate of 16) — **deliberate, leave it; backlog.**
20. A `_checkpoint(when, scope, reason)` closure for the two `mark_paused` sites — **deliberate, leave it** (both sites are now pinned; the refactor is a nicety).

**Merge-blocking: none.** Recommended before merge, all documentation and all
one-liners: #15 (spec audit note), finding 1 (stale `gather.py` comment),
finding 7 (spec status header), finding 9 (`run list` docstring).

## ⚠️ Cannot verify from diff

- That the shipped `_SIGNATURES` match a **real** future refusal. Only the one
  measured 5-hour string exists as evidence; the `seven_day` and generic
  patterns are admitted guesses in the module's own comments, and a 7-day
  refusal that matches none of the three degrades to a plain `HerderError` —
  i.e. the pre-change failure mode, not a pause.
- That `_error_detail` preserves the `resets …` clause for every real refusal
  envelope shape. Only the measured shape is fixtured; a refusal whose message
  exceeds 500 chars before the clause would classify with `resets_at=None` and
  fall back to `unknown_reset_wait`.
- Real sleeping, real signal delivery and real terminal behaviour. `_sleep` is
  monkeypatched and `KeyboardInterrupt` is raised synthetically; a SIGINT
  arriving inside `process_show` rather than inside `sleep_until` is *not*
  checkpointed (it exits 130 via `main_cli`), which is per spec but untested.
- Whether `~/.llama/llm-failures/` growth is acceptable in practice.
- The `--wait`-inside-the-cap message shape as an operator sees it: with
  `--no-wait` and a short wait, the run prints no "resumes HH:MM" line at all,
  only the "N shows left" hint. Read as intended; not pinned as such.

## Tree state

`git status --porcelain` clean at the end of this review. I made **no** edits
and **no** commits. Note for the orchestrator: partway through, the working
tree briefly showed `packages/llama/src/llama/pacing.py` with
`enabled=cfg.enabled` mutated to `enabled=True`, and then
`packages/llama/src/llama/stages/gather.py` modified — both self-reverted
within seconds. That is a **concurrent agent running a mutation pass** against
the same checkout (a `finalqual` scratch dir exists alongside this one), not
this reviewer. I touched nothing and reverted nothing. The 1741-pass suite run
reported above completed before that activity began.
