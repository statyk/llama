# Code-quality verdict — Tasks 3 / 4 / 4b (usage-pacing phase 1)

Reviewer: code-quality. Read-only. Range `4b5a2d2..682240d` (3 commits) on `usage-pacing`.

## Verdict: **Approved**

One Important finding, which is test-only and does not affect the behaviour of the
shipped code; the rest are Minor. The batch's crux invariant — a `RateLimited` is
never swallowed, downgraded or retried — is correct end to end on every path I could
trace, and every behavioural constraint in it is **mutation-proven load-bearing**
(5 of 5 killed). The two surviving mutations are both on `capture_failure`, a
diagnostics side-effect that has no production caller until Task 7.

---

## 1. Does the invariant hold end to end?

Traced a session-limit refusal from `subprocess.run` to the show loop:

- `claude_cli._run:127-133` (non-zero exit — the **measured** signature, per
  `limits.py:3-11`) builds `message`, captures, `classify(message)` → raises the
  `RateLimited`. Correct.
- `claude_cli._run:139-145` (`is_error` envelope) — same shape. Correct.
- `tasks._with_transport_retry:40` re-raises on the first raise; no sleep, no second
  call. Correct, and the docstring now carries the *reason* (window is empty, not
  "definitive verdict"), which is the right distinction to record.
- `tasks.run_json_task:93-103` / `run_research_task:122-133` — the outer ladder loops
  catch only `(ValidationError, ValueError)` around `model_validate_json`, and
  `HerderError` is not a `ValueError` (`provider.py:4`), so nothing there can swallow
  it or escalate a tier against an empty window. Verified by reading, not assumed.
- `gather.py:993-999` re-raises before the broad clause. Verified by grep that
  `gather.py:1000` was the **only** broad `except HerderError` in any llama stage —
  `interpret`, `winnow`, `research`, `vet_research`, `brief`, `artist_index` all call
  `run_json_task`/`run_research_task` bare, so they propagate for free. No other
  swallow site exists in the stage layer.
- It then lands in `cli.py:237`'s `except (TaskFailed, HerderError, IAError)` and is
  recorded as a per-show failure. That is today's behaviour and is Task 7's job to
  change; not a defect of this batch (see Minor-1 for the comment that says otherwise).

**No surviving path in llama swallows, downgrades or retries it.**

### Failure paths in `_run` that skip `classify`

| `_run` path | `classify`? | verdict |
|---|---|---|
| `TimeoutExpired` / `FileNotFoundError` (125-126) | no | **Correct.** The text is our own `f"claude invocation failed: {e}"`, not the backend's; a limit refusal exits promptly rather than timing out, and none of the three signatures can appear in a `TimeoutExpired` repr. |
| `json.JSONDecodeError` (136-138) | no | **Defensible omission.** Reachable only at `returncode == 0`; the measured refusal is exit 1, and a non-zero exit with non-JSON stdout already classifies, because `_error_detail:107` falls back to `stderr or stdout`. Undocumented, though — see Minor-2. |
| `result` not a string (146-148) | no | **Correct.** `is_error` is false here; there is no failure text to classify. |

---

## 2. Capture placement

`capture_failure(cmd, proc)` is called on **3 of the 5** raise sites in `_run`:
non-zero exit (129), not-JSON (137), `is_error` (141). Not called on the
`TimeoutExpired`/`FileNotFoundError` branch or on the "no string `result` field"
branch (see Minor-3, Minor-4).

- **Ordering vs `classify`:** immaterial to behaviour — `classify` is total and cannot
  raise (`parse_reset` wraps `ZoneInfo` in `try/except`, bounds the hour via
  `%12` on a `\d{1,2}` group, and range-checks the minute). Capture-**before**-raise is
  the part that matters and is right on all three sites; capture-before-classify is
  the defensively correct order anyway.
- **Double capture:** impossible within one `_run` (every branch raises). Across
  `_with_transport_retry` a transport failure captures once per *attempt* — that is one
  file per real invocation, which is what the feature is for, not duplication.
- **Leak:** none. The prompt is passed as `input=prompt` on stdin and never appears in
  `cmd` (`_run:117-119` builds `cmd` from the binary, flags and model only), so the
  `cmd:` line in a capture cannot contain it. The body writes the backend's own
  stdout/stderr, which is exactly the intended payload.

---

## 3. `except RateLimited: raise` in `gather`

**Right call.** Placing an explicit clause above the broad one keeps the broad clause's
meaning intact ("an alignment failure degrades to a review flag") and states the
exception at the call site; narrowing the broad clause with an `isinstance` guard would
have buried the intent in a predicate. It also matches the file's heavy
comment-the-trade-off style.

The comment is accurate on the part that matters: I verified
`workspace.should_run:66-67` is `force or not path.exists()` and `show.json` is
gather's stage artifact (`show_stage_artifacts:94`), so a flag written here really
would be permanent across a resume. Control flow after the re-raise is right — it skips
the `if llm_result is not None …` block, the `flags.append`, and `write_artifact` at
`gather.py:1138-1139`, so **nothing at all is persisted**.

---

## 4. Test hygiene — mutation table

Run in-place in the main tree, `PYTHONDONTWRITEBYTECODE=1`, full suite
(`./.venv/bin/python -m pytest -q -p no:randomly`) per mutation, source restored from an
in-memory copy after each. Baseline: 1681 passed / 7 deselected.

| # | Mutation | Result | Killed by |
|---|---|---|---|
| M1 | `claude_cli._run` `is_error` branch: drop `classify` | **KILLED** | `test_session_limit_in_an_error_envelope_raises_rate_limited` |
| M2 | `claude_cli._run` returncode branch: drop `classify` | **KILLED** | `test_session_limit_on_nonzero_exit_raises_rate_limited` |
| M3 | `tasks.py:40`: remove `RateLimited` from the no-retry tuple | **KILLED** | both `test_rate_limit_*` + the gather test (3 failures) |
| M4 | `gather.py:993`: delete `except RateLimited: raise` | **KILLED** | `test_gather_rate_limit_during_llm_alignment_propagates_and_does_not_flag` |
| M5 | `_run` returncode branch: remove `capture_failure` | **KILLED** | `test_a_failure_is_captured_when_a_capture_dir_is_set` |
| M6 | `_run` `is_error` branch: remove `capture_failure` | **SURVIVED** | — |
| M7 | `_run` not-JSON branch: remove `capture_failure` | **SURVIVED** | — |
| M8 | `gather.py`: keep the clause but `pass` instead of `raise` | **KILLED** | the same gather test |

**Pinned:** all five behavioural constraints (classify on both classifying branches;
no-retry in `_with_transport_retry`; re-raise in gather — and M8 shows the gather test
pins the *raise*, not merely the presence of a clause).

**Unpinned:** `capture_failure` on the `is_error` branch (`claude_cli.py:141`) and on
the not-JSON branch (`claude_cli.py:137`). Both can be deleted with a green suite.

---

## 5. The Task 4b test specifically (`test_stage_gather.py:269-290`)

- **It does reach the fallback branch, and cannot pass for the wrong reason.**
  `align_provider` is consumed at exactly one call site (`gather.py:988`), and
  `FakeProvider.complete` appends to `.calls` *before* serving the queued exception
  (`fake.py:21-24`), so `assert align_fake.calls` at line 289 is a genuine
  branch-entry proof. Better still, the failure mode is self-detecting: if the fixture
  ever stopped producing sub-threshold coverage, no LLM call would happen, no
  `RateLimited` would be raised, and `pytest.raises` would fail — the test cannot go
  green while silently skipping the branch.
- **Both halves are asserted.** `pytest.raises(RateLimited)` for propagation, and
  `not sws.show.exists()` for the persisted-damage half. The latter is a *superset* of
  the brief's "no `low-confidence structure alignment` flag": `write_artifact(show_ws.show, …)`
  at `gather.py:1138` is the only persistence in `run_gather` and sits ~145 lines after
  the branch, so an abort here means nothing is written. Given the harm is
  specifically a file on disk that `should_run` then freezes, asserting on the file is
  the more faithful check than asserting on a returned object.

---

## Findings

**Important-1 — `capture_failure` on the `is_error` branch is unpinned**
(`packages/herder/src/herder/claude_cli.py:141`; mutation M6 survives). This is the
capture site the feature exists for: `failures.py:1-8` says the whole point is that the
envelope's structured fields (`api_error_status`, `subtype`, `terminal_reason`) are gone
by the time the caller sees 500 characters of `_error_detail` — and those fields live in
the `is_error` envelope, not on the exit-code path that *is* pinned. Two lines fix it
(reuse `test_a_failure_is_captured_when_a_capture_dir_is_set` with the envelope
`FakeProc`, as `test_session_limit_in_an_error_envelope_*` already builds). Same
applies, less sharply, to the not-JSON branch (M7). Test-only; does not block the batch
and can land with Task 7, where `set_capture_dir` first gets a production caller.

**Minor-1 — the gather comment forward-references behaviour that does not exist yet**
(`packages/llama/src/llama/stages/gather.py:998`): "Let it reach `_execute`, which pauses
instead." Today `cli.py:237` catches it as a per-show failure and continues to the next
show, which will hit the same wall. True only after Task 7. Fine within a phase; worth a
glance at the end of the phase to confirm it became true.

**Minor-2 — the not-JSON branch's lack of `classify` is undocumented**
(`claude_cli.py:136-138`). The omission is defensible (only reachable at exit 0), but a
reader comparing the three branches sees two classify and one not, with nothing saying
why. One clause in a comment, or classify there too — either resolves it.

**Minor-3 — one failure path raises with no capture at all**
(`claude_cli.py:146-148`, "claude output has no string 'result' field"). That message
carries zero diagnostic content, so it is the failure most in need of the raw envelope,
and it is the only `_run` raise site with no `capture_failure`.

**Minor-4 — `TimeoutExpired` is not captured** (`claude_cli.py:125-126`). Skipping
`classify` there is right, but `subprocess.TimeoutExpired` carries `.stdout`/`.stderr`
(text mode, `capture_output=True`), and `capture_failure` is duck-typed on exactly those
attributes plus `returncode` — so `capture_failure(cmd, e)` would work and would capture
a 900 s hang, which is otherwise undiagnosable. Optional.

**Minor-5 — the three raise sites in `_run` are near-identical** (127-133, 139-145, and
the bare 146-148). Two blocks are byte-identical apart from the message expression. The
repetition is small enough to live with and matches the file's flat style, but it has
already cost something: the two divergences this review found (Minor-3, Important-1's
sibling M7) are exactly the kind a shared

```python
def _fail(cmd, proc, message) -> NoReturn:
    capture_failure(cmd, proc)
    limited = classify(message)
    raise limited if limited is not None else HerderError(message)
```

would make impossible. Optional refactor, not a defect.

**Minor-6 — import-source inconsistency** (`gather.py:7-8`): `HerderError, TaskFailed,
run_json_task` come from `herder`, `RateLimited` from `herder.limits`, though
`herder/__init__.py:2` re-exports it. `tasks.py`/`claude_cli.py` *must* use the submodule
(circular import); `gather.py` need not. Cosmetic.

**Minor-7 — continuation indent** (`test_stage_gather.py:288`): `align_provider=align_fake)`
is two columns short of the open paren. No linter is configured in this repo, so this is
a nit only.

**Informational (out of scope)** — the invariant is `claude_cli`-specific. `openrouter.py:37`
raises a plain `HerderError` for any non-200, so an HTTP 429 there is still retried 3×
and then fails the show. Correct for this batch (the design targets the Claude
subscription window); noting it as the symmetric site if that backend is ever run under
a limit.

**Non-findings, checked:** `herder` imports nothing from `llama`/`emcee` (all three
changes respect the direction). No new dependencies. Tests are offline, use `tmp_path`,
patch `subprocess.run`/`tasks._sleep`, and read no wall clock — `RateLimited` is
constructed directly in the tests rather than via `classify`, so nothing depends on
`datetime.now`. Mid-file section imports in the two herder test files match an
established convention (12 other test files do the same). The implementer's deviation
from the brief's `test_gather.py` → the real `test_stage_gather.py` is correct; no such
file as `test_gather.py` exists.

---

## Tree state

**The tree is clean.** Every mutation was applied in memory and the original bytes
rewritten in a `finally`. Verified after the run: `git status --porcelain` empty,
`git diff --stat` empty, full suite `1681 passed, 7 deselected` — identical to the
pre-review baseline. No edits, no commits, no subagents.
