# Task 7 — code-quality verdict

**Verdict: Changes requested** (two required pins; the shipped behaviour is correct in both cases —
what is missing is the test that would stop it silently becoming wrong).

Reviewed read-only against `42d90a4..980e02b` on `usage-pacing`. No edits, no commits; every
mutation restored and `git status --porcelain` verified empty at the end (see the bottom of this
file). Baseline and final: **1736 passed, 7 deselected**.

---

## Summary of the merits review

The loop is correct. I walked it by hand and then drove `_execute` directly through eight scenarios
the test suite does not cover (script: `<scratchpad>/sdd/t7qual/drive.py`, transcript in
`t7qual.log`): the limit landing on the last entry of the first pass with a lock-deferred show
earlier; on the only entry; on an entry in the deferred pass; on the *last* deferred entry; a real
failure plus a limit on both the sleeping and the checkpointing branch; a held show plus a limit; and
a backend alternating refuse/succeed across four shows. **No show was dropped, none was processed
twice to completion, and every scenario terminated.**

Why that holds structurally:

- `pending` and `deferred` are disjoint by construction. A lock-deferred entry always sits at an
  index *below* the index at which `limited` is set, and `unprocessed.extend(pending[idx:])` starts
  at that index — so the `unprocessed.extend(deferred)` on the next line cannot double-queue.
  (`cli.py:299-310`.)
- The deferred pass only runs when the first pass finished un-limited, so at that point the only
  unprocessed entries are exactly `deferred`; `deferred[idx:]` therefore covers the whole remainder.
- The outer `while pending:` terminates because an entry leaves the queue only by completing, and a
  cycle that completes nothing is caught by `stalled`. Every non-stalled cycle strictly shrinks the
  queue.
- The pause is **outside** `file_lock` — `if limited:` sits after the `try/except Locked` block, and
  the sleep is after the `for`. A paused process holds no per-show lock, so it cannot block another
  `llama` for hours. This is the property the task most needed to get right and it is right.

Other checks that came back clean:

- **`sleep_until` can never see a naive datetime.** `resume_at` returns either `_now() + Δ` (aware)
  or `resets_at + skew` guarded on `tzinfo is not None` (`pacing.py:124-127`). `resume_after` is
  **display-only** — the only two readers are `cli.py:568` and `cli.py:2323`, both of which print the
  string. Nothing parses it back into `sleep_until`. The implementer's departure from the brief here
  is the right call: the brief's literal code would have turned a pause into a `ValueError` crash.
- **`duration_arg` is a genuine fix, not gold-plating.** `parse_duration` really does reject
  `format_delta`'s `2h 0m` on the space, so the brief's hint printed a command that would not run.
  I checked the new function across its own range by hand: `0 → 1m`, `30 → 1m`, `90 → 2m`,
  `3600 → 1h`, `3601 → 1h1m`, `108000 → 30h`, negative → `1m`. All parse, none rounds short.
- **Ctrl-C during a pause** checkpoints and prints the resume hint; Ctrl-C anywhere else exits 130
  quietly through `main_cli` (`cli.py:2648`). No traceback on either path.
- **No YAGNI / no phase-2 creep.** No usage-cache reader, no EWMA, no percent thresholds, no fixed
  rail, no `llama pacing` command. The `_session_json` widening is two always-present nullable keys
  and is argued for in the report; I agree, and `test_status_cmd`'s exact key-set assertion caught it,
  which is the system working.
- Python 3.11+, no new third-party dependencies, tests offline and deterministic (frozen `_now`,
  stubbed `_sleep`, `tmp_path` roots, no real sleeping).

---

## Findings

### Important

**I1. The paused marker's `failures[]` is unpinned — `cli.py:341` (and `cli.py:355` on the KBINT path).**
Mutant `N7` replaces `mark_paused(ws, _outcome(), failures, …)` with `mark_paused(ws, _outcome(), [], …)`
and the **entire suite stays green (1736 passed)**. This is reachable: driver scenario 6 produces
`state=paused, outcome='1 failed', failures=['a']` — a run that lost a show to a real error and *then*
hit a window. `sessions.mark_incomplete`'s own docstring names that list as "the only durable record
of WHY, since the per-show handler otherwise only prints to stderr"; the pause path inherits that
responsibility and nothing holds it there. One assertion in
`test_a_checkpoint_leaves_the_interrupted_show_for_the_resume` (or a new scenario with a failure
before the limit) closes it.

**I2. Two of the three terms in the no-progress guard are unpinned — `cli.py:328`.**
`done_now = packaged + held + len(failures)`. Mutants `N3` (drop `len(failures)`) and `N4` (drop
`held`) **both survive the full suite**; only the `packaged` term is pinned, by
`test_progress_between_pauses_still_earns_another_sleep`. Both mutants cause a **premature
checkpoint**: a cycle whose only progress was a held or failed show reads as stalled, and the run
stops early with shows still queued. That is the same operator-visible failure as a silently skipped
show, spelled with a different verb, and it is exactly the class this task was told to guard. The
shipped choice is the correct one — a held or failed show leaves the queue permanently, so it *is*
progress — and it deserves a test saying so. Cheapest fix: extend
`test_progress_between_pauses_still_earns_another_sleep` with a variant whose between-pause progress
is a held show and another whose progress is a failure.

**I3. A `RateLimited` from a run-level stage still loses the whole run (filed, not a regression).**
`run_search` / `run_winnow` (`cli.py:213-218`) and `run_interpret` (`cli.py:392`, outside `_execute`
entirely) are not covered by the pause machinery. A refusal there reaches `main_cli` (`cli.py:2643`)
as `error: …` plus exit 1 — no pause marker, no resume hint, run lost. `winnow` is the LLM-heaviest
run-level stage (`score_reviews` + `light_research` per candidate), so it is a likely place for a
session limit to actually land. The brief scopes this task to the show boundary and the behaviour is
identical to `42d90a4`, so this is **not a defect in the delivered work** — but "a usage limit never
costs you a run" is not yet true, and the implementer's Concern 1 should be filed rather than closed.

### Minor

**M1. `wait_s <= pace.max_wait_s` boundary unpinned — `cli.py:334`.** `M9` (`<=` → `<`) survives.
Only the exact tie is affected and the two branches stay mutually exclusive either way, so no show is
lost. Cosmetic.

**M2. Two pacing config knobs are only ever exercised at their defaults — `pacing.py:106-107`.**
Replacing `parse_duration(cfg.reset_skew)` with the literal `120.0` (`Q14`) or
`parse_duration(cfg.unknown_reset_wait)` with `3600.0` (`P10`/`Q15`) survives the full suite: no test
sets a non-default value for either. `enabled`, `wait` and `max_wait` are properly pinned; these two
are config keys that could stop working without anything noticing.

**M3. The checkpoint hint's `--max-wait` suffix condition is unpinned — `cli.py:348-350`.** `Q10`
(append unconditionally) survives. On the two checkpoint paths that are *inside* the cap (`--no-wait`,
and the `stalled` guard) the mutant prints e.g. `--max-wait 12m`, advice that would make the operator's
next run checkpoint sooner rather than later. Shipped conditional is right.

**M4. `--no-pacing`'s `FAILED <show>: <err>` stderr line is unpinned — `cli.py:265`.** `Q17` survives;
`test_pacing_disabled_records_the_limit_as_a_show_failure` asserts the marker's `failures[]` but not
the operator-visible line. The escape hatch is specified to reproduce the old behaviour *exactly*, and
the old behaviour printed that line.

**M5. `duration_arg`'s sub-minute floor is unpinned — `pacing.py:47`.** `P12` (drop `max(1, …)`)
survives: no test drives a checkpoint whose over-cap wait is under 60 s (needs roughly
`--max-wait 0m`). The mutant emits `0m`, which `parse_duration` accepts as 0 — a hint that would make
every subsequent run checkpoint immediately. Low reachability; noting it because the floor is
deliberate and undefended.

**M6. `max_wait or cfg.max_wait` treats `""` as "not given" — `pacing.py:105`.** `P14` (rewrite as
`cfg.max_wait if max_wait is None else max_wait`) survives. `--max-wait ""` currently falls back to
the config default instead of failing the eager validation. The `wait` parameter two lines above uses
the stricter `is None` convention; matching it would be consistent and free.

**M7. `_execute`'s `pace=None` default is unpinned for `enabled` — `cli.py:180-181`.** `P15` (default
to `enabled=False`) survives. The one caller relying on the default is `_redo_run_level`
(`cli.py:2055`), i.e. `llama redo --run … --from search|winnow`, which takes no pacing flags.
Deliberate per the report, but nothing stops it silently losing pacing.

**M8. The same instant is printed in two zones on two surfaces.** `cli.py:337` prints
`resumes {when.astimezone():%H:%M}` — local, time only, no date. `cli.py:568` prints
`resumes {s.resume_after}` — raw UTC ISO with the date. An operator who checkpoints at 22:00 local and
then runs `llama run list` sees two different-looking renderings of one fact. Related nit on
`cli.py:330`: `paused after 1 shows` (grammar), and its count excludes failures while `done_now` two
lines above includes them — driver scenario 6 prints `paused after 0 shows` after one show had already
failed.

**M9. `resume_at`'s unknown-reset fallback is scope-blind — `pacing.py:126`.** The observed grammar in
`herder.limits` only carries a `resets …` clause for the 5-hour window, so a `seven_day` refusal takes
the 1 h default and writes `now + 1h` into the marker as `resume_after` — confidently wrong for a
weekly window. The run itself still behaves correctly (1 h nap, refuse again, no-progress guard
checkpoints); it is the *recorded instant* that misinforms whoever reads `run list`. Phase-1
reactive-only makes this defensible; worth filing rather than changing here.

**M10. A vacuous assertion — `packages/llama/tests/test_pace_loop.py:236` and `:246`.**
`held = {"b"}` … `assert held == {"b"}`. Nothing in the test ever mutates `held`; the `_file_lock`
stub matches on `path.parent.name`, not on that set. It reads like a pin and pins nothing.

**M11 (observation, no action).** With default config the checkpoint-over-cap branch is unreachable in
production: `herder.limits.MAX_RESET_AHEAD_S` caps a parsed reset at 5.5 h, `+2m` skew keeps it under
the 6 h `max_wait`, and the unknown-reset fallback is 1 h. The branch is reached only via a lowered
`--max-wait` (which is the point of the flag) or a hand-built `RateLimited` like the 30 h fixture in
`test_sessions.py`. Not a defect — worth knowing that the 30 h fixture is not a shape `herder` can
produce.

---

## Mutation kill table

70 mutants applied one at a time to the working tree, full suite run under a 120 s subprocess timeout
with `PYTHONDONTWRITEBYTECODE=1`, `__pycache__` cleared and `git status --porcelain` checked after
every restore. Harnesses: `<scratchpad>/sdd/t7qual/mut.py`, `mut2.py`, `mut3.py`; log: `t7qual.log`.

**54 KILLED · 14 SURVIVED · 1 INVALID · 1 HANG.**

### Wave 1 — the brief's known-dangerous list, plus the first pass of my own

| # | mutation | file:line | result |
|---|---|---|---|
| M1 | `unprocessed.extend(pending[idx:])` → `pending[idx+1:]` | cli.py:308 | KILLED |
| M2 | `if limited:` moved to the TOP of the `for` body (the original plan defect) | cli.py:300-309 | KILLED |
| M3 | no-progress guard removed (`stalled = False`) | cli.py:329 | KILLED |
| M3b | no-progress guard inverted (`!=`) | cli.py:329 | KILLED |
| M4 | `unprocessed.extend(deferred[idx:])` → `deferred[idx+1:]` | cli.py:319 | KILLED |
| M5 | `unprocessed.extend(deferred)` dropped on the limited path | cli.py:311-312 | KILLED |
| M6 | `except RateLimited` arm deleted (falls into the `HerderError` arm) | cli.py:263 | KILLED |
| M7 | the limit appended to `failures[]` after all | cli.py:271-272 | KILLED |
| M8 | `_pacing._now()` → module-level rebound `_now` (import-time binding trap) | cli.py:325 | KILLED |
| **M9** | **`wait_s <= max_wait_s` → `<`** | **cli.py:334** | **SURVIVED** |
| M10 | `pace.wait` ignored (always sleeps) | cli.py:334 | KILLED |
| N1 | `pending = unprocessed` dropped before `continue` | cli.py:344 | KILLED |
| N2 | `done_before_pause` watermark never updated | cli.py:330 | KILLED |
| **N3** | **`done_now` drops `len(failures)`** | **cli.py:328** | **SURVIVED** |
| **N4** | **`done_now` drops `held`** | **cli.py:328** | **SURVIVED** |
| N5 | deferred pass takes the lock non-blocking | cli.py:317 | KILLED |
| N6 | Ctrl-C writes `mark_complete` instead of `mark_paused` | cli.py:339 | KILLED |
| **N7** | **`mark_paused(…, failures, …)` → `[]`** | **cli.py:341** | **SURVIVED** |
| N8 | `while pending:` → `if pending:` | cli.py:296 | INVALID (SyntaxError: `continue` outside loop) |
| N9 | `unprocessed` hoisted out of the cycle (shared across passes) | cli.py:298 | KILLED |
| N10 | `if not limited: break` removed | cli.py:321-322 | KILLED |
| N11 | `duration_arg` floors instead of ceils | pacing.py:47 | KILLED |
| N12 | `duration_arg` drops the minutes component | pacing.py:51 | KILLED |
| N13 | `resume_at` accepts a naive `resets_at` | pacing.py:125 | KILLED |
| N14 | `sleep_until`'s naive guard removed | pacing.py:66-67 | KILLED |
| N15 | `pace_options` ignores the `wait` flag | pacing.py:104 | KILLED |
| N16 | `pace_options` ignores `--max-wait` | pacing.py:105 | KILLED |
| N17 | `--no-pacing` does not clear `enabled` | cli.py:169 | KILLED |
| N18 | eager `--max-wait` validation removed | cli.py:165-169 | KILLED |
| N19 | `set_capture_dir(...)` removed | cli.py:184 | KILLED |
| N20 | `scope = limited.scope` → `None` | cli.py:327 | KILLED |
| N21 | reset skew dropped from `resume_at` | pacing.py:127 | KILLED |
| N22 | `_outcome()` stops reporting failures | cli.py:288-289 | KILLED |
| N23 | final `mark_incomplete`/`mark_complete` collapsed to always-complete | cli.py:363-366 | KILLED |

### Wave 2 — beyond the implementer's list

| # | mutation | file:line | result |
|---|---|---|---|
| P1 | lock-deferred shows dropped instead of queued (`deferred.append` → `pass`) | cli.py:305 | KILLED |
| P2 | no `break` after the limit (rest of the pass keeps running) | cli.py:309 | KILLED |
| P3 | deferred pass: limit re-queues nothing | cli.py:318-320 | KILLED |
| P4 | `deferred` merged into `unprocessed` on BOTH branches (double-queue) | cli.py:311 | KILLED |
| P5 | checkpoint marker records `_now()` instead of `when` | cli.py:341 | KILLED |
| P6 | Ctrl-C marker records `_now()` instead of `when` | cli.py:339 | KILLED |
| P7 | `mark_paused` outcome → `None` | cli.py:341 | KILLED |
| P8 | "shows left" counts `pending`, not `unprocessed` | cli.py:342 | KILLED |
| P9 | `if not pace.enabled:` inverted | cli.py:264 | KILLED |
| **P10** | **unknown-reset fallback hard-codes 3600 s** | **pacing.py:126** | **SURVIVED** |
| P11 | `format_delta`'s 60 s floor removed | pacing.py:32 | KILLED |
| **P12** | **`duration_arg` drops its `max(1, …)` floor** | **pacing.py:47** | **SURVIVED** |
| P13 | `parse_duration` accepts the empty string | pacing.py:25 | KILLED |
| **P14** | **`max_wait or cfg.max_wait` → `is None` check** | **pacing.py:105** | **SURVIVED** |
| **P15** | **`_execute`'s `pace=None` default becomes `enabled=False`** | **cli.py:180-181** | **SURVIVED** |
| P16 | `sleep_until` naps once instead of chunking | pacing.py:71 | KILLED |
| P17 | `sleep_until`'s `remaining <= 0` → `< 0` | pacing.py:69 | KILLED |
| P18 | `stalled` ignored in the sleep condition | cli.py:334 | KILLED |
| P19 | `limited` not cleared before `continue` | cli.py:343 | **HANG** (see note) |

**P19 note — the brief's warning about a hang is real, and it is informative.** With `limited` left
stale, the loop re-processes the head of the queue every cycle; each re-process increments `packaged`,
so `done_now` keeps rising, `stalled` never fires, and the run naps forever. Both
`test_pace_loop.py` and `test_sessions.py` hang rather than fail (60 s `timeout`, rc=143). The
takeaway for the shipped code: **`stalled` is not the termination bound** — termination rests on
`limited = None` plus the fact that an entry leaves the queue only by completing. That holds as
shipped (verified by hand and by all eight driver scenarios), but the guard should not be read as a
safety net it is not.

### Wave 3 — display, JSON and session-marker surfaces

| # | mutation | file:line | result |
|---|---|---|---|
| Q1 | `_session_json` drops `resume_after` | cli.py:2323 | KILLED |
| Q2 | `_session_json` drops `pause_reason` | cli.py:2323 | KILLED |
| Q3 | `run list` drops the `resumes …` column | cli.py:567-568 | KILLED |
| Q4 | `STATE_PAUSED` removed from the attention list | sessions.py:85 | KILLED |
| Q5 | `mark_paused` writes `STATE_INCOMPLETE` | sessions.py:67 | KILLED |
| Q6 | `SessionInfo` stops reading `resume_after` back | sessions.py:133 | KILLED |
| **Q7** | **`paused after {packaged + held} shows` → a constant** | **cli.py:330** | **SURVIVED** |
| Q8 | the "no progress since last pause" line removed | cli.py:331-332 | KILLED |
| Q9 | the "exceeds --max-wait" explanation removed | cli.py:346-348 | KILLED |
| **Q10** | **`--max-wait` hint suffix appended unconditionally** | **cli.py:349-350** | **SURVIVED** |
| Q11 | the resume hint names the wrong run | cli.py:342-343 | KILLED |
| **Q12** | **the `resumes HH:MM (Nm)` pre-sleep line removed** | **cli.py:336-337** | **SURVIVED** |
| Q13 | `pace_options` hard-codes `enabled=True` | pacing.py:103 | KILLED |
| **Q14** | **`reset_skew_s` hard-coded to 120.0** | **pacing.py:107** | **SURVIVED** |
| **Q15** | **`unknown_reset_wait_s` hard-coded to 3600.0** | **pacing.py:106** | **SURVIVED** |
| Q16 | `sleep_until` stops echoing progress | pacing.py:73-75 | KILLED |
| **Q17** | **`--no-pacing` drops its `FAILED …` stderr line** | **cli.py:265** | **SURVIVED** |

### Unpinned constraints, stated plainly

1. `failures[]` reaching the **paused** session marker (I1) — the one I would insist on.
2. **held** shows and **failed** shows counting as progress in the no-progress guard (I2) — likewise.
3. The `wait_s <= max_wait_s` tie (M1).
4. `pacing.reset_skew` and `pacing.unknown_reset_wait` at any non-default value (M2).
5. The `--max-wait` hint suffix appearing only when the wait actually exceeded the cap (M3).
6. `--no-pacing`'s `FAILED …` stderr line (M4).
7. `duration_arg`'s sub-minute floor (M5).
8. `pace_options`' empty-string `--max-wait` handling (M6).
9. `_execute`'s `pace=None` default having `enabled=True` (M7).
10. The pre-sleep `resumes HH:MM` line and the `paused after N shows` count (Q7/Q12, M8) — cosmetic.

Everything on the brief's known-dangerous list is **dead**, including all four bookkeeping mutations,
both no-progress mutations, the except-ordering swap, the failures-append, and the import-time
`_now` rebinding trap. The implementer's 14-mutant self-test is corroborated; the survivors above are
all outside the set it ran.

---

## Required before approval

1. Pin `failures[]` on the paused marker (I1).
2. Pin `held` and `len(failures)` as progress in the no-progress guard (I2).

Everything else is optional. I2 in particular is one parametrized variant of an existing test.

## Recommended follow-ups (file, do not do here)

- I3: run-level stages (`interpret`/`search`/`winnow`) are outside the pause machinery.
- M9: `resume_at`'s unknown-reset fallback is scope-blind, so a `seven_day` pause records a wrong
  `resume_after`.
- M8: pick one rendering of the resume instant across the checkpoint line and `run list`.

## Housekeeping

`git status --porcelain` is **empty**. `git log --oneline -1` → `980e02b`. Full suite re-run after
the last restore: **1736 passed, 7 deselected**. No edits, no commits, no subagents.
