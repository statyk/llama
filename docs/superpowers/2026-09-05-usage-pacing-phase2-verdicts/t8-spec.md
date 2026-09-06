# Task 8 — SPEC-COMPLIANCE review

## Verdict

**Spec PASS.**

Every enumerated requirement of `$D/briefs/task-8-brief.md` is delivered, and the
three authorized rulings (R15/R16/R17) are applied correctly. Nothing from the
brief is missing. The extras are small, defensible, and I endorse all three (see
"Unauthorized deviations" below).

One **Important** finding stands (I1, the concern I was asked to rule on). It is
an inherited defect in a brief-mandated string, not a failure to implement the
brief, which is why the verdict is PASS rather than FAIL — but I recommend it be
fixed before merge rather than deferred, and I give a concrete four-clause fix.

---

## How I verified (isolation honoured)

I did not modify `/Users/shawn/projects/llama-wt-pacing2` and did not run the
suite there. Everything below ran against snapshots materialized with
`git archive`, executed with `"$WT/.venv/bin/python" -m pytest` (never a
`.venv/bin/*` console script) and `PYTHONPATH` shadowing.

**Shadowing proved, twice.** First by resolution:

```
$ PYTHONPATH="$S/packages/llama/src:$S/packages/herder/src:$S/packages/emcee/src" \
    "$WT/.venv/bin/python" -c "import llama, herder; print(llama.__file__); print(herder.__file__)"
.../work/t8-spec/snap/packages/llama/src/llama/__init__.py
.../work/t8-spec/snap/packages/herder/src/herder/__init__.py
```

Then by a **planted sentinel** — a `raise RuntimeError("SENTINEL-T8SPEC")` at the
top of the snapshot's `_pacing_line`:

```
$ ... -m pytest packages/llama/tests/test_pacing_decide.py \
      packages/llama/tests/test_cli_commands.py packages/llama/tests/test_pace_loop.py -q
38 failed, 53 passed in 1.73s          # sentinel planted
91 passed in 0.48s                     # sentinel removed
```

The check demonstrably reports both outcomes, so the green result is not the
"never looked" failure mode. `cli.py` was restored from a backup and
`grep -c SENTINEL-T8SPEC` returns 0.

**Full-suite count not re-measured** — that is the orchestrator's measurement by
the isolation rule; I verified the 91 task-relevant tests only. Named as
unverified, below.

---

## Requirement-by-requirement

| # | Brief requirement | Status |
| --- | --- | --- |
| 1 | `pacing.shows_that_fit(reading, per_show_delta, ceiling) -> int \| None`, body as given | **Delivered, byte-identical.** `pacing.py:233`, guard `reading is None or reading.five_hour is None or not per_show_delta`, return `max(0, int((ceiling - reading.five_hour.percent) // per_show_delta))`. Two extra docstring paragraphs; no behavioural change. |
| 2 | 3 tests in `test_pacing_decide.py` (ceiling-not-100, unknown-without-estimate, floors-at-zero) | **Delivered verbatim**, all three present and passing. |
| 3 | `_pacing_line(reading, state, pace)` in `cli.py`, exact string/separator/conditionals | **Delivered verbatim** at `cli.py:221` — em dash, `·` separator, conditional `weekly`/`est`/`~N fit before`, `%H:%M` via `astimezone()`. |
| 4 | `llama pacing` Typer command with the given body | **Delivered** at `cli.py:1369` (decorator) / `1372` (`def pacing()`), immediately after `pipeline`. R15 applied: `_meter(config, pace)` with `pace = pace_options(config)` built first. `load_config(_config_path)` per the brief's comment. Early `return` on `reading is None`; `Proceed`/`verdict.reason` branch as written. |
| 5 | 2 tests + `_usage_reading` / `_cfg_file` helpers in `test_cli_commands.py` | **Delivered verbatim.** |
| 6 | Print `_pacing_line` **once** in `_execute`, immediately after the verdict returns `Proceed` | **Delivered** at `cli.py:270-283`, after the `PauseUntil` early-return and before `set_capture_dir` / `run_discover`. Printed once, not per show. |
| 7 | Append `"; the remaining {count - fits} pause until the reset"` when `fits < count` | **Delivered verbatim.** |
| 8 | **Do not reduce `count`** | **Honoured.** `count` reaches `choose_entries` untouched; pinned by `test_the_run_start_line_names_the_shortfall_without_shrinking_the_run`, whose `counts == [3]` assertion the implementer's mutation 5 kills. |
| 9 | R15: `_meter(config, pace)` at both new call sites | **Applied correctly** (`cli.py:265`, `cli.py:1382`). |
| 10 | R16: bind the pre-flight reading once and reuse it | **Applied correctly.** `reading = _meter(config, pace)` at `cli.py:265`, consumed by both `decide()` and `_pacing_line`/`shows_that_fit`. No second `_meter` call anywhere in `_execute`. |
| 11 | R17: brief's rendered shape, not the spec's `~6 of 13` | **Applied.** No `count` inside `_pacing_line`; the consequence clause is appended by `_execute` only. |
| 12 | CLAUDE.md clause under "Run (llama, acquisition)" | **Delivered**, one clause after `llama pipeline`, matching the surrounding style. |

### Global constraints

- **Offline/deterministic** — ✓. New tests use `_clock`, fixed `NOW`, injected readings; no subprocess, no sleep, no real `$HOME` (`_cfg_file` writes a `root =` config into `tmp_path`).
- **`read_usage`/`parse_usage_text` never raise** — untouched by this diff. ✓
- **Backend gating** — `_meter` untouched. I proved empirically that `read_usage` is *not* called under `openrouter` or `--no-pacing` (probe below installs `pytest.fail` as `read_usage`; both probes pass). ✓
- **`RateLimited` before `HerderError`** — this diff adds no `except` blocks. Existing ordering at `cli.py:327` (run-level) and `cli.py:389` (show loop) is unchanged. ✓
- **`openrouter.py` untouched** — ✓, `git diff --stat` lists 6 files, none of them it.
- **No `--batch` / `--force` / `trust_age`** — ✓, `git diff 6f7c126..a42c051 | grep 'trust_age\|--batch'` → none.

### RED-before-GREEN reproduced independently

I did not take the implementer's word for it. Snapshot of `6f7c126` with only the
two test files taken from `a42c051`:

```
$ ... -m pytest packages/llama/tests/test_pacing_decide.py \
      packages/llama/tests/test_cli_commands.py -q -k "fit or pacing_command"
5 failed, 38 deselected in 0.27s
```

Failures: `AttributeError: module 'llama.pacing' has no attribute 'shows_that_fit'`
(×3) and `assert 2 == 0 … SystemExit(2)` (×2, `No such command 'pacing'`) —
exactly the brief's Step-2 prediction, and exactly what the implementer reported.

---

## MISSING

Nothing from the brief.

## EXTRA (everything not in the brief's snippets)

1. `Proceed` added to the `from llama.pacing import …` list — **required** by the
   command's own body as the brief wrote it. Not really extra.
2. `@app.command(rich_help_panel="Watch", short_help=…)` + `"pacing"` in
   `_COMMAND_ORDER` (implementer deviation 3).
3. `from conftest import cli_invoke` in `test_cli_commands.py` (deviation 4).
4. `choose=` parameter on `test_pace_loop.py::_drive` + two new tests there
   (deviation 5).
5. Extra explanatory docstring paragraphs on `shows_that_fit` and `_pacing_line`,
   and comment blocks at `cli.py:262-264` and `cli.py:271-275`. Prose only.
6. Three commits rather than the brief's single `git commit` in Step 5. Neutral —
   the TDD split is what CLAUDE.md's incremental-commit guidance wants, and each
   commit names a real test command.

---

## Ruling on the concern I was asked to decide

> `_meter` returns `None` for three reasons and `_execute` prints
> `"usage read unavailable — pacing on limit errors only"` in all three.

### The factual claims — verified myself, not taken on trust

**Claim: `_meter` has three `None` paths.** Confirmed. `cli.py:216`:

```python
    if not pace.enabled or config.llm_for("default").backend != "claude_cli":
        return None
    return read_usage()
```

Three: `pace.enabled` false, backend not `claude_cli`, and `read_usage()`
returning `None`. `_pacing_line` sees only the `None` and cannot distinguish them.

**Claim: the same line is printed on all three.** Confirmed empirically. Three
probes driven through `_execute` (probe file removed after the run; the two
gate-path probes install `pytest.fail` as `read_usage`, so a passing probe *is*
proof the meter was never read):

```
NO-PACING OUT>>   'usage read unavailable — pacing on limit errors only'
OPENROUTER OUT>>  'usage read unavailable — pacing on limit errors only'
FAILED-READ OUT>> 'usage read unavailable — pacing on limit errors only'
3 passed in 0.15s
```

Corroborated independently by the sentinel run: `_pacing_line` raising broke
`test_no_pacing_never_reads_the_meter`, which proves the formatter is on the
`--no-pacing` path.

**Claim: under `--no-pacing` there is no pacing on limit errors.** Confirmed, with
a correction to the implementer's wording. There are *two* handlers, and they
behave differently:

- `cli.py:340` (run-level stages): `if not pace.enabled: raise` — re-raises, exit 1.
  This is the "re-raises" the implementer described.
- `cli.py:393` (show loop): `if not pace.enabled:` echoes
  `FAILED <pid>: <exc>` and appends to `failures` — it does **not** re-raise; the
  show is recorded as a loss and the run continues.

Different mechanics, same conclusion: with `--no-pacing` nothing pauses on a
limit error. The sentence's second clause is false.

**Claim: openrouter never produces a `RateLimited`.** Confirmed by construction.
`grep -rn "classify(" packages/*/src` returns exactly two call sites, both in
`herder/claude_cli.py` (lines 130 and 147). `herder/openrouter.py:37` raises a
plain `HerderError` on any non-200. No openrouter response can become a
`RateLimited`, so "pacing on limit errors only" promises a backstop that does not
exist on that backend.

**One thing the implementer did not report, and it is the sharper half.** The same
defect afflicts `llama pacing` itself, where it is worse, because that command
exists precisely to answer "what is my pacing situation":

```
PACING/openrouter exit 0 out>> 'usage read unavailable — pacing on limit errors only\n'
PACING/disabled   exit 0 out>> 'usage read unavailable — pacing on limit errors only\n'
PACING/happy      exit 0 out>> 'pacing: 5h 65% · weekly 7% · est 4.2%/show · ~5 fit before 18:00\nwould proceed\n'
PACING/pause      exit 0 out>> 'pacing: 5h 95% · weekly 7%\nwould pause: 5h window at 95%\n'
```

On the first two the command reports a *read failure* for a read it never
attempted, then returns without a verdict — an operator with `[pacing] enabled =
false` is told their meter is broken.

### The ruling

**It is a spec divergence, not merely an infelicitous rendering of a mandated
string** — but the divergence originates in the brief, not in the implementation.
The spec assigns that sentence to exactly one case, at
`2026-09-05-usage-pacing-phase2-design.md`:

> When the read fails, one line says so and the proactive rules are skipped for
> that boundary, falling back to the reactive backstop:
> ```
> usage read unavailable — pacing on limit errors only
> ```

"When the read fails" is a scope, and the diff renders the string outside it. The
implementer was right to flag it and right not to silently redesign it; the fix is
a design call, which is what I am making here.

Graded **Important**, not Critical: no behaviour is wrong, no state is corrupted,
and the first clause ("usage read unavailable") is true on all three paths — only
the second clause lies. But it lies on a supported, documented flag, and lies to
the one command an operator runs to get a straight answer, so I would fix it
before merge rather than roll it into the final-review minors.

### Which option

Not (b): it drops the "the proactive gate is blind this run" warning that the spec
explicitly wants, and does nothing for `llama pacing`, which must always answer.

Not (c): rewording to something true in all three cases costs the spec its exact
sentence in the exact case the spec wrote it for, and hands `llama pacing` a
vaguer answer — the implementer's own objection, and I agree with it.

**Take (a), extended to cover `llama pacing` — call it (a′).** It is the only
option that keeps the spec's sentence attached to the spec's case. Concretely:

```python
def _meter_applies(config: Config, pace: PaceOptions) -> bool:
    """Whether a reading is even attempted. `_meter` returns None both when it
    could not read and when it did not try; only the caller that knows which
    may say why."""
    return pace.enabled and config.llm_for("default").backend == "claude_cli"
```

- `_meter` gates on it (one line, unchanged behaviour, no duplicated predicate).
- `_execute`: wrap the whole three-line forecast block in
  `if _meter_applies(config, pace):`. A run that opted out has nothing to report,
  and silence is not a false statement.
- `pacing`: before the `_pacing_line` call, `if not _meter_applies(config, pace):`
  echo the actual reason (`"pacing disabled"` when `not pace.enabled`, else
  `f"no usage window on the {config.llm_for('default').backend} backend"`) and
  return. `_pacing_line`'s existing early return then serves only the genuine
  read failure, which is what the spec scoped it to.

Cost ≈ 8 lines. **It does not disturb either brief-mandated CLI test**: I verified
that `Config()`'s default backend is `claude_cli` (`config.py:200`) and
`PacingConfig.enabled` defaults `True` (`config.py:109`), so
`test_pacing_command_says_so_when_the_meter_cannot_be_read` sits on the
genuine-failed-read path and keeps its `"unavailable"` assertion. Two new tests
are needed (a `--no-pacing` run prints no pacing line; `llama pacing` on
`openrouter` names the backend) — `test_no_pacing_never_reads_the_meter` passes
either way, so it cannot serve as the guard.

If the orchestrator prefers to defer, (a′) is a clean standalone follow-up and
nothing in Task 9+ depends on the string.

---

## The three unauthorized deviations, judged freshly

**Deviation 3 — `rich_help_panel="Watch"` + `_COMMAND_ORDER`. ACCEPT, and I would
have required it.** `grep -n rich_help_panel cli.py` shows every one of the 16
`@app.command` sites carries a panel; a bare `@app.command()` would have put
`pacing` in an unnamed group *below* "Sessions & config", which reads as an
oversight rather than a design. The brief's own words are "in the shape of `llama
pipeline`", and `pipeline` is `@app.command(rich_help_panel="Watch", …)` at
`cli.py:1339` — the line above `pacing`'s. The `_COMMAND_ORDER` entry makes the
placement deterministic rather than falling to `len(_COMMAND_ORDER)`. Rendered
help verified: **Watch** panel now reads `status / show / pipeline / pacing`.
`short_help` is the panel's one-line column and every sibling has one. In spec.

**Deviation 4 — `from conftest import cli_invoke`. ACCEPT, unavoidable.** The
brief's test bodies call `cli_invoke` and the brief's own `_cfg_file` docstring
says "`cli_invoke` lives in conftest.py", but `cli_invoke` is a plain function at
`conftest.py:4`, not a fixture, so it is not auto-injected. Without the import the
brief's verbatim tests do not run at all. The pattern is established in **four**
other files in this suite (`test_triage.py:14`, `test_show_cmd.py:15`,
`test_cli.py:8`, `test_fix.py:11` — I printed each). Behaviourally identical to
the file's `runner.invoke` convention. The alternative (rewriting the brief's test
bodies) would have been the worse deviation.

**Deviation 5 — two extra `test_pace_loop.py` tests + the `choose=` parameter.
ACCEPT.** The brief's five tests are all reachable only through `llama pacing`,
which has no `count`, so the shortfall clause the brief explicitly specifies
would have shipped with **zero** coverage — the brief asks for behaviour it gives
no test for, and closing that is what a reviewer would otherwise have demanded.
The file choice is not the implementer's discretion: the global constraints say
run-level integration tests belong in `test_pace_loop.py` and not `conftest.py`.
The `choose=` parameter is the more interesting half and it is *correct*: `_drive`
sets `cli.choose_entries` **after** the caller's own monkeypatches, so a test
patching `choose_entries` to observe `count` is silently clobbered and its
assertion measures nothing — precisely this branch's four-times-paid failure mode.
Threading the override the way `winnow=`/`search=` already are is the right fix,
and all 48 `test_pace_loop.py` tests pass with it.

---

## Findings

### Critical
None.

### Important

- **I1.** `"usage read unavailable — pacing on limit errors only"` is printed on
  the two paths where the meter was never read (`--no-pacing`; any non-`claude_cli`
  backend), where its second clause is false; the spec scopes that sentence to a
  failed read. Affects both `_execute` and `llama pacing` (where it also suppresses
  the verdict line). Fix: **(a′)** above, ~8 lines + 2 tests. Evidence in the ruling
  section.

### Minor (record and triage at final review; do not fix now)

- **M1.** Spec's `llama pacing` section asks for "the three meters"; the rendered
  line shows two (`5h`, `weekly`) — `UsageReading.per_model` is never displayed.
  Brief-mandated formatter, so not an implementation error; a brief/spec gap for
  the plan owner. One line in `_pacing_line` if wanted.
- **M2.** The unavailable branch is the only `_pacing_line` return without the
  `pacing: ` prefix, so at run start it is the one line nothing marks as pacing
  output. Brief-verbatim. Falls out for free if I1 is taken.
- **M3.** When `fits` is known but `five_hour.resets_at` is `None`, `_execute`
  appends "…pause until the reset" onto a line that names no reset and shows no
  forecast. Reachable (unparseable reset). Brief-mandated shape.
- **M4.** Commit `ea14004`'s trailer says "(16 passed)"; the real result at that
  commit is **13 passed** — I re-ran it from a snapshot of `ea14004`. Self-reported
  by the implementer; message-only, the named command is exact.
- **M5.** `_pacing_line` uses `astimezone()`, i.e. the machine's local zone. Correct
  for an operator-facing line and brief-specified; the tests assert only
  `"~2 fit before"`, so the suite stays zone-independent. Recorded so nobody later
  "fixes" it to UTC.
- **M6.** CLAUDE.md's new clause describes the meters/cost/forecast but omits the
  `would proceed` / `would pause: …` verdict line the command also prints.

---

## Could not verify from the diff

- **The full-suite count (1835 passed, 7 deselected).** The isolation rule reserves
  the suite to the orchestrator, so I ran only the 91 task-relevant tests
  (`test_pacing_decide.py`, `test_cli_commands.py`, `test_pace_loop.py` → `91
  passed`) from a sentinel-proven snapshot. The orchestrator's own measurement at
  `a42c051` stands unchallenged by anything I found.
- **Nothing else.** Every other requirement was checkable from the diff and the
  branch source.

---

## Commands run (all from snapshots; `S`/`R`/`E` are `git archive` extractions,
`PY="$WT/.venv/bin/python"`, `PP="$S/packages/llama/src:$S/packages/herder/src:$S/packages/emcee/src"`)

```
git archive a42c051 | tar -x -C "$D/work/t8-spec/snap"
PYTHONPATH="$PP" "$PY" -c "import llama, herder; print(llama.__file__); print(herder.__file__)"
      -> both resolve inside the snapshot

PYTHONPATH="$PP" "$PY" -m pytest packages/llama/tests/test_pacing_decide.py \
    packages/llama/tests/test_cli_commands.py packages/llama/tests/test_pace_loop.py -q
      -> 91 passed in 0.48s
      (with the SENTINEL raise planted in _pacing_line: 38 failed, 53 passed in 1.73s)

PYTHONPATH="$PP" "$PY" -m pytest packages/llama/tests/test_zz_t8spec_probe.py -q -s
      -> NO-PACING / OPENROUTER / FAILED-READ all print the identical
         'usage read unavailable — pacing on limit errors only'; 3 passed

PYTHONPATH="$PP" "$PY" -m pytest packages/llama/tests/test_zz_t8spec_probe2.py -q -s
      -> PACING/openrouter and PACING/disabled print the same string and no verdict;
         PACING/happy -> 'pacing: 5h 65% · weekly 7% · est 4.2%/show · ~5 fit before 18:00' + 'would proceed';
         PACING/pause -> 'would pause: 5h window at 95%'; 4 passed

git archive 6f7c126 | tar -x -C "$D/work/t8-spec/red"   # + the two test files from a42c051
PYTHONPATH=<red> "$PY" -m pytest ... -q -k "fit or pacing_command"
      -> 5 failed, 38 deselected in 0.27s        (RED reproduced)

git archive ea14004 | tar -x -C "$D/work/t8-spec/ea"
PYTHONPATH=<ea> "$PY" -m pytest packages/llama/tests/test_pacing_decide.py -q
      -> 13 passed in 0.15s                      (commit message says 16)

COLUMNS=100 "$PY" -c "<CliRunner --help>"        -> Watch panel: status / show / pipeline / pacing
grep -rn "classify(" packages/*/src              -> only claude_cli.py:130, :147
git diff 6f7c126..a42c051 | grep "trust_age\|--batch"   -> none
git diff --stat 6f7c126..a42c051                 -> 6 files, openrouter.py not among them
```

Both throwaway probe files were deleted from the snapshot after the runs; the
worktree was never written to, and the snapshot's `cli.py` was restored from
backup (`grep -c SENTINEL-T8SPEC` → 0).

## Blocked / refused

Nothing. No tool refused any call and no permission was denied.
